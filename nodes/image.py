import torch
import numpy as np
from PIL import Image, ImageColor, ImageDraw, ImageFont
import os
import glob
import random

class kkPadImageToCanvas:
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
    CATEGORY = "🌟kktools/图像"

    def tensor_to_pil(self, img_tensor):
        """将 ComfyUI 图像张量 (Batch, H, W, C) 转换为 PIL 图像列表"""
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

    def pil_to_tensor(self, pil_images):
        """将 PIL 图像列表转换回 ComfyUI 图像张量"""
        tensors = []
        for img in pil_images:
            img_rgb = img.convert("RGB")
            img_np = np.array(img_rgb).astype(np.float32) / 255.0
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

class kkImageFrame:
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
    CATEGORY = "🌟kktools/图像"

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
            img_np = 255. * img_tensor.cpu().numpy()
            img_np = np.clip(img_np, 0, 255).astype(np.uint8)
            return [Image.fromarray(img_np)]

    def pil_to_tensor(self, pil_images):
        """将 PIL 图像列表转换回 ComfyUI 图像张量"""
        tensors = []
        for img in pil_images:
            img_rgb = img.convert("RGB")
            img_np = np.array(img_rgb).astype(np.float32) / 255.0
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

class kkResize:
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
    CATEGORY = "🌟kktools/图像"

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
            img_np = 255. * img_tensor.cpu().numpy()
            img_np = np.clip(img_np, 0, 255).astype(np.uint8)
            return [Image.fromarray(img_np)]

    def mask_to_pil(self, mask_tensor):
        """将蒙版张量转换为 PIL 图像"""
        if mask_tensor is None:
            return None
            
        if len(mask_tensor.shape) == 4:  # Batch of masks
            batch_size, height, width, _ = mask_tensor.shape
            masks = []
            for i in range(batch_size):
                mask_np = mask_tensor[i].cpu().numpy() * 255.0
                mask_np = np.clip(mask_np, 0, 255).astype(np.uint8)
                mask_np = mask_np.reshape(height, width)
                mask = Image.fromarray(mask_np)
                masks.append(mask)
            return masks
        else:
            mask_np = mask_tensor.cpu().numpy() * 255.0
            mask_np = np.clip(mask_np, 0, 255).astype(np.uint8)
            return [Image.fromarray(mask_np)]

    def pil_to_tensor(self, pil_images):
        """将 PIL 图像列表转换回 ComfyUI 图像张量"""
        tensors = []
        for img in pil_images:
            img_rgb = img.convert("RGB")
            img_np = np.array(img_rgb).astype(np.float32) / 255.0
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
            mask_np = mask_np.reshape(mask_np.shape[0], mask_np.shape[1], 1)
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

class kkGetImage:
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
    CATEGORY = "🌟kktools/图像"

    def get_image_size(self, image):
        # 获取图像的基本信息
        batch_size, height, width, channels = image.shape
        
        return (width, height)

class kkBatchImageLoader:
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
    CATEGORY = "🌟kktools/图像"
    
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
                print(f"kkBatchImageLoader Error: {error_msg}")
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
                print(f"kkBatchImageLoader Error: {error_msg}")
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
                print(f"kkBatchImageLoader Error: {error_msg}")
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
                print(f"kkBatchImageLoader Error: {error_msg}")
                empty_tensor = torch.zeros((1, 512, 512, 3))
                empty_mask = torch.zeros((1, 512, 512, 1))
                return (empty_tensor, empty_mask, 0, error_msg)
            
            # 合并所有图像张量
            images_tensor = torch.cat(images, dim=0)
            masks_tensor = torch.cat(masks, dim=0)
            
            # 生成文件信息
            file_info = self._generate_file_info(loaded_files, total_files, load_order, load_interval, start_index, seed, batch_index)
            
            # 打印调试信息
            print(f"kkBatchImageLoader:")
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
            print(f"kkBatchImageLoader Error: {error_msg}")
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

