# ComfyUI kktools 节点包使用说明

欢迎合作交流微信【kkcomfy】  
共创：KK HL

## 📋 概述

kktools 是一组面向 ComfyUI 的实用节点集合，当前版本为 `v3.5.0`，覆盖图像处理、数学与正则、提示词处理、尺寸生成、字符串处理、随机选择、视频处理、音频拼接、分镜生成，以及 OpenMAIC 独立课件视频流程等常见工作流场景。

当前版本的几个统一规则：
- 节点显示名默认使用 `英文名（中文名）`
- 节点分类统一在 `🌟kktools/...`
- 所有节点类名统一增加 `kk` 前缀，便于和官方节点或第三方节点区分
- `nodes/` 目录下的节点文件由 [__init__.py](__init__.py) 自动发现并注册
- 前端扩展 [web/kkllm.js](web/kkllm.js) 会为 `kkLLM` 和 `kkStoryboardScriptLLM` 提供 `provider` / `model` 联动
- 前端扩展 [web/kk_markdown_upload.js](web/kk_markdown_upload.js) 为 `kkMarkdown上传` 提供本地 `.md` 文件选择与上传
- 前端扩展 [web/skills_template_selector.js](web/skills_template_selector.js) 为 `kkSkills模板选择器` 提供 Skill 卡片管理
- 前端扩展 [web/imagen_theme.js](web/imagen_theme.js) 参考 PPT 工具风格，为不同节点分类提供独立配色
- 顶部“运行管理”实时显示 CPU、系统内存、GPU 与显存使用情况，并支持原生运行工具栏靠近顶部时自动吸附
- 示例工作流已经同步到当前节点名

发布说明见 [RELEASE_NOTES_3.5.0.md](RELEASE_NOTES_3.5.0.md)。模板与 PPT 节点分别位于 `🌟kktools/模板工具`、`🌟kktools/PPT工具`；灵思生图统一使用 `kkGPT-image_API`。

## 🚀 安装

1. 将本项目目录放到 `ComfyUI/custom_nodes/comfyui-kktools-main` 下。
2. 在 ComfyUI 使用的 Python 环境中安装依赖：

```bash
pip install numpy pillow requests
# 可选：不同采样率音频自动重采样
pip install torchaudio
```

3. 重启 ComfyUI，等待 kktools 节点自动注册。
4. 在节点面板中搜索 `🌟kktools`、英文类名或中文名。
5. 如果需要图像标注里的中文字体，请把 `.ttf`、`.otf`、`.ttc` 放到 [fonts](fonts) 目录。

## 📦 依赖与环境

- 基础依赖：`torch`、`numpy`、`Pillow`
- 网络能力：`requests`
- 可选依赖：`torchaudio`
  - 当 `kkAudioMerge4` 处理不同采样率音频时，会尝试调用 `torchaudio` 自动重采样
- LLM 节点支持多厂商 API：DeepSeek、OpenAI、Gemini、豆包
- 图像 API 节点：
  - `kk_API配置`：集中保存 Base URL 和 API Key，可同时连接 `kkGPT-image_API` 与 `kkLLM`。
  - `kkGPT-image_API`：支持普通多图参考、模板束与 PPT束；可直接填写接口信息，也可连接 `kk_API配置`。
  - 模板工具位于 `🌟kktools/模板工具`，PPT 工具位于 `🌟kktools/PPT工具`。
- 当前仓库已自带前端扩展目录 [web](web)，无需额外配置即可加载 `provider` / `model` 联动

## 🧭 快速上手

- 在节点面板中搜索 `🌟kktools`、英文类名，或中文名。
- 推荐先打开总览工作流 [workflows/kktools_workflow_node_demo_gallery.json](workflows/kktools_workflow_node_demo_gallery.json)。
- 分模块示例可查看 [workflows/README.md](workflows/README.md)。
- OpenMAIC 独立版课件到视频流程可直接加载 [workflows/OpenMAIC独立版-从课件到视频.workflow.json](workflows/OpenMAIC独立版-从课件到视频.workflow.json)。
- 图像、视频、音频类节点建议先接入你自己的 `IMAGE`、`VIDEO`、`AUDIO` 输入再运行。
- 如果你手里有旧工作流，请留意：
  - 当前全部节点都已切换为 `kk...` 前缀命名
  - 旧工作流里的旧节点名需要重新选择或替换
  - `kkLingsiNativePromptImage` 已移除菜单注册；请使用 `kkGPT-image_API`。
  - 旧工作流如果使用过 `kkVideoTextOCR`，需要手动移除或改用其他文本提取方案

## 📁 项目结构

- [__init__.py](__init__.py)：自动发现与注册节点，统一节点显示名，并导出版本号与前端目录
- [nodes](nodes)：全部节点源码
- [nodes/openmaic](nodes/openmaic)：OpenMAIC 独立版课件导入、讲稿、TTS、字幕和视频导出节点
- [web/kkllm.js](web/kkllm.js)：`kkLLM` / `kkStoryboardScriptLLM` 的模型联动前端脚本
- [web/kk_markdown_upload.js](web/kk_markdown_upload.js)：`kkMarkdown上传` 的文件选择和上传前端脚本
- [web/skills_template_selector.js](web/skills_template_selector.js)：`kkSkills模板选择器` 的卡片选择、搜索、改名和删除界面
- [web/imagen_theme.js](web/imagen_theme.js)：PPT、模板及其他节点分类的主题配色
- [web/runtime_manager.js](web/runtime_manager.js)：顶部运行资源监控与原生运行工具栏吸附交互
- [runtime_manager_routes.py](runtime_manager_routes.py)：本机 CPU、内存、GPU 与显存统计接口
- [workflows](workflows)：总览与分模块示例工作流
- [fonts](fonts)：可选字体资源
- [RELEASE_NOTES_3.5.0.md](RELEASE_NOTES_3.5.0.md)：当前版本更新说明

## 🧩 源码入口

