# -*- coding: utf-8 -*-
"""
获取鼠标位置步骤（输入/鼠标/基础操作流程）
========================

:class:`GetMousePosition`：获取当前鼠标位置
可填 ``{{变量}}`` 引用）。
"""
from dataclasses import dataclass
from model.步骤.step import Step

from tools.mouse_controller import mouse_ctrl

__all__ = ["GetMousePosition"]

@dataclass
class GetMousePositionInput:
    """输入：无输入。"""
    pass


@dataclass
class GetMousePositionOutput:
    """无输出。"""
    坐标x: "number" = 0  # type: ignore
    坐标y: "number" = 0  # type: ignore


class GetMousePosition(Step):
    """获取鼠标位置步骤：获取鼠标位置"""

    name = "获取鼠标位置"
    description = "获取当前鼠标位置"
    input_class = GetMousePositionInput
    output_class = GetMousePositionOutput

    def run(self) -> int:
        x, y = mouse_ctrl.get_position()
        self.outputs.坐标x = x
        self.outputs.坐标y = y
        return 1


# ================================================================
# 冒烟演示：直接 ``python -m actions.输入.鼠标.基础操作.获取位置`` 运行
# ================================================================
if __name__ == "__main__":
    import sys

    from model.工程.kscp_package import KscpPackage
    from model.变量.project_variable import ProjectVariable
    from model.步骤.step import StepStatus
    from model.变量.variable_tree import VariableTree

    _mod = sys.modules[__name__]

    pkg = KscpPackage.create_empty()
    tree = VariableTree.create_empty()
    tree.add("ox", ProjectVariable.create("number", 0, pkg))
    tree.add("oy", ProjectVariable.create("number", 0, pkg))

    # create_default：无输入、两输出（坐标x/坐标y）
    g = GetMousePosition.create_default(tree, pkg)
    assert g.io._input_type == [] and g.io._output_type == ["number", "number"]
    assert g.name == "获取鼠标位置"

    # run 用桩替换（冒烟不得真实读取鼠标）；输出绑定变量
    class _StubCtl:
        def get_position(self):
            return (123, 456)

    _mod.mouse_ctrl = _StubCtl()
    g.io.change_value("output", 0, "ox")
    g.io.change_value("output", 1, "oy")
    assert g.do() == 1
    assert tree.get("ox").get_actual_data() == 123
    assert tree.get("oy").get_actual_data() == 456
    assert g.status is StepStatus.FINISHED

    # 往返
    fmt = g.to_format_string()
    g2 = GetMousePosition.from_format_string(fmt, tree, pkg)
    assert isinstance(g2, GetMousePosition)
    assert g2.io.to_format_string() == g.io.to_format_string()

    print("GetMousePosition smoke OK")