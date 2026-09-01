# -*- coding: utf-8 -*-
"""
设置数字变量步骤
========================

:class:`SetNumber`：设置数字
"""
from dataclasses import dataclass
from model.step import Step


__all__ = ["SetNumber"]

@dataclass
class SetNumberInput:
    """输入：数字"""
    数字:"number" = ""  # type: ignore


@dataclass
class SetNumberOutput:
    """输出：数字变量"""
    数字变量:"number" = "" # type: ignore


class SetNumber(Step):
    """设置数字变量步骤：设置指定数字变量"""

    name = "设置数字变量"
    description = "设置指定数字变量"
    input_class = SetNumberInput
    output_class = SetNumberOutput

    def run(self) -> int:
        self.outputs.数字变量 = float(self.inputs.数字)
        return 1


# ================================================================
# 冒烟演示：直接 ``python -m actions.变量控制.变量设置.设置number`` 运行
# ================================================================
if __name__ == "__main__":
    import sys

    from PyQt5.QtWidgets import QApplication

    from model.kscp_package import KscpPackage
    from model.log_model import LogModel
    from model.project_variable import ProjectVariable
    from model.variable_tree import VariableTree

    app = QApplication.instance() or QApplication(sys.argv)

    pkg = KscpPackage.create_empty()
    tree = VariableTree.create_empty()
    tree.add("n", ProjectVariable.create("number", 0, pkg))

    # create_default：槽类型推导
    s = SetNumber.create_default(tree, pkg)
    assert s.io._input_type == ["number"] and s.io._output_type == ["number"]
    assert s.name == "设置数字变量"

    # do()：输入 500 → run() 置 self.outputs.数字变量 → output() 写回变量 n
    # （若 run() 误用 io.write_outputs 直写、不置 self.outputs，output() 会以
    #   默认空值覆盖 → 「输出槽值不合规（number 类型）」ERROR；此冒烟即防该回归）
    s.io.change_value("input", 0, "500")
    s.io.change_value("output", 0, "n")
    LogModel.instance().clear()
    assert s.do() == 1
    assert s.status.value == "执行结束"
    v = tree.get("n")
    assert v.data == 500.0 and v.valid, (v.data, v.valid)
    assert not LogModel.instance().entries

    # 往返
    fmt = s.to_format_string()
    s2 = SetNumber.from_format_string(fmt, tree, pkg)
    assert isinstance(s2, SetNumber)
    assert s2.io.to_format_string() == s.io.to_format_string()

    print("SetNumber smoke OK")