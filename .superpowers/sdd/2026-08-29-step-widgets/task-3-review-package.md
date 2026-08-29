# Review package — Task 3 (StepCard)

文件清单: widgets/step_card.py（新建，唯一新文件）

## widgets/step_card.py 全文（当前磁盘状态）
# -*- coding: utf-8 -*-
"""
步骤对象卡片（GUI 控件）
======================

:class:`StepCard` 是「步骤对象」的可视化卡片：顶部条 = 激活按钮 + 步骤名，
中部 = 步骤自定义视图（:meth:`Step.info_widget`），下方 = 输入/输出 GUI
（:meth:`StepIOWidget.gen_widget`，编辑即写回 io 数据）。背景色随步骤状态
（:attr:`Step.status`）与 io 校验（:attr:`StepIOWidget.is_valid`）变化；
左上角激活按钮翻转 :attr:`Step.enabled`（未激活时按钮灰底、卡片边框虚线）。

**状态纯显示**：卡片不执行 ``do()``；``status`` 由外部（后续执行器）设置后
调 :meth:`refresh` 更新颜色。io 非法（输入输出 GUI 有不合规的值）→ 红色，
优先于任何状态色。

基本用法
--------
::

    card = StepCard(step)
    card.refresh()            # 重检 io 校验 + 状态 + 激活 → 重绘颜色
    card.set_selected(True)   # 选中高亮（视图管理）
"""

from __future__ import annotations

from typing import Optional

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QLineEdit, QToolButton, QVBoxLayout, QWidget,
)

from actions.base import Step, StepStatus

__all__ = ["StepCard"]

# 状态 → 背景色（io 非法时红优先）
_STATUS_COLORS = {
    StepStatus.PENDING: "#d9a83a",
    StepStatus.RUNNING: "#4caf50",
    StepStatus.FINISHED: "#bdbdbd",
    StepStatus.ERROR: "#e15554",
}
_INVALID_COLOR = "#e15554"   # io 非法（任何状态优先）
_SELECT_BORDER = "#3a7bd5"   # 选中高亮边框


class StepCard(QFrame):
    """步骤对象卡片：激活按钮 + 自定义视图 + 输入/输出 GUI；背景色随状态/校验变化。"""

    menu_requested = pyqtSignal(object, object)   # (自身, 全局坐标)；菜单由视图统一构建

    def __init__(self, step: Step, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._step = step
        self._selected = False
        self.setFixedSize(240, 340)
        self.setCursor(Qt.PointingHandCursor)

        self._btn_active = QToolButton(self)
        self._btn_active.setCheckable(True)
        self._btn_active.setChecked(step.enabled)
        self._btn_active.setFixedSize(26, 26)
        self._btn_active.setToolTip("激活（勾选运行）/ 停用")
        self._btn_active.clicked.connect(self._on_active_toggled)

        self._name = QLabel(step.name)
        self._name.setStyleSheet(
            "font-weight:bold; font-size:15px; color:#333;"
            " background:transparent; border:none;")

        top = QHBoxLayout()
        top.setContentsMargins(8, 8, 8, 0)
        top.setSpacing(8)
        top.addWidget(self._btn_active)
        top.addWidget(self._name, 1)

        self._info = step.info_widget(self)
        self._io_widget = step.io.gen_widget(self)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 8)
        lay.setSpacing(4)
        lay.addLayout(top)
        lay.addWidget(self._info)
        lay.addWidget(self._io_widget)
        lay.addStretch()

        # 颜色刷新钩子①：io 文本框编辑（QLineEdit 输入即重检）
        for fld in (list(self._io_widget.input_fields)
                    + list(self._io_widget.output_fields)):
            if isinstance(fld, QLineEdit):
                fld.textChanged.connect(lambda *_: self.refresh())
        # 颜色刷新钩子②：资源类按钮经 picker 选择后重检
        orig_picker = step.io.picker

        def _picker(tree, vtype, parent):
            result = orig_picker(tree, vtype, parent)
            self.refresh()
            return result

        step.io.picker = _picker
        self.refresh()

    @property
    def step(self) -> Step:
        return self._step

    def refresh(self) -> None:
        """重检 io 校验 + 状态 + 激活 → 重绘背景色与按钮样式。"""
        self._btn_active.setChecked(self._step.enabled)
        self._update_style()

    def set_selected(self, selected: bool) -> None:
        """选中高亮（视图管理）：选中卡片边框变蓝，不影响状态背景色。"""
        self._selected = selected
        self._update_style()

    # ================================================================
    # 内部
    # ================================================================
    def _on_active_toggled(self, checked: bool) -> None:
        self._step.enabled = checked
        self._update_style()

    def _update_style(self) -> None:
        color = _INVALID_COLOR if not self._step.io.is_valid \
            else _STATUS_COLORS.get(self._step.status,
                                    _STATUS_COLORS[StepStatus.PENDING])
        border = _SELECT_BORDER if self._selected else color
        border_style = "dashed" if not self._step.enabled else "solid"
        self.setStyleSheet(
            "StepCard { background:%s; border:2px %s %s; border-radius:10px; }"
            % (color, border_style, border))
        name_color = "#777" if not self._step.enabled else "#333"
        self._name.setStyleSheet(
            "font-weight:bold; font-size:15px; color:%s;"
            " background:transparent; border:none;" % name_color)
        self._btn_active.setText("✓" if self._step.enabled else "✗")
        self._btn_active.setStyleSheet(
            "QToolButton { border:none; border-radius:13px; color:#fff;"
            " font-weight:bold; font-size:15px; background:%s; }"
            % ("#27ae60" if self._step.enabled else "#9e9e9e"))

    def contextMenuEvent(self, event) -> None:  # noqa: N802 (Qt 命名)
        self.menu_requested.emit(self, event.globalPos())
        event.accept()


