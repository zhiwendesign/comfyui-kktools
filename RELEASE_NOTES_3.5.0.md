# kktools v3.5.0 Release Notes

适用于 GitHub Release、更新公告或版本说明。

## 更新概览

### 2026-09-20 视频深度转换节点

- 新增 `kkVideoPose（视频转人体骨骼视频）`，复用 ComfyUI 内置 SDPose 将输入视频逐帧转换为人体骨骼视频。
- 支持分别显示身体、头部、手部、面部和脚部，可调整线宽、面部点大小和置信度，并可选保留输入音轨。
- 节点直接使用官方 `sdpose_wholebody_fp16.safetensors` 的 `MODEL` 和 `VAE` 输出，不增加第三方依赖或后台下载。
- 修复 SDPose 在个别帧输出 `NaN` 关键点时，骨骼绘制因无法将无效坐标转换为整数而中断的问题。
- 新增 `kkVideoCompare（视频对比）`，支持 2–5 路视频按时间同步后横向并排，在节点内使用同一个播放器、播放按钮和进度条预览；支持可选外部音频，未连接时默认使用视频 1 的音轨。
- 新增 `kkVideoDepth（视频转深度视频）`，使用 ComfyUI 内置 Depth Anything 3 将输入视频逐帧转换为深度视频。
- 支持灰度与 Turbo 彩色输出、`v2_style` 与 `min_max` 两种归一化方式，并可调节模型处理分辨率。
- 输出保持输入视频的原分辨率和 FPS，可选择保留或移除原始音频。
- 节点直接接入官方 `DA3_MODEL`，不新增第三方依赖，也不会自动下载模型。
- 修复 `kkVideoDepth` 和 `kkMergeVideos` 输出连接新版 `SaveVideo` 时，因 `crf` 等编码参数未被视频对象接收而保存失败的问题。

### 2026-09-19 运行管理、比例输出与分类主题更新

- `kkGetImage（获取图像尺寸）` 新增 `ratio` 字符串输出，会从 `16:9`、`9:16`、`1:1`、`3:2`、`2:3`、`3:4`、`4:3`、`21:9` 中返回最接近输入图像的常用比例。
- 新增顶部“运行管理”，实时显示 CPU、系统内存、GPU 与显存使用情况；默认每 2 秒刷新，也可点击立即刷新。
- 运行管理仅读取本机状态，不会发送统计信息到外部服务。
- 保留 ComfyUI 原生运行工具栏及其功能；拖动工具栏靠近顶部运行管理区域时，会自动吸附到显存信息右侧。
- 参考 PPT 工具的深色 UI，为图像、数学计算、提示词、尺寸、字符串、随机、视频、音频、分镜和兼容分类增加独立配色。
- OpenMAIC 的导入、独立版、导出、音频和工具分类同步增加差异化配色；模板、PPT 及现有特殊节点继续保留原有主题。
- 分类主题仅修改节点外观，不改变节点输入、输出或执行逻辑。

### 2026-09-14 文档与字符串节点更新

- 新增 `kkMarkdownToString（MD转字符串）`，接收 `KK_MARKDOWN_FILE` 并输出标准 `STRING`。
- 补充 `kkMarkdownToString` 的中文显示名和备用注册入口。
- 按当前代码重新盘点并重写 README 节点清单，完整列出 69 个可注册节点标识和 17 个分类。
- 模板、PPT、OpenMAIC 与兼容节点改为逐节点说明，同时标明节点标识和界面显示名。
- `kkimage2_GAPI`、`kkLingsiNativePromptImage`、`kkImageAPI` 改列为已停用节点，不再混入现役节点清单。
- `kkMarkdown上传` 的 MD 文件、文件夹地址和 ZIP 压缩包改为严格三选一；同时填写多个来源会明确报错，通过上传按钮选择文件时会自动清空另外两个来源。

### 2026-09-11 功能更新

