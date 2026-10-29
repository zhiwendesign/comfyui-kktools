import base64
import io
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import numpy as np
import torch
from PIL import Image


MAX_IMAGES = 9
DEFAULT_WIDTH = 220
DEFAULT_HEIGHT = 80
TRANSPARENT_IMAGE = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M/wHwAF/gL+Xw3cWQAAAABJRU5ErkJggg=="
DEFAULT_HTML = """<div style="width:220px;height:80px;display:flex;align-items:center;justify-content:center;background:#171717;color:#ffffff;font-family:Arial,sans-serif;font-size:18px;">
  ${texttitle}
</div>"""

VARIABLE_RE = re.compile(
    r"\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:(?P<quote>['\"`])(?P<text>.*?)(?P=quote)|(?P<number>-?(?:\d+(?:\.\d*)?|\.\d+)))\s*;?",
    re.DOTALL,
)
PLACEHOLDER_RE = re.compile(r"\$\{([A-Za-z_$][\w$]*)\}")
STYLE_SIZE_RE = {
    "width": re.compile(r"\bwidth\s*:\s*(\d+(?:\.\d+)?)px\b", re.IGNORECASE),
    "height": re.compile(r"\bheight\s*:\s*(\d+(?:\.\d+)?)px\b", re.IGNORECASE),
}
ATTRIBUTE_SIZE_RE = {
    "width": re.compile(r"\bwidth\s*=\s*['\"]?(\d+(?:\.\d+)?)", re.IGNORECASE),
    "height": re.compile(r"\bheight\s*=\s*['\"]?(\d+(?:\.\d+)?)", re.IGNORECASE),
}


def _unescape_javascript_string(value, quote):
    return (
        value.replace(f"\\{quote}", quote)
        .replace("\\n", "\n")
        .replace("\\r", "\r")
        .replace("\\t", "\t")
        .replace("\\\\", "\\")
    )


def extract_variables(html):
    variables = {}
    for match in VARIABLE_RE.finditer(str(html or "")):
        value = match.group("text")
        if value is not None:
            value = _unescape_javascript_string(value, match.group("quote"))
        else:
            value = match.group("number")
        variables[match.group(1)] = value
    return variables


def replace_placeholders(html, values):
    return PLACEHOLDER_RE.sub(lambda match: str(values.get(match.group(1), match.group(0))), str(html or ""))


def extract_canvas_size(html):
    dimensions = []
    for name, default in (("width", DEFAULT_WIDTH), ("height", DEFAULT_HEIGHT)):
        match = STYLE_SIZE_RE[name].search(html) or ATTRIBUTE_SIZE_RE[name].search(html)
        value = int(round(float(match.group(1)))) if match else default
        dimensions.append(max(1, value))
    return tuple(dimensions)


def _mask_alpha(mask, index, height, width):
    if mask.ndim == 4:
        frame = mask[min(index, int(mask.shape[0]) - 1)]
        if frame.shape[0] == 1:
            frame = frame[0]
        elif frame.shape[-1] == 1:
            frame = frame[:, :, 0]
    elif mask.ndim == 3:
        frame = mask[min(index, int(mask.shape[0]) - 1)]
    else:
        frame = mask
    if frame.ndim != 2:
        raise ValueError("kcanvas mask input must use the ComfyUI MASK format")
    frame = frame.detach().cpu().to(dtype=torch.float32)
    if tuple(frame.shape) != (height, width):
        frame = torch.nn.functional.interpolate(
            frame[None, None],
            size=(height, width),
            mode="bilinear",
            align_corners=False,
        )[0, 0]
    return (frame.clamp(0.0, 1.0).numpy() * 255.0).round().astype(np.uint8)