| 模块 | 分类 | 源码 |
|---|---|---|
| 图像 | `🌟kktools/图像` | [image.py](nodes/image.py)、[ImageSplit.py](nodes/ImageSplit.py)、[lingsi.py](nodes/lingsi.py) |
| 数学计算 | `🌟kktools/数学计算` | [Math.py](nodes/Math.py) |
| 提示词 | `🌟kktools/提示词` | [prompts.py](nodes/prompts.py) |
| 尺寸 | `🌟kktools/尺寸` | [size.py](nodes/size.py) |
| 字符串 | `🌟kktools/字符串` | [kkstring.py](nodes/kkstring.py) |
| 随机 | `🌟kktools/随机` | [RandomSelector.py](nodes/RandomSelector.py) |
| 视频 | `🌟kktools/视频` | [video.py](nodes/video.py) |
| 音频 | `🌟kktools/音频` | [audio.py](nodes/audio.py) |
| 分镜 | `🌟kktools/分镜` | [StoryboardScript.py](nodes/StoryboardScript.py) |
| 模板工具 | `🌟kktools/模板工具` | [imagen_studio.py](nodes/imagen_studio.py) |
| PPT 工具 | `🌟kktools/PPT工具` | [imagen_ppt.py](nodes/imagen_ppt.py) |
| 兼容 | `🌟kktools/兼容` | [compat_text.py](nodes/compat_text.py) |
| OpenMAIC | `OpenMAIC/导入`、`OpenMAIC/独立版`、`OpenMAIC/导出`、`OpenMAIC/音频`、`OpenMAIC/工具` | [openmaic_nodes.py](nodes/openmaic_nodes.py)、[openmaic](nodes/openmaic) |

## 🖥️ 运行管理

- 默认显示在 ComfyUI 顶部工具栏，实时查看 CPU、系统内存、GPU 和显存使用情况。
- 每 2 秒自动刷新；点击状态栏可立即刷新。
- GPU 利用率仅在当前计算后端支持读取时显示，其他环境会显示设备类型和显存占用。
- 保留 ComfyUI 原生运行按钮及其拖拽功能；拖动原生工具栏靠近顶部运行管理区域时，会自动吸附到显存信息右侧。
- 所有数据只通过本机 ComfyUI 接口读取，不会发送到外部服务。

## 🎨 分类主题

- 沿用 PPT 工具的深色节点样式，通过标题栏颜色快速区分不同功能分类。
- 图像、数学计算、提示词、尺寸、字符串、随机、视频、音频、分镜和兼容分类均使用独立配色。
- 模板工具、PPT 工具和现有特殊节点保留各自主题；OpenMAIC 的导入、独立版、导出、音频和工具分类也分别配色。
- 主题只改变节点外观，不修改节点输入、输出、执行逻辑或现有工作流兼容性。

## 🧾 全部节点与分类

当前代码共提供 71 个可注册节点标识，分布在 17 个分类中。`OpenMAIC_导入课件独立版` 是 `OpenMAIC_PPTX导入独立版` 的兼容标识，两者使用同一个实现。

| 分类 | 节点标识（界面显示名） |
|---|---|
| `🌟kktools/图像` | `kkImageOverlay`（图像叠加）、`kkPadImageToCanvas`（图像填充到画布）、`kkImageFrame`（图像边框）、`kkResize`（图像蒙版同步调整）、`kkGetImage`（获取图像尺寸）、`kkBatchImageLoader`（批量图像加载）、`kkImageTileSplit2x2`（图像2x2分块）、`kkImageGridMerge`（图像宫格合并）、`kkImageSplit`（图像切割）、`kk_API配置`、`kkGPT-image_API` |
| `🌟kktools/数学计算` | `kkMathExpressionNode`（数学表达式）、`kkRegexNode`（正则表达式）、`kkRegexNodeAdvanced`（正则表达式高级） |
| `🌟kktools/提示词` | `kkBatchPrompt`（批量提示词）、`kkMarkdown上传`、`kkSkills模板选择器`、`kkLLM`（多厂商LLM） |
| `🌟kktools/尺寸` | `kkSizeNode`（尺寸生成） |
| `🌟kktools/字符串` | `kkStringNode`（字符串裁剪）、`kkStringNodeAdvanced`（字符串裁剪高级）、`kkStringMergeNode`（字符串合并）、`kkStringToIntNode`（字符串转整数）、`kkMarkdownToString`（MD转字符串）、`kkInputNode`（多类型输入）、`kkReplaceNode`（字符串替换）、`kkSomethingToAny`（任意类型转换） |
| `🌟kktools/随机` | `kkRandomSelector`（随机选择器） |
| `🌟kktools/视频` | `kkVideoFirstLastFrames`（视频首尾帧提取）、`kkVideoFramesAdvanced`（视频抽帧高级）、`kkVideoDepth`（视频转深度视频）、`kkVideoCompare`（视频对比）、`kkMergeVideos`（视频合并） |
| `🌟kktools/音频` | `kkAudioMerge4`（音频四合一） |
| `🌟kktools/分镜` | `kkStoryboardScript`（默认分镜）、`kkStoryboardScriptLLM`（LLM分镜）、`kkStoryboardShotOutput`（分镜输出） |
| `🌟kktools/模板工具` | `ImagenStudioTemplateDistiller`（模板蒸馏）、`ImagenStudioTemplateIngest`（模板入库）、`ImagenStudioTemplateSelector`（模板选择器）、`ImagenStudioTemplateComposer`（模板拼装）、`ImagenStudioRunningHubRHArtG2`（RunningHub 生图） |
| `🌟kktools/PPT工具` | `ImagenStudioPPTOutlineDraft`（PPT 大纲草拟）、`ImagenStudioPPTOutlinePlan`（PPT 大纲规划）、`ImagenStudioPPTDesignBrief`（PPT 设计规范）、`ImagenStudioPPTPageComposer`（PPT 页面拼装）、`ImagenStudioPPTRunningHubBatch`（PPT RunningHub 批量生图）、`ImagenStudioPPTPipeUnpack`（PPT 束拆包）、`ImagenStudioPPTImageWriteback`（PPT 图像写回）、`ImagenStudioPPTExport`（PPT 导出） |
| `🌟kktools/兼容` | `ShowText\|pysssss`（兼容文本展示）、`CR Text`（兼容文本） |
| `OpenMAIC/导入` | `OpenMAIC_PPTX导入独立版`（📊 PPTX导入（独立版））、`OpenMAIC_导入课件独立版`（同实现兼容标识）、`OpenMAIC_图片导入独立版`（📁 图片导入（独立版）） |
| `OpenMAIC/独立版` | `OpenMAICStandaloneImportCourseware`（OpenMAIC 独立导入课件）、`OpenMAICStandaloneGenerateScript`（OpenMAIC 独立生成讲稿）、`OpenMAICStandaloneBatchTTS`（OpenMAIC 独立批量TTS）、`OpenMAICStandaloneTTSAdapter`（OpenMAIC TTS文本转接器）、`OpenMAICStandaloneCollectTTSAudio`（OpenMAIC 收集TTS音频）、`OpenMAICStandaloneExportVideo`（OpenMAIC 独立导出课件视频） |
| `OpenMAIC/导出` | `OpenMAIC_视频导出`（📹 视频导出）、`OpenMAIC_导出设置`（⚙️ 导出设置） |
| `OpenMAIC/音频` | `OpenMAIC_TTS设置`（🎙️ TTS 设置）、`OpenMAIC_文本转语音`（🔊 文本转语音）、`OpenMAIC_音频混音`（🎵 音频混音）、`OpenMAIC_字幕生成`（📝 字幕生成）、`OpenMAIC_FunASR字幕对齐`（🎙️ FunASR字幕对齐）、`OpenMAIC_简单字幕对齐`（📋 简单字幕对齐） |
| `OpenMAIC/工具` | `OpenMAIC_拆分讲解列表`（🔢 拆分讲解列表）、`OpenMAIC_从动作提取字幕`（🎬 字幕时间点提取） |

