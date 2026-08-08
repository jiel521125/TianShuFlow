"""SQL repository for user-defined model configurations.

Mirrors ``persistence.agents.sql`` in shape but speaks the project's
async session dialect directly -- the agents store happens to be
synchronous because the callers are sync (filesystem paths). The
gateway routers that consume this repository are async (FastAPI
endpoints), so we use ``AsyncSession`` and ``await session.commit()``
etc.

Field encryption
----------------
``api_key`` is encrypted-at-rest when the server has been configured
with ``TIANSHU_FIELD_ENCRYPTION_KEY`` (any non-empty string). The
key is fed through SHA-256 → base64-32 to derive a Fernet key, then
values are tagged with the ``fernet:v1:`` prefix on write and
stripped on read. If the environment variable is unset, secrets are
stored in the clear -- acceptable for local dev / no-auth
deployments but never for multi-tenant.

Public surfaces
---------------
The repository never returns ``api_key`` to callers -- it returns a
redacted ``api_key_set`` boolean instead, mirroring the convention
already used by channel connections.
"""

from __future__ import annotations

import base64
import hashlib
import logging
import os
import uuid
from datetime import UTC, datetime
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from tianshu.persistence.engine import get_session_factory
from tianshu.persistence.user_models.model import UserModelRow

logger = logging.getLogger(__name__)


class ApiKeyCipher:
    """Encrypts API keys before they are persisted."""

    def __init__(self, fernet: Fernet) -> None:
        self._fernet = fernet

    @classmethod
    def from_passphrase(cls, passphrase: str) -> ApiKeyCipher:
        """Derive a Fernet key from any passphrase via SHA-256 + base64-32.

        Uses the same derivation as
        :class:`tianshu.persistence.channel_connections.sql.ChannelCredentialCipher`
        so we could share a single key across both stores in the future.
        """
        digest = hashlib.sha256(passphrase.encode("utf-8")).digest()
        return cls(Fernet(base64.urlsafe_b64encode(digest)))

    def encrypt(self, value: str | None) -> str | None:
        if value is None:
            return None
        return "fernet:v1:" + self._fernet.encrypt(value.encode("utf-8")).decode("ascii")

    def decrypt(self, value: str | None) -> str | None:
        if value is None:
            return None
        token = value.removeprefix("fernet:v1:")
        try:
            return self._fernet.decrypt(token.encode("ascii")).decode("utf-8")
        except (InvalidToken, ValueError):
            logger.warning("Failed to decrypt user_model api_key -- returning as-is")
            return value


def get_api_key_cipher() -> ApiKeyCipher | None:
    """Build an :class:`ApiKeyCipher` from the environment, if configured.

    Returns ``None`` when ``TIANSHU_FIELD_ENCRYPTION_KEY`` is unset,
    signalling that secrets must be stored in the clear. Cached for
    the life of the process.
    """
    passphrase = os.environ.get("TIANSHU_FIELD_ENCRYPTION_KEY")
    if not passphrase:
        return None
    return ApiKeyCipher.from_passphrase(passphrase)


