from nodes import PreviewImage


class kkImageComparer(PreviewImage):
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {},
            "optional": {
                "image_a": ("IMAGE",),
                "image_b": ("IMAGE",),
            },
            "hidden": {
                "prompt": "PROMPT",
                "extra_pnginfo": "EXTRA_PNGINFO",
            },
        }

    RETURN_TYPES = ()
    FUNCTION = "compare_images"
    CATEGORY = "🌟kktools/图像"
    OUTPUT_NODE = True
    DESCRIPTION = "交互式对比两张图像，支持不同尺寸和批次选图。"

    def compare_images(self, image_a=None, image_b=None, prompt=None, extra_pnginfo=None):
        result = {"ui": {"a_images": [], "b_images": []}}
        if image_a is not None and len(image_a) > 0:
            saved = self.save_images(image_a, "kktools_compare_a", prompt, extra_pnginfo)
            result["ui"]["a_images"] = saved.get("ui", {}).get("images", [])
        if image_b is not None and len(image_b) > 0:
            saved = self.save_images(image_b, "kktools_compare_b", prompt, extra_pnginfo)
            result["ui"]["b_images"] = saved.get("ui", {}).get("images", [])
        return result


NODE_CLASS_MAPPINGS = {"kkimage Comparer": kkImageComparer}
NODE_DISPLAY_NAME_MAPPINGS = {"kkimage Comparer": "kkimage Comparer（图像对比）"}
