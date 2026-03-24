"""
ComfyUI Custom Node: StoryboardScript
分镜头脚本节点 - 将文本优化为分镜头脚本格式 + 分镜输出节点
"""

import re
import json
import ast
import requests

PROVIDER_MODEL_OPTIONS = {
    "deepseek": [
        "deepseek-chat",
        "deepseek-reasoner",
    ],
    "openai": [
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
    ],
    "gemini": [
        "gemini-2.5-pro",
        "gemini-2.5-flash",
        "gemini-2.5-flash-lite",
    ],
    "doubao": [
        "doubao-seed-1-6-251015",
        "doubao-seed-1-6-250615",
        "doubao-seed-1-6-thinking-250715",
        "doubao-seed-1-6-flash-250715",
        "doubao-1-5-thinking-pro",
        "doubao-1-5-thinking-vision-pro",
        "doubao-1-5-pro-32k-250115",
        "doubao-1-5-lite-32k-250115",
    ],
}

DEFAULT_LLM_TEMPERATURE = 0.7

DEFAULT_STORYBOARD_SYSTEM_PROMPT = """你是专业影视导演、分镜师和视觉脚本策划。
请根据用户提供的剧情描述输出适合图像或视频生成的分镜头脚本。

你必须只返回一个 JSON 对象，不要返回 Markdown、代码块、解释或额外文本。
JSON 对象格式如下：
{
  "script_text": "完整的分镜脚本文本",
  "shot_list": [
    {
      "镜号": 1,
      "景别": "全景",
      "运镜方式": "固定",
      "时长": "4秒",
      "画面内容/动作描述": "描述镜头中的主体、动作、构图、环境和关键细节",
      "音频": "环境音或对白，可选"
    }
  ]
}

要求：
1. shot_list 必须是数组，镜号按顺序递增。
2. 每个镜头必须包含 景别、运镜方式、时长、画面内容/动作描述。
3. script_text 必须是可直接阅读的完整分镜脚本文本，并与 shot_list 内容一致。
4. 保持剧情连贯、镜头可执行，避免空泛概述。
5. 除 JSON 外不要输出任何其他内容。"""