- 新增 `kk_API配置`，集中输出 Base URL 与 API Key；`kkGPT-image_API` 和 `kkLLM` 均可直接接入。
- `kkGPT-image_API` 新增运行日志输出；内容审核失败时明确提示“生成图像为敏感内容，请修改提示词或上传参考图像”。
- `kkGPT-image_API` 支持连接 `kkSizeNode.ratio`。
- `kkLLM` 将 `original_prompt` 调整为第一个输出，后续依次为优化结果和状态信息。
- 更新 `kkLLM` 多厂商模型列表，修复旧工作流中 `provider`、`model` 输入失效的问题。
- `kkLLM` 新增 Markdown 输入；连接后以 Markdown 内容代替基础提示词。
- 新增 `kkMarkdown上传`，支持单个 `.md`、ComfyUI 输入目录中的文件夹及 `.zip` 压缩包。
- 新增 `kkSkills模板选择器`，支持本地入库、封面、搜索、自动刷新、悬浮改名和右上角删除。
- `kkSkills模板选择器` 输出携带完整模板集合，可交给 `kkRandomSelector` 按 seed 随机选择 Skill。
- `kkSkills模板选择器` 新增模板包导入与导出，支持恢复模板名称和同名封面；导入会校验路径、文件数、单文件大小与解压后总大小。
- Skills 本地数据迁移到 ComfyUI 用户目录 `user/kktools/skills-templates`，也可通过 `KKTOOLS_SKILLS_DIR` 自定义。
- Skills 卡片区域随节点尺寸自适应，不再强制缩小用户主动调整的节点高度。
- `kkSkills模板选择器` 新增 `Tag` 字符串输入，支持为 Markdown Skill 写入分类标签、卡片展示和搜索。
- `kkMarkdown上传` 新增可选 `Tag` 输入与第二个 `Tag` 输出，可直接连接 `kkSkills模板选择器.Tag`。
- `kkRandomSelector` 新增 `Markdown文件` 输入和输出，兼容 `kkMarkdown上传` 与 `kkSkills模板选择器`。
- 移除 `kkimage2_Zuco` 和空的 `🌟kktools/AI生图` 分类。
- 重新整理 README，补齐图像、模板、PPT、Skills、随机选择及兼容节点说明。

### 后续整理

- 模板工具分类统一为 `🌟kktools/模板工具`。
- PPT 工具分类统一为 `🌟kktools/PPT工具`。
- 移除重复的 `kkLingsiNativePromptImage` 注册，灵思图像节点统一为 `kkGPT-image_API`。
- `kkGPT-image_API` 归入 `🌟kktools/图像`，移除 `kkimage2_Zuco`；不再保留空的 `🌟kktools/AI生图` 分类。
- 模板与 PPT 节点显示名称移除 “Imagen Studio” 前缀。

本次版本主要完成了 kktools 节点体系的一次统一整理，重点包括：

- 全部节点类名统一增加 `kk` 前缀
- 字符串模块文件由 `nodes/string.py` 重命名为 `nodes/kkstring.py`
- 总 README 重写为完整节点说明文档
- 所有示例工作流同步更新为新节点名
- 示例工作流模块内布局重新整理，减少节点重叠
- 前端扩展脚本同步适配新的分镜节点名

## 重点更新

### 1. 全部节点统一 `kk` 前缀

为规避与官方节点或第三方节点重名，本次将全部节点统一调整为 `kk...` 命名，例如：

- `PadImageToCanvas` -> `kkPadImageToCanvas`
- `MathExpressionNode` -> `kkMathExpressionNode`
- `StringNode` -> `kkStringNode`
- `MergeVideos` -> `kkMergeVideos`
- `StoryboardScriptLLM` -> `kkStoryboardScriptLLM`

当前代码共包含 35 个 `kk` 前缀的现役节点；模板、PPT、OpenMAIC 和兼容节点继续使用各自已有标识。

### 2. 字符串模块文件重命名

- `nodes/string.py` 已重命名为 `nodes/kkstring.py`
- 自动发现与备用手动加载逻辑已同步更新

### 3. README 总文档重写

根目录 `readme.md` 已更新为完整总说明，覆盖当前全部模块和全部节点，包含：

- 节点清单
- 模块说明
- 节点功能简介
- 工作流入口
- 使用说明与升级提示

### 4. 示例工作流全面更新

`workflows` 目录中的总览与模块示例已同步完成：

- 新节点名替换
- 顶部说明卡文案统一
- 模块内节点间距优化
- 总览工作流布局重排

### 5. LLM 前端联动更新

`web/kkllm.js` 已同步适配新的分镜节点名，确保相关模型下拉联动继续正常工作。

## Breaking Changes

本次版本包含破坏性命名变更：

- 旧工作流中的旧节点名不会自动映射到新节点名
- 旧的 `InputNode`、`RegexNode` 以及其它无 `kk` 前缀节点，现已统一更名
- 如使用旧工作流，请重新选择对应的新节点

## 升级建议

升级到 v3.5.0 后，建议：

1. 重启 ComfyUI
2. 重新加载或重连旧工作流中的旧节点
3. 优先参考新的总览工作流和模块示例工作流

## 示例工作流入口

- 总览工作流：`workflows/kktools_workflow_node_demo_gallery.json`
- 模块索引：`workflows/README.md`

## 适合对外发布的简版说明

kktools v3.5.0 已发布。本次版本统一为全部节点增加 `kk` 前缀，规避与官方/第三方节点重名；同时重命名字符串模块文件为 `kkstring.py`，重写总 README，更新全部示例工作流文案与布局，并同步修复前端扩展对新节点名的适配。由于本次属于命名规范化版本，旧工作流中的旧节点名需要重新替换为新版 `kk...` 节点。
