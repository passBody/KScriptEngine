# -*- coding: utf-8 -*-
"""
日志窗口（GUI 控件）
==================

:class:`LogWidget` 承载 :class:`model.log_model.LogModel`（单例），以列表形式显示日志，
支持级别筛选、清空、导出，监听模型变更实时刷新。

级别筛选为 5 个可勾选开关（DEBUG/INFO/WARNING/ERROR/CRITICAL），勾选即显示该级别，
可任意组合；全不勾选则列表为空。

基本用法
--------
::

    from PyQt5.QtWidgets import QApplication
    from widgets import LogWidget
    from model import LogModel

    app = QApplication([])
    w = LogWidget()
    w.show()
    LogModel.instance().info("启动完成")
    app.exec_()
"""

from __future__ import annotations

from typing import Dict, Optional, Set

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QFont
from PyQt5.QtWidgets import (
    QApplication, QFileDialog, QHBoxLayout, QLabel, QListWidget,
    QListWidgetItem, QMenu, QPushButton, QToolButton, QVBoxLayout, QWidget,
)

from model.log_model import LogEntry, LogLevel, LogModel

__all__ = ["LogWidget"]

_LEVEL_HEX = {
    LogLevel.DEBUG: "#888888",
    LogLevel.INFO: "#333333",
    LogLevel.WARNING: "#e67e22",
    LogLevel.ERROR: "#e15554",
    LogLevel.CRITICAL: "#b03a2e",
}


class LogWidget(QWidget):
    """承载 LogModel 的日志窗口：列表 + 级别筛选开关 + 清空 + 导出。"""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._model = LogModel.instance()
        self._toggles: Dict[LogLevel, QToolButton] = {}

        bar = QHBoxLayout()
        bar.setContentsMargins(6, 4, 6, 4)
        title = QLabel("日志")
        title.setStyleSheet("font-weight:bold;")
        bar.addWidget(title)
        bar.addStretch()
        # 5 个级别筛选点：勾选=显示该级别，可任意组合
        for lv in LogLevel.levels():
            tb = QToolButton(self)
            tb.setText(lv.name)
            tb.setCheckable(True)
            tb.setChecked(True)          # 默认全显示
            tb.setAutoRaise(True)
            tb.setStyleSheet(
                "QToolButton { border:1px solid #ccc; border-radius:4px;"
                " padding:1px 6px; color:#bbb; background:transparent; }"
                "QToolButton:checked { color:%s; background:#f0f0f0;"
                " border-color:#999; }"
                "QToolButton:hover { border-color:#888; }" % _LEVEL_HEX[lv])
            tb.toggled.connect(self._on_filter)   # 连接在 setChecked 之后，避免初始触发
            bar.addWidget(tb)
            self._toggles[lv] = tb
        self._btn_clear = QPushButton("清空")
        self._btn_clear.clicked.connect(self._on_clear)
        bar.addWidget(self._btn_clear)
        self._btn_export = QPushButton("导出…")
        self._btn_export.clicked.connect(self._on_export)
        bar.addWidget(self._btn_export)

        self._list = QListWidget()
        self._list.setFont(QFont("Consolas", 9))
        self._list.setUniformItemSizes(True)
        self._list.setContextMenuPolicy(Qt.CustomContextMenu)
        self._list.customContextMenuRequested.connect(self._on_log_context_menu)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addLayout(bar)
        lay.addWidget(self._list, 1)

        self._model.add_listener(self._refresh)
        self._rendered_count = 0    # 已渲染条目数（增量刷新锚点）
        self._refresh()

    # ---- 刷新 ----
    def _refresh(self) -> None:
        """模型变更监听：**增量追加**新条目（不清空重建）。

        仅在条目数回退（模型被清空）时全量重建。用户回看旧日志时不被强制
        拉底：追加仅在原本已位于底部时跟随滚动。
        """
        entries = self._model.entries
        if len(entries) < self._rendered_count:
            self._rebuild(entries)   # 清空等回退场景
            return
        vbar = self._list.verticalScrollBar()
        at_bottom = vbar.value() >= vbar.maximum()
        for e in entries[self._rendered_count:]:
            self._add_item(e)
        self._rendered_count = len(entries)
        if at_bottom:
            self._list.scrollToBottom()

    def _rebuild(self, entries) -> None:
        """全量重建（条目数回退 / 级别筛选变化）。"""
        self._list.clear()
        for e in entries:
            self._add_item(e)
        self._rendered_count = len(entries)
        self._list.scrollToBottom()

    def _add_item(self, e: LogEntry) -> None:
        text = "%s %-8s %s" % (LogModel.format_time(e.time), e.level.name, e.message)
        item = QListWidgetItem(text)
        item.setForeground(QColor(_LEVEL_HEX.get(e.level, "#333333")))
        self._list.addItem(item)
        if e.level not in self._active_levels():
            item.setHidden(True)

    def _active_levels(self) -> Set[LogLevel]:
        """当前勾选（=显示）的级别集合。"""
        return {lv for lv, tb in self._toggles.items() if tb.isChecked()}

    # ---- 控件回调 ----
    def _on_filter(self, _checked: bool) -> None:
        self._rebuild(self._model.entries)   # 筛选变化 → 全部条目重估 hidden

    def _on_clear(self) -> None:
        self._model.clear()        # 监听器触发 _refresh

    def _on_export(self) -> None:
        path, filt = QFileDialog.getSaveFileName(
            self, "导出日志", "kscript.log",
            "文本日志 (*.log);;JSON (*.json)")
        if not path:
            return
        fmt = "json" if filt.startswith("JSON") else "text"
        try:
            with open(path, "wb") as f:
                f.write(self._model.export(fmt))
            self._model.info("日志已导出：%s" % path)
        except OSError as e:
            self._model.error("导出失败：%s" % e)

    # ---- 右键复制 ----
    def _on_log_context_menu(self, pos) -> None:
        item = self._list.itemAt(pos)
        if item is None:
            return
        self._list.setCurrentItem(item)      # 右键即选中该条
        menu = QMenu(self)
        a_copy = menu.addAction("复制")
        if menu.exec_(self._list.viewport().mapToGlobal(pos)) is a_copy:
            self._copy_item(item)

    def _copy_item(self, item: QListWidgetItem) -> None:
        cb = QApplication.clipboard()
        if cb is not None:
            cb.setText(item.text())

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt 命名)
        self._model.remove_listener(self._refresh)
        super().closeEvent(event)


