import torch
import numpy as np
from PIL import Image, ImageColor, ImageDraw, ImageFont
import os
import glob
import random

# ============== 图像分块切割节点 ==============
class ImageSplit:
    """
    图像分块切割节点
    将一张输入图片切割成指定网格大小的子图
    可选择合并输出或单独输出每个分块
    """

    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "image": ("IMAGE",),
                "grid_size": (["2x2", "3x3", "1x2", "2x1", "1x3", "3x1", "4x4", "custom"], {
                    "default": "2x2"
                }),
                "custom_width": ("INT", {
                    "default": 2,
                    "min": 1,
                    "max": 10,
                    "step": 1,
                    "display": "number"
                }),
                "custom_height": ("INT", {
                    "default": 2,
                    "min": 1,
                    "max": 10,
                    "step": 1,
                    "display": "number"
                }),
                "overlap_pixels": ("INT", {
                    "default": 0,
                    "min": 0,
                    "max": 512,
                    "step": 1,
                    "display": "number"
                }),
                "output_order": (["row-major", "column-major", "diagonal"], {
                    "default": "row-major"
                }),
            }
        }

    RETURN_TYPES = ("IMAGE",) * 17
    RETURN_NAMES = ("merged_tiles",) + tuple([f"tile_{i+1:02d}" for i in range(16)])
    FUNCTION = "split_image"
    CATEGORY = "kktools/Image"
    OUTPUT_IS_LIST = (False,) * 17

    def tensor_to_pil(self, img_tensor):
        """将 ComfyUI 图像张量转换为 PIL 图像"""
        if len(img_tensor.shape) == 4:  # Batch of images
            batch_size, height, width, channels = img_tensor.shape
            images = []
            for i in range(batch_size):
                img_np = 255. * img_tensor[i].cpu().numpy()
                img_np = np.clip(img_np, 0, 255).astype(np.uint8)
                if channels == 1:
                    img_np = img_np.reshape(height, width)
                elif channels == 3:
                    img_np = img_np.reshape(height, width, 3)
                elif channels == 4:
                    img_np = img_np.reshape(height, width, 4)
                img = Image.fromarray(img_np)
                images.append(img)
            return images
        else:
            # 单张图像
            img_np = 255. * img_tensor.cpu().numpy()
            img_np = np.clip(img_np, 0, 255).astype(np.uint8)
            return [Image.fromarray(img_np)]

    def pil_to_tensor(self, pil_images):
        """将 PIL 图像列表转换回 ComfyUI 图像张量"""
        if not pil_images:
            return torch.zeros((1, 256, 256, 3))
            
        tensors = []
        for img in pil_images:
            # 确保图像为 RGB 模式
            img_rgb = img.convert("RGB")
            img_np = np.array(img_rgb).astype(np.float32) / 255.0
            tensor = torch.from_numpy(img_np)[None,]
            tensors.append(tensor)
        
        if tensors:
            return torch.cat(tensors, dim=0)
        else:
            return torch.zeros((1, 256, 256, 3))

    def pil_to_single_tensor(self, pil_image):
        """将单个 PIL 图像转换为张量"""
        if pil_image is None:
            return torch.zeros((1, 256, 256, 3))
            
        # 确保图像为 RGB 模式
        img_rgb = pil_image.convert("RGB")
        img_np = np.array(img_rgb).astype(np.float32) / 255.0
        tensor = torch.from_numpy(img_np)[None,]
        return tensor

    def calculate_tile_bounds(self, width, height, grid_x, grid_y, overlap_pixels):
        """计算所有分块的边界坐标"""
        bounds = []
        
        # 计算每个分块的宽度和高度（不考虑重叠）
        tile_width = width // grid_x
        tile_height = height // grid_y
        
        # 计算剩余像素（如果不能整除）
        width_remainder = width % grid_x
        height_remainder = height % grid_y
        
        # 调整重叠像素，确保不会越界
        max_overlap_w = min(overlap_pixels, tile_width // 3) if tile_width > 0 else 0
        max_overlap_h = min(overlap_pixels, tile_height // 3) if tile_height > 0 else 0
        overlap_w = min(overlap_pixels, max_overlap_w)
        overlap_h = min(overlap_pixels, max_overlap_h)
        
        for y in range(grid_y):
            for x in range(grid_x):
                # 计算当前分块的起始坐标
                start_x = x * tile_width
                start_y = y * tile_height
                
                # 对最后一列/行进行宽度/高度调整
                if x == grid_x - 1:
                    # 最后一列使用剩余宽度
                    end_x = width
                else:
                    end_x = start_x + tile_width
                    
                if y == grid_y - 1:
                    # 最后一行使用剩余高度
                    end_y = height
                else:
                    end_y = start_y + tile_height
                
                # 应用重叠（向内扩展）
                tile_start_x = max(0, start_x - overlap_w) if x > 0 else start_x
                tile_start_y = max(0, start_y - overlap_h) if y > 0 else start_y
                tile_end_x = min(width, end_x + overlap_w) if x < grid_x - 1 else end_x
                tile_end_y = min(height, end_y + overlap_h) if y < grid_y - 1 else end_y
                
                bounds.append({
                    "grid_pos": (x, y),
                    "index": y * grid_x + x,
                    "bounds": (tile_start_x, tile_start_y, tile_end_x, tile_end_y),
                    "size": (tile_end_x - tile_start_x, tile_end_y - tile_start_y)
                })
        
        return bounds

    def get_output_order_indices(self, grid_x, grid_y, order_type):
        """根据输出顺序类型获取索引顺序"""
        indices = []
        
        if order_type == "row-major":
            # 行优先：从左到右，从上到下
            for y in range(grid_y):
                for x in range(grid_x):
                    indices.append(y * grid_x + x)
                    
        elif order_type == "column-major":
            # 列优先：从上到下，从左到右
            for x in range(grid_x):
                for y in range(grid_y):
                    indices.append(y * grid_x + x)
                    
        elif order_type == "diagonal":
            # 对角线顺序（仅适用于正方形网格）
            if grid_x == grid_y:
                # 对角线顺序：从左上到右下，按对角线分组
                for d in range(grid_x + grid_y - 1):
                    for x in range(max(0, d - grid_y + 1), min(grid_x, d + 1)):
                        y = d - x
                        if y < grid_y:
                            indices.append(y * grid_x + x)
            else:
                # 如果不是正方形网格，使用行优先作为备选
                print(f"⚠️ 对角线顺序仅支持正方形网格，{grid_x}x{grid_y}将使用行优先顺序")
                return self.get_output_order_indices(grid_x, grid_y, "row-major")
        
        return indices

    def split_image(self, image, grid_size, custom_width, custom_height, overlap_pixels, output_order, include_original=False, merge_output=True):
        """
        将输入图像切割成指定网格大小的子图
        
        Args:
            image: 输入图像张量
            grid_size: 网格大小，如 "2x2", "3x3" 等
            custom_width: 自定义网格宽度（当grid_size="custom"时使用）
            custom_height: 自定义网格高度（当grid_size="custom"时使用）
            overlap_pixels: 重叠像素数（用于防止切割边缘问题）
            output_order: 输出顺序
            include_original: 是否包含原始图像
            merge_output: 是否合并输出所有分块
        """
        # 解析网格大小
        if grid_size == "custom":
            grid_x = custom_width
            grid_y = custom_height
        else:
            try:
                grid_x, grid_y = map(int, grid_size.split('x'))
            except:
                print(f"⚠️ 无效的网格大小: {grid_size}，使用默认 2x2")
                grid_x, grid_y = 2, 2
        
        # 检查网格大小是否有效
        if grid_x <= 0 or grid_y <= 0:
            print(f"⚠️ 无效的网格大小: {grid_x}x{grid_y}，使用默认 2x2")
            grid_x, grid_y = 2, 2
        
        # 转换为 PIL 图像
        pil_images = self.tensor_to_pil(image)
        
        if not pil_images:
            empty_tensor = torch.zeros((1, 256, 256, 3))
            outputs = [empty_tensor] * 17
            return tuple(outputs)
        
        # 只处理第一张图像（如果有多张，只取第一张）
        pil_img = pil_images[0]
        
        # 确保图像为 RGB 模式
        img = pil_img.convert("RGB")
        width, height = img.size
        
        # 检查图像是否足够大
        if width < grid_x or height < grid_y:
            print(f"⚠️ 图像尺寸过小 ({width}x{height})，无法进行 {grid_x}x{grid_y} 切割")
            img_tensor = self.pil_to_single_tensor(img)
            outputs = [img_tensor] + [torch.zeros((1, 256, 256, 3))] * 16
            return tuple(outputs)
        
        # 计算总的分块数
        total_tiles = grid_x * grid_y
        
        # 计算所有分块的边界
        bounds_list = self.calculate_tile_bounds(width, height, grid_x, grid_y, overlap_pixels)
        
        # 获取输出顺序的索引
        order_indices = self.get_output_order_indices(grid_x, grid_y, output_order)
        
        # 准备分块列表
        tiles = []
        
        # 按照指定顺序切割图像
        for idx in order_indices:
            if idx < len(bounds_list):
                bound_info = bounds_list[idx]
                try:
                    tile = img.crop(bound_info["bounds"])
                    tiles.append(tile)
                except Exception as e:
                    print(f"⚠️ 切割分块 {bound_info['grid_pos']} 失败: {e}")
                    # 如果切割失败，添加空白图像
                    blank_tile = Image.new("RGB", bound_info["size"], (128, 128, 128))
                    tiles.append(blank_tile)
        
        # 转换原始图像为张量
        merged_tiles_list = tiles.copy()
        if include_original:
            merged_tiles_list.insert(0, img)

        if merged_tiles_list:
            merged_tensor = self.pil_to_tensor(merged_tiles_list)
        else:
            merged_tensor = torch.zeros((1, 256, 256, 3))
        
        # 转换分块为单独的张量
        tile_tensors = []
        for tile in tiles:
            tile_tensor = self.pil_to_single_tensor(tile)
            tile_tensors.append(tile_tensor)
        
        # 准备所有输出
        outputs = []
        
        outputs.append(merged_tensor)

        # 单独的分块图像 (tile_01 到 tile_16)
        for i in range(16):
            if i < len(tile_tensors):
                outputs.append(tile_tensors[i])
            else:
                outputs.append(torch.zeros((1, 256, 256, 3)))
        
        # 打印调试信息
        print(f"🔪 图像切割 ({grid_x}x{grid_y}):")
        print(f"  原始尺寸: {width}x{height}")
        print(f"  网格大小: {grid_x}x{grid_y}")
        print(f"  总分割数: {total_tiles}")
        print(f"  重叠像素: {overlap_pixels}")
        print(f"  输出顺序: {output_order}")
        print(f"  包含原图: {include_original}")
        print(f"  合并输出: {merge_output}")
        print(f"  成功切割: {len(tiles)}/{total_tiles} 个分块")
        
        # 显示分块信息
        for i, bound_info in enumerate(bounds_list[:min(4, len(bounds_list))]):
            x, y = bound_info['grid_pos']
            tile_w, tile_h = bound_info['size']
            print(f"  分块({x},{y}): {tile_w}x{tile_h}, 区域: {bound_info['bounds']}")
        
        return tuple(outputs)

    @classmethod
    def VALIDATE_INPUTS(cls, grid_size, custom_width, custom_height, **kwargs):
        """验证输入参数"""
        if grid_size == "custom":
            if custom_width <= 0 or custom_height <= 0:
                return "自定义网格大小必须为正整数"
            if custom_width > 10 or custom_height > 10:
                return "自定义网格大小不能超过10x10"
        else:
            try:
                grid_x, grid_y = map(int, grid_size.split('x'))
                if grid_x <= 0 or grid_y <= 0:
                    return "网格大小必须为正整数"
                if grid_x > 10 or grid_y > 10:
                    return "网格大小不能超过10x10"
            except:
                return "网格大小格式无效，请使用如 '2x2', '3x3' 的格式"
        return True


# ============== 节点注册部分 ==============
NODE_CLASS_MAPPINGS = {
    "ImageSplit": ImageSplit,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "ImageSplit": "Image Split (图像切割)",
}

__all__ = ['NODE_CLASS_MAPPINGS', 'NODE_DISPLAY_NAME_MAPPINGS']
