"""
ComfyUI Custom Node: kktoolsString
卡卡字符串节点 - 字符串裁剪和处理功能
"""

class StringNode:
    """字符串裁剪节点（基础裁剪） - 忽略开头和结尾指定数量的字符"""
    
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "text": ("STRING", {
                    "default": "",
                    "multiline": True,
                    "forceInput": True  # 强制从其他节点输入
                }),
                "skip_start": ("INT", {
                    "default": 0,
                    "min": 0,
                    "max": 1000,
                    "step": 1,
                    "display": "number"
                }),
                "skip_end": ("INT", {
                    "default": 0,
                    "min": 0,
                    "max": 1000,
                    "step": 1,
                    "display": "number"
                }),
            }
        }
    
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("trimmed_text",)
    FUNCTION = "trim_string"
    CATEGORY = "kktools/String"
    
    def trim_string(self, text, skip_start, skip_end):
        """
        裁剪字符串，忽略开头和结尾指定数量的字符
        
        Args:
            text: 输入的字符串
            skip_start: 忽略开头的字符数
            skip_end: 忽略结尾的字符数
            
        Returns:
            裁剪后的字符串
        """
        if not text:
            return ("",)
        
        text_length = len(text)
        
        # 如果要忽略的字符总数大于等于文本长度，返回空字符串
        if skip_start + skip_end >= text_length:
            return ("",)
        
        # 计算裁剪范围
        start_index = skip_start
        end_index = text_length - skip_end if skip_end > 0 else text_length
        
        # 执行裁剪
        trimmed = text[start_index:end_index]
        
        return (trimmed,)


class StringNodeAdvanced:
    """字符串裁剪节点（高级裁剪） - 带详细信息输出"""
    
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "text": ("STRING", {
                    "default": "",
                    "multiline": True,
                    "forceInput": True
                }),
                "skip_start": ("INT", {
                    "default": 0,
                    "min": 0,
                    "max": 1000,
                    "step": 1,
                    "display": "number"
                }),
                "skip_end": ("INT", {
                    "default": 0,
                    "min": 0,
                    "max": 1000,
                    "step": 1,
                    "display": "number"
                }),
            }
        }
    
    RETURN_TYPES = ("STRING", "INT", "INT", "INT")
    RETURN_NAMES = ("trimmed_text", "original_length", "trimmed_length", "removed_chars")
    FUNCTION = "trim_string_advanced"
    CATEGORY = "kktools/String"
    
    def trim_string_advanced(self, text, skip_start, skip_end):
        """
        裁剪字符串，忽略开头和结尾指定数量的字符（带详细信息）
        
        Args:
            text: 输入的字符串
            skip_start: 忽略开头的字符数
            skip_end: 忽略结尾的字符数
            
        Returns:
            (裁剪后的字符串, 原始长度, 裁剪后长度, 移除的字符数)
        """
        if not text:
            return ("", 0, 0, 0)
        
        original_length = len(text)
        
        # 如果要忽略的字符总数大于等于文本长度，返回空字符串
        if skip_start + skip_end >= original_length:
            return ("", original_length, 0, original_length)
        
        # 计算裁剪范围
        start_index = skip_start
        end_index = original_length - skip_end if skip_end > 0 else original_length
        
        # 执行裁剪
        trimmed = text[start_index:end_index]
        trimmed_length = len(trimmed)
        removed_chars = original_length - trimmed_length
        
        return (trimmed, original_length, trimmed_length, removed_chars)


