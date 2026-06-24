import html
import importlib.util
import io
import json
import os
import re
import sys
import time
import zipfile
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image


def _load_imagen_studio():
    if "imagen_studio" in sys.modules:
        return sys.modules["imagen_studio"]
    path = Path(__file__).with_name("imagen_studio.py")
    spec = importlib.util.spec_from_file_location("imagen_studio", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("无法加载 Imagen Studio 基础模块。")
    module = importlib.util.module_from_spec(spec)
    sys.modules["imagen_studio"] = module
    spec.loader.exec_module(module)
    return module


studio = _load_imagen_studio()
TemplateDistillError = studio.TemplateDistillError


IMAGEN_PPT_PIPE_TYPE = "IMAGEN_PPT_PIPE"
IMAGEN_PPT_PIPE_VERSION = 1
NODE_CATEGORY_CN = "Imagen Studio/PPT工具"
PPT_ASPECT_OPTIONS_CN = ("自动", "16:9", "4:3", "1:1", "9:16")
PPT_ROLE_OPTIONS = ("cover", "toc", "section", "content", "data", "quote", "image-focus", "closing", "thanks")
PPT_DEFAULT_ROLES = ["cover", "section", "content", "data", "closing"]
PPT_EXPORT_DIR_NAME = "ppt-exports"
CONTENT_PAGE_MAX_CHARS = 700
CONTENT_PAGE_MAX_LINES = 10


PPT_OUTLINE_DRAFTER_PROMPT = """你是 PPT 内容策划师。输入：
- user_idea: 用户想法（可空）
- selected_pages: 可用页面角色参考数组（cover/toc/section/content/data/quote/thanks），只用于参考，不决定页数
- style_hint: 可选，模板名称/风格提示
- existing_content: 用户已编写的大纲内容（可空）

请输出严格 JSON（不要 Markdown 代码块）：
{
  "content": "Markdown 大纲文本",
  "outline": ["按最终 Markdown 大纲逐行拆分"],
  "notes": "<=30字中文，说明如何润色/组织"
}

Markdown 大纲规则：
1. content 必须使用 Markdown 标题层级组织。
2. # 一级标题 = 封面页，只用于整套 PPT 标题。
3. ## 二级标题 = 章节页，用于业务回顾、方案介绍、未来规划等章节。
4. ### 三级标题 + 下面内容 = 内容页，正文、列表、数据句写在对应 ### 下。
5. 不要为了模板里有目录/鸣谢/结束页就主动添加这些页面；只有用户内容或 user_idea 明确需要时才添加。

任务规则：
1. 若 existing_content 非空，只能基于已有内容润色、补充和结构化为 Markdown 大纲，保留用户的核心信息、顺序和语气，不要另起炉灶。
2. 若 existing_content 为空但 user_idea 非空，根据 user_idea 生成一份简洁可用的 Markdown 大纲。
3. 若 selected_pages 包含 data 且用户内容需要数据表达，至少给出 2 条带数字的数据点。
4. 文案应简洁、可读、可直接用于图像排版渲染。"""


PPT_DESIGN_BRIEF_PROMPT = """你是一位专业的视觉设计总监。你将收到一份 PPT 演示文稿的完整信息：
- user_idea: 用户对这组 PPT 的主题/想法描述
- outline: 完整大纲（包含所有页的标题和内容摘要）
- total_pages: 总页数
- aspect_ratio: 画面比例
- prompt_language: 输出语言偏好 (zh/en)
- reference_images: 参考图分析结果数组（可能为空）

你的任务是生成一份统一的视觉设计规范 (Design Brief)，确保后续每一页的图片生成都遵循同一套视觉语言。

输出严格的 JSON（不要 Markdown 代码块）：
{
  "visual_theme": "一句话概括整体视觉主题（≤100 字）",
  "color_palette": {
    "primary": "#hex — 主色",
    "secondary": "#hex — 辅助色",
    "accent": "#hex — 点缀色",
    "background_tone": "背景色调描述"
  },
  "style_keywords": ["关键词1", "关键词2"],
  "decoration_elements": "统一的装饰元素描述（≤150 字）",
  "composition_principles": "构图原则（≤150 字）",
  "atmosphere": "整体氛围（≤80 字）",
  "consistency_rules": "跨页一致性规则（≤200 字）",
  "page_rhythm": "页面节奏建议（≤150 字）"
}

规则：
1. 如果有 reference_images，优先从参考图中提取视觉基调，然后扩展为完整规范。
2. color_palette 必须互相协调，适合长时间观看。
3. style_keywords 应该是可直接用于 image generation prompt 的描述词，5~8 个。
4. 所有文字字段用 prompt_language 指定的语言输出。
5. 不要返回任何 JSON 之外的内容。"""


PPT_PAGE_COMPOSER_PROMPT = """你为“文生图 PPT 页面”服务。输入：
- page_style: { name, role, layoutDescription, style_prompt_en, style_prompt_zh, negative_prompt }
- user_idea: 用户对整体风格/调性的想法（可空）
- user_content: 用户提供的该页文案（可能含标题、副标题、正文要点、数据等，中英混合）
- aspect_ratio: 如 "16:9"
- target_model: "generic-comfyui"
- prompt_language: "zh" | "en"
- reference_images: 数组 { index, description, keep_strict[] }，可能为空

你的目标：写一段提示词，让模型生成一整张 PPT 页面（含真实可读文字排版），既还原 page_style 的版式与风格，又把 user_content 嵌入到正确位置。

严格输出 JSON：
{
  "prompt": "提示词。结构：STYLE；单页演示文稿说明；按 layoutDescription 描述版面；所有真实文本用双引号包起逐字渲染；STYLE ELEMENTS TO PRESERVE；SUBJECT ELEMENTS TO PRESERVE。",
  "negative": "英文负面词，继承 page_style.negative_prompt 并补充 misspelled text, garbled characters, blurry typography",
  "notes": "≤30 字中文说明"
}

规则：
1. prompt_language="zh" 时 prompt 用中文，="en" 时用英文。
2. style_fingerprint 必须原样保留，禁止概括成笼统风格。
3. 必须显式列出用户的每一条文本，并用双引号包住。
4. 保留 layoutDescription 的构图与留白。
5. 不要输出 Markdown、不要额外解释。

如果输入 JSON 中包含 design_brief，必须遵循其中的配色、装饰元素、构图原则、页面节奏和跨页一致性规则。
如果输入 JSON 中包含 page_position，根据封面/中间页/尾页自然调整视觉强度。"""


PPT_FREEFORM_COMPOSER_PROMPT = """你为“文生图 PPT 页面”服务（无既有模板）。输入：
- user_idea: 用户对整体风格/调性的想法（可能为空）
- slide_role: 用户指定的页面角色（cover/toc/section/content/data/quote/thanks）
- user_content: 本页要呈现的文案（标题、副标题、要点、数据等）
- aspect_ratio: 如 "16:9"
- target_model: "generic-comfyui"
- prompt_language: "zh" | "en"
- reference_images: 数组 { index, description, keep_strict[] }（可能为空）

产出一段提示词，让模型生成一整张 PPT 页面（含文字排版）。若 user_idea 为空，自行推断专业商务风。

严格输出 JSON：
{
  "prompt": "提示词。结构：STYLE；单张演示文稿页面和 slide_role；整体版面；真实文本用双引号包起；参考图保留项。",
  "negative": "英文负面词 + misspelled text, garbled characters, blurry typography",
  "notes": "≤30 字中文说明"
}

规则：prompt_language="zh" 时 prompt 用中文，="en" 时用英文；不要 Markdown、不要解释；用户的每条真实文本必须用双引号包起。
如果输入 JSON 中包含 design_brief，必须遵循其中的配色、装饰元素、构图原则、页面节奏和跨页一致性规则。"""


def pick(obj: Any, *keys: str) -> str:
    return studio.pick(obj, *keys)


def as_object(value: Any) -> dict[str, Any]:
    return studio.as_object(value)


def as_list(value: Any) -> list[str]:
    return studio.as_list(value)


def normalize_language(value: Any) -> str:
    return studio.normalize_language_option(value)


def normalize_aspect(value: Any, default: str = "16:9") -> str:
    aspect = studio.normalize_aspect_ratio_option(value, default)
    return default if aspect == "auto" else aspect


def read_input(inputs: dict[str, Any], name: str, default: Any = "") -> Any:
    return inputs[name] if name in inputs else default


def coerce_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        parsed = studio.try_json(value)
        if isinstance(parsed, dict):
            return parsed
    return {}


def pipe_contains_secret(value: Any) -> bool:
    return studio.pipe_contains_secret_key(value)


def resolve_template_from_pipe(template_pipe: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    pipe = studio.coerce_pipe_value(template_pipe)
    template = as_object(pipe.get("template"))
    if not template and pipe.get("template_json"):
        template = studio.parse_template_json(str(pipe.get("template_json") or ""))
    return pipe, template


def get_template_page_styles(template: dict[str, Any]) -> list[dict[str, Any]]:
    raw = template.get("pageStyles")
    if isinstance(raw, list) and raw:
        return [normalize_page_style(item) for item in raw if isinstance(item, dict)]
    if template:
        return [normalize_page_style({
            "id": "__template_style__",
            "name": f"{pick(template, 'name') or '模板'} 整体风格",
            "role": "content",
            "layoutDescription": pick(template, "requirements", "description") or "参考该模板的整体视觉风格生成页面。",
            "stylePromptEn": pick(template, "stylePromptEn", "style_prompt_en"),
            "stylePromptZh": pick(template, "stylePromptZh", "style_prompt_zh"),
            "negativePrompt": pick(template, "negativePrompt", "negative_prompt", "negative"),
        })]
    return []


def normalize_page_style(style: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": pick(style, "id") or f"style-{abs(hash(json.dumps(style, ensure_ascii=False, sort_keys=True))) % 100000}",
        "name": pick(style, "name", "title") or "页面样式",
        "role": normalize_role(pick(style, "role", "type") or "content"),
        "layoutDescription": pick(style, "layoutDescription", "layout_description", "layout", "description"),
        "stylePromptEn": pick(style, "stylePromptEn", "style_prompt_en", "prompt_en", "promptEn"),
        "stylePromptZh": pick(style, "stylePromptZh", "style_prompt_zh", "prompt_zh", "promptZh"),
        "negativePrompt": pick(style, "negativePrompt", "negative_prompt", "negative"),
    }


def normalize_role(value: Any) -> str:
    raw = str(value or "").strip().lower()
    if re.search(r"(cover|封面|title)", raw, re.I):
        return "cover"
    if re.search(r"(closing|thanks|thank|结尾|结束|感谢|联系)", raw, re.I):
        return "closing"
    if re.search(r"(section|chapter|章节|扉页|过渡)", raw, re.I):
        return "section"
    if re.search(r"(data|chart|数字|数据|表格)", raw, re.I):
        return "data"
    if re.search(r"(image-focus|image|视觉焦点|图文焦点|个人介绍|介绍)", raw, re.I):
        return "image-focus"
    if re.search(r"(toc|目录)", raw, re.I):
        return "toc"
    if re.search(r"(quote|金句|引用)", raw, re.I):
        return "quote"
    return raw or "content"


def infer_outline_role(title: str, explicit_role: str = "") -> str:
    if explicit_role:
        return normalize_role(explicit_role)
    normalized = normalize_role(title)
    return "content" if normalized == str(title or "").strip().lower() else normalized


def role_from_markdown_heading(level: int, title: str) -> str:
    if level == 1:
        return "cover"
    if level == 2:
        return "section"
    return infer_outline_role(title)


def strip_markdown_marks(text: Any) -> str:
    return re.sub(r"[*_`]+", "", re.sub(r"^[\s>*#-]+", "", str(text or ""))).strip()


def strip_inline_markdown(text: Any) -> str:
    value = str(text or "")
    value = re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"\1", value)
    value = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", value)
    value = re.sub(r"`([^`]+)`", r"\1", value)
    value = re.sub(r"\*\*([^*]+)\*\*", r"\1", value)
    value = re.sub(r"__([^_]+)__", r"\1", value)
    value = re.sub(r"\*([^*]+)\*", r"\1", value)
    value = re.sub(r"_([^_]+)_", r"\1", value)
    return value.strip()


def split_markdown_table_row(line: str) -> list[str] | None:
    trimmed = str(line or "").strip()
    if not (trimmed.startswith("|") and trimmed.endswith("|")):
        return None
    cells = [strip_inline_markdown(cell).strip() for cell in trimmed[1:-1].split("|")]
    return cells if len(cells) >= 2 else None


def is_table_separator(cells: list[str] | None) -> bool:
    return bool(cells) and all(re.match(r"^:?-{3,}:?$", re.sub(r"\s+", "", cell or "")) for cell in cells)


def has_markdown_table(text: str) -> bool:
    lines = str(text or "").replace("\r\n", "\n").split("\n")
    for index in range(max(0, len(lines) - 1)):
        if split_markdown_table_row(lines[index]) and is_table_separator(split_markdown_table_row(lines[index + 1])):
            return True
    return False


def finalize_outline_block(block: dict[str, Any]) -> dict[str, Any]:
    if block.get("role") != "cover" and has_markdown_table(str(block.get("text") or "")):
        next_block = dict(block)
        next_block["role"] = "data"
        return next_block
    return block


def split_logical_chunks(body: str) -> list[str]:
    normalized = str(body or "").replace("\r\n", "\n").strip()
    if not normalized:
        return []
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", normalized) if part.strip()]
    if len(paragraphs) > 1:
        return paragraphs
    lines = [line.strip() for line in normalized.split("\n") if line.strip()]
    if len(lines) > 1:
        return lines
    sentences = [item.strip() for item in re.findall(r"[^。！？.!?；;]+[。！？.!?；;]?", normalized) if item.strip()]
    if len(sentences) > 1:
        return sentences
    if len(normalized) <= CONTENT_PAGE_MAX_CHARS:
        return [normalized]
    return [normalized[i:i + CONTENT_PAGE_MAX_CHARS] for i in range(0, len(normalized), CONTENT_PAGE_MAX_CHARS)]


def is_content_block_too_long(text: str) -> bool:
    lines = [line.strip() for line in str(text or "").split("\n") if line.strip()]
    return len(str(text or "")) > CONTENT_PAGE_MAX_CHARS or len(lines) > CONTENT_PAGE_MAX_LINES


def split_long_content_block(block: dict[str, Any]) -> list[dict[str, Any]]:
    if int(block.get("level") or 0) != 3 or not is_content_block_too_long(str(block.get("text") or "")):
        return [block]
    lines = str(block.get("text") or "").split("\n")
    heading = lines[0].strip() if lines else f"### {block.get('title') or '内容'}"
    chunks = split_logical_chunks("\n".join(lines[1:]).strip())
    if len(chunks) <= 1:
        return [block]
    out = []
    for index, chunk in enumerate(chunks):
        item = dict(block)
        item["title"] = f"{block.get('title') or '内容'} {index + 1}"
        item["text"] = "\n".join([f"{heading}（{index + 1}/{len(chunks)}）", chunk]).strip()
        out.append(item)
    return out


def parse_markdown_outline_blocks(raw: str) -> list[dict[str, Any]]:
    lines = str(raw or "").replace("\r\n", "\n").split("\n")
    blocks: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    preface: list[str] = []
    for line in lines:
        match = re.match(r"^(#{1,3})\s+(.+?)\s*$", line)
        if match:
            if current:
                blocks.append(finalize_outline_block(current))
            level = len(match.group(1))
            title = strip_markdown_marks(match.group(2)) or f"第 {len(blocks) + 1} 页"
            current = {
                "index": len(blocks) + 1,
                "title": title,
                "role": role_from_markdown_heading(level, title),
                "text": line.strip(),
                "level": level,
            }
            continue
        if current:
            current["text"] = f"{current.get('text') or ''}\n{line}"
        elif line.strip():
            preface.append(line.strip())
    if current:
        blocks.append(finalize_outline_block(current))
    if not blocks:
        return []
    prefix = "\n".join(preface)
    normalized = []
    for index, block in enumerate(blocks):
        item = dict(block)
        item["text"] = "\n\n".join([prefix, str(item.get("text") or "").strip()]).strip() if index == 0 else str(item.get("text") or "").strip()
        normalized.append(item)
    return [
        {**item, "index": index + 1}
        for index, item in enumerate([page for block in normalized for page in split_long_content_block(block)])
    ]


def parse_legacy_outline_blocks(raw: str) -> list[dict[str, Any]]:
    chunks = [chunk.strip() for chunk in re.split(r"\n\s*\n", str(raw or "").replace("\r\n", "\n")) if chunk.strip()]
    blocks = []
    for index, chunk in enumerate(chunks):
        first_line = next((line.strip() for line in chunk.split("\n") if line.strip()), f"第 {index + 1} 页")
        title = strip_markdown_marks(first_line)[:60] or f"第 {index + 1} 页"
        blocks.append({
            "index": index + 1,
            "title": title,
            "role": "data" if has_markdown_table(chunk) else infer_outline_role(title),
            "text": chunk,
            "level": 3,
        })
    return blocks


def parse_outline_blocks(raw: str) -> list[dict[str, Any]]:
    markdown = parse_markdown_outline_blocks(raw)
    return markdown if markdown else parse_legacy_outline_blocks(raw)


def split_markdown_table_for_generation(lines: list[str], start_index: int) -> tuple[str, int] | None:
    header = split_markdown_table_row(lines[start_index])
    separator = split_markdown_table_row(lines[start_index + 1]) if start_index + 1 < len(lines) else None
    if not header or not is_table_separator(separator):
        return None
    rows: list[list[str]] = []
    index = start_index + 2
    while index < len(lines):
        row = split_markdown_table_row(lines[index])
        if not row:
            break
        if not is_table_separator(row):
            rows.append(row)
        index += 1
    if not rows:
        return None
    output = ["表格内容（必须画成可读表格，保留列名和每一行）：", f"列：{' / '.join(header)}"]
    for row_index, row in enumerate(rows):
        values = [f"{name}：{row[cell_index] if cell_index < len(row) and row[cell_index] else '-'}" for cell_index, name in enumerate(header)]
        output.append(f"第 {row_index + 1} 行：{'；'.join(values)}")
    return "\n".join(output), index - 1


def sanitize_markdown_for_generation(text: str) -> str:
    lines = str(text or "").replace("\r\n", "\n").split("\n")
    cleaned: list[str] = []
    in_fence = False
    index = 0
    while index < len(lines):
        raw = lines[index]
        trimmed = raw.strip()
        if re.match(r"^```", trimmed):
            in_fence = not in_fence
            index += 1
            continue
        if not in_fence and re.match(r"^[-*_]{3,}$", trimmed):
            index += 1
            continue
        if not in_fence and index < len(lines) - 1:
            table = split_markdown_table_for_generation(lines, index)
            if table:
                cleaned.append(table[0])
                index = table[1] + 1
                continue
        line = re.sub(r"^\s{0,3}#{1,6}\s+", "", raw)
        line = re.sub(r"^\s{0,3}>\s?", "", line)
        line = re.sub(r"^\s*(?:[-+*]|\d+[.)])\s+", "", line)
        cleaned.append(strip_inline_markdown(line).strip())
        index += 1
    return re.sub(r"\n{3,}", "\n\n", "\n".join(cleaned)).strip()


def role_score(style_role: str, block: dict[str, Any], index: int, total: int) -> int:
    role = normalize_role(style_role)
    block_role = normalize_role(block.get("role"))
    if role == block_role:
        return 100
    if block_role == "content" and role in ("content", "image-focus"):
        return 70
    if block_role == "image-focus" and role in ("image-focus", "content"):
        return 70
    if block_role == "section" and role in ("section", "toc"):
        return 70
    if block_role == "data" and role in ("data", "content", "image-focus"):
        return 70
    if index == 0 and role == "cover":
        return 50
    if index == total - 1 and role in ("closing", "thanks"):
        return 50
    return 0


def pick_page_style_for_block(block: dict[str, Any], index: int, total: int, page_styles: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, str]:
    if not page_styles:
        return None, "freeform"
    best = page_styles[0]
    best_score = -1
    for style in page_styles:
        score = role_score(str(style.get("role") or ""), block, index, total)
        if score > best_score:
            best = style
            best_score = score
    if best_score > 0:
        return best, "role"
    fallback = [style for style in page_styles if normalize_role(style.get("role")) in ("content", "image-focus")]
    pool = fallback or page_styles
    return pool[index % len(pool)], "cycle"


def make_ppt_pipe(**kwargs: Any) -> dict[str, Any]:
    pipe = {
        "pipe_type": IMAGEN_PPT_PIPE_TYPE,
        "version": IMAGEN_PPT_PIPE_VERSION,
        "title": str(kwargs.get("title") or "PPT").strip() or "PPT",
        "user_idea": str(kwargs.get("user_idea") or "").strip(),
        "outline_markdown": str(kwargs.get("outline_markdown") or "").strip(),
        "aspect_ratio": str(kwargs.get("aspect_ratio") or "16:9").strip(),
        "prompt_language": str(kwargs.get("prompt_language") or "zh").strip(),
        "target_model": str(kwargs.get("target_model") or "generic-comfyui").strip(),
        "template_id": str(kwargs.get("template_id") or "").strip(),
        "template_name": str(kwargs.get("template_name") or "").strip(),
        "template": as_object(kwargs.get("template")),
        "template_pipe": as_object(kwargs.get("template_pipe")),
        "page_styles": kwargs.get("page_styles") if isinstance(kwargs.get("page_styles"), list) else [],
        "pages": kwargs.get("pages") if isinstance(kwargs.get("pages"), list) else [],
        "design_brief": kwargs.get("design_brief") if isinstance(kwargs.get("design_brief"), dict) else {},
        "reference_images": kwargs.get("reference_images") if isinstance(kwargs.get("reference_images"), list) else [],
        "result_json": str(kwargs.get("result_json") or "").strip(),
        "export_path": str(kwargs.get("export_path") or "").strip(),
        "export_json": str(kwargs.get("export_json") or "").strip(),
    }
    if pipe_contains_secret(pipe):
        raise TemplateDistillError("PPT节点束中不应包含 API Key。")
    return pipe


def ensure_ppt_pipe(value: Any) -> dict[str, Any]:
    pipe = coerce_dict(value)
    if not pipe or pipe.get("pipe_type") != IMAGEN_PPT_PIPE_TYPE:
        raise TemplateDistillError("请连接有效的 PPT节点束。")
    if pipe_contains_secret(pipe):
        raise TemplateDistillError("PPT节点束中不应包含 API Key。")
    return pipe


def title_from_outline(blocks: list[dict[str, Any]], fallback: str = "PPT") -> str:
    return str(blocks[0].get("title") if blocks else fallback or "PPT").strip() or "PPT"


def selected_roles_from_template(template: dict[str, Any]) -> list[str]:
    roles = [normalize_role(style.get("role")) for style in get_template_page_styles(template)]
    return list(dict.fromkeys([role for role in roles if role])) or PPT_DEFAULT_ROLES


def call_llm_json(system_prompt: str, payload: dict[str, Any], config_path: str, temperature: float = 0.5) -> dict[str, Any]:
    config = studio.load_config(config_path)
    task_config = studio.resolve_task_config(config, "llm")
    parsed = studio.call_agent(
        task_config,
        system_prompt,
        json.dumps(payload, ensure_ascii=False),
        temperature=temperature,
        response_format={"type": "json_object"},
    )
    return as_object(parsed)


def analyze_ppt_references(reference_images: Any, config_path: str, max_edge: int = 2400) -> list[dict[str, Any]]:
    data_urls = studio.image_tensor_to_data_urls(reference_images, max_edge=max_edge)[:4]
    if not data_urls:
        return []
    config = studio.load_config(config_path)
    vision_config = studio.resolve_task_config(config, "vlm")
    return studio.analyze_reference_image_urls(data_urls, vision_config)


def run_ppt_outline_draft(user_idea: str, existing_outline: str, template_pipe: Any, config_path: str) -> dict[str, str]:
    pipe, template = resolve_template_from_pipe(template_pipe)
    idea = str(user_idea or "").strip()
    existing = str(existing_outline or "").strip()
    if not idea and not existing:
        raise TemplateDistillError("请填写用户想法或已有大纲。")
    payload = {
        "user_idea": idea,
        "selected_pages": selected_roles_from_template(template),
        "style_hint": pick(template, "name") or str(pipe.get("template_name") or ""),
        "existing_content": existing or None,
    }
    try:
        parsed = call_llm_json(PPT_OUTLINE_DRAFTER_PROMPT, payload, config_path, temperature=0.5)
    except Exception:
        if existing:
            return {"outline_markdown": existing, "notes": "模型草拟失败，已返回已有大纲。"}
        raise
    outline = str(pick(parsed, "content") or "\n".join(as_list(parsed.get("outline"))) or existing).strip()
    if not outline:
        raise TemplateDistillError("PPT 大纲草拟没有返回可用内容。")
    return {"outline_markdown": outline, "notes": pick(parsed, "notes", "note")}


def run_ppt_outline_plan(
    outline_markdown: str,
    user_idea: str,
    template_pipe: Any,
    aspect_ratio: str,
    prompt_language: str,
    target_model: str,
) -> dict[str, Any]:
    outline = str(outline_markdown or "").strip()
    if not outline:
        raise TemplateDistillError("大纲 Markdown 不能为空。")
    blocks = parse_outline_blocks(outline)
    if not blocks:
        raise TemplateDistillError("没有从大纲中解析到页面。")
    template_bundle, template = resolve_template_from_pipe(template_pipe)
    page_styles = get_template_page_styles(template)
    pages = []
    for index, block in enumerate(blocks):
        page_style, match_kind = pick_page_style_for_block(block, index, len(blocks), page_styles)
        page_style_id = str(page_style.get("id") or "") if page_style else ""
        role = normalize_role(block.get("role"))
        style_name = str(page_style.get("name") or role) if page_style else role
        pages.append({
            "id": f"ppt-page-{index + 1:03d}",
            "pageNo": index + 1,
            "title": str(block.get("title") or f"第 {index + 1} 页").strip(),
            "role": role,
            "pageStyleId": page_style_id,
            "pageStyle": page_style or None,
            "styleName": style_name,
            "roleLabel": f"{index + 1}. {block.get('title') or ''} · {style_name}",
            "matchKind": match_kind,
            "outlineText": sanitize_markdown_for_generation(str(block.get("text") or "")) or str(block.get("title") or ""),
            "prompt": "",
            "negative": "",
            "notes": "",
            "taskId": "",
            "outputUrl": "",
        })
    aspect = normalize_aspect(aspect_ratio, "16:9")
    language = normalize_language(prompt_language)
    title = title_from_outline(blocks)
    pipe = make_ppt_pipe(
        title=title,
        user_idea=user_idea,
        outline_markdown=outline,
        aspect_ratio=aspect,
        prompt_language=language,
        target_model=str(target_model or "").strip() or "generic-comfyui",
        template_id=str(template_bundle.get("template_id") or pick(template, "id") or ""),
        template_name=str(template_bundle.get("template_name") or pick(template, "name") or ""),
        template=template,
        template_pipe=template_bundle,
        page_styles=page_styles,
        pages=pages,
    )
    return {"pipe": pipe, "page_plan_json": json.dumps({"pages": pages}, ensure_ascii=False, indent=2), "title": title}


def fallback_design_brief(pipe: dict[str, Any], error: str = "") -> dict[str, Any]:
    template = as_object(pipe.get("template"))
    style = pick(template, "stylePromptZh", "stylePromptEn") or pick(template, "description", "requirements")
    return {
        "visual_theme": style or f"{pipe.get('title') or 'PPT'} 的统一演示文稿视觉风格",
        "style_keywords": [item for item in [pick(template, "category"), "presentation slide", "consistent layout"] if item],
        "decoration_elements": "保持同一套色彩、版式和装饰元素。",
        "composition_principles": "各页保持清晰层级、足够留白和稳定对齐。",
        "atmosphere": "专业、统一、清晰",
        "consistency_rules": "跨页保持字体、色彩、卡片形态和视觉节奏一致。",
        "page_rhythm": "封面更强，中间页稳定，尾页收束。",
        "fallback_error": error,
    }


def run_ppt_design_brief(ppt_pipe: Any, reference_images: Any, config_path: str, max_edge: int = 2400) -> dict[str, Any]:
    pipe = dict(ensure_ppt_pipe(ppt_pipe))
    references = analyze_ppt_references(reference_images, config_path, max_edge=max_edge) if reference_images is not None else []
    payload = {
        "user_idea": pipe.get("user_idea") or "",
        "outline": pipe.get("outline_markdown") or "",
        "total_pages": len(pipe.get("pages") or []),
        "aspect_ratio": pipe.get("aspect_ratio") or "16:9",
        "prompt_language": pipe.get("prompt_language") or "zh",
        "reference_images": references,
    }
    try:
        design_brief = call_llm_json(PPT_DESIGN_BRIEF_PROMPT, payload, config_path, temperature=0.6)
    except Exception as exc:
        design_brief = fallback_design_brief(pipe, str(exc)[:300])
    pipe["design_brief"] = design_brief
    pipe["reference_images"] = references
    return {
        "pipe": pipe,
        "design_brief_json": json.dumps(design_brief, ensure_ascii=False, indent=2),
        "reference_analysis_json": json.dumps(references, ensure_ascii=False, indent=2),
    }


def fallback_page_prompt(pipe: dict[str, Any], page: dict[str, Any], page_style: dict[str, Any] | None) -> str:
    language = pipe.get("prompt_language") or "zh"
    style = ""
    if page_style:
        style = page_style.get("stylePromptZh") if language == "zh" else page_style.get("stylePromptEn")
        style = style or page_style.get("stylePromptEn") or page_style.get("stylePromptZh") or ""
    content = page.get("outlineText") or page.get("title") or ""
    aspect = pipe.get("aspect_ratio") or "16:9"
    if language == "en":
        return "\n".join(part for part in [
            f"Create one complete PPT slide, aspect ratio {aspect}.",
            f"Slide role: {page.get('role') or 'content'}.",
            f"Style: {style}" if style else "",
            f"Layout: {page_style.get('layoutDescription')}" if page_style and page_style.get("layoutDescription") else "",
            f"Content to render as readable text: {content}",
            "Keep all text sharp, readable, correctly spelled, and aligned.",
        ] if part)
    return "\n".join(part for part in [
        f"生成一张完整 PPT 页面，画面比例 {aspect}。",
        f"页面角色：{page.get('role') or 'content'}。",
        f"视觉风格：{style}" if style else "",
        f"版式结构：{page_style.get('layoutDescription')}" if page_style and page_style.get("layoutDescription") else "",
        f"需要渲染为真实可读文字的文案：\n{content}",
        "文字必须清晰、准确、无乱码，整体排版稳定精致。",
    ] if part)


def normalize_compose_result(parsed: dict[str, Any], pipe: dict[str, Any], page: dict[str, Any], page_style: dict[str, Any] | None, fallback_used: bool) -> dict[str, Any]:
    fallback_prompt = fallback_page_prompt(pipe, page, page_style)
    return {
        "prompt": pick(parsed, "prompt", "positive_prompt", "positivePrompt") or fallback_prompt,
        "negative": pick(parsed, "negative", "negative_prompt", "negativePrompt") or (page_style or {}).get("negativePrompt") or "misspelled text, garbled characters, blurry typography",
        "notes": pick(parsed, "notes", "note") or ("已使用兜底提示词" if fallback_used else "已拼装页面提示词"),
        "fallbackUsed": fallback_used,
    }


def run_ppt_page_compose(ppt_pipe: Any, config_path: str) -> dict[str, Any]:
    pipe = dict(ensure_ppt_pipe(ppt_pipe))
    pages = [dict(page) for page in pipe.get("pages") or []]
    if not pages:
        raise TemplateDistillError("PPT节点束中没有页面，请先连接“大纲规划”。")
    config = studio.load_config(config_path)
    task_config = studio.resolve_task_config(config, "llm")
    total = len(pages)
    prompt_rows = []
    for index, page in enumerate(pages):
        page_style = as_object(page.get("pageStyle")) or None
        payload = {
            "user_idea": pipe.get("user_idea") or "",
            "user_content": page.get("outlineText") or page.get("title") or "",
            "aspect_ratio": pipe.get("aspect_ratio") or "16:9",
            "target_model": pipe.get("target_model") or "generic-comfyui",
            "prompt_language": pipe.get("prompt_language") or "zh",
            "reference_images": pipe.get("reference_images") or [],
            "ref_count": len(pipe.get("reference_images") or []),
            "design_brief": pipe.get("design_brief") or None,
            "page_position": {"current": index + 1, "total": total},
        }
        system_prompt = PPT_PAGE_COMPOSER_PROMPT
        if page_style:
            payload["page_style"] = {
                "name": page_style.get("name"),
                "role": page_style.get("role"),
                "layoutDescription": page_style.get("layoutDescription"),
                "style_prompt_en": page_style.get("stylePromptEn"),
                "style_prompt_zh": page_style.get("stylePromptZh"),
                "negative_prompt": page_style.get("negativePrompt"),
            }
        else:
            system_prompt = PPT_FREEFORM_COMPOSER_PROMPT
            payload["slide_role"] = page.get("role") or "content"
        fallback_used = False
        try:
            parsed = as_object(studio.call_agent(
                task_config,
                system_prompt,
                json.dumps(payload, ensure_ascii=False),
                temperature=0.5,
                response_format={"type": "json_object"},
            ))
        except Exception as exc:
            parsed = {"notes": str(exc)[:200]}
            fallback_used = True
        normalized = normalize_compose_result(parsed, pipe, page, page_style, fallback_used)
        page.update(normalized)
        prompt_rows.append({
            "pageNo": page.get("pageNo"),
            "title": page.get("title"),
            "role": page.get("role"),
            "prompt": page.get("prompt"),
            "negative": page.get("negative"),
            "notes": page.get("notes"),
            "fallbackUsed": page.get("fallbackUsed"),
        })
    pipe["pages"] = pages
    pipe["prompt_list_json"] = json.dumps(prompt_rows, ensure_ascii=False, indent=2)
    return {
        "pipe": pipe,
        "prompt_list_json": pipe["prompt_list_json"],
        "pages_json": json.dumps(pages, ensure_ascii=False, indent=2),
    }


def tensor_to_numpy_batch(images: Any) -> np.ndarray:
    if images is None:
        return np.empty((0, 1, 1, 3), dtype=np.float32)
    if hasattr(images, "detach"):
        images = images.detach().cpu().numpy()
    arr = np.asarray(images).astype(np.float32)
    if arr.ndim == 3:
        arr = arr[None, ...]
    return np.clip(arr, 0.0, 1.0)


def numpy_batch_to_comfy(arr: np.ndarray) -> Any:
    try:
        import torch

        return torch.from_numpy(arr.astype(np.float32))
    except Exception:
        return arr.astype(np.float32)


def normalize_image_batch(images: list[Any]) -> Any:
    arrays = [tensor_to_numpy_batch(image)[0] for image in images if tensor_to_numpy_batch(image).shape[0] > 0]
    if not arrays:
        raise TemplateDistillError("没有可输出的 PPT 页面图片。")
    h, w = arrays[0].shape[:2]
    normalized = []
    for array in arrays:
        if array.shape[:2] != (h, w):
            pil = Image.fromarray((np.clip(array, 0, 1) * 255).astype(np.uint8))
            pil = pil.resize((w, h), Image.LANCZOS)
            array = np.asarray(pil).astype(np.float32) / 255.0
        normalized.append(array)
    return numpy_batch_to_comfy(np.stack(normalized, axis=0))


def run_ppt_runninghub_batch(
    ppt_pipe: Any,
    channel: str,
    resolution: str,
    quality: str,
    config_path: str,
    reference_images: Any = None,
    timeout_minutes: int = 30,
    poll_interval_seconds: int = 5,
) -> dict[str, Any]:
    pipe = dict(ensure_ppt_pipe(ppt_pipe))
    pages = [dict(page) for page in pipe.get("pages") or []]
    if not pages:
        raise TemplateDistillError("PPT节点束中没有页面。")
    images = []
    results = []
    total_steps = max(1, len(pages) * 5)
    progress_bar = None
    try:
        from comfy.utils import ProgressBar

        progress_bar = ProgressBar(total_steps)
    except Exception:
        progress_bar = None
    timeout_seconds = max(60, int(timeout_minutes or 30) * 60)
    poll_interval = max(1, int(poll_interval_seconds or 5))
    for page_index, page in enumerate(pages):
        prompt = str(page.get("prompt") or "").strip()
        if not prompt:
            raise TemplateDistillError(f"第 {page.get('pageNo') or '?'} 页缺少 prompt，请先连接“PPT 页面拼装”。")
        page_no = page.get("pageNo") or page_index + 1
        step_base = page_index * 5

        def progress_callback(stage: str = "", current: int = 0, total: int = 5, message: str = "", status: str = "") -> None:
            absolute = min(total_steps, step_base + max(0, int(current or 0)))
            studio.update_comfy_progress_bar(progress_bar, absolute, total_steps)
            if message:
                print(f"[ComfyUI Imagen Studio PPT] 第 {page_no}/{len(pages)} 页：{message}")

        result = studio.run_runninghub_rhart_g2(
            prompt=prompt,
            aspect_ratio=pipe.get("aspect_ratio") or "16:9",
            resolution=resolution,
            config_path=config_path,
            channel=channel,
            quality=quality,
            reference_images=reference_images,
            poll_interval=float(poll_interval),
            timeout_seconds=float(timeout_seconds),
            progress_callback=progress_callback,
        )
        page["taskId"] = result["task_id"]
        page["outputUrl"] = result["output_url"]
        page["resultJson"] = result["result_json"]
        images.append(result["image"])
        results.append({
            "pageNo": page.get("pageNo"),
            "title": page.get("title"),
            "taskId": page.get("taskId"),
            "outputUrl": page.get("outputUrl"),
        })
    pipe["pages"] = pages
    pipe["runninghub"] = {
        "channel": studio.normalize_runninghub_channel_option(channel),
        "resolution": resolution if resolution in studio.RUNNINGHUB_RESOLUTIONS else "1k",
        "quality": studio.normalize_runninghub_quality_option(quality),
        "timeoutMinutes": int(timeout_seconds / 60),
        "pollIntervalSeconds": poll_interval,
        "results": results,
    }
    pipe["result_json"] = json.dumps(pipe["runninghub"], ensure_ascii=False, indent=2)
    return {
        "image": normalize_image_batch(images),
        "pipe": pipe,
        "result_json": pipe["result_json"],
    }


def safe_filename(value: str, fallback: str = "ppt") -> str:
    clean = re.sub(r'[\\/:*?"<>|]+', "_", str(value or fallback))
    clean = re.sub(r"\s+", "_", clean).strip("._ ")
    return clean[:80] or fallback


def output_export_dir() -> Path:
    try:
        import folder_paths

        root = Path(folder_paths.get_output_directory()) / "imagen-ppt"
    except Exception:
        root = studio.imagen_studio_data_dir() / PPT_EXPORT_DIR_NAME
    root.mkdir(parents=True, exist_ok=True)
    return root


def image_batch_to_png_bytes(images: Any) -> list[bytes]:
    arr = tensor_to_numpy_batch(images)
    out = []
    for item in arr:
        image = Image.fromarray((np.clip(item, 0, 1) * 255).astype(np.uint8)).convert("RGB")
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        out.append(buffer.getvalue())
    return out


def page_images_from_pipe(pipe: dict[str, Any]) -> list[bytes]:
    out = []
    for page in pipe.get("pages") or []:
        url = str(page.get("outputUrl") or "").strip()
        if not url:
            continue
        data = studio.download_bytes(url, timeout=120, label="ppt page image download")
        image = Image.open(io.BytesIO(data)).convert("RGB")
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        out.append(buffer.getvalue())
    return out


def slide_size_emu(aspect_ratio: str) -> tuple[int, int]:
    match = re.match(r"^(\d+(?:\.\d+)?)\s*[:x]\s*(\d+(?:\.\d+)?)$", str(aspect_ratio or "16:9"), re.I)
    w = float(match.group(1)) if match else 16.0
    h = float(match.group(2)) if match else 9.0
    emu_per_inch = 914400
    long_edge = 13.333333
    short_edge = 7.5
    if abs(w - h) < 0.001:
        return int(short_edge * emu_per_inch), int(short_edge * emu_per_inch)
    if w > h:
        cx = int(long_edge * emu_per_inch)
        return cx, int(cx * h / w)
    cy = int(long_edge * emu_per_inch)
    return int(cy * w / h), cy


def xml_escape(value: Any) -> str:
    return html.escape(str(value or ""), quote=True)


def content_types(count: int) -> str:
    slides = "\n".join(f'  <Override PartName="/ppt/slides/slide{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>' for i in range(1, count + 1))
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Default Extension="png" ContentType="image/png"/>
  <Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
  <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
  <Override PartName="/ppt/presentation.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/>
  <Override PartName="/ppt/slideMasters/slideMaster1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideMaster+xml"/>
  <Override PartName="/ppt/slideLayouts/slideLayout1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideLayout+xml"/>
  <Override PartName="/ppt/notesMasters/notesMaster1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.notesMaster+xml"/>
  <Override PartName="/ppt/theme/theme1.xml" ContentType="application/vnd.openxmlformats-officedocument.theme+xml"/>
{slides}
{chr(10).join(f'  <Override PartName="/ppt/notesSlides/notesSlide{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.notesSlide+xml"/>' for i in range(1, count + 1))}
</Types>'''


def rels(items: list[tuple[str, str, str]]) -> str:
    body = "\n".join(f'  <Relationship Id="{rid}" Type="{typ}" Target="{xml_escape(target)}"/>' for rid, typ, target in items)
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
{body}
</Relationships>'''


def presentation_xml(count: int, cx: int, cy: int) -> str:
    slide_ids = "\n".join(f'    <p:sldId id="{255 + i}" r:id="rId{i + 2}"/>' for i in range(1, count + 1))
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:presentation xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
  <p:sldMasterIdLst><p:sldMasterId id="2147483648" r:id="rId1"/></p:sldMasterIdLst>
  <p:notesMasterIdLst><p:notesMasterId r:id="rId2"/></p:notesMasterIdLst>
  <p:sldIdLst>
{slide_ids}
  </p:sldIdLst>
  <p:sldSz cx="{cx}" cy="{cy}" type="screen16x9"/>
  <p:notesSz cx="6858000" cy="9144000"/>
</p:presentation>'''


def slide_xml(index: int, title: str, cx: int, cy: int) -> str:
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
  <p:cSld>
    <p:spTree>
      <p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>
      <p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>
      <p:pic>
        <p:nvPicPr><p:cNvPr id="2" name="{xml_escape(title or f'Slide {index}')}"/><p:cNvPicPr><a:picLocks noChangeAspect="1"/></p:cNvPicPr><p:nvPr/></p:nvPicPr>
        <p:blipFill><a:blip r:embed="rId1"/><a:stretch><a:fillRect/></a:stretch></p:blipFill>
        <p:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr>
      </p:pic>
    </p:spTree>
  </p:cSld>
  <p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr>
</p:sld>'''


def slide_master_xml() -> str:
    return '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sldMaster xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
  <p:cSld><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr/></p:spTree></p:cSld>
  <p:clrMap bg1="lt1" tx1="dk1" bg2="lt2" tx2="dk2" accent1="accent1" accent2="accent2" accent3="accent3" accent4="accent4" accent5="accent5" accent6="accent6" hlink="hlink" folHlink="folHlink"/>
  <p:sldLayoutIdLst><p:sldLayoutId id="2147483649" r:id="rId1"/></p:sldLayoutIdLst>
  <p:txStyles><p:titleStyle/><p:bodyStyle/><p:otherStyle/></p:txStyles>
</p:sldMaster>'''


def slide_layout_xml() -> str:
    return '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sldLayout xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" type="blank" preserve="1">
  <p:cSld name="Blank"><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr/></p:spTree></p:cSld>
  <p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr>
</p:sldLayout>'''


def notes_master_xml() -> str:
    return '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:notesMaster xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
  <p:cSld><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr/></p:spTree></p:cSld>
  <p:clrMap bg1="lt1" tx1="dk1" bg2="lt2" tx2="dk2" accent1="accent1" accent2="accent2" accent3="accent3" accent4="accent4" accent5="accent5" accent6="accent6" hlink="hlink" folHlink="folHlink"/>
  <p:notesStyle><a:lvl1pPr marL="0" indent="0"><a:defRPr sz="1200"/></a:lvl1pPr></p:notesStyle>
</p:notesMaster>'''


def notes_text(page: dict[str, Any]) -> str:
    parts = [
        f"页码: {page.get('pageNo') or ''}",
        f"标题: {page.get('title') or ''}",
        f"角色: {page.get('role') or ''}",
        f"大纲:\n{page.get('outlineText') or ''}",
        f"Prompt:\n{page.get('prompt') or ''}",
        f"Negative:\n{page.get('negative') or ''}" if page.get("negative") else "",
        f"RunningHub taskId: {page.get('taskId') or ''}" if page.get("taskId") else "",
        f"结果URL: {page.get('outputUrl') or ''}" if page.get("outputUrl") else "",
    ]
    return "\n\n".join(part for part in parts if part)[:60000]


def notes_paragraphs(value: str) -> str:
    paragraphs = []
    for line in str(value or "").splitlines() or [""]:
        paragraphs.append(
            f'<a:p><a:r><a:rPr lang="zh-CN" sz="1100"/><a:t>{xml_escape(line or " ")}</a:t></a:r><a:endParaRPr lang="zh-CN" sz="1100"/></a:p>'
        )
    return "".join(paragraphs)


def notes_slide_xml(index: int, page: dict[str, Any]) -> str:
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:notes xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
  <p:cSld name="Notes {index}">
    <p:spTree>
      <p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>
      <p:grpSpPr/>
      <p:sp>
        <p:nvSpPr><p:cNvPr id="2" name="Notes Placeholder {index}"/><p:cNvSpPr txBox="1"/><p:nvPr><p:ph type="body" idx="1"/></p:nvPr></p:nvSpPr>
        <p:spPr><a:xfrm><a:off x="685800" y="685800"/><a:ext cx="5486400" cy="7772400"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr>
        <p:txBody><a:bodyPr/><a:lstStyle/>{notes_paragraphs(notes_text(page))}</p:txBody>
      </p:sp>
    </p:spTree>
  </p:cSld>
  <p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr>
</p:notes>'''


def theme_xml() -> str:
    return '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<a:theme xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" name="Imagen Studio">
  <a:themeElements>
    <a:clrScheme name="Office"><a:dk1><a:sysClr val="windowText" lastClr="000000"/></a:dk1><a:lt1><a:sysClr val="window" lastClr="FFFFFF"/></a:lt1><a:dk2><a:srgbClr val="1F2937"/></a:dk2><a:lt2><a:srgbClr val="F8FAFC"/></a:lt2><a:accent1><a:srgbClr val="2563EB"/></a:accent1><a:accent2><a:srgbClr val="F59E0B"/></a:accent2><a:accent3><a:srgbClr val="10B981"/></a:accent3><a:accent4><a:srgbClr val="EF4444"/></a:accent4><a:accent5><a:srgbClr val="8B5CF6"/></a:accent5><a:accent6><a:srgbClr val="06B6D4"/></a:accent6><a:hlink><a:srgbClr val="0000FF"/></a:hlink><a:folHlink><a:srgbClr val="800080"/></a:folHlink></a:clrScheme>
    <a:fontScheme name="Office"><a:majorFont><a:latin typeface="Aptos Display"/></a:majorFont><a:minorFont><a:latin typeface="Aptos"/></a:minorFont></a:fontScheme>
    <a:fmtScheme name="Office"><a:fillStyleLst><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:fillStyleLst><a:lnStyleLst><a:ln w="6350"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:ln></a:lnStyleLst><a:effectStyleLst><a:effectStyle><a:effectLst/></a:effectStyle></a:effectStyleLst><a:bgFillStyleLst><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:bgFillStyleLst></a:fmtScheme>
  </a:themeElements>
</a:theme>'''


def build_image_deck_pptx(title: str, aspect_ratio: str, pages: list[dict[str, Any]], images: list[bytes]) -> bytes:
    if not images:
        raise TemplateDistillError("没有可导出的 PPT 页面图片。")
    count = min(len(images), len(pages) or len(images))
    cx, cy = slide_size_emu(aspect_ratio)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types(count))
        zf.writestr("_rels/.rels", rels([
            ("rId1", "http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument", "ppt/presentation.xml"),
            ("rId2", "http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties", "docProps/core.xml"),
            ("rId3", "http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties", "docProps/app.xml"),
        ]))
        zf.writestr("docProps/core.xml", f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>{xml_escape(title)}</dc:title></cp:coreProperties>''')
        zf.writestr("docProps/app.xml", f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"><Application>Imagen Studio ComfyUI</Application><Slides>{count}</Slides></Properties>''')
        presentation_rels = [
            ("rId1", "http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster", "slideMasters/slideMaster1.xml"),
            ("rId2", "http://schemas.openxmlformats.org/officeDocument/2006/relationships/notesMaster", "notesMasters/notesMaster1.xml"),
        ]
        presentation_rels.extend((f"rId{i + 2}", "http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide", f"slides/slide{i}.xml") for i in range(1, count + 1))
        zf.writestr("ppt/presentation.xml", presentation_xml(count, cx, cy))
        zf.writestr("ppt/_rels/presentation.xml.rels", rels(presentation_rels))
        zf.writestr("ppt/slideMasters/slideMaster1.xml", slide_master_xml())
        zf.writestr("ppt/slideMasters/_rels/slideMaster1.xml.rels", rels([
            ("rId1", "http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout", "../slideLayouts/slideLayout1.xml"),
            ("rId2", "http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme", "../theme/theme1.xml"),
        ]))
        zf.writestr("ppt/notesMasters/notesMaster1.xml", notes_master_xml())
        zf.writestr("ppt/notesMasters/_rels/notesMaster1.xml.rels", rels([
            ("rId1", "http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme", "../theme/theme1.xml"),
        ]))
        zf.writestr("ppt/slideLayouts/slideLayout1.xml", slide_layout_xml())
        zf.writestr("ppt/slideLayouts/_rels/slideLayout1.xml.rels", rels([
            ("rId1", "http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster", "../slideMasters/slideMaster1.xml"),
        ]))
        zf.writestr("ppt/theme/theme1.xml", theme_xml())
        for index in range(1, count + 1):
            page = pages[index - 1] if index - 1 < len(pages) else {}
            zf.writestr(f"ppt/slides/slide{index}.xml", slide_xml(index, str(page.get("title") or f"Slide {index}"), cx, cy))
            zf.writestr(f"ppt/slides/_rels/slide{index}.xml.rels", rels([
                ("rId1", "http://schemas.openxmlformats.org/officeDocument/2006/relationships/image", f"../media/image{index}.png"),
                ("rId2", "http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout", "../slideLayouts/slideLayout1.xml"),
                ("rId3", "http://schemas.openxmlformats.org/officeDocument/2006/relationships/notesSlide", f"../notesSlides/notesSlide{index}.xml"),
            ]))
            zf.writestr(f"ppt/notesSlides/notesSlide{index}.xml", notes_slide_xml(index, page))
            zf.writestr(f"ppt/notesSlides/_rels/notesSlide{index}.xml.rels", rels([
                ("rId1", "http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide", f"../slides/slide{index}.xml"),
                ("rId2", "http://schemas.openxmlformats.org/officeDocument/2006/relationships/notesMaster", "../notesMasters/notesMaster1.xml"),
            ]))
            zf.writestr(f"ppt/media/image{index}.png", images[index - 1])
    return buffer.getvalue()


def run_ppt_export(ppt_pipe: Any, images: Any, filename: str) -> dict[str, str]:
    pipe = dict(ensure_ppt_pipe(ppt_pipe))
    pages = [dict(page) for page in pipe.get("pages") or []]
    image_bytes = image_batch_to_png_bytes(images) if images is not None else page_images_from_pipe(pipe)
    if not image_bytes:
        raise TemplateDistillError("请连接图片批次，或先运行 PPT RunningHub 批量生图。")
    title = str(filename or pipe.get("title") or "ppt").strip()
    output_path = output_export_dir() / f"{safe_filename(title)}-{int(time.time())}.pptx"
    output_path.write_bytes(build_image_deck_pptx(title, pipe.get("aspect_ratio") or "16:9", pages, image_bytes))
    export = {
        "path": str(output_path),
        "pageCount": min(len(image_bytes), len(pages) or len(image_bytes)),
        "title": title,
    }
    pipe["export_path"] = str(output_path)
    pipe["export_json"] = json.dumps(export, ensure_ascii=False, indent=2)
    return {"path": str(output_path), "export_json": pipe["export_json"]}


class ImagenStudioPPTOutlineDraft:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "用户想法": ("STRING", {"default": "", "multiline": True, "placeholder": "输入这套 PPT 的主题、受众、用途。"}),
                "已有大纲": ("STRING", {"default": "", "multiline": True, "placeholder": "可选，粘贴已有 Markdown 大纲，AI 会润色结构。"}),
                "配置路径": ("STRING", {"default": "", "placeholder": "留空使用 kktools/imagen-studio/config.json"}),
            },
            "optional": {
                "模板束": (studio.IMAGEN_STUDIO_PIPE_TYPE, {"tooltip": "可连接 Imagen Studio 模板选择器输出的模板束，用于提供页面角色和风格提示。"}),
            },
        }

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("大纲Markdown", "草拟说明")
    FUNCTION = "draft"
    CATEGORY = NODE_CATEGORY_CN
    DESCRIPTION = "根据用户想法和可选模板束草拟 PPT Markdown 大纲。"

    def draft(self, **kwargs):
        result = run_ppt_outline_draft(
            read_input(kwargs, "用户想法", ""),
            read_input(kwargs, "已有大纲", ""),
            read_input(kwargs, "模板束", None),
            read_input(kwargs, "配置路径", ""),
        )
        return result["outline_markdown"], result["notes"]


