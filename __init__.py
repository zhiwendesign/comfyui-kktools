"""
ComfyUI Custom Nodes: kktools Nodes
kktools自定义节点集合
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
        module_name = os.path.splitext(py_file)[0]
        file_path = os.path.join(nodes_dir, py_file)
        
        print(f"🔍 正在加载模块: {module_name}")
        module = load_module_from_file(module_name, file_path)
        
        if module is None:
            continue
            
        # 查找模块中的节点类
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            
            # 检查是否是类且是有效的节点类
            if (isinstance(attr, type) and 
                hasattr(attr, 'INPUT_TYPES') and 
                hasattr(attr, 'RETURN_TYPES') and 
                hasattr(attr, 'FUNCTION') and 
                hasattr(attr, 'CATEGORY')):
                
                # 添加到映射
                node_class_mappings[attr_name] = attr
                
                # 生成显示名称
                display_name = attr_name
                if attr_name.startswith('kktools'):
                    display_name = f"kktools {attr_name[7:]}"
                
                # 添加中文描述
                chinese_desc = ""
                if 'Size' in attr_name:
                    chinese_desc = " (尺寸)"
                elif 'Batch' in attr_name:
                    chinese_desc = " (批量提示词)"
                elif 'Prompt' in attr_name:
                    chinese_desc = " (AI提示词生成)"
                elif 'String' in attr_name:
                    if 'Merge' in attr_name:
                        chinese_desc = " (字符串合并)"
                    elif 'Input' in attr_name:
                        chinese_desc = " (字符串/整数输入)"
                    elif 'Replace' in attr_name:
                        chinese_desc = " (字符串替换)"
                    elif 'Advanced' in attr_name:
                        chinese_desc = " (字符串裁剪-高级)"
                    else:
                        chinese_desc = " (字符串裁剪)"
                elif 'Regex' in attr_name:
                    if 'Advanced' in attr_name:
                        chinese_desc = " (正则表达式-高级)"
                    else:
                        chinese_desc = " (正则表达式)"
                elif 'PadImage' in attr_name:
                    chinese_desc = " (图像填充到画布)"
                elif 'ImageFrame' in attr_name:
                    chinese_desc = " (图像边框)"
                elif 'Resize_img_and_mask' in attr_name:
                    chinese_desc = " (图像蒙版同步调整)"
                elif 'GetImage' in attr_name:
                    chinese_desc = " (获取图像尺寸)"
                elif 'Resize' in attr_name:
                    chinese_desc = " (图像蒙版同步调整)"
                elif 'AIPromptOptimizer' in attr_name:
                    chinese_desc = " (AI提示词优化)"
                # 新增的节点名称映射
                elif attr_name == 'InputNode':
                    chinese_desc = " (多类型输入)"
                elif attr_name == 'ReplaceNode':
                    chinese_desc = " (字符串替换)"
                elif attr_name == 'SomethingToAny':
                    chinese_desc = " (任意类型转换)"
                elif attr_name == 'MathExpressionNode':
                    chinese_desc = " (数学表达式)"
                
                node_display_name_mappings[attr_name] = f"{display_name}{chinese_desc}"
                print(f"      ✅ 注册节点: {attr_name} -> {node_display_name_mappings[attr_name]}")
    
    return node_class_mappings, node_display_name_mappings

# 导入所有节点类
print("🔄 开始加载 kktools Nodes...")

# 使用自动发现机制加载节点
NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS = discover_and_load_nodes()

# 手动加载特定节点（备用方案，如果自动发现失败）
if not NODE_CLASS_MAPPINGS:
    print("⚠️  自动发现失败，使用手动加载...")
    
    # 这里保留原有的手动加载逻辑作为备用
    nodes_to_load = [
        ("size_node.py", ["kktoolsSize"]),
        ("batch_prompt_loader.py", ["kktoolsBatchPromptLoader"]),
        ("multi_ai_prompt_generator.py", ["MultiAIPromptGenerator"]),
        ("string_node.py", ["kktoolsStringNode", "kktoolsStringNodeAdvanced", 
                          "kktoolsStringMergeNode", "kktoolsStringInputNode", 
                          "kktoolsStringReplaceNode"]),
        ("regex_node.py", ["kktoolsRegexNode", "kktoolsRegexNodeAdvanced"]),
        ("image_layout.py", ["PadImageToCanvas", "ImageFrame", "Resize"]),
        ("prompts.py", ["BatchPrompt", "AIPromptOptimizerNode"]),
    ]
    
    for file_name, class_names in nodes_to_load:
        file_path = os.path.join(nodes_dir, file_name)
        module_name = os.path.splitext(file_name)[0]
        
        module = load_module_from_file(module_name, file_path)
        if module:
            for class_name in class_names:
                if hasattr(module, class_name):
                    NODE_CLASS_MAPPINGS[class_name] = getattr(module, class_name)
                    print(f"   ✅ {class_name} 手动加载成功")

print(f"✅ kktools Nodes 加载完成！共注册 {len(NODE_CLASS_MAPPINGS)} 个节点\n")

# 导出
__all__ = ['NODE_CLASS_MAPPINGS', 'NODE_DISPLAY_NAME_MAPPINGS']

# 元信息
__version__ = "3.4.0"
__author__ = "kktools"
__description__ = "kktools Custom Nodes Collection for ComfyUI"