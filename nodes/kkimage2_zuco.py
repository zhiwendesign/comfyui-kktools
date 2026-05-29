"""kktools Zuco Image2 node.

合并 Zuco Image2 Text to Image 与 Image to Image：
- 不接 image：文生图，调用 /v1/images/generations
- 接入 image：图生图，调用 /v1/images/edits
"""

import base64
import io
import os
import time
from pathlib import Path

import numpy as np
import requests
import torch
from PIL import Image

try:
    import certifi
except ImportError:
    certifi = None


ZUCO_MODEL = "gpt-image-2"
ZUCO_BASE_URL = "https://api.zuco.ai/v1"
REQUEST_TIMEOUT_SECONDS = 600
MAX_REFERENCE_PIXELS = 2048 * 2048
SYSTEM_CA_FILE = Path("/etc/ssl/cert.pem")
OUTPUT_FORMATS = ["png", "jpeg", "webp"]
RESOLUTIONS = ["1K", "2K", "4K"]
RESOLUTION_MAX_EDGE = {
    "1K": 1024,
    "2K": 2048,
    "4K": 3840,
}
MIN_OUTPUT_PIXELS = 655_360
MAX_OUTPUT_PIXELS = 8_294_400
SIZE_OPTIONS = [
    "auto",
    "1024x1024",
    "1024x1536",
    "1536x1024",
    "2048x2048",
    "2048x1152",
    "1152x2048",
    "3840x2160",
    "2160x3840",
    "Custom",
]


def _normalize_base_url(base_url: str) -> str:
    base_url = (base_url or ZUCO_BASE_URL).strip().rstrip("/")
    if not base_url:
        return ZUCO_BASE_URL
    if not base_url.endswith("/v1"):
        base_url = f"{base_url}/v1"
    return base_url


def _api_url(base_url: str, path: str) -> str:
    return f"{_normalize_base_url(base_url)}/{path.lstrip('/')}"


def _verify_paths():
    paths = []
    if certifi is not None:
        certifi_path = certifi.where()
        if certifi_path and Path(certifi_path).exists():
            paths.append(certifi_path)
    if SYSTEM_CA_FILE.exists():
        paths.append(str(SYSTEM_CA_FILE))
    paths.append(True)
    return paths


def _resolve_api_key(api_key: str) -> str:
    key = (api_key or "").strip() or os.environ.get("ZUCO_API_KEY", "").strip()
    if not key:
        raise RuntimeError("Zuco API Key 为空（可在节点上填写，或设置环境变量 ZUCO_API_KEY）")
    return key


def _resolve_prompt(prompt: str) -> str:
    prompt = (prompt or "").strip()
    if not prompt:
        raise RuntimeError("Prompt 不能为空")
    return prompt


def _resolve_size(width: int, height: int) -> str:
    try:
        width = int(width)
        height = int(height)
    except Exception:
        raise RuntimeError("width 和 height 必须是整数")
    if width % 16 != 0 or height % 16 != 0:
        raise RuntimeError(f"width 和 height 必须是 16 的倍数，当前为 {width}x{height}")
    if max(width, height) > 3840:
        raise RuntimeError(f"分辨率长边不能超过 3840，当前为 {width}x{height}")
    ratio = max(width, height) / max(1, min(width, height))
    if ratio > 3:
        raise RuntimeError(f"画幅比例不能超过 3:1，当前为 {width}x{height}")
    total_pixels = width * height
    if not MIN_OUTPUT_PIXELS <= total_pixels <= MAX_OUTPUT_PIXELS:
        raise RuntimeError(f"总像素必须在 {MIN_OUTPUT_PIXELS:,} 到 {MAX_OUTPUT_PIXELS:,} 之间，当前为 {total_pixels:,}")
    return f"{width}x{height}"


def _snap16(value: float) -> int:
    return max(256, min(3840, int(round(value / 16) * 16)))


def _size_from_template(size: str, resolution: str) -> str:
    try:
        template_width, template_height = [int(part) for part in size.lower().split("x", 1)]
    except Exception:
        raise RuntimeError(f"不支持的 size: {size}")

    if template_width <= 0 or template_height <= 0:
        raise RuntimeError(f"不支持的 size: {size}")

    max_edge = RESOLUTION_MAX_EDGE.get(str(resolution or "1K").upper(), 1024)
    aspect = template_width / template_height
    if aspect >= 1.0:
        width = _snap16(max_edge)
        height = _snap16(max_edge / aspect)
    else:
        height = _snap16(max_edge)
        width = _snap16(max_edge * aspect)

    pixels = width * height
    if pixels < MIN_OUTPUT_PIXELS:
        scale = (MIN_OUTPUT_PIXELS / pixels) ** 0.5
        width = _snap16(width * scale)
        height = _snap16(height * scale)
    elif pixels > MAX_OUTPUT_PIXELS:
        scale = (MAX_OUTPUT_PIXELS / pixels) ** 0.5
        width = _snap16(width * scale)
        height = _snap16(height * scale)

    while width * height > MAX_OUTPUT_PIXELS and width >= 272 and height >= 272:
        if width >= height:
            width -= 16
        else:
            height -= 16

    while width * height < MIN_OUTPUT_PIXELS and width <= 3824 and height <= 3824:
        if width >= height:
            width += 16
        else:
            height += 16

    return _resolve_size(width, height)


