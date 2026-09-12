"""
ComfyUI Custom Node: Prompt
提示词节点 - 批量提示词加载和AI提示词优化
"""

import requests
import hashlib
import io
import json
import os
import glob
import re
import time
import uuid
import zipfile
from pathlib import Path, PurePosixPath

import numpy as np
from PIL import Image

KK_IMAGE_API_CONFIG_TYPE = "KK_IMAGE_API_CONFIG"
KK_MARKDOWN_FILE_TYPE = "KK_MARKDOWN_FILE"
MAX_MARKDOWN_FILE_BYTES = 5 * 1024 * 1024
MAX_MARKDOWN_FILES = 100
MAX_MARKDOWN_ARCHIVE_BYTES = 50 * 1024 * 1024


def _skills_library_dir():
    configured = str(os.environ.get("KKTOOLS_SKILLS_DIR") or "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    try:
        import folder_paths
    except ImportError:
        return Path(__file__).resolve().parent.parent / "skills-templates"
    return Path(folder_paths.get_user_directory()).resolve() / "kktools" / "skills-templates"


SKILLS_LIBRARY_DIR = _skills_library_dir()
SKILLS_INDEX_PATH = SKILLS_LIBRARY_DIR / "index.json"

PROVIDER_MODEL_OPTIONS = {
    "deepseek": [
        "deepseek-v4-flash",
        "deepseek-v4-pro",
        "deepseek-v4-flash-vision-exp",
        "custom",
    ],
    "openai": [
        "gpt-5.6-sol",
        "gpt-5.6-terra",
        "gpt-5.6-luna",
        "gpt-5.6",
        "gpt-5.4",
        "gpt-5.4-pro",
        "gpt-5-mini",
        "gpt-5-nano",
        "gpt-5.1",
        "gpt-5",
        "gpt-4.1",
        "gpt-4.1-mini",
        "gpt-4.1-nano",
        "gpt-4o",
        "gpt-4o-mini",
        "o3",
        "o4-mini",
        "o3-mini",
        "custom",
    ],
    "gemini": [
        "gemini-3.8-flash",
        "gemini-3.7-flash",
        "gemini-3.6-flash",
        "gemini-3.5-flash",
        "gemini-3.5-flash-lite",
        "gemini-3.1-flash-lite",
        "gemini-3.1-pro-preview",
        "gemini-3-flash-preview",
        "gemini-2.5-pro",
        "gemini-2.5-flash",
        "gemini-2.5-flash-lite",
        "custom",
    ],
    "doubao": [
        "doubao-seed-2-0-pro-260215",
        "doubao-seed-2-0-lite-260428",
        "doubao-seed-2-0-lite-260215",
        "doubao-seed-2-0-mini-260428",
        "doubao-seed-2-0-code-preview-260215",
        "doubao-seed-1-6-251015",
        "doubao-seed-1-6-250615",
        "doubao-seed-1-6-thinking-250715",
        "doubao-seed-1-6-flash-250715",
        "doubao-1-5-thinking-pro",
        "doubao-1-5-thinking-vision-pro",
        "doubao-1-5-pro-32k-250115",
        "doubao-1-5-lite-32k-250115",
        "custom",
    ],
}

LEGACY_SYSTEM_MESSAGES = {
    "你是一个专业的AI绘画提示词优化专家。请根据用户要求优化提示词，直接输出优化后的提示词，不要添加任何解释或标记。",
}
LEGACY_SYSTEM_MESSAGE_MARKERS = (
    "AI绘画提示词优化专家",
    "请根据用户要求优化提示词",
)


class kkBatchPrompt:
    """批量提示词节点 - 用于批量加载和处理提示词"""
    
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "prompt_file": ("STRING", {
                    "default": "",
                    "multiline": False,
                    "placeholder": "输入提示词文件路径或目录路径"
                }),
                "file_mode": (["single_file", "directory"], {
                    "default": "single_file"
                }),
                "batch_size": ("INT", {
                    "default": 1,
                    "min": 1,
                    "max": 100,
                    "step": 1
                }),
                "current_batch": ("INT", {
                    "default": 0,
                    "min": 0,
                    "max": 999,
                    "step": 1
                }),
            }
        }
    
    RETURN_TYPES = ("STRING", "INT", "INT", "STRING")
    RETURN_NAMES = ("prompt", "batch_index", "total_batches", "file_info")
    FUNCTION = "load_prompt"
    CATEGORY = "🌟kktools/提示词"
    
    def load_prompt(self, prompt_file, file_mode, batch_size, current_batch):
        """
        加载批量提示词
        
        Args:
            prompt_file: 提示词文件路径或目录路径
            file_mode: 文件模式（单个文件或目录）
            batch_size: 批量大小
            current_batch: 当前批次
            
        Returns:
            (提示词, 批次索引, 总批次数, 文件信息)
        """
        try:
            prompts = []
            
            if file_mode == "single_file":
                # 单个文件模式
                if os.path.isfile(prompt_file):
                    with open(prompt_file, 'r', encoding='utf-8') as f:
                        if prompt_file.endswith('.json'):
                            # JSON文件处理
                            data = json.load(f)
                            if isinstance(data, list):
                                prompts = data
                            elif isinstance(data, dict):
                                prompts = list(data.values())
                            else:
                                prompts = [str(data)]
                        else:
                            # 文本文件处理
                            prompts = [line.strip() for line in f if line.strip()]
                else:
                    return ("", 0, 0, f"文件不存在: {prompt_file}")
            
            else:  # directory mode
                # 目录模式 - 读取目录下所有文本文件
                if os.path.isdir(prompt_file):
                    text_files = glob.glob(os.path.join(prompt_file, "*.txt")) + \
                                glob.glob(os.path.join(prompt_file, "*.json"))
                    
                    for file_path in text_files:
                        try:
                            with open(file_path, 'r', encoding='utf-8') as f:
                                if file_path.endswith('.json'):
                                    data = json.load(f)
                                    if isinstance(data, list):
                                        prompts.extend(data)
                                    elif isinstance(data, dict):
                                        prompts.extend(list(data.values()))
                                    else:
                                        prompts.append(str(data))
                                else:
                                    prompts.extend([line.strip() for line in f if line.strip()])
                        except Exception as e:
                            print(f"读取文件 {file_path} 时出错: {e}")
                else:
                    return ("", 0, 0, f"目录不存在: {prompt_file}")
            
            if not prompts:
                return ("", 0, 0, "未找到有效的提示词")
            
            # 计算批次信息
            total_batches = (len(prompts) + batch_size - 1) // batch_size
            batch_index = current_batch % total_batches if total_batches > 0 else 0
            
            # 获取当前批次的提示词
            start_idx = batch_index * batch_size
            end_idx = min(start_idx + batch_size, len(prompts))
            current_prompts = prompts[start_idx:end_idx]
            
            # 合并当前批次的提示词
            combined_prompt = "\n".join(current_prompts)
            
            # 打印调试信息
            print(f"Batch Prompt Loader:")
            print(f"  File Mode: {file_mode}")
            print(f"  Total Prompts: {len(prompts)}")
            print(f"  Batch Size: {batch_size}")
            print(f"  Current Batch: {batch_index + 1}/{total_batches}")
            print(f"  Prompts in Batch: {len(current_prompts)}")
            
            file_info = f"批次 {batch_index + 1}/{total_batches}, 本批次提示词数: {len(current_prompts)}"
            
            return (combined_prompt, batch_index, total_batches, file_info)
            
        except Exception as e:
            error_msg = f"加载提示词时出错: {str(e)}"
            print(f"Batch Prompt Loader Error: {error_msg}")
            return ("", 0, 0, error_msg)


