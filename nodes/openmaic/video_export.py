"""
ComfyUI OpenMAIC 节点 - 视频导出节点

视频导出节点，包含音频混音、字幕压制和编码功能。

功能：
- 合并讲解音频和背景音乐
- 生成字幕（ASS格式）
- 支持多种编码器（CPU、NVENC、QSV、AMF）
- 分辨率预设（720p、1080p、1440p、4K）
"""

import os
import json
import subprocess
import tempfile
import shutil
from typing import Tuple, Dict, Any, Optional, List

NODE_CLASS_MAPPINGS = {}
NODE_DISPLAY_NAME_MAPPINGS = {}

VIDEO_EXPORT_RESOLUTIONS = {
    '720p': {'width': 1280, 'height': 720, 'bitrate': 4},
    '1080p': {'width': 1920, 'height': 1080, 'bitrate': 8},
    '1440p': {'width': 2560, 'height': 1440, 'bitrate': 16},
    '4k': {'width': 3840, 'height': 2160, 'bitrate': 35},
}

DEFAULT_SUBTITLE_STYLE = {
    'font_family': '微软雅黑',
    'font_size_px': 48,
    'font_weight': 'bold',
    'text_color': '#ffffff',
    'outline_color': '#000000',
    'outline_width_px': 4,
    'shadow_enabled': True,
    'shadow_blur_px': 8,
    'shadow_opacity': 0.35,
    'position': 'bottom-safe',
    'background_mode': 'none',
}


def register_node(cls):
    NODE_CLASS_MAPPINGS[cls.__name__] = cls
    NODE_DISPLAY_NAME_MAPPINGS[cls.__name__] = cls.DISPLAY_NAME
    return cls