### 已停用节点

- `kkimage2_GAPI`、`kkLingsiNativePromptImage` 和 `kkImageAPI` 已从菜单注册中停用，不计入上述 71 个现役节点标识。

---

## 🖼️ 图像模块

源码位置：[nodes/image.py](nodes/image.py) 、[nodes/ImageSplit.py](nodes/ImageSplit.py)、[nodes/lingsi.py](nodes/lingsi.py)、[nodes/kkimage2_gapi.py](nodes/kkimage2_gapi.py)

### kkImageOverlay（图像叠加）

- 将 `image2` 叠加到 `image1` 上，输出尺寸保持为 `image1` 的尺寸。
- 支持位置：`左上`、`左中`、`左下`、`居中`、`上中`、`下中`、`右上`、`右中`、`右下`。
- 支持 `margin_x`、`margin_y` 设置水平和垂直边距；居中位置下作为偏移量使用。
- 支持 `image2` 自带 alpha 透明通道，也可接入透明 PNG 的 `mask` 作为叠加透明通道。
- 输入批次数不一致时，会复用较短输入的最后一张图。
- 输出：`IMAGE`

### kkPadImageToCanvas（图像填充到画布）

- 将输入图像放置到指定尺寸的新画布中，支持纯色背景、透明背景、居中或自定义偏移。
- 常用参数：`width`、`height`、`fill_color`、`center`、`left_padding`、`top_padding`
- 适合做统一分辨率、补边、加留白和图像位置微调。
- 输出：`IMAGE`

### kkImageFrame（图像边框）

- 将 1 到 3 张图像排版成对比图，支持横排、竖排、网格、边框、底部文字说明。
- 常用参数：`image_count`、`mode`、`footer_height`、`font_size`、`border_thickness`、`font_selection`
- 适合做前后对比、模型效果对比、版本对比图。
- 输出：`IMAGE`

### kkResize（图像蒙版同步调整）

- 同时调整图像和对应蒙版尺寸，保证两者始终对齐。
- 支持 `stretch`、`scale_width`、`scale_height`、`scale_long`、`scale_short`、`fit_padding`、`fill_crop`
- 支持 `nearest`、`bilinear`、`bicubic`、`lanczos`
- 输出：`IMAGE`、`MASK`

### kkGetImage（获取图像尺寸）

- 读取输入图像的宽高，并自动匹配最接近的常用比例：`16:9`、`9:16`、`1:1`、`3:2`、`2:3`、`3:4`、`4:3`、`21:9`。
- 适合把图像尺寸继续传给后续节点做动态计算。
- 输出：`width`、`height`、`ratio`

### kkBatchImageLoader（批量图像加载）

- 从目录批量读取图像，支持顺序、倒序、随机读取，也支持分批次取图。
- 常用参数：`directory`、`load_order`、`load_interval`、`start_index`、`max_images`、`file_extensions`、`seed`、`batch_index`
- 适合批量测试、批量预处理、数据集抽样。
- 输出：`images`、`masks`、`loaded_count`、`file_info`

### kkImageTileSplit2x2（图像2x2分块）

- 将一张图切成 2x2 四块，支持分块重叠和输出顺序控制。
- 常用参数：`overlap_pixels`、`output_order`
- 适合大图分块生成、局部细化、拼图处理。
- 遇到奇数尺寸或 batch 内分块尺寸不一致时，会自动 padding 到统一尺寸，避免张量拼接错误。
- 输出：左上、右上、左下、右下四张图

### kkImageGridMerge（图像宫格合并）

- 将多张输入图像按 `2x2`、`3x3`、`4x4` 合并为宫格，是 `kkImageSplit` / `kkImageTileSplit2x2` 的反向拼接工具。
- 输入顺序：按行优先排列，`image1` 从左上开始，依次向右、再换到下一行。
- `2x2` 使用前 4 张图，`3x3` 使用前 9 张图，`4x4` 使用前 16 张图；未接入的可选格子会用背景色填充。
- 常用参数：`grid_size`、`cell_size_mode`、`background_color`
- `cell_size_mode` 支持 `match_image1`、`max`、`min`，用于在多张图尺寸不一致时统一单元格尺寸。
- 输出 batch 前会再次统一画布尺寸，可兼容上游切图产生的 313/315 这类边缘尺寸差异。
- 输出：`IMAGE`

### kkImageSplit（图像切割）

- 按网格切割一张图，支持 `2x2`、`3x3`、`4x4`、横竖切分和自定义网格。
- 支持 `row-major`、`column-major`、`diagonal` 三种输出顺序，并可设置分块重叠。
- 遇到奇数尺寸或分块尺寸不一致时，会自动 padding 到统一尺寸，方便继续接入宫格合并或批处理节点。
- 输出 `merged_tiles` 以及最多 16 个 `tile_xx` 子图，适合大图切块工作流。

### kk_API配置

- 输入：`Base URL`、`API Key`。
- 输出：单一 `API配置` 束，可复用到多个 `kkGPT-image_API` 或 `kkLLM` 节点。
- 连接配置束后，下游节点优先使用束内地址和密钥；未连接时仍可在下游节点内直接填写。
- API Key 会保存在工作流节点数据中，分享工作流前请先清空密钥。

### kkGPT-image_API

