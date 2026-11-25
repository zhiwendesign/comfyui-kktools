"""MiniCPM workflows using configurable Ollama or llama.cpp services."""
from __future__ import annotations

import base64
import io
import json
import math
import re
from pathlib import Path, PureWindowsPath
from urllib.parse import urlsplit

import numpy as np
import requests
from PIL import Image
import torch


_CATEGORY = "🌟kktools/MiniCPM"
_CONNECTION = "KK_MINICPM_CONNECTION"
_MODELS = ["openbmb/minicpm-v4.7:35b-a3b", "minicpm-v4.5:latest", "openbmb/minicpm5-2b:q8_0", "自定义"]
_VISION_MODEL = _MODELS[0]
_VIDEO_MODEL = _MODELS[1]
_TEXT_MODEL = _MODELS[2]
def _check_interrupt():
    # ComfyUI's interruption flag is checked between batch items, not during an HTTP request.
    try:
        import comfy.model_management
    except ImportError:
        return
    comfy.model_management.throw_exception_if_processing_interrupted()


def _local_url(url):
    parsed = urlsplit(str(url).strip())
    if (parsed.scheme not in {"http", "https"} or not parsed.hostname
            or parsed.username is not None or parsed.password is not None
            or parsed.query or parsed.fragment):
        raise ValueError("服务地址须为 HTTP 或 HTTPS 基础地址，不能包含账号、密码、查询参数或片段。")
    try:
        parsed.port
    except ValueError as exc:
        raise ValueError("服务地址端口无效。") from exc
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path.rstrip('/')}"


def _request(connection, endpoint, payload, check_interrupt=True):
    if check_interrupt:
        _check_interrupt()
    url = _local_url(connection["url"]) + endpoint
    try:
        # Connect to the exact configured service, not a proxy or redirected host.
        with requests.Session() as session:
            session.trust_env = False
            response = session.post(url, json=payload, timeout=connection["timeout"], allow_redirects=False)
        if not 200 <= response.status_code < 300:
            try:
                detail = response.json().get("error", response.text)
            except (ValueError, AttributeError):
                detail = response.text
            raise RuntimeError(f"模型服务请求失败 (HTTP {response.status_code}): {str(detail)[:1000]}")
        data = response.json()
    except requests.exceptions.Timeout as exc:
        raise RuntimeError("模型服务请求超时；请检查模型加载状态或增加 Loader 的超时时间。") from exc
    except requests.exceptions.ConnectionError as exc:
        raise RuntimeError("无法连接模型服务；请确认所选服务已启动且地址正确。") from exc
    except requests.exceptions.RequestException as exc:
        raise RuntimeError(f"模型服务请求失败: {exc}") from exc
    if not isinstance(data, dict):
        raise RuntimeError("模型服务返回了无效响应。")
    if data.get("error"):
        raise RuntimeError(f"模型服务返回错误: {data['error']}")
    return data


def _image_batch(image, limit):
    if not isinstance(image, torch.Tensor):
        raise TypeError("图像必须是 ComfyUI IMAGE 张量。")
    if image.ndim == 3:
        image = image.unsqueeze(0)
    if image.ndim != 4 or image.shape[-1] not in (1, 3, 4) or image.shape[0] < 1:
        raise ValueError("IMAGE 需要是 [batch, height, width, channels] 且通道数为 1、3 或 4。")
    if image.shape[0] > limit:
        raise ValueError(f"单次最多输入 {limit} 张图片，当前为 {image.shape[0]}。")
    return image


