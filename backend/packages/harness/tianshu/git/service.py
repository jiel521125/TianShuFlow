"""Git integration service.

Bridges a workspace folder (embedded storage in the database) with a
remote Git repository (GitHub / Gitee) through a per-user disk work
tree: ``<runtime_home>/users/{user_id}/git/{folder_id}``.

- ``pull``  clones/fetches the remote into the work tree, then syncs the
  disk files (relative paths, ``.git`` excluded) into the folder DB.
- ``push``  syncs the folder DB files onto disk, then
  ``git add -A && commit && push``.

Credentials are read from ``user_settings`` (section ``git``, keys
``github_token`` / ``gitee_token``) and are never echoed to logs or the
SSE stream. Every git command runs as an argument list (no shell
interpolation) for injection safety.
"""

from __future__ import annotations

import asyncio
import logging
import os
import subprocess
from collections.abc import Awaitable, Callable
from pathlib import Path

from tianshu.config.runtime_paths import runtime_home
from tianshu.persistence.user_settings.sql import UserSettingsRepository
from tianshu.persistence.workspaces.sql import WorkspaceRepository

logger = logging.getLogger(__name__)

LogEmitter = Callable[[str], Awaitable[None]]

_VALID_PROVIDERS = frozenset({"github", "gitee"})

# Files we never sync (git internals + platform metadata).
_EXCLUDED_DIR_NAMES = frozenset({".git"})
_EXCLUDED_FILE_NAMES = frozenset({".DS_Store"})


class GitError(Exception):
    """Raised for user-facing git operation failures."""


