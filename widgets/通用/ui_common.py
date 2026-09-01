# -*- coding: utf-8 -*-
"""
通用 UI 小件
============

自绘图标 :func:`make_icon`、程序窗口尺寸 :func:`window_size`、落地页大卡片
:class:`LandingCard`、带标题面板 :class:`TitledPanel` 与占位页 :func:`placeholder`
（原 main_widget 内联小件，拆分至此以便复用与维护）。
"""

from __future__ import annotations

import os
from typing import Optional, Tuple

from PyQt5.QtCore import QPoint, Qt, pyqtSignal
from PyQt5.QtGui import (
    QColor, QCursor, QFont, QIcon, QPainter, QPen, QPixmap, QPolygon,
)
from PyQt5.QtWidgets import QApplication, QFrame, QLabel, QVBoxLayout, QWidget

__all__ = ["ClickableLabel", "LandingCard", "TitledPanel",
           "ensure_qt_plugin_path", "make_icon", "placeholder", "window_size"]


class ClickableLabel(QLabel):
    """可点击标签：左键点击发出 ``clicked``（资源/变量树缩略图共用，评审#21）。"""

    clicked = pyqtSignal()

    def mousePressEvent(self, event) -> None:  # noqa: N802 (Qt 命名)
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


def ensure_qt_plugin_path() -> None:
    """确保 Qt 插件（platforms/imageformats 等）可被找到——venv 等独立部署必需。

    根因：PyQt5 在 venv 里把插件目录解析到**基础 Python 安装目录**
    （如 ``C:/0_self/bin/Python314/platforms``）而非当前环境的 site-packages，
    导致「no Qt platform plugin could be initialized」弹窗。此处显式指向
    当前环境中 PyQt5 附带的 plugins 目录；已设置的环境变量不覆盖
    （用户手工设置优先）。须在创建 QApplication 之前调用。
    """
    import PyQt5
    plugins = os.path.join(os.path.dirname(PyQt5.__file__), "Qt5", "plugins")
    os.environ.setdefault("QT_QPA_PLATFORM_PLUGIN_PATH",
                          os.path.join(plugins, "platforms"))
    os.environ.setdefault("QT_PLUGIN_PATH", plugins)


def window_size() -> Tuple[int, int]:
    """程序窗口尺寸：当前屏幕可用区域的 2/3（宽、高）。

    多屏时取光标所在屏（窗口出现在用户当前所在屏幕），无则主屏。
    """
    app = QApplication.instance()
    screen = app.screenAt(QCursor.pos()) if app is not None else None
    if screen is None and app is not None:
        screen = app.primaryScreen()
    if screen is None:
        return (1280, 720)          # 兜底（无屏幕环境）
    g = screen.availableGeometry()
    return g.width() * 2 // 3, g.height() * 2 // 3


def make_icon(kind: str) -> QIcon:
    """按类别绘制简洁图标：resource=文件夹、variable={ }、step=列表、default=方块。

    exec/settings 为活动栏底部功能按钮绘制，放大到 48px（用户反馈图标太小）。
    """
    pm = QPixmap(32, 32)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    if kind == "resource":
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#2b5fa0"))
        p.drawRoundedRect(3, 5, 13, 7, 2, 2)        # 文件夹标签
        p.setBrush(QColor("#3a7bd5"))
        p.drawRoundedRect(3, 9, 26, 18, 3, 3)        # 文件夹主体
    elif kind == "variable":
        p.setPen(QPen(QColor("#27ae60"), 2))
        p.setFont(QFont("Consolas", 14, QFont.Bold))
        p.drawText(pm.rect(), Qt.AlignCenter, "{ }")
    elif kind == "step":
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#e67e22"))
        for y in (7, 14, 21):
            p.drawRoundedRect(4, y, 24, 5, 2, 2)
    elif kind == "composite":
        # 叠层卡片（合成卡片 = 多步骤的集合）：后片 + 前片错位，紫区别于步骤橙
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#8e6db5"))
        p.drawRoundedRect(4, 4, 20, 20, 3, 3)       # 后片
        p.setBrush(QColor("#b290e0"))
        p.drawRoundedRect(8, 8, 20, 20, 3, 3)       # 前片
        p.setBrush(QColor("#fff3e0"))
        for y in (12, 18, 24):
            p.drawRoundedRect(11, y, 14, 3, 1, 1)    # 前片内三条横线
    elif kind == "template":
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#e67e22"))
        p.drawRoundedRect(5, 5, 22, 22, 4, 4)      # 橙色方块（与占位「步骤」裸三横线区分）
        p.setBrush(QColor("#fff3e0"))
        for y in (12, 18, 24):
            p.drawRoundedRect(9, y, 14, 3, 1, 1)   # 方块内三条横线
    elif kind == "exec":
        # 绿色播放三角（执行语义）
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#27ae60"))
        p.drawPolygon(QPolygon([QPoint(10, 8), QPoint(10, 24), QPoint(25, 16)]))
    elif kind == "settings":
        # 齿轮：外环 + 内圆
        p.setPen(QPen(QColor("#888888"), 2.5))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(QPoint(16, 16), 9, 9)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#888888"))
        p.drawEllipse(QPoint(16, 16), 3.5, 3.5)
    else:
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#888888"))
        p.drawRoundedRect(5, 5, 22, 22, 4, 4)
    p.end()
    if kind in ("exec", "settings"):
        pm = pm.scaled(48, 48, transformMode=Qt.SmoothTransformation)  # 底部功能按钮图标放大
    return QIcon(pm)


