"""
OpenMAIC ComfyUI standalone full pipeline nodes.

These nodes do not call the OpenMAIC Next.js service. They run inside ComfyUI
and use local files, optional OpenAI-compatible LLM APIs, local/remote TTS APIs,
and ffmpeg to produce a static courseware video.
"""

import base64
import hashlib
import json
import os
import posixpath
import re
import shutil
import subprocess
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from xml.etree import ElementTree as ET

try:
    from .import_nodes import (
        convert_pptx_to_pdf,
        extract_pptx_text,
        extract_pptx_text_fallback,
        find_powerpoint,
        parse_pdf_extract_text,
        parse_pdf_to_images,
        split_speech_segments,
    )
except Exception:
    from import_nodes import (  # type: ignore
        convert_pptx_to_pdf,
        extract_pptx_text,
        extract_pptx_text_fallback,
        find_powerpoint,
        parse_pdf_extract_text,
        parse_pdf_to_images,
        split_speech_segments,
    )

try:
    from .tts_nodes import OpenMAIC_文本转语音
except Exception:
    from tts_nodes import OpenMAIC_文本转语音  # type: ignore


NODE_CLASS_MAPPINGS: Dict[str, Any] = {}
NODE_DISPLAY_NAME_MAPPINGS: Dict[str, str] = {}

DEFAULT_ROOT = "E:/2026/OpenMAIC/outputs/comfyui-standalone"
DEFAULT_PAGE_DIR = f"{DEFAULT_ROOT}/pages"
DEFAULT_AUDIO_DIR = f"{DEFAULT_ROOT}/audio"
DEFAULT_VIDEO_DIR = f"{DEFAULT_ROOT}/video"

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}
PRESENTATION_EXTS = {".pptx", ".ppt"}
RESOLUTIONS = {
    "1K 1280x720": (1280, 720, 4),
    "2K 1920x1080": (1920, 1080, 8),
    "4K 3840x2160": (3840, 2160, 35),
}

SUBTITLE_STYLES = {
    "前端默认": {
        "font": "Microsoft YaHei",
        "size": 48,
        "color": "&H00FFFFFF",
        "outline": "&H00000000",
        "outline_width": 4,
        "shadow": 2,
        "alignment": 2,
        "margin_v": 70,
    },
    "黑底条": {
        "font": "Microsoft YaHei",
        "size": 44,
        "color": "&H00FFFFFF",
        "outline": "&H00000000",
        "outline_width": 2,
        "shadow": 1,
        "alignment": 2,
        "margin_v": 55,
        "border_style": 3,
        "back_color": "&HAA000000",
    },
    "大字描边": {
        "font": "Microsoft YaHei",
        "size": 60,
        "color": "&H00FFFFFF",
        "outline": "&H00000000",
        "outline_width": 6,
        "shadow": 2,
        "alignment": 2,
        "margin_v": 80,
    },
    "顶部字幕": {
        "font": "Microsoft YaHei",
        "size": 44,
        "color": "&H00FFFFFF",
        "outline": "&H00000000",
        "outline_width": 4,
        "shadow": 2,
        "alignment": 8,
        "margin_v": 55,
    },
    "无背景简洁": {
        "font": "Microsoft YaHei",
        "size": 42,
        "color": "&H00FFFFFF",
        "outline": "&H00000000",
        "outline_width": 2,
        "shadow": 0,
        "alignment": 2,
        "margin_v": 60,
    },
}


def register_node(cls):
    NODE_CLASS_MAPPINGS[cls.__name__] = cls
    NODE_DISPLAY_NAME_MAPPINGS[cls.__name__] = cls.DISPLAY_NAME
    return cls


def ensure_dir(path: str) -> str:
    normalized = os.path.abspath(os.path.normpath(path))
    os.makedirs(normalized, exist_ok=True)
    return normalized


def json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2)


def json_loads(value: str, name: str) -> Any:
    try:
        return json.loads(value or "null")
    except Exception as exc:
        raise ValueError(f"{name} 不是有效 JSON: {exc}") from exc


def normalize_local_path_input(value: str) -> str:
    text = str(value or "")
    # Windows "Copy as path" / rich-text copies can include invisible bidi marks.
    text = re.sub(r"[\u200e\u200f\u202a-\u202e\u2066-\u2069\ufeff]", "", text)
    text = text.strip().strip('"').strip("'")
    return os.path.abspath(os.path.normpath(text)) if text else ""


def natural_key(value: str) -> List[Any]:
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", value)]


def clamp(value: float, min_value: float, max_value: float) -> float:
    try:
        numeric = float(value)
    except Exception:
        numeric = min_value
    return min(max_value, max(min_value, numeric))


def coerce_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return value != 0
    text = str(value).strip().lower()
    if text in ("true", "1", "yes", "on", "开启", "是"):
        return True
    if text in ("false", "0", "no", "off", "关闭", "否"):
        return False
    return default


def copy_or_overwrite(src: str, dst: str, overwrite: bool) -> None:
    if os.path.exists(dst) and not overwrite:
        return
    shutil.copy2(src, dst)


def find_tool(name: str, env_names: Optional[List[str]] = None) -> str:
    for env_name in env_names or []:
        candidate = os.environ.get(env_name)
        if candidate and os.path.exists(candidate):
            return candidate
    bundled = [
        Path("E:/2026/OpenMAIC/vendor/ffmpeg/bin") / f"{name}.exe",
        Path("E:/COMFYUI/ComfyUI-aki-v1.5/ffmpeg/bin") / f"{name}.exe",
    ]
    for candidate in bundled:
        if candidate.exists():
            return str(candidate)
    found = shutil.which(name) or shutil.which(f"{name}.exe")
    if found:
        return found
    raise FileNotFoundError(f"找不到 {name}，请把 ffmpeg/ffprobe 加入 PATH，或设置环境变量。")


def run_command(cmd: List[str], timeout: int = 600) -> None:
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if result.returncode != 0:
        stderr = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(f"命令执行失败: {' '.join(cmd)}\n{stderr}")


def ffprobe_duration(path: str) -> float:
    ffprobe = find_tool("ffprobe", ["OPENMAIC_FFPROBE_PATH", "FFPROBE_PATH"])
    result = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            path,
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    try:
        duration = float((result.stdout or "").strip())
    except Exception:
        duration = 0.0
    if duration <= 0:
        raise RuntimeError(f"无法读取媒体时长: {path}")
    return duration


def _comfyui_audio_to_waveform(audio: Any, label: str = "ComfyUI AUDIO") -> Tuple[Any, int]:
    try:
        import numpy as np
    except Exception as exc:
        raise RuntimeError(f"处理 {label} 输入需要 numpy。") from exc

    sr: Optional[int] = None
    data: Any = None

    if isinstance(audio, dict):
        sr = audio.get("sample_rate") or audio.get("sr") or audio.get("rate")
        for key in ("waveform", "samples", "audio", "data"):
            if key in audio:
                data = audio[key]
                break
    elif isinstance(audio, (tuple, list)):
        cand_ints = [x for x in audio if isinstance(x, (int, np.integer))]
        cand_arrays = [x for x in audio if hasattr(x, "shape")]
        if len(cand_ints) >= 1 and len(cand_arrays) >= 1:
            sr = int(cand_ints[0])
            data = cand_arrays[0]
        elif len(audio) == 2:
            a, b = audio
            if isinstance(a, (int, np.integer)) and hasattr(b, "shape"):
                sr, data = int(a), b
            elif isinstance(b, (int, np.integer)) and hasattr(a, "shape"):
                sr, data = int(b), a

    if sr is None or data is None:
        raise ValueError(f"{label} 不是有效 AUDIO 数据。")

    try:
        sr_value = int(float(sr))
    except Exception as exc:
        raise ValueError(f"{label} 采样率无效: {sr}") from exc
    if sr_value <= 0:
        raise ValueError(f"{label} 采样率无效: {sr}")

    if hasattr(data, "detach"):
        data = data.detach()
    if hasattr(data, "cpu"):
        data = data.cpu().numpy()
    wav = np.asarray(data)

    if wav.ndim == 0:
        raise ValueError(f"{label} waveform 为空。")
    if wav.ndim == 1:
        wav = wav[None, :]
    elif wav.ndim == 2:
        ch_dim = 0 if wav.shape[0] <= 8 and wav.shape[0] <= wav.shape[1] else 1 if wav.shape[1] <= 8 else 0
        if ch_dim == 1:
            wav = np.transpose(wav, (1, 0))
    elif wav.ndim >= 3:
        sizes = list(wav.shape)
        sample_axis = int(np.argmax(sizes))
        axes = [i for i in range(wav.ndim) if i != sample_axis] + [sample_axis]
        wav = np.transpose(wav, axes)
        c = int(np.prod(wav.shape[:-1]))
        wav = np.reshape(wav, (c, wav.shape[-1]))
    else:
        raise ValueError(f"{label} waveform 维度不受支持。")

    if np.issubdtype(wav.dtype, np.integer):
        info = np.iinfo(wav.dtype)
        denom = float(max(abs(info.min), abs(info.max))) or 32767.0
        wav = wav.astype(np.float32) / denom
    else:
        wav = np.clip(wav.astype(np.float32), -1.0, 1.0)

    return wav, sr_value


def _save_pcm16_wav(path: str, wav: Any, sample_rate: int, label: str = "ComfyUI AUDIO") -> None:
    try:
        import numpy as np
    except Exception as exc:
        raise RuntimeError(f"保存 {label} 临时 WAV 需要 numpy。") from exc

    wav = np.clip(np.asarray(wav, dtype=np.float32), -1.0, 1.0)
    if wav.ndim == 1:
        wav = wav[None, :]
    pcm = (wav * 32767.0).astype(np.int16)

    import contextlib
    import wave

    with contextlib.closing(wave.open(path, "wb")) as wf:
        wf.setnchannels(int(pcm.shape[0]))
        wf.setsampwidth(2)
        wf.setframerate(int(sample_rate))
        wf.writeframes(np.transpose(pcm, (1, 0)).tobytes())


def prepare_background_music_source(
    background_music: Any,
    audio_path: str,
    work_dir: str,
) -> Tuple[str, str, str]:
    source_kind = "none"
    selected_path = ""
    warning = ""

    if isinstance(background_music, str):
        audio_path = audio_path or background_music
    elif background_music is not None:
        try:
            wav, sample_rate = _comfyui_audio_to_waveform(background_music, "背景音乐")
            selected_path = os.path.join(work_dir, "background-music.wav")
            _save_pcm16_wav(selected_path, wav, sample_rate, "背景音乐")
            source_kind = "audio"
            return selected_path, source_kind, warning
        except Exception as exc:
            warning = f"背景音乐 AUDIO 输入无效，已忽略: {exc}"
            return "", source_kind, warning

    normalized_path = normalize_local_path_input(audio_path)
    if normalized_path and os.path.exists(normalized_path):
        source_kind = "path"
        selected_path = normalized_path
    elif normalized_path:
        warning = f"背景音乐路径不存在: {normalized_path}"

    return selected_path, source_kind, warning


def image_size(path: str) -> Tuple[int, int]:
    try:
        from PIL import Image

        with Image.open(path) as img:
            return int(img.width), int(img.height)
    except Exception:
        return 1920, 1080


def clean_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    return text


def strip_markdown_fences(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```(?:json|text|markdown)?\s*", "", text, flags=re.I)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


def normalize_segments(text: str, max_chars: int = 320) -> List[str]:
    return split_speech_segments(clean_text(text), max_chars=max_chars) or []


DESIGN_PROMPT_CUTOFF_PATTERN = re.compile(
    r"Prompt\s*[:：]\s*(?:STYLE|\{\s*[\"']prompt[\"']\s*:)|"
    r"STYLE(?:\s+ELEMENTS\s+TO\s+PRESERVE)?\s*[:：]|"
    r"SUBJECT\s+ELEMENTS\s+TO\s+PRESERVE\s*[:：]|"
    r"Negative\s*[:：]|模型\s*[:：]|服务商\s*[:：]|图像\s*比例\s*[:：]|分辨率\s*[:：]",
    re.I,
)


def repair_mojibake_text(text: str) -> str:
    value = str(text or "")
    if not value:
        return ""

    def score(candidate: str) -> int:
        markers = ("�", "Ã", "Â", "â", "璇", "涓", "鍙", "鏂", "绗", "鐢", "妯", "瀵", "搴")
        return sum(candidate.count(marker) for marker in markers)

    best = value
    best_score = score(value)
    for encoding in ("gbk", "cp936", "latin1", "cp1252"):
        try:
            repaired = value.encode(encoding).decode("utf-8")
        except Exception:
            continue
        repaired_score = score(repaired)
        if repaired_score < best_score:
            best = repaired
            best_score = repaired_score
    return best


def strip_html_for_import(text: str) -> str:
    value = str(text or "")
    value = re.sub(r"<style[\s\S]*?</style>", " ", value, flags=re.I)
    value = re.sub(r"<script[\s\S]*?</script>", " ", value, flags=re.I)
    value = re.sub(r"<[^>]+>", " ", value)
    value = (
        value.replace("&nbsp;", " ")
        .replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
        .replace("&apos;", "'")
        .replace("&#39;", "'")
    )
    return re.sub(r"\s+", " ", value).strip()


def remove_design_prompt_text(text: str) -> str:
    normalized = re.sub(r"\s+", " ", str(text or "")).strip()
    if not normalized:
        return ""
    match = DESIGN_PROMPT_CUTOFF_PATTERN.search(normalized)
    if match:
        normalized = normalized[: match.start()].strip()
    return normalized


def clean_imported_text(text: Any) -> str:
    value = repair_mojibake_text(str(text or ""))
    value = strip_html_for_import(value) if "<" in value and ">" in value else value
    value = value.replace("\r\n", "\n").replace("\r", "\n").replace("\u00a0", " ")
    lines: List[str] = []
    for raw_line in value.split("\n"):
        line = raw_line.strip()
        if not line:
            continue
        if re.match(r"^\s*(?:```|~~~)", line):
            continue
        if re.match(r"^\s*(?:-{3,}|\*{3,}|_{3,})\s*$", line):
            continue
        if re.match(r"^\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?\s*$", line):
            continue
        line = re.sub(r"^\s*(?:>\s*)+", "", line)
        line = re.sub(r"^\s{0,3}#{1,6}\s*", "", line)
        line = re.sub(r"^\s*[-*+]\s+", "", line)
        line = re.sub(r"^\s*\d+[.)]\s+", "", line)
        if "|" in line:
            cells = [cell.strip() for cell in line.split("|") if cell.strip()]
            if len(cells) > 1:
                line = ", ".join(cells)
        line = re.sub(r"`([^`]+)`", r"\1", line)
        line = re.sub(r"\*\*([^*]+)\*\*", r"\1", line)
        line = re.sub(r"__([^_]+)__", r"\1", line)
        line = re.sub(r"\*([^*]+)\*", r"\1", line)
        line = re.sub(r"_([^_]+)_", r"\1", line)
        line = re.sub(r"https?://\S+", " ", line)
        line = re.sub(r"[`*_~]+", "", line)
        line = re.sub(r"\s+", " ", line).strip()
        if line:
            lines.append(line)
    return remove_design_prompt_text(" ".join(lines))


def mime_from_filename(path: str) -> str:
    ext = Path(path).suffix.lower()
    if ext in {".jpg", ".jpeg"}:
        return "image/jpeg"
    if ext == ".webp":
        return "image/webp"
    if ext == ".gif":
        return "image/gif"
    if ext == ".bmp":
        return "image/bmp"
    if ext == ".pdf":
        return "application/pdf"
    return "image/png"


def file_to_data_url(path: str, mime_type: Optional[str] = None) -> str:
    with open(path, "rb") as f:
        payload = base64.b64encode(f.read()).decode("ascii")
    return f"data:{mime_type or mime_from_filename(path)};base64,{payload}"


def full_slide_hotspot(slide_index: int) -> Dict[str, Any]:
    return {
        "id": f"hotspot_s{slide_index}_full",
        "kind": "full-slide",
        "text": "",
        "x": 8,
        "y": 8,
        "w": 84,
        "h": 84,
        "priority": 1,
    }


def normalize_hotspot_list(hotspots: List[Dict[str, Any]], slide_index: int) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    for index, hotspot in enumerate(hotspots or []):
        try:
            x = clamp(float(hotspot.get("x", 0)), 0, 100)
            y = clamp(float(hotspot.get("y", 0)), 0, 100)
            w = clamp(min(float(hotspot.get("w", 0)), 100 - x), 1, 100)
            h = clamp(min(float(hotspot.get("h", 0)), 100 - y), 1, 100)
        except Exception:
            continue
        if w <= 0 or h <= 0:
            continue
        normalized.append(
            {
                **hotspot,
                "id": hotspot.get("id") or f"hotspot_s{slide_index}_{index + 1}",
                "kind": hotspot.get("kind") or "text",
                "text": clean_imported_text(hotspot.get("text", "")),
                "x": x,
                "y": y,
                "w": w,
                "h": h,
            }
        )
    return normalized or [full_slide_hotspot(slide_index)]


