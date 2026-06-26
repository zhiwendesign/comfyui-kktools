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
  - Imagen Studio：`kktools_imagen_studio_template_pipe_runninghub.workflow.json`
  - Imagen Studio PPT：`kktools_imagen_studio_ppt_pipe.workflow.json`
  - Imagen Studio PPT 灵思转接：`kktools_imagen_studio_ppt_lingsi_bridge.workflow.json`

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

#### `kktools_imagen_studio_template_pipe_runninghub.workflow.json`
- **模块**：Imagen Studio 模板工具
- **包含节点**：
  - `Imagen Studio 模板蒸馏`
  - `Imagen Studio 模板入库`
  - `Imagen Studio 模板选择器`
  - `Imagen Studio 模板拼装`
  - `Imagen Studio RunningHub 生图`
- **说明**：展示模板蒸馏入库、模板选择、提示词拼装和 RunningHub 生图的完整节点束流程

#### `kktools_imagen_studio_template_pipe_runninghub.api.json`
- **模块**：Imagen Studio 模板工具
- **说明**：对应 API 格式示例，适合通过 ComfyUI API 调用同一套模板束工作流

#### `kktools_imagen_studio_ppt_pipe.workflow.json`
- **模块**：Imagen Studio PPT 工具
- **包含节点**：
  - `Imagen Studio PPT 大纲草拟`
  - `Imagen Studio PPT 大纲规划`
  - `Imagen Studio PPT 设计规范`
  - `Imagen Studio PPT 页面拼装`
  - `kkimage2_灵思API`
  - `Imagen Studio PPT 束拆包`
  - `Imagen Studio PPT 图像写回`
  - `Imagen Studio PPT 导出`
- **说明**：展示从模板选择、大纲草拟、页面规划、prompt 拼装、灵思批量生图到 PPTX 导出的完整节点束流程
- **节点束**：PPT 节点和模板节点共用 `IMAGEN_STUDIO_PIPE`，PPT 输出束会保留模板信息并追加页面、prompt、结果和导出字段
- **运行状态**：`PPT 页面拼装`、`kkimage2_灵思API` 的 PPT 批量模式和 `PPT RunningHub 批量生图` 会在节点内显示状态条，控制台同步输出详细阶段日志
- **页面拼装**：`Imagen Studio PPT 页面拼装` 默认 `并发数=20`，最大 50；输出仍按 PPT 页序排列
- **批量生图**：`kkimage2_灵思API` 可直接接 `PPT束`，默认 `并发数=3`，最大 20；遇到 429 会自动重试，默认重试 6 次，基础等待 15 秒，单次等待最多 500 秒；输出仍按 PPT 页序排列
- **单页调试**：`PPT 束拆包` 可把指定页的 `正向提示词` 拆成普通字符串接到 `kkimage2_灵思API.prompt`；再把 `PPT 束拆包.当前页码` 接到 `PPT 图像写回.页码`，生图结果会自动写回同一页
- **导出连线**：默认只连接 `kkimage2_灵思API.PPT束 -> PPT 导出.PPT束`；`image` 输出只接 `SaveImage`，避免画布保存时产生孤儿图片链接
- **导出位置**：PPTX 默认写入 ComfyUI 的 `output/imagen-ppt/`，`PPT文件路径` 输出会返回完整路径

#### `kktools_imagen_studio_ppt_lingsi_bridge.workflow.json`
- **模块**：Imagen Studio PPT 工具 + `kkimage2_灵思API`
- **包含节点**：
  - `Imagen Studio 模板选择器`
  - `Imagen Studio PPT 大纲规划`
  - `Imagen Studio PPT 设计规范`
  - `Imagen Studio PPT 页面拼装`
  - `Imagen Studio PPT 束拆包`
  - `kkimage2_灵思API`
  - `Imagen Studio PPT 图像写回`
  - `Imagen Studio PPT 导出`
  - `SaveImage`
- **说明**：演示单页调试链路：把 `PPT束` 拆成普通 prompt 接入灵思生图，再把图片写回同一页并导出 PPTX
- **关键连线**：`PPT 束拆包.正向提示词 -> kkimage2_灵思API.prompt`，`PPT 束拆包.当前页码 -> PPT 图像写回.页码`
- **使用方式**：默认生成第 1 页；要生成其它页，只改 `PPT 束拆包` 的 `页码`，写回页码会自动同步

## ⚠️ 使用建议

- 字符串、数学、随机、尺寸、提示词类节点：
  - 打开后即可直接查看默认参数与输出口设计

- 图像、视频、音频、分镜输出类节点：
  - 需要先把你自己的 `IMAGE`、`VIDEO`、`AUDIO`、`LIST` 接到左侧输入口

- `kkBatchImageLoader` 与 `kkBatchPrompt`：
  - 需要把示例中的目录或文件路径改成你本机的真实路径

- `kkLLM` 与 `kkStoryboardScriptLLM`：
  - 需要填写有效的 `api_key` 后再运行
