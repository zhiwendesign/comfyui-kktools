"""Small compatibility shims for text-only third-party nodes used by old workflows."""


class _ShowTextPysssssCompat:
    CATEGORY = "🌟kktools/兼容"
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("STRING",)
    FUNCTION = "show_text"
    OUTPUT_NODE = False

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "text": ("STRING", {"default": "", "multiline": True}),
            },
        }

    def show_text(self, text=""):
        return (str(text or ""),)


class _CRTextCompat:
    CATEGORY = "🌟kktools/兼容"
    RETURN_TYPES = ("*", "STRING")
    RETURN_NAMES = ("text", "show_help")
    FUNCTION = "text"
    OUTPUT_NODE = False

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "text": ("STRING", {"default": "", "multiline": True}),
            },
        }

    def text(self, text=""):
        return (str(text or ""), "https://github.com/Suzie1/ComfyUI_Comfyroll_CustomNodes")


NODE_CLASS_MAPPINGS = {
    "ShowText|pysssss": _ShowTextPysssssCompat,
    "CR Text": _CRTextCompat,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "ShowText|pysssss": "ShowText|pysssss（兼容文本展示）",
    "CR Text": "CR Text（兼容文本）",
}

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
