"""
ComfyUI Custom Nodes: 🌟kktools Nodes
🌟kktools自定义节点集合
"""

import os
import sys
import importlib.util
import traceback

# 添加当前目录到Python路径
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

# nodes 文件夹路径
nodes_dir = os.path.join(current_dir, "nodes")
WEB_DIRECTORY = "./web"
DISABLED_NODE_CLASSES = {"kkimage2_GAPI"}

NODE_CHINESE_NAME_MAPPINGS = {
    "kkAudioMerge4": "音频四合一",
    "kkBatchImageLoader": "批量图像加载",
    "kkBatchPrompt": "批量提示词",
    "kkGetImage": "获取图像尺寸",
    "kkImageGridMerge": "图像宫格合并",
    "kkImageFrame": "图像边框",
    "kkImageOverlay": "图像叠加",
    "kkImageSplit": "图像切割",
    "kkImageTileSplit2x2": "图像2x2分块",
    "kkInputNode": "多类型输入",
    "kkLLM": "多厂商LLM",
    "kkMathExpressionNode": "数学表达式",
    "kkMergeVideos": "视频合并",
    "kkPadImageToCanvas": "图像填充到画布",
    "kkRandomSelector": "随机选择器",
    "kkRegexNode": "正则表达式",
    "kkRegexNodeAdvanced": "正则表达式高级",
    "kkReplaceNode": "字符串替换",
    "kkResize": "图像蒙版同步调整",
    "kkSizeNode": "尺寸生成",
    "kkSomethingToAny": "任意类型转换",
    "kkStoryboardScript": "默认分镜",
    "kkStoryboardScriptLLM": "LLM分镜",
    "kkStoryboardShotOutput": "分镜输出",
    "kkStringMergeNode": "字符串合并",
    "kkStringNode": "字符串裁剪",
    "kkStringNodeAdvanced": "字符串裁剪高级",
    "kkStringToIntNode": "字符串转整数",
    "kkVideoFirstLastFrames": "视频首尾帧提取",
    "kkVideoFramesAdvanced": "视频抽帧高级",
}


def build_node_display_name(class_name):
    """统一生成节点显示名：EnglishName（中文名称）"""
    chinese_name = NODE_CHINESE_NAME_MAPPINGS.get(class_name)
    if chinese_name:
        return f"{class_name}（{chinese_name}）"
    return class_name

def load_module_from_file(module_name, file_path):
    """从文件路径加载模块"""
    try:
        if not os.path.exists(file_path):
            print(f"   ⚠️  文件不存在: {file_path}")
            return None
            
        spec = importlib.util.spec_from_file_location(module_name, file_path)
        if spec is None:
            print(f"   ❌ 无法创建模块规范: {module_name}")
            return None
            
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        print(f"   ✅ {module_name} 加载成功")
        return module
    except Exception as e:
        print(f"   ❌ 加载 {module_name} 失败: {e}")
        print(f"   详细错误: {traceback.format_exc()}")
        return None

# 动态发现并加载节点模块
def discover_and_load_nodes():
    """自动发现并加载 nodes 目录下的所有节点模块"""
    node_class_mappings = {}
    node_display_name_mappings = {}
    
    if not os.path.exists(nodes_dir):
        print(f"⚠️  nodes 目录不存在: {nodes_dir}")
        return node_class_mappings, node_display_name_mappings
    
    # 获取所有Python文件
    python_files = [f for f in os.listdir(nodes_dir) 
                   if f.endswith('.py') and not f.startswith('_')]
    
    print(f"🔄 在 nodes 目录中发现 {len(python_files)} 个Python文件")
    
    for py_file in python_files:
        module_name = os.path.splitext(py_file)[0].replace('-', '_')
        file_path = os.path.join(nodes_dir, py_file)
        
        print(f"🔍 正在加载模块: {module_name}")
        module = load_module_from_file(module_name, file_path)
        
        if module is None:
            continue

        module_display_name_mappings = getattr(module, "NODE_DISPLAY_NAME_MAPPINGS", {})
        module_node_mappings = getattr(module, "NODE_CLASS_MAPPINGS", {})

        for class_name, node_class in module_node_mappings.items():
            if class_name in DISABLED_NODE_CLASSES:
                print(f"      ⏭️  跳过禁用节点: {class_name}")
                continue
            if not (
                isinstance(node_class, type)
                and hasattr(node_class, 'INPUT_TYPES')
                and hasattr(node_class, 'RETURN_TYPES')
                and hasattr(node_class, 'FUNCTION')
                and hasattr(node_class, 'CATEGORY')
            ):
                continue
            node_class_mappings[class_name] = node_class
            node_display_name_mappings[class_name] = module_display_name_mappings.get(class_name) or build_node_display_name(class_name)
            print(f"      ✅ 注册节点: {class_name} -> {node_display_name_mappings[class_name]}")

        # 查找模块中的节点类
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if attr_name.startswith("_") or attr in module_node_mappings.values():
                continue
            
            # 检查是否是类且是有效的节点类
            if (isinstance(attr, type) and 
                hasattr(attr, 'INPUT_TYPES') and 
                hasattr(attr, 'RETURN_TYPES') and 
                hasattr(attr, 'FUNCTION') and 
                hasattr(attr, 'CATEGORY')):
                if attr_name in DISABLED_NODE_CLASSES:
                    print(f"      ⏭️  跳过禁用节点: {attr_name}")
                    continue
                
                # 添加到映射
                node_class_mappings[attr_name] = attr
                
                node_display_name_mappings[attr_name] = module_display_name_mappings.get(attr_name) or build_node_display_name(attr_name)
                print(f"      ✅ 注册节点: {attr_name} -> {node_display_name_mappings[attr_name]}")
    
    return node_class_mappings, node_display_name_mappings

