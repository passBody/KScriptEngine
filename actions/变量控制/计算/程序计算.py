# -*- coding: utf-8 -*-
"""
计算步骤
========================

:class:`Calculate`：计算
"""
from dataclasses import dataclass
from model.步骤.step import Step, optional
import math


__all__ = ["Calculate"]

@dataclass
class CalculateInput:
    """输入：计算"""
    值1: "string" = ""  # type: ignore
    值2: "string" = optional("")  # type: ignore
    计算符: "string" = ""  # type:ignore


@dataclass
class CalculateOutput:
    """输出：转化到"""
    输出值: "string" = ""  # type: ignore


class Calculate(Step):
    """计算步骤：通过字符串代码直接计算"""

    name = "数值计算"
    description = "通过字符串代码直接计算\n当前只支持俩个值\n求根号 -> math.sqrt(%1%)\n求幂值 -> %1% ** %2%\n加法 -> %1% + %2%"
    input_class = CalculateInput
    output_class = CalculateOutput

    def run(self) -> int:
        计算符:str = str(self.inputs.计算符)
        a = self.inputs.值1
        b = self.inputs.值2
        计算符 = 计算符.replace('%1%', str(a)).replace('%2%', str(b))
        self.outputs.输出值 = eval(计算符, {'math':math})
        return 1