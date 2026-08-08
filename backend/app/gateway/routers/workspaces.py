"""CRUD API for per-user workspaces (personal space).

Each user owns their own space hierarchy:

- ``/api/workspaces`` -- personal spaces
- ``/api/workspaces/{ws_id}/folders`` -- project folders (folder = project)
- ``/api/workspaces/{ws_id}/folders/{folder_id}/files`` -- documents

Storage policy: metadata plus Markdown body only (binary content is out
of scope this phase; ``storage_status``/``content_ref`` reserve the seam
for a future cloud-storage backend).

Ownership: the caller identity always comes from
``get_effective_user_id()``. Every repository method filters by it, and
resources that do not belong to the caller resolve to 404 -- we never
leak whether another user's resource exists.
"""

from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, field_validator

from tianshu.persistence.workspaces.sql import (
    DuplicateNameError,
    WorkspaceRepository,
)
from tianshu.runtime.user_context import get_effective_user_id

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/workspaces", tags=["workspaces"])

repo = WorkspaceRepository()

# Document body limit (mirrors docs/workspace/requirements.md).
MAX_DOCUMENT_BYTES = 1_000_000

# Name length limits.
MAX_WORKSPACE_NAME_LEN = 100
MAX_FOLDER_NAME_LEN = 100
MAX_FILE_NAME_LEN = 255


def _user_id(request: Request) -> str:
    return get_effective_user_id()


def _clean_name(value: str, *, max_len: int, field: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise HTTPException(status_code=400, detail=f"{field} must not be empty")
    if len(cleaned) > max_len:
        raise HTTPException(
            status_code=400,
            detail=f"{field} must be at most {max_len} characters",
        )
    return cleaned


def _validate_content(value: str | None) -> str | None:
    if value is None:
        return None
    size = len(value.encode("utf-8"))
    if size > MAX_DOCUMENT_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Document body too large: maximum is {MAX_DOCUMENT_BYTES} bytes",
        )
    return value


# --------------------------------------------------------------------------
# Request models
# --------------------------------------------------------------------------


