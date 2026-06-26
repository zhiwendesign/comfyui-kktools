from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from aiohttp import web


_ROUTES_REGISTERED = False


def imagen_studio_nodes_module():
    module = sys.modules.get("imagen_studio")
    if module is not None:
        return module

    module_path = Path(__file__).resolve().parent / "nodes" / "imagen_studio.py"
    spec = importlib.util.spec_from_file_location("imagen_studio", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load Imagen Studio nodes from {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["imagen_studio"] = module
    spec.loader.exec_module(module)
    return module


def register_routes() -> None:
    global _ROUTES_REGISTERED
    if _ROUTES_REGISTERED:
        return
    try:
        from server import PromptServer
    except Exception:
        return

    routes = PromptServer.instance.routes
    imagen_nodes = imagen_studio_nodes_module()

    @routes.get("/imagen-studio/templates")
    async def get_templates(_request):
        return web.json_response({"templates": imagen_nodes.list_saved_template_summaries()})

    @routes.get("/imagen-studio/templates/thumbnail")
    async def get_template_thumbnail(request):
        template_id = request.rel_url.query.get("id", "")
        path = imagen_nodes.resolve_template_thumbnail_path(template_id)
        if path.is_file():
            return web.FileResponse(path)
        return web.Response(status=404, text="template thumbnail not found")

    @routes.patch("/imagen-studio/templates/{template_id}")
    async def patch_template(request):
        template_id = request.match_info.get("template_id", "")
        try:
            body = await request.json()
        except Exception:
            body = {}
        try:
            record = imagen_nodes.update_template_name(template_id, str(body.get("name") or ""))
            return web.json_response({"ok": True, "template": record})
        except imagen_nodes.TemplateDistillError as exc:
            return web.json_response({"ok": False, "error": str(exc)}, status=400)

    @routes.delete("/imagen-studio/templates/{template_id}")
    async def delete_template(request):
        template_id = request.match_info.get("template_id", "")
        try:
            record = imagen_nodes.delete_template_from_library(template_id)
            return web.json_response({"ok": True, "template": record})
        except imagen_nodes.TemplateDistillError as exc:
            return web.json_response({"ok": False, "error": str(exc)}, status=400)

    _ROUTES_REGISTERED = True
