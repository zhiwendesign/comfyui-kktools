"""
ComfyUI Custom Node: kkLingsiNativePromptImage
灵思原生 Prompt 生图节点 - 调用 MindAPI 生成图像
"""

import base64
import io
import json
import math
import re
import time
import urllib.error
import urllib.request
import uuid


CHAT_ENDPOINT = "https://www.mindapi.cc/v1/chat/completions"
IMAGE_BASE_URL = "https://www.mindapi.cc/v1"
IMAGE_GENERATIONS_ENDPOINT = f"{IMAGE_BASE_URL}/images/generations"
IMAGE_EDITS_ENDPOINT = f"{IMAGE_BASE_URL}/images/edits"
BANANA_GENERATE_ENDPOINT = "https://www.mindapi.cc/pt/v1/api/generate"
ENDPOINT = CHAT_ENDPOINT
REQUEST_TIMEOUT_SECONDS = 300
MAX_PIXELS = 8_294_400

MODELS = [
    "gpt-image-2",
    "nano-banana-2",
    "nano-banana-pro",
]

ASPECT_RATIOS = [
    "auto",
    "1:1",
    "3:2",
    "2:3",
    "5:4",
    "4:5",
    "4:3",
    "3:4",
    "16:9",
    "9:16",
    "21:9",
    "9:21",
    "2:1",
    "1:2",
    "3:1",
    "1:3",
]

RESOLUTIONS = ["1K", "2K", "4K"]
EDGE_FROM_RESOLUTION = {"1K": 1024, "2K": 2048, "4K": 3840}
SAFE_1K_SIZES = {
    (16, 9): "1536x864",
    (9, 16): "864x1536",
    (21, 9): "1568x672",
    (9, 21): "672x1568",
    (2, 1): "1472x736",
    (1, 2): "736x1472",
    (3, 1): "1776x592",
    (1, 3): "592x1776",
}
GPT_IMAGE_SIZE_TABLE = {
    ("1:1",  "1K"): "1024x1024", ("1:1",  "2K"): "2048x2048", ("1:1",  "4K"): "2880x2880",
    ("16:9", "1K"): "1280x720",  ("16:9", "2K"): "2048x1152", ("16:9", "4K"): "3840x2160",
    ("9:16", "1K"): "720x1280",  ("9:16", "2K"): "1152x2048", ("9:16", "4K"): "2160x3840",
    ("4:3",  "1K"): "1152x864",  ("4:3",  "2K"): "2304x1728", ("4:3",  "4K"): "3264x2448",
    ("3:4",  "1K"): "864x1152",  ("3:4",  "2K"): "1728x2304", ("3:4",  "4K"): "2448x3264",
    ("3:2",  "1K"): "1536x1024", ("3:2",  "2K"): "2048x1360", ("3:2",  "4K"): "3504x2336",
    ("2:3",  "1K"): "1024x1536", ("2:3",  "2K"): "1360x2048", ("2:3",  "4K"): "2336x3504",
    ("5:4",  "1K"): "1120x896",  ("5:4",  "2K"): "2240x1792", ("5:4",  "4K"): "3200x2560",
    ("4:5",  "1K"): "896x1120",  ("4:5",  "2K"): "1792x2240", ("4:5",  "4K"): "2560x3200",
    ("21:9", "1K"): "1456x624",  ("21:9", "2K"): "2912x1248", ("21:9", "4K"): "3840x1648",
    ("9:21", "1K"): "624x1456",  ("9:21", "2K"): "1248x2912", ("9:21", "4K"): "1648x3840",
    ("1:3",  "1K"): "688x2048",                                ("1:3",  "4K"): "1280x3840",
    ("3:1",  "1K"): "2048x688",                                ("3:1",  "4K"): "3840x1280",
    ("2:1",  "1K"): "1536x768",  ("2:1",  "2K"): "3072x1536", ("2:1",  "4K"): "3840x1920",
    ("1:2",  "1K"): "768x1536",  ("1:2",  "2K"): "1536x3072", ("1:2",  "4K"): "1920x3840",
}
GEMINI_EFFECTIVE_RESOLUTION = {
}


class MindAPIHttpError(RuntimeError):
    def __init__(self, status, body, attempts=None):
        super().__init__(f"MindAPI HTTP {status}: {str(body)[:500]}")
        self.status = status
        self.body = body
        self.attempts = attempts or []


class MindAPINetworkError(RuntimeError):
    def __init__(self, message, attempts):
        super().__init__(message)
        self.attempts = attempts


def _json_dumps(value):
    return json.dumps(value, ensure_ascii=False, indent=2)


def _snap_16(value):
    return int(round(max(64, min(3840, value)) / 16) * 16)


def _fit_dimensions(width, height):
    width = max(64, float(width or 1024))
    height = max(64, float(height or 1024))
    scale = min(3840 / max(width, height), math.sqrt(MAX_PIXELS / (width * height)), 1)
    width = _snap_16(width * scale)
    height = _snap_16(height * scale)

    while width * height > MAX_PIXELS and width >= 80 and height >= 80:
        if width >= height:
            width -= 16
        else:
            height -= 16
    return f"{width}x{height}"