class kkMarkdownUpload:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "markdown_file": ("STRING", {
                    "default": "",
                    "multiline": False,
                    "placeholder": "点击下方按钮上传 .md 文件",
                }),
            },
            "optional": {
                "folder_path": ("STRING", {
                    "default": "",
                    "multiline": False,
                    "placeholder": "ComfyUI input 内的文件夹地址",
                }),
                "archive_file": ("STRING", {
                    "default": "",
                    "multiline": False,
                    "placeholder": "点击下方按钮上传 .zip 压缩包",
                }),
                "Tag": ("STRING", {
                    "default": "",
                    "multiline": False,
                    "placeholder": "可选分类标签，例如：人像 / PPT / 电商",
                    "tooltip": "随 Markdown 文件一起输出，供 Skills 模板选择器使用。",
                }),
            },
        }

    RETURN_TYPES = (KK_MARKDOWN_FILE_TYPE, "STRING")
    RETURN_NAMES = ("Markdown文件", "Tag")
    FUNCTION = "load"
    CATEGORY = "🌟kktools/提示词"

    @classmethod
    def IS_CHANGED(cls, markdown_file, folder_path="", archive_file="", Tag=""):
        try:
            items = _load_markdown_sources(markdown_file, folder_path, archive_file)
            digest = hashlib.sha1()
            for item in items:
                digest.update(item["filename"].encode("utf-8"))
                digest.update(item["content"].encode("utf-8"))
            return digest.hexdigest()
        except (OSError, ValueError, RuntimeError, zipfile.BadZipFile):
            return f"{markdown_file}|{folder_path}|{archive_file}|{Tag}"

    def load(self, markdown_file, folder_path="", archive_file="", Tag=""):
        items = _load_markdown_sources(markdown_file, folder_path, archive_file)
        return ({
            "filename": items[0]["filename"] if len(items) == 1 else f"Markdown集合（{len(items)}个文件）",
            "content": "\n\n".join(item["content"] for item in items),
            "items": items,
        }, str(Tag or "").strip())


def _input_path(value, expected):
    import folder_paths

    relative_path = str(value or "").strip()
    input_root = Path(folder_paths.get_input_directory()).resolve()
    path = (input_root / relative_path).resolve()
    if not relative_path or os.path.commonpath((str(input_root), str(path))) != str(input_root):
        raise RuntimeError("Markdown 来源必须位于 ComfyUI 输入目录。")
    if expected == "file" and not path.is_file():
        raise RuntimeError(f"文件不存在：{relative_path}")
    if expected == "directory" and not path.is_dir():
        raise RuntimeError(f"文件夹不存在：{relative_path}")
    return input_root, path


def _read_markdown_file(path, display_name):
    if path.stat().st_size > MAX_MARKDOWN_FILE_BYTES:
        raise RuntimeError(f"Markdown 文件不能超过 5 MB：{display_name}")
    try:
        return {"filename": display_name, "content": path.read_text(encoding="utf-8")}
    except UnicodeDecodeError as exc:
        raise RuntimeError(f"Markdown 文件必须使用 UTF-8 编码：{display_name}") from exc