class StoryboardScriptBase:
    """分镜节点共享逻辑"""

    @classmethod
    def _get_provider_models(cls, provider):
        return list(PROVIDER_MODEL_OPTIONS.get(provider, PROVIDER_MODEL_OPTIONS["deepseek"]))

    def _generate_storyboard_locally(self, input_text, style, max_shots, include_audio):
        """使用内置规则生成分镜"""
        # 分析输入文本，提取场景元素
        scenes = self._analyze_text(input_text)

        # 生成分镜头
        shots = self._generate_shots(scenes, style, max_shots, include_audio)

        # 格式化为文本
        script_text = self._format_script(shots, style)

        # 转换为列表格式
        shot_list = self._to_list_format(shots)

        print(f"✅ 默认生成完成，共 {len(shots)} 个镜头")

        return (script_text, shot_list)

    def _generate_storyboard_with_api(
        self,
        input_text,
        style,
        max_shots,
        include_audio,
        api_key,
        provider,
        model,
        system_prompt,
    ):
        """使用 LLM API 生成分镜"""
        if not str(api_key).strip():
            raise ValueError("请填写 API Key。")

        resolved_model = self._resolve_model(provider, model)
        resolved_system_prompt = self._resolve_system_prompt(system_prompt)
        user_message = self._build_storyboard_user_message(
            input_text=input_text,
            style=style,
            max_shots=max_shots,
            include_audio=include_audio,
        )
        max_output_tokens = self._estimate_max_output_tokens(max_shots, include_audio)

        response_text = self._call_llm_api(
            system_message=resolved_system_prompt,
            user_message=user_message,
            api_key=api_key,
            provider=provider,
            model=resolved_model,
            max_output_tokens=max_output_tokens,
        )

        storyboard_data = self._parse_storyboard_payload(response_text)
        shots = self._normalize_shot_items(storyboard_data.get("shot_list"), max_shots, include_audio)
        if not shots:
            raise ValueError("API 返回的 shot_list 为空。")

        script_text = str(storyboard_data.get("script_text", "")).strip()
        if not script_text:
            script_text = self._format_script(shots, style)

        shot_list = self._to_list_format(shots)

        print(f"✅ API 生成完成，共 {len(shots)} 个镜头")
        print(f"  Provider: {provider}")
        print(f"  Model: {resolved_model}")

        return (script_text, shot_list)

    def _resolve_model(self, provider, model):
        available_models = self._get_provider_models(provider)
        selected_model = str(model).strip()

        if not selected_model:
            selected_model = available_models[0] if available_models else ""

        if selected_model not in available_models and selected_model:
            return selected_model

        return selected_model

    def _resolve_system_prompt(self, system_prompt):
        custom_system_prompt = str(system_prompt).strip()
        if not custom_system_prompt:
            return DEFAULT_STORYBOARD_SYSTEM_PROMPT

        return (
            f"{DEFAULT_STORYBOARD_SYSTEM_PROMPT}\n\n"
            f"补充创作要求（必须遵守，但不能破坏 JSON 输出结构）：\n"
            f"{custom_system_prompt}"
        )

    def _build_storyboard_user_message(self, input_text, style, max_shots, include_audio):
        """构建分镜生成请求"""
        audio_requirement = "需要为每个镜头补充音频描述。" if include_audio else "不需要音频字段；如无必要可省略或留空。"
        return f"""请将以下内容改写为分镜头脚本，并严格返回 JSON：

原始内容：
{input_text}

生成要求：
- 风格：{style}
- 最大镜头数：{max_shots}
- {audio_requirement}
- 分镜需要剧情连贯、画面明确、便于实际执行。
- script_text 需要是完整可读的分镜脚本。
- shot_list 中每个镜头都要包含：镜号、景别、运镜方式、时长、画面内容/动作描述。"""

    def _estimate_max_output_tokens(self, max_shots, include_audio):
        """估算 LLM 输出 token 上限"""
        base_tokens = 500 + max(1, int(max_shots)) * 180
        if include_audio:
            base_tokens += 120
        return min(max(base_tokens, 800), 4096)

    def _resolve_base_url(self, provider, model):
        if provider == "deepseek":
            return "https://api.deepseek.com/chat/completions"
        if provider == "openai":
            return "https://api.openai.com/v1/chat/completions"
        if provider == "doubao":
            return "https://ark.cn-beijing.volces.com/api/v3/chat/completions"
        if provider == "gemini":
            return f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

        raise ValueError(f"不支持的 provider: {provider}")

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

    def _clean_llm_response(self, text):
        """清理 LLM 返回文本"""
        cleaned = str(text).strip()
        if cleaned.startswith("```"):
            match = re.search(r"```(?:json)?\s*(.*?)\s*```", cleaned, re.DOTALL)
            if match:
                cleaned = match.group(1).strip()
        return cleaned

    def _call_llm_api(
        self,
        system_message,
        user_message,
        api_key,
        provider,
        model,
        max_output_tokens,
    ):
        """调用多厂商 LLM API"""
        url = self._resolve_base_url(provider, model)

        if provider == "gemini":
            headers = {
                "Content-Type": "application/json",
            }
            payload = {
                "system_instruction": {
                    "parts": [
                        {
                            "text": system_message
                        }
                    ]
                },
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
                    "temperature": DEFAULT_LLM_TEMPERATURE,
                    "maxOutputTokens": max_output_tokens,
                }
            }
            response = requests.post(
                url,
                headers=headers,
                params={"key": api_key},
                json=payload,
                timeout=45,
            )
        else:
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}"
            }
            payload = {
                "model": model,
                "messages": [
                    {
                        "role": "system",
                        "content": system_message
                    },
                    {
                        "role": "user",
                        "content": user_message
                    }
                ],
                "max_tokens": max_output_tokens,
                "temperature": DEFAULT_LLM_TEMPERATURE,
                "stream": False
            }
            response = requests.post(url, headers=headers, json=payload, timeout=45)

        response.raise_for_status()
        result = response.json()

        if provider == "gemini":
            content = self._parse_gemini_content(result)
        else:
            content = self._parse_openai_compatible_content(result)

        print(f"StoryboardScript API Call:")
        print(f"  Provider: {provider}")
        print(f"  Model: {model}")
        print(f"  URL: {url}")
        print(f"  Prompt Length: {len(user_message)}")

        return self._clean_llm_response(content)

    def _extract_json_text(self, response_text):
        """从响应文本中提取 JSON 字符串"""
        candidates = []
        cleaned = self._clean_llm_response(response_text)
        if cleaned:
            candidates.append(cleaned)

        fence_match = re.search(r"```(?:json)?\s*(.*?)\s*```", str(response_text), re.DOTALL)
        if fence_match:
            candidates.append(fence_match.group(1).strip())

        text = str(response_text)
        object_start = text.find("{")
        object_end = text.rfind("}")
        if object_start != -1 and object_end > object_start:
            candidates.append(text[object_start:object_end + 1].strip())

        list_start = text.find("[")
        list_end = text.rfind("]")
        if list_start != -1 and list_end > list_start:
            candidates.append(text[list_start:list_end + 1].strip())

        seen = set()
        for candidate in candidates:
            if not candidate or candidate in seen:
                continue
            seen.add(candidate)
            try:
                json.loads(candidate)
                return candidate
            except Exception:
                continue

        raise ValueError("无法从 API 响应中提取有效 JSON。")

    def _parse_storyboard_payload(self, response_text):
        """解析 LLM 返回的分镜 JSON"""
        json_text = self._extract_json_text(response_text)
        data = json.loads(json_text)

        if isinstance(data, list):
            return {
                "script_text": "",
                "shot_list": data,
            }

        if not isinstance(data, dict):
            raise ValueError("API 返回的分镜数据不是对象。")

        return {
            "script_text": data.get("script_text") or data.get("script") or data.get("分镜脚本") or "",
            "shot_list": data.get("shot_list") or data.get("shots") or data.get("镜头列表") or [],
        }

    def _normalize_duration(self, value, default_duration=4):
        """将时长规范为整数秒"""
        if isinstance(value, (int, float)):
            duration = int(round(value))
        else:
            match = re.search(r"(\d+(?:\.\d+)?)", str(value))
            duration = int(round(float(match.group(1)))) if match else default_duration

        return min(max(duration, 1), 30)

    def _normalize_shot_items(self, raw_shots, max_shots, include_audio):
        """将 API 返回的镜头列表规范为内部格式"""
        if not isinstance(raw_shots, list):
            raise ValueError("API 返回的 shot_list 不是列表。")

        normalized_shots = []
        for index, raw_item in enumerate(raw_shots[:max_shots]):
            if isinstance(raw_item, str):
                raw_item = {
                    "画面内容/动作描述": raw_item
                }

            if not isinstance(raw_item, dict):
                continue

            description = str(
                raw_item.get("画面内容/动作描述")
                or raw_item.get("description")
                or raw_item.get("画面")
                or ""
            ).strip()
            if not description:
                continue

            audio = str(raw_item.get("音频") or raw_item.get("audio") or "").strip() if include_audio else ""

            normalized_shots.append({
                "shot_num": index + 1,
                "shot_size": str(raw_item.get("景别") or raw_item.get("shot_size") or "中景").strip() or "中景",
                "camera_move": str(raw_item.get("运镜方式") or raw_item.get("camera_move") or "固定").strip() or "固定",
                "duration": self._normalize_duration(raw_item.get("时长") or raw_item.get("duration") or 4),
                "description": description,
                "audio": audio,
            })

        return normalized_shots
    
    def _analyze_text(self, text):
        """分析文本，提取场景元素"""
        scenes = []
        
        # 基础场景分析
        sentences = re.split(r'[。！？；]', text)
        sentences = [s.strip() for s in sentences if s.strip()]
        
        # 提取关键元素
        elements = {
            "characters": [],
            "actions": [],
            "locations": [],
            "objects": [],
            "emotions": []
        }
        
        # 简单的中文分词和关键词提取
        keywords = {
            "characters": ["小明", "小红", "小华", "老师", "学生", "妈妈", "爸爸", "孩子", "大人", "老人", "女孩", "男孩", "女人", "男人"],
            "locations": ["公园", "学校", "家里", "街道", "商场", "餐厅", "咖啡馆", "办公室", "教室", "操场", "花园", "森林", "海边"],
            "actions": ["走", "跑", "跳", "看", "说", "笑", "哭", "拿", "放", "坐", "站", "躺", "吃", "喝", "玩", "打", "拍"],
            "emotions": ["开心", "快乐", "悲伤", "难过", "愤怒", "生气", "惊讶", "害怕", "紧张", "放松", "兴奋", "平静"]
        }
        
        for sent in sentences:
            scene = {"text": sent, "elements": {}}
            for category, kw_list in keywords.items():
                found = [kw for kw in kw_list if kw in sent]
                if found:
                    scene["elements"][category] = found
            scenes.append(scene)
        
        # 如果没有提取到足够的场景，使用默认分割
        if not scenes:
            scenes = [{"text": text, "elements": {}}]
        
        return scenes
    
    def _generate_shots(self, scenes, style, max_shots, include_audio):
        """生成分镜头列表"""
        shots = []
        
        # 景别选项
        shot_sizes = ["特写", "近景", "中景", "全景", "远景"]
        
        # 运镜方式
        camera_moves = ["固定", "推", "拉", "摇", "移", "跟", "升降"]
        
        # 根据风格调整详细程度
        if style == "简洁":
            detail_factor = 0.3
        elif style == "详细":
            detail_factor = 1.0
        else:  # 专业
            detail_factor = 0.7
        
        # 为每个场景生成镜头
        for i, scene in enumerate(scenes[:max_shots]):
            shot_num = i + 1
            
            # 根据场景内容选择景别
            shot_size = self._select_shot_size(scene, i, len(scenes))
            
            # 选择运镜方式
            camera_move = self._select_camera_move(scene, i)
            
            # 生成时长（基础2-8秒，根据场景复杂度调整）
            duration = self._calculate_duration(scene, style)
            
            # 生成画面描述
            description = self._generate_description(scene, shot_size, camera_move, style)
            
            # 生成音频描述（如果需要）
            audio = ""
            if include_audio:
                audio = self._generate_audio(scene, style)
            
            shot = {
                "shot_num": shot_num,
                "shot_size": shot_size,
                "camera_move": camera_move,
                "duration": duration,
                "description": description,
                "audio": audio if include_audio else ""
            }
            
            shots.append(shot)
        
        return shots
    
    def _select_shot_size(self, scene, index, total_scenes):
        """选择景别"""
        shot_sizes = ["特写", "近景", "中景", "全景", "远景"]
        
        # 根据场景位置选择
        if index == 0:
            # 开场常用远景或全景
            return "全景"
        elif index == total_scenes - 1:
            # 结尾常用远景或全景
            return "远景"
        else:
            # 中间根据场景元素选择
            text = scene.get("text", "")
            if "表情" in text or "眼神" in text or "眼泪" in text:
                return "特写"
            elif "说话" in text or "对话" in text:
                return "近景"
            elif "动作" in text or "运动" in text:
                return "中景"
            else:
                return shot_sizes[index % len(shot_sizes)]
    
    def _select_camera_move(self, scene, index):
        """选择运镜方式"""
        camera_moves = ["固定", "推", "拉", "摇", "移", "跟", "升降"]
        text = scene.get("text", "")
        
        if "靠近" in text or "接近" in text:
            return "推"
        elif "远离" in text or "离开" in text:
            return "拉"
        elif "环绕" in text or "旋转" in text:
            return "摇"
        elif "跟随" in text or "跟着" in text:
            return "跟"
        elif index % 2 == 0:
            return "固定"
        else:
            return camera_moves[index % len(camera_moves)]
    
    def _calculate_duration(self, scene, style):
        """计算镜头时长"""
        text = scene.get("text", "")
        # 根据文本长度估算时长
        word_count = len(text)
        
        if style == "简洁":
            base_duration = 3
        elif style == "详细":
            base_duration = 5
        else:
            base_duration = 4
        
        # 根据文字长度调整
        if word_count < 20:
            duration = base_duration
        elif word_count < 50:
            duration = base_duration + 1
        else:
            duration = base_duration + 2
        
        # 限制范围
        duration = min(max(duration, 2), 8)
        
        return duration
    
    def _generate_description(self, scene, shot_size, camera_move, style):
        """生成画面描述"""
        text = scene.get("text", "")
        
        if style == "简洁":
            description = text[:50] + ("..." if len(text) > 50 else "")
        elif style == "详细":
            elements = scene.get("elements", {})
            characters = elements.get("characters", ["人物"])
            actions = elements.get("actions", ["动作"])
            
            description = f"{shot_size}镜头，{camera_move}运镜。"
            description += f"{'、'.join(characters)}正在进行{'、'.join(actions)}。"
            description += f" {text}"
        else:  # 专业
            description = f"【{shot_size}·{camera_move}】{text}"
        
        return description
    
    def _generate_audio(self, scene, style):
        """生成音频描述"""
        text = scene.get("text", "")
        
        if "说" in text or "叫" in text:
            return "人物对话"
        elif "音乐" in text:
            return "背景音乐"
        elif "声音" in text:
            return "环境音效"
        else:
            return "环境音"
    
    def _format_script(self, shots, style):
        """格式化为脚本文本"""
        lines = []
        
        # 表头
        if style == "简洁":
            lines.append("镜号 | 景别 | 运镜 | 时长 | 画面描述")
            lines.append("-" * 50)
            
            for shot in shots:
                line = f"{shot['shot_num']:02d} | {shot['shot_size']} | {shot['camera_move']} | {shot['duration']}s | {shot['description'][:40]}"
                lines.append(line)
        
        elif style == "详细":
            lines.append("=" * 80)
            lines.append("分镜头脚本")
            lines.append("=" * 80)
            lines.append(f"{'镜号':<4} {'景别':<6} {'运镜方式':<8} {'时长':<6} {'画面内容/动作描述'}")
            lines.append("-" * 80)
            
            for shot in shots:
                line = f"{shot['shot_num']:<4} {shot['shot_size']:<6} {shot['camera_move']:<8} {shot['duration']}秒   {shot['description']}"
                lines.append(line)
            
            if any(shot.get('audio') for shot in shots):
                lines.append("")
                lines.append("-" * 80)
                lines.append("音频说明:")
                for shot in shots:
                    if shot.get('audio'):
                        lines.append(f"  镜{shot['shot_num']}: {shot['audio']}")
        
        else:  # 专业
            lines.append("┌────┬──────┬────────┬──────┬────────────────────────────────────┐")
            lines.append("│镜号│ 景别 │ 运镜方式 │ 时长 │ 画面内容/动作描述                 │")
            lines.append("├────┼──────┼────────┼──────┼────────────────────────────────────┤")
            
            for shot in shots:
                desc = shot['description'][:36] + "..." if len(shot['description']) > 36 else shot['description']
                line = f"│{shot['shot_num']:^3}│{shot['shot_size']:^5}│{shot['camera_move']:^7}│{shot['duration']:^4}s│{desc:<36}│"
                lines.append(line)
            
            lines.append("└────┴──────┴────────┴──────┴────────────────────────────────────┘")
        
        return "\n".join(lines)
    
    def _to_list_format(self, shots):
        """转换为列表格式"""
        shot_list = []
        
        for shot in shots:
            shot_item = {
                "镜号": shot['shot_num'],
                "景别": shot['shot_size'],
                "运镜方式": shot['camera_move'],
                "时长": f"{shot['duration']}秒",
                "画面内容/动作描述": shot['description']
            }
            
            if shot.get('audio'):
                shot_item["音频"] = shot['audio']
            
            shot_list.append(shot_item)
        
        return shot_list


