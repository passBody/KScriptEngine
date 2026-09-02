# -*- coding: utf-8 -*-
"""
步骤
========================

:class:`[[类名]]`：xxxx
"""
from dataclasses import dataclass
from model.step import Step


__all__ = ["[[类名]]"]

@dataclass
class [[类名]]Input:
    """输入：xxx"""
    pass


@dataclass
class [[类名]]Output:
    """输出：xxx"""
    pass


class [[类名]](Step):
    """xxx步骤：xxx"""

    name = "xxx"
    description = "xxx"
    input_class = [[类名]]Input
    output_class = [[类名]]Output

    def run(self) -> int:
        pass
        return 1