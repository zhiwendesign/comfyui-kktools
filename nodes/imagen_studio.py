import base64
import hashlib
import io
import json
import os
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image


SUPPORTED_CATEGORIES = ("poster", "illustration", "photography", "comic")
CATEGORY_LABEL_CN = {
    "poster": "海报",
    "illustration": "插画",
    "photography": "摄影",
    "comic": "漫画",
    "ppt": "PPT",
    "detail-page": "详情页",
}
CATEGORY_LABEL_EN = {value: key for key, value in CATEGORY_LABEL_CN.items()}
CATEGORY_OPTIONS_CN = tuple(CATEGORY_LABEL_CN[value] for value in SUPPORTED_CATEGORIES)
CATEGORY_VALUE_BY_LABEL = {label: value for value, label in CATEGORY_LABEL_CN.items()}
LANGUAGE_OPTIONS_CN = ("中文", "英文")
LANGUAGE_VALUE_BY_LABEL = {"中文": "zh", "英文": "en", "zh": "zh", "en": "en"}
NODE_CATEGORY_CN = "Imagen Studio/模板工具"

VISION_ANALYZER_PROMPT = """你是资深视觉设计师，擅长从一组参考图中抽象出可复用的「视觉风格语言」。
请严格输出 JSON，字段如下（不要额外文字、不要 Markdown 代码块）：
{
  "palette": ["主色 hex 3~5 个"],
  "lighting": "光线/氛围描述（≤30 字）",
  "composition": "构图特征（≤30 字）",
  "subject_treatment": "主体处理方式（材质/笔触/描边）（≤30 字）",
  "texture": "质感/纹理关键词（≤20 字）",
  "mood": "情绪/调性（≤15 字）",
  "typography_hint": "若包含文字元素，字体/排版特征；否则留空",
  "negative_traits": ["应避免的视觉要素 3~6 个"],
  "style_keywords": ["核心风格英文关键词 5~10 个"]
}"""

TEMPLATE_DISTILLER_PROMPT = """你会收到一份视觉风格 JSON。请产出两段风格提示词片段，都尽量简短、信息密度高：
输出严格 JSON：
{
  "style_prompt_en": "一段英文风格描述，60~120 words，涵盖 palette/lighting/composition/texture/mood/subject_treatment。不要包含具体主体，只描述风格。",
  "style_prompt_zh": "一段中文风格描述，60~120 字，同上。",
  "negative_prompt": "英文负面词，逗号分隔，≤20 词"
}"""

REFERENCE_ANALYZER_PROMPT = """You are a professional visual style analyst. The user will provide one reference image.
Return strict JSON only, with no Markdown.

Describe two complementary things:
1. description: Simplified Chinese, 120-250 characters, describing what is in the image: subject, composition, color, lighting, visible text, and key details.
2. style_fingerprint: English, 180-360 words, one dense paragraph about how the image is made, not what the specific subject is.

For style_fingerprint, write in this exact order: medium and rendering; line quality; texture and grain; palette and color treatment; composition and layout; typography treatment if text exists. Use concrete terms such as pencil sketch, flat vector, photorealistic DSLR, cel shading, manga screentone, halftone dots, risograph offset, paper grain, chromatic aberration, cross-hatching, screenprint, duotone, outlined slab type, condensed sans.

Output schema:
{
  "description": "Chinese description",
  "style_fingerprint": "English style fingerprint paragraph",
  "keep_strict": ["subject elements that must remain, <=8 items"],
  "style_keep_strict": ["style elements that must remain, <=8 items"],
  "rendering_medium": "<=20 words",
  "composition_type": "<=15 words",
  "typography_style": "<=20 words, or empty string",
  "has_text": true,
  "dominant_colors": ["#RRGGBB"]
}"""

PROMPT_COMPOSER_PROMPT = """You are an image generation prompt engineer. The user will provide JSON with:
- template.style_prompt_en / template.style_prompt_zh
- template.negative_prompt
- user_idea
- aspect_ratio
- prompt_language: "zh" or "en"
- target_model, usually "generic-comfyui"
- reference_images: optional items with description, style_fingerprint, keep_strict, and style_keep_strict

Return strict JSON only, with no Markdown:
{
  "prompt": "final positive prompt",
  "negative": "final negative prompt",
  "notes": "short Chinese note, <=40 characters"
}

Rules:
1. The subject and concrete request come from user_idea. The visual style comes from the template and reference image style fingerprints.
2. If prompt_language is "zh", write the final positive prompt in Simplified Chinese. If it is "en", write it in English.
3. For target_model "generic-comfyui", produce a clear ComfyUI-friendly prompt: concise descriptive phrases, strong visual nouns, medium/rendering, lighting, composition, texture, palette, typography if relevant, and aspect-ratio intent. Do not include model-specific flags unless the target_model explicitly calls for them.
4. If reference_images is not empty, place the first reference image style_fingerprint early as a STYLE section, lightly translating only when prompt_language is zh. Preserve technical style terms such as halftone, risograph, cross-hatching, cel shading, duotone, paper grain.
5. List concrete elements from keep_strict and style_keep_strict inside the prompt. Avoid vague phrases like "follow the reference"; be specific.
6. Keep the template style visible, but do not let it replace the user's subject.
7. negative should inherit template.negative_prompt and may add concise quality-control negatives.
8. notes should briefly explain the composition choice in Chinese."""

COMPOSER_ASPECT_RATIOS = ("auto", "1:1", "16:9", "9:16", "4:3", "3:4", "3:2", "2:3", "21:9", "9:21")
ASPECT_RATIO_OPTIONS_CN = ("自动", "1:1", "16:9", "9:16", "4:3", "3:4", "3:2", "2:3", "21:9", "9:21")
ASPECT_RATIO_VALUE_BY_LABEL = {value: value for value in COMPOSER_ASPECT_RATIOS}
ASPECT_RATIO_VALUE_BY_LABEL["自动"] = "auto"
RUNNINGHUB_RESOLUTIONS = ("1k", "2k", "4k")
RUNNINGHUB_DEFAULT_BASE_URL = "https://www.runninghub.cn/openapi/v2"
RUNNINGHUB_CHANNEL_OPTIONS_CN = ("第三方低价渠道", "官方渠道")
RUNNINGHUB_CHANNEL_VALUE_BY_LABEL = {
    "第三方低价渠道": "third_party",
    "官方渠道": "official",
    "third_party": "third_party",
    "official": "official",
}
RUNNINGHUB_TEXT_TO_IMAGE_PATHS = {
    "third_party": "/rhart-image-g-2/text-to-image",
    "official": "/rhart-image-g-2-official/text-to-image",
}
RUNNINGHUB_IMAGE_TO_IMAGE_PATHS = {
    "third_party": "/rhart-image-g-2/image-to-image",
    "official": "/rhart-image-g-2-official/image-to-image",
}
RUNNINGHUB_QUALITY_OPTIONS = ("low", "medium", "high")
RUNNINGHUB_DEFAULT_QUALITY = "medium"
RUNNINGHUB_QUERY_PATH = "/query"
RUNNINGHUB_POLL_INTERVAL_SECONDS = 5.0
RUNNINGHUB_TIMEOUT_SECONDS = 600.0
DEFAULT_USER_IDEA = "根据模板风格生成一张完整主视觉图像，保留模板的构图、配色、质感、光影和整体氛围。"
IMAGEN_STUDIO_DATA_DIR_NAME = "imagen-studio"
TEMPLATE_LIBRARY_DIR_NAME = "templates"
TEMPLATE_INDEX_FILENAME = "index.json"
TEMPLATE_THUMBNAIL_DIR_NAME = "thumbnails"
TEMPLATE_SAVE_CATEGORY_OPTIONS_CN = ("自动",) + CATEGORY_OPTIONS_CN
IMAGEN_STUDIO_PIPE_TYPE = "IMAGEN_STUDIO_PIPE"
IMAGEN_STUDIO_PIPE_VERSION = 1


class TemplateDistillError(RuntimeError):
    pass


@dataclass(frozen=True)
class TaskConfig:
    model: str
    api_key: str
    base_url: str


@dataclass(frozen=True)
class RunningHubConfig:
    api_key: str
    base_url: str


def read_input_value(inputs: dict[str, Any], cn_name: str, default: Any = "") -> Any:
    return inputs[cn_name] if cn_name in inputs else default


def imagen_studio_data_dir() -> Path:
    return Path(__file__).resolve().parents[1] / IMAGEN_STUDIO_DATA_DIR_NAME


def normalize_category_option(value: Any) -> str:
    text = str(value or "").strip()
    if text in CATEGORY_VALUE_BY_LABEL:
        return CATEGORY_VALUE_BY_LABEL[text]
    return text if text in SUPPORTED_CATEGORIES else "poster"


def normalize_language_option(value: Any) -> str:
    text = str(value or "").strip()
    return LANGUAGE_VALUE_BY_LABEL.get(text, "zh")


def normalize_aspect_ratio_option(value: Any, default: str = "auto") -> str:
    text = str(value or "").strip()
    normalized = ASPECT_RATIO_VALUE_BY_LABEL.get(text, text)
    if normalized in COMPOSER_ASPECT_RATIOS:
        return normalized
    return default


def normalize_runninghub_channel_option(value: Any) -> str:
    text = str(value or "").strip()
    return RUNNINGHUB_CHANNEL_VALUE_BY_LABEL.get(text, "third_party")


def normalize_runninghub_quality_option(value: Any) -> str:
    text = str(value or "").strip().lower()
    return text if text in RUNNINGHUB_QUALITY_OPTIONS else RUNNINGHUB_DEFAULT_QUALITY


def normalize_base_url(base_url: str) -> str:
    value = str(base_url or "").strip().rstrip("/")
    value = re.sub(
        r"/(chat/completions|completions|images/(generations|edits|variations)|audio/[a-z]+|embeddings|models|responses)/?$",
        "",
        value,
        flags=re.I,
    )
    if value and not re.search(r"/v\d+$", value):
        value = f"{value}/v1"
    return value


def try_json(value: Any) -> Any:
    if value is None:
        return None
    text = str(value)
    match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    body = match.group(1) if match else text
    for candidate in (body, _between(body, "{", "}"), _between(body, "[", "]")):
        if not candidate:
            continue
        try:
            return json.loads(candidate)
        except Exception:
            pass
    return None


def _between(text: str, left: str, right: str) -> str:
    start = text.find(left)
    end = text.rfind(right)
    if start >= 0 and end > start:
        return text[start : end + 1]
    return ""


def pick(obj: dict[str, Any] | None, *keys: str) -> str:
    if not isinstance(obj, dict):
        return ""
    for key in keys:
        value = obj.get(key)
        if value not in (None, ""):
            return str(value)
    return ""


def as_object(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item or "").strip()]


