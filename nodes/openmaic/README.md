# ComfyUI OpenMAIC 节点

ComfyUI 自定义节点，用于课件导入和视频导出流水线。

## 安装

1. 将此文件夹复制到 ComfyUI 的 `custom_nodes` 目录：
   ```
   custom_nodes/ComfyUI-OpenMAIC-Nodes/
   ```

2. 重启 ComfyUI

3. 节点将出现在 ComfyUI 节点浏览器中的 `OpenMAIC` 类别下。

---

## 节点概览

### 📂 导入节点 (OpenMAIC/导入)

| 节点 | 说明 |
|------|------|
| 📂 导入课件 | 通过 OpenMAIC API 导入课件并生成讲解 |
| 📂 导入课件（独立版） | 直接处理幻灯片，无需 API |
| 🖼️ 从图片加载课件 | 从图片文件路径加载课件 |

### ✅ 独立完整流程节点 (OpenMAIC/独立版)

| 节点 | 说明 |
|------|------|
| OpenMAIC 独立导入课件 | PPTX/PDF/图片目录转本地页图和页面文本 |
| OpenMAIC 独立生成讲稿 | 保留原文、口语化、教学化或按页面生成讲稿 |
| OpenMAIC 独立批量TTS | 逐页/逐段生成音频并合并讲解音频 |
| OpenMAIC 独立导出课件视频 | 页图 + 音频 + 字幕 + BGM 合成 MP4 |

### 📹 导出节点 (OpenMAIC/导出)

| 节点 | 说明 |
|------|------|
| 📹 视频导出 | 导出视频：合并画面、音频、字幕、BGM |
| ⚙️ 导出设置 | 创建视频导出配置 |

### 🎵 音频节点 (OpenMAIC/音频)

| 节点 | 说明 |
|------|------|
| 🎵 音频混音 | 混音：讲解音频 + 背景音乐 |
| 📝 字幕生成 | 生成 ASS 格式字幕文件 |
| 🎙️ FunASR字幕对齐 | **ASR对齐字幕** - 使用 FunASR 精确识别语音并对齐时间 |
| 📋 简单字幕对齐 | 简单字幕对齐（无需 ASR，基于时长估算） |

### 🔧 工具节点 (OpenMAIC/工具)

| 节点 | 说明 |
|------|------|
| 🔢 拆分讲解列表 | 拆分讲解列表用于迭代处理 |
| 🎬 字幕时间点提取 | 从讲解动作提取字幕时间点 |

---

## 工作流架构

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         完整视频导出流水线                                 │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  【课件】 ──► 【导入】 ──► 【动作列表】                                    │
│                              │                                           │
│         ┌───────────────────┼───────────────────┐                      │
│         ▼                   ▼                   ▼                       │
│   【语音动作】         【FunASR对齐】         【音频混音】                  │
│         │                (ASR识别)              │                       │
│         ▼                   │                   │                       │
│   【字幕时间点】 ◄────────────┘                   │                       │
│         │                                        │                       │
│         │                    ┌───────────────────┘                       │
│         ▼                    ▼                                           │
│   【字幕文件(ASS)】      【混音音频】                                       │
│         │                      │                                        │
│         └──────────┬──────────┘                                          │
│                    ▼                                                      │
│              【视频编码器】                                                 │
│                    │                                                      │
│                    ▼                                                      │
│              【最终视频】                                                  │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 核心功能：FunASR 字幕对齐

### 什么是 FunASR？

FunASR（Fun Automated Speech Recognition）是阿里巴巴开源的语音识别模型，可以将音频转录为带时间戳的文字序列。

### 工作原理

1. **语音转文字**: FunASR 将音频转录为带精确时间戳的文字
2. **时间对齐**: 将 ASR 识别结果与原始讲稿/动作匹配
3. **字幕生成**: 基于对齐结果生成精确的字幕时间轴

### 优势

- 字幕时间点基于实际语音，而非估算
- 自动处理语速变化
- 支持中文（paraformer-zh 模型）
- 对齐失败时自动回退到估算时间

### 安装 FunASR

```bash
pip install funasr

# 或安装 GPU 版本（需要 NVIDIA 显卡）
pip install funasr[onnxruntime-gpu]
```

### 环境变量

```bash
# Python 解释器（如果不在 PATH 中）
FUNASR_PYTHON=python

# 默认模型
FUNASR_MODEL=paraformer-zh

# 推理设备
FUNASR_DEVICE=auto   # 自动选择（优先GPU）
# 或指定设备
FUNASR_DEVICE=cpu    # 仅CPU
FUNASR_DEVICE=cuda:0 # 指定GPU
```

---

## 使用示例

### 推荐：独立完整课件视频

新主示例：

```
workflows/openmaic-standalone-full-video.workflow.json
```

这条链路不依赖 OpenMAIC 项目后端服务：

```
【OpenMAIC 独立导入课件】
        ↓
【OpenMAIC 独立生成讲稿】
        ↓
【OpenMAIC 独立批量TTS】
        ↓
【OpenMAIC 独立导出课件视频】
```

说明：

- `独立导入课件` 支持 PPTX/PDF/图片目录，并输出真实本地页图。
- `独立生成讲稿` 在节点内配置 OpenAI-compatible LLM，不读取 OpenMAIC 前端设置。
- `独立批量TTS` 默认调用本地 IndexTTS Gradio：`http://127.0.0.1:7861`。
- `独立导出课件视频` 直接用页图、音频和字幕合成 MP4，不需要 VHS 空路径节点。

