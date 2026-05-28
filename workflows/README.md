# ComfyUI kktools 工作流示例指南

## 📋 概述

`workflows` 目录提供了按模块划分的示例工作流，每个工作流收录对应模块下所有节点的最小演示。

所有示例都遵循根目录 [readme.md](../readme.md) 的模块划分与说明风格，每个节点都配有一张 `Note` 说明卡，包含功能描述、关键参数和最小演示方式。

当前示例已全部切换到 `kk...` 前缀节点名。

## 🧭 快速上手

- 想按模块学习：
  - 图像：`kkworkflow_image.json`
  - 数学：`kkworkflow_math.json`
  - 提示词：`kkworkflow_prompts.json`
  - 尺寸：`kkworkflow_size.json`
  - 字符串：`kkworkflow_string.json`
  - 随机：`kkworkflow_random.json`
  - 视频：`kkworkflow_video.json`
  - 音频：`kkworkflow_Audio.json`
  - 分镜：`kkworkflow_storyboard.json`

## 🎯 工作流索引

### 模块工作流

#### `kkworkflow_image.json`
- **模块**：图像处理模块
- **包含节点**：
  - `kkImageOverlay`（图像叠加）
  - `kkPadImageToCanvas`（图像填充到画布）
  - `kkImageFrame`（图像边框）
  - `kkResize`（图像蒙版同步调整）
  - `kkGetImage`（获取图像尺寸）
  - `kkBatchImageLoader`（批量图像加载）
  - `kkImageTileSplit2x2`（图像2x2分块）
  - `kkImageGridMerge`（图像宫格合并）
  - `kkImageSplit`（图像切割）
  - `kkimage2_灵思API`
  - `kkimage2_Zuco`
- **说明**：收录图像处理模块下所有节点的最小演示，每个节点配有说明卡

#### `kkworkflow_math.json`
- **模块**：数学运算模块
- **包含节点**：
  - `kkMathExpressionNode`（数学表达式）
  - `kkRegexNode`（正则表达式）
  - `kkRegexNodeAdvanced`（正则表达式高级）
- **说明**：收录数学与正则模块下所有节点的最小演示

#### `kkworkflow_prompts.json`
- **模块**：提示词模块
- **包含节点**：
  - `kkBatchPrompt`（批量提示词）
  - `kkLLM`（多厂商LLM）
- **说明**：收录提示词处理模块下所有节点的最小演示

#### `kkworkflow_size.json`
- **模块**：尺寸生成模块
- **包含节点**：
  - `kkSizeNode`（尺寸生成）
- **说明**：收录尺寸生成模块下所有节点的最小演示

#### `kkworkflow_string.json`
- **模块**：字符串处理模块
- **包含节点**：
  - `kkStringNode`（字符串裁剪）
  - `kkStringNodeAdvanced`（字符串裁剪高级）
  - `kkStringMergeNode`（字符串合并）
  - `kkInputNode`（多类型输入）
  - `kkReplaceNode`（字符串替换）
  - `kkSomethingToAny`（任意类型转换）
  - `kkStringToIntNode`（字符串转整数）
- **说明**：收录字符串处理模块下所有节点的最小演示

#### `kkworkflow_random.json`
- **模块**：随机选择模块
- **包含节点**：
  - `kkRandomSelector`（随机选择器）
- **说明**：收录随机选择模块下所有节点的最小演示

#### `kkworkflow_video.json`
- **模块**：视频处理模块
- **包含节点**：
  - `kkVideoFirstLastFrames`（视频首尾帧提取）
  - `kkVideoFramesAdvanced`（视频抽帧高级）
  - `kkMergeVideos`（视频合并）
- **说明**：收录视频处理模块下所有节点的最小演示

#### `kkworkflow_Audio.json`
- **模块**：音频处理模块
- **包含节点**：
  - `kkAudioMerge4`（音频四合一）
- **说明**：收录音频处理模块下所有节点的最小演示

#### `kkworkflow_storyboard.json`
- **模块**：分镜模块
- **包含节点**：
  - `kkStoryboardScript`（默认分镜）
  - `kkStoryboardScriptLLM`（LLM分镜）
  - `kkStoryboardShotOutput`（分镜输出）
- **说明**：收录分镜模块下所有节点的最小演示

## ⚠️ 使用建议

- 字符串、数学、随机、尺寸、提示词类节点：
  - 打开后即可直接查看默认参数与输出口设计

- 图像、视频、音频、分镜输出类节点：
  - 需要先把你自己的 `IMAGE`、`VIDEO`、`AUDIO`、`LIST` 接到左侧输入口

- `kkBatchImageLoader` 与 `kkBatchPrompt`：
  - 需要把示例中的目录或文件路径改成你本机的真实路径

- `kkLLM` 与 `kkStoryboardScriptLLM`：
  - 需要填写有效的 `api_key` 后再运行