if __name__ == "__main__":
    import sys
    from PyQt5.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(sys.argv)
    LogModel._reset_instance()
    w = LogWidget()
    m = LogModel.instance()
    m.info("a"); m.debug("b"); m.error("c")
    assert w._list.count() == 3
    # 默认 5 个全勾选 → 全显示
    assert all(not w._list.item(i).isHidden() for i in range(w._list.count()))
    # 关掉 INFO、DEBUG → 只剩 ERROR
    w._toggles[LogLevel.INFO].setChecked(False)
    w._toggles[LogLevel.DEBUG].setChecked(False)
    visible = [w._list.item(i) for i in range(w._list.count())
               if not w._list.item(i).isHidden()]
    assert len(visible) == 1 and "ERROR" in visible[0].text()
    # 再关掉 ERROR → 全隐藏
    w._toggles[LogLevel.ERROR].setChecked(False)
    assert all(w._list.item(i).isHidden() for i in range(w._list.count()))
    # 全开 → 全显示
    for lv in LogLevel.levels():
        w._toggles[lv].setChecked(True)
    assert all(not w._list.item(i).isHidden() for i in range(w._list.count()))
    # 清空
    w._btn_clear.click()
    assert w._list.count() == 0

    # ---- 增量刷新：追加保留旧条目对象；回看时不被强制拉底 ----
    LogModel._reset_instance()
    w2 = LogWidget()
    w2.resize(300, 40)               # 小窗口：条目超出可视区（滚动条生效）
    m2 = LogModel.instance()
    m2.info("first")
    it0 = w2._list.item(0)
    assert it0 is not None
    m2.info("second")
    assert w2._list.item(0) is it0, "增量追加不得重建旧条目对象"
    assert w2._list.count() == 2
    for i in range(10):
        m2.info("filler%d" % i)
    assert w2._list.count() == 12
    vbar = w2._list.verticalScrollBar()
    vbar.setValue(0)                 # 用户回看顶部
    m2.info("third")
    assert w2._list.count() == 13
    assert vbar.value() == 0, "回看旧日志时不得被强制拉底"
    # 清空（条目数回退）→ 全量重建
    m2.clear()
    assert w2._list.count() == 0
    m2.info("after-clear")
    assert w2._list.count() == 1
    # 右键复制（直接验证 _copy_item）
    m.info("copy-me")
    it = w._list.item(w._list.count() - 1)
    assert it is not None
    w._copy_item(it)
    assert QApplication.clipboard().text() == it.text()
    print("LogWidget smoke OK")
