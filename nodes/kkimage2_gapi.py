"""ComfyUI 自定义节点 —— 移植自 pages/gapi-image (GAPI Vision)。

- 默认「代理」留空时不走系统/环境 HTTP(S) 代理，避免错误代理污染请求。
- 「代理」字段可填 http://127.0.0.1:7890 手动代理。
- 「代理」字段也可填 system / env / 系统代理，改用系统环境代理。
- 图生图支持批次，并可压缩上传参考图，降低 4K 图生图被远端 60 秒网关断开的概率。
"""

import base64
import io
import json
import os
import time

import numpy as np
import requests
import torch
from PIL import Image


GAPI_ENDPOINT_DEFAULT = "https://api.gapi.cc"
GAPI_DEFAULT_MODEL = "gpt-image-2-plus"
GAPI_OPTIMIZER_MODEL = "gpt-5.5"
GAPI_REQUEST_TIMEOUT = 300
GAPI_OPTIMIZER_TIMEOUT = 300
GAPI_MAX_PIXELS = 8_294_400
GAPI_DEFAULT_RETRIES = 1
GAPI_DEFAULT_CONNECT_TIMEOUT = 30
GAPI_DEFAULT_REFERENCE_MAX_EDGE = 1536



MODELS = ["gpt-image-2-plus", "gpt-image-2", "gpt-image-1", "dall-e-3"]
RATIOS = ["1:1", "3:2", "2:3", "16:9", "9:16", "4:3", "3:4", "21:9", "auto"]
RESOLUTIONS = ["1K", "2K", "4K"]
FORMAT_LABELS = ["png", "jpeg", "webp"]

QUALITY_LABELS = ["自适应", "高画质", "中画质", "低画质"]
QUALITY_TO_API = {"自适应": "auto", "高画质": "high", "中画质": "medium", "低画质": "low"}

MODERATION_LABELS = ["自适应", "宽松"]
MODERATION_TO_API = {"自适应": "auto", "宽松": "low"}

STYLE_ORDER = [
    ("不指定", "none"),
    ("商业摄影", "commercial"),
    ("小红书风", "xhs"),
    ("复古胶片", "film"),
    ("人像大片", "portrait"),
    ("矢量插画", "vector"),
    ("3D 渲染", "3d"),
    ("动漫插画", "anime"),
    ("油画质感", "oil"),
    ("水彩手绘", "watercolor"),
    ("概念美术", "concept"),
    ("赛博朋克", "cyberpunk"),
    ("极简海报", "poster"),
    ("电商主图", "product"),
]
STYLE_LABELS = [label for label, _ in STYLE_ORDER]
STYLE_LABEL_TO_ID = {label: sid for label, sid in STYLE_ORDER}

STYLE_KEYWORDS = {
    "none": "",
    "commercial": "professional commercial photography, sharp focus, soft studio lighting, premium product feel, high detail, magazine quality",
    "xhs": "lifestyle photography, soft warm natural light, pastel tones, minimalist aesthetic, vlog style, premium clean composition",
    "film": "vintage film photography, kodak portra 400, grainy texture, muted faded colors, nostalgic mood, 35mm look",
    "portrait": "editorial portrait, cinematic lighting, shallow depth of field, vogue magazine cover composition, refined fashion styling",
    "vector": "flat vector illustration, clean line work, minimal palette, geometric shapes, modern editorial design",
    "3d": "3d render, octane render, photorealistic textures, soft global illumination, studio backdrop, subtle reflections",
    "anime": "anime illustration, cel-shaded coloring, expressive character design, vibrant atmospheric lighting, studio quality",
    "oil": "oil painting, rich textured brush strokes, classical composition, dramatic chiaroscuro lighting, museum quality",
    "watercolor": "watercolor illustration, soft washes, organic bleeding edges, gentle pastel palette, hand drawn feel",
    "concept": "concept art, painterly atmosphere, cinematic key visual, epic composition, dramatic mood lighting",
    "cyberpunk": "cyberpunk aesthetic, neon signage, rainy futuristic city, moody dark palette, blade runner vibe",
    "poster": "minimalist poster design, bold typography placement hint, generous negative space, premium brand layout",
    "product": "e-commerce hero shot, clean white seamless background, soft box lighting, product centered, sharp clean details",
}


