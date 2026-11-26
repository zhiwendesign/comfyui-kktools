class kkSwitchCase:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "switch_condition": ("STRING", {"default": "1", "tooltip": "输入要匹配的分支名称，区分大小写。"}),
                "case_1": ("STRING", {"default": "1"}),
                "case_2": ("STRING", {"default": "2"}),
                "case_3": ("STRING", {"default": "3"}),
            },
            "optional": {
                **{f"input_{index}": ("*", {"lazy": True}) for index in range(1, 10)},
                **{f"case_{index}": ("STRING", {"default": str(index)}) for index in range(4, 10)},
            },
        }

    RETURN_TYPES = ("*",)
    RETURN_NAMES = ("output",)
    OUTPUT_TOOLTIPS = ("原样传递选中输入的数据与类型，例如 STRING、IMAGE、MASK 或自定义类型。",)
    FUNCTION = "select"
    CATEGORY = "🌟kktools/逻辑"
    DESCRIPTION = "最多九路输入可分别连接任意类型。按 case 顺序匹配，仅执行并原样输出选中的分支。"

    @staticmethod
    def _selected_input(condition, cases, inputs):
        for index, label in enumerate(cases, start=1):
            if condition == label:
                name = f"input_{index}"
                if name not in inputs:
                    raise ValueError(f"条件 {condition!r} 匹配 case_{index}，请连接 {name}。")
                return name
        raise ValueError(f"条件 {condition!r} 未匹配任何分支，请检查 switch_condition 和 case_1 至 case_9。")

    def check_lazy_status(self, switch_condition, case_1, case_2, case_3, **inputs):
        cases = (case_1, case_2, case_3, *(inputs.get(f"case_{index}", str(index)) for index in range(4, 10)))
        name = self._selected_input(switch_condition, cases, inputs)
        return [name] if inputs[name] is None else []

    def select(self, switch_condition, case_1, case_2, case_3, **inputs):
        cases = (case_1, case_2, case_3, *(inputs.get(f"case_{index}", str(index)) for index in range(4, 10)))
        name = self._selected_input(switch_condition, cases, inputs)
        return (inputs[name],)


NODE_CLASS_MAPPINGS = {"kkSwitchCase": kkSwitchCase}
NODE_DISPLAY_NAME_MAPPINGS = {"kkSwitchCase": "kkSwitchCase（条件分支选择）"}
