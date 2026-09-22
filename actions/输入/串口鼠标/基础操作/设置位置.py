# -*- coding: utf-8 -*-
"""
串口鼠标定位步骤（输入/串口鼠标/基础操作流程）
============================================

:class:`SerialMousePosition`：把鼠标定位到绝对坐标
（``Mouse:SETPOSAbs {x},{y}``）。

输入槽
------
* ``串口``（string）：设备所在串口名，自定义视图为下拉框。
* ``x`` / ``y``（number）：绝对坐标（像素）。

运行规则
--------
* 坐标按设备当前标定的屏幕尺寸换算，故改分辨率后先下发
  :class:`~actions.输入.串口鼠标.基础操作.设置屏幕尺寸.SerialSetScreenSize`。
"""
from dataclasses import dataclass

from tools.serial_step import SerialStep

__all__ = ["SerialMousePosition"]


@dataclass
class SerialMousePositionInput:
    """输入：串口名与绝对坐标 (x, y)。"""
    串口: "string" = ""  # type: ignore
    x: "number" = 0      # type: ignore
    y: "number" = 0      # type: ignore


@dataclass
class SerialMousePositionOutput:
    """无输出。"""
    pass


class SerialMousePosition(SerialStep):
    """串口鼠标定位步骤：下发 Mouse:SETPOSAbs 绝对定位。"""

    name = "串口鼠标定位"
    description = "定位鼠标到绝对坐标（Mouse:SETPOSAbs x,y）"
    input_class = SerialMousePositionInput
    output_class = SerialMousePositionOutput

    def run(self) -> int:
        x = self._int(self.inputs.x, "x")
        y = self._int(self.inputs.y, "y")
        if x is None or y is None:
            return 1
        self._send("Mouse:SETPOSAbs %d,%d" % (x, y))
        return 1


# ================================================================
# 冒烟演示：直接 ``python -m actions.输入.串口鼠标.基础操作.设置位置`` 运行
# ================================================================
if __name__ == "__main__":
    from model.工程.kscp_package import KscpPackage
    from model.步骤.step import StepStatus
    from model.变量.project_variable import ProjectVariable
    from model.变量.variable_tree import VariableTree

    from tools.serial_step import install_stub_serial

    pkg = KscpPackage.create_empty()
    tree = VariableTree.create_empty()
    tree.add("cx", ProjectVariable.create("number", 640, pkg))

    s = SerialMousePosition.create_default(tree, pkg)
    assert (s.io._input_type, s.io._output_type) == (["string", "number", "number"], [])
    assert s.name == "串口鼠标定位"

    stub = install_stub_serial()
    s.io.change_value("input", 0, "COM7")

    # 常量坐标；小数向下取整
    s.io.change_value("input", 1, "100")
    s.io.change_value("input", 2, "200.7")
    assert s.do() == 1
    assert s.status is StepStatus.FINISHED, s.status
    assert stub.calls == [("COM7", "Mouse:SETPOSAbs 100,200")], stub.calls

    # 变量引用（坐标可来自识别/匹配步骤的输出）
    stub.calls.clear()
    s.io.change_value("input", 1, "{{cx}}")
    s.io.change_value("input", 2, "0")
    assert s.do() == 1
    assert stub.calls == [("COM7", "Mouse:SETPOSAbs 640,0")], stub.calls

    # 串口失败 → 执行错误（run 不抛）
    from tools.serial_controller import SerialError
    stub.fail = SerialError("串口 COM7 下发失败: 桩")
    assert s.do() == 1
    assert s.status is StepStatus.ERROR
    stub.fail = None

    # 往返
    fmt = s.to_format_string()
    s2 = SerialMousePosition.from_format_string(fmt, tree, pkg)
    assert isinstance(s2, SerialMousePosition)
    assert s2.io.to_format_string() == s.io.to_format_string()

    print("SerialMousePosition smoke OK")
