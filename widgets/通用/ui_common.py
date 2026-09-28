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
from typing import List, Optional, Tuple

from PyQt5.QtCore import QEvent, QEventLoop, QObject, QPoint, QRect, Qt, pyqtSignal
from PyQt5.QtGui import (
    QColor, QCursor, QFont, QIcon, QPainter, QPen, QPixmap, QPolygon, QWindow,
)
from PyQt5.QtWidgets import (
    QApplication, QDialog, QFrame, QLabel, QVBoxLayout, QWidget,
)

__all__ = ["ClickableLabel", "CRITICAL_COLOR", "ERROR_COLOR", "LandingCard",
           "TitledPanel", "ensure_qt_plugin_path",
           "load_app_qss", "make_icon", "placeholder", "run_dialog",
           "window_size"]

# ---- 语义色（全工程唯一来源：错误红/严重暗红勿再散落硬编码） ----
ERROR_COLOR = "#e15554"      # 错误红：io 非法 / 运行错误 / 日志 ERROR
CRITICAL_COLOR = "#b03a2e"   # 严重暗红：日志 CRITICAL（较 ERROR 深一级）


def load_app_qss() -> str:
    """应用级 QSS（view/app.qss）：滚动条等难以按组件局部设置的公共样式。

    找不到文件 → 返回空串（不设样式，程序照常运行）。
    """
    path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "view", "app.qss")
    if not os.path.isfile(path):
        return ""
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


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


# ---- 弹窗：非模态运行 + 点窗口以外关闭（设置窗口/卡片选择变量窗口共用） ----
_active_closers: List["_ClickOutsideCloser"] = []   # 栈：末尾 = 最内层弹窗


class _ClickOutsideCloser(QObject):
    """点弹窗以外 → 等价 ESC（``reject``），并吞掉那次按下。

    不设父对象：生存期由 :func:`run_dialog` 的局部引用把住、随其返回而销毁 ——
    挂成弹窗子对象看似省事，但过滤器一旦活过 ``run_dialog``（例如冒烟里打桩了
    ``run_dialog`` 而 ``finished`` 永不触发）就会在解释器收尾时随 QApplication
    一起拆，实测会**崩在退出码上、且无回溯**（GC 次序不定 → 时好时坏）。
    """

    def __init__(self, dlg: QDialog) -> None:
        super().__init__()
        self._dlg = dlg

    def eventFilter(self, obj, event) -> bool:  # noqa: N802 (Qt 命名)
        if event.type() != QEvent.MouseButtonPress:
            return False
        # 嵌套 run_dialog（如「选择变量」里再开「新建局部变量」）：只最内层响应。
        # 否则点内层弹窗的那一下会被外层当成「点外面」→ 外层一起被关掉。
        if _active_closers and _active_closers[-1] is not self:
            return False
        if self._is_inside(obj):
            return False
        self._dlg.reject()
        return True                    # 吞：不让下层控件收到这次点击（防误触）

    def _is_inside(self, obj) -> bool:
        """这次按下是否落在本弹窗内（含其弹出子窗）。

        **两层都要认**：一次原生点击先以 ``receiver=QWindow``（窗口层）派发一遍，
        随后才以 ``receiver=控件``（控件层）再派发——只认 QWidget 会把窗口层那次
        当成「点外面」，于是**弹窗被自己内部的一次点击 reject 掉、且该次点击被吞**
        （按钮收不到 ``clicked``，表现为「选完值没反应」）。实测 receiver 序列：
        ``[QWindow, QPushButton]``。

        不能写 ``windowFlags() & Qt.Popup``：Popup 自带 Window 位，任意窗口都非零。
        """
        if isinstance(obj, QWidget):
            top = obj.window()
            wtype = top.windowType()
        elif isinstance(obj, QWindow):
            top = obj                   # 窗口层：receiver 就是窗口本身
            wtype = top.type()          # QWindow 无 windowType()，取 type()
        else:
            return False
        return (top is self._dlg or top is self._dlg.windowHandle()
                or wtype in (Qt.Popup, Qt.ToolTip))