def group_text_boxes_into_hotspots(boxes: List[Dict[str, Any]], slide_index: int) -> List[Dict[str, Any]]:
    valid = [
        box
        for box in boxes
        if clean_imported_text(box.get("text", "")) and float(box.get("w", 0) or 0) > 0 and float(box.get("h", 0) or 0) > 0
    ]
    valid.sort(key=lambda item: (round(float(item.get("y", 0) or 0) / 1.2), float(item.get("x", 0) or 0)))
    lines: List[List[Dict[str, Any]]] = []
    for box in valid:
        y = float(box.get("y", 0) or 0)
        h = float(box.get("h", 1) or 1)
        target = next((line for line in lines if abs(float(line[0].get("y", 0) or 0) - y) < max(1.2, h * 0.7)), None)
        if target is None:
            lines.append([box])
        else:
            target.append(box)

    hotspots: List[Dict[str, Any]] = []
    for index, line in enumerate(lines[:50], 1):
        xs = [float(box.get("x", 0) or 0) for box in line]
        ys = [float(box.get("y", 0) or 0) for box in line]
        rights = [float(box.get("x", 0) or 0) + float(box.get("w", 0) or 0) for box in line]
        bottoms = [float(box.get("y", 0) or 0) + float(box.get("h", 0) or 0) for box in line]
        text = " ".join(clean_imported_text(box.get("text", "")) for box in sorted(line, key=lambda item: float(item.get("x", 0) or 0))).strip()
        if not text:
            continue
        min_x = min(xs)
        min_y = min(ys)
        hotspots.append(
            {
                "id": f"hotspot_line_{index}",
                "kind": "text",
                "text": text,
                "x": clamp(min_x - 0.4, 0, 100),
                "y": clamp(min_y - 0.4, 0, 100),
                "w": clamp(max(rights) - min_x + 0.8, 1, 100),
                "h": clamp(max(bottoms) - min_y + 0.8, 1, 100),
                "priority": 70 if len(text) > 12 else 40,
            }
        )
    return normalize_hotspot_list(hotspots, slide_index)


def pptx_shapes_to_hotspots(slide: Dict[str, Any], slide_index: int) -> List[Dict[str, Any]]:
    hotspots: List[Dict[str, Any]] = []
    for index, shape in enumerate(slide.get("shapes") or [], 1):
        text = clean_imported_text(shape.get("text", ""))
        if not text:
            continue
        slide_width = float(shape.get("slide_width") or 0) or 1
        slide_height = float(shape.get("slide_height") or 0) or 1
        if "x" in shape:
            x = float(shape.get("x") or 0)
            y = float(shape.get("y") or 0)
            w = float(shape.get("w") or 0)
            h = float(shape.get("h") or 0)
        else:
            x = float(shape.get("left") or 0) / slide_width * 100
            y = float(shape.get("top") or 0) / slide_height * 100
            w = float(shape.get("width") or 0) / slide_width * 100
            h = float(shape.get("height") or 0) / slide_height * 100
        hotspots.append(
            {
                "id": f"hotspot_s{slide_index}_{index}",
                "kind": "text",
                "text": text[:500],
                "x": x,
                "y": y,
                "w": max(w, 1),
                "h": max(h, 1),
                "priority": 90,
            }
        )
    return normalize_hotspot_list(hotspots, slide_index)


def pdf_shapes_to_hotspots(slide: Dict[str, Any], slide_index: int) -> List[Dict[str, Any]]:
    boxes: List[Dict[str, Any]] = []
    for shape in slide.get("shapes") or []:
        text = clean_imported_text(shape.get("text", ""))
        if not text:
            continue
        boxes.append(
            {
                "text": text,
                "x": float(shape.get("x", 0) or 0),
                "y": float(shape.get("y", 0) or 0),
                "w": float(shape.get("w", 0) or 0),
                "h": float(shape.get("h", 0) or 0),
            }
        )
    return group_text_boxes_into_hotspots(boxes, slide_index)


def imported_deck_diagnostics(slides: List[Dict[str, Any]]) -> Dict[str, int]:
    return {
        "slideCount": len(slides),
        "textSlideCount": sum(1 for slide in slides if clean_imported_text(slide.get("text", ""))),
        "noteSlideCount": sum(1 for slide in slides if clean_imported_text(slide.get("note", ""))),
        "hotspotTextSlideCount": sum(
            1
            for slide in slides
            if any(clean_imported_text(hotspot.get("text", "")) for hotspot in slide.get("hotspots", []))
        ),
    }


def export_pptx_with_powerpoint(pptx_path: str, output_dir: str, overwrite: bool) -> List[str]:
    powerpoint = find_powerpoint()
    if not powerpoint:
        return []

    marker = os.path.join(output_dir, "_powerpoint_export_done.txt")
    if os.path.exists(marker) and not overwrite:
        existing = sorted(
            [os.path.join(output_dir, f) for f in os.listdir(output_dir) if f.startswith("page-") and f.endswith(".png")]
        )
        if existing:
            return existing

    script = f"""
$ErrorActionPreference = 'Stop'
$pptxPath = {json.dumps(os.path.abspath(pptx_path))}
$outDir = {json.dumps(os.path.abspath(output_dir))}
$powerPoint = $null
$presentation = $null
try {{
  New-Item -ItemType Directory -Force -Path $outDir | Out-Null
  $powerPoint = New-Object -ComObject PowerPoint.Application
  $presentation = $powerPoint.Presentations.Open($pptxPath, $true, $false, $false)
  for ($i = 1; $i -le $presentation.Slides.Count; $i++) {{
    $out = Join-Path $outDir ("page-" + $i.ToString("000") + ".png")
    $presentation.Slides.Item($i).Export($out, "PNG", 1920, 1080)
  }}
}}
finally {{
  if ($presentation) {{ $presentation.Close() }}
  if ($powerPoint) {{ $powerPoint.Quit() }}
  [GC]::Collect()
  [GC]::WaitForPendingFinalizers()
}}
"""
    script_path = os.path.join(output_dir, "export_pptx_pages.ps1")
    with open(script_path, "w", encoding="utf-8") as f:
        f.write(script)
    run_command(
        [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            script_path,
        ],
        timeout=180,
    )
    with open(marker, "w", encoding="utf-8") as f:
        f.write(time.strftime("%Y-%m-%d %H:%M:%S"))
    return sorted(
        [os.path.join(output_dir, f) for f in os.listdir(output_dir) if f.startswith("page-") and f.endswith(".png")]
    )


def render_pdf_to_output(pdf_path: str, output_dir: str, overwrite: bool) -> List[str]:
    try:
        import fitz  # type: ignore

        doc = fitz.open(pdf_path)
        result: List[str] = []
        for idx in range(len(doc)):
            out = os.path.join(output_dir, f"page-{idx + 1:03d}.png")
            if os.path.exists(out) and not overwrite:
                result.append(out)
                continue
            page = doc[idx]
            pix = page.get_pixmap(matrix=fitz.Matrix(2.0, 2.0), alpha=False)
            pix.save(out)
            result.append(out)
        doc.close()
        return result
    except ImportError:
        pass

    pdftoppm = shutil.which("pdftoppm") or shutil.which("pdftoppm.exe")
    if pdftoppm:
        prefix = os.path.join(output_dir, "page")
        run_command([pdftoppm, "-png", "-r", "150", pdf_path, prefix], timeout=180)
        generated = sorted([os.path.join(output_dir, f) for f in os.listdir(output_dir) if re.match(r"page-\d+\.png$", f)])
        renamed: List[str] = []
        for i, path in enumerate(generated, 1):
            dst = os.path.join(output_dir, f"page-{i:03d}.png")
            if path != dst:
                if os.path.exists(dst):
                    os.remove(dst)
                os.replace(path, dst)
            renamed.append(dst)
        return renamed

    raise RuntimeError("PDF 渲染需要 PyMuPDF 或 pdftoppm。请给 ComfyUI Python 安装 pymupdf，或使用 PPTX/图片目录。")


def extract_pdf_text_safe(pdf_path: str, page_count: int) -> List[Dict[str, Any]]:
    try:
        return parse_pdf_extract_text(pdf_path)
    except Exception:
        return [{"index": i + 1, "text": "", "note": "", "source": "empty"} for i in range(page_count)]


def xml_local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def pptx_text_runs(element: Any) -> List[str]:
    texts: List[str] = []
    for child in element.iter():
        if xml_local_name(str(child.tag)) == "t" and child.text:
            value = clean_imported_text(child.text)
            if value:
                texts.append(value)
    return texts


def pptx_slide_size_from_zip(zf: zipfile.ZipFile) -> Tuple[float, float]:
    try:
        root = ET.fromstring(zf.read("ppt/presentation.xml"))
        for element in root.iter():
            if xml_local_name(str(element.tag)) == "sldSz":
                width = float(element.attrib.get("cx") or 0)
                height = float(element.attrib.get("cy") or 0)
                if width > 0 and height > 0:
                    return width, height
    except Exception:
        pass
    return 12192000.0, 6858000.0


def read_xml_attribute(text: str, name: str) -> str:
    escaped = re.escape(name)
    match = re.search(rf"\b{escaped}=([\"'])(.*?)\1", text, flags=re.I)
    return match.group(2) if match else ""


def resolve_zip_target(source_file: str, target: str) -> str:
    if target.startswith("/"):
        return target.lstrip("/")
    return posixpath.normpath(posixpath.join(posixpath.dirname(source_file), target)).lstrip("/")


def read_slide_relationships(zf: zipfile.ZipFile, slide_file: str) -> Dict[str, str]:
    rels_path = slide_file.replace("ppt/slides/", "ppt/slides/_rels/") + ".rels"
    if rels_path not in zf.namelist():
        return {}
    try:
        rels_xml = zf.read(rels_path).decode("utf-8", errors="ignore")
    except Exception:
        return {}
    rels: Dict[str, str] = {}
    for match in re.finditer(r"<Relationship\b[^>]*>", rels_xml):
        tag = match.group(0)
        rel_id = read_xml_attribute(tag, "Id")
        target = read_xml_attribute(tag, "Target")
        rel_type = read_xml_attribute(tag, "Type")
        if rel_id and target and rel_type.endswith("/image"):
            rels[rel_id] = resolve_zip_target(slide_file, target)
    return rels


def read_blip_rel_id(xml: str) -> str:
    tag = re.search(r"<a:blip\b[^>]*>", xml)
    return read_xml_attribute(tag.group(0), "r:embed") if tag else ""


def read_transform_area_ratio(xml: str, slide_width: float, slide_height: float) -> float:
    tag = re.search(r"<a:ext\b[^>]*>", xml)
    if not tag:
        return 0.0
    try:
        width = float(read_xml_attribute(tag.group(0), "cx") or 0)
        height = float(read_xml_attribute(tag.group(0), "cy") or 0)
    except Exception:
        return 0.0
    if width <= 0 or height <= 0 or slide_width <= 0 or slide_height <= 0:
        return 0.0
    return (width * height) / (slide_width * slide_height)


def mime_from_media_path(filename: str) -> Optional[str]:
    ext = Path(filename).suffix.lower()
    if ext in {".jpg", ".jpeg"}:
        return "image/jpeg"
    if ext == ".png":
        return "image/png"
    if ext == ".webp":
        return "image/webp"
    if ext == ".gif":
        return "image/gif"
    if ext == ".bmp":
        return "image/bmp"
    return None


def find_best_embedded_slide_image(slide_xml: str, rels: Dict[str, str], slide_width: float, slide_height: float) -> Optional[str]:
    candidates: List[Tuple[bool, float, str]] = []
    for match in re.finditer(r"<p:bg\b[\s\S]*?</p:bg>", slide_xml):
        rel_id = read_blip_rel_id(match.group(0))
        media_path = rels.get(rel_id)
        if media_path:
            candidates.append((True, 1.0, media_path))

    for match in re.finditer(r"<p:pic\b[\s\S]*?</p:pic>", slide_xml):
        block = match.group(0)
        rel_id = read_blip_rel_id(block)
        media_path = rels.get(rel_id)
        if not media_path:
            continue
        area_ratio = read_transform_area_ratio(block, slide_width, slide_height)
        candidates.append((False, area_ratio, media_path))

    usable = [item for item in candidates if item[0] or item[1] >= 0.65]
    usable.sort(key=lambda item: (1 if item[0] else 0, item[1]), reverse=True)
    return usable[0][2] if usable else None


def extract_pptx_embedded_image_pages(pptx_path: str, output_dir: str, overwrite: bool) -> List[str]:
    image_paths: List[str] = []
    try:
        with zipfile.ZipFile(pptx_path, "r") as zf:
            names = zf.namelist()
            slide_width, slide_height = pptx_slide_size_from_zip(zf)
            slide_files = sorted(
                [name for name in names if re.match(r"ppt/slides/slide\d+\.xml$", name)],
                key=natural_key,
            )
            if not slide_files:
                return []
            for index, slide_file in enumerate(slide_files, 1):
                slide_xml = zf.read(slide_file).decode("utf-8", errors="ignore")
                rels = read_slide_relationships(zf, slide_file)
                media_path = find_best_embedded_slide_image(slide_xml, rels, slide_width, slide_height)
                if not media_path or media_path not in names or not mime_from_media_path(media_path):
                    return []
                ext = Path(media_path).suffix.lower()
                if ext == ".jpeg":
                    ext = ".jpg"
                out_path = os.path.join(output_dir, f"page-{index:03d}{ext or '.png'}")
                if not os.path.exists(out_path) or overwrite:
                    with open(out_path, "wb") as f:
                        f.write(zf.read(media_path))
                image_paths.append(out_path)
    except Exception:
        return []
    return image_paths


def find_libreoffice_command() -> Optional[str]:
    candidates = [
        os.environ.get("LIBREOFFICE_PATH"),
        os.environ.get("SOFFICE_PATH"),
        "soffice",
        "libreoffice",
        r"C:\Program Files\LibreOffice\program\soffice.exe",
        r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
    ]
    for candidate in [item for item in candidates if item]:
        try:
            subprocess.run([candidate, "--version"], capture_output=True, text=True, timeout=5)
            return candidate
        except Exception:
            continue
    return None


def run_command_text(cmd: List[str], timeout: int = 120) -> None:
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"命令超时: {' '.join(cmd)}") from exc
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(f"命令执行失败: {' '.join(cmd)}\n{detail}")


def convert_pptx_to_pdf_like_frontend(pptx_path: str, output_dir: str) -> str:
    pdf_path = os.path.join(output_dir, os.path.splitext(os.path.basename(pptx_path))[0] + ".pdf")
    failures: List[str] = []
    soffice = find_libreoffice_command()
    if soffice:
        try:
            run_command_text(
                [
                    soffice,
                    "--headless",
                    "--nologo",
                    "--nofirststartwizard",
                    "--norestore",
                    "--convert-to",
                    "pdf",
                    "--outdir",
                    output_dir,
                    pptx_path,
                ],
                timeout=120,
            )
            if os.path.exists(pdf_path):
                return pdf_path
            failures.append("LibreOffice 已执行转换，但没有生成 PDF 文件。")
        except Exception as exc:
            failures.append(f"LibreOffice: {exc}")
    else:
        failures.append("未找到 LibreOffice/soffice。")

    if os.name == "nt":
        script_path = os.path.join(output_dir, "convert-pptx-to-pdf.ps1")
        script = r"""
$ErrorActionPreference = 'Stop'
$pptxPath = $args[0]
$pdfPath = $args[1]
$powerPoint = $null
$presentation = $null
try {
  $msoTrue = -1
  $msoFalse = 0
  $powerPoint = New-Object -ComObject PowerPoint.Application
  try { $powerPoint.DisplayAlerts = 1 } catch {}
  try {
    $presentation = $powerPoint.Presentations.Open($pptxPath, $msoTrue, $msoFalse, $msoFalse)
  }
  catch {
    $presentation = $powerPoint.Presentations.Open($pptxPath, $msoTrue, $msoFalse, $msoTrue)
  }
  $presentation.SaveAs($pdfPath, 32)
}
finally {
  if ($presentation -ne $null) {
    $presentation.Close()
    [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($presentation)
  }
  if ($powerPoint -ne $null) {
    $powerPoint.Quit()
    [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($powerPoint)
  }
  [GC]::Collect()
  [GC]::WaitForPendingFinalizers()
}
""".strip()
        with open(script_path, "w", encoding="utf-8") as f:
            f.write(script)
        try:
            run_command_text(
                [
                    "powershell.exe",
                    "-NoProfile",
                    "-NonInteractive",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    script_path,
                    pptx_path,
                    pdf_path,
                ],
                timeout=120,
            )
            if os.path.exists(pdf_path):
                return pdf_path
            failures.append("PowerPoint 已执行转换，但没有生成 PDF 文件。")
        except Exception as exc:
            failures.append(f"PowerPoint: {exc}")

    raise RuntimeError("；".join(failures) or "无法将 PPTX 转换为 PDF。")