class UserModelRepository:
    """Persistence facade for the user_models table."""

    def __init__(self, cipher: ApiKeyCipher | None = None) -> None:
        self._cipher = cipher

    @staticmethod
    def _new_id() -> str:
        return uuid.uuid4().hex

    @staticmethod
    def _now() -> datetime:
        return datetime.now(UTC)

    def _encrypt_secret(self, value: str | None) -> str | None:
        if value is None:
            return None
        if self._cipher is None:
            return value
        return self._cipher.encrypt(value)

    def _decrypt_secret(self, value: str | None) -> str | None:
        if value is None or self._cipher is None:
            return value
        return self._cipher.decrypt(value)

    def _row_to_dict(self, row: UserModelRow) -> dict[str, Any]:
        data = {
            "id": row.id,
            "user_id": row.user_id,
            "name": row.name,
            "display_name": row.display_name,
            "description": row.description,
            "provider": row.provider,
            "api_key_set": bool(row.api_key),
            "base_url": row.base_url,
            "model": row.model,
            "parameters": row.parameters or {},
            "supports_thinking": row.supports_thinking,
            "supports_reasoning_effort": row.supports_reasoning_effort,
            "context_window": row.context_window,
            "enabled": row.enabled,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }
        return data

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
                    select(UserModelRow)
                    .where(UserModelRow.user_id == user_id)
                    .order_by(UserModelRow.name)
                )
            ).scalars().all()
            return [self._row_to_dict(r) for r in rows]

    async def get(self, user_id: str, name: str) -> dict[str, Any] | None:
        factory = self._require_factory()
        async with factory() as session:  # type: ignore[union-attr]
            row = (
                await session.execute(
                    select(UserModelRow).where(
                        UserModelRow.user_id == user_id,
                        UserModelRow.name == name,
                    )
                )
            ).scalar_one_or_none()
            return self._row_to_dict(row) if row is not None else None

    async def get_row_for_factory(self, user_id: str, name: str) -> UserModelRow | None:
        """Return the raw ORM row with the api_key decrypted.

        Used by :mod:`tianshu.models.factory` to build a chat model.
        The factory consumes the row immediately and discards it; the
        caller must not log or persist the decrypted value.

        Returns the row as a *detached* snapshot so the caller can
        use it without holding the session open.
        """
        factory = self._require_factory()
        async with factory() as session:  # type: ignore[union-attr]
            row = (
                await session.execute(
                    select(UserModelRow).where(
                        UserModelRow.user_id == user_id,
                        UserModelRow.name == name,
                    )
                )
            ).scalar_one_or_none()
            if row is None:
                return None
            # Decrypt so the consumer (the langchain chat-model ctor)
            # sees a real key. ``expunge`` keeps the session clean.
            row.api_key = self._decrypt_secret(row.api_key)
            session.expunge(row)
            return row

    async def create(
        self,
        *,
        user_id: str,
        name: str,
        provider: str,
        model: str,
        display_name: str | None = None,
        description: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        parameters: dict[str, Any] | None = None,
        supports_thinking: bool = False,
        supports_reasoning_effort: bool = False,
        context_window: int | None = None,
        enabled: bool = True,
    ) -> dict[str, Any]:
        new_id = self._new_id()
        encrypted_key = self._encrypt_secret(api_key)
        now = self._now()
        factory = self._require_factory()
        async with factory() as session:  # type: ignore[union-attr]
            row = UserModelRow(
                id=new_id,
                user_id=user_id,
                name=name,
                display_name=display_name,
                description=description,
                provider=provider,
                api_key=encrypted_key,
                base_url=base_url,
                model=model,
                parameters=parameters or {},
                supports_thinking=supports_thinking,
                supports_reasoning_effort=supports_reasoning_effort,
                context_window=context_window,
                enabled=enabled,
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

    async def update(
        self,
        *,
        user_id: str,
        name: str,
        display_name: str | None = None,
        description: str | None = None,
        set_api_key: tuple[bool, str | None] = (False, None),
        set_base_url: tuple[bool, str | None] = (False, None),
        model: str | None = None,
        parameters: dict[str, Any] | None = None,
        supports_thinking: bool | None = None,
        supports_reasoning_effort: bool | None = None,
        context_window: int | None = None,
        enabled: bool | None = None,
    ) -> dict[str, Any] | None:
        """Partial update.

        ``set_api_key`` / ``set_base_url`` are ``(present, value)``
        tuples so callers can explicitly clear a value (``(True, None)``)
        or leave the field alone (``(False, None)``). Plain ``None``
        would be ambiguous because both "absent" and "clear" use it.
        """
        factory = self._require_factory()
        async with factory() as session:  # type: ignore[union-attr]
            row = (
                await session.execute(
                    select(UserModelRow).where(
                        UserModelRow.user_id == user_id,
                        UserModelRow.name == name,
                    )
                )
            ).scalar_one_or_none()
            if row is None:
                return None
            if display_name is not None:
                row.display_name = display_name
            if description is not None:
                row.description = description
            api_key_present, api_key_value = set_api_key
            if api_key_present:
                row.api_key = self._encrypt_secret(api_key_value)
            base_url_present, base_url_value = set_base_url
            if base_url_present:
                row.base_url = base_url_value
            if model is not None:
                row.model = model
            if parameters is not None:
                row.parameters = parameters
            if supports_thinking is not None:
                row.supports_thinking = supports_thinking
            if supports_reasoning_effort is not None:
                row.supports_reasoning_effort = supports_reasoning_effort
            if context_window is not None:
                row.context_window = context_window
            if enabled is not None:
                row.enabled = enabled
            row.updated_at = self._now()
            await session.commit()
            await session.refresh(row)
            return self._row_to_dict(row)

    async def delete(self, *, user_id: str, name: str) -> bool:
        factory = self._require_factory()
        async with factory() as session:  # type: ignore[union-attr]
            rows = (
                await session.execute(
                    select(UserModelRow).where(
                        UserModelRow.user_id == user_id,
                        UserModelRow.name == name,
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
            return int(
                (
                    await session.execute(
                        select(func.count())
                        .select_from(UserModelRow)
                        .where(UserModelRow.user_id == user_id)
                    )
                ).scalar_one()
            )


# Helpers for constructing partial update payloads.
NO_UPDATE: tuple[bool, str | None] = (False, None)


def set_value(value: str | None) -> tuple[bool, str | None]:
    """Return a partial-update tuple that sets the field to ``value``."""
    return (True, value)


def clear_value(value: str | None = None) -> tuple[bool, str | None]:
    """Return a partial-update tuple that clears the field (sets to ``value``)."""
    return (True, value)