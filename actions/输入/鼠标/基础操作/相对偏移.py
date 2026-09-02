# -*- coding: utf-8 -*-
"""
鼠标偏移步骤（输入/鼠标/基础操作流程）
====================================

:class:`MouseOffset`：鼠标按相对偏移 (dx, dy) 移动。
"""
from dataclasses import dataclass

from model.步骤.step import Step
from model.执行.run_interrupt import interruptible_sleep
from tools.mouse_controller import mouse_ctrl

__all__ = ["MouseOffset"]


@dataclass
class MouseOffsetInput:
    """输入：鼠标当前坐标偏移 (dx, dy) count次, 每次间隔Cooldown秒。"""
    dx: "number" = 0  # type: ignore
    dy: "number" = 0  # type: ignore
    count: "number" = 0  # type: ignore
    Cooldown: "number" = 0  # type: ignore


@dataclass
class MouseOffsetOutput:
    """输出：无输出。"""
    pass


class MouseOffset(Step):
    """鼠标偏移步骤：鼠标当前坐标偏移 (dx, dy) count次, 每次间隔Cooldown秒。"""

    name = "鼠标偏移"
    description = "鼠标当前坐标偏移 (dx, dy) count次, 每次间隔Cooldown秒。"
    input_class = MouseOffsetInput
    output_class = MouseOffsetOutput

    def run(self) -> int:
        Cooldown = float(self.inputs.Cooldown)
        dx = int(self.inputs.dx)
        dy = int(self.inputs.dy)
        Cooldown = max(0.01, Cooldown)
        for _ in range(int(self.inputs.count)):
            mouse_ctrl.move_relative(dx, dy)
            # 可中断睡眠：执行器「立即停止」时打断连击间隔（Step 无 sleep 方法）
            interruptible_sleep(Cooldown)
        return 1


# ================================================================
# 冒烟演示：直接 ``python -m actions.输入.鼠标.基础操作.相对偏移`` 运行
# ================================================================
if __name__ == "__main__":
    import sys

    from model.工程.kscp_package import KscpPackage
    from model.log_model import LogModel
    from model.步骤.step import StepStatus
    from model.变量.variable_tree import VariableTree

    # actions/__init__.py 已登记本模块：桩须挂在当前执行命名空间（见 按键.py 注释）
    _mod = sys.modules[__name__]

    pkg = KscpPackage.create_empty()
    tree = VariableTree.create_empty()

    # create_default：槽类型推导（dx/dy/count/Cooldown）
    m = MouseOffset.create_default(tree, pkg)
    assert m.io._input_type == ["number", "number", "number", "number"]
    assert m.name == "鼠标偏移"

    # run 用桩替换（冒烟不得真实鼠标操作）
    called = []

    class _StubCtl:
        def move_relative(self, dx, dy):
            called.append((dx, dy))

    _mod.mouse_ctrl = _StubCtl()
    slept = []
    _orig_sleep = _mod.interruptible_sleep
    _mod.interruptible_sleep = lambda t: (slept.append(t), False)[1]

    m.io.change_value("input", 0, "30")
    m.io.change_value("input", 1, "-10")
    m.io.change_value("input", 2, "2")
    m.io.change_value("input", 3, "0.05")
    LogModel.instance().clear()
    assert m.do() == 1
    assert called == [(30, -10), (30, -10)], called   # count 次相对移动
    assert slept == [0.05, 0.05], slept               # 每次间隔 Cooldown
    assert m.status is StepStatus.FINISHED

    _mod.interruptible_sleep = _orig_sleep

    # 往返
    fmt = m.to_format_string()
    m2 = MouseOffset.from_format_string(fmt, tree, pkg)
    assert isinstance(m2, MouseOffset)
    assert m2.io.to_format_string() == m.io.to_format_string()

    print("MouseOffset smoke OK")
