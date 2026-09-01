# -*- coding: utf-8 -*-
"""
多次点击步骤（输入模拟）
========================

:class:`MultiClick`：按坐标列表依次模拟鼠标左键点击（基于内嵌
:mod:`libs.key_control` 的 :class:`InputControl.mouse_click`）。

输入槽
------
* ``坐标列表``（string）：``"x1,y1;x2,y2;…"`` 形式（可引用变量，如
  image_marker dots 模式标注后生成的坐标串）。
* ``间隔时间``（number，秒）：两次点击之间的等待（末次点击后不等待）。

运行规则
--------
* 坐标列表为空/格式非法：状态「执行错误」+ 日志报错（不抛异常）。
* 否则：逐点 ``mouse_click(x, y)``，点与点之间 sleep 间隔，返回 1。

> 模拟输入到游戏窗口需以管理员身份运行 KScript。
"""
import time
from dataclasses import dataclass
from typing import List, Optional, Tuple

from libs.key_control import InputControl
from model.log_model import LogModel
from model.执行.run_interrupt import interruptible_sleep
from model.步骤.step import Step, StepStatus

__all__ = ["MultiClick"]


def _new_control() -> InputControl:
    """创建输入设备控制器（冒烟测试替换为桩，避免真实鼠标操作）。"""
    return InputControl()


def parse_points(text: str) -> Optional[List[Tuple[float, float]]]:
    """解析 ``"x1,y1;x2,y2;…"`` 坐标串；空/非法 → None。"""
    if not isinstance(text, str) or not text.strip():
        return None
    pts: List[Tuple[float, float]] = []
    for part in text.split(";"):
        part = part.strip()
        if not part:
            return None
        xy = part.split(",")
        if len(xy) != 2:
            return None
        try:
            pts.append((float(xy[0].strip()), float(xy[1].strip())))
        except ValueError:
            return None
    return pts


@dataclass
class MultiClickInput:
    """输入：坐标列表（string）与点击间隔（number 秒）。"""
    坐标列表: "string" = ""  # type: ignore
    间隔时间: "number" = 0.1  # type: ignore


@dataclass
class MultiClickOutput:
    """无输出。"""
    pass


class MultiClick(Step):
    """多次点击步骤：按坐标列表依次左键点击。"""

    name = "多次点击"
    description = "按坐标列表依次模拟鼠标左键点击"
    input_class = MultiClickInput
    output_class = MultiClickOutput

    def run(self) -> int:
        pts = parse_points(self.inputs.坐标列表)
        if not pts:
            self.status = StepStatus.ERROR
            LogModel.instance().error(
                "多次点击步骤：坐标列表为空或格式非法（应为 x1,y1;x2,y2;…）")
            return 1
        interval = self.inputs.间隔时间 if self.inputs.间隔时间 > 0 else 0
        ctl = _new_control()
        for i, (x, y) in enumerate(pts):
            if i and interval:
                # 可中断睡眠：立即停止时中断等待并结束本步骤（不再点击剩余点）
                if interruptible_sleep(interval):
                    break
            ctl.mouse_click(x, y)
        return 1


# ================================================================
# 冒烟演示：直接 ``python -m actions.输入.多次点击`` 运行
# ================================================================
if __name__ == "__main__":
    import sys

    from PyQt5.QtWidgets import QApplication

    from model.工程.kscp_package import KscpPackage
    from model.log_model import LogModel
    from model.变量.project_variable import ProjectVariable
    from model.变量.variable_tree import VariableTree

    # actions/__init__.py 已登记本模块：桩须挂在当前执行命名空间（见 按键.py 注释）
    _mod = sys.modules[__name__]

    app = QApplication.instance() or QApplication(sys.argv)

    pkg = KscpPackage.create_empty()
    tree = VariableTree.create_empty()

    # parse_points：合法/非法/空
    assert parse_points("100,200;300,400") == [(100.0, 200.0), (300.0, 400.0)]
    assert parse_points(" 1.5, 2.5 ") == [(1.5, 2.5)]
    assert parse_points("") is None
    assert parse_points("abc") is None
    assert parse_points("1,2;3") is None
    assert parse_points("1,2;;3,4") is None

    # create_default：槽类型推导
    m = MultiClick.create_default(tree, pkg)
    assert m.io._input_type == ["string", "number"]
    assert m.io._output_type == []
    assert m.name == "多次点击"

    # run 用桩替换（冒烟不得真实鼠标操作）；time.sleep 也用桩（冒烟不等待）
    called = []

    class _StubCtl:
        def mouse_click(self, x, y, duration=None):
            called.append((x, y, duration))

    _mod._new_control = lambda: _StubCtl()
    slept = []
    _orig_sleep = _mod.interruptible_sleep
    _mod.interruptible_sleep = lambda t: (slept.append(t), False)[1]

    # 正常：两点 + 间隔（点间 sleep 一次）
    m.io.change_value("input", 0, "100,200;300,400")
    m.io.change_value("input", 1, "0.2")
    assert m.do() == 1
    assert called == [(100.0, 200.0, None), (300.0, 400.0, None)], called
    assert slept == [0.2], slept
    # 间隔 <= 0 → 不 sleep
    called.clear()
    slept.clear()
    m.io.change_value("input", 1, "0")
    assert m.do() == 1
    assert len(called) == 2 and slept == []
    # 坐标列表非法 → ERROR + 日志（不抛异常）
    LogModel.instance().clear()
    m.io.change_value("input", 0, "abc")
    assert m.do() == 1
    assert m.status is StepStatus.ERROR
    assert any("坐标列表为空或格式非法" in e.message
               for e in LogModel.instance().entries)

    # 往返
    fmt = m.to_format_string()
    assert "=" not in fmt and "+" not in fmt and "/" not in fmt
    m2 = MultiClick.from_format_string(fmt, tree, pkg)
    assert isinstance(m2, MultiClick)
    assert m2.io.to_format_string() == m.io.to_format_string()

    _mod.interruptible_sleep = _orig_sleep
    print("MultiClick smoke OK")
