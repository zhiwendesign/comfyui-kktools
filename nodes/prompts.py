"""
ComfyUI Custom Node: Prompt
提示词节点 - 批量提示词加载和AI提示词优化
"""

import requests
import json
import os
import glob
import re

PROVIDER_MODEL_OPTIONS = {
    "deepseek": [
        "deepseek-chat",
        "deepseek-reasoner",
        "custom",
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
        "custom",
    ],
    "gemini": [
        "gemini-2.5-pro",
        "gemini-2.5-flash",
        "gemini-2.5-flash-lite",
        "custom",
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
        "custom",
    ],
}


class BatchPrompt:
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
    CATEGORY = "kktools/Prompt"
    
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
                    "placeholder": "输入基础提示词"
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
                    "default": "你是一个专业的AI绘画提示词优化专家。请根据用户要求优化提示词，直接输出优化后的提示词，不要添加任何解释或标记。",
                    "multiline": True,
                    "placeholder": "输入系统角色设定"
                }),
            },
            "optional": {
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
    RETURN_NAMES = ("optimized_prompt", "original_prompt", "optimization_info")
    FUNCTION = "optimize_prompt"
    CATEGORY = "kktools/Prompt"
    
    def optimize_prompt(
        self,
        base_prompt,
        api_key,
        provider,
        model,
        custom_model,
        base_url,
        system_message,
        max_length=500,
        temperature=0.7,
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
            (优化后的提示词, 原始提示词, 优化信息)
        """
        try:
            if not base_prompt.strip():
                return ("", base_prompt, "错误: 基础提示词为空")
            
            if not api_key.strip():
                return (base_prompt, base_prompt, "警告: 未提供API密钥，返回原始提示词")
            
            # 构建用户消息
            user_message = self._build_user_message(base_prompt, max_length)
            
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
                return (optimized_prompt, base_prompt, info)
            else:
                return (base_prompt, base_prompt, "API调用失败，返回原始提示词")
                
        except Exception as e:
            error_msg = f"优化提示词时出错: {str(e)}"
            print(f"kkLLM Error: {error_msg}")
            return (base_prompt, base_prompt, f"错误: {error_msg}")
    
    def _build_user_message(self, base_prompt, max_length):
        """构建用户消息"""
        return f"请优化以下AI绘画提示词，使其更加详细、具有表现力，包含适当的技术细节和画质描述，保持核心内容不变但提升整体质量。输出长度不超过{max_length}字符：\n\n{base_prompt}"
    
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
                        "temperature": temperature,
                        "maxOutputTokens": max_length,
                    }
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
                payload = {
                    "model": resolved_model,
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
            optimized = ' '.join(base_prompt.split())
            
            # 添加通用质量提升关键词
            optimized += ", masterpiece, best quality, highly detailed, high resolution, 8K"
            
            # 移除可能的重复逗号
            optimized = re.sub(r',+', ',', optimized)
            optimized = optimized.strip(',').strip()
            
            print(f"Local Optimization Applied: {optimized[:100]}...")
            return optimized[:500]  # 限制长度
            
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
    "BatchPrompt": BatchPrompt,
    "kkLLM": kkLLM,
}

# 节点在菜单中显示的名称
NODE_DISPLAY_NAME_MAPPINGS = {
    "BatchPrompt": "Batch Prompt (批量提示词)",
    "kkLLM": "kkLLM (多厂商大模型提示词优化)",
}

__all__ = ['NODE_CLASS_MAPPINGS', 'NODE_DISPLAY_NAME_MAPPINGS']
