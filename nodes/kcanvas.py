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


def _image_frame(image, index):
    frame = image[min(index, int(image.shape[0]) - 1)] if image.ndim == 4 else image
    array = frame.detach().cpu().numpy()
    if array.ndim != 3:
        raise ValueError("kcanvas image inputs must use the ComfyUI IMAGE format")
    if array.shape[0] in (1, 3, 4) and array.shape[-1] not in (1, 3, 4):
        array = np.transpose(array, (1, 2, 0))
    array = (np.clip(array, 0.0, 1.0) * 255.0).round().astype(np.uint8)
    if array.shape[-1] == 1:
        array = np.repeat(array, 3, axis=-1)
    return Image.fromarray(array[:, :, :4], "RGBA" if array.shape[-1] == 4 else "RGB")


def image_to_data_url(image, index=0):
    buffer = io.BytesIO()
    _image_frame(image, index).save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def image_batch_size(image):
    return int(image.shape[0]) if image is not None and image.ndim == 4 else 1


def template_values(html, images, batch_index):
    values = extract_variables(html)
    values.setdefault("texttitle", "标题")
    values.setdefault("textcontext", "内容")

    for index in range(1, MAX_IMAGES + 1):
        key = f"image{index}"
        image = images[index - 1]
        if image is not None:
            values[key] = image_to_data_url(image, batch_index)
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
        result = subprocess.run(command, capture_output=True, text=True, timeout=45)
        if result.returncode != 0 or not screenshot_path.is_file():
            detail = (result.stderr or result.stdout or "Chrome did not create a screenshot").strip()
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
                **{f"image{index}": ("IMAGE",) for index in range(1, MAX_IMAGES + 1)},
            },
        }

    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("image",)
    FUNCTION = "render"
    CATEGORY = "🌟kktools/图像"
    DESCRIPTION = "使用本机 Chrome 或 Edge 将 HTML 渲染为图像。"

    def render(self, html, image1=None, **kwargs):
        images = [image1, *[kwargs.get(f"image{index}") for index in range(2, MAX_IMAGES + 1)]]
        batch_size = max((image_batch_size(image) for image in images if image is not None), default=1)
        outputs = []
        for batch_index in range(batch_size):
            resolved = replace_placeholders(html, template_values(html, images, batch_index))
            document, width, height = prepare_document(resolved)
            outputs.append(render_document(document, width, height))
        return (torch.cat(outputs, dim=0),)


NODE_CLASS_MAPPINGS = {"kcanvas": kcanvas}
NODE_DISPLAY_NAME_MAPPINGS = {"kcanvas": "kcanvas（HTML渲染）"}
