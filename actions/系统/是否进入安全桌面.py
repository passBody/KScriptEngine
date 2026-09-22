# -*- coding: utf-8 -*-
"""
是否进入安全桌面步骤（系统）
============================

:class:`IsSecureDesktop`：判断当前是否处于 Windows **安全桌面**
（UAC 提权确认 / Ctrl+Alt+Del / 登录锁屏）。

安全桌面上鼠标/键盘模拟注入到的是**另一套桌面**，脚本要么等它消失再操作，
要么先判定走分支——本步骤只做判定，不模拟任何输入。

输入槽
------
* 无。

输出槽
------
* ``结果``（string）：``"1"`` = 是（在安全桌面），``"0"`` = 否。

运行规则
--------
* **不打 info 日志**：本步骤的典型用法是放进循环里反复调用（等 UAC 桌面出现），
  每圈一行「是否进入安全桌面：否（…）」会刷屏淹没真正的日志。要看判定依据
  （桌面名 / Win32 错误码）请另挂「打印当前桌面模式」步骤。
* **判不了**（拿不到输入桌面名、又不是「拒绝访问」）→ 置执行错误 + 错误日志，
  **不写输出槽**：此时写 ``"0"`` 等于谎报「不在安全桌面」，而方向反了最危险。
  这条**保留**——它不是循环里刷屏的那条，而恰恰是最该被看见的那条。
* 三级判定与「疑似」的含义见 :mod:`libs.win_desktop`。
"""
from dataclasses import dataclass

from libs.win_desktop import probe_input_desktop
from model.log_model import LogModel
from model.步骤.step import Step, StepStatus

__all__ = ["IsSecureDesktop"]


@dataclass
class IsSecureDesktopInput:
    """无输入。"""
    pass


@dataclass
class IsSecureDesktopOutput:
    """输出：结果（string），"1"=是 / "0"=否。"""
    结果: "string" = ""  # type: ignore


class IsSecureDesktop(Step):
    """是否进入安全桌面步骤：输出 1/0，依据写日志。"""

    name = "是否进入安全桌面"
    description = ("判断当前是否处于 Windows 安全桌面（UAC 提权 / Ctrl+Alt+Del / 登录锁屏）\n"
                   "输出「结果」：1=是，0=否")
    input_class = IsSecureDesktopInput
    output_class = IsSecureDesktopOutput

    def run(self) -> int:
        status = probe_input_desktop()
        if status.secure is None:
            self.status = StepStatus.ERROR
            LogModel.instance().error("%s：%s" % (self.name, status.describe()))
            return 1
        self.outputs.结果 = "1" if status.secure else "0"
        return 1                        # 静默：常被循环调用，依据看「打印当前桌面模式」


# ================================================================
# 冒烟演示：直接 ``python -m actions.系统.是否进入安全桌面`` 运行
# ================================================================
if __name__ == "__main__":
    import sys

    from libs.win_desktop import InputDesktop
    from model.工程.kscp_package import KscpPackage
    from model.变量.project_variable import ProjectVariable
    from model.变量.variable_tree import VariableTree

    _mod = sys.modules[__name__]      # 桩必须挂到当前执行命名空间（runpy 陷阱）

    pkg = KscpPackage.create_empty()
    tree = VariableTree.create_empty()
    tree.add("res", ProjectVariable.create("string", "旧值", pkg))

    s = IsSecureDesktop.create_default(tree, pkg)
    assert s.io._input_type == [] and s.io._output_type == ["string"]
    assert s.name == "是否进入安全桌面"
    s.io.change_value("output", 0, "res")

    def _stub(status):
        """把桩换成「探测返回固定结果」，避免冒烟真的依赖本机桌面状态。"""
        _mod.probe_input_desktop = lambda: status

    def _logs():
        return [(e.level.name, e.message) for e in LogModel.instance().entries]

    # ---- 否：普通桌面 Default → "0"，且**一条日志都不留**（循环调用不刷屏） ----
    _stub(InputDesktop(False, "Default", 0))
    LogModel.instance().clear()
    assert s.do() == 1
    assert s.status is StepStatus.FINISHED, s.status
    assert tree.get("res").get_actual_data() == "0"
    assert _logs() == [], _logs()

    # ---- 是：Winlogon → "1"，同样静默 ----
    _stub(InputDesktop(True, "Winlogon", 0))
    LogModel.instance().clear()
    assert s.do() == 1
    assert s.status is StepStatus.FINISHED
    assert tree.get("res").get_actual_data() == "1"
    assert _logs() == [], _logs()

    # ---- 是（疑似）：被拒（错误码 5）→ "1"，也静默（依据交由「打印当前桌面模式」） ----
    _stub(InputDesktop(True, None, 5))
    LogModel.instance().clear()
    assert s.do() == 1
    assert tree.get("res").get_actual_data() == "1"
    assert _logs() == [], _logs()

    # ---- 判不了 → 执行错误，输出槽**保持旧值**（绝不谎报 "0"） ----
    _stub(InputDesktop(None, None, 87))
    LogModel.instance().clear()
    assert s.do() == 1
    assert s.status is StepStatus.ERROR, s.status
    assert tree.get("res").get_actual_data() == "1", "判不了时不该动输出槽"
    assert any(lv == "ERROR" and "无法判定" in m for lv, m in _logs()), _logs()

    # ---- 真探测也能跑通（只读，无副作用；不断言本机结果） ----
    _mod.probe_input_desktop = probe_input_desktop
    assert s.do() == 1
    assert tree.get("res").get_actual_data() in ("0", "1")

    # ---- 往返 ----
    fmt = s.to_format_string()
    s2 = IsSecureDesktop.from_format_string(fmt, tree, pkg)
    assert isinstance(s2, IsSecureDesktop)
    assert s2.io.to_format_string() == s.io.to_format_string()

    print("IsSecureDesktop smoke OK")
