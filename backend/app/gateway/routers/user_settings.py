"""REST API for per-user settings ("千人千面").

Each user owns an independent copy of the settings sections
(``appearance`` / ``notification`` / ``channels`` / ``integrations`` /
``tools``). The gateway merges the user's overrides (``user_settings``
table) over the server-side defaults registered in
:mod:`tianshu.settings.defaults` and returns the *effective* value.

Sections without an override resolve to the default; ``DELETE`` resets
a section to its default. All reads/writes are scoped to the current
user via ``get_effective_user_id()`` -- there is no cross-user access
path.

This router stores no secrets: API keys, OAuth tokens and MCP
credentials stay in their existing admin-managed stores.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, Body, HTTPException, Request

from tianshu.persistence.user_settings.sql import UserSettingsRepository
from tianshu.runtime.user_context import get_effective_user_id
from tianshu.settings.defaults import (
    MAX_SECTION_VALUE_BYTES,
    SETTINGS_SECTIONS,
    get_default,
    is_valid_section,
    merge_effective,
    validate_section_value,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/user", tags=["user-settings"])


def _repo() -> UserSettingsRepository:
    return UserSettingsRepository()


def _settings_section_response(
    section: str,
    value: dict[str, Any] | None,
) -> dict[str, Any]:
    """Build the per-section response shape ``{section, default, value, effective}``."""
    return {
        "section": section,
        "default": get_default(section),
        "value": value,
        "effective": merge_effective(section, value),
    }


def _require_section(section: str) -> None:
    if not is_valid_section(section):
        raise HTTPException(
            status_code=404,
            detail=f"Unknown settings section: {section}",
        )


def _http_400(detail: str) -> HTTPException:
    return HTTPException(status_code=400, detail=detail)


def _ensure_db() -> UserSettingsRepository:
    try:
        repo = _repo()
    except RuntimeError as exc:
        raise HTTPException(
            status_code=503,
            detail="Persistence is not available (database backend=memory)",
        ) from exc
    return repo


async def _load_override(
    repo: UserSettingsRepository, user_id: str, section: str
) -> dict[str, Any] | None:
    try:
        return await repo.get(user_id, section)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=503,
            detail="Persistence is not available (database backend=memory)",
        ) from exc


@router.get("/settings")
async def get_all_settings(request: Request) -> dict[str, Any]:
    """Return defaults, overrides and effective values for all sections."""
    user_id = get_effective_user_id()
    repo = _ensure_db()
    overrides = await repo.list_for_user(user_id)
    defaults: dict[str, Any] = {}
    values: dict[str, Any] = {}
    effective: dict[str, Any] = {}
    for section in sorted(SETTINGS_SECTIONS):
        defaults[section] = get_default(section)
        value = overrides.get(section)
        if value is not None:
            values[section] = value
        effective[section] = merge_effective(section, value)
    return {"defaults": defaults, "values": values, "effective": effective}


@router.get("/settings/{section}")
async def get_settings_section(section: str) -> dict[str, Any]:
    _require_section(section)
    user_id = get_effective_user_id()
    repo = _ensure_db()
    value = await _load_override(repo, user_id, section)
    return _settings_section_response(section, value)


@router.put("/settings/{section}")
async def put_settings_section(
    section: str,
    payload: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    """Merge *payload* over the user's existing override for a section.

    The merged result is validated against the section schema before it
    is persisted, so invalid input returns 400 and never touches the DB.
    """
    _require_section(section)
    if not payload:
        raise _http_400(f"Invalid value for '{section}': body must be a non-empty object")
    size = len(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
    if size > MAX_SECTION_VALUE_BYTES:
        raise _http_400(
            f"Invalid value for '{section}': payload too large (max {MAX_SECTION_VALUE_BYTES} bytes)"
        )

    user_id = get_effective_user_id()
    repo = _ensure_db()
    current = await _load_override(repo, user_id, section) or {}
    merged = {**current, **payload}
    try:
        normalized = validate_section_value(section, merged)
    except ValueError as exc:
        raise _http_400(str(exc)) from exc

    stored = await repo.upsert(user_id=user_id, key=section, value=normalized)
    return _settings_section_response(section, stored)


@router.delete("/settings/{section}")
async def delete_settings_section(section: str) -> dict[str, Any]:
    """Reset a section to its default (delete the user's override)."""
    _require_section(section)
    user_id = get_effective_user_id()
    repo = _ensure_db()
    await repo.delete(user_id=user_id, key=section)
    return _settings_section_response(section, None)