- 基于灵思 MindAPI 兼容路由的原生 Prompt 生图节点，支持纯文生图和可选参考图图生图。
- 可选的 `API配置` 输入用于连接 `kk_API配置`，配置束中的 Base URL 和 API Key 优先于节点内直接填写的值。
- 支持 `gpt-image-2.5-sunburst`、`gpt-image-2.5-flare`、`gpt-image-2`、`nano-banana-2`、`nano-banana-pro`，可设置比例、分辨率、质量和生成数量。
- 常用参数：`api_key`、`prompt`、`model`、`aspect_ratio`、`resolution`、`quality`、`count`、`base_url`
- `quality` 支持 `auto / low / medium / high / xhigh / max`，默认 `high`；`xhigh` 和 `max` 仅用于 GPT Image 2.5。GPT Image 的文生图、参考图编辑和 PPT 批量模式都会传给接口。
- `base_url` 默认是 `https://mindapi.cc`；填第三方兼容站点时，节点仍会自动使用当前固定路由。
- 可选的 `ratio` 字符串输入可连接 `kkSizeNode.ratio`，连接后会覆盖 `aspect_ratio` 下拉框；传入比例仍须属于生图节点支持的比例列表。
- 可选输入：默认只有 `image`；连接后自动显示下一个，最多 `image_1` 至 `image_8`（共 9 张）。断开尾部连接后多余输入会自动收起；不同尺寸图片会按第一张图片尺寸统一后再合并。
- 不接参考图时为文生图；接入任意参考图时为多图参考生图。
- `raw_json` 会输出请求摘要、响应解析、图片候选信息和错误排查信息，便于定位接口返回异常。
- 输出：`IMAGE`、`raw_json`、`PPT束`、`日志`。内容审核失败时，日志会提示修改提示词或上传参考图像。

### kkimage2_GAPI（已停用）

- 源码仍保留，但已从菜单注册中停用，不属于当前可用节点。
- 现有工作流请改用 `kkGPT-image_API`。

## 🔢 数学模块

源码位置：[nodes/Math.py](nodes/Math.py)

### kkMathExpressionNode（数学表达式）

- 用表达式做数值计算，支持变量 `a b c d` 以及同义变量 `x y z w`。
- 内置常见数学函数、比较函数、常量，适合尺寸计算、步数换算、流程控制前的数值预处理。
- 输出：浮点结果、整数结果、字符串结果

### kkRegexNode（正则表达式）

- 对字符串执行正则匹配和替换。
- 支持模式：`match`、`search`、`findall`、`replace`
- 适合从文本中抽取片段、提取标记、批量替换关键词。
- 输出：`STRING`

### kkRegexNodeAdvanced（正则表达式高级）

- 在基础正则节点上增加了标志位和详细结果输出。
- 支持 `IGNORECASE`、`MULTILINE`、`DOTALL`
- 输出：结果文本、匹配数量、匹配内容、附加信息
- 适合做更可控的文本筛选、日志分析、格式化处理。

---

## 💬 提示词模块

源码位置：[nodes/prompts.py](nodes/prompts.py)

### kkBatchPrompt（批量提示词）

- 从单文件或目录读取提示词，按批次输出。
- 支持 `.txt` 和 `.json`
- 常用参数：`prompt_file`、`file_mode`、`batch_size`、`current_batch`
- 输出：当前批次提示词、批次索引、总批次数、文件信息

### kkMarkdown上传

- 三种来源必须三选一：上传单个 `.md`、读取 ComfyUI 输入目录内的文件夹，或上传 `.zip` 压缩包；同时填写多个来源会直接报错。
- 可选填写 `Tag`，会作为第二个 `Tag` 字符串输出，可直接连接 `kkSkills模板选择器.Tag`。
- 文件夹和 ZIP 会递归收集最多 100 个 `.md`；单个 Markdown 最大 5 MB，ZIP 及其中 Markdown 的总大小最大 50 MB。
- Markdown 必须采用 UTF-8 编码；ZIP 内容直接读取，不会解压到文件系统。
- 文件保存在 ComfyUI 输入目录的 `kktools_markdown` 子目录；上传和读取阶段都会校验扩展名与目录边界。
- 输出：单一 `Markdown文件` 束；多文件连接 `kkSkills模板选择器` 后会逐个保存为 Skill，连接 `kkLLM` 时会合并为一份输入文本。

### kkSkills模板选择器

- 可选输入 `Markdown文件` 用于连接 `kkMarkdown上传`；每次执行都会把 Markdown 内容保存或更新到本地 Skills 模板库。
- 可选输入 `Tag` 为 Skill 写入分类标签；标签会保存到模板库、显示在卡片上，并支持搜索。
- 可选输入 `封面图` 会保存为 Skill 卡片封面；图片自动缩放到最长边 512 像素并保存为 JPEG。
- 不连接 Markdown 时，可从节点内的卡片选择已有 Skill 并输出。
- 卡片界面支持搜索、刷新、重命名和删除；相同 Markdown 内容会更新原记录，不会重复入库。
- 支持导入和导出 `kktools-skills-package.zip`；模板包会保留名称、Markdown 与封面，并限制文件数、单文件大小和解压后总大小。
- 输出：`Markdown文件`、`Skill名称`、`状态`。Markdown 主内容是当前选中的 Skill，同时在 `items` 中携带整个模板库，可连接 `kkLLM`，也可交给 `kkRandomSelector` 随机抽取。
- 模板库保存在 ComfyUI 用户目录的 `user/kktools/skills-templates`，也可通过环境变量 `KKTOOLS_SKILLS_DIR` 指定其他本地目录；数据不再写入插件源码目录。

### kkLLM（多厂商LLM）

- 使用 LLM 优化提示词，当前支持 DeepSeek V4、OpenAI GPT-5.6、Gemini 3.x/2.5 和豆包 Seed 2.0/1.6。
- `Markdown文件` 接入后，Markdown 全文会覆盖手动填写的 `base_prompt`，此时 `base_prompt` 可以留空。
- 切换 `provider` 时，前端会自动刷新对应的 `model` 选项。
- 支持 `base_prompt`、`provider`、`model`、`custom_model`、`base_url`、`system_message`、`max_length`、`temperature`，并可接入 `Markdown文件` 与 `API配置`。
- 可选的 `API配置` 输入可连接 `kk_API配置`；连接后优先使用配置束中的 API Key，并将 Base URL 转换为兼容的 `/v1/chat/completions` 地址。
- 没填 `api_key` 时会直接返回原始提示词，不会中断工作流；请求失败、额度不足或网络异常时会退回本地优化方案。
- 输出顺序：`original_prompt`、`optimized_prompt`、`optimization_info`。