def run_dialog(dlg: QDialog) -> bool:
    """非模态跑 ``dlg`` 并阻塞，返回是否「确定」（等价 ``exec_() == Accepted``）；
    期间点窗口以外 = 同 ESC（取消并关闭，丢弃未提交的编辑）。

    为何不用 ``exec_()``：它强制应用模态，而模态期间其它窗口的鼠标按下**到不了**
    应用级事件过滤器（模态在 ``QApplication::notify`` 里就被丢弃，实测一个事件都
    收不到）→「点窗口以外关闭」无从实现。非模态下事件照常派发，过滤器既看得到、
    也吞得掉（外部那次点击不会误触下层控件）。

    非模态的另一效果：弹窗开着时主窗口仍「可交互」，但**弹窗以外**的任何点击都会
    先关掉弹窗并被吞——等价于模态的观感。窗口级快捷键（``Qt.WindowShortcut``）仍只随
    各自窗口激活而触发，弹窗为活动窗口期间主窗口快捷键不会误触发。
    """
    app = QApplication.instance()
    closer = _ClickOutsideCloser(dlg)
    loop = QEventLoop()
    dlg.finished.connect(loop.quit)
    app.installEventFilter(closer)
    _active_closers.append(closer)          # 入栈：本弹窗期间由它响应（见 eventFilter）
    try:
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()   # 非模态不保证抢焦点（热键编辑框等需立即可输入）
        loop.exec_()
    finally:
        app.removeEventFilter(closer)
        if _active_closers and _active_closers[-1] is closer:
            _active_closers.pop()
    return dlg.result() == QDialog.Accepted