def _load_markdown_sources(markdown_file="", folder_path="", archive_file=""):
    archive_value = str(archive_file or "").strip()
    folder_value = str(folder_path or "").strip()
    markdown_value = str(markdown_file or "").strip()
    if archive_value:
        _input_root, path = _input_path(archive_value, "file")
        if path.suffix.lower() != ".zip":
            raise RuntimeError("压缩包仅支持 .zip 格式。")
        if path.stat().st_size > MAX_MARKDOWN_ARCHIVE_BYTES:
            raise RuntimeError("ZIP 压缩包不能超过 50 MB。")
        items = []
        total_size = 0
        try:
            with zipfile.ZipFile(path) as archive:
                entries = [entry for entry in archive.infolist() if not entry.is_dir() and Path(entry.filename).suffix.lower() == ".md"]
                if len(entries) > MAX_MARKDOWN_FILES:
                    raise RuntimeError("ZIP 内 Markdown 文件不能超过 100 个。")
                for entry in entries:
                    total_size += entry.file_size
                    if entry.file_size > MAX_MARKDOWN_FILE_BYTES or total_size > MAX_MARKDOWN_ARCHIVE_BYTES:
                        raise RuntimeError("ZIP 内 Markdown 文件大小超出限制。")
                    try:
                        content = archive.read(entry).decode("utf-8")
                    except UnicodeDecodeError as exc:
                        raise RuntimeError(f"Markdown 文件必须使用 UTF-8 编码：{entry.filename}") from exc
                    items.append({"filename": f"{path.name}/{entry.filename}", "content": content})
        except zipfile.BadZipFile as exc:
            raise RuntimeError("ZIP 压缩包格式无效或文件已损坏。") from exc
    elif folder_value:
        input_root, path = _input_path(folder_value, "directory")
        files = sorted(
            item for item in path.rglob("*.md")
            if item.is_file() and os.path.commonpath((str(input_root), str(item.resolve()))) == str(input_root)
        )
        if len(files) > MAX_MARKDOWN_FILES:
            raise RuntimeError("文件夹内 Markdown 文件不能超过 100 个。")
        items = [_read_markdown_file(item, item.relative_to(input_root).as_posix()) for item in files]
    elif markdown_value:
        input_root, path = _input_path(markdown_value, "file")
        if path.suffix.lower() != ".md":
            raise RuntimeError("仅支持 .md 文件。")
        items = [_read_markdown_file(path, path.relative_to(input_root).as_posix())]
    else:
        raise RuntimeError("请上传 Markdown 文件、填写文件夹地址或上传 ZIP 压缩包。")
    if not items:
        raise RuntimeError("没有找到可加载的 Markdown 文件。")
    return items


def _read_skills_index():
    if not SKILLS_INDEX_PATH.is_file():
        return {"version": 1, "skills": []}
    try:
        data = json.loads(SKILLS_INDEX_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError("Skills 模板库 index.json 读取失败。") from exc
    if not isinstance(data, dict) or not isinstance(data.get("skills"), list):
        raise RuntimeError("Skills 模板库 index.json 格式不正确。")
    return data


def _write_skills_index(data):
    SKILLS_LIBRARY_DIR.mkdir(parents=True, exist_ok=True)
    temp_path = SKILLS_INDEX_PATH.with_suffix(".json.tmp")
    temp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temp_path, SKILLS_INDEX_PATH)


def _skill_record(skill_id):
    clean_id = str(skill_id or "").strip()
    return next((item for item in _read_skills_index()["skills"] if item.get("id") == clean_id), None)


def _skill_cover_path(skill_id):
    return SKILLS_LIBRARY_DIR / "covers" / f"{skill_id}.jpg"


