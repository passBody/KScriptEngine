# -*- coding: utf-8 -*-
"""
串口复位步骤（输入/串口鼠标/基础操作流程）
========================================

:class:`SerialReset`：向串口鼠标下发 ``*RST`` 复位设备。

输入槽
------
* ``串口``（string）：设备所在串口名，自定义视图为下拉框（见
  :class:`widgets.卡片.serial_port_view.SerialPortView`）。

运行规则
--------
* 无参数、不读响应。复位后设备屏幕尺寸回到默认 **1920x1024**，需要重新下发
  :class:`~actions.输入.串口鼠标.基础操作.设置屏幕尺寸.SerialSetScreenSize`。

> 串口鼠标以管理员身份运行 KScript 后对游戏窗口的模拟输入才生效。
"""
from dataclasses import dataclass

from tools.serial_step import SerialStep

__all__ = ["SerialReset"]


@dataclass
class SerialResetInput:
    """输入：串口名（string）。"""
    串口: "string" = ""  # type: ignore


@dataclass
class SerialResetOutput:
    """无输出。"""
    pass


class SerialReset(SerialStep):
    """串口复位步骤：下发 *RST 复位设备。"""

    name = "串口复位"
    description = "复位串口鼠标设备（*RST）\n屏幕尺寸恢复默认 1920x1024"
    input_class = SerialResetInput
    output_class = SerialResetOutput

    def run(self) -> int:
        self._send("*RST")
        return 1


# ================================================================
# 冒烟演示：直接 ``python -m actions.输入.串口鼠标.基础操作.复位`` 运行
# ================================================================
if __name__ == "__main__":
    from model.工程.kscp_package import KscpPackage
    from model.log_model import LogModel
    from model.步骤.step import StepStatus
    from model.变量.project_variable import ProjectVariable
    from model.变量.variable_tree import VariableTree

    # 桩打在**基类模块全局**：SerialStep._send 读的正是它，故各 action 冒烟
    # 不必各自打桩（见 tools.serial_step.install_stub_serial 的说明）。
    from tools.serial_step import install_stub_serial

    pkg = KscpPackage.create_empty()
    tree = VariableTree.create_empty()
    tree.add("空串", ProjectVariable.create("string", "", pkg))

    s = SerialReset.create_default(tree, pkg)
    assert (s.io._input_type, s.io._output_type) == (["string"], [])
    assert s.name == "串口复位"

    stub = install_stub_serial()

    # 空串常量进不了 run：io 校验直接拦下（do 重抛）
    s.io.change_value("input", 0, "")
    try:
        s.do()
        raise AssertionError("空串常量应被 io 校验拦下")
    except ValueError:
        pass

    # 空值守卫须经「string 变量引用 → 空串」才触达 run()
    s.io.change_value("input", 0, "{{空串}}")
    LogModel.instance().clear()
    assert s.do() == 1
    assert s.status is StepStatus.ERROR
    assert stub.calls == [], stub.calls
    assert any("未选择串口" in e.message for e in LogModel.instance().entries), \
        [e.message for e in LogModel.instance().entries]

    # 正常：下发 *RST（无参数、不读响应）
    s.io.change_value("input", 0, "COM7")
    LogModel.instance().clear()
    assert s.do() == 1
    assert s.status is StepStatus.FINISHED, s.status
    assert stub.calls == [("COM7", "*RST")], stub.calls
    assert any("*RST" in e.message for e in LogModel.instance().entries), \
        [e.message for e in LogModel.instance().entries]

    # 串口失败 → 执行错误（run 不抛异常）
    from tools.serial_controller import SerialError
    stub.fail = SerialError("打开串口 COM7 失败: 桩")
    LogModel.instance().clear()
    assert s.do() == 1
    assert s.status is StepStatus.ERROR
    assert any(e.level.name == "ERROR" for e in LogModel.instance().entries)
    stub.fail = None

    # 往返
    fmt = s.to_format_string()
    s2 = SerialReset.from_format_string(fmt, tree, pkg)
    assert isinstance(s2, SerialReset)
    assert s2.io.to_format_string() == s.io.to_format_string()

    print("SerialReset smoke OK")
