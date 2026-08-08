"""Server-side defaults and validation for per-user settings.

This is the single source of truth for the shape of each settings
section. The gateway merges a user's overrides (``user_settings``
table) over these defaults; sections without an override resolve to
the default.

Strict validation prevents typo'd or hostile values from landing in
the database -- unknown keys and invalid values raise ``ValueError``
which the router turns into a 400 response.
"""

from __future__ import annotations

from typing import Any

# Known settings sections. Unknown sections are rejected by the router
# (404) and the repository never stores them.
SETTINGS_SECTIONS = frozenset(
    {"appearance", "notification", "channels", "integrations", "tools"}
)

THEMES = frozenset({"system", "light", "dark"})
LOCALES = frozenset({"en-US", "zh-CN"})

DEFAULT_USER_SETTINGS: dict[str, dict[str, Any]] = {
    "appearance": {
        "theme": "system",
        "locale": "en-US",
    },
    "notification": {
        "enabled": True,
    },
    # Per-user preference layer over the admin-managed global config.
    # ``inherit_global=true`` (default) follows the global resources
    # as-is; setting it false activates the per-user enabled list.
    "channels": {
        "inherit_global": True,
        "enabled_channels": [],
    },
    "integrations": {
        "inherit_global": True,
        "enabled_integrations": [],
    },
    "tools": {
        "inherit_global": True,
        "enabled_servers": [],
    },
}


def is_valid_section(section: str) -> bool:
    return section in SETTINGS_SECTIONS


def get_default(section: str) -> dict[str, Any]:
    """Return a deep copy of the default value for a section."""
    if section not in DEFAULT_USER_SETTINGS:
        raise KeyError(f"Unknown settings section: {section}")
    return _deep_copy(DEFAULT_USER_SETTINGS[section])


def _deep_copy(value: dict[str, Any]) -> dict[str, Any]:
    import copy

    return copy.deepcopy(value)


# --------------------------------------------------------------------------
# Validation helpers
# --------------------------------------------------------------------------


def _fail(section: str, field: str, message: str) -> None:
    raise ValueError(f"Invalid value for '{section}.{field}': {message}")


def _require_dict(section: str, value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(
            f"Invalid value for '{section}': expected an object, got {type(value).__name__}"
        )
    return value


def _validate_bool(section: str, field: str, value: Any) -> bool:
    if not isinstance(value, bool):
        _fail(section, field, "expected a boolean")
    return value


# Limits guarding the JSONB store against oversized/hostile payloads.
MAX_STRING_LIST_LENGTH = 500
MAX_STRING_ITEM_LENGTH = 256
MAX_SECTION_VALUE_BYTES = 65536


def _validate_str_list(section: str, field: str, value: Any) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        _fail(section, field, "expected an array of strings")
    if len(value) > MAX_STRING_LIST_LENGTH:
        _fail(
            section,
            field,
            f"too many items (max {MAX_STRING_LIST_LENGTH})",
        )
    # De-duplicate while preserving order.
    seen: set[str] = set()
    result: list[str] = []
    for item in value:
        if len(item) > MAX_STRING_ITEM_LENGTH:
            _fail(
                section,
                field,
                f"item too long (max {MAX_STRING_ITEM_LENGTH} chars)",
            )
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def _validate_enum(section: str, field: str, value: Any, allowed: frozenset[str]) -> str:
    if not isinstance(value, str) or value not in allowed:
        allowed_list = ", ".join(sorted(allowed))
        _fail(section, field, f"expected one of: {allowed_list}")
    return value


# Per-section field validators: field -> callable(value) -> normalized.
_VALIDATORS: dict[str, dict[str, Any]] = {
    "appearance": {
        "theme": lambda v: _validate_enum("appearance", "theme", v, THEMES),
        "locale": lambda v: _validate_enum("appearance", "locale", v, LOCALES),
    },
    "notification": {
        "enabled": lambda v: _validate_bool("notification", "enabled", v),
    },
    "channels": {
        "inherit_global": lambda v: _validate_bool("channels", "inherit_global", v),
        "enabled_channels": lambda v: _validate_str_list(
            "channels", "enabled_channels", v
        ),
    },
    "integrations": {
        "inherit_global": lambda v: _validate_bool(
            "integrations", "inherit_global", v
        ),
        "enabled_integrations": lambda v: _validate_str_list(
            "integrations", "enabled_integrations", v
        ),
    },
    "tools": {
        "inherit_global": lambda v: _validate_bool("tools", "inherit_global", v),
        "enabled_servers": lambda v: _validate_str_list(
            "tools", "enabled_servers", v
        ),
    },
}


def validate_section_value(section: str, value: Any) -> dict[str, Any]:
    """Validate and normalize a full override value for a section.

    Every key present in *value* must be a known field for the section
    and pass its validator. Returns a new dict with only the known
    fields (unknown keys are rejected, not silently dropped).
    """
    if section not in _VALIDATORS:
        raise KeyError(f"Unknown settings section: {section}")
    data = _require_dict(section, value)
    validators = _VALIDATORS[section]
    unknown = set(data) - set(validators)
    if unknown:
        names = ", ".join(sorted(unknown))
        raise ValueError(f"Invalid value for '{section}': unknown field(s): {names}")
    normalized: dict[str, Any] = {}
    for field, validator in validators.items():
        if field in data:
            normalized[field] = validator(data[field])
    return normalized


def merge_effective(section: str, override: dict[str, Any] | None) -> dict[str, Any]:
    """Return ``default ∪ override`` for a section (shallow per field)."""
    merged = get_default(section)
    if override:
        merged.update(override)
    return merged