class ImagenStudioPPTOutlinePlan:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "大纲Markdown": ("STRING", {"default": "", "multiline": True, "placeholder": "# 封面标题\n\n## 章节\n\n### 内容页\n- 要点"}),
                "用户想法": ("STRING", {"default": "", "multiline": True, "placeholder": "可选，传给后续页面拼装。"}),
                "画面比例": (PPT_ASPECT_OPTIONS_CN, {"default": "16:9"}),
                "提示词语言": (studio.LANGUAGE_OPTIONS_CN, {"default": "中文"}),
                "目标模型": ("STRING", {"default": "generic-comfyui"}),
            },
            "optional": {
                "模板束": (studio.IMAGEN_STUDIO_PIPE_TYPE, {"tooltip": "连接模板选择器，若模板含 pageStyles 会自动按角色匹配。"}),
            },
        }

    RETURN_TYPES = (IMAGEN_PPT_PIPE_TYPE, "STRING", "STRING")
    RETURN_NAMES = ("PPT束", "页面计划JSON", "PPT标题")
    FUNCTION = "plan"
    CATEGORY = NODE_CATEGORY_CN
    DESCRIPTION = "把 Markdown 大纲拆成 PPT 页面计划，并写入 IMAGEN_PPT_PIPE。"

    def plan(self, **kwargs):
        result = run_ppt_outline_plan(
            read_input(kwargs, "大纲Markdown", ""),
            read_input(kwargs, "用户想法", ""),
            read_input(kwargs, "模板束", None),
            read_input(kwargs, "画面比例", "16:9"),
            read_input(kwargs, "提示词语言", "中文"),
            read_input(kwargs, "目标模型", "generic-comfyui"),
        )
        return result["pipe"], result["page_plan_json"], result["title"]