def unique_list(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        clean = str(value or "").strip()
        key = clean.lower()
        if not clean or key in seen:
            continue
        seen.add(key)
        out.append(clean)
    return out


def first_reference(features: dict[str, Any]) -> dict[str, Any]:
    refs = features.get("reference_images")
    if not isinstance(refs, list):
        refs = features.get("referenceImages")
    return as_object(refs[0]) if isinstance(refs, list) and refs else {}


def normalize_generic_features(features: Any) -> dict[str, Any]:
    raw = as_object(features)
    summary = as_object(raw.get("global_summary") or raw.get("globalSummary"))
    if not summary:
        return raw
    next_features = dict(raw)
    next_features.setdefault("palette", summary.get("palette") or [])
    next_features.setdefault("typography_hint", summary.get("typography_hint") or summary.get("typographyHint") or "")
    next_features.setdefault("mood", summary.get("mood") or "")
    next_features.setdefault("composition", summary.get("composition") or "")
    next_features.setdefault(
        "clean_image_control",
        summary.get("clean_image_control") or summary.get("cleanImageControl") or None,
    )
    return next_features


def clean_control_text(clean_control: Any) -> list[str]:
    obj = as_object(clean_control)
    return [str(obj.get(key) or "").strip() for key in ("background", "color", "elements", "text", "edges") if str(obj.get(key) or "").strip()]


def fallback_style_prompt_en(features: dict[str, Any]) -> str:
    normalized = normalize_generic_features(features)
    summary = as_object(normalized.get("global_summary") or normalized.get("globalSummary"))
    ref = first_reference(normalized)
    palette = as_list(normalized.get("palette") or summary.get("palette"))
    parts = [
        pick(ref, "style_fingerprint", "styleFingerprint"),
        f"Composition: {normalized.get('composition')}" if normalized.get("composition") else "",
        f"Typography: {normalized.get('typography_hint')}" if normalized.get("typography_hint") else "",
        f"Mood: {normalized.get('mood')}" if normalized.get("mood") else "",
        f"Palette: {', '.join(palette)}" if palette else "",
    ]
    style_keep = as_list(ref.get("style_keep_strict") or ref.get("styleKeepStrict"))
    if style_keep:
        parts.append(f"Style elements to preserve: {'; '.join(style_keep)}")
    controls = clean_control_text(normalized.get("clean_image_control") or summary.get("clean_image_control"))
    if controls:
        parts.append(f"Clean image control: {'; '.join(controls)}")
    return " ".join(part.strip() for part in parts if str(part or "").strip())


def fallback_style_prompt_zh(features: dict[str, Any]) -> str:
    normalized = normalize_generic_features(features)
    summary = as_object(normalized.get("global_summary") or normalized.get("globalSummary"))
    ref = first_reference(normalized)
    palette = as_list(normalized.get("palette") or summary.get("palette"))
    parts = [
        f"整体氛围：{normalized.get('mood')}" if normalized.get("mood") else "",
        f"构图：{normalized.get('composition')}" if normalized.get("composition") else "",
        f"排版：{normalized.get('typography_hint')}" if normalized.get("typography_hint") else "",
        f"配色：{'、'.join(palette)}" if palette else "",
        f"参考图：{pick(ref, 'description')}" if pick(ref, "description") else "",
    ]
    style_keep = as_list(ref.get("style_keep_strict") or ref.get("styleKeepStrict"))
    if style_keep:
        parts.append(f"需保留的风格元素：{'；'.join(style_keep)}")
    controls = clean_control_text(normalized.get("clean_image_control") or summary.get("clean_image_control"))
    if controls:
        parts.append(f"画面控制：{'；'.join(controls)}")
    return "；".join(part.strip() for part in parts if str(part or "").strip())


def fallback_negative_prompt(features: dict[str, Any]) -> str:
    normalized = normalize_generic_features(features)
    summary = as_object(normalized.get("global_summary") or normalized.get("globalSummary"))
    ref = first_reference(normalized)
    return ", ".join(
        unique_list(
            as_list(normalized.get("negative_traits") or normalized.get("negativeTraits"))
            + as_list(summary.get("negative_traits") or summary.get("negativeTraits"))
            + as_list(ref.get("negative_traits") or ref.get("negativeTraits"))
        )
    )


def normalize_generic_analysis_result(features: Any = None, style: Any = None) -> dict[str, Any]:
    normalized_features = normalize_generic_features(features or {})
    style_obj = as_object(style)
    return {
        "features": normalized_features,
        "stylePromptEn": pick(style_obj, "style_prompt_en", "stylePromptEn", "prompt_en", "promptEn")
        or pick(normalized_features, "style_prompt_en", "stylePromptEn", "prompt_en", "promptEn")
        or fallback_style_prompt_en(normalized_features),
        "stylePromptZh": pick(style_obj, "style_prompt_zh", "stylePromptZh", "prompt_zh", "promptZh")
        or pick(normalized_features, "style_prompt_zh", "stylePromptZh", "prompt_zh", "promptZh")
        or fallback_style_prompt_zh(normalized_features),
        "negativePrompt": pick(style_obj, "negative_prompt", "negativePrompt", "negative")
        or pick(normalized_features, "negative_prompt", "negativePrompt", "negative")
        or fallback_negative_prompt(normalized_features),
    }


def expand_config_path_candidate(value: str | Path) -> list[Path]:
    path = Path(str(value or "").strip().strip('"'))
    if not str(path):
        return []
    if path.name.lower() == "config.json":
        return [path]
    return [
        path / "config.json",
        path / "data" / "config.json",
    ]


def dedupe_paths(paths: list[Path]) -> list[Path]:
    seen: set[str] = set()
    out: list[Path] = []
    for path in paths:
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        out.append(path)
    return out


def local_node_config_candidates(current_file: Path) -> list[Path]:
    node_dir = imagen_studio_data_dir()
    return [
        node_dir / "config.json",
        node_dir / "data" / "config.json",
    ]


def find_default_config_path(explicit_path: str = "") -> Path:
    explicit = str(explicit_path or "").strip().strip('"')
    candidates: list[Path] = []
    if explicit:
        candidates.extend(expand_config_path_candidate(explicit))
    here = Path(__file__).resolve()
    if not explicit:
        candidates.extend(local_node_config_candidates(here))
    candidates = dedupe_paths(candidates)
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    checked = "\n".join(f"- {path}" for path in candidates)
    raise TemplateDistillError(
        "未找到 ComfyUI Imagen 配置。请在 kktools/imagen-studio 目录创建 config.json，"
        "或在节点的“配置路径”中指定一个独立 config.json 文件。"
        + (f"\n已检查路径：\n{checked}" if checked else "")
    )


def config_from_env() -> dict[str, Any]:
    api_key = os.getenv("COMFYUI_IMAGEN_API_KEY") or os.getenv("OPENAI_API_KEY") or ""
    base_url = os.getenv("COMFYUI_IMAGEN_BASE_URL") or os.getenv("OPENAI_BASE_URL") or ""
    vision_model = os.getenv("COMFYUI_IMAGEN_VISION_MODEL") or os.getenv("COMFYUI_IMAGEN_VLM_MODEL") or ""
    text_model = os.getenv("COMFYUI_IMAGEN_TEXT_MODEL") or os.getenv("COMFYUI_IMAGEN_LLM_MODEL") or ""
    if not (api_key and base_url and vision_model and text_model):
        return {}
    return {
        "apiKey": api_key,
        "baseUrl": base_url,
        "visionModel": vision_model,
        "textModel": text_model,
        "providers": [],
        "providerModels": [],
        "modelAssignments": {},
    }


def load_config(config_path: str = "") -> dict[str, Any]:
    if str(config_path or "").strip():
        path = find_default_config_path(config_path)
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise TemplateDistillError(f"读取 ComfyUI Imagen 配置失败：{path}") from exc
    try:
        path = find_default_config_path("")
    except TemplateDistillError:
        env_config = config_from_env()
        if env_config:
            return env_config
        raise
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise TemplateDistillError(f"读取 ComfyUI Imagen 配置失败：{path}") from exc


def load_optional_config(config_path: str = "") -> dict[str, Any]:
    try:
        return load_config(config_path)
    except TemplateDistillError:
        if str(config_path or "").strip():
            raise
        return {}


def normalize_runninghub_base_url(base_url: str) -> str:
    value = str(base_url or "").strip().rstrip("/")
    if not value:
        return RUNNINGHUB_DEFAULT_BASE_URL
    value = re.sub(r"/(rhart-image-g-2/text-to-image|query)/?$", "", value, flags=re.I)
    return value.rstrip("/") or RUNNINGHUB_DEFAULT_BASE_URL


def resolve_runninghub_config(config: dict[str, Any]) -> RunningHubConfig:
    api_key = (
        pick(config, "runninghubApiKey", "runningHubApiKey", "runninghub_api_key")
        or os.getenv("RUNNINGHUB_API_KEY")
        or ""
    ).strip()
    base_url = (
        pick(config, "runninghubBaseUrl", "runningHubBaseUrl", "runninghub_base_url")
        or os.getenv("RUNNINGHUB_BASE_URL")
        or RUNNINGHUB_DEFAULT_BASE_URL
    )
    if not api_key:
        raise TemplateDistillError("未配置 RunningHub API Key。请在节点 config.json 中设置 runninghubApiKey，或设置 RUNNINGHUB_API_KEY。")
    return RunningHubConfig(api_key=api_key, base_url=normalize_runninghub_base_url(base_url))


def resolve_task_config(config: dict[str, Any], task: str) -> TaskConfig:
    assignment_key = "vlm" if task == "vlm" else "llm"
    legacy_model_key = "visionModel" if task == "vlm" else "textModel"
    capability = "vlm" if task == "vlm" else "llm"
    providers = [p for p in config.get("providers", []) if isinstance(p, dict)]
    models = [m for m in config.get("providerModels", []) if isinstance(m, dict)]
    assignments = as_object(config.get("modelAssignments"))
    provider_by_id = {str(p.get("id") or ""): p for p in providers}

    def provider_usable(provider: dict[str, Any] | None) -> bool:
        return bool(provider and provider.get("enabled") is not False and provider.get("baseUrl") and provider.get("apiKey"))

    def model_usable(model: dict[str, Any], require_capability: bool = True) -> bool:
        if model.get("enabled") is False:
            return False
        if require_capability and capability not in as_list(model.get("capabilities")):
            return False
        return provider_usable(provider_by_id.get(str(model.get("providerId") or "")))

    assigned_id = str(assignments.get(assignment_key) or "")
    if assigned_id:
        assigned = next((m for m in models if str(m.get("id") or "") == assigned_id), None)
        if assigned and model_usable(assigned, require_capability=True):
            provider = provider_by_id[str(assigned.get("providerId") or "")]
            return TaskConfig(str(assigned.get("name") or ""), str(provider.get("apiKey") or ""), normalize_base_url(str(provider.get("baseUrl") or "")))

    fallback_model = next((m for m in models if model_usable(m, require_capability=True)), None)
    if fallback_model:
        provider = provider_by_id[str(fallback_model.get("providerId") or "")]
        return TaskConfig(str(fallback_model.get("name") or ""), str(provider.get("apiKey") or ""), normalize_base_url(str(provider.get("baseUrl") or "")))

    legacy_model = str(config.get(legacy_model_key) or "").strip()
    provider = (
        next((p for p in providers if str(p.get("id") or "") == "provider_default" and provider_usable(p)), None)
        or next((p for p in providers if provider_usable(p)), None)
        or ({"apiKey": config.get("apiKey"), "baseUrl": config.get("baseUrl")} if config.get("apiKey") and config.get("baseUrl") else None)
    )
    if legacy_model and provider_usable(provider):
        return TaskConfig(legacy_model, str(provider.get("apiKey") or ""), normalize_base_url(str(provider.get("baseUrl") or "")))

    raise TemplateDistillError(f"ComfyUI Imagen 配置中没有可用的 {task.upper()} 模型。")


def normalize_chat_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [normalize_chat_content(item) for item in content]
        return "\n".join(part for part in parts if part)
    if isinstance(content, dict):
        if isinstance(content.get("text"), str):
            return content["text"]
        if isinstance(content.get("content"), (str, list, dict)):
            return normalize_chat_content(content["content"])
    return "" if content is None else str(content)


def post_json(url: str, headers: dict[str, str], body: dict[str, Any], timeout: int, label: str = "chat") -> dict[str, Any]:
    payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=payload,
        headers={
            **headers,
            "Accept": "application/json",
            "User-Agent": "ComfyUI-Imagen-Studio/1.0",
        },
        method="POST",
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=timeout) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            text = response.read().decode(charset, errors="replace")
            status = int(response.getcode() or 0)
    except urllib.error.HTTPError as exc:
        charset = exc.headers.get_content_charset() if exc.headers else None
        text = exc.read().decode(charset or "utf-8", errors="replace")
        raise TemplateDistillError(f"{label} {exc.code}: {text[:500]}") from exc
    except urllib.error.URLError as exc:
        raise TemplateDistillError(f"{label} 请求失败：{exc.reason}") from exc

    if status < 200 or status >= 300:
        raise TemplateDistillError(f"{label} {status}: {text[:500]}")
    try:
        return json.loads(text)
    except Exception as exc:
        raise TemplateDistillError(f"{label} 返回的不是 JSON：{text[:500]}") from exc


