"""
ComfyUI OpenMAIC 节点 - 完全独立版

不依赖任何外部服务，本地完成所有功能：
1. PPTX 导入 → 课件数据
2. 本地讲稿匹配
3. 讲解动作生成
4. 文本转语音
5. 音频混音
6. 视频导出
"""

import os
import json
import base64
import re
import subprocess
import asyncio
import uuid
from datetime import datetime
from typing import Tuple, Dict, Any, Optional, List

NODE_CLASS_MAPPINGS = {}
NODE_DISPLAY_NAME_MAPPINGS = {}
WEB_DIRECTORY = "./web"
UPLOAD_ROOT = os.environ.get("OPENMAIC_STANDALONE_UPLOAD_DIR", "E:/2026/OpenMAIC/outputs/comfyui-standalone/uploads")


def _clean_dialog_path(value: str) -> str:
    value = re.sub(r"[\u200e\u200f\u202a-\u202e\u2066-\u2069\ufeff]", "", value or "")
    return value.strip().strip('"').strip("'")


def _safe_path_part(value: str) -> str:
    value = _clean_dialog_path(value)
    value = value.replace("\\", "/").split("/")[-1]
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", value).strip(" .")
    return value or "upload"


def _safe_relative_path(value: str) -> str:
    value = _clean_dialog_path(value).replace("\\", "/")
    parts = [_safe_path_part(part) for part in value.split("/") if part and part not in (".", "..")]
    return os.path.join(*parts) if parts else _safe_path_part(value)


async def _save_upload_field(field, root_dir: str) -> str:
    relative = _safe_relative_path(field.filename or "upload")
    target = os.path.abspath(os.path.join(root_dir, relative))
    root_abs = os.path.abspath(root_dir)
    if not (target == root_abs or target.startswith(root_abs + os.sep)):
        raise RuntimeError("Invalid upload path")
    os.makedirs(os.path.dirname(target), exist_ok=True)
    with open(target, "wb") as handle:
        while True:
            chunk = await field.read_chunk()
            if not chunk:
                break
            handle.write(chunk)
    return target


def _open_windows_dialog(kind: str) -> str:
    if kind == "folder":
        script = r'''
Add-Type -AssemblyName System.Windows.Forms
[System.Windows.Forms.Application]::EnableVisualStyles()
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$owner = New-Object System.Windows.Forms.Form
$owner.TopMost = $true
$owner.ShowInTaskbar = $false
$owner.StartPosition = "CenterScreen"
$owner.Width = 1
$owner.Height = 1
$owner.Opacity = 0.01
$owner.Show()
$owner.Activate()
$dialog = New-Object System.Windows.Forms.FolderBrowserDialog
$dialog.Description = "Select courseware image folder"
$dialog.ShowNewFolderButton = $false
try {
  if ($dialog.ShowDialog($owner) -eq [System.Windows.Forms.DialogResult]::OK) {
    [Console]::Out.WriteLine($dialog.SelectedPath)
  }
} finally {
  $owner.Close()
  $owner.Dispose()
}
'''
    else:
        script = r'''
Add-Type -AssemblyName System.Windows.Forms
[System.Windows.Forms.Application]::EnableVisualStyles()
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$owner = New-Object System.Windows.Forms.Form
$owner.TopMost = $true
$owner.ShowInTaskbar = $false
$owner.StartPosition = "CenterScreen"
$owner.Width = 1
$owner.Height = 1
$owner.Opacity = 0.01
$owner.Show()
$owner.Activate()
$dialog = New-Object System.Windows.Forms.OpenFileDialog
$dialog.Title = "Select courseware file"
$dialog.Filter = "Courseware files (*.pptx;*.ppt;*.pdf;*.png;*.jpg;*.jpeg;*.webp;*.bmp;*.gif)|*.pptx;*.ppt;*.pdf;*.png;*.jpg;*.jpeg;*.webp;*.bmp;*.gif|All files (*.*)|*.*"
$dialog.Multiselect = $false
try {
  if ($dialog.ShowDialog($owner) -eq [System.Windows.Forms.DialogResult]::OK) {
    [Console]::Out.WriteLine($dialog.FileName)
  }
} finally {
  $owner.Close()
  $owner.Dispose()
}
'''
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-STA", "-ExecutionPolicy", "Bypass", "-Command", script],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(detail or "打开文件选择器失败")
    return _clean_dialog_path(result.stdout)