def is_gpt_image_model(model):
    return re.match(r"^gpt-image-2(?:$|[-_])", str(model or ""), re.I) is not None


def is_banana_model(model):
    return str(model or "") in {"nano-banana-2", "nano-banana-pro"}


def size_from_aspect(aspect_ratio, max_edge):
    match = re.match(r"^(\d+)\s*[:x]\s*(\d+)$", str(aspect_ratio or "").strip(), re.I)
    if not match:
        return None

    aspect_w = max(1, int(match.group(1)))
    aspect_h = max(1, int(match.group(2)))
    edge = max(64, min(3840, int(max_edge or 1024)))
    if edge == 1024:
        safe_1k_size = SAFE_1K_SIZES.get((aspect_w, aspect_h))
        if safe_1k_size:
            return safe_1k_size

    long_edge = max(aspect_w, aspect_h)
    scale = edge / long_edge

    return _fit_dimensions(aspect_w * scale, aspect_h * scale)


def _image_tensor_size(image):
    if image is None:
        return None
    shape = getattr(image, "shape", None)
    if not shape:
        return None
    dims = [int(item) for item in shape]
    if len(dims) == 4:
        return dims[2], dims[1]
    if len(dims) == 3:
        if dims[-1] in (1, 3, 4):
            return dims[1], dims[0]
        return dims[2], dims[1]
    return None


def size_from_image(image):
    size = _image_tensor_size(image)
    if not size:
        return None
    return _fit_dimensions(size[0], size[1])


def _data_url_summary(value):
    text = str(value or "")
    match = re.match(r"^(data:image/[^;]+;base64,)", text, re.I)
    prefix = match.group(1) if match else ""
    return {
        "type": "data_url",
        "mime": prefix.replace("data:", "").replace(";base64,", "") or "image",
        "length": len(text),
        "preview": f"{prefix}<base64:{max(0, len(text) - len(prefix))} chars>",
    }


def _sanitize_debug_value(value):
    if isinstance(value, dict):
        return {key: _sanitize_debug_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize_debug_value(item) for item in value]
    if isinstance(value, str) and value.startswith("data:image/"):
        return _data_url_summary(value)
    if isinstance(value, str) and len(value) > 4096 and re.match(r"^[A-Za-z0-9+/=_-]+$", value):
        return {
            "type": "base64",
            "length": len(value),
            "preview": f"<base64:{len(value)} chars>",
        }
    return value


def _headers(api_key, content_type="application/json", accept=None):
    headers = {
        "Authorization": f"Bearer {str(api_key or '').strip()}",
        "User-Agent": "ComfyUI-Lingsi-MindAPI-Node/1.0",
        "Connection": "close",
    }
    if content_type:
        headers["Content-Type"] = content_type
    if accept:
        headers["Accept"] = accept
    return headers


def _masked_headers(content_type="application/json", accept=None):
    headers = {"Authorization": "Bearer ***"}
    if content_type:
        headers["Content-Type"] = content_type
    if accept:
        headers["Accept"] = accept
    return headers


def _build_text_prompt(prompt, aspect_ratio):
    text = str(prompt or "").strip()
    if aspect_ratio and aspect_ratio != "auto":
        text += f"\n\n(Aspect ratio: {aspect_ratio}; output the image in this ratio.)"
    return text


def _build_user_content(prompt, aspect_ratio, reference_data_url):
    text = _build_text_prompt(prompt, aspect_ratio)
    if reference_data_url:
        return [
            {"type": "text", "text": text},
            {"type": "image_url", "image_url": {"url": reference_data_url}},
        ]
    return text


def effective_resolution_for_model(model, resolution):
    if model in GEMINI_EFFECTIVE_RESOLUTION:
        return GEMINI_EFFECTIVE_RESOLUTION[model]
    return resolution


def build_request_body(model, prompt, aspect_ratio, resolution, reference_data_url=None, count=1):
    effective_resolution = effective_resolution_for_model(model, resolution)
    content = _build_user_content(prompt, aspect_ratio, reference_data_url)
    body = {
        "model": model,
        "messages": [{"role": "user", "content": content}],
        "n": max(1, int(count or 1)),
    }

    size = None
    if is_gpt_image_model(model):
        body.update({
            "stream": True,
            "temperature": 0.7,
            "group": "default",
            "top_p": 1,
            "frequency_penalty": 0,
            "presence_penalty": 0,
        })
        if aspect_ratio != "auto":
            size = size_from_aspect(aspect_ratio, EDGE_FROM_RESOLUTION[effective_resolution])
            if size:
                body["size"] = size
    else:
        body["temperature"] = 0.7
        image_config = {"image_size": effective_resolution}
        if aspect_ratio != "auto":
            image_config["aspect_ratio"] = aspect_ratio
        body["extra_body"] = {"google": {"image_config": image_config}}

    return body, effective_resolution, size