def download_bytes(url: str, timeout: int = 120, label: str = "download") -> bytes:
    request = urllib.request.Request(
        str(url or "").strip(),
        headers={"User-Agent": "ComfyUI-Imagen-Studio/1.0"},
        method="GET",
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=timeout) as response:
            status = int(response.getcode() or 0)
            data = response.read()
    except urllib.error.HTTPError as exc:
        text = exc.read().decode("utf-8", errors="replace")
        raise TemplateDistillError(f"{label} {exc.code}: {text[:500]}") from exc
    except urllib.error.URLError as exc:
        raise TemplateDistillError(f"{label} 请求失败：{exc.reason}") from exc
    if status < 200 or status >= 300:
        raise TemplateDistillError(f"{label} {status}")
    return data


def image_bytes_to_comfy_image(data: bytes) -> Any:
    try:
        image = Image.open(io.BytesIO(data)).convert("RGB")
    except Exception as exc:
        raise TemplateDistillError("下载的 RunningHub 结果不是可读取的图像。") from exc
    array = np.asarray(image).astype(np.float32) / 255.0
    batch = array[None, ...]
    try:
        import torch

        return torch.from_numpy(batch)
    except Exception:
        return batch


def runninghub_headers(config: RunningHubConfig) -> dict[str, str]:
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {config.api_key}",
    }


def runninghub_url(config: RunningHubConfig, path_value: str) -> str:
    return f"{config.base_url.rstrip('/')}/{path_value.lstrip('/')}"


def runninghub_submit_path(channel: str, mode: str) -> str:
    normalized_channel = normalize_runninghub_channel_option(channel)
    if mode == "image-to-image":
        return RUNNINGHUB_IMAGE_TO_IMAGE_PATHS[normalized_channel]
    return RUNNINGHUB_TEXT_TO_IMAGE_PATHS[normalized_channel]


def build_runninghub_submit_request(
    prompt: str,
    aspect_ratio: str,
    resolution: str,
    channel: str = "third_party",
    quality: str = RUNNINGHUB_DEFAULT_QUALITY,
    image_urls: list[str] | None = None,
) -> tuple[str, dict[str, Any], dict[str, str]]:
    urls = [str(item).strip() for item in (image_urls or []) if str(item).strip()]
    mode = "image-to-image" if urls else "text-to-image"
    normalized_channel = normalize_runninghub_channel_option(channel)
    normalized_quality = normalize_runninghub_quality_option(quality)
    submit_path = runninghub_submit_path(normalized_channel, mode)
    payload: dict[str, Any] = {
        "prompt": prompt,
        "aspectRatio": aspect_ratio,
        "resolution": resolution,
        "quality": normalized_quality,
    }
    if urls:
        payload["imageUrls"] = urls
    return submit_path, payload, {
        "channel": normalized_channel,
        "mode": mode,
        "submit_path": submit_path,
        "quality": normalized_quality,
    }


def extract_runninghub_task_id(response: dict[str, Any]) -> str:
    data = as_object(response.get("data"))
    return pick(response, "taskId", "task_id") or pick(data, "taskId", "task_id")


def extract_runninghub_status(response: dict[str, Any]) -> str:
    data = as_object(response.get("data"))
    return (pick(response, "status") or pick(data, "status")).upper()


def extract_runninghub_error(response: dict[str, Any]) -> str:
    data = as_object(response.get("data"))
    return pick(response, "errorMessage", "error_message", "message", "error") or pick(data, "errorMessage", "error_message", "message", "error") or "Unknown error"


def extract_runninghub_result_url(response: dict[str, Any]) -> str:
    data = as_object(response.get("data"))
    candidates = response.get("results")
    if not candidates:
        candidates = data.get("results")
    if not candidates and isinstance(response.get("data"), list):
        candidates = response.get("data")
    if not isinstance(candidates, list) or not candidates:
        return ""
    first = candidates[0]
    if isinstance(first, str):
        return first
    if isinstance(first, dict):
        return pick(first, "url", "imageUrl", "image_url")
    return ""


def runninghub_submit(
    config: RunningHubConfig,
    prompt: str,
    aspect_ratio: str,
    resolution: str,
    channel: str = "third_party",
    quality: str = RUNNINGHUB_DEFAULT_QUALITY,
    image_urls: list[str] | None = None,
) -> tuple[str, dict[str, Any], dict[str, str]]:
    submit_path, payload, meta = build_runninghub_submit_request(
        prompt=prompt,
        aspect_ratio=aspect_ratio,
        resolution=resolution,
        channel=channel,
        quality=quality,
        image_urls=image_urls,
    )
    response = post_json(
        runninghub_url(config, submit_path),
        runninghub_headers(config),
        payload,
        timeout=60,
        label="runninghub submit",
    )
    task_id = extract_runninghub_task_id(response)
    if not task_id:
        error_message = extract_runninghub_error(response)
        error_code = pick(response, "errorCode", "error_code")
        if error_message and error_message != "Unknown error":
            suffix = f"（errorCode={error_code}）" if error_code else ""
            raise TemplateDistillError(f"RunningHub 提交失败：{error_message}{suffix}")
        raise TemplateDistillError(f"RunningHub 提交成功但没有返回 taskId：{json.dumps(response, ensure_ascii=False)[:500]}")
    return task_id, response, meta


def runninghub_query(config: RunningHubConfig, task_id: str) -> dict[str, Any]:
    return post_json(
        runninghub_url(config, RUNNINGHUB_QUERY_PATH),
        runninghub_headers(config),
        {"taskId": task_id},
        timeout=60,
        label="runninghub query",
    )


def run_runninghub_rhart_g2(
    prompt: str,
    aspect_ratio: str = "1:1",
    resolution: str = "1k",
    config_path: str = "",
    channel: str = "third_party",
    quality: str = RUNNINGHUB_DEFAULT_QUALITY,
    reference_images: Any = None,
    poll_interval: float = RUNNINGHUB_POLL_INTERVAL_SECONDS,
    timeout_seconds: float = RUNNINGHUB_TIMEOUT_SECONDS,
    progress_callback: Any = None,
) -> dict[str, Any]:
    def emit_progress(stage: str, current: int, total: int, message: str, status: str = "") -> None:
        if not callable(progress_callback):
            return
        try:
            progress_callback(stage=stage, current=current, total=total, message=message, status=status)
        except TypeError:
            progress_callback(message)

    clean_prompt = str(prompt or "").strip()
    if not clean_prompt:
        raise TemplateDistillError("正向提示词不能为空。")
    aspect = normalize_aspect_ratio_option(aspect_ratio, "1:1")
    if aspect == "auto":
        aspect = "1:1"
    res = resolution if resolution in RUNNINGHUB_RESOLUTIONS else "1k"
    normalized_quality = normalize_runninghub_quality_option(quality)
    image_urls = image_tensor_to_data_urls(reference_images, max_edge=2400) if reference_images is not None else []
    config = resolve_runninghub_config(load_optional_config(config_path))

    begin = time.time()
    status_history: list[dict[str, Any]] = []
    emit_progress("submit", 1, 5, "提交 RunningHub 任务")
    task_id, submit_response, submit_meta = runninghub_submit(
        config,
        clean_prompt,
        aspect,
        res,
        channel=channel,
        quality=normalized_quality,
        image_urls=image_urls,
    )
    print(f"[ComfyUI Imagen Studio] RunningHub task submitted: {task_id}")
    emit_progress("queued", 2, 5, f"RunningHub 任务已提交：{task_id}", "SUBMITTED")
    final_response: dict[str, Any] = {}
    while True:
        if time.time() - begin > timeout_seconds:
            raise TemplateDistillError(f"RunningHub 任务在 {int(timeout_seconds)} 秒后超时。taskId={task_id}")
        query_response = runninghub_query(config, task_id)
        status = extract_runninghub_status(query_response)
        status_history.append({"status": status, "elapsedSeconds": round(time.time() - begin, 3)})
        if status == "SUCCESS":
            final_response = query_response
            break
        if status in ("QUEUED", "RUNNING", "PENDING"):
            print(f"[ComfyUI Imagen Studio] RunningHub task {task_id}: {status}")
            emit_progress("poll", 3, 5, f"RunningHub 生成中：{status}", status)
            if poll_interval > 0:
                time.sleep(poll_interval)
            continue
        if status in ("FAILED", "FAIL", "ERROR", "CANCELED", "CANCELLED"):
            raise TemplateDistillError(f"RunningHub 任务失败：{extract_runninghub_error(query_response)}")
        raise TemplateDistillError(f"RunningHub 返回未知任务状态：{status or '(empty)'}")

    output_url = extract_runninghub_result_url(final_response)
    if not output_url:
        raise TemplateDistillError("RunningHub 任务成功但没有返回结果 URL。")
    emit_progress("download", 4, 5, "下载 RunningHub 结果图像", "SUCCESS")
    image = image_bytes_to_comfy_image(download_bytes(output_url, timeout=120, label="runninghub image download"))
    elapsed = time.time() - begin
    emit_progress("done", 5, 5, "RunningHub 任务完成", "SUCCESS")
    result = {
        "taskId": task_id,
        "status": "SUCCESS",
        "outputUrl": output_url,
        "channel": submit_meta["channel"],
        "mode": submit_meta["mode"],
        "submit_path": submit_meta["submit_path"],
        "quality": submit_meta["quality"],
        "elapsedSeconds": round(elapsed, 3),
        "statusHistory": status_history,
        "submit": submit_response,
        "final": final_response,
    }
    return {
        "image": image,
        "output_url": output_url,
        "task_id": task_id,
        "result_json": json.dumps(result, ensure_ascii=False, indent=2),
    }