try:
    from aiohttp import web
    from server import PromptServer

    @PromptServer.instance.routes.post("/openmaic_standalone/browse_courseware")
    async def openmaic_standalone_browse_courseware(request):
        try:
            body = await request.json()
        except Exception:
            body = {}
        kind = "folder" if body.get("kind") == "folder" else "file"
        try:
            selected = await asyncio.to_thread(_open_windows_dialog, kind)
            return web.json_response({"path": selected, "cancelled": not bool(selected)})
        except Exception as exc:
            return web.json_response({"error": str(exc)}, status=500)

    @PromptServer.instance.routes.post("/openmaic_standalone/upload_courseware")
    async def openmaic_standalone_upload_courseware(request):
        try:
            reader = await request.multipart()
            upload_id = datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8]
            root_dir = os.path.abspath(os.path.join(UPLOAD_ROOT, upload_id))
            os.makedirs(root_dir, exist_ok=True)
            kind = request.query.get("kind") or "file"
            saved_paths: List[str] = []

            while True:
                field = await reader.next()
                if field is None:
                    break
                if field.name == "kind":
                    kind_text = (await field.text()).strip()
                    if kind_text:
                        kind = kind_text
                    continue
                if field.name != "files" or not field.filename:
                    continue
                saved_paths.append(await _save_upload_field(field, root_dir))

            if not saved_paths:
                return web.json_response({"error": "No file selected"}, status=400)

            if kind == "folder":
                selected_path = root_dir
            else:
                selected_path = saved_paths[0]

            return web.json_response({
                "path": selected_path,
                "count": len(saved_paths),
                "uploadDir": root_dir,
            })
        except Exception as exc:
            return web.json_response({"error": str(exc)}, status=500)

except Exception:
    pass


def register_node(cls):
    NODE_CLASS_MAPPINGS[cls.__name__] = cls
    NODE_DISPLAY_NAME_MAPPINGS[cls.__name__] = cls.DISPLAY_NAME
    return cls


# ============== 工具节点 ==============

@register_node
class OpenMAIC_拆分讲解列表:
    """
    拆分讲解列表 - 拆分讲解列表用于逐条处理
    """
    CATEGORY = "OpenMAIC/工具"
    DISPLAY_NAME = "🔢 拆分讲解列表"
    RETURN_TYPES = ("DICT", "INT", "INT")
    RETURN_NAMES = ("单条讲解", "当前索引", "总数")
    FUNCTION = "process"

    @classmethod
    def INPUT_TYPES(cls) -> Dict[str, Any]:
        return {
            "required": {
                "讲解列表": ("LIST", {"tooltip": "讲解字典列表"}),
            },
            "optional": {
                "索引": ("INT", {"default": 0, "min": 0, "max": 9999}),
            },
        }

    def process(self, 讲解列表: List[Dict], 索引: int = 0) -> Tuple[Dict, int, int]:
        总数 = len(讲解列表)
        if 索引 < 0 or 索引 >= 总数:
            return ({"slide_index": 0, "text": ""}, 索引, 总数)
        return (讲解列表[索引], 索引, 总数)


# ============== 导入视频导出节点 ==============
try:
    from .video_export import (
        NODE_CLASS_MAPPINGS as VIDEO_EXPORT_NODES,
        NODE_DISPLAY_NAME_MAPPINGS as VIDEO_EXPORT_DISPLAY_NAMES,
    )
    _has_video_export = True
