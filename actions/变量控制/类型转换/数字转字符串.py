# -*- coding: utf-8 -*-
"""
数字转字符串步骤
========================

:class:`Number2String`：数字转字符串
"""
from dataclasses import dataclass
from model.step import Step, optional

from model.log_model import LogModel


__all__ = ["Number2String"]

@dataclass
class Number2StringInput:
    """输入：数字转字符串"""
    数字: "number" = ""  # type: ignore


@dataclass
class Number2StringOutput:
    """输出：转化到"""
    字符串: "string" = ""  # type: ignore


class Number2String(Step):
    """数字转字符串步骤：将数字转化为字符串"""

    name = "数字转字符串"
    description = "将数字转化为字符串"
    input_class = Number2StringInput
    output_class = Number2StringOutput

    def run(self) -> int:
        try:
            s = str(self.inputs.数字)
        except:
            _info = f'`{self.inputs.数字}`数字转字符串失败'
            raise ValueError(_info)
        self.outputs.字符串 = s
        return 1


# ================================================================
# 冒烟演示：直接 ``python -m actions.变量控制.类型转换.数字转字符串`` 运行
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
    tree.add("t", ProjectVariable.create("string", "", pkg))

    s = Number2String.create_default(tree, pkg)
    assert s.io._input_type == ["number"] and s.io._output_type == ["string"]
    assert s.name == "数字转字符串"

    # do()：输入 42 → run() 置 self.outputs.字符串 → output() 写回 t
    s.io.change_value("input", 0, "42")
    s.io.change_value("output", 0, "t")
    LogModel.instance().clear()
    assert s.do() == 1
    assert s.status.value == "执行结束"
    v = tree.get("t")
    assert v.data == "42" and v.valid, (v.data, v.valid)
    assert not LogModel.instance().entries

    # 往返
    fmt = s.to_format_string()
    s2 = Number2String.from_format_string(fmt, tree, pkg)
    assert isinstance(s2, Number2String)
    assert s2.io.to_format_string() == s.io.to_format_string()

    print("Number2String smoke OK")