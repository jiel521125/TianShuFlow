"""Async repository for the user workspace hierarchy.

Every method takes the owning ``user_id`` and filters every SQL
statement by it, so a caller can never read or mutate another user's
rows even if the route layer is bypassed (IDOR double-check).

Cascade deletes are explicit (delete files -> folders -> workspace)
inside a single transaction; there are no ORM relationships to rely on.

Uniqueness conflicts surface as :class:`DuplicateNameError` (mapped to
HTTP 409 by the router). All other invariants (lengths, limits) are
validated by the router before reaching this layer.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import PurePosixPath

from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from tianshu.persistence.engine import get_session_factory
from tianshu.persistence.workspaces.model import (
    UserWorkspaceRow,
    WorkspaceFileRow,
    WorkspaceFolderRow,
)

# Business limits (mirror docs/workspace/requirements.md).
MAX_WORKSPACES = 50
MAX_FOLDERS_PER_WORKSPACE = 500
MAX_FILES_PER_FOLDER = 2000


class DuplicateNameError(ValueError):
    """Raised when a name already exists within the same parent scope."""


# Common extension -> MIME hints (documents only this phase).
_MIME_BY_EXT = {
    "md": "text/markdown",
    "markdown": "text/markdown",
    "txt": "text/plain",
    "json": "application/json",
    "yaml": "application/yaml",
    "yml": "application/yaml",
    "html": "text/html",
    "htm": "text/html",
    "css": "text/css",
    "csv": "text/csv",
}


class WorkspaceRepository:
    """Persistence facade for user_workspaces/workspace_folders/workspace_files."""

    @staticmethod
    def _new_id() -> str:
        return uuid.uuid4().hex

    @staticmethod
    def _now() -> datetime:
        return datetime.now(UTC)

    @staticmethod
    def _require_factory() -> AsyncSession:  # type: ignore[type-arg]
        factory = get_session_factory()
        if factory is None:
            raise RuntimeError("Database session factory is not initialised")
        return factory

    # ---------------------------------------------------------------- helpers

    @staticmethod
    def _extension_of(name: str) -> str | None:
        ext = PurePosixPath(name).suffix.lstrip(".").lower()
        return ext[:20] if ext else None

    @staticmethod
    def _mime_for(extension: str | None) -> str:
        if extension:
            mime = _MIME_BY_EXT.get(extension)
            if mime:
                return mime
        return "application/octet-stream"

    @staticmethod
    def _folder_to_dict(row: WorkspaceFolderRow, file_count: int = 0) -> dict:
        return {
            "id": row.id,
            "workspace_id": row.workspace_id,
            "name": row.name,
            "sort_order": row.sort_order,
            "file_count": file_count,
            "git_provider": row.git_provider,
            "git_repo_url": row.git_repo_url,
            "git_repo_name": row.git_repo_name,
            "git_updated_at": (
                row.git_updated_at.isoformat() if row.git_updated_at else None
            ),
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }

    async def get_folder_git(self, user_id: str, folder_id: str) -> dict | None:
        """Return the folder's git binding (provider / repo URL / repo name)."""
        folder = await self.get_folder(user_id, folder_id)
        if folder is None:
            return None
        return {
            "folder_id": folder["id"],
            "provider": folder["git_provider"],
            "repo_url": folder["git_repo_url"],
            "repo_name": folder["git_repo_name"],
            "git_updated_at": folder["git_updated_at"],
        }

    async def set_folder_git(
        self,
        user_id: str,
        folder_id: str,
        *,
        provider: str,
        repo_url: str,
        repo_name: str,
    ) -> dict:
        """Persist the folder's git binding (write = replace)."""
        factory = self._require_factory()
        async with factory() as session:  # type: ignore[union-attr]
            row = (
                await session.execute(
                    select(WorkspaceFolderRow).where(
                        WorkspaceFolderRow.id == folder_id,
                        WorkspaceFolderRow.user_id == user_id,
                    )
                )
            ).scalar_one_or_none()
            if row is None:
                raise KeyError(folder_id)
            row.git_provider = provider
            row.git_repo_url = repo_url
            row.git_repo_name = repo_name
            row.git_updated_at = None
            row.updated_at = self._now()
            await session.commit()
            await session.refresh(row)
            return {
                "folder_id": row.id,
                "provider": row.git_provider,
                "repo_url": row.git_repo_url,
                "repo_name": row.git_repo_name,
                "git_updated_at": None,
            }

    async def touch_folder_git(self, user_id: str, folder_id: str) -> None:
        """Mark a successful pull/push on the folder binding."""
        factory = self._require_factory()
        async with factory() as session:  # type: ignore[union-attr]
            row = (
                await session.execute(
                    select(WorkspaceFolderRow).where(
                        WorkspaceFolderRow.id == folder_id,
                        WorkspaceFolderRow.user_id == user_id,
                    )
                )
            ).scalar_one_or_none()
            if row is None:
                return
            row.git_updated_at = self._now()
            await session.commit()

    @staticmethod
    def _file_to_dict(row: WorkspaceFileRow, *, include_content: bool = False) -> dict:
        data = {
            "id": row.id,
            "folder_id": row.folder_id,
            "workspace_id": row.workspace_id,
            "name": row.name,
            "extension": row.extension,
            "mime_type": row.mime_type,
            "size_bytes": row.size_bytes,
            "storage_status": row.storage_status,
            "content_ref": row.content_ref,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }
        if include_content:
            data["content"] = row.content
        return data

    async def _count_files_by_workspace(self, user_id: str) -> dict[str, int]:
        factory = self._require_factory()
        async with factory() as session:  # type: ignore[union-attr]
            rows = (
                await session.execute(
                    select(WorkspaceFileRow.workspace_id, func.count())
                    .where(WorkspaceFileRow.user_id == user_id)
                    .group_by(WorkspaceFileRow.workspace_id)
                )
            ).all()
            return {ws_id: count for ws_id, count in rows}

    async def _count_files_by_folder(self, user_id: str, folder_ids: list[str]) -> dict[str, int]:
        if not folder_ids:
            return {}
        factory = self._require_factory()
        async with factory() as session:  # type: ignore[union-attr]
            rows = (
                await session.execute(
                    select(WorkspaceFileRow.folder_id, func.count())
                    .where(
                        WorkspaceFileRow.user_id == user_id,
                        WorkspaceFileRow.folder_id.in_(folder_ids),
                    )
                    .group_by(WorkspaceFileRow.folder_id)
                )
            ).all()
            return {folder_id: count for folder_id, count in rows}

    @staticmethod
    def _name_conflict_exc() -> DuplicateNameError:
        return DuplicateNameError("duplicate name")

    # -------------------------------------------------------------- workspaces

    async def list_workspaces(self, user_id: str) -> list[dict]:
        factory = self._require_factory()
        async with factory() as session:  # type: ignore[union-attr]
            rows = (
                await session.execute(
                    select(UserWorkspaceRow)
                    .where(UserWorkspaceRow.user_id == user_id)
                    .order_by(UserWorkspaceRow.created_at.asc(), UserWorkspaceRow.id.asc())
                )
            ).scalars().all()
        file_counts = await self._count_files_by_workspace(user_id)
        result: list[dict] = []
        for row in rows:
            result.append(self._workspace_to_dict(row, file_counts.get(row.id, 0)))
        return result

    @staticmethod
    def _workspace_to_dict(row: UserWorkspaceRow, folder_count: int = 0, file_count: int = 0) -> dict:
        return {
            "id": row.id,
            "name": row.name,
            "description": row.description,
            "is_default": row.is_default,
            "folder_count": folder_count,
            "file_count": file_count,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }

    async def get_workspace(self, user_id: str, workspace_id: str) -> dict | None:
        factory = self._require_factory()
        async with factory() as session:  # type: ignore[union-attr]
            row = (
                await session.execute(
                    select(UserWorkspaceRow).where(
                        UserWorkspaceRow.id == workspace_id,
                        UserWorkspaceRow.user_id == user_id,
                    )
                )
            ).scalar_one_or_none()
            if row is None:
                return None
            folder_count = (
                await session.execute(
                    select(func.count())
                    .select_from(WorkspaceFolderRow)
                    .where(
                        WorkspaceFolderRow.workspace_id == workspace_id,
                        WorkspaceFolderRow.user_id == user_id,
                    )
                )
            ).scalar_one()
            file_count = (
                await session.execute(
                    select(func.count())
                    .select_from(WorkspaceFileRow)
                    .where(
                        WorkspaceFileRow.workspace_id == workspace_id,
                        WorkspaceFileRow.user_id == user_id,
                    )
                )
            ).scalar_one()
            return self._workspace_to_dict(row, folder_count, file_count)

    async def count_workspaces(self, user_id: str) -> int:
        factory = self._require_factory()
        async with factory() as session:  # type: ignore[union-attr]
            return (
                await session.execute(
                    select(func.count())
                    .select_from(UserWorkspaceRow)
                    .where(UserWorkspaceRow.user_id == user_id)
                )
            ).scalar_one()

    async def create_workspace(
        self, user_id: str, name: str, description: str | None
    ) -> dict:
        factory = self._require_factory()
        now = self._now()
        async with factory() as session:  # type: ignore[union-attr]
            existing_count = (
                await session.execute(
                    select(func.count())
                    .select_from(UserWorkspaceRow)
                    .where(UserWorkspaceRow.user_id == user_id)
                )
            ).scalar_one()
            if existing_count >= MAX_WORKSPACES:
                raise ValueError("too many workspaces")
            duplicate = (
                await session.execute(
                    select(UserWorkspaceRow.id)
                    .where(
                        UserWorkspaceRow.user_id == user_id,
                        func.lower(UserWorkspaceRow.name) == name.lower(),
                    )
                    .limit(1)
                )
            ).scalar_one_or_none()
            if duplicate is not None:
                raise self._name_conflict_exc()
            row = UserWorkspaceRow(
                id=self._new_id(),
                user_id=user_id,
                name=name,
                description=description,
                is_default=existing_count == 0,
                created_at=now,
                updated_at=now,
            )
            session.add(row)
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
                raise self._name_conflict_exc()
            await session.refresh(row)
            return self._workspace_to_dict(row)

    async def update_workspace(
        self, user_id: str, workspace_id: str, *, name: str | None, description: str | None
    ) -> dict | None:
        factory = self._require_factory()
        async with factory() as session:  # type: ignore[union-attr]
            row = (
                await session.execute(
                    select(UserWorkspaceRow).where(
                        UserWorkspaceRow.id == workspace_id,
                        UserWorkspaceRow.user_id == user_id,
                    )
                )
            ).scalar_one_or_none()
            if row is None:
                return None
            if name is not None and name.lower() != row.name.lower():
                duplicate = (
                    await session.execute(
                        select(UserWorkspaceRow.id)
                        .where(
                            UserWorkspaceRow.user_id == user_id,
                            func.lower(UserWorkspaceRow.name) == name.lower(),
                            UserWorkspaceRow.id != workspace_id,
                        )
                        .limit(1)
                    )
                ).scalar_one_or_none()
                if duplicate is not None:
                    raise self._name_conflict_exc()
                row.name = name
            if description is not None:
                row.description = description
            row.updated_at = self._now()
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
                raise self._name_conflict_exc()
            await session.refresh(row)
            return self._workspace_to_dict(row)

    async def delete_workspace(self, user_id: str, workspace_id: str) -> bool:
        factory = self._require_factory()
        async with factory() as session:  # type: ignore[union-attr]
            row = (
                await session.execute(
                    select(UserWorkspaceRow).where(
                        UserWorkspaceRow.id == workspace_id,
                        UserWorkspaceRow.user_id == user_id,
                    )
                )
            ).scalar_one_or_none()
            if row is None:
                return False
            was_default = row.is_default
            await session.execute(
                delete(WorkspaceFileRow).where(
                    WorkspaceFileRow.workspace_id == workspace_id,
                    WorkspaceFileRow.user_id == user_id,
                )
            )
            await session.execute(
                delete(WorkspaceFolderRow).where(
                    WorkspaceFolderRow.workspace_id == workspace_id,
                    WorkspaceFolderRow.user_id == user_id,
                )
            )
            await session.delete(row)
            await session.flush()

            if was_default:
                # Promote the earliest remaining workspace, if any.
                next_row = (
                    await session.execute(
                        select(UserWorkspaceRow)
                        .where(
                            UserWorkspaceRow.user_id == user_id,
                            UserWorkspaceRow.id != workspace_id,
                        )
                        .order_by(
                            UserWorkspaceRow.created_at.asc(), UserWorkspaceRow.id.asc()
                        )
                        .limit(1)
                    )
                ).scalar_one_or_none()
                if next_row is not None:
                    next_row.is_default = True
                    next_row.updated_at = self._now()
            await session.commit()
            return True

    # ---------------------------------------------------------------- folders

    async def list_folders(self, user_id: str, workspace_id: str) -> list[dict]:
        factory = self._require_factory()
        async with factory() as session:  # type: ignore[union-attr]
            rows = (
                await session.execute(
                    select(WorkspaceFolderRow)
                    .where(
                        WorkspaceFolderRow.workspace_id == workspace_id,
                        WorkspaceFolderRow.user_id == user_id,
                    )
                    .order_by(
                        WorkspaceFolderRow.sort_order.asc(),
                        WorkspaceFolderRow.created_at.asc(),
                        WorkspaceFolderRow.id.asc(),
                    )
                )
            ).scalars().all()
        file_counts = await self._count_files_by_folder(
            user_id, [row.id for row in rows]
        )
        return [
            self._folder_to_dict(row, file_counts.get(row.id, 0))
            for row in rows
        ]

    async def get_folder(self, user_id: str, folder_id: str) -> dict | None:
        factory = self._require_factory()
        async with factory() as session:  # type: ignore[union-attr]
            row = (
                await session.execute(
                    select(WorkspaceFolderRow).where(
                        WorkspaceFolderRow.id == folder_id,
                        WorkspaceFolderRow.user_id == user_id,
                    )
                )
            ).scalar_one_or_none()
            if row is None:
                return None
            file_count = (
                await session.execute(
                    select(func.count())
                    .select_from(WorkspaceFileRow)
                    .where(
                        WorkspaceFileRow.folder_id == folder_id,
                        WorkspaceFileRow.user_id == user_id,
                    )
                )
            ).scalar_one()
            return self._folder_to_dict(row, file_count)

    async def create_folder(self, user_id: str, workspace_id: str, name: str) -> dict:
        factory = self._require_factory()
        now = self._now()
        async with factory() as session:  # type: ignore[union-attr]
            # Workspace must exist and belong to the caller.
            ws_exists = (
                await session.execute(
                    select(UserWorkspaceRow.id).where(
                        UserWorkspaceRow.id == workspace_id,
                        UserWorkspaceRow.user_id == user_id,
                    )
                )
            ).scalar_one_or_none()
            if ws_exists is None:
                raise KeyError(workspace_id)
            count = (
                await session.execute(
                    select(func.count())
                    .select_from(WorkspaceFolderRow)
                    .where(
                        WorkspaceFolderRow.workspace_id == workspace_id,
                        WorkspaceFolderRow.user_id == user_id,
                    )
                )
            ).scalar_one()
            if count >= MAX_FOLDERS_PER_WORKSPACE:
                raise ValueError("too many folders")
            duplicate = (
                await session.execute(
                    select(WorkspaceFolderRow.id)
                    .where(
                        WorkspaceFolderRow.workspace_id == workspace_id,
                        WorkspaceFolderRow.user_id == user_id,
                        func.lower(WorkspaceFolderRow.name) == name.lower(),
                    )
                    .limit(1)
                )
            ).scalar_one_or_none()
            if duplicate is not None:
                raise self._name_conflict_exc()
            max_sort = (
                await session.execute(
                    select(func.max(WorkspaceFolderRow.sort_order)).where(
                        WorkspaceFolderRow.workspace_id == workspace_id,
                        WorkspaceFolderRow.user_id == user_id,
                    )
                )
            ).scalar_one()
            row = WorkspaceFolderRow(
                id=self._new_id(),
                workspace_id=workspace_id,
                user_id=user_id,
                name=name,
                sort_order=(max_sort or 0) + 1,
                created_at=now,
                updated_at=now,
            )
            session.add(row)
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
                raise self._name_conflict_exc()
            await session.refresh(row)
            return self._folder_to_dict(row)

    async def update_folder(
        self,
        user_id: str,
        folder_id: str,
        *,
        name: str | None,
        sort_order: int | None,
    ) -> dict | None:
        factory = self._require_factory()
        async with factory() as session:  # type: ignore[union-attr]
            row = (
                await session.execute(
                    select(WorkspaceFolderRow).where(
                        WorkspaceFolderRow.id == folder_id,
                        WorkspaceFolderRow.user_id == user_id,
                    )
                )
            ).scalar_one_or_none()
            if row is None:
                return None
            if name is not None and name.lower() != row.name.lower():
                duplicate = (
                    await session.execute(
                        select(WorkspaceFolderRow.id)
                        .where(
                            WorkspaceFolderRow.workspace_id == row.workspace_id,
                            WorkspaceFolderRow.user_id == user_id,
                            func.lower(WorkspaceFolderRow.name) == name.lower(),
                            WorkspaceFolderRow.id != folder_id,
                        )
                        .limit(1)
                    )
                ).scalar_one_or_none()
                if duplicate is not None:
                    raise self._name_conflict_exc()
                row.name = name
            if sort_order is not None:
                row.sort_order = sort_order
            row.updated_at = self._now()
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
                raise self._name_conflict_exc()
            await session.refresh(row)
            return self._folder_to_dict(row)

    async def delete_folder(self, user_id: str, folder_id: str) -> bool:
        factory = self._require_factory()
        async with factory() as session:  # type: ignore[union-attr]
            row = (
                await session.execute(
                    select(WorkspaceFolderRow).where(
                        WorkspaceFolderRow.id == folder_id,
                        WorkspaceFolderRow.user_id == user_id,
                    )
                )
            ).scalar_one_or_none()
            if row is None:
                return False
            await session.execute(
                delete(WorkspaceFileRow).where(
                    WorkspaceFileRow.folder_id == folder_id,
                    WorkspaceFileRow.user_id == user_id,
                )
            )
            await session.delete(row)
            await session.commit()
            return True

    # ------------------------------------------------------------------ files

    async def list_files(self, user_id: str, folder_id: str) -> list[dict]:
        factory = self._require_factory()
        async with factory() as session:  # type: ignore[union-attr]
            rows = (
                await session.execute(
                    select(WorkspaceFileRow)
                    .where(
                        WorkspaceFileRow.folder_id == folder_id,
                        WorkspaceFileRow.user_id == user_id,
                    )
                    .order_by(
                        WorkspaceFileRow.created_at.asc(), WorkspaceFileRow.id.asc()
                    )
                )
            ).scalars().all()
            return [self._file_to_dict(row) for row in rows]

    async def get_file(
        self, user_id: str, file_id: str, *, include_content: bool = False
    ) -> dict | None:
        factory = self._require_factory()
        async with factory() as session:  # type: ignore[union-attr]
            row = (
                await session.execute(
                    select(WorkspaceFileRow).where(
                        WorkspaceFileRow.id == file_id,
                        WorkspaceFileRow.user_id == user_id,
                    )
                )
            ).scalar_one_or_none()
            if row is None:
                return None
            return self._file_to_dict(row, include_content=include_content)

    async def create_file(
        self, user_id: str, folder_id: str, name: str, content: str
    ) -> dict:
        factory = self._require_factory()
        now = self._now()
        async with factory() as session:  # type: ignore[union-attr]
            folder = (
                await session.execute(
                    select(WorkspaceFolderRow).where(
                        WorkspaceFolderRow.id == folder_id,
                        WorkspaceFolderRow.user_id == user_id,
                    )
                )
            ).scalar_one_or_none()
            if folder is None:
                raise KeyError(folder_id)
            count = (
                await session.execute(
                    select(func.count())
                    .select_from(WorkspaceFileRow)
                    .where(
                        WorkspaceFileRow.folder_id == folder_id,
                        WorkspaceFileRow.user_id == user_id,
                    )
                )
            ).scalar_one()
            if count >= MAX_FILES_PER_FOLDER:
                raise ValueError("too many files")
            duplicate = (
                await session.execute(
                    select(WorkspaceFileRow.id)
                    .where(
                        WorkspaceFileRow.folder_id == folder_id,
                        WorkspaceFileRow.user_id == user_id,
                        func.lower(WorkspaceFileRow.name) == name.lower(),
                    )
                    .limit(1)
                )
            ).scalar_one_or_none()
            if duplicate is not None:
                raise self._name_conflict_exc()
            extension = self._extension_of(name)
            row = WorkspaceFileRow(
                id=self._new_id(),
                folder_id=folder_id,
                workspace_id=folder.workspace_id,
                user_id=user_id,
                name=name,
                extension=extension,
                mime_type=self._mime_for(extension),
                size_bytes=len(content.encode("utf-8")),
                content=content,
                storage_status="embedded",
                created_at=now,
                updated_at=now,
            )
            session.add(row)
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
                raise self._name_conflict_exc()
            await session.refresh(row)
            return self._file_to_dict(row, include_content=True)

    async def update_file(
        self,
        user_id: str,
        file_id: str,
        *,
        name: str | None,
        content: str | None,
    ) -> dict | None:
        factory = self._require_factory()
        async with factory() as session:  # type: ignore[union-attr]
            row = (
                await session.execute(
                    select(WorkspaceFileRow).where(
                        WorkspaceFileRow.id == file_id,
                        WorkspaceFileRow.user_id == user_id,
                    )
                )
            ).scalar_one_or_none()
            if row is None:
                return None
            if name is not None and name.lower() != row.name.lower():
                duplicate = (
                    await session.execute(
                        select(WorkspaceFileRow.id)
                        .where(
                            WorkspaceFileRow.folder_id == row.folder_id,
                            WorkspaceFileRow.user_id == user_id,
                            func.lower(WorkspaceFileRow.name) == name.lower(),
                            WorkspaceFileRow.id != file_id,
                        )
                        .limit(1)
                    )
                ).scalar_one_or_none()
                if duplicate is not None:
                    raise self._name_conflict_exc()
                row.name = name
                row.extension = self._extension_of(name)
                row.mime_type = self._mime_for(row.extension)
            if content is not None:
                row.content = content
                row.size_bytes = len(content.encode("utf-8"))
            row.updated_at = self._now()
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
                raise self._name_conflict_exc()
            await session.refresh(row)
            return self._file_to_dict(row, include_content=True)

    async def delete_file(self, user_id: str, file_id: str) -> bool:
        factory = self._require_factory()
        async with factory() as session:  # type: ignore[union-attr]
            result = await session.execute(
                delete(WorkspaceFileRow).where(
                    WorkspaceFileRow.id == file_id,
                    WorkspaceFileRow.user_id == user_id,
                )
            )
            await session.commit()
            return result.rowcount > 0