def _images(image, max_dimension=1024, limit=32):
    image = _image_batch(image, limit)
    encoded = []
    for item in image:
        values = item.detach().cpu().numpy()
        if not np.isfinite(values).all():
            raise ValueError("图像含有 NaN 或无限值。")
        array = (np.clip(values, 0, 1) * 255).round().astype(np.uint8)
        if array.shape[-1] == 1:
            array = array[..., 0]
        img = Image.fromarray(array).convert("RGB")
        img.thumbnail((int(max_dimension), int(max_dimension)), Image.Resampling.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        encoded.append(base64.b64encode(buf.getvalue()).decode("ascii"))
    return encoded


def _chat(connection, prompt, images=None, system="", json_mode=False, keep_alive=None):
    if not str(prompt).strip():
        raise ValueError("提示词不能为空。")
    messages = []
    if str(system).strip():
        messages.append({"role": "system", "content": str(system).strip()})
    backend = connection.get("backend", "Ollama")
    if backend == "llama.app":
        content = [{"type": "text", "text": str(prompt)}]
        content.extend({"type": "image_url", "image_url": {"url": "data:image/png;base64," + image}} for image in (images or []))
        messages.append({"role": "user", "content": content if images else str(prompt)})
        payload = {"model": connection["model"], "messages": messages, "stream": False,
                   "max_tokens": connection["max_tokens"], "temperature": connection["temperature"],
                   "seed": connection["seed"], "chat_template_kwargs": {"enable_thinking": False}}
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        endpoint = "/chat/completions" if connection["url"].endswith("/v1") else "/v1/chat/completions"
        response = _request(connection, endpoint, payload)
        choices = response.get("choices", [])
        text = choices[0].get("message", {}).get("content", "") if isinstance(choices, list) and choices and isinstance(choices[0], dict) else ""
        if not isinstance(text, str) or not text.strip():
            raise RuntimeError("模型没有返回有效文本；可增加 max_tokens 或检查模型是否支持当前输入。")
        return text.strip()
    user = {"role": "user", "content": str(prompt)}
    if images:
        user["images"] = images
    messages.append(user)
    payload = {
        "model": connection["model"], "messages": messages, "stream": False,
        "think": False, "keep_alive": connection["keep_alive"] if keep_alive is None else keep_alive,
        "options": {"temperature": connection["temperature"], "num_predict": connection["max_tokens"],
                    "num_ctx": connection["context_length"], "seed": connection["seed"]},
    }
    if json_mode:
        payload["format"] = "json"
    response = _request(connection, "/api/chat", payload)
    text = response.get("message", {}).get("content", "")
    if not isinstance(text, str) or not text.strip():
        raise RuntimeError("模型没有返回有效文本；可增加 max_tokens 或检查模型是否支持当前输入。")
    return text.strip()


def _unload(connection):
    if connection.get("backend", "Ollama") == "llama.app":
        return False
    _request(connection, "/api/generate", {"model": connection["model"], "keep_alive": 0, "stream": False}, check_interrupt=False)
    return True


def _parse_json(text):
    source = str(text).strip()
    try:
        return json.loads(source)
    except json.JSONDecodeError as first_error:
        # Accept fenced JSON and common model prefixes, but do not execute or repair content.
        decoder = json.JSONDecoder()
        match = re.search(r"[\[{]", source)
        if match:
            try:
                value, _ = decoder.raw_decode(source[match.start():])
                return value
            except json.JSONDecodeError:
                pass
        raise ValueError(f"未找到有效 JSON：{first_error.msg}（位置 {first_error.pos}）") from first_error


def _get_path(value, path):
    path = path.strip()
    if not path:
        return value
    parts = [p.replace("~1", "/").replace("~0", "~") for p in path[1:].split("/")] if path.startswith("/") else path.split(".")
    for part in parts:
        if isinstance(value, dict):
            if part not in value:
                raise ValueError(f"JSON 中不存在字段：{part}")
            value = value[part]
        elif isinstance(value, list):
            if not part.isdigit() or int(part) >= len(value):
                raise ValueError(f"JSON 数组索引无效：{part}")
            value = value[int(part)]
        else:
            raise ValueError(f"无法继续读取字段：{part}")
    return value


class kkMiniCPMLocalLoader:
    CATEGORY = _CATEGORY + "/旧版兼容"
    DEPRECATED = True
    RETURN_TYPES = (_CONNECTION, "STRING")
    RETURN_NAMES = ("connection", "model_path")
    FUNCTION = "load"

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "model": (["MiniCPM-V 4.7", "MiniCPM-V 4.5", "MiniCPM5 2B", "自定义 GGUF"],),
            "context_length": ("INT", {"default": 4096, "min": 1024, "max": 32768, "step": 256}),
            "max_tokens": ("INT", {"default": 512, "min": 1, "max": 8192}),
            "temperature": ("FLOAT", {"default": 0.3, "min": 0.0, "max": 2.0, "step": 0.05}),
            "seed": ("INT", {"default": 42, "min": 0, "max": 0xFFFFFFFF}),
            "timeout_seconds": ("INT", {"default": 900, "min": 10, "max": 7200}),
        }, "optional": {
            "model_path": ("STRING", {"default": "", "tooltip": "旧版兼容字段；不再用于加载文件。"}),
            "projector_path": ("STRING", {"default": "", "tooltip": "旧版兼容字段；不再用于加载文件。"}),
        }}

    def load(self, model, context_length, max_tokens, temperature, seed, timeout_seconds, model_path="", projector_path=""):
        models = {"MiniCPM-V 4.7": _VISION_MODEL, "MiniCPM-V 4.5": _VIDEO_MODEL, "MiniCPM5 2B": _TEXT_MODEL}
        if model not in models:
            raise ValueError("旧版自定义 GGUF 不再直接加载；请换用 KK MiniCPM Loader 并选择 Ollama 模型。")
        return kkMiniCPMLoader().load(models[model], "http://127.0.0.1:11434", 0,
                                      context_length, max_tokens, temperature, seed, timeout_seconds)


