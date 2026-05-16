# ComfyUI kktools 节点包使用说明

欢迎合作交流微信【kkcomfy】  
共创：KK HL

## 📋 概述

kktools 是一组面向 ComfyUI 的实用节点集合，当前版本为 `v3.5.0`，包含 9 个模块、29 个节点，覆盖图像处理、数学与正则、提示词处理、尺寸生成、字符串处理、随机选择、视频处理、音频拼接和分镜生成等常见工作流场景。

当前版本的几个统一规则：
- 节点显示名默认使用 `英文名（中文名）`
- 节点分类统一在 `🌟kktools/...`
- 所有节点类名统一增加 `kk` 前缀，便于和官方节点或第三方节点区分
- `nodes/` 目录下的节点文件由 [__init__.py](__init__.py) 自动发现并注册
- 前端扩展 [web/kkllm.js](web/kkllm.js) 会为 `kkLLM` 和 `kkStoryboardScriptLLM` 提供 `provider` / `model` 联动
- 示例工作流已经同步到当前节点名

发布说明见 [RELEASE_NOTES_3.5.0.md](RELEASE_NOTES_3.5.0.md)。

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
- 当前仓库已自带前端扩展目录 [web](web)，无需额外配置即可加载 `provider` / `model` 联动

## 🧭 快速上手

- 在节点面板中搜索 `🌟kktools`、英文类名，或中文名。
- 推荐先打开总览工作流 [workflows/kktools_workflow_node_demo_gallery.json](workflows/kktools_workflow_node_demo_gallery.json)。
- 分模块示例可查看 [workflows/README.md](workflows/README.md)。
- 图像、视频、音频类节点建议先接入你自己的 `IMAGE`、`VIDEO`、`AUDIO` 输入再运行。
- 如果你手里有旧工作流，请留意：
  - 当前全部节点都已切换为 `kk...` 前缀命名
  - 旧工作流里的旧节点名需要重新选择或替换
  - 旧工作流如果使用过 `kkVideoTextOCR`，需要手动移除或改用其他文本提取方案

## 📁 项目结构

- [__init__.py](__init__.py)：自动发现与注册节点，统一节点显示名，并导出版本号与前端目录
- [nodes](nodes)：全部节点源码
- [web/kkllm.js](web/kkllm.js)：`kkLLM` / `kkStoryboardScriptLLM` 的模型联动前端脚本
- [workflows](workflows)：总览与分模块示例工作流
- [fonts](fonts)：可选字体资源
- [RELEASE_NOTES_3.5.0.md](RELEASE_NOTES_3.5.0.md)：当前版本更新说明

## 🧩 源码入口

- 图像模块：[nodes/image.py](nodes/image.py)、[nodes/ImageSplit.py](nodes/ImageSplit.py)
- 数学模块：[nodes/Math.py](nodes/Math.py)
- 提示词模块：[nodes/prompts.py](nodes/prompts.py)
- 尺寸模块：[nodes/size.py](nodes/size.py)
- 字符串模块：[nodes/kkstring.py](nodes/kkstring.py)
- 随机模块：[nodes/RandomSelector.py](nodes/RandomSelector.py)
- 视频模块：[nodes/video.py](nodes/video.py)
- 音频模块：[nodes/audio.py](nodes/audio.py)
- 分镜模块：[nodes/StoryboardScript.py](nodes/StoryboardScript.py)

## 🧾 节点清单

- 图像模块：`kkPadImageToCanvas`、`kkImageFrame`、`kkResize`、`kkGetImage`、`kkBatchImageLoader`、`kkImageTileSplit2x2`、`kkImageGridMerge`、`kkImageSplit`
- 数学模块：`kkMathExpressionNode`、`kkRegexNode`、`kkRegexNodeAdvanced`
- 提示词模块：`kkBatchPrompt`、`kkLLM`
- 尺寸模块：`kkSizeNode`
- 字符串模块：`kkStringNode`、`kkStringNodeAdvanced`、`kkStringMergeNode`、`kkInputNode`、`kkReplaceNode`、`kkSomethingToAny`、`kkStringToIntNode`
- 随机模块：`kkRandomSelector`
- 视频模块：`kkVideoFirstLastFrames`、`kkVideoFramesAdvanced`、`kkMergeVideos`
- 音频模块：`kkAudioMerge4`
- 分镜模块：`kkStoryboardScript`、`kkStoryboardScriptLLM`、`kkStoryboardShotOutput`

---

## 🖼️ 图像模块

源码位置：[nodes/image.py](nodes/image.py) 、[nodes/ImageSplit.py](nodes/ImageSplit.py)

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

- 读取输入图像的宽高信息。
- 适合把图像尺寸继续传给后续节点做动态计算。
- 输出：`width`、`height`

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

---

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

### kkLLM（多厂商LLM）

- 使用 LLM 优化提示词，当前支持 DeepSeek、OpenAI、Gemini、豆包。
- 切换 `provider` 时，前端会自动刷新对应的 `model` 选项。
- 支持 `provider`、`model`、`custom_model`、`base_url`、`system_message`、`max_length`、`temperature`
- 没填 `api_key` 时会直接返回原始提示词，不会中断工作流；请求失败、额度不足或网络异常时会退回本地优化方案。
- 输出：优化后的提示词、原始提示词、优化信息

---

## 📐 尺寸模块

源码位置：[nodes/size.py](nodes/size.py)

### kkSizeNode（尺寸生成）

- 生成指定尺寸的 latent，同时输出最终宽高。
- 支持 `preset` 和 `custom` 两种模式，预设尺寸针对 SDXL 做了优化。
- 所有尺寸会自动校正为 8 的倍数。
- 输出：`LATENT`、`width`、`height`

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

---

## 🎲 随机模块

源码位置：[nodes/RandomSelector.py](nodes/RandomSelector.py)

### kkRandomSelector（随机选择器）

- 从 JSON 配置的多组候选项中随机选择一个值。
- 支持用 `target_groups` 限定候选组，用 `seed` 保证可复现。
- 输出：选中的值、选中的组名、全部组名列表

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
- 分镜 API：`kkStoryboardScriptLLM` 需要有效 `api_key`，不会像 `kkLLM` 一样自动切回本地分镜生成。
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
