# -*- coding: utf-8 -*-
"""
延时步骤（控制流程）
====================

:class:`TimeDelay`：延时指定秒数（单位 s）。输入 ``seconds``（number），无输出。

运行规则
--------
* ``seconds > 0``：``time.sleep(seconds)``，返回偏移量 1。
* ``seconds <= 0``：状态切换为「执行错误」，日志报错（不抛异常）。

基本用法
--------
::

    step = TimeDelay.create_default(tree, pkg)
    step.io.change_value("input", 0, "2")    # 延时 2 秒
    offset = step.do()                        # 1
"""
import time
from dataclasses import dataclass

from model.步骤.step import Step, StepStatus
from model.log_model import LogModel
from model.执行.run_interrupt import interruptible_sleep

__all__ = ["TimeDelay"]


@dataclass
class TimeDelayInput:
    """输入：延时秒数（number）。"""
    seconds: "number" = 0.5 # type: ignore  # 评审#28：默认 0.0 恒为错误态


@dataclass
class TimeDelayOutput:
    """无输出。"""
    pass


class TimeDelay(Step):
    """延时步骤：用于延时（单位s）。"""

    name = "固定延时"
    description = "用于延时（单位s）"
    input_class = TimeDelayInput
    output_class = TimeDelayOutput

    def run(self) -> int:
        if self.inputs.seconds <= 0:
            self.status = StepStatus.ERROR
            LogModel.instance().error(
                "延时秒数必须大于 0: %r" % self.inputs.seconds)
        else:
            # 可中断睡眠：执行器「立即停止」时 ~20ms 内返回（未登记事件时即普通 sleep）
            interruptible_sleep(self.inputs.seconds)
        return 1

# ================================================================
# 冒烟演示：直接 ``python -m actions.控制流程.time_delay`` 运行
# ================================================================
if __name__ == "__main__":
    import sys
    import time

    from PyQt5.QtWidgets import QApplication

    from model.工程.kscp_package import KscpPackage
    from model.log_model import LogModel
    from model.变量.variable_tree import VariableTree

    app = QApplication.instance() or QApplication(sys.argv)

    pkg = KscpPackage.create_empty()
    tree = VariableTree.create_empty()

    # create_default：槽类型由字段签名推导
    t = TimeDelay.create_default(tree, pkg)
    assert t.io._input_type == ["number"]
    assert t.io._output_type == []
    assert t.name == "延时" and t.description == "用于延时（单位s）"
    assert t.status is StepStatus.PENDING

    # 正常：延时 0.05s，状态 FINISHED，偏移量 1
    t.io.change_value("input", 0, "0.05")
    t0 = time.monotonic()
    assert t.do() == 1
    assert time.monotonic() - t0 >= 0.05
    assert t.status is StepStatus.FINISHED

    # 非法：seconds <= 0 → 状态 ERROR + 日志报错（不抛异常）
    LogModel.instance().clear()
    t.io.change_value("input", 0, "0")
    assert t.do() == 1
    assert t.status is StepStatus.ERROR
    assert any("延时秒数必须大于 0" in e.message
               for e in LogModel.instance().entries)
    assert len(LogModel.instance().entries) == 1

    # 负值同样报错
    t.io.change_value("input", 0, "-1")
    assert t.do() == 1
    assert t.status is StepStatus.ERROR

    # 往返：还原后可继续执行
    fmt = t.to_format_string()
    assert "=" not in fmt and "+" not in fmt and "/" not in fmt
    t2 = TimeDelay.from_format_string(fmt, tree, pkg)
    assert isinstance(t2, TimeDelay)
    assert t2.io.to_format_string() == t.io.to_format_string()
    t2.io.change_value("input", 0, "0.05")
    assert t2.do() == 1 and t2.status is StepStatus.FINISHED

    # ---- 中断 True 分支：登记停止事件并置位 → 秒级延时被立即打断 ----
    # 真实 interruptible_sleep + 线程本地事件（复现执行器「立即停止」路径）
    import threading as _th
    import model.执行.run_interrupt as _ri
    _ev = _th.Event()
    _ri.set_stop_event(_ev)
    try:
        _ev.set()
        t.io.change_value("input", 0, "5")
        _t0 = time.monotonic()
        assert t.do() == 1
        assert time.monotonic() - _t0 < 1.0      # 5s 延时远未睡满即被打断
    finally:
        _ri.clear_stop_event(_ev)
    # 复位后恢复正常睡眠（0.05 睡满）
    t.io.change_value("input", 0, "0.05")
    _t0 = time.monotonic()
    assert t.do() == 1
    assert time.monotonic() - _t0 >= 0.05
    assert t.status is StepStatus.FINISHED

    print("TimeDelay smoke OK")
