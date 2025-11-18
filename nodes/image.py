import torch
import numpy as np
from PIL import Image, ImageColor, ImageDraw, ImageFont
import os
import glob
import random

class PadImageToCanvas:
    """
    一个 ComfyUI 节点，用于将输入图像放置到指定尺寸和颜色的新画布上。
    用户可以控制图像是居中还是通过自定义的左边距和顶边距来定位。
    """

    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "image": ("IMAGE",),
                "width": ("INT", {"default": 512, "min": 64, "max": 8192, "step": 8}),
                "height": ("INT", {"default": 512, "min": 64, "max": 8192, "step": 8}),
                "fill_color": ("STRING", {"default": "#FFFFFF"}),
                "center": ("BOOLEAN", {"default": True}),
                "left_padding": ("INT", {"default": 0, "min": -8192, "max": 8192, "step": 1}),
                "top_padding": ("INT", {"default": 0, "min": -8192, "max": 8192, "step": 1}),
            }
        }

    RETURN_TYPES = ("IMAGE",)
    FUNCTION = "pad_image"
    CATEGORY = "kktools/Image"

    def tensor_to_pil(self, img_tensor):
        """将 ComfyUI 图像张量 (Batch, H, W, C) 转换为 PIL 图像列表"""
        batch_size, _, _, _ = img_tensor.shape
        images = []
        for i in range(batch_size):
            img_np = 255. * img_tensor[i].cpu().numpy()
            img = Image.fromarray(np.clip(img_np, 0, 255).astype(np.uint8))
            images.append(img)
        return images

    def pil_to_tensor(self, pil_images):
        """将 PIL 图像列表转换回 ComfyUI 图像张量"""
        tensors = []
        for img in pil_images:
            img_np = np.array(img).astype(np.float32) / 255.0
            tensor = torch.from_numpy(img_np)[None,]
            tensors.append(tensor)
        return torch.cat(tensors, dim=0)

    def pad_image(self, image, width, height, fill_color, center, left_padding, top_padding):
        # 1. 将输入的张量转换为 PIL 图像
        pil_images = self.tensor_to_pil(image)
        
        processed_images = []

        # 2. 解析填充颜色 (支持 #RGB, #RRGGBB, #RRGGBBAA)
        try:
            # 尝试获取 RGBA 颜色，以便支持透明背景
            bg_color = ImageColor.getcolor(fill_color, "RGBA")
        except ValueError:
            # 如果失败（例如颜色字符串不含 alpha），则默认为 RGB
            bg_color = ImageColor.getcolor(fill_color, "RGB")
            # 如果是 RGB，我们需要手动添加一个不透明的 Alpha
            bg_color = bg_color + (255,)

        for img in pil_images:
            # 3. 确保输入图像为 RGBA 模式，以便在粘贴时正确处理透明度
            img_rgba = img.convert("RGBA")
            img_width, img_height = img_rgba.size

            # 4. 创建新的画布（始终为 RGBA 模式）
            canvas = Image.new("RGBA", (width, height), bg_color)

            # 5. 计算粘贴位置
            if center:
                # 居中对齐
                x_pos = (width - img_width) // 2
                y_pos = (height - img_height) // 2
            else:
                # 自定义边距
                x_pos = left_padding
                y_pos = top_padding

            # 6. 将图像粘贴到画布上
            # 我们使用 img_rgba 的 alpha 通道作为蒙版，以确保透明区域正确
            canvas.paste(img_rgba, (x_pos, y_pos), mask=img_rgba)

            # 7. 根据背景色是否透明，决定最终输出是 RGB 还是 RGBA
            if bg_color[3] == 255: # 如果背景是不透明的
                processed_images.append(canvas.convert("RGB"))
            else: # 如果背景是透明的
                processed_images.append(canvas)

        # 8. 将处理后的 PIL 图像转换回张量
        output_tensor = self.pil_to_tensor(processed_images)
        
        return (output_tensor,)