class ImagenStudioPPTDesignBrief:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "PPT束": (IMAGEN_PPT_PIPE_TYPE, {"tooltip": "连接 PPT 大纲规划输出。"}),
                "配置路径": ("STRING", {"default": ""}),
                "最长边": ("INT", {"default": 2400, "min": 512, "max": 4096, "step": 64}),
            },
            "optional": {
                "参考图像": ("IMAGE", {"tooltip": "可选，用于生成跨页统一设计规范。"}),
            },
        }

    RETURN_TYPES = (IMAGEN_PPT_PIPE_TYPE, "STRING", "STRING")
    RETURN_NAMES = ("PPT束", "设计规范JSON", "参考图分析JSON")
    FUNCTION = "brief"
    CATEGORY = NODE_CATEGORY_CN
    DESCRIPTION = "为整套 PPT 生成统一设计规范，写回 PPT束。"

    def brief(self, **kwargs):
        result = run_ppt_design_brief(
            read_input(kwargs, "PPT束", None),
            read_input(kwargs, "参考图像", None),
            read_input(kwargs, "配置路径", ""),
            int(read_input(kwargs, "最长边", 2400) or 2400),
        )
        return result["pipe"], result["design_brief_json"], result["reference_analysis_json"]


class ImagenStudioPPTPageComposer:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "PPT束": (IMAGEN_PPT_PIPE_TYPE, {"tooltip": "连接 PPT 设计规范或 PPT 大纲规划输出。"}),
                "配置路径": ("STRING", {"default": ""}),
            },
        }

    RETURN_TYPES = (IMAGEN_PPT_PIPE_TYPE, "STRING", "STRING")
    RETURN_NAMES = ("PPT束", "Prompt列表JSON", "页面JSON")
    FUNCTION = "compose"
    CATEGORY = NODE_CATEGORY_CN
    DESCRIPTION = "逐页拼装 PPT 生图 prompt，写回 PPT束。"

    def compose(self, **kwargs):
        result = run_ppt_page_compose(
            read_input(kwargs, "PPT束", None),
            read_input(kwargs, "配置路径", ""),
        )
        return result["pipe"], result["prompt_list_json"], result["pages_json"]