# 导入所有节点类
print("🔄 开始加载 🌟kktools Nodes...")

# 使用自动发现机制加载节点
NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS = discover_and_load_nodes()

try:
    from imagen_studio_routes import register_routes as register_imagen_studio_routes

    register_imagen_studio_routes()
except Exception as exc:
    print(f"[kktools Imagen Studio] 模板库接口注册失败：{exc}")

try:
    from kktools_settings.settings_routes import register_routes as register_kktools_settings_routes

    register_kktools_settings_routes()
except Exception as exc:
    print(f"[kktools Settings] 接口注册失败：{exc}")

# 手动加载特定节点（备用方案，如果自动发现失败）
if not NODE_CLASS_MAPPINGS:
    print("⚠️  自动发现失败，使用手动加载...")
    
    # 这里保留原有的手动加载逻辑作为备用
    nodes_to_load = [
        ("size.py", ["kkSizeNode"]),
        ("prompts.py", ["kkBatchPrompt", "kkLLM"]),
        ("kkstring.py", ["kkStringNode", "kkStringNodeAdvanced",
                        "kkStringMergeNode", "kkStringToIntNode",
                        "kkInputNode", "kkReplaceNode", "kkSomethingToAny"]),
        ("Math.py", ["kkMathExpressionNode", "kkRegexNode", "kkRegexNodeAdvanced"]),
        ("image.py", ["kkImageOverlay", "kkPadImageToCanvas", "kkImageFrame", "kkResize",
                     "kkGetImage", "kkBatchImageLoader", "kkImageTileSplit2x2",
                     "kkImageGridMerge"]),
        ("ImageSplit.py", ["kkImageSplit"]),
        ("RandomSelector.py", ["kkRandomSelector"]),
        ("video.py", ["kkVideoFirstLastFrames", "kkVideoFramesAdvanced", "kkMergeVideos"]),
        ("audio.py", ["kkAudioMerge4"]),
        ("StoryboardScript.py", ["kkStoryboardScript", "kkStoryboardScriptLLM", "kkStoryboardShotOutput"]),
        ("kkimage2_zuco.py", ["kkimage2_Zuco"]),
        ("lingsi.py", ["kkLingsiNativePromptImage", "kkimage2_灵思API"]),
    ]
    
    for file_name, class_names in nodes_to_load:
        file_path = os.path.join(nodes_dir, file_name)
        module_name = os.path.splitext(file_name)[0].replace('-', '_')
        
        module = load_module_from_file(module_name, file_path)
        if module:
            for class_name in class_names:
                if class_name in DISABLED_NODE_CLASSES:
                    print(f"   ⏭️  {class_name} 已禁用，跳过手动加载")
                    continue
                if hasattr(module, class_name):
                    NODE_CLASS_MAPPINGS[class_name] = getattr(module, class_name)
                    NODE_DISPLAY_NAME_MAPPINGS[class_name] = build_node_display_name(class_name)
                    print(f"   ✅ {class_name} 手动加载成功")

print(f"✅ 🌟kktools Nodes 加载完成！共注册 {len(NODE_CLASS_MAPPINGS)} 个节点\n")

# 导出
__all__ = ['NODE_CLASS_MAPPINGS', 'NODE_DISPLAY_NAME_MAPPINGS', 'WEB_DIRECTORY']

# 元信息
__version__ = "3.5.0"
__author__ = "🌟kktools"
__description__ = "🌟kktools Custom Nodes Collection for ComfyUI"
