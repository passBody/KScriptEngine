# -*- coding: utf-8 -*-
"""
输出日志步骤（控制流程）
========================

:class:`LogStep`：向日志面板输出一条 info 日志。输入 ``消息``（string，
可填 ``{{变量}}`` 引用）。

运行规则
--------
* ``LogModel.instance().info(消息)``，返回 1。
"""
from dataclasses import dataclass

from model.log_model import LogModel
from model.步骤.step import Step

__all__ = ["LogStep"]


@dataclass
class LogStepInput:
    """输入：消息（string）。"""
    消息: "string" = ""  # type: ignore


@dataclass
class LogStepOutput:
    """无输出。"""
    pass


class LogStep(Step):
    """输出日志步骤：向日志面板输出一条信息。"""

    name = "输出日志"
    description = "向日志面板输出一条信息"
    input_class = LogStepInput
    output_class = LogStepOutput

    def run(self) -> int:
        LogModel.instance().info(self.inputs.消息)
        return 1


# ================================================================
# 冒烟演示：直接 ``python -m actions.控制流程.输出日志`` 运行
# ================================================================
if __name__ == "__main__":
    import sys

    from PyQt5.QtWidgets import QApplication

    from model.工程.kscp_package import KscpPackage
    from model.log_model import LogModel
    from model.变量.variable_tree import VariableTree

    app = QApplication.instance() or QApplication(sys.argv)

    pkg = KscpPackage.create_empty()
    tree = VariableTree.create_empty()

    # create_default：槽类型推导
    s = LogStep.create_default(tree, pkg)
    assert s.io._input_type == ["string"]
    assert s.io._output_type == []
    assert s.name == "输出日志"

    # run：写入 info 日志
    LogModel.instance().clear()
    s.io.change_value("input", 0, "你好，KScript")
    assert s.do() == 1
    assert s.status.value == "执行结束"
    entries = LogModel.instance().entries
    assert len(entries) == 1 and entries[0].message == "你好，KScript"

    # 往返
    fmt = s.to_format_string()
    assert "=" not in fmt and "+" not in fmt and "/" not in fmt
    s2 = LogStep.from_format_string(fmt, tree, pkg)
    assert isinstance(s2, LogStep)
    assert s2.io.to_format_string() == s.io.to_format_string()

    print("LogStep smoke OK")