---

## 📐 尺寸模块

源码位置：[nodes/size.py](nodes/size.py)

### kkSizeNode（尺寸生成）

- 生成指定尺寸的 latent，同时输出最终宽高和比例。
- 支持 `preset` 和 `custom` 两种模式，预设尺寸针对 SDXL 做了优化。
- 所有尺寸会自动校正为 8 的倍数。
- 输出：`LATENT`、`width`、`height`、`ratio`

---

## 📝 字符串模块

源码位置：[nodes/kkstring.py](nodes/kkstring.py)

### kkStringNode（字符串裁剪）

- 按字符数裁掉文本开头和结尾。
- 常用参数：`skip_start`、`skip_end`
- 输出：裁剪后的字符串

### kkStringNodeAdvanced（字符串裁剪高级）

- 在基础裁剪之外，额外输出原始长度、裁剪后长度和移除字符数。
- 适合做文本调试、规则清洗、批处理结果检查。
- 输出：裁剪后的字符串、原始长度、裁剪后长度、移除字符数

### kkStringMergeNode（字符串合并）

- 将 2 到 4 个字符串按顺序拼接，可选分隔符。
- 常用参数：`string1`、`string2`、`string3`、`string4`、`separator`
- 输出：合并后的字符串

### kkInputNode（多类型输入）

- 提供两组手动输入槽，每组可在 `STRING`、`INT`、`FLOAT` 之间切换。
- 每组都会同时输出三种格式，方便做测试、占位输入、参数注入。
- 输出：两组 `string/int/float`

### kkReplaceNode（字符串替换）

- 对输入文本执行字符串替换。
- 支持只替换第一个匹配项，或替换全部匹配项。
- 输出：替换后的字符串、替换次数

### kkSomethingToAny（任意类型转换）

- 在 `STRING`、`INT`、`FLOAT`、`BOOLEAN` 之间做基础转换，并统一输出字符串、整数、浮点数三种结果。
- 适合做节点之间的类型桥接，减少临时转换逻辑。
- 输出：`string_output`、`int_output`、`float_output`

### kkStringToIntNode（字符串转整数）

- 接收 `string1`、`string2`、`string3`、`string4` 四个字符串输入。
- 当前逻辑不会解析字符串内容，而是固定输出 `1`、`2`、`3`、`4`。
- 适合做固定占位、演示或兼容某些固定输入场景。

### kkMarkdownToString（MD 转 String）

- 接收 `kkMarkdown上传` 输出的 `Markdown文件`。
- 输出 Markdown 文件全文的标准 `STRING`，方便连接普通字符串节点。

---

## 🎲 随机模块

源码位置：[nodes/RandomSelector.py](nodes/RandomSelector.py)

### kkRandomSelector（随机选择器）

- 从 JSON 配置的多组候选项中随机选择一个值。
- 支持用 `target_groups` 限定候选组，用 `seed` 保证可复现。
- 可选连接 `kkMarkdown上传` 的 `Markdown文件`；输入包含多个 Markdown 文件时，会按 `seed` 随机选择一个文件，且无需解析 JSON 候选项。
- 连接 `kkSkills模板选择器` 时，以整个 Skills 模板库作为随机候选集合；改变 `seed` 可选择不同 Skill。
- 输出：选中的值或 Markdown 内容、选中的组名、全部组名或文件名列表、选中的 `Markdown文件`

---

## 🎬 视频模块

源码位置：[nodes/video.py](nodes/video.py)

### kkVideoFirstLastFrames（视频首尾帧提取）

- 从 `VIDEO` 输入中提取首帧、尾帧和一个仅含首尾两帧的新图像批次。
- 同时把原视频音频直接透传出来。
- 输出：`first_frame`、`last_frame`、`first_last_frames`、`audio`

### kkVideoFramesAdvanced（视频抽帧高级）

- 支持两种抽帧方式：
  - `every_frame`：输出全部帧
  - `interval_seconds`：按秒间隔抽帧
- 输出：图像批次、FPS、抽取帧数、说明信息
- 适合做视频分析、关键帧提取、视频转图像序列。

### kkVideoDepth（视频转深度视频）

