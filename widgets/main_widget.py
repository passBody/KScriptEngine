# -*- coding: utf-8 -*-
"""
主窗口（入口）
============

:class:`MainWindow` 是 KScript 的主窗口。无工程时显示「新建 / 打开」两个大卡片；
打开 ``.kscp`` 后，左侧是管理树切换栏 + 当前管理树，中间是当前管理树的大预览。

管理树经 :class:`ManagementTree` 抽象（预留接口）：每个管理树提供左侧树控件
``tree_widget()`` 与中间预览 ``preview_widget()``。当前实现资源 / 变量 /
步骤列表 / 步骤模板四棵管理树；步骤列表管理树（:class:`StepListManagementTree`）
= 左侧 :class:`StepListTreeWidget` + 宿主 :class:`_StepListHost`（承载
:class:`StepListView`），与变量管理树共享同一棵变量树（变量变更 → 卡片重检
颜色），不再有占位「步骤」项。

启动::

    python main.py                # landing：新建 / 打开
    python main.py xxx.kscp       # 直接打开
    python main.py --check        # 自检（渲染后自动退出）
"""

from __future__ import annotations

import os
import platform
import sys
from typing import Callable, List, Optional, Tuple

from PyQt5.QtCore import Qt, QSize, QTimer, pyqtSignal
from PyQt5.QtGui import QColor, QCursor, QFont, QIcon, QPainter, QPen, QPixmap
from PyQt5.QtWidgets import (
    QAction, QApplication, QFileDialog, QFrame, QHBoxLayout, QLabel,
    QLineEdit, QMainWindow, QMenu, QMessageBox, QPushButton, QSplitter,
    QStackedWidget, QToolButton, QVBoxLayout, QWidget,
)

from model.kscp_package import KscpPackage
from model.log_model import LogLevel, LogModel
from widgets.resource_tree_widget import ResourceTreeWidget
from widgets.log_widget import LogWidget
from widgets.variable_tree_widget import VariableTreeWidget
from model.step_list import StepList
from model.step_list_store import StepListStore
from model.step_manager import StepManager
from model.variable_tree import VariableTree
from widgets.step_list_view import StepClipboard, StepListView
from widgets.step_list_tree_widget import StepListTreeWidget
from widgets.step_tree_widget import StepTreeWidget

__all__ = ["ManagementTree", "MainWindow", "main"]


# ================================================================
# 活动栏图标（自绘，避免 QStyle 枚举 stub 问题）
# ================================================================
_ICON_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "icon", "kscript.ico")


def _window_size() -> Tuple[int, int]:
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


def _make_icon(kind: str) -> QIcon:
    """按类别绘制简洁图标：resource=文件夹、variable={ }、step=列表、default=方块。"""
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
    elif kind == "template":
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#e67e22"))
        p.drawRoundedRect(5, 5, 22, 22, 4, 4)      # 橙色方块（与占位「步骤」裸三横线区分）
        p.setBrush(QColor("#fff3e0"))
        for y in (12, 18, 24):
            p.drawRoundedRect(9, y, 14, 3, 1, 1)   # 方块内三条横线
    else:
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#888888"))
        p.drawRoundedRect(5, 5, 22, 22, 4, 4)
    p.end()
    return QIcon(pm)


# ================================================================
# 管理树接口（预留）
# ================================================================
class ManagementTree:
    """管理树基类（预留接口）：提供左侧树控件 + 中间预览控件。

    子类实现 :meth:`_build_tree` / :meth:`_build_preview`（或重写
    :meth:`tree_widget` / :meth:`preview_widget`）。控件懒构建并缓存。
    """

    def __init__(self, name: str) -> None:
        self._name = name
        self._tree: Optional[QWidget] = None
        self._preview: Optional[QWidget] = None

    @property
    def name(self) -> str:
        return self._name

    def icon(self) -> QIcon:
        """管理树图标（活动栏用）。子类可重写以提供专属图标。"""
        return _make_icon("default")

    def tree_widget(self) -> QWidget:
        if self._tree is None:
            self._tree = self._build_tree()
        return self._tree

    def preview_widget(self) -> QWidget:
        if self._preview is None:
            self._preview = self._build_preview()
        return self._preview

    def _build_tree(self) -> QWidget:
        raise NotImplementedError

    def _build_preview(self) -> QWidget:
        raise NotImplementedError


class ResourceManagementTree(ManagementTree):
    """资源管理树：``ResourceTreeWidget`` + 其预览面板。"""

    def __init__(self, package: KscpPackage) -> None:
        super().__init__("资源")
        self._package = package
        self._rtree: Optional[ResourceTreeWidget] = None

    def icon(self) -> QIcon:
        return _make_icon("resource")

    def tree_widget(self) -> QWidget:
        if self._rtree is None:
            self._rtree = ResourceTreeWidget(self._package)
        assert self._rtree is not None
        return self._rtree

    def preview_widget(self) -> QWidget:
        if self._rtree is None:
            self._rtree = ResourceTreeWidget(self._package)
        assert self._rtree is not None
        if self._preview is None:
            self._preview = self._rtree.preview_widget()
        assert self._preview is not None
        return self._preview