def extract_pptx_text_xml(path: str) -> List[Dict[str, Any]]:
    slides: List[Dict[str, Any]] = []
    try:
        with zipfile.ZipFile(path, "r") as zf:
            slide_width, slide_height = pptx_slide_size_from_zip(zf)
            slide_files = sorted(
                [name for name in zf.namelist() if re.match(r"ppt/slides/slide\d+\.xml$", name)],
                key=natural_key,
            )
            for slide_index, slide_file in enumerate(slide_files, 1):
                root = ET.fromstring(zf.read(slide_file))
                shapes: List[Dict[str, Any]] = []
                texts: List[str] = []
                shape_index = 0
                for element in root.iter():
                    if xml_local_name(str(element.tag)) not in {"sp", "graphicFrame"}:
                        continue
                    shape_texts = pptx_text_runs(element)
                    if not shape_texts:
                        continue
                    text = clean_imported_text(" ".join(shape_texts))
                    if not text:
                        continue
                    texts.append(text)
                    off = element.find(".//{*}xfrm/{*}off")
                    ext = element.find(".//{*}xfrm/{*}ext")
                    if off is None or ext is None:
                        continue
                    try:
                        x = float(off.attrib.get("x") or 0) / slide_width * 100
                        y = float(off.attrib.get("y") or 0) / slide_height * 100
                        w = float(ext.attrib.get("cx") or 0) / slide_width * 100
                        h = float(ext.attrib.get("cy") or 0) / slide_height * 100
                    except Exception:
                        continue
                    if w <= 0 or h <= 0:
                        continue
                    shape_index += 1
                    shapes.append(
                        {
                            "text": text,
                            "x": x,
                            "y": y,
                            "w": w,
                            "h": h,
                            "slide_width": 100,
                            "slide_height": 100,
                            "source": "pptx-xml",
                            "order": shape_index,
                        }
                    )

                note = ""
                notes_file = f"ppt/notesSlides/notesSlide{slide_index}.xml"
                if notes_file in zf.namelist():
                    note_root = ET.fromstring(zf.read(notes_file))
                    note_parts = [
                        part
                        for part in pptx_text_runs(note_root)
                        if part and part.strip() != str(slide_index)
                    ]
                    note = clean_imported_text(" ".join(note_parts))

                slides.append(
                    {
                        "index": slide_index,
                        "text": clean_imported_text(" ".join(texts)),
                        "note": note,
                        "shapes": shapes,
                    }
                )
    except Exception:
        return []
    return slides


def extract_pptx_text_safe(path: str, page_count: int) -> List[Dict[str, Any]]:
    slides = extract_pptx_text(path) or extract_pptx_text_xml(path) or extract_pptx_text_fallback(path)
    if not slides:
        slides = []
    while len(slides) < page_count:
        slides.append({"index": len(slides) + 1, "text": "", "note": ""})
    return slides[:page_count]


def parse_script_by_page(script: str, page_count: int) -> List[str]:
    pages = [{"pageIndex": index + 1, "text": ""} for index in range(page_count)]
    return [item["text"] for item in match_script_to_pages(pages, script)]


def page_marker_index(line: str) -> Optional[int]:
    trimmed = re.sub(r"^\s*#{1,6}\s*", "", (line or "").strip())
    patterns = [
        r"^第\s*(\d+)\s*(?:页|頁|张|張|P|p)\s*[:：\-—–]?\s*$",
        r"^(?:slide|page|p)\s*(\d+)\s*[:：\-—–]?\s*$",
        r"^[【\[]?\s*(\d+)\s*/\s*\d+\s*[】\]]?\s*$",
    ]
    for pattern in patterns:
        match = re.match(pattern, trimmed, re.I)
        if match:
            value = int(match.group(1))
            return value if value > 0 else None
    return None


def split_script_by_page_markers(script: str, page_count: int) -> Optional[List[Dict[str, Any]]]:
    buckets: Dict[int, List[str]] = {}
    current: Optional[int] = None
    found = False
    for line in script.replace("\r\n", "\n").split("\n"):
        marker = page_marker_index(line)
        if marker is not None:
            current = marker
            found = True
            buckets.setdefault(marker, [])
            continue
        if current is not None:
            buckets.setdefault(current, []).append(line)
    if not found:
        return None
    return [
        {"slideIndex": index + 1, "text": clean_text("\n".join(buckets.get(index + 1, [])).strip()), "source": "marker"}
        for index in range(page_count)
    ]


def split_script_by_separators(script: str, page_count: int) -> Optional[List[Dict[str, Any]]]:
    parts = [part.strip() for part in re.split(r"\n\s*(?:---+|===+|\*\*\*+)\s*\n", script) if part.strip()]
    if len(parts) != page_count:
        return None
    return [{"slideIndex": index + 1, "text": clean_text(parts[index]), "source": "separator"} for index in range(page_count)]


def split_text_into_page_count(text: str, count: int) -> List[str]:
    clean = (text or "").strip()
    if count <= 1:
        return [clean]
    if not clean:
        return [""] * count
    approx = max(1, int((len(clean) + count - 1) / count))
    result: List[str] = []
    rest = clean
    for index in range(count):
        if index == count - 1:
            result.append(rest.strip())
            break
        window = rest[max(0, approx - 80) : approx + 80]
        punctuation = re.search(r"[。！？!?；;,.，、\n]", window)
        cut = approx
        if punctuation:
            cut = max(1, max(0, approx - 80) + punctuation.start() + 1)
        result.append(rest[:cut].strip())
        rest = rest[cut:].strip()
    while len(result) < count:
        result.append("")
    return result[:count]


def page_source_text(page: Dict[str, Any]) -> str:
    parts: List[str] = []
    for key in ("text", "note"):
        value = clean_imported_text(page.get(key, ""))
        if value:
            parts.append(value)
    hotspots = page.get("hotspots")
    if isinstance(hotspots, list):
        seen = set(parts)
        for hotspot in hotspots:
            if not isinstance(hotspot, dict):
                continue
            text = clean_imported_text(hotspot.get("text", ""))
            if text and text not in seen:
                seen.add(text)
                parts.append(text)
            if len(" ".join(parts)) >= 600:
                break
    return clean_text(" ".join(parts))


def tokenize_for_script_match(text: str) -> set:
    value = clean_imported_text(text).lower()
    latin = re.findall(r"[a-z0-9]{2,}", value)
    cjk = re.findall(r"[\u3400-\u9fff]", value)
    bigrams = [cjk[index] + cjk[index + 1] for index in range(max(0, len(cjk) - 1))]
    return set(latin + bigrams + cjk[::2])


def script_text_similarity(left: str, right: str) -> float:
    left_tokens = tokenize_for_script_match(left)
    right_tokens = tokenize_for_script_match(right)
    if not left_tokens or not right_tokens:
        return 0.0
    overlap = sum(1 for token in left_tokens if token in right_tokens)
    return overlap / max(1.0, (len(left_tokens) * len(right_tokens)) ** 0.5)


def assign_script_automatically(pages: List[Dict[str, Any]], script: str) -> List[Dict[str, Any]]:
    page_count = len(pages)
    paragraphs = [
        re.sub(r"\s*\n\s*", " ", part).strip()
        for part in re.split(r"\n{2,}", script.replace("\r\n", "\n"))
        if part.strip()
    ]
    if not paragraphs:
        return [{"slideIndex": index + 1, "text": "", "source": "empty"} for index in range(page_count)]
    if len(paragraphs) < page_count:
        per_page = split_text_into_page_count(script, page_count)
        return [{"slideIndex": index + 1, "text": clean_text(per_page[index]), "source": "auto"} for index in range(page_count)]

    buckets = [[] for _ in range(page_count)]
    cursor = 0
    for paragraph in paragraphs:
        window_end = min(page_count - 1, cursor + 2)
        best_index = cursor
        best_score = -1.0
        for page_index in range(cursor, window_end + 1):
            score = script_text_similarity(paragraph, page_source_text(pages[page_index]))
            if score > best_score:
                best_score = score
                best_index = page_index
        buckets[best_index].append(paragraph)
        if best_index > cursor or len(buckets[cursor]) >= max(1, int((len(paragraphs) + page_count - 1) / page_count)):
            cursor = min(page_count - 1, best_index + 1)

    return [
        {"slideIndex": index + 1, "text": clean_text("\n\n".join(buckets[index])), "source": "auto"}
        for index in range(page_count)
    ]


def match_script_to_pages(pages: List[Dict[str, Any]], script: str) -> List[Dict[str, Any]]:
    page_count = len(pages)
    clean_script = (script or "").strip()
    if not clean_script:
        matches = [
            {
                "slideIndex": int(page.get("pageIndex") or index + 1),
                "text": page_source_text(page),
                "source": "note" if page_source_text(page) else "empty",
            }
            for index, page in enumerate(pages)
        ]
    else:
        matches = (
            split_script_by_page_markers(clean_script, page_count)
            or split_script_by_separators(clean_script, page_count)
            or assign_script_automatically(pages, clean_script)
        )
    for index, match in enumerate(matches):
        match["slideIndex"] = int(pages[index].get("pageIndex") or match.get("slideIndex") or index + 1)
        match["segments"] = normalize_segments(match.get("text") or "")
    return matches


def openai_compatible_chat(base_url: str, api_key: str, model: str, messages: List[Dict[str, Any]], timeout: int) -> str:
    base = (base_url or "").rstrip("/")
    if not base:
        base = "https://api.openai.com/v1"
    if base.endswith("/chat/completions"):
        url = base
    else:
        url = f"{base}/chat/completions"
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.7,
    }
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"AI 请求失败 HTTP {exc.code}: {detail[:500]}") from exc
    content = body.get("choices", [{}])[0].get("message", {}).get("content", "")
    if not content:
        raise RuntimeError(f"AI 返回为空: {body}")
    return strip_markdown_fences(content)


def image_to_data_url(image_path: str, max_side: int = 1100, quality: int = 78) -> str:
    if not image_path or not os.path.exists(image_path):
        raise FileNotFoundError(f"找不到用于视觉理解的页面图片: {image_path}")
    try:
        from PIL import Image
    except Exception as exc:
        raise RuntimeError("视觉理解需要 Pillow/PIL，但当前 ComfyUI Python 无法导入 PIL。") from exc

    with Image.open(image_path) as image:
        image = image.convert("RGB")
        scale = min(1.0, float(max_side) / max(image.width or 1, image.height or 1))
        if scale < 1.0:
            image = image.resize(
                (max(1, int(image.width * scale)), max(1, int(image.height * scale))),
                Image.Resampling.LANCZOS,
            )
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            tmp_path = tmp.name
        try:
            image.save(tmp_path, "JPEG", quality=quality, optimize=True)
            with open(tmp_path, "rb") as f:
                payload = base64.b64encode(f.read()).decode("ascii")
        finally:
            try:
                os.remove(tmp_path)
            except Exception:
                pass
    return f"data:image/jpeg;base64,{payload}"


def gradio_client_predict(base_url: str, api_name: str, *args: Any) -> Any:
    from gradio_client import Client  # type: ignore

    client = Client(base_url)
    return client.predict(*args, api_name=api_name if api_name.startswith("/") else f"/{api_name}")


def normalize_gradio_base_url(base_url: str) -> str:
    root = (base_url or "http://127.0.0.1:7861").strip().rstrip("/")
    if not root:
        raise ValueError("Gradio base URL is required")
    return root


def gradio_api_call_url(base_url: str, api_name: str, event_id: Optional[str] = None) -> str:
    root = normalize_gradio_base_url(base_url)
    clean_name = api_name.strip().lstrip("/")
    encoded_name = urllib.parse.quote(clean_name, safe="")
    url = f"{root}/gradio_api/call/{encoded_name}"
    if event_id:
        url += f"/{urllib.parse.quote(str(event_id), safe='')}"
    return url


def read_http_error_detail(exc: urllib.error.HTTPError) -> str:
    try:
        return exc.read().decode("utf-8", errors="replace")[:1000]
    except Exception:
        return str(exc)


def gradio_http_post_json(url: str, payload: Dict[str, Any], timeout: int) -> Any:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            text = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"HTTP {exc.code} {url}: {read_http_error_detail(exc)}") from exc
    return json.loads(text) if text.strip() else None


def gradio_http_get_text(url: str, timeout: int) -> str:
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"HTTP {exc.code} {url}: {read_http_error_detail(exc)}") from exc


def parse_gradio_event_stream(text: str) -> List[Dict[str, str]]:
    events: List[Dict[str, str]] = []
    event = "message"
    data_lines: List[str] = []

    def flush() -> None:
        nonlocal event, data_lines
        if data_lines or event != "message":
            events.append({"event": event, "data": "\n".join(data_lines)})
        event = "message"
        data_lines = []

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if not line:
            flush()
            continue
        if line.startswith("event:"):
            event = line[len("event:"):].strip() or "message"
            continue
        if line.startswith("data:"):
            data_lines.append(line[len("data:"):].lstrip())
    flush()
    return events


def read_gradio_complete_data(text: str) -> Any:
    events = parse_gradio_event_stream(text)
    for item in reversed(events):
        if item.get("event") == "error":
            raise RuntimeError(item.get("data") or "Gradio API returned an error")
    for item in reversed(events):
        if item.get("event") == "complete":
            data = item.get("data") or ""
            return json.loads(data) if data else None
    if text.strip().startswith(("{", "[")):
        return json.loads(text)
    raise RuntimeError("Gradio API did not return a complete event")


def call_gradio_http_api(base_url: str, api_name: str, data: List[Any], timeout: int) -> Any:
    submit_url = gradio_api_call_url(base_url, api_name)
    submitted = gradio_http_post_json(submit_url, {"data": data}, timeout)
    if isinstance(submitted, dict):
        event_id = submitted.get("event_id")
        if event_id:
            event_text = gradio_http_get_text(gradio_api_call_url(base_url, api_name, str(event_id)), timeout)
            return read_gradio_complete_data(event_text)
        if "data" in submitted:
            return submitted.get("data")
    return submitted


def parse_gradio_table(result: Any) -> List[List[Any]]:
    if isinstance(result, tuple):
        for item in reversed(result):
            rows = parse_gradio_table(item)
            if rows:
                return rows
    if isinstance(result, dict):
        data = result.get("data")
        if isinstance(data, list):
            return data
    if isinstance(result, list):
        if result and all(isinstance(row, list) for row in result):
            return result
        for item in result:
            rows = parse_gradio_table(item)
            if rows:
                return rows
    return []


def looks_like_audio_path(value: str) -> bool:
    return bool(re.search(r"\.(wav|mp3|m4a|flac)(\?|$)", value or "", re.I))


def gradio_file_url(base_url: str, file_path: str) -> str:
    path = (file_path or "").replace("\\", "/")
    encoded = "/".join(urllib.parse.quote(part, safe="") for part in path.split("/"))
    return f"{normalize_gradio_base_url(base_url)}/gradio_api/file={encoded}"


def is_local_gradio_url(base_url: str) -> bool:
    try:
        parsed = urllib.parse.urlsplit(normalize_gradio_base_url(base_url))
    except Exception:
        return False
    host = (parsed.hostname or "").lower()
    return host in {"", "localhost", "127.0.0.1", "::1"}


def normalize_gradio_result_path(value: str) -> str:
    text = urllib.parse.unquote(str(value or "").strip().strip("\"'"))
    if not text:
        return ""
    if text.startswith("file://"):
        parsed = urllib.parse.urlsplit(text)
        return urllib.parse.unquote(parsed.path.lstrip("/"))
    if text.startswith("http://") or text.startswith("https://"):
        parsed = urllib.parse.urlsplit(text)
        text = parsed.path or ""
        if "file=" in text:
            text = text.split("file=", 1)[1]
    if "file=" in text:
        text = text.split("file=", 1)[1]
    return urllib.parse.unquote(text).replace("/", os.sep).replace("\\", os.sep).lstrip(os.sep)


def safe_path_join(root: str, relative_path: str) -> Optional[str]:
    root_abs = os.path.abspath(root)
    candidate = os.path.abspath(os.path.join(root_abs, relative_path))
    try:
        if os.path.commonpath([root_abs, candidate]) != root_abs:
            return None
    except ValueError:
        return None
    return candidate


def infer_indextts_roots(value: Any) -> List[str]:
    roots: List[str] = []

    def add(root: str) -> None:
        root = os.path.abspath(os.path.expanduser(os.path.expandvars(root)))
        if root and root not in roots:
            roots.append(root)

    def visit(item: Any) -> None:
        if isinstance(item, str):
            text = urllib.parse.unquote(item).replace("/", "\\")
            marker_match = re.search(r"^([A-Za-z]:\\.+?)\\(?:outputs|tmp)\\", text, re.I)
            if marker_match:
                add(marker_match.group(1))
        elif isinstance(item, dict):
            for nested in item.values():
                visit(nested)
        elif isinstance(item, list):
            for nested in item:
                visit(nested)

    visit(value)
    return roots


def indextts_local_roots(seed: Any = None) -> List[str]:
    roots: List[str] = []

    def add(root: Optional[str]) -> None:
        if not root:
            return
        root = os.path.abspath(os.path.expanduser(os.path.expandvars(root)))
        if root and root not in roots:
            roots.append(root)

    for key in ("OPENMAIC_INDEXTTS_ROOT", "INDEXTTS_ROOT", "INDEX_TTS_ROOT"):
        add(os.environ.get(key))
    for root in infer_indextts_roots(seed):
        add(root)
    for root in ("E:/AI/index-tts-2", "D:/AI/index-tts-2", "C:/AI/index-tts-2"):
        add(root)
    return roots


def resolve_indextts_local_audio_path(base_url: str, result_path: str, seed: Any = None) -> Optional[str]:
    if not is_local_gradio_url(base_url):
        return None
    normalized = normalize_gradio_result_path(result_path)
    if not normalized or not looks_like_audio_path(normalized):
        return None
    if os.path.isabs(normalized) and os.path.exists(normalized):
        return normalized
    for root in indextts_local_roots(seed):
        candidate = safe_path_join(root, normalized)
        if candidate and os.path.exists(candidate) and looks_like_audio_path(candidate):
            return candidate
    return None


def quote_url_for_urllib(url: str) -> str:
    parsed = urllib.parse.urlsplit((url or "").replace("\\", "/"))
    path = urllib.parse.quote(parsed.path, safe="/%=:")
    query = urllib.parse.quote(parsed.query, safe="=&%/:?+")
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, path, query, parsed.fragment))