### 完整流程（带 FunASR）

```
【从图片加载课件】→【导入课件】→【语音动作】
                                          │
                      ┌───────────────────┤
                      ▼                   ▼
              【音频文件】         【语音动作】
                      │                   │
                      ▼                   ▼
              【音频混音】         【FunASR字幕对齐】
                      │                   │
                      │                   ▼
                      │            【字幕生成(ASS)】
                      │                   │
                      └─────────┬─────────┘
                                ▼
                         【导出设置】
                                │
                                ▼
                         【视频导出】
```

### 简单流程（无需 FunASR）

```
【从图片加载课件】→【导入课件】→【字幕时间点提取】→【字幕生成】
                                          │
【音频文件】 ──────────────────────────────►【音频混音】
                                          │
                              ┌───────────┴───────────┐
                              ▼                       ▼
                       【导出设置】               【视频导出】
```

---

## 节点输入输出详解

### 🎙️ FunASR字幕对齐

| 输入 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| 音频路径 | STRING | - | 音频文件路径（MP3、WAV、M4A） |
| 语音事件 | LIST | - | 语音事件列表: [{text, start_ms, end_ms}] |
| 设置 | DICT | {} | FunASR 设置 |

**设置选项：**
```python
{
    "model": "paraformer-zh",      # FunASR 模型
    "device": "auto",              # 设备: auto/cpu/cuda:0
    "vad_model": "fsmn-vad",       # 语音活动检测模型
    "punc_model": "ct-punc",       # 标点恢复模型
    "window_tolerance_ms": 420,    # 时间窗口容差（毫秒）
    "min_match_score": 0.3,        # 最小匹配分数
}
```

**输出：**
```python
{
    "字幕时间点": [
        {"text": "第一句台词", "start": 0.0, "end": 2.5},
        {"text": "第二句台词", "start": 2.5, "end": 5.0},
    ],
    "对齐信息": {
        "mode": "funasr-aligned",
        "aligned_count": 10,
        "total_events": 12,
        "alignment_rate": 0.83,
    }
}
```

### 📹 视频导出

| 输入 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| 视频画面 | STRING | - | 视频帧目录或MP4文件 |
| 讲解音频 | STRING | - | 讲解音频文件路径 |
| 导出设置 | DICT | {} | 导出配置 |
| 背景音乐 | STRING | "" | BGM路径（可选） |
| 字幕时间点 | LIST | [] | 字幕时间轴 |

### ⚙️ 导出设置

| 输入 | 类型 | 默认值 | 选项 |
|------|------|--------|------|
| 分辨率 | STRING | 1080p | 720p, 1080p, 1440p, 4k |
| 帧率 | INT | 30 | 24-60 |
| 编码器 | STRING | nvenc | cpu=通用, nvenc=NVIDIA, qsv=Intel, amf=AMD |
| 启用字幕 | BOOLEAN | True | 是否烧录字幕 |
| 启用BGM | BOOLEAN | False | 是否启用BGM |
| 讲解音量 | INT | 0 | -24 到 +12 dB |
| BGM音量 | INT | -18 | -48 到 0 dB |

---

## 系统要求

### FFmpeg（必须）

FFmpeg 用于视频编码和音频处理：

```bash
# Windows
winget install ffmpeg

# macOS
brew install ffmpeg

# Linux
sudo apt install ffmpeg
```

### FunASR（可选，用于精确字幕对齐）

```bash
pip install funasr
```

---

## 原项目对应逻辑

本节点实现参考了原项目的以下核心逻辑：

### 1. FunASR 字幕对齐

**原项目文件**: `lib/server/video-export/funasr-subtitles.ts`

```typescript
// 原项目核心流程
const result = await transcribeWithLocalFunASR({ audioPath, workDir });
const aligned = alignFunASRSegmentsToSpeechEvents(speechEvents, result.segments);

// 对齐策略：
// - 文本相似度匹配 (40%)
// - 时间重叠计算 (60%)
// - 失败时回退到估算时间
```

### 2. 音频混音

**原项目文件**: `lib/server/video-export/ffmpeg.ts`

```typescript
// 原项目 FFmpeg 混音命令
buildMixBgmAudioCommand({
    narrationPath,
    bgmPath,
    narrationVolumeDb,  // dB调整
    bgmVolumeDb,       // BGM音量
    loop: true,
})
```

### 3. 字幕生成

**原项目文件**: `lib/server/video-export/subtitles.ts`

```typescript
// 生成ASS格式字幕
buildAssSubtitleDocument(cues, { width, height, style })
```

### 4. 课件导入

**原项目文件**: `lib/server/imported-classroom/runner.ts`

```typescript
// 导入课件核心流程
const matches = matchScriptToSlides(deck, script);
const actionPlans = buildImportedLectureActions(deck, matches);
```

---

## 文件结构

```
ComfyUI-OpenMAIC-Nodes/
├── __init__.py              # 节点注册入口
├── video_export.py          # 视频导出节点（音频混音）
├── funasr_subtitles.py     # FunASR 字幕对齐节点
├── node_definitions.json    # 节点定义文档
├── README.md                # 本文档
└── workflows/              # 工作流示例
    ├── full-export-with-funasr.json    # 完整流程（FunASR）
    ├── basic-export-no-funasr.json      # 基础流程（无ASR）
    ├── video-export-pipeline.json       # 视频导出示例
    └── basic-import-deck.json          # 导入课件示例
```