class kkImageTileSplit2x2:
    """
    图像2x2分块切割节点
    将一张输入图片切割成2x2的四张子图输出
    """

    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "image": ("IMAGE",),
                "overlap_pixels": ("INT", {
                    "default": 0,
                    "min": 0,
                    "max": 512,
                    "step": 1,
                    "display": "number"
                }),
                "output_order": (["top-left,top-right,bottom-left,bottom-right", 
                                 "row-major", 
                                 "column-major"], {
                    "default": "top-left,top-right,bottom-left,bottom-right"
                }),
            }
        }

    RETURN_TYPES = ("IMAGE", "IMAGE", "IMAGE", "IMAGE")
    RETURN_NAMES = ("image_tl", "image_tr", "image_bl", "image_br")
    FUNCTION = "split_image"
    CATEGORY = "🌟kktools/图像"
    OUTPUT_IS_LIST = (True, True, True, True)

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

        max_width = max(img.size[0] for img in pil_images)
        max_height = max(img.size[1] for img in pil_images)
        tensors = []
        for img in pil_images:
            # 确保图像为 RGB 模式
            img_rgb = img.convert("RGB")
            if img_rgb.size != (max_width, max_height):
                padded = Image.new("RGB", (max_width, max_height), (0, 0, 0))
                padded.paste(img_rgb, (0, 0))
                img_rgb = padded
            img_np = np.array(img_rgb).astype(np.float32) / 255.0
            tensor = torch.from_numpy(img_np)[None,]
            tensors.append(tensor)
        
        if tensors:
            return torch.cat(tensors, dim=0)
        else:
            return torch.zeros((1, 256, 256, 3))

    def split_image(self, image, overlap_pixels, output_order):
        """
        将输入图像切割成2x2的四张子图
        
        Args:
            image: 输入图像张量
            overlap_pixels: 重叠像素数（用于防止切割边缘问题）
            output_order: 输出顺序
        """
        # 转换为 PIL 图像
        pil_images = self.tensor_to_pil(image)
        
        if not pil_images:
            # 返回空的张量列表
            empty_tensor = torch.zeros((1, 256, 256, 3))
            return ([empty_tensor], [empty_tensor], [empty_tensor], [empty_tensor])
        
        # 准备输出列表
        top_left_list = []
        top_right_list = []
        bottom_left_list = []
        bottom_right_list = []
        
        for pil_img in pil_images:
            # 确保图像为 RGB 模式
            img = pil_img.convert("RGB")
            width, height = img.size
            
            # 检查图像是否足够大
            if width < 2 or height < 2:
                print(f"⚠️ 图像尺寸过小 ({width}x{height})，无法进行2x2切割")
                # 返回原始图像的4个副本
                top_left_list.append(img)
                top_right_list.append(img)
                bottom_left_list.append(img)
                bottom_right_list.append(img)
                continue
            
            # 计算切割点
            half_width = width // 2
            half_height = height // 2
            
            # 调整重叠像素，确保不会越界
            overlap_w = min(overlap_pixels, half_width // 2)
            overlap_h = min(overlap_pixels, half_height // 2)
            
            # 定义切割区域（考虑重叠）
            # 左上角
            tl_x1 = max(0, 0 - overlap_w)
            tl_y1 = max(0, 0 - overlap_h)
            tl_x2 = min(width, half_width + overlap_w)
            tl_y2 = min(height, half_height + overlap_h)
            
            # 右上角
            tr_x1 = max(0, half_width - overlap_w)
            tr_y1 = max(0, 0 - overlap_h)
            tr_x2 = min(width, width)
            tr_y2 = min(height, half_height + overlap_h)
            
            # 左下角
            bl_x1 = max(0, 0 - overlap_w)
            bl_y1 = max(0, half_height - overlap_h)
            bl_x2 = min(width, half_width + overlap_w)
            bl_y2 = min(height, height)
            
            # 右下角
            br_x1 = max(0, half_width - overlap_w)
            br_y1 = max(0, half_height - overlap_h)
            br_x2 = min(width, width)
            br_y2 = min(height, height)
            
            # 执行切割
            try:
                img_tl = img.crop((tl_x1, tl_y1, tl_x2, tl_y2))
                img_tr = img.crop((tr_x1, tr_y1, tr_x2, tr_y2))
                img_bl = img.crop((bl_x1, bl_y1, bl_x2, bl_y2))
                img_br = img.crop((br_x1, br_y1, br_x2, br_y2))
                
                # 打印调试信息
                print(f"🔪 2x2 图像切割:")
                print(f"  原始尺寸: {width}x{height}")
                print(f"  重叠像素: {overlap_pixels}")
                print(f"  左上: {img_tl.size}, 区域: ({tl_x1},{tl_y1})-({tl_x2},{tl_y2})")
                print(f"  右上: {img_tr.size}, 区域: ({tr_x1},{tr_y1})-({tr_x2},{tr_y2})")
                print(f"  左下: {img_bl.size}, 区域: ({bl_x1},{bl_y1})-({bl_x2},{bl_y2})")
                print(f"  右下: {img_br.size}, 区域: ({br_x1},{br_y1})-({br_x2},{br_y2})")
                
            except Exception as e:
                print(f"⚠️ 图像切割失败: {e}")
                # 如果切割失败，返回原始图像
                img_tl = img
                img_tr = img
                img_bl = img
                img_br = img
            
            # 根据输出顺序添加到对应的列表
            if output_order == "top-left,top-right,bottom-left,bottom-right":
                top_left_list.append(img_tl)
                top_right_list.append(img_tr)
                bottom_left_list.append(img_bl)
                bottom_right_list.append(img_br)
            elif output_order == "row-major":
                # 行优先：第一行，第二行
                top_left_list.append(img_tl)
                top_right_list.append(img_tr)
                bottom_left_list.append(img_bl)
                bottom_right_list.append(img_br)
            elif output_order == "column-major":
                # 列优先：第一列，第二列
                top_left_list.append(img_tl)
                top_right_list.append(img_bl)
                bottom_left_list.append(img_tr)
                bottom_right_list.append(img_br)
            else:
                # 默认顺序
                top_left_list.append(img_tl)
                top_right_list.append(img_tr)
                bottom_left_list.append(img_bl)
                bottom_right_list.append(img_br)
        
        # 转换回张量
        tl_tensor = self.pil_to_tensor(top_left_list)
        tr_tensor = self.pil_to_tensor(top_right_list)
        bl_tensor = self.pil_to_tensor(bottom_left_list)
        br_tensor = self.pil_to_tensor(bottom_right_list)
        
        # 转换为列表格式（因为 OUTPUT_IS_LIST = True）
        return ([tl_tensor], [tr_tensor], [bl_tensor], [br_tensor])


class kkImageGridMerge:
    """
    将多张图按 2x2、3x3、4x4 宫格合并，作为 kkImageSplit 的反向拼接工具。
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image1": ("IMAGE",),
                "image2": ("IMAGE",),
                "image3": ("IMAGE",),
                "image4": ("IMAGE",),
                "grid_size": (["2x2", "3x3", "4x4"], {"default": "2x2"}),
                "cell_size_mode": (["match_image1", "max", "min"], {"default": "match_image1"}),
                "background_color": ("STRING", {"default": "#000000"}),
            },
            "optional": {
                "image5": ("IMAGE",),
                "image6": ("IMAGE",),
                "image7": ("IMAGE",),
                "image8": ("IMAGE",),
                "image9": ("IMAGE",),
                "image10": ("IMAGE",),
                "image11": ("IMAGE",),
                "image12": ("IMAGE",),
                "image13": ("IMAGE",),
                "image14": ("IMAGE",),
                "image15": ("IMAGE",),
                "image16": ("IMAGE",),
            }
        }

    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("image",)
    FUNCTION = "merge_grid"
    CATEGORY = "🌟kktools/图像"

    def tensor_to_pil(self, img_tensor):
        """将 ComfyUI 图像张量转换为 PIL 图像列表。"""
        if img_tensor is None:
            return []

        if len(img_tensor.shape) == 4:
            batch_size, height, width, channels = img_tensor.shape
            images = []
            for i in range(batch_size):
                img_np = 255.0 * img_tensor[i].cpu().numpy()
                img_np = np.clip(img_np, 0, 255).astype(np.uint8)
                if channels == 1:
                    img_np = img_np.reshape(height, width)
                elif channels == 3:
                    img_np = img_np.reshape(height, width, 3)
                elif channels == 4:
                    img_np = img_np.reshape(height, width, 4)
                images.append(Image.fromarray(img_np))
            return images

        img_np = 255.0 * img_tensor.cpu().numpy()
        img_np = np.clip(img_np, 0, 255).astype(np.uint8)
        return [Image.fromarray(img_np)]

    def pil_to_tensor(self, pil_images, background_color=(0, 0, 0)):
        """将 PIL 图像列表转换回 ComfyUI IMAGE 张量。"""
        if not pil_images:
            return torch.zeros((1, 256, 256, 3))

        max_width = max(img.size[0] for img in pil_images)
        max_height = max(img.size[1] for img in pil_images)
        tensors = []
        for img in pil_images:
            img_rgb = img.convert("RGB")
            if img_rgb.size != (max_width, max_height):
                padded = Image.new("RGB", (max_width, max_height), background_color)
                padded.paste(img_rgb, (0, 0))
                img_rgb = padded
            img_np = np.array(img_rgb).astype(np.float32) / 255.0
            tensors.append(torch.from_numpy(img_np)[None,])
        return torch.cat(tensors, dim=0)

    def resolve_batch_cell_size(self, image_batches, batch_size, cell_size_mode):
        if cell_size_mode == "match_image1":
            return image_batches[0][0].size

        sizes = []
        for batch in image_batches:
            for batch_index in range(batch_size):
                sizes.append(batch[batch_index].size)

        if cell_size_mode == "min":
            return min(width for width, _height in sizes), min(height for _width, height in sizes)
        return max(width for width, _height in sizes), max(height for _width, height in sizes)

    def parse_grid_size(self, grid_size):
        try:
            columns, rows = map(int, str(grid_size).lower().split("x", 1))
        except ValueError as exc:
            raise ValueError(f"Unsupported grid_size: {grid_size}") from exc
        if columns != rows or columns not in (2, 3, 4):
            raise ValueError(f"Unsupported grid_size: {grid_size}")
        return columns, rows

    def merge_grid(
        self,
        image1,
        image2,
        image3,
        image4,
        grid_size,
        cell_size_mode,
        background_color,
        image5=None,
        image6=None,
        image7=None,
        image8=None,
        image9=None,
        image10=None,
        image11=None,
        image12=None,
        image13=None,
        image14=None,
        image15=None,
        image16=None,
    ):
        columns, rows = self.parse_grid_size(grid_size)
        cell_count = columns * rows
        images = [
            image1, image2, image3, image4,
            image5, image6, image7, image8,
            image9, image10, image11, image12,
            image13, image14, image15, image16,
        ][:cell_count]
        image_batches = [self.tensor_to_pil(image) for image in images]
        connected_batches = [batch for batch in image_batches if batch]

        batch_size = min(len(batch) for batch in connected_batches)
        if batch_size <= 0:
            return (torch.zeros((1, 256, 256, 3)),)

        try:
            bg_color = ImageColor.getcolor(background_color, "RGB")
        except ValueError:
            bg_color = (0, 0, 0)

        resampling = getattr(getattr(Image, "Resampling", Image), "LANCZOS")
        merged_images = []
        cell_width, cell_height = self.resolve_batch_cell_size(image_batches, batch_size, cell_size_mode)

        for batch_index in range(batch_size):
            cells = [
                batch[batch_index].convert("RGB") if batch else Image.new("RGB", (cell_width, cell_height), bg_color)
                for batch in image_batches
            ]
            resized_cells = [
                cell if cell.size == (cell_width, cell_height) else cell.resize((cell_width, cell_height), resampling)
                for cell in cells
            ]

            canvas = Image.new("RGB", (cell_width * columns, cell_height * rows), bg_color)
            for index, cell in enumerate(resized_cells):
                x = (index % columns) * cell_width
                y = (index // columns) * cell_height
                canvas.paste(cell, (x, y))
            merged_images.append(canvas)

        return (self.pil_to_tensor(merged_images, bg_color),)


import base64
import io
import json
import math
import re
import time
import urllib.error
import urllib.request


ENDPOINT = "https://www.mindapi.cc/v1/chat/completions"
REQUEST_TIMEOUT_SECONDS = 300
REQUEST_RETRY_DELAYS_SECONDS = [2, 5, 10]
MAX_PIXELS = 8_294_400

MODELS = [
    "gpt-image-2",
    "gemini-3-pro-image-preview-2k",
    "gemini-3-pro-image-preview-4k",
]

ASPECT_RATIOS = [
    "auto",
    "1:1",
    "3:2",
    "2:3",
    "5:4",
    "4:5",
    "4:3",
    "3:4",
    "16:9",
    "9:16",
    "21:9",
    "9:21",
    "2:1",
    "1:2",
    "3:1",
    "1:3",
]

RESOLUTIONS = ["1K", "2K", "4K"]
EDGE_FROM_RESOLUTION = {"1K": 1024, "2K": 2048, "4K": 3840}
GEMINI_EFFECTIVE_RESOLUTION = {
    "gemini-3-pro-image-preview-2k": "2K",
    "gemini-3-pro-image-preview-4k": "4K",
}


class MindAPIHttpError(RuntimeError):
    def __init__(self, status, body, service_name="MindAPI"):
        super().__init__(f"{service_name} HTTP {status}: {str(body)[:500]}")
        self.status = status
        self.body = body


class MindAPINetworkError(RuntimeError):
    def __init__(self, message, attempts):
        super().__init__(message)
        self.attempts = attempts


def _json_dumps(value):
    return json.dumps(value, ensure_ascii=False, indent=2)


def _snap_16(value):
    return int(round(max(64, min(3840, value)) / 16) * 16)


def is_gpt_image_model(model):
    return re.match(r"^gpt-image-2(?:$|[-_])", str(model or ""), re.I) is not None


def size_from_aspect(aspect_ratio, max_edge):
    match = re.match(r"^(\d+)\s*[:x]\s*(\d+)$", str(aspect_ratio or "").strip(), re.I)
    if not match:
        return None

    aspect_w = max(1, int(match.group(1)))
    aspect_h = max(1, int(match.group(2)))
    edge = max(64, min(3840, int(max_edge or 1024)))
    long_edge = max(aspect_w, aspect_h)
    scale = edge / long_edge

    width = _snap_16(aspect_w * scale)
    height = _snap_16(aspect_h * scale)

    if width * height > MAX_PIXELS:
        shrink = math.sqrt(MAX_PIXELS / (width * height))
        width = _snap_16(width * shrink)
        height = _snap_16(height * shrink)

    while width * height > MAX_PIXELS and width >= 80 and height >= 80:
        if width >= height:
            width -= 16
        else:
            height -= 16

    return f"{width}x{height}"


def _data_url_summary(value):
    text = str(value or "")
    match = re.match(r"^(data:image/[^;]+;base64,)", text, re.I)
    prefix = match.group(1) if match else ""
    return {
        "type": "data_url",
        "mime": prefix.replace("data:", "").replace(";base64,", "") or "image",
        "length": len(text),
        "preview": f"{prefix}<base64:{max(0, len(text) - len(prefix))} chars>",
    }


def _sanitize_debug_value(value):
    if isinstance(value, dict):
        return {key: _sanitize_debug_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize_debug_value(item) for item in value]
    if isinstance(value, str) and value.startswith("data:image/"):
        return _data_url_summary(value)
    return value


def _build_text_prompt(prompt, aspect_ratio):
    text = str(prompt or "").strip()
    if aspect_ratio and aspect_ratio != "auto":
        text += f"\n\n(Aspect ratio: {aspect_ratio}; output the image in this ratio.)"
    return text


def _build_user_content(prompt, aspect_ratio, reference_data_url):
    text = _build_text_prompt(prompt, aspect_ratio)
    if reference_data_url:
        return [
            {"type": "text", "text": text},
            {"type": "image_url", "image_url": {"url": reference_data_url}},
        ]
    return text


def effective_resolution_for_model(model, resolution):
    if model in GEMINI_EFFECTIVE_RESOLUTION:
        return GEMINI_EFFECTIVE_RESOLUTION[model]
    return resolution


def build_request_body(model, prompt, aspect_ratio, resolution, reference_data_url=None):
    effective_resolution = effective_resolution_for_model(model, resolution)
    content = _build_user_content(prompt, aspect_ratio, reference_data_url)
    body = {
        "model": model,
        "messages": [{"role": "user", "content": content}],
    }

    size = None
    if is_gpt_image_model(model):
        body.update({
            "stream": True,
            "temperature": 0.7,
            "group": "default",
            "top_p": 1,
            "frequency_penalty": 0,
            "presence_penalty": 0,
        })
        if aspect_ratio != "auto":
            size = size_from_aspect(aspect_ratio, EDGE_FROM_RESOLUTION[effective_resolution])
            if size:
                body["size"] = size
    else:
        body["temperature"] = 0.7
        image_config = {"image_size": effective_resolution}
        if aspect_ratio != "auto":
            image_config["aspect_ratio"] = aspect_ratio
        body["extra_body"] = {"google": {"image_config": image_config}}

    return body, effective_resolution, size


def _normalize_base_url(base_url):
    text = str(base_url or "").strip() or "https://api.zuco.ai/v1"
    return text.rstrip("/")


def _join_api_url(base_url, path):
    endpoint_path = str(path or "").strip()
    if endpoint_path.startswith("http://") or endpoint_path.startswith("https://"):
        return endpoint_path
    if not endpoint_path.startswith("/"):
        endpoint_path = "/" + endpoint_path
    return _normalize_base_url(base_url) + endpoint_path


def _http_post_json_to_endpoint(api_key, body, stream, endpoint, user_agent, service_name="MindAPI"):
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "text/event-stream" if stream else "application/json",
        "User-Agent": user_agent,
        "Connection": "close",
    }
    attempts = []

    for attempt_index in range(len(REQUEST_RETRY_DELAYS_SECONDS) + 1):
        request = urllib.request.Request(endpoint, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
                content_type = response.headers.get("Content-Type", "")
                status = getattr(response, "status", None) or response.getcode()
                response_headers = dict(response.headers.items())
                if stream and "json" not in content_type.lower():
                    return _read_sse_response(response, status, response_headers)
                return _read_json_response(response, status, response_headers)
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", "replace")
            raise MindAPIHttpError(exc.code, raw, service_name=service_name) from exc
        except (urllib.error.URLError, TimeoutError, ConnectionResetError, OSError) as exc:
            attempts.append({
                "attempt": attempt_index + 1,
                "error": str(exc),
            })
            if attempt_index >= len(REQUEST_RETRY_DELAYS_SECONDS):
                message = (
                    f"{service_name} request failed after "
                    f"{len(attempts)} attempts: {exc}. "
                    "This is a network/TLS connection reset before a valid API response."
                )
                raise MindAPINetworkError(message, attempts) from exc
            time.sleep(REQUEST_RETRY_DELAYS_SECONDS[attempt_index])


def _http_post_json(api_key, body, stream):
    return _http_post_json_to_endpoint(
        api_key=api_key,
        body=body,
        stream=stream,
        endpoint=ENDPOINT,
        user_agent="ComfyUI-kktools-kkimage2-LingsiAPI/1.0",
        service_name="MindAPI",
    )


def _read_json_response(response, status, headers):
    raw_text = response.read().decode("utf-8", "replace")
    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError:
        data = None
    return {
        "mode": "json",
        "status": status,
        "headers": headers,
        "raw_text": raw_text,
        "json": data,
        "content_text": _extract_chat_text(data) if data is not None else raw_text,
    }


def _read_sse_response(response, status, headers):
    events = []
    parsed_events = []
    content_parts = []

    for raw_line in response:
        line = raw_line.decode("utf-8", "replace").strip()
        if not line or line.startswith(":") or not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if not payload or payload == "[DONE]":
            continue
        events.append(payload)
        try:
            parsed = json.loads(payload)
            parsed_events.append(parsed)
            piece = _extract_stream_piece(parsed)
            if piece:
                content_parts.append(piece)
        except json.JSONDecodeError:
            content_parts.append(payload)

    return {
        "mode": "stream",
        "status": status,
        "headers": headers,
        "stream_events": events,
        "stream_json": parsed_events,
        "content_text": "".join(content_parts),
    }


def _normalize_chat_content(content):
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(filter(None, (_normalize_chat_content(item) for item in content)))
    if isinstance(content, dict):
        if isinstance(content.get("text"), str):
            return content["text"]
        if isinstance(content.get("content"), (str, list, dict)):
            return _normalize_chat_content(content["content"])
        image_url = content.get("image_url")
        if isinstance(image_url, dict) and image_url.get("url"):
            return str(image_url["url"])
        if isinstance(image_url, str):
            return image_url
        for key in ("url", "output_url"):
            if content.get(key):
                return str(content[key])
        inline_data = content.get("inline_data") or content.get("inlineData")
        if isinstance(inline_data, dict) and inline_data.get("data"):
            mime = inline_data.get("mime_type") or inline_data.get("mimeType") or "image/png"
            return f"data:{mime};base64,{inline_data['data']}"
    try:
        return json.dumps(content, ensure_ascii=False)
    except TypeError:
        return str(content)


def _extract_chat_text(data):
    if not isinstance(data, dict):
        return ""
    chunks = []
    choices = data.get("choices")
    if isinstance(choices, list):
        for choice in choices:
            if not isinstance(choice, dict):
                continue
            message = choice.get("message") or {}
            chunks.append(_normalize_chat_content(message.get("content")))
            if isinstance(message.get("images"), list):
                chunks.append(_normalize_chat_content(message["images"]))
            chunks.append(_normalize_chat_content(choice.get("text")))
    chunks.append(_normalize_chat_content(data.get("content")))
    chunks.append(_normalize_chat_content(data.get("text")))
    return "\n".join(filter(None, chunks))


def _extract_stream_piece(data):
    if not isinstance(data, dict):
        return ""
    choice = (data.get("choices") or [{}])[0]
    if not isinstance(choice, dict):
        choice = {}
    delta = choice.get("delta") or {}
    message = choice.get("message") or {}
    for source in (delta, message, choice, data):
        if not isinstance(source, dict):
            continue
        for key in ("content", "text", "image_url", "url", "inline_data", "inlineData"):
            if key in source:
                text = _normalize_chat_content(source.get(key))
                if text:
                    return text
    return ""


def _push_candidate(candidates, seen, value, source):
    if not value:
        return
    text = str(value).strip()
    if not text or text in seen:
        return
    if not (text.startswith("data:image/") or text.startswith("http://") or text.startswith("https://")):
        return
    seen.add(text)
    candidates.append({
        "kind": "data_url" if text.startswith("data:image/") else "url",
        "source": source,
        "value": text,
    })


def _extract_from_text(text, candidates, seen, source):
    value = str(text or "")
    for match in re.finditer(r"data:image/[a-z0-9.+-]+;base64,[A-Za-z0-9+/=_-]+", value, re.I):
        _push_candidate(candidates, seen, match.group(0), source)

    for match in re.finditer(r"!\[[^\]]*\]\(([^)\s]+)\)", value, re.I):
        _push_candidate(candidates, seen, match.group(1), source)

    urls = []
    for match in re.finditer(r"https?://[^\s)<>'\"]+", value, re.I):
        url = match.group(0).rstrip(".,;:!?)]")
        urls.append(url)
        if re.search(r"\.(png|jpe?g|webp|gif|bmp)(\?|$)", url, re.I):
            _push_candidate(candidates, seen, url, source)

    if not candidates and urls:
        _push_candidate(candidates, seen, urls[-1], source)


def _maybe_data_url_from_base64(value, mime="image/png"):
    text = re.sub(r"\s+", "", str(value or ""))
    if len(text) < 128:
        return None
    if not re.match(r"^[A-Za-z0-9+/=_-]+$", text):
        return None
    return f"data:{mime};base64,{text}"


def _walk_for_images(value, candidates, seen, source="response"):
    if isinstance(value, str):
        _extract_from_text(value, candidates, seen, source)
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _walk_for_images(item, candidates, seen, f"{source}[{index}]")
        return
    if not isinstance(value, dict):
        return

    image_url = value.get("image_url")
    if isinstance(image_url, dict):
        _push_candidate(candidates, seen, image_url.get("url"), f"{source}.image_url.url")
    elif isinstance(image_url, str):
        _push_candidate(candidates, seen, image_url, f"{source}.image_url")

    for key in ("url", "output_url"):
        if isinstance(value.get(key), str):
            _push_candidate(candidates, seen, value[key], f"{source}.{key}")

    for key in ("b64_json", "base64", "image_base64"):
        if isinstance(value.get(key), str):
            data_url = value[key] if value[key].startswith("data:image/") else _maybe_data_url_from_base64(value[key])
            _push_candidate(candidates, seen, data_url, f"{source}.{key}")

    inline_data = value.get("inline_data") or value.get("inlineData")
    if isinstance(inline_data, dict) and inline_data.get("data"):
        mime = inline_data.get("mime_type") or inline_data.get("mimeType") or "image/png"
        data_url = _maybe_data_url_from_base64(inline_data.get("data"), mime)
        _push_candidate(candidates, seen, data_url, f"{source}.inline_data")

    for key, item in value.items():
        _walk_for_images(item, candidates, seen, f"{source}.{key}")


def extract_image_candidates(response_payload):
    candidates = []
    seen = set()
    _walk_for_images(response_payload, candidates, seen)
    content_text = response_payload.get("content_text") if isinstance(response_payload, dict) else ""
    if content_text:
        _extract_from_text(content_text, candidates, seen, "content_text")
    return candidates


def _image_bytes_from_data_url(data_url):
    match = re.match(r"^data:image/[^;]+;base64,(.+)$", str(data_url or ""), re.I | re.S)
    if not match:
        raise ValueError("Invalid image data URL")
    encoded = re.sub(r"\s+", "", match.group(1))
    padding = "=" * (-len(encoded) % 4)
    if "-" in encoded or "_" in encoded:
        return base64.urlsafe_b64decode(encoded + padding)
    return base64.b64decode(encoded + padding)


def _image_bytes_from_url(url, api_key):
    headers = {
        "User-Agent": "ComfyUI-kktools-kkimage2-LingsiAPI/1.0",
        "Accept": "image/*,*/*;q=0.8",
    }
    request = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        if exc.code not in (401, 403):
            raise
        headers["Authorization"] = f"Bearer {api_key}"
        request = urllib.request.Request(url, headers=headers, method="GET")
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            return response.read()


def image_bytes_from_candidate(candidate, api_key):
    value = candidate["value"]
    if candidate["kind"] == "data_url":
        return _image_bytes_from_data_url(value)
    return _image_bytes_from_url(value, api_key)


def tensor_to_data_url(image):
    import numpy as np
    from PIL import Image

    frame = image
    if hasattr(frame, "detach"):
        frame = frame.detach().cpu().numpy()
    if getattr(frame, "ndim", 0) == 4:
        frame = frame[0]
    if getattr(frame, "ndim", 0) != 3:
        raise ValueError("Reference image must be a ComfyUI IMAGE tensor")

    array = np.clip(frame, 0.0, 1.0)
    array = (array * 255.0).round().astype(np.uint8)
    if array.shape[-1] == 1:
        array = np.repeat(array, 3, axis=-1)
    if array.shape[-1] == 4:
        mode = "RGBA"
    else:
        array = array[:, :, :3]
        mode = "RGB"

    pil_image = Image.fromarray(array, mode=mode)
    buffer = io.BytesIO()
    pil_image.save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def image_bytes_to_tensor(image_bytes):
    tensor, _original_size, _final_size, _resized = image_bytes_to_tensor_info(image_bytes)
    return tensor


def image_bytes_to_tensor_info(image_bytes, target_size=None):
    import numpy as np
    import torch
    from PIL import Image, ImageOps

    resampling = getattr(getattr(Image, "Resampling", Image), "LANCZOS")

    with Image.open(io.BytesIO(image_bytes)) as pil_image:
        pil_image = ImageOps.exif_transpose(pil_image).convert("RGB")
        original_size = pil_image.size
        resized = False
        if target_size and pil_image.size != target_size:
            pil_image = pil_image.resize(target_size, resampling)
            resized = True
        final_size = pil_image.size
        array = np.asarray(pil_image).astype(np.float32) / 255.0
    return torch.from_numpy(array)[None,], original_size, final_size, resized


def concat_image_tensors(tensors):
    import torch

    return torch.cat(tensors, dim=0)


def _candidate_debug(candidate):
    value = candidate.get("value", "")
    if isinstance(value, str) and value.startswith("data:image/"):
        value = _data_url_summary(value)
    return {
        "kind": candidate.get("kind"),
        "source": candidate.get("source"),
        "value": value,
    }


def _debug_package(
    ok,
    model,
    requested_resolution,
    effective_resolution,
    aspect_ratio,
    has_input_image,
    request_body,
    requested_count=1,
    generated_count=0,
    response_payload=None,
    parsed_images=None,
    selected_image=None,
    responses=None,
    error=None,
    endpoint=ENDPOINT,
):
    package = {
        "ok": ok,
        "endpoint": endpoint,
        "request": {
            "headers": {
                "Authorization": "Bearer ***",
                "Content-Type": "application/json",
            },
            "body": _sanitize_debug_value(request_body),
        },
        "model": model,
        "effective_model": model,
        "requested_resolution": requested_resolution,
        "effective_resolution": effective_resolution,
        "aspect_ratio": aspect_ratio,
        "has_input_image": bool(has_input_image),
        "requested_count": requested_count,
        "generated_count": generated_count,
        "parsed_images": [_candidate_debug(item) for item in (parsed_images or [])],
        "selected_image": _candidate_debug(selected_image) if selected_image else None,
        "responses": responses or [],
        "error": error,
    }
    if response_payload is not None:
        package["raw_response"] = response_payload
    return package


# ComfyUI 节点注册
NODE_CLASS_MAPPINGS = {
    "kkPadImageToCanvas": kkPadImageToCanvas,
    "kkImageFrame": kkImageFrame,
    "kkResize": kkResize,
    "kkGetImage": kkGetImage,
    "kkBatchImageLoader": kkBatchImageLoader,
    "kkImageTileSplit2x2": kkImageTileSplit2x2,
    "kkImageGridMerge": kkImageGridMerge,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "kkPadImageToCanvas": "kkPadImageToCanvas（图像填充到画布）",
    "kkImageFrame": "kkImageFrame（图像边框）",
    "kkResize": "kkResize（图像蒙版同步调整）",
    "kkGetImage": "kkGetImage（获取图像尺寸）",
    "kkBatchImageLoader": "kkBatchImageLoader（批量图像加载）",
    "kkImageTileSplit2x2": "kkImageTileSplit2x2（图像2x2分块）",
    "kkImageGridMerge": "kkImageGridMerge（图像宫格合并）",
}

__all__ = ['NODE_CLASS_MAPPINGS', 'NODE_DISPLAY_NAME_MAPPINGS']
