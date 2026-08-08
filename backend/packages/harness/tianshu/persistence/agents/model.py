"""ORM model for custom agent definitions.

One row per ``(user_id, name)`` custom agent. ``config`` holds the full
:class:`~tianshu.config.agents_config.AgentConfig` document *minus* ``name``
(which is the natural key, carried by the ``name`` column). Storing the config
as a single JSON document — rather than a column per field — is deliberate: the
codebase already declares, via ``preserve_non_managed_fields``, that any field
added to ``AgentConfig`` in the future must round-trip through writers that do
not know it. A document column honours that invariant with zero schema churn
(a new ``AgentConfig`` field needs no migration here); the only queries are by
``(user_id, name)`` and list-by-user, which are exactly the indexed columns.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from tianshu.persistence.base import Base


class AgentRow(Base):
    __tablename__ = "agents"
    # Bind ORM to the application schema when running under
    # database.backend=postgres. The async engine also sets search_path,
    # but server-side prepared statements can bypass it. Qualifying the
    # table here ensures INSERT/UPDATE/SELECT resolve to tianshu.agents
    # unconditionally.
    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_agents_user_name"),
        {"schema": "tianshu"},
    )

    # Surrogate primary key (uuid4 hex). The natural key is (user_id, name),
    # enforced by the UNIQUE constraint above; a surrogate PK keeps the row
    # identity stable if an agent is ever renamed in a future revision.
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    # Stored lowercase, matching the on-disk layout (Paths.user_agent_dir lowercases).
    name: Mapped[str] = mapped_column(String(128))
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    soul: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
