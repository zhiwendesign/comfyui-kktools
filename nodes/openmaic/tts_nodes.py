"""
ComfyUI OpenMAIC 节点 - TTS 语音合成节点

使用多种 TTS 提供商将文本转换为语音。

支持的提供商：
- OpenAI TTS
- Azure TTS
- GLM TTS
- Qwen TTS
- Claude TTS
- 豆包 TTS
- ElevenLabs TTS
- IndexTTS 本地
- VoxCPM 本地
"""

import os
import json
import tempfile
import subprocess
import base64
from typing import Tuple, Dict, Any, Optional, List

NODE_CLASS_MAPPINGS = {}
NODE_DISPLAY_NAME_MAPPINGS = {}

# TTS 提供商配置
TTS_PROVIDERS = {
    'openai-tts': {
        'name': 'OpenAI TTS',
        'requires_api_key': True,
        'default_base_url': 'https://api.openai.com/v1',
        'voices': ['alloy', 'echo', 'fable', 'nova', 'onyx', 'sage', 'shimmer', 'verse'],
    },
    'azure-tts': {
        'name': 'Azure TTS',
        'requires_api_key': True,
        'default_base_url': 'https://{region}.tts.speech.microsoft.com',
        'voices': ['zh-CN-XiaoxiaoNeural', 'zh-CN-YunxiNeural', 'zh-CN-XiaoyiNeural', 'zh-CN-YunjianNeural'],
    },
    'glm-tts': {
        'name': 'GLM TTS',
        'requires_api_key': True,
        'default_base_url': 'https://open.bigmodel.cn/api/paas/v4',
        'voices': ['tongtong', 'chuichui', 'xiaochen', 'jam', 'kazi', 'douji', 'luodo'],
    },
    'qwen-tts': {
        'name': 'Qwen TTS',
        'requires_api_key': True,
        'default_base_url': 'https://dashscope.aliyuncs.com/api/v1',
        'voices': ['Cherry', 'Serena', 'Ethan', 'Chelsie', 'Momo', 'Vivian', 'Moon'],
    },
    'claude-tts': {
        'name': 'Claude TTS',
        'requires_api_key': True,
        'default_base_url': 'https://api.anthropic.com',
        'voices': ['female-yujie', 'male-qn-jingying', 'female-shaonv', 'Chinese (Mandarin)_Gentleman'],
    },
    'doubao-tts': {
        'name': '豆包 TTS',
        'requires_api_key': True,
        'default_base_url': 'https://openspeech.bytedance.com/api/v3/tts',
        'voices': ['zh_female_vv_uranus_bigtts', 'zh_female_xiaohe_uranus_bigtts', 'zh_male_m191_uranus_bigtts'],
    },
    'elevenlabs-tts': {
        'name': 'ElevenLabs TTS',
        'requires_api_key': True,
        'default_base_url': 'https://api.elevenlabs.io/v1',
        'voices': ['alloy', 'echo', 'fable', 'nova', 'onyx', 'sage', 'shimmer'],
    },
    'indextts-gradio': {
        'name': 'IndexTTS 本地',
        'requires_api_key': False,
        'default_base_url': 'http://127.0.0.1:9876',
        'voices': ['default'],
    },
    'voxcpm-tts': {
        'name': 'VoxCPM 本地',
        'requires_api_key': False,
        'default_base_url': 'http://127.0.0.1:8000',
        'voices': ['default'],
    },
}

PROVIDER_OPTIONS = list(TTS_PROVIDERS.keys())


def register_node(cls):
    NODE_CLASS_MAPPINGS[cls.__name__] = cls
    NODE_DISPLAY_NAME_MAPPINGS[cls.__name__] = cls.DISPLAY_NAME
    return cls