def chat_completion(task_config: TaskConfig, messages: list[dict[str, Any]], temperature: float, response_format: dict[str, str] | None = None, timeout: int = 300) -> str:
    if not task_config.model or not task_config.api_key or not task_config.base_url:
        raise TemplateDistillError("模型配置不完整，需要 model、api_key 和 base_url。")
    body: dict[str, Any] = {
        "model": task_config.model,
        "messages": messages,
        "temperature": temperature,
    }
    if response_format:
        body["response_format"] = response_format
    headers = {
        "Authorization": f"Bearer {task_config.api_key}",
        "Content-Type": "application/json",
    }
    url = f"{task_config.base_url}/chat/completions"
    data = post_json(url, headers, body, timeout)
    choice = (data.get("choices") or [{}])[0]
    message = choice.get("message") or {}
    return normalize_chat_content(message.get("content") if "content" in message else choice.get("text"))


def call_with_retry(func, tries: int = 2, base_delay: float = 1.0):
    last_error: Exception | None = None
    for attempt in range(tries):
        try:
            return func()
        except Exception as exc:
            last_error = exc
            if attempt + 1 < tries:
                time.sleep(base_delay * (2**attempt))
    if last_error:
        raise last_error
    raise TemplateDistillError("重试失败，但没有捕获到具体异常。")


def call_agent(
    task_config: TaskConfig,
    system_prompt: str,
    user_content: str | list[dict[str, Any]],
    temperature: float,
    response_format: dict[str, str] | None = None,
    vision_response_format_fallback: bool = False,
) -> Any:
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]

    def call(format_value: dict[str, str] | None):
        raw = call_with_retry(
            lambda: chat_completion(task_config, messages, temperature, response_format=format_value),
            tries=2,
            base_delay=1.0,
        )
        parsed = try_json(raw)
        if parsed is None:
            raise TemplateDistillError(f"模型没有返回可解析的 JSON。原始片段：{str(raw)[:1000]}")
        return parsed

    try:
        return call(response_format)
    except Exception:
        if vision_response_format_fallback and response_format:
            return call(None)
        raise


def image_tensor_to_data_urls(images: Any, max_edge: int = 2400) -> list[str]:
    if images is None:
        return []
    if hasattr(images, "detach"):
        images = images.detach().cpu().numpy()
    array = np.asarray(images)
    if array.ndim == 3:
        array = array[None, ...]
    if array.ndim != 4:
        raise TemplateDistillError(f"需要 ComfyUI IMAGE 张量 [B,H,W,C]，实际形状是 {array.shape}。")

    out: list[str] = []
    for item in array:
        if item.shape[-1] < 3:
            raise TemplateDistillError("图像张量至少需要 3 个通道。")
        rgb = np.clip(item[..., :3] * 255.0, 0, 255).astype(np.uint8)
        image = Image.fromarray(rgb).convert("RGB")
        edge = max(image.size)
        if max_edge and edge > max_edge:
            scale = max_edge / edge
            image = image.resize((max(1, round(image.width * scale)), max(1, round(image.height * scale))), Image.LANCZOS)
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=88, optimize=True)
        encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
        out.append(f"data:image/jpeg;base64,{encoded}")
    return out


def template_library_dir(library_dir: str | Path | None = None) -> Path:
    if library_dir:
        return Path(library_dir)
    return imagen_studio_data_dir() / TEMPLATE_LIBRARY_DIR_NAME


def template_index_path(library_dir: str | Path | None = None) -> Path:
    return template_library_dir(library_dir) / TEMPLATE_INDEX_FILENAME


def template_thumbnail_dir(library_dir: str | Path | None = None) -> Path:
    return template_library_dir(library_dir) / TEMPLATE_THUMBNAIL_DIR_NAME


def ensure_template_library(library_dir: str | Path | None = None) -> Path:
    root = template_library_dir(library_dir)
    root.mkdir(parents=True, exist_ok=True)
    template_thumbnail_dir(root).mkdir(parents=True, exist_ok=True)
    return root


def empty_template_index() -> dict[str, Any]:
    return {"version": 1, "templates": []}


def read_template_index(library_dir: str | Path | None = None) -> dict[str, Any]:
    path = template_index_path(library_dir)
    if not path.exists():
        return empty_template_index()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise TemplateDistillError(f"读取模板库失败：{path}") from exc
    if isinstance(data, list):
        return {"version": 1, "templates": data}
    if not isinstance(data, dict):
        raise TemplateDistillError("模板库 index.json 格式不正确。")
    templates = data.get("templates")
    if not isinstance(templates, list):
        data["templates"] = []
    data["version"] = int(data.get("version") or 1)
    return data


def write_template_index(data: dict[str, Any], library_dir: str | Path | None = None) -> Path:
    root = ensure_template_library(library_dir)
    path = root / TEMPLATE_INDEX_FILENAME
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temp_path, path)
    return path


def clean_template_name(name: Any) -> str:
    return str(name or "").strip() or "未命名模板"


def stable_template_id(name: str, category: str) -> str:
    digest = hashlib.sha1(f"{category}|{name}".encode("utf-8")).hexdigest()[:16]
    return f"tpl-{digest}"


def normalize_template_save_category(value: Any, template: dict[str, Any] | None = None) -> str:
    text = str(value or "").strip()
    if text == "自动":
        text = pick(template, "category", "customCategory", "custom_category")
    if text in CATEGORY_LABEL_EN:
        text = CATEGORY_LABEL_EN[text]
    category = normalize_category_option(text)
    if category in SUPPORTED_CATEGORIES or category in ("ppt", "detail-page"):
        return category
    if text in ("ppt", "detail-page"):
        return text
    return "poster"


def template_category_label(category: str) -> str:
    return CATEGORY_LABEL_CN.get(category, "其他")


def template_description(template: dict[str, Any]) -> str:
    features = as_object(template.get("features"))
    return pick(template, "description") or pick(features, "mood", "lighting", "composition")


def template_tags(template: dict[str, Any]) -> list[str]:
    tags = template.get("tags")
    if isinstance(tags, list):
        return [str(tag).strip() for tag in tags if str(tag or "").strip()]
    return []


def first_image_to_thumbnail_bytes(images: Any, max_edge: int = 512) -> bytes:
    if images is None:
        return b""
    if hasattr(images, "detach"):
        images = images.detach().cpu().numpy()
    array = np.asarray(images)
    if array.ndim == 3:
        array = array[None, ...]
    if array.ndim != 4 or array.shape[0] < 1 or array.shape[-1] < 3:
        raise TemplateDistillError(f"缩略图需要 ComfyUI IMAGE 张量 [B,H,W,C]，实际形状是 {array.shape}。")
    rgb = np.clip(array[0][..., :3] * 255.0, 0, 255).astype(np.uint8)
    image = Image.fromarray(rgb).convert("RGB")
    edge = max(image.size)
    if max_edge and edge > max_edge:
        scale = max_edge / edge
        image = image.resize((max(1, round(image.width * scale)), max(1, round(image.height * scale))), Image.LANCZOS)
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=88, optimize=True)
    return buffer.getvalue()


def save_template_thumbnail(template_id: str, thumbnail: Any, library_dir: str | Path | None = None) -> str:
    data = first_image_to_thumbnail_bytes(thumbnail)
    if not data:
        return ""
    root = ensure_template_library(library_dir)
    relative = f"{TEMPLATE_THUMBNAIL_DIR_NAME}/{template_id}.jpg"
    path = root / relative
    path.write_bytes(data)
    return relative


def resolve_template_thumbnail_path(template_id: str, library_dir: str | Path | None = None) -> Path:
    clean_id = str(template_id or "").strip()
    if not clean_id:
        return template_thumbnail_dir(library_dir) / "__missing__.jpg"
    record = find_template_record(clean_id, library_dir)
    thumbnail_path = str(as_object(record).get("thumbnailPath") or "")
    if thumbnail_path:
        candidate = template_library_dir(library_dir) / thumbnail_path
        if candidate.is_file():
            return candidate
    root = template_thumbnail_dir(library_dir)
    for suffix in (".jpg", ".jpeg", ".png", ".webp"):
        candidate = root / f"{clean_id}{suffix}"
        if candidate.is_file():
            return candidate
    return root / f"{clean_id}.jpg"


def template_thumbnail_url(template_id: str, record: dict[str, Any], library_dir: str | Path | None = None) -> str:
    path = resolve_template_thumbnail_path(template_id, library_dir)
    if path.is_file() or record.get("thumbnailPath"):
        updated = str(record.get("updatedAt") or "")
        suffix = f"&t={updated}" if updated else ""
        return f"/imagen-studio/templates/thumbnail?id={template_id}{suffix}"
    return ""


def find_template_record(template_id: str, library_dir: str | Path | None = None) -> dict[str, Any] | None:
    clean_id = str(template_id or "").strip()
    if not clean_id:
        return None
    index = read_template_index(library_dir)
    for record in index.get("templates", []):
        if as_object(record).get("id") == clean_id:
            return as_object(record)
    return None


def safe_template_library_file(path: Path, library_dir: str | Path | None = None) -> bool:
    try:
        root = template_library_dir(library_dir).resolve()
        candidate = path.resolve()
        return candidate == root or root in candidate.parents
    except Exception:
        return False


def update_template_name(template_id: str, name: str, library_dir: str | Path | None = None) -> dict[str, Any]:
    clean_id = str(template_id or "").strip()
    clean_name = clean_template_name(name)
    if not clean_id:
        raise TemplateDistillError("模板ID不能为空。")
    if not clean_name:
        raise TemplateDistillError("模板名称不能为空。")

    index = read_template_index(library_dir)
    records = [as_object(record) for record in index.get("templates", [])]
    now = int(time.time() * 1000)
    for idx, record in enumerate(records):
        if str(record.get("id") or "") != clean_id:
            continue
        template = dict(as_object(record.get("template")))
        template["name"] = clean_name
        template["updatedAt"] = now
        record["name"] = clean_name
        record["template"] = template
        record["updatedAt"] = now
        records[idx] = record
        index["templates"] = sorted(records, key=lambda item: int(item.get("updatedAt") or 0), reverse=True)
        write_template_index(index, library_dir)
        return record
    raise TemplateDistillError(f"模板库中未找到模板：{clean_id}")


