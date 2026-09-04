# -*- coding: utf-8 -*-
"""
固定偏移跳转步骤（控制流程/分支流程）
========================

:class:`SkipTo`：如果是，则跳过下一个卡片
可填 ``{{变量}}`` 引用）。
"""
from dataclasses import dataclass
from model.步骤.step import Step

__all__ = ["SkipTo"]


@dataclass
class SkipToInput:
    """输入：移动鼠标至 (x, y)"""
    跳转偏移: "number" = 0  # type: ignore


@dataclass
class SkipToOutput:
    """无输出。"""
    pass


class SkipTo(Step):
    """固定偏移跳转步骤：执行固定偏移"""

    name = "固定偏移跳转"
    description = "指定跳转偏移\n1则跳转至下一步\n-1则是上一步\n0报错"
    input_class = SkipToInput
    output_class = SkipToOutput

    def run(self) -> int:
        if int(self.inputs.跳转偏移):
            return int(self.inputs.跳转偏移)
        else:
            raise ValueError("不可跳转至自身")