class ImageFrame:
    """
    图像边框节点，用于显示1-3张图像进行视觉比较，并添加边框和标签
    """

    @classmethod
    def INPUT_TYPES(s):
        # 获取可用字体列表
        font_options = s.get_font_options()
        
        return {
            "required": {
                "image_count": ("INT", {"default": 2, "min": 1, "max": 3, "step": 1}),
                "footer_height": ("INT", {"default": 100, "min": 0, "max": 1000, "step": 10}),
                "font_size": ("INT", {"default": 50, "min": 10, "max": 200, "step": 5}),
                "border_thickness": ("INT", {"default": 20, "min": 0, "max": 200, "step": 5}),
                "mode": (["horizontal", "vertical", "grid"], {"default": "horizontal"}),
                "background_color": ("STRING", {"default": "#FFFFFF"}),
                "text_color": ("STRING", {"default": "#000000"}),
                "text_margin": ("INT", {"default": 10, "min": 0, "max": 200, "step": 5}),
                "font_selection": (font_options, {"default": "Arial"}),
            },
            "optional": {
                "image1": ("IMAGE",),
                "image2": ("IMAGE",),
                "image3": ("IMAGE",),
                "label1": ("STRING", {"default": "图像1"}),
                "label2": ("STRING", {"default": "图像2"}),
                "label3": ("STRING", {"default": "图像3"}),
            }
        }

    RETURN_TYPES = ("IMAGE",)
    FUNCTION = "create_image_frame"
    CATEGORY = "kktools/Image"

    @classmethod
    def get_font_options(cls):
        """获取可用的字体选项列表，按照1自定义文件2系统文件的顺序"""
        font_options = []
        
        # 1. 首先添加自定义字体文件
        custom_fonts = cls.find_custom_fonts()
        font_options.extend(custom_fonts)
        
        # 2. 添加系统字体
        system_fonts = [
            "Arial",
            "Arial Bold", 
            "Arial Italic",
            "Arial Bold Italic",
            "DejaVu Sans",
            "DejaVu Sans Bold",
            "DejaVu Sans Oblique",
            "Liberation Sans",
            "Liberation Sans Bold",
            "Liberation Sans Italic"
        ]
        font_options.extend(system_fonts)
        
        return font_options

    @classmethod
    def find_custom_fonts(cls):
        """查找自定义字体文件 - 在 ComfyUI/custom_nodes/Comfyui-XingYue/fonts 中"""
        custom_fonts = []
        
        # 获取当前脚本所在目录
        current_dir = os.path.dirname(os.path.abspath(__file__))
        
        # 主要字体目录：ComfyUI/custom_nodes/Comfyui-XingYue/fonts
        main_font_dir = os.path.join(current_dir, 'fonts')
        
        # 备用字体目录（兼容旧路径）
        backup_font_dirs = [
            os.path.join(current_dir, '..', 'fonts'),
            os.path.join(current_dir, '..', '..', 'fonts'),
        ]
        
        # 支持的字体文件扩展名
        extensions = ['.ttf', '.otf', '.ttc']
        
        # 首先检查主要字体目录
        font_dirs_to_check = [main_font_dir] + backup_font_dirs
        
        for font_dir in font_dirs_to_check:
            if not os.path.exists(font_dir):
                continue
                
            try:
                for file in os.listdir(font_dir):
                    file_path = os.path.join(font_dir, file)
                    if os.path.isfile(file_path) and any(file.lower().endswith(ext) for ext in extensions):
                        # 使用文件名（不带扩展名）作为显示名称
                        font_name = os.path.splitext(file)[0]
                        if font_name not in custom_fonts:
                            custom_fonts.append(font_name)
                            print(f"✅ 找到自定义字体: {font_name} -> {file_path}")
            except Exception as e:
                print(f"⚠️ 扫描字体目录时出错 {font_dir}: {e}")
        
        print(f"🎯 共找到 {len(custom_fonts)} 个自定义字体")
        return custom_fonts

    def tensor_to_pil(self, img_tensor):
        """将 ComfyUI 图像张量转换为 PIL 图像"""
        if len(img_tensor.shape) == 4:  # Batch of images
            batch_size, _, _, _ = img_tensor.shape
            images = []
            for i in range(batch_size):
                img_np = 255. * img_tensor[i].cpu().numpy()
                img = Image.fromarray(np.clip(img_np, 0, 255).astype(np.uint8))
                images.append(img)
            return images
        else:
            img_np = 255. * img_tensor.cpu().numpy()
            return [Image.fromarray(np.clip(img_np, 0, 255).astype(np.uint8))]

    def pil_to_tensor(self, pil_images):
        """将 PIL 图像列表转换回 ComfyUI 图像张量"""
        tensors = []
        for img in pil_images:
            img_np = np.array(img).astype(np.float32) / 255.0
            tensor = torch.from_numpy(img_np)[None,]
            tensors.append(tensor)
        return torch.cat(tensors, dim=0)

    def find_font_file(self, font_name):
        """根据字体名称查找字体文件 - 在 ComfyUI/custom_nodes/Comfyui-XingYue/fonts 中"""
        # 获取当前脚本所在目录
        current_dir = os.path.dirname(os.path.abspath(__file__))
        
        # 主要字体目录：ComfyUI/custom_nodes/Comfyui-XingYue/fonts
        main_font_dir = os.path.join(current_dir, 'fonts')
        
        # 备用字体目录（兼容旧路径）
        backup_font_dirs = [
            os.path.join(current_dir, '..', 'fonts'),
            os.path.join(current_dir, '..', '..', 'fonts'),
        ]
        
        # 支持的字体文件扩展名
        extensions = ['.ttf', '.otf', '.ttc']
        
        # 首先检查主要字体目录
        font_dirs_to_check = [main_font_dir] + backup_font_dirs
        
        # 在所有字体目录中搜索
        for font_dir in font_dirs_to_check:
            if not os.path.exists(font_dir):
                continue
                
            for root, dirs, files in os.walk(font_dir):
                for file in files:
                    file_lower = file.lower()
                    name_without_ext = os.path.splitext(file)[0]
                    
                    # 检查文件名是否匹配
                    if (font_name.lower() == file_lower or 
                        font_name.lower() == name_without_ext.lower()):
                        font_path = os.path.join(root, file)
                        if os.path.exists(font_path):
                            return font_path
        
        return None

    def get_font(self, font_size, font_selection="Arial"):
        """加载字体 - 按照1自定义文件2系统文件的顺序"""
        # 1. 首先尝试作为自定义字体文件加载
        found_font_path = self.find_font_file(font_selection)
        if found_font_path:
            try:
                custom_font = ImageFont.truetype(found_font_path, font_size)
                print(f"✅ 使用自定义字体: {found_font_path}")
                return custom_font
            except Exception as e:
                print(f"⚠️ 无法加载自定义字体文件 {found_font_path}: {e}")
        
        # 2. 如果自定义字体失败，尝试系统字体
        try:
            # 根据字体选择确定系统字体
            font_mapping = {
                "Arial": "arial.ttf",
                "Arial Bold": "arialbd.ttf", 
                "Arial Italic": "ariali.ttf",
                "Arial Bold Italic": "arialbi.ttf",
                "DejaVu Sans": "DejaVuSans.ttf",
                "DejaVu Sans Bold": "DejaVuSans-Bold.ttf",
                "DejaVu Sans Oblique": "DejaVuSans-Oblique.ttf",
                "Liberation Sans": "LiberationSans-Regular.ttf",
                "Liberation Sans Bold": "LiberationSans-Bold.ttf",
                "Liberation Sans Italic": "LiberationSans-Italic.ttf"
            }
            
            font_file = font_mapping.get(font_selection)
            
            if font_file:
                try:
                    system_font = ImageFont.truetype(font_file, font_size)
                    print(f"✅ 使用系统字体: {font_file}")
                    return system_font
                except:
                    pass
            
            # 如果映射失败，尝试直接加载常见字体
            font_names = [
                "arial.ttf", "arialbd.ttf", "ariali.ttf", "arialbi.ttf",
                "DejaVuSans.ttf", "DejaVuSans-Bold.ttf", "DejaVuSans-Oblique.ttf",
                "LiberationSans-Regular.ttf", "LiberationSans-Bold.ttf", "LiberationSans-Italic.ttf"
            ]
            
            for font_name in font_names:
                try:
                    system_font = ImageFont.truetype(font_name, font_size)
                    print(f"✅ 使用系统字体: {font_name}")
                    return system_font
                except:
                    continue
            
            # 如果系统字体都失败，使用备用字体
            print(f"⚠️ 无法加载系统字体，使用备用字体")
            return ImageFont.load_default()
            
        except Exception as e:
            print(f"⚠️ 字体加载失败: {e}, 使用备用字体")
            return ImageFont.load_default()

    def create_image_frame(self, image_count, footer_height, font_size, border_thickness, mode, background_color, text_color, text_margin, font_selection, image1=None, image2=None, image3=None, label1="图像1", label2="图像2", label3="图像3"):
        # 收集所有输入的图像
        input_images = []
        input_labels = [label1, label2, label3]
        
        if image1 is not None:
            input_images.append(image1)
        if image2 is not None:
            input_images.append(image2)
        if image3 is not None:
            input_images.append(image3)
        
        # 根据 image_count 限制实际使用的图像数量
        actual_image_count = min(image_count, len(input_images))
        if actual_image_count == 0:
            # 如果没有输入图像，返回空图像
            empty_tensor = torch.zeros((1, 512, 512, 3))
            return (empty_tensor,)
        
        # 转换为 PIL 图像
        pil_images_list = []
        for i in range(actual_image_count):
            pil_images = self.tensor_to_pil(input_images[i])
            pil_images_list.append(pil_images)
        
        # 确定批处理大小（取所有图像批次的最小值）
        batch_size = min(len(images) for images in pil_images_list if len(images) > 0)
        
        processed_images = []
        
        # 解析颜色
        try:
            bg_color = ImageColor.getcolor(background_color, "RGB")
        except:
            bg_color = (255, 255, 255)  # 默认白色
            
        try:
            txt_color = ImageColor.getcolor(text_color, "RGB")
        except:
            txt_color = (0, 0, 0)  # 默认黑色

        for batch_idx in range(batch_size):
            images = []
            image_sizes = []
            
            # 获取当前批次的所有图像
            for i in range(actual_image_count):
                img = pil_images_list[i][batch_idx].convert("RGB")
                images.append(img)
                image_sizes.append(img.size)
            
            # 加载字体（按照1自定义文件2系统文件的顺序）
            font = self.get_font(font_size, font_selection)
            
            if mode == "horizontal" or (mode == "grid" and actual_image_count <= 2):
                # 水平排列（1-2张图）或网格模式下的1-2张图
                total_width = sum(size[0] for size in image_sizes) + border_thickness * (actual_image_count + 1)
                total_height = max(size[1] for size in image_sizes) + border_thickness * 2 + footer_height
                
                # 创建画布
                canvas = Image.new("RGB", (total_width, total_height), bg_color)
                draw = ImageDraw.Draw(canvas)
                
                # 放置图像
                x_offset = border_thickness
                for i, img in enumerate(images):
                    canvas.paste(img, (x_offset, border_thickness))
                    
                    # 添加标签
                    if footer_height > 0 and font_size > 0:
                        text_bbox = draw.textbbox((0, 0), input_labels[i], font=font)
                        text_width = text_bbox[2] - text_bbox[0]
                        text_x = x_offset + (image_sizes[i][0] - text_width) // 2
                        text_y = total_height - footer_height + text_margin
                        draw.text((text_x, text_y), input_labels[i], font=font, fill=txt_color)
                    
                    x_offset += image_sizes[i][0] + border_thickness
                    
            elif mode == "vertical" or (mode == "grid" and actual_image_count == 1):
                # 垂直排列（1-3张图）或网格模式下的1张图
                total_width = max(size[0] for size in image_sizes) + border_thickness * 2
                total_height = sum(size[1] for size in image_sizes) + border_thickness * (actual_image_count + 1) + footer_height
                
                # 创建画布
                canvas = Image.new("RGB", (total_width, total_height), bg_color)
                draw = ImageDraw.Draw(canvas)
                
                # 放置图像
                y_offset = border_thickness
                for i, img in enumerate(images):
                    canvas.paste(img, (border_thickness, y_offset))
                    
                    # 添加标签
                    if footer_height > 0 and font_size > 0:
                        text_bbox = draw.textbbox((0, 0), input_labels[i], font=font)
                        text_width = text_bbox[2] - text_bbox[0]
                        text_x = (total_width - text_width) // 2
                        text_y = y_offset + image_sizes[i][1] + text_margin
                        draw.text((text_x, text_y), input_labels[i], font=font, fill=txt_color)
                    
                    y_offset += image_sizes[i][1] + border_thickness
                    
            else:  # grid mode with 3 images
                # 网格模式排列3张图（2x2网格，但只使用3个位置）
                max_width = max(size[0] for size in image_sizes)
                max_height = max(size[1] for size in image_sizes)
                
                total_width = max_width * 2 + border_thickness * 3
                total_height = max_height * 2 + border_thickness * 3 + footer_height
                
                # 创建画布
                canvas = Image.new("RGB", (total_width, total_height), bg_color)
                draw = ImageDraw.Draw(canvas)
                
                # 定义网格位置
                grid_positions = [
                    (border_thickness, border_thickness),  # 左上
                    (max_width + border_thickness * 2, border_thickness),  # 右上
                    (border_thickness, max_height + border_thickness * 2),  # 左下
                ]
                
                # 放置图像
                for i, img in enumerate(images):
                    if i < 3:  # 确保不超过3张图
                        x, y = grid_positions[i]
                        # 居中放置图像
                        img_x = x + (max_width - image_sizes[i][0]) // 2
                        img_y = y + (max_height - image_sizes[i][1]) // 2
                        canvas.paste(img, (img_x, img_y))
                        
                        # 添加标签
                        if footer_height > 0 and font_size > 0:
                            text_bbox = draw.textbbox((0, 0), input_labels[i], font=font)
                            text_width = text_bbox[2] - text_bbox[0]
                            
                            if i == 0:  # 左上
                                text_x = x + (max_width - text_width) // 2
                                text_y = y + max_height + text_margin
                            elif i == 1:  # 右上
                                text_x = x + (max_width - text_width) // 2
                                text_y = y + max_height + text_margin
                            else:  # 左下
                                text_x = x + (max_width - text_width) // 2
                                text_y = y + max_height + text_margin
                            
                            draw.text((text_x, text_y), input_labels[i], font=font, fill=txt_color)
            
            processed_images.append(canvas)
        
        # 转换回张量
        output_tensor = self.pil_to_tensor(processed_images)
        return (output_tensor,)

