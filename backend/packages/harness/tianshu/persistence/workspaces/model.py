"""ORM models for user workspaces (personal space).

Three-table hierarchy owned by a single user ("千人千面" per-user
storage):

- ``user_workspaces``  -- one personal space per user (name, default flag)
- ``workspace_folders`` -- top-level project folders inside a space
  (a folder == one project, used to isolate documents per project)
- ``workspace_files``  -- documents / file records inside a folder

Storage policy: **metadata plus Markdown document body only**. Binary
content is never stored in the database; ``storage_status`` /
``content_ref`` reserve the seam for a future cloud storage backend.

Every row carries the owner ``user_id`` redundantly so every
repository query can filter by owner without joining across tables
(IDOR double-check at the persistence layer).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from tianshu.persistence.base import Base


def _new_id() -> str:
    return uuid.uuid4().hex


def _now() -> datetime:
    return datetime.now(UTC)


class UserWorkspaceRow(Base):
    __tablename__ = "user_workspaces"
    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_user_workspaces_user_name"),
        {"schema": "tianshu"},
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_new_id)

    user_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # First space of a user is automatically the default one; deleting
    # the default promotes the earliest remaining space.
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now, onupdate=_now
    )


class WorkspaceFolderRow(Base):
    __tablename__ = "workspace_folders"
    __table_args__ = (
        UniqueConstraint("workspace_id", "name", name="uq_workspace_folders_ws_name"),
        {"schema": "tianshu"},
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_new_id)

    workspace_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    user_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)

    # Folder name doubles as the project name.
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Git binding: a folder can be linked to one remote repository
    # (GitHub / Gitee). The token itself lives in ``user_settings``
    # (section ``git``); the folder only stores the provider + repo URL.
    git_provider: Mapped[str | None] = mapped_column(String(16), nullable=True)
    git_repo_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    git_repo_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    git_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now, onupdate=_now
    )


class WorkspaceFileRow(Base):
    __tablename__ = "workspace_files"
    __table_args__ = (
        UniqueConstraint("folder_id", "name", name="uq_workspace_files_folder_name"),
        {"schema": "tianshu"},
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_new_id)

    folder_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    # Redundant for cascade-safety and owner filtering without joins.
    workspace_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    user_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    extension: Mapped[str | None] = mapped_column(String(20), nullable=True)
    mime_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)

    # Markdown body for documents. Binary content is out of scope for
    # this phase (never stored here).
    content: Mapped[str | None] = mapped_column(Text, nullable=True)

    # embedded = body lives in ``content``; cloud = reserved for a
    # future object-store backend pointed at by ``content_ref``.
    storage_status: Mapped[str] = mapped_column(String(20), nullable=False, default="embedded")
    content_ref: Mapped[str | None] = mapped_column(String(512), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now, onupdate=_now
    )