def parse_aspect(ratio: str) -> float:
    s = (ratio or "").strip()
    if not s:
        return 0.0
    sep = -1
    for i, ch in enumerate(s):
        if ch in (":", "x", "X", "/"):
            sep = i
            break
    if sep <= 0 or sep >= len(s) - 1:
        return 0.0
    try:
        w = float(s[:sep])
        h = float(s[sep + 1:])
    except ValueError:
        return 0.0
    if w <= 0 or h <= 0:
        return 0.0
    return w / h


def edge_from_resolution(res: str) -> int:
    if res == "4K":
        return 3840
    if res == "2K":
        return 2048
    return 1024


def _snap16(v: float) -> int:
    v = max(64.0, min(3840.0, v))
    return int(round(v / 16) * 16)


def size_from_aspect(ratio: str, max_edge: int) -> str:
    asp = parse_aspect(ratio)
    if asp <= 0:
        return ""
    edge = max(64, min(3840, max_edge))
    if asp >= 1.0:
        aw, ah = asp, 1.0
    else:
        aw, ah = 1.0, 1.0 / asp
    long_edge = max(aw, ah)
    scale = edge / long_edge
    w = _snap16(aw * scale)
    h = _snap16(ah * scale)
    if w * h > GAPI_MAX_PIXELS:
        shrink = (GAPI_MAX_PIXELS / (w * h)) ** 0.5
        w = _snap16(w * shrink)
        h = _snap16(h * shrink)
    while w * h > GAPI_MAX_PIXELS and w >= 80 and h >= 80:
        if w >= h:
            w -= 16
        else:
            h -= 16
    return f"{w}x{h}"


def size_for_ratio(ratio: str, resolution: str) -> str:
    t = (ratio or "").strip().lower()
    if not t or t == "auto":
        return "auto"
    edge = edge_from_resolution(resolution)
    comp = size_from_aspect(ratio, edge)
    if comp:
        return comp
    if t == "1:1":
        return "1024x1024"
    if t == "3:2":
        return "1536x1024"
    if t == "2:3":
        return "1024x1536"
    asp = parse_aspect(ratio)
    if asp <= 0:
        return "auto"
    if abs(asp - 1.0) < 0.04:
        return "1024x1024"
    return "1536x1024" if asp > 1.0 else "1024x1536"


def aspect_orientation(ratio: str) -> str:
    if not ratio or ratio == "auto":
        return ""
    a = parse_aspect(ratio)
    if a <= 0:
        return ""
    if abs(a - 1.0) < 0.04:
        return "square"
    if a > 2.0:
        return "ultra-wide cinematic landscape"
    if a > 1.4:
        return "wide landscape"
    if a > 1.0:
        return "landscape"
    if a < 0.5:
        return "ultra-tall vertical portrait"
    if a < 0.72:
        return "tall portrait"
    return "portrait"


def prompt_with_ratio_hint(prompt: str, ratio: str) -> str:
    base = (prompt or "").strip()
    orient = aspect_orientation(ratio)
    if not orient:
        return base
    hint = f"(Aspect ratio: {ratio}, output the image as {orient} composition.)"
    return hint if not base else f"{base}\n\n{hint}"


def build_styled_prompt(prompt: str, style_id: str) -> str:
    base = (prompt or "").strip()
    if not style_id or style_id == "none":
        return base
    kw = STYLE_KEYWORDS.get(style_id, "").strip()
    if not kw:
        return base
    return kw if not base else f"{base}, {kw}"


def build_edit_prompt(prompt: str, ratio: str) -> str:
    return "Use the following text as the complete prompt. Do not rewrite it:\n" + prompt_with_ratio_hint(prompt, ratio)


def _normalize_base(base: str) -> str:
    b = (base or "").strip()
    if not b:
        return GAPI_ENDPOINT_DEFAULT
    return b.rstrip("/")


def url_generate(base: str) -> str:
    b = _normalize_base(base)
    if "/v1/images/generations" in b:
        return b
    if "/v1/images/edits" in b:
        return b[: b.rindex("/v1/images/edits")] + "/v1/images/generations"
    return b + "/v1/images/generations"


def url_edit(base: str) -> str:
    b = _normalize_base(base)
    if "/v1/images/edits" in b:
        return b
    if "/v1/images/generations" in b:
        return b[: b.rindex("/v1/images/generations")] + "/v1/images/edits"
    return b + "/v1/images/edits"


