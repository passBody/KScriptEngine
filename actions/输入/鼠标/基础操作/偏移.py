# -*- coding: utf-8 -*-
"""
鼠标偏移步骤（输入/鼠标/基础操作流程）
========================

:class:`MouseOffset`：鼠标偏移指定坐标
"""
from dataclasses import dataclass
from model.步骤.step import Step

from libs.key_control import InputControl
from model.log_model import LogModel


__all__ = ["MouseOffset"]

def _new_control() -> InputControl:
    """创建输入设备控制器（冒烟测试替换为桩，避免真实鼠标移动）。"""
    return InputControl()

@dataclass
class MouseOffsetInput:
    """输入：鼠标当前坐标偏移(dx, dy)"""
    dx: "number" = ""  # type: ignore
    dy: "number" = ""  # type: ignore


@dataclass
class MouseOffsetOutput:
    """输出：无输出"""
    pass


class MouseOffset(Step):
    """鼠标偏移步骤：鼠标偏移指定坐标"""

    name = "鼠标偏移"
    description = "将鼠标偏移指定坐标"
    input_class = MouseOffsetInput
    output_class = MouseOffsetOutput

    def run(self) -> int:
        control = _new_control()
        pos = int(self.inputs.x), int(self.inputs.y)
        start_pos = control.mouse_position
        control.mouse_control.move(pos)
        end_pos = control.mouse_position
        offset_pos = end_pos[0] - start_pos[0], end_pos[1] - start_pos[1]
        _info = f'控制鼠标从{start_pos}移动到{end_pos} 偏移了{offset_pos}'
        LogModel.instance().info(_info)
        return 1