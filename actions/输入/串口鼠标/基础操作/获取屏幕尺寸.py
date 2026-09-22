# -*- coding: utf-8 -*-
"""
串口获取屏幕尺寸步骤（输入/串口鼠标/基础操作流程）
================================================

:class:`SerialGetScreenSize`：查询设备当前标定的屏幕尺寸
（``DISPlay:GETsize?`` → ``{w},{h}``）。

输入槽
------
* ``串口``（string）：设备所在串口名，自定义视图为下拉框。

输出槽
------
* ``宽`` / ``高``（number）：设备回送的像素尺寸。

运行规则
--------
* 响应按 ``w,h`` 解析；无响应（超时）/ 格式非法 / 非数值 → 执行错误、不写输出。
"""
from dataclasses import dataclass

from tools.serial_step import SerialStep

__all__ = ["SerialGetScreenSize"]


@dataclass
class SerialGetScreenSizeInput:
    """输入：串口名（string）。"""
    串口: "string" = ""  # type: ignore


@dataclass
class SerialGetScreenSizeOutput:
    """输出：屏幕宽高（number）。"""
    宽: "number" = 0  # type: ignore
    高: "number" = 0  # type: ignore


class SerialGetScreenSize(SerialStep):
    """串口获取屏幕尺寸步骤：查询设备当前屏幕尺寸 DISPlay:GETsize?。"""

    name = "串口获取屏幕尺寸"
    description = "查询设备当前屏幕尺寸（DISPlay:GETsize?）\n回送 w,h 写入「宽」「高」输出变量"
    input_class = SerialGetScreenSizeInput
    output_class = SerialGetScreenSizeOutput

    def run(self) -> int:
        resp = self._query("DISPlay:GETsize?")
        if resp is None:
            return 1
        parts = [p.strip() for p in resp.split(",")]
        if len(parts) != 2:
            self._fail("屏幕尺寸响应格式非法（期望 w,h）: %r" % resp)
            return 1
        w = self._int(parts[0], "宽")
        h = self._int(parts[1], "高")
        if w is None or h is None:
            return 1
        self.outputs.宽 = w
        self.outputs.高 = h
        return 1


# ================================================================
# 冒烟演示：直接 ``python -m actions.输入.串口鼠标.基础操作.获取屏幕尺寸`` 运行
# ================================================================
if __name__ == "__main__":
    from model.工程.kscp_package import KscpPackage
    from model.log_model import LogModel
    from model.步骤.step import StepStatus
    from model.变量.project_variable import ProjectVariable
    from model.变量.variable_tree import VariableTree
    from tools.serial_controller import SerialError

    from tools.serial_step import install_stub_serial

    pkg = KscpPackage.create_empty()
    tree = VariableTree.create_empty()
    tree.add("sw", ProjectVariable.create("number", 0, pkg))
    tree.add("sh", ProjectVariable.create("number", 0, pkg))

    s = SerialGetScreenSize.create_default(tree, pkg)
    assert (s.io._input_type, s.io._output_type) == (["string"], ["number", "number"])
    assert s.name == "串口获取屏幕尺寸"
    s.io.change_value("output", 0, "sw")
    s.io.change_value("output", 1, "sh")

    stub = install_stub_serial({"DISPlay:GETsize?": "1920,1024"})
    s.io.change_value("input", 0, "COM7")

    # 正常：w,h 写进输出变量
    assert s.do() == 1
    assert s.status is StepStatus.FINISHED, s.status
    assert stub.calls == [("COM7", "DISPlay:GETsize?")], stub.calls
    assert (tree.get("sw").get_actual_data(), tree.get("sh").get_actual_data()) == (1920, 1024)

    # 带空白/CR 的响应照样解析（控制器已 strip，这里再兜一层字段空白）
    stub.respond = {"DISPlay:GETsize?": " 1280 , 720 "}
    assert s.do() == 1
    assert (tree.get("sw").get_actual_data(), tree.get("sh").get_actual_data()) == (1280, 720)

    # 格式非法（字段数不对）→ 执行错误、输出保持原值
    stub.respond = {"DISPlay:GETsize?": "1280"}
    LogModel.instance().clear()
    assert s.do() == 1
    assert s.status is StepStatus.ERROR
    assert (tree.get("sw").get_actual_data(), tree.get("sh").get_actual_data()) == (1280, 720)
    assert any("格式非法" in e.message for e in LogModel.instance().entries), \
        [e.message for e in LogModel.instance().entries]

    # 字段非数值 → 执行错误
    stub.respond = {"DISPlay:GETsize?": "1280,abc"}
    assert s.do() == 1
    assert s.status is StepStatus.ERROR

    # 无响应（超时）→ 执行错误
    stub.respond = {}
    stub.fail = SerialError("串口 COM7 无响应（超时 1.0s）: DISPlay:GETsize?")
    assert s.do() == 1
    assert s.status is StepStatus.ERROR
    stub.fail = None

    # 往返
    fmt = s.to_format_string()
    s2 = SerialGetScreenSize.from_format_string(fmt, tree, pkg)
    assert isinstance(s2, SerialGetScreenSize)
    assert s2.io.to_format_string() == s.io.to_format_string()

    print("SerialGetScreenSize smoke OK")
