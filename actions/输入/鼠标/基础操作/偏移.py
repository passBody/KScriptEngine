# -*- coding: utf-8 -*-
"""
鼠标偏移步骤（输入/鼠标/基础操作流程）
====================================

:class:`MouseOffset`：鼠标按相对偏移 (dx, dy) 移动。
"""
from dataclasses import dataclass

from libs.key_control import InputControl
from model.log_model import LogModel
from model.步骤.step import Step

__all__ = ["MouseOffset"]


def _new_control() -> InputControl:
    """创建输入设备控制器（冒烟测试替换为桩，避免真实鼠标移动）。"""
    return InputControl()


@dataclass
class MouseOffsetInput:
    """输入：鼠标当前坐标偏移 (dx, dy)。"""
    dx: "number" = 0  # type: ignore
    dy: "number" = 0  # type: ignore


@dataclass
class MouseOffsetOutput:
    """输出：无输出。"""
    pass


class MouseOffset(Step):
    """鼠标偏移步骤：鼠标按相对偏移 (dx, dy) 移动。"""

    name = "鼠标偏移"
    description = "将鼠标偏移指定坐标"
    input_class = MouseOffsetInput
    output_class = MouseOffsetOutput

    def run(self) -> int:
        control = _new_control()
        start_pos = control.mouse_position
        control.mouse_control.move(int(self.inputs.dx), int(self.inputs.dy))
        end_pos = control.mouse_position
        offset_pos = end_pos[0] - start_pos[0], end_pos[1] - start_pos[1]
        LogModel.instance().info(
            "鼠标从 %s 偏移到 %s，实际偏移 %s"
            % (start_pos, end_pos, offset_pos))
        return 1


# ================================================================
# 冒烟演示：直接 ``python -m actions.输入.鼠标.基础操作.偏移`` 运行
# ================================================================
if __name__ == "__main__":
    import sys

    from PyQt5.QtWidgets import QApplication

    from model.工程.kscp_package import KscpPackage
    from model.log_model import LogModel
    from model.步骤.step import StepStatus
    from model.变量.variable_tree import VariableTree

    # actions/__init__.py 已登记本模块：桩须挂在当前执行命名空间（见 按键.py 注释）
    _mod = sys.modules[__name__]

    app = QApplication.instance() or QApplication(sys.argv)

    pkg = KscpPackage.create_empty()
    tree = VariableTree.create_empty()

    # create_default：槽类型推导
    m = MouseOffset.create_default(tree, pkg)
    assert m.io._input_type == ["number", "number"]
    assert m.name == "鼠标偏移"

    # run 用桩替换（冒烟不得真实鼠标操作）
    called = []

    class _StubMouse:
        def move(self, dx, dy):
            called.append((dx, dy))

    class _StubCtl:
        def __init__(self):
            self.mouse_control = _StubMouse()

        @property
        def mouse_position(self):
            return (100, 100)

    _mod._new_control = lambda: _StubCtl()

    m.io.change_value("input", 0, "30")
    m.io.change_value("input", 1, "-10")
    LogModel.instance().clear()
    assert m.do() == 1
    assert called == [(30, -10)], called          # move(dx, dy) 双参
    assert m.status is StepStatus.FINISHED

    # 往返
    fmt = m.to_format_string()
    m2 = MouseOffset.from_format_string(fmt, tree, pkg)
    assert isinstance(m2, MouseOffset)
    assert m2.io.to_format_string() == m.io.to_format_string()

    print("MouseOffset smoke OK")
