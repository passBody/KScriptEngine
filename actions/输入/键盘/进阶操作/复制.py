# -*- coding: utf-8 -*-
"""
复制步骤（输入/键盘/进阶操作流程）
========================

:class:`KeyPaste`：按下指定键盘键
可填 ``{{变量}}`` 引用）。
"""
from dataclasses import dataclass
from model.步骤.step import Step, optional

import pyperclip
from tools.key_controller import key_ctrl

__all__ = ["KeyPaste"]

@dataclass
class KeyPasteInput:
    """输入：点击指定的键盘键"""
    复制文本: "string" = optional("")  # type: ignore

@dataclass
class KeyPasteOutput:
    """无输出。"""
    pass

class KeyPaste(Step):
    """复制步骤：在文本编辑框中复制指定字符串"""

    name = "复制"
    description = "在文本编辑框中复制指定字符串\n如果输入为空，则复制已有内容"
    input_class = KeyPasteInput
    output_class = KeyPasteOutput

    def run(self) -> int:
        text:str = self.inputs.复制文本
        if text:
            pyperclip.copy(text)
        return 1