@register_node
class OpenMAIC_视频导出:
    """
    视频导出 - 合并画面、音频、字幕和BGM

    类别：OpenMAIC/导出

    输入：
    - 视频画面：视频帧目录路径或已有MP4文件
    - 讲解音频：讲解音频文件路径
    - 导出设置：导出配置（分辨率、FPS、编码器等）
    - 背景音乐：背景音乐文件路径（可选）
    - 字幕时间点：字幕时间轴列表（可选）

    输出：
    - 视频输出：输出视频文件路径
    - 音频输出：输出音频文件路径
    """
    CATEGORY = "OpenMAIC/导出"
    DISPLAY_NAME = "📹 视频导出"
    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("视频输出", "音频输出")
    FUNCTION = "process"
    OUTPUT_NODE = True

    @classmethod
    def INPUT_TYPES(cls) -> Dict[str, Any]:
        return {
            "required": {
                "视频画面": ("STRING", {"tooltip": "视频帧目录或MP4文件路径"}),
                "讲解音频": ("STRING", {"tooltip": "讲解音频文件路径（WAV、MP3、M4A）"}),
                "导出设置": ("DICT", {"default": {}, "tooltip": "导出配置设置"}),
            },
            "optional": {
                "背景音乐": ("STRING", {"default": "", "tooltip": "背景音乐文件路径（可选）"}),
                "字幕时间点": ("LIST", {"default": [], "tooltip": "字幕时间轴：[{start, end, text}]"}),
            },
        }

    def process(self, 视频画面, 讲解音频, 导出设置, 背景音乐="", 字幕时间点=None):
        if 字幕时间点 is None:
            字幕时间点 = []

        config = self._parse_export_settings(导出设置)
        temp_dir = tempfile.mkdtemp(prefix="openmaic_export_")

        try:
            # 1. 构建混音音频
            audio_output = self._build_mixed_audio(讲解音频, 背景音乐, config, temp_dir)

            # 2. 生成字幕文件
            subtitle_path = None
            if config['subtitle_enabled'] and 字幕时间点:
                subtitle_path = self._generate_subtitle_file(字幕时间点, config, temp_dir)

            # 3. 编码视频
            video_output = self._encode_video(视频画面, audio_output, subtitle_path, config, temp_dir)
            return (video_output, audio_output)
        finally:
            try:
                shutil.rmtree(temp_dir)
            except Exception:
                pass

    def _parse_export_settings(self, settings):
        resolution = settings.get('resolution', '1080p')
        res = VIDEO_EXPORT_RESOLUTIONS.get(resolution, VIDEO_EXPORT_RESOLUTIONS['1080p'])
        return {
            'width': res['width'],
            'height': res['height'],
            'fps': settings.get('fps', 30),
            'video_bitrate_mbps': settings.get('video_bitrate_mbps', res['bitrate']),
            'audio_bitrate_kbps': settings.get('audio_bitrate_kbps', 192),
            'encoder': settings.get('encoder', 'cpu'),
            'subtitle_enabled': settings.get('subtitle_enabled', True),
            'subtitle_style': settings.get('subtitle_style', DEFAULT_SUBTITLE_STYLE),
            'narration_volume_db': settings.get('narration_volume_db', 0),
            'bgm_enabled': bool(settings.get('bgm_path') or settings.get('bgm_enabled')),
            'bgm_volume_db': settings.get('bgm_volume_db', -18),
            'bgm_loop': settings.get('bgm_loop', True),
        }

    def _build_mixed_audio(self, narration_path, bgm_path, config, temp_dir):
        output_path = os.path.join(temp_dir, "mixed_audio.m4a")
        if not config['bgm_enabled'] or not bgm_path:
            return self._normalize_audio(narration_path, config, temp_dir)

        duration = self._get_media_duration(narration_path)
        bgm_input = ['-stream_loop', '-1', '-i', bgm_path] if config['bgm_loop'] else ['-i', bgm_path]
        narr_gain = 10 ** (config['narration_volume_db'] / 20)
        bgm_gain = 10 ** (config['bgm_volume_db'] / 20)

        filter_complex = [
            f'[0:a]aresample=44100,aformat=channel_layouts=stereo,volume={narr_gain}[n]',
            f'[1:a]aresample=44100,aformat=channel_layouts=stereo,volume={bgm_gain},atrim=0:{duration:.3f},asetpts=N/SR/TB[b]',
            '[n][b]amix=inputs=2:duration=first:normalize=0[m]',
            '[m]alimiter=limit=0.95:attack=5:release=50[out]',
        ]
        cmd = ['ffmpeg', '-y', '-i', narration_path, *bgm_input, '-filter_complex', ';'.join(filter_complex),
               '-map', '[out]', '-t', f'{duration:.3f}', '-c:a', 'aac', '-b:a', f"{config['audio_bitrate_kbps']}k", output_path]
        self._run_ffmpeg(cmd)
        return output_path

    def _normalize_audio(self, audio_path, config, temp_dir):
        output_path = os.path.join(temp_dir, "normalized_audio.m4a")
        if config['narration_volume_db'] == 0:
            cmd = ['ffmpeg', '-y', '-i', audio_path, '-c:a', 'aac', '-b:a', f"{config['audio_bitrate_kbps']}k", output_path]
        else:
            gain = 10 ** (config['narration_volume_db'] / 20)
            cmd = ['ffmpeg', '-y', '-i', audio_path, '-af', f'aresample=44100,aformat=stereo,volume={gain}',
                   '-c:a', 'aac', '-b:a', f"{config['audio_bitrate_kbps']}k", output_path]
        self._run_ffmpeg(cmd)
        return output_path

    def _generate_subtitle_file(self, cues, config, temp_dir):
        if not cues:
            return None
        output_path = os.path.join(temp_dir, "subtitles.ass")
        style = config['subtitle_style']

        ass_content = f"""[Script Info]
Title: OpenMAIC 字幕
ScriptType: v4.00+

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, Bold, BorderStyle, Outline, Shadow, Alignment
Style: Default,{style.get('font_family', '微软雅黑')},{style.get('font_size_px', 48)},&H00FFFFFF,&H00000000,&H00000000,{(style.get('font_weight') == 'bold')},1,{style.get('outline_width_px', 4)},{style.get('shadow_blur_px', 8)},2

[Events]
Format: Layer, Start, End, Style, Text
"""
        for cue in cues:
            start = self._seconds_to_ass_time(cue.get('start', 0))
            end = self._seconds_to_ass_time(cue.get('end', cue.get('start', 0) + 1))
            text = cue.get('text', '').replace('\n', '\\N')
            ass_content += f"Dialogue: 0,{start},{end},Default,{text}\n"

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(ass_content)
        return output_path

    def _encode_video(self, video_input, audio_path, subtitle_path, config, temp_dir):
        output_path = os.path.join(temp_dir, "output_video.mp4")
        encoder_map = {'cpu': 'libx264', 'nvenc': 'h264_nvenc', 'qsv': 'h264_qsv', 'amf': 'h264_amf'}
        video_codec = encoder_map.get(config['encoder'], 'libx264')
        preset = 'fast' if config['encoder'] != 'cpu' else 'veryfast'

        if os.path.isdir(video_input):
            input_args = ['-framerate', str(config['fps']), '-i', os.path.join(video_input, '%06d.png')]
        else:
            input_args = ['-i', video_input]

        cmd = ['ffmpeg', '-y', *input_args, '-i', audio_path]
        if subtitle_path:
            cmd.extend(['-vf', f"subtitles='{subtitle_path}'"])
        cmd.extend(['-c:v', video_codec, '-preset', preset, '-b:v', f"{config['video_bitrate_mbps']}M",
                   '-r', str(config['fps']), '-pix_fmt', 'yuv420p', '-c:a', 'aac',
                   '-b:a', f"{config['audio_bitrate_kbps']}k", '-movflags', '+faststart', '-shortest', output_path])
        self._run_ffmpeg(cmd)
        return output_path

    def _run_ffmpeg(self, cmd, timeout=300):
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if result.returncode != 0:
            raise Exception(f"FFmpeg 错误: {result.stderr}")

    def _get_media_duration(self, file_path):
        cmd = ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', file_path]
        result = subprocess.run(cmd, capture_output=True, text=True)
        return float(result.stdout.strip())

    def _seconds_to_ass_time(self, seconds):
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = seconds % 60
        return f"{h}:{m:02d}:{s:05.2f}"


