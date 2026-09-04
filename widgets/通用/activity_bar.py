# -*- coding: utf-8 -*-
"""
活动栏（左侧切换栏）
====================

:class:`ActivityBar` 为 VSCode 风格活动栏：竖排图标按钮，悬停 tooltip 显示
功能名；顶部为管理树导航项（互斥勾选，切换时发 :data:`currentChanged`），
底部为功能按钮（执行/设置，``clear()`` 不清除底部按钮）。
"""

from __future__ import annotations

from typing import List, Optional

from PyQt5.QtCore import QSize, Qt, pyqtSignal
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QToolButton, QVBoxLayout, QWidget

__all__ = ["ActivityBar"]


class ActivityBar(QWidget):
    """VSCode 风格活动栏：竖排图标按钮，悬停 tooltip 显示功能名。"""

    currentChanged = pyqtSignal(int)   # 导航项切换（勾选态变化）

    def __init__(self, parent: QWidget = None) -> None:
        super().__init__(parent)
        self.setFixedWidth(56)
        self._lay = QVBoxLayout(self)
        self._lay.setContentsMargins(4, 8, 4, 8)
        self._lay.setSpacing(6)
        self._lay.addStretch()
        self._buttons: List[QToolButton] = []
        self._bottom_buttons: List[QToolButton] = []   # 底部功能按钮（clear 不清）

    def add_item(self, name: str, icon: QIcon) -> None:
        btn = QToolButton(self)
        btn.setCheckable(True)
        btn.setAutoExclusive(True)
        btn.setAutoRaise(True)
        btn.setToolButtonStyle(Qt.ToolButtonIconOnly)
        btn.setIcon(icon)
        btn.setIconSize(QSize(26, 26))
        btn.setFixedSize(44, 44)
        btn.setToolTip(name)                       # 悬停显示功能名
        btn.setStyleSheet(
            "QToolButton { border:none; border-radius:6px; background:transparent; }"
            "QToolButton:hover { background:#e3e3e3; }"
            "QToolButton:checked { background:#cfe0f5; }"
            "QToolButton:checked:hover { background:#bfd5f0; }")
        idx = len(self._buttons)

        def _on_toggled(checked: bool, i: int = idx) -> None:
            if checked:
                self.currentChanged.emit(i)

        btn.toggled.connect(_on_toggled)
        self._lay.insertWidget(self._lay.count() - 1 - len(self._bottom_buttons), btn)
        self._buttons.append(btn)

    def add_bottom_button(self, name: str, icon: QIcon, on_click,
                          checkable: bool = False,
                          alignment: Optional[int] = None) -> QToolButton:
        """底部功能按钮（stretch 之下；``clear()`` 不清除——非管理树切换项）。

        ``checkable``：状态按钮（如执行待命态绿色高亮）；瞬时按钮（如设置）
        用 False——否则点击后 checked 样式残留（悬停/按压高亮不退）。
        ``alignment``：QLayout 对齐位（如 ``Qt.AlignHCenter`` 居中放小于栏宽的
        按钮；默认 ``None`` = 不指定对齐，按钮靠左）。48×48 按钮填满 48px
        内容区，对齐无视觉效果；36×36 刷新按钮传 AlignHCenter 才居中。
        """
        btn = QToolButton(self)
        btn.setCheckable(checkable)
        btn.setAutoRaise(True)
        btn.setToolButtonStyle(Qt.ToolButtonIconOnly)
        btn.setIcon(icon)
        btn.setIconSize(QSize(36, 36))   # 功能按钮图标大于导航项（用户反馈）
        btn.setFixedSize(48, 48)
        btn.setToolTip(name)
        btn.setStyleSheet(
            "QToolButton { border:none; border-radius:6px; background:transparent; }"
            "QToolButton:hover { background:#e3e3e3; }"
            "QToolButton:checked { background:#c8e6c9; }"
            "QToolButton:checked:hover { background:#b7dcba; }")
        btn.clicked.connect(on_click)
        # 默认无对齐（靠左）；传对齐位则居中/靠右等（PyQt5 addWidget 第三参不收 int 0）
        if alignment is None:
            self._lay.addWidget(btn)
        else:
            self._lay.addWidget(btn, 0, alignment)   # stretch 之后 = 栏位最底
        self._bottom_buttons.append(btn)
        return btn

    def clear(self) -> None:
        for btn in self._buttons:
            btn.deleteLater()
        self._buttons.clear()

    def set_current_row(self, row: int) -> None:
        if 0 <= row < len(self._buttons):
            self._buttons[row].setChecked(True)


# ================================================================
# 冒烟演示：直接 ``python -m widgets.通用.activity_bar`` 运行
# ================================================================
if __name__ == "__main__":
    import sys

    from PyQt5.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(sys.argv)
    icon = QIcon()                        # 空图标即可（导航不渲染内容断言）

    bar = ActivityBar()
    bar.add_item("甲", icon)
    bar.add_item("乙", icon)
    assert len(bar._buttons) == 2
    b0, b1 = bar._buttons
    assert b0.isCheckable() and b0.isChecked() is False
    switched = []
    bar.currentChanged.connect(switched.append)
    b1.setChecked(True)                   # 自动互斥 → 触发 currentChanged(1)
    assert switched == [1], switched
    assert b1.isChecked() and not b0.isChecked()

    # 底部功能按钮：非 checkable 瞬时按钮；48×48 + 图标 36×36（用户反馈加大）
    clicked = []
    bb = bar.add_bottom_button("设置", icon, lambda: clicked.append(1))
    assert not bb.isCheckable()
    assert bb.size() == QSize(48, 48) and bb.iconSize() == QSize(36, 36)
    bb.click()
    assert clicked == [1]
    # checkable 状态钮（执行按钮模式）
    exec_btn = bar.add_bottom_button("执行", icon, lambda: None, checkable=True)
    assert exec_btn.isCheckable()
    assert len(bar._bottom_buttons) == 2

    # clear：只清导航项，底部按钮保留；空列表 set_current_row 无副作用
    bar.clear()
    assert len(bar._buttons) == 0
    assert bar._bottom_buttons == [bb, exec_btn]
    bar.set_current_row(0)                # 越界 → 不崩

    # 对齐：默认 0（靠左，36×36 在 48px 内容区贴左）；传 AlignHCenter → 居中
    from PyQt5.QtCore import Qt as _Qt
    _c = bar.add_bottom_button("居中", icon, lambda: None, alignment=_Qt.AlignHCenter)
    _ci = bar._lay.itemAt(bar._lay.count() - 1)
    assert _ci.widget() is _c
    assert _ci.alignment() == _Qt.AlignHCenter
    _d = bar.add_bottom_button("默认", icon, lambda: None)
    _di = bar._lay.itemAt(bar._lay.count() - 1)
    assert _di.widget() is _d
    assert int(_di.alignment()) == 0     # 默认无对齐（Qt.Alignment(0) == 0 在 PyQt5 不成立，取 int 比）

    print("ActivityBar smoke OK")