class StringMergeNode:
    """字符串合并节点（字符串合并） - 合并多个字符串"""
    
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "string1": ("STRING", {
                    "default": "",
                    "multiline": True,
                }),
                "string2": ("STRING", {
                    "default": "",
                    "multiline": True,
                }),
            },
            "optional": {
                "separator": ("STRING", {
                    "default": "",
                    "multiline": False,
                }),
                "string3": ("STRING", {
                    "default": "",
                    "multiline": True,
                }),
                "string4": ("STRING", {
                    "default": "",
                    "multiline": True,
                }),
            }
        }
    
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("merged_string",)
    FUNCTION = "merge_strings"
    CATEGORY = "kktools/String"
    
    def merge_strings(self, string1="", string2="", separator="", string3="", string4=""):
        """
        合并多个字符串
        
        Args:
            string1: 第一个字符串
            string2: 第二个字符串
            separator: 分隔符（可选）
            string3: 第三个字符串（可选）
            string4: 第四个字符串（可选）
            
        Returns:
            合并后的字符串
        """
        # 确保所有输入都是字符串
        string1 = str(string1) if string1 is not None else ""
        string2 = str(string2) if string2 is not None else ""
        string3 = str(string3) if string3 is not None else ""
        string4 = str(string4) if string4 is not None else ""
        separator = str(separator) if separator is not None else ""
        
        # 收集所有非空字符串
        strings = [s for s in [string1, string2, string3, string4] if s]
        
        # 使用分隔符合并
        merged = separator.join(strings)
        
        # 打印调试信息
        print(f"kktools String Merge:")
        print(f"  Input 1: {repr(string1)}")
        print(f"  Input 2: {repr(string2)}")
        print(f"  Input 3: {repr(string3)}")
        print(f"  Input 4: {repr(string4)}")
        print(f"  Separator: {repr(separator)}")
        print(f"  Merged Result: {repr(merged)}")
        print(f"  Result Length: {len(merged)}")
        
        return (merged,)


class InputNode:
    """输入节点（多类型输入）（多类型输入节点） - 可以输入2组字符串、整数或浮点数"""
    
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                # 第一组输入
                "input_type_1": (["STRING", "INT", "FLOAT"], {
                    "default": "STRING"
                }),
                "string_value_1": ("STRING", {
                    "default": "",
                    "multiline": True,
                }),
                "int_value_1": ("INT", {
                    "default": 0,
                    "min": -999999,
                    "max": 999999,
                    "step": 1,
                    "display": "number"
                }),
                "float_value_1": ("FLOAT", {
                    "default": 0.0,
                    "min": -999999.0,
                    "max": 999999.0,
                    "step": 0.1,
                    "display": "number"
                }),
                # 第二组输入
                "input_type_2": (["STRING", "INT", "FLOAT"], {
                    "default": "STRING"
                }),
                "string_value_2": ("STRING", {
                    "default": "",
                    "multiline": True,
                }),
                "int_value_2": ("INT", {
                    "default": 0,
                    "min": -999999,
                    "max": 999999,
                    "step": 1,
                    "display": "number"
                }),
                "float_value_2": ("FLOAT", {
                    "default": 0.0,
                    "min": -999999.0,
                    "max": 999999.0,
                    "step": 0.1,
                    "display": "number"
                }),
            }
        }
    
    RETURN_TYPES = ("STRING", "INT", "FLOAT", "STRING", "INT", "FLOAT")
    RETURN_NAMES = ("string_output_1", "int_output_1", "float_output_1", "string_output_2", "int_output_2", "float_output_2")
    FUNCTION = "process_input"
    CATEGORY = "kktools/String"
    
    def process_input(self, input_type_1, string_value_1, int_value_1, float_value_1,
                     input_type_2, string_value_2, int_value_2, float_value_2):
        """
        根据选择的类型输出对应的值（2组）
        
        Args:
            input_type_1: 第一组输入类型 (STRING, INT 或 FLOAT)
            string_value_1: 第一组字符串值
            int_value_1: 第一组整数值
            float_value_1: 第一组浮点数值
            input_type_2: 第二组输入类型 (STRING, INT 或 FLOAT)
            string_value_2: 第二组字符串值
            int_value_2: 第二组整数值
            float_value_2: 第二组浮点数值
            
        Returns:
            (字符串输出1, 整数输出1, 浮点数输出1, 字符串输出2, 整数输出2, 浮点数输出2)
        """
        # 处理第一组
        if input_type_1 == "STRING":
            # 如果选择字符串类型，尝试将字符串转换为整数和浮点数
            try:
                int_output_1 = int(string_value_1) if string_value_1.strip() else 0
            except ValueError:
                int_output_1 = 0
            try:
                float_output_1 = float(string_value_1) if string_value_1.strip() else 0.0
            except ValueError:
                float_output_1 = 0.0
            string_output_1 = string_value_1
        elif input_type_1 == "INT":
            # 如果选择整数类型，将整数转换为字符串和浮点数
            string_output_1 = str(int_value_1)
            int_output_1 = int_value_1
            float_output_1 = float(int_value_1)
        else:  # FLOAT
            # 如果选择浮点数类型，将浮点数转换为字符串和整数
            string_output_1 = str(float_value_1)
            int_output_1 = int(float_value_1)
            float_output_1 = float_value_1
        
        # 处理第二组
        if input_type_2 == "STRING":
            # 如果选择字符串类型，尝试将字符串转换为整数和浮点数
            try:
                int_output_2 = int(string_value_2) if string_value_2.strip() else 0
            except ValueError:
                int_output_2 = 0
            try:
                float_output_2 = float(string_value_2) if string_value_2.strip() else 0.0
            except ValueError:
                float_output_2 = 0.0
            string_output_2 = string_value_2
        elif input_type_2 == "INT":
            # 如果选择整数类型，将整数转换为字符串和浮点数
            string_output_2 = str(int_value_2)
            int_output_2 = int_value_2
            float_output_2 = float(int_value_2)
        else:  # FLOAT
            # 如果选择浮点数类型，将浮点数转换为字符串和整数
            string_output_2 = str(float_value_2)
            int_output_2 = int(float_value_2)
            float_output_2 = float_value_2
        
        return (string_output_1, int_output_1, float_output_1, string_output_2, int_output_2, float_output_2)


