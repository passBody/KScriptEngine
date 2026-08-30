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

import os
import weakref
from typing import Optional, Tuple

from PyQt5.QtCore import QTimer, Qt, pyqtSignal
from PyQt5.QtGui import QCursor
from PyQt5.QtWidgets import (
    QApplication, QFrame, QHBoxLayout, QLabel, QLineEdit, QToolButton,
    QVBoxLayout, QWidget,
)

from model.step import Step, StepStatus

__all__ = ["StepCard", "card_size_for_screen"]

# 卡片样式表：毛玻璃/圆角/柔和状态色 + 属性选择器（动态状态经属性切换）
_CARD_QSS_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "view", "cards.qss")

# 文件缺失/损坏时的最小兜底样式（评审#9：模块级读取会让整个 widgets 包导入失败）
_FALLBACK_CARD_QSS = "StepCard { border-radius: 8px; }"

_CARD_QSS: Optional[str] = None


def _card_qss() -> str:
    """懒加载卡片样式表（首次使用时读取并缓存；缺失/损坏 → 兜底样式）。"""
    global _CARD_QSS
    if _CARD_QSS is None:
        try:
            with open(_CARD_QSS_PATH, encoding="utf-8") as f:
                _CARD_QSS = f.read()
        except OSError:
            _CARD_QSS = _FALLBACK_CARD_QSS
    return _CARD_QSS


