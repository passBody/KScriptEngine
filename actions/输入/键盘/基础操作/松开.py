# -*- coding: utf-8 -*-
"""
键盘松开步骤（输入/键盘/基础操作流程）
========================

:class:`KeyRelease`：松开指定键盘键
可填 ``{{变量}}`` 引用）。
"""
from dataclasses import dataclass
from model.步骤.step import Step

from model.log_model import LogModel
from tools.key_controller import key_ctrl


__all__ = ["KeyRelease"]

@dataclass
class KeyReleaseInput:
    """输入：松开指定的键盘键"""
    指定按键: "string" = ""  # type: ignore


@dataclass
class KeyReleaseOutput:
    """无输出。"""
    pass


class KeyRelease(Step):
    """键盘松开步骤：控制键盘松开"""

    name = "键盘松开"
    description = "松开指定的键盘键\n通过`+`号可以组合按键（如`WIN+D`）"
    input_class = KeyReleaseInput
    output_class = KeyReleaseOutput

    def run(self) -> int:
        keys:str = self.inputs.指定按键
        mode = keys.split('+')
        _info = f'控制键盘松开{keys}'
        LogModel.instance().info(_info)
        for i in mode[::-1]:
            key_ctrl.release(i)
        return 1