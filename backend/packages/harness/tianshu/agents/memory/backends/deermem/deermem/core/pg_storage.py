"""PostgreSQL-backed memory storage for DeerMem.

All persistent memory state -- user-global summaries, facts, and search --
lives in PostgreSQL. Two tables per configured schema:

- ``memory_documents`` -- one row per ``(user_id, agent_name)`` scope holding
  the user-global summary document (``doc`` JSONB: version/lastUpdated/user/
  history) plus the shared manifest ``revision`` used for optimistic
  concurrency control. ``agent_name`` is ``''`` (empty-string sentinel) for
  the user-global row because PostgreSQL makes primary-key columns NOT NULL.
- ``memory_facts`` -- one row per ``(user_id, agent_name, fact_id)`` holding
  the normalized fact as JSONB. Facts are always scoped to one agent.

Concurrency mirrors the file backend's journal + cross-process lock with the
database's own guarantees: every mutation runs inside a transaction that locks
the scope's ``memory_documents`` row with ``SELECT ... FOR UPDATE``, so two
writers racing for the same scope serialize and the manifest ``revision``
check (``MemoryManifestRevisionConflict``) behaves exactly like the file
backend's expected-revision check. The fact-level revision conflict semantics
(``MemoryFactRevisionConflict``) are identical to the file backend because
both reuse ``storage._normalize_fact``.

Search is SQL-native (ILIKE over content/title), so no derived index is
needed and ``rebuild_index`` is a cheap no-op (the data is already in the
database).

This module must stay import-portable: it intentionally has no ``from
tianshu`` imports (the vendored directory only permits the ABC import in
``deer_mem.py``).
"""

from __future__ import annotations

import copy
import logging
import re
import threading
import uuid
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

from ..config import DeerMemConfig
from .paths import DEFAULT_AGENT_BUCKET
from .storage import (
    DOCUMENT_VERSION,
    MemoryFactRevisionConflict,
    MemoryManifestRevisionConflict,
    MemoryRevisionConflict,
    MemoryStorage,
    MemoryStorageCorruption,
    MemoryStorageError,
    _normalize_fact,
    _scope_dict,
    create_empty_memory,
    utc_now_iso_z,
)

logger = logging.getLogger(__name__)

_SCHEMA_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

_DOCUMENTS_TABLE = "memory_documents"
_FACTS_TABLE = "memory_facts"


def _validate_schema_identifier(schema: str) -> str:
    """Validate a PostgreSQL schema name as a plain identifier."""
    if not _SCHEMA_IDENTIFIER_RE.fullmatch(schema):
        raise ValueError(
            f"memory.backend_config.postgres_schema={schema!r} is not a plain PostgreSQL identifier"
        )
    return schema


def _quote_ident(identifier: str) -> str:
    return f'"{_validate_schema_identifier(identifier)}"'


def _as_scope_key(scope: dict[str, str | None]) -> tuple[str | None, str | None]:
    user_id = scope.get("userId")
    agent_name = scope.get("agentName")
    if user_id is not None and not isinstance(user_id, str):
        raise ValueError("memory scope userId must be a string or null")
    if agent_name is not None and not isinstance(agent_name, str):
        raise ValueError("memory scope agentName must be a string or null")
    return user_id, agent_name


def _db_user_id(user_id: str | None) -> str:
    """Map the no-auth ``None`` scope to a deterministic sentinel.

    The file backend stores the no-auth scope at the storage root; PostgreSQL
    keeps it as a ``''`` user id so the composite primary keys stay unique
    (PostgreSQL treats NULL as distinct in unique constraints).
    """
    return "" if user_id is None else user_id


def _db_agent_name(agent_name: str | None) -> str:
    """Map the user-global ``None`` scope to a deterministic sentinel.

    PostgreSQL adds NOT NULL to every primary-key column, so the user-global
    row (``agent_name=None`` in the file backend) must use a sentinel that no
    real agent name can collide with. Real agent names match ``[A-Za-z0-9-]+``
    and are never empty, so ``''`` is unambiguous.
    """
    return "" if agent_name is None else agent_name


def _document_payload(*, version: str, last_updated: str, user: dict[str, Any], history: dict[str, Any]) -> dict[str, Any]:
    return {
        "version": version,
        "lastUpdated": last_updated,
        "user": user,
        "history": history,
    }