class kkMiniCPMLoader:
    CATEGORY = _CATEGORY
    RETURN_TYPES = (_CONNECTION, "STRING")
    RETURN_NAMES = ("connection", "model_name")
    FUNCTION = "load"

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "model": ("STRING", {"default": "", "tooltip": "填写服务中可用的模型名称。"}),
            "url": ("STRING", {"default": "http://127.0.0.1:11434"}),
            "keep_alive_seconds": ("INT", {"default": 0, "min": 0, "max": 86400}),
            "context_length": ("INT", {"default": 4096, "min": 1024, "max": 32768, "step": 256}),
            "max_tokens": ("INT", {"default": 512, "min": 1, "max": 8192}),
            "temperature": ("FLOAT", {"default": 0.3, "min": 0.0, "max": 2.0, "step": 0.05}),
            "seed": ("INT", {"default": 42, "min": 0, "max": 0xFFFFFFFF}),
            "timeout_seconds": ("INT", {"default": 900, "min": 10, "max": 7200}),
        }, "optional": {"custom_model": ("STRING", {"default": "", "tooltip": "旧工作流兼容字段。"}),
                        "backend": (["Ollama", "llama.app"], {"default": "Ollama", "tooltip": "选择服务的接口类型；llama.app 使用 OpenAI 兼容接口。"})}}

    def load(self, model, url, keep_alive_seconds, context_length, max_tokens, temperature, seed, timeout_seconds, custom_model="", backend="Ollama"):
        model = custom_model.strip() if model == "自定义" else model
        model = model.strip()
        if not model:
            raise ValueError("请填写服务中可用的模型名称。")
        if backend not in {"Ollama", "llama.app"}:
            raise ValueError("请选择 Ollama 或 llama.app 服务。")
        config = {"url": _local_url(url), "model": model, "keep_alive": int(keep_alive_seconds),
                  "context_length": int(context_length), "max_tokens": int(max_tokens),
                  "temperature": float(temperature), "seed": int(seed), "timeout": int(timeout_seconds), "backend": backend}
        return (config, model)


class kkMiniCPMVision:
    CATEGORY = _CATEGORY
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("description",)
    FUNCTION = "analyze"

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"connection": (_CONNECTION,), "image": ("IMAGE",),
            "prompt": ("STRING", {"default": "请详细描述图片中的主体、环境、构图、色彩和光线，只描述可见内容。", "multiline": True}),
            "max_dimension": ("INT", {"default": 1024, "min": 256, "max": 2048, "step": 64})}}

    def analyze(self, connection, image, prompt, max_dimension):
        return (_chat(connection, prompt, _images(image, max_dimension)),)