class GitService:
    def __init__(self) -> None:
        self._workspaces = WorkspaceRepository()
        self._settings = UserSettingsRepository()

    # ------------------------------------------------------------------ paths

    def _workdir(self, user_id: str, folder_id: str) -> Path:
        return runtime_home() / "users" / user_id / "git" / folder_id

    # ----------------------------------------------------------------- tokens

    async def _token_for(self, user_id: str, provider: str) -> str | None:
        settings = await self._settings.get(user_id, "git") or {}
        return settings.get(f"{provider}_token") or None

    @staticmethod
    def _auth_url(repo_url: str, token: str) -> str:
        """Inject the token into an https:// URL (never logged)."""
        if "://" in repo_url:
            scheme, rest = repo_url.split("://", 1)
            return f"{scheme}://{token}@{rest}"
        return repo_url

    # ----------------------------------------------------------- git commands

    async def _run(
        self,
        workdir: Path,
        args: list[str],
        emit: LogEmitter,
    ) -> tuple[int, list[str]]:
        """Run one git command as an argument list, streaming output lines.

        The subprocess runs in a worker thread instead of
        ``asyncio.create_subprocess_exec`` because the gateway starts on a
        Windows ``SelectorEventLoop`` (required for psycopg3), which does not
        support asyncio subprocesses and raises ``NotImplementedError``.
        """
        proc = await asyncio.to_thread(
            subprocess.Popen,
            args,
            cwd=str(workdir),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=dict(os.environ),
        )
        queue: asyncio.Queue[str | None] = asyncio.Queue()

        def pump() -> None:
            assert proc.stdout is not None
            for raw in proc.stdout:
                text = raw.decode(errors="replace").rstrip("\n")
                if text:
                    queue.put_nowait(text)
            proc.wait()
            queue.put_nowait(None)

        pump_task = asyncio.create_task(asyncio.to_thread(pump))
        lines: list[str] = []
        while True:
            text = await queue.get()
            if text is None:
                break
            lines.append(text)
            try:
                await emit(text)
            except Exception:  # noqa: BLE001 - never break the git flow
                logger.exception("SSE emit failed")
        await pump_task
        return proc.returncode or 0, lines

    # --------------------------------------------------------------- bridges

    async def _sync_db_to_disk(self, user_id: str, folder_id: str, workdir: Path) -> int:
        """Write every folder DB file into the work tree. Returns file count."""
        files = await self._workspaces.list_files(user_id, folder_id)
        for file_row in files:
            full = await self._workspaces.get_file(user_id, file_row["id"], include_content=True)
            dest = workdir / file_row["name"]
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text((full or {}).get("content") or "", encoding="utf-8")
        return len(files)

    async def _sync_disk_to_db(self, user_id: str, folder_id: str, workdir: Path, emit: LogEmitter) -> int:
        """Upsert work-tree files (``.git`` excluded) into the folder DB.

        File names use the repository-relative posix path (may contain
        sub-directories). DB rows whose file disappeared from disk are
        deleted. Returns the number of synced files.
        """
        files = await self._workspaces.list_files(user_id, folder_id)
        db_by_name = {f["name"].lower(): f for f in files}
        seen: set[str] = set()
        updated = 0
        for path in workdir.rglob("*"):
            if path.is_dir() or _EXCLUDED_DIR_NAMES.intersection(path.parts):
                continue
            if path.name in _EXCLUDED_FILE_NAMES:
                continue
            rel = path.relative_to(workdir).as_posix()
            key = rel.lower()
            seen.add(key)
            content = path.read_text(encoding="utf-8", errors="replace")
            try:
                existing = db_by_name.get(key)
                if existing is None:
                    await self._workspaces.create_file(user_id, folder_id, rel, content)
                elif existing.get("storage_status") == "embedded" and await self._file_content(user_id, existing["id"]) != content:
                    await self._workspaces.update_file(user_id, existing["id"], name=rel, content=content)
                updated += 1
            except Exception as exc:  # noqa: BLE001 - keep syncing the rest
                logger.warning("sync file %s failed: %s", rel, exc)
                await emit(f"[跳过] {rel}: {exc}")
        # Delete DB rows whose disk file vanished (e.g. removed upstream).
        for name_lower, row in db_by_name.items():
            if name_lower not in seen:
                try:
                    await self._workspaces.delete_file(user_id, row["id"])
                except Exception:  # noqa: BLE001
                    logger.warning("delete stale file %s failed", row["name"])
        return updated

    async def _file_content(self, user_id: str, file_id: str) -> str:
        full = await self._workspaces.get_file(user_id, file_id, include_content=True)
        return (full or {}).get("content") or ""

    # ------------------------------------------------------------------- pull

    async def pull(self, user_id: str, folder_id: str, emit: LogEmitter) -> dict:
        binding = await self._workspaces.get_folder_git(user_id, folder_id)
        if not binding or not binding.get("repo_url"):
            raise GitError("该文件夹尚未绑定仓库，请先在会话区完成绑定")
        provider: str = binding["provider"] or ""
        repo_url: str = binding["repo_url"] or ""
        if provider not in _VALID_PROVIDERS:
            raise GitError(f"不支持的仓库平台: {provider}")
        token = await self._token_for(user_id, provider)
        if not token:
            raise GitError(f"未配置 {provider} Token，请到 设置 → Git 集成 中配置")
        workdir = self._workdir(user_id, folder_id)
        workdir.mkdir(parents=True, exist_ok=True)
        auth_url = self._auth_url(repo_url, token)
        if not (workdir / ".git").exists():
            await emit(f"git clone {repo_url}")
            code, _ = await self._run(workdir, ["git", "clone", auth_url, "."], emit)
            if code != 0:
                raise GitError("克隆失败，请检查 Token 与仓库地址")
        else:
            await self._run(workdir, ["git", "remote", "set-url", "origin", auth_url], emit)
            await emit("git pull")
            code, _ = await self._run(workdir, ["git", "pull", "--ff-only"], emit)
            if code != 0:
                raise GitError("拉取失败（可能本地有未提交变更）")
        await emit("同步到工作空间文件夹 ...")
        updated = await self._sync_disk_to_db(user_id, folder_id, workdir, emit)
        await self._workspaces.touch_folder_git(user_id, folder_id)
        return {"updated": updated}

    # ------------------------------------------------------------------- push

    async def push(self, user_id: str, folder_id: str, emit: LogEmitter) -> dict:
        binding = await self._workspaces.get_folder_git(user_id, folder_id)
        if not binding or not binding.get("repo_url"):
            raise GitError("该文件夹尚未绑定仓库，请先拉取或绑定仓库")
        provider: str = binding["provider"] or ""
        repo_url: str = binding["repo_url"] or ""
        if provider not in _VALID_PROVIDERS:
            raise GitError(f"不支持的仓库平台: {provider}")
        token = await self._token_for(user_id, provider)
        if not token:
            raise GitError(f"未配置 {provider} Token，请到 设置 → Git 集成 中配置")
        workdir = self._workdir(user_id, folder_id)
        workdir.mkdir(parents=True, exist_ok=True)
        if not (workdir / ".git").exists():
            raise GitError("该文件夹尚未拉取过仓库，请先拉取")
        await emit("写入本地工作区 ...")
        await self._sync_db_to_disk(user_id, folder_id, workdir)
        auth_url = self._auth_url(repo_url, token)
        await self._run(workdir, ["git", "remote", "set-url", "origin", auth_url], emit)
        code, _ = await self._run(workdir, ["git", "add", "-A"], emit)
        if code != 0:
            raise GitError("git add 失败")
        code, lines = await self._run(workdir, ["git", "commit", "-m", "[TianShu] update via workspace"], emit)
        if code != 0:
            joined = "\n".join(lines).lower()
            if "nothing to commit" in joined:
                await emit("无文件变更，无需提交")
                return {"pushed": 0, "committed": False}
            raise GitError("git commit 失败")
        await emit("git push")
        code, _ = await self._run(workdir, ["git", "push"], emit)
        if code != 0:
            raise GitError("推送失败（远端可能拒绝了推送）")
        await self._workspaces.touch_folder_git(user_id, folder_id)
        return {"pushed": 1, "committed": True}
