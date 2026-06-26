"""Unified config read/write for kktools settings panel."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# Fields
IMAGEN_STUDIO_KEYS = ["apiKey", "baseUrl", "visionModel", "textModel"]
RUNNINGHUB_KEYS = ["runninghubApiKey", "runninghubBaseUrl"]
SECRET_KEYS = {"apiKey", "runninghubApiKey"}

# Default values
DEFAULT_SETTINGS: dict[str, str] = {
    "apiKey": "",
    "baseUrl": "https://api.zuco.ai/v1",
    "visionModel": "gpt-5.5",
    "textModel": "gpt-5.5",
    "runninghubApiKey": "",
    "runninghubBaseUrl": "https://www.runninghub.cn/openapi/v2",
}


def _config_path() -> Path:
    """Return the path to imagen-studio/config.json."""
    return Path(__file__).resolve().parents[1] / "imagen-studio" / "config.json"


def get_config_path() -> str:
    """Return the concrete config path used by the settings panel."""
    return str(_config_path())


def get_settings() -> dict[str, str]:
    """Read all settings from config.json. Returns DEFAULT_SETTINGS if file is missing."""
    path = _config_path()
    if not path.is_file():
        return dict(DEFAULT_SETTINGS)
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return dict(DEFAULT_SETTINGS)
        # Merge with defaults so missing keys get defaults
        result = dict(DEFAULT_SETTINGS)
        result.update(data)
        return result
    except (json.JSONDecodeError, OSError):
        return dict(DEFAULT_SETTINGS)


def save_settings(data: dict[str, Any]) -> bool:
    """Save full settings to config.json. Returns True on success."""
    if not isinstance(data, dict):
        return False
    path = _config_path()
    try:
        settings = get_settings()
        for key, value in data.items():
            if key in SECRET_KEYS and _should_preserve_secret(value):
                continue
            settings[key] = value
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)
        return True
    except (OSError, TypeError):
        return False


def get_setting_value(key: str, default: str | None = None) -> str | None:
    """Read a single setting value."""
    settings = get_settings()
    return settings.get(key, default)


def update_setting(key: str, value: Any) -> bool:
    """Update a single setting and persist to config.json."""
    settings = get_settings()
    settings[key] = value
    return save_settings(settings)


def mask_api_key(key: str | None) -> str:
    """Mask an API key for display. Returns '' for empty/None, '***' otherwise."""
    if not key or not str(key).strip():
        return ""
    return "***"


def _should_preserve_secret(value: Any) -> bool:
    """Treat blank and masked secret fields as 'keep the existing value'."""
    return str(value or "").strip() in {"", "***"}


def get_masked_settings() -> dict[str, str]:
    """Return all settings with API keys masked for frontend display."""
    settings = get_settings()
    masked = dict(settings)
    for key in SECRET_KEYS:
        masked[key] = mask_api_key(masked.get(key))
    return masked


def get_imagen_studio_settings() -> dict[str, str]:
    """Return only imagen_studio provider settings."""
    settings = get_settings()
    return {k: settings.get(k, DEFAULT_SETTINGS.get(k, "")) for k in IMAGEN_STUDIO_KEYS}


def get_runninghub_settings() -> dict[str, str]:
    """Return only runninghub provider settings."""
    settings = get_settings()
    return {k: settings.get(k, DEFAULT_SETTINGS.get(k, "")) for k in RUNNINGHUB_KEYS}
