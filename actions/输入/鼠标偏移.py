# -*- coding: utf-8 -*-
from dataclasses import dataclass
import time

from libs.key_control import InputControl
from model.步骤.step import Step

__all__ = ["MouseMove"]


def _new_control() -> InputControl:
    """创建输入设备控制器（冒烟测试替换为桩，避免真实鼠标移动）。"""
    return InputControl()


@dataclass
class MouseOffsetInput:
    """输入：目标坐标 x/y（number）。"""
    x: "number" = 0        # type: ignore
    y: "number" = 0        # type: ignore
    t: "number" = 0        # type: ignore


@dataclass
class MouseOffsetOutput:
    """无输出。"""
    pass


class MouseOffset(Step):
    """鼠标偏移：将鼠标持续偏移t秒。"""

    name = "鼠标偏移"
    description = "将鼠标持续偏移t秒。"
    input_class = MouseOffsetInput
    output_class = MouseOffsetOutput

    def run(self) -> int:
        s = time.time()
        while time.time() - s < self.inputs.t:
            _new_control().mouse_control.move(self.inputs.x, self.inputs.y)
            time.sleep(0.01)
        return 1