- 使用 ComfyUI 内置的 Depth Anything 3 对输入 `VIDEO` 逐帧估算深度，并输出保持原分辨率和 FPS 的新 `VIDEO`。
- `da3_model` 连接官方 `Load Depth Anything 3` 节点；推荐使用 ComfyUI 官方蓝图采用的 `depth_anything_3_mono_large.safetensors`。
- 模型官方下载：[Comfy-Org 模型页面](https://huggingface.co/Comfy-Org/Depth-Anything-3/blob/main/geometry_estimation/depth_anything_3_mono_large.safetensors)；[直接下载模型](https://huggingface.co/Comfy-Org/Depth-Anything-3/resolve/main/geometry_estimation/depth_anything_3_mono_large.safetensors)。
- 模型大小约 1.34 GB，SHA256：`9b44eda5bedba5b4e125686fdb79d1db309c1b9785277576eb930f885b008f96`。下载后放入 ComfyUI 的 `models/geometry_estimation` 目录并刷新模型列表。
- `resolution` 控制模型处理分辨率；较低数值速度更快、显存占用更低，较高数值可保留更多细节。
- `output_mode` 支持灰度深度视频和 Turbo 彩色深度视频，`normalization` 支持 `v2_style` 与 `min_max`。
- `keep_audio` 默认开启，输出视频会保留输入视频的原始音轨；关闭后输出无音频深度视频。
- 输出：`depth_video`

### kkVideoCompare（视频对比）

- 输入 `video1` 和 `video2`，节点内直接输出左右并排的同步视频预览：左侧为视频 1，右侧为视频 2。
- 两路画面合成为一个标准视频流，因此共用同一个播放、暂停和进度拖拽控件，不会出现两个播放器进度不同步的问题。
- 自动使用两路视频中较低的 FPS，并以较短视频的结束时间作为对比时长；画面按较小高度等比例缩放，避免拉伸变形。
- 支持可选 `audio` 输入；连接后使用外部音频，未连接时默认使用 `video1` 的原始音轨。
- 输出可继续连接原生 `SaveVideo` 保存。
- 输出：`comparison_video`

### kkMergeVideos（视频合并）

- 将最多 5 路 `VIDEO` 顺序拼接成一个新视频。
- 支持保持原始分辨率，或参考某一路视频尺寸/FPS，或手动自定义尺寸与 FPS。
- 如果没有额外接入 `audio`，会自动把每段视频自带音频顺序拼接进去；没有音轨的片段会自动补静音。
- 如果接入了外部 `audio`，则以外部音频为输出音轨。
- 输出：`VIDEO`

---

## 🔊 音频模块

源码位置：[nodes/audio.py](nodes/audio.py)

### kkAudioMerge4（音频四合一）

- 将最多 4 路 `AUDIO` 按顺序拼接成 1 路输出。
- 会自动对齐 batch 和声道；当采样率不同且环境中安装了 `torchaudio` 时，会自动重采样。
- 适合配音片段拼接、音频段落合并、批量音轨串联。
- 输出：`AUDIO`

---

## 模板工具（🌟kktools/模板工具）

模板工具使用统一的 `IMAGEN_STUDIO_PIPE` 模板束传递模板内容、提示词和生成结果。

### ImagenStudioTemplateDistiller（模板蒸馏）

- 分析一张或多张参考图，提取可复用的视觉风格、负面提示词和结构化视觉特征。
- 主要输入：`参考图像`、`模板类型`、`模板名称`、`模板需求`、`BaseURL`、`API Key`、`最长边`。
- 输出：`模板束`、`模板JSON`、中英文风格提示词、负面提示词、视觉特征 JSON。

### ImagenStudioTemplateIngest（模板入库）

- 把模板束保存到本地模板库，可选择是否覆盖同名模板，并可用 `缩略图` 配置卡片封面。
- 输出：更新后的 `模板束`、`模板ID`、`模板名称`、`保存路径`。

### ImagenStudioTemplateSelector（模板选择器）

- 通过卡片浏览本地模板库，支持搜索、缩略图、改名和删除。
- 输出选中模板的 `模板束`、模板 JSON、中英文风格提示词、负面提示词和模板名称。

### ImagenStudioTemplateComposer（模板拼装）

- 把模板束、用户需求、画面比例、提示词语言及可选参考图拼装为最终生图提示词。
- 输出：写入拼装结果的 `模板束`、正向提示词、负面提示词、拼装说明和拼装 JSON。

### ImagenStudioRunningHubRHArtG2（RunningHub 生图）

- 读取模板束内提示词或手动提示词，调用 RunningHub RHArt G2；有参考图时自动进入图生图模式。
- 支持渠道、比例、分辨率和 `low / medium / high` 质量设置。
- 输出：`图像`、更新后的 `模板束`、结果 URL、任务 ID、结果 JSON。

### 配置位置

Imagen Studio 在 kktools 内使用独立运行目录：

```text
ComfyUI/custom_nodes/comfyui-kktools/imagen-studio/config.json
ComfyUI/custom_nodes/comfyui-kktools/imagen-studio/templates/
```

可从 `imagen-studio/config.example.json` 复制出 `config.json`，填写：

- `apiKey / baseUrl / visionModel / textModel`
- `runninghubApiKey / runninghubBaseUrl`

真实 `config.json` 和 `templates/` 已加入 `.gitignore`，不会提交到仓库。

### RunningHub

`RunningHub 生图` 支持：

- 渠道：`第三方低价渠道 / 官方渠道`
- 文生图：不连接 `参考图像`
- 图生图：连接 `参考图像`
- 质量：`low / medium / high`

RunningHub 提交会始终发送 `quality` 字段，避免接口返回 `field 'quality' is required`。

示例工作流：

```text
workflows/kktools_imagen_studio_template_pipe_runninghub.workflow.json
workflows/kktools_imagen_studio_template_pipe_runninghub.api.json
```

---

## PPT 工具（🌟kktools/PPT工具）

PPT 节点使用统一的 `IMAGEN_STUDIO_PIPE` 束传递模板信息、页面计划、提示词、生成结果和导出信息。

### ImagenStudioPPTOutlineDraft（PPT 大纲草拟）

- 根据用户想法、已有 Markdown 大纲和可选模板束生成或润色 PPT 大纲。
- 输出：`大纲Markdown`、`草拟说明`。

### ImagenStudioPPTOutlinePlan（PPT 大纲规划）

- 将 Markdown 大纲拆分成页面计划，并设置画面比例、提示词语言和目标模型。
- 输出：`PPT束`、`页面计划JSON`、`PPT标题`。

### ImagenStudioPPTDesignBrief（PPT 设计规范）

- 根据 PPT 束和可选参考图建立整套演示文稿统一的视觉规范。
- 输出：更新后的 `PPT束`、`设计规范JSON`、`参考图分析JSON`。

### ImagenStudioPPTPageComposer（PPT 页面拼装）

- 并发为每一页生成生图提示词；支持单页超时和 1–50 并发。
- 输出：更新后的 `PPT束`、`Prompt列表JSON`、`页面JSON`。

### ImagenStudioPPTRunningHubBatch（PPT RunningHub 批量生图）

- 并发调用 RunningHub 生成全部页面，可配置渠道、分辨率、质量、单页超时和轮询间隔。
- 输出：页面 `图像` 批次、写入结果的 `PPT束`、`结果JSON`。

### ImagenStudioPPTPipeUnpack（PPT 束拆包）

- 按页或合并全部页面，从 PPT 束中拆出普通字符串提示词，便于连接任意生图节点。
- 输出：`PPT束`、正负提示词、页面标题、页面 JSON、总页数和当前页码。

### ImagenStudioPPTImageWriteback（PPT 图像写回）

- 将外部生图结果写回 PPT 束中的指定页。
- 输出：更新后的 `PPT束`、`写回JSON`。

### ImagenStudioPPTExport（PPT 导出）

- 使用束内图片路径、URL 或可选图像批次导出图片型 PPTX。
- 输出：`PPT文件路径`、`导出JSON`；默认保存到 ComfyUI 输出目录的 `imagen-ppt` 子目录。

它们复用现有的 模板库、配置文件和 RunningHub 接口，不依赖原项目的 PPT 工作台页面或 deck 历史。

这种束化方式参考 EasyUse 的统一 pipe 思路：能连线代表类型兼容，节点运行时仍会检查自己需要的字段；比如 PPT 设计节点需要先有页面计划，缺字段时会给中文错误提示。

`PPT 页面拼装` 支持并发调用 LLM 拼装每页 prompt，`并发数` 默认 20、最大 50，输出仍按 PPT 页序排列。

`kkGPT-image_API` 可以直接连接 `PPT束`，一次性并发生成所有页面并把图片路径写回束内；`并发数` 默认 3、最大 20。遇到 429 限流会自动重试，默认重试 6 次，基础等待 15 秒并指数退避，单次等待最多 500 秒。生成后把 `kkGPT-image_API.PPT束` 接到 `PPT 导出.PPT束` 即可导出 PPTX。

`PPT RunningHub 批量生图` 仍可作为 RunningHub 渠道使用，支持并发提交页面任务，`并发数` 默认 50、最大 100；同时保留 `单页超时分钟`、`轮询间隔秒` 参数。

`PPT 页面拼装`、`kkGPT-image_API` 的 PPT 批量模式和 `PPT RunningHub 批量生图` 会在节点内部显示运行状态条，包括当前页、阶段、完成数和失败提示；更详细的排队、轮询、兜底信息会同步打印到 ComfyUI 控制台。页面拼装还提供 `单页超时秒`，默认 180 秒。

单页调试时，也可以使用 `PPT 束拆包` 把指定页的 `正向提示词` 拆成普通 `STRING`，再连接到 `kkGPT-image_API.prompt`。拆包节点会额外输出 `当前页码`，可直接连接到 `PPT 图像写回.页码`，这样拆第几页就会自动写回第几页。

```text
PPT 页面拼装.PPT束 -> PPT 束拆包.PPT束
PPT 束拆包.正向提示词 -> kkGPT-image_API.prompt
kkGPT-image_API.image -> PPT 图像写回.图像
PPT 束拆包.PPT束 -> PPT 图像写回.PPT束
PPT 束拆包.当前页码 -> PPT 图像写回.页码
PPT 图像写回.PPT束 -> PPT 导出.PPT束
```

推荐导出连线：`kkGPT-image_API.PPT束 -> PPT 导出.PPT束`。`PPT 导出` 会从束里的页面图片路径或 URL 生成 PPTX；`图像` 输入只作为高级备用入口，默认示例不再连接它。

PPTX 默认保存到 ComfyUI 输出目录下的 `output/imagen-ppt/`，节点右侧 `PPT文件路径` 会返回完整文件路径。

示例工作流：

```text
workflows/kktools_imagen_studio_ppt_pipe.workflow.json
```

---

## 🎞️ 分镜模块

源码位置：[nodes/StoryboardScript.py](nodes/StoryboardScript.py)

### kkStoryboardScript（默认分镜）

- 使用本地规则把一段描述文本转成分镜脚本。
- 支持 `max_shots`（最大镜头数，1-30）、`include_audio`（是否包含音频）、`seconds_per_shot`（每个分镜时长）。
- 支持固定时长或随机时长两种节奏：
  - 固定时长：设置 `seconds_per_shot`，所有镜头使用相同时长
  - 随机时长：开启 `enable_random_duration`，设置 `min_shot_duration` 和 `max_shot_duration`，每个镜头时长在范围内随机
- 输出格式：
  ```
  镜头1（0-4秒）
  画面：...
  音效：...
  台词：（人物，语气）"..."
  字幕：...
  ```
- 输出：分镜文本、结构化镜头列表

### kkStoryboardScriptLLM（LLM分镜）

- 使用 LLM 生成分镜脚本，支持 DeepSeek、OpenAI、Gemini、豆包。
- 支持参数：`api_key`、`provider`、`model`、`max_shots`（1-30）、`include_audio`、`seconds_per_shot`、`enable_random_duration`、`min_shot_duration`、`max_shot_duration`、`system_prompt`
- 需要填写有效 `api_key`；生成失败时会返回错误文本和空镜头列表，方便在工作流中继续排查。
- 适合复杂剧情、风格化分镜、需要更强理解能力的文本转镜头任务。
- 输出格式与默认分镜一致，包含画面、音效、台词、字幕字段。
- 输出：分镜文本、结构化镜头列表

### kkStoryboardShotOutput（分镜输出）

- 从分镜节点生成的 `shot_list` 中取出指定镜头，并格式化输出。
- 支持四种输出格式：
  - `完整`：带边框的详细格式
  - `简洁`：精简的一行格式
  - `纯文本`：仅输出画面描述
  - `分镜`：标准分镜格式（推荐）
- 支持 `auto_next`：自动切换到下一个镜头/下一组
- 支持 `group_size`：分组输出，每 N 个分镜为一组同时输出
- 可用于逐镜头推进工作流、逐条喂给后续图像或视频节点。
- 输出：镜头文本、当前索引、总镜头数

---

## 🎓 OpenMAIC 课件视频模块

源码位置：[nodes/openmaic](nodes/openmaic)、[nodes/openmaic_nodes.py](nodes/openmaic_nodes.py)。详细依赖与工作流说明见 [nodes/openmaic/README.md](nodes/openmaic/README.md)。

### OpenMAIC_PPTX导入独立版（📊 PPTX导入（独立版））

- 分类：`OpenMAIC/导入`。
- 解析 PPTX 课件并输出课件数据、匹配结果、动作列表和页面数量。

### OpenMAIC_导入课件独立版（兼容标识）

- 分类：`OpenMAIC/导入`。
- 指向 `OpenMAIC_PPTX导入独立版` 的同一个实现，用于兼容已有工作流。

### OpenMAIC_图片导入独立版（📁 图片导入（独立版））

- 分类：`OpenMAIC/导入`。
- 把图片目录作为课件页面导入，输出结构与 PPTX 导入节点一致。

### OpenMAICStandaloneImportCourseware（OpenMAIC 独立导入课件）

- 分类：`OpenMAIC/独立版`。
- 接收 PPTX、PDF 或图片目录，生成页面图片、页面文本和课件数据。
- 输出：课件数据、页面图片 JSON、图片目录、页面文本 JSON、页数。

### OpenMAICStandaloneGenerateScript（OpenMAIC 独立生成讲稿）

- 分类：`OpenMAIC/独立版`。
- 根据课件数据生成逐页或分段讲稿，支持保留原文、口语化和教学化。
- 输出：分段讲稿 JSON、完整讲稿、段数。

### OpenMAICStandaloneBatchTTS（OpenMAIC 独立批量TTS）

- 分类：`OpenMAIC/独立版`。
- 批量将分段讲稿转为语音并合并。
- 输出：音频清单、合并音频、音频片段 JSON、数量。

### OpenMAICStandaloneTTSAdapter（OpenMAIC TTS文本转接器）

- 分类：`OpenMAIC/独立版`。
- 把分段讲稿拆成可连接外部 TTS 的文本任务。
- 输出：TTS 文本、任务 JSON、任务数量。

### OpenMAICStandaloneCollectTTSAudio（OpenMAIC 收集TTS音频）

- 分类：`OpenMAIC/独立版`。
- 收集外部 TTS 返回的音频并恢复为课件音频清单。
- 输出：合并音频及音频片段信息。

### OpenMAICStandaloneExportVideo（OpenMAIC 独立导出课件视频）

- 分类：`OpenMAIC/独立版`。
- 将页图、逐页音频、字幕和 BGM 合成为课件视频。
- 输出：视频路径、视频清单 JSON。

### OpenMAIC_视频导出（📹 视频导出）

- 分类：`OpenMAIC/导出`。
- 合并视频画面、讲解音频、字幕与 BGM。
- 输出：视频路径、音频路径。

### OpenMAIC_导出设置（⚙️ 导出设置）

- 分类：`OpenMAIC/导出`。
- 生成分辨率、帧率、编码器、字幕、BGM 和音量配置束。

### OpenMAIC_TTS设置（🎙️ TTS 设置）

- 分类：`OpenMAIC/音频`。
- 集中生成 TTS 厂商、接口、声音、语速等配置束。

### OpenMAIC_文本转语音（🔊 文本转语音）

- 分类：`OpenMAIC/音频`。
- 读取文本和 TTS 配置生成语音文件。
- 输出：音频文件路径、音频片段信息。

### OpenMAIC_音频混音（🎵 音频混音）

- 分类：`OpenMAIC/音频`。
- 混合讲解音频与背景音乐。
- 输出：混音文件、时长。

### OpenMAIC_字幕生成（📝 字幕生成）

- 分类：`OpenMAIC/音频`。
- 根据字幕时间点生成 ASS 字幕文件。

### OpenMAIC_FunASR字幕对齐（🎙️ FunASR字幕对齐）

- 分类：`OpenMAIC/音频`。
- 使用 ASR 时间戳对齐讲稿与音频，需额外安装 FunASR。
- 输出：字幕时间点、对齐统计。

### OpenMAIC_简单字幕对齐（📋 简单字幕对齐）

- 分类：`OpenMAIC/音频`。
- 不依赖 ASR，按音频时长估算字幕时间点。

### OpenMAIC_拆分讲解列表（🔢 拆分讲解列表）

- 分类：`OpenMAIC/工具`。
- 按索引从讲解列表取出单条讲解。
- 输出：单条讲解、当前索引、总数。

### OpenMAIC_从动作提取字幕（🎬 字幕时间点提取）

- 分类：`OpenMAIC/工具`。
- 从动作列表提取可供字幕生成节点使用的时间轴。

## 🔌 兼容文本节点

源码位置：[nodes/compat_text.py](nodes/compat_text.py)

### ShowText|pysssss（兼容文本展示）

- 分类：`🌟kktools/兼容`。
- 在未安装原扩展时接收并展示字符串，帮助旧工作流正常加载。

### CR Text（兼容文本）

- 分类：`🌟kktools/兼容`。
- 提供旧工作流需要的基础字符串输入与透传。

- 这两个节点是兼容入口，不建议在新工作流中主动使用；安装对应原扩展后应优先使用原节点。

---

## 🎯 工作流示例

### 节点总览工作流

- [workflows/kktools_workflow_node_demo_gallery.json](workflows/kktools_workflow_node_demo_gallery.json)
- 用于快速浏览当前节点能力
- 每个节点都配有最小演示和说明卡

### 模块工作流

- 图像：[workflows/kktools_workflow_image_examples.json](workflows/kktools_workflow_image_examples.json)
- 数学：[workflows/kktools_workflow_math_examples.json](workflows/kktools_workflow_math_examples.json)
- 提示词：[workflows/kktools_workflow_prompts_examples.json](workflows/kktools_workflow_prompts_examples.json)
- 尺寸：[workflows/kktools_workflow_size_examples.json](workflows/kktools_workflow_size_examples.json)
- 字符串：[workflows/kktools_workflow_string_examples.json](workflows/kktools_workflow_string_examples.json)
- 随机：[workflows/kktools_workflow_random_examples.json](workflows/kktools_workflow_random_examples.json)
- 视频：[workflows/kktools_workflow_video_examples.json](workflows/kktools_workflow_video_examples.json)
- 音频：[workflows/kktools_workflow_audio_examples.json](workflows/kktools_workflow_audio_examples.json)
- 分镜：[workflows/kktools_workflow_storyboard_examples.json](workflows/kktools_workflow_storyboard_examples.json)

### 工作流索引

- [workflows/README.md](workflows/README.md)
- 用于快速查看每个工作流文件的用途和适用场景

---

## ⚠️ 使用说明

- 字体问题：`kkImageFrame` 需要可用字体，中文建议放到 [fonts](fonts) 目录。
- 提示词 API：`kkLLM` 未填写 `api_key` 时会返回原始提示词；请求失败时会自动退回本地优化结果。
- Markdown 上传：MD 文件、文件夹地址、ZIP 压缩包必须三选一；只接受 UTF-8 编码、最大 5 MB 的 `.md` 文件；上传按钮未出现时请重启 ComfyUI 并强制刷新浏览器页面。
- 分镜 API：`kkStoryboardScriptLLM` 需要有效 `api_key`，不会像 `kkLLM` 一样自动切回本地分镜生成。
- 图像 API：`kkGPT-image_API` 需要有效接口 Key；接口异常时会在 `raw_json` 中提供排查信息。
- 旧工作流兼容：如果旧工作流使用过 `InputNode` 或 `RegexNode`，请改为 `kkInputNode` 和 `kkRegexNode`。
- 音频采样率：`kkAudioMerge4` 遇到不同采样率时建议安装 `torchaudio`。
- 图像切分与合并：`kkImageTileSplit2x2`、`kkImageSplit`、`kkImageGridMerge` 会在输出 batch 前统一尺寸，减少奇数分辨率导致的 `Sizes of tensors must match` 错误。
- 节点未显示：重启 ComfyUI，并检查日志里是否出现 “🌟kktools Nodes 加载完成” 以及节点注册数量。

## 📄 版本与版权

- 当前版本：3.5.0（见 [__init__.py](__init__.py)）
- 更新说明：[RELEASE_NOTES_3.5.0.md](RELEASE_NOTES_3.5.0.md)
- 作者：kktools
- 共创：KK HL
- 仅用于学习与研究，请遵循 ComfyUI 与相关依赖的许可证要求。
