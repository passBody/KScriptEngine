# -*- coding: utf-8 -*-
"""
是否跳过下一个步骤（控制流程/分支流程）
========================

:class:`IsSkipNext`：如果是，则跳过下一个卡片
可填 ``{{变量}}`` 引用）。
"""
from dataclasses import dataclass
from model.步骤.step import Step, optional

__all__ = ["IsSkipNext"]


@dataclass
class IsSkipNextInput:
    """输入：移动鼠标至 (x, y)"""
    判断符: "string" = optional("")  # type: ignore
    是否取反: "number" = 0  # type: ignore


@dataclass
class IsSkipNextOutput:
    """无输出。"""
    pass


class IsSkipNext(Step):
    """是否跳过下一个步骤：如果是则跳过下一个步骤"""

    name = "是否跳过下一个"
    description = (
        f" 如果是则跳过下一个步骤\n "
        f"取反则反之\n "
        f"`0`|``|`False`->为不跳过 其余为跳过\n "
        f"`1`->取反 ; `0`->不取反"
    )
    input_class = IsSkipNextInput
    output_class = IsSkipNextOutput

    def run(self) -> int:
        pd ='' if str(self.inputs.判断符) in ['0','','False'] else 'ok'
        return 2 if bool(str(pd))^int(self.inputs.是否取反) else 1