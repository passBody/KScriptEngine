# -*- coding: utf-8 -*-
"""
设置字符串变量步骤
========================

:class:`SetString`：设置字符串
"""
from dataclasses import dataclass
from model.step import Step, optional


__all__ = ["SetString"]

@dataclass
class SetStringInput:
    """输入：字符串"""
    字符串:"string" = optional("")  # type: ignore


@dataclass
class SetStringOutput:
    """输出：字符串变量"""
    字符串变量:"string" = "" # type: ignore


class SetString(Step):
    """设置字符串变量步骤：设置指定字符串变量"""

    name = "设置字符串变量"
    description = "设置指定字符串变量"
    input_class = SetStringInput
    output_class = SetStringOutput

    def run(self) -> int:
        self.outputs.字符串变量 = str(self.inputs.字符串)
        return 1


# ================================================================
# 冒烟演示：直接 ``python -m actions.变量控制.变量设置.设置string`` 运行
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
    tree.add("s", ProjectVariable.create("string", "", pkg))

    s = SetString.create_default(tree, pkg)
    assert s.io._input_type == ["string"] and s.io._output_type == ["string"]
    assert s.name == "设置字符串变量"

    # do()：输入 "hi" → run() 置 self.outputs.字符串变量 → output() 写回 s
    # （run() 须置 self.outputs，否则 output() 以默认空串覆盖，变量恒为空）
    s.io.change_value("input", 0, "hi")
    s.io.change_value("output", 0, "s")
    LogModel.instance().clear()
    assert s.do() == 1
    assert s.status.value == "执行结束"
    v = tree.get("s")
    assert v.data == "hi" and v.valid, (v.data, v.valid)
    assert not LogModel.instance().entries

    fmt = s.to_format_string()
    s2 = SetString.from_format_string(fmt, tree, pkg)
    assert isinstance(s2, SetString)
    assert s2.io.to_format_string() == s.io.to_format_string()

    print("SetString smoke OK")