def delete_template_from_library(template_id: str, library_dir: str | Path | None = None) -> dict[str, Any]:
    clean_id = str(template_id or "").strip()
    if not clean_id:
        raise TemplateDistillError("模板ID不能为空。")

    index = read_template_index(library_dir)
    records = [as_object(record) for record in index.get("templates", [])]
    removed: dict[str, Any] | None = None
    remaining: list[dict[str, Any]] = []
    for record in records:
        if str(record.get("id") or "") == clean_id:
            removed = record
        else:
            remaining.append(record)
    if not removed:
        raise TemplateDistillError(f"模板库中未找到模板：{clean_id}")

    thumbnail_path = resolve_template_thumbnail_path(clean_id, library_dir)
    if thumbnail_path.is_file() and safe_template_library_file(thumbnail_path, library_dir):
        try:
            thumbnail_path.unlink()
        except OSError:
            pass

    index["templates"] = remaining
    write_template_index(index, library_dir)
    return removed


def list_saved_template_summaries(library_dir: str | Path | None = None) -> list[dict[str, Any]]:
    index = read_template_index(library_dir)
    summaries: list[dict[str, Any]] = []
    for raw_record in index.get("templates", []):
        record = as_object(raw_record)
        template = as_object(record.get("template"))
        template_id = pick(record, "id") or pick(template, "id")
        if not template_id:
            continue
        category = pick(record, "category") or normalize_template_save_category("自动", template)
        normalized = normalize_template_for_composer(json.dumps(template, ensure_ascii=False))
        summaries.append(
            {
                "id": template_id,
                "name": pick(record, "name") or pick(template, "name") or template_id,
                "category": category,
                "categoryLabel": template_category_label(category),
                "description": pick(record, "description") or template_description(template),
                "tags": record.get("tags") if isinstance(record.get("tags"), list) else template_tags(template),
                "stylePromptEn": normalized["style_prompt_en"],
                "stylePromptZh": normalized["style_prompt_zh"],
                "negativePrompt": normalized["negative_prompt"],
                "thumbnailUrl": template_thumbnail_url(template_id, record, library_dir),
                "createdAt": record.get("createdAt") or template.get("createdAt") or 0,
                "updatedAt": record.get("updatedAt") or template.get("updatedAt") or 0,
            }
        )
    summaries.sort(key=lambda item: int(item.get("updatedAt") or 0), reverse=True)
    return summaries


def save_template_to_library(
    template_json: str,
    name: str = "",
    category: str = "自动",
    thumbnail: Any = None,
    overwrite: bool = True,
    library_dir: str | Path | None = None,
) -> dict[str, Any]:
    template = parse_template_json(template_json)
    if not template:
        raise TemplateDistillError("模板JSON不能为空。")
    template_name = clean_template_name(name or pick(template, "name"))
    category_value = normalize_template_save_category(category, template)
    template_id = stable_template_id(template_name, category_value)
    now = int(time.time() * 1000)

    index = read_template_index(library_dir)
    records = [as_object(record) for record in index.get("templates", [])]
    existing_index = next((idx for idx, record in enumerate(records) if record.get("id") == template_id), -1)
    existing = records[existing_index] if existing_index >= 0 else {}
    if existing and not overwrite:
        raise TemplateDistillError(f"模板已存在：{template_name}。如需更新，请开启覆盖同名。")

    thumbnail_path = save_template_thumbnail(template_id, thumbnail, library_dir) if thumbnail is not None else ""
    if not thumbnail_path:
        thumbnail_path = str(existing.get("thumbnailPath") or "")

    saved_template = dict(template)
    saved_template["id"] = template_id
    saved_template["name"] = template_name
    saved_template["category"] = category_value
    saved_template["folder"] = template_category_label(category_value)
    saved_template["thumbnail"] = f"/imagen-studio/templates/thumbnail?id={template_id}" if thumbnail_path else None
    saved_template["updatedAt"] = now
    saved_template["createdAt"] = existing.get("createdAt") or saved_template.get("createdAt") or now

    record = {
        "id": template_id,
        "name": template_name,
        "category": category_value,
        "categoryLabel": template_category_label(category_value),
        "description": template_description(saved_template),
        "tags": template_tags(saved_template),
        "thumbnailPath": thumbnail_path,
        "template": saved_template,
        "createdAt": saved_template["createdAt"],
        "updatedAt": now,
    }
    if existing_index >= 0:
        records[existing_index] = record
    else:
        records.append(record)
    index["templates"] = sorted(records, key=lambda item: int(item.get("updatedAt") or 0), reverse=True)
    path = write_template_index(index, library_dir)
    return {
        "template_json": json.dumps(saved_template, ensure_ascii=False, indent=2),
        "template_id": template_id,
        "template_name": template_name,
        "save_path": str(path),
        "record": record,
    }


def run_template_select(template_id: str, library_dir: str | Path | None = None) -> dict[str, Any]:
    clean_id = str(template_id or "").strip()
    if not clean_id:
        raise TemplateDistillError("请先在模板选择器中选择一个模板。")
    record = find_template_record(clean_id, library_dir)
    if not record:
        raise TemplateDistillError(f"模板库中未找到模板：{clean_id}")
    template = as_object(record.get("template"))
    if not template:
        raise TemplateDistillError(f"模板记录损坏：{clean_id}")
    normalized = normalize_template_for_composer(json.dumps(template, ensure_ascii=False))
    return {
        "template_json": json.dumps(template, ensure_ascii=False, indent=2),
        "style_prompt_en": normalized["style_prompt_en"],
        "style_prompt_zh": normalized["style_prompt_zh"],
        "negative_prompt": normalized["negative_prompt"],
        "template_name": pick(record, "name") or pick(template, "name"),
    }


def trim_text(value: Any, limit: int) -> str:
    text = str(value or "").strip()
    return text[:limit] if limit > 0 else text


def parse_template_json(template_json: str) -> dict[str, Any]:
    text = str(template_json or "").strip()
    if not text:
        return {}
    parsed = try_json(text)
    if not isinstance(parsed, dict):
        raise TemplateDistillError("模板JSON不是合法 JSON。")
    template = as_object(parsed.get("template"))
    if template and not any(key in parsed for key in ("stylePromptEn", "style_prompt_en", "stylePromptZh", "style_prompt_zh")):
        return template
    return parsed


def normalize_template_for_composer(
    template_json: str,
    style_prompt_en: str = "",
    style_prompt_zh: str = "",
    negative_prompt: str = "",
) -> dict[str, Any]:
    raw = parse_template_json(template_json)
    features = as_object(raw.get("features"))
    style_en = str(style_prompt_en or "").strip() or pick(raw, "stylePromptEn", "style_prompt_en", "promptEn", "prompt_en") or pick(features, "stylePromptEn", "style_prompt_en", "promptEn", "prompt_en")
    style_zh = str(style_prompt_zh or "").strip() or pick(raw, "stylePromptZh", "style_prompt_zh", "promptZh", "prompt_zh") or pick(features, "stylePromptZh", "style_prompt_zh", "promptZh", "prompt_zh")
    negative = str(negative_prompt or "").strip() or pick(raw, "negativePrompt", "negative_prompt", "negative") or pick(features, "negativePrompt", "negative_prompt", "negative")
    return {
        "id": pick(raw, "id"),
        "name": pick(raw, "name"),
        "category": pick(raw, "category", "customCategory", "custom_category"),
        "description": pick(raw, "description"),
        "style_prompt_en": style_en,
        "style_prompt_zh": style_zh,
        "negative_prompt": negative,
        "features": features,
    }


def reference_item_from_agent_result(parsed: Any, index: int) -> dict[str, Any]:
    obj = as_object(parsed)
    return {
        "index": index,
        "description": trim_text(pick(obj, "description"), 800),
        "style_fingerprint": trim_text(pick(obj, "style_fingerprint", "styleFingerprint"), 2400),
        "keep_strict": as_list(obj.get("keep_strict") or obj.get("keepStrict"))[:8],
        "style_keep_strict": as_list(obj.get("style_keep_strict") or obj.get("styleKeepStrict"))[:8],
        "rendering_medium": trim_text(pick(obj, "rendering_medium", "renderingMedium"), 200),
        "composition_type": trim_text(pick(obj, "composition_type", "compositionType"), 150),
        "typography_style": trim_text(pick(obj, "typography_style", "typographyStyle"), 200),
        "has_text": bool(obj.get("has_text") if "has_text" in obj else obj.get("hasText")),
        "dominant_colors": as_list(obj.get("dominant_colors") or obj.get("dominantColors"))[:5],
    }


def analyze_reference_image_urls(data_urls: list[str], vision_config: TaskConfig) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for index, url in enumerate(data_urls[:4]):
        try:
            parsed = call_agent(
                vision_config,
                REFERENCE_ANALYZER_PROMPT,
                [
                    {"type": "text", "text": "Analyze this reference image and return strict JSON."},
                    {"type": "image_url", "image_url": {"url": url}},
                ],
                temperature=0.15,
                response_format={"type": "json_object"},
                vision_response_format_fallback=True,
            )
            item = reference_item_from_agent_result(parsed, index)
            if not item["description"] and not item["style_fingerprint"]:
                raise TemplateDistillError("参考图分析返回了空结果")
            items.append(item)
        except Exception as exc:
            items.append({
                "index": index,
                "description": f"(reference image {index + 1} analysis failed: {str(exc)[:120]})",
                "style_fingerprint": "",
                "keep_strict": [],
                "style_keep_strict": [],
                "rendering_medium": "",
                "composition_type": "",
                "typography_style": "",
                "has_text": False,
                "dominant_colors": [],
            })
    return items


def fallback_compose_prompt(template: dict[str, Any], user_idea: str, aspect_ratio: str, prompt_language: str, reference_items: list[dict[str, Any]]) -> str:
    style = template.get("style_prompt_zh") if prompt_language == "zh" else template.get("style_prompt_en")
    if not style:
        style = template.get("style_prompt_en") or template.get("style_prompt_zh") or ""
    reference_styles = [str(item.get("style_fingerprint") or "").strip() for item in reference_items if str(item.get("style_fingerprint") or "").strip()]
    keep_subject = unique_list([value for item in reference_items for value in as_list(item.get("keep_strict"))])
    keep_style = unique_list([value for item in reference_items for value in as_list(item.get("style_keep_strict"))])
    parts = [
        f"STYLE: {style}" if style else "",
        f"REFERENCE STYLE: {' '.join(reference_styles)[:1800]}" if reference_styles else "",
        f"SUBJECT: {str(user_idea or '').strip()}",
        f"SUBJECT ELEMENTS TO PRESERVE: {'; '.join(keep_subject)}" if keep_subject else "",
        f"STYLE ELEMENTS TO PRESERVE: {'; '.join(keep_style)}" if keep_style else "",
        f"ASPECT RATIO: {aspect_ratio}" if aspect_ratio and aspect_ratio != "auto" else "",
    ]
    return "\n".join(part for part in parts if part)


