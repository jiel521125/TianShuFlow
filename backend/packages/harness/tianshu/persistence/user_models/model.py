"""ORM model for user-defined model configurations.

One row per ``(user_id, name)`` user-registered model. ``provider``
selects the langchain chat-model class (``openai`` | ``anthropic`` |
``google`` | ``deepseek`` | ``custom_openai``), and the credential
fields are stored encrypted-at-rest when a server-side encryption
key is configured (``TIANSHU_FIELD_ENCRYPTION_KEY``); otherwise they
land in the database as plain text under the user_id namespace,
which is acceptable for single-tenant / no-auth deployments.

A row is *visible* only to its owner (``user_id == caller``).
System-configured models live in ``AppConfig.models`` (yaml) and are
returned alongside these rows by ``GET /api/models``.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from tianshu.persistence.base import Base


class UserModelRow(Base):
    __tablename__ = "user_models"
    # Bind ORM to the application schema when database.backend=postgres.
    # See :mod:`tianshu.persistence.agents.model` for the rationale --
    # psycopg's server-side prepared statements bypass search_path.
    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_user_models_user_name"),
        {"schema": "tianshu"},
    )

    # Surrogate PK; (user_id, name) is the natural key.
    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: uuid.uuid4().hex
    )

    user_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)

    # User-facing identifier used in the model dropdown and stored as
    # the ``name`` field on the wire. Must be unique per user.
    name: Mapped[str] = mapped_column(String(128), nullable=False)

    display_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Provider selector. Validated against the langchain provider map at
    # factory time; see :mod:`tianshu.models.user_provider_registry`.
    #   - "openai"        -> langchain_openai.ChatOpenAI
    #   - "anthropic"     -> langchain_anthropic.ChatAnthropic
    #   - "google"        -> langchain_google_genai.ChatGoogleGenerativeAI
    #   - "deepseek"      -> tianshu.models.langchain_chat_deepseek.ChatDeepSeek
    #   - "custom_openai" -> langchain_openai.ChatOpenAI(base_url=...)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)

    # Provider-specific identifiers and credentials.
    # ``api_key`` is stored encrypted when ``TIANSHU_FIELD_ENCRYPTION_KEY``
    # is configured; otherwise it is stored in the clear. The router
    # never logs or echoes this value back to the client -- it only
    # returns a redacted ``"api_key_set": bool`` flag in the API.
    api_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    base_url: Mapped[str | None] = mapped_column(String(512), nullable=True)

    # Actual model identifier sent to the provider (e.g. "gpt-4o",
    # "claude-3-5-sonnet-latest"). Distinct from ``name`` which is the
    # stable handle in our system.
    model: Mapped[str] = mapped_column(String(256), nullable=False)

    # Free-form bag of model parameters forwarded to the langchain
    # chat-model constructor (temperature, max_tokens, extra_headers,
    # etc.). Schema-less on purpose so we can extend without migration.
    parameters: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    supports_thinking: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    supports_reasoning_effort: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )

    context_window: Mapped[int | None] = mapped_column(Integer, nullable=True)

    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

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