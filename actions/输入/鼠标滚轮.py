# -*- coding: utf-8 -*-
"""
鼠标滚轮步骤（输入模拟）
========================

:class:`MouseScroll`：滚动鼠标滚轮（基于内嵌 :mod:`libs.key_control` 的
:class:`InputControl.mouse_scroll`）。

输入槽
------
* ``水平滚动``（number）：横向滚动格数，正=向右、负=向左。
* ``垂直滚动``（number）：纵向滚动格数，正=向上、负=向下（pynput 语义）。

> 模拟输入到游戏窗口需以管理员身份运行 KScript。
"""
from dataclasses import dataclass

from libs.key_control import InputControl
from model.步骤.step import Step

__all__ = ["MouseScroll"]


def _new_control() -> InputControl:
    """创建输入设备控制器（冒烟测试替换为桩，避免真实鼠标操作）。"""
    return InputControl()


@dataclass
class MouseScrollInput:
    """输入：水平/垂直滚动格数（number）。"""
    水平滚动: "number" = 0  # type: ignore
    垂直滚动: "number" = 0  # type: ignore


@dataclass
class MouseScrollOutput:
    """无输出。"""
    pass


class MouseScroll(Step):
    """鼠标滚轮步骤：滚动滚轮指定格数。"""

    name = "鼠标滚轮"
    description = "滚动鼠标滚轮（水平/垂直格数，正=右/上）"
    input_class = MouseScrollInput
    output_class = MouseScrollOutput

    def run(self) -> int:
        _new_control().mouse_scroll(
            int(self.inputs.水平滚动), int(self.inputs.垂直滚动))
        return 1


# ================================================================
# 冒烟演示：直接 ``python -m actions.输入.鼠标滚轮`` 运行
# ================================================================
if __name__ == "__main__":
    import sys

    from PyQt5.QtWidgets import QApplication

    from model.工程.kscp_package import KscpPackage
    from model.变量.variable_tree import VariableTree

    # actions/__init__.py 已登记本模块：桩须挂在当前执行命名空间（见 按键.py 注释）
    _mod = sys.modules[__name__]

    app = QApplication.instance() or QApplication(sys.argv)

    pkg = KscpPackage.create_empty()
    tree = VariableTree.create_empty()

    # create_default：槽类型推导
    m = MouseScroll.create_default(tree, pkg)
    assert m.io._input_type == ["number", "number"]
    assert m.io._output_type == []
    assert m.name == "鼠标滚轮"

    # run 用桩替换（冒烟不得真实鼠标操作）
    called = []

    class _StubCtl:
        def mouse_scroll(self, dx, dy):
            called.append((dx, dy))

    _mod._new_control = lambda: _StubCtl()

    m.io.change_value("input", 0, "0")
    m.io.change_value("input", 1, "-3")
    assert m.do() == 1
    assert called == [(0, -3)], called

    # 往返
    fmt = m.to_format_string()
    assert "=" not in fmt and "+" not in fmt and "/" not in fmt
    m2 = MouseScroll.from_format_string(fmt, tree, pkg)
    assert isinstance(m2, MouseScroll)
    assert m2.io.to_format_string() == m.io.to_format_string()

    print("MouseScroll smoke OK")
