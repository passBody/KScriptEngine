# -*- coding: utf-8 -*-
"""
字符串转数字步骤
========================

:class:`String2Number`：字符串转数字
"""
from dataclasses import dataclass
from model.步骤.step import Step

__all__ = ["String2Number"]

@dataclass
class String2NumberInput:
    """输入：字符串转数字"""
    字符串: "string" = ""  # type: ignore


@dataclass
class String2NumberOutput:
    """输出：转化到"""
    数字: "number" = ""  # type: ignore


class String2Number(Step):
    """字符串转数字步骤：将字符串转化为数字"""

    name = "字符串转数字"
    description = "将字符串转化为数字"
    input_class = String2NumberInput
    output_class = String2NumberOutput

    def run(self) -> int:
        try:
            num = float(self.inputs.字符串)
        except:
            _info = f'`{self.inputs.字符串}`字符串转数字失败'
            raise ValueError(_info)
        self.outputs.数字 = num
        return 1


# ================================================================
# 冒烟演示：直接 ``python -m actions.变量控制.类型转换.字符串转数字`` 运行
# ================================================================
if __name__ == "__main__":
    import sys

    from PyQt5.QtWidgets import QApplication

    from model.工程.kscp_package import KscpPackage
    from model.log_model import LogModel
    from model.变量.project_variable import ProjectVariable
    from model.变量.variable_tree import VariableTree

    app = QApplication.instance() or QApplication(sys.argv)

    pkg = KscpPackage.create_empty()
    tree = VariableTree.create_empty()
    tree.add("m", ProjectVariable.create("number", 0, pkg))

    s = String2Number.create_default(tree, pkg)
    assert s.io._input_type == ["string"] and s.io._output_type == ["number"]
    assert s.name == "字符串转数字"

    # do()：输入 "3.14" → run() 置 self.outputs.数字 → output() 写回 m
    s.io.change_value("input", 0, "3.14")
    s.io.change_value("output", 0, "m")
    LogModel.instance().clear()
    assert s.do() == 1
    assert s.status.value == "执行结束"
    v = tree.get("m")
    assert v.data == 3.14 and v.valid, (v.data, v.valid)
    assert not LogModel.instance().entries

    # 非数字输入 → run() 抛 ValueError → do() 置 ERROR + 日志（不写脏数据）
    bad = String2Number.create_default(tree, pkg)
    bad.io.change_value("input", 0, "abc")
    bad.io.change_value("output", 0, "m")
    LogModel.instance().clear()
    try:
        bad.do()
        raise AssertionError("非数字输入应抛 ValueError")
    except ValueError:
        pass
    assert bad.status.value == "执行错误"
    assert any("转数字失败" in e.message for e in LogModel.instance().entries)

    # 往返
    fmt = s.to_format_string()
    s2 = String2Number.from_format_string(fmt, tree, pkg)
    assert isinstance(s2, String2Number)
    assert s2.io.to_format_string() == s.io.to_format_string()

    print("String2Number smoke OK")