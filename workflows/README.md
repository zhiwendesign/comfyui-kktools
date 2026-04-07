# ComfyUI kktools 工作流示例指南

## 📋 概述

`workflows` 目录提供了两类示例：

- 总览型工作流：用于快速浏览全部节点
- 模块型工作流：按 `readme.md` 的模块顺序拆分，便于逐个学习和测试

所有新示例都遵循根目录 [readme.md](../readme.md) 的模块划分与说明风格，每个节点都配有一张 `Note` 说明卡，包含功能描述、关键参数和最小演示方式。

当前示例已全部切换到 `kk...` 前缀节点名。

## 🧭 快速上手

- 想一次看全全部节点：
  - 打开 `kktools_workflow_node_demo_gallery.json`

- 想按模块学习：
  - 图像：`kktools_workflow_image_examples.json`
  - 数学：`kktools_workflow_math_examples.json`
  - 提示词：`kktools_workflow_prompts_examples.json`
  - 尺寸：`kktools_workflow_size_examples.json`
  - 字符串：`kktools_workflow_string_examples.json`
  - 随机：`kktools_workflow_random_examples.json`
  - 视频：`kktools_workflow_video_examples.json`
  - 音频：`kktools_workflow_audio_examples.json`
  - 分镜：`kktools_workflow_storyboard_examples.json`

- 想保留旧版参考：
  - 打开 `kktools_workflow_node_demo_.json`

## 🎯 工作流索引

### 总览工作流

- `kktools_workflow_node_demo_gallery.json`
  - 当前推荐的节点总览工作流
  - 覆盖当前仓库全部 kktools 节点
  - 每个节点包含最小演示与说明卡

- `kktools_workflow_node_demo_.json`
  - 仓库中原有的旧版总览工作流
  - 适合作为历史参考

### 模块工作流

- `kktools_workflow_image_examples.json`
  - 图像处理模块示例

- `kktools_workflow_math_examples.json`
  - 数学运算模块示例

- `kktools_workflow_prompts_examples.json`
  - 提示词模块示例

- `kktools_workflow_size_examples.json`
  - 尺寸生成模块示例

- `kktools_workflow_string_examples.json`
  - 字符串处理模块示例

- `kktools_workflow_random_examples.json`
  - 随机选择模块示例

- `kktools_workflow_video_examples.json`
  - 视频处理模块示例

- `kktools_workflow_audio_examples.json`
  - 音频处理模块示例

- `kktools_workflow_storyboard_examples.json`
  - 分镜模块示例

## ⚠️ 使用建议

- 字符串、数学、随机、尺寸、提示词类节点：
  - 打开后即可直接查看默认参数与输出口设计

- 图像、视频、音频、分镜输出类节点：
  - 需要先把你自己的 `IMAGE`、`VIDEO`、`AUDIO`、`LIST` 接到左侧输入口

- `kkBatchImageLoader` 与 `kkBatchPrompt`：
  - 需要把示例中的目录或文件路径改成你本机的真实路径

- `kkLLM` 与 `kkStoryboardScriptLLM`：
  - 需要填写有效的 `api_key` 后再运行