class ImagenStudioPPTRunningHubBatch:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "PPT束": (IMAGEN_PPT_PIPE_TYPE, {"tooltip": "连接 PPT 页面拼装输出。"}),
                "渠道": (studio.RUNNINGHUB_CHANNEL_OPTIONS_CN, {"default": "第三方低价渠道"}),
                "分辨率": (studio.RUNNINGHUB_RESOLUTIONS, {"default": "1k"}),
                "质量": (studio.RUNNINGHUB_QUALITY_OPTIONS, {"default": studio.RUNNINGHUB_DEFAULT_QUALITY}),
                "单页超时分钟": ("INT", {"default": 30, "min": 1, "max": 180, "step": 1, "tooltip": "每一页 RunningHub 任务最多等待多久。PPT 页面通常比普通图更慢，默认 30 分钟。"}),
                "轮询间隔秒": ("INT", {"default": 5, "min": 1, "max": 60, "step": 1, "tooltip": "查询 RunningHub 任务状态的间隔。"}),
                "配置路径": ("STRING", {"default": ""}),
            },
            "optional": {
                "参考图像": ("IMAGE", {"tooltip": "可选，连接后每页 RunningHub 调用会走图生图。"}),
            },
        }

    RETURN_TYPES = ("IMAGE", IMAGEN_PPT_PIPE_TYPE, "STRING")
    RETURN_NAMES = ("图像", "PPT束", "结果JSON")
    FUNCTION = "generate"
    CATEGORY = NODE_CATEGORY_CN
    DESCRIPTION = "逐页调用 RunningHub RHArt G2，输出 PPT 页面图像批次。"

    def generate(self, **kwargs):
        result = run_ppt_runninghub_batch(
            read_input(kwargs, "PPT束", None),
            read_input(kwargs, "渠道", "第三方低价渠道"),
            read_input(kwargs, "分辨率", "1k"),
            read_input(kwargs, "质量", studio.RUNNINGHUB_DEFAULT_QUALITY),
            read_input(kwargs, "配置路径", ""),
            read_input(kwargs, "参考图像", None),
            int(read_input(kwargs, "单页超时分钟", 30) or 30),
            int(read_input(kwargs, "轮询间隔秒", 5) or 5),
        )
        return result["image"], result["pipe"], result["result_json"]