def normalize_composer_result(parsed: Any, template: dict[str, Any], fallback_prompt: str, fallback_used: bool) -> dict[str, Any]:
    obj = as_object(parsed)
    prompt = pick(obj, "prompt", "positive_prompt", "positivePrompt") or fallback_prompt
    negative = pick(obj, "negative", "negative_prompt", "negativePrompt") or str(template.get("negative_prompt") or "")
    notes = pick(obj, "notes", "note") or ("fallback composition used" if fallback_used else "prompt composed")
    return {
        "prompt": prompt,
        "negative_prompt": negative,
        "notes": notes,
        "fallback_used": fallback_used,
    }


def default_user_idea(template: dict[str, Any]) -> str:
    name = str(template.get("name") or "").strip()
    category = str(template.get("category") or "").strip()
    suffix = " ".join(part for part in (name, category) if part)
    if suffix:
        return f"{DEFAULT_USER_IDEA} Template context: {suffix}."
    return DEFAULT_USER_IDEA


def run_template_compose(
    template_json: str,
    user_idea: str,
    reference_images: Any = None,
    aspect_ratio: str = "auto",
    prompt_language: str = "zh",
    target_model: str = "generic-comfyui",
    style_prompt_en: str = "",
    style_prompt_zh: str = "",
    negative_prompt: str = "",
    config_path: str = "",
    max_edge: int = 2400,
) -> dict[str, Any]:
    aspect = normalize_aspect_ratio_option(aspect_ratio, "auto")
    language = normalize_language_option(prompt_language)
    target = str(target_model or "").strip() or "generic-comfyui"
    template = normalize_template_for_composer(template_json, style_prompt_en, style_prompt_zh, negative_prompt)
    idea = str(user_idea or "").strip() or default_user_idea(template)

    config = load_config(config_path)
    text_config = resolve_task_config(config, "llm")
    data_urls = image_tensor_to_data_urls(reference_images, max_edge=max_edge)[:4]
    reference_items: list[dict[str, Any]] = []
    if data_urls:
        vision_config = resolve_task_config(config, "vlm")
        reference_items = analyze_reference_image_urls(data_urls, vision_config)

    payload = {
        "template": template,
        "user_idea": idea,
        "aspect_ratio": aspect,
        "target_model": target,
        "prompt_language": language,
        "reference_images": reference_items,
    }
    fallback_prompt = fallback_compose_prompt(template, idea, aspect, language, reference_items)
    parsed: dict[str, Any] = {}
    fallback_used = False
    try:
        parsed = call_agent(
            text_config,
            PROMPT_COMPOSER_PROMPT,
            json.dumps(payload, ensure_ascii=False),
            temperature=0.6,
            response_format={"type": "json_object"},
        )
    except Exception:
        fallback_used = True

    normalized = normalize_composer_result(parsed, template, fallback_prompt, fallback_used)
    compose = {
        **payload,
        "prompt": normalized["prompt"],
        "negative_prompt": normalized["negative_prompt"],
        "notes": normalized["notes"],
        "fallback_used": normalized["fallback_used"],
    }
    return {
        "prompt": normalized["prompt"],
        "negative_prompt": normalized["negative_prompt"],
        "notes": normalized["notes"],
        "reference_analysis_json": json.dumps(reference_items, ensure_ascii=False, indent=2),
        "compose_json": json.dumps(compose, ensure_ascii=False, indent=2),
    }


def build_template_json(name: str, category: str, requirements: str, normalized: dict[str, Any]) -> dict[str, Any]:
    features = as_object(normalized.get("features"))
    template_name = str(name or "").strip() or "未命名风格"
    return {
        "id": f"comfyui-{int(time.time() * 1000)}",
        "name": template_name,
        "description": str(features.get("mood") or ""),
        "category": category,
        "customCategory": "",
        "folder": CATEGORY_LABEL_CN.get(category, "其他"),
        "tags": [],
        "requirements": requirements or "",
        "thumbnail": None,
        "features": features,
        "stylePromptEn": normalized.get("stylePromptEn") or "",
        "stylePromptZh": normalized.get("stylePromptZh") or "",
        "negativePrompt": normalized.get("negativePrompt") or "",
        "referenceImages": [],
        "pageStyles": [],
        "createdAt": int(time.time() * 1000),
    }


def run_template_distill(images: Any, category: str, name: str, requirements: str, config_path: str, max_edge: int) -> dict[str, Any]:
    category = normalize_category_option(category)
    data_urls = image_tensor_to_data_urls(images, max_edge=max_edge)
    if not data_urls:
        raise TemplateDistillError("至少需要输入一张参考图像。")

    config = load_config(config_path)
    vision_config = resolve_task_config(config, "vlm")
    text_config = resolve_task_config(config, "llm")
    category_label = CATEGORY_LABEL_CN.get(category, category)
    req_line = f"\n用户的模板需求：{requirements}" if requirements else ""
    category_line = f"\n模板目标类型：{category_label}"

    vision_user = [
        {"type": "text", "text": f"分析以下参考图并输出 style features JSON。{category_line}{req_line}"},
        *[{"type": "image_url", "image_url": {"url": url}} for url in data_urls],
    ]
    features = call_agent(
        vision_config,
        VISION_ANALYZER_PROMPT,
        vision_user,
        temperature=0.3,
        response_format={"type": "json_object"},
        vision_response_format_fallback=True,
    )
    if not isinstance(features, dict) or not features:
        raise TemplateDistillError("视觉模型没有返回可用的风格特征。")

    style: dict[str, Any] = {}
    distill_payload = dict(as_object(features))
    distill_payload["_category"] = category_label
    distill_payload["_requirements"] = requirements or ""
    try:
        style = call_agent(
            text_config,
            TEMPLATE_DISTILLER_PROMPT,
            json.dumps(distill_payload, ensure_ascii=False),
            temperature=0.4,
            response_format={"type": "json_object"},
        )
    except Exception:
        style = {}

    normalized = normalize_generic_analysis_result(features, style)
    template = build_template_json(name, category, requirements, normalized)
    return {
        "style_prompt_en": template["stylePromptEn"],
        "style_prompt_zh": template["stylePromptZh"],
        "negative_prompt": template["negativePrompt"],
        "features_json": json.dumps(template["features"], ensure_ascii=False, indent=2),
        "template_json": json.dumps(template, ensure_ascii=False, indent=2),
    }


def create_comfy_progress_bar(total: int) -> Any:
    try:
        import comfy.utils

        return comfy.utils.ProgressBar(max(1, int(total)))
    except Exception:
        return None


def update_comfy_progress_bar(progress_bar: Any, current: int, total: int | None = None) -> None:
    if progress_bar is None:
        return
    current = max(0, int(current))
    try:
        if total is None:
            progress_bar.update(current)
        else:
            progress_bar.update_absolute(current, max(current, int(total)))
    except TypeError:
        try:
            progress_bar.update_absolute(current)
        except Exception:
            pass
    except Exception:
        pass


