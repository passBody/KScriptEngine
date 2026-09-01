# -*- coding: utf-8 -*-
"""
鼠标定位步骤（输入/鼠标/基础操作流程）
========================

:class:`MousePosition`：将鼠标定位到指定坐标
可填 ``{{变量}}`` 引用）。
"""
from dataclasses import dataclass
from model.step import Step

from libs.key_control import InputControl
from model.log_model import LogModel


__all__ = ["MousePosition"]

def _new_control() -> InputControl:
    """创建输入设备控制器（冒烟测试替换为桩，避免真实鼠标移动）。"""
    return InputControl()

@dataclass
class MousePositionInput:
    """输入：移动鼠标至 (x, y)"""
    x: "number" = ""  # type: ignore
    y: "number" = ""  # type: ignore


@dataclass
class MousePositionOutput:
    """无输出。"""
    pass


class MousePosition(Step):
    """鼠标定位步骤：控制鼠标定位"""

    name = "鼠标定位"
    description = "定位鼠标到指定坐标"
    input_class = MousePositionInput
    output_class = MousePositionOutput

    def run(self) -> int:
        pos = int(self.inputs.x), int(self.inputs.y)
        _new_control().mouse_control.position = pos
        _info = f'控制鼠标定位到{pos}'
        LogModel.instance().info(_info)
        return 1