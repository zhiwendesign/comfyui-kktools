class kkIfElse:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "boolean": ("BOOLEAN", {"default": True, "tooltip": "True 选择 on_true，False 选择 on_false。"}),
            },
            "optional": {
                "on_true": ("*", {"lazy": True}),
                "on_false": ("*", {"lazy": True}),
            },
        }

    RETURN_TYPES = ("*",)
    RETURN_NAMES = ("output",)
    FUNCTION = "select"
    CATEGORY = "🌟kktools/逻辑"
    DESCRIPTION = "根据布尔值选择并原样输出一路输入，仅执行选中的分支。"

    @staticmethod
    def _selected_input(boolean, inputs):
        name = "on_true" if boolean else "on_false"
        if name not in inputs:
            raise ValueError(f"当前条件为 {boolean}，请连接 {name}。")
        return name

    def check_lazy_status(self, boolean, **inputs):
        name = self._selected_input(boolean, inputs)
        return [name] if inputs[name] is None else []

    def select(self, boolean, **inputs):
        name = self._selected_input(boolean, inputs)
        return (inputs[name],)


NODE_CLASS_MAPPINGS = {"kkIfElse": kkIfElse}
NODE_DISPLAY_NAME_MAPPINGS = {"kkIfElse": "kkIfElse（布尔分支选择）"}
