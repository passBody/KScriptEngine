# -*- coding: utf-8 -*-
"""
串口鼠标松开步骤（输入/串口鼠标/基础操作流程）
============================================

:class:`SerialMouseRelease`：松开鼠标键（``Mouse:Release {m}``）。

输入槽
------
* ``串口``（string）：设备所在串口名，自定义视图为下拉框。
* ``指定按键``（number，枚举）：1-左键 2-中键 3-右键。

运行规则
--------
* 按键值须为 1/2/3，其它值 → 执行错误、不下发。
* 与 :class:`~actions.输入.串口鼠标.基础操作.按下.SerialMousePress` 配对使用
  （拖拽 = 按下 → 定位 → 松开）。
"""
from dataclasses import dataclass

from tools.serial_step import SerialStep

__all__ = ["SerialMouseRelease"]


@dataclass
class SerialMouseReleaseInput:
    """输入：串口名与鼠标键（1-left/2-middle/3-right）。"""
    串口: "string" = ""    # type: ignore
    指定按键: "number" = 1  # type: ignore


@dataclass
class SerialMouseReleaseOutput:
    """无输出。"""
    pass


class SerialMouseRelease(SerialStep):
    """串口鼠标松开步骤：下发 Mouse:Release 松开指定键。"""

    name = "串口鼠标松开"
    description = "松开指定鼠标键（Mouse:Release）-> 1:left | 2:middle | 3:right"
    input_class = SerialMouseReleaseInput
    output_class = SerialMouseReleaseOutput

    def run(self) -> int:
        btn = self._button(self.inputs.指定按键)
        if btn is None:
            return 1
        self._send("Mouse:Release %d" % btn)
        return 1


# ================================================================
# 冒烟演示：直接 ``python -m actions.输入.串口鼠标.基础操作.松开`` 运行
# ================================================================
if __name__ == "__main__":
    from model.工程.kscp_package import KscpPackage
    from model.log_model import LogModel
    from model.步骤.step import StepStatus
    from model.变量.variable_tree import VariableTree

    from tools.serial_step import install_stub_serial

    pkg = KscpPackage.create_empty()
    tree = VariableTree.create_empty()

    s = SerialMouseRelease.create_default(tree, pkg)
    assert (s.io._input_type, s.io._output_type) == (["string", "number"], [])
    assert s.name == "串口鼠标松开"

    stub = install_stub_serial()
    s.io.change_value("input", 0, "COM7")
    s.io.change_value("input", 1, "1")          # 键值槽（create_default 后为空）
    assert s.do() == 1
    assert s.status is StepStatus.FINISHED, s.status
    assert stub.calls == [("COM7", "Mouse:Release 1")], stub.calls

    stub.calls.clear()
    s.io.change_value("input", 1, "2")
    assert s.do() == 1
    assert stub.calls == [("COM7", "Mouse:Release 2")], stub.calls

    # 越界键值 → 执行错误、不下发
    stub.calls.clear()
    s.io.change_value("input", 1, "0")
    LogModel.instance().clear()
    assert s.do() == 1
    assert s.status is StepStatus.ERROR
    assert stub.calls == [], stub.calls
    assert any("1(左)/2(中)/3(右)" in e.message
               for e in LogModel.instance().entries), \
        [e.message for e in LogModel.instance().entries]

    # 与「按下」配对：按下 → 松开 的命令序列
    from .按下 import SerialMousePress
    stub.calls.clear()
    s.io.change_value("input", 1, "1")
    p = SerialMousePress.create_default(tree, pkg)
    p.io.change_value("input", 0, "COM7")
    p.io.change_value("input", 1, "1")
    assert p.do() == 1 and s.do() == 1
    assert stub.calls == [("COM7", "Mouse:Press 1"), ("COM7", "Mouse:Release 1")], stub.calls

    # 往返
    fmt = s.to_format_string()
    s2 = SerialMouseRelease.from_format_string(fmt, tree, pkg)
    assert isinstance(s2, SerialMouseRelease)
    assert s2.io.to_format_string() == s.io.to_format_string()

    print("SerialMouseRelease smoke OK")