def _image_frame(image, index, mask=None):
    frame = image[min(index, int(image.shape[0]) - 1)] if image.ndim == 4 else image
    array = frame.detach().cpu().numpy()
    if array.ndim != 3:
        raise ValueError("kcanvas image inputs must use the ComfyUI IMAGE format")
    if array.shape[0] in (1, 3, 4) and array.shape[-1] not in (1, 3, 4):
        array = np.transpose(array, (1, 2, 0))
    array = (np.clip(array, 0.0, 1.0) * 255.0).round().astype(np.uint8)
    if array.shape[-1] == 1:
        array = np.repeat(array, 3, axis=-1)
    if mask is not None and array.shape[-1] != 4:
        alpha = _mask_alpha(mask, index, array.shape[0], array.shape[1])
        array = np.concatenate((array[:, :, :3], alpha[:, :, None]), axis=-1)
    return Image.fromarray(array[:, :, :4], "RGBA" if array.shape[-1] == 4 else "RGB")


def image_to_data_url(image, index=0, mask=None):
    buffer = io.BytesIO()
    _image_frame(image, index, mask).save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def image_batch_size(image):
    return int(image.shape[0]) if image is not None and image.ndim == 4 else 1


def image_has_alpha(image):
    if image is None or image.ndim not in (3, 4):
        return False
    if image.shape[-1] == 4:
        return True
    channel_axis = 1 if image.ndim == 4 else 0
    return image.shape[channel_axis] == 4


def mask_batch_size(mask):
    return int(mask.shape[0]) if mask is not None and mask.ndim >= 3 else 1


def template_values(html, images, batch_index, mask=None):
    values = extract_variables(html)
    values.setdefault("texttitle", "标题")
    values.setdefault("textcontext", "内容")

    for index in range(1, MAX_IMAGES + 1):
        key = f"image{index}"
        image = images[index - 1]
        if image is not None:
            values[key] = image_to_data_url(image, batch_index, mask if index == 1 else None)
        else:
            values.setdefault(key, TRANSPARENT_IMAGE)

    if images[0] is not None:
        values["img"] = values["image1"]
    elif "img" in values and "image1" not in extract_variables(html):
        values["image1"] = values["img"]
    else:
        values.setdefault("img", values["image1"])
    return values


def _font_css(html):
    font_dir = Path(__file__).resolve().parents[1] / "fonts"
    if not font_dir.is_dir():
        return ""

    lowered = html.lower()
    rules = []
    font_types = {
        ".otf": ("font/otf", "opentype"),
        ".ttf": ("font/ttf", "truetype"),
        ".ttc": ("font/collection", "collection"),
    }
    for path in font_dir.iterdir():
        suffix = path.suffix.lower()
        if suffix not in font_types or path.stem.lower() not in lowered:
            continue
        mime_type, format_name = font_types[suffix]
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        rules.append(
            f"@font-face{{font-family:{json.dumps(path.stem)};src:url(data:{mime_type};base64,{encoded}) format('{format_name}');font-style:normal;}}"
        )
    return "".join(rules)


def prepare_document(html):
    width, height = extract_canvas_size(html)
    css = (
        f"html,body{{margin:0;padding:0;width:{width}px;height:{height}px;overflow:hidden;background:transparent;}}"
        f"*{{box-sizing:border-box;}}{_font_css(html)}"
    )
    style = f"<style>{css}</style>"
    if re.search(r"<html\b", html, re.IGNORECASE):
        if re.search(r"</head\s*>", html, re.IGNORECASE):
            document = re.sub(r"</head\s*>", f"{style}</head>", html, count=1, flags=re.IGNORECASE)
        else:
            document = re.sub(r"(<html\b[^>]*>)", rf"\1<head><meta charset=\"utf-8\">{style}</head>", html, count=1, flags=re.IGNORECASE)
    else:
        document = f"<!doctype html><html><head><meta charset=\"utf-8\">{style}</head><body>{html}</body></html>"
    return document, width, height


def find_browser():
    candidates = [
        os.environ.get("KKTOOLS_BROWSER_PATH"),
        os.environ.get("CHROME_PATH"),
        os.environ.get("EDGE_PATH"),
        shutil.which("google-chrome"),
        shutil.which("google-chrome-stable"),
        shutil.which("chromium"),
        shutil.which("chromium-browser"),
        shutil.which("microsoft-edge"),
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    ]
    return next((candidate for candidate in candidates if candidate and Path(candidate).is_file()), None)


def _browser_output(value):
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value or "")


