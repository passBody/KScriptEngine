# -*- coding: utf-8 -*-
"""
按键步骤（输入模拟）
====================

:class:`KeyClick`：模拟键盘按键（基于内嵌 :mod:`libs.key_control` 的
:class:`InputControl`）。键名语义沿用 InputControl：单字符 / 命名键
（space/enter/esc/shift/ctrl/alt 等）/ 多字符 = 同时按下的和弦。

输入槽
------
* ``键名``（string）：按键文本（如 ``'q'`` / ``'space'`` / ``'ae'`` 和弦）。
* ``按住时长``（number，秒）：按下后多久松开。

运行规则
--------
* 键名为空：状态「执行错误」+ 日志报错（不抛异常）。
* 否则：``key_click(键名, 时长 if 时长 > 0 else None)``，返回 1。

> 模拟输入到游戏窗口需以管理员身份运行 KScript。
"""
from dataclasses import dataclass

from libs.key_control import InputControl
from model.log_model import LogModel
from model.step import Step, StepStatus

__all__ = ["KeyClick"]


def _new_control() -> InputControl:
    """创建输入设备控制器（冒烟测试替换为桩，避免真实按键）。"""
    return InputControl()


@dataclass
class KeyClickInput:
    """输入：键名（string）、按住时长（number 秒）。"""
    键名: "string" = ""      # type: ignore
    按住时长: "number" = 0.05 # type: ignore


@dataclass
class KeyClickOutput:
    """无输出。"""
    pass


class KeyClick(Step):
    """按键步骤：模拟键盘按键。"""

    name = "按键"
    description = "模拟键盘按键（单字符/命名键/和弦）"
    input_class = KeyClickInput
    output_class = KeyClickOutput

    def run(self) -> int:
        if not self.inputs.键名:
            self.status = StepStatus.ERROR
            LogModel.instance().error("按键步骤：键名不能为空")
            return 1
        duration = self.inputs.按住时长 if self.inputs.按住时长 > 0 else None
        _new_control().key_click(self.inputs.键名, duration)
        return 1


# ================================================================
# 冒烟演示：直接 ``python -m actions.输入.按键`` 运行
# ================================================================
if __name__ == "__main__":
    import sys

    from PyQt5.QtWidgets import QApplication

    from model.kscp_package import KscpPackage
    from model.log_model import LogModel
    from model.project_variable import ProjectVariable
    from model.variable_tree import VariableTree

    # actions/__init__.py 已登记本模块：runpy 执行前会先被包导入（sys.modules 里
    # 是旧命名空间）。桩必须挂在当前执行命名空间（run 的闭包指向它），否则冒烟会
    # 调用真实 InputControl——故不用 ``import ... as _mod``。
    _mod = sys.modules[__name__]

    app = QApplication.instance() or QApplication(sys.argv)

    pkg = KscpPackage.create_empty()
    tree = VariableTree.create_empty()

    # create_default：槽类型推导
    k = KeyClick.create_default(tree, pkg)
    assert k.io._input_type == ["string", "number"]
    assert k.io._output_type == []
    assert k.name == "按键" and k.status is StepStatus.PENDING

    # run 用桩替换（冒烟不得真实按键）
    called = []

    class _StubCtl:
        def key_click(self, key, duration=None):
            called.append((key, duration))

    _mod._new_control = lambda: _StubCtl()

    # 正常：键名 + 时长
    k.io.change_value("input", 0, "q")
    k.io.change_value("input", 1, "0.1")
    assert k.do() == 1
    assert k.status is StepStatus.FINISHED
    assert called == [("q", 0.1)], called
    # 时长 <= 0 → 传 None（点击）
    called.clear()
    k.io.change_value("input", 1, "0")
    assert k.do() == 1
    assert called == [("q", None)], called
    # 键名为空 → ERROR + 日志（不抛异常）
    # 空常量过不了 StepIOWidget 校验（input() 先于 run() 抛 ValueError），
    # 用「string 变量引用 → 空串」触达 run() 的键名守卫（真实场景：变量为空）
    LogModel.instance().clear()
    tree.add("empty_key", ProjectVariable.create("string", "", pkg))
    k.io.change_value("input", 0, "{{empty_key}}")
    assert k.do() == 1
    assert k.status is StepStatus.ERROR
    assert any("键名不能为空" in e.message for e in LogModel.instance().entries)

    # 往返：还原后可继续执行
    fmt = k.to_format_string()
    assert "=" not in fmt and "+" not in fmt and "/" not in fmt
    k2 = KeyClick.from_format_string(fmt, tree, pkg)
    assert isinstance(k2, KeyClick)
    assert k2.io.to_format_string() == k.io.to_format_string()

    print("KeyClick smoke OK")