class ReplaceNode:
    """替换节点（字符串替换）（字符串替换节点） - 替换字符串中的指定内容"""
    
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "text": ("STRING", {
                    "default": "",
                    "multiline": True,
                    "forceInput": True
                }),
                "old_text": ("STRING", {
                    "default": "",
                    "multiline": False,
                }),
                "new_text": ("STRING", {
                    "default": "",
                    "multiline": False,
                }),
                "replace_all": ("BOOLEAN", {
                    "default": True,
                }),
            }
        }
    
    RETURN_TYPES = ("STRING", "INT")
    RETURN_NAMES = ("replaced_text", "replace_count")
    FUNCTION = "replace_string"
    CATEGORY = "kktools/String"
    
    def replace_string(self, text, old_text, new_text, replace_all):
        """
        替换字符串中的指定内容
        
        Args:
            text: 原始字符串
            old_text: 要替换的文本
            new_text: 替换为的文本
            replace_all: 是否替换所有匹配项
            
        Returns:
            (替换后的字符串, 替换次数)
        """
        if not text or not old_text:
            return (text, 0)
        
        # 确保所有输入都是字符串
        text = str(text) if text is not None else ""
        old_text = str(old_text) if old_text is not None else ""
        new_text = str(new_text) if new_text is not None else ""
        
        # 执行替换
        if replace_all:
            # 替换所有匹配项
            replaced_text = text.replace(old_text, new_text)
            # 计算替换次数
            replace_count = text.count(old_text)
        else:
            # 仅替换第一个匹配项
            replaced_text = text.replace(old_text, new_text, 1)
            # 计算替换次数（0或1）
            replace_count = 1 if old_text in text else 0
        
        # 打印调试信息
        print(f"kktools String Replace:")
        print(f"  Original Text: {repr(text)}")
        print(f"  Old Text: {repr(old_text)}")
        print(f"  New Text: {repr(new_text)}")
        print(f"  Replace All: {replace_all}")
        print(f"  Replaced Text: {repr(replaced_text)}")
        print(f"  Replace Count: {replace_count}")
        
        return (replaced_text, replace_count)