def _resolve_size_option(size: str, resolution: str, custom_width: int, custom_height: int) -> str:
    size = str(size or "auto").strip()
    if size == "auto":
        return "auto"
    if size == "Custom":
        return _resolve_size(custom_width, custom_height)
    if size in SIZE_OPTIONS:
        return _size_from_template(size, resolution)
    raise RuntimeError(f"不支持的 size: {size}")


def _extract_error(response: requests.Response) -> str:
    try:
        payload = response.json()
    except Exception:
        return response.text[:1000] if response.text else response.reason
    error = payload.get("error") if isinstance(payload, dict) else None
    if isinstance(error, dict):
        return error.get("message") or str(error)
    if isinstance(error, str):
        return error
    return str(payload)[:1000]


def _tensor_to_pil(image: torch.Tensor) -> Image.Image:
    image = image.detach().cpu()
    if image.ndim == 4:
        image = image[0]
    array = image.numpy()
    array = np.clip(array * 255.0, 0, 255).astype(np.uint8)
    return Image.fromarray(array).convert("RGB")


def _resize_to_limit(pil_image: Image.Image, max_pixels: int = MAX_REFERENCE_PIXELS) -> Image.Image:
    width, height = pil_image.size
    pixels = width * height
    if pixels <= max_pixels:
        return pil_image
    scale = (max_pixels / pixels) ** 0.5
    new_width = max(1, int(width * scale))
    new_height = max(1, int(height * scale))
    return pil_image.resize((new_width, new_height), Image.Resampling.LANCZOS)


def _image_tensor_to_png_bytes(image: torch.Tensor) -> bytes:
    pil_image = _resize_to_limit(_tensor_to_pil(image))
    buffer = io.BytesIO()
    pil_image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def _mask_tensor_to_png_bytes(mask: torch.Tensor) -> bytes:
    mask = mask.detach().cpu()
    if mask.ndim == 3:
        mask = mask[0]
    alpha = 1.0 - mask.numpy()
    alpha = np.clip(alpha * 255.0, 0, 255).astype(np.uint8)
    rgba = np.zeros((alpha.shape[0], alpha.shape[1], 4), dtype=np.uint8)
    rgba[:, :, 3] = alpha
    pil_mask = _resize_to_limit(Image.fromarray(rgba))
    buffer = io.BytesIO()
    pil_mask.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def _decode_b64_image(b64_json: str) -> torch.Tensor:
    image_bytes = io.BytesIO(base64.b64decode(b64_json))
    image = Image.open(image_bytes).convert("RGB")
    array = np.asarray(image, dtype=np.float32) / 255.0
    return torch.from_numpy(array)


def _download_image(url: str, headers: dict, timeout: int, verify) -> torch.Tensor:
    response = requests.get(url, headers=headers, timeout=timeout, verify=verify)
    if response.status_code < 200 or response.status_code >= 300:
        raise RuntimeError(f"下载结果图失败 HTTP {response.status_code}")
    image = Image.open(io.BytesIO(response.content)).convert("RGB")
    array = np.asarray(image, dtype=np.float32) / 255.0
    return torch.from_numpy(array)


def _response_to_images(payload: dict, headers: dict, timeout: int, verify) -> torch.Tensor:
    data = payload.get("data") or []
    if not data:
        raise RuntimeError("Zuco Image API 返回为空，未解析到图片")
    tensors = []
    for image_data in data:
        if image_data.get("b64_json"):
            tensors.append(_decode_b64_image(image_data["b64_json"]))
        elif image_data.get("url"):
            tensors.append(_download_image(image_data["url"], headers, timeout, verify))
        else:
            raise RuntimeError("图片结果既不包含 b64_json，也不包含 url")
    return torch.stack(tensors, dim=0)