class StoryboardScript(StoryboardScriptBase):
    """默认规则分镜节点"""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "input_text": ("STRING", {
                    "multiline": True,
                    "default": "一个阳光明媚的早晨，小明在公园里散步，突然看到一只可爱的小狗，他开心地跑过去和小狗玩耍。",
                    "placeholder": "输入需要转换为分镜头脚本的描述文本"
                }),
            },
            "optional": {
                "max_shots": ("INT", {
                    "default": 6,
                    "min": 1,
                    "max": 20,
                    "step": 1,
                    "display": "number"
                }),
                "include_audio": ("BOOLEAN", {
                    "default": False,
                    "label_off": "不包含",
                    "label_on": "包含"
                }),
            }
        }

    RETURN_TYPES = ("STRING", "LIST")
    RETURN_NAMES = ("script_text", "shot_list")
    FUNCTION = "generate_storyboard"
    CATEGORY = "kktools/Storyboard"

    def generate_storyboard(self, input_text, style="专业", max_shots=6, include_audio=False):
        """使用默认规则生成分镜"""
        print(f"\n📽️ 默认分镜生成开始")
        print(f"  输入文本: {input_text[:100]}...")
        print(f"  风格: {style}")
        print(f"  最大镜头数: {max_shots}")

        try:
            return self._generate_storyboard_locally(input_text, style, max_shots, include_audio)
        except Exception as e:
            error_msg = f"❌ 生成失败: {str(e)}"
            print(error_msg)
            return (error_msg, [])


