import operator


_COMPARISONS = {
    "a == b": (operator.eq, "a", "b"),
    "a != b": (operator.ne, "a", "b"),
    "a < b": (operator.lt, "a", "b"),
    "a > b": (operator.gt, "a", "b"),
    "a <= b": (operator.le, "a", "b"),
    "a >= b": (operator.ge, "a", "b"),
    "a > 0": (operator.gt, "a", "zero"),
    "a <= 0": (operator.le, "a", "zero"),
    "b > 0": (operator.gt, "b", "zero"),
    "b <= 0": (operator.le, "b", "zero"),
}


class kkCompare:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "comparison": (list(_COMPARISONS), {"default": "a == b"}),
            },
            "optional": {
                "a": ("INT", {"forceInput": True, "tooltip": "参与比较的整数，未连接时为 0。"}),
                "b": ("INT", {"forceInput": True, "tooltip": "参与比较的整数，未连接时为 0。"}),
            },
        }

    RETURN_TYPES = ("BOOLEAN",)
    RETURN_NAMES = ("boolean",)
    FUNCTION = "compare"
    CATEGORY = "🌟kktools/逻辑"
    DESCRIPTION = "使用选定公式比较 a 和 b，输出 True 或 False。未连接的输入按 0 处理。"

    def compare(self, comparison, a=0, b=0):
        operation, left, right = _COMPARISONS[comparison]
        values = {"a": a, "b": b, "zero": 0}
        try:
            return (bool(operation(values[left], values[right])),)
        except (TypeError, ValueError, RuntimeError) as error:
            raise ValueError(
                f"无法计算 {comparison}，请检查输入类型和比较结果是否为单个布尔值：{error}"
            ) from error


NODE_CLASS_MAPPINGS = {"kkCompare": kkCompare}
NODE_DISPLAY_NAME_MAPPINGS = {"kkCompare": "kkCompare（比较）"}