class kkMiniCPMVideo:
    CATEGORY = _CATEGORY
    RETURN_TYPES = ("STRING", "INT")
    RETURN_NAMES = ("analysis", "sampled_frames")
    FUNCTION = "analyze"

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"connection": (_CONNECTION,), "video": ("VIDEO",),
            "prompt": ("STRING", {"default": "按时间顺序描述主体、场景、动作和镜头变化。只描述画面，不猜测声音或对白。", "multiline": True}),
            "max_frames": ("INT", {"default": 8, "min": 1, "max": 32}),
            "max_dimension": ("INT", {"default": 512, "min": 256, "max": 1024, "step": 64})}}

    def analyze(self, connection, video, prompt, max_frames, max_dimension):
        if not hasattr(video, "get_components"):
            raise TypeError("video 需要连接 ComfyUI VIDEO。")
        frames = video.get_components().images
        if not isinstance(frames, torch.Tensor) or frames.ndim != 4 or len(frames) == 0:
            raise ValueError("视频没有可用图像帧。")
        count = min(len(frames), int(max_frames))
        indices = torch.linspace(0, len(frames)-1, count, device=frames.device).round().long()
        sampled = frames.index_select(0, indices)
        intro = "These are ordered video frames. There is no audio input.\n"
        return (_chat(connection, intro + prompt, _images(sampled, max_dimension)), count)


class kkMiniCPMText:
    CATEGORY = _CATEGORY
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("response",)
    FUNCTION = "generate"

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"connection": (_CONNECTION,), "text": ("STRING", {"default": "", "multiline": True}),
            "instruction": ("STRING", {"default": "请理解并处理下面的文本。", "multiline": True})}}

    def generate(self, connection, text, instruction):
        if not text.strip():
            raise ValueError("text 不能为空。")
        return (_chat(connection, f"{instruction}\n\n文本：\n{text}"),)


class kkMiniCPMCaption:
    CATEGORY = _CATEGORY
    RETURN_TYPES = ("STRING", "STRING", "INT", "STRING")
    RETURN_NAMES = ("captions_json", "captions_text", "count", "saved_files_json")
    FUNCTION = "caption"

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"connection": (_CONNECTION,), "images": ("IMAGE",),
            "instruction": ("STRING", {"default": "为这张训练图片写一段准确、具体的中文描述，只输出描述。", "multiline": True}),
            "max_dimension": ("INT", {"default": 768, "min": 256, "max": 2048, "step": 64})},
            "optional": {"filenames": ("STRING", {"default": "", "multiline": True, "tooltip": "可选：每行一个文件名，与输入图片顺序一致。"}),
                "save_txt": ("BOOLEAN", {"default": False, "tooltip": "保存到 ComfyUI output 下的子目录；不会覆盖已有文件。"}),
                "output_folder": ("STRING", {"default": "MiniCPM_captions", "tooltip": "仅允许单层文件夹名称。"})}}

    def caption(self, connection, images, instruction, max_dimension, filenames="", save_txt=False, output_folder="MiniCPM_captions"):
        images = _image_batch(images, limit=256)
        names = [x.strip() for x in filenames.splitlines() if x.strip()]
        if names and len(names) != len(images):
            raise ValueError(f"文件名数量 {len(names)} 与图片数量 {len(images)} 不一致。")
        paths = []
        if save_txt:
            if not re.fullmatch(r"[\w\-\u4e00-\u9fff]+", output_folder) or output_folder in {".", ".."}:
                raise ValueError("输出文件夹必须是单层名称，只能包含字母、数字、中文、下划线或短横线。")
            import folder_paths
            base = Path(folder_paths.get_output_directory()).resolve()
            target = (base / output_folder).resolve()
            if target.parent != base:
                raise ValueError("输出文件夹必须位于 ComfyUI output 目录中。")
            for i in range(len(images)):
                stem = PureWindowsPath(names[i].replace("/", "\\")).stem if names else f"image_{i+1:06d}"
                if not stem or stem in {".", ".."} or re.search(r'[<>:"/\\|?*\x00-\x1f]', stem) or stem[-1:] in {" ", "."}:
                    raise ValueError(f"文件名无效：{names[i] if names else stem}")
                paths.append(target / (stem + ".txt"))
            if len({str(p).casefold() for p in paths}) != len(paths):
                raise ValueError("文件名重复，无法保存同名标注。")
            if any(p.exists() for p in paths):
                raise FileExistsError("目标标注文件已存在；请更换文件夹或文件名，节点不会覆盖已有文件。")
        records = []
        try:
            for i, image in enumerate(images):
                # Keep the model alive between batch items, then honor the Loader setting.
                keep = "5m" if i < len(images) - 1 else connection["keep_alive"]
                result = _chat(connection, instruction, _images(image, max_dimension, limit=1), keep_alive=keep)
                records.append({"index": i + 1, "filename": names[i] if names else "", "caption": result})
        except Exception:
            if len(images) > 1 and connection["keep_alive"] == 0:
                try:
                    _unload(connection)
                except Exception:
                    pass
            raise
        if paths:
            paths[0].parent.mkdir(parents=True, exist_ok=True)
            for path, record in zip(paths, records):
                # Exclusive creation protects existing user files even if another process races the preflight.
                with path.open("x", encoding="utf-8", newline="\n") as output:
                    output.write(record["caption"] + "\n")
        return (json.dumps(records, ensure_ascii=False, indent=2), "\n\n".join(r["caption"] for r in records),
                len(records), json.dumps([str(p) for p in paths], ensure_ascii=False))