def find_audio_candidate(value: Any, base_url: str) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        text = value
        if text.startswith("data:audio"):
            return text
        for match in re.findall(r"([A-Za-z]:[\\/][^\\n\\r\\t\"'<>|]+?\\.(?:wav|mp3|m4a|flac))", text, re.I):
            if os.path.exists(match):
                return match
        for match in re.findall(r"(?:href|src)=[\"']([^\"']+\\.(?:wav|mp3|m4a|flac)(?:\\?[^\"']*)?)[\"']", text, re.I):
            return urllib.parse.urljoin(base_url.rstrip("/") + "/", match)
        if looks_like_audio_path(text):
            local_audio = resolve_indextts_local_audio_path(base_url, text, value)
            if local_audio:
                return local_audio
            if text.startswith("http://") or text.startswith("https://"):
                return text
            if os.path.exists(text):
                return text
            return gradio_file_url(base_url, text)
    if isinstance(value, dict):
        url_value = value.get("url")
        if isinstance(url_value, str) and looks_like_audio_path(url_value):
            local_audio = resolve_indextts_local_audio_path(base_url, url_value, value)
            if local_audio:
                return local_audio
            return urllib.parse.urljoin(base_url.rstrip("/") + "/", url_value)
        path_value = value.get("path")
        if isinstance(path_value, str) and looks_like_audio_path(path_value):
            local_audio = resolve_indextts_local_audio_path(base_url, path_value, value)
            if local_audio:
                return local_audio
            if os.path.exists(path_value):
                return path_value
            return gradio_file_url(base_url, path_value)
        for key in ("name", "data"):
            candidate = find_audio_candidate(value.get(key), base_url)
            if candidate:
                return candidate
        for item in value.values():
            candidate = find_audio_candidate(item, base_url)
            if candidate:
                return candidate
    if isinstance(value, list):
        for item in value:
            candidate = find_audio_candidate(item, base_url)
            if candidate:
                return candidate
    return None


def save_audio_candidate(candidate: str, output_path: str, timeout: int = 300) -> None:
    if candidate.startswith("data:audio"):
        audio_data = candidate.split(",", 1)[1] if "," in candidate else candidate
        with open(output_path, "wb") as f:
            f.write(base64.b64decode(audio_data))
        return
    if candidate.startswith("http://") or candidate.startswith("https://"):
        with urllib.request.urlopen(quote_url_for_urllib(candidate), timeout=timeout) as response:
            with open(output_path, "wb") as f:
                shutil.copyfileobj(response, f)
        return
    if os.path.exists(candidate):
        shutil.copy2(candidate, output_path)
        return
    raise RuntimeError(f"无法保存 TTS 音频，候选结果无效: {candidate}")


