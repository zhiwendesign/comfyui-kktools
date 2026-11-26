class kkStringLength:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "text": ("STRING", {"forceInput": True, "tooltip": "需要统计的文本，空格和换行也计入长度。"}),
            },
        }

    RETURN_TYPES = ("INT",)
    RETURN_NAMES = ("length",)
    FUNCTION = "count"
    CATEGORY = "🌟kktools/逻辑"
    DESCRIPTION = "统计文本的 Unicode 字符数，空格、标点和换行均计入。"

    def count(self, text):
        return (len(text),)


NODE_CLASS_MAPPINGS = {"kkStringLength": kkStringLength}
NODE_DISPLAY_NAME_MAPPINGS = {"kkStringLength": "kkStringLength（字数统计）"}
