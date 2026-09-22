# -*- coding: utf-8 -*-
"""
串口鼠标点击步骤（输入/串口鼠标/进阶操作流程）
============================================

:class:`SerialMouseClick`：在坐标处点击鼠标键，一步完成
（``Mouse:Click {m},{x},{y},{t}``）。

输入槽
------
* ``串口``（string）：设备所在串口名，自定义视图为下拉框。
* ``指定按键``（number，枚举）：1-左键 2-中键 3-右键。
* ``x`` / ``y``（number）：点击坐标（像素，绝对值）。
* ``按住时长``（number，**毫秒**）：按下到松开的等待，**须大于 0**。

运行规则
--------
* 等价于设备端的「定位 → 按下 → 等 t 毫秒 → 松开」一次完成，比在脚本里拆成
  三个步骤少两次串口往返、时序更稳。
* 按键越界 / 时长 ``<= 0`` → 执行错误、不下发。
"""
from dataclasses import dataclass

from tools.serial_step import SerialStep

__all__ = ["SerialMouseClick"]


@dataclass
class SerialMouseClickInput:
    """输入：串口名、鼠标键、坐标与按住时长（毫秒）。"""
    串口: "string" = ""       # type: ignore
    指定按键: "number" = 1     # type: ignore
    x: "number" = 0           # type: ignore
    y: "number" = 0           # type: ignore
    按住时长: "number" = 50    # type: ignore


@dataclass
class SerialMouseClickOutput:
    """无输出。"""
    pass


class SerialMouseClick(SerialStep):
    """串口鼠标点击步骤：下发 Mouse:Click 完成一次点击。"""

    name = "串口鼠标点击"
    description = ("在坐标处点击鼠标键（Mouse:Click m,x,y,t）\n"
                   "m: 1:left 2:middle 3:right；t 为按住时长（毫秒，须 > 0）")
    input_class = SerialMouseClickInput
    output_class = SerialMouseClickOutput

    def run(self) -> int:
        btn = self._button(self.inputs.指定按键)
        x = self._int(self.inputs.x, "x")
        y = self._int(self.inputs.y, "y")
        ms = self._duration_ms(self.inputs.按住时长)
        if btn is None or x is None or y is None or ms is None:
            return 1
        self._send("Mouse:Click %d,%d,%d,%d" % (btn, x, y, ms))
        return 1


# ================================================================
# 冒烟演示：直接 ``python -m actions.输入.串口鼠标.进阶操作.点击`` 运行
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
    tree.add("py", ProjectVariable.create("number", 400, pkg))
    tree.add("空串", ProjectVariable.create("string", "", pkg))

    s = SerialMouseClick.create_default(tree, pkg)
    assert (s.io._input_type, s.io._output_type) == \
        (["string", "number", "number", "number", "number"], [])
    assert s.name == "串口鼠标点击"

    stub = install_stub_serial()
    s.io.change_value("input", 0, "COM7")
    # 注：dataclass 字段默认值只是签名提示，不进 io 槽 —— 全部槽须逐个填
    s.io.change_value("input", 1, "1")
    s.io.change_value("input", 2, "0")
    s.io.change_value("input", 3, "0")
    s.io.change_value("input", 4, "50")
    assert s.do() == 1
    assert s.status is StepStatus.FINISHED, s.status
    assert stub.calls == [("COM7", "Mouse:Click 1,0,0,50")], stub.calls

    # 显式参数；坐标取整、时长取整
    stub.calls.clear()
    s.io.change_value("input", 1, "3")
    s.io.change_value("input", 2, "800")
    s.io.change_value("input", 3, "{{py}}")
    s.io.change_value("input", 4, "120.9")
    assert s.do() == 1
    assert stub.calls == [("COM7", "Mouse:Click 3,800,400,120")], stub.calls

    # 时长 <= 0 → 执行错误、不下发（t>0 是设备约定）
    stub.calls.clear()
    s.io.change_value("input", 4, "0")
    LogModel.instance().clear()
    assert s.do() == 1
    assert s.status is StepStatus.ERROR
    assert stub.calls == [], stub.calls
    assert any("大于 0 毫秒" in e.message for e in LogModel.instance().entries), \
        [e.message for e in LogModel.instance().entries]

    # 按键越界 → 执行错误、不下发
    stub.calls.clear()
    s.io.change_value("input", 4, "50")
    s.io.change_value("input", 1, "4")
    assert s.do() == 1
    assert s.status is StepStatus.ERROR
    assert stub.calls == [], stub.calls
    s.io.change_value("input", 1, "1")

    # 未选串口（经变量引用解析为空串）→ 执行错误、不下发
    stub.calls.clear()
    s.io.change_value("input", 0, "{{空串}}")
    assert s.do() == 1
    assert s.status is StepStatus.ERROR
    assert stub.calls == [], stub.calls
    s.io.change_value("input", 0, "COM7")

    # 往返
    fmt = s.to_format_string()
    s2 = SerialMouseClick.from_format_string(fmt, tree, pkg)
    assert isinstance(s2, SerialMouseClick)
    assert s2.io.to_format_string() == s.io.to_format_string()

    print("SerialMouseClick smoke OK")