def url_chat(base: str) -> str:
    b = _normalize_base(base)
    if "/v1/chat/completions" in b:
        return b
    if "/v1/images/" in b:
        idx = b.index("/v1/images/")
        return b[:idx] + "/v1/chat/completions"
    return b + "/v1/chat/completions"


def extract_error(raw_text: str) -> str:
    if not raw_text:
        return ""
    try:
        obj = json.loads(raw_text)
    except Exception:
        return raw_text[:200]
    if isinstance(obj, dict):
        err = obj.get("error")
        if isinstance(err, dict):
            msg = err.get("message")
            if isinstance(msg, str):
                return msg
        msg = obj.get("message")
        if isinstance(msg, str):
            return msg
    return raw_text[:200]


def extract_optimized_text(raw_text: str) -> str:
    try:
        obj = json.loads(raw_text)
    except Exception:
        return ""
    choices = obj.get("choices", []) if isinstance(obj, dict) else []
    if not isinstance(choices, list) or not choices:
        return ""
    first = choices[0]
    if not isinstance(first, dict):
        return ""
    msg = first.get("message", {})
    if not isinstance(msg, dict):
        return ""
    content = msg.get("content")
    return content.strip() if isinstance(content, str) else ""


def extract_image_b64_list(raw_text: str) -> list:
    try:
        obj = json.loads(raw_text)
    except Exception:
        return []
    data = obj.get("data", []) if isinstance(obj, dict) else []
    out = []
    if isinstance(data, list):
        for it in data:
            if isinstance(it, dict):
                b64 = it.get("b64_json")
                if isinstance(b64, str) and b64:
                    out.append(b64)
    return out


def b64_to_image_tensor(b64_str: str) -> torch.Tensor:
    raw = base64.b64decode(b64_str)
    img = Image.open(io.BytesIO(raw)).convert("RGB")
    arr = np.asarray(img, dtype=np.float32) / 255.0
    return torch.from_numpy(arr).unsqueeze(0)


