"""SQL repository for the per-user MCP server registry (``user_mcp`` table).

Mirrors ``persistence.user_models.sql`` in shape: the gateway routers
consuming this repository are async (FastAPI endpoints), so we use
``AsyncSession`` and ``await session.commit()``.

Secret handling
---------------
``env`` may carry credentials for stdio servers (and could carry headers
for remote servers later). Following the ``user_models`` dual-surface
convention, the API-facing helpers (``list_for_user`` / ``get``) return
``env`` with every value masked to ``***``, while the runtime-facing
``get_all_for_runtime`` returns the real values so tool building can
actually start the server. No secret is ever logged or echoed to the
client.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from tianshu.persistence.engine import get_session_factory
from tianshu.persistence.user_mcp.model import UserMCPServerRow

logger = logging.getLogger(__name__)

# Masked placeholder for secret-bearing fields returned to the API client.
_MASKED_VALUE = "***"


class UserMCPServerRepository:
    """Persistence facade for the user_mcp table."""

    def __init__(self) -> None:
        self._now = lambda: datetime.now(UTC)

    @staticmethod
    def _new_id() -> str:
        return uuid.uuid4().hex

    def _row_to_dict(self, row: UserMCPServerRow, *, mask_env: bool = True) -> dict[str, Any]:
        env = row.env or None
        if mask_env and env:
            env = {key: _MASKED_VALUE for key in env}
        return {
            "id": row.id,
            "user_id": row.user_id,
            "name": row.name,
            "display_name": row.display_name,
            "description": row.description,
            "transport": row.transport,
            "command": row.command,
            "args": row.args or None,
            "env": env,
            "env_set": bool(row.env),
            "url": row.url,
            "tool_name_prefix": row.tool_name_prefix,
            "tool_call_timeout": row.tool_call_timeout,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }

    def _row_to_runtime_dict(self, row: UserMCPServerRow) -> dict[str, Any]:
        """Raw row shape consumed by the MCP tool builder (real env values)."""
        return {
            "name": row.name,
            "display_name": row.display_name,
            "transport": row.transport,
            "command": row.command,
            "args": row.args,
            "env": row.env,
            "url": row.url,
            "tool_name_prefix": row.tool_name_prefix,
            "tool_call_timeout": row.tool_call_timeout,
        }

    def _require_factory(self) -> "AsyncSession":  # type: ignore[type-arg]
        factory = get_session_factory()
        if factory is None:
            raise RuntimeError("Database session factory is not initialised")
        return factory

    async def list_for_user(self, user_id: str) -> list[dict[str, Any]]:
        factory = self._require_factory()
        async with factory() as session:  # type: ignore[union-attr]
            rows = (
                await session.execute(
                    select(UserMCPServerRow)
                    .where(UserMCPServerRow.user_id == user_id)
                    .order_by(UserMCPServerRow.name)
                )
            ).scalars().all()
            return [self._row_to_dict(r) for r in rows]

    async def get(self, user_id: str, name: str) -> dict[str, Any] | None:
        factory = self._require_factory()
        async with factory() as session:  # type: ignore[union-attr]
            row = (
                await session.execute(
                    select(UserMCPServerRow).where(
                        UserMCPServerRow.user_id == user_id,
                        UserMCPServerRow.name == name,
                    )
                )
            ).scalar_one_or_none()
            return self._row_to_dict(row) if row is not None else None

    async def get_all_for_runtime(self, user_id: str) -> list[dict[str, Any]]:
        """Return every row of *user_id* with real env values.

        Used by the runtime MCP resolver to build tools. Callers must not
        log or persist the returned values.
        """
        factory = self._require_factory()
        async with factory() as session:  # type: ignore[union-attr]
            rows = (
                await session.execute(
                    select(UserMCPServerRow)
                    .where(UserMCPServerRow.user_id == user_id)
                    .order_by(UserMCPServerRow.name)
                )
            ).scalars().all()
            return [self._row_to_runtime_dict(r) for r in rows]

    async def create(
        self,
        *,
        user_id: str,
        name: str,
        transport: str,
        command: str | None = None,
        args: list[str] | None = None,
        env: dict[str, Any] | None = None,
        url: str | None = None,
        display_name: str | None = None,
        description: str | None = None,
        tool_name_prefix: bool = True,
        tool_call_timeout: float | None = None,
    ) -> dict[str, Any]:
        now = self._now()
        factory = self._require_factory()
        async with factory() as session:  # type: ignore[union-attr]
            row = UserMCPServerRow(
                id=self._new_id(),
                user_id=user_id,
                name=name,
                display_name=display_name,
                description=description,
                transport=transport,
                command=command,
                args=args,
                env=env,
                url=url,
                tool_name_prefix=tool_name_prefix,
                tool_call_timeout=tool_call_timeout,
                created_at=now,
                updated_at=now,
            )
            session.add(row)
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
                raise
            await session.refresh(row)
            return self._row_to_dict(row)

    # Fields a PATCH may update. Every key maps 1:1 to a ``UserMCPServerRow``
    # column, so a value of ``None`` legitimately clears the column.
    ALLOWED_UPDATE_FIELDS = frozenset(
        {
            "display_name",
            "description",
            "transport",
            "command",
            "args",
            "env",
            "url",
            "tool_name_prefix",
            "tool_call_timeout",
        }
    )

    async def update(
        self,
        *,
        user_id: str,
        name: str,
        fields: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Partial update with explicit present-value semantics.

        Only the keys present in *fields* are written; ``None`` clears the
        column (e.g. ``{"url": None}`` when switching stdio → sse). Keys not
        in :attr:`ALLOWED_UPDATE_FIELDS` raise ``ValueError`` so a caller bug
        cannot mutate an unexpected column.
        """
        unknown = set(fields) - self.ALLOWED_UPDATE_FIELDS
        if unknown:
            raise ValueError(f"Unknown user_mcp update field(s): {sorted(unknown)}")
        factory = self._require_factory()
        async with factory() as session:  # type: ignore[union-attr]
            row = (
                await session.execute(
                    select(UserMCPServerRow).where(
                        UserMCPServerRow.user_id == user_id,
                        UserMCPServerRow.name == name,
                    )
                )
            ).scalar_one_or_none()
            if row is None:
                return None
            for key, value in fields.items():
                setattr(row, key, value)
            row.updated_at = self._now()
            await session.commit()
            await session.refresh(row)
            return self._row_to_dict(row)

    async def delete(self, *, user_id: str, name: str) -> bool:
        factory = self._require_factory()
        async with factory() as session:  # type: ignore[union-attr]
            rows = (
                await session.execute(
                    select(UserMCPServerRow).where(
                        UserMCPServerRow.user_id == user_id,
                        UserMCPServerRow.name == name,
                    )
                )
            ).scalars().all()
            if not rows:
                return False
            for row in rows:
                await session.delete(row)
            await session.commit()
            return True

    async def count_for_user(self, user_id: str) -> int:
        factory = self._require_factory()
        async with factory() as session:  # type: ignore[union-attr]
            from sqlalchemy import func

            return int(
                (
                    await session.execute(
                        select(func.count())
                        .select_from(UserMCPServerRow)
                        .where(UserMCPServerRow.user_id == user_id)
                    )
                ).scalar_one()
            )
