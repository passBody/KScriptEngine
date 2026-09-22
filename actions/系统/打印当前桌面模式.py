# -*- coding: utf-8 -*-
"""
打印当前桌面模式步骤（系统）
============================

:class:`PrintDesktopMode`：把当前输入桌面（``Default`` / ``Winlogon`` / …）连同
判定依据打印到日志。

**为何单独一个步骤**：「是否进入安全桌面」的典型用法是放进循环里反复调用
（等 UAC 桌面出现），它自己再打日志就是每圈一行刷屏。于是把「看依据」拆出来：
判定步骤静默，想看一眼桌面模式时在循环外挂本步骤。

输入槽
------
* 无。

输出槽
------
* 无（纯打印，不改变流程）。

运行规则
--------
* 恒 info 一行，含桌面名 / Win32 错误码（措辞见
  :meth:`libs.win_desktop.InputDesktop.describe`）。
* **判不了时也只 info、不置错误**：本步骤是诊断用的旁观者，不该把流程打断——
  文字本身就写着「无法判定（…）」。要按判定结果分支，用「是否进入安全桌面」。
"""
from dataclasses import dataclass

from libs.win_desktop import probe_input_desktop
from model.log_model import LogModel
from model.步骤.step import Step

__all__ = ["PrintDesktopMode"]


@dataclass
class PrintDesktopModeInput:
    """无输入。"""
    pass


@dataclass
class PrintDesktopModeOutput:
    """无输出。"""
    pass


class PrintDesktopMode(Step):
    """打印当前桌面模式步骤：一行 info 日志，不改变流程。"""

    name = "打印当前桌面模式"
    description = "把当前输入桌面模式（Default / Winlogon …）与判定依据打印到日志"
    input_class = PrintDesktopModeInput
    output_class = PrintDesktopModeOutput

    def run(self) -> int:
        LogModel.instance().info(
            "%s：%s" % (self.name, probe_input_desktop().describe()))
        return 1


# ================================================================
# 冒烟演示：直接 ``python -m actions.系统.打印当前桌面模式`` 运行
# ================================================================
if __name__ == "__main__":
    import sys

    from libs.win_desktop import InputDesktop
    from model.工程.kscp_package import KscpPackage
    from model.步骤.step import StepStatus
    from model.变量.variable_tree import VariableTree

    _mod = sys.modules[__name__]      # 桩必须挂到当前执行命名空间（runpy 陷阱）
    _real = _mod.probe_input_desktop

    pkg = KscpPackage.create_empty()
    tree = VariableTree.create_empty()

    s = PrintDesktopMode.create_default(tree, pkg)
    assert s.io._input_type == [] and s.io._output_type == []   # 纯打印：两个槽都为空
    assert s.name == "打印当前桌面模式"

    def _stub(status):
        """把桩换成「探测返回固定结果」，避免冒烟真的依赖本机桌面状态。"""
        _mod.probe_input_desktop = lambda: status

    def _logs():
        return [(e.level.name, e.message) for e in LogModel.instance().entries]

    # ---- 否：普通桌面 → 一行 info，带桌面名 ----
    _stub(InputDesktop(False, "Default", 0))
    LogModel.instance().clear()
    assert s.do() == 1
    assert s.status is StepStatus.FINISHED, s.status
    assert _logs() == [("INFO", "打印当前桌面模式：否（当前输入桌面 Default）")], _logs()

    # ---- 是：Winlogon → 同样一行 ----
    _stub(InputDesktop(True, "Winlogon", 0))
    LogModel.instance().clear()
    assert s.do() == 1
    assert any(lv == "INFO" and "Winlogon" in m for lv, m in _logs()), _logs()

    # ---- 判不了：仍只 info、不置错误（旁观者不打断流程），文本写明「无法判定」 ----
    _stub(InputDesktop(None, None, 87))
    LogModel.instance().clear()
    assert s.do() == 1
    assert s.status is StepStatus.FINISHED, s.status
    assert _logs() == [("INFO", "打印当前桌面模式：无法判定（未取到输入桌面，Win32 错误码 87）")], _logs()

    # ---- 与「是否进入安全桌面」互不干扰：真探测也能跑通（只读，不断言本机结果） ----
    _mod.probe_input_desktop = _real
    LogModel.instance().clear()
    assert s.do() == 1
    assert [lv for lv, _ in _logs()] == ["INFO"], _logs()

    # ---- 往返 ----
    fmt = s.to_format_string()
    s2 = PrintDesktopMode.from_format_string(fmt, tree, pkg)
    assert isinstance(s2, PrintDesktopMode)
    assert s2.io.to_format_string() == s.io.to_format_string()

    print("PrintDesktopMode smoke OK")
