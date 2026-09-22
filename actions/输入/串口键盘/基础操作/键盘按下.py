# -*- coding: utf-8 -*-
"""
串口键盘按下步骤（输入/串口键盘/进阶操作流程）
============================================

:class:`SerialKeyPress`：按下键盘键不松开（``Key:Press {m}``）。

输入槽
------
* ``串口``（string）：设备所在串口名，自定义视图为下拉框。
* ``按键``（string）：键名，支持 ``f1`` ``ctrl`` ``enter`` ``esc`` ``win``
  ``alt`` 等。

运行规则
--------
* 字母键的大小写由**设备内部**统一转小写，此处原样下发（写 ``A`` 或 ``a``
  效果相同）。
* 组合键请用 :class:`~actions.输入.串口键盘.进阶操作.键盘组合.SerialKeyCombo`
  （设备端保证依次按下、逆序松开的时序），本步骤只按一个键名下发。
* 按下后须由 :class:`~actions.输入.串口键盘.进阶操作.键盘松开.SerialKeyRelease`
  收尾，否则设备的键会一直处于按下态。
"""
from dataclasses import dataclass

from tools.serial_step import SerialStep

__all__ = ["SerialKeyPress"]


@dataclass
class SerialKeyPressInput:
    """输入：串口名与键名（string）。"""
    串口: "string" = ""  # type: ignore
    按键: "string" = ""  # type: ignore


@dataclass
class SerialKeyPressOutput:
    """无输出。"""
    pass


class SerialKeyPress(SerialStep):
    """串口键盘按下步骤：下发 Key:Press 按下指定键。"""

    name = "串口键盘按下"
    description = "按下指定键盘键（Key:Press）\n支持 f1 ctrl enter esc win alt 等"
    input_class = SerialKeyPressInput
    output_class = SerialKeyPressOutput

    def run(self) -> int:
        key = self._str(self.inputs.按键, "按键")
        if key is None:
            return 1
        self._send("Key:Press %s" % key)
        return 1


# ================================================================
# 冒烟演示：直接 ``python -m actions.输入.串口键盘.进阶操作.键盘按下`` 运行
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
    tree.add("k", ProjectVariable.create("string", "enter", pkg))
    tree.add("空串", ProjectVariable.create("string", "", pkg))

    s = SerialKeyPress.create_default(tree, pkg)
    assert (s.io._input_type, s.io._output_type) == (["string", "string"], [])
    assert s.name == "串口键盘按下"

    stub = install_stub_serial()
    s.io.change_value("input", 0, "COM7")

    # 单个键名；大小写原样下发（设备内部转小写）
    s.io.change_value("input", 1, "F1")
    assert s.do() == 1
    assert s.status is StepStatus.FINISHED, s.status
    assert stub.calls == [("COM7", "Key:Press F1")], stub.calls

    # string 变量引用
    stub.calls.clear()
    s.io.change_value("input", 1, "{{k}}")
    assert s.do() == 1
    assert stub.calls == [("COM7", "Key:Press enter")], stub.calls

    # 空按键（经变量引用解析为空串）→ 执行错误、不下发
    stub.calls.clear()
    s.io.change_value("input", 1, "{{空串}}")
    LogModel.instance().clear()
    assert s.do() == 1
    assert s.status is StepStatus.ERROR
    assert stub.calls == [], stub.calls
    assert any("按键 为空" in e.message for e in LogModel.instance().entries), \
        [e.message for e in LogModel.instance().entries]

    # 未选串口 → 执行错误、不下发
    stub.calls.clear()
    s.io.change_value("input", 1, "a")
    s.io.change_value("input", 0, "{{空串}}")
    assert s.do() == 1
    assert s.status is StepStatus.ERROR
    assert stub.calls == [], stub.calls

    # 往返
    fmt = s.to_format_string()
    s2 = SerialKeyPress.from_format_string(fmt, tree, pkg)
    assert isinstance(s2, SerialKeyPress)
    assert s2.io.to_format_string() == s.io.to_format_string()

    print("SerialKeyPress smoke OK")
