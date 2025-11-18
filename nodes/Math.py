"""
ComfyUI Custom Node: kktoolsMath
星月数学运算节点 - 数学表达式计算和正则表达式操作
"""

import math
import operator
import re

class MathExpressionNode:
    """数学表达式节点 - 执行数学运算和表达式计算"""
    
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "expression": ("STRING", {
                    "default": "a + b",
                    "multiline": True,
                    "placeholder": "输入数学表达式，例如: a + b, sqrt(x), min(a,b) 等"
                }),
                "a": ("FLOAT", {
                    "default": 0.0,
                    "min": -999999999.0,
                    "max": 999999999.0,
                    "step": 0.1,
                    "display": "number"
                }),
                "b": ("FLOAT", {
                    "default": 0.0,
                    "min": -999999999.0,
                    "max": 999999999.0,
                    "step": 0.1,
                    "display": "number"
                }),
            },
            "optional": {
                "c": ("FLOAT", {
                    "default": 0.0,
                    "min": -999999999.0,
                    "max": 999999999.0,
                    "step": 0.1,
                    "display": "number"
                }),
                "d": ("FLOAT", {
                    "default": 0.0,
                    "min": -999999999.0,
                    "max": 999999999.0,
                    "step": 0.1,
                    "display": "number"
                }),
                "round_decimals": ("INT", {
                    "default": 6,
                    "min": 0,
                    "max": 10,
                    "step": 1,
                    "display": "number"
                }),
            }
        }
    
    RETURN_TYPES = ("FLOAT", "INT", "STRING")
    RETURN_NAMES = ("float_result", "int_result", "string_result")
    FUNCTION = "evaluate_expression"
    CATEGORY = "kktools/Math"
    
    def evaluate_expression(self, expression, a, b, c=0.0, d=0.0, round_decimals=6):
        """
        执行数学表达式计算
        
        Args:
            expression: 数学表达式字符串
            a, b, c, d: 输入变量值
            round_decimals: 结果小数位数
            
        Returns:
            (浮点数结果, 整数结果, 字符串结果)
        """
        try:
            # 安全的环境字典，包含数学函数和常量
            safe_dict = {
                # 输入变量
                'a': a, 'b': b, 'c': c, 'd': d,
                'x': a, 'y': b, 'z': c, 'w': d,
                
                # 基本数学运算
                'add': operator.add,
                'sub': operator.sub,
                'mul': operator.mul,
                'div': operator.truediv,
                'truediv': operator.truediv,
                'floordiv': operator.floordiv,
                'mod': operator.mod,
                'pow': operator.pow,
                
                # 比较运算
                'eq': operator.eq,
                'ne': operator.ne,
                'lt': operator.lt,
                'le': operator.le,
                'gt': operator.gt,
                'ge': operator.ge,
                
                # 数学函数
                'abs': abs,
                'round': round,
                'min': min,
                'max': max,
                'sum': sum,
                
                # 数学常量
                'pi': math.pi,
                'e': math.e,
                'tau': math.tau,
                'inf': math.inf,
                
                # 幂函数和对数
                'sqrt': math.sqrt,
                'exp': math.exp,
                'log': math.log,
                'log10': math.log10,
                'log2': math.log2,
                
                # 特殊函数
                'ceil': math.ceil,
                'floor': math.floor,
                'trunc': math.trunc,
                'fabs': math.fabs,
                'factorial': math.factorial,
                'gcd': math.gcd,
                
                # 统计函数
                'hypot': math.hypot,
                'copysign': math.copysign,
            }
            
            # 执行表达式计算
            result = eval(expression, {"__builtins__": {}}, safe_dict)
            
            # 处理结果
            float_result = float(result)
            int_result = int(round(float_result))
            
            # 四舍五入到指定小数位
            rounded_float = round(float_result, round_decimals)
            
            # 生成字符串结果
            if round_decimals == 0:
                string_result = str(int(rounded_float))
            else:
                string_result = f"{rounded_float:.{round_decimals}f}".rstrip('0').rstrip('.')
            
            # 打印调试信息
            print(f"kktools Math Expression:")
            print(f"  Expression: {expression}")
            print(f"  Variables: a={a}, b={b}, c={c}, d={d}")
            print(f"  Float Result: {float_result}")
            print(f"  Int Result: {int_result}")
            print(f"  String Result: {string_result}")
            
            return (float_result, int_result, string_result)
            
        except Exception as e:
            # 错误处理
            error_msg = f"计算错误: {str(e)}"
            print(f"kktools Math Expression Error: {error_msg}")
            
            # 返回默认值
            return (0.0, 0, error_msg)