def card_size_for_screen() -> Tuple[int, int]:
    """按当前屏幕尺寸计算卡片宽高（随显示器动态缩放）。

    基准：1080p → 240×340（宽 = 屏宽×0.125，高 = 屏高×0.315）；
    4K(3840×2160) → 480×680。多屏取光标所在屏，无则主屏，再兜底 1080p。
    """
    app = QApplication.instance()
    screen = app.screenAt(QCursor.pos()) if app is not None else None
    if screen is None and app is not None:
        screen = app.primaryScreen()
    if screen is None:
        return (240, 340)
    g = screen.availableGeometry()
    return max(180, g.width() * 125 // 1000), max(260, g.height() * 315 // 1000)


def _notify_io_edited(self_ref) -> None:
    """字段 textChanged 槽（弱引用取卡）：卡片存活才重检 + 通知。

    经弱引用而非直接闭包持卡，避免「字段 → textChanged 槽 → 卡片」引用环：
    已弃卡片（视图重建后移出场景）可被回收，其 io 控件随之销毁——不会滞留、
    也不会让 io 同步碰到 C++ 已销毁的旧控件。
    """
    card = self_ref()
    if card is not None:
        card._io_edited()


class StepCard(QFrame):
    """步骤对象卡片：激活按钮 + 自定义视图 + 输入/输出 GUI；背景色随状态/校验变化。"""

    menu_requested = pyqtSignal(object, object)   # (自身, 全局坐标)；菜单由视图统一构建
    io_changed = pyqtSignal()                     # 内容已改（io 编辑/签名编辑）→ 宿主保存链路

    def __init__(self, step: Step, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._step = step
        self._selected = False
        self.setFixedSize(*card_size_for_screen())   # 尺寸随显示器动态变化
        self.setCursor(Qt.PointingHandCursor)

        self._btn_active = QToolButton(self)
        self._btn_active.setObjectName("btnActive")
        self._btn_active.setCheckable(True)
        self._btn_active.setChecked(step.enabled)
        self._btn_active.setFixedSize(26, 26)
        self._btn_active.setToolTip("激活（勾选运行）/ 停用")
        self._btn_active.clicked.connect(self._on_active_toggled)

        self._name = QLabel(step.name)
        self._name.setObjectName("cardName")

        # 阴影由视图在场景层绘制（_CardShadowItem）；此处禁用 QGraphicsEffect：
        # QGraphicsDropShadowEffect 挂在 QGraphicsProxyWidget 上会让卡片整体渲染
        # 白屏（Qt 5.15 Windows 纹理化 bug），且 Qt QSS 不支持 box-shadow。
        self.setStyleSheet(_card_qss())   # 静态规则文件 + 动态属性选择器

        top = QHBoxLayout()
        top.setContentsMargins(8, 8, 8, 0)
        top.setSpacing(6)
        top.addWidget(self._btn_active)
        top.addWidget(self._name, 0)          # 步骤名（小字，固定）
        self._tag_edit = QLineEdit(step.tag)
        self._tag_edit.setObjectName("cardTag")
        self._tag_edit.setPlaceholderText("签名…")
        self._tag_edit.textChanged.connect(self._on_tag_edited)
        top.addWidget(self._tag_edit, 1)      # 签名（标签属性，可编辑）

        self._info = step.info_widget(self)
        self._io_widget = step.io.gen_widget(self)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 8)
        lay.setSpacing(4)
        lay.addLayout(top)
        lay.addWidget(self._info)
        lay.addWidget(self._io_widget)
        lay.addStretch()

        # 颜色刷新钩子①：io 文本框编辑（QLineEdit 输入即重检；用户输入 → 通知内容已改）
        # 弱引用传卡（防自引用环，见 _notify_io_edited）
        self_ref = weakref.ref(self)
        for fld in (list(self._io_widget.input_fields)
                    + list(self._io_widget.output_fields)):
            if isinstance(fld, QLineEdit):
                fld.textChanged.connect(lambda *_, r=self_ref: _notify_io_edited(r))
        # 颜色刷新钩子②：资源类按钮经 picker 选择后重检
        # 扁平化包装：每次只包最原始 picker（经 _kscript_orig 回溯），
        # 旧包装器被替换后即无引用、可回收——避免视图重建时链式累积、已弃卡片滞留
        orig = getattr(step.io.picker, "_kscript_orig", step.io.picker)

        def _picker(tree, vtype, parent):
            result = orig(tree, vtype, parent)
            QTimer.singleShot(0, self._io_edited)   # 延迟到值落地后（下一事件循环迭代）重检 + 通知
            return result

        _picker._kscript_orig = orig
        step.io.picker = _picker
        self.refresh()

    @property
    def step(self) -> Step:
        return self._step

    def refresh(self) -> None:
        """重检 io 校验 + 状态 + 激活 → 重绘背景色与按钮样式；同步签名框。"""
        self._btn_active.setChecked(self._step.enabled)
        self._tag_edit.blockSignals(True)      # 外部改 tag（加载/粘贴）→ 同步控件，不重复触发保存
        self._tag_edit.setText(self._step.tag)
        self._tag_edit.blockSignals(False)
        self._update_style()

    def set_selected(self, selected: bool) -> None:
        """选中高亮（视图管理）：选中卡片边框变蓝，不影响状态背景色。"""
        self._selected = selected
        self._update_style()

    def set_read_only(self, ro: bool) -> None:
        """执行期只读：禁用激活按钮/签名编辑/io 控件（悬停动画由视图管理，不受影响）。"""
        self._btn_active.setEnabled(not ro)
        self._tag_edit.setReadOnly(ro)
        for fld in (list(self._io_widget.input_fields)
                    + list(self._io_widget.output_fields)):
            fld.setEnabled(not ro)

    # ================================================================
    # 内部
    # ================================================================
    def _io_edited(self) -> None:
        """io 内容已改：重检颜色 + 发出 :attr:`io_changed`（宿主保存链路）。

        在 io 编辑触发点调用（文本框 textChanged / picker 取值落地后的延迟队列）；
        只通知与重检，绝不修改数据（数据由 StepIOWidget 自身写回）。
        """
        self.refresh()
        self.io_changed.emit()

    def _on_active_toggled(self, checked: bool) -> None:
        """激活按钮切换 → 写回 enabled + 立刻刷新本卡 + 通知保存链路。

        刷新保证按钮文本/属性即时同步；io_changed 经视图 edited → 宿主：
        保存工程 + 同步左侧树勾选框（双向联动）。
        """
        self._step.enabled = checked
        self.refresh()
        self.io_changed.emit()

    def _on_tag_edited(self, text: str) -> None:
        """签名框编辑 → 写回步骤标签属性 + 通知内容已改（宿主保存链路）。"""
        self._step.tag = text
        self.io_changed.emit()

    def _update_style(self) -> None:
        """设置动态属性驱动 QSS（规则见 view/cards.qss），并重评估样式。

        属性：``state``(pending/running/finished/error)、``valid``(io 校验)、
        ``active``(激活)、``selected``(选中)；未激活虚线边框、io 非法红优先、
        选中蓝边框均由 QSS 属性选择器表达（级联顺序见文件内注释）。
        """
        # 注意：动态属性名不能叫 "enabled"——它是 QWidget 的 Q_PROPERTY，
        # setProperty 会走内置 setter 等价 setEnabled(False)，把整卡真正禁用
        # （点击无效、hover 动画消失、无法切回激活）。用 "active" 只做样式。
        self.setProperty("state", self._step.status.name.lower())
        self.setProperty("active", self._step.enabled)
        self.setProperty("valid", self._step.io.is_valid)
        self.setProperty("selected", self._selected)
        self._name.setProperty("active", self._step.enabled)
        self._btn_active.setProperty("active", self._step.enabled)
        self._btn_active.setText("✓" if self._step.enabled else "✗")
        for w in (self, self._name, self._btn_active):
            w.style().unpolish(w)
            w.style().polish(w)

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

    from model.step import Step
    from model.kscp_package import KscpPackage
    from model.project_variable import ProjectVariable
    from model.variable_tree import VariableTree

    app = QApplication.instance() or QApplication(sys.argv)

    # 桩步骤（与 model.step 冒烟同款）
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

    # 样式来自 view/cards.qss（毛玻璃/圆角/柔和色）；动态状态经属性选择器
    assert "StepCard {" in card.styleSheet() and "border-radius" in card.styleSheet()
    assert _CARD_QSS_PATH.endswith("cards.qss")      # 懒加载路径指向文件
    # 样式表文件缺失 → 兜底样式不崩（评审#9：原模块级读取会让整个包导入失败）
    import tempfile as _tmp
    _orig_qss_path = _CARD_QSS_PATH
    globals()["_CARD_QSS_PATH"] = os.path.join(
        _tmp.gettempdir(), "不存在的cards.qss")
    globals()["_CARD_QSS"] = None
    assert "StepCard" in _card_qss()
    globals()["_CARD_QSS_PATH"] = _orig_qss_path
    globals()["_CARD_QSS"] = None
    # 阴影：禁止 QGraphicsEffect（QGraphicsDropShadowEffect 在 QGraphicsProxyWidget
    # 中渲染整体白屏，Qt 5.15 Windows 纹理化 bug）；投影由视图在场景层绘制
    assert card.graphicsEffect() is None
    # io 非法（空槽）→ valid=False（红优先规则在 QSS 文件内）
    assert card.property("valid") is False
    # 配置 io → PENDING
    s.io.change_value("input", 0, "5")
    s.io.change_value("output", 0, "n1")
    card.refresh()
    assert card.property("state") == "pending"
    # 状态：RUNNING / FINISHED / ERROR
    s.status = StepStatus.RUNNING
    card.refresh()
    assert card.property("state") == "running"
    s.status = StepStatus.FINISHED
    card.refresh()
    assert card.property("state") == "finished"
    s.status = StepStatus.ERROR
    card.refresh()
    assert card.property("state") == "error"
    # io 变非法 → valid=False（红优先于状态色）
    s.status = StepStatus.PENDING
    s.io.change_value("input", 0, "")
    card.refresh()
    assert card.property("valid") is False and card.property("state") == "pending"

    # 激活按钮：翻转 enabled → 属性 + 按钮文本（虚线边框由 QSS [active="false"] 规则）
    s.io.change_value("input", 0, "5")
    card.refresh()
    assert s.enabled is True and card.property("active") is True
    assert card.isEnabled() and card._btn_active.isEnabled()
    card._btn_active.setChecked(False)
    card._on_active_toggled(False)
    assert s.enabled is False and card.property("active") is False
    assert card._btn_active.text() == "✗"      # 未激活 = 灰底「✗」
    # 非激活只是 enabled=False + 背景灰，控件本身必须可交互
    # （hover 动画、点击切回激活；旧实现 setProperty("enabled") 误调
    #   QWidget::setEnabled 把整卡禁用 → 无法控制）
    assert card.isEnabled() and card._btn_active.isEnabled()
    assert card._btn_active.isCheckable()
    card._on_active_toggled(True)
    assert s.enabled is True and card.property("active") is True
    assert card._btn_active.text() == "✓"      # 激活 = 绿底「✓」
    assert card.isEnabled() and card._btn_active.isEnabled()

    # 选中高亮：selected 属性（蓝边框由 QSS [selected="true"] 规则）
    card.set_selected(True)
    assert card.property("selected") is True
    card.set_selected(False)
    assert card.property("selected") is False

    # menu_requested 信号：右键发出（自身, 坐标）
    got = []
    card.menu_requested.connect(lambda c, p: got.append((c, p)))
    card.menu_requested.emit(card, QPoint(1, 2))
    assert got == [(card, QPoint(1, 2))]

    # 尺寸随显示器动态（1080p 基准 240×340）
    cw, ch = card_size_for_screen()
    assert (card.width(), card.height()) == (cw, ch)

    # picker 延迟重检：fake picker 让 io 变非法；refresh 延迟到值落地后
    def fake_picker(tree, vtype, parent):
        s.io.change_value("input", 0, "")
        return None

    s.io.picker = fake_picker                     # 构造前替换（card2 构造时会被包装）
    card2 = StepCard(s)                           # 此时 io 合法
    card2.refresh()
    assert card2.property("state") == "pending"
    s.io.picker(None, "number", card2)            # 模拟点击资源类「选择变量」按钮
    # 值已落地但重检被延迟到下一事件循环迭代 → 仍是合法状态（同步刷新未发生）
    assert card2.property("valid") is True
    app.processEvents()                           # 触发零延迟定时器
    assert card2.property("valid") is False       # 值已落地、延迟重检生效

    # ---- I-1：io 编辑 → io_changed（真实 textChanged 路径：卡片内 QLineEdit 输入） ----
    s3 = _StubStep.create_default(tree, pkg)
    card3 = StepCard(s3)
    fired = []
    card3.io_changed.connect(lambda: fired.append(1))
    card3._io_widget.input_fields[0].setText("9")   # 模拟用户输入 → textChanged
    assert fired == [1], fired

    # ---- I-2：picker 包装链扁平（_kscript_orig 回溯计数 = 1，重建不累积） ----
    s4 = _StubStep.create_default(tree, pkg)
    StepCard(s4)
    StepCard(s4)                                   # 视图重建两次（添加/粘贴/删除均 refresh）
    chain_len = 0
    cur = s4.io.picker
    while getattr(cur, "_kscript_orig", None) is not None:
        chain_len += 1
        cur = cur._kscript_orig
    assert chain_len == 1, chain_len              # 扁平：每次包装都从最原始 picker 起

    # ---- K-2：签名框编辑 → tag 写回 + io_changed（宿主保存链路） ----
    s_tag = _StubStep.create_default(tree, pkg)
    card_tag = StepCard(s_tag)
    assert card_tag._tag_edit.text() == ""         # 默认空标签
    fired = []
    card_tag.io_changed.connect(lambda: fired.append(1))
    card_tag._tag_edit.setText("清理阶段")          # 真实 textChanged 路径
    assert s_tag.tag == "清理阶段"
    assert fired == [1], fired
    # 外部改 tag（加载/粘贴还原）→ refresh 同步控件、不重复发保存
    s_tag.tag = "新标签"
    card_tag.refresh()
    assert card_tag._tag_edit.text() == "新标签"
    assert fired == [1], fired                     # blockSignals：同步不触发保存

    # 签名框字体：14 号宋体（QSS #cardTag 规则内显式声明；「14号」= 14pt，
    # 14px ≈ 10.5pt 视觉增幅太小——用户反馈「没变大」后才改用 pt 单位）
    import re as _re
    _tag_rule = _re.search(r"#cardTag \{[^}]*\}", _card_qss(), _re.S)
    assert _tag_rule is not None
    assert "SimSun" in _tag_rule.group(0) and "font-size: 14pt" in _tag_rule.group(0)

    print("StepCard smoke OK")