class StoryboardScriptLLM(StoryboardScriptBase):
    """LLM 分镜节点"""

    @classmethod
    def INPUT_TYPES(cls):
        default_provider = "deepseek"
        default_models = cls._get_provider_models(default_provider)
        return {
            "required": {
                "input_text": ("STRING", {
                    "multiline": True,
                    "default": "一个阳光明媚的早晨，小明在公园里散步，突然看到一只可爱的小狗，他开心地跑过去和小狗玩耍。",
                    "placeholder": "输入需要转换为分镜头脚本的描述文本"
                }),
                "api_key": ("STRING", {
                    "default": "",
                    "multiline": False,
                    "placeholder": "输入 API Key"
                }),
                "provider": (["deepseek", "openai", "gemini", "doubao"], {
                    "default": default_provider
                }),
                "model": (default_models, {
                    "default": default_models[0]
                }),
            },
            "optional": {
                "max_shots": ("INT", {
                    "default": 6,
                    "min": 1,
                    "max": 20,
                    "step": 1,
                    "display": "number"
                }),
                "include_audio": ("BOOLEAN", {
                    "default": False,
                    "label_off": "不包含",
                    "label_on": "包含"
                }),
                "system_prompt": ("STRING", {
                    "default": "",
                    "multiline": True,
                    "placeholder": "留空使用内置分镜 System Prompt"
                }),
            }
        }

    RETURN_TYPES = ("STRING", "LIST")
    RETURN_NAMES = ("script_text", "shot_list")
    FUNCTION = "generate_storyboard_llm"
    CATEGORY = "kktools/Storyboard"

    def generate_storyboard_llm(
        self,
        input_text,
        api_key,
        provider,
        model,
        max_shots=6,
        include_audio=False,
        system_prompt="",
    ):
        """使用 LLM 生成分镜"""
        style = "专业"
        print(f"\n🤖 LLM 分镜生成开始")
        print(f"  输入文本: {input_text[:100]}...")
        print(f"  风格: {style}")
        print(f"  最大镜头数: {max_shots}")
        print(f"  Provider: {provider}")
        print(f"  Model: {model}")

        try:
            return self._generate_storyboard_with_api(
                input_text=input_text,
                style=style,
                max_shots=max_shots,
                include_audio=include_audio,
                api_key=api_key,
                provider=provider,
                model=model,
                system_prompt=system_prompt,
            )
        except Exception as e:
            error_msg = f"❌ LLM 生成失败: {str(e)}"
            print(error_msg)
            return (error_msg, [])