def _post_with_ca_fallback(url: str, *, headers: dict, timeout: int, retries: int = 0, json_body=None, files=None, data=None) -> tuple[dict, str]:
    last_error = None
    retry_statuses = {408, 409, 425, 429, 500, 502, 503, 504}
    total_attempts = max(0, min(5, int(retries or 0))) + 1
    for verify in _verify_paths():
        for attempt in range(total_attempts):
            try:
                response = requests.post(
                    url,
                    headers=headers,
                    json=json_body,
                    files=files,
                    data=data,
                    timeout=timeout,
                    verify=verify,
                )
                if response.status_code in retry_statuses and attempt < total_attempts - 1:
                    time.sleep(min(8.0, 1.5 * (attempt + 1)))
                    continue
                if response.status_code < 200 or response.status_code >= 300:
                    raise RuntimeError(f"Zuco Image API 错误 HTTP {response.status_code}: {_extract_error(response)}")
                return response.json(), str(verify)
            except requests.exceptions.SSLError as exc:
                last_error = exc
                break
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as exc:
                last_error = exc
                if attempt < total_attempts - 1:
                    time.sleep(min(8.0, 1.5 * (attempt + 1)))
                    continue
                raise RuntimeError(f"连接 Zuco Image API 失败：{exc}") from exc
    raise RuntimeError(f"连接 Zuco Image API 失败：{last_error}")


class kkimage2_Zuco:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "api_key": ("STRING", {"default": "", "multiline": False}),
                "prompt": ("STRING", {"default": "", "multiline": True}),
                "size": (SIZE_OPTIONS, {"default": "1024x1024"}),
                "custom_width": ("INT", {"default": 1024, "min": 256, "max": 3840, "step": 16}),
                "custom_height": ("INT", {"default": 1024, "min": 256, "max": 3840, "step": 16}),
                "output_format": (OUTPUT_FORMATS, {"default": "png"}),
                "resolution": (RESOLUTIONS, {"default": "1K"}),
            },
            "optional": {
                "image": ("IMAGE",),
                "mask": ("MASK",),
                "timeout_seconds": ("INT", {"default": REQUEST_TIMEOUT_SECONDS, "min": 1, "max": 3600}),
                "retry_count": ("INT", {"default": 2, "min": 0, "max": 5, "step": 1}),
            },
        }

    RETURN_TYPES = ("IMAGE", "STRING")
    RETURN_NAMES = ("image", "status")
    FUNCTION = "generate"
    CATEGORY = "🌟kktools/AI生图"

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return float("nan")

    def generate(
        self,
        api_key,
        prompt,
        size="1024x1024",
        custom_width=1024,
        custom_height=1024,
        output_format="png",
        resolution="1K",
        image=None,
        mask=None,
        timeout_seconds=REQUEST_TIMEOUT_SECONDS,
        retry_count=2,
    ):
        key = _resolve_api_key(api_key)
        prompt = _resolve_prompt(prompt)
        size = _resolve_size_option(size, resolution, custom_width, custom_height)
        timeout = max(1, int(timeout_seconds or REQUEST_TIMEOUT_SECONDS))
        headers = {
            "Authorization": f"Bearer {key}",
            "Accept": "application/json",
        }

        if image is None:
            payload = {
                "model": ZUCO_MODEL,
                "prompt": prompt,
                "size": size,
                "output_format": output_format,
            }
            payload_response, verify_used = _post_with_ca_fallback(
                _api_url(ZUCO_BASE_URL, "/images/generations"),
                headers=headers,
                json_body=payload,
                timeout=timeout,
                retries=retry_count,
            )
            images = _response_to_images(payload_response, headers, timeout, verify_used)
            return (images, f"Zuco 文生图完成 · 输出 {images.shape[0]} 张 · 尺寸 {size} · 模型 {ZUCO_MODEL}")

        if mask is not None:
            if image.shape[0] != 1:
                raise RuntimeError("mask 只能和单张 image 一起使用")
            if tuple(mask.shape[-2:]) != tuple(image.shape[1:3]):
                raise RuntimeError("mask 和 image 的宽高必须一致")

        batch_size = int(image.shape[0]) if hasattr(image, "shape") and len(image.shape) == 4 else 1
        files = []
        for index in range(batch_size):
            image_bytes = _image_tensor_to_png_bytes(image[index : index + 1] if batch_size > 1 else image)
            field_name = "image" if batch_size == 1 else "image[]"
            files.append((field_name, (f"image_{index}.png", image_bytes, "image/png")))
        if mask is not None:
            files.append(("mask", ("mask.png", _mask_tensor_to_png_bytes(mask), "image/png")))

        data = {
            "model": ZUCO_MODEL,
            "prompt": prompt,
            "size": size,
            "output_format": output_format,
        }
        payload_response, verify_used = _post_with_ca_fallback(
            _api_url(ZUCO_BASE_URL, "/images/edits"),
            headers=headers,
            data=data,
            files=files,
            timeout=timeout,
            retries=retry_count,
        )
        images = _response_to_images(payload_response, headers, timeout, verify_used)
        return (images, f"Zuco 图生图完成 · 输出 {images.shape[0]} 张 · 输入 {batch_size} 张 · 尺寸 {size} · 模型 {ZUCO_MODEL}")


NODE_CLASS_MAPPINGS = {
    "kkimage2_Zuco": kkimage2_Zuco,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "kkimage2_Zuco": "kkimage2_Zuco",
}

__all__ = ["kkimage2_Zuco"]
