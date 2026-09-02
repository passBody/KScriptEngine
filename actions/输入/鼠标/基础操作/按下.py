# -*- coding: utf-8 -*-
"""
鼠标按下步骤（输入/鼠标/基础操作流程）
========================

:class:`MousePress`：按下指定鼠标
可填 ``{{变量}}`` 引用）。
"""
from dataclasses import dataclass
from model.步骤.step import Step

from model.log_model import LogModel
from tools.mouse_controller import mouse_ctrl

__all__ = ["MousePress"]

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
        press_name = ['无效按键', '左键', '中键', '右键'][mode]
        _info = f'控制鼠标按下{press_name}'
        LogModel.instance().info(_info)
        mouse_ctrl.press(['无效按键', 'left', 'middle', 'right'][mode])
        return 1