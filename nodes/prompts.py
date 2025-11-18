"""
ComfyUI Custom Node: Prompt
提示词节点 - 批量提示词加载和AI提示词优化
"""

import requests
import json
import os
import glob

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


class AIPromptOptimizerNode:
    """提示词节点（AI优化） - 通过DeepSeek API优化提示词"""
    
    @classmethod
    def INPUT_TYPES(cls):
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
                    "placeholder": "输入DeepSeek API Key"
                }),
                "optimization_level": (["light", "medium", "heavy"], {
                    "default": "medium"
                }),
                "target_style": (["realistic", "anime", "artistic", "cinematic", "photographic", "painting"], {
                    "default": "realistic"
                }),
                "include_technical": ("BOOLEAN", {
                    "default": True
                }),
            },
            "optional": {
                "reference_prompt": ("STRING", {
                    "default": "",
                    "multiline": True,
                    "placeholder": "参考提示词（可选）"
                }),
                "max_length": ("INT", {
                    "default": 500,
                    "min": 50,
                    "max": 2000,
                    "step": 50
                }),
            }
        }
    
    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("optimized_prompt", "original_prompt", "optimization_info")
    FUNCTION = "optimize_prompt"
    CATEGORY = "kktools/Prompt"
    
    def optimize_prompt(self, base_prompt, api_key, optimization_level, target_style, include_technical, reference_prompt="", max_length=500):
        """
        通过DeepSeek API优化提示词
        
        Args:
            base_prompt: 基础提示词
            api_key: DeepSeek API密钥
            optimization_level: 优化级别
            target_style: 目标风格
            include_technical: 是否包含技术细节
            reference_prompt: 参考提示词（可选）
            max_length: 最大长度
            
        Returns:
            (优化后的提示词, 原始提示词, 优化信息)
        """
        try:
            if not base_prompt.strip():
                return ("", base_prompt, "错误: 基础提示词为空")
            
            if not api_key.strip():
                return (base_prompt, base_prompt, "警告: 未提供API密钥，返回原始提示词")
            
            # 构建优化指令
            optimization_instructions = self._build_optimization_instructions(
                optimization_level, target_style, include_technical, reference_prompt, max_length
            )
            
            # 调用DeepSeek API
            optimized_prompt = self._call_deepseek_api(
                base_prompt, optimization_instructions, api_key, max_length
            )
            
            if optimized_prompt:
                info = f"优化完成 - 级别: {optimization_level}, 风格: {target_style}"
                return (optimized_prompt, base_prompt, info)
            else:
                return (base_prompt, base_prompt, "API调用失败，返回原始提示词")
                
        except Exception as e:
            error_msg = f"优化提示词时出错: {str(e)}"
            print(f"AIPromptOptimizer Error: {error_msg}")
            return (base_prompt, base_prompt, f"错误: {error_msg}")
    
    def _build_optimization_instructions(self, optimization_level, target_style, include_technical, reference_prompt, max_length):
        """构建优化指令"""
        instructions = []
        
        # 优化级别
        if optimization_level == "light":
            instructions.append("对以下AI绘画提示词进行轻度优化，保持原意但提升表达流畅度")
        elif optimization_level == "medium":
            instructions.append("对以下AI绘画提示词进行中等程度优化，改善结构和关键词组织")
        else:  # heavy
            instructions.append("对以下AI绘画提示词进行全面优化，彻底重构并增强表现力")
        
        # 目标风格
        style_mapping = {
            "realistic": "写实风格",
            "anime": "动漫风格", 
            "artistic": "艺术风格",
            "cinematic": "电影风格",
            "photographic": "摄影风格",
            "painting": "绘画风格"
        }
        instructions.append(f"目标风格: {style_mapping.get(target_style, target_style)}")
        
        # 技术细节
        if include_technical:
            instructions.append("包含适当的技术细节和画质描述")
        
        # 参考提示词
        if reference_prompt.strip():
            instructions.append(f"参考以下提示词风格: {reference_prompt}")
        
        # 长度限制
        instructions.append(f"输出长度不超过{max_length}字符")
        
        instructions.append("直接输出优化后的提示词，不要添加任何解释或标记")
        
        return "。".join(instructions)
    
    def _call_deepseek_api(self, base_prompt, instructions, api_key, max_length):
        """调用DeepSeek API"""
        try:
            url = "https://api.deepseek.com/chat/completions"
            
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}"
            }
            
            system_message = "你是一个专业的AI绘画提示词优化专家。请根据用户要求优化提示词。"
            
            payload = {
                "model": "deepseek-chat",
                "messages": [
                    {
                        "role": "system",
                        "content": system_message
                    },
                    {
                        "role": "user", 
                        "content": f"{instructions}\n\n需要优化的提示词:\n{base_prompt}"
                    }
                ],
                "max_tokens": max_length,
                "temperature": 0.7,
                "stream": False
            }
            
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            response.raise_for_status()
            
            result = response.json()
            optimized_prompt = result["choices"][0]["message"]["content"].strip()
            
            # 清理可能的标记和解释
            optimized_prompt = self._clean_prompt(optimized_prompt)
            
            # 打印调试信息
            print(f"AIPromptOptimizer API Call:")
            print(f"  Original Length: {len(base_prompt)}")
            print(f"  Optimized Length: {len(optimized_prompt)}")
            print(f"  Original: {base_prompt[:100]}...")
            print(f"  Optimized: {optimized_prompt[:100]}...")
            
            return optimized_prompt
            
        except requests.exceptions.RequestException as e:
            print(f"DeepSeek API请求错误: {e}")
            return None
        except (KeyError, IndexError) as e:
            print(f"DeepSeek API响应解析错误: {e}")
            return None
        except Exception as e:
            print(f"DeepSeek API调用未知错误: {e}")
            return None
    
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
        
        return prompt


# ComfyUI 节点注册
NODE_CLASS_MAPPINGS = {
    "BatchPrompt": BatchPrompt,
    "AIPromptOptimizerNode": AIPromptOptimizerNode,
}

# 节点在菜单中显示的名称
NODE_DISPLAY_NAME_MAPPINGS = {
    "BatchPrompt": "Batch Prompt (批量提示词)",
    "AIPromptOptimizerNode": "AI Prompt Optimizer (AI提示词优化)",
}

__all__ = ['BatchPrompt', 'AIPromptOptimizerNode']