class PostgresMemoryStorage(MemoryStorage):
    """PostgreSQL storage backend implementing the full ``MemoryStorage`` surface.

    Construction is side-effect free; the connection and schema are created
    lazily on first use. A single psycopg connection guarded by a re-entrant
    lock serializes all access (DeerMem runs in a multi-threaded gateway; the
    memory workload is low-frequency).
    """

    def __init__(self, config: DeerMemConfig, retrieval: Any = None):
        if retrieval is not None:
            raise ValueError("PostgresMemoryStorage does not accept a retrieval adapter; search is SQL-native")
        if not config.postgres_url:
            raise ValueError(
                "memory.backend_config.postgres_url is required for the postgres memory storage backend. "
                "Refusing to silently fall back because memory is persistent state."
            )
        self._config = config
        self._schema = (config.postgres_schema or "public").strip() or "public"
        _validate_schema_identifier(self._schema)
        quoted_schema = _quote_ident(self._schema)
        self._documents_table = f"{quoted_schema}.{_DOCUMENTS_TABLE}"
        self._facts_table = f"{quoted_schema}.{_FACTS_TABLE}"
        self._conn: psycopg.Connection[Any] | None = None
        self._lock = threading.RLock()
        self._closed = False

    # ── Connection / schema ────────────────────────────────────────────

    def _ensure_schema(self, conn: psycopg.Connection[Any]) -> None:
        conn.execute(f"CREATE SCHEMA IF NOT EXISTS {_quote_ident(self._schema)}")
        conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {self._documents_table} (
                user_id TEXT NOT NULL,
                agent_name TEXT,
                doc JSONB NOT NULL,
                revision INTEGER NOT NULL,
                PRIMARY KEY (user_id, agent_name)
            )
            """
        )
        conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {self._facts_table} (
                user_id TEXT NOT NULL,
                agent_name TEXT NOT NULL,
                fact_id TEXT NOT NULL,
                fact JSONB NOT NULL,
                PRIMARY KEY (user_id, agent_name, fact_id)
            )
            """
        )
        conn.commit()

    def _connection(self) -> psycopg.Connection[Any]:
        if self._conn is None:
            if self._closed:
                raise MemoryStorageCorruption("PostgresMemoryStorage is closed")
            conn = psycopg.connect(self._config.postgres_url, autocommit=False)
            try:
                self._ensure_schema(conn)
            except Exception:
                conn.close()
                raise
            self._conn = conn
        return self._conn

    # ── Row helpers ────────────────────────────────────────────────────

    def _select_document_row(
        self,
        conn: psycopg.Connection[Any],
        user_id: str | None,
        agent_name: str | None,
        *,
        for_update: bool = False,
    ) -> tuple[dict[str, Any], int] | None:
        lock_clause = " FOR UPDATE" if for_update else ""
        row = conn.execute(
            f"SELECT doc, revision FROM {self._documents_table} WHERE user_id = %s AND agent_name = %s{lock_clause}",
            (_db_user_id(user_id), _db_agent_name(agent_name)),
        ).fetchone()
        if row is None:
            return None
        return row[0], int(row[1])

    @staticmethod
    def _document_from_row(doc: dict[str, Any], revision: int) -> dict[str, Any]:
        return {
            "version": doc.get("version", DOCUMENT_VERSION),
            "revision": revision,
            "lastUpdated": doc.get("lastUpdated", ""),
            "user": copy.deepcopy(doc.get("user", {})),
            "history": copy.deepcopy(doc.get("history", {})),
        }

    def _select_fact(self, conn: psycopg.Connection[Any], user_id: str | None, agent_name: str, fact_id: str) -> dict[str, Any] | None:
        row = conn.execute(
            f"SELECT fact FROM {self._facts_table} WHERE user_id = %s AND agent_name = %s AND fact_id = %s",
            (_db_user_id(user_id), agent_name, fact_id),
        ).fetchone()
        return None if row is None else row[0]

    def _select_facts(self, conn: psycopg.Connection[Any], user_id: str | None, agent_name: str) -> list[dict[str, Any]]:
        rows = conn.execute(
            f"SELECT fact FROM {self._facts_table} WHERE user_id = %s AND agent_name = %s ORDER BY fact_id",
            (_db_user_id(user_id), agent_name),
        ).fetchall()
        return [copy.deepcopy(row[0]) for row in rows]

    def _select_fact_ids(self, conn: psycopg.Connection[Any], user_id: str | None, agent_name: str | None) -> set[str]:
        if agent_name is None:
            return set()
        rows = conn.execute(
            f"SELECT fact_id FROM {self._facts_table} WHERE user_id = %s AND agent_name = %s",
            (_db_user_id(user_id), agent_name),
        ).fetchall()
        return {str(row[0]) for row in rows}

    def _ensure_document_row(self, conn: psycopg.Connection[Any], user_id: str | None, agent_name: str | None) -> None:
        conn.execute(
            f"INSERT INTO {self._documents_table} (user_id, agent_name, doc, revision) VALUES (%s, %s, %s, 0) "
            f"ON CONFLICT (user_id, agent_name) DO NOTHING",
            (
                _db_user_id(user_id),
                _db_agent_name(agent_name),
                Jsonb(_document_payload(version=DOCUMENT_VERSION, last_updated=utc_now_iso_z(), user={}, history={})),
            ),
        )

    # ── Document reads ─────────────────────────────────────────────────

    def _read_document(self, agent_name: str | None = None, *, user_id: str | None = None) -> dict[str, Any]:
        """Load the user-global summary document plus one agent's facts.

        Mirrors the file backend layout: summaries (``user``/``history``), the
        shared manifest ``revision`` and ``lastUpdated`` all live in the
        user-global row (``agent_name=''`` sentinel); facts live in the
        per-agent ``memory_facts`` rows. ``agent_name=None`` returns only the
        global document (empty ``facts``).
        """
        with self._lock:
            conn = self._connection()
            row = self._select_document_row(conn, user_id, None)
            if row is None:
                result = create_empty_memory()
                result["facts"] = self._select_facts(conn, user_id, agent_name) if agent_name is not None else []
            else:
                doc, revision = row
                result = self._document_from_row(doc, revision)
                result["facts"] = self._select_facts(conn, user_id, agent_name) if agent_name is not None else []
            # Close the read transaction: a bare SELECT on an autocommit=False
            # connection would otherwise leave it "idle in transaction", holding
            # ACCESS SHARE locks that block schema DDL (e.g. DROP SCHEMA CASCADE
            # during test teardown) and bloat long-lived gateway connections.
            conn.commit()
            return result

    # ── MemoryStorage ABC ──────────────────────────────────────────────

    def load(self, agent_name: str | None = None, *, user_id: str | None = None) -> dict[str, Any]:
        """Load the current document; the database is the source of truth."""
        return self._read_document(agent_name, user_id=user_id)

    def reload(self, agent_name: str | None = None, *, user_id: str | None = None, _rebuild_retrieval: bool = True) -> dict[str, Any]:
        """Reload from the database (no cache to invalidate)."""
        del _rebuild_retrieval  # SQL-native search needs no derived index
        return self._read_document(agent_name, user_id=user_id)

    # ── Mutations ──────────────────────────────────────────────────────

    def _commit_changes(
        self,
        conn: psycopg.Connection[Any],
        *,
        user_id: str | None,
        agent_name: str | None,
        upserts: list[dict[str, Any]],
        deletes: list[str],
        summaries: dict[str, Any] | None,
        expected_revision: int | None,
        delete_revisions: dict[str, int] | None = None,
        upsert_revisions: dict[str, int | None] | None = None,
    ) -> tuple[dict[str, Any], list[tuple[str, Any, None]]]:
        """Apply one change set inside the caller's transaction.

        The user-global ``memory_documents`` row is locked with ``FOR UPDATE``
        so concurrent writers serialize on the shared manifest revision -- the
        same single-manifest semantics as the file backend (where every agent's
        fact change also bumps the shared ``memory.json`` revision). All writes
        (facts + global summary document + revision bump) commit atomically
        with the transaction -- the PostgreSQL equivalent of the file backend's
        journaled multi-file commit.
        """
        self._ensure_document_row(conn, user_id, None)
        row = self._select_document_row(conn, user_id, None, for_update=True)
        if row is None:  # defensive: the insert above must have created it
            raise MemoryStorageError("PostgreSQL memory document row could not be created")
        current_doc, current_revision = row
        if expected_revision is not None and expected_revision != current_revision:
            raise MemoryManifestRevisionConflict(f"Expected user-memory revision {expected_revision}, found {current_revision}")
        if (upserts or deletes) and agent_name is None:
            raise ValueError("agent_name is required for fact repository changes")

        scope = _scope_dict(user_id, agent_name)
        prepared: dict[str, dict[str, Any]] = {}
        for incoming in upserts:
            if not isinstance(incoming, dict):
                raise ValueError("change_set.upserts must contain fact objects")
            candidate = copy.deepcopy(incoming)
            candidate["id"] = str(candidate.get("id") or f"fact_{uuid.uuid4().hex}")
            fact_id = candidate["id"]
            if fact_id in prepared:
                raise ValueError(f"Duplicate fact id {fact_id!r} in upserts")
            existing = self._select_fact(conn, user_id, agent_name, fact_id)
            if upsert_revisions is not None and fact_id in upsert_revisions:
                expected_fact_revision = upsert_revisions[fact_id]
                if expected_fact_revision is None and existing is not None:
                    raise MemoryFactRevisionConflict(f"Fact {fact_id!r} must not already exist")
                if expected_fact_revision is not None:
                    actual_fact_revision = None if existing is None else existing.get("revision")
                    if actual_fact_revision != expected_fact_revision:
                        raise MemoryFactRevisionConflict(f"Expected fact {fact_id!r} revision {expected_fact_revision}, found {actual_fact_revision}")
            normalized = _normalize_fact(candidate, scope=scope, existing=existing)
            if existing != normalized:
                prepared[fact_id] = normalized

        delete_ids = [str(fact_id) for fact_id in deletes]
        if len(delete_ids) != len(set(delete_ids)):
            raise ValueError("Duplicate fact ids are not allowed in deletes")
        removals: dict[str, dict[str, Any]] = {}
        for fact_id in delete_ids:
            if fact_id in prepared:
                raise ValueError(f"Fact {fact_id!r} cannot be upserted and deleted together")
            existing = self._select_fact(conn, user_id, agent_name, fact_id)
            if existing is None:
                continue
            if delete_revisions and fact_id in delete_revisions and delete_revisions[fact_id] != existing.get("revision"):
                raise MemoryFactRevisionConflict(f"Expected fact {fact_id!r} revision {delete_revisions[fact_id]}, found {existing.get('revision')}")
            removals[fact_id] = existing

        user_section = copy.deepcopy(current_doc.get("user", {}))
        history_section = copy.deepcopy(current_doc.get("history", {}))
        if summaries is not None:
            if not isinstance(summaries, dict):
                raise ValueError("change_set.summaries must be an object")
            if "user" in summaries:
                if not isinstance(summaries["user"], dict):
                    raise ValueError("change_set.summaries.user must be an object")
                user_section.update(copy.deepcopy(summaries["user"]))
            if "history" in summaries:
                if not isinstance(summaries["history"], dict):
                    raise ValueError("change_set.summaries.history must be an object")
                history_section.update(copy.deepcopy(summaries["history"]))
        summaries_changed = user_section != current_doc.get("user", {}) or history_section != current_doc.get("history", {})

        if not prepared and not removals and not summaries_changed:
            return self._document_from_row(current_doc, current_revision), []

        next_revision = current_revision + 1
        db_user = _db_user_id(user_id)
        db_agent = _db_agent_name(agent_name)
        notifications: list[tuple[str, Any, None]] = []
        for fact_id, normalized in prepared.items():
            conn.execute(
                f"INSERT INTO {self._facts_table} (user_id, agent_name, fact_id, fact) VALUES (%s, %s, %s, %s) "
                f"ON CONFLICT (user_id, agent_name, fact_id) DO UPDATE SET fact = EXCLUDED.fact",
                (db_user, db_agent, fact_id, Jsonb(normalized)),
            )
            notifications.append(("upsert", normalized, None))
        for fact_id in removals:
            conn.execute(
                f"DELETE FROM {self._facts_table} WHERE user_id = %s AND agent_name = %s AND fact_id = %s",
                (db_user, db_agent, fact_id),
            )
            notifications.append(("remove", fact_id, None))

        new_doc = _document_payload(version=DOCUMENT_VERSION, last_updated=utc_now_iso_z(), user=user_section, history=history_section)
        conn.execute(
            f"UPDATE {self._documents_table} SET doc = %s, revision = %s WHERE user_id = %s AND agent_name = %s",
            (Jsonb(new_doc), next_revision, db_user, _db_agent_name(None)),
        )
        memory_file = self._document_from_row(new_doc, next_revision)
        return memory_file, notifications

    def save(
        self,
        memory_data: dict[str, Any],
        agent_name: str | None = None,
        *,
        user_id: str | None = None,
        expected_revision: int | None = None,
    ) -> bool:
        """Compatibility full replacement, diffed into per-fact operations."""
        try:
            if not isinstance(memory_data, dict):
                raise ValueError("memory_data must be an object")
            if agent_name is not None and "facts" not in memory_data:
                raise ValueError("memory_data.facts is required for an agent full save")
            facts_raw = memory_data.get("facts", [])
            if not isinstance(facts_raw, list):
                raise ValueError("memory_data.facts must be a list")
            if any(not isinstance(fact, dict) for fact in facts_raw):
                raise ValueError("memory_data.facts must contain only fact objects")
            if agent_name is None and facts_raw:
                raise ValueError("agent_name is required to persist facts")
            with self._lock:
                conn = self._connection()
                try:
                    ids = [str(fact.get("id") or "") for fact in facts_raw]
                    if len(ids) != len(set(ids)):
                        raise ValueError("Duplicate fact ids are not allowed")
                    old_ids = self._select_fact_ids(conn, user_id, agent_name)
                    summaries = None
                    if agent_name is None:
                        summaries = {"user": memory_data.get("user", {}), "history": memory_data.get("history", {})}
                    self._commit_changes(
                        conn,
                        user_id=user_id,
                        agent_name=agent_name,
                        upserts=copy.deepcopy(facts_raw),
                        deletes=sorted(old_ids - set(ids)),
                        summaries=summaries,
                        expected_revision=expected_revision,
                    )
                    conn.commit()
                except MemoryRevisionConflict:
                    conn.rollback()
                    raise
                except (psycopg.Error, ValueError, MemoryStorageCorruption) as exc:
                    conn.rollback()
                    logger.error("Failed to save memory scope %r: %s", (user_id, agent_name), exc)
                    return False
        except MemoryRevisionConflict:
            raise
        except (ValueError, MemoryStorageCorruption) as exc:
            logger.error("Failed to save memory scope %r: %s", (user_id, agent_name), exc)
            return False
        return True

    def apply_changes(
        self,
        change_set: dict[str, Any],
        *,
        user_id: str | None = None,
        agent_name: str | None = None,
        expected_manifest_revision: int | None = None,
        allow_manifest_rebase: bool = False,
    ) -> dict[str, Any]:
        """Commit an incremental change set and return only the applied delta.

        Mirrors ``FileMemoryStorage.apply_changes``: the manifest revision is
        checked inside the row-locked transaction, and a bounded retry loop
        rebases disjoint fact-only change sets when the shared revision moved
        (``allow_manifest_rebase``).
        """
        has_fact_changes = bool(change_set.get("upserts") or change_set.get("deletes"))
        if has_fact_changes and agent_name is None:
            raise ValueError("agent_name is required for fact repository changes")
        summaries = change_set.get("summaries")
        upserts = copy.deepcopy(change_set.get("upserts", []))
        deletes = change_set.get("deletes", [])
        delete_revisions = change_set.get("deleteRevisions")
        upsert_revisions = change_set.get("upsertRevisions")
        if not isinstance(upserts, list) or not isinstance(deletes, list):
            raise ValueError("change_set.upserts and change_set.deletes must be lists")
        if delete_revisions is not None and not isinstance(delete_revisions, dict):
            raise ValueError("change_set.deleteRevisions must be an object")
        if upsert_revisions is not None and not isinstance(upsert_revisions, dict):
            raise ValueError("change_set.upsertRevisions must be an object")

        normalized_upsert_revisions: dict[str, int | None] = {}
        for incoming in upserts:
            if not isinstance(incoming, dict):
                raise ValueError("change_set.upserts must contain fact objects")
            incoming["id"] = str(incoming.get("id") or f"fact_{uuid.uuid4().hex}")
            fact_id = incoming["id"]
            if isinstance(upsert_revisions, dict) and fact_id in upsert_revisions:
                expected_fact_revision = upsert_revisions[fact_id]
            else:
                expected_fact_revision = incoming.get("revision") if "revision" in incoming else None
            if expected_fact_revision is not None and (isinstance(expected_fact_revision, bool) or not isinstance(expected_fact_revision, int) or expected_fact_revision < 1):
                raise ValueError("change_set.upsertRevisions values must be null or integers >= 1")
            normalized_upsert_revisions[fact_id] = expected_fact_revision

        expected = expected_manifest_revision
        notifications: list[tuple[str, Any, None]] = []
        memory_file: dict[str, Any] | None = None
        safe_delete_rebase = not deletes or (isinstance(delete_revisions, dict) and all(str(fact_id) in delete_revisions for fact_id in deletes))
        safe_upsert_rebase = all(str(incoming["id"]) in normalized_upsert_revisions for incoming in upserts)
        for attempt in range(3):
            try:
                with self._lock:
                    conn = self._connection()
                    try:
                        memory_file, notifications = self._commit_changes(
                            conn,
                            user_id=user_id,
                            agent_name=agent_name,
                            upserts=upserts,
                            deletes=[str(fact_id) for fact_id in deletes],
                            summaries=copy.deepcopy(summaries),
                            expected_revision=expected,
                            delete_revisions=copy.deepcopy(delete_revisions),
                            upsert_revisions=normalized_upsert_revisions,
                        )
                        conn.commit()
                    except MemoryRevisionConflict:
                        conn.rollback()
                        raise
                break
            except MemoryManifestRevisionConflict as exc:
                can_rebase = allow_manifest_rebase and has_fact_changes and summaries is None and safe_delete_rebase and safe_upsert_rebase and attempt < 2
                if not can_rebase:
                    raise
                expected = self._current_revision(user_id=user_id, agent_name=agent_name)
                logger.info("Rebasing disjoint memory fact change after revision conflict: %s", exc)
        if memory_file is None:  # defensive: the bounded loop either commits or raises
            raise MemoryStorageError("Memory repository change did not produce a result")
        return {
            "complete": False,
            "version": memory_file.get("version", DOCUMENT_VERSION),
            "revision": memory_file.get("revision", 0),
            "lastUpdated": memory_file.get("lastUpdated", ""),
            "upsertedFacts": [copy.deepcopy(value) for action, value, _ in notifications if action == "upsert" and isinstance(value, dict)],
            "deletedFactIds": [str(value) for action, value, _ in notifications if action == "remove"],
        }

    def _current_revision(self, *, user_id: str | None, agent_name: str | None) -> int:
        del agent_name  # the shared manifest revision lives in the user-global row
        with self._lock:
            conn = self._connection()
            row = conn.execute(
                f"SELECT revision FROM {self._documents_table} WHERE user_id = %s AND agent_name = %s",
                (_db_user_id(user_id), _db_agent_name(None)),
            ).fetchone()
            conn.commit()
            return int(row[0]) if row else 0

    def clear_all(self, *, user_id: str | None = None) -> dict[str, Any]:
        """Clear one user's summaries and every agent fact bucket."""
        with self._lock:
            conn = self._connection()
            try:
                db_user = _db_user_id(user_id)
                conn.execute(f"DELETE FROM {self._facts_table} WHERE user_id = %s", (db_user,))
                self._ensure_document_row(conn, user_id, None)
                row = conn.execute(
                    f"SELECT revision FROM {self._documents_table} WHERE user_id = %s AND agent_name = %s FOR UPDATE",
                    (db_user, _db_agent_name(None)),
                ).fetchone()
                if row is None:  # defensive: the insert above must have created it
                    raise MemoryStorageError("PostgreSQL memory document row could not be created")
                next_revision = int(row[0]) + 1
                empty = create_empty_memory()
                conn.execute(
                    f"UPDATE {self._documents_table} SET doc = %s, revision = %s WHERE user_id = %s AND agent_name = %s",
                    (
                        Jsonb(_document_payload(version=DOCUMENT_VERSION, last_updated=utc_now_iso_z(), user=empty["user"], history=empty["history"])),
                        next_revision,
                        db_user,
                        _db_agent_name(None),
                    ),
                )
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return self.reload(DEFAULT_AGENT_BUCKET, user_id=user_id)

    # ── Fact repository ────────────────────────────────────────────────

    def get_fact(
        self,
        fact_id: str,
        *,
        user_id: str | None = None,
        agent_name: str | None = None,
    ) -> dict[str, Any] | None:
        if agent_name is None:
            raise ValueError("agent_name is required to get a fact")
        with self._lock:
            conn = self._connection()
            fact = self._select_fact(conn, user_id, agent_name, fact_id)
            conn.commit()  # close the read transaction (see _read_document)
        return copy.deepcopy(fact)

    def list_facts(
        self,
        *,
        user_id: str | None = None,
        agent_name: str | None = None,
        filters: dict[str, Any] | None = None,
        cursor: int = 0,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        if cursor < 0 or limit < 1:
            raise ValueError("cursor must be >= 0 and limit must be >= 1")
        if agent_name is None:
            return []
        with self._lock:
            conn = self._connection()
            facts = self._select_facts(conn, user_id, agent_name)
            conn.commit()  # close the read transaction (see _read_document)
        filters = filters or {}
        matched = [fact for fact in facts if all(key in fact and fact.get(key) == value for key, value in filters.items())]
        return copy.deepcopy(matched[cursor : cursor + limit])

    # ── Retrieval (SQL-native) ─────────────────────────────────────────

    def search_facts(
        self,
        query: str,
        *,
        scopes: list[dict[str, str | None]],
        top_k: int = 10,
        mode: str = "hybrid",
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Case-insensitive SQL search over stored fact content and title."""
        del mode  # single SQL strategy; no separate lexical/semantic modes
        query_lower = query.strip().lower()
        if not query_lower or top_k <= 0:
            return []
        filters = filters or {}
        results: list[dict[str, Any]] = []
        with self._lock:
            conn = self._connection()
            for scope in scopes:
                user_id, agent_name = _as_scope_key(scope)
                if agent_name is None:
                    continue
                for fact in self._select_facts(conn, user_id, agent_name):
                    if any(fact.get(key) != value for key, value in filters.items()):
                        continue
                    content = fact.get("content")
                    title = fact.get("title")
                    content_lower = content.lower() if isinstance(content, str) else ""
                    title_lower = title.lower() if isinstance(title, str) else ""
                    if query_lower not in content_lower and query_lower not in title_lower:
                        continue
                    score = float(fact.get("confidence") or 0.5)
                    if query_lower in title_lower:
                        score += 0.25
                    fact["score"] = score
                    results.append({"fact": copy.deepcopy(fact), "score": score, "matchType": "postgres"})
            conn.commit()  # close the read transaction (see _read_document)
        results.sort(key=lambda result: result["score"], reverse=True)
        return results[:top_k]

    def rebuild_index(self, scopes: list[dict[str, str | None]] | None = None) -> dict[str, Any]:
        """No derived index is needed: facts are already in PostgreSQL."""
        with self._lock:
            conn = self._connection()
            if scopes is None:
                indexed = int(conn.execute(f"SELECT COUNT(*) FROM {self._facts_table}").fetchone()[0])
            else:
                indexed = 0
                for scope in scopes:
                    user_id, agent_name = _as_scope_key(scope)
                    if agent_name is None:
                        continue
                    indexed += int(
                        conn.execute(
                            f"SELECT COUNT(*) FROM {self._facts_table} WHERE user_id IS NOT DISTINCT FROM %s AND agent_name = %s",
                            (user_id, agent_name),
                        ).fetchone()[0]
                    )
            conn.commit()  # close the read transaction (see _read_document)
        return {"supported": True, "indexed": indexed, "failed": 0}

    def retrieval_status(self) -> dict[str, Any]:
        return {"configured": True, "mode": "postgres_sql"}

    def capabilities(self) -> set[str]:
        return {"postgres", "sql-facts", "global-summary-json", "revision", "fact-repository", "retrieval"}

    # ── Lifecycle ──────────────────────────────────────────────────────

    def close(self) -> None:
        with self._lock:
            self._closed = True
            if self._conn is not None:
                try:
                    self._conn.close()
                except Exception:  # noqa: BLE001 - best-effort teardown
                    logger.exception("Failed to close the PostgreSQL memory connection")
                self._conn = None
