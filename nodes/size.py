"""
ComfyUI Custom Node: Size
尺寸节点 - 用于生成不同比例和尺寸的latent张量
"""

import torch

class SizeNode:
    """尺寸节点（尺寸生成） - 支持预设比例和自定义尺寸"""
    
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "size_mode": (["preset", "custom"], {
                    "default": "preset"
                }),
                "aspect_ratio": (["1:1", "16:9", "9:16", "4:3", "3:4", "3:2", "2:3"], {
                    "default": "1:1"
                }),
                "custom_width": ("INT", {
                    "default": 512,
                    "min": 64,
                    "max": 8192,
                    "step": 8
                }),
                "custom_height": ("INT", {
                    "default": 512,
                    "min": 64,
                    "max": 8192,
                    "step": 8
                }),
                "batch_size": ("INT", {
                    "default": 1,
                    "min": 1,
                    "max": 64,
                    "step": 1
                }),
            }
        }
    
    RETURN_TYPES = ("LATENT", "INT", "INT")
    RETURN_NAMES = ("latent", "width", "height")
    FUNCTION = "generate"
    CATEGORY = "kktools"
    
    def generate(self, size_mode, aspect_ratio, custom_width, custom_height, batch_size):
        """生成latent张量并返回尺寸信息"""
        # 预设尺寸映射（针对SDXL优化的尺寸）
        size_mapping = {
            "1:1": (1328, 1328),
            "16:9": (1664, 928),
            "9:16": (928, 1664),
            "4:3": (1472, 1104),
            "3:4": (1104, 1472),
            "3:2": (1584, 1056),
            "2:3": (1056, 1584),
        }
        
        if size_mode == "preset":
            width, height = size_mapping[aspect_ratio]
        else:  # custom mode
            width, height = custom_width, custom_height
        
        # 确保尺寸是8的倍数（latent要求）
        width = (width // 8) * 8
        height = (height // 8) * 8
        
        # 计算latent尺寸（通常是实际尺寸的1/8）
        latent_width = width // 8
        latent_height = height // 8
        
        # 创建空的latent张量
        latent_tensor = torch.zeros([batch_size, 4, latent_height, latent_width])
        
        # 打印调试信息
        print(f"Size Node:")
        print(f"  Size Mode: {size_mode}")
        print(f"  Aspect Ratio: {aspect_ratio}")
        print(f"  Final Width: {width}")
        print(f"  Final Height: {height}")
        print(f"  Latent Width: {latent_width}")
        print(f"  Latent Height: {latent_height}")
        print(f"  Batch Size: {batch_size}")
        
        return ({"samples": latent_tensor}, width, height)


# ComfyUI 节点注册
NODE_CLASS_MAPPINGS = {
    "SizeNode": SizeNode,
}

# 节点在菜单中显示的名称
NODE_DISPLAY_NAME_MAPPINGS = {
    "SizeNode": "尺寸节点（尺寸生成）",
}

__all__ = ['SizeNode']