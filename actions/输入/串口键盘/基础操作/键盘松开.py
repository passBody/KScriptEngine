# -*- coding: utf-8 -*-
"""
串口键盘松开步骤（输入/串口键盘/进阶操作流程）
============================================

:class:`SerialKeyRelease`：松开键盘键（``Key:Release {m}``）。

输入槽
------
* ``串口``（string）：设备所在串口名，自定义视图为下拉框。
* ``按键``（string）：键名。

运行规则
--------
* 与 :class:`~actions.输入.串口键盘.进阶操作.键盘按下.SerialKeyPress` 配对使用
  （长按 = 按下 → 其它步骤 → 松开）。
* 键名原样下发，字母大小写由设备内部统一转小写。
"""
from dataclasses import dataclass

from tools.serial_step import SerialStep

__all__ = ["SerialKeyRelease"]


@dataclass
class SerialKeyReleaseInput:
    """输入：串口名与键名（string）。"""
    串口: "string" = ""  # type: ignore
    按键: "string" = ""  # type: ignore


@dataclass
class SerialKeyReleaseOutput:
    """无输出。"""
    pass


class SerialKeyRelease(SerialStep):
    """串口键盘松开步骤：下发 Key:Release 松开指定键。"""

    name = "串口键盘松开"
    description = "松开指定键盘键（Key:Release）\n支持 f1 ctrl enter esc win alt 等"
    input_class = SerialKeyReleaseInput
    output_class = SerialKeyReleaseOutput

    def run(self) -> int:
        key = self._str(self.inputs.按键, "按键")
        if key is None:
            return 1
        self._send("Key:Release %s" % key)
        return 1


# ================================================================
# 冒烟演示：直接 ``python -m actions.输入.串口键盘.进阶操作.键盘松开`` 运行
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
    tree.add("空串", ProjectVariable.create("string", "", pkg))

    s = SerialKeyRelease.create_default(tree, pkg)
    assert (s.io._input_type, s.io._output_type) == (["string", "string"], [])
    assert s.name == "串口键盘松开"

    stub = install_stub_serial()
    s.io.change_value("input", 0, "COM7")
    s.io.change_value("input", 1, "ctrl")
    assert s.do() == 1
    assert s.status is StepStatus.FINISHED, s.status
    assert stub.calls == [("COM7", "Key:Release ctrl")], stub.calls

    # 空按键（经变量引用解析为空串）→ 执行错误、不下发
    stub.calls.clear()
    s.io.change_value("input", 1, "{{空串}}")
    LogModel.instance().clear()
    assert s.do() == 1
    assert s.status is StepStatus.ERROR
    assert stub.calls == [], stub.calls
    assert any("按键 为空" in e.message for e in LogModel.instance().entries), \
        [e.message for e in LogModel.instance().entries]

    # 与「键盘按下」配对：长按 ctrl 的命令序列
    from .键盘按下 import SerialKeyPress
    stub.calls.clear()
    s.io.change_value("input", 1, "Ctrl")
    p = SerialKeyPress.create_default(tree, pkg)
    p.io.change_value("input", 0, "COM7")
    p.io.change_value("input", 1, "Ctrl")
    assert p.do() == 1 and s.do() == 1
    assert stub.calls == [("COM7", "Key:Press Ctrl"),
                          ("COM7", "Key:Release Ctrl")], stub.calls

    # 往返
    fmt = s.to_format_string()
    s2 = SerialKeyRelease.from_format_string(fmt, tree, pkg)
    assert isinstance(s2, SerialKeyRelease)
    assert s2.io.to_format_string() == s.io.to_format_string()

    print("SerialKeyRelease smoke OK")
