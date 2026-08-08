"""Git integration API (GitHub / Gitee).

- ``GET/PUT /api/git/config`` -- per-user PAT tokens (masked outbound).
- ``POST /api/git/pull`` / ``POST /api/git/push`` -- SSE streams that run
  the git operation and stream command logs to the conversation area.

Credentials live in ``user_settings`` (section ``git``) and are isolated
by ``get_effective_user_id()``. The folder→repository binding lives on
the folder itself (see ``/api/workspaces/.../folders/{id}/git``).
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Annotated, Any, Awaitable, Callable

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from tianshu.git.service import GitError, GitService
from tianshu.persistence.user_settings.sql import UserSettingsRepository
from tianshu.persistence.workspaces.sql import WorkspaceRepository
from tianshu.runtime.user_context import get_effective_user_id

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/git", tags=["git"])

_service = GitService()
_settings = UserSettingsRepository()
_workspaces = WorkspaceRepository()

_VALID_PROVIDERS = frozenset({"github", "gitee"})

LogEmitter = Callable[[str], Awaitable[None]]


class GitConfigUpdateRequest(BaseModel):
    github_token: str | None = Field(
        default=None, description="GitHub PAT; null/empty clears the token"
    )
    gitee_token: str | None = Field(
        default=None, description="Gitee PAT; null/empty clears the token"
    )


def _user_id() -> str:
    return get_effective_user_id()


# ------------------------------------------------------------------- config


@router.get("/config")
async def get_git_config() -> dict[str, Any]:
    user_id = _user_id()
    settings = await _settings.get(user_id, "git") or {}
    return {
        provider: {"configured": bool(settings.get(f"{provider}_token"))}
        for provider in sorted(_VALID_PROVIDERS)
    }


@router.put("/config")
async def put_git_config(body: GitConfigUpdateRequest) -> dict[str, Any]:
    user_id = _user_id()
    settings = dict(await _settings.get(user_id, "git") or {})
    changed = False
    for provider in _VALID_PROVIDERS:
        key = f"{provider}_token"
        value = getattr(body, key)
        if value is None or not value.strip():
            if key in settings:
                del settings[key]
                changed = True
        else:
            settings[key] = value.strip()
            changed = True
    if not settings:
        await _settings.delete(user_id=user_id, key="git")
    elif changed:
        await _settings.upsert(user_id=user_id, key="git", value=settings)
    current = await _settings.get(user_id, "git") or {}
    return {
        provider: {"configured": bool(current.get(f"{provider}_token"))}
        for provider in sorted(_VALID_PROVIDERS)
    }


# ------------------------------------------------------------ SSE operations


async def _sse_worker(
    worker: Callable[[LogEmitter], Awaitable[dict[str, Any]]],
) -> StreamingResponse:
    queue: asyncio.Queue[tuple[str, Any]] = asyncio.Queue()

    async def emit(line: str) -> None:
        await queue.put(("log", line))

    async def run() -> None:
        try:
            result = await worker(emit)
            await queue.put(
                (
                    "done",
                    {
                        "ok": True,
                        "message": result.get("message", "操作成功"),
                        **{k: v for k, v in result.items() if k != "message"},
                    },
                )
            )
        except GitError as exc:
            await queue.put(("done", {"ok": False, "message": str(exc)}))
        except Exception as exc:  # noqa: BLE001
            logger.exception("git operation failed")
            await queue.put(("done", {"ok": False, "message": str(exc)}))

    task = asyncio.create_task(run())

    async def event_stream():
        try:
            while True:
                kind, payload = await queue.get()
                if kind == "log":
                    yield f"event: log\ndata: {json.dumps({'line': payload})}\n\n"
                else:
                    yield f"event: done\ndata: {json.dumps(payload)}\n\n"
                    break
        finally:
            task.cancel()

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


class GitOperationRequest(BaseModel):
    folder_id: str = Field(..., description="Workspace folder id to pull/push")


@router.post("/pull")
async def git_pull(body: GitOperationRequest) -> StreamingResponse:
    user_id = _user_id()
    folder = await _workspaces.get_folder(user_id, body.folder_id)
    if folder is None:
        raise HTTPException(status_code=404, detail="Folder not found")

    async def worker(emit: LogEmitter) -> dict[str, Any]:
        await emit(f"开始拉取到文件夹「{folder['name']}」 ...")
        result = await _service.pull(user_id, body.folder_id, emit)
        return {
            "message": f"拉取成功：{result.get('updated', 0)} 个文件已同步",
            "updated": result.get("updated", 0),
        }

    return await _sse_worker(worker)


@router.post("/push")
async def git_push(body: GitOperationRequest) -> StreamingResponse:
    user_id = _user_id()
    folder = await _workspaces.get_folder(user_id, body.folder_id)
    if folder is None:
        raise HTTPException(status_code=404, detail="Folder not found")

    async def worker(emit: LogEmitter) -> dict[str, Any]:
        await emit(f"开始推送文件夹「{folder['name']}」 ...")
        result = await _service.push(user_id, body.folder_id, emit)
        if result.get("committed"):
            return {"message": "推送成功：变更已提交并推送到远端", "pushed": 1}
        return {"message": "没有需要推送的变更", "pushed": 0}

    return await _sse_worker(worker)
