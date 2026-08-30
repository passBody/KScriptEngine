# -*- coding: utf-8 -*-
"""
鼠标移动步骤（输入模拟）
========================

:class:`MouseMove`：把鼠标移动到坐标 (x, y)（不按键）。常作为「鼠标点击」
「鼠标拖动」等步骤的前置定位步骤。

输入槽
------
* ``x`` / ``y``（number）：目标坐标（可引用变量）。

> 模拟输入到游戏窗口需以管理员身份运行 KScript。
"""
from dataclasses import dataclass

from libs.key_control import InputControl
from model.step import Step

__all__ = ["MouseMove"]


def _new_control() -> InputControl:
    """创建输入设备控制器（冒烟测试替换为桩，避免真实鼠标移动）。"""
    return InputControl()


@dataclass
class MouseMoveInput:
    """输入：目标坐标 x/y（number）。"""
    x: "number" = 0        # type: ignore
    y: "number" = 0        # type: ignore


@dataclass
class MouseMoveOutput:
    """无输出。"""
    pass


class MouseMove(Step):
    """鼠标移动步骤：把鼠标移动到指定坐标。"""

    name = "鼠标移动"
    description = "把鼠标移动到指定坐标（不按键）"
    input_class = MouseMoveInput
    output_class = MouseMoveOutput

    def run(self) -> int:
        _new_control().mouse_move(self.inputs.x, self.inputs.y)
        return 1


# ================================================================
# 冒烟演示：直接 ``python -m actions.输入.鼠标移动`` 运行
# ================================================================
if __name__ == "__main__":
    import sys

    from PyQt5.QtWidgets import QApplication

    from model.kscp_package import KscpPackage
    from model.variable_tree import VariableTree

    # actions/__init__.py 已登记本模块：桩须挂在当前执行命名空间（见 按键.py 注释）
    _mod = sys.modules[__name__]

    app = QApplication.instance() or QApplication(sys.argv)

    pkg = KscpPackage.create_empty()
    tree = VariableTree.create_empty()

    # create_default：槽类型推导
    m = MouseMove.create_default(tree, pkg)
    assert m.io._input_type == ["number", "number"]
    assert m.io._output_type == []
    assert m.name == "鼠标移动"

    # run 用桩替换（冒烟不得真实鼠标操作）
    called = []

    class _StubCtl:
        def mouse_move(self, x, y):
            called.append((x, y))

    _mod._new_control = lambda: _StubCtl()

    m.io.change_value("input", 0, "100")
    m.io.change_value("input", 1, "200")
    assert m.do() == 1
    assert called == [(100.0, 200.0)], called

    # 往返
    fmt = m.to_format_string()
    assert "=" not in fmt and "+" not in fmt and "/" not in fmt
    m2 = MouseMove.from_format_string(fmt, tree, pkg)
    assert isinstance(m2, MouseMove)
    assert m2.io.to_format_string() == m.io.to_format_string()

    print("MouseMove smoke OK")
