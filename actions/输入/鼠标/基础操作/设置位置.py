# -*- coding: utf-8 -*-
"""
鼠标定位步骤（输入/鼠标/基础操作流程）
========================

:class:`SetMousePosition`：将鼠标定位到指定坐标
可填 ``{{变量}}`` 引用）。
"""
from dataclasses import dataclass
from model.步骤.step import Step

from model.log_model import LogModel
from tools.mouse_controller import mouse_ctrl

__all__ = ["SetMousePosition"]


@dataclass
class SetMousePositionInput:
    """输入：移动鼠标至 (x, y)"""
    x: "number" = ""  # type: ignore
    y: "number" = ""  # type: ignore


@dataclass
class SetMousePositionOutput:
    """无输出。"""
    pass


class SetMousePosition(Step):
    """鼠标定位步骤：控制鼠标定位"""

    name = "鼠标定位"
    description = "定位鼠标到指定坐标"
    input_class = SetMousePositionInput
    output_class = SetMousePositionOutput

    def run(self) -> int:
        pos = int(self.inputs.x), int(self.inputs.y)
        mouse_ctrl.set_position(*pos)
        _info = f'控制鼠标定位到{pos}'
        LogModel.instance().info(_info)
        return 1


# ================================================================
# 冒烟演示：直接 ``python -m actions.输入.鼠标.基础操作.设置位置`` 运行
# ================================================================
if __name__ == "__main__":
    import sys

    from model.工程.kscp_package import KscpPackage
    from model.log_model import LogModel
    from model.步骤.step import StepStatus
    from model.变量.variable_tree import VariableTree

    _mod = sys.modules[__name__]

    pkg = KscpPackage.create_empty()
    tree = VariableTree.create_empty()

    # create_default：槽类型推导
    s = SetMousePosition.create_default(tree, pkg)
    assert s.io._input_type == ["number", "number"]
    assert s.name == "鼠标定位"

    # run 用桩替换（冒烟不得真实鼠标操作）
    called = []

    class _StubCtl:
        def set_position(self, x, y):
            called.append((x, y))

    _mod.mouse_ctrl = _StubCtl()
    s.io.change_value("input", 0, "100")
    s.io.change_value("input", 1, "200")
    LogModel.instance().clear()
    assert s.do() == 1
    assert called == [(100, 200)], called
    assert s.status is StepStatus.FINISHED
    assert any("定位" in e.message for e in LogModel.instance().entries)

    # 往返
    fmt = s.to_format_string()
    s2 = SetMousePosition.from_format_string(fmt, tree, pkg)
    assert isinstance(s2, SetMousePosition)
    assert s2.io.to_format_string() == s.io.to_format_string()

    print("SetMousePosition smoke OK")