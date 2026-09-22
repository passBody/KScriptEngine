# -*- coding: utf-8 -*-
"""
串口鼠标按下步骤（输入/串口鼠标/基础操作流程）
============================================

:class:`SerialMousePress`：按下鼠标键不松开（``Mouse:Press {m}``）。

输入槽
------
* ``串口``（string）：设备所在串口名，自定义视图为下拉框。
* ``指定按键``（number，枚举）：1-左键 2-中键 3-右键。

运行规则
--------
* 按键值须为 1/2/3，其它值 → 执行错误、不下发（与同类模板「无效按键」的宽容
  处理不同：串口命令下发到硬件，宁可停步也不发无效指令）。
* 按下后须由 :class:`~actions.输入.串口鼠标.基础操作.松开.SerialMouseRelease`
  或 :class:`~actions.输入.串口鼠标.进阶操作.点击.SerialMouseClick` 收尾，
  否则设备的键会一直处于按下态。
"""
from dataclasses import dataclass

from tools.serial_step import SerialStep

__all__ = ["SerialMousePress"]


@dataclass
class SerialMousePressInput:
    """输入：串口名与鼠标键（1-left/2-middle/3-right）。"""
    串口: "string" = ""    # type: ignore
    指定按键: "number" = 1  # type: ignore


@dataclass
class SerialMousePressOutput:
    """无输出。"""
    pass


class SerialMousePress(SerialStep):
    """串口鼠标按下步骤：下发 Mouse:Press 按下指定键。"""

    name = "串口鼠标按下"
    description = "按下指定鼠标键（Mouse:Press）-> 1:left | 2:middle | 3:right"
    input_class = SerialMousePressInput
    output_class = SerialMousePressOutput

    def run(self) -> int:
        btn = self._button(self.inputs.指定按键)
        if btn is None:
            return 1
        self._send("Mouse:Press %d" % btn)
        return 1


# ================================================================
# 冒烟演示：直接 ``python -m actions.输入.串口鼠标.基础操作.按下`` 运行
# ================================================================
if __name__ == "__main__":
    from model.工程.kscp_package import KscpPackage
    from model.log_model import LogModel
    from model.步骤.step import StepStatus
    from model.变量.project_variable import ProjectVariable
    from model.变量.variable_tree import VariableTree

    from tools.serial_step import install_stub_serial

    pkg = KscpPackage.create_empty()
    tree = VariableTree.create_empty()
    tree.add("btn", ProjectVariable.create("number", 3, pkg))

    s = SerialMousePress.create_default(tree, pkg)
    assert (s.io._input_type, s.io._output_type) == (["string", "number"], [])
    assert s.name == "串口鼠标按下"

    stub = install_stub_serial()
    s.io.change_value("input", 0, "COM7")
    s.io.change_value("input", 1, "1")          # 键值槽（create_default 后为空）
    assert s.do() == 1
    assert stub.calls == [("COM7", "Mouse:Press 1")], stub.calls

    for _m, _name in (("2", "中键"), ("3", "右键")):
        stub.calls.clear()
        s.io.change_value("input", 1, _m)
        assert s.do() == 1
        assert stub.calls == [("COM7", "Mouse:Press %s" % _m)], (_name, stub.calls)

    # 变量引用
    stub.calls.clear()
    s.io.change_value("input", 1, "{{btn}}")
    assert s.do() == 1
    assert stub.calls == [("COM7", "Mouse:Press 3")], stub.calls

    # 越界键值（9）→ 执行错误、不下发
    stub.calls.clear()
    s.io.change_value("input", 1, "9")
    LogModel.instance().clear()
    assert s.do() == 1
    assert s.status is StepStatus.ERROR
    assert stub.calls == [], stub.calls
    assert any("1(左)/2(中)/3(右)" in e.message
               for e in LogModel.instance().entries), \
        [e.message for e in LogModel.instance().entries]

    # 往返
    fmt = s.to_format_string()
    s2 = SerialMousePress.from_format_string(fmt, tree, pkg)
    assert isinstance(s2, SerialMousePress)
    assert s2.io.to_format_string() == s.io.to_format_string()

    print("SerialMousePress smoke OK")
