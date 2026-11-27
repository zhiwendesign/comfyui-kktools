# 更新日志

本文件汇总近期节点变化；插件当前版本号仍为 `3.5.0`。更早的版本说明见 [RELEASE_NOTES_3.5.0.md](RELEASE_NOTES_3.5.0.md)。

## 2026-11-27

- **图像与蒙版**：修复 `kkResize` 处理 ComfyUI 标准 `[B,H,W]` 蒙版时报错；输出标准蒙版维度，并兼容旧版单通道输入。
- **图像生成**：`kkGPT-image_API` 的提示词编辑区随节点宽度调整，已连接字符串且提示词留空时提示使用第一路非空字符串。
- **网络请求**：图像 API 遇到 DNS 解析失败时短暂重试并记录原因；其他网络故障不会自动重复提交请求。
- **文档**：补充颜色、字体与逻辑节点使用说明，整理 MiniCPM 服务与示例入口。

## 2026-11-26

- 新增 `kkColorPicker` 和 `kkFontLoader`，支持可视化选色、快捷色块与本地字体选择。
- 新增 `kkCompare`、`kkStringLength`、`kkIfElse` 和 `kkSwitchCase`，支持整数比较、字符统计及多类型条件分支。
- `kkSwitchCase` 与 `kkRandomSelector` 的通用输入按连接动态增加，最多 9 路；输出保留所选数据的类型。

## 2026-11-25

- 新增可配置的 MiniCPM 模型服务节点及图像、视频、文本、OCR、质检等示例，支持 Ollama 与 llama.app。

## 2026-11-04

- `kcanvas` 支持多组图片与蒙版配对输入，便于在 HTML 画布中使用透明图片。
