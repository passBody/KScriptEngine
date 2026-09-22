# -*- coding: utf-8 -*-
"""
串口键盘组合步骤（输入/串口键盘/进阶操作流程）
============================================

:class:`SerialKeyCombo`：按下组合键（``Key:Combo {ms},{t}``）。

输入槽
------
* ``串口``（string）：设备所在串口名，自定义视图为下拉框。
* ``组合键``（string）：``+`` 分隔的键名序列，如 ``alt+ctrl+c``。
* ``按住时长``（number，**毫秒**）：全部按下后多久开始松开，**须大于 0**。

运行规则
--------
* 时序由**设备端**保证：按书写顺序依次按下，等待 t 毫秒后**逆序**松开——
  比脚本里拆成多次「按下/松开」准确得多。
* 组合键为空 / 时长 ``<= 0`` → 执行错误、不下发。
"""
from dataclasses import dataclass

from tools.serial_step import SerialStep

__all__ = ["SerialKeyCombo"]


@dataclass
class SerialKeyComboInput:
    """输入：串口名、组合键串与按住时长（毫秒）。"""
    串口: "string" = ""      # type: ignore
    组合键: "string" = ""    # type: ignore
    按住时长: "number" = 50   # type: ignore


@dataclass
class SerialKeyComboOutput:
    """无输出。"""
    pass


class SerialKeyCombo(SerialStep):
    """串口键盘组合步骤：下发 Key:Combo 完成一次组合键。"""

    name = "串口键盘组合"
    description = ("按下组合键（Key:Combo alt+ctrl+c,t）\n"
                   "按书写顺序依次按下，等 t 毫秒后逆序松开；t 须 > 0")
    input_class = SerialKeyComboInput
    output_class = SerialKeyComboOutput

    def run(self) -> int:
        keys = self._str(self.inputs.组合键, "组合键")
        ms = self._duration_ms(self.inputs.按住时长)
        if keys is None or ms is None:
            return 1
        self._send("Key:Combo %s,%d" % (keys, ms))
        return 1


# ================================================================
# 冒烟演示：直接 ``python -m actions.输入.串口键盘.进阶操作.键盘组合`` 运行
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
    tree.add("combo", ProjectVariable.create("string", "win+d", pkg))
    tree.add("空串", ProjectVariable.create("string", "", pkg))

    s = SerialKeyCombo.create_default(tree, pkg)
    assert (s.io._input_type, s.io._output_type) == (["string", "string", "number"], [])
    assert s.name == "串口键盘组合"

    stub = install_stub_serial()
    s.io.change_value("input", 0, "COM7")

    # 题面示例：alt+ctrl+c；组合键原样下发（设备端负责按下/逆序松开时序）
    # 注：dataclass 字段默认值只是签名提示，不进 io 槽 —— 全部槽须逐个填
    s.io.change_value("input", 1, "alt+ctrl+c")
    s.io.change_value("input", 2, "50")
    assert s.do() == 1
    assert s.status is StepStatus.FINISHED, s.status
    assert stub.calls == [("COM7", "Key:Combo alt+ctrl+c,50")], stub.calls

    # 变量引用 + 显式时长
    stub.calls.clear()
    s.io.change_value("input", 1, "{{combo}}")
    s.io.change_value("input", 2, "200")
    assert s.do() == 1
    assert stub.calls == [("COM7", "Key:Combo win+d,200")], stub.calls

    # 空组合键（经变量引用解析为空串）→ 执行错误、不下发
    stub.calls.clear()
    s.io.change_value("input", 1, "{{空串}}")
    LogModel.instance().clear()
    assert s.do() == 1
    assert s.status is StepStatus.ERROR
    assert stub.calls == [], stub.calls
    assert any("组合键 为空" in e.message for e in LogModel.instance().entries), \
        [e.message for e in LogModel.instance().entries]

    # 时长 <= 0 → 执行错误、不下发
    stub.calls.clear()
    s.io.change_value("input", 1, "ctrl+c")
    s.io.change_value("input", 2, "0")
    assert s.do() == 1
    assert s.status is StepStatus.ERROR
    assert stub.calls == [], stub.calls

    # 往返
    fmt = s.to_format_string()
    s2 = SerialKeyCombo.from_format_string(fmt, tree, pkg)
    assert isinstance(s2, SerialKeyCombo)
    assert s2.io.to_format_string() == s.io.to_format_string()

    print("SerialKeyCombo smoke OK")