@register_node
class OpenMAIC_TTS设置:
    """
    TTS 设置 - 配置语音合成参数

    类别：OpenMAIC/音频

    输入：
    - 提供商：TTS 提供商选择
    - 音色：语音音色选择
    - 语速：语音速度 (0.5-2.0)
    - API密钥：提供商 API 密钥（可选）
    - 自定义API地址：自定义 API 地址（可选）

    输出：
    - TTS配置（字典）：TTS 配置
    """
    CATEGORY = "OpenMAIC/音频"
    DISPLAY_NAME = "🎙️ TTS 设置"
    RETURN_TYPES = ("DICT",)
    RETURN_NAMES = ("TTS配置",)
    FUNCTION = "process"

    @classmethod
    def INPUT_TYPES(cls) -> Dict[str, Any]:
        voices_by_provider = {}
        for provider_id, provider in TTS_PROVIDERS.items():
            voices_by_provider[provider_id] = provider['voices']

        return {
            "required": {
                "提供商": (PROVIDER_OPTIONS, {
                    "default": "qwen-tts",
                    "tooltip": "选择 TTS 提供商"
                }),
                "音色": ("STRING", {
                    "default": "",
                    "tooltip": "选择语音音色"
                }),
            },
            "optional": {
                "语速": ("FLOAT", {
                    "default": 1.0,
                    "min": 0.5,
                    "max": 2.0,
                    "step": 0.1,
                    "tooltip": "语音速度 (0.5-2.0)"
                }),
                "API密钥": ("STRING", {
                    "default": "",
                    "tooltip": "TTS 提供商 API 密钥"
                }),
                "自定义API地址": ("STRING", {
                    "default": "",
                    "tooltip": "自定义 API 地址（可选）"
                }),
            },
        }

    def process(
        self,
        提供商: str,
        音色: str,
        语速: float = 1.0,
        API密钥: str = "",
        自定义API地址: str = "",
    ) -> Tuple[Dict[str, Any]]:
        # 获取默认音色
        if not 音色:
            音色 = TTS_PROVIDERS.get(提供商, {}).get('voices', ['default'])[0]

        config = {
            'provider_id': 提供商,
            'voice': 音色,
            'speed': 语速,
            'format': 'mp3',
        }

        if API密钥:
            config['api_key'] = API密钥

        if 自定义API地址:
            config['base_url'] = 自定义API地址

        return (config,)


