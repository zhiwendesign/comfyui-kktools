"""REST API routes for kktools settings panel."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from aiohttp import web

from .config_manager import get_config_path, get_masked_settings, get_settings, save_settings, update_setting

_SETTINGS_REGISTERED = False


def _bearer_headers(api_key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key}",
        "User-Agent": "ComfyUI-kktools-Settings/1.0",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def _masked_headers() -> dict[str, str]:
    return {
        "Authorization": "Bearer ***",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def _http_get_json(url: str, headers: dict[str, str], timeout: int = 30) -> dict[str, Any] | None:
    """Send a GET request and return parsed JSON, or None on error."""
    try:
        request = urllib.request.Request(url, headers=headers, method="GET")
        with urllib.request.urlopen(request, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", "replace")
            return json.loads(raw)
    except Exception:
        return None


def _http_post_json(
    url: str, headers: dict[str, str], body: dict[str, Any], timeout: int = 30
) -> dict[str, Any] | None:
    """Send a POST request with JSON body and return parsed JSON, or None on error."""
    try:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(url, data=data, headers=headers, method="POST")
        with urllib.request.urlopen(request, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", "replace")
            return json.loads(raw)
    except Exception:
        return None


def _fetch_models_from_url(base_url: str, api_key: str) -> tuple[bool, list[str], str]:
    """Fetch model list from a /v1/models endpoint. Returns (ok, models, error_message)."""
    url = f"{base_url.rstrip('/')}/v1/models"
    headers = _bearer_headers(api_key)
    data = _http_get_json(url, headers)
    if data is None:
        return False, [], "无法连接到 API，请检查 Base URL 和网络"
    # Try OpenAI-compatible format
    models = []
    if isinstance(data, dict):
        raw = data.get("data") or data.get("models") or []
        if isinstance(raw, list):
            for m in raw:
                if isinstance(m, dict):
                    models.append(m.get("id") or m.get("name") or str(m))
                elif isinstance(m, str):
                    models.append(m)
    if not models and isinstance(data, list):
        for m in data:
            if isinstance(m, dict):
                models.append(m.get("id") or m.get("name") or str(m))
            elif isinstance(m, str):
                models.append(m)
    if not models:
        # Fallback: try to extract any string IDs
        return False, [], "API 返回的数据中未找到模型列表"
    return True, models, ""


def _test_imagen_studio() -> tuple[bool, str, list[str]]:
    """Test imagen_studio connectivity. Returns (ok, message, models)."""
    settings = get_settings()
    api_key = str(settings.get("apiKey") or "").strip()
    base_url = str(settings.get("baseUrl") or "").strip()
    if not api_key:
        return False, "请先填写 API Key", []
    if not base_url:
        return False, "请先填写 Base URL", []
    ok, models, error = _fetch_models_from_url(base_url, api_key)
    if ok:
        return True, f"连接成功，找到 {len(models)} 个模型", models
    return False, error, []


def _test_runninghub() -> tuple[bool, str, list[str]]:
    """Test runninghub connectivity. Returns (ok, message, models)."""
    settings = get_settings()
    api_key = str(settings.get("runninghubApiKey") or "").strip()
    base_url = str(settings.get("runninghubBaseUrl") or "").strip()
    if not api_key:
        return False, "请先填写 RunningHub API Key", []
    if not base_url:
        return False, "请先填写 RunningHub Base URL", []
    ok, models, error = _fetch_models_from_url(base_url, api_key)
    if ok:
        return True, f"连接成功，找到 {len(models)} 个模型", models
    return False, error, []


def register_routes() -> None:
    global _SETTINGS_REGISTERED
    if _SETTINGS_REGISTERED:
        return
    try:
        from server import PromptServer
    except Exception:
        return

    routes = PromptServer.instance.routes

    @routes.get("/kktools/settings")
    async def get_all_settings(_request):
        """Return all settings with API keys masked."""
        return web.json_response({"ok": True, "data": get_masked_settings(), "configPath": get_config_path()})

    @routes.post("/kktools/settings")
    async def save_all_settings(request):
        """Save full config from request body."""
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"ok": False, "error": "无效的 JSON"}, status=400)
        if not isinstance(body, dict):
            return web.json_response({"ok": False, "error": "配置数据格式错误"}, status=400)
        if save_settings(body):
            return web.json_response({"ok": True, "configPath": get_config_path()})
        return web.json_response({"ok": False, "error": "保存失败"}, status=500)

    @routes.patch("/kktools/settings")
    async def patch_settings(request):
        """Partial update: body is {field: value, ...}."""
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"ok": False, "error": "无效的 JSON"}, status=400)
        if not isinstance(body, dict):
            return web.json_response({"ok": False, "error": "配置数据格式错误"}, status=400)
        for key, value in body.items():
            update_setting(key, value)
        return web.json_response({"ok": True})

    @routes.get("/kktools/settings/{provider}/models")
    async def get_provider_models(request):
        """Fetch model list from a provider's API."""
        provider = request.match_info.get("provider", "")
        if provider == "imagen_studio":
            ok, models, error = _fetch_models_from_url(
                get_settings().get("baseUrl", ""),
                get_settings().get("apiKey", ""),
            )
            if ok:
                return web.json_response({"ok": True, "models": models})
            return web.json_response({"ok": False, "error": error}, status=400)
        if provider == "runninghub":
            ok, models, error = _fetch_models_from_url(
                get_settings().get("runninghubBaseUrl", ""),
                get_settings().get("runninghubApiKey", ""),
            )
            if ok:
                return web.json_response({"ok": True, "models": models})
            return web.json_response({"ok": False, "error": error}, status=400)
        return web.json_response({"ok": False, "error": f"未知 provider: {provider}"}, status=400)

    @routes.post("/kktools/settings/{provider}/test")
    async def test_provider(request):
        """Test connectivity for a provider."""
        provider = request.match_info.get("provider", "")
        if provider == "imagen_studio":
            ok, message, models = _test_imagen_studio()
            resp = {"ok": ok, "message": message}
            if ok:
                resp["models"] = models
            return web.json_response(resp)
        if provider == "runninghub":
            ok, message, models = _test_runninghub()
            resp = {"ok": ok, "message": message}
            if ok:
                resp["models"] = models
            return web.json_response(resp)
        return web.json_response({"ok": False, "error": f"未知 provider: {provider}"}, status=400)

    _SETTINGS_REGISTERED = True