class VariableManagementTree(ManagementTree):
    """变量管理树：``VariableTreeWidget`` + 其编辑卡。"""

    def __init__(self, package: KscpPackage,
                 tree: Optional[VariableTree] = None) -> None:
        super().__init__("变量")
        self._package = package
        self._tree = tree
        self._vtree: Optional[VariableTreeWidget] = None

    def icon(self) -> QIcon:
        return _make_icon("variable")

    def tree_widget(self) -> QWidget:
        if self._vtree is None:
            self._vtree = VariableTreeWidget(self._package, self._tree)
        assert self._vtree is not None
        return self._vtree

    def preview_widget(self) -> QWidget:
        if self._vtree is None:
            self._vtree = VariableTreeWidget(self._package, self._tree)
        assert self._vtree is not None
        if self._preview is None:
            self._preview = self._vtree.preview_widget()
        assert self._preview is not None
        return self._preview


class StepManagementTree(ManagementTree):
    """步骤模板管理树：``StepTreeWidget`` + 其只读信息面板。"""

    def __init__(self, package: KscpPackage,
                 mgr: Optional[StepManager] = None) -> None:
        super().__init__("步骤模板")
        self._package = package
        self._mgr = mgr   # None → StepTreeWidget 自建工厂（独立使用场景）
        self._stree: Optional[StepTreeWidget] = None

    def icon(self) -> QIcon:
        return _make_icon("template")

    def tree_widget(self) -> QWidget:
        if self._stree is None:
            self._stree = StepTreeWidget(self._package, self._mgr)
        assert self._stree is not None
        return self._stree

    def preview_widget(self) -> QWidget:
        if self._stree is None:
            self._stree = StepTreeWidget(self._package, self._mgr)
        assert self._stree is not None
        if self._preview is None:
            self._preview = self._stree.preview_widget()
        assert self._preview is not None
        return self._preview


class StepListManagementTree(ManagementTree):
    """步骤列表管理树：StepListTreeWidget + 宿主（占位/列表视图）。"""

    def __init__(self, package: KscpPackage, tree: VariableTree,
                 mgr: Optional[StepManager] = None) -> None:
        super().__init__("步骤列表")
        self._package = package
        self._tree = tree
        if mgr is not None:
            self._mgr = mgr   # 与步骤模板树共享同一工厂（模板只加载一次）
        else:
            self._mgr = StepManager(package, tree)
            self._mgr.load()
        if package.exists("step_list.json"):
            self._store = StepListStore.from_json(
                package.read_file("step_list.json"), self._mgr)
        else:
            self._store = StepListStore.create_empty()
            self._save_store()
        self._clipboard = StepClipboard()
        self._sl_tree: Optional[StepListTreeWidget] = None
        self._host: Optional[_StepListHost] = None
        self._current: Optional[str] = None

    def icon(self) -> QIcon:
        return _make_icon("step")

    def _save_store(self) -> None:
        self._package.write_file("step_list.json", self._store.to_json_bytes())

    def refresh_cards(self) -> None:
        """变量树变化 → 宿主重检卡片颜色（不重建）。"""
        if self._host is not None:
            self._host.refresh_validity()

    def tree_widget(self) -> QWidget:
        if self._sl_tree is None:
            self._sl_tree = StepListTreeWidget(
                self._store, self._mgr, self._clipboard,
                self._save_store, None)
            self._sl_tree.list_selected.connect(self._on_list_selected)
            self._sl_tree.store_changed.connect(self._on_store_changed)
        assert self._sl_tree is not None
        return self._sl_tree

    def _on_edited(self) -> None:
        """视图内容编辑（io/签名/激活切换）→ 保存 + 树勾选框同步激活态。"""
        self._save_store()
        if self._sl_tree is not None:
            self._sl_tree.refresh_active_marks()

    def preview_widget(self) -> QWidget:
        if self._host is None:
            self._host = _StepListHost(
                self._mgr, self._clipboard, self._on_edited, None)
            # 视图错误数变化 → 重标左侧树错误条目（树可能尚未构建，判空）
            self._host.errors_changed.connect(self._refresh_tree_marks)
        assert self._host is not None
        return self._host

    def _refresh_tree_marks(self, _n: int) -> None:
        """卡片错误数变化 → 按列表 io 校验重标树错误条目（红加粗，见 refresh_error_marks）。"""
        if self._sl_tree is not None:
            self._sl_tree.refresh_error_marks()

    # ---- 宿主联动 ----
    def _on_list_selected(self, path: str) -> None:
        self._current = path
        if self._host is not None:
            try:
                self._host.set_list(self._store.get(path), self._mgr)
            except FileNotFoundError:
                self._host.set_list(None)

    def _on_store_changed(self) -> None:
        """树内容变更（勾选激活/添加/粘贴/删除）→ 宿主同步当前列表。

        删除 → 占位页；其余（尤其树勾选框切换激活，list_selected 不触发）
        → 重建卡片画面，激活切换立即刷新视图。
        """
        if self._host is None or self._current is None:
            return
        try:
            lst = self._store.get(self._current)
        except FileNotFoundError:
            self._host.set_list(None)
        else:
            self._host.set_list(lst, self._mgr)


