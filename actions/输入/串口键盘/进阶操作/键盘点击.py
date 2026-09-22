# -*- coding: utf-8 -*-
"""
串口键盘点击步骤（输入/串口键盘/进阶操作流程）
============================================

:class:`SerialKeyTap`：按下并松开一个键（``Key:Tap {m},{t}``）。

输入槽
------
* ``串口``（string）：设备所在串口名，自定义视图为下拉框。
* ``按键``（string）：键名。
* ``按住时长``（number，**毫秒**）：按下到松开的等待，**须大于 0**。

运行规则
--------
* 比脚本里拆成「按下 + 松开」两步少一次串口往返，且中间间隔由设备精确保证。
* 按键为空 / 时长 ``<= 0`` → 执行错误、不下发。
"""
from dataclasses import dataclass

from tools.serial_step import SerialStep

__all__ = ["SerialKeyTap"]


@dataclass
class SerialKeyTapInput:
    """输入：串口名、键名与按住时长（毫秒）。"""
    串口: "string" = ""      # type: ignore
    按键: "string" = ""      # type: ignore
    按住时长: "number" = 50   # type: ignore


@dataclass
class SerialKeyTapOutput:
    """无输出。"""
    pass


class SerialKeyTap(SerialStep):
    """串口键盘点击步骤：下发 Key:Tap 完成一次按键。"""

    name = "串口键盘点击"
    description = ("点击指定键盘键（Key:Tap m,t）\n"
                   "t 为按住时长（毫秒，须 > 0）；支持 f1 ctrl enter esc win alt 等")
    input_class = SerialKeyTapInput
    output_class = SerialKeyTapOutput

    def run(self) -> int:
        key = self._str(self.inputs.按键, "按键")
        ms = self._duration_ms(self.inputs.按住时长)
        if key is None or ms is None:
            return 1
        self._send("Key:Tap %s,%d" % (key, ms))
        return 1


# ================================================================
# 冒烟演示：直接 ``python -m actions.输入.串口键盘.进阶操作.键盘点击`` 运行
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
    tree.add("k", ProjectVariable.create("string", "esc", pkg))
    tree.add("空串", ProjectVariable.create("string", "", pkg))

    s = SerialKeyTap.create_default(tree, pkg)
    assert (s.io._input_type, s.io._output_type) == (["string", "string", "number"], [])
    assert s.name == "串口键盘点击"

    stub = install_stub_serial()
    s.io.change_value("input", 0, "COM7")

    # 注：dataclass 字段默认值只是签名提示，不进 io 槽 —— 全部槽须逐个填
    s.io.change_value("input", 1, "enter")
    s.io.change_value("input", 2, "50")
    assert s.do() == 1
    assert s.status is StepStatus.FINISHED, s.status
    assert stub.calls == [("COM7", "Key:Tap enter,50")], stub.calls

    # 变量引用；时长小数取整
    stub.calls.clear()
    s.io.change_value("input", 1, "{{k}}")
    s.io.change_value("input", 2, "80.4")
    assert s.do() == 1
    assert stub.calls == [("COM7", "Key:Tap esc,80")], stub.calls

    # 时长 <= 0 → 执行错误、不下发
    stub.calls.clear()
    s.io.change_value("input", 2, "0")
    LogModel.instance().clear()
    assert s.do() == 1
    assert s.status is StepStatus.ERROR
    assert stub.calls == [], stub.calls
    assert any("大于 0 毫秒" in e.message for e in LogModel.instance().entries), \
        [e.message for e in LogModel.instance().entries]

    # 空按键 → 执行错误、不下发
    stub.calls.clear()
    s.io.change_value("input", 2, "50")
    s.io.change_value("input", 1, "{{空串}}")
    assert s.do() == 1
    assert s.status is StepStatus.ERROR
    assert stub.calls == [], stub.calls

    # 往返
    fmt = s.to_format_string()
    s2 = SerialKeyTap.from_format_string(fmt, tree, pkg)
    assert isinstance(s2, SerialKeyTap)
    assert s2.io.to_format_string() == s.io.to_format_string()

    print("SerialKeyTap smoke OK")
