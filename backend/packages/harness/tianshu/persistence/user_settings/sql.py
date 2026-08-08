"""Per-user settings overrides.

Each user owns zero or more override rows in the ``user_settings``
table. The gateway merges them over the server-side defaults
registered in :mod:`tianshu.settings.defaults`; a section without a
row resolves to the default.

The repository mirrors :mod:`tianshu.persistence.user_models.sql`:
async sessions, one row per ``(user_id, key)``, no secrets involved.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from tianshu.persistence.engine import get_session_factory
from tianshu.persistence.user_settings.model import UserSettingsRow


class UserSettingsRepository:
    """Persistence facade for the user_settings table."""

    @staticmethod
    def _new_id() -> str:
        return uuid.uuid4().hex

    @staticmethod
    def _now() -> datetime:
        return datetime.now(UTC)

    @staticmethod
    def _row_to_dict(row: UserSettingsRow) -> dict[str, Any]:
        return {
            "user_id": row.user_id,
            "key": row.key,
            "value": row.value or {},
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }

    @staticmethod
    def _require_factory() -> AsyncSession:  # type: ignore[type-arg]
        factory = get_session_factory()
        if factory is None:
            raise RuntimeError("Database session factory is not initialised")
        return factory

    async def list_for_user(self, user_id: str) -> dict[str, dict[str, Any]]:
        """Return ``{key: value}`` overrides for a user."""
        factory = self._require_factory()
        async with factory() as session:  # type: ignore[union-attr]
            rows = (
                await session.execute(
                    select(UserSettingsRow).where(UserSettingsRow.user_id == user_id)
                )
            ).scalars().all()
            return {row.key: row.value or {} for row in rows}

    async def get(self, user_id: str, key: str) -> dict[str, Any] | None:
        """Return the raw override value for one section, or None."""
        factory = self._require_factory()
        async with factory() as session:  # type: ignore[union-attr]
            row = (
                await session.execute(
                    select(UserSettingsRow).where(
                        UserSettingsRow.user_id == user_id,
                        UserSettingsRow.key == key,
                    )
                )
            ).scalar_one_or_none()
            return dict(row.value) if row is not None and row.value else None

    async def upsert(
        self,
        *,
        user_id: str,
        key: str,
        value: dict[str, Any],
    ) -> dict[str, Any]:
        """Insert or merge-replace the override for ``(user_id, key)``.

        ``value`` must already be validated/normalised by the defaults
        registry -- the repository stores it verbatim.
        """
        factory = self._require_factory()
        async with factory() as session:  # type: ignore[union-attr]
            row = (
                await session.execute(
                    select(UserSettingsRow).where(
                        UserSettingsRow.user_id == user_id,
                        UserSettingsRow.key == key,
                    )
                )
            ).scalar_one_or_none()
            now = self._now()
            if row is None:
                row = UserSettingsRow(
                    id=self._new_id(),
                    user_id=user_id,
                    key=key,
                    value=value,
                    created_at=now,
                    updated_at=now,
                )
                session.add(row)
            else:
                row.value = value
                row.updated_at = now
            await session.commit()
            await session.refresh(row)
            return dict(row.value)

    async def delete(self, *, user_id: str, key: str) -> bool:
        """Remove the override, falling back to defaults. Returns True if a row was removed."""
        factory = self._require_factory()
        async with factory() as session:  # type: ignore[union-attr]
            result = await session.execute(
                delete(UserSettingsRow).where(
                    UserSettingsRow.user_id == user_id,
                    UserSettingsRow.key == key,
                )
            )
            await session.commit()
            return result.rowcount > 0