class kkMiniCPMPrompt:
    CATEGORY = _CATEGORY
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("optimized_prompt",)
    FUNCTION = "optimize"

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"connection": (_CONNECTION,), "text": ("STRING", {"default": "", "multiline": True}),
            "language": (["中文", "English"], {"default": "中文"}),
            "target": ("STRING", {"default": "图像生成", "multiline": False})}}

    def optimize(self, connection, text, language, target):
        if not text.strip():
            raise ValueError("原始需求不能为空。")
        instruction = f"将用户需求优化为适合{target}的{language}提示词，保留原意，避免虚构关键事实，只输出提示词。\n\n需求：\n{text}"
        return (_chat(connection, instruction),)


class kkMiniCPMOCR:
    CATEGORY = _CATEGORY
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("recognized_text",)
    FUNCTION = "recognize"

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"connection": (_CONNECTION,), "image": ("IMAGE",),
            "instruction": ("STRING", {"default": "识别图片中可见的文字，尽量保留阅读顺序和换行；不确定的内容标为[无法辨认]，只输出识别结果。", "multiline": True}),
            "max_dimension": ("INT", {"default": 1536, "min": 256, "max": 2048, "step": 64})}}

    def recognize(self, connection, image, instruction, max_dimension):
        return (_chat(connection, instruction, _images(image, max_dimension)),)