def _save_skill_cover(skill_id, image):
    if image is None:
        return False
    array = image.detach().cpu().numpy() if hasattr(image, "detach") else np.asarray(image)
    if array.ndim == 4:
        array = array[0]
    if array.ndim != 3 or array.shape[-1] < 3:
        raise RuntimeError("封面图必须是有效的 ComfyUI IMAGE。")
    rgb = np.clip(array[..., :3] * 255.0, 0, 255).astype(np.uint8)
    cover = Image.fromarray(rgb).convert("RGB")
    edge = max(cover.size)
    if edge > 512:
        scale = 512 / edge
        cover = cover.resize((max(1, round(cover.width * scale)), max(1, round(cover.height * scale))), Image.LANCZOS)
    path = _skill_cover_path(skill_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    buffer = io.BytesIO()
    cover.save(buffer, format="JPEG", quality=88, optimize=True)
    path.write_bytes(buffer.getvalue())
    return True


def _save_skill(markdown_file, cover=None, tag=""):
    content = str(markdown_file.get("content") or "")
    if not content.strip():
        raise RuntimeError("Skill Markdown 内容为空。")
    source_name = Path(str(markdown_file.get("filename") or "skill.md")).stem or "未命名 Skill"
    skill_id = f"skill-{hashlib.sha1(content.encode('utf-8')).hexdigest()[:16]}"
    index = _read_skills_index()
    records = [dict(item) for item in index["skills"]]
    position = next((i for i, item in enumerate(records) if item.get("id") == skill_id), -1)
    existing = records[position] if position >= 0 else {}
    clean_tag = str(tag or existing.get("tag") or "").strip()
    now = int(time.time() * 1000)
    has_cover = _save_skill_cover(skill_id, cover) or bool(existing.get("hasCover"))
    record = {
        "id": skill_id,
        "name": existing.get("name") or source_name,
        "tag": clean_tag,
        "description": next((line.lstrip("# ").strip() for line in content.splitlines() if line.strip()), ""),
        "content": content,
        "sourceFilename": str(markdown_file.get("filename") or ""),
        "hasCover": has_cover,
        "createdAt": existing.get("createdAt") or now,
        "updatedAt": now,
    }
    if position >= 0:
        records[position] = record
    else:
        records.append(record)
    index["skills"] = sorted(records, key=lambda item: int(item.get("updatedAt") or 0), reverse=True)
    _write_skills_index(index)
    return record


def _rename_skill(skill_id, name):
    clean_name = str(name or "").strip()
    if not clean_name:
        raise RuntimeError("Skill 名称不能为空。")
    index = _read_skills_index()
    for record in index["skills"]:
        if record.get("id") == skill_id:
            record["name"] = clean_name
            record["updatedAt"] = int(time.time() * 1000)
            _write_skills_index(index)
            return record
    raise RuntimeError(f"Skills 模板库中未找到：{skill_id}")


def _tag_skill(skill_id, tag):
    index = _read_skills_index()
    for record in index["skills"]:
        if record.get("id") == skill_id:
            record["tag"] = str(tag or "").strip()
            record["updatedAt"] = int(time.time() * 1000)
            _write_skills_index(index)
            return record
    raise RuntimeError(f"Skills 模板库中未找到：{skill_id}")


def _delete_skill(skill_id):
    index = _read_skills_index()
    record = next((item for item in index["skills"] if item.get("id") == skill_id), None)
    if not record:
        raise RuntimeError(f"Skills 模板库中未找到：{skill_id}")
    index["skills"] = [item for item in index["skills"] if item.get("id") != skill_id]
    _write_skills_index(index)
    cover_path = _skill_cover_path(skill_id)
    if cover_path.is_file() and SKILLS_LIBRARY_DIR.resolve() in cover_path.resolve().parents:
        cover_path.unlink()
    return record


def _skill_summaries():
    return [{
        "id": item.get("id"),
        "name": item.get("name"),
        "tag": item.get("tag", ""),
        "description": item.get("description"),
        "sourceFilename": item.get("sourceFilename"),
        "coverUrl": f"/kktools/skills/cover?id={item.get('id')}&t={item.get('updatedAt')}" if item.get("hasCover") else "",
        "createdAt": item.get("createdAt"),
        "updatedAt": item.get("updatedAt"),
    } for item in _read_skills_index()["skills"]]


def _skill_package_files(archive):
    files = {}
    total_size = 0
    for entry in archive.infolist():
        if entry.is_dir():
            continue
        if entry.flag_bits & 1:
            raise RuntimeError("模板包不能包含加密文件。")
        name = entry.filename.replace("\\", "/")
        path = PurePosixPath(name)
        if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
            raise RuntimeError(f"模板包包含无效路径：{entry.filename}")
        total_size += entry.file_size
        if total_size > MAX_MARKDOWN_ARCHIVE_BYTES:
            raise RuntimeError("模板包解压后的总大小不能超过 50 MB。")
        files[path.as_posix()] = entry
    if len(files) > MAX_MARKDOWN_FILES * 2 + 1:
        raise RuntimeError("模板包内文件数量过多。")
    return files


def _skill_package_specs(archive, files):
    manifest_entry = files.get("manifest.json")
    if manifest_entry:
        manifest = json.loads(archive.read(manifest_entry).decode("utf-8"))
        if not isinstance(manifest, dict) or manifest.get("format") != "kktools-skills" or not isinstance(manifest.get("skills"), list):
            raise RuntimeError("模板包 manifest.json 格式不正确。")
        if len(manifest["skills"]) > MAX_MARKDOWN_FILES:
            raise RuntimeError("模板包内 Skill 不能超过 100 个。")
        specs = []
        for item in manifest["skills"]:
            if not isinstance(item, dict):
                raise RuntimeError("模板包 manifest.json 包含无效 Skill。")
            markdown = str(item.get("markdown") or "").replace("\\", "/")
            cover = str(item.get("cover") or "").replace("\\", "/")
            if markdown not in files or Path(markdown).suffix.lower() != ".md":
                raise RuntimeError(f"模板包缺少 Markdown：{markdown}")
            if cover and cover not in files:
                raise RuntimeError(f"模板包缺少封面：{cover}")
            specs.append({"name": str(item.get("name") or "").strip(), "tag": str(item.get("tag") or "").strip(), "markdown": markdown, "cover": cover})
        return specs

    markdown_paths = sorted(name for name in files if Path(name).suffix.lower() == ".md")
    if len(markdown_paths) > MAX_MARKDOWN_FILES:
        raise RuntimeError("模板包内 Skill 不能超过 100 个。")
    specs = []
    for markdown in markdown_paths:
        path = PurePosixPath(markdown)
        cover = next((
            path.with_suffix(suffix).as_posix()
            for suffix in (".jpg", ".jpeg", ".png", ".webp")
            if path.with_suffix(suffix).as_posix() in files
        ), "")
        specs.append({"name": path.stem, "tag": "", "markdown": markdown, "cover": cover})
    return specs


def _skill_cover_from_package(archive, entry):
    if entry.file_size > MAX_MARKDOWN_FILE_BYTES:
        raise RuntimeError(f"封面文件不能超过 5 MB：{entry.filename}")
    image = Image.open(io.BytesIO(archive.read(entry)))
    if image.width > 4096 or image.height > 4096 or image.width * image.height > 16_000_000:
        raise RuntimeError(f"封面图片尺寸过大：{entry.filename}")
    return np.asarray(image.convert("RGB"), dtype=np.float32) / 255.0


def _import_skill_package(data):
    imported = 0
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        files = _skill_package_files(archive)
        specs = _skill_package_specs(archive, files)
        if not specs:
            raise RuntimeError("模板包中没有 Markdown Skill。")
        for spec in specs:
            entry = files[spec["markdown"]]
            if entry.file_size > MAX_MARKDOWN_FILE_BYTES:
                raise RuntimeError(f"Markdown 文件不能超过 5 MB：{spec['markdown']}")
            content = archive.read(entry).decode("utf-8")
            record = _save_skill({"filename": Path(spec["markdown"]).name, "content": content}, tag=spec.get("tag", ""))
            if spec["name"]:
                record = _rename_skill(record["id"], spec["name"])
            if spec.get("tag") is not None:
                record = _tag_skill(record["id"], spec["tag"])
            if spec["cover"]:
                _save_skill_cover(record["id"], _skill_cover_from_package(archive, files[spec["cover"]]))
                index = _read_skills_index()
                for item in index["skills"]:
                    if item.get("id") == record["id"]:
                        item["hasCover"] = True
                _write_skills_index(index)
            imported += 1
    return imported


def _export_skill_package():
    buffer = io.BytesIO()
    manifest = {"format": "kktools-skills", "version": 1, "skills": []}
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for item in _read_skills_index()["skills"]:
            skill_id = str(item["id"])
            safe_name = re.sub(r"[\\/:*?\"<>|]", "_", item.get("name") or skill_id).strip() or skill_id
            directory = f"skills/{skill_id}"
            markdown_path = f"{directory}/{safe_name}.md"
            archive.writestr(markdown_path, item.get("content") or "")
            exported = {"name": item.get("name") or skill_id, "tag": item.get("tag", ""), "markdown": markdown_path}
            cover = _skill_cover_path(skill_id)
            if item.get("hasCover") and cover.is_file():
                cover_path = f"{directory}/{safe_name}.jpg"
                archive.writestr(cover_path, cover.read_bytes())
                exported["cover"] = cover_path
            manifest["skills"].append(exported)
        archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
    return buffer.getvalue()


class kkSkillsTemplateSelector:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "Skill ID": ("STRING", {"default": "", "multiline": False, "placeholder": "从下方 Skills 卡片中选择"}),
            },
            "optional": {
                "Markdown文件": (KK_MARKDOWN_FILE_TYPE, {"tooltip": "连接 kkMarkdown上传；执行后自动保存到 Skills 模板库。"}),
                "Tag": ("STRING", {"default": "", "multiline": False, "forceInput": True, "tooltip": "可选分类标签，连接 kkMarkdown上传 的 Tag 输出。"}),
                "封面图": ("IMAGE", {"tooltip": "可选，作为本次入库 Skill 的卡片封面。"}),
            },
        }

    RETURN_TYPES = (KK_MARKDOWN_FILE_TYPE, "STRING", "STRING")
    RETURN_NAMES = ("Markdown文件", "Skill名称", "状态")
    FUNCTION = "select"
    CATEGORY = "🌟kktools/提示词"
    OUTPUT_NODE = True

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return time.time()

    def select(self, **kwargs):
        markdown_file = kwargs.get("Markdown文件")
        if isinstance(markdown_file, dict):
            items = markdown_file.get("items") if isinstance(markdown_file.get("items"), list) else [markdown_file]
            records = [_save_skill(item, kwargs.get("封面图"), kwargs.get("Tag", "")) for item in items if isinstance(item, dict)]
            if not records:
                raise RuntimeError("Markdown 束中没有可保存的 Skill。")
            record = records[0]
            status = f"已保存 {len(records)} 个 Skill 到模板库"
        else:
            skill_id = str(kwargs.get("Skill ID") or "").strip()
            if not skill_id:
                raise RuntimeError("请连接 Markdown 文件或从 Skills 模板选择器中选择一个 Skill。")
            record = _skill_record(skill_id)
            if not record:
                raise RuntimeError(f"Skills 模板库中未找到：{skill_id}")
            status = "Skill 已选择"
        skill_items = [{
            "filename": item.get("sourceFilename") or f"{item['name']}.md",
            "content": item["content"],
            "tag": item.get("tag", ""),
        } for item in _read_skills_index()["skills"]]
        return {
            "ui": {"skill_id": [record["id"]]},
            "result": (
                {
                    "filename": record.get("sourceFilename") or f"{record['name']}.md",
                    "content": record["content"],
                    "items": skill_items,
                },
                record["name"],
                status,
            ),
        }