def _run_browser(command):
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=45,
        )
        detail = (result.stderr or result.stdout or "Chrome did not create a screenshot").strip()
        return result.returncode, detail
    except subprocess.TimeoutExpired as error:
        detail = (_browser_output(error.stderr) or _browser_output(error.stdout)).strip()
        suffix = f": {detail}" if detail else ""
        return None, f"Chrome timed out after {error.timeout} seconds{suffix}"


def _is_windows_gpu_sandbox_failure(returncode, detail):
    lowered = str(detail or "").lower()
    return os.name == "nt" and (
        returncode in (-1073741790, 3221225506)
        or "gpu process isn't usable" in lowered
        or "gpu process exited unexpectedly" in lowered
    )


def render_document(document, width, height):
    browser = find_browser()
    if not browser:
        raise RuntimeError("kcanvas requires a local Chrome or Edge browser")

    with tempfile.TemporaryDirectory(prefix="kktools-kcanvas-") as temp_dir:
        temp_path = Path(temp_dir)
        html_path = temp_path / "canvas.html"
        screenshot_path = temp_path / "canvas.png"
        html_path.write_text(document, encoding="utf-8")
        command = [
            browser,
            "--headless=new",
            "--disable-gpu",
            "--disable-extensions",
            "--hide-scrollbars",
            "--no-first-run",
            "--force-device-scale-factor=1",
            f"--user-data-dir={temp_path / 'profile'}",
            f"--window-size={width},{height}",
            f"--screenshot={screenshot_path}",
            "--virtual-time-budget=5000",
            html_path.as_uri(),
        ]
        if os.name != "nt" and hasattr(os, "geteuid") and os.geteuid() == 0:
            command.insert(1, "--no-sandbox")

        returncode, detail = _run_browser(command)
        failed = returncode != 0 or not screenshot_path.is_file()
        if failed and _is_windows_gpu_sandbox_failure(returncode, detail):
            # Some restricted Windows sessions cannot start Chromium's GPU sandbox.
            # Keep the normal sandboxed path as the default and only relax it for this known failure.
            screenshot_path.unlink(missing_ok=True)
            fallback_command = [command[0], "--no-sandbox", *command[1:]]
            returncode, detail = _run_browser(fallback_command)

        if returncode != 0 or not screenshot_path.is_file():
            raise RuntimeError(f"kcanvas render failed: {detail}")
        with Image.open(screenshot_path) as screenshot:
            array = np.asarray(screenshot.convert("RGB"), dtype=np.float32) / 255.0
    return torch.from_numpy(array)[None,]


class kcanvas:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "html": ("STRING", {"default": DEFAULT_HTML, "multiline": True}),
            },
            "optional": {
                "image1": ("IMAGE",),
                "mask": ("MASK", {"tooltip": "作为 image1 的透明度：白色保留、黑色透明；RGBA 图像优先使用自身 Alpha。"}),
                **{f"image{index}": ("IMAGE",) for index in range(2, MAX_IMAGES + 1)},
            },
        }

    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("image",)
    FUNCTION = "render"
    CATEGORY = "🌟kktools/图像"
    DESCRIPTION = "使用本机 Chrome 或 Edge 将 HTML 渲染为图像；mask 可为 image1 添加透明度。"

    def render(self, html, image1=None, mask=None, **kwargs):
        images = [image1, *[kwargs.get(f"image{index}") for index in range(2, MAX_IMAGES + 1)]]
        batch_size = max((image_batch_size(image) for image in images if image is not None), default=1)
        if image1 is not None and mask is not None and not image_has_alpha(image1):
            batch_size = max(batch_size, mask_batch_size(mask))
        outputs = []
        for batch_index in range(batch_size):
            resolved = replace_placeholders(html, template_values(html, images, batch_index, mask))
            document, width, height = prepare_document(resolved)
            outputs.append(render_document(document, width, height))
        return (torch.cat(outputs, dim=0),)


NODE_CLASS_MAPPINGS = {"kcanvas": kcanvas}
NODE_DISPLAY_NAME_MAPPINGS = {"kcanvas": "kcanvas（HTML渲染）"}
