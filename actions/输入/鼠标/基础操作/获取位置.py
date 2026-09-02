# -*- coding: utf-8 -*-
"""
获取鼠标位置步骤（输入/鼠标/基础操作流程）
========================

:class:`GetMousePosition`：获取当前鼠标位置
可填 ``{{变量}}`` 引用）。
"""
from dataclasses import dataclass
from model.步骤.step import Step

from tools.mouse_controller import mouse_ctrl

__all__ = ["GetMousePosition"]

@dataclass
class GetMousePositionInput:
    """输入：无输入。"""
    pass


@dataclass
class GetMousePositionOutput:
    """无输出。"""
    坐标x: "number" = 0  # type: ignore
    坐标y: "number" = 0  # type: ignore


class GetMousePosition(Step):
    """获取鼠标位置步骤：获取鼠标位置"""

    name = "获取鼠标位置"
    description = "获取当前鼠标位置"
    input_class = GetMousePositionInput
    output_class = GetMousePositionOutput

    def run(self) -> int:
        x, y = mouse_ctrl.get_position()
        self.outputs.坐标x = x
        self.outputs.坐标y = y
        return 1