class kkLLM:
    """多厂商 LLM 提示词优化节点，支持 DeepSeek、OpenAI、Gemini 和豆包 API。"""
    
    @classmethod
    def INPUT_TYPES(cls):
        default_provider = "deepseek"
        default_models = cls._get_provider_models(default_provider)
        return {
            "required": {
                "base_prompt": ("STRING", {
                    "default": "",
                    "multiline": True,
                    "placeholder": "可选；连接 Markdown 文件后可留空"
                }),
                "api_key": ("STRING", {
                    "default": "",
                    "multiline": False,
                    "placeholder": "输入 API Key"
                }),
                "provider": (["deepseek", "openai", "gemini", "doubao"], {
                    "default": "deepseek"
                }),
                "model": (default_models, {
                    "default": default_models[0]
                }),
                "custom_model": ("STRING", {
                    "default": "",
                    "multiline": False,
                    "placeholder": "仅当 model=custom 时生效；Ark 也可填写接入点 ID"
                }),
                "base_url": ("STRING", {
                    "default": "",
                    "multiline": False,
                    "placeholder": "留空使用对应厂商默认 API 地址"
                }),
                "system_message": ("STRING", {
                    "default": "",
                    "multiline": True,
                    "placeholder": "可选：输入系统角色设定；留空则不发送 system 消息"
                }),
            },
            "optional": {
                "Markdown文件": (KK_MARKDOWN_FILE_TYPE, {
                    "tooltip": "连接 kkMarkdown上传；连接后使用 Markdown 文件全文作为基础提示词。",
                }),
                "API配置": (KK_IMAGE_API_CONFIG_TYPE, {
                    "tooltip": "连接 kk_API配置 后，优先使用其中的 Base URL 和 API Key。",
                }),
                "max_length": ("INT", {
                    "default": 500,
                    "min": 50,
                    "max": 2000,
                    "step": 50
                }),
                "temperature": ("FLOAT", {
                    "default": 0.7,
                    "min": 0.1,
                    "max": 1.0,
                    "step": 0.1
                }),
            }
        }
    
    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("original_prompt", "optimized_prompt", "optimization_info")
    FUNCTION = "optimize_prompt"
    CATEGORY = "🌟kktools/提示词"
    
    def optimize_prompt(
        self,
        base_prompt="",
        api_key="",
        provider="deepseek",
        model="deepseek-v4-flash",
        custom_model="",
        base_url="",
        system_message="",
        max_length=500,
        temperature=0.7,
        API配置=None,
        Markdown文件=None,
    ):
        """
        通过多厂商 LLM API 优化提示词
        
        Args:
            base_prompt: 基础提示词
            api_key: API密钥
            provider: 提供商
            model: 模型名
            base_url: 自定义 API 地址
            system_message: 系统角色设定
            max_length: 最大长度
            temperature: 生成温度
            
        Returns:
            (原始提示词, 优化后的提示词, 优化信息)
        """
        try:
            if isinstance(Markdown文件, dict):
                base_prompt = str(Markdown文件.get("content") or "")
            if isinstance(API配置, dict):
                api_key = str(API配置.get("api_key") or api_key or "").strip()
                configured_base_url = str(API配置.get("base_url") or "").strip()
                if configured_base_url:
                    base_url = self._chat_endpoint_from_config(configured_base_url)

            if not base_prompt.strip():
                return (base_prompt, "", "错误: 基础提示词为空")
            
            if not api_key.strip():
                return (base_prompt, base_prompt, "警告: 未提供API密钥，返回原始提示词")
            
            # 原样发送用户输入，不额外拼接任何提示词指令。
            user_message = base_prompt
            
            # 调用对应 LLM API
            optimized_prompt = self._call_llm_api(
                base_prompt=base_prompt,
                system_message=system_message,
                user_message=user_message,
                api_key=api_key,
                provider=provider,
                model=model,
                custom_model=custom_model,
                base_url=base_url,
                max_length=max_length,
                temperature=temperature,
            )
            
            if optimized_prompt:
                resolved_model = self._resolve_model(provider, model, custom_model)
                info = f"优化完成 | provider={provider} | model={resolved_model}"
                return (base_prompt, optimized_prompt, info)
            else:
                return (base_prompt, base_prompt, "API调用失败，返回原始提示词")
                
        except Exception as e:
            error_msg = f"优化提示词时出错: {str(e)}"
            print(f"kkLLM Error: {error_msg}")
            return (base_prompt, base_prompt, f"错误: {error_msg}")

    @staticmethod
    def _chat_endpoint_from_config(base_url):
        url = str(base_url or "").strip().rstrip("/")
        if url.endswith("/chat/completions"):
            return url
        if url.endswith("/v1"):
            return f"{url}/chat/completions"
        return f"{url}/v1/chat/completions"
    
    @classmethod
    def _get_provider_models(cls, provider):
        return list(PROVIDER_MODEL_OPTIONS.get(provider, ["custom"]))

    def _resolve_model(self, provider, model, custom_model=""):
        available_models = self._get_provider_models(provider)
        selected_model = str(model).strip()
        custom_model = str(custom_model).strip()

        if not selected_model:
            selected_model = available_models[0] if available_models else ""

        if selected_model == "custom":
            if custom_model:
                return custom_model
            raise ValueError(f"{provider} 选择 custom 时必须填写 custom_model。")

        # 兼容旧工作流或手动修改后的未知模型值。
        if selected_model not in available_models and selected_model:
            return selected_model

        return selected_model

    def _resolve_base_url(self, provider, base_url, model):
        base_url = base_url.strip()
        if base_url:
            return base_url

        if provider == "deepseek":
            return "https://api.deepseek.com/chat/completions"
        if provider == "openai":
            return "https://api.openai.com/v1/chat/completions"
        if provider == "doubao":
            return "https://ark.cn-beijing.volces.com/api/v3/chat/completions"
        if provider == "gemini":
            return f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

        raise ValueError(f"不支持的 provider: {provider}")

    def _normalize_system_message(self, system_message):
        text = str(system_message or "").strip()
        if text in LEGACY_SYSTEM_MESSAGES:
            return ""
        if all(marker in text for marker in LEGACY_SYSTEM_MESSAGE_MARKERS):
            return ""
        return text

    def _parse_openai_compatible_content(self, result):
        content = result["choices"][0]["message"]["content"]
        if isinstance(content, list):
            text_parts = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    text_parts.append(item.get("text", ""))
                elif isinstance(item, str):
                    text_parts.append(item)
            return "".join(text_parts).strip()
        return str(content).strip()

    def _parse_gemini_content(self, result):
        candidates = result.get("candidates", [])
        if not candidates:
            raise ValueError("Gemini 返回结果中没有 candidates。")

        parts = candidates[0].get("content", {}).get("parts", [])
        texts = []
        for part in parts:
            if isinstance(part, dict) and "text" in part:
                texts.append(part["text"])

        if not texts:
            raise ValueError("Gemini 返回结果中没有文本内容。")

        return "".join(texts).strip()

    def _call_llm_api(self, base_prompt, system_message, user_message, api_key, provider, model, custom_model, base_url, max_length, temperature):
        """调用多厂商 LLM API"""
        try:
            resolved_model = self._resolve_model(provider, model, custom_model)
            url = self._resolve_base_url(provider, base_url, resolved_model)
            system_message = self._normalize_system_message(system_message)

            if provider == "gemini":
                headers = {
                    "Content-Type": "application/json",
                }
                payload = {
                    "contents": [
                        {
                            "role": "user",
                            "parts": [
                                {
                                    "text": user_message
                                }
                            ]
                        }
                    ],
                    "generationConfig": {
                        "temperature": temperature,
                        "maxOutputTokens": max_length,
                    }
                }
                if str(system_message or "").strip():
                    payload["system_instruction"] = {
                        "parts": [
                            {
                                "text": system_message
                            }
                        ]
                    }
                response = requests.post(
                    url,
                    headers=headers,
                    params={"key": api_key},
                    json=payload,
                    timeout=30,
                )
            else:
                headers = {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {api_key}"
                }
                messages = []
                if str(system_message or "").strip():
                    messages.append({
                        "role": "system",
                        "content": system_message
                    })
                messages.append({
                    "role": "user",
                    "content": user_message
                })
                payload = {
                    "model": resolved_model,
                    "messages": messages,
                    "max_tokens": max_length,
                    "temperature": temperature,
                    "stream": False
                }
                response = requests.post(url, headers=headers, json=payload, timeout=30)

            if response.status_code == 402:
                print(f"{provider} API 需要付费或额度不足，使用本地优化作为备选方案")
                return self._local_prompt_optimization(base_prompt)
            
            response.raise_for_status()
            
            result = response.json()

            if provider == "gemini":
                optimized_prompt = self._parse_gemini_content(result)
            else:
                optimized_prompt = self._parse_openai_compatible_content(result)
            
            # 清理可能的标记和解释
            optimized_prompt = self._clean_prompt(optimized_prompt)
            
            # 打印调试信息
            print(f"kkLLM API Call:")
            print(f"  Provider: {provider}")
            print(f"  Model: {resolved_model}")
            print(f"  URL: {url}")
            print(f"  Original Length: {len(base_prompt)}")
            print(f"  Optimized Length: {len(optimized_prompt)}")
            print(f"  System Message: {system_message[:50]}...")
            print(f"  User Message: {user_message[:50]}...")
            
            return optimized_prompt
            
        except requests.exceptions.RequestException as e:
            print(f"{provider} API请求错误: {e}，使用本地优化")
            return self._local_prompt_optimization(base_prompt)
        except Exception as e:
            print(f"{provider} API调用错误: {e}，使用本地优化")
            return self._local_prompt_optimization(base_prompt)
    
    def _local_prompt_optimization(self, base_prompt):
        """本地提示词优化备选方案"""
        try:
            # 基础清理和简单优化
            optimized = str(base_prompt or "")
            
            print(f"Local Optimization Applied: {optimized[:100]}...")
            return optimized
            
        except Exception as e:
            print(f"Local optimization error: {e}")
            return base_prompt
    
    def _clean_prompt(self, prompt):
        """清理提示词，移除可能的标记和解释"""
        # 移除常见的标记前缀
        markers = ["优化后的提示词:", "提示词:", "Result:", "Output:", "```", "---"]
        for marker in markers:
            if prompt.startswith(marker):
                prompt = prompt[len(marker):].strip()
        
        # 移除可能的代码块标记
        if prompt.startswith("```text") or prompt.startswith("```prompt"):
            prompt = prompt.split("```", 2)[-1].strip()
        
        # 移除引号
        prompt = prompt.strip('"').strip("'")
        
        return prompt


