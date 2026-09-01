# -*- coding: utf-8 -*-
"""
鼠标拖动步骤（输入模拟）
========================

:class:`MouseDrag`：按住鼠标左键从起点平滑拖拽到终点（基于内嵌
:mod:`libs.key_control` 的 :class:`InputControl.mouse_drag`）。

输入槽
------
* ``起点x`` / ``起点y``（number）：拖拽起点。
* ``终点x`` / ``终点y``（number）：拖拽终点。
* ``移动耗时``（number，秒）：拖拽总耗时（按距离插值平滑移动）；<=0 时瞬间到位。

> 模拟输入到游戏窗口需以管理员身份运行 KScript。
"""
from dataclasses import dataclass

from libs.key_control import InputControl
from model.步骤.step import Step

__all__ = ["MouseDrag"]


def _new_control() -> InputControl:
    """创建输入设备控制器（冒烟测试替换为桩，避免真实鼠标操作）。"""
    return InputControl()


@dataclass
class MouseDragInput:
    """输入：起点/终点坐标与移动耗时。"""
    起点x: "number" = 0   # type: ignore
    起点y: "number" = 0   # type: ignore
    终点x: "number" = 0   # type: ignore
    终点y: "number" = 0   # type: ignore
    移动耗时: "number" = 0.5  # type: ignore


@dataclass
class MouseDragOutput:
    """无输出。"""
    pass


class MouseDrag(Step):
    """鼠标拖动步骤：按住左键从起点拖到终点。"""

    name = "鼠标拖动"
    description = "按住鼠标左键从起点平滑拖拽到终点"
    input_class = MouseDragInput
    output_class = MouseDragOutput

    def run(self) -> int:
        duration = self.inputs.移动耗时 if self.inputs.移动耗时 > 0 else None
        _new_control().mouse_drag(
            self.inputs.起点x, self.inputs.起点y,
            self.inputs.终点x, self.inputs.终点y, duration)
        return 1


# ================================================================
# 冒烟演示：直接 ``python -m actions.输入.鼠标拖动`` 运行
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
    m = MouseDrag.create_default(tree, pkg)
    assert m.io._input_type == ["number", "number", "number", "number", "number"]
    assert m.io._output_type == []
    assert m.name == "鼠标拖动"

    # run 用桩替换（冒烟不得真实鼠标操作）
    called = []

    class _StubCtl:
        def mouse_drag(self, x1, y1, x2, y2, duration=None):
            called.append((x1, y1, x2, y2, duration))

    _mod._new_control = lambda: _StubCtl()

    # 正常：起点/终点/耗时
    m.io.change_value("input", 0, "100")
    m.io.change_value("input", 1, "200")
    m.io.change_value("input", 2, "400")
    m.io.change_value("input", 3, "500")
    m.io.change_value("input", 4, "0.5")
    assert m.do() == 1
    assert called == [(100.0, 200.0, 400.0, 500.0, 0.5)], called
    # 耗时 <= 0 → None（瞬间拖拽）
    called.clear()
    m.io.change_value("input", 4, "0")
    assert m.do() == 1
    assert called == [(100.0, 200.0, 400.0, 500.0, None)], called

    # 往返
    fmt = m.to_format_string()
    assert "=" not in fmt and "+" not in fmt and "/" not in fmt
    m2 = MouseDrag.from_format_string(fmt, tree, pkg)
    assert isinstance(m2, MouseDrag)
    assert m2.io.to_format_string() == m.io.to_format_string()

    print("MouseDrag smoke OK")
