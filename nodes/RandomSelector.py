"""
随机选择器 - 从多组数据中随机选择值
"""

import torch
import numpy as np
import json
import random

class RandomSelector:
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
            }
        }
    
    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("selected_value", "selected_group", "all_groups")
    FUNCTION = "random_select"
    CATEGORY = "kktools/随机"
    
    def random_select(self, json_config, target_groups="", seed=0):
        """从JSON配置中随机选择一个值"""
        try:
            # 设置随机种子
            random.seed(seed)
            np.random.seed(seed)
            
            # 解析JSON配置
            config = json.loads(json_config)
            
            # 验证配置格式
            if not isinstance(config, list):
                return ("配置错误: 必须是JSON数组", "", "")
            
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
                print(f"⚠️ RandomSelector: 没有找到有效的组")
                return ("", "", all_groups_str)
            
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
                print(f"⚠️ RandomSelector: 没有可选的项")
                return ("", "", all_groups_str)
            
            # 随机选择一个项
            selected_index = random.randint(0, len(all_items)-1)
            selected_value = all_items[selected_index]
            selected_group = group_mapping[selected_index]
            
            # 打印调试信息
            print(f"✅ RandomSelector:")
            print(f"   选中的组: {selected_group}")
            print(f"   选中的值: {selected_value}")
            print(f"   总组数: {len(all_groups)}")
            print(f"   总选项数: {len(all_items)}")
            
            return (selected_value, selected_group, all_groups_str)
            
        except json.JSONDecodeError as e:
            error_msg = f"JSON解析错误: {str(e)}"
            print(f"❌ RandomSelector: {error_msg}")
            return (error_msg, "", "")
        except Exception as e:
            error_msg = f"错误: {str(e)}"
            print(f"❌ RandomSelector: {error_msg}")
            return (error_msg, "", "")


# ComfyUI 节点注册
NODE_CLASS_MAPPINGS = {
    "RandomSelector": RandomSelector,
}

# 节点在菜单中显示的名称
NODE_DISPLAY_NAME_MAPPINGS = {
    "RandomSelector": "RandomSelector（随机选择器）",
}

__all__ = ['NODE_CLASS_MAPPINGS', 'NODE_DISPLAY_NAME_MAPPINGS', 'RandomSelector']