def image_tensor_to_png_bytes(tensor: torch.Tensor, max_edge: int = 0) -> bytes:
    """把 ComfyUI IMAGE tensor 转成 PNG bytes。

    max_edge > 0 时会在上传前等比缩小参考图。这样不影响最终 output size，
    但能显著减少图生图上传体积和远端处理时间，尤其是 4K 输出时。
    """
    # ComfyUI IMAGE 通常是 [B, H, W, C]；单张图是 [H, W, C]。
    if hasattr(tensor, "dim") and tensor.dim() == 4:
        tensor = tensor[0]
    arr = (tensor.detach().cpu().numpy() * 255.0).clip(0, 255).astype(np.uint8)
    img = Image.fromarray(arr).convert("RGB")
    try:
        edge = int(max_edge or 0)
    except Exception:
        edge = 0
    if edge > 0:
        w, h = img.size
        long_edge = max(w, h)
        if long_edge > edge:
            scale = edge / float(long_edge)
            nw = max(64, int(round(w * scale)))
            nh = max(64, int(round(h * scale)))
            img = img.resize((nw, nh), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def _stack_batch(tensors: list) -> torch.Tensor:
    if not tensors:
        return torch.zeros((1, 64, 64, 3), dtype=torch.float32)
    shapes = {t.shape for t in tensors}
    if len(shapes) == 1:
        return torch.cat(tensors, dim=0)
    target_h = max(t.shape[1] for t in tensors)
    target_w = max(t.shape[2] for t in tensors)
    padded = []
    for t in tensors:
        h, w = t.shape[1], t.shape[2]
        if h == target_h and w == target_w:
            padded.append(t)
            continue
        pad = torch.zeros((1, target_h, target_w, t.shape[3]), dtype=t.dtype)
        pad[:, :h, :w, :] = t
        padded.append(pad)
    return torch.cat(padded, dim=0)


def _resolve_key(api_key: str) -> str:
    k = (api_key or "").strip()
    if not k:
        k = os.environ.get("GAPI_API_KEY", "").strip()
    return k


def _timeout_seconds(value, default: int = GAPI_REQUEST_TIMEOUT) -> int:
    """把节点里的超时时间转换为 requests 可用的秒数。

    默认 300 秒（5 分钟）；为了避免误填 0 或负数导致立刻失败，最小按 1 秒处理。
    """
    try:
        seconds = int(value)
    except Exception:
        seconds = int(default)
    return max(1, seconds)


def _retry_count(value, default: int = GAPI_DEFAULT_RETRIES) -> int:
    """网络断连/临时 HTTP 错误的重试次数，避免偶发 RemoteDisconnected 直接失败。"""
    try:
        n = int(value)
    except Exception:
        n = int(default)
    return max(0, min(5, n))


def _int_range(value, default: int, min_value: int, max_value: int) -> int:
    try:
        n = int(value)
    except Exception:
        n = int(default)
    return max(min_value, min(max_value, n))


def _proxy_config(proxy: str):
    """返回 (proxies, trust_env, mode_label)。

    - 留空：不走代理，也不读取系统 HTTP(S)_PROXY。
    - system/env/系统代理：读取系统环境代理。
    - http://127.0.0.1:7890：手动指定代理。
    """
    p = (proxy or "").strip()
    if not p:
        return {"http": None, "https": None}, False, "不走代理"
    if p.lower() in {"system", "env", "auto", "系统代理", "使用系统代理"}:
        return None, True, "系统代理"
    return {"http": p, "https": p}, False, "手动代理"


def _request_fail_hint(e: Exception) -> str:
    msg = str(e)
    if "RemoteDisconnected" in msg or "Remote end closed connection" in msg or "Connection aborted" in msg:
        return (
            "远端服务器/中间网关主动断开连接。若总是在约 60 秒左右失败，通常不是本地节点超时，"
            "而是接口网关有 60 秒限制；建议图生图先降到 2K 或 1K，减少批次数/参考图数量，"
            "或更换支持长请求的接口地址。"
        )
    if isinstance(e, requests.exceptions.ReadTimeout):
        return "读取响应超时。可把「超时时间(秒)」调大，或降低分辨率/批次数。"
    if isinstance(e, requests.exceptions.ConnectTimeout):
        return (
            "连接接口超时，说明请求还没进入生图阶段。若你在国内网络，节点「代理」留空会强制不走代理；"
            "请在「代理」里填 http://127.0.0.1:7890，或填 system 使用系统环境代理。"
        )
    return "请检查接口地址、网络、代理或 API 服务状态；国内网络优先检查代理。"


def _image_batch_len(batch) -> int:
    if batch is None:
        return 0
    try:
        if hasattr(batch, "dim") and batch.dim() >= 4:
            return int(batch.shape[0])
        if hasattr(batch, "ndim") and batch.ndim >= 4:
            return int(batch.shape[0])
    except Exception:
        pass
    return 1


def _select_batch_image(batch, index: int) -> torch.Tensor:
    """从 ComfyUI IMAGE 批次里取第 index 张；短批次会复用最后一张。"""
    if batch is None:
        raise RuntimeError("参考图为空")
    if hasattr(batch, "dim") and batch.dim() >= 4:
        n = int(batch.shape[0])
        if n <= 0:
            raise RuntimeError("参考图批次为空")
        return batch[min(index, n - 1)]
    if hasattr(batch, "ndim") and batch.ndim >= 4:
        n = int(batch.shape[0])
        if n <= 0:
            raise RuntimeError("参考图批次为空")
        return batch[min(index, n - 1)]
    return batch


def _post(url: str, *, headers: dict, json_body=None, data=None, files=None, timeout: int, proxy: str, retries: int = 0):
    """带轻量重试的 POST。

    - read timeout 使用节点「超时时间(秒)」。
    - connect timeout 固定 30 秒，避免网络不通时卡满 5 分钟。
    - Connection: close 避免复用坏连接。
    - 对 RemoteDisconnected / Timeout / 502/503/504/429 等临时问题自动重试。
    - 代理字段支持：留空=不走代理；system/env/系统代理=系统代理；URL=手动代理。
    """
    req_headers = dict(headers or {})
    req_headers.setdefault("Accept", "application/json")
    req_headers.setdefault("Connection", "close")
    retry_status = {408, 409, 425, 429, 500, 502, 503, 504}
    last_exc = None
    total = max(0, int(retries)) + 1
    proxies, trust_env, _proxy_mode = _proxy_config(proxy)

    for attempt in range(total):
        try:
            with requests.Session() as session:
                session.trust_env = trust_env
                kwargs = dict(
                    url=url,
                    headers=req_headers,
                    json=json_body,
                    data=data,
                    files=files,
                    timeout=(GAPI_DEFAULT_CONNECT_TIMEOUT, timeout),
                )
                if proxies is not None:
                    kwargs["proxies"] = proxies
                resp = session.post(**kwargs)
            if resp.status_code in retry_status and attempt < total - 1:
                resp.close()
                time.sleep(min(8.0, 1.5 * (attempt + 1)))
                continue
            return resp
        except requests.exceptions.ProxyError:
            raise
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            last_exc = e
            if attempt >= total - 1:
                raise
            time.sleep(min(8.0, 1.5 * (attempt + 1)))

    if last_exc is not None:
        raise last_exc
    raise RuntimeError("请求失败：未知错误")


class kkimage2_GAPI:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "提示词": ("STRING", {"multiline": True, "default": ""}),
                "模型": (MODELS, {"default": GAPI_DEFAULT_MODEL}),
                "画幅比例": (RATIOS, {"default": "1:1"}),
                "分辨率": (RESOLUTIONS, {"default": "1K"}),
                "画质": (QUALITY_LABELS, {"default": "自适应"}),
                "风格预设": (STYLE_LABELS, {"default": "不指定"}),
                "生成张数": ("INT", {"default": 1, "min": 1, "max": 8}),
                "输出格式": (FORMAT_LABELS, {"default": "png"}),
                "内容审核": (MODERATION_LABELS, {"default": "自适应"}),
                "API_Key": ("STRING", {"default": "", "multiline": False}),
                "接口地址": ("STRING", {"default": GAPI_ENDPOINT_DEFAULT, "multiline": False}),
                "超时时间(秒)": ("INT", {"default": 300, "min": 1, "max": 3600}),
                "失败重试次数": ("INT", {"default": 1, "min": 0, "max": 5}),
                "参考图上传长边": ("INT", {"default": 1536, "min": 512, "max": 4096}),
            },
            "optional": {
                "参考图1": ("IMAGE",),
                "参考图2": ("IMAGE",),
                "参考图3": ("IMAGE",),
                "参考图4": ("IMAGE",),
                "参考图5": ("IMAGE",),
                "自定义模型": ("STRING", {"default": "", "multiline": False}),
                "代理": ("STRING", {"default": "", "multiline": False, "placeholder": "留空=不走代理；填 http://127.0.0.1:7890 或 system"}),
            },
        }

    RETURN_TYPES = ("IMAGE", "STRING")
    RETURN_NAMES = ("图像", "状态")
    FUNCTION = "run"
    CATEGORY = "🌟kktools/图像"

    def run(self, **kw):
        key = _resolve_key(kw.get("API_Key", ""))
        if not key:
            raise RuntimeError("API Key 为空（可在节点上填写，或设置环境变量 GAPI_API_KEY）")

        prompt = kw.get("提示词", "") or ""
        model = kw.get("模型", GAPI_DEFAULT_MODEL)
        ratio = kw.get("画幅比例", "1:1")
        resolution = kw.get("分辨率", "1K")
        quality_api = QUALITY_TO_API.get(kw.get("画质", "自适应"), "auto")
        style_id = STYLE_LABEL_TO_ID.get(kw.get("风格预设", "不指定"), "none")
        batch_count = int(kw.get("生成张数", 1))
        output_format = kw.get("输出格式", "png")
        moderation_api = MODERATION_TO_API.get(kw.get("内容审核", "自适应"), "auto")
        endpoint = kw.get("接口地址", GAPI_ENDPOINT_DEFAULT)
        custom_model = (kw.get("自定义模型", "") or "").strip()
        proxy = kw.get("代理", "")
        timeout = _timeout_seconds(kw.get("超时时间(秒)", GAPI_REQUEST_TIMEOUT))
        retries = _retry_count(kw.get("失败重试次数", GAPI_DEFAULT_RETRIES))
        ref_max_edge = _int_range(kw.get("参考图上传长边", GAPI_DEFAULT_REFERENCE_MAX_EDGE), GAPI_DEFAULT_REFERENCE_MAX_EDGE, 512, 4096)

        final_model = custom_model or model
        size = size_for_ratio(ratio, resolution)

        refs = [kw.get(f"参考图{i}") for i in range(1, 6)]
        refs = [r for r in refs if r is not None]
        if not refs:
            styled = build_styled_prompt(prompt, style_id)
            final_prompt = prompt_with_ratio_hint(styled, ratio)
            url = url_generate(endpoint)
            body = {
                "model": final_model,
                "prompt": final_prompt,
                "size": size,
                "output_format": output_format,
                "moderation": moderation_api,
                "quality": quality_api,
            }
            headers = {
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            }

            tensors = []
            parts = []
            for i in range(batch_count):
                t0 = time.time()
                try:
                    r = _post(url, headers=headers, json_body=body, timeout=timeout, proxy=proxy, retries=retries)
                except requests.exceptions.ProxyError as e:
                    raise RuntimeError(f"代理连接失败：{e}。可清空「代理」字段或填入可用代理 URL。")
                except requests.exceptions.RequestException as e:
                    raise RuntimeError(f"请求失败：{e}。{_request_fail_hint(e)}")
                took = time.time() - t0
                if r.status_code < 200 or r.status_code >= 300:
                    raise RuntimeError(f"生成失败 HTTP {r.status_code}：{extract_error(r.text)}")
                b64_list = extract_image_b64_list(r.text)
                if not b64_list:
                    raise RuntimeError(f"响应未解析到图像 · {r.text[:200]}")
                for b in b64_list:
                    tensors.append(b64_to_image_tensor(b))
                parts.append(f"第 {i + 1}/{batch_count} 张 {took:.1f}s")

            images = _stack_batch(tensors)
            status = f"已生成 {len(tensors)} 张 · 尺寸 {size} · 模型 {final_model} · 超时 {timeout}s · 重试 {retries} 次 · " + " | ".join(parts)
            return (images, status)

        wrapped = build_edit_prompt(prompt, ratio)
        url = url_edit(endpoint)

        data = {
            "model": final_model,
            "prompt": wrapped,
            "size": size,
            "output_format": output_format,
            "moderation": moderation_api,
        }
        headers = {"Authorization": f"Bearer {key}"}

        batch_total = max(_image_batch_len(r) for r in refs)
        if batch_total <= 0:
            raise RuntimeError("参考图批次为空")

        tensors = []
        parts = []
        for batch_index in range(batch_total):
            files = []
            for idx, batch in enumerate(refs):
                img_tensor = _select_batch_image(batch, batch_index)
                png = image_tensor_to_png_bytes(img_tensor, max_edge=ref_max_edge)
                files.append(("image[]", (f"ref_{idx}_batch_{batch_index}.png", png, "image/png")))

            t0 = time.time()
            try:
                r = _post(url, headers=headers, data=data, files=files, timeout=timeout, proxy=proxy, retries=retries)
            except requests.exceptions.ProxyError as e:
                raise RuntimeError(f"代理连接失败：{e}。可清空「代理」字段或填入可用代理 URL。")
            except requests.exceptions.RequestException as e:
                raise RuntimeError(f"请求失败：{e}。{_request_fail_hint(e)}")
            took = time.time() - t0
            if r.status_code < 200 or r.status_code >= 300:
                raise RuntimeError(f"编辑失败 HTTP {r.status_code}：{extract_error(r.text)}")
            b64_list = extract_image_b64_list(r.text)
            if not b64_list:
                raise RuntimeError(f"响应未解析到图像 · {r.text[:200]}")
            for b in b64_list:
                tensors.append(b64_to_image_tensor(b))
            parts.append(f"批次 {batch_index + 1}/{batch_total} {took:.1f}s")

        status = (
            f"编辑完成 · 输出 {len(tensors)} 张 · 输入批次 {batch_total} · 尺寸 {size} · "
            f"参考图输入 {len(refs)} 组 · 上传长边≤{ref_max_edge}px · 超时 {timeout}s · 重试 {retries} 次 · " + " | ".join(parts)
        )
        return (_stack_batch(tensors), status)


NODE_CLASS_MAPPINGS = {
    "kkimage2_GAPI": kkimage2_GAPI,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "kkimage2_GAPI": "kkimage2_GAPI",
}
