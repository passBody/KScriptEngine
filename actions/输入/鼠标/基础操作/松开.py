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
from tools.mouse_controller import mouse_ctrl


__all__ = ["MouseRelease"]

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
        release_name = ['无效按键', '左键', '中键', '右键'][mode]
        _info = f'控制鼠标松开{release_name}'
        LogModel.instance().info(_info)
        mouse_ctrl.release(['无效按键', 'left', 'middle', 'right'][mode])
        return 1