class kkMiniCPMQA:
    CATEGORY = _CATEGORY
    RETURN_TYPES = ("STRING", "STRING", "BOOLEAN", "FLOAT")
    RETURN_NAMES = ("summary", "report_json", "passed", "score")
    FUNCTION = "evaluate"

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"connection": (_CONNECTION,), "image": ("IMAGE",),
            "criteria": ("STRING", {"default": "检查主体是否完整、画面是否清晰、有无明显视觉缺陷。", "multiline": True}),
            "max_dimension": ("INT", {"default": 1024, "min": 256, "max": 2048, "step": 64})},
            "optional": {"reference_image": ("IMAGE",)}}

    def evaluate(self, connection, image, criteria, max_dimension, reference_image=None):
        image = _image_batch(image, limit=1)
        if reference_image is not None:
            reference_image = _image_batch(reference_image, limit=1)
        if len(image) != 1 or (reference_image is not None and len(reference_image) != 1):
            raise ValueError("质检图片和参考图片各需要恰好一张。")
        imgs = _images(image, max_dimension)
        reference = ""
        if reference_image is not None:
            imgs = _images(reference_image, max_dimension) + imgs
            reference = "第一张是参考图，第二张是待检图。"
        prompt = (reference + "根据画面和下面的标准质检，仅输出 JSON 对象，字段必须为 "
                  '"passed"（布尔值）、"score"（0到100的数字）、"issues"（字符串数组）、"summary"（中文字符串）。'
                  "无法确定时说明不确定，不要虚构。\n标准：" + criteria)
        value = _parse_json(_chat(connection, prompt, imgs, json_mode=True))
        if (not isinstance(value, dict) or type(value.get("passed")) is not bool
                or type(value.get("score")) not in (int, float)
                or not math.isfinite(value["score"]) or not 0 <= value["score"] <= 100
                or not isinstance(value.get("issues"), list) or not all(isinstance(x, str) for x in value["issues"])
                or not isinstance(value.get("summary"), str)):
            raise ValueError("质检模型未返回符合要求的 JSON；请重试或调整标准。")
        return (value["summary"], json.dumps(value, ensure_ascii=False, indent=2), value["passed"], float(value["score"]))


class kkMiniCPMRouter:
    CATEGORY = _CATEGORY
    RETURN_TYPES = ("STRING", "STRING", "BOOLEAN", "BOOLEAN", "BOOLEAN", "BOOLEAN", "BOOLEAN", "BOOLEAN", "BOOLEAN")
    RETURN_NAMES = ("route", "route_json", "is_vision", "is_video", "is_text", "is_caption", "is_prompt", "is_ocr", "is_qa")
    FUNCTION = "route"

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"intent": (["auto", "vision", "video", "text", "caption", "prompt", "ocr", "qa"],),
            "request": ("STRING", {"default": "", "multiline": True})},
            "optional": {"image": ("IMAGE",), "video": ("VIDEO",),
                         "classifier": (_CONNECTION, {"tooltip": "可选：连接 MiniCPM5 等文本模型进行语义路由；只发送请求文字和素材类型，不发送图片或视频。"})}}

    def route(self, intent, request, image=None, video=None, classifier=None):
        selected = intent
        method = "manual"
        if selected == "auto" and classifier is not None:
            method = "model"
            allowed = ["text", "prompt"]
            if image is not None:
                allowed.extend(["vision", "caption", "ocr", "qa"])
            if video is not None:
                allowed.append("video")
            descriptions = {"prompt": "撰写或优化图像、视频生成提示词", "text": "普通文本处理、问答、总结或翻译",
                            "vision": "理解或描述图片", "caption": "为图片打标或写训练描述",
                            "ocr": "提取或识别图片文字", "qa": "检查图片质量或比较参考图", "video": "分析视频画面"}
            choices = "；".join(f"{name}（{descriptions[name]}）" for name in allowed)
            examples = ["翻译这篇文章→text", "润色生成图片的提示词→prompt"]
            if image is not None:
                examples.extend(["识别图中的文字→ocr", "检查图片的质量→qa", "为图片打训练标签→caption", "描述这张图片→vision"])
            if video is not None:
                examples.append("分析视频中人物的动作→video")
            prompt = (f"判断用户任务属于哪个类别。{choices}。示例：{'；'.join(examples)}。"
                      '只输出 JSON 对象，例如 {"route":"text"}。'
                      f"可选分类只能是：{', '.join(allowed)}。用户请求：{request}")
            result = _parse_json(_chat(classifier, prompt, json_mode=True))
            selected = result.get("route") if isinstance(result, dict) else None
            if not isinstance(selected, str) or selected not in allowed:
                raise ValueError(f"语义路由未返回有效结果，可选值：{', '.join(allowed)}。")
        elif selected == "auto":
            method = "rules"
            s = request.lower()
            if video is not None:
                selected = "video"
            elif image is not None:
                if re.search(r"ocr|识字|识别.*文字|提取.*文字|文字.*识别|文字.*提取", s): selected = "ocr"
                elif re.search(r"质检|质量检查|视觉检查|quality", s): selected = "qa"
                elif re.search(r"打标|标注|caption|标签", s): selected = "caption"
                else: selected = "vision"
            else:
                selected = "prompt" if re.search(r"优化.*提示词|提示词.*优化|prompt", s) else "text"
        if selected == "video" and video is None:
            raise ValueError("video 路由需要连接 VIDEO 输入。")
        if selected in {"vision", "ocr", "qa", "caption"} and image is None:
            raise ValueError(f"{selected} 路由需要连接 IMAGE 输入。")
        route_data = {"route": selected, "method": method, "request": request, "has_image": image is not None, "has_video": video is not None}
        return (selected, json.dumps(route_data, ensure_ascii=False), *(selected == r for r in ("vision", "video", "text", "caption", "prompt", "ocr", "qa")))


