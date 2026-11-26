import re


class kkColorPicker:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "color": ("STRING", {"default": "#0089FF", "tooltip": "输入六位十六进制颜色，或使用下方取色器。"}),
            },
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("color",)
    FUNCTION = "select_color"
    CATEGORY = "🌟kktools/颜色"
    DESCRIPTION = "选择颜色并输出 #RRGGBB 格式的字符串。"

    def select_color(self, color):
        value = color.strip()
        if not value.startswith("#"):
            value = "#" + value
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", value):
            raise ValueError("颜色应为六位十六进制，例如 #0089FF。")
        return (value.upper(),)


NODE_CLASS_MAPPINGS = {"kkColorPicker": kkColorPicker}
NODE_DISPLAY_NAME_MAPPINGS = {"kkColorPicker": "kkColorPicker（颜色选择器）"}