def coerce_pipe_value(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        parsed = try_json(value)
        if isinstance(parsed, dict):
            return parsed
    return {}


def pipe_contains_secret_key(value: Any) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            if isinstance(key, str):
                lowered = key.lower()
                if "apikey" in lowered or "api_key" in lowered or "authorization" in lowered:
                    return True
            if pipe_contains_secret_key(item):
                return True
    elif isinstance(value, list):
        return any(pipe_contains_secret_key(item) for item in value)
    return False


def make_imagen_studio_pipe(
    *,
    template_json: str = "",
    template_id: str = "",
    template_name: str = "",
    style_prompt_en: str = "",
    style_prompt_zh: str = "",
    negative_prompt: str = "",
    prompt: str = "",
    notes: str = "",
    compose_json: str = "",
    reference_analysis_json: str = "",
    result_json: str = "",
    task_id: str = "",
    output_url: str = "",
    user_idea: str = "",
    aspect_ratio: str = "auto",
    prompt_language: str = "zh",
    target_model: str = "generic-comfyui",
    save_path: str = "",
    source: str = "",
    template: dict[str, Any] | None = None,
    runninghub: dict[str, Any] | None = None,
) -> dict[str, Any]:
    template_obj = as_object(template)
    if not template_obj and template_json:
        template_obj = parse_template_json(template_json)
    normalized = normalize_template_for_composer(
        json.dumps(template_obj or {}, ensure_ascii=False),
        style_prompt_en=style_prompt_en,
        style_prompt_zh=style_prompt_zh,
        negative_prompt=negative_prompt,
    )
    clean_template_json = template_json.strip() if isinstance(template_json, str) else ""
    if not clean_template_json and template_obj:
        clean_template_json = json.dumps(template_obj, ensure_ascii=False, indent=2)

    pipe = {
        "pipe_type": IMAGEN_STUDIO_PIPE_TYPE,
        "version": IMAGEN_STUDIO_PIPE_VERSION,
        "template_id": str(template_id or pick(template_obj, "id") or "").strip(),
        "template_name": str(template_name or pick(template_obj, "name") or "").strip(),
        "template_json": clean_template_json,
        "template": template_obj,
        "style_prompt_en": normalized["style_prompt_en"],
        "style_prompt_zh": normalized["style_prompt_zh"],
        "negative_prompt": normalized["negative_prompt"],
        "prompt": str(prompt or "").strip(),
        "notes": str(notes or "").strip(),
        "compose_json": str(compose_json or "").strip(),
        "reference_analysis_json": str(reference_analysis_json or "").strip(),
        "result_json": str(result_json or "").strip(),
        "task_id": str(task_id or "").strip(),
        "output_url": str(output_url or "").strip(),
        "user_idea": str(user_idea or "").strip(),
        "aspect_ratio": str(aspect_ratio or "").strip(),
        "prompt_language": str(prompt_language or "").strip(),
        "target_model": str(target_model or "").strip(),
        "save_path": str(save_path or "").strip(),
        "source": str(source or "").strip(),
    }
    if runninghub is not None:
        pipe["runninghub"] = as_object(runninghub)
    if pipe_contains_secret_key(pipe):
        raise TemplateDistillError("模板束中不应包含 API Key。")
    return pipe


def resolve_template_pipe(template_pipe: Any, template_id: str, library_dir: str | Path | None = None) -> dict[str, Any]:
    pipe = coerce_pipe_value(template_pipe)
    candidate_id = str(template_id or pipe.get("template_id") or "").strip()
    if pipe:
        template_json = str(pipe.get("template_json") or "").strip()
        if not template_json:
            template_obj = as_object(pipe.get("template"))
            if template_obj:
                template_json = json.dumps(template_obj, ensure_ascii=False, indent=2)
        if template_json:
            pipe["template_json"] = template_json
            if candidate_id and not str(pipe.get("template_id") or "").strip():
                pipe["template_id"] = candidate_id
            if not str(pipe.get("template_name") or "").strip():
                pipe["template_name"] = str(pipe.get("name") or candidate_id or "").strip()
            return pipe
    if not candidate_id:
        raise TemplateDistillError("请先选择模板或连接模板束。")
    selected = run_template_select(candidate_id, library_dir=library_dir)
    return make_imagen_studio_pipe(
        template_id=candidate_id,
        template_name=selected["template_name"],
        template_json=selected["template_json"],
        style_prompt_en=selected["style_prompt_en"],
        style_prompt_zh=selected["style_prompt_zh"],
        negative_prompt=selected["negative_prompt"],
        source="template-selector",
    )


def copy_pipe_extra_fields(target: dict[str, Any], source: dict[str, Any]) -> dict[str, Any]:
    for key in ("features_json",):
        if source.get(key):
            target[key] = source[key]
    return target


def run_template_distill_pipe(images: Any, category: str, name: str, requirements: str, config_path: str, max_edge: int = 2400) -> dict[str, Any]:
    distilled = run_template_distill(images, category, name, requirements, config_path, max_edge)
    pipe = make_imagen_studio_pipe(
        template_json=distilled["template_json"],
        style_prompt_en=distilled["style_prompt_en"],
        style_prompt_zh=distilled["style_prompt_zh"],
        negative_prompt=distilled["negative_prompt"],
        source="template-distill",
    )
    pipe["features_json"] = distilled["features_json"]
    return {
        "pipe": pipe,
        **distilled,
    }


def run_template_ingest(
    template_pipe: Any,
    overwrite: bool = True,
    thumbnail: Any = None,
) -> dict[str, Any]:
    base_pipe = resolve_template_pipe(template_pipe, "")
    template_json = str(base_pipe.get("template_json") or "").strip()
    if not template_json:
        raise TemplateDistillError("模板束中缺少模板JSON，无法入库。")

    saved = save_template_to_library(
        template_json=template_json,
        name=str(base_pipe.get("template_name") or "").strip(),
        category="自动",
        thumbnail=thumbnail,
        overwrite=overwrite,
    )
    output_pipe = make_imagen_studio_pipe(
        template_json=saved["template_json"],
        template_id=saved["template_id"],
        template_name=saved["template_name"],
        style_prompt_en=str(base_pipe.get("style_prompt_en") or "").strip(),
        style_prompt_zh=str(base_pipe.get("style_prompt_zh") or "").strip(),
        negative_prompt=str(base_pipe.get("negative_prompt") or "").strip(),
        prompt=str(base_pipe.get("prompt") or "").strip(),
        notes=str(base_pipe.get("notes") or "").strip(),
        compose_json=str(base_pipe.get("compose_json") or "").strip(),
        reference_analysis_json=str(base_pipe.get("reference_analysis_json") or "").strip(),
        result_json=str(base_pipe.get("result_json") or "").strip(),
        task_id=str(base_pipe.get("task_id") or "").strip(),
        output_url=str(base_pipe.get("output_url") or "").strip(),
        user_idea=str(base_pipe.get("user_idea") or "").strip(),
        aspect_ratio=str(base_pipe.get("aspect_ratio") or "auto").strip(),
        prompt_language=str(base_pipe.get("prompt_language") or "zh").strip(),
        target_model=str(base_pipe.get("target_model") or "generic-comfyui").strip(),
        save_path=saved["save_path"],
        source="template-ingest",
        runninghub=as_object(base_pipe.get("runninghub")),
    )
    copy_pipe_extra_fields(output_pipe, base_pipe)
    return {
        "pipe": output_pipe,
        "template_id": saved["template_id"],
        "template_name": saved["template_name"],
        "save_path": saved["save_path"],
    }


def run_template_select_pipe(template_id: str, library_dir: str | Path | None = None) -> dict[str, Any]:
    selected = run_template_select(template_id, library_dir=library_dir)
    pipe = make_imagen_studio_pipe(
        template_id=str(template_id or "").strip(),
        template_name=selected["template_name"],
        template_json=selected["template_json"],
        style_prompt_en=selected["style_prompt_en"],
        style_prompt_zh=selected["style_prompt_zh"],
        negative_prompt=selected["negative_prompt"],
        source="template-selector",
    )
    return {"pipe": pipe, **selected}


def run_template_compose_pipe(
    template_pipe: Any,
    user_idea: str,
    reference_images: Any = None,
    aspect_ratio: str = "auto",
    prompt_language: str = "zh",
    config_path: str = "",
    max_edge: int = 2400,
) -> dict[str, Any]:
    base_pipe = resolve_template_pipe(template_pipe, "")
    template_json = str(base_pipe.get("template_json") or "").strip()
    if not template_json:
        raise TemplateDistillError("模板束中缺少模板JSON，无法拼装。")

    compose = run_template_compose(
        template_json=template_json,
        user_idea=user_idea,
        reference_images=reference_images,
        aspect_ratio=aspect_ratio,
        prompt_language=prompt_language,
        target_model="generic-comfyui",
        style_prompt_en=str(base_pipe.get("style_prompt_en") or "").strip(),
        style_prompt_zh=str(base_pipe.get("style_prompt_zh") or "").strip(),
        negative_prompt=str(base_pipe.get("negative_prompt") or "").strip(),
        config_path=config_path,
        max_edge=max_edge,
    )
    output_pipe = make_imagen_studio_pipe(
        template_json=template_json,
        template_id=str(base_pipe.get("template_id") or "").strip(),
        template_name=str(base_pipe.get("template_name") or "").strip(),
        style_prompt_en=str(base_pipe.get("style_prompt_en") or "").strip(),
        style_prompt_zh=str(base_pipe.get("style_prompt_zh") or "").strip(),
        negative_prompt=compose["negative_prompt"],
        prompt=compose["prompt"],
        notes=compose["notes"],
        compose_json=compose["compose_json"],
        reference_analysis_json=compose["reference_analysis_json"],
        result_json=str(base_pipe.get("result_json") or "").strip(),
        task_id=str(base_pipe.get("task_id") or "").strip(),
        output_url=str(base_pipe.get("output_url") or "").strip(),
        user_idea=user_idea,
        aspect_ratio=normalize_aspect_ratio_option(aspect_ratio, "auto"),
        prompt_language=normalize_language_option(prompt_language),
        target_model="generic-comfyui",
        save_path=str(base_pipe.get("save_path") or "").strip(),
        source="template-compose",
        runninghub=as_object(base_pipe.get("runninghub")),
    )
    copy_pipe_extra_fields(output_pipe, base_pipe)
    return {
        "pipe": output_pipe,
        "prompt": compose["prompt"],
        "negative_prompt": compose["negative_prompt"],
        "notes": compose["notes"],
        "compose_json": compose["compose_json"],
    }


def run_runninghub_pipe(
    template_pipe: Any,
    prompt_override: str = "",
    aspect_ratio: str = "1:1",
    resolution: str = "1k",
    config_path: str = "",
    channel: str = "third_party",
    quality: str = RUNNINGHUB_DEFAULT_QUALITY,
    reference_images: Any = None,
    progress_callback: Any = None,
) -> dict[str, Any]:
    base_pipe = coerce_pipe_value(template_pipe)
    if not base_pipe:
        raise TemplateDistillError("请先连接模板束。")
    prompt = str(prompt_override or base_pipe.get("prompt") or "").strip()
    if not prompt:
        raise TemplateDistillError("模板束中缺少正向提示词，请先连接模板拼装节点。")

    runninghub = run_runninghub_rhart_g2(
        prompt=prompt,
        aspect_ratio=aspect_ratio,
        resolution=resolution,
        config_path=config_path,
        channel=channel,
        quality=quality,
        reference_images=reference_images,
        progress_callback=progress_callback,
    )
    runninghub_result = try_json(runninghub["result_json"]) or {}
    output_pipe = make_imagen_studio_pipe(
        template_json=str(base_pipe.get("template_json") or "").strip(),
        template_id=str(base_pipe.get("template_id") or "").strip(),
        template_name=str(base_pipe.get("template_name") or "").strip(),
        style_prompt_en=str(base_pipe.get("style_prompt_en") or "").strip(),
        style_prompt_zh=str(base_pipe.get("style_prompt_zh") or "").strip(),
        negative_prompt=str(base_pipe.get("negative_prompt") or "").strip(),
        prompt=prompt,
        notes=str(base_pipe.get("notes") or "").strip(),
        compose_json=str(base_pipe.get("compose_json") or "").strip(),
        reference_analysis_json=str(base_pipe.get("reference_analysis_json") or "").strip(),
        result_json=runninghub["result_json"],
        task_id=runninghub["task_id"],
        output_url=runninghub["output_url"],
        user_idea=str(base_pipe.get("user_idea") or "").strip(),
        aspect_ratio=normalize_aspect_ratio_option(aspect_ratio, "1:1"),
        prompt_language=str(base_pipe.get("prompt_language") or "").strip(),
        target_model=str(base_pipe.get("target_model") or "generic-comfyui").strip(),
        save_path=str(base_pipe.get("save_path") or "").strip(),
        source="runninghub-rhart-g2",
        runninghub={
            "task_id": runninghub["task_id"],
            "output_url": runninghub["output_url"],
            "result_json": runninghub["result_json"],
            "channel": str(runninghub_result.get("channel") or normalize_runninghub_channel_option(channel)),
            "mode": str(runninghub_result.get("mode") or ("image-to-image" if reference_images is not None else "text-to-image")),
            "submit_path": str(runninghub_result.get("submit_path") or ""),
            "quality": str(runninghub_result.get("quality") or normalize_runninghub_quality_option(quality)),
        },
    )
    copy_pipe_extra_fields(output_pipe, base_pipe)
    return {
        "image": runninghub["image"],
        "pipe": output_pipe,
        "output_url": runninghub["output_url"],
        "task_id": runninghub["task_id"],
        "result_json": runninghub["result_json"],
    }


class ImagenStudioTemplateDistiller:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "参考图像": ("IMAGE", {"tooltip": "用于提取模板风格的一张或多张参考图。"}),
                "模板类型": (CATEGORY_OPTIONS_CN, {"default": "海报", "tooltip": "选择模板的大类，内部会映射为原始英文类型。"}),
                "模板名称": ("STRING", {"default": "", "multiline": False, "placeholder": "可选，例如：夏季果茶海报", "tooltip": "写入返回的模板JSON，留空会自动命名。"}),
                "模板需求": ("STRING", {"default": "", "multiline": True, "placeholder": "可选，补充你希望保留或强调的模板风格要求。", "tooltip": "只作为风格蒸馏约束。"}),
                "配置路径": ("STRING", {"default": "", "multiline": False, "placeholder": "留空使用节点目录 config.json", "tooltip": "可选，指向独立 config.json 或包含 config.json 的目录。"}),
                "最长边": ("INT", {"default": 2400, "min": 512, "max": 4096, "step": 64, "tooltip": "发送给视觉模型前压缩参考图的最长边。"}),
            }
        }

    RETURN_TYPES = (IMAGEN_STUDIO_PIPE_TYPE, "STRING", "STRING", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("模板束", "模板JSON", "英文风格提示词", "中文风格提示词", "负面提示词", "视觉特征JSON")
    FUNCTION = "distill"
    CATEGORY = NODE_CATEGORY_CN
    DESCRIPTION = "从参考图中蒸馏可复用的视觉模板风格，主输出为模板束，同时保留文本调试输出。"
    OUTPUT_TOOLTIPS = (
        "包含模板JSON、风格词和视觉特征的 Imagen Studio 节点束。",
        "蒸馏得到的完整模板JSON。",
        "英文风格提示词。",
        "中文风格提示词。",
        "模板负面提示词。",
        "视觉模型抽取的结构化特征JSON。",
    )

    def distill(self, **kwargs):
        result = run_template_distill_pipe(
            read_input_value(kwargs, "参考图像", None),
            read_input_value(kwargs, "模板类型", "海报"),
            read_input_value(kwargs, "模板名称", ""),
            read_input_value(kwargs, "模板需求", ""),
            read_input_value(kwargs, "配置路径", ""),
            int(read_input_value(kwargs, "最长边", 2400) or 2400),
        )
        return (
            result["pipe"],
            result["template_json"],
            result["style_prompt_en"],
            result["style_prompt_zh"],
            result["negative_prompt"],
            result["features_json"],
        )


class ImagenStudioTemplateIngest:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "模板束": (IMAGEN_STUDIO_PIPE_TYPE, {"tooltip": "连接“模板蒸馏”或其他 Imagen Studio 节点输出的模板束。"}),
                "覆盖同名": ("BOOLEAN", {"default": True, "tooltip": "开启后，同名同类型模板会更新，不会重复新增。"}),
            },
            "optional": {
                "缩略图": ("IMAGE", {"tooltip": "可选，连接参考图或生成图保存为模板卡片缩略图。"}),
            },
        }

    RETURN_TYPES = (IMAGEN_STUDIO_PIPE_TYPE, "STRING", "STRING", "STRING")
    RETURN_NAMES = ("模板束", "模板ID", "模板名称", "保存路径")
    FUNCTION = "ingest"
    CATEGORY = NODE_CATEGORY_CN
    OUTPUT_NODE = True
    DESCRIPTION = "把模板束保存到当前 ComfyUI 节点目录的本地模板库。"
    OUTPUT_TOOLTIPS = (
        "写入模板库后的模板束。",
        "模板库中的稳定模板ID。",
        "模板库展示名称。",
        "模板库 index.json 的保存路径。",
    )

    def ingest(self, **kwargs):
        result = run_template_ingest(
            template_pipe=read_input_value(kwargs, "模板束", None),
            overwrite=bool(read_input_value(kwargs, "覆盖同名", True)),
            thumbnail=read_input_value(kwargs, "缩略图", None),
        )
        return (
            result["pipe"],
            result["template_id"],
            result["template_name"],
            result["save_path"],
        )


