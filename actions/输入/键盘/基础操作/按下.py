# -*- coding: utf-8 -*-
"""
键盘按下步骤（输入/键盘/基础操作流程）
========================

:class:`KeyPress`：按下指定键盘键
可填 ``{{变量}}`` 引用）。
"""
from dataclasses import dataclass
from model.步骤.step import Step

from model.log_model import LogModel
from tools.key_controller import key_ctrl

__all__ = ["KeyPress"]

@dataclass
class KeyPressInput:
    """输入：按下指定的键盘键"""
    指定按键: "string" = ""  # type: ignore


@dataclass
class KeyPressOutput:
    """无输出。"""
    pass


class KeyPress(Step):
    """键盘按下步骤：控制键盘按下"""

    name = "键盘按下"
    description = "按下指定的键盘键\n通过`+`号可以组合按键（如`WIN+D`）"
    input_class = KeyPressInput
    output_class = KeyPressOutput

    def run(self) -> int:
        keys:str = self.inputs.指定按键
        mode = keys.split('+')
        _info = f'控制键盘按下{keys}'
        LogModel.instance().info(_info)
        for i in mode:
            key_ctrl.press(i)
        return 1