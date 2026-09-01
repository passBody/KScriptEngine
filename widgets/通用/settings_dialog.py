# -*- coding: utf-8 -*-
"""
设置弹窗（各执行列表页热键 + 停止方式）
========================================

:class:`HotkeyEdit` 为热键编辑框（聚焦后按任意单字符键完成绑定，可清空）；
:class:`SettingsDialog` 为集中表格：每行一个执行列表页（页名 + 热键编辑框
+ 清除按钮），保存前校验页间热键唯一（大小写不敏感——HotkeyListener
大小写不敏感），冲突弹窗警告并中止（不落盘）。
热键与停止方式最终由主窗口写入工程包 ``executor.json``（本模块不落盘）。
"""

from __future__ import annotations

from typing import Dict, List, Optional

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QDialog, QDialogButtonBox, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
    QMessageBox, QPushButton, QRadioButton, QVBoxLayout, QWidget,
)

__all__ = ["HotkeyEdit", "SettingsDialog"]


class HotkeyEdit(QLineEdit):
    """热键编辑框（设置弹窗内）：聚焦后按任意键完成绑定（保存由弹窗按钮统一执行）。

    空值 = 该页不绑定热键；``set_hotkey("")`` 供清除按钮使用。
    """

    def __init__(self, initial: str, parent=None) -> None:
        super().__init__(parent)
        self._hotkey = initial
        self.setReadOnly(True)
        self.setFixedWidth(42)
        self.setAlignment(Qt.AlignCenter)
        self.setToolTip(
            "点击后按下任意单字符键绑定执行热键（留空 = 该页不绑定）。\n"
            "热键勿与步骤按键冲突（模拟按键也会被监听）。")
        self.setText(self._hotkey)

    def hotkey(self) -> str:
        return self._hotkey

    def set_hotkey(self, key: str) -> None:
        """外部设置/清除（清除按钮用）。"""
        self._hotkey = key
        self.setText(key)

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
    """设置弹窗：各执行列表页热键表格 + 停止方式；右下角「保存/取消」按钮。"""

    def __init__(self, pages: List[str], hotkeys: Dict[str, str],
                 stop_mode: str = "after_step",
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("设置")
        self.resize(420, 250 + max(0, len(pages) - 1) * 36)
        self._edits: Dict[str, HotkeyEdit] = {}

        lay = QVBoxLayout(self)
        # 表头 + 每页一行：页名 + 热键编辑框 + 清除按钮
        head = QHBoxLayout()
        h1 = QLabel("执行列表")
        h1.setStyleSheet("font-weight:bold;")
        head.addWidget(h1, 2)
        h2 = QLabel("触发热键（留空 = 不绑定）")
        h2.setStyleSheet("font-weight:bold;")
        head.addWidget(h2, 3)
        head.addSpacing(48)
        lay.addLayout(head)
        for page in pages:
            row = QHBoxLayout()
            name = QLabel(page)
            name.setToolTip(page)
            edit = HotkeyEdit(hotkeys.get(page, ""), self)
            clear_btn = QPushButton("清除")
            clear_btn.setFixedWidth(48)
            clear_btn.clicked.connect(
                lambda _=False, e=edit: e.set_hotkey(""))
            row.addWidget(name, 2)
            row.addWidget(edit, 3)
            row.addWidget(clear_btn)
            lay.addLayout(row)
            self._edits[page] = edit

        # 停止方式单选组（immediate / after_step）
        self._stop_immediate = QRadioButton(
            "立即停止（可中断延时/连击/拖拽等待）", self)
        self._stop_after = QRadioButton("当前步骤结束后停止", self)
        if stop_mode == "immediate":
            self._stop_immediate.setChecked(True)
        else:
            self._stop_after.setChecked(True)
        group = QGroupBox("停止方式", self)
        glay = QVBoxLayout(group)
        glay.addWidget(self._stop_immediate)
        glay.addWidget(self._stop_after)
        lay.addWidget(group)

        tip = QLabel("热键勿与步骤按键冲突（模拟按键也会被监听）；\n模拟输入到游戏窗口需管理员运行。")
        tip.setStyleSheet("color:#888;")
        lay.addWidget(tip)
        btns = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        btns.button(QDialogButtonBox.Save).setText("保存")
        btns.button(QDialogButtonBox.Cancel).setText("取消")
        btns.accepted.connect(self._on_save_clicked)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def hotkeys(self) -> Dict[str, str]:
        """各页热键映射：{页名: 单字符或空串}。"""
        return {page: edit.hotkey() for page, edit in self._edits.items()}

    def stop_mode(self) -> str:
        """当前选中的停止方式：immediate / after_step。"""
        return "immediate" if self._stop_immediate.isChecked() else "after_step"

    def _validate(self) -> Optional[str]:
        """页间热键唯一校验（大小写不敏感——HotkeyListener 大小写不敏感）；
        冲突 → 错误文案，否则 None。"""
        seen: Dict[str, str] = {}
        for page, edit in self._edits.items():
            hk = edit.hotkey()
            if not hk:
                continue
            low = hk.lower()
            if low in seen:
                return "热键「%s」已绑定到页「%s」，请勿重复" % (hk, seen[low])
            seen[low] = page
        return None

    def _on_save_clicked(self) -> None:
        """保存前查重：冲突 → 弹窗警告并中止（不落盘）。"""
        err = self._validate()
        if err is not None:
            QMessageBox.warning(self, "设置", err)
            return
        self.accept()


# ================================================================
# 冒烟演示：直接 ``python -m widgets.通用.settings_dialog`` 运行
# ================================================================
if __name__ == "__main__":
    import sys

    from PyQt5.QtWidgets import QApplication, QDialogButtonBox

    app = QApplication.instance() or QApplication(sys.argv)

    # 表格：每页一行（页名 + 热键 + 清除）；读回映射
    dlg = SettingsDialog(["执行列表1", "执行列表2"],
                         {"执行列表1": "f", "执行列表2": ""})
    assert dlg._edits["执行列表1"].text() == "f"
    assert dlg._edits["执行列表2"].text() == ""
    assert dlg.hotkeys() == {"执行列表1": "f", "执行列表2": ""}
    # 按钮中文（用户反馈：Save/Cancel 改中文）
    _bb = dlg.findChild(QDialogButtonBox)
    assert _bb is not None
    assert _bb.button(QDialogButtonBox.Save).text() == "保存"
    assert _bb.button(QDialogButtonBox.Cancel).text() == "取消"
    # 热键编辑：绑定/非法还原（不真实按键，直接调 _apply_key）
    assert dlg._edits["执行列表1"]._apply_key("h")
    assert dlg._edits["执行列表1"].text() == "h"
    assert not dlg._edits["执行列表1"]._apply_key("ab")
    assert dlg._edits["执行列表1"].text() == "h"       # 非法不落盘、显示还原
    # 清除：留空 = 不绑定
    dlg._edits["执行列表1"].set_hotkey("")
    assert dlg.hotkeys() == {"执行列表1": "", "执行列表2": ""}

    # 停止方式：默认 after_step；显式 immediate → 选中即读回；切换互斥生效
    assert not dlg._stop_immediate.isChecked() and dlg._stop_after.isChecked()
    assert dlg.stop_mode() == "after_step"
    dlg2 = SettingsDialog(["执行列表1"], {}, "immediate")
    assert dlg2._stop_immediate.isChecked() and not dlg2._stop_after.isChecked()
    assert dlg2.stop_mode() == "immediate"
    dlg2._stop_after.setChecked(True)          # 单选互斥：勾 after 自动取消 immediate
    assert not dlg2._stop_immediate.isChecked()
    assert dlg2.stop_mode() == "after_step"

    # 查重：大小写不敏感（f vs F 冲突——HotkeyListener 大小写不敏感）
    dlg2._edits["执行列表1"].set_hotkey("f")
    assert dlg2._validate() is None
    dlg3 = SettingsDialog(["页1", "页2"], {"页1": "f", "页2": "F"})
    err = dlg3._validate()
    assert err is not None and "已绑定" in err, err
    dlg3._edits["页2"].set_hotkey("g")
    assert dlg3._validate() is None

    print("SettingsDialog smoke OK")