def make_icon(kind: str) -> QIcon:
    """按类别绘制简洁图标：resource=文件夹、variable={ }、step=列表、default=方块。

    exec/settings/refresh/minimize 为活动栏底部功能按钮绘制，放大到 48px 并统一
    尺寸（用户反馈图标太小 + 底部四钮图标内容须一致）。
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
    elif kind == "minimize":
        # 窗口底部横杠（最小化语义）
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#5b7085"))
        p.drawRoundedRect(7, 25, 18, 4, 2, 2)
    elif kind == "refresh":
        # 圆弧箭头（刷新语义）：蓝灰圆弧 + 箭头头，与 exec/settings 同为底部功能按钮
        p.setPen(QPen(QColor("#2b5fa0"), 3, cap=Qt.RoundCap))
        p.setBrush(Qt.NoBrush)
        p.drawArc(QRect(6, 6, 20, 20), 30 * 16, 300 * 16)   # 300° 弧，缺口在右上
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#2b5fa0"))
        p.drawPolygon(QPolygon([QPoint(22, 6), QPoint(28, 12), QPoint(16, 12)]))  # 箭头头
    elif kind == "data":
        # 表格（数据视图语义）：蓝灰外框 + 表头分隔横线 + 一条竖线分列，
        # 与 resource 同色系；按 32×32 原样返回（工具栏文字按钮旁小图标，不放大）
        pen = QPen(QColor("#2b5fa0"), 2)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawRect(5, 6, 22, 20)                       # 外框
        p.drawLine(5, 13, 27, 13)                      # 表头分隔横线
        p.drawLine(13, 13, 13, 26)                     # 列分隔竖线
    else:
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#888888"))
        p.drawRoundedRect(5, 5, 22, 22, 4, 4)
    p.end()
    if kind in ("exec", "settings", "refresh", "minimize"):
        pm = pm.scaled(48, 48, transformMode=Qt.SmoothTransformation)  # 底部功能按钮图标放大并统一尺寸
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

    # make_icon：各类别（含未知回退）生成非空图标；exec/settings/refresh/minimize 放大 48px
    for kind in ("resource", "variable", "step", "composite", "template",
                 "exec", "settings", "refresh", "minimize", "data", "default", "未知"):
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

    # 语义色常量（错误红全工程唯一来源，勿散落硬编码）
    assert ERROR_COLOR == "#e15554" and CRITICAL_COLOR == "#b03a2e"
    # 应用级 QSS：view/app.qss 存在且含滚动条样式
    qss = load_app_qss()
    assert "QScrollBar" in qss, qss

    # ---- 弹窗：非模态运行 + 点窗口以外关闭（吞掉该次点击，不误触下层） ----
    from PyQt5.QtCore import QEvent, QPoint, QTimer
    from PyQt5.QtTest import QTest
    from PyQt5.QtWidgets import QDialog, QLineEdit, QPushButton

    host = QWidget()
    host.resize(240, 160)
    hit = []
    btn = QPushButton("下层按钮", host)
    btn.move(10, 10)
    btn.clicked.connect(lambda: hit.append(1))
    host.show()
    app.processEvents()

    def _fallback(dlg, ms=3000):
        """兜底：万一事件没按预期到达，别把冒烟挂死。"""
        QTimer.singleShot(ms, dlg.reject)

    def _native_click(win: QWidget, target: QWidget, pt: QPoint) -> None:
        """**真·原生点击**：经窗口层派发，与真人鼠标同一条路。

        必须这样点——``QTest.mouseClick(QWidget, …)`` 只发控件层事件，测不出
        「窗口层那次被误判成点弹窗以外」（实测一次原生点击的 receiver 序列是
        ``[QWindow, QPushButton]``：窗口层先到，控件层后到）。
        """
        QTest.qWaitForWindowExposed(win)
        QTest.mouseClick(win.windowHandle(), Qt.LeftButton, Qt.NoModifier,
                         target.mapTo(win, pt))

    # 1) 点弹窗以外 → 关闭（reject=取消）+ 该次点击被吞（下层按钮不响应）
    dlg1 = QDialog(None)
    dlg1.setWindowTitle("t1")
    dlg1.resize(180, 120)
    dlg1.move(400, 120)
    _fallback(dlg1)
    QTimer.singleShot(60, lambda: _native_click(host, btn, QPoint(5, 5)))
    assert run_dialog(dlg1) is False          # 未「确定」→ 取消语义（同 ESC）
    assert hit == [], hit                     # 外部点击被吞，未误触下层按钮
    assert not dlg1.isVisible()
    # 过滤器随 run_dialog 返回即摘（否则会活到解释器收尾，崩在退出码上、无回溯）
    QTest.mouseClick(btn, Qt.LeftButton, pos=QPoint(5, 5))
    assert hit == [1], hit

    # 2) 弹窗**内部**点击 → 不关闭、控件照常收到（回归：曾把窗口层那次当「点外面」，
    #    于是弹窗被自己内部的一次点击 reject 掉、点击被吞 → 按钮收不到 clicked，
    #    表现为「在卡片里点 … 选变量，选完没反应/填不进去」）
    dlg2 = QDialog(None)
    dlg2.setWindowTitle("t2")
    dlg2.resize(180, 120)
    dlg2.move(400, 120)
    edit = QLineEdit(dlg2)
    edit.move(10, 10)
    ok2 = QPushButton("确定", dlg2)
    ok2.move(10, 50)
    ok2.clicked.connect(dlg2.accept)
    _fallback(dlg2)
    still_open = []

    def _click_inside():
        QTest.mouseClick(edit, Qt.LeftButton, pos=QPoint(5, 5))   # 点输入框即不该关
        still_open.append(dlg2.isVisible())
        _native_click(dlg2, ok2, QPoint(5, 5))                   # 点「确定」→ 应生效

    QTimer.singleShot(60, _click_inside)
    assert run_dialog(dlg2) is True            # 内部点击生效 → 走到 accept
    assert still_open == [True], still_open

    # 3) run_dialog 透传 accept/reject 结果
    dlg3 = QDialog(None)
    QTimer.singleShot(20, dlg3.accept)
    assert run_dialog(dlg3) is True
    dlg4 = QDialog(None)
    QTimer.singleShot(20, dlg4.reject)
    assert run_dialog(dlg4) is False

    # 4) 嵌套 run_dialog（「选择变量」里再开「新建局部变量」）：内层开着时只有内层
    #    响应——否则点内层弹窗那一下会被外层当成「点外面」，外层跟着一起被关掉
    dlg5 = QDialog(None)
    dlg5.setWindowTitle("外层")
    dlg5.resize(200, 120)
    dlg5.move(400, 120)
    _fallback(dlg5)
    inner_got = []

    def _open_inner():
        dlg6 = QDialog(None)
        dlg6.setWindowTitle("内层")
        dlg6.resize(200, 120)
        ok6 = QPushButton("内确定", dlg6)
        ok6.move(10, 10)
        ok6.clicked.connect(dlg6.accept)
        QTimer.singleShot(60, lambda: _native_click(dlg6, ok6, QPoint(5, 5)))
        _fallback(dlg6)
        inner_got.append(run_dialog(dlg6))
        assert dlg5.isVisible(), "内层操作把外层一起关了（_active_closers 栈没生效）"
        dlg5.accept()

    QTimer.singleShot(60, _open_inner)
    assert run_dialog(dlg5) is True
    assert inner_got == [True], inner_got     # 内层自己的点击生效
    assert not _active_closers, _active_closers   # 栈已清空（不留残余）

    # 5) 弹出子窗（QComboBox 下拉等 Qt.Popup）不算「点外面」——两层都要放行
    #    （QWindow 用 type()：它是 flags 与 WindowType_Mask 的结果，可直接比 Popup；
    #     写 windowFlags() & Qt.Popup 则任意窗口都非零——Popup 自带 Window 位）
    dlg7 = QDialog(None)
    closer7 = _ClickOutsideCloser(dlg7)
    pop = QWidget(None, Qt.Popup)
    other = QWidget(None, Qt.Window)
    pop.show()
    other.show()
    QTest.qWaitForWindowExposed(pop)
    QTest.qWaitForWindowExposed(other)
    assert closer7._is_inside(dlg7) is True
    assert closer7._is_inside(pop.windowHandle()) is True, "窗口层：弹出子窗被当外面"
    assert closer7._is_inside(pop) is True, "控件层：弹出子窗被当外面"
    assert closer7._is_inside(other.windowHandle()) is False, "窗口层：别的窗口应算外面"
    assert closer7._is_inside(other) is False, "控件层：别的窗口应算外面"
    pop.close()
    other.close()
    dlg7.close()
    host.close()

    print("ui_common smoke OK")
