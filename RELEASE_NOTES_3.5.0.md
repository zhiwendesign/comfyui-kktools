# kktools v3.5.0 Release Notes

适用于 GitHub Release、更新公告或版本说明。

## 更新概览

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

当前版本共整理为 28 个 `kk` 前缀节点。

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