class Resize:
    """
    图像和蒙版同步调整尺寸节点
    用于同时调整图像和对应蒙版的尺寸，保持两者尺寸一致
    """

    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "image": ("IMAGE",),
                "width": ("INT", {"default": 512, "min": 64, "max": 8192, "step": 8}),
                "height": ("INT", {"default": 512, "min": 64, "max": 8192, "step": 8}),
                "resize_mode": (["scale_width", "scale_height", "scale_long", "scale_short", "stretch", "fit_padding", "fill_crop"], {"default": "stretch"}),
                "interpolation": (["nearest", "bilinear", "bicubic", "lanczos"], {"default": "lanczos"}),
            },
            "optional": {
                "mask": ("MASK",),
            }
        }

    RETURN_TYPES = ("IMAGE", "MASK")
    RETURN_NAMES = ("image", "mask")
    FUNCTION = "resize_both"
    CATEGORY = "kktools/Image"

    def tensor_to_pil(self, img_tensor):
        """将 ComfyUI 图像张量转换为 PIL 图像"""
        if len(img_tensor.shape) == 4:  # Batch of images
            batch_size, _, _, _ = img_tensor.shape
            images = []
            for i in range(batch_size):
                img_np = 255. * img_tensor[i].cpu().numpy()
                img = Image.fromarray(np.clip(img_np, 0, 255).astype(np.uint8))
                images.append(img)
            return images
        else:
            img_np = 255. * img_tensor.cpu().numpy()
            return [Image.fromarray(np.clip(img_np, 0, 255).astype(np.uint8))]

    def mask_to_pil(self, mask_tensor):
        """将蒙版张量转换为 PIL 图像"""
        if mask_tensor is None:
            return None
            
        if len(mask_tensor.shape) == 4:  # Batch of masks
            batch_size, _, _, _ = mask_tensor.shape
            masks = []
            for i in range(batch_size):
                mask_np = mask_tensor[i].cpu().numpy() * 255.0
                mask = Image.fromarray(np.clip(mask_np, 0, 255).astype(np.uint8))
                masks.append(mask)
            return masks
        else:
            mask_np = mask_tensor.cpu().numpy() * 255.0
            return [Image.fromarray(np.clip(mask_np, 0, 255).astype(np.uint8))]

    def pil_to_tensor(self, pil_images):
        """将 PIL 图像列表转换回 ComfyUI 图像张量"""
        tensors = []
        for img in pil_images:
            img_np = np.array(img).astype(np.float32) / 255.0
            tensor = torch.from_numpy(img_np)[None,]
            tensors.append(tensor)
        return torch.cat(tensors, dim=0)

    def pil_to_mask(self, pil_masks):
        """将 PIL 蒙版列表转换回 ComfyUI 蒙版张量"""
        if pil_masks is None:
            return None
            
        tensors = []
        for mask in pil_masks:
            mask_np = np.array(mask).astype(np.float32) / 255.0
            tensor = torch.from_numpy(mask_np)[None,]
            tensors.append(tensor)
        return torch.cat(tensors, dim=0)

    def resize_both(self, image, width, height, resize_mode, interpolation, mask=None):
        # 转换为 PIL 图像
        pil_images = self.tensor_to_pil(image)
        
        # 转换为 PIL 蒙版（如果存在）
        pil_masks = self.mask_to_pil(mask) if mask is not None else None
        
        # 确定批处理大小
        batch_size = len(pil_images)
        if pil_masks is not None:
            batch_size = min(batch_size, len(pil_masks))
        
        if batch_size == 0:
            # 如果没有输入，返回空张量
            empty_image = torch.zeros((1, height, width, 3))
            empty_mask = torch.zeros((1, height, width, 1)) if mask is not None else None
            return (empty_image, empty_mask) if empty_mask is not None else (empty_image,)
        
        # 设置插值方法
        interpolation_map = {
            "nearest": Image.Resampling.NEAREST,
            "bilinear": Image.Resampling.BILINEAR,
            "bicubic": Image.Resampling.BICUBIC,
            "lanczos": Image.Resampling.LANCZOS
        }
        interp_method = interpolation_map.get(interpolation, Image.Resampling.LANCZOS)
        
        resized_images = []
        resized_masks = [] if pil_masks is not None else None
        
        for batch_idx in range(batch_size):
            img = pil_images[batch_idx].convert("RGB")
            msk = pil_masks[batch_idx].convert("L") if pil_masks is not None else None
            
            if resize_mode == "stretch":
                # 直接拉伸到目标尺寸
                resized_img = img.resize((width, height), interp_method)
                if msk is not None:
                    resized_mask = msk.resize((width, height), Image.Resampling.NEAREST)
                
            elif resize_mode == "scale_width":
                # 按宽度等比缩放
                scale_factor = width / img.width
                new_height = int(img.height * scale_factor)
                resized_img = img.resize((width, new_height), interp_method)
                if msk is not None:
                    resized_mask = msk.resize((width, new_height), Image.Resampling.NEAREST)
                
            elif resize_mode == "scale_height":
                # 按高度等比缩放
                scale_factor = height / img.height
                new_width = int(img.width * scale_factor)
                resized_img = img.resize((new_width, height), interp_method)
                if msk is not None:
                    resized_mask = msk.resize((new_width, height), Image.Resampling.NEAREST)
                
            elif resize_mode == "scale_long":
                # 按长边等比缩放
                img_ratio = img.width / img.height
                target_ratio = width / height
                
                if img_ratio > target_ratio:
                    # 图像较宽，按宽度缩放
                    scale_factor = width / img.width
                    new_height = int(img.height * scale_factor)
                    resized_img = img.resize((width, new_height), interp_method)
                    if msk is not None:
                        resized_mask = msk.resize((width, new_height), Image.Resampling.NEAREST)
                else:
                    # 图像较高，按高度缩放
                    scale_factor = height / img.height
                    new_width = int(img.width * scale_factor)
                    resized_img = img.resize((new_width, height), interp_method)
                    if msk is not None:
                        resized_mask = msk.resize((new_width, height), Image.Resampling.NEAREST)
                
            elif resize_mode == "scale_short":
                # 按短边等比缩放
                img_ratio = img.width / img.height
                target_ratio = width / height
                
                if img_ratio > target_ratio:
                    # 图像较宽，按高度缩放
                    scale_factor = height / img.height
                    new_width = int(img.width * scale_factor)
                    resized_img = img.resize((new_width, height), interp_method)
                    if msk is not None:
                        resized_mask = msk.resize((new_width, height), Image.Resampling.NEAREST)
                else:
                    # 图像较高，按宽度缩放
                    scale_factor = width / img.width
                    new_height = int(img.height * scale_factor)
                    resized_img = img.resize((width, new_height), interp_method)
                    if msk is not None:
                        resized_mask = msk.resize((width, new_height), Image.Resampling.NEAREST)
                
            elif resize_mode == "fit_padding":
                # 等比缩放并填充到目标尺寸
                img_ratio = img.width / img.height
                target_ratio = width / height
                
                if img_ratio > target_ratio:
                    # 图像较宽，填充高度
                    new_height = int(width / img_ratio)
                    resized_img = img.resize((width, new_height), interp_method)
                    
                    # 创建填充画布
                    canvas = Image.new("RGB", (width, height), (0, 0, 0))
                    pad_top = (height - new_height) // 2
                    canvas.paste(resized_img, (0, pad_top))
                    resized_img = canvas
                    
                    if msk is not None:
                        resized_mask = msk.resize((width, new_height), Image.Resampling.NEAREST)
                        mask_canvas = Image.new("L", (width, height), 0)
                        mask_canvas.paste(resized_mask, (0, pad_top))
                        resized_mask = mask_canvas
                else:
                    # 图像较高，填充宽度
                    new_width = int(height * img_ratio)
                    resized_img = img.resize((new_width, height), interp_method)
                    
                    # 创建填充画布
                    canvas = Image.new("RGB", (width, height), (0, 0, 0))
                    pad_left = (width - new_width) // 2
                    canvas.paste(resized_img, (pad_left, 0))
                    resized_img = canvas
                    
                    if msk is not None:
                        resized_mask = msk.resize((new_width, height), Image.Resampling.NEAREST)
                        mask_canvas = Image.new("L", (width, height), 0)
                        mask_canvas.paste(resized_mask, (pad_left, 0))
                        resized_mask = mask_canvas
                
            else:  # fill_crop
                # 等比缩放并裁剪到目标尺寸
                img_ratio = img.width / img.height
                target_ratio = width / height
                
                if img_ratio > target_ratio:
                    # 图像较宽，裁剪宽度
                    new_height = height
                    new_width = int(height * img_ratio)
                    resized_img = img.resize((new_width, new_height), interp_method)
                    
                    # 居中裁剪
                    left = (new_width - width) // 2
                    resized_img = resized_img.crop((left, 0, left + width, height))
                    
                    if msk is not None:
                        resized_mask = msk.resize((new_width, new_height), Image.Resampling.NEAREST)
                        resized_mask = resized_mask.crop((left, 0, left + width, height))
                else:
                    # 图像较高，裁剪高度
                    new_width = width
                    new_height = int(width / img_ratio)
                    resized_img = img.resize((new_width, new_height), interp_method)
                    
                    # 居中裁剪
                    top = (new_height - height) // 2
                    resized_img = resized_img.crop((0, top, width, top + height))
                    
                    if msk is not None:
                        resized_mask = msk.resize((new_width, new_height), Image.Resampling.NEAREST)
                        resized_mask = resized_mask.crop((0, top, width, top + height))
            
            resized_images.append(resized_img)
            if msk is not None and resized_masks is not None:
                resized_masks.append(resized_mask)
        
        # 转换回张量
        output_image = self.pil_to_tensor(resized_images)
        output_mask = self.pil_to_mask(resized_masks) if resized_masks is not None else None
        
        # 如果没有蒙版输入，返回空的蒙版张量
        if output_mask is None:
            output_mask = torch.zeros((batch_size, height, width, 1))
        
        return (output_image, output_mask)