@register_node
class OpenMAIC_文本转语音:
    """
    文本转语音 - 将文本列表转换为语音音频

    类别：OpenMAIC/音频

    输入：
    - 语音片段：语音片段列表 [{text, start_ms, end_ms}]
    - TTS配置：TTS 配置

    输出：
    - 音频文件：生成的音频文件路径
    - 音频片段：带时间轴的音频片段列表
    """
    CATEGORY = "OpenMAIC/音频"
    DISPLAY_NAME = "🔊 文本转语音"
    RETURN_TYPES = ("STRING", "LIST")
    RETURN_NAMES = ("音频文件", "音频片段")
    FUNCTION = "process"

    @classmethod
    def INPUT_TYPES(cls) -> Dict[str, Any]:
        return {
            "required": {
                "语音片段": ("LIST", {
                    "tooltip": "语音片段列表：[{text, start_ms, end_ms}]"
                }),
                "TTS配置": ("DICT", {
                    "tooltip": "TTS 配置"
                }),
            },
        }

    def process(
        self,
        语音片段: List[Dict[str, Any]],
        TTS配置: Dict[str, Any],
    ) -> Tuple[str, List[Dict[str, Any]]]:
        if not 语音片段:
            raise ValueError("语音片段列表不能为空")

        provider = TTS配置.get('provider_id', 'qwen-tts')
        voice = TTS配置.get('voice', 'default')
        speed = TTS配置.get('speed', 1.0)
        api_key = TTS配置.get('api_key', '')
        base_url = TTS配置.get('base_url', '')

        temp_dir = tempfile.mkdtemp(prefix="openmaic_tts_")
        audio_files = []

        # 合并所有文本用于估算
        combined_text = " ".join([seg.get('text', '') for seg in 语音片段])

        # 调用 TTS API
        try:
            audio_data = self._call_tts_api(
                provider=provider,
                text=combined_text,
                voice=voice,
                speed=speed,
                api_key=api_key,
                base_url=base_url,
            )
        except Exception as e:
            raise Exception(f"TTS 生成失败: {str(e)}")

        # 保存音频文件
        temp_audio = os.path.join(temp_dir, "combined_audio.mp3")
        with open(temp_audio, 'wb') as f:
            f.write(audio_data)

        # 获取总时长
        duration = self._get_audio_duration(temp_audio)

        # 根据比例计算每个片段的时间轴
        total_chars = len(combined_text)
        audio_segments = []
        current_time = 0.0

        for seg in 语音片段:
            text = seg.get('text', '')
            text_len = len(text)
            if total_chars > 0 and text_len > 0:
                seg_duration = (text_len / total_chars) * duration
            else:
                seg_duration = 3.0  # 默认 3 秒

            audio_segments.append({
                'text': text,
                'start': current_time,
                'end': current_time + seg_duration,
                'duration': seg_duration,
            })
            current_time += seg_duration

        return (temp_audio, audio_segments)

    def _call_tts_api(
        self,
        provider: str,
        text: str,
        voice: str,
        speed: float,
        api_key: str,
        base_url: str,
    ) -> bytes:
        """调用 TTS API"""
        if provider == 'qwen-tts':
            return self._call_qwen_tts(text, voice, speed, api_key, base_url)
        elif provider == 'openai-tts':
            return self._call_openai_tts(text, voice, speed, api_key, base_url)
        elif provider == 'glm-tts':
            return self._call_glm_tts(text, voice, speed, api_key, base_url)
        elif provider == 'claude-tts':
            return self._call_claude_tts(text, voice, speed, api_key, base_url)
        elif provider == 'doubao-tts':
            return self._call_doubao_tts(text, voice, speed, api_key, base_url)
        elif provider == 'elevenlabs-tts':
            return self._call_elevenlabs_tts(text, voice, speed, api_key, base_url)
        elif provider == 'indextts-gradio':
            return self._call_indextts(text, voice, speed, base_url)
        elif provider == 'voxcpm-tts':
            return self._call_voxcpm(text, voice, speed, base_url)
        else:
            raise ValueError(f"不支持的 TTS 提供商: {provider}")

    def _call_qwen_tts(
        self,
        text: str,
        voice: str,
        speed: float,
        api_key: str,
        base_url: str,
    ) -> bytes:
        """调用 Qwen TTS API"""
        url = f"{base_url or 'https://dashscope.aliyuncs.com/api/v1'}/services/tts/text-to-speech"

        headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json',
        }

        payload = {
            'model': 'qwen3-tts-flash',
            'input': {'text': text},
            'parameters': {
                'voice': voice,
                'speech_rate': str(speed),
                'response_format': 'mp3',
            },
        }

        import urllib.request
        data = json.dumps(payload).encode('utf-8')
        request = urllib.request.Request(url, data=data, headers=headers, method='POST')

        with urllib.request.urlopen(request, timeout=60) as response:
            result = json.loads(response.read().decode('utf-8'))
            audio_b64 = result.get('output', {}).get('audio', '')
            if not audio_b64:
                raise ValueError("Qwen TTS 返回无效音频数据")
            return base64.b64decode(audio_b64)

    def _call_openai_tts(
        self,
        text: str,
        voice: str,
        speed: float,
        api_key: str,
        base_url: str,
    ) -> bytes:
        """调用 OpenAI TTS API"""
        url = f"{base_url or 'https://api.openai.com/v1'}/audio/speech"

        headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json',
        }

        payload = {
            'model': 'gpt-4o-mini-tts',
            'input': text,
            'voice': voice,
            'speed': speed,
            'response_format': 'mp3',
        }

        import urllib.request
        data = json.dumps(payload).encode('utf-8')
        request = urllib.request.Request(url, data=data, headers=headers, method='POST')

        with urllib.request.urlopen(request, timeout=60) as response:
            return response.read()

    def _call_glm_tts(
        self,
        text: str,
        voice: str,
        speed: float,
        api_key: str,
        base_url: str,
    ) -> bytes:
        """调用 GLM TTS API"""
        url = f"{base_url or 'https://open.bigmodel.cn/api/paas/v4'}/audio/speech"

        headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json',
        }

        payload = {
            'model': 'glm-tts',
            'input': text,
            'voice': voice,
            'speed': speed,
        }

        import urllib.request
        data = json.dumps(payload).encode('utf-8')
        request = urllib.request.Request(url, data=data, headers=headers, method='POST')

        with urllib.request.urlopen(request, timeout=60) as response:
            return response.read()

    def _call_claude_tts(
        self,
        text: str,
        voice: str,
        speed: float,
        api_key: str,
        base_url: str,
    ) -> bytes:
        """调用 Claude TTS API"""
        url = f"{base_url or 'https://api.anthropic.com'}/v1/t2a_v2"

        headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json',
        }

        payload = {
            'model': 'speech-2.8-hd',
            'text': text,
            'voice_setting': {
                'voice_id': voice,
                'speed': speed,
            },
            'output_format': {
                'bitrate': 128000,
                'sample_rate': 32000,
                'format': 'mp3',
            },
        }

        import urllib.request
        data = json.dumps(payload).encode('utf-8')
        request = urllib.request.Request(url, data=data, headers=headers, method='POST')

        with urllib.request.urlopen(request, timeout=60) as response:
            result = json.loads(response.read().decode('utf-8'))
            audio_b64 = result.get('data', {}).get('audio_file', '')
            if not audio_b64:
                raise ValueError("Claude TTS 返回无效音频数据")
            return base64.b64decode(audio_b64)

    def _call_doubao_tts(
        self,
        text: str,
        voice: str,
        speed: float,
        api_key: str,
        base_url: str,
    ) -> bytes:
        """调用豆包 TTS API"""
        url = f"{base_url or 'https://openspeech.bytedance.com/api/v3/tts'}"

        headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json',
        }

        payload = {
            'appid': api_key.split(':')[0] if ':' in api_key else '',
            'voice': voice,
            'speed': speed,
            'format': 'mp3',
            'text': text,
        }

        import urllib.request
        data = json.dumps(payload).encode('utf-8')
        request = urllib.request.Request(url, data=data, headers=headers, method='POST')

        with urllib.request.urlopen(request, timeout=60) as response:
            result = json.loads(response.read().decode('utf-8'))
            audio_b64 = result.get('audio')
            if not audio_b64:
                raise ValueError("豆包 TTS 返回无效音频数据")
            return base64.b64decode(audio_b64)

    def _call_elevenlabs_tts(
        self,
        text: str,
        voice: str,
        speed: float,
        api_key: str,
        base_url: str,
    ) -> bytes:
        """调用 ElevenLabs TTS API"""
        url = f"{base_url or 'https://api.elevenlabs.io/v1'}/text-to-speech/{voice}"

        headers = {
            'xi-api-key': api_key,
            'Content-Type': 'application/json',
            'Accept': 'audio/mpeg',
        }

        payload = {
            'text': text,
            'model_id': 'eleven_multilingual_v2',
            'voice_settings': {
                'stability': 0.5,
                'similarity_boost': 0.75,
                'style': 0.0,
                'use_speaker_boost': True,
            },
        }

        import urllib.request
        data = json.dumps(payload).encode('utf-8')
        request = urllib.request.Request(url, data=data, headers=headers, method='POST')

        with urllib.request.urlopen(request, timeout=60) as response:
            return response.read()

    def _call_indextts(
        self,
        text: str,
        voice: str,
        speed: float,
        base_url: str,
    ) -> bytes:
        """调用 IndexTTS Gradio API"""
        url = f"{base_url or 'http://127.0.0.1:9876'}/api/predict"

        payload = {
            'data': [text, 1.0 / speed, "male", "Off"],
        }

        import urllib.request
        data = json.dumps(payload).encode('utf-8')
        request = urllib.request.Request(
            url,
            data=data,
            headers={'Content-Type': 'application/json'},
            method='POST',
        )

        with urllib.request.urlopen(request, timeout=120) as response:
            result = json.loads(response.read().decode('utf-8'))
            audio_b64 = result.get('data', [''])[0]
            if not audio_b64 or not audio_b64.startswith('data:audio'):
                raise ValueError("IndexTTS 返回无效音频数据")
            # 提取 base64 音频数据
            audio_str = audio_b64.split(',')[1] if ',' in audio_b64 else audio_b64
            return base64.b64decode(audio_str)

    def _call_voxcpm(
        self,
        text: str,
        voice: str,
        speed: float,
        base_url: str,
    ) -> bytes:
        """调用 VoxCPM 本地 API"""
        url = f"{base_url or 'http://127.0.0.1:8000'}/tts"

        payload = {
            'text': text,
            'speed': speed,
        }

        import urllib.request
        data = json.dumps(payload).encode('utf-8')
        request = urllib.request.Request(
            url,
            data=data,
            headers={'Content-Type': 'application/json'},
            method='POST',
        )

        with urllib.request.urlopen(request, timeout=60) as response:
            return response.read()

    def _get_audio_duration(self, file_path: str) -> float:
        """获取音频时长"""
        cmd = [
            'ffprobe',
            '-v', 'error',
            '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1',
            file_path,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        try:
            return float(result.stdout.strip())
        except Exception:
            return 3.0


# 导出节点映射
NODE_CLASS_MAPPINGS = {
    "OpenMAIC_TTS设置": OpenMAIC_TTS设置,
    "OpenMAIC_文本转语音": OpenMAIC_文本转语音,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "OpenMAIC_TTS设置": "🎙️ TTS 设置",
    "OpenMAIC_文本转语音": "🔊 文本转语音",
}