# ================================================================
# 冒烟演示：直接 ``python -m widgets.step_card`` 运行
# ================================================================
if __name__ == "__main__":
    import sys

    from PyQt5.QtCore import QPoint
    from PyQt5.QtWidgets import QApplication

    from actions.base import Step
    from model.kscp_package import KscpPackage
    from model.project_variable import ProjectVariable
    from model.variable_tree import VariableTree

    app = QApplication.instance() or QApplication(sys.argv)

    # 桩步骤（与 actions.base 冒烟同款）
    from dataclasses import dataclass

    @dataclass
    class _StubInput:
        a: number = 0  # type: ignore

    @dataclass
    class _StubOutput:
        total: number = 0  # type: ignore

    class _StubStep(Step):
        name = "桩步骤"
        description = "测试用桩步骤"
        input_class = _StubInput
        output_class = _StubOutput

        def run(self) -> int:
            self.outputs.total = self.inputs.a * 2
            return 1

    pkg = KscpPackage.create_empty()
    tree = VariableTree.create_empty()
    tree.add("n1", ProjectVariable.create("number", 100, pkg))

    s = _StubStep.create_default(tree, pkg)
    card = StepCard(s)

    # io 非法（空槽）→ 红优先于状态色
    assert _INVALID_COLOR in card.styleSheet()
    # 配置 io → PENDING 暗黄
    s.io.change_value("input", 0, "5")
    s.io.change_value("output", 0, "n1")
    card.refresh()
    assert _STATUS_COLORS[StepStatus.PENDING] in card.styleSheet()
    # 状态色：RUNNING 绿 / FINISHED 灰 / ERROR 红
    s.status = StepStatus.RUNNING
    card.refresh()
    assert _STATUS_COLORS[StepStatus.RUNNING] in card.styleSheet()
    s.status = StepStatus.FINISHED
    card.refresh()
    assert _STATUS_COLORS[StepStatus.FINISHED] in card.styleSheet()
    s.status = StepStatus.ERROR
    card.refresh()
    assert _STATUS_COLORS[StepStatus.ERROR] in card.styleSheet()
    # io 变非法 → 红优先（PENDING 状态验证优先级）
    s.status = StepStatus.PENDING
    s.io.change_value("input", 0, "")
    card.refresh()
    assert _INVALID_COLOR in card.styleSheet()

    # 激活按钮：翻转 enabled + 按钮样式/边框虚线
    s.io.change_value("input", 0, "5")
    card.refresh()
    assert s.enabled is True
    assert "solid" in card.styleSheet()
    card._btn_active.setChecked(False)
    card._on_active_toggled(False)
    assert s.enabled is False
    assert "dashed" in card.styleSheet()
    assert card._btn_active.text() == "✗"      # 未激活 = 灰底「✗」
    card._on_active_toggled(True)
    assert s.enabled is True and "solid" in card.styleSheet()
    assert card._btn_active.text() == "✓"      # 激活 = 绿底「✓」

    # 选中高亮：蓝边框；不影响状态背景色
    card.set_selected(True)
    assert _SELECT_BORDER in card.styleSheet()
    card.set_selected(False)
    assert _SELECT_BORDER not in card.styleSheet()

    # menu_requested 信号：右键发出（自身, 坐标）
    got = []
    card.menu_requested.connect(lambda c, p: got.append((c, p)))
    card.menu_requested.emit(card, QPoint(1, 2))
    assert got == [(card, QPoint(1, 2))]

    # 尺寸
    assert card.width() == 240 and card.height() == 340

    print("StepCard smoke OK")