class _StepListHost(QStackedWidget):
    """步骤列表视图宿主：占位页 + 工具栏 + StepListView（视图编辑 → 保存回调）。

    工具栏两行：「跳转序号 / 搜索标签定位」（卡片过多时定位用，
    经 :meth:`StepListView.jump_to_index` / :meth:`StepListView.locate_by_tag`）；
    下方「错误卡片: N + 跳转错误」（错误数随视图刷新经
    :attr:`StepListView.errors_changed` 同步，跳转经 :meth:`StepListView.jump_to_error`）。
    错误数同时经 :attr:`errors_changed` 转发给宿主（步骤列表管理树 → 树条目红标记）。
    """

    errors_changed = pyqtSignal(int)   # 错误卡片数（转发自 StepListView）

    def __init__(self, mgr: StepManager, clipboard: StepClipboard,
                 on_edited: Callable[[], None],
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._placeholder = QLabel("从左侧选择一个步骤列表")
        self._placeholder.setAlignment(Qt.AlignCenter)
        self._placeholder.setStyleSheet("color:#999; font-size:15px;")
        self.addWidget(self._placeholder)          # 0
        self._view = StepListView(mgr, clipboard, None)
        self._view.edited.connect(on_edited)
        self._view.errors_changed.connect(self._on_errors_changed)
        self._view.errors_changed.connect(self.errors_changed)
        page1 = QWidget()
        lay = QVBoxLayout(page1)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(self._build_toolbar())
        lay.addWidget(self._view)
        self.addWidget(page1)                      # 1
        self.setCurrentIndex(0)

    def _build_toolbar(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("viewToolbar")
        bar.setStyleSheet(
            "#viewToolbar { background: rgba(244, 247, 252, 0.9);"
            " border-bottom: 1px solid rgba(128, 148, 178, 0.4); }")
        lay = QVBoxLayout(bar)
        lay.setContentsMargins(8, 4, 8, 4)
        lay.setSpacing(2)
        row1 = QHBoxLayout()
        row1.setSpacing(6)
        row1.addWidget(QLabel("跳转"))
        self._jump_edit = QLineEdit()
        self._jump_edit.setFixedWidth(64)
        self._jump_edit.setPlaceholderText("序号")
        self._jump_edit.returnPressed.connect(self._on_jump)
        row1.addWidget(self._jump_edit)
        btn_jump = QPushButton("定位")
        btn_jump.clicked.connect(self._on_jump)
        row1.addWidget(btn_jump)
        row1.addSpacing(12)
        row1.addWidget(QLabel("搜索标签"))
        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText("关键词")
        self._search_edit.returnPressed.connect(self._on_search)
        row1.addWidget(self._search_edit, 1)
        btn_search = QPushButton("搜索")
        btn_search.clicked.connect(self._on_search)
        row1.addWidget(btn_search)
        self._toolbar_status = QLabel("")
        self._toolbar_status.setStyleSheet("color:#888;")
        row1.addWidget(self._toolbar_status)
        lay.addLayout(row1)
        # 第二行：错误卡片信息（数量随视图 errors_changed 同步）+ 跳转错误
        row2 = QHBoxLayout()
        row2.setSpacing(6)
        self._error_count = QLabel("错误卡片: 0")
        self._error_count.setStyleSheet("color:#c8564c;")
        row2.addWidget(self._error_count)
        btn_errors = QPushButton("跳转错误")
        btn_errors.clicked.connect(self._on_jump_error)
        row2.addWidget(btn_errors)
        row2.addStretch(1)
        lay.addLayout(row2)
        return bar

    def _on_errors_changed(self, n: int) -> None:
        self._error_count.setText("错误卡片: %d" % n)

    def _on_jump_error(self) -> None:
        """跳转到下一张错误卡片（视图循环定位）；无错误卡 → 提示。"""
        if self._view.jump_to_error():
            self._toolbar_status.setText("已定位错误卡片")
        else:
            self._toolbar_status.setText("无错误卡片")

    def _on_jump(self) -> None:
        text = self._jump_edit.text().strip()
        try:
            n = int(text)
        except ValueError:
            self._toolbar_status.setText("序号需为数字")
            return
        total = len(self._view._cards)
        if self._view.jump_to_index(n):
            self._toolbar_status.setText("已定位 %d/%d" % (n, total))
        else:
            self._toolbar_status.setText("序号越界（1-%d）" % total)

    def _on_search(self) -> None:
        if self._view.locate_by_tag(self._search_edit.text()):
            self._toolbar_status.setText("已定位")
        else:
            self._toolbar_status.setText("未找到匹配标签")

    def set_list(self, step_list: Optional[StepList],
                 mgr: Optional[StepManager] = None) -> None:
        self._view.set_list(step_list, mgr)
        self.setCurrentIndex(1 if step_list is not None else 0)

    def refresh_validity(self) -> None:
        self._view.refresh_validity()


class PlaceholderManagementTree(ManagementTree):
    """占位管理树：演示切换 + 预留接口，后续替换为真实实现。"""

    def __init__(self, name: str, icon_kind: str = "default") -> None:
        super().__init__(name)
        self._icon_kind = icon_kind

    def icon(self) -> QIcon:
        return _make_icon(self._icon_kind)

    def _build_tree(self) -> QWidget:
        return self._placeholder("「%s管理树」待实现" % self._name)

    def _build_preview(self) -> QWidget:
        return self._placeholder("「%s管理树」预览 待实现" % self._name)

    @staticmethod
    def _placeholder(text: str) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lbl = QLabel(text)
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setStyleSheet("color:#999; font-size:16px;")
        lay.addWidget(lbl)
        return w


# ================================================================
# landing 卡片
# ================================================================
class _LandingCard(QFrame):
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


class _TitledPanel(QWidget):
    """带标题的栏容器（预留：日志栏等后续面板复用本类）。"""

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


class _ActivityBar(QWidget):
    """VSCode 风格活动栏：竖排图标按钮，悬停 tooltip 显示功能名。"""

    currentChanged = pyqtSignal(int)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setFixedWidth(56)
        self._lay = QVBoxLayout(self)
        self._lay.setContentsMargins(4, 8, 4, 8)
        self._lay.setSpacing(6)
        self._lay.addStretch()
        self._buttons: List[QToolButton] = []

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
        self._lay.insertWidget(self._lay.count() - 1, btn)   # 插在 stretch 之前
        self._buttons.append(btn)

    def clear(self) -> None:
        for btn in self._buttons:
            btn.deleteLater()
        self._buttons.clear()

    def set_current_row(self, row: int) -> None:
        if 0 <= row < len(self._buttons):
            self._buttons[row].setChecked(True)


# ================================================================
# 主窗口
# ================================================================
class MainWindow(QMainWindow):
    """KScript 主窗口：landing（无工程）/ project（已开包）两态。"""

    def __init__(self, path: Optional[str] = None,
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._package: Optional[KscpPackage] = None
        self._kscp_path: Optional[str] = None
        self._managers: List[ManagementTree] = []
        self.setWindowTitle("KScript")
        self.resize(600, 350)            # landing 保持原尺寸；打开工程时放大为屏幕 2/3
        self._project_sized = False
        self._log_widget: Optional[LogWidget] = None
        self._status_counts: Optional[QLabel] = None
        self._status_python: Optional[QLabel] = None
        self._manage_btn: Optional[QToolButton] = None
        self._step_mgr: Optional[StepManagementTree] = None

        self._central = QStackedWidget()
        self.setCentralWidget(self._central)
        self._central.addWidget(self._build_landing())    # page 0
        self._project_widget: Optional[QWidget] = None
        self._switcher: Optional[_ActivityBar] = None
        self._tree_stack: Optional[QStackedWidget] = None
        self._preview_stack: Optional[QStackedWidget] = None
        self._tree_panel: Optional[_TitledPanel] = None

        self._build_toolbar()
        self._setup_statusbar()
        LogModel.instance().info("KScript 启动")
        if path:
            self._open_file(path)   # 失败则停在 landing

    # ---- 工具栏 ----
    def _build_toolbar(self) -> None:
        tb = self.addToolBar("主工具栏")
        assert tb is not None
        tb.setMovable(False)
        # 文件菜单：新建 / 打开 / 保存 / 另存为（快捷键挂菜单项上）
        file_btn = QToolButton(self)
        file_btn.setText("文件")
        file_btn.setPopupMode(QToolButton.InstantPopup)
        file_menu = QMenu(file_btn)
        a_new = file_menu.addAction("新建")
        a_new.setShortcut("Ctrl+N")
        a_new.triggered.connect(self._on_new)
        a_open = file_menu.addAction("打开…")
        a_open.setShortcut("Ctrl+O")
        a_open.triggered.connect(self._on_open)
        file_menu.addSeparator()
        a_save = file_menu.addAction("保存")
        a_save.setShortcut("Ctrl+S")
        a_save.triggered.connect(self._on_save)
        a_save_as = file_menu.addAction("另存为…")
        a_save_as.setShortcut("Ctrl+Shift+S")
        a_save_as.triggered.connect(self._on_save_as)
        file_btn.setMenu(file_menu)
        tb.addWidget(file_btn)

        # 管理菜单：导入步骤模板（未开包不可用）
        self._manage_btn = QToolButton(self)
        self._manage_btn.setText("管理")
        self._manage_btn.setPopupMode(QToolButton.InstantPopup)
        manage_menu = QMenu(self._manage_btn)
        a_import = manage_menu.addAction("导入…")
        a_import.triggered.connect(self._on_import)
        self._manage_btn.setMenu(manage_menu)
        self._manage_btn.setEnabled(False)
        tb.addWidget(self._manage_btn)

        # 窗口菜单：显示日志开关
        win_btn = QToolButton(self)
        win_btn.setText("窗口")
        win_btn.setPopupMode(QToolButton.InstantPopup)
        win_menu = QMenu(win_btn)
        self._a_show_log = win_menu.addAction("显示日志")
        self._a_show_log.setCheckable(True)
        self._a_show_log.setChecked(True)
        self._a_show_log.toggled.connect(self._on_toggle_log)
        win_btn.setMenu(win_menu)
        tb.addWidget(win_btn)

    def _on_toggle_log(self, checked: bool) -> None:
        if self._log_widget is not None:
            self._log_widget.setVisible(checked)

    def _on_import(self) -> None:
        if self._package is None or self._step_mgr is None:
            return
        folder = QFileDialog.getExistingDirectory(
            self, "导入步骤模板 — 选择 actions 文件夹", "")
        if not folder:
            return
        stree = self._step_mgr.tree_widget()
        assert isinstance(stree, StepTreeWidget)
        n = stree.import_templates(folder)
        sb = self.statusBar()
        assert sb is not None
        if n:
            sb.showMessage("已导入 %d 个步骤模板" % n, 5000)
            LogModel.instance().info("导入步骤模板完成: 成功 %d 个" % n)
        else:
            sb.showMessage("没有可导入的步骤模板", 5000)
            LogModel.instance().warning("导入步骤模板: 没有成功导入任何模板（详见日志）")

    # ---- 状态栏（环境提示）----
    def _setup_statusbar(self) -> None:
        sb = self.statusBar()
        assert sb is not None
        self._status_counts = QLabel("错误: 0  警告: 0")
        sb.addWidget(self._status_counts)                      # 左：错误/警告计数
        self._status_python = QLabel("Python %s" % platform.python_version())
        sb.addPermanentWidget(self._status_python)            # 右：Python 版本
        LogModel.instance().add_listener(self._update_status_counts)
        self._update_status_counts()

    def _update_status_counts(self) -> None:
        assert self._status_counts is not None
        m = LogModel.instance()
        err = sum(1 for e in m.entries
                  if e.level in (LogLevel.ERROR, LogLevel.CRITICAL))
        warn = sum(1 for e in m.entries if e.level == LogLevel.WARNING)
        self._status_counts.setText("错误: %d  警告: %d" % (err, warn))

    def _on_new(self) -> None:
        LogModel.instance().info("新建工程")
        self._open_package(KscpPackage.create_empty(), None)

    def _on_open(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "打开 .kscp", "", "KScript 工程 (*.kscp)")
        if path:
            self._open_file(path)

    def _open_file(self, path: str) -> None:
        try:
            pkg = KscpPackage.from_kscp(path)
        except Exception as e:  # 文件缺失/损坏等，统一提示并停在 landing
            QMessageBox.critical(self, "打开失败", "无法打开 %s：%s" % (path, e))
            LogModel.instance().error("打开失败：%s：%s" % (path, e))
            return
        LogModel.instance().info("打开工程：%s" % path)
        self._open_package(pkg, path)

    def _on_save(self) -> None:
        if self._package is None:
            return
        if not self._kscp_path:      # 尚无路径（新建工程）→ 同另存为：弹窗选路径
            self._on_save_as()
            return
        self._save_to(self._kscp_path)

    def _on_save_as(self) -> None:
        if self._package is None:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "另存为 .kscp", "", "KScript 工程 (*.kscp)")
        if not path:
            return
        self._save_to(path)

    def _save_to(self, path: str) -> None:
        """保存到指定路径：写盘 + 当前工程路径/标题更新（保存与另存为共用）。"""
        self._package.save(path)
        self._kscp_path = path
        self.setWindowTitle("KScript — %s" % path)
        sb = self.statusBar()
        assert sb is not None
        sb.showMessage("已保存：%s" % path, 3000)
        LogModel.instance().info("已保存：%s" % path)

    # ---- landing ----
    def _build_landing(self) -> QWidget:
        page = QWidget()
        lay = QHBoxLayout(page)
        lay.setContentsMargins(40, 40, 40, 40)
        lay.setSpacing(30)
        card_new = _LandingCard("新建", "创建一个空工程")
        card_new.clicked.connect(self._on_new)
        card_open = _LandingCard("打开", "打开一个 .kscp 文件")
        card_open.clicked.connect(self._on_open)
        lay.addStretch()
        lay.addWidget(card_new)
        lay.addWidget(card_open)
        lay.addStretch()
        return page

    # ---- project 视图 ----
    def _build_project_view(self) -> QWidget:
        sp = QSplitter()
        sp.setChildrenCollapsible(False)      # 防止拖到极小时栏「突然消失」

        # 切换栏（VSCode 风格图标条，无标题，悬停显示功能名）
        self._switcher = _ActivityBar()
        self._switcher.currentChanged.connect(self._on_switch)

        # 树栏（标题随当前管理树变化）
        self._tree_stack = QStackedWidget()
        self._tree_panel = _TitledPanel("资源树栏", self._tree_stack)
        self._tree_panel.setMinimumWidth(180)

        # 右栏：视图栏在上、日志栏在下（树栏右边、视图栏下边）
        self._preview_stack = QStackedWidget()
        preview_panel = _TitledPanel("视图栏", self._preview_stack)
        preview_panel.setMinimumWidth(200)
        self._log_widget = LogWidget()
        right = QSplitter(Qt.Vertical)
        right.setChildrenCollapsible(False)
        right.addWidget(preview_panel)
        right.addWidget(self._log_widget)
        right.setStretchFactor(0, 1)   # 视图栏吸收纵向
        right.setStretchFactor(1, 0)   # 日志栏高度稳定，仅手动拖动改变
        right.setSizes([540, 160])

        sp.addWidget(self._switcher)
        sp.addWidget(self._tree_panel)
        sp.addWidget(right)
        # 窗口缩放：切换栏固定、树栏宽度不变（stretch 0）、右栏吸收余量（stretch 1）
        sp.setStretchFactor(0, 0)
        sp.setStretchFactor(1, 0)
        sp.setStretchFactor(2, 1)
        sp.setSizes([56, 180, 700])
        return sp

    def _reset_project_view(self) -> None:
        """清空切换栏与两个栈，按当前 managers 重新填充。"""
        assert self._switcher is not None
        assert self._tree_stack is not None and self._preview_stack is not None
        self._switcher.clear()
        for _ in range(self._tree_stack.count()):
            self._tree_stack.removeWidget(self._tree_stack.widget(0))
        for _ in range(self._preview_stack.count()):
            self._preview_stack.removeWidget(self._preview_stack.widget(0))
        for m in self._managers:
            self._switcher.add_item(m.name, m.icon())
            self._tree_stack.addWidget(m.tree_widget())
            self._preview_stack.addWidget(m.preview_widget())

    def _on_switch(self, row: int) -> None:
        if row < 0:
            return
        assert self._tree_stack is not None and self._preview_stack is not None
        assert self._tree_panel is not None
        self._tree_stack.setCurrentIndex(row)
        self._preview_stack.setCurrentIndex(row)
        if row < len(self._managers):
            self._tree_panel.set_title("%s树栏" % self._managers[row].name)

    # ---- 打开工程 ----
    def _open_package(self, package: KscpPackage, path: Optional[str]) -> None:
        self._package = package
        self._kscp_path = path
        tree = self._load_shared_tree(package)
        # 模板工厂全局共享一份（步骤列表与步骤模板树共用）：
        # 各自 load 会打出两条「步骤模板加载完成」日志并重复加载。
        shared_mgr = StepManager(package, tree)
        shared_mgr.load()
        self._step_mgr = StepManagementTree(package, shared_mgr)
        # 左侧管理树排序（从上到下）：步骤列表 / 全局变量 / 步骤模板 / 资源
        self._managers = [
            StepListManagementTree(package, tree, shared_mgr),
            VariableManagementTree(package, tree),
            self._step_mgr,
            ResourceManagementTree(package),
        ]
        # 变量树变化 → 步骤卡片重检颜色（io 校验随变量树变）
        var_mgr = self._managers[1]
        sl_mgr = self._managers[0]
        assert isinstance(var_mgr, VariableManagementTree)
        assert isinstance(sl_mgr, StepListManagementTree)
        vtw = var_mgr.tree_widget()
        assert isinstance(vtw, VariableTreeWidget)
        vtw.tree_changed.connect(sl_mgr.refresh_cards)
        # 进入工程第一画面：store 非空 → 自动选中第一个步骤列表（显示序 DFS 首个列表）
        # 树/宿主均为懒构建 → 先构建再选中；宿主须在联动前构建，否则列表不显示
        sl_tree = sl_mgr.tree_widget()
        assert isinstance(sl_tree, StepListTreeWidget)
        sl_mgr.preview_widget()
        first_path = sl_tree.first_list_path()
        if first_path:
            item = sl_tree._find_item(first_path)
            if item is not None:
                sl_tree.setCurrentItem(item)   # 触发 list_selected → 宿主显示
        if self._manage_btn is not None:
            self._manage_btn.setEnabled(True)
        if self._project_widget is None:
            self._project_widget = self._build_project_view()
            self._central.addWidget(self._project_widget)
        self._reset_project_view()
        self._central.setCurrentWidget(self._project_widget)
        self.setWindowTitle("KScript — %s" % (path or "新工程"))
        if not self._project_sized:          # 首次进入工程视图：窗口 = 屏幕 2/3 并居中
            self.resize(*_window_size())
            screen = QApplication.primaryScreen()
            if screen is not None:
                g = screen.availableGeometry()
                self.move(g.left() + (g.width() - self.width()) // 2,
                          g.top() + (g.height() - self.height()) // 2)
            self._project_sized = True
        assert self._switcher is not None
        # 默认管理树 = 步骤列表管理树（_managers 第 1 位；进入工程即见步骤列表）
        self._switcher.set_current_row(0)

    @staticmethod
    def _load_shared_tree(package: KscpPackage) -> VariableTree:
        """加载一棵共享变量树（存在 variables.json → 读回；否则空树 + 写盘）。"""
        if package.exists("variables.json"):
            return VariableTree.from_json(
                package.read_file("variables.json"), package)
        tree = VariableTree.create_empty()
        package.write_file("variables.json", tree.to_json_bytes())
        return tree


# ================================================================
# 入口
# ================================================================
def main(path: Optional[str] = None, check: bool = False) -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setWindowIcon(QIcon(_ICON_PATH))          # 程序图标 → 所有窗口/弹窗继承
    app.setAttribute(Qt.AA_DisableWindowContextHelpButton, True)  # 弹窗右上角无「?」
    win = MainWindow(path)
    win.show()
    if check:
        QTimer.singleShot(800, app.quit)
    return app.exec_()


if __name__ == "__main__":
    import sys
    import tempfile

    from PyQt5.QtWidgets import QApplication

    from model.project_variable import ProjectVariable
    from model.step_list import StepList

    app = QApplication.instance() or QApplication(sys.argv)

    # 模板字节（有效模板；中文/引号内容一律用 .encode("utf-8")，禁用中文 bytes 字面量）
    GOOD = '''# -*- coding: utf-8 -*-
from dataclasses import dataclass
from actions.base import Step

@dataclass
class _DemoInput:
    count: "number" = 0

@dataclass
class _DemoOutput:
    total: "number" = 0

class DemoStep(Step):
    name = "示例"
    description = "测试模板"
    input_class = _DemoInput
    output_class = _DemoOutput

    def run(self) -> int:
        self.outputs.total = self.inputs.count * 2
        return 1
'''
    tmp = tempfile.mktemp(suffix=".kscp")
    pkg = KscpPackage.create_empty()
    pkg.write_file("actions/示例.py", GOOD.encode("utf-8"))
    tree = VariableTree.create_empty()
    tree.add("n1", ProjectVariable.create("number", 100, pkg))
    pkg.write_file("variables.json", tree.to_json_bytes())
    pkg.save(tmp)

    win = MainWindow(tmp)
    win.show()                       # 不 exec：构造期已同步构建全部控件

    # managers 结构：第 1 位 = StepListManagementTree（替换占位）
    assert len(win._managers) == 4
    sl_mgr = win._managers[0]
    assert isinstance(sl_mgr, StepListManagementTree)
    assert sl_mgr.name == "步骤列表"
    # 默认管理树 = 步骤列表管理树（切换栏第 1 位高亮）
    assert win._switcher is not None
    assert len(win._switcher._buttons) == 4
    assert win._switcher._buttons[0].isChecked()

    # 共享变量树：变量管理树与步骤列表管理树同树
    var_mgr = win._managers[1]
    assert isinstance(var_mgr, VariableManagementTree)
    vtw = var_mgr.tree_widget()
    assert isinstance(vtw, VariableTreeWidget)
    assert vtw._tree is sl_mgr._tree
    host = sl_mgr.preview_widget()
    assert isinstance(host, _StepListHost)
    assert isinstance(sl_mgr.tree_widget(), StepListTreeWidget)

    # 空 store → step_list.json 已写盘（镜像 variables.json 模式）
    assert win._package is not None
    assert win._package.exists("step_list.json")
    assert sl_mgr._store.paths() == []

    # 经 store API 添加列表 → 保存落盘（store 与包同实例）
    sl = StepList.create_empty()
    s = sl_mgr._mgr.create_step("示例")
    s.io.change_value("input", 0, "5")
    s.io.change_value("output", 0, "n1")
    sl.add(s)
    sl_mgr._store.add_list("主列表", sl)
    sl_mgr._save_store()
    raw = win._package.read_file("step_list.json")
    assert '"主列表"' in raw.decode("utf-8")

    # list_selected → 宿主视图出现卡片
    tw = sl_mgr.tree_widget()
    assert isinstance(tw, StepListTreeWidget)
    tw.refresh()                     # store 经 API 直改（950 行绕过树操作）→ 重建树含「主列表」
    tw.list_selected.emit("主列表")
    assert host.currentIndex() == 1
    assert len(host._view._cards) == 1

    # 变量 tree_changed → refresh_cards 不崩（已接线 host）
    vtw.tree_changed.emit()
    assert len(host._view._cards) == 1

    # 工具栏：跳转序号 / 搜索标签（host 组装存在 + 动作反馈文本）
    assert host._jump_edit is not None and host._search_edit is not None
    assert host._view._index_labels                        # 卡片正上方有序号标签
    host._jump_edit.setText("1")
    host._on_jump()
    assert host._toolbar_status.text() == "已定位 1/1"
    host._jump_edit.setText("9")
    host._on_jump()
    assert host._toolbar_status.text() == "序号越界（1-1）"
    host._search_edit.setText("xx")
    host._on_search()
    assert host._toolbar_status.text() == "未找到匹配标签"
    host._view._cards[0].step.tag = "主力"
    host._search_edit.setText("主力")
    host._on_search()
    assert host._toolbar_status.text() == "已定位"

    # 工具栏第二行：错误卡片数量（经 errors_changed 同步）+ 跳转错误
    assert host._error_count.text() == "错误卡片: 0"     # 卡片 io 有效
    host._view._cards[0].step.io.change_value("input", 0, "")
    host._view.refresh_validity()          # 输入字段 blockSignals → 显式重检发计数
    assert host._error_count.text() == "错误卡片: 1"
    # 错误数经 errors_changed 转发 → 左侧树条目红加粗（宿主联动）
    it_main = tw._find_item("主列表")
    assert it_main is not None
    assert it_main.font(0).bold()
    assert it_main.foreground(0).color() == QColor(200, 50, 40)
    host._on_jump_error()
    assert host._toolbar_status.text() == "已定位错误卡片"
    assert host._view._selected is host._view._cards[0]
    host._view._cards[0].step.io.change_value("input", 0, "5")
    host._view.refresh_validity()
    assert host._error_count.text() == "错误卡片: 0"
    assert not it_main.font(0).bold()      # 修复 → 树标记恢复默认
    host._on_jump_error()
    assert host._toolbar_status.text() == "无错误卡片"

    # 当前列表被删 → 宿主回占位页
    sl_mgr._store.remove("主列表")
    tw.store_changed.emit()
    assert host.currentIndex() == 0

    # ---- 含列表的工程 → 进入第一画面自动显示第一个步骤列表 ----
    tmp2 = tempfile.mktemp(suffix=".kscp")
    pkg2 = KscpPackage.create_empty()
    pkg2.write_file("actions/示例.py", GOOD.encode("utf-8"))
    tree2 = VariableTree.create_empty()
    tree2.add("n1", ProjectVariable.create("number", 100, pkg2))
    pkg2.write_file("variables.json", tree2.to_json_bytes())
    slm2 = StepListManagementTree(pkg2, tree2)         # 复用其 store/mgr 装配 step_list.json
    s2 = slm2._mgr.create_step("示例")
    s2.io.change_value("input", 0, "5")
    s2.io.change_value("output", 0, "n1")
    sl2 = StepList.create_empty()
    slm2._store.add_list("乙", sl2)                    # walk 序首位；空列表
    slm2._store.add_group("组甲")
    sl3 = StepList.create_empty()
    sl3.add(s2)
    slm2._store.add_list("组甲/丙", sl3)               # 显示序 DFS 第一个列表
    slm2._save_store()
    pkg2.save(tmp2)

    win2 = MainWindow(tmp2)
    win2.show()
    sl_mgr2 = win2._managers[0]
    assert isinstance(sl_mgr2, StepListManagementTree)
    tw2 = sl_mgr2.tree_widget()
    assert isinstance(tw2, StepListTreeWidget)
    assert tw2.first_list_path() == "乙"                # walk 序（= 显示序 = 执行序）首个列表
    host2 = sl_mgr2.preview_widget()
    assert isinstance(host2, _StepListHost)
    assert host2.currentIndex() == 1                    # 非占位：自动切到列表视图
    assert len(host2._view._cards) == 0                 # 「乙」为空列表 → 无卡片
    assert sl_mgr2._current == "乙"                     # 树中选中项 = 第一个列表
    assert host2._view._step_list is sl_mgr2._store.get("乙")

    # ---- 需求：激活切换双向立刻刷新（树勾选 → 卡片；卡片按钮 → 树勾选框） ----
    it2 = tw2._find_item("组甲/丙")
    assert it2 is not None
    tw2.setCurrentItem(it2)                      # 切到含步骤 s2 的列表
    assert sl_mgr2._current == "组甲/丙"
    assert host2._view._step_list is sl_mgr2._store.get("组甲/丙")
    card2 = host2._view._cards[0]
    assert card2.step is sl_mgr2._store.get("组甲/丙").steps[0]
    assert card2.property("active") is True
    it2.setCheckState(0, Qt.Unchecked)           # 树勾选框：停用列表内全部步骤
    assert host2._view._cards[0].step.enabled is False
    card2 = host2._view._cards[0]                # 宿主重建后的新卡片
    assert card2.property("active") is False     # 卡片画面立刻刷新
    card2._btn_active.setChecked(True)
    card2._on_active_toggled(True)               # 卡片激活按钮 → 树勾选框同步
    assert card2.step.enabled is True
    assert it2.checkState(0) == Qt.Checked
    # 保存链路：卡片激活切换 → view.edited → 宿主保存
    edited_calls = []
    host2._view.edited.connect(lambda: edited_calls.append(1))
    card2._btn_active.setChecked(False)
    card2._on_active_toggled(False)
    assert edited_calls == [1], edited_calls
    assert card2.property("active") is False
    card2._on_active_toggled(True)               # 复位，不影响后续用例

    # 程序窗口 = 当前屏幕可用区 2/3（用户需求：2/3 显示器宽高）
    win_w, win_h = _window_size()
    assert win.width() == win_w and win.height() == win_h

    # 程序图标：icon/kscript.ico 存在且可加载（应用到所有窗口/弹窗）
    assert os.path.exists(_ICON_PATH)
    assert not QIcon(_ICON_PATH).isNull()
    # 弹窗右上角无「?」按钮：全局属性存在（main() 中启用）
    assert hasattr(Qt, "AA_DisableWindowContextHelpButton")

    # ---- 文件菜单：新建/打开/保存/另存为 合并到「文件」下拉（带快捷键） ----
    file_btns = [b for b in win.findChildren(QToolButton) if b.text() == "文件"]
    assert len(file_btns) == 1, file_btns
    fm = file_btns[0].menu()
    assert fm is not None
    ftexts = [a.text() for a in fm.actions() if not a.isSeparator()]
    assert ftexts == ["新建", "打开…", "保存", "另存为…"], ftexts
    a_map = {a.text(): a for a in fm.actions()}
    assert a_map["新建"].shortcut().toString() == "Ctrl+N"
    assert a_map["打开…"].shortcut().toString() == "Ctrl+O"
    assert a_map["保存"].shortcut().toString() == "Ctrl+S"
    assert a_map["另存为…"].shortcut().toString() == "Ctrl+Shift+S"

    # 另存为：总是弹路径框 → 写新文件 + 当前路径/标题切换（原文件不受影响）
    tmp3 = tempfile.mktemp(suffix=".kscp")
    orig_gsf = QFileDialog.getSaveFileName
    QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (tmp3, ""))
    try:
        win2._on_save_as()                       # win2 已打开 tmp2
    finally:
        QFileDialog.getSaveFileName = orig_gsf
    assert os.path.exists(tmp3)                  # 新文件已写出
    assert win2._kscp_path == tmp3               # 当前工程路径切到新文件
    assert win2.windowTitle() == "KScript — %s" % tmp3
    assert os.path.exists(tmp2)                  # 原文件未被改动
    # 另存为后保存：有路径 → 直接写新路径，不再弹窗
    calls = []
    QFileDialog.getSaveFileName = staticmethod(
        lambda *a, **k: calls.append(1) or ("", ""))
    try:
        win2._on_save()
    finally:
        QFileDialog.getSaveFileName = orig_gsf
    assert calls == []

    print("MainWindow smoke OK")
