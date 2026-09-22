# -*- coding: utf-8 -*-
"""
串口设置屏幕尺寸步骤（输入/串口鼠标/基础操作流程）
================================================

:class:`SerialSetScreenSize`：告知设备标定屏幕尺寸
（``DISPlay:SETsize {w},{h}``）。

输入槽
------
* ``串口``（string）：设备所在串口名，自定义视图为下拉框。
* ``宽`` / ``高``（number）：像素尺寸。

运行规则
--------
* 设备按此尺寸把绝对坐标（:class:`~actions.输入.串口鼠标.基础操作.设置位置.SerialMousePosition`）
  映射到屏幕，**改分辨率后必须重新下发**。
* 字段默认值 1920x1024 即设备复位后的默认尺寸（见
  :class:`~actions.输入.串口鼠标.基础操作.复位.SerialReset`），
  与目标机实际分辨率不符时按实际填。
"""
from dataclasses import dataclass

from tools.serial_step import SerialStep

__all__ = ["SerialSetScreenSize"]


@dataclass
class SerialSetScreenSizeInput:
    """输入：串口名与屏幕宽高（number）。"""
    串口: "string" = ""  # type: ignore
    宽: "number" = 1920  # type: ignore
    高: "number" = 1024  # type: ignore


@dataclass
class SerialSetScreenSizeOutput:
    """无输出。"""
    pass


class SerialSetScreenSize(SerialStep):
    """串口设置屏幕尺寸步骤：下发 DISPlay:SETsize。"""

    name = "串口设置屏幕尺寸"
    description = "告知设备屏幕尺寸（DISPlay:SETsize）\n改分辨率后须重新下发"
    input_class = SerialSetScreenSizeInput
    output_class = SerialSetScreenSizeOutput

    def run(self) -> int:
        w = self._int(self.inputs.宽, "宽")
        h = self._int(self.inputs.高, "高")
        if w is None or h is None:
            return 1
        self._send("DISPlay:SETsize %d,%d" % (w, h))
        return 1


# ================================================================
# 冒烟演示：直接 ``python -m actions.输入.串口鼠标.基础操作.设置屏幕尺寸`` 运行
# ================================================================
if __name__ == "__main__":
    from model.工程.kscp_package import KscpPackage
    from model.log_model import LogModel
    from model.步骤.step import StepStatus
    from model.变量.variable_tree import VariableTree

    from tools.serial_step import install_stub_serial

    pkg = KscpPackage.create_empty()
    tree = VariableTree.create_empty()

    s = SerialSetScreenSize.create_default(tree, pkg)
    assert (s.io._input_type, s.io._output_type) == (["string", "number", "number"], [])
    assert s.name == "串口设置屏幕尺寸"

    stub = install_stub_serial()
    s.io.change_value("input", 0, "COM7")
    # 注：dataclass 字段默认值只是签名提示，不进 io 槽 —— create_default 的槽
    # 一律为空，必须逐个填，否则 resolve_inputs 直接判「输入不合规」。
    s.io.change_value("input", 1, "1920")
    s.io.change_value("input", 2, "1024")
    assert s.do() == 1
    assert s.status is StepStatus.FINISHED, s.status
    assert stub.calls == [("COM7", "DISPlay:SETsize 1920,1024")], stub.calls

    # 显式尺寸；小数按向下取整
    stub.calls.clear()
    s.io.change_value("input", 1, "2560")
    s.io.change_value("input", 2, "1440.9")
    assert s.do() == 1
    assert stub.calls == [("COM7", "DISPlay:SETsize 2560,1440")], stub.calls

    # 字符串变量引用数字（io 隐式转换）也能下发
    from model.变量.project_variable import ProjectVariable
    tree.add("W", ProjectVariable.create("number", 1280, pkg))
    tree.add("H", ProjectVariable.create("number", 720, pkg))
    stub.calls.clear()
    s.io.change_value("input", 1, "{{W}}")
    s.io.change_value("input", 2, "{{H}}")
    assert s.do() == 1
    assert stub.calls == [("COM7", "DISPlay:SETsize 1280,720")], stub.calls

    # 串口失败 → 执行错误（run 不抛）
    from tools.serial_controller import SerialError
    stub.fail = SerialError("串口 COM7 下发失败: 桩")
    LogModel.instance().clear()
    assert s.do() == 1
    assert s.status is StepStatus.ERROR
    stub.fail = None

    # 往返
    fmt = s.to_format_string()
    s2 = SerialSetScreenSize.from_format_string(fmt, tree, pkg)
    assert isinstance(s2, SerialSetScreenSize)
    assert s2.io.to_format_string() == s.io.to_format_string()

    print("SerialSetScreenSize smoke OK")
