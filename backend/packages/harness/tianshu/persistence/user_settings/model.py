"""ORM model for per-user settings overrides.

One row per ``(user_id, key)`` user override. ``key`` names a settings
section (``appearance`` | ``notification`` | ``channels`` |
``integrations`` | ``tools``) whose shape and defaults are defined by
:mod:`tianshu.settings.defaults`. The ``value`` JSON object is
validated by that registry before it is persisted, so this table never
holds schema-less garbage.

A row is *visible* only to its owner (``user_id == caller``). Sections
without a row simply resolve to the server-side default.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, DateTime, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from tianshu.persistence.base import Base


class UserSettingsRow(Base):
    __tablename__ = "user_settings"
    # Bind ORM to the application schema when database.backend=postgres
    # (psycopg's server-side prepared statements bypass search_path).
    __table_args__ = (
        UniqueConstraint("user_id", "key", name="uq_user_settings_user_key"),
        {"schema": "tianshu"},
    )

    # Surrogate PK; (user_id, key) is the natural key.
    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: uuid.uuid4().hex
    )

    user_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)

    # Settings section key (validated against the defaults registry).
    key: Mapped[str] = mapped_column(String(64), nullable=False)

    # User override for the section. Validated by
    # ``tianshu.settings.defaults.validate_section_value`` before write.
    value: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