class LandingCard(QFrame):
    """可点击的大卡片；左键点击发出 ``clicked``。"""

    clicked = pyqtSignal()

    def __init__(self, title: str, desc: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setMinimumWidth(240)
        self.setMinimumHeight(240)
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet(
            "QFrame { background:#fafafa; border:2px solid #ccc; border-radius:14px; }"
            "QFrame:hover { border-color:#3a7bd5; background:#fff; }")
        lay = QVBoxLayout(self)
        lay.addStretch()
        t = QLabel(title)
        t.setAlignment(Qt.AlignCenter)
        t.setStyleSheet("font-size:30px; font-weight:bold; color:#333; background:transparent; border:none;")
        d = QLabel(desc)
        d.setAlignment(Qt.AlignCenter)
        d.setStyleSheet("font-size:13px; color:#888; background:transparent; border:none;")
        lay.addWidget(t)
        lay.addWidget(d)
        lay.addStretch()

    def mousePressEvent(self, event) -> None:  # noqa: N802 (Qt 命名)
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class TitledPanel(QWidget):
    """带标题的栏容器（日志栏等面板复用）。"""

    def __init__(self, title: str, content: QWidget,
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._title = QLabel(title)
        self._title.setStyleSheet(
            "background:#eaeaea; color:#333;"
            " padding:4px 8px; border-bottom:1px solid #ccc;")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(self._title)
        lay.addWidget(content, 1)

    def set_title(self, title: str) -> None:
        self._title.setText(title)


def placeholder(text: str) -> QWidget:
    """占位页：居中灰字提示（管理树「待实现」等场景）。"""
    w = QWidget()
    lay = QVBoxLayout(w)
    lbl = QLabel(text)
    lbl.setAlignment(Qt.AlignCenter)
    lbl.setStyleSheet("color:#999; font-size:16px;")
    lay.addWidget(lbl)
    return w


# ================================================================
# 冒烟演示：直接 ``python -m widgets.通用.ui_common`` 运行
# ================================================================
if __name__ == "__main__":
    import sys

    from PyQt5.QtWidgets import QApplication

    # Qt 插件指路须先于 QApplication（venv 部署修复的核心入口）
    ensure_qt_plugin_path()
    _plugins = os.path.join(
        os.path.dirname(__import__("PyQt5").__file__), "Qt5", "plugins")
    assert os.environ["QT_PLUGIN_PATH"] == _plugins
    assert os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] == os.path.join(
        _plugins, "platforms")
    assert os.path.isdir(os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"])
    # 已设置的不覆盖（用户手工设置优先）
    os.environ["QT_PLUGIN_PATH"] = "X"
    ensure_qt_plugin_path()
    assert os.environ["QT_PLUGIN_PATH"] == "X"
    del os.environ["QT_PLUGIN_PATH"]

    app = QApplication.instance() or QApplication(sys.argv)

    # make_icon：各类别（含未知回退）生成非空图标；exec/settings 放大 48px
    for kind in ("resource", "variable", "step", "composite", "template",
                 "exec", "settings", "default", "未知"):
        assert not make_icon(kind).isNull(), kind
    assert make_icon("exec").availableSizes()

    # window_size：当前屏幕可用区 2/3
    w, h = window_size()
    assert w > 0 and h > 0
    screen = app.primaryScreen()
    if screen is not None:
        g = screen.availableGeometry()
        assert (w, h) == (g.width() * 2 // 3, g.height() * 2 // 3)

    # LandingCard：clicked 信号（连线验证，绕过真实鼠标）
    card = LandingCard("新建", "创建一个空工程")
    got = []
    card.clicked.connect(lambda: got.append(1))
    card.clicked.emit()
    assert got == [1]

    # TitledPanel：标题随 set_title 更新
    panel = TitledPanel("甲", QLabel("x"))
    assert panel._title.text() == "甲"
    panel.set_title("乙")
    assert panel._title.text() == "乙"

    # placeholder：居中灰字提示
    ph = placeholder("待实现")
    lbl = ph.findChild(QLabel)
    assert lbl is not None and lbl.text() == "待实现"

    print("ui_common smoke OK")