# ComfyUI 节点注册
NODE_CLASS_MAPPINGS = {
    "kkBatchPrompt": kkBatchPrompt,
    "kkMarkdown上传": kkMarkdownUpload,
    "kkSkills模板选择器": kkSkillsTemplateSelector,
    "kkLLM": kkLLM,
}

# 节点在菜单中显示的名称
NODE_DISPLAY_NAME_MAPPINGS = {
    "kkBatchPrompt": "kkBatchPrompt（批量提示词）",
    "kkMarkdown上传": "kkMarkdown上传",
    "kkSkills模板选择器": "kkSkills模板选择器",
    "kkLLM": "kkLLM（多厂商LLM）",
}

__all__ = ['NODE_CLASS_MAPPINGS', 'NODE_DISPLAY_NAME_MAPPINGS']


try:
    import folder_paths
    from aiohttp import web
    from server import PromptServer

    @PromptServer.instance.routes.post("/kktools/upload_markdown")
    async def kktools_upload_markdown(request):
        reader = await request.multipart()
        field = await reader.next()
        if field is None or field.name != "file" or not field.filename:
            return web.json_response({"error": "未选择文件。"}, status=400)

        filename = Path(field.filename).name
        suffix = Path(filename).suffix.lower()
        if suffix not in {".md", ".zip"}:
            return web.json_response({"error": "仅支持 .md 或 .zip 文件。"}, status=400)

        chunks = []
        total_size = 0
        size_limit = MAX_MARKDOWN_FILE_BYTES if suffix == ".md" else MAX_MARKDOWN_ARCHIVE_BYTES
        while True:
            chunk = await field.read_chunk()
            if not chunk:
                break
            total_size += len(chunk)
            if total_size > size_limit:
                return web.json_response({"error": ".md 不能超过 5 MB，.zip 不能超过 50 MB。"}, status=400)
            chunks.append(chunk)

        if suffix == ".md":
            try:
                b"".join(chunks).decode("utf-8")
            except UnicodeDecodeError:
                return web.json_response({"error": "Markdown 文件必须使用 UTF-8 编码。"}, status=400)

        input_root = Path(folder_paths.get_input_directory()).resolve()
        upload_root = input_root / "kktools_markdown"
        upload_root.mkdir(parents=True, exist_ok=True)
        upload_root = upload_root.resolve()
        if os.path.commonpath((str(input_root), str(upload_root))) != str(input_root):
            return web.json_response({"error": "Markdown 上传目录无效。"}, status=400)
        target = upload_root / filename
        if target.exists():
            target = upload_root / f"{target.stem}-{uuid.uuid4().hex[:8]}{suffix}"
        target.write_bytes(b"".join(chunks))
        relative_path = target.relative_to(input_root).as_posix()
        return web.json_response({"filename": relative_path})

    @PromptServer.instance.routes.get("/kktools/skills")
    async def kktools_get_skills(_request):
        try:
            return web.json_response({"skills": _skill_summaries()})
        except RuntimeError as exc:
            return web.json_response({"error": str(exc)}, status=500)

    @PromptServer.instance.routes.post("/kktools/skills/import")
    async def kktools_import_skills(request):
        try:
            reader = await request.multipart()
            field = await reader.next()
            if field is None or not field.filename or Path(field.filename).suffix.lower() != ".zip":
                return web.json_response({"ok": False, "error": "请选择 .zip 模板包。"}, status=400)
            data = bytearray()
            while True:
                chunk = await field.read_chunk()
                if not chunk:
                    break
                data.extend(chunk)
                if len(data) > MAX_MARKDOWN_ARCHIVE_BYTES:
                    return web.json_response({"ok": False, "error": "模板包不能超过 50 MB。"}, status=400)
            imported = _import_skill_package(data)
            return web.json_response({"ok": True, "imported": imported})
        except (zipfile.BadZipFile, UnicodeDecodeError, OSError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
            return web.json_response({"ok": False, "error": f"模板包导入失败：{exc}"}, status=400)

    @PromptServer.instance.routes.get("/kktools/skills/export")
    async def kktools_export_skills(_request):
        try:
            data = _export_skill_package()
            return web.Response(body=data, content_type="application/zip", headers={"Content-Disposition": "attachment; filename=kktools-skills-package.zip"})
        except (OSError, RuntimeError, ValueError) as exc:
            return web.json_response({"ok": False, "error": f"模板包导出失败：{exc}"}, status=500)

    @PromptServer.instance.routes.get("/kktools/skills/cover")
    async def kktools_get_skill_cover(request):
        skill_id = str(request.rel_url.query.get("id") or "")
        record = _skill_record(skill_id)
        path = _skill_cover_path(skill_id)
        if record and record.get("hasCover") and path.is_file() and SKILLS_LIBRARY_DIR.resolve() in path.resolve().parents:
            return web.FileResponse(path)
        return web.Response(status=404, text="Skill cover not found")

    @PromptServer.instance.routes.patch("/kktools/skills/{skill_id}")
    async def kktools_rename_skill(request):
        try:
            body = await request.json()
            record = _rename_skill(request.match_info.get("skill_id", ""), body.get("name"))
            if "tag" in body:
                record = _tag_skill(record["id"], body.get("tag"))
            return web.json_response({"ok": True, "skill": record})
        except (RuntimeError, json.JSONDecodeError) as exc:
            return web.json_response({"ok": False, "error": str(exc)}, status=400)

    @PromptServer.instance.routes.delete("/kktools/skills/{skill_id}")
    async def kktools_delete_skill(request):
        try:
            record = _delete_skill(request.match_info.get("skill_id", ""))
            return web.json_response({"ok": True, "skill": record})
        except RuntimeError as exc:
            return web.json_response({"ok": False, "error": str(exc)}, status=400)
except (ImportError, AttributeError):
    pass