class SomethingToAny:
    """类型转换节点（任意类型转换）（类型转换节点） - 将任意输入转换为指定类型"""
    
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "input_type": (["STRING", "INT", "FLOAT", "BOOLEAN"], {
                    "default": "STRING"
                }),
                "output_type": (["STRING", "INT", "FLOAT"], {
                    "default": "STRING"
                }),
                "string_input": ("STRING", {
                    "default": "",
                    "multiline": True,
                }),
                "int_input": ("INT", {
                    "default": 0,
                    "min": -999999,
                    "max": 999999,
                    "step": 1,
                    "display": "number"
                }),
                "float_input": ("FLOAT", {
                    "default": 0.0,
                    "min": -999999.0,
                    "max": 999999.0,
                    "step": 0.1,
                    "display": "number"
                }),
                "boolean_input": ("BOOLEAN", {
                    "default": False,
                }),
            }
        }
    
    RETURN_TYPES = ("STRING", "INT", "FLOAT")
    RETURN_NAMES = ("string_output", "int_output", "float_output")
    FUNCTION = "convert_any"
    CATEGORY = "kktools/String"
    
    def convert_any(self, input_type, output_type, string_input, int_input, float_input, boolean_input):
        """
        将任意输入转换为指定类型
        
        Args:
            input_type: 输入类型选择
            output_type: 输出类型选择
            string_input: 字符串输入
            int_input: 整数输入
            float_input: 浮点数输入
            boolean_input: 布尔值输入
            
        Returns:
            转换后的值（三种类型都输出）
        """
        # 首先根据输入类型获取原始值
        if input_type == "STRING":
            raw_value = string_input
        elif input_type == "INT":
            raw_value = int_input
        elif input_type == "FLOAT":
            raw_value = float_input
        else:  # BOOLEAN
            raw_value = boolean_input
        
        # 然后根据输出类型进行转换
        string_result = ""
        int_result = 0
        float_result = 0.0
        
        try:
            if output_type == "STRING":
                # 转换为字符串
                string_result = str(raw_value)
                # 同时提供其他类型的转换
                if input_type == "STRING":
                    try:
                        int_result = int(string_input) if string_input.strip() else 0
                    except ValueError:
                        int_result = 0
                    try:
                        float_result = float(string_input) if string_input.strip() else 0.0
                    except ValueError:
                        float_result = 0.0
                elif input_type == "INT":
                    int_result = int_input
                    float_result = float(int_input)
                elif input_type == "FLOAT":
                    int_result = int(float_input)
                    float_result = float_input
                else:  # BOOLEAN
                    int_result = 1 if boolean_input else 0
                    float_result = 1.0 if boolean_input else 0.0
                    
            elif output_type == "INT":
                # 转换为整数
                if input_type == "STRING":
                    int_result = int(string_input) if string_input.strip() else 0
                elif input_type == "INT":
                    int_result = int_input
                elif input_type == "FLOAT":
                    int_result = int(float_input)
                else:  # BOOLEAN
                    int_result = 1 if boolean_input else 0
                
                # 同时提供其他类型的转换
                string_result = str(int_result)
                float_result = float(int_result)
                
            else:  # FLOAT
                # 转换为浮点数
                if input_type == "STRING":
                    float_result = float(string_input) if string_input.strip() else 0.0
                elif input_type == "INT":
                    float_result = float(int_input)
                elif input_type == "FLOAT":
                    float_result = float_input
                else:  # BOOLEAN
                    float_result = 1.0 if boolean_input else 0.0
                
                # 同时提供其他类型的转换
                string_result = str(float_result)
                int_result = int(float_result)
                
        except (ValueError, TypeError):
            # 转换失败时使用默认值
            string_result = ""
            int_result = 0
            float_result = 0.0
        
        # 打印调试信息
        print(f"kktools Something to Any:")
        print(f"  Input Type: {input_type}")
        print(f"  Output Type: {output_type}")
        print(f"  String Input: {repr(string_input)}")
        print(f"  Int Input: {int_input}")
        print(f"  Float Input: {float_input}")
        print(f"  Boolean Input: {boolean_input}")
        print(f"  String Output: {repr(string_result)}")
        print(f"  Int Output: {int_result}")
        print(f"  Float Output: {float_result}")
        
        return (string_result, int_result, float_result)


# 更新 __all__ 列表
__all__ = [
    'StringNode',           # 基础字符串裁剪
    'StringNodeAdvanced',   # 高级字符串裁剪
    'StringMergeNode',      # 字符串合并
    'InputNode',            # 多类型输入
    'ReplaceNode',          # 字符串替换
    'SomethingToAny'        # 任意类型转换
]