class RegexNode:
    """正则表达式节点 - 进行正则表达式匹配和替换"""
    
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "text": ("STRING", {
                    "default": "",
                    "multiline": True,
                    "forceInput": True
                }),
                "pattern": ("STRING", {
                    "default": "",
                    "multiline": False,
                    "forceInput": True
                }),
                "mode": (["match", "search", "findall", "replace"],),
                "replacement": ("STRING", {
                    "default": "",
                    "multiline": False,
                    "forceInput": False
                }),
            }
        }
    
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("result",)
    FUNCTION = "regex_operation"
    CATEGORY = "kktools/Math"
    
    def regex_operation(self, text, pattern, mode, replacement=""):
        """
        执行正则表达式操作
        
        Args:
            text: 输入的文本
            pattern: 正则表达式模式
            mode: 操作模式 (match, search, findall, replace)
            replacement: 替换文本（仅在replace模式下使用）
            
        Returns:
            操作结果字符串
        """
        try:
            if mode == "match":
                # 匹配：从字符串开头进行匹配
                match = re.match(pattern, text)
                if match:
                    return (match.group(0),)
                else:
                    return ("",)
            
            elif mode == "search":
                # 搜索：在字符串中搜索第一个匹配项
                match = re.search(pattern, text)
                if match:
                    return (match.group(0),)
                else:
                    return ("",)
            
            elif mode == "findall":
                # 查找所有：返回所有匹配项，用换行符分隔
                matches = re.findall(pattern, text)
                if matches:
                    return ("\n".join(str(m) for m in matches),)
                else:
                    return ("",)
            
            elif mode == "replace":
                # 替换：替换所有匹配项
                result = re.sub(pattern, replacement, text)
                return (result,)
            
            else:
                return ("Unknown mode",)
        
        except re.error as e:
            return (f"Regex Error: {str(e)}",)
        except Exception as e:
            return (f"Error: {str(e)}",)


class RegexNodeAdvanced:
    """正则表达式高级节点 - 带匹配详情和标志支持"""
    
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "text": ("STRING", {
                    "default": "",
                    "multiline": True,
                    "forceInput": True
                }),
                "pattern": ("STRING", {
                    "default": "",
                    "multiline": False,
                    "forceInput": True
                }),
                "mode": (["match", "search", "findall", "replace"],),
                "replacement": ("STRING", {
                    "default": "",
                    "multiline": False,
                    "forceInput": False
                }),
                "flags": (["none", "IGNORECASE", "MULTILINE", "DOTALL"],),
            }
        }
    
    RETURN_TYPES = ("STRING", "INT", "STRING", "STRING")
    RETURN_NAMES = ("result", "match_count", "matched_text", "info")
    FUNCTION = "regex_operation_advanced"
    CATEGORY = "kktools/Math"
    
    def regex_operation_advanced(self, text, pattern, mode, replacement="", flags="none"):
        """
        执行正则表达式操作（带详细信息）
        
        Args:
            text: 输入的文本
            pattern: 正则表达式模式
            mode: 操作模式 (match, search, findall, replace)
            replacement: 替换文本（仅在replace模式下使用）
            flags: 正则表达式标志
            
        Returns:
            (结果, 匹配数, 匹配的文本, 信息)
        """
        try:
            # 处理标志
            regex_flags = 0
            if flags == "IGNORECASE":
                regex_flags = re.IGNORECASE
            elif flags == "MULTILINE":
                regex_flags = re.MULTILINE
            elif flags == "DOTALL":
                regex_flags = re.DOTALL
            
            if mode == "match":
                match = re.match(pattern, text, regex_flags)
                if match:
                    return (match.group(0), 1, match.group(0), "Match found at start")
                else:
                    return ("", 0, "", "No match found")
            
            elif mode == "search":
                match = re.search(pattern, text, regex_flags)
                if match:
                    return (match.group(0), 1, match.group(0), f"Found at position {match.start()}")
                else:
                    return ("", 0, "", "No match found")
            
            elif mode == "findall":
                matches = re.findall(pattern, text, regex_flags)
                match_count = len(matches)
                matched_text = "\n".join(str(m) for m in matches) if matches else ""
                info = f"Found {match_count} matches"
                return (matched_text, match_count, matched_text, info)
            
            elif mode == "replace":
                result = re.sub(pattern, replacement, text, flags=regex_flags)
                matches_before = len(re.findall(pattern, text, regex_flags))
                return (result, matches_before, f"Replaced {matches_before} occurrences", "Replacement completed")
            
            else:
                return ("Unknown mode", 0, "", "Unknown mode")
        
        except re.error as e:
            return (f"Regex Error: {str(e)}", 0, "", f"Error: {str(e)}")
        except Exception as e:
            return (f"Error: {str(e)}", 0, "", f"Error: {str(e)}")


# ComfyUI 节点注册
NODE_CLASS_MAPPINGS = {
    "MathExpressionNode": MathExpressionNode,
    "RegexNode": RegexNode,
    "RegexNodeAdvanced": RegexNodeAdvanced,
}

# 节点在菜单中显示的名称
NODE_DISPLAY_NAME_MAPPINGS = {
    "MathExpressionNode": "运算（数学表达式）",
    "RegexNode": "运算（正则表达式）",
    "RegexNodeAdvanced": "运算（正则表达式高级）",
}

# 更新 __all__ 列表
__all__ = [
    'MathExpressionNode',   # 数学表达式节点
    'RegexNode',           # 正则表达式节点
    'RegexNodeAdvanced'    # 正则表达式高级节点
]