class ImagenStudioTemplateSelector:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "模板ID": ("STRING", {"default": "", "multiline": False, "placeholder": "在下方模板卡片中选择，或手动输入模板ID。", "tooltip": "工作流保存时会记录这个模板ID。"}),
            }
        }

    RETURN_TYPES = (IMAGEN_STUDIO_PIPE_TYPE, "STRING", "STRING", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("模板束", "模板JSON", "英文风格提示词", "中文风格提示词", "负面提示词", "模板名称")
    FUNCTION = "select"
    CATEGORY = NODE_CATEGORY_CN
    DESCRIPTION = "从本地模板库选择已保存模板，主输出为模板束，同时保留文本调试输出。"
    OUTPUT_TOOLTIPS = (
        "包含已选模板信息的 Imagen Studio 节点束。",
        "可用于调试或兼容的模板JSON。",
        "模板中的英文风格提示词。",
        "模板中的中文风格提示词。",
        "模板中的负面提示词。",
        "当前选择的模板名称。",
    )

    def select(self, **kwargs):
        result = run_template_select_pipe(read_input_value(kwargs, "模板ID", ""))
        return (
            result["pipe"],
            result["template_json"],
            result["style_prompt_en"],
            result["style_prompt_zh"],
            result["negative_prompt"],
            result["template_name"],
        )


class ImagenStudioTemplateComposer:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "模板束": (IMAGEN_STUDIO_PIPE_TYPE, {"tooltip": "连接“模板蒸馏”或“模板选择器”的模板束输出。"}),
                "用户需求": ("STRING", {"default": DEFAULT_USER_IDEA, "multiline": True, "placeholder": "描述这次要生成或还原的新主体、新画面和具体要求。", "tooltip": "最终画面的主体和创意需求来自这里。"}),
                "画面比例": (ASPECT_RATIO_OPTIONS_CN, {"default": "自动", "tooltip": "写入最终提示词的画面比例意图。"}),
                "提示词语言": (LANGUAGE_OPTIONS_CN, {"default": "中文", "tooltip": "控制最终正向提示词使用中文或英文。"}),
                "配置路径": ("STRING", {"default": "", "multiline": False, "placeholder": "留空使用节点目录 config.json", "tooltip": "可选，指向独立 config.json 或包含 config.json 的目录。"}),
                "最长边": ("INT", {"default": 2400, "min": 512, "max": 4096, "step": 64, "tooltip": "发送参考图给视觉模型前压缩图像的最长边。"}),
            },
            "optional": {
                "参考图像": ("IMAGE", {"tooltip": "可选，最多分析4张，用于补充本次拼装的参考图风格。"}),
            },
        }

    RETURN_TYPES = (IMAGEN_STUDIO_PIPE_TYPE, "STRING", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("模板束", "正向提示词", "负面提示词", "拼装说明", "拼装JSON")
    FUNCTION = "compose"
    CATEGORY = NODE_CATEGORY_CN
    DESCRIPTION = "把模板束、用户需求和可选参考图拼装成最终生图提示词，并写回模板束。"
    OUTPUT_TOOLTIPS = (
        "写入正向提示词、负面词和拼装JSON后的模板束。",
        "最终正向提示词。",
        "最终负面提示词。",
        "本次拼装的简短说明。",
        "完整拼装过程JSON，便于调试。",
    )

    def compose(self, **kwargs):
        result = run_template_compose_pipe(
            template_pipe=read_input_value(kwargs, "模板束", None),
            user_idea=read_input_value(kwargs, "用户需求", ""),
            reference_images=read_input_value(kwargs, "参考图像", None),
            aspect_ratio=read_input_value(kwargs, "画面比例", "自动"),
            prompt_language=read_input_value(kwargs, "提示词语言", "中文"),
            config_path=read_input_value(kwargs, "配置路径", ""),
            max_edge=int(read_input_value(kwargs, "最长边", 2400) or 2400),
        )
        return (
            result["pipe"],
            result["prompt"],
            result["negative_prompt"],
            result["notes"],
            result["compose_json"],
        )


class ImagenStudioRunningHubRHArtG2:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "模板束": (IMAGEN_STUDIO_PIPE_TYPE, {"tooltip": "连接“模板拼装”的模板束输出。"}),
                "渠道": (RUNNINGHUB_CHANNEL_OPTIONS_CN, {"default": "第三方低价渠道", "tooltip": "选择 RunningHub 第三方低价渠道或官方渠道。"}),
                "画面比例": (ASPECT_RATIO_OPTIONS_CN, {"default": "1:1", "tooltip": "发送给 RunningHub 的 aspectRatio；自动会按 1:1 处理。"}),
                "分辨率": (RUNNINGHUB_RESOLUTIONS, {"default": "1k", "tooltip": "发送给 RunningHub 的 resolution。"}),
                "质量": (RUNNINGHUB_QUALITY_OPTIONS, {"default": RUNNINGHUB_DEFAULT_QUALITY, "tooltip": "发送给 RunningHub 的 quality，支持 low / medium / high。"}),
                "配置路径": ("STRING", {"default": "", "multiline": False, "placeholder": "留空使用节点目录 config.json", "tooltip": "可选，指向包含 runninghubApiKey 的独立配置文件或目录。"}),
            },
            "optional": {
                "参考图像": ("IMAGE", {"tooltip": "可选，连接后自动切换为图生图，并把整批图片作为 imageUrls 发送给 RunningHub。"}),
                "正向提示词": ("STRING", {"default": "", "multiline": True, "placeholder": "可选，非空时覆盖模板束中的正向提示词。", "tooltip": "手动覆盖发送给 RunningHub RHArt G2 的 prompt。"}),
            },
        }

    RETURN_TYPES = ("IMAGE", IMAGEN_STUDIO_PIPE_TYPE, "STRING", "STRING", "STRING")
    RETURN_NAMES = ("图像", "模板束", "结果URL", "任务ID", "结果JSON")
    FUNCTION = "generate"
    CATEGORY = NODE_CATEGORY_CN
    OUTPUT_NODE = True
    DESCRIPTION = "读取模板束中的正向提示词，按所选渠道调用 RunningHub RHArt G2；未接参考图像时走文生图，接入参考图像时自动切换为图生图，并支持 low / medium / high 质量档位。"
    OUTPUT_TOOLTIPS = (
        "下载后的 ComfyUI IMAGE。",
        "写入 RunningHub taskId 和结果URL后的模板束。",
        "RunningHub 返回的第一张结果图URL。",
        "RunningHub 任务ID。",
        "提交和查询摘要JSON，不包含 API Key。",
    )

    def generate(self, **kwargs):
        progress_bar = create_comfy_progress_bar(5)

        def progress_callback(**info):
            update_comfy_progress_bar(progress_bar, int(info.get("current") or 0), int(info.get("total") or 5))

        result = run_runninghub_pipe(
            template_pipe=read_input_value(kwargs, "模板束", None),
            prompt_override=read_input_value(kwargs, "正向提示词", ""),
            channel=read_input_value(kwargs, "渠道", "第三方低价渠道"),
            aspect_ratio=read_input_value(kwargs, "画面比例", "1:1"),
            resolution=read_input_value(kwargs, "分辨率", "1k"),
            quality=read_input_value(kwargs, "质量", RUNNINGHUB_DEFAULT_QUALITY),
            config_path=read_input_value(kwargs, "配置路径", ""),
            reference_images=read_input_value(kwargs, "参考图像", None),
            progress_callback=progress_callback,
        )
        return (
            result["image"],
            result["pipe"],
            result["output_url"],
            result["task_id"],
            result["result_json"],
        )


NODE_CLASS_MAPPINGS = {
    "ImagenStudioTemplateDistiller": ImagenStudioTemplateDistiller,
    "ImagenStudioTemplateIngest": ImagenStudioTemplateIngest,
    "ImagenStudioTemplateSelector": ImagenStudioTemplateSelector,
    "ImagenStudioTemplateComposer": ImagenStudioTemplateComposer,
    "ImagenStudioRunningHubRHArtG2": ImagenStudioRunningHubRHArtG2,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "ImagenStudioTemplateDistiller": "Imagen Studio 模板蒸馏",
    "ImagenStudioTemplateIngest": "Imagen Studio 模板入库",
    "ImagenStudioTemplateSelector": "Imagen Studio 模板选择器",
    "ImagenStudioTemplateComposer": "Imagen Studio 模板拼装",
    "ImagenStudioRunningHubRHArtG2": "Imagen Studio RunningHub 生图",
}
