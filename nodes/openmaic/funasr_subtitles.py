"""
ComfyUI OpenMAIC 节点 - FunASR 字幕对齐节点

使用 FunASR（ Fun Automated Speech Recognition）进行语音识别，
生成精确的字幕时间轴。

功能：
- 本地 FunASR 推理
- 自动与语音事件对齐
- 对齐失败时回退到估算时间
"""

import os
import json
import subprocess
import tempfile
import shutil
from typing import Tuple, Dict, Any, Optional, List
import re

NODE_CLASS_MAPPINGS = {}
NODE_DISPLAY_NAME_MAPPINGS = {}


def register_node(cls):
    NODE_CLASS_MAPPINGS[cls.__name__] = cls
    NODE_DISPLAY_NAME_MAPPINGS[cls.__name__] = cls.DISPLAY_NAME
    return cls


@register_node
class OpenMAIC_FunASR字幕对齐:
    """
    FunASR 字幕对齐 - 使用语音识别精确对齐字幕时间点

    使用 FunASR 将音频转录为带时间戳的文字，
    然后与原始讲稿/动作匹配，生成精确的字幕时间轴。

    类别：OpenMAIC/音频

    输入：
    - 音频路径：音频文件路径
    - 语音事件：包含文字和时间的语音事件列表
    - 设置：FunASR 配置（可选）

    输出：
    - 字幕时间点：字幕时间轴列表
    - 对齐信息：对齐统计和模式信息
    """

    CATEGORY = "OpenMAIC/音频"
    DISPLAY_NAME = "🎙️ FunASR字幕对齐"
    RETURN_TYPES = ("LIST", "DICT")
    RETURN_NAMES = ("字幕时间点", "对齐信息")
    FUNCTION = "process"
    OUTPUT_NODE = False

    @classmethod
    def INPUT_TYPES(cls) -> Dict[str, Any]:
        return {
            "required": {
                "音频路径": ("STRING", {"tooltip": "音频文件路径（MP3、WAV、M4A）"}),
                "语音事件": ("LIST", {"tooltip": "语音事件列表：[{text, start_ms, end_ms}]"}),
            },
            "optional": {
                "设置": ("DICT", {"default": {}, "tooltip": "FunASR 设置：{model, device, vad_model, punc_model}"}),
            },
        }

    def process(
        self,
        音频路径: str,
        语音事件: List[Dict[str, Any]],
        设置: Optional[Dict[str, Any]] = None,
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """使用 FunASR 对齐字幕"""
        if not os.path.exists(音频路径):
            raise FileNotFoundError(f"音频文件不存在: {音频路径}")

        if not 语音事件:
            return ([], {"mode": "无事件", "aligned_count": 0})

        设置 = 设置 or {}

        # 创建临时目录
        temp_dir = tempfile.mkdtemp(prefix="openmaic_funasr_")

        try:
            # 转换为 16kHz WAV
            wav_path = os.path.join(temp_dir, "input.wav")
            self._convert_audio_to_wav(音频路径, wav_path)

            # 运行 FunASR 识别
            result = self._run_funasr(wav_path, temp_dir, 设置)

            # 对齐识别结果与语音事件
            cues, info = self._align_segments(
                语音事件,
                result.get('segments', []),
                设置
            )

            return (cues, info)

        finally:
            try:
                shutil.rmtree(temp_dir)
            except Exception:
                pass

    def _convert_audio_to_wav(self, input_path: str, output_path: str):
        """转换为 16kHz 单声道 WAV"""
        cmd = [
            'ffmpeg', '-y',
            '-i', input_path,
            '-ar', '16000',
            '-ac', '1',
            '-acodec', 'pcm_s16le',
            output_path,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode != 0:
            raise Exception(f"音频转换失败: {result.stderr}")

    def _run_funasr(
        self,
        wav_path: str,
        work_dir: str,
        设置: Dict[str, Any]
    ) -> Dict[str, Any]:
        """运行 FunASR 语音识别"""
        result_path = os.path.join(work_dir, "funasr_result.json")
        script_path = os.path.join(work_dir, "transcribe.py")

        # 获取配置
        model = 设置.get('model', os.environ.get('FUNASR_MODEL', 'paraformer-zh'))
        device = 设置.get('device', 'auto')
        vad_model = 设置.get('vad_model', 'fsmn-vad')
        punc_model = 设置.get('punc_model', 'ct-punc')

        # 生成识别脚本
        script = self._generate_funasr_script(model, device, vad_model, punc_model)

        with open(script_path, 'w', encoding='utf-8') as f:
            f.write(script)

        # 运行 FunASR
        cmd = [
            os.environ.get('FUNASR_PYTHON', 'python'),
            script_path,
            wav_path,
            result_path,
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=1800,  # 30分钟超时
            )
            if result.returncode != 0:
                raise Exception(f"FunASR 失败: {result.stderr}")

            with open(result_path, 'r', encoding='utf-8') as f:
                return json.load(f)

        except subprocess.TimeoutExpired:
            raise Exception("FunASR 识别超时")
        except FileNotFoundError:
            raise Exception("未找到 FunASR。请安装：pip install funasr")
        except json.JSONDecodeError:
            raise Exception("FunASR 输出格式无效")

    def _generate_funasr_script(
        self,
        model: str,
        device: str,
        vad_model: str,
        punc_model: str
    ) -> str:
        """生成 FunASR 识别脚本"""
        if device == 'auto':
            device_code = '''
import torch
device = "cuda:0" if torch.cuda.is_available() else "cpu"
'''
        else:
            device_code = f'device = "{device}"'

        return f'''
import json
import os
import sys
import traceback

{device_code}

def optional_env(name, default=""):
    value = os.environ.get(name, default)
    if value is None:
        return ""
    value = str(value).strip()
    return "" if value.lower() in ("", "none", "false", "0") else value

try:
    from funasr import AutoModel

    audio_path = sys.argv[1]
    output_path = sys.argv[2]

    kwargs = {{
        "model": "{model}",
        "device": device,
    }}

    vad = "{vad_model}"
    if vad:
        kwargs["vad_model"] = vad
        kwargs["vad_kwargs"] = {{"max_single_segment_time": 30000}}

    punc = "{punc_model}"
    if punc:
        kwargs["punc_model"] = punc

    model = AutoModel(**kwargs)
    result = model.generate(
        input=audio_path,
        sentence_timestamp=True,
        batch_size_s=300,
        use_itn=True,
    )

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False)

except Exception:
    traceback.print_exc()
    sys.exit(1)
'''

    def _align_segments(
        self,
        语音事件: List[Dict[str, Any]],
        funasr_segments: List[Dict[str, Any]],
        设置: Dict[str, Any]
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """将 FunASR 片段与语音事件对齐"""
        if not funasr_segments:
            return self._fallback_to_estimated(语音事件)

        # 提取片段
        segments = self._extract_segments(funasr_segments)

        if not segments:
            return self._fallback_to_estimated(语音事件)

        # 构建对齐
        alignments = []
        aligned_count = 0

        for event in 语音事件:
            event_text = self._normalize_text(event.get('text', ''))
            if not event_text:
                alignments.append({
                    'event': event,
                    'mode': 'empty',
                    'segments': [],
                    'cues': [{
                        'text': '',
                        'start': event.get('start_ms', 0) / 1000.0,
                        'end': event.get('end_ms', 0) / 1000.0,
                    }]
                })
                continue

            # 查找匹配的片段
            matching = self._find_matching_segments(event, segments, 设置)

            if matching:
                aligned_count += 1
                cues = self._build_cues(event, matching)
                alignments.append({
                    'event': event,
                    'mode': 'funasr-aligned',
                    'segments': matching,
                    'cues': cues
                })
            else:
                alignments.append({
                    'event': event,
                    'mode': 'estimated-fallback',
                    'segments': [],
                    'cues': [{
                        'text': event_text,
                        'start': event.get('start_ms', 0) / 1000.0,
                        'end': event.get('end_ms', 0) / 1000.0,
                    }]
                })

        # 扁平化 cues
        all_cues = []
        for alignment in alignments:
            all_cues.extend(alignment['cues'])

        # 构建信息
        info = {
            'mode': 'funasr' if aligned_count > 0 else 'estimated',
            'aligned_count': aligned_count,
            'total_events': len(语音事件),
            'funasr_segments': len(segments),
            'alignment_rate': aligned_count / len(语音事件) if 语音事件 else 0,
        }

        return (all_cues, info)

    def _extract_segments(self, funasr_result) -> List[Dict[str, Any]]:
        """从 FunASR 结果中提取片段"""
        segments = []

        def visit(value):
            if isinstance(value, list):
                for item in value:
                    visit(item)
                return

            if not isinstance(value, dict):
                return

            text = self._normalize_text(
                value.get('text') or
                value.get('sentence') or
                value.get('content') or
                ''
            )

            if not text:
                for key in ['sentence_info', 'sentences', 'segments', 'result', 'results']:
                    if key in value:
                        visit(value[key])
                return

            start_ms = self._extract_timing(value, 'start')
            end_ms = self._extract_timing(value, 'end')

            if start_ms is not None and end_ms is not None and end_ms > start_ms:
                duration = end_ms - start_ms
                if duration >= 120:  # 最小120ms
                    segments.append({
                        'text': text,
                        'start_ms': start_ms,
                        'end_ms': end_ms,
                    })

        visit(funasr_result)

        # 按开始时间排序
        segments.sort(key=lambda x: x['start_ms'])

        # 去重
        seen = set()
        result = []
        for seg in segments:
            key = f"{seg['start_ms']}:{seg['end_ms']}:{seg['text']}"
            if key not in seen:
                seen.add(key)
                result.append(seg)

        return result

    def _extract_timing(self, obj: Dict, key: str) -> Optional[int]:
        """提取时间值（毫秒）"""
        for k in [
            f'{key}_ms', f'{key}ms',
            f'{key}_time', f'{key}time',
            f'begin_{key}' if key == 'start' else None,
            f'end_{key}' if key == 'start' else None,
        ]:
            if k and k in obj:
                value = obj[k]
                if isinstance(value, (int, float)):
                    return int(value * 1000) if value < 10000 else int(value)
                if isinstance(value, str):
                    return self._parse_timestamp(value)

        if 'timestamp' in obj:
            ts = obj['timestamp']
            if isinstance(ts, list) and len(ts) >= 2:
                idx = 0 if key == 'start' else -1
                val = ts[idx]
                if isinstance(val, list):
                    val = val[0 if key == 'start' else 1]
                if isinstance(val, (int, float)):
                    return int(val * 1000) if val < 10000 else int(val)

        return None

    def _parse_timestamp(self, value: str) -> Optional[int]:
        """解析时间戳如 '00:01:23.456' 为毫秒"""
        value = value.strip()
        if ':' in value:
            parts = value.split(':')
            try:
                if len(parts) == 3:
                    h, m, s = parts
                    seconds = float(s)
                    return int((int(h) * 3600 + int(m) * 60 + seconds) * 1000)
                elif len(parts) == 2:
                    m, s = parts
                    seconds = float(s)
                    return int((int(m) * 60 + seconds) * 1000)
            except ValueError:
                pass
        return None

    def _normalize_text(self, text: str) -> str:
        """规范化文本"""
        if not text:
            return ''
        return re.sub(r'\s+', ' ', str(text)).strip()

    def _find_matching_segments(
        self,
        event: Dict[str, Any],
        segments: List[Dict[str, Any]],
        设置: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """查找与语音事件匹配的 FunASR 片段"""
        event_text = self._normalize_text(event.get('text', ''))
        event_start = event.get('start_ms', 0)
        event_end = event.get('end_ms', 0)

        # 时间窗口内的片段
        tolerance = 设置.get('window_tolerance_ms', 420)
        window_start = max(0, event_start - tolerance)
        window_end = event_end + tolerance

        candidates = [
            seg for seg in segments
            if seg['end_ms'] >= window_start and seg['start_ms'] <= window_end
        ]

        if not candidates:
            return []

        # 计算相似度得分
        scored = []
        for seg in candidates:
            score = self._text_similarity(event_text, seg['text'])
            overlap = self._calculate_overlap(
                seg['start_ms'], seg['end_ms'],
                event_start, event_end
            )
            # 加权得分：文本 40%，重叠 60%
            final_score = score * 0.4 + overlap * 0.6
            scored.append((seg, final_score))

        # 按得分降序排序
        scored.sort(key=lambda x: x[1], reverse=True)

        # 返回高分匹配
        threshold = 设置.get('min_match_score', 0.3)
        return [seg for seg, score in scored if score > threshold]

    def _text_similarity(self, text1: str, text2: str) -> float:
        """计算文本相似度 (0-1)"""
        if not text1 or not text2:
            return 0.0

        t1 = self._normalize_text_for_compare(text1)
        t2 = self._normalize_text_for_compare(text2)

        if t1 == t2:
            return 1.0
        if t1 in t2:
            return len(t1) / len(t2)
        if t2 in t1:
            return len(t2) / len(t1)

        # 字符级相似度
        common = sum(1 for a, b in zip(t1, t2) if a == b)
        return common / max(len(t1), len(t2), 1)

    def _normalize_text_for_compare(self, text: str) -> str:
        """规范化比较文本"""
        return self._normalize_text(text).lower()

    def _calculate_overlap(
        self,
        seg_start: int,
        seg_end: int,
        event_start: int,
        event_end: int
    ) -> float:
        """计算时间重叠比例"""
        overlap = max(0, min(seg_end, event_end) - max(seg_start, event_start))
        seg_duration = seg_end - seg_start
        return overlap / max(seg_duration, 1)

    def _build_cues(
        self,
        event: Dict[str, Any],
        segments: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """从对齐片段构建字幕"""
        if not segments:
            return [{
                'text': self._normalize_text(event.get('text', '')),
                'start': event.get('start_ms', 0) / 1000.0,
                'end': event.get('end_ms', 0) / 1000.0,
            }]

        event_start = event.get('start_ms', 0)
        event_end = event.get('end_ms', 0)

        cues = []
        for seg in segments:
            start = max(seg['start_ms'], event_start)
            end = min(seg['end_ms'], event_end)

            if end - start >= 120:  # 最小持续时间
                cues.append({
                    'text': seg['text'],
                    'start': start / 1000.0,
                    'end': end / 1000.0,
                })

        if not cues:
            return [{
                'text': self._normalize_text(event.get('text', '')),
                'start': event.get('start_ms', 0) / 1000.0,
                'end': event.get('end_ms', 0) / 1000.0,
            }]

        return cues

    def _fallback_to_estimated(
        self,
        语音事件: List[Dict[str, Any]]
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """回退到估算时间"""
        cues = []
        for event in 语音事件:
            text = self._normalize_text(event.get('text', ''))
            if text:
                cues.append({
                    'text': text,
                    'start': event.get('start_ms', 0) / 1000.0,
                    'end': event.get('end_ms', 0) / 1000.0,
                })

        info = {
            'mode': 'estimated-fallback',
            'aligned_count': 0,
            'total_events': len(语音事件),
            'funasr_segments': 0,
            'alignment_rate': 0.0,
        }

        return (cues, info)


@register_node
class OpenMAIC_简单字幕对齐:
    """
    简单字幕对齐 - 无需 FunASR，基于时长估算

    根据语音事件的时长估算字幕时间点，
    在自然断点处分割文字。

    类别：OpenMAIC/音频

    输入：
    - 语音事件：包含文字和时间的语音事件列表

    输出：
    - 字幕时间点：字幕时间轴列表
    """

    CATEGORY = "OpenMAIC/音频"
    DISPLAY_NAME = "📋 简单字幕对齐"
    RETURN_TYPES = ("LIST",)
    RETURN_NAMES = ("字幕时间点",)
    FUNCTION = "process"

    @classmethod
    def INPUT_TYPES(cls) -> Dict[str, Any]:
        return {
            "required": {
                "语音事件": ("LIST", {"tooltip": "语音事件列表：[{text, start_ms, end_ms}]"}),
            },
        }

    def process(self, 语音事件: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]]]:
        """从语音事件生成字幕时间点"""
        cues = []
        for event in 语音事件:
            text = self._normalize_text(event.get('text', ''))
            if not text:
                continue

            start_ms = event.get('start_ms', 0)
            end_ms = event.get('end_ms', 0)
            duration_ms = end_ms - start_ms

            # 按自然断点分割文字
            parts = self._split_text(text, duration_ms)

            for i, part in enumerate(parts):
                part_start = start_ms + (duration_ms * i // len(parts))
                part_end = start_ms + (duration_ms * (i + 1) // len(parts))
                cues.append({
                    'text': part,
                    'start': part_start / 1000.0,
                    'end': part_end / 1000.0,
                })

        return (cues,)

    def _normalize_text(self, text: str) -> str:
        if not text:
            return ''
        return re.sub(r'\s+', ' ', str(text)).strip()

    def _split_text(self, text: str, duration_ms: float) -> List[str]:
        """根据时长分割文字"""
        # 目标每条字幕约3-4秒
        target_duration_ms = 3500
        char_per_ms = len(text) / max(duration_ms, 1000)

        # 查找自然断点
        breakpoints = [0]
        current_pos = 0

        for match in re.finditer(r'[。！？!？;；:：，、\s]+', text):
            pos = match.start()
            segment_duration = (pos - current_pos) * char_per_ms

            if segment_duration > target_duration_ms:
                breakpoints.append(pos)
                current_pos = pos
            elif segment_duration > target_duration_ms * 0.7:
                breakpoints.append(pos)
                current_pos = pos

        breakpoints.append(len(text))

        # 提取片段
        parts = []
        for i in range(len(breakpoints) - 1):
            part = text[breakpoints[i]:breakpoints[i + 1]].strip()
            if part:
                parts.append(part)

        return parts if parts else [text]


# 导出节点映射
NODE_CLASS_MAPPINGS = {
    "OpenMAIC_FunASR字幕对齐": OpenMAIC_FunASR字幕对齐,
    "OpenMAIC_简单字幕对齐": OpenMAIC_简单字幕对齐,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "OpenMAIC_FunASR字幕对齐": "🎙️ FunASR字幕对齐",
    "OpenMAIC_简单字幕对齐": "📋 简单字幕对齐",
}