class kkMiniCPMJSON:
    CATEGORY = _CATEGORY
    RETURN_TYPES = ("STRING", "STRING", "BOOLEAN", "STRING")
    RETURN_NAMES = ("normalized_json", "value", "valid", "error")
    FUNCTION = "parse"

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"text": ("STRING", {"default": "", "multiline": True}),
            "path": ("STRING", {"default": "", "tooltip": "留空返回整个 JSON；支持 a.b.0 或 /a/b/0。"})}}

    def parse(self, text, path):
        try:
            data = _parse_json(text)
            result = _get_path(data, path)
            value = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False, separators=(",", ":"))
            return (json.dumps(data, ensure_ascii=False, indent=2), value, True, "")
        except ValueError as exc:
            return ("", "", False, str(exc))


class kkMiniCPMUnload:
    CATEGORY = _CATEGORY
    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("value", "status")
    FUNCTION = "unload"
    OUTPUT_NODE = True

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"connection": (_CONNECTION,)},
                "optional": {"after": ("STRING", {"forceInput": True, "tooltip": "连接推理结果，确保推理结束后再卸载。"})}}

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return float("nan")

    def unload(self, connection, after=""):
        unloaded = _unload(connection)
        status = (f"已向 Ollama 请求卸载 {connection['model']}。" if unloaded else
                  "llama.app 的模型由服务管理；请在服务中卸载或关闭服务。")
        return (after, status)


NODE_CLASS_MAPPINGS = {
    "kkMiniCPMLocalLoader": kkMiniCPMLocalLoader, "kkMiniCPMLoader": kkMiniCPMLoader, "kkMiniCPMVision": kkMiniCPMVision,
    "kkMiniCPMVideo": kkMiniCPMVideo, "kkMiniCPMText": kkMiniCPMText,
    "kkMiniCPMCaption": kkMiniCPMCaption, "kkMiniCPMPrompt": kkMiniCPMPrompt,
    "kkMiniCPMOCR": kkMiniCPMOCR, "kkMiniCPMQA": kkMiniCPMQA,
    "kkMiniCPMRouter": kkMiniCPMRouter, "kkMiniCPMJSON": kkMiniCPMJSON,
    "kkMiniCPMUnload": kkMiniCPMUnload,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "kkMiniCPMLocalLoader": "KK MiniCPM Local Loader",
    "kkMiniCPMLoader": "KK MiniCPM Loader",
    "kkMiniCPMVision": "KK MiniCPM Vision",
    "kkMiniCPMVideo": "KK MiniCPM Video",
    "kkMiniCPMText": "KK MiniCPM Text",
    "kkMiniCPMCaption": "KK MiniCPM Caption",
    "kkMiniCPMPrompt": "KK MiniCPM Prompt",
    "kkMiniCPMOCR": "KK MiniCPM OCR",
    "kkMiniCPMQA": "KK MiniCPM QA",
    "kkMiniCPMRouter": "KK MiniCPM Router",
    "kkMiniCPMJSON": "KK MiniCPM JSON",
    "kkMiniCPMUnload": "KK MiniCPM Unload",
}
