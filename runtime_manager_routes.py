"""Local runtime resource statistics for the kktools toolbar monitor."""

from __future__ import annotations

import os
import time

import psutil
from aiohttp import web


_ROUTES_REGISTERED = False
_STARTED_AT = time.time()


def _used_percent(total: int, free: int) -> float | None:
    if total <= 0:
        return None
    return round(max(0.0, min(100.0, (total - free) * 100 / total)), 1)


def _device_utilization(torch_module, device) -> float | None:
    backend = getattr(torch_module, device.type, None)
    utilization = getattr(backend, "utilization", None)
    if not callable(utilization):
        return None
    try:
        return round(float(utilization(device)), 1)
    except Exception:
        return None


def get_runtime_stats() -> dict:
    import comfy.model_management as model_management

    memory = psutil.virtual_memory()
    process = psutil.Process(os.getpid())
    primary_device = model_management.get_torch_device()
    devices = model_management.get_all_torch_devices()
    if primary_device in devices:
        devices = [primary_device] + [device for device in devices if device != primary_device]
    else:
        devices = [primary_device] + list(devices)

    gpu_devices = []
    for device in devices:
        if device.type == "cpu":
            continue
        total, _torch_total = model_management.get_total_memory(device, torch_total_too=True)
        free, _torch_free = model_management.get_free_memory(device, torch_free_too=True)
        gpu_devices.append(
            {
                "name": model_management.get_torch_device_name(device),
                "type": device.type,
                "index": device.index,
                "utilization": _device_utilization(model_management.torch, device),
                "memory_total": total,
                "memory_free": free,
                "memory_used": max(0, total - free),
                "memory_percent": _used_percent(total, free),
            }
        )

    return {
        "cpu": {
            "percent": round(psutil.cpu_percent(interval=None), 1),
            "logical_cores": psutil.cpu_count(logical=True),
        },
        "memory": {
            "total": memory.total,
            "available": memory.available,
            "used": memory.used,
            "percent": round(memory.percent, 1),
        },
        "process": {
            "memory_used": process.memory_info().rss,
            "uptime_seconds": round(time.time() - _STARTED_AT),
        },
        "devices": gpu_devices,
    }


def register_routes() -> None:
    global _ROUTES_REGISTERED
    if _ROUTES_REGISTERED:
        return
    try:
        from server import PromptServer
    except Exception:
        return

    @PromptServer.instance.routes.get("/kktools/runtime_stats")
    async def runtime_stats(_request):
        try:
            return web.json_response({"ok": True, "data": get_runtime_stats()})
        except Exception as exc:
            return web.json_response({"ok": False, "error": str(exc)}, status=500)

    _ROUTES_REGISTERED = True


psutil.cpu_percent(interval=None)