@register_node
class OpenMAIC_导出设置:
    """导出设置 - 创建视频导出配置"""
    CATEGORY = "OpenMAIC/导出"
    DISPLAY_NAME = "⚙️ 导出设置"
    RETURN_TYPES = ("DICT",)
    RETURN_NAMES = ("设置",)
    FUNCTION = "process"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "分辨率": (["720p", "1080p", "1440p", "4k"], {"default": "1080p", "tooltip": "视频分辨率"}),
                "帧率": ("INT", {"default": 30, "min": 24, "max": 60, "tooltip": "每秒帧数"}),
                "编码器": (["cpu", "nvenc", "qsv", "amf"], {"default": "nvenc", "tooltip": "cpu=通用 | nvenc=NVIDIA | qsv=Intel | amf=AMD"}),
            },
            "optional": {
                "启用字幕": ("BOOLEAN", {"default": True, "tooltip": "是否烧录字幕到视频"}),
                "启用BGM": ("BOOLEAN", {"default": False, "tooltip": "是否启用背景音乐"}),
                "讲解音量": ("INT", {"default": 0, "min": -24, "max": 12, "tooltip": "讲解音量调整（dB）"}),
                "BGM音量": ("INT", {"default": -18, "min": -48, "max": 0, "tooltip": "背景音乐音量（dB）"}),
            },
        }

    def process(self, 分辨率, 帧率, 编码器, 启用字幕=True, 启用BGM=False, 讲解音量=0, BGM音量=-18):
        res = VIDEO_EXPORT_RESOLUTIONS.get(分辨率, VIDEO_EXPORT_RESOLUTIONS['1080p'])
        return ({
            "resolution": 分辨率,
            "width": res['width'],
            "height": res['height'],
            "fps": 帧率,
            "video_bitrate_mbps": res['bitrate'],
            "audio_bitrate_kbps": 192,
            "encoder": 编码器,
            "subtitle_enabled": 启用字幕,
            "subtitle_style": DEFAULT_SUBTITLE_STYLE.copy(),
            "narration_volume_db": 讲解音量,
            "bgm_enabled": 启用BGM,
            "bgm_volume_db": BGM音量,
            "bgm_loop": True,
        },)


@register_node
class OpenMAIC_音频混音:
    """音频混音 - 混合讲解音频与背景音乐"""
    CATEGORY = "OpenMAIC/音频"
    DISPLAY_NAME = "🎵 音频混音"
    RETURN_TYPES = ("STRING", "FLOAT")
    RETURN_NAMES = ("混音音频", "时长")
    FUNCTION = "process"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {"讲解音频": ("STRING", {"tooltip": "讲解音频文件路径"})},
            "optional": {
                "背景音乐": ("STRING", {"default": "", "tooltip": "背景音乐文件路径（可选）"}),
                "讲解音量": ("INT", {"default": 0, "min": -24, "max": 12, "tooltip": "讲解音量（dB）"}),
                "BGM音量": ("INT", {"default": -18, "min": -48, "max": 0, "tooltip": "背景音乐音量（dB）"}),
                "循环BGM": ("BOOLEAN", {"default": True, "tooltip": "循环BGM至讲解长度"}),
            },
        }

    def process(self, 讲解音频, 背景音乐="", 讲解音量=0, BGM音量=-18, 循环BGM=True):
        temp_dir = tempfile.mkdtemp(prefix="openmaic_audio_")
        output_path = os.path.join(temp_dir, "mixed_audio.m4a")
        duration = self._get_duration(讲解音频)
        narr_gain = 10 ** (讲解音量 / 20)

        if not 背景音乐:
            cmd = ['ffmpeg', '-y', '-i', 讲解音频, '-af', f'volume={narr_gain}', '-c:a', 'aac', '-b:a', '192k', output_path]
        else:
            bgm_gain = 10 ** (BGM音量 / 20)
            bgm_input = ['-stream_loop', '-1', '-i', 背景音乐] if 循环BGM else ['-i', 背景音乐]
            fc = [
                f'[0:a]aresample=44100,aformat=stereo,volume={narr_gain}[n]',
                f'[1:a]aresample=44100,aformat=stereo,volume={bgm_gain},atrim=0:{duration:.3f},asetpts=N/SR/TB[b]',
                '[n][b]amix=inputs=2:normalize=0[m]',
                '[m]alimiter=limit=0.95:attack=5:release=50[out]',
            ]
            cmd = ['ffmpeg', '-y', '-i', 讲解音频, *bgm_input, '-filter_complex', ';'.join(fc),
                   '-map', '[out]', '-t', f'{duration:.3f}', '-c:a', 'aac', '-b:a', '192k', output_path]

        self._run_ffmpeg(cmd)
        return (output_path, duration)

    def _run_ffmpeg(self, cmd):
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            raise Exception(f"FFmpeg 错误: {r.stderr}")

    def _get_duration(self, file_path):
        r = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', file_path],
                          capture_output=True, text=True)
        return float(r.stdout.strip())