class ImagenStudioPPTExport:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "PPT束": (IMAGEN_PPT_PIPE_TYPE, {"tooltip": "连接 PPT RunningHub 批量生图输出。"}),
                "文件名": ("STRING", {"default": "imagen-ppt"}),
            },
            "optional": {
                "图像": ("IMAGE", {"tooltip": "可选，连接 RunningHub 批量生图的图像批次；不接时会尝试从 PPT束里的 URL 下载。"}),
            },
        }

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("PPT文件路径", "导出JSON")
    FUNCTION = "export"
    CATEGORY = NODE_CATEGORY_CN
    OUTPUT_NODE = True
    DESCRIPTION = "把页面图像导出为图片型 PPTX 文件。"

    def export(self, **kwargs):
        result = run_ppt_export(
            read_input(kwargs, "PPT束", None),
            read_input(kwargs, "图像", None),
            read_input(kwargs, "文件名", "imagen-ppt"),
        )
        return result["path"], result["export_json"]


NODE_CLASS_MAPPINGS = {
    "ImagenStudioPPTOutlineDraft": ImagenStudioPPTOutlineDraft,
    "ImagenStudioPPTOutlinePlan": ImagenStudioPPTOutlinePlan,
    "ImagenStudioPPTDesignBrief": ImagenStudioPPTDesignBrief,
    "ImagenStudioPPTPageComposer": ImagenStudioPPTPageComposer,
    "ImagenStudioPPTRunningHubBatch": ImagenStudioPPTRunningHubBatch,
    "ImagenStudioPPTExport": ImagenStudioPPTExport,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "ImagenStudioPPTOutlineDraft": "Imagen Studio PPT 大纲草拟",
    "ImagenStudioPPTOutlinePlan": "Imagen Studio PPT 大纲规划",
    "ImagenStudioPPTDesignBrief": "Imagen Studio PPT 设计规范",
    "ImagenStudioPPTPageComposer": "Imagen Studio PPT 页面拼装",
    "ImagenStudioPPTRunningHubBatch": "Imagen Studio PPT RunningHub 批量生图",
    "ImagenStudioPPTExport": "Imagen Studio PPT 导出",
}

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "IMAGEN_PPT_PIPE_TYPE"]
