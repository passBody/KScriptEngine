# -*- coding: utf-8 -*-
"""
设置弹窗（触发热键配置）
========================

:class:`HotkeyEdit` 为热键编辑框（聚焦后按任意单字符键完成绑定）；
:class:`SettingsDialog` 承载其于设置弹窗内，右下角「保存/取消」按钮。
热键最终由主窗口写入工程包 ``executor.json``（本模块不落盘）。
"""

from __future__ import annotations

from typing import Optional

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QLineEdit, QVBoxLayout,
    QWidget,
)

__all__ = ["HotkeyEdit", "SettingsDialog"]


class HotkeyEdit(QLineEdit):
    """热键编辑框（设置弹窗内）：聚焦后按任意键完成绑定（保存由弹窗按钮统一执行）。"""

    def __init__(self, initial: str, parent=None) -> None:
        super().__init__(parent)
        self._hotkey = initial
        self.setReadOnly(True)
        self.setFixedWidth(42)
        self.setAlignment(Qt.AlignCenter)
        self.setToolTip(
            "点击后按下任意单字符键绑定执行热键。\n"
            "热键勿与步骤按键冲突（模拟按键也会被监听）。")
        self.setText(self._hotkey)

    def hotkey(self) -> str:
        return self._hotkey

    def mousePressEvent(self, event) -> None:  # noqa: N802 (Qt 命名)
        self.setText("…")                     # 提示等待按键
        super().mousePressEvent(event)

    def keyPressEvent(self, event) -> None:  # noqa: N802 (Qt 命名)
        if event.key() == Qt.Key_Escape:
            self.setText(self._hotkey)           # 取消还原
            return
        ch = event.text()
        if ch:
            self._apply_key(ch)

    def _apply_key(self, key: str) -> bool:
        """校验并记录待绑定热键；非法（非单字符）→ False 且还原显示。"""
        if not isinstance(key, str) or len(key) != 1:
            self.setText(self._hotkey)
            return False
        self._hotkey = key
        self.setText(key)
        return True


class SettingsDialog(QDialog):
    """设置弹窗：触发热键配置；右下角「保存/取消」按钮。"""

    def __init__(self, hotkey: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("设置")
        self.resize(320, 140)
        self._hotkey_edit = HotkeyEdit(hotkey, self)

        lay = QVBoxLayout(self)
        row = QHBoxLayout()
        lbl = QLabel("触发热键")
        row.addWidget(lbl)
        row.addStretch()
        row.addWidget(self._hotkey_edit)
        lay.addLayout(row)
        tip = QLabel("热键勿与步骤按键冲突（模拟按键也会被监听）；\n模拟输入到游戏窗口需管理员运行。")
        tip.setStyleSheet("color:#888;")
        lay.addWidget(tip)
        btns = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        btns.button(QDialogButtonBox.Save).setText("保存")
        btns.button(QDialogButtonBox.Cancel).setText("取消")
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def hotkey(self) -> str:
        return self._hotkey_edit.hotkey()


# ================================================================
# 冒烟演示：直接 ``python -m widgets.settings_dialog`` 运行
# ================================================================
if __name__ == "__main__":
    import sys

    from PyQt5.QtWidgets import QApplication, QDialogButtonBox

    app = QApplication.instance() or QApplication(sys.argv)

    # 编辑框：点击后按键绑定（不真实按键，直接调 _apply_key）；非法拒绝并还原
    dlg = SettingsDialog("`")
    assert dlg._hotkey_edit.text() == "`"
    # 按钮中文（用户反馈：Save/Cancel 改中文）
    _bb = dlg.findChild(QDialogButtonBox)
    assert _bb is not None
    assert _bb.button(QDialogButtonBox.Save).text() == "保存"
    assert _bb.button(QDialogButtonBox.Cancel).text() == "取消"
    assert dlg._hotkey_edit._apply_key("f")
    assert dlg._hotkey_edit.text() == "f" and dlg.hotkey() == "f"
    assert not dlg._hotkey_edit._apply_key("ab")
    assert dlg._hotkey_edit.text() == "f" and dlg.hotkey() == "f"   # 非法不落盘、显示还原

    print("SettingsDialog smoke OK")