except ImportError:
    import sys
    sys.path.insert(0, os.path.dirname(__file__))
    from video_export import (
        NODE_CLASS_MAPPINGS as VIDEO_EXPORT_NODES,
        NODE_DISPLAY_NAME_MAPPINGS as VIDEO_EXPORT_DISPLAY_NAMES,
    )
    _has_video_export = True

# ============== 导入 FunASR 字幕对齐节点 ==============
try:
    from .funasr_subtitles import (
        NODE_CLASS_MAPPINGS as FUNASR_NODES,
        NODE_DISPLAY_NAME_MAPPINGS as FUNASR_DISPLAY_NAMES,
    )
    _has_funasr = True
except ImportError:
    import sys
    sys.path.insert(0, os.path.dirname(__file__))
    from funasr_subtitles import (
        NODE_CLASS_MAPPINGS as FUNASR_NODES,
        NODE_DISPLAY_NAME_MAPPINGS as FUNASR_DISPLAY_NAMES,
    )
    _has_funasr = True

# ============== 导入 TTS 节点 ==============
try:
    from .tts_nodes import (
        NODE_CLASS_MAPPINGS as TTS_NODES,
        NODE_DISPLAY_NAME_MAPPINGS as TTS_DISPLAY_NAMES,
    )
    _has_tts = True
except ImportError:
    import sys
    sys.path.insert(0, os.path.dirname(__file__))
    from tts_nodes import (
        NODE_CLASS_MAPPINGS as TTS_NODES,
        NODE_DISPLAY_NAME_MAPPINGS as TTS_DISPLAY_NAMES,
    )
    _has_tts = True

# ============== 导入独立版导入节点 ==============
try:
    from .import_nodes import (
        NODE_CLASS_MAPPINGS as STANDALONE_IMPORT_NODES,
        NODE_DISPLAY_NAME_MAPPINGS as STANDALONE_IMPORT_DISPLAY_NAMES,
    )
    _has_standalone_import = True
except ImportError:
    import sys
    sys.path.insert(0, os.path.dirname(__file__))
    from import_nodes import (
        NODE_CLASS_MAPPINGS as STANDALONE_IMPORT_NODES,
        NODE_DISPLAY_NAME_MAPPINGS as STANDALONE_IMPORT_DISPLAY_NAMES,
    )
    _has_standalone_import = True

# ============== 导入独立完整工作流节点 ==============
try:
    from .standalone_full import (
        NODE_CLASS_MAPPINGS as STANDALONE_FULL_NODES,
        NODE_DISPLAY_NAME_MAPPINGS as STANDALONE_FULL_DISPLAY_NAMES,
    )
    _has_standalone_full = True
except ImportError:
    import sys
    sys.path.insert(0, os.path.dirname(__file__))
    from standalone_full import (
        NODE_CLASS_MAPPINGS as STANDALONE_FULL_NODES,
        NODE_DISPLAY_NAME_MAPPINGS as STANDALONE_FULL_DISPLAY_NAMES,
    )
    _has_standalone_full = True

# ============== 合并所有节点 ==============
NODE_CLASS_MAPPINGS = {
    # 工具节点
    "OpenMAIC_拆分讲解列表": OpenMAIC_拆分讲解列表,
    # 独立版导入节点（完全本地化）
    **STANDALONE_IMPORT_NODES,
    # 独立完整工作流节点
    **STANDALONE_FULL_NODES,
    # 视频导出节点
    **VIDEO_EXPORT_NODES,
    # FunASR 字幕对齐节点
    **FUNASR_NODES,
    # TTS 节点
    **TTS_NODES,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    # 工具节点
    "OpenMAIC_拆分讲解列表": "🔢 拆分讲解列表",
    # 独立版导入节点
    **STANDALONE_IMPORT_DISPLAY_NAMES,
    # 独立完整工作流节点
    **STANDALONE_FULL_DISPLAY_NAMES,
    # 视频导出节点
    **VIDEO_EXPORT_DISPLAY_NAMES,
    # FunASR 字幕对齐节点
    **FUNASR_DISPLAY_NAMES,
    # TTS 节点
    **TTS_DISPLAY_NAMES,
}

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]