def build_banana_request_body(model, prompt, aspect_ratio, resolution, image_base64=None):
    images = []
    if image_base64:
        images.append(image_base64)
    return {
        "model": model,
        "prompt": str(prompt or ""),
        "images": images,
        "aspectRatio": aspect_ratio,
        "imageSize": resolution,
        "replyType": "json",
    }


def _http_post_json(api_key, body, stream=False, endpoint=CHAT_ENDPOINT):
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    headers = _headers(
        api_key,
        "application/json",
        "text/event-stream" if stream else "application/json",
    )

    request = urllib.request.Request(endpoint, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            content_type = response.headers.get("Content-Type", "")
            status = getattr(response, "status", None) or response.getcode()
            response_headers = dict(response.headers.items())
            if stream and "json" not in content_type.lower():
                return _read_sse_response(response, status, response_headers)
            return _read_json_response(response, status, response_headers)
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        attempts = [{"attempt": 1, "type": "http", "status": exc.code, "body": raw}]
        raise MindAPIHttpError(exc.code, raw, attempts) from exc
    except (urllib.error.URLError, TimeoutError, ConnectionResetError, OSError) as exc:
        attempts = [{"attempt": 1, "error": str(exc)}]
        message = f"MindAPI request failed: {exc}."
        raise MindAPINetworkError(message, attempts) from exc


def _multipart_body(fields, files):
    boundary = f"----CodexComfyUILingsi{uuid.uuid4().hex}"
    chunks = []

    for name, value in fields.items():
        if value is None:
            continue
        chunks.extend([
            f"--{boundary}\r\n".encode("utf-8"),
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8"),
            str(value).encode("utf-8"),
            b"\r\n",
        ])

    for field_name, filename, content_type, data in files:
        chunks.extend([
            f"--{boundary}\r\n".encode("utf-8"),
            (
                f'Content-Disposition: form-data; name="{field_name}"; '
                f'filename="{filename}"\r\n'
            ).encode("utf-8"),
            f"Content-Type: {content_type}\r\n\r\n".encode("utf-8"),
            data,
            b"\r\n",
        ])

    chunks.append(f"--{boundary}--\r\n".encode("utf-8"))
    return boundary, b"".join(chunks)


def _http_post_multipart(api_key, endpoint, fields, files):
    boundary, data = _multipart_body(fields, files)
    headers = _headers(api_key, f"multipart/form-data; boundary={boundary}", "application/json")

    request = urllib.request.Request(endpoint, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            status = getattr(response, "status", None) or response.getcode()
            return _read_json_response(response, status, dict(response.headers.items()))
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        attempts = [{"attempt": 1, "type": "http", "status": exc.code, "body": raw}]
        raise MindAPIHttpError(exc.code, raw, attempts) from exc
    except (urllib.error.URLError, TimeoutError, ConnectionResetError, OSError) as exc:
        attempts = [{"attempt": 1, "error": str(exc)}]
        message = f"MindAPI request failed: {exc}."
        raise MindAPINetworkError(message, attempts) from exc


def _read_json_response(response, status, headers):
    raw_text = response.read().decode("utf-8", "replace")
    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError:
        data = None
    return {
        "mode": "json",
        "status": status,
        "headers": headers,
        "raw_text": raw_text,
        "json": data,
        "content_text": _extract_chat_text(data) if data is not None else raw_text,
    }


def _read_sse_response(response, status, headers):
    events = []
    parsed_events = []
    content_parts = []

    for raw_line in response:
        line = raw_line.decode("utf-8", "replace").strip()
        if not line or line.startswith(":") or not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if not payload or payload == "[DONE]":
            continue
        events.append(payload)
        try:
            parsed = json.loads(payload)
            parsed_events.append(parsed)
            piece = _extract_stream_piece(parsed)
            if piece:
                content_parts.append(piece)
        except json.JSONDecodeError:
            content_parts.append(payload)

    return {
        "mode": "stream",
        "status": status,
        "headers": headers,
        "stream_events": events,
        "stream_json": parsed_events,
        "content_text": "".join(content_parts),
    }


def _normalize_chat_content(content):
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(filter(None, (_normalize_chat_content(item) for item in content)))
    if isinstance(content, dict):
        if isinstance(content.get("text"), str):
            return content["text"]
        if isinstance(content.get("content"), (str, list, dict)):
            return _normalize_chat_content(content["content"])
        image_url = content.get("image_url")
        if isinstance(image_url, dict) and image_url.get("url"):
            return str(image_url["url"])
        if isinstance(image_url, str):
            return image_url
        for key in ("url", "output_url"):
            if content.get(key):
                return str(content[key])
        inline_data = content.get("inline_data") or content.get("inlineData")
        if isinstance(inline_data, dict) and inline_data.get("data"):
            mime = inline_data.get("mime_type") or inline_data.get("mimeType") or "image/png"
            return f"data:{mime};base64,{inline_data['data']}"
    try:
        return json.dumps(content, ensure_ascii=False)
    except TypeError:
        return str(content)


def _extract_chat_text(data):
    if not isinstance(data, dict):
        return ""
    chunks = []
    choices = data.get("choices")
    if isinstance(choices, list):
        for choice in choices:
            if not isinstance(choice, dict):
                continue
            message = choice.get("message") or {}
            chunks.append(_normalize_chat_content(message.get("content")))
            if isinstance(message.get("images"), list):
                chunks.append(_normalize_chat_content(message["images"]))
            chunks.append(_normalize_chat_content(choice.get("text")))
    chunks.append(_normalize_chat_content(data.get("content")))
    chunks.append(_normalize_chat_content(data.get("text")))
    return "\n".join(filter(None, chunks))


def _extract_stream_piece(data):
    if not isinstance(data, dict):
        return ""
    choice = (data.get("choices") or [{}])[0]
    if not isinstance(choice, dict):
        choice = {}
    delta = choice.get("delta") or {}
    message = choice.get("message") or {}
    for source in (delta, message, choice, data):
        if not isinstance(source, dict):
            continue
        for key in ("content", "text", "image_url", "url", "inline_data", "inlineData"):
            if key in source:
                text = _normalize_chat_content(source.get(key))
                if text:
                    return text
    return ""


def _candidate_exclusion_set(values):
    excluded = set()
    for value in values or []:
        text = str(value or "").strip()
        if not text:
            continue
        excluded.add(text)
        if text.startswith("data:image/") and "," in text:
            excluded.add(text.split(",", 1)[1].strip())
    return excluded


def _is_excluded_candidate(value, excluded):
    text = str(value or "").strip()
    if not text:
        return False
    if text in excluded:
        return True
    if text.startswith("data:image/") and "," in text:
        return text.split(",", 1)[1].strip() in excluded
    return False


def _push_candidate(candidates, seen, value, source, excluded=None):
    if not value:
        return
    text = str(value).strip()
    if not text or text in seen:
        return
    if _is_excluded_candidate(text, excluded or set()):
        return
    if not (text.startswith("data:image/") or text.startswith("http://") or text.startswith("https://")):
        return
    seen.add(text)
    candidates.append({
        "kind": "data_url" if text.startswith("data:image/") else "url",
        "source": source,
        "value": text,
    })


def _extract_from_text(text, candidates, seen, source, excluded=None):
    value = str(text or "")
    for match in re.finditer(r"data:image/[a-z0-9.+-]+;base64,[A-Za-z0-9+/=_-]+", value, re.I):
        _push_candidate(candidates, seen, match.group(0), source, excluded)

    for match in re.finditer(r"!\[[^\]]*\]\(([^)\s]+)\)", value, re.I):
        _push_candidate(candidates, seen, match.group(1), source, excluded)

    urls = []
    for match in re.finditer(r"https?://[^\s)<>'\"]+", value, re.I):
        url = match.group(0).rstrip(".,;:!?)]")
        urls.append(url)
        if re.search(r"\.(png|jpe?g|webp|gif|bmp)(\?|$)", url, re.I):
            _push_candidate(candidates, seen, url, source, excluded)

    if not candidates and urls:
        _push_candidate(candidates, seen, urls[-1], source, excluded)


def _maybe_data_url_from_base64(value, mime="image/png"):
    text = re.sub(r"\s+", "", str(value or ""))
    if len(text) < 128:
        return None
    if not re.match(r"^[A-Za-z0-9+/=_-]+$", text):
        return None
    return f"data:{mime};base64,{text}"


def _walk_for_images(value, candidates, seen, source="response", excluded=None):
    if isinstance(value, str):
        _extract_from_text(value, candidates, seen, source, excluded)
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _walk_for_images(item, candidates, seen, f"{source}[{index}]", excluded)
        return
    if not isinstance(value, dict):
        return

    image_url = value.get("image_url")
    if isinstance(image_url, dict):
        _push_candidate(candidates, seen, image_url.get("url"), f"{source}.image_url.url", excluded)
    elif isinstance(image_url, str):
        _push_candidate(candidates, seen, image_url, f"{source}.image_url", excluded)

    for key in ("url", "output_url"):
        if isinstance(value.get(key), str):
            _push_candidate(candidates, seen, value[key], f"{source}.{key}", excluded)

    for key in ("b64_json", "base64", "image_base64"):
        if isinstance(value.get(key), str):
            data_url = value[key] if value[key].startswith("data:image/") else _maybe_data_url_from_base64(value[key])
            _push_candidate(candidates, seen, data_url, f"{source}.{key}", excluded)

    inline_data = value.get("inline_data") or value.get("inlineData")
    if isinstance(inline_data, dict) and inline_data.get("data"):
        mime = inline_data.get("mime_type") or inline_data.get("mimeType") or "image/png"
        data_url = _maybe_data_url_from_base64(inline_data.get("data"), mime)
        _push_candidate(candidates, seen, data_url, f"{source}.inline_data", excluded)

    for key, item in value.items():
        _walk_for_images(item, candidates, seen, f"{source}.{key}", excluded)


def extract_image_candidates(response_payload, exclude_values=None):
    candidates = []
    seen = set()
    excluded = _candidate_exclusion_set(exclude_values)
    _walk_for_images(response_payload, candidates, seen, excluded=excluded)
    content_text = response_payload.get("content_text") if isinstance(response_payload, dict) else ""
    if content_text:
        _extract_from_text(content_text, candidates, seen, "content_text", excluded)
    return candidates


def _image_bytes_from_data_url(data_url):
    match = re.match(r"^data:image/[^;]+;base64,(.+)$", str(data_url or ""), re.I | re.S)
    if not match:
        raise ValueError("Invalid image data URL")
    encoded = re.sub(r"\s+", "", match.group(1))
    padding = "=" * (-len(encoded) % 4)
    if "-" in encoded or "_" in encoded:
        return base64.urlsafe_b64decode(encoded + padding)
    return base64.b64decode(encoded + padding)


def _image_bytes_from_url(url, api_key):
    headers = {
        "User-Agent": "ComfyUI-Lingsi-MindAPI-Node/1.0",
        "Accept": "image/*,*/*;q=0.8",
    }
    request = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        if exc.code not in (401, 403):
            raise
        headers["Authorization"] = f"Bearer {api_key}"
        request = urllib.request.Request(url, headers=headers, method="GET")
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            return response.read()


def image_bytes_from_candidate(candidate, api_key):
    value = candidate["value"]
    if candidate["kind"] == "data_url":
        return _image_bytes_from_data_url(value)
    return _image_bytes_from_url(value, api_key)


def tensor_to_data_url(image):
    import numpy as np
    from PIL import Image

    frame = image
    if hasattr(frame, "detach"):
        frame = frame.detach().cpu().numpy()
    if getattr(frame, "ndim", 0) == 4:
        frame = frame[0]
    if getattr(frame, "ndim", 0) != 3:
        raise ValueError("Reference image must be a ComfyUI IMAGE tensor")

    array = np.clip(frame, 0.0, 1.0)
    array = (array * 255.0).round().astype(np.uint8)
    if array.shape[-1] == 1:
        array = np.repeat(array, 3, axis=-1)
    if array.shape[-1] == 4:
        mode = "RGBA"
    else:
        array = array[:, :, :3]
        mode = "RGB"

    pil_image = Image.fromarray(array, mode=mode)
    buffer = io.BytesIO()
    pil_image.save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def tensor_to_base64_png(image):
    return base64.b64encode(tensor_to_png_bytes(image)).decode("ascii")


def tensor_to_png_bytes(image):
    import numpy as np
    from PIL import Image

    frame = image
    if hasattr(frame, "detach"):
        frame = frame.detach().cpu().numpy()
    if getattr(frame, "ndim", 0) == 4:
        frame = frame[0]
    if getattr(frame, "ndim", 0) != 3:
        raise ValueError("Reference image must be a ComfyUI IMAGE tensor")

    array = np.clip(frame, 0.0, 1.0)
    array = (array * 255.0).round().astype(np.uint8)
    if array.shape[0] in (1, 3, 4) and array.shape[-1] not in (1, 3, 4):
        array = np.transpose(array, (1, 2, 0))
    if array.shape[-1] == 1:
        array = np.repeat(array, 3, axis=-1)
    if array.shape[-1] == 4:
        mode = "RGBA"
    else:
        array = array[:, :, :3]
        mode = "RGB"

    pil_image = Image.fromarray(array, mode=mode)
    buffer = io.BytesIO()
    pil_image.save(buffer, format="PNG")
    return buffer.getvalue()


def image_bytes_to_tensor(image_bytes):
    tensor, _original_size, _final_size, _resized = image_bytes_to_tensor_info(image_bytes)
    return tensor


def image_bytes_to_tensor_info(image_bytes):
    import numpy as np
    import torch
    from PIL import Image, ImageOps

    with Image.open(io.BytesIO(image_bytes)) as pil_image:
        pil_image = ImageOps.exif_transpose(pil_image).convert("RGB")
        original_size = pil_image.size
        resized = False
        final_size = pil_image.size
        array = np.asarray(pil_image).astype(np.float32) / 255.0
    return torch.from_numpy(array)[None,], original_size, final_size, resized


def concat_image_tensors(tensors):
    import torch

    return torch.cat(tensors, dim=0)


def _candidate_debug(candidate):
    value = candidate.get("value", "")
    if isinstance(value, str) and value.startswith("data:image/"):
        value = _data_url_summary(value)
    return {
        "kind": candidate.get("kind"),
        "source": candidate.get("source"),
        "value": value,
    }


def _debug_package(
    ok,
    model,
    requested_resolution,
    effective_resolution,
    aspect_ratio,
    has_input_image,
    request_body,
    endpoint=CHAT_ENDPOINT,
    route=None,
    request_summary=None,
    requested_size=None,
    upstream_size=None,
    output_target_size=None,
    requested_count=1,
    generated_count=0,
    response_payload=None,
    parsed_images=None,
    selected_image=None,
    skipped_images=None,
    responses=None,
    error=None,
):
    package = {
        "ok": ok,
        "endpoint": endpoint,
        "request": request_summary or {
            "headers": _masked_headers("application/json"),
            "body": _sanitize_debug_value(request_body),
        },
        "model": model,
        "effective_model": model,
        "requested_resolution": requested_resolution,
        "effective_resolution": effective_resolution,
        "aspect_ratio": aspect_ratio,
        "has_input_image": bool(has_input_image),
        "requested_size": requested_size,
        "upstream_size": upstream_size,
        "output_target_size": output_target_size,
        "requested_count": requested_count,
        "generated_count": generated_count,
        "parsed_images": [_candidate_debug(item) for item in (parsed_images or [])],
        "selected_image": _candidate_debug(selected_image) if selected_image else None,
        "skipped_images": skipped_images or [],
        "responses": responses or [],
        "error": error,
    }
    if route:
        package["route"] = route
    if response_payload is not None:
        package["raw_response"] = _sanitize_debug_value(response_payload)
    return package


class kkLingsiNativePromptImage:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "api_key": ("STRING", {"default": "", "multiline": False}),
                "prompt": ("STRING", {"default": "", "multiline": True}),
                "model": (MODELS, {"default": "gpt-image-2"}),
                "aspect_ratio": (ASPECT_RATIOS, {"default": "auto"}),
                "resolution": (RESOLUTIONS, {"default": "1K"}),
                "count": ("INT", {"default": 1, "min": 1, "max": 12, "step": 1}),
            },
            "optional": {
                "image": ("IMAGE",),
            },
        }

    RETURN_TYPES = ("IMAGE", "STRING")
    RETURN_NAMES = ("image", "raw_json")
    FUNCTION = "generate"
    CATEGORY = "🌟kktools/AI生图"

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return time.time()

    def generate(self, api_key, prompt, model, aspect_ratio, resolution, count=1, image=None):
        api_key = str(api_key or "").strip()
        prompt = str(prompt or "").strip()
        model = str(model or "").strip()
        aspect_ratio = str(aspect_ratio or "auto").strip()
        resolution = str(resolution or "1K").strip().upper()
        count = max(1, min(12, int(count or 1)))

        if not api_key:
            raise RuntimeError("api_key is required")
        if not prompt:
            raise RuntimeError("prompt is required")
        if model not in MODELS:
            raise RuntimeError(f"Unsupported model: {model}")
        if aspect_ratio not in ASPECT_RATIOS:
            raise RuntimeError(f"Unsupported aspect_ratio: {aspect_ratio}")
        if resolution not in RESOLUTIONS:
            raise RuntimeError(f"Unsupported resolution: {resolution}")

        has_input_image = image is not None
        is_gpt_image = is_gpt_image_model(model)
        is_banana = is_banana_model(model)
        effective_resolution = effective_resolution_for_model(model, resolution)
        endpoint = CHAT_ENDPOINT
        route = "/chat/completions"
        request_body = None
        request_summary = None
        request_stream = False
        multipart_fields = None
        multipart_files = None
        requested_size = None
        upstream_size = None
        output_target_size = None
        candidate_exclude_values = []
        reference_image_bytes = None
        skipped_input_images = []

        if is_gpt_image:
            # GPT image uses the exact size selected by aspect ratio and resolution.
            if aspect_ratio != "auto":
                requested_size = GPT_IMAGE_SIZE_TABLE.get((aspect_ratio, effective_resolution))
                if not requested_size:
                    raise RuntimeError(
                        f"Unsupported gpt-image-2 size mapping: aspect_ratio={aspect_ratio}, "
                        f"resolution={effective_resolution}"
                    )
            elif has_input_image:
                requested_size = size_from_image(image)

            if requested_size:
                upstream_size = requested_size

            if has_input_image:
                endpoint = IMAGE_EDITS_ENDPOINT
                route = "/images/edits"
                image_png = tensor_to_png_bytes(image)
                reference_image_bytes = image_png
                multipart_fields = {
                    "model": model,
                    "prompt": prompt,
                    "n": "1",
                }
                if upstream_size:
                    multipart_fields["size"] = upstream_size
                multipart_files = [("image", "image_0.png", "image/png", image_png)]
                request_body = dict(multipart_fields)
                request_summary = {
                    "headers": _masked_headers("multipart/form-data; boundary=<generated>"),
                    "form": {
                        **multipart_fields,
                        "image": {
                            "filename": "image_0.png",
                            "content_type": "image/png",
                            "bytes": len(image_png),
                        },
                    },
                }
            else:
                endpoint = IMAGE_GENERATIONS_ENDPOINT
                route = "/images/generations"
                request_body = {
                    "model": model,
                    "prompt": prompt,
                    "n": count,
                }
                if upstream_size:
                    request_body["size"] = upstream_size
                request_summary = {
                    "headers": _masked_headers("application/json"),
                    "body": _sanitize_debug_value(request_body),
                }
        elif is_banana:
            endpoint = BANANA_GENERATE_ENDPOINT
            route = "/pt/v1/api/generate"
            reference_image_base64 = tensor_to_base64_png(image) if has_input_image else None
            reference_data_url = (
                f"data:image/png;base64,{reference_image_base64}"
                if reference_image_base64
                else None
            )
            if reference_image_base64:
                candidate_exclude_values.append(reference_image_base64)
            if reference_data_url:
                candidate_exclude_values.append(reference_data_url)
                reference_image_bytes = _image_bytes_from_data_url(reference_data_url)
            request_body = build_banana_request_body(
                model=model,
                prompt=prompt,
                aspect_ratio=aspect_ratio,
                resolution=resolution,
                image_base64=reference_image_base64,
            )
            request_summary = {
                "headers": _masked_headers("application/json"),
                "body": _sanitize_debug_value(request_body),
            }
        else:
            reference_data_url = tensor_to_data_url(image) if has_input_image else None
            if reference_data_url:
                candidate_exclude_values.append(reference_data_url)
                reference_image_bytes = _image_bytes_from_data_url(reference_data_url)
            request_body, effective_resolution, _size = build_request_body(
                model=model,
                prompt=prompt,
                aspect_ratio=aspect_ratio,
                resolution=resolution,
                reference_data_url=reference_data_url,
                count=count,
            )
            request_stream = bool(request_body.get("stream"))
            request_summary = {
                "headers": _masked_headers(
                    "application/json",
                    "text/event-stream" if request_stream else "application/json",
                ),
                "body": _sanitize_debug_value(request_body),
            }

        response_payload = None
        candidates = []
        debug = None
        output_tensors = []
        response_items = []
        # Banana and GPT image edits use one request per image; GPT image generations can ask upstream for count.
        loop_count = count if (is_banana or (is_gpt_image and has_input_image)) else 1

        print(
            f"[Lingsi] model={model} route={route} aspect_ratio={aspect_ratio} "
            f"resolution={resolution} eff_resolution={effective_resolution} "
            f"requested_size={requested_size} upstream_size={upstream_size} "
            f"output_target={output_target_size} count={count} "
            f"has_image={has_input_image}"
        )

        try:
            for index in range(loop_count):
                if len(output_tensors) >= count:
                    break
                print(
                    f"[Lingsi] iter {index + 1}/{loop_count} route={route} "
                    f"collected={len(output_tensors)}/{count}"
                )
                if is_gpt_image and has_input_image:
                    response_payload = _http_post_multipart(
                        api_key=api_key,
                        endpoint=endpoint,
                        fields=multipart_fields,
                        files=multipart_files,
                    )
                else:
                    response_payload = _http_post_json(
                        api_key=api_key,
                        body=request_body,
                        stream=request_stream,
                        endpoint=endpoint,
                    )
                candidates = extract_image_candidates(
                    response_payload,
                    exclude_values=candidate_exclude_values,
                )
                print(f"[Lingsi] got {len(candidates)} image candidate(s)")

                collected_in_response = 0
                image_fetch_attempts = []
                for candidate in candidates:
                    attempts = []
                    try:
                        image_bytes = image_bytes_from_candidate(candidate, api_key)
                        if reference_image_bytes and image_bytes == reference_image_bytes:
                            skipped = _candidate_debug(candidate)
                            skipped["reason"] = "matches_input_image"
                            skipped_input_images.append(skipped)
                            attempts.append({
                                "candidate": _candidate_debug(candidate),
                                "skipped": "matches_input_image",
                            })
                            image_fetch_attempts.extend(attempts)
                            continue
                        image_tensor, original_size, final_size, resized = image_bytes_to_tensor_info(image_bytes)
                        output_tensors.append(image_tensor)
                        response_items.append({
                            "index": len(output_tensors),
                            "raw_response": _sanitize_debug_value(response_payload),
                            "parsed_images": [_candidate_debug(item) for item in candidates],
                            "selected_image": _candidate_debug(candidate),
                            "original_size": {"width": original_size[0], "height": original_size[1]},
                            "output_size": {"width": final_size[0], "height": final_size[1]},
                            "resized_to_batch": resized,
                            "image_fetch_attempts": attempts,
                        })
                        collected_in_response += 1
                        # 收够 count 张就停
                        if len(output_tensors) >= count:
                            break
                    except Exception as exc:
                        attempts.append({
                            "candidate": _candidate_debug(candidate),
                            "error": str(exc),
                        })
                        image_fetch_attempts.extend(attempts)

                if collected_in_response == 0:
                    debug = _debug_package(
                        ok=False,
                        model=model,
                        requested_resolution=resolution,
                        effective_resolution=effective_resolution,
                        aspect_ratio=aspect_ratio,
                        has_input_image=has_input_image,
                        request_body=request_body,
                        endpoint=endpoint,
                        route=route,
                        request_summary=request_summary,
                        requested_size=requested_size,
                        upstream_size=upstream_size,
                        output_target_size=output_target_size,
                        requested_count=count,
                        generated_count=len(output_tensors),
                        response_payload=response_payload,
                        parsed_images=candidates,
                        skipped_images=skipped_input_images,
                        responses=response_items,
                        error=f"No usable image was found in MindAPI response #{index + 1}.",
                    )
                    debug["image_fetch_attempts"] = image_fetch_attempts
                    raise RuntimeError(_json_dumps(debug))

            print(f"[Lingsi] done, collected {len(output_tensors)} image(s)")

            output_sizes = {
                (item["output_size"]["width"], item["output_size"]["height"])
                for item in response_items
            }
            if len(output_sizes) > 1:
                debug = _debug_package(
                    ok=False,
                    model=model,
                    requested_resolution=resolution,
                    effective_resolution=effective_resolution,
                    aspect_ratio=aspect_ratio,
                    has_input_image=has_input_image,
                    request_body=request_body,
                    endpoint=endpoint,
                    route=route,
                    request_summary=request_summary,
                    requested_size=requested_size,
                    upstream_size=upstream_size,
                    output_target_size=output_target_size,
                    requested_count=count,
                    generated_count=len(output_tensors),
                    response_payload=response_payload,
                    parsed_images=candidates,
                    skipped_images=skipped_input_images,
                    responses=response_items,
                    error="API returned images with mismatched sizes; local resize is disabled",
                )
                debug["returned_sizes"] = [
                    {
                        "index": item["index"],
                        "width": item["output_size"]["width"],
                        "height": item["output_size"]["height"],
                    }
                    for item in response_items
                ]
                raise RuntimeError(_json_dumps(debug))

            image_batch = concat_image_tensors(output_tensors)
            debug = _debug_package(
                ok=True,
                model=model,
                requested_resolution=resolution,
                effective_resolution=effective_resolution,
                aspect_ratio=aspect_ratio,
                has_input_image=has_input_image,
                request_body=request_body,
                endpoint=endpoint,
                route=route,
                request_summary=request_summary,
                requested_size=requested_size,
                upstream_size=upstream_size,
                output_target_size=output_target_size,
                requested_count=count,
                generated_count=len(output_tensors),
                parsed_images=candidates,
                selected_image=response_items[0]["selected_image"] if response_items else None,
                skipped_images=skipped_input_images,
                responses=response_items,
            )
            return image_batch, _json_dumps(debug)
        except MindAPIHttpError as exc:
            debug = _debug_package(
                ok=False,
                model=model,
                requested_resolution=resolution,
                effective_resolution=effective_resolution,
                aspect_ratio=aspect_ratio,
                has_input_image=has_input_image,
                request_body=request_body,
                endpoint=endpoint,
                route=route,
                request_summary=request_summary,
                requested_size=requested_size,
                upstream_size=upstream_size,
                output_target_size=output_target_size,
                requested_count=count,
                generated_count=len(output_tensors),
                response_payload={"status": exc.status, "body": exc.body},
                parsed_images=candidates,
                skipped_images=skipped_input_images,
                responses=response_items,
                error=str(exc),
            )
            debug["http_attempts"] = _sanitize_debug_value(exc.attempts)
            raise RuntimeError(_json_dumps(debug)) from exc
        except MindAPINetworkError as exc:
            debug = _debug_package(
                ok=False,
                model=model,
                requested_resolution=resolution,
                effective_resolution=effective_resolution,
                aspect_ratio=aspect_ratio,
                has_input_image=has_input_image,
                request_body=request_body,
                endpoint=endpoint,
                route=route,
                request_summary=request_summary,
                requested_size=requested_size,
                upstream_size=upstream_size,
                output_target_size=output_target_size,
                requested_count=count,
                generated_count=len(output_tensors),
                response_payload=response_payload,
                parsed_images=candidates,
                skipped_images=skipped_input_images,
                responses=response_items,
                error=str(exc),
            )
            debug["network_attempts"] = exc.attempts
            raise RuntimeError(_json_dumps(debug)) from exc
        except Exception as exc:
            if debug is not None:
                raise
            debug = _debug_package(
                ok=False,
                model=model,
                requested_resolution=resolution,
                effective_resolution=effective_resolution,
                aspect_ratio=aspect_ratio,
                has_input_image=has_input_image,
                request_body=request_body,
                endpoint=endpoint,
                route=route,
                request_summary=request_summary,
                requested_size=requested_size,
                upstream_size=upstream_size,
                output_target_size=output_target_size,
                requested_count=count,
                generated_count=len(output_tensors),
                response_payload=response_payload,
                parsed_images=candidates,
                skipped_images=skipped_input_images,
                responses=response_items,
                error=str(exc),
            )
            if hasattr(exc, "attempts"):
                debug["network_attempts"] = exc.attempts
            raise RuntimeError(_json_dumps(debug)) from exc


class kkimage2_灵思API(kkLingsiNativePromptImage):
    pass


NODE_CLASS_MAPPINGS = {
    "kkLingsiNativePromptImage": kkLingsiNativePromptImage,
    "kkimage2_灵思API": kkimage2_灵思API,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "kkLingsiNativePromptImage": "kkLingsiNativePromptImage（灵思原生Prompt生图）",
    "kkimage2_灵思API": "kkimage2_灵思API",
}