@register_node
class OpenMAIC_字幕生成:
    """字幕生成 - 从语音片段生成ASS字幕文件"""
    CATEGORY = "OpenMAIC/音频"
    DISPLAY_NAME = "📝 字幕生成"
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("字幕文件",)
    FUNCTION = "process"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {"语音片段": ("LIST", {"tooltip": "语音片段列表：[{text, start, end}]"})},
            "optional": {"样式": ("DICT", {"default": DEFAULT_SUBTITLE_STYLE, "tooltip": "字幕样式设置"})},
        }

    def process(self, 语音片段, 样式=None):
        if 样式 is None:
            样式 = DEFAULT_SUBTITLE_STYLE
        temp_dir = tempfile.mkdtemp(prefix="openmaic_subtitles_")
        output_path = os.path.join(temp_dir, "subtitles.ass")

        ass = f"""[Script Info]
Title: OpenMAIC 字幕
ScriptType: v4.00+

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, Bold, BorderStyle, Outline, Shadow, Alignment
Style: Default,{样式.get('font_family', '微软雅黑')},{样式.get('font_size_px', 48)},&H00FFFFFF,&H00000000,&H00000000,{(样式.get('font_weight') == 'bold')},1,{样式.get('outline_width_px', 4)},{样式.get('shadow_blur_px', 8)},2

[Events]
Format: Layer, Start, End, Style, Text
"""
        for seg in 语音片段:
            start = self._to_ass_time(seg.get('start', 0))
            end = self._to_ass_time(seg.get('end', seg.get('start', 0) + 1))
            text = seg.get('text', '').replace('\n', '\\N')
            ass += f"Dialogue: 0,{start},{end},Default,{text}\n"

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(ass)
        return (output_path,)

    def _to_ass_time(self, seconds):
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = seconds % 60
        return f"{h}:{m:02d}:{s:05.2f}"


@register_node
class OpenMAIC_从动作提取字幕:
    """从讲解动作提取字幕时间点"""
    CATEGORY = "OpenMAIC/工具"
    DISPLAY_NAME = "🎬 字幕时间点提取"
    RETURN_TYPES = ("LIST",)
    RETURN_NAMES = ("字幕时间点",)
    FUNCTION = "process"

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"动作列表": ("LIST", {"tooltip": "动作列表"})}}

    def process(self, 动作列表):
        cues = []
        for action in 动作列表:
            if action.get('type') == 'speech' and action.get('text'):
                cues.append({
                    'text': action['text'],
                    'start': action.get('start_ms', 0) / 1000.0,
                    'end': action.get('end_ms', action.get('start_ms', 0) + 3000) / 1000.0,
                })
        return (cues,)


# 导出节点映射
NODE_CLASS_MAPPINGS = {
    "OpenMAIC_视频导出": OpenMAIC_视频导出,
    "OpenMAIC_导出设置": OpenMAIC_导出设置,
    "OpenMAIC_音频混音": OpenMAIC_音频混音,
    "OpenMAIC_字幕生成": OpenMAIC_字幕生成,
    "OpenMAIC_从动作提取字幕": OpenMAIC_从动作提取字幕,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "OpenMAIC_视频导出": "📹 视频导出",
    "OpenMAIC_导出设置": "⚙️ 导出设置",
    "OpenMAIC_音频混音": "🎵 音频混音",
    "OpenMAIC_字幕生成": "📝 字幕生成",
    "OpenMAIC_从动作提取字幕": "🎬 字幕时间点提取",
}
