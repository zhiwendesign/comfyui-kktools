# KK MiniCPM 节点

这组节点通过配置的 Ollama 或 llama.app 模型服务接口调用模型。安装后请完全重启 ComfyUI，在 `🌟kktools/MiniCPM` 分类或通过 `KK MiniCPM` 搜索节点。

旧版 `KK MiniCPM Local Loader` 保留用于兼容已有工作流，三个预设现已转为调用本机 Ollama；模型路径和视觉投影字段不再生效。旧版自定义 GGUF 不能自动转换，需换用 `KK MiniCPM Loader` 并选择 Ollama 模型。新工作流建议直接使用 `KK MiniCPM Loader`。旧版示例文件名如果包含“本地直载”，运行时现在同样需要 Ollama。

## 连接模型

`KK MiniCPM Loader` 输出 `connection`，连接到需要推理的节点。`backend` 选择接口类型，`url` 填写服务地址，`model` 自由填写服务中存在的模型名，不限定模型名称：

- Ollama：选择 `Ollama`，例如填写 `http://127.0.0.1:11434`，模型名可通过 `ollama list` 查看。
- llama.app：选择 `llama.app`，填写服务提供的 OpenAI 兼容基础地址，例如 `http://127.0.0.1:9931/v1`；模型名填写服务中加载的名称。需要先启动该服务并加载模型，图片功能需要视觉模型。

地址支持用户指定的 HTTP/HTTPS 服务；文本与图片会发送到填写的地址。当前节点不提供 API 密钥输入。`keep_alive_seconds` 和 `context_length` 只作用于 Ollama；llama.app 的模型保留与上下文大小由服务管理。`max_tokens`、温度、seed 和超时应用于请求。旧工作流的“自定义”与 `custom_model` 输入仍可兼容。

## 节点

| 节点 | 用途 |
|---|---|
| KK MiniCPM Vision | 读取一张图片或图片批次并回答问题。 |
| KK MiniCPM Video | 接收 ComfyUI `VIDEO`，均匀抽帧后按时间顺序发送给模型。 |
| KK MiniCPM Text | 根据指令处理文本。 |
| KK MiniCPM Caption | 逐张处理 `IMAGE` 批次，输出按输入顺序排列的 JSON 和文本。可选输入每行一个文件名。 |
| KK MiniCPM Prompt | 优化图像或其他生成任务的提示词，可选中文或英文。 |
| KK MiniCPM OCR | 提取可见文字，关键内容需要人工核对。 |
| KK MiniCPM QA | 按标准输出摘要、JSON、通过标志和 0–100 分；可选连接参考图。结果是模型判断，重要用途需复核。 |
| KK MiniCPM Router | 根据连接的素材和关键词生成任务标签、JSON 和布尔标志，也可以手动指定任务类型。`auto` 模式下可选连接 MiniCPM5 的 `classifier` 做语义分类，仅发送请求文字和素材类型；不发送图片或视频内容。它只输出路由结果，需要配合条件/开关节点执行分支。 |
| KK MiniCPM JSON | 解析 JSON、代码块内 JSON 或带前缀的 JSON，输出规范化 JSON、字段值、成功标志和错误信息。路径支持 `a.b.0` 或 JSON Pointer `/a/b/0`。 |
| KK MiniCPM Unload | 请求 Ollama 卸载当前连接的模型；llama.app 模型由服务管理，节点只输出提示。将上游文本结果接到 `after`，可保证推理结束后再执行，并从 `value` 输出原文本。 |

Caption 的 `save_txt` 默认关闭。开启后，标注会保存到 ComfyUI `output` 下的 `output_folder` 子目录；提供 `filenames` 时按相应文件名保存为 `.txt`，未提供时使用 `image_000001.txt` 等序号。输入文件名数量必须与图片数一致；同名文件已存在时会报错，不会覆盖。`saved_files_json` 给出实际写入路径。Ollama 模式下 Caption 处理同一批图片时会临时保留模型，最后按 Loader 的 keep-alive 设置释放。

Video 分析的是抽取的画面，不包含音频转录，也可能漏掉快速动作。当前 ComfyUI VIDEO 接口会先解码视频到内存，建议先使用约 15 秒的短视频。输出的 `sampled_frames` 是实际送入模型的帧数。

## 示例

示例工作流同时位于本插件的 `workflows` 文件夹和 ComfyUI 的 `user/default/workflows` 中，名称以 `KK MiniCPM` 开头。分别演示图片、视频、文本与提示词、批量打标、OCR、质检以及路由与 JSON；这样可以按需运行一个模型。视频示例需要先在 Load Video 节点选择自己的文件；批量打标示例默认仅输出结果，不写文件。

如 Ollama 中找不到模型，请在 Ollama 桌面应用检查模型目录和模型列表。4.7 体积较大，建议推理时关闭其他占用显存的大模型；如果资源不足，先降低上下文长度或切换可用的较小视觉模型。