def tts_text_hash(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def normalize_tts_speed(speed: Any) -> str:
    try:
        return f"{float(speed):.3f}"
    except Exception:
        return str(speed or "")


def normalize_tts_service_url(url: str) -> str:
    return (url or "").strip().rstrip("/")


def tts_sidecar_path(audio_path: str) -> str:
    return f"{audio_path}.json"


def build_tts_cache_metadata(
    provider: str,
    text: str,
    voice: str,
    speed: Any,
    service_url: str,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    metadata = {
        "textHash": tts_text_hash(text),
        "textPreview": clean_text(text)[:160],
        "provider": provider or "",
        "voice": voice or "",
        "speed": normalize_tts_speed(speed),
        "serviceUrl": normalize_tts_service_url(service_url),
    }
    if extra:
        metadata.update(extra)
    return metadata


def load_tts_sidecar(audio_path: str) -> Optional[Dict[str, Any]]:
    path = tts_sidecar_path(audio_path)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            value = json.load(f)
        return value if isinstance(value, dict) else None
    except Exception:
        return None


def write_tts_sidecar(audio_path: str, metadata: Dict[str, Any]) -> None:
    payload = dict(metadata)
    payload["audioPath"] = os.path.abspath(audio_path)
    payload["updatedAt"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    with open(tts_sidecar_path(audio_path), "w", encoding="utf-8") as f:
        f.write(json_dumps(payload))


def tts_cache_matches(audio_path: str, expected: Dict[str, Any]) -> bool:
    if not os.path.exists(audio_path):
        return False
    actual = load_tts_sidecar(audio_path)
    if not actual:
        return False
    for key, value in expected.items():
        if key == "textPreview":
            continue
        if isinstance(value, (dict, list)):
            expected_value = json.dumps(value, ensure_ascii=False, sort_keys=True)
        else:
            expected_value = str(value or "")
        actual_value = actual.get(key)
        if isinstance(actual_value, (dict, list)):
            actual_value = json.dumps(actual_value, ensure_ascii=False, sort_keys=True)
        else:
            actual_value = str(actual_value or "")
        if actual_value != expected_value:
            return False
    try:
        return ffprobe_duration(audio_path) > 0.15
    except Exception:
        return False


def compact_gradio_text(value: Any) -> str:
    text = clean_text(str(value or ""))
    text = text.replace("...", "").replace("…", "")
    return re.sub(r"\s+", "", text)


def gradio_text_matches(row_text: Any, expected_text: str) -> bool:
    actual = compact_gradio_text(row_text)
    expected = compact_gradio_text(expected_text)
    if not actual or not expected:
        return False
    if actual == expected:
        return True
    if expected.startswith(actual):
        return True
    prefix_len = min(len(actual), len(expected), 24)
    return prefix_len >= 8 and actual[:prefix_len] == expected[:prefix_len]


def gradio_row_value(row: Any, index: int) -> str:
    if isinstance(row, (list, tuple)) and len(row) > index:
        return str(row[index] or "")
    return ""


def gradio_row_job_id(row: Any) -> str:
    return gradio_row_value(row, 0).strip()


def gradio_row_status(row: Any) -> str:
    return gradio_row_value(row, 1).strip()


def gradio_row_progress(row: Any) -> str:
    return gradio_row_value(row, 2).strip()


def gradio_row_input(row: Any) -> str:
    return gradio_row_value(row, 3)


def gradio_row_result(row: Any) -> str:
    return gradio_row_value(row, 4)


def gradio_row_is_done(row: Any) -> bool:
    status = gradio_row_status(row).lower()
    progress = gradio_row_progress(row).lower()
    return status in {"done", "success", "succeeded", "completed", "finished"} or progress in {"100%", "100"}


def gradio_row_is_failed(row: Any) -> bool:
    text = json.dumps(row, ensure_ascii=False).lower()
    return bool(re.search(r"failed|error|失败|错误", text))


def gradio_row_has_audio_result(row: Any) -> bool:
    return bool(looks_like_audio_path(gradio_row_result(row)))


def select_submitted_indextts_row(rows: List[List[Any]], text: str) -> Optional[List[Any]]:
    matching = [row for row in rows if gradio_text_matches(gradio_row_input(row), text)]
    for row in matching:
        if not gradio_row_is_done(row):
            return row
    if matching:
        return matching[0]
    for row in rows:
        if gradio_row_job_id(row) and not gradio_row_is_done(row) and not gradio_row_has_audio_result(row):
            return row
    return None


def find_indextts_job_row(rows: List[List[Any]], job_id: str) -> Optional[List[Any]]:
    for row in rows:
        if gradio_row_job_id(row) == job_id:
            return row
    return None


def describe_gradio_row(row: Any) -> str:
    return json.dumps(row, ensure_ascii=False)[:500]


def call_indextts_gradio(
    text: str,
    voice: str,
    speed: float,
    base_url: str,
    output_path: str,
    timeout: int,
) -> Dict[str, Any]:
    base_url = (base_url or "http://127.0.0.1:7861").rstrip("/")
    voice = voice or "gmg"

    data = [
        voice,
        speed,
        None,
        text,
        "\u4e0e\u97f3\u8272\u53c2\u8003\u97f3\u9891\u76f8\u540c",
        None,
        0.8,
        "",
        False,
        120,
        0.0,
        0.0,
        0.0,
        0.0,
        0.0,
        0.0,
        0.0,
        0.0,
        True,
        0.8,
        30,
        0.8,
        0.0,
        3,
        10.0,
        1500,
    ]

    deadline = time.time() + timeout
    try:
        submitted = call_gradio_http_api(base_url, "submit_and_refresh", data, timeout)
        submitted_rows = parse_gradio_table(submitted)
        submitted_row = select_submitted_indextts_row(submitted_rows, text)
        job_id = gradio_row_job_id(submitted_row) if submitted_row else ""
        if not job_id and isinstance(submitted, str):
            job_id = submitted
        if not job_id:
            raise RuntimeError("IndexTTS did not return a Job ID for the submitted text")

        while time.time() < deadline:
            time.sleep(2)
            refreshed = call_gradio_http_api(base_url, "refresh_all_outputs", [], min(timeout, 120))
            rows = parse_gradio_table(refreshed)
            row = find_indextts_job_row(rows, job_id)
            if not row:
                continue
            row_input = gradio_row_input(row)
            if row_input and not gradio_text_matches(row_input, text):
                raise RuntimeError(
                    f"IndexTTS Job ID {job_id} input text mismatch. "
                    f"Expected: {clean_text(text)[:80]}; row: {row_input[:120]}"
                )
            if gradio_row_is_failed(row):
                raise RuntimeError(f"IndexTTS job {job_id} failed: {describe_gradio_row(row)}")
            if not gradio_row_is_done(row):
                continue
            result_value = gradio_row_result(row)
            candidate = find_audio_candidate(result_value, base_url)
            if not candidate:
                raise RuntimeError(
                    f"IndexTTS job {job_id} finished but returned no readable audio: {describe_gradio_row(row)}"
                )
            save_audio_candidate(candidate, output_path, timeout=timeout)
            return {"jobId": job_id, "sourceAudioPath": candidate}
    except Exception as first_error:
        legacy_url = f"{base_url}/api/predict"
        payload = {"data": [text, 1.0 / max(speed, 0.1), voice, "Off"]}
        try:
            req = urllib.request.Request(
                legacy_url,
                data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                headers={"Content-Type": "application/json; charset=utf-8"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=timeout) as response:
                body = json.loads(response.read().decode("utf-8"))
            candidate = find_audio_candidate(body, base_url)
            if candidate:
                save_audio_candidate(candidate, output_path, timeout=timeout)
                return {"jobId": "legacy-api", "sourceAudioPath": candidate}
        except Exception:
            pass
        raise RuntimeError(f"IndexTTS 调用失败: {first_error}") from first_error

    raise TimeoutError(f"IndexTTS 超时，{timeout} 秒内没有拿到音频结果。")


def make_subtitle_ass(segments: List[Dict[str, Any]], output_path: str, style_name: str, width: int, height: int) -> str:
    style = dict(SUBTITLE_STYLES.get(style_name, SUBTITLE_STYLES["前端默认"]))
    scale = max(0.65, min(width / 1920.0, 2.0))
    size = int(style.get("size", 48) * scale)
    outline = max(1, int(style.get("outline_width", 4) * scale))
    margin_v = int(style.get("margin_v", 70) * scale)
    border_style = int(style.get("border_style", 1))
    back_color = style.get("back_color", "&H00000000")

    def ass_time(seconds: float) -> str:
        seconds = max(0.0, float(seconds or 0.0))
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = seconds % 60
        return f"{h}:{m:02d}:{s:05.2f}"

    lines = [
        "[Script Info]",
        "Title: OpenMAIC Standalone Subtitles",
        "ScriptType: v4.00+",
        f"PlayResX: {width}",
        f"PlayResY: {height}",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: Default,{style.get('font','Microsoft YaHei')},{size},{style.get('color','&H00FFFFFF')},&H00FFFFFF,{style.get('outline','&H00000000')},{back_color},-1,0,0,0,100,100,0,0,{border_style},{outline},{style.get('shadow',2)},{style.get('alignment',2)},60,60,{margin_v},1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    for seg in segments:
        text = str(seg.get("text") or "").replace("\n", "\\N").replace("{", "").replace("}", "")
        if not text:
            continue
        lines.append(
            f"Dialogue: 0,{ass_time(seg.get('start',0))},{ass_time(seg.get('end',0))},Default,,0,0,0,,{text}"
        )
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return output_path


MIN_CUE_DURATION_MS = 120
SEGMENT_WINDOW_TOLERANCE_MS = 420
SEGMENT_LOOKAHEAD = 3
MERGED_SEGMENT_TEXT_SCORE = 0.72
MERGED_SEGMENT_TIME_TOLERANCE_MS = 1200
MIN_MATCH_SCORE = 0.46
MIN_TEXT_COVERAGE = 0.24
MIN_TEXT_PRECISION = 0.2
SPLIT_HINT_CHARS = set(".,!?;: ，。！？；：、")


def make_subtitle_srt(cues: List[Dict[str, Any]], output_path: str) -> str:
    def srt_time(seconds: float) -> str:
        seconds = max(0.0, float(seconds or 0.0))
        total_ms = int(round(seconds * 1000))
        h = total_ms // 3_600_000
        total_ms %= 3_600_000
        m = total_ms // 60_000
        total_ms %= 60_000
        s = total_ms // 1000
        ms = total_ms % 1000
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    lines: List[str] = []
    index = 1
    for cue in cues:
        text = normalize_subtitle_source_text(cue.get("text") or "")
        start = float(cue.get("start") or 0)
        end = float(cue.get("end") or 0)
        if not text or end <= start:
            continue
        lines.extend([str(index), f"{srt_time(start)} --> {srt_time(end)}", text, ""])
        index += 1
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return output_path


def normalize_subtitle_source_text(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def subtitle_text_length(text: str) -> int:
    return len(re.sub(r"\s+", "", normalize_subtitle_source_text(text)))


def build_speech_events_from_timeline(timeline: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []
    for index, item in enumerate(timeline):
        text = normalize_subtitle_source_text(item.get("text") or "")
        if not text:
            continue
        start = float(item.get("start") or 0)
        end = float(item.get("end") or 0)
        if end <= start:
            duration = float(item.get("duration") or item.get("durationSeconds") or 0)
            end = start + max(0.0, duration)
        if end <= start:
            continue
        events.append(
            {
                "sceneId": item.get("sceneId") or f"page-{int(item.get('pageIndex') or index + 1):03d}",
                "actionId": f"speech-{index + 1:04d}",
                "actionIndex": index,
                "pageIndex": int(item.get("pageIndex") or index + 1),
                "startMs": int(round(start * 1000)),
                "endMs": int(round(end * 1000)),
                "text": text,
            }
        )
    return events


def build_estimated_subtitle_cues(
    speech_events: List[Dict[str, Any]],
    style_name: str = "前端默认",
) -> List[Dict[str, Any]]:
    cues: List[Dict[str, Any]] = []
    for event in speech_events:
        text = normalize_subtitle_source_text(event.get("text") or "")
        start_ms = int(event.get("startMs") or 0)
        end_ms = int(event.get("endMs") or 0)
        duration_ms = end_ms - start_ms
        if not text or duration_ms < MIN_CUE_DURATION_MS:
            continue
        parts = split_subtitle_text(text, style_name)
        total_weight = sum(max(1, subtitle_text_length(part)) for part in parts) or 1
        elapsed_weight = 0
        for index, part in enumerate(parts):
            part_weight = max(1, subtitle_text_length(part))
            cue_start_ms = start_ms if index == 0 else start_ms + round(duration_ms * elapsed_weight / total_weight)
            elapsed_weight += part_weight
            cue_end_ms = end_ms if index == len(parts) - 1 else start_ms + round(duration_ms * elapsed_weight / total_weight)
            if cue_end_ms - cue_start_ms >= MIN_CUE_DURATION_MS:
                cues.append({"start": cue_start_ms / 1000.0, "end": cue_end_ms / 1000.0, "text": part})
    return cues


def split_subtitle_text(text: str, style_name: str = "前端默认") -> List[str]:
    text = normalize_subtitle_source_text(text)
    if not text:
        return []
    style = SUBTITLE_STYLES.get(style_name, SUBTITLE_STYLES["前端默认"])
    max_chars = int(style.get("max_chars") or 34)
    if subtitle_text_length(text) <= max_chars:
        return [text]

    parts: List[str] = []
    remaining = text
    while subtitle_text_length(remaining) > max_chars:
        cut = find_subtitle_split_index(remaining, max_chars)
        part = remaining[:cut].strip()
        if part:
            parts.append(part)
        remaining = remaining[cut:].strip()
        if not remaining:
            break
    if remaining:
        parts.append(remaining)
    return parts or [text]


def find_subtitle_split_index(text: str, max_chars: int) -> int:
    chars = list(text)
    if len(chars) <= max_chars:
        return len(chars)
    lower = max(1, int(max_chars * 0.55))
    upper = min(len(chars), max_chars + 8)
    for index in range(upper, lower - 1, -1):
        if chars[index - 1] in SPLIT_HINT_CHARS:
            return index
    return min(len(chars), max_chars)


def run_funasr_transcription(audio_path: str, work_dir: str) -> Tuple[Any, List[Dict[str, Any]], str]:
    if not audio_path or not os.path.exists(audio_path):
        raise FileNotFoundError(f"缺少合并讲解音频，无法生成 FunASR 字幕: {audio_path}")

    ffmpeg = find_tool("ffmpeg", ["OPENMAIC_FFMPEG_PATH", "FFMPEG_PATH"])
    wav_path = os.path.join(work_dir, "funasr-input.wav")
    result_path = os.path.join(work_dir, "funasr-result.json")
    script_path = os.path.join(work_dir, "funasr-transcribe.py")
    run_command([ffmpeg, "-y", "-i", audio_path, "-ar", "16000", "-ac", "1", wav_path], timeout=600)

    with open(script_path, "w", encoding="utf-8") as f:
        f.write(FUNASR_TRANSCRIBE_SCRIPT)

    python_bin = (
        os.environ.get("OPENMAIC_FUNASR_PYTHON")
        or os.environ.get("FUNASR_PYTHON")
        or "python"
    )
    timeout = int(float(os.environ.get("OPENMAIC_FUNASR_TIMEOUT_MS") or os.environ.get("FUNASR_TIMEOUT_MS") or 1_800_000) / 1000)
    timeout = max(60, timeout)
    try:
        result = subprocess.run(
            [python_bin, script_path, wav_path, result_path],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(f"未找到 FunASR Python: {python_bin}") from exc
    except subprocess.TimeoutExpired as exc:
        raise TimeoutError(f"FunASR 识别超时，超过 {timeout} 秒。") from exc

    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(f"FunASR 识别失败: {detail}")
    try:
        with open(result_path, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except Exception as exc:
        raise RuntimeError("FunASR 输出格式无效，无法读取 JSON。") from exc

    segments = extract_funasr_segments(raw)
    if not segments:
        raise RuntimeError("FunASR 没有返回可用的句级时间戳。")
    return raw, segments, result_path


FUNASR_TRANSCRIBE_SCRIPT = r'''
import json
import os
import sys
import traceback


def optional_env(name, default=""):
    value = os.environ.get(name, default)
    if value is None:
        return ""
    value = str(value).strip()
    return "" if value.lower() in ("", "none", "false", "0") else value


try:
    from funasr import AutoModel

    audio_path = sys.argv[1]
    output_path = sys.argv[2]

    device = optional_env("OPENMAIC_FUNASR_DEVICE", optional_env("FUNASR_DEVICE", "auto"))
    if device == "auto":
        try:
            import torch
            device = "cuda:0" if torch.cuda.is_available() else "cpu"
        except Exception:
            device = "cpu"

    kwargs = {
        "model": optional_env("OPENMAIC_FUNASR_MODEL", optional_env("FUNASR_MODEL", "paraformer-zh")),
        "device": device,
    }

    vad_model = optional_env("OPENMAIC_FUNASR_VAD_MODEL", optional_env("FUNASR_VAD_MODEL", "fsmn-vad"))
    if vad_model:
        kwargs["vad_model"] = vad_model
        kwargs["vad_kwargs"] = {"max_single_segment_time": int(os.environ.get("OPENMAIC_FUNASR_MAX_SEGMENT_MS", "30000"))}

    punc_model = optional_env("OPENMAIC_FUNASR_PUNC_MODEL", optional_env("FUNASR_PUNC_MODEL", "ct-punc"))
    if punc_model:
        kwargs["punc_model"] = punc_model

    spk_model = optional_env("OPENMAIC_FUNASR_SPK_MODEL", optional_env("FUNASR_SPK_MODEL", ""))
    if spk_model:
        kwargs["spk_model"] = spk_model

    model = AutoModel(**kwargs)
    result = model.generate(
        input=audio_path,
        sentence_timestamp=True,
        batch_size_s=int(os.environ.get("OPENMAIC_FUNASR_BATCH_SIZE_S", "300")),
        use_itn=True,
    )

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False)
except Exception:
    traceback.print_exc()
    sys.exit(1)
'''


def extract_funasr_segments(raw: Any) -> List[Dict[str, Any]]:
    known = collect_known_funasr_segments(raw)
    segments = known if known else collect_any_funasr_segments(raw)
    return normalize_funasr_segments(segments)


def collect_known_funasr_segments(raw: Any) -> List[Dict[str, Any]]:
    segments: List[Dict[str, Any]] = []

    def visit(value: Any) -> None:
        if isinstance(value, list):
            for item in value:
                visit(item)
            return
        if not isinstance(value, dict):
            return
        has_child_segments = False
        for key in ["sentence_info", "sentences", "segments", "result", "results"]:
            child = value.get(key)
            if isinstance(child, list) and child:
                has_child_segments = True
                visit(child)
        if not has_child_segments:
            segment = extract_object_segment(value)
            if segment:
                segments.append(segment)

    visit(raw)
    return segments


def collect_any_funasr_segments(raw: Any) -> List[Dict[str, Any]]:
    segments: List[Dict[str, Any]] = []

    def visit(value: Any) -> None:
        if isinstance(value, list):
            for item in value:
                visit(item)
            return
        if not isinstance(value, dict):
            return
        segment = extract_object_segment(value)
        if segment:
            segments.append(segment)
        for child in value.values():
            visit(child)

    visit(raw)
    return segments


def extract_object_segment(obj: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    text = normalize_subtitle_source_text(
        obj.get("text") or obj.get("sentence") or obj.get("content") or obj.get("onebest") or ""
    )
    if not text:
        return None
    time_range = get_object_time_range(obj)
    if not time_range:
        return None
    start_ms, end_ms = time_range
    if end_ms <= start_ms:
        return None
    return {"text": text, "startMs": start_ms, "endMs": end_ms}


def get_object_time_range(obj: Dict[str, Any]) -> Optional[Tuple[int, int]]:
    start = first_timestamp_ms(obj, ["start_ms", "begin_ms", "start", "begin", "start_time", "begin_time"])
    end = first_timestamp_ms(obj, ["end_ms", "end", "end_time", "finish_time"])
    if start is not None and end is not None:
        return (start, end)

    timestamp = obj.get("timestamp")
    if isinstance(timestamp, list) and len(timestamp) >= 2:
        first = timestamp[0]
        last = timestamp[-1]
        if isinstance(first, list) and isinstance(last, list):
            ts_start = read_timestamp_ms(first[0] if first else None)
            ts_end = read_timestamp_ms(last[1] if len(last) > 1 else (last[0] if last else None))
        else:
            ts_start = read_timestamp_ms(first)
            ts_end = read_timestamp_ms(last)
        if ts_start is not None and ts_end is not None:
            return (ts_start, ts_end)
    return None


def first_timestamp_ms(obj: Dict[str, Any], keys: List[str]) -> Optional[int]:
    for key in keys:
        value = read_timestamp_ms(obj.get(key))
        if value is not None:
            return value
    return None


def read_timestamp_ms(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    if isinstance(value, str) and ":" in value:
        return parse_clock_timestamp_ms(value)
    try:
        number_value = float(value)
    except Exception:
        return None
    if not number_value == number_value:
        return None
    looks_like_seconds = isinstance(value, str) and "." in value or not float(number_value).is_integer()
    return int(round(number_value * 1000 if looks_like_seconds else number_value))


def parse_clock_timestamp_ms(value: str) -> Optional[int]:
    try:
        parts = [float(part) for part in value.split(":")]
    except Exception:
        return None
    if len(parts) == 3:
        return int(round(((parts[0] * 60 + parts[1]) * 60 + parts[2]) * 1000))
    if len(parts) == 2:
        return int(round((parts[0] * 60 + parts[1]) * 1000))
    return None


def normalize_funasr_segments(segments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    deduped: Dict[str, Dict[str, Any]] = {}
    for segment in segments:
        text = normalize_subtitle_source_text(segment.get("text") or "")
        start_ms = max(0, int(round(float(segment.get("startMs") or 0))))
        end_ms = max(start_ms + 1, int(round(float(segment.get("endMs") or 0))))
        if not text or end_ms - start_ms < MIN_CUE_DURATION_MS:
            continue
        deduped[f"{start_ms}:{end_ms}:{text}"] = {"text": text, "startMs": start_ms, "endMs": end_ms}
    return sorted(deduped.values(), key=lambda item: (item["startMs"], item["endMs"]))


def align_funasr_segments_to_speech_events(
    speech_events: List[Dict[str, Any]],
    raw_segments: List[Dict[str, Any]],
    style_name: str,
) -> List[Dict[str, Any]]:
    segments = [
        {**segment, "text": normalize_subtitle_source_text(segment.get("text") or "")}
        for segment in raw_segments
        if normalize_subtitle_source_text(segment.get("text") or "")
        and int(segment.get("endMs") or 0) - int(segment.get("startMs") or 0) >= MIN_CUE_DURATION_MS
    ]
    speech_aware_segments = split_merged_segments_by_speech_events(speech_events, segments)
    assignments = assign_segments_to_speech_events(speech_events, speech_aware_segments)
    aligned: List[Dict[str, Any]] = []

    for speech_index, speech_event in enumerate(speech_events):
        matched_segments = [speech_aware_segments[i] for i in assignments[speech_index]]
        timed_segments = keep_timed_segments(matched_segments)
        cue_segments = keep_timed_segments(
            [
                segment
                for segment in (clamp_segment_to_speech_event(seg, speech_event) for seg in timed_segments)
                if segment is not None
            ]
        )
        match = build_funasr_match_result(speech_event, cue_segments)
        if not match or should_fallback_to_estimated(match):
            aligned.append(
                {
                    "speechEvent": speech_event,
                    "mode": "estimated-fallback",
                    "matchedSegments": timed_segments,
                    "match": match,
                    "cues": build_estimated_subtitle_cues([speech_event], style_name),
                }
            )
            continue

        cues = build_aligned_cues_for_speech(speech_event, cue_segments, style_name)
        if not cues:
            aligned.append(
                {
                    "speechEvent": speech_event,
                    "mode": "estimated-fallback",
                    "matchedSegments": timed_segments,
                    "match": match,
                    "cues": build_estimated_subtitle_cues([speech_event], style_name),
                }
            )
            continue

        aligned.append(
            {
                "speechEvent": speech_event,
                "mode": "funasr-aligned",
                "matchedSegments": timed_segments,
                "match": match,
                "cues": cues,
            }
        )
    return aligned


def split_merged_segments_by_speech_events(
    speech_events: List[Dict[str, Any]],
    segments: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    result: List[Dict[str, Any]] = []
    for segment in segments:
        candidates = []
        for speech_event in speech_events:
            text_score = get_text_similarity_score(speech_event.get("text") or "", segment.get("text") or "")
            if text_score < MERGED_SEGMENT_TEXT_SCORE:
                continue
            overlap = get_overlap_ms(
                int(segment["startMs"]),
                int(segment["endMs"]),
                int(speech_event["startMs"]) - MERGED_SEGMENT_TIME_TOLERANCE_MS,
                int(speech_event["endMs"]) + MERGED_SEGMENT_TIME_TOLERANCE_MS,
            )
            if overlap > 0:
                candidates.append(speech_event)
        if len(candidates) < 2:
            result.append(segment)
        else:
            result.extend(split_segment_across_speeches(segment, candidates))
    return sorted(result, key=lambda item: (item["startMs"], item["endMs"]))


def split_segment_across_speeches(segment: Dict[str, Any], speech_events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    duration_ms = int(segment["endMs"]) - int(segment["startMs"])
    weights = [max(1, len(to_alignment_text(event.get("text") or ""))) for event in speech_events]
    total_weight = sum(weights) or len(speech_events)
    parts: List[Dict[str, Any]] = []
    cursor = int(segment["startMs"])
    consumed_weight = 0
    for index, speech_event in enumerate(speech_events):
        consumed_weight += weights[index]
        end_ms = int(segment["endMs"]) if index == len(speech_events) - 1 else int(segment["startMs"]) + round(duration_ms * consumed_weight / total_weight)
        if end_ms - cursor >= MIN_CUE_DURATION_MS:
            parts.append(
                {
                    "text": normalize_subtitle_source_text(speech_event.get("text") or ""),
                    "startMs": cursor,
                    "endMs": end_ms,
                }
            )
        cursor = end_ms
    return parts or [segment]


def assign_segments_to_speech_events(
    speech_events: List[Dict[str, Any]],
    segments: List[Dict[str, Any]],
) -> List[List[int]]:
    assignments: List[List[int]] = [[] for _ in speech_events]
    if not speech_events or not segments:
        return assignments
    speech_index = 0
    for segment_index, segment in enumerate(segments):
        while (
            speech_index < len(speech_events) - 1
            and int(segment["startMs"]) >= int(speech_events[speech_index]["endMs"]) + SEGMENT_WINDOW_TOLERANCE_MS
        ):
            speech_index += 1
        candidates = collect_candidate_speech_indices(speech_events, speech_index, segment)
        best_speech_index = candidates[0] if candidates else speech_index
        best_score = -1.0
        for candidate_index in candidates:
            score = score_segment_for_speech(segment, speech_events[candidate_index])
            if score > best_score:
                best_score = score
                best_speech_index = candidate_index
        assignments[best_speech_index].append(segment_index)
        if best_speech_index > speech_index:
            speech_index = best_speech_index
    return assignments


def collect_candidate_speech_indices(
    speech_events: List[Dict[str, Any]],
    speech_index: int,
    segment: Dict[str, Any],
) -> List[int]:
    candidates: List[int] = []
    for index in range(speech_index, min(len(speech_events), speech_index + SEGMENT_LOOKAHEAD + 1)):
        speech = speech_events[index]
        if int(speech["startMs"]) > int(segment["endMs"]) + SEGMENT_WINDOW_TOLERANCE_MS and candidates:
            break
        candidates.append(index)
    return candidates or [min(speech_index, len(speech_events) - 1)]


def score_segment_for_speech(segment: Dict[str, Any], speech_event: Dict[str, Any]) -> float:
    duration_ms = max(1, int(segment["endMs"]) - int(segment["startMs"]))
    overlap_ms = get_overlap_ms(
        int(segment["startMs"]),
        int(segment["endMs"]),
        int(speech_event["startMs"]),
        int(speech_event["endMs"]),
    )
    overlap_score = overlap_ms / duration_ms
    center_score = get_center_score(segment, speech_event)
    text_score = get_text_similarity_score(segment.get("text") or "", speech_event.get("text") or "")
    return overlap_score * 0.55 + center_score * 0.15 + text_score * 0.3


def get_center_score(segment: Dict[str, Any], speech_event: Dict[str, Any]) -> float:
    center = (int(segment["startMs"]) + int(segment["endMs"])) / 2
    start = int(speech_event["startMs"])
    end = int(speech_event["endMs"])
    if start <= center <= end:
        return 1.0
    distance = start - center if center < start else center - end
    if distance >= SEGMENT_WINDOW_TOLERANCE_MS:
        return 0.0
    return 1 - distance / SEGMENT_WINDOW_TOLERANCE_MS


def build_funasr_match_result(
    speech_event: Dict[str, Any],
    segments: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    if not segments:
        return None
    speech_text = to_alignment_text(speech_event.get("text") or "")
    segment_text = to_alignment_text(" ".join(segment.get("text") or "" for segment in segments))
    speech_duration = max(1, int(speech_event["endMs"]) - int(speech_event["startMs"]))
    covered_duration = sum(int(segment["endMs"]) - int(segment["startMs"]) for segment in segments)
    time_coverage = min(1.0, covered_duration / speech_duration)
    if not speech_text or not segment_text:
        return {
            "score": time_coverage,
            "textCoverage": 0,
            "textPrecision": 0,
            "timeCoverage": time_coverage,
            "matchedSegmentCount": len(segments),
        }
    speech_matched_chars = get_ordered_overlap_count(speech_text, segment_text)
    segment_matched_chars = get_ordered_overlap_count(segment_text, speech_text)
    text_coverage = speech_matched_chars / max(1, len(speech_text))
    text_precision = segment_matched_chars / max(1, len(segment_text))
    score = text_coverage * 0.5 + text_precision * 0.2 + time_coverage * 0.3
    return {
        "score": score,
        "textCoverage": text_coverage,
        "textPrecision": text_precision,
        "timeCoverage": time_coverage,
        "matchedSegmentCount": len(segments),
    }


def should_fallback_to_estimated(match: Dict[str, Any]) -> bool:
    if float(match.get("timeCoverage") or 0) < 0.18:
        return True
    if float(match.get("score") or 0) >= MIN_MATCH_SCORE:
        return False
    return (
        float(match.get("textCoverage") or 0) < MIN_TEXT_COVERAGE
        and float(match.get("textPrecision") or 0) < MIN_TEXT_PRECISION
    )


def keep_timed_segments(segments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [segment for segment in segments if int(segment["endMs"]) - int(segment["startMs"]) >= MIN_CUE_DURATION_MS]


def clamp_segment_to_speech_event(segment: Dict[str, Any], speech_event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    start_ms = max(int(segment["startMs"]), int(speech_event["startMs"]))
    end_ms = min(int(segment["endMs"]), int(speech_event["endMs"]))
    if end_ms - start_ms < MIN_CUE_DURATION_MS:
        return None
    return {**segment, "startMs": start_ms, "endMs": end_ms}


def build_aligned_cues_for_speech(
    speech_event: Dict[str, Any],
    segments: List[Dict[str, Any]],
    style_name: str,
) -> List[Dict[str, Any]]:
    source_text = normalize_subtitle_source_text(speech_event.get("text") or "")
    if not source_text or not segments:
        return []
    if len(segments) == 1:
        return build_estimated_subtitle_cues(
            [
                {
                    **speech_event,
                    "startMs": int(segments[0]["startMs"]),
                    "endMs": int(segments[0]["endMs"]),
                    "text": source_text,
                }
            ],
            style_name,
        )
    weights = [max(1, subtitle_text_length(segment.get("text") or "")) for segment in segments]
    text_parts = split_speech_text_by_weights(source_text, weights, style_name)
    cues: List[Dict[str, Any]] = []
    for index, segment in enumerate(segments):
        text = normalize_subtitle_source_text(text_parts[index] if index < len(text_parts) else "")
        if not text or int(segment["endMs"]) - int(segment["startMs"]) < MIN_CUE_DURATION_MS:
            continue
        cues.extend(
            build_estimated_subtitle_cues(
                [
                    {
                        **speech_event,
                        "startMs": int(segment["startMs"]),
                        "endMs": int(segment["endMs"]),
                        "text": text,
                    }
                ],
                style_name,
            )
        )
    return cues


def split_speech_text_by_weights(text: str, weights: List[int], style_name: str) -> List[str]:
    normalized = normalize_subtitle_source_text(text)
    if not normalized:
        return []
    if len(weights) <= 1:
        return [normalized]
    natural_parts = split_subtitle_text(normalized, style_name)
    if len(natural_parts) == len(weights):
        return natural_parts
    chars = list(normalized)
    total_weight = sum(max(1, weight) for weight in weights) or len(weights)
    parts: List[str] = []
    cursor = 0
    consumed_weight = 0
    for index, weight in enumerate(weights):
        remaining_parts = len(weights) - index - 1
        if index == len(weights) - 1:
            parts.append("".join(chars[cursor:]).strip())
            break
        consumed_weight += max(1, weight)
        target = round(len(chars) * consumed_weight / total_weight)
        min_cut = cursor + 1
        max_cut = len(chars) - remaining_parts
        cut = max(min_cut, min(max_cut, target))
        hinted = find_weighted_split_index(chars, cursor, cut, max_cut)
        parts.append("".join(chars[cursor:hinted]).strip())
        cursor = hinted
    return [part for part in parts if part]


def find_weighted_split_index(chars: List[str], cursor: int, target: int, max_cut: int) -> int:
    search_radius = 8
    lower = max(cursor + 1, target - search_radius)
    upper = min(max_cut, target + search_radius)
    best = target
    best_distance = 10_000
    for index in range(lower, upper + 1):
        if chars[index - 1] not in SPLIT_HINT_CHARS:
            continue
        distance = abs(index - target)
        if distance < best_distance:
            best = index
            best_distance = distance
    return best


def to_alignment_text(text: str) -> str:
    return re.sub(r"[\s,.!?;:'\"()\[\]{}<>，。！？；：、‘’“”《》【】（）…-]+", "", normalize_subtitle_source_text(text).lower())


def get_text_similarity_score(segment_text: str, speech_text: str) -> float:
    segment_comparable = to_alignment_text(segment_text)
    speech_comparable = to_alignment_text(speech_text)
    if not segment_comparable or not speech_comparable:
        return 0.0
    if segment_comparable in speech_comparable:
        return 1.0
    if speech_comparable in segment_comparable:
        return len(speech_comparable) / max(1, len(segment_comparable))
    ordered_coverage = get_ordered_overlap_count(segment_comparable, speech_comparable) / max(1, len(segment_comparable))
    prefix_coverage = get_common_prefix_length(segment_comparable, speech_comparable) / max(1, min(len(segment_comparable), len(speech_comparable)))
    substring_coverage = get_longest_common_substring_length(segment_comparable, speech_comparable) / max(1, len(segment_comparable))
    return max(prefix_coverage, ordered_coverage * 0.7 + substring_coverage * 0.3)


def get_ordered_overlap_count(source: str, target: str) -> int:
    source_index = 0
    target_index = 0
    matched = 0
    while source_index < len(source) and target_index < len(target):
        if source[source_index] == target[target_index]:
            matched += 1
            source_index += 1
            target_index += 1
        else:
            target_index += 1
    return matched


def get_common_prefix_length(left: str, right: str) -> int:
    limit = min(len(left), len(right))
    count = 0
    while count < limit and left[count] == right[count]:
        count += 1
    return count


def get_longest_common_substring_length(left: str, right: str) -> int:
    if not left or not right:
        return 0
    previous = [0] * (len(right) + 1)
    longest = 0
    for left_index in range(1, len(left) + 1):
        current = [0] * (len(right) + 1)
        for right_index in range(1, len(right) + 1):
            if left[left_index - 1] != right[right_index - 1]:
                continue
            current[right_index] = previous[right_index - 1] + 1
            longest = max(longest, current[right_index])
        previous = current
    return longest


def get_overlap_ms(start_a: int, end_a: int, start_b: int, end_b: int) -> int:
    return max(0, min(end_a, end_b) - max(start_a, start_b))


def build_standalone_subtitle_cues(
    timeline: List[Dict[str, Any]],
    merged_audio_path: str,
    timing_provider: str,
    style_name: str,
    work_dir: str,
    output_dir: str,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    speech_events = build_speech_events_from_timeline(timeline)
    if not speech_events:
        return [], {
            "requestedTimingProvider": timing_provider,
            "actualTimingProvider": "estimated",
            "fallbackReason": "没有可用的 speechEvents，无法生成字幕。",
            "debugPath": "",
            "speechEventCount": 0,
            "funasrSegmentCount": 0,
        }

    requested = "funasr" if timing_provider == "FunASR真实对齐" else "estimated"
    if requested != "funasr":
        return build_estimated_subtitle_cues(speech_events, style_name), {
            "requestedTimingProvider": "estimated",
            "actualTimingProvider": "estimated",
            "fallbackReason": "",
            "debugPath": "",
            "speechEventCount": len(speech_events),
            "funasrSegmentCount": 0,
        }

    debug_path = os.path.join(output_dir, "funasr-alignment-debug.json")
    fallback_reason = ""
    try:
        raw, funasr_segments, _ = run_funasr_transcription(merged_audio_path, work_dir)
        aligned = align_funasr_segments_to_speech_events(speech_events, funasr_segments, style_name)
        cues = [cue for item in aligned for cue in item.get("cues", [])]
        debug_data = {
            "speechEvents": speech_events,
            "funasrSegments": funasr_segments,
            "alignment": [
                {
                    "sceneId": item["speechEvent"].get("sceneId"),
                    "speechText": item["speechEvent"].get("text"),
                    "speechStartMs": item["speechEvent"].get("startMs"),
                    "speechEndMs": item["speechEvent"].get("endMs"),
                    "mode": item.get("mode"),
                    "match": item.get("match"),
                    "matchedSegments": item.get("matchedSegments"),
                    "cues": item.get("cues"),
                }
                for item in aligned
            ],
            "raw": raw,
        }
        with open(debug_path, "w", encoding="utf-8") as f:
            f.write(json_dumps(debug_data))
        actual = "funasr" if any(item.get("mode") == "funasr-aligned" for item in aligned) else "estimated"
        return cues, {
            "requestedTimingProvider": "funasr",
            "actualTimingProvider": actual,
            "fallbackReason": "" if actual == "funasr" else "FunASR 未能可靠匹配任何讲稿段，已回退估算。",
            "debugPath": debug_path,
            "speechEventCount": len(speech_events),
            "funasrSegmentCount": len(funasr_segments),
        }
    except Exception as exc:
        fallback_reason = str(exc)
        cues = build_estimated_subtitle_cues(speech_events, style_name)
        debug_data = {
            "speechEvents": speech_events,
            "funasrSegments": [],
            "alignment": [],
            "fallbackReason": fallback_reason,
        }
        try:
            with open(debug_path, "w", encoding="utf-8") as f:
                f.write(json_dumps(debug_data))
        except Exception:
            debug_path = ""
        return cues, {
            "requestedTimingProvider": "funasr",
            "actualTimingProvider": "estimated",
            "fallbackReason": fallback_reason,
            "debugPath": debug_path,
            "speechEventCount": len(speech_events),
            "funasrSegmentCount": 0,
        }


@register_node
class OpenMAICStandaloneImportCourseware:
    CATEGORY = "OpenMAIC/独立版"
    DISPLAY_NAME = "OpenMAIC 独立导入课件"
    RETURN_TYPES = ("STRING", "STRING", "STRING", "STRING", "INT")
    RETURN_NAMES = ("课件数据", "页面图片JSON", "页面图片目录", "页面文本JSON", "页数")
    FUNCTION = "import_courseware"

    @classmethod
    def INPUT_TYPES(cls) -> Dict[str, Any]:
        return {
            "required": {
                "课件路径": ("STRING", {"default": "", "tooltip": "PPTX/PDF 文件路径，或图片目录路径"}),
            },
            "optional": {
                "输出目录": ("STRING", {"default": DEFAULT_PAGE_DIR}),
                "课件标题": ("STRING", {"default": ""}),
                "覆盖已有文件": ("BOOLEAN", {"default": True}),
            },
        }

    def import_courseware(
        self,
        课件路径: str,
        输出目录: str = DEFAULT_PAGE_DIR,
        课件标题: str = "",
        覆盖已有文件: bool = True,
    ) -> Tuple[str, str, str, str, int]:
        source = normalize_local_path_input(课件路径)
        if not source or not os.path.exists(source):
            raise ValueError(f"课件路径不存在: {source or 课件路径}")

        output_dir = ensure_dir(normalize_local_path_input(输出目录) or DEFAULT_PAGE_DIR)
        title = clean_imported_text(课件标题) or clean_imported_text(Path(source).stem) or "Imported Deck"
        ext = Path(source).suffix.lower()
        image_paths: List[str] = []
        text_pages: List[Dict[str, Any]] = []
        slides: List[Dict[str, Any]] = []
        warnings: List[str] = []
        render_source: Optional[Dict[str, str]] = None

        if os.path.isdir(source):
            files = sorted(
                [f for f in os.listdir(source) if Path(f).suffix.lower() in IMAGE_EXTS],
                key=natural_key,
            )
            if not files:
                raise ValueError(f"图片目录里没有可用图片: {source}")
            for index, filename in enumerate(files, 1):
                src = os.path.join(source, filename)
                dst = os.path.join(output_dir, f"page-{index:03d}{Path(filename).suffix.lower()}")
                copy_or_overwrite(src, dst, 覆盖已有文件)
                image_paths.append(dst)
                width, height = image_size(dst)
                slides.append(
                    {
                        "index": index,
                        "image": file_to_data_url(dst),
                        "imagePath": os.path.abspath(dst),
                        "width": width,
                        "height": height,
                        "text": "",
                        "hotspots": [full_slide_hotspot(index)],
                    }
                )
        elif ext in PRESENTATION_EXTS:
            converted_pdf_path: Optional[str] = None
            try:
                with tempfile.TemporaryDirectory(prefix="openmaic_pptx_pdf_") as temp_dir:
                    converted_pdf_path = convert_pptx_to_pdf_like_frontend(source, temp_dir)
                    temp_images = render_pdf_to_output(converted_pdf_path, temp_dir, True)
                    for index, img in enumerate(temp_images, 1):
                        dst = os.path.join(output_dir, f"page-{index:03d}.png")
                        copy_or_overwrite(img, dst, True)
                        image_paths.append(dst)
                    try:
                        render_source = {"type": "pdf", "dataUrl": file_to_data_url(converted_pdf_path, "application/pdf")}
                    except Exception:
                        render_source = None
            except Exception as pdf_error:
                image_paths = extract_pptx_embedded_image_pages(source, output_dir, True)
                if image_paths:
                    warnings.append(
                        f"PPTX 转 PDF 失败，已改用 PPTX 内嵌整页图片作为页面截图: {pdf_error}"
                    )
                else:
                    raise RuntimeError(
                        "PPTX 导入失败：无法转 PDF，也没有找到可用的内嵌整页图片。"
                        "请安装 LibreOffice，或先在 PowerPoint 中导出为 PDF 后再导入。"
                        f" 转 PDF错误: {pdf_error}"
                    ) from pdf_error
            if not image_paths:
                raise RuntimeError("PPTX 导入失败：没有生成任何页面图片。")
            slides = extract_pptx_text_safe(source, len(image_paths))
            normalized_slides: List[Dict[str, Any]] = []
            if len(slides) != len(image_paths):
                warnings.append("PPTX 文本页数和渲染图片页数不一致，已按图片页数补齐。")
            for index, image_path in enumerate(image_paths, 1):
                slide = slides[index - 1] if index - 1 < len(slides) else {}
                text = clean_imported_text(slide.get("text", ""))
                note = clean_imported_text(slide.get("note", ""))
                width, height = image_size(image_path)
                hotspots = pptx_shapes_to_hotspots(slide, index)
                normalized_slide = {
                    "index": index,
                    "image": file_to_data_url(image_path),
                    "imagePath": os.path.abspath(image_path),
                    "width": width,
                    "height": height,
                    "text": text,
                    "hotspots": hotspots,
                }
                if note:
                    normalized_slide["note"] = note
                normalized_slides.append(normalized_slide)
                text_pages.append(
                    {
                        "pageIndex": index,
                        "title": f"第 {index} 页",
                        "text": text,
                        "note": note,
                        "hotspots": hotspots,
                        "width": width,
                        "height": height,
                        "source": "pptx",
                    }
                )
            slides = normalized_slides
        elif ext == ".pdf":
            image_paths = render_pdf_to_output(source, output_dir, 覆盖已有文件)
            pdf_text = extract_pdf_text_safe(source, len(image_paths))
            for index in range(len(image_paths)):
                item = pdf_text[index] if index < len(pdf_text) else {}
                image_path = image_paths[index]
                text = clean_imported_text(item.get("text", ""))
                width, height = image_size(image_path)
                hotspots = pdf_shapes_to_hotspots(item, index + 1)
                slides.append(
                    {
                        "index": index + 1,
                        "image": file_to_data_url(image_path),
                        "imagePath": os.path.abspath(image_path),
                        "width": width,
                        "height": height,
                        "text": text,
                        "hotspots": hotspots,
                    }
                )
                text_pages.append(
                    {
                        "pageIndex": index + 1,
                        "title": f"第 {index + 1} 页",
                        "text": text,
                        "note": "",
                        "hotspots": hotspots,
                        "width": width,
                        "height": height,
                        "source": "pdf",
                    }
                )
        elif ext in IMAGE_EXTS:
            dst = os.path.join(output_dir, f"page-001{ext}")
            copy_or_overwrite(source, dst, 覆盖已有文件)
            image_paths = [dst]
            width, height = image_size(dst)
            hotspots = [full_slide_hotspot(1)]
            slides = [
                {
                    "index": 1,
                    "image": file_to_data_url(dst),
                    "imagePath": os.path.abspath(dst),
                    "width": width,
                    "height": height,
                    "text": "",
                    "hotspots": hotspots,
                }
            ]
        else:
            raise ValueError("只支持 PPTX/PPT、PDF、单张图片或图片目录。")

        pages = []
        for index, path in enumerate(image_paths, 1):
            width, height = image_size(path)
            pages.append(
                {
                    "pageIndex": index,
                    "sceneId": f"page-{index:03d}",
                    "title": f"第 {index} 页",
                    "imagePath": os.path.abspath(path),
                    "width": width,
                    "height": height,
                }
            )
            slide = slides[index - 1] if index - 1 < len(slides) else {}
            if len(text_pages) < index:
                text_pages.append(
                    {
                        "pageIndex": index,
                        "title": f"第 {index} 页",
                        "text": clean_imported_text(slide.get("text", "")),
                        "note": clean_imported_text(slide.get("note", "")),
                        "hotspots": slide.get("hotspots", [full_slide_hotspot(index)]),
                        "width": width,
                        "height": height,
                        "source": "images" if os.path.isdir(source) or ext in IMAGE_EXTS else ext.lstrip("."),
                    }
                )

        deck = {
            "title": title,
            "sourceType": "images" if os.path.isdir(source) or ext in IMAGE_EXTS else ("pdf" if ext == ".pdf" else "pptx"),
            "slides": [
                {
                    key: value
                    for key, value in slide.items()
                    if key != "imagePath"
                }
                for slide in slides
            ],
            "diagnostics": imported_deck_diagnostics(slides),
        }
        if warnings:
            deck["warnings"] = warnings
        if render_source:
            deck["renderSource"] = render_source

        with open(os.path.join(output_dir, "openmaic-standalone-pages.json"), "w", encoding="utf-8") as f:
            f.write(json_dumps(pages))
        with open(os.path.join(output_dir, "openmaic-standalone-deck.json"), "w", encoding="utf-8") as f:
            f.write(json_dumps(deck))
        with open(os.path.join(output_dir, "openmaic-standalone-page-text.json"), "w", encoding="utf-8") as f:
            f.write(json_dumps(text_pages))
        return (json_dumps(deck), json_dumps(pages), output_dir, json_dumps(text_pages), len(pages))


@register_node
class OpenMAICStandaloneGenerateScript:
    CATEGORY = "OpenMAIC/独立版"
    DISPLAY_NAME = "OpenMAIC 独立生成讲稿"
    RETURN_TYPES = ("STRING", "STRING", "INT")
    RETURN_NAMES = ("分段讲稿JSON", "完整讲稿", "段数")
    FUNCTION = "generate_script"

    @classmethod
    def INPUT_TYPES(cls) -> Dict[str, Any]:
        return {
            "required": {
                "页面文本JSON": ("STRING", {"default": "", "multiline": True}),
                "讲稿模式": (["保留原文", "轻度口语化", "教学化改写", "无讲稿按页面生成"], {"default": "轻度口语化"}),
            },
            "optional": {
                "页面图片JSON": ("STRING", {"default": "", "multiline": True}),
                "原始讲稿": ("STRING", {"default": "", "multiline": True}),
                "视觉理解": (["开启", "关闭"], {"default": "开启"}),
                "LLM接口地址": ("STRING", {"default": "https://api.openai.com/v1"}),
                "LLM模型": ("STRING", {"default": "gpt-4o-mini"}),
                "VLM模型": ("STRING", {"default": ""}),
                "LLM_API_KEY": ("STRING", {"default": ""}),
                "单页超时秒": ("INT", {"default": 120, "min": 10, "max": 600}),
                "并发数": ("INT", {"default": 4, "min": 1, "max": 16}),
            },
        }

    def generate_script(
        self,
        页面文本JSON: str,
        讲稿模式: str,
        页面图片JSON: str = "",
        原始讲稿: str = "",
        视觉理解: str = "开启",
        LLM接口地址: str = "https://api.openai.com/v1",
        LLM模型: str = "gpt-4o-mini",
        VLM模型: str = "",
        LLM_API_KEY: str = "",
        单页超时秒: int = 120,
        并发数: int = 4,
    ) -> Tuple[str, str, int]:
        pages = json_loads(页面文本JSON, "页面文本JSON")
        if not isinstance(pages, list) or not pages:
            raise ValueError("页面文本JSON 不能为空。")
        image_pages: List[Dict[str, Any]] = []
        if 页面图片JSON.strip():
            parsed_images = json_loads(页面图片JSON, "页面图片JSON")
            if isinstance(parsed_images, list):
                image_pages = parsed_images
            else:
                raise ValueError("页面图片JSON 必须是数组。")
        image_by_page = {
            int(item.get("pageIndex") or idx + 1): item
            for idx, item in enumerate(image_pages)
            if isinstance(item, dict)
        }

        page_count = len(pages)
        raw_script = (原始讲稿 or "").strip()
        ignore_script = 讲稿模式 == "无讲稿按页面生成"
        has_user_script = bool(raw_script) and not ignore_script
        script_matches = match_script_to_pages(pages, raw_script if has_user_script else "")
        api_key = LLM_API_KEY or os.environ.get("OPENAI_API_KEY") or os.environ.get("LLM_API_KEY") or ""
        needs_ai = 讲稿模式 in {"轻度口语化", "教学化改写", "无讲稿按页面生成"}
        use_vision = needs_ai and 视觉理解 == "开启"
        effective_model = (VLM模型.strip() if use_vision and VLM模型.strip() else LLM模型.strip())

        if needs_ai and not effective_model:
            raise ValueError("需要 AI 生成讲稿时，LLM模型不能为空。")
        if needs_ai and not api_key and "localhost" not in LLM接口地址 and "127.0.0.1" not in LLM接口地址:
            raise ValueError("需要 AI 生成讲稿时，请填写 LLM_API_KEY，或使用本地兼容接口。")

        page_contexts: List[Dict[str, Any]] = []
        for index, page in enumerate(pages, 1):
            page_text = page_source_text(page)
            match = script_matches[index - 1] if index - 1 < len(script_matches) else {"text": "", "source": "empty"}
            original_text = clean_text(match.get("text") or "")
            base_text = original_text if has_user_script else page_text
            previous_seed = ""
            if index > 1:
                prev_page = pages[index - 2]
                prev_match = script_matches[index - 2] if index - 2 < len(script_matches) else {"text": ""}
                previous_seed = clean_text((prev_match.get("text") if has_user_script else "") or page_source_text(prev_page))[-180:]
            generation_mode = "script-rewrite" if has_user_script and needs_ai else ("generate" if needs_ai else "preserve")
            page_contexts.append(
                {
                    "index": index,
                    "page": page,
                    "pageText": page_text,
                    "match": match,
                    "originalText": original_text,
                    "baseText": base_text,
                    "previousTail": previous_seed,
                    "generationMode": generation_mode,
                }
            )

        def build_page_script(ctx: Dict[str, Any]) -> Dict[str, Any]:
            index = int(ctx["index"])
            page = ctx["page"]
            page_text = str(ctx["pageText"] or "")
            match = ctx["match"]
            original_text = str(ctx["originalText"] or "")
            base_text = str(ctx["baseText"] or "")
            previous_tail = str(ctx["previousTail"] or "")
            generation_mode = str(ctx["generationMode"] or "")
            if 讲稿模式 == "保留原文":
                final_text = base_text
            else:
                if 讲稿模式 == "轻度口语化":
                    instruction = (
                        "你是 OpenMAIC 的课件口播讲稿改写器。把输入内容改写成自然中文口播稿，"
                        "保留关键信息，结合课件画面理解内容。禁止朗读页码、标题、大纲、Markdown 表格符号，"
                        "不要输出解释、编号、JSON 或 Markdown。"
                    )
                elif 讲稿模式 == "教学化改写":
                    instruction = (
                        "你是 OpenMAIC 的课程老师讲稿改写器。把输入内容改写成老师上课讲解口吻，"
                        "结合课件画面补足必要过渡和教学解释。禁止照读标题和项目符号，"
                        "不要输出解释、编号、JSON 或 Markdown。"
                    )
                else:
                    instruction = (
                        "你是 OpenMAIC 的课程口播生成器。根据课件画面、页面文字和备注生成自然中文课程口播稿。"
                        "不要朗读页码、标题、大纲字样，不要输出解释、编号、JSON 或 Markdown。"
                    )
                source = base_text or page_text
                if not source and not use_vision:
                    raise RuntimeError(f"第 {index} 页没有可用于生成讲稿的文本；请开启视觉理解或补充原始讲稿。")
                user_text = (
                    f"任务模式：{generation_mode}\n"
                    f"当前页：{index}/{page_count}\n"
                    f"上一页讲稿结尾：{previous_tail or '无'}\n"
                    f"页面提取内容：{page_text or '（无文本提取结果）'}\n"
                    f"匹配到的原始讲稿：{source or '（无原始讲稿）'}\n"
                    "请输出这一页最终口播稿。只输出讲稿正文，不要编号，不要解释。"
                )
                image_item = image_by_page.get(int(page.get("pageIndex") or index), {})
                image_path = str(image_item.get("imagePath") or "")
                messages: List[Dict[str, Any]]
                if use_vision:
                    if not image_path:
                        raise RuntimeError(
                            f"第 {index} 页没有可用于视觉理解的页面图片。请确认“页面图片JSON”已从导入节点连接到生成讲稿节点，或把“视觉理解”改为“关闭”。"
                        )
                    try:
                        image_url = image_to_data_url(image_path)
                    except Exception as exc:
                        raise RuntimeError(f"第 {index} 页视觉理解图片读取失败: {exc}") from exc
                    messages = [
                        {"role": "system", "content": instruction},
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": user_text},
                                {"type": "image_url", "image_url": {"url": image_url}},
                            ],
                        },
                    ]
                else:
                    messages = [
                        {"role": "system", "content": instruction},
                        {"role": "user", "content": user_text},
                    ]
                try:
                    final_text = openai_compatible_chat(
                        LLM接口地址,
                        api_key,
                        effective_model,
                        messages,
                        int(单页超时秒 or 120),
                    )
                except Exception as exc:
                    hint = (
                        "。当前开启了视觉理解，请确认 VLM模型 支持图片输入；如果只想用文本，请把 视觉理解 改为 关闭。"
                        if use_vision
                        else ""
                    )
                    raise RuntimeError(f"第 {index} 页讲稿生成失败: {exc}{hint}") from exc

            final_text = clean_text(clean_imported_text(strip_markdown_fences(final_text)))
            if needs_ai and not final_text:
                raise RuntimeError(f"第 {index} 页讲稿生成失败，AI 返回为空。")
            if not final_text:
                final_text = f"第 {index} 页暂无讲解内容。"

            item = {
                "pageIndex": int(page.get("pageIndex") or index),
                "sceneId": page.get("sceneId") or f"page-{index:03d}",
                "title": page.get("title") or f"第 {index} 页",
                "text": final_text,
                "source": 讲稿模式,
                "matchSource": match.get("source") or "empty",
                "originalText": original_text,
                "rewrittenText": final_text if needs_ai else "",
                "scriptTransformMode": 讲稿模式,
                "generationMode": generation_mode,
            }
            return item

        if needs_ai:
            max_workers = max(1, min(int(并发数 or 4), 16, len(page_contexts)))
        else:
            max_workers = 1

        if max_workers <= 1:
            segments = [build_page_script(ctx) for ctx in page_contexts]
        else:
            results: Dict[int, Dict[str, Any]] = {}
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {executor.submit(build_page_script, ctx): int(ctx["index"]) for ctx in page_contexts}
                for future in as_completed(futures):
                    index = futures[future]
                    try:
                        results[index] = future.result()
                    except Exception as exc:
                        raise RuntimeError(f"第 {index} 页讲稿生成失败: {exc}") from exc
            segments = [results[index] for index in sorted(results)]

        full_parts = [str(item.get("text") or "") for item in segments]

        return (json_dumps(segments), "\n\n".join(full_parts), len(segments))


@register_node
class OpenMAICStandaloneBatchTTS:
    CATEGORY = "OpenMAIC/独立版"
    DISPLAY_NAME = "OpenMAIC 独立批量TTS"
    RETURN_TYPES = ("STRING", "STRING", "STRING", "INT")
    RETURN_NAMES = ("音频清单JSON", "合并讲解音频", "音频片段JSON", "音频数量")
    FUNCTION = "generate_tts"

    @classmethod
    def INPUT_TYPES(cls) -> Dict[str, Any]:
        return {
            "required": {
                "分段讲稿JSON": ("STRING", {"default": "", "multiline": True}),
                "输出目录": ("STRING", {"default": DEFAULT_AUDIO_DIR}),
                "TTS提供商": (["indextts-gradio", "openai-tts", "qwen-tts", "glm-tts", "doubao-tts", "elevenlabs-tts", "voxcpm-tts"], {"default": "indextts-gradio"}),
            },
            "optional": {
                "音色": ("STRING", {"default": "gmg"}),
                "TTS服务地址": ("STRING", {"default": "http://127.0.0.1:7861"}),
                "TTS_API_KEY": ("STRING", {"default": ""}),
                "语速": ("FLOAT", {"default": 1.2, "min": 0.5, "max": 2.0, "step": 0.1}),
                "拆分方式": (["按页合并", "按短句拆分"], {"default": "按页合并"}),
                "覆盖已有文件": ("BOOLEAN", {"default": False}),
                "单段超时秒": ("INT", {"default": 900, "min": 30, "max": 3600}),
                "并发数": ("INT", {"default": 1, "min": 1, "max": 16}),
            },
        }

    def generate_tts(
        self,
        分段讲稿JSON: str,
        输出目录: str,
        TTS提供商: str,
        音色: str = "gmg",
        TTS服务地址: str = "http://127.0.0.1:7861",
        TTS_API_KEY: str = "",
        语速: float = 1.2,
        拆分方式: str = "按页合并",
        覆盖已有文件: bool = False,
        单段超时秒: int = 900,
        并发数: int = 1,
    ) -> Tuple[str, str, str, int]:
        pages = json_loads(分段讲稿JSON, "分段讲稿JSON")
        if not isinstance(pages, list) or not pages:
            raise ValueError("分段讲稿JSON 不能为空。")

        output_dir = ensure_dir(输出目录)
        tts = OpenMAIC_文本转语音()
        manifest: List[Dict[str, Any]] = []
        timeline: List[Dict[str, Any]] = []
        current = 0.0

        items: List[Dict[str, Any]] = []
        for page in pages:
            page_index = int(page.get("pageIndex") or len(items) + 1)
            text = clean_text(page.get("text") or "")
            parts = [text] if 拆分方式 == "按页合并" else normalize_segments(text)
            for idx, part in enumerate(parts or [text], 1):
                if not part:
                    continue
                items.append(
                    {
                        "pageIndex": page_index,
                        "sceneId": page.get("sceneId") or f"page-{page_index:03d}",
                        "title": page.get("title") or f"第 {page_index} 页",
                        "segmentIndex": idx,
                        "text": part,
                    }
                )

        if not items:
            raise ValueError("没有可用于 TTS 的文本。")

        def generate_one(item: Dict[str, Any]) -> Dict[str, Any]:
            prefix = f"openmaic-page-{item['pageIndex']:03d}-speech-{item['segmentIndex']:03d}"
            out_path = os.path.join(output_dir, f"{prefix}.wav")
            cache_metadata = build_tts_cache_metadata(TTS提供商, item["text"], 音色, 语速, TTS服务地址)
            reused = False
            generation_info: Dict[str, Any] = {}
            if not 覆盖已有文件 and tts_cache_matches(out_path, cache_metadata):
                reused = True
                generation_info = load_tts_sidecar(out_path) or {}
            else:
                if TTS提供商 == "indextts-gradio":
                    try:
                        generation_info = call_indextts_gradio(
                            item["text"],
                            音色,
                            float(语速),
                            TTS服务地址,
                            out_path,
                            int(单段超时秒 or 900),
                        )
                    except Exception as exc:
                        sample = clean_text(item["text"])[:80]
                        raise RuntimeError(
                            f"IndexTTS 调用失败：第 {item['pageIndex']} 页第 {item['segmentIndex']} 段，文本片段: {sample}。{exc}"
                        ) from exc
                else:
                    audio = tts._call_tts_api(  # type: ignore[attr-defined]
                        TTS提供商,
                        item["text"],
                        音色,
                        float(语速),
                        TTS_API_KEY,
                        TTS服务地址,
                    )
                    with open(out_path, "wb") as f:
                        f.write(audio)
                    generation_info = {"jobId": "api", "sourceAudioPath": os.path.abspath(out_path)}
                write_tts_sidecar(
                    out_path,
                    {
                        **cache_metadata,
                        **(generation_info or {}),
                        "durationSeconds": ffprobe_duration(out_path),
                    },
                )
            duration = ffprobe_duration(out_path)
            return {
                **item,
                "audioPath": os.path.abspath(out_path),
                "durationSeconds": duration,
                "status": "ok",
                "reused": reused,
                "jobId": generation_info.get("jobId") or "",
                "sourceAudioPath": generation_info.get("sourceAudioPath") or "",
                "textHash": cache_metadata["textHash"],
            }

        if TTS提供商 == "indextts-gradio":
            tts_workers = 1
        else:
            tts_workers = max(1, min(int(并发数 or 1), 16, len(items)))

        if tts_workers <= 1:
            manifest = [generate_one(item) for item in items]
        else:
            indexed_results: Dict[int, Dict[str, Any]] = {}
            with ThreadPoolExecutor(max_workers=tts_workers) as executor:
                futures = {executor.submit(generate_one, item): idx for idx, item in enumerate(items)}
                for future in as_completed(futures):
                    idx = futures[future]
                    indexed_results[idx] = future.result()
            manifest = [indexed_results[idx] for idx in sorted(indexed_results)]

        for entry in manifest:
            duration = float(entry.get("durationSeconds") or 0.0)
            timeline.append({**entry, "start": current, "end": current + duration, "duration": duration})
            current += duration

        merged_path = os.path.join(output_dir, "openmaic-standalone-narration.m4a")
        concat_path = os.path.join(output_dir, "openmaic-standalone-audio-concat.txt")
        with open(concat_path, "w", encoding="utf-8") as f:
            for entry in manifest:
                safe = entry["audioPath"].replace("\\", "/").replace("'", "'\\''")
                f.write(f"file '{safe}'\n")
        ffmpeg = find_tool("ffmpeg", ["OPENMAIC_FFMPEG_PATH", "FFMPEG_PATH"])
        run_command([ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", concat_path, "-c:a", "aac", "-b:a", "192k", merged_path], timeout=900)

        with open(os.path.join(output_dir, "openmaic-standalone-tts-manifest.json"), "w", encoding="utf-8") as f:
            f.write(json_dumps(manifest))
        with open(os.path.join(output_dir, "openmaic-standalone-audio-timeline.json"), "w", encoding="utf-8") as f:
            f.write(json_dumps(timeline))
        return (json_dumps(manifest), os.path.abspath(merged_path), json_dumps(timeline), len(manifest))


@register_node
class OpenMAICStandaloneTTSAdapter:
    CATEGORY = "OpenMAIC/独立版"
    DISPLAY_NAME = "OpenMAIC TTS文本转接器"
    RETURN_TYPES = ("STRING", "STRING", "INT")
    RETURN_NAMES = ("TTS文本", "TTS任务JSON", "任务数量")
    OUTPUT_IS_LIST = (True, False, False)
    FUNCTION = "adapt"

    @classmethod
    def INPUT_TYPES(cls) -> Dict[str, Any]:
        return {
            "required": {
                "分段讲稿JSON": ("STRING", {"default": "", "multiline": True}),
            },
            "optional": {
                "拆分方式": (["按页合并", "按短句拆分"], {"default": "按页合并"}),
            },
        }

    def adapt(
        self,
        分段讲稿JSON: str,
        拆分方式: str = "按页合并",
    ) -> Tuple[List[str], str, int]:
        pages = json_loads(分段讲稿JSON, "分段讲稿JSON")
        if not isinstance(pages, list) or not pages:
            raise ValueError("分段讲稿JSON 不能为空。")

        tasks: List[Dict[str, Any]] = []
        for page in pages:
            page_index = int(page.get("pageIndex") or len(tasks) + 1)
            text = clean_text(page.get("text") or "")
            parts = [text] if 拆分方式 == "按页合并" else normalize_segments(text)
            for idx, part in enumerate(parts or [text], 1):
                part = clean_text(part)
                if not part:
                    continue
                tasks.append(
                    {
                        "pageIndex": page_index,
                        "sceneId": page.get("sceneId") or f"page-{page_index:03d}",
                        "title": page.get("title") or f"第 {page_index} 页",
                        "segmentIndex": idx,
                        "text": part,
                    }
                )

        if not tasks:
            raise ValueError("没有可用于 TTS 的文本。")

        return ([task["text"] for task in tasks], json_dumps(tasks), len(tasks))


@register_node
class OpenMAICStandaloneCollectTTSAudio:
    CATEGORY = "OpenMAIC/独立版"
    DISPLAY_NAME = "OpenMAIC 收集TTS音频"
    RETURN_TYPES = ("STRING", "STRING", "STRING", "INT")
    RETURN_NAMES = ("音频清单JSON", "合并讲解音频", "音频片段JSON", "音频数量")
    INPUT_IS_LIST = True
    OUTPUT_IS_LIST = (False, False, False, False)
    FUNCTION = "collect"

    @classmethod
    def INPUT_TYPES(cls) -> Dict[str, Any]:
        return {
            "required": {
                "TTS音频": ("AUDIO",),
                "TTS任务JSON": ("STRING", {"default": "", "multiline": True}),
                "输出目录": ("STRING", {"default": DEFAULT_AUDIO_DIR}),
            },
            "optional": {
                "覆盖已有文件": ("BOOLEAN", {"default": True}),
            },
        }

    def collect(
        self,
        TTS音频: List[Any],
        TTS任务JSON: List[str],
        输出目录: List[str],
        覆盖已有文件: List[bool] = None,
    ) -> Tuple[str, str, str, int]:
        tasks_json = TTS任务JSON[0] if isinstance(TTS任务JSON, list) and TTS任务JSON else TTS任务JSON
        output_dir_value = 输出目录[0] if isinstance(输出目录, list) and 输出目录 else 输出目录
        overwrite_value = 覆盖已有文件[0] if isinstance(覆盖已有文件, list) and 覆盖已有文件 else True

        tasks = json_loads(tasks_json, "TTS任务JSON")
        if not isinstance(tasks, list) or not tasks:
            raise ValueError("TTS任务JSON 不能为空。")
        audios = TTS音频 if isinstance(TTS音频, list) else [TTS音频]
        if len(audios) != len(tasks):
            raise ValueError(f"TTS音频数量与任务数量不一致：音频 {len(audios)} 个，任务 {len(tasks)} 个。")

        output_dir = ensure_dir(str(output_dir_value or DEFAULT_AUDIO_DIR))
        manifest: List[Dict[str, Any]] = []
        timeline: List[Dict[str, Any]] = []
        current = 0.0

        for index, (task, audio) in enumerate(zip(tasks, audios), 1):
            page_index = int(task.get("pageIndex") or index)
            segment_index = int(task.get("segmentIndex") or 1)
            prefix = f"openmaic-page-{page_index:03d}-speech-{segment_index:03d}"
            out_path = os.path.join(output_dir, f"{prefix}.wav")
            existed_before = os.path.exists(out_path)
            reused = bool(not overwrite_value and existed_before)
            if not reused:
                wav, sample_rate = _comfyui_audio_to_waveform(audio, f"TTS音频 第 {index} 段")
                _save_pcm16_wav(out_path, wav, sample_rate, f"TTS音频 第 {index} 段")
            duration = ffprobe_duration(out_path)
            entry = {
                **task,
                "audioPath": os.path.abspath(out_path),
                "durationSeconds": duration,
                "status": "ok",
                "reused": reused,
                "jobId": "comfyui-index-tts-node",
                "sourceAudioPath": os.path.abspath(out_path),
                "textHash": tts_text_hash(str(task.get("text") or "")),
            }
            manifest.append(entry)
            timeline.append({**entry, "start": current, "end": current + duration, "duration": duration})
            current += duration

        merged_path = os.path.join(output_dir, "openmaic-standalone-narration.m4a")
        concat_path = os.path.join(output_dir, "openmaic-standalone-audio-concat.txt")
        with open(concat_path, "w", encoding="utf-8") as f:
            for entry in manifest:
                safe = entry["audioPath"].replace("\\", "/").replace("'", "'\\''")
                f.write(f"file '{safe}'\n")
        ffmpeg = find_tool("ffmpeg", ["OPENMAIC_FFMPEG_PATH", "FFMPEG_PATH"])
        run_command([ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", concat_path, "-c:a", "aac", "-b:a", "192k", merged_path], timeout=900)

        with open(os.path.join(output_dir, "openmaic-standalone-tts-manifest.json"), "w", encoding="utf-8") as f:
            f.write(json_dumps(manifest))
        with open(os.path.join(output_dir, "openmaic-standalone-audio-timeline.json"), "w", encoding="utf-8") as f:
            f.write(json_dumps(timeline))
        return (json_dumps(manifest), os.path.abspath(merged_path), json_dumps(timeline), len(manifest))


@register_node
class OpenMAICStandaloneExportVideo:
    CATEGORY = "OpenMAIC/独立版"
    DISPLAY_NAME = "OpenMAIC 独立导出课件视频"
    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("视频路径", "视频清单JSON")
    FUNCTION = "export_video"
    OUTPUT_NODE = True

    @classmethod
    def INPUT_TYPES(cls) -> Dict[str, Any]:
        return {
            "required": {
                "页面图片JSON": ("STRING", {"default": "", "multiline": True}),
                "音频清单JSON": ("STRING", {"default": "", "multiline": True}),
                "音频片段JSON": ("STRING", {"default": "", "multiline": True}),
                "合并讲解音频": ("STRING", {"default": ""}),
                "输出目录": ("STRING", {"default": DEFAULT_VIDEO_DIR}),
                "视频文件名": ("STRING", {"default": "openmaic-standalone-courseware.mp4"}),
                "分辨率": (list(RESOLUTIONS.keys()), {"default": "2K 1920x1080"}),
            },
            "optional": {
                "字幕": (["开启", "关闭"], {"default": "开启"}),
                "字幕时间轴": (["FunASR真实对齐", "估算时间轴"], {"default": "FunASR真实对齐"}),
                "字幕样式预设": (list(SUBTITLE_STYLES.keys()), {"default": "前端默认"}),
                "背景音乐": ("AUDIO",),
                "背景音乐路径": ("STRING", {"default": ""}),
                "编码器": (["cpu", "nvenc", "qsv", "amf"], {"default": "cpu"}),
                "帧率": ("INT", {"default": 30, "min": 24, "max": 60}),
                "覆盖已有文件": ("BOOLEAN", {"default": True}),
                "背景音乐循环到结尾": ("BOOLEAN", {"default": True}),
                "片段并发数": ("INT", {"default": 2, "min": 1, "max": 4}),
            },
        }

    def export_video(
        self,
        页面图片JSON: str,
        音频清单JSON: str,
        音频片段JSON: str,
        合并讲解音频: str,
        输出目录: str,
        视频文件名: str,
        分辨率: str,
        字幕: str = "开启",
        字幕时间轴: str = "FunASR真实对齐",
        字幕样式预设: str = "前端默认",
        背景音乐: Any = None,
        背景音乐路径: str = "",
        编码器: str = "cpu",
        帧率: int = 30,
        覆盖已有文件: bool = True,
        背景音乐循环到结尾: bool = True,
        片段并发数: int = 2,
        **额外参数: Any,
    ) -> Tuple[str, str]:
        if 背景音乐 is None and "背景音乐音频" in 额外参数:
            背景音乐 = 额外参数.get("背景音乐音频")
        if not 背景音乐路径 and "背景音乐文本路径" in 额外参数:
            背景音乐路径 = str(额外参数.get("背景音乐文本路径") or "")

        pages = json_loads(页面图片JSON, "页面图片JSON")
        audio_manifest = json_loads(音频清单JSON, "音频清单JSON")
        timeline = json_loads(音频片段JSON, "音频片段JSON")
        if not isinstance(pages, list) or not pages:
            raise ValueError("页面图片JSON 不能为空。")
        if not isinstance(audio_manifest, list) or not audio_manifest:
            raise ValueError("音频清单JSON 不能为空。")
        if not isinstance(timeline, list) or not timeline:
            raise ValueError("音频片段JSON 不能为空。")

        output_dir = ensure_dir(输出目录)
        filename = Path(视频文件名 or "openmaic-standalone-courseware.mp4").stem + ".mp4"
        output_path = os.path.join(output_dir, filename)
        if os.path.exists(output_path) and not 覆盖已有文件:
            return (os.path.abspath(output_path), json_dumps({"videoPath": os.path.abspath(output_path), "status": "skipped_existing"}))

        width, height, bitrate = RESOLUTIONS.get(分辨率, RESOLUTIONS["2K 1920x1080"])
        ffmpeg = find_tool("ffmpeg", ["OPENMAIC_FFMPEG_PATH", "FFMPEG_PATH"])
        codec_map = {"cpu": "libx264", "nvenc": "h264_nvenc", "qsv": "h264_qsv", "amf": "h264_amf"}
        codec = codec_map.get(编码器, "libx264")
        preset_args = ["-preset", "veryfast"] if codec == "libx264" else ["-preset", "fast"]
        page_map = {int(p.get("pageIndex") or i + 1): p for i, p in enumerate(pages)}

        work_dir = tempfile.mkdtemp(prefix="openmaic_standalone_video_")
        clips: List[str] = []
        try:
            def build_clip(index: int, entry: Dict[str, Any]) -> str:
                page_index = int(entry.get("pageIndex") or index)
                page = page_map.get(page_index) or pages[min(page_index - 1, len(pages) - 1)]
                image_path = page.get("imagePath")
                audio_path = entry.get("audioPath")
                if not image_path or not os.path.exists(image_path):
                    raise FileNotFoundError(f"找不到第 {page_index} 页图片: {image_path}")
                if not audio_path or not os.path.exists(audio_path):
                    raise FileNotFoundError(f"找不到第 {index} 段音频: {audio_path}")
                duration = float(entry.get("durationSeconds") or ffprobe_duration(audio_path))
                clip_path = os.path.join(work_dir, f"clip-{index:04d}.mp4")
                vf = f"scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,format=yuv420p"
                run_command(
                    [
                        ffmpeg,
                        "-y",
                        "-loop",
                        "1",
                        "-t",
                        f"{duration:.3f}",
                        "-i",
                        image_path,
                        "-i",
                        audio_path,
                        "-vf",
                        vf,
                        "-r",
                        str(int(帧率 or 30)),
                        "-c:v",
                        codec,
                        *preset_args,
                        "-b:v",
                        f"{bitrate}M",
                        "-c:a",
                        "aac",
                        "-b:a",
                        "192k",
                        "-shortest",
                        clip_path,
                    ],
                    timeout=600,
                )
                return clip_path

            clip_workers = max(1, min(int(片段并发数 or 2), 4, len(audio_manifest)))
            if width >= 3840:
                clip_workers = min(clip_workers, 2)

            if clip_workers <= 1:
                clips = [build_clip(index, entry) for index, entry in enumerate(audio_manifest, 1)]
            else:
                indexed_clips: Dict[int, str] = {}
                with ThreadPoolExecutor(max_workers=clip_workers) as executor:
                    futures = {
                        executor.submit(build_clip, index, entry): index
                        for index, entry in enumerate(audio_manifest, 1)
                    }
                    for future in as_completed(futures):
                        index = futures[future]
                        indexed_clips[index] = future.result()
                clips = [indexed_clips[index] for index in sorted(indexed_clips)]

            concat_list = os.path.join(work_dir, "clips.txt")
            with open(concat_list, "w", encoding="utf-8") as f:
                for clip in clips:
                    f.write(f"file '{clip.replace(chr(92), '/')}'\n")
            joined = os.path.join(work_dir, "joined.mp4")
            run_command([ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", concat_list, "-c", "copy", joined], timeout=900)

            filters: List[str] = []
            subtitle_path = ""
            srt_path = ""
            subtitle_debug_path = ""
            subtitle_info: Dict[str, Any] = {
                "requestedTimingProvider": "none",
                "actualTimingProvider": "none",
                "fallbackReason": "",
                "debugPath": "",
                "speechEventCount": 0,
                "funasrSegmentCount": 0,
            }
            if 字幕 == "开启":
                subtitle_dir = ensure_dir(os.path.join(output_dir, "subtitles"))
                cues, subtitle_info = build_standalone_subtitle_cues(
                    timeline,
                    合并讲解音频,
                    字幕时间轴,
                    字幕样式预设,
                    work_dir,
                    subtitle_dir,
                )
                if cues:
                    subtitle_path = make_subtitle_ass(cues, os.path.join(subtitle_dir, "subtitles.ass"), 字幕样式预设, width, height)
                    srt_path = make_subtitle_srt(cues, os.path.join(subtitle_dir, "subtitles.srt"))
                    subtitle_debug_path = subtitle_info.get("debugPath") or ""
                    escaped = subtitle_path.replace("\\", "/").replace(":", "\\:")
                    filters.append(f"subtitles='{escaped}'")

            bgm_loop_to_end = coerce_bool(背景音乐循环到结尾, True)
            bgm_source_path, bgm_source_kind, bgm_warning = prepare_background_music_source(背景音乐, 背景音乐路径, work_dir)
            if bgm_source_path and os.path.exists(bgm_source_path):
                if bgm_loop_to_end:
                    filter_complex = "[0:a]volume=1.0[n];[1:a]volume=0.13,aloop=loop=-1:size=2e+09[b];[n][b]amix=inputs=2:duration=first:normalize=0[aout]"
                    cmd = [ffmpeg, "-y", "-i", joined, "-stream_loop", "-1", "-i", bgm_source_path]
                else:
                    filter_complex = "[0:a]volume=1.0[n];[1:a]volume=0.13[b];[n][b]amix=inputs=2:duration=first:normalize=0[aout]"
                    cmd = [ffmpeg, "-y", "-i", joined, "-i", bgm_source_path]
                if filters:
                    cmd.extend(["-vf", ",".join(filters)])
                cmd.extend(["-filter_complex", filter_complex, "-map", "0:v", "-map", "[aout]", "-c:v", codec, *preset_args, "-b:v", f"{bitrate}M", "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", output_path])
                run_command(cmd, timeout=900)
            elif filters:
                run_command([ffmpeg, "-y", "-i", joined, "-vf", ",".join(filters), "-c:v", codec, *preset_args, "-b:v", f"{bitrate}M", "-c:a", "copy", "-movflags", "+faststart", output_path], timeout=900)
            else:
                shutil.copy2(joined, output_path)

            manifest = {
                "videoPath": os.path.abspath(output_path),
                "resolution": {"width": width, "height": height},
                "fps": int(帧率 or 30),
                "subtitle": 字幕,
                "subtitleTimingProvider": subtitle_info.get("requestedTimingProvider", "none"),
                "actualSubtitleTimingProvider": subtitle_info.get("actualTimingProvider", "none"),
                "subtitleStyle": 字幕样式预设,
                "subtitlePath": os.path.abspath(subtitle_path) if subtitle_path else "",
                "srtPath": os.path.abspath(srt_path) if srt_path else "",
                "funasrDebugPath": os.path.abspath(subtitle_debug_path) if subtitle_debug_path else "",
                "fallbackReason": subtitle_info.get("fallbackReason", ""),
                "speechEventCount": subtitle_info.get("speechEventCount", 0),
                "funasrSegmentCount": subtitle_info.get("funasrSegmentCount", 0),
                "backgroundMusicSource": bgm_source_kind,
                "backgroundMusicPath": os.path.abspath(bgm_source_path) if bgm_source_kind == "path" else "",
                "backgroundMusicLoopToEnd": bgm_loop_to_end,
                "backgroundMusicWarning": bgm_warning,
                "clipCount": len(clips),
                "clipConcurrency": clip_workers,
                "durationSeconds": ffprobe_duration(output_path),
                "createdAt": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
            manifest_path = os.path.join(output_dir, "openmaic-standalone-video-manifest.json")
            with open(manifest_path, "w", encoding="utf-8") as f:
                f.write(json_dumps(manifest))
            return (os.path.abspath(output_path), json_dumps(manifest))
        finally:
            shutil.rmtree(work_dir, ignore_errors=True)


NODE_CLASS_MAPPINGS = {
    "OpenMAICStandaloneImportCourseware": OpenMAICStandaloneImportCourseware,
    "OpenMAICStandaloneGenerateScript": OpenMAICStandaloneGenerateScript,
    "OpenMAICStandaloneBatchTTS": OpenMAICStandaloneBatchTTS,
    "OpenMAICStandaloneTTSAdapter": OpenMAICStandaloneTTSAdapter,
    "OpenMAICStandaloneCollectTTSAudio": OpenMAICStandaloneCollectTTSAudio,
    "OpenMAICStandaloneExportVideo": OpenMAICStandaloneExportVideo,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "OpenMAICStandaloneImportCourseware": "OpenMAIC 独立导入课件",
    "OpenMAICStandaloneGenerateScript": "OpenMAIC 独立生成讲稿",
    "OpenMAICStandaloneBatchTTS": "OpenMAIC 独立批量TTS",
    "OpenMAICStandaloneTTSAdapter": "OpenMAIC TTS文本转接器",
    "OpenMAICStandaloneCollectTTSAudio": "OpenMAIC 收集TTS音频",
    "OpenMAICStandaloneExportVideo": "OpenMAIC 独立导出课件视频",
}
