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

from model.执行.hotkey import normalize_hotkey

__all__ = ["HotkeyEdit", "SettingsDialog"]

# Qt 修饰键 → 单独修饰键热键名（按下修饰键本身时捕获）
_QT_MOD_NAMES = {
    Qt.Key_Control: "Ctrl",
    Qt.Key_Alt: "Alt",
    Qt.Key_Shift: "Shift",
    Qt.Key_Meta: "Cmd",
}


def _spec_from_event(key: int, modifiers) -> Optional[str]:
    """按键事件 → 热键规格（已规范化）；不可成串 → None。

    修饰键单独按下 → ``"Ctrl"`` 等（剥离自身修饰位）；其余键 →
    ``QKeySequence(modifiers | key)`` 的 PortableText（"F1"/"Ctrl+Alt+I"/单键）。
    """
    from PyQt5.QtGui import QKeySequence

    if key in _QT_MOD_NAMES:
        spec = _QT_MOD_NAMES[key]
    else:
        spec = QKeySequence(int(modifiers) | key).toString(
            QKeySequence.PortableText)
        if not spec:
            return None
    return normalize_hotkey(spec)


class HotkeyEdit(QLineEdit):
    """热键编辑框（设置弹窗内）：聚焦后按下任意按键完成绑定（支持单键 /
    F1 等功能键 / Ctrl+Alt+I 等组合 / 单独修饰键 Ctrl；保存由弹窗按钮统一执行）。

    空值 = 该页不绑定热键；``set_hotkey("")`` 供清除按钮使用。
    """

    def __init__(self, initial: str, parent=None) -> None:
        super().__init__(parent)
        self._hotkey = normalize_hotkey(initial) or ""   # 显示/比较统一规范形式
        self.setReadOnly(True)
        self.setFixedWidth(110)            # 容纳 "Ctrl+Alt+Shift+M" 等组合
        self.setAlignment(Qt.AlignCenter)
        self.setToolTip(
            "点击后按下按键绑定执行热键（支持 F1、Ctrl+Alt+I、Ctrl、单键；\n"
            "退格清空 = 该页不绑定）。热键勿与步骤按键冲突（模拟按键也会被监听）。")
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
        if event.key() in (Qt.Key_Backspace, Qt.Key_Delete):
            self.set_hotkey("")                  # 退格/删除 → 清空
            return
        spec = _spec_from_event(event.key(), event.modifiers())
        if spec is not None:
            self._apply_key(spec)

    def _apply_key(self, spec: str) -> bool:
        """校验并记录待绑定热键；非法（无法解析）→ False 且还原显示。"""
        norm = normalize_hotkey(spec)
        if norm is None:
            self.setText(self._hotkey)
            return False
        self._hotkey = norm
        self.setText(norm)
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
        """页间热键唯一校验（按规范化形式比较——大小写/别名/修饰键顺序
        不敏感天然覆盖）；冲突 → 错误文案，否则 None。"""
        seen: Dict[str, str] = {}
        for page, edit in self._edits.items():
            hk = edit.hotkey()
            if not hk:
                continue
            norm = normalize_hotkey(hk) or hk
            if norm in seen:
                return "热键「%s」已绑定到页「%s」，请勿重复" % (norm, seen[norm])
            seen[norm] = page
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

    # 表格：每页一行（页名 + 热键 + 清除）；读回映射（初始值经规范化）
    dlg = SettingsDialog(["执行列表1", "执行列表2"],
                         {"执行列表1": "f", "执行列表2": ""})
    assert dlg._edits["执行列表1"].text() == "F"
    assert dlg._edits["执行列表2"].text() == ""
    assert dlg.hotkeys() == {"执行列表1": "F", "执行列表2": ""}
    # 按钮中文（用户反馈：Save/Cancel 改中文）
    _bb = dlg.findChild(QDialogButtonBox)
    assert _bb is not None
    assert _bb.button(QDialogButtonBox.Save).text() == "保存"
    assert _bb.button(QDialogButtonBox.Cancel).text() == "取消"
    # 热键编辑：绑定/规范化/非法还原（不真实按键，直接调 _apply_key）
    assert dlg._edits["执行列表1"]._apply_key("h")
    assert dlg._edits["执行列表1"].text() == "H"
    assert dlg._edits["执行列表1"]._apply_key("ctrl+alt+i")
    assert dlg._edits["执行列表1"].text() == "Ctrl+Alt+I"
    assert not dlg._edits["执行列表1"]._apply_key("F13")
    assert dlg._edits["执行列表1"].text() == "Ctrl+Alt+I"   # 非法不落盘、显示还原
    # 捕获路径：事件 → 规格（F1 / 组合 / 单独修饰键）
    assert _spec_from_event(Qt.Key_F1, Qt.NoModifier) == "F1"
    assert _spec_from_event(Qt.Key_I, Qt.ControlModifier | Qt.AltModifier) \
        == "Ctrl+Alt+I"
    assert _spec_from_event(Qt.Key_Control, Qt.ControlModifier) == "Ctrl"
    assert _spec_from_event(Qt.Key_Shift, Qt.ShiftModifier) == "Shift"
    # 退格清空（真实 keyPressEvent 路径）
    from PyQt5.QtCore import QEvent
    from PyQt5.QtGui import QKeyEvent
    _edit = dlg._edits["执行列表1"]
    _edit.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_Backspace, Qt.NoModifier))
    assert _edit.text() == "" and _edit.hotkey() == ""
    # 清除按钮同义
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

    # 查重：规范化相等（F1 vs f1 / Ctrl+Alt+I vs ctrl+alt+i 均冲突）
    dlg2._edits["执行列表1"].set_hotkey("F1")
    assert dlg2._validate() is None
    dlg3 = SettingsDialog(["页1", "页2"], {"页1": "F1", "页2": "f1"})
    err = dlg3._validate()
    assert err is not None and "已绑定" in err, err
    dlg3._edits["页2"].set_hotkey("ctrl+alt+i")
    dlg3._edits["页1"].set_hotkey("Ctrl+Alt+I")
    err = dlg3._validate()
    assert err is not None and "已绑定" in err, err
    dlg3._edits["页2"].set_hotkey("G")
    assert dlg3._validate() is None

    print("SettingsDialog smoke OK")
