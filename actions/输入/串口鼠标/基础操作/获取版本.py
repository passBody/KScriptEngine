# -*- coding: utf-8 -*-
"""
串口获取版本步骤（输入/串口鼠标/基础操作流程）
============================================

:class:`SerialVersion`：查询串口鼠标设备版本（``*IDN?``）。

输入槽
------
* ``串口``（string）：设备所在串口名，自定义视图为下拉框。

输出槽
------
* ``版本``（string）：设备回送的版本串。

运行规则
--------
* 下发 ``*IDN?`` 并读回一行；无响应（超时）→ 执行错误、不写输出。
"""
from dataclasses import dataclass

from tools.serial_step import SerialStep

__all__ = ["SerialVersion"]


@dataclass
class SerialVersionInput:
    """输入：串口名（string）。"""
    串口: "string" = ""  # type: ignore


@dataclass
class SerialVersionOutput:
    """输出：版本串（string）。"""
    版本: "string" = ""  # type: ignore


class SerialVersion(SerialStep):
    """串口获取版本步骤：查询设备版本 *IDN?。"""

    name = "串口获取版本"
    description = "查询串口鼠标设备版本（*IDN?），写入「版本」输出变量"
    input_class = SerialVersionInput
    output_class = SerialVersionOutput

    def run(self) -> int:
        resp = self._query("*IDN?")
        if resp is None:
            return 1
        self.outputs.版本 = resp
        return 1


# ================================================================
# 冒烟演示：直接 ``python -m actions.输入.串口鼠标.基础操作.获取版本`` 运行
# ================================================================
if __name__ == "__main__":
    from model.工程.kscp_package import KscpPackage
    from model.log_model import LogModel
    from model.步骤.step import StepStatus
    from model.变量.project_variable import ProjectVariable
    from model.变量.variable_tree import VariableTree
    from tools.serial_controller import SerialError

    # 桩打在基类模块全局（SerialStep._query 读的就是它）——见 tools.serial_step
    from tools.serial_step import install_stub_serial

    pkg = KscpPackage.create_empty()
    tree = VariableTree.create_empty()
    tree.add("ver", ProjectVariable.create("string", "", pkg))

    s = SerialVersion.create_default(tree, pkg)
    assert (s.io._input_type, s.io._output_type) == (["string"], ["string"])
    assert s.name == "串口获取版本"
    s.io.change_value("output", 0, "ver")

    stub = install_stub_serial({"*IDN?": "KScript-Serial 1.0"})

    # 正常：响应写进输出变量
    s.io.change_value("input", 0, "COM7")
    assert s.do() == 1
    assert s.status is StepStatus.FINISHED, s.status
    assert stub.calls == [("COM7", "*IDN?")], stub.calls
    assert tree.get("ver").get_actual_data() == "KScript-Serial 1.0"

    # 无响应 → 执行错误、输出变量保持原值
    stub.fail = SerialError("串口 COM7 无响应（超时 1.0s）: *IDN?")
    LogModel.instance().clear()
    assert s.do() == 1
    assert s.status is StepStatus.ERROR
    assert tree.get("ver").get_actual_data() == "KScript-Serial 1.0"
    assert any(e.level.name == "ERROR" for e in LogModel.instance().entries)
    stub.fail = None

    # 往返
    fmt = s.to_format_string()
    s2 = SerialVersion.from_format_string(fmt, tree, pkg)
    assert isinstance(s2, SerialVersion)
    assert s2.io.to_format_string() == s.io.to_format_string()

    print("SerialVersion smoke OK")
