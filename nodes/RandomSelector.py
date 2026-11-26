"""
随机选择器 - 从多组数据中随机选择值
"""

import json
import random

_INPUT_PORTS = tuple(f"input_{index}" for index in range(1, 10))


def _pick_input(seed, inputs):
    connected = [name for name in _INPUT_PORTS if name in inputs]
    selected = random.Random(seed).choice(connected) if connected else None
    return selected, connected


class kkRandomSelector:
    """随机选择器"""
    
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "json_config": ("STRING", {
                    "default": '[{"groupName":"group1","list":["option1","option2","option3"]},{"groupName":"group2","list":["option4","option5","option6"]}]',
                    "multiline": True
                }),
                "target_groups": ("STRING", {
                    "default": "",
                    "multiline": False,
                    "tooltip": "输入要限制的组名，用逗号分隔，如: group1,group2"
                }),
                "seed": ("INT", {
                    "default": 0,
                    "min": 0,
                    "max": 0xffffffffffffffff,
                    "step": 1
                })
            },
            "optional": {
                "Markdown文件": ("KK_MARKDOWN_FILE", {
                    "lazy": True,
                    "tooltip": "连接 kkMarkdown上传；包含多个文件时按 seed 随机选择一个"
                }),
                **{name: ("*", {"lazy": True}) for name in _INPUT_PORTS},
            },
        }
    
    RETURN_TYPES = ("*", "STRING", "STRING", "KK_MARKDOWN_FILE")
    RETURN_NAMES = ("selected_value", "selected_group", "all_groups", "Markdown文件")
    FUNCTION = "random_select"
    CATEGORY = "🌟kktools/随机"
    DESCRIPTION = "按 seed 从已连接的 input_1 至 input_9 中抽取一路并原样输出。通用输入留空时，从 Markdown 文件或 JSON 候选项中抽取。"

    def check_lazy_status(self, seed, **inputs):
        selected, _ = _pick_input(seed, inputs)
        source = selected or "Markdown文件"
        return [source] if source in inputs and inputs[source] is None else []
    
    def random_select(self, json_config, target_groups="", seed=0, Markdown文件=None, **inputs):
        empty_markdown = {"filename": "", "content": "", "items": []}
        selected_input, connected = _pick_input(seed, inputs)
        if selected_input is not None:
            return (inputs[selected_input], selected_input, ",".join(connected), empty_markdown)

        try:
            rng = random.Random(seed)

            if Markdown文件:
                items = Markdown文件.get("items") or [Markdown文件]
                items = [item for item in items if isinstance(item, dict) and "content" in item]
                if not items:
                    return ("Markdown 输入中没有可选文件", "", "", empty_markdown)

                selected = items[rng.randrange(len(items))]
                selected_markdown = {
                    "filename": str(selected.get("filename", "Markdown文件")),
                    "content": str(selected["content"]),
                    "items": [selected],
                }
                filenames = ",".join(str(item.get("filename", "Markdown文件")) for item in items)
                return (selected_markdown["content"], "Markdown", filenames, selected_markdown)
            
            # 解析JSON配置
            config = json.loads(json_config)
            
            # 验证配置格式
            if not isinstance(config, list):
                return ("配置错误: 必须是JSON数组", "", "", empty_markdown)
            
            # 收集所有可用的组名
            all_groups = []
            for group in config:
                if isinstance(group, dict) and "groupName" in group:
                    all_groups.append(group["groupName"])
            
            all_groups_str = ",".join(all_groups)
            
            # 解析目标组名
            target_group_list = []
            if target_groups and target_groups.strip():
                target_group_list = [g.strip() for g in target_groups.split(",") if g.strip()]
            
            # 筛选符合条件的组
            valid_groups = []
            if target_group_list:
                # 只选择指定的组
                for group in config:
                    if isinstance(group, dict) and "groupName" in group and group["groupName"] in target_group_list:
                        valid_groups.append(group)
            else:
                # 使用所有组
                for group in config:
                    if isinstance(group, dict) and "groupName" in group:
                        valid_groups.append(group)
            
            # 如果没有有效的组
            if not valid_groups:
                print(f"⚠️ kkRandomSelector: 没有找到有效的组")
                return ("", "", all_groups_str, empty_markdown)
            
            # 收集所有符合条件的选项
            all_items = []
            group_mapping = {}
            
            for group in valid_groups:
                group_name = group["groupName"]
                items = group.get("list", [])
                for item in items:
                    all_items.append(str(item))
                    group_mapping[len(all_items)-1] = group_name
            
            # 如果没有可选的项
            if not all_items:
                print(f"⚠️ kkRandomSelector: 没有可选的项")
                return ("", "", all_groups_str, empty_markdown)
            
            # 随机选择一个项
            selected_index = rng.randrange(len(all_items))
            selected_value = all_items[selected_index]
            selected_group = group_mapping[selected_index]
            
            # 打印调试信息
            print(f"✅ kkRandomSelector:")
            print(f"   选中的组: {selected_group}")
            print(f"   选中的值: {selected_value}")
            print(f"   总组数: {len(all_groups)}")
            print(f"   总选项数: {len(all_items)}")
            
            return (selected_value, selected_group, all_groups_str, empty_markdown)
            
        except json.JSONDecodeError as e:
            error_msg = f"JSON解析错误: {str(e)}"
            print(f"❌ kkRandomSelector: {error_msg}")
            return (error_msg, "", "", empty_markdown)
        except Exception as e:
            error_msg = f"错误: {str(e)}"
            print(f"❌ kkRandomSelector: {error_msg}")
            return (error_msg, "", "", empty_markdown)


# ComfyUI 节点注册
NODE_CLASS_MAPPINGS = {
    "kkRandomSelector": kkRandomSelector,
}

# 节点在菜单中显示的名称
NODE_DISPLAY_NAME_MAPPINGS = {
    "kkRandomSelector": "kkRandomSelector（随机选择器）",
}

__all__ = ['NODE_CLASS_MAPPINGS', 'NODE_DISPLAY_NAME_MAPPINGS', 'kkRandomSelector']