class StoryboardShotOutput:
    """分镜输出节点 - 从镜头列表依次输出每一条分镜"""
    
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "shot_list": ("LIST", {
                    "default": [],
                    "description": "从分镜头脚本节点输出的镜头列表"
                }),
                "shot_index": ("INT", {
                    "default": 0,
                    "min": 0,
                    "max": 999,
                    "step": 1,
                    "display": "number",
                    "description": "要输出的镜头索引（从0开始）"
                }),
            },
            "optional": {
                "output_format": (["完整", "简洁", "纯文本"], {
                    "default": "完整",
                    "description": "输出格式"
                }),
                "auto_next": ("BOOLEAN", {
                    "default": False,
                    "label_off": "手动",
                    "label_on": "自动",
                    "description": "自动输出下一个镜头"
                }),
            }
        }
    
    RETURN_TYPES = ("STRING", "INT", "INT")
    RETURN_NAMES = ("shot_string", "current_index", "total_count")
    FUNCTION = "output_shot"
    CATEGORY = "kktools/Storyboard"
    
    def output_shot(self, shot_list, shot_index, output_format="完整", auto_next=False):
        """
        从镜头列表输出指定的分镜
        
        Args:
            shot_list: 镜头列表（JSON格式）
            shot_index: 要输出的镜头索引
            output_format: 输出格式（完整/简洁/纯文本）
            auto_next: 是否自动输出下一个
            
        Returns:
            shot_string: 格式化的分镜字符串
            current_index: 当前输出的索引
            total_count: 总镜头数
        """
        print(f"\n🎬 分镜输出开始")
        print(f"  镜头索引: {shot_index}")
        print(f"  输出格式: {output_format}")
        
        try:
            # 解析镜头列表
            shots = self._parse_shot_list(shot_list)
            
            if not shots:
                print(f"⚠️ 镜头列表为空")
                return ("镜头列表为空", 0, 0)
            
            total_count = len(shots)
            
            # 确保索引有效
            if shot_index < 0:
                shot_index = 0
            elif shot_index >= total_count:
                shot_index = total_count - 1
            
            # 获取当前镜头
            current_shot = shots[shot_index]
            
            # 格式化输出
            shot_string = self._format_shot(current_shot, output_format, shot_index + 1, total_count)
            
            # 确定下一个索引（如果自动下一个）
            next_index = shot_index
            if auto_next and shot_index < total_count - 1:
                next_index = shot_index + 1
            
            print(f"✅ 输出镜头 {shot_index + 1}/{total_count}")
            print(f"  内容: {shot_string[:100]}...")
            
            return (shot_string, next_index if auto_next else shot_index, total_count)
            
        except Exception as e:
            error_msg = f"❌ 输出失败: {str(e)}"
            print(error_msg)
            import traceback
            traceback.print_exc()
            return (error_msg, 0, 0)
    
    def _parse_shot_list(self, shot_list):
        """解析镜头列表，支持多种格式"""
        shots = []
        
        # 如果已经是列表
        if isinstance(shot_list, list):
            shots = shot_list
        
        # 如果是字符串，尝试解析JSON
        elif isinstance(shot_list, str):
            try:
                # 尝试JSON解析
                shots = json.loads(shot_list)
            except:
                try:
                    # 尝试Python字面量解析
                    shots = ast.literal_eval(shot_list)
                except:
                    # 如果是多行字符串，尝试逐行解析
                    lines = shot_list.strip().split('\n')
                    for line in lines:
                        if line.strip():
                            try:
                                shot = json.loads(line)
                                shots.append(shot)
                            except:
                                pass
        
        # 如果是从StoryboardScript节点输出的LIST类型
        elif hasattr(shot_list, '__iter__') and not isinstance(shot_list, str):
            shots = list(shot_list)
        
        return shots
    
    def _format_shot(self, shot, output_format, current_num, total_count):
        """格式化单个分镜"""
        
        # 获取镜头数据
        shot_num = shot.get("镜号", current_num)
        shot_size = shot.get("景别", shot.get("shot_size", "中景"))
        camera_move = shot.get("运镜方式", shot.get("camera_move", "固定"))
        duration = shot.get("时长", shot.get("duration", "4秒"))
        description = shot.get("画面内容/动作描述", shot.get("description", ""))
        audio = shot.get("音频", shot.get("audio", ""))
        
        if output_format == "简洁":
            # 简洁格式
            result = f"景别: {shot_size}； 运镜: {camera_move}； 时长: {duration}； 画面描述: {description}"
            if audio:
                result += f"； 音频: {audio}"
            
        elif output_format == "纯文本":
            # 纯文本格式，只返回画面描述
            result = description
            
        else:  # 完整格式
            # 完整格式
            result = f"""
╔══════════════════════════════════════════════════════════════╗
║ 镜头 {current_num}/{total_count}                                        
╠══════════════════════════════════════════════════════════════╣
║ 景别: {shot_size}                                                    
║ 运镜: {camera_move}                                                  
║ 时长: {duration}                                                     
║──────────────────────────────────────────────────────────────║
║ 画面描述:                                                          
║ {description}                                                      
"""
            if audio:
                result += f"""
║──────────────────────────────────────────────────────────────║
║ 音频: {audio}                                                        
"""
            result += """
╚══════════════════════════════════════════════════════════════╝"""
        
        return result.strip()


# 节点注册
NODE_CLASS_MAPPINGS = {
    "StoryboardScript": StoryboardScript,
    "StoryboardScriptLLM": StoryboardScriptLLM,
    "StoryboardShotOutput": StoryboardShotOutput,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "StoryboardScript": "📋 分镜头脚本生成(默认)",
    "StoryboardScriptLLM": "🤖 分镜头脚本生成(LLM)",
    "StoryboardShotOutput": "🎬 分镜输出(单条)",
}

__all__ = ['StoryboardScript', 'StoryboardScriptLLM', 'StoryboardShotOutput']

print("✅ 分镜头脚本节点已加载")
print("   📋 分镜头脚本生成(默认): 使用本地规则生成分镜")
print("   🤖 分镜头脚本生成(LLM): 使用大模型生成分镜")
print("   🎬 分镜输出(单条): 从镜头列表输出指定分镜")