class GetImage:
    """
    获取图像尺寸节点
    用于提取图像的宽度和高度信息
    """

    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "image": ("IMAGE",),
            }
        }

    RETURN_TYPES = ("INT", "INT")
    RETURN_NAMES = ("width", "height")
    FUNCTION = "get_image_size"
    CATEGORY = "kktools/Image"

    def get_image_size(self, image):
        # 获取图像的基本信息
        batch_size, height, width, channels = image.shape
        
        return (width, height)

class BatchImageLoader:
    """批量图像加载节点 - 支持顺序/倒序/随机加载和加载间隔"""
    
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "directory": ("STRING", {
                    "default": "",
                    "multiline": False,
                    "placeholder": "输入图像文件夹路径"
                }),
                "load_order": (["sequential", "reverse", "random"], {
                    "default": "sequential"
                }),
                "load_interval": ("INT", {
                    "default": 1,
                    "min": 1,
                    "max": 100,
                    "step": 1,
                    "display": "number"
                }),
                "start_index": ("INT", {
                    "default": 0,
                    "min": 0,
                    "max": 9999,
                    "step": 1,
                    "display": "number"
                }),
                "max_images": ("INT", {
                    "default": 0,
                    "min": 0,
                    "max": 1000,
                    "step": 1,
                    "display": "number"
                }),
                "file_extensions": (["all", "png", "jpg", "jpeg", "webp", "bmp", "tiff"], {
                    "default": "all"
                }),
                "seed": ("INT", {
                    "default": 0,
                    "min": 0,
                    "max": 9999999999,
                    "step": 1,
                    "display": "number"
                }),
            },
            "optional": {
                "batch_index": ("INT", {
                    "default": 0,
                    "min": 0,
                    "max": 9999,
                    "step": 1
                }),
            }
        }
    
    RETURN_TYPES = ("IMAGE", "MASK", "INT", "STRING")
    RETURN_NAMES = ("images", "masks", "loaded_count", "file_info")
    FUNCTION = "load_images"
    CATEGORY = "kktools/Image"
    
    def load_images(self, directory, load_order, load_interval, start_index, max_images, file_extensions, seed, batch_index=0):
        """
        批量加载图像
        
        Args:
            directory: 图像文件夹路径
            load_order: 加载顺序 (sequential=顺序, reverse=倒序, random=随机)
            load_interval: 加载间隔 (每N张加载1张)
            start_index: 起始索引
            max_images: 最大加载数量 (0=无限制)
            file_extensions: 文件扩展名过滤
            seed: 随机种子 (用于随机排序)
            batch_index: 批次索引 (用于分批次加载)
            
        Returns:
            (图像张量, 蒙版张量, 加载数量, 文件信息)
        """
        try:
            # 检查目录是否存在
            if not directory or not os.path.exists(directory):
                error_msg = f"目录不存在: {directory}"
                print(f"BatchImageLoader Error: {error_msg}")
                empty_tensor = torch.zeros((1, 512, 512, 3))
                empty_mask = torch.zeros((1, 512, 512, 1))
                return (empty_tensor, empty_mask, 0, error_msg)
            
            # 获取支持的图像文件扩展名
            extensions = self._get_supported_extensions(file_extensions)
            
            # 查找所有图像文件
            image_files = []
            for ext in extensions:
                pattern = os.path.join(directory, f"*.{ext}")
                image_files.extend(glob.glob(pattern))
            
            # 按文件名排序
            image_files.sort()
            
            if not image_files:
                error_msg = f"在目录中未找到图像文件: {directory}"
                print(f"BatchImageLoader Error: {error_msg}")
                empty_tensor = torch.zeros((1, 512, 512, 3))
                empty_mask = torch.zeros((1, 512, 512, 1))
                return (empty_tensor, empty_mask, 0, error_msg)
            
            # 根据加载顺序调整文件列表
            if load_order == "reverse":
                image_files.reverse()
            elif load_order == "random":
                # 设置随机种子
                if seed > 0:
                    random.seed(seed)
                random.shuffle(image_files)
                print(f"🎲 使用随机种子 {seed} 打乱文件顺序")
            
            # 应用起始索引
            if start_index > 0:
                image_files = image_files[start_index:]
            
            # 应用加载间隔
            if load_interval > 1:
                image_files = image_files[::load_interval]
            
            # 应用最大数量限制
            if max_images > 0:
                image_files = image_files[:max_images]
            
            # 分批次处理
            total_files = len(image_files)
            if batch_index > 0:
                # 计算批次大小（简单分批次）
                batch_size = max(1, total_files // (batch_index + 1))
                start_idx = batch_index * batch_size
                end_idx = min(start_idx + batch_size, total_files)
                image_files = image_files[start_idx:end_idx]
                print(f"📦 批次处理: 索引 {batch_index}, 范围 {start_idx}-{end_idx}")
            
            if not image_files:
                error_msg = "没有符合条件的图像文件"
                print(f"BatchImageLoader Error: {error_msg}")
                empty_tensor = torch.zeros((1, 512, 512, 3))
                empty_mask = torch.zeros((1, 512, 512, 1))
                return (empty_tensor, empty_mask, 0, error_msg)
            
            # 加载图像
            images = []
            masks = []
            loaded_files = []
            
            for file_path in image_files:
                try:
                    # 加载图像
                    image = Image.open(file_path)
                    image = image.convert("RGB")
                    
                    # 转换为numpy数组并归一化
                    image_np = np.array(image).astype(np.float32) / 255.0
                    image_tensor = torch.from_numpy(image_np)[None,]
                    images.append(image_tensor)
                    
                    # 创建空的蒙版（与图像相同尺寸）
                    mask_tensor = torch.ones((1, image_np.shape[0], image_np.shape[1], 1))
                    masks.append(mask_tensor)
                    
                    loaded_files.append(os.path.basename(file_path))
                    
                    print(f"✅ 加载图像: {os.path.basename(file_path)} - 尺寸: {image.size}")
                    
                except Exception as e:
                    print(f"⚠️ 加载图像失败 {file_path}: {e}")
                    continue
            
            if not images:
                error_msg = "所有图像加载失败"
                print(f"BatchImageLoader Error: {error_msg}")
                empty_tensor = torch.zeros((1, 512, 512, 3))
                empty_mask = torch.zeros((1, 512, 512, 1))
                return (empty_tensor, empty_mask, 0, error_msg)
            
            # 合并所有图像张量
            images_tensor = torch.cat(images, dim=0)
            masks_tensor = torch.cat(masks, dim=0)
            
            # 生成文件信息
            file_info = self._generate_file_info(loaded_files, total_files, load_order, load_interval, start_index, seed, batch_index)
            
            # 打印调试信息
            print(f"BatchImageLoader:")
            print(f"  目录: {directory}")
            print(f"  加载顺序: {load_order}")
            print(f"  加载间隔: {load_interval}")
            print(f"  起始索引: {start_index}")
            print(f"  最大数量: {max_images}")
            print(f"  文件类型: {file_extensions}")
            print(f"  随机种子: {seed}")
            print(f"  批次索引: {batch_index}")
            print(f"  找到文件: {total_files} 个")
            print(f"  实际加载: {len(images)} 个")
            print(f"  输出尺寸: {images_tensor.shape}")
            
            return (images_tensor, masks_tensor, len(images), file_info)
            
        except Exception as e:
            error_msg = f"批量加载图像时出错: {str(e)}"
            print(f"BatchImageLoader Error: {error_msg}")
            empty_tensor = torch.zeros((1, 512, 512, 3))
            empty_mask = torch.zeros((1, 512, 512, 1))
            return (empty_tensor, empty_mask, 0, error_msg)
    
    def _get_supported_extensions(self, file_extensions):
        """获取支持的图像文件扩展名列表"""
        if file_extensions == "all":
            return ["png", "jpg", "jpeg", "webp", "bmp", "tiff", "tif"]
        else:
            return [file_extensions]
    
    def _generate_file_info(self, loaded_files, total_files, load_order, load_interval, start_index, seed, batch_index):
        """生成文件信息字符串"""
        info_parts = []
        
        info_parts.append(f"总共: {total_files} 文件")
        info_parts.append(f"加载: {len(loaded_files)} 文件")
        
        # 加载顺序描述
        order_desc = {
            "sequential": "顺序",
            "reverse": "倒序", 
            "random": f"随机(种子:{seed})"
        }
        info_parts.append(f"顺序: {order_desc.get(load_order, load_order)}")
        
        info_parts.append(f"间隔: {load_interval}")
        info_parts.append(f"起始: {start_index}")
        
        if batch_index > 0:
            info_parts.append(f"批次: {batch_index}")
        
        if loaded_files:
            if len(loaded_files) <= 3:
                files_display = ", ".join(loaded_files)
            else:
                files_display = f"{loaded_files[0]}, {loaded_files[1]}, ... , {loaded_files[-1]}"
            info_parts.append(f"文件: {files_display}")
        
        return " | ".join(info_parts)


# ComfyUI 节点注册
NODE_CLASS_MAPPINGS = {
    "PadImageToCanvas": PadImageToCanvas,
    "ImageFrame": ImageFrame,
    "Resize": Resize,
    "GetImage": GetImage,
    "BatchImageLoader": BatchImageLoader,
}

# 节点在菜单中显示的名称
NODE_DISPLAY_NAME_MAPPINGS = {
    "PadImageToCanvas": "Pad Image to Canvas (图像填充到画布)",
    "ImageFrame": "Image Frame (图像边框)",
    "Resize": "Resize (图像蒙版同步调整)",
    "GetImage": "Get Image (获取图像尺寸)",
    "BatchImageLoader": "Batch Image Loader (批量图像加载)",
}

__all__ = ['NODE_CLASS_MAPPINGS', 'NODE_DISPLAY_NAME_MAPPINGS']