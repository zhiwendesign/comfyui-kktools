## 🌟 kktools节点合集介绍

欢迎合作交流微信【XingYueAiArt】

---

✨ KKTools ComfyUI 工具包 - ✨

🎯 专为ComfyUI设计的超实用自定义节点集合！就像给你的AI绘画工作流装上了“瑞士军刀”🛠️，让提示词处理、图像操作、数学计算变得超级简单！

📦 核心功能模块
🎨 图像处理节点
📍 文件：image.py

节点名称	功能说明	使用场景
Pad Image to Canvas	将图像放置到指定画布上	给图片加背景、调整构图
Image Frame	创建带边框的图像对比展示	多图对比、作品展示
Resize	图像和蒙版同步调整尺寸	保持图像蒙版一致性
Get Image	获取图像尺寸信息	获取图片宽高数据
Batch Image Loader	批量加载图像	处理大量图片素材
💡 使用技巧：

用Image Frame做A/B测试对比图

Pad Image to Canvas支持透明背景，做素材合成超方便

Batch Image Loader可以按顺序/随机加载图片，适合做素材库

📝 提示词处理节点
📍 文件：prompts.py

节点名称	功能说明	使用场景
Batch Prompt	批量加载提示词文件	批量生成、提示词库管理
AI Prompt Optimizer	通过DeepSeek优化提示词	提升提示词质量、风格统一
💡 使用技巧：

Batch Prompt支持JSON和TXT格式，可以建立自己的提示词库

AI优化器有轻/中/重三种优化级别，按需选择

可以指定目标风格（写实/动漫/艺术等）

🔤 字符串处理节点
📍 文件：string.py

节点名称	功能说明	使用场景
String Node	基础字符串裁剪	去除多余字符
String Node Advanced	高级裁剪带统计信息	精确控制文本长度
String Merge Node	合并多个字符串	组合多个提示词
Input Node	多类型输入转换	数据类型转换
Replace Node	字符串替换	批量修改提示词
Something To Any	任意类型转换	数据格式统一
💡 使用技巧：

字符串合并可以加分隔符，适合组合多个关键词

替换节点支持全部替换或单个替换

类型转换确保数据在不同节点间流畅传递

📐 尺寸和数学节点
📍 文件：size.py & Math.py

节点名称	功能说明	使用场景
Size Node	生成预设尺寸的latent	快速设置画布尺寸
Math Expression Node	数学表达式计算	动态计算参数
Regex Node	正则表达式操作	复杂文本处理
💡 使用技巧：

Size Node支持1:1、16:9等常用比例，SDXL优化尺寸

数学表达式支持变量a/b/c/d，可以用min/max/sqrt等函数

正则表达式适合提取或替换特定模式的文本

🚀 工作流搭建建议
🎨 多图对比工作流
text
Image Frame → 设置2-3个输入 → 添加标签 → 输出对比图
适合： 模型对比、参数调试效果展示

📝 智能提示词工作流
text
基础提示词 → AI优化器 → 字符串处理 → 最终提示词
适合： 快速生成高质量提示词

🖼️ 批量处理工作流
text
Batch Image Loader → Resize调整 → Pad to Canvas统一尺寸
适合： 素材预处理、数据集制作

💫 特色功能亮点
🎯 中文友好 - 节点名称和描述都支持中文

🔄 批量处理 - 支持文件批量加载和批量操作

🎨 视觉化 - Image Frame让对比结果一目了然

🤖 AI增强 - 集成DeepSeek API优化提示词

📊 数据统计 - 高级节点提供详细的操作统计

🌟 使用小贴士
字体支持：Image Frame节点支持自定义字体，把字体文件放在fonts文件夹即可

错误处理：所有节点都有完善的错误提示，遇到问题看控制台输出

性能优化：批量处理时注意设置合理的批次大小，避免内存溢出