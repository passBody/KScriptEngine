# -*- coding: utf-8 -*-
"""
鼠标按下步骤（输入/鼠标/基础操作流程）
========================

:class:`MousePress`：按下指定鼠标
可填 ``{{变量}}`` 引用）。
"""
from dataclasses import dataclass
from model.step import Step

from libs.key_control import InputControl
from model.log_model import LogModel
from pynput import mouse


__all__ = ["MousePress"]

def _new_control() -> InputControl:
    """创建输入设备控制器（冒烟测试替换为桩，避免真实鼠标移动）。"""
    return InputControl()

@dataclass
class MousePressInput:
    """输入：按下指定的鼠标键 -> 1:left | 2:middle | 3:right"""
    指定按键: "number" = ""  # type: ignore


@dataclass
class MousePressOutput:
    """无输出。"""
    pass


class MousePress(Step):
    """鼠标按下步骤：控制鼠标按下"""

    name = "鼠标按下"
    description = "按下指定的鼠标键 -> 1:left | 2:middle | 3:right"
    input_class = MousePressInput
    output_class = MousePressOutput

    def run(self) -> int:
        mode = self.inputs.指定按键
        try:
            mode = int(mode)
            if mode not in [1,2,3]: mode = 0
        except:
            mode = 0
        button = [mouse.Button.unknown, mouse.Button.left, mouse.Button.middle, mouse.Button.right][mode]
        _new_control().mouse_control.press(button)  # 1:left | 2:middle | 3:right
        press_name = ['无效按键', '左键', '中键', '右键'][mode]
        _info = f'控制鼠标按下{press_name}'
        LogModel.instance().info(_info)
        return 1