class WorkspaceCreateRequest(BaseModel):
    name: str
    description: str | None = None

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("name must not be empty")
        if len(value.strip()) > MAX_WORKSPACE_NAME_LEN:
            raise ValueError(f"name must be at most {MAX_WORKSPACE_NAME_LEN} characters")
        return value.strip()

    @field_validator("description")
    @classmethod
    def _description(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if len(cleaned) > 2000:
            raise ValueError("description must be at most 2000 characters")
        return cleaned


class WorkspaceUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None

    @field_validator("name")
    @classmethod
    def _name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("name must not be empty")
        if len(cleaned) > MAX_WORKSPACE_NAME_LEN:
            raise ValueError(f"name must be at most {MAX_WORKSPACE_NAME_LEN} characters")
        return cleaned

    @field_validator("description")
    @classmethod
    def _description(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if len(cleaned) > 2000:
            raise ValueError("description must be at most 2000 characters")
        return cleaned


class FolderCreateRequest(BaseModel):
    name: str

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("name must not be empty")
        if len(value.strip()) > MAX_FOLDER_NAME_LEN:
            raise ValueError(f"name must be at most {MAX_FOLDER_NAME_LEN} characters")
        return value.strip()


class FolderUpdateRequest(BaseModel):
    name: str | None = None
    sort_order: int | None = Field(default=None, ge=0, le=10_000)

    @field_validator("name")
    @classmethod
    def _name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("name must not be empty")
        if len(cleaned) > MAX_FOLDER_NAME_LEN:
            raise ValueError(f"name must be at most {MAX_FOLDER_NAME_LEN} characters")
        return cleaned


class FileCreateRequest(BaseModel):
    name: str
    content: str = ""

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("name must not be empty")
        if len(value.strip()) > MAX_FILE_NAME_LEN:
            raise ValueError(f"name must be at most {MAX_FILE_NAME_LEN} characters")
        return value.strip()

    @field_validator("content")
    @classmethod
    def _content(cls, value: str) -> str:
        if len(value.encode("utf-8")) > MAX_DOCUMENT_BYTES:
            raise ValueError(f"content must be at most {MAX_DOCUMENT_BYTES} bytes")
        return value


class FileUpdateRequest(BaseModel):
    name: str | None = None
    content: str | None = None

    @field_validator("name")
    @classmethod
    def _name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("name must not be empty")
        if len(cleaned) > MAX_FILE_NAME_LEN:
            raise ValueError(f"name must be at most {MAX_FILE_NAME_LEN} characters")
        return cleaned

    @field_validator("content")
    @classmethod
    def _content(cls, value: str | None) -> str | None:
        return _validate_content(value)


# --------------------------------------------------------------------------
# Error mapping
# --------------------------------------------------------------------------


def _map_repo_error(exc: Exception) -> HTTPException:
    if isinstance(exc, DuplicateNameError):
        return HTTPException(status_code=409, detail="A resource with this name already exists")
    if isinstance(exc, KeyError):
        return HTTPException(status_code=404, detail="Resource not found")
    if isinstance(exc, ValueError) and str(exc) == "too many workspaces":
        return HTTPException(status_code=413, detail="Workspace limit reached (50 per user)")
    if isinstance(exc, ValueError) and str(exc) == "too many folders":
        return HTTPException(status_code=413, detail="Folder limit reached (500 per workspace)")
    if isinstance(exc, ValueError) and str(exc) == "too many files":
        return HTTPException(status_code=413, detail="File limit reached (2000 per folder)")
    logger.exception("Workspace operation failed")
    return HTTPException(status_code=500, detail="Internal error")


# --------------------------------------------------------------------------
# Workspaces
# --------------------------------------------------------------------------


@router.get("")
async def list_workspaces(request: Request) -> dict[str, Any]:
    user_id = _user_id(request)
    workspaces = await repo.list_workspaces(user_id)
    return {"workspaces": workspaces, "count": len(workspaces)}


@router.post("")
async def create_workspace(request: Request, body: WorkspaceCreateRequest) -> dict[str, Any]:
    user_id = _user_id(request)
    try:
        workspace = await repo.create_workspace(user_id, body.name, body.description)
    except Exception as exc:  # noqa: BLE001 - mapped below
        raise _map_repo_error(exc)
    return {"workspace": workspace}


@router.get("/{workspace_id}")
async def get_workspace(request: Request, workspace_id: str) -> dict[str, Any]:
    user_id = _user_id(request)
    workspace = await repo.get_workspace(user_id, workspace_id)
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    folders = await repo.list_folders(user_id, workspace_id)
    return {"workspace": workspace, "folders": folders}


@router.patch("/{workspace_id}")
async def update_workspace(
    request: Request, workspace_id: str, body: WorkspaceUpdateRequest
) -> dict[str, Any]:
    user_id = _user_id(request)
    if body.name is None and body.description is None:
        raise HTTPException(status_code=400, detail="Nothing to update")
    try:
        workspace = await repo.update_workspace(
            user_id, workspace_id, name=body.name, description=body.description
        )
    except Exception as exc:  # noqa: BLE001 - mapped below
        raise _map_repo_error(exc)
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return {"workspace": workspace}


@router.delete("/{workspace_id}", status_code=204)
async def delete_workspace(request: Request, workspace_id: str) -> None:
    user_id = _user_id(request)
    deleted = await repo.delete_workspace(user_id, workspace_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Workspace not found")


# --------------------------------------------------------------------------
# Folders
# --------------------------------------------------------------------------


@router.post("/{workspace_id}/folders")
async def create_folder(
    request: Request, workspace_id: str, body: FolderCreateRequest
) -> dict[str, Any]:
    user_id = _user_id(request)
    try:
        folder = await repo.create_folder(user_id, workspace_id, body.name)
    except Exception as exc:  # noqa: BLE001 - mapped below
        raise _map_repo_error(exc)
    return {"folder": folder}


@router.patch("/{workspace_id}/folders/{folder_id}")
async def update_folder(
    request: Request,
    workspace_id: str,
    folder_id: str,
    body: FolderUpdateRequest,
) -> dict[str, Any]:
    del workspace_id  # ownership enforced via the folder row itself
    user_id = _user_id(request)
    if body.name is None and body.sort_order is None:
        raise HTTPException(status_code=400, detail="Nothing to update")
    try:
        folder = await repo.update_folder(
            user_id, folder_id, name=body.name, sort_order=body.sort_order
        )
    except Exception as exc:  # noqa: BLE001 - mapped below
        raise _map_repo_error(exc)
    if folder is None:
        raise HTTPException(status_code=404, detail="Folder not found")
    return {"folder": folder}


@router.delete("/{workspace_id}/folders/{folder_id}", status_code=204)
async def delete_folder(request: Request, workspace_id: str, folder_id: str) -> None:
    del workspace_id  # ownership enforced via the folder row itself
    user_id = _user_id(request)
    deleted = await repo.delete_folder(user_id, folder_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Folder not found")


# --------------------------------------------------------------------------
# Files
# --------------------------------------------------------------------------


@router.get("/{workspace_id}/folders/{folder_id}/files")
async def list_files(
    request: Request, workspace_id: str, folder_id: str
) -> dict[str, Any]:
    user_id = _user_id(request)
    # Verify the folder belongs to the caller (404 otherwise).
    folder = await repo.get_folder(user_id, folder_id)
    if folder is None or folder["workspace_id"] != workspace_id:
        raise HTTPException(status_code=404, detail="Folder not found")
    files = await repo.list_files(user_id, folder_id)
    return {"files": files, "count": len(files)}


@router.post("/{workspace_id}/folders/{folder_id}/files")
async def create_file(
    request: Request,
    workspace_id: str,
    folder_id: str,
    body: FileCreateRequest,
) -> dict[str, Any]:
    user_id = _user_id(request)
    try:
        file_row = await repo.create_file(user_id, folder_id, body.name, body.content)
    except Exception as exc:  # noqa: BLE001 - mapped below
        raise _map_repo_error(exc)
    if file_row["workspace_id"] != workspace_id:
        raise HTTPException(status_code=404, detail="Folder not found")
    return {"file": file_row}


@router.get("/{workspace_id}/folders/{folder_id}/files/{file_id}")
async def get_file(
    request: Request, workspace_id: str, folder_id: str, file_id: str
) -> dict[str, Any]:
    user_id = _user_id(request)
    file_row = await repo.get_file(user_id, file_id, include_content=True)
    if (
        file_row is None
        or file_row["folder_id"] != folder_id
        or file_row["workspace_id"] != workspace_id
    ):
        raise HTTPException(status_code=404, detail="File not found")
    return {"file": file_row}


@router.patch("/{workspace_id}/folders/{folder_id}/files/{file_id}")
async def update_file(
    request: Request,
    workspace_id: str,
    folder_id: str,
    file_id: str,
    body: FileUpdateRequest,
) -> dict[str, Any]:
    user_id = _user_id(request)
    if body.name is None and body.content is None:
        raise HTTPException(status_code=400, detail="Nothing to update")
    try:
        file_row = await repo.update_file(
            user_id, file_id, name=body.name, content=body.content
        )
    except Exception as exc:  # noqa: BLE001 - mapped below
        raise _map_repo_error(exc)
    if (
        file_row is None
        or file_row["folder_id"] != folder_id
        or file_row["workspace_id"] != workspace_id
    ):
        raise HTTPException(status_code=404, detail="File not found")
    return {"file": file_row}


@router.delete("/{workspace_id}/folders/{folder_id}/files/{file_id}", status_code=204)
async def delete_file(
    request: Request, workspace_id: str, folder_id: str, file_id: str
) -> None:
    user_id = _user_id(request)
    file_row = await repo.get_file(user_id, file_id)
    if (
        file_row is None
        or file_row["folder_id"] != folder_id
        or file_row["workspace_id"] != workspace_id
    ):
        raise HTTPException(status_code=404, detail="File not found")
    deleted = await repo.delete_file(user_id, file_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="File not found")


# --------------------------------------------------------------------------
# Folder ↔ Git repository binding
# --------------------------------------------------------------------------
# Mounted at /api/folders (see app.py). folder_id is globally unique, so
# the binding endpoints only need the folder id; ownership is still
# enforced per-user by the repository layer.

folder_git_router = APIRouter(prefix="/api/folders", tags=["workspaces"])

_VALID_GIT_PROVIDERS = frozenset({"github", "gitee"})


def _normalize_repo_url(value: str) -> str:
    """Validate an https repository URL and normalize it to end with ``.git``."""
    cleaned = value.strip()
    if not cleaned.startswith("https://"):
        raise HTTPException(
            status_code=400, detail="repo_url must be an https:// URL"
        )
    return cleaned if cleaned.endswith(".git") else f"{cleaned}.git"


def _derive_repo_name(repo_url: str) -> str:
    """Derive ``owner/repo`` from ``https://host/owner/repo.git``."""
    path = repo_url.split("://", 1)[1].split("/", 1)[1] if "://" in repo_url else repo_url
    path = path.rstrip("/")
    if path.endswith(".git"):
        path = path[:-4]
    parts = [p for p in path.split("/") if p]
    if len(parts) < 2:
        raise HTTPException(status_code=400, detail="repo_url must include owner/repo")
    return "/".join(parts[-2:])


class FolderGitBindRequest(BaseModel):
    provider: str
    repo_url: str

    @field_validator("provider")
    @classmethod
    def _provider(cls, value: str) -> str:
        provider = value.strip().lower()
        if provider not in _VALID_GIT_PROVIDERS:
            raise ValueError("provider must be one of: github, gitee")
        return provider

    @field_validator("repo_url")
    @classmethod
    def _repo_url(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("repo_url must not be empty")
        return value


@folder_git_router.get("/{folder_id}/git")
async def get_folder_git(request: Request, folder_id: str) -> dict[str, Any]:
    user_id = _user_id(request)
    binding = await repo.get_folder_git(user_id, folder_id)
    if binding is None:
        raise HTTPException(status_code=404, detail="Folder not found")
    return binding


@folder_git_router.put("/{folder_id}/git")
async def put_folder_git(
    request: Request, folder_id: str, body: FolderGitBindRequest
) -> dict[str, Any]:
    user_id = _user_id(request)
    repo_url = _normalize_repo_url(body.repo_url)
    repo_name = _derive_repo_name(repo_url)
    try:
        binding = await repo.set_folder_git(
            user_id,
            folder_id,
            provider=body.provider,
            repo_url=repo_url,
            repo_name=repo_name,
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="Folder not found")
    except Exception as exc:  # noqa: BLE001 - mapped below
        raise _map_repo_error(exc)
    return binding
