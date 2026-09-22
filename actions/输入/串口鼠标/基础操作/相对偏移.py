# -*- coding: utf-8 -*-
"""
串口鼠标偏移步骤（输入/串口鼠标/基础操作流程）
============================================

:class:`SerialMouseOffset`：鼠标按相对偏移 (dx, dy) 移动
（``Mouse:SETMove {x},{y}``）。

输入槽
------
* ``串口``（string）：设备所在串口名，自定义视图为下拉框。
* ``x`` / ``y``（number）：相对偏移量，**可为负**。

运行规则
--------
* 与 :class:`~actions.输入.串口鼠标.基础操作.设置位置.SerialMousePosition` 的绝对
  定位相对：本步骤不改变设备记录的绝对坐标基准，偏移量直接叠加。
"""
from dataclasses import dataclass

from tools.serial_step import SerialStep

__all__ = ["SerialMouseOffset"]


@dataclass
class SerialMouseOffsetInput:
    """输入：串口名与相对偏移 (dx, dy)。"""
    串口: "string" = ""  # type: ignore
    x: "number" = 0      # type: ignore
    y: "number" = 0      # type: ignore


@dataclass
class SerialMouseOffsetOutput:
    """无输出。"""
    pass


class SerialMouseOffset(SerialStep):
    """串口鼠标偏移步骤：下发 Mouse:SETMove 相对移动。"""

    name = "串口鼠标偏移"
    description = "鼠标按相对偏移移动（Mouse:SETMove x,y），x/y 可为负"
    input_class = SerialMouseOffsetInput
    output_class = SerialMouseOffsetOutput

    def run(self) -> int:
        dx = self._int(self.inputs.x, "x")
        dy = self._int(self.inputs.y, "y")
        if dx is None or dy is None:
            return 1
        self._send("Mouse:SETMove %d,%d" % (dx, dy))
        return 1


# ================================================================
# 冒烟演示：直接 ``python -m actions.输入.串口鼠标.基础操作.相对偏移`` 运行
# ================================================================
if __name__ == "__main__":
    from model.工程.kscp_package import KscpPackage
    from model.步骤.step import StepStatus
    from model.变量.project_variable import ProjectVariable
    from model.变量.variable_tree import VariableTree

    from tools.serial_step import install_stub_serial

    pkg = KscpPackage.create_empty()
    tree = VariableTree.create_empty()
    tree.add("dy", ProjectVariable.create("number", -30, pkg))

    s = SerialMouseOffset.create_default(tree, pkg)
    assert (s.io._input_type, s.io._output_type) == (["string", "number", "number"], [])
    assert s.name == "串口鼠标偏移"

    stub = install_stub_serial()
    s.io.change_value("input", 0, "COM7")

    # 负偏移照样下发（相对位移的核心用例；number 槽的 "-40" 能过 io 校验）
    s.io.change_value("input", 1, "30")
    s.io.change_value("input", 2, "-40")
    assert s.do() == 1
    assert s.status is StepStatus.FINISHED, s.status
    assert stub.calls == [("COM7", "Mouse:SETMove 30,-40")], stub.calls

    # 负值来自 number 变量
    stub.calls.clear()
    s.io.change_value("input", 1, "0")
    s.io.change_value("input", 2, "{{dy}}")
    assert s.do() == 1
    assert stub.calls == [("COM7", "Mouse:SETMove 0,-30")], stub.calls

    # 串口失败 → 执行错误（run 不抛）
    from tools.serial_controller import SerialError
    stub.fail = SerialError("串口 COM7 下发失败: 桩")
    assert s.do() == 1
    assert s.status is StepStatus.ERROR
    stub.fail = None

    # 往返
    fmt = s.to_format_string()
    s2 = SerialMouseOffset.from_format_string(fmt, tree, pkg)
    assert isinstance(s2, SerialMouseOffset)
    assert s2.io.to_format_string() == s.io.to_format_string()

    print("SerialMouseOffset smoke OK")
