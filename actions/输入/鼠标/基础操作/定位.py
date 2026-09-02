# -*- coding: utf-8 -*-
"""
鼠标定位步骤（输入/鼠标/基础操作流程）
========================

:class:`SetMousePosition`：将鼠标定位到指定坐标
可填 ``{{变量}}`` 引用）。
"""
from dataclasses import dataclass
from model.步骤.step import Step

from model.log_model import LogModel
from tools.mouse_controller import mouse_ctrl

__all__ = ["SetMousePosition"]


@dataclass
class SetMousePositionInput:
    """输入：移动鼠标至 (x, y)"""
    x: "number" = ""  # type: ignore
    y: "number" = ""  # type: ignore


@dataclass
class SetMousePositionOutput:
    """无输出。"""
    pass


class SetMousePosition(Step):
    """鼠标定位步骤：控制鼠标定位"""

    name = "鼠标定位"
    description = "定位鼠标到指定坐标"
    input_class = SetMousePositionInput
    output_class = SetMousePositionOutput

    def run(self) -> int:
        pos = int(self.inputs.x), int(self.inputs.y)
        mouse_ctrl.set_position(*pos)
        _info = f'控制鼠标定位到{pos}'
        LogModel.instance().info(_info)
        return 1