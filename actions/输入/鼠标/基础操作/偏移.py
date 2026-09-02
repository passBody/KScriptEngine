# -*- coding: utf-8 -*-
"""
鼠标偏移步骤（输入/鼠标/基础操作流程）
====================================

:class:`MouseOffset`：鼠标按相对偏移 (dx, dy) 移动。
"""
from dataclasses import dataclass

from model.步骤.step import Step
from tools.mouse_controller import mouse_ctrl

__all__ = ["MouseOffset"]


@dataclass
class MouseOffsetInput:
    """输入：鼠标当前坐标偏移 (dx, dy) count次, 每次间隔Cooldown秒。"""
    dx: "number" = 0  # type: ignore
    dy: "number" = 0  # type: ignore
    count: "number" = 0  # type: ignore
    Cooldown: "number" = 0  # type: ignore


@dataclass
class MouseOffsetOutput:
    """输出：无输出。"""
    pass


class MouseOffset(Step):
    """鼠标偏移步骤：鼠标当前坐标偏移 (dx, dy) count次, 每次间隔Cooldown秒。"""

    name = "鼠标偏移"
    description = "鼠标当前坐标偏移 (dx, dy) count次, 每次间隔Cooldown秒。"
    input_class = MouseOffsetInput
    output_class = MouseOffsetOutput

    def run(self) -> int:
        Cooldown = float(self.inputs.Cooldown)
        dx = int(self.inputs.dx)
        dy = int(self.inputs.dy)
        Cooldown = max(0.01, Cooldown)
        for _ in range(int(self.inputs.count)):
            mouse_ctrl.move_relative(dx, dy)
            self.sleep(Cooldown)
        return 1
