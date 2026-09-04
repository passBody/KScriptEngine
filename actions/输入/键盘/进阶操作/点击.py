# -*- coding: utf-8 -*-
"""
键盘点击步骤（输入/键盘/进阶操作流程）
========================

:class:`KeyPress`：按下指定键盘键
可填 ``{{变量}}`` 引用）。
"""
from dataclasses import dataclass
from model.步骤.step import Step

from model.log_model import LogModel
from tools.key_controller import key_ctrl

__all__ = ["KeyClick"]

@dataclass
class KeyClickInput:
    """输入：点击指定的键盘键"""
    指定按键: "string" = ""  # type: ignore
    持续时间: "number" = 0.05  # type: ignore


@dataclass
class KeyClickOutput:
    """无输出。"""
    pass


class KeyClick(Step):
    """键盘点击步骤：控制键盘点击"""

    name = "键盘点击"
    description = "点击指定的键盘键\n通过`+`号可以组合按键（如`WIN+D`）"
    input_class = KeyClickInput
    output_class = KeyClickOutput

    def run(self) -> int:
        keys:str = self.inputs.指定按键
        mode = keys.split('+')
        _info = f'控制键盘点击{keys}'
        LogModel.instance().info(_info)
        key_ctrl.combo(*mode, duration=self.inputs.持续时间)
        return 1