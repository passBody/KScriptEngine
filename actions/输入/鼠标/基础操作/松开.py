# -*- coding: utf-8 -*-
"""
鼠标松开步骤（输入/鼠标/基础操作流程）
========================

:class:`MouseRelease`：松开指定鼠标
可填 ``{{变量}}`` 引用）。
"""
from dataclasses import dataclass
from model.步骤.step import Step

from libs.key_control import InputControl
from model.log_model import LogModel
from pynput import mouse


__all__ = ["MouseRelease"]

def _new_control() -> InputControl:
    """创建输入设备控制器（冒烟测试替换为桩，避免真实鼠标移动）。"""
    return InputControl()

@dataclass
class MouseReleaseInput:
    """输入：松开指定的鼠标键 -> 1:left | 2:middle | 3:right"""
    指定按键: "number" = ""  # type: ignore


@dataclass
class MouseReleaseOutput:
    """无输出。"""
    pass


class MouseRelease(Step):
    """鼠标松开步骤：控制鼠标松开"""

    name = "鼠标松开"
    description = "松开指定的鼠标键 -> 1:left | 2:middle | 3:right"
    input_class = MouseReleaseInput
    output_class = MouseReleaseOutput

    def run(self) -> int:
        mode = self.inputs.指定按键
        try:
            mode = int(mode)
            if mode not in [1,2,3]: mode = 0
        except:
            mode = 0
        button = [mouse.Button.unknown, mouse.Button.left, mouse.Button.middle, mouse.Button.right][mode]
        _new_control().mouse_control.release(button)  # 1:left | 2:middle | 3:right
        release_name = ['无效按键', '左键', '中键', '右键'][mode]
        _info = f'控制鼠标松开{release_name}'
        LogModel.instance().info(_info)
        return 1