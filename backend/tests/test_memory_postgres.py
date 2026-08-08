"""Live-PostgreSQL tests for the deermem PostgreSQL memory backend.

Replaces the deleted SQLite/FTS5 retrieval-adapter tests
(``test_memory_retrieval_adapter.py``): facts, summaries, and search now all
live in PostgreSQL (``PostgresMemoryStorage``), so the retrieval behaviour that
used to be covered by a derived FTS5 index is covered here through the storage
surface and the DeerMem-level ``warm_retrieval`` / lazy-warm plumbing.

Requires ``TIANSHU_TEST_POSTGRES_URL`` (the repo convention for live-PostgreSQL
tests, see ``test_pg_schema_integration.py``); skipped otherwise. Each test gets
an isolated temporary schema via ``deermem_pg_backend_config``.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from unittest.mock import MagicMock

import pytest

from tianshu.agents.memory.backends.deermem.deer_mem import DeerMem
from tianshu.agents.memory.backends.deermem.deermem.config import DeerMemConfig
from tianshu.agents.memory.backends.deermem.deermem.core.pg_storage import PostgresMemoryStorage
from tianshu.agents.memory.backends.deermem.deermem.core.storage import (
    MemoryFactRevisionConflict,
    MemoryManifestRevisionConflict,
    create_empty_memory,
)


def _fact(fact_id: str, content: str, *, category: str = "context", confidence: float = 0.8) -> dict:
    return {
        "id": fact_id,
        "content": content,
        "category": category,
        "confidence": confidence,
        "createdAt": "2026-07-21T00:00:00Z",
        "source": {"type": "test", "threadId": None},
    }


def _storage(deermem_pg_backend_config: dict) -> PostgresMemoryStorage:
    return PostgresMemoryStorage(DeerMemConfig(**deermem_pg_backend_config))


def _scope(user_id: str, agent_name: str) -> dict[str, str]:
    return {"userId": user_id, "agentName": agent_name}


class TestPostgresMemoryStorage:
    def test_save_and_load_roundtrip(self, deermem_pg_backend_config: dict) -> None:
        storage = _storage(deermem_pg_backend_config)
        try:
            memory = create_empty_memory()
            memory["user"]["workContext"] = {"summary": "alice profile", "updatedAt": "now"}
            assert storage.save(memory, user_id="alice") is True
            loaded = storage.load(user_id="alice")
            assert loaded["user"]["workContext"]["summary"] == "alice profile"
            assert loaded["revision"] == 1
        finally:
            storage.close()

    def test_agent_fact_roundtrip(self, deermem_pg_backend_config: dict) -> None:
        storage = _storage(deermem_pg_backend_config)
        try:
            result = storage.apply_changes(
                {"upserts": [_fact("one", "alpha beta")]},
                user_id="alice",
                agent_name="agent-a",
            )
            assert result["revision"] == 1
            assert [fact["id"] for fact in result["upsertedFacts"]] == ["one"]
            stored = storage.get_fact("one", user_id="alice", agent_name="agent-a")
            assert stored is not None and stored["content"] == "alpha beta"
        finally:
            storage.close()

    def test_apply_changes_bumps_shared_manifest_revision(self, deermem_pg_backend_config: dict) -> None:
        storage = _storage(deermem_pg_backend_config)
        try:
            first = storage.apply_changes({"upserts": [_fact("one", "first")]}, user_id="alice", agent_name="agent-a")
            second = storage.apply_changes({"upserts": [_fact("two", "second")]}, user_id="alice", agent_name="agent-a")
            assert first["revision"] == 1
            assert second["revision"] == 2
        finally:
            storage.close()

    def test_manifest_revision_conflict_fails_fast(self, deermem_pg_backend_config: dict) -> None:
        storage = _storage(deermem_pg_backend_config)
        try:
            storage.apply_changes({"upserts": [_fact("one", "first")]}, user_id="alice", agent_name="agent-a")
            with pytest.raises(MemoryManifestRevisionConflict):
                storage.apply_changes(
                    {"upserts": [_fact("two", "second")]},
                    user_id="alice",
                    agent_name="agent-a",
                    expected_manifest_revision=0,
                )
        finally:
            storage.close()

    def test_fact_revision_conflict_fails_fast(self, deermem_pg_backend_config: dict) -> None:
        storage = _storage(deermem_pg_backend_config)
        try:
            storage.apply_changes({"upserts": [_fact("one", "first")]}, user_id="alice", agent_name="agent-a")
            with pytest.raises(MemoryFactRevisionConflict):
                storage.apply_changes(
                    {"upserts": [_fact("one", "first")], "upsertRevisions": {"one": 5}},
                    user_id="alice",
                    agent_name="agent-a",
                )
        finally:
            storage.close()

    def test_user_isolation_same_fact_id_does_not_leak(self, deermem_pg_backend_config: dict) -> None:
        storage = _storage(deermem_pg_backend_config)
        try:
            storage.apply_changes({"upserts": [_fact("same", "Alice private alpha")]}, user_id="alice", agent_name="__default__")
            storage.apply_changes({"upserts": [_fact("same", "Bob private beta")]}, user_id="bob", agent_name="__default__")
            alice = storage.search_facts("alpha", scopes=[_scope("alice", "__default__")])
            bob = storage.search_facts("alpha", scopes=[_scope("bob", "__default__")])
            assert [item["fact"]["content"] for item in alice] == ["Alice private alpha"]
            assert bob == []
        finally:
            storage.close()

    def test_search_is_case_insensitive_and_ranked(self, deermem_pg_backend_config: dict) -> None:
        storage = _storage(deermem_pg_backend_config)
        try:
            storage.apply_changes(
                {
                    "upserts": [
                        _fact("low", "python deployment preference", confidence=0.4),
                        _fact("high", "Python deployment context", confidence=0.9),
                    ]
                },
                user_id="alice",
                agent_name="agent-a",
            )
            results = storage.search_facts("PYTHON", scopes=[_scope("alice", "agent-a")], top_k=5)
            assert [item["fact"]["id"] for item in results] == ["high", "low"]
            assert all(item["matchType"] == "postgres" for item in results)
        finally:
            storage.close()

    def test_user_global_summaries_and_no_auth_scope(self, deermem_pg_backend_config: dict) -> None:
        storage = _storage(deermem_pg_backend_config)
        try:
            memory = create_empty_memory()
            memory["user"]["workContext"] = {"summary": "no-auth profile", "updatedAt": "now"}
            # user_id=None (no-auth) maps to a deterministic '' sentinel row
            assert storage.save(memory, user_id=None) is True
            loaded = storage.load(user_id=None)
            assert loaded["user"]["workContext"]["summary"] == "no-auth profile"
            assert loaded["revision"] == 1
            # a real user scope never sees the no-auth sentinel summaries
            assert storage.load(user_id="bob")["user"]["workContext"]["summary"] == ""
        finally:
            storage.close()

    def test_clear_all_removes_summaries_and_every_agent_fact(self, deermem_pg_backend_config: dict) -> None:
        storage = _storage(deermem_pg_backend_config)
        try:
            memory = create_empty_memory()
            memory["user"]["workContext"] = {"summary": "shared", "updatedAt": "now"}
            storage.save(memory, user_id="alice")
            storage.apply_changes({"upserts": [_fact("one", "default fact")]}, user_id="alice", agent_name="__default__")
            storage.apply_changes({"upserts": [_fact("two", "custom fact")]}, user_id="alice", agent_name="custom-agent")
            cleared = storage.clear_all(user_id="alice")
            assert cleared["user"]["workContext"]["summary"] == ""
            assert cleared["facts"] == []
            assert storage.list_facts(user_id="alice", agent_name="custom-agent") == []
        finally:
            storage.close()

    def test_capabilities_and_retrieval_status(self, deermem_pg_backend_config: dict) -> None:
        storage = _storage(deermem_pg_backend_config)
        try:
            assert storage.retrieval_status() == {"configured": True, "mode": "postgres_sql"}
            assert {"postgres", "retrieval", "fact-repository"} <= storage.capabilities()
            # SQL-native: rebuild is a cheap count, never fatal
            storage.apply_changes({"upserts": [_fact("one", "indexed fact")]}, user_id="alice", agent_name="agent-a")
            assert storage.rebuild_index()["indexed"] >= 1
        finally:
            storage.close()

    def test_concurrent_upserts_are_searchable(self, deermem_pg_backend_config: dict) -> None:
        storage = _storage(deermem_pg_backend_config)

        def write(index: int) -> None:
            storage.apply_changes({"upserts": [_fact(f"fact-{index}", f"concurrent memory item {index}")]}, user_id="alice", agent_name="agent-a")

        try:
            with ThreadPoolExecutor(max_workers=8) as pool:
                list(pool.map(write, range(20)))
            results = storage.search_facts("concurrent memory", scopes=[_scope("alice", "agent-a")], top_k=20)
            assert {item["fact"]["id"] for item in results} == {f"fact-{index}" for index in range(20)}
        finally:
            storage.close()


class TestDeerMemRetrieval:
    """DeerMem-level retrieval plumbing against the PostgreSQL backend (was FTS5)."""

    def test_warm_retrieval_rebuilds_the_complete_index(self, deermem_pg_backend_config: dict) -> None:
        manager = DeerMem(backend_config={**deermem_pg_backend_config, "token_counting": "char"})
        _, fact_id = manager.create_fact("warm retrieval fact", user_id="alice")
        assert manager.warm_retrieval()
        assert any(fact["id"] == fact_id for fact in manager.search("warm", user_id="alice"))

    def test_warm_retrieval_accepts_partial_fact_failures(self, deermem_pg_backend_config: dict) -> None:
        manager = DeerMem(backend_config={**deermem_pg_backend_config, "token_counting": "char"})
        manager._storage.rebuild_index = lambda scopes=None: {"supported": True, "indexed": 2, "failed": 1}  # type: ignore[method-assign]
        assert manager.warm_retrieval()
        assert manager._retrieval_fully_warmed

    def test_warm_retrieval_retries_after_fatal_rebuild_failure(self, deermem_pg_backend_config: dict) -> None:
        manager = DeerMem(backend_config={**deermem_pg_backend_config, "token_counting": "char"})
        manager._storage.rebuild_index = lambda scopes=None: {"supported": True, "indexed": 0, "failed": 1, "fatal": True}  # type: ignore[method-assign]
        assert not manager.warm_retrieval()
        assert not manager._retrieval_fully_warmed

    def test_lazy_warm_rebuilds_each_requested_scope(self, deermem_pg_backend_config: dict) -> None:
        manager = DeerMem(backend_config={**deermem_pg_backend_config, "token_counting": "char"})
        calls: list[list[dict[str, str | None]]] = []
        manager._storage.rebuild_index = lambda scopes=None: calls.append(scopes or []) or {"supported": True, "failed": 0}  # type: ignore[method-assign]
        scopes = [{"userId": "alice", "agentName": "a"}, {"userId": "bob", "agentName": "b"}]
        manager._ensure_retrieval_scopes(scopes)
        assert calls == [[scopes[0]], [scopes[1]]]

    def test_lazy_warm_does_not_retry_partial_fact_failures(self, deermem_pg_backend_config: dict) -> None:
        manager = DeerMem(backend_config={**deermem_pg_backend_config, "token_counting": "char"})
        rebuild = MagicMock(return_value={"supported": True, "indexed": 2, "failed": 1})
        manager._storage.rebuild_index = rebuild  # type: ignore[method-assign]
        scopes = [{"userId": "alice", "agentName": "a"}]
        manager._ensure_retrieval_scopes(scopes)
        manager._ensure_retrieval_scopes(scopes)
        rebuild.assert_called_once_with(scopes)

    def test_deermem_close_releases_retrieval_connection(self, deermem_pg_backend_config: dict) -> None:
        manager = DeerMem(backend_config={**deermem_pg_backend_config, "token_counting": "char"})
        close_storage = MagicMock()
        manager._storage.close = close_storage  # type: ignore[attr-defined]
        manager.close()
        close_storage.assert_called_once_with()

    def test_create_and_restart_persist_across_instances(self, deermem_pg_backend_config: dict) -> None:
        """Two DeerMem instances sharing one schema see the same facts (restart)."""
        config = {**deermem_pg_backend_config, "token_counting": "char"}
        manager = DeerMem(backend_config=config)
        try:
            _, fact_id = manager.create_fact("PostgreSQL retrieval survives restart", category="knowledge", user_id="alice")
            assert fact_id is not None
            assert any(fact["id"] == fact_id for fact in manager.search("restart", user_id="alice"))

            restarted = DeerMem(backend_config=config)
            try:
                assert any(fact["id"] == fact_id for fact in restarted.search("survives restart", user_id="alice"))
            finally:
                restarted.close()
        finally:
            manager.close()
