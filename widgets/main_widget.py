# -*- coding: utf-8 -*-
"""
主窗口（入口）
============

:class:`MainWindow` 是 KScript 的主窗口。无工程时显示「新建 / 打开」两个大卡片；
打开 ``.kscp`` 后，左侧是管理树切换栏 + 当前管理树，中间是当前管理树的大预览。

界面组件按职责拆分：管理树簇见 :mod:`widgets.树.management_trees`，活动栏见
:mod:`widgets.通用.activity_bar`，设置弹窗见 :mod:`widgets.通用.settings_dialog`，
通用小件（图标/窗口尺寸/落地卡片/标题面板/占位）见 :mod:`widgets.通用.ui_common`。
本模块保留主窗口本体 + 执行器接线 + 程序入口。

启动::

    python main.py                # landing：新建 / 打开
    python main.py xxx.kscp       # 直接打开
    python main.py --check        # 自检（渲染后自动退出）
"""

from __future__ import annotations

import json
import os
import platform
import sys
from typing import Callable, Dict, List, Optional, Tuple

from PyQt5.QtCore import QObject, Qt, QSize, QTimer, pyqtSignal
from PyQt5.QtGui import QColor, QIcon
from PyQt5.QtWidgets import (
    QApplication, QDialog, QFileDialog, QHBoxLayout, QLabel,
    QMainWindow, QMenu, QMessageBox, QSplitter, QStackedWidget, QToolButton,
    QWidget,
)

from model.执行.hotkey import HotkeyListener, normalize_hotkey, parse_hotkey
from model.工程.kscp_package import KscpPackage
from model.log_model import LogLevel, LogModel
from model.步骤.step import StepStatus
from model.步骤.step_manager import StepManager
from model.执行.step_runner import StepRunner, StepRunnerState
from model.变量.variable_tree import VariableTree
from model.合成卡片.composite_card import CompositeCard
from model.合成卡片.composite_card_store import CompositeCardStore
from model.合成卡片.placeholder_step import PlaceholderStep
from widgets.通用.log_widget import LogWidget
from widgets.树.step_list_tree_widget import StepListTreeWidget
from widgets.树.step_tree_widget import StepInfoPanel, StepTreeWidget
from widgets.树.variable_tree_widget import VariableTreeWidget
from widgets.通用.activity_bar import ActivityBar
from widgets.树.management_trees import (
    ManagementTree, ResourceManagementTree, StepListHost,
    StepListManagementTree, StepManagementTree, VariableManagementTree,
    CompositeManagementTree,
)
from widgets.卡片.step_list_view import StepClipboard
from widgets.通用.settings_dialog import SettingsDialog
from widgets.通用.ui_common import (
    LandingCard, TitledPanel, ensure_qt_plugin_path, make_icon, window_size,
)

__all__ = ["MainWindow", "main"]


# 程序图标路径（main() 应用）
_ICON_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "icon", "kscript.ico")


class _ExecBridge(QObject):
    """执行器跨线程桥：工作线程 emit → Qt queued 到 GUI 线程刷新。"""
    runner_state = pyqtSignal(object)     # (page, gen, state)：页+代际标记防陈旧覆盖
    hotkey_toggle = pyqtSignal(str)       # page：某页热键按下（监听回调闭包携带页名）
    log_changed = pyqtSignal()            # LogModel 变更（worker 线程记日志）→ GUI 线程刷计数
    step_status = pyqtSignal(object)      # (page, step)：步骤状态变更 → 卡片颜色/树高亮
    progress = pyqtSignal(object)         # (page, 第几步, 总数)：执行进度 → 状态栏


# 模拟注入点：冒烟测试替换以避开真实热键/线程（与 picker 包装同思路）
def _make_step_runner(store, only_path=None, stop_mode="after_step"):
    return StepRunner(store, only_path, stop_mode)


def _make_hotkey_listener(hotkey, on_toggle, defer_lone_modifier=False):
    return HotkeyListener(hotkey, on_toggle, defer_lone_modifier)


def _lone_mod_deferred(hotkey: str, all_hotkeys: List[str]) -> bool:
    """单独修饰键热键是否存在前缀冲突 → 是否延迟到释放判定（组合优先）。

    仅当本热键是单独修饰键（Ctrl/Alt/Shift/Cmd），且**其他**热键中存在
    含该修饰键的非修饰键热键（如 Ctrl+Alt+I）时返回 True。
    """
    try:
        mods, target = parse_hotkey(hotkey)
    except ValueError:
        return False
    if target not in {"key:ctrl", "key:alt", "key:shift", "key:cmd"}:
        return False
    for other in all_hotkeys:
        if other == hotkey:
            continue
        try:
            omods, otarget = parse_hotkey(other)
        except ValueError:
            continue
        if otarget not in {"key:ctrl", "key:alt", "key:shift", "key:cmd"} \
                and target in omods:
            return True
    return False


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
        self._runners: Dict[str, StepRunner] = {}            # 页名 → 执行器（READY 后保留复用）
        self._runner_gens: Dict[str, int] = {}               # 页名 → 代际（陈旧状态过滤）
        self._hotkey_listeners: Dict[str, HotkeyListener] = {}   # 页名 → 常驻热键监听器
        self._exec_btn: Optional[QToolButton] = None       # 活动栏底部「执行」按钮
        self._settings_btn: Optional[QToolButton] = None   # 活动栏底部「设置」按钮
        self._exec_status: Optional[QLabel] = None
        self._exec_bridge = _ExecBridge()
        self._exec_bridge.runner_state.connect(self._on_runner_state)
        self._exec_bridge.hotkey_toggle.connect(self._handle_hotkey_toggle)
        self._exec_bridge.log_changed.connect(self._update_status_counts)
        self._exec_bridge.step_status.connect(self._on_step_status)
        self._exec_bridge.progress.connect(self._on_progress)
        self._exec_locked = False
        self._exec_scope = "all"     # 执行范围（仅作用于当前页）：all=全部列表 / current=仅当前列表
        self._sl_error_count = 0     # 当前步骤列表视图的错误/占位卡片数（>0 → 禁止执行）
        self._current_page = ""      # 当前执行列表页（sl_mgr 页信号驱动）
        self._armed = False   # 全部页待命开关（执行按钮切换；未待命所有页热键忽略）
        self._step_hooks: Dict[str, List[Tuple[object, Callable]]] = {}   # 页名 → 步骤状态监听
        self._step_paths: Dict[str, Dict[object, str]] = {}   # 页名 → step→列表路径（树高亮）

        self._central = QStackedWidget()
        self.setCentralWidget(self._central)
        self._central.addWidget(self._build_landing())    # page 0
        self._project_widget: Optional[QWidget] = None
        self._switcher: Optional[ActivityBar] = None
        self._tree_stack: Optional[QStackedWidget] = None
        self._preview_stack: Optional[QStackedWidget] = None
        self._tree_panel: Optional[TitledPanel] = None

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
        file_btn.setToolButtonStyle(Qt.ToolButtonTextOnly)   # 无图标占位，防文本被压缩截断
        file_btn.setMinimumWidth(self.fontMetrics().horizontalAdvance("文件") + 16)
        file_btn.setPopupMode(QToolButton.InstantPopup)
        file_menu = QMenu(file_btn)
        self._a_new = file_menu.addAction("新建")
        self._a_new.setShortcut("Ctrl+N")
        self._a_new.triggered.connect(self._on_new)
        self._a_open = file_menu.addAction("打开…")
        self._a_open.setShortcut("Ctrl+O")
        self._a_open.triggered.connect(self._on_open)
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
        self._manage_btn.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self._manage_btn.setMinimumWidth(self.fontMetrics().horizontalAdvance("管理") + 16)
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
        win_btn.setToolButtonStyle(Qt.ToolButtonTextOnly)
        win_btn.setMinimumWidth(self.fontMetrics().horizontalAdvance("窗口") + 16)
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
        # 经桥监听：worker 线程记日志 → queued 到 GUI 线程刷计数（不直接操作 QLabel）
        LogModel.instance().add_listener(self._exec_bridge.log_changed.emit)
        self._update_status_counts()
        self._exec_status = QLabel("")
        sb.addPermanentWidget(self._exec_status)

    def _update_status_counts(self) -> None:
        assert self._status_counts is not None
        m = LogModel.instance()
        err = sum(1 for e in m.entries
                  if e.level in (LogLevel.ERROR, LogLevel.CRITICAL))
        warn = sum(1 for e in m.entries if e.level == LogLevel.WARNING)
        self._status_counts.setText("错误: %d  警告: %d" % (err, warn))

    # ---- 页热键监听（常驻：工程打开即生效） ----
    def _start_page_listeners(self) -> None:
        """为每个配置了热键的页建常驻监听器（每热键一个 pynput 监听线程）。"""
        self._stop_page_listeners()
        if not self._managers or self._package is None:
            return
        sl_mgr = self._managers[0]
        assert isinstance(sl_mgr, StepListManagementTree)
        hotkeys = self._page_hotkeys()
        all_hks = [v for v in hotkeys.values() if v]
        for page in sl_mgr.page_store.page_names():
            hk = hotkeys.get(page, "")
            if hk:
                # 单独修饰键（Ctrl）与含该修饰键的组合（Ctrl+Alt+I）并存 →
                # 组合优先：修饰键热键延迟到释放判定
                self._hotkey_listeners[page] = _make_hotkey_listener(
                    hk, lambda p=page: self._exec_bridge.hotkey_toggle.emit(p),
                    _lone_mod_deferred(hk, all_hks))
                self._hotkey_listeners[page].start()
        LogModel.instance().info(
            "执行列表热键监听已启动：%s"
            % ("、".join(sorted(self._hotkey_listeners)) or "（无）"))

    def _stop_page_listeners(self) -> None:
        for lst in self._hotkey_listeners.values():
            lst.stop()
        self._hotkey_listeners.clear()

    # ---- 执行器接线 ----
    def _on_exec_clicked(self) -> None:
        """执行按钮：**全部页待命开关**——点击后所有页开始监听各自热键
        （按钮绿），再点关闭（执行中的页同时请求停止）。不会直接执行步骤。"""
        if self._package is None:
            return
        if self._armed:
            self._armed = False
            for runner in self._runners.values():
                if runner.state is not StepRunnerState.READY:
                    runner.request_stop()  # 关闭待命同时停止执行（旧「停监听」语义）
            LogModel.instance().info("已关闭待命：全部页热键停止监听")
        else:
            self._armed = True
            LogModel.instance().info("已进入待命：全部页热键监听中（按各自热键执行/停止）")
        self._refresh_exec_status()
        self._update_exec_button()

    def _handle_hotkey_toggle(self, page: str) -> None:
        """某页热键按下（GUI 线程，经桥 queued）：仅待命中生效——
        READY → start；RUNNING/STOPPING → request_stop。"""
        if not self._managers:
            return
        sl_mgr = self._managers[0]
        if not isinstance(sl_mgr, StepListManagementTree):
            return
        if page not in sl_mgr.page_store.page_names():
            return                     # 悬空热键（页已删）防御
        if not self._armed:
            return                     # 未待命：全部页热键忽略
        runner = self._runners.get(page)
        if runner is not None and runner.state is not StepRunnerState.READY:
            runner.request_stop()      # toggle：执行中再按 = 停止
            return
        # 安全网：该页含错误/占位卡片 → 禁止执行（按钮禁用是主防线，此处兜底热键直触）
        if self._exec_has_errors(page):
            LogModel.instance().error(
                "禁止执行：页「%s」含错误/占位卡片，请先修正或删除后再执行" % page)
            self._set_exec_status("禁止执行：页「%s」含错误/占位卡片" % page)
            return
        only = None
        if self._exec_scope == "current" and page == self._current_page:
            only = sl_mgr.current_path   # 「仅执行当前列表」只作用于当前页
        runner = _make_step_runner(
            sl_mgr.page_store.get_page(page), only, self._current_stop_mode())
        self._runners[page] = runner
        gen = self._runner_gens.get(page, 0) + 1
        self._runner_gens[page] = gen
        runner.add_state_listener(
            lambda st, g=gen, p=page: self._exec_bridge.runner_state.emit((p, g, st)))
        runner.add_progress_listener(
            lambda i, n, p=page: self._exec_bridge.progress.emit((p, i, n)))
        self._attach_step_hooks(page)   # 执行前挂该页卡片状态监听
        runner.start()
        LogModel.instance().info("执行列表「%s」开始执行" % page)

    def _exec_has_errors(self, page: Optional[str] = None) -> bool:
        """待执行页（默认当前页）按执行范围是否含错误/占位卡片。

        占位卡片（:class:`PlaceholderStep`，模板缺失/签名不匹配）与 io 非法卡
        均视为不可执行。按钮禁用是主防线（随当前视图错误数变化）；本方法在
        热键触发执行前按**执行范围**兜底扫描，闭合「待命后引入错误」的缺口。
        """
        if not self._managers:
            return False
        sl_mgr = self._managers[0]
        if not isinstance(sl_mgr, StepListManagementTree):
            return False
        page = page or self._current_page
        if page not in sl_mgr.page_store.page_names():
            return False
        store = sl_mgr.page_store.get_page(page)
        if self._exec_scope == "current" and page == self._current_page \
                and sl_mgr.current_path:
            paths = [sl_mgr.current_path]
        else:
            paths = [p for p, is_group in store.walk() if not is_group]
        for p in paths:
            try:
                sl = store.get(p)
            except FileNotFoundError:
                continue
            for s in sl.steps:
                if isinstance(s, PlaceholderStep) or not s.io.is_valid:
                    return True
        return False

    def _on_runner_state(self, payload) -> None:
        """执行器状态变化（GUI 线程）：状态栏 + 编辑锁定（活跃重算）+ 挂钩清理。"""
        page, gen, st = payload
        if self._runner_gens.get(page) != gen:
            return                      # 陈旧 runner（已重建）的迟到状态 → 忽略
        if st is StepRunnerState.RUNNING:
            self._recompute_lock()
        elif st is StepRunnerState.STOPPING:
            pass
        else:                           # READY：只摘该页 hooks
            self._detach_step_hooks(page)
            self._recompute_lock()
        self._refresh_exec_status()

    def _recompute_lock(self) -> None:
        """按活跃执行器集合重算 UI 锁定（任一页非 READY → 锁定；不用加减计数防漏算）。"""
        active = any(r.state is not StepRunnerState.READY
                     for r in self._runners.values())
        self._set_exec_locked(active)
        self._update_exec_button()

    def _refresh_exec_status(self) -> None:
        """状态栏：当前页状态（待命开关/执行中/停止中）+ 后台页执行中提示。"""
        if self._exec_status is None:
            return
        page = self._current_page
        runner = self._runners.get(page)
        hk = self._page_hotkeys().get(page, "")
        armed = self._armed
        if runner is not None and runner.state is StepRunnerState.RUNNING:
            text = ("执行中……（页「%s」按 %s 停止）" % (page, hk)
                    if hk else "执行中……（点执行按钮停止）")
        elif runner is not None and runner.state is StepRunnerState.STOPPING:
            text = "停止中……（%s）" % self._stop_hint()
        elif armed:
            text = ("待命：全部页热键生效（页「%s」按 %s 执行/停止）" % (page, hk)
                    if hk else "待命：全部页热键生效（页「%s」未绑定热键）" % page)
        else:
            text = ("未待命：点执行按钮开启全部页热键（页「%s」热键 %s）" % (page, hk)
                    if hk else "页「%s」未绑定热键：请在设置中绑定后按热键执行" % page)
        others = sum(1 for p, r in self._runners.items()
                     if p != page and r.state is not StepRunnerState.READY)
        if others:
            text += "｜另 %d 页执行中" % others
        self._set_exec_status(text)

    # ---- 执行期卡片状态刷新（spec §6 组件 6）：步骤状态 → 桥 → 重检卡片颜色 ----
    def _attach_step_hooks(self, page: str) -> None:
        """执行前：为该页 store 全部步骤挂状态监听（该页卡片颜色/树高亮随执行刷新）。"""
        self._detach_step_hooks(page)          # 幂等：先清旧钩再挂新钩
        self._step_paths[page] = {}
        if not self._managers:
            return
        sl_mgr = self._managers[0]
        if not isinstance(sl_mgr, StepListManagementTree):
            return
        store = sl_mgr.page_store.get_page(page)
        for path, is_group in store.walk():
            if is_group:
                continue
            for step in store.get(path).steps:
                self._step_paths[page][step] = path
                cb = lambda s, _st, p=page: self._exec_bridge.step_status.emit((p, s))
                step.add_status_listener(cb)
                self._step_hooks.setdefault(page, []).append((step, cb))

    def _detach_step_hooks(self, page: str) -> None:
        """该页执行结束：移除该页步骤状态监听并清空；当前页 → 清树高亮。"""
        for step, cb in self._step_hooks.pop(page, []):
            step.remove_status_listener(cb)
        self._step_paths.pop(page, None)
        if page == self._current_page:
            self._clear_running_highlight()

    def _clear_running_highlight(self) -> None:
        """清除步骤列表树的执行高亮（▶ 前缀/蓝色）。"""
        if not self._managers:
            return
        m0 = self._managers[0]
        if isinstance(m0, StepListManagementTree):
            for t in m0.trees():
                t.set_running_path(None)

    def _on_step_status(self, payload) -> None:
        """步骤状态变化（GUI 线程，经桥 queued）：该页卡片重检颜色 + 树高亮执行中列表。"""
        page, step = payload
        if not self._managers:
            return
        m0 = self._managers[0]
        if not isinstance(m0, StepListManagementTree):
            return
        if page != self._current_page:
            return                     # 后台页状态不刷宿主（宿主只显示当前页）
        m0.refresh_cards()
        t = m0.current_tree()
        if t is not None:
            # 找当前 RUNNING 的步骤 → 高亮其列表；无则清高亮
            running = None
            for s, path in self._step_paths.get(page, {}).items():
                if s.status is StepStatus.RUNNING:
                    running = path
                    break
            t.set_running_path(running)

    def _on_progress(self, payload) -> None:
        """执行进度（GUI 线程，经桥 queued）：当前页执行中 → 状态栏「执行中 i/n」。"""
        page, i, n = payload
        if page != self._current_page:
            return
        runner = self._runners.get(page)
        if runner is not None and runner.state is StepRunnerState.RUNNING:
            self._set_exec_status("执行中 %d/%d……（按热键停止）" % (i, n))

    def _rebuild_runner(self, page: str) -> None:
        """该页 runner 待命时按当前范围重建（状态/进度监听重挂）。

        执行范围切换（全部页）、或「仅执行当前列表」下当前页选中列表变化时调用。
        """
        if not self._managers:
            return
        runner = self._runners.get(page)
        if runner is None or runner.state is not StepRunnerState.READY:
            return
        sl_mgr = self._managers[0]
        assert isinstance(sl_mgr, StepListManagementTree)
        only = sl_mgr.current_path \
            if (self._exec_scope == "current" and page == self._current_page) else None
        self._runners[page] = _make_step_runner(
            sl_mgr.page_store.get_page(page), only, self._current_stop_mode())
        gen = self._runner_gens.get(page, 0)   # 重建复用当前代际
        self._runners[page].add_state_listener(
            lambda st, g=gen, p=page: self._exec_bridge.runner_state.emit((p, g, st)))
        self._runners[page].add_progress_listener(
            lambda i, n, p=page: self._exec_bridge.progress.emit((p, i, n)))

    def _set_exec_status(self, text: str) -> None:
        if self._exec_status is not None:
            self._exec_status.setText(text)

    # ---- 页联动（sl_mgr 页信号） ----
    def _on_page_changed(self, page: str) -> None:
        """页切换：跟随当前页 + 刷新状态栏/按钮；scope=current 时重建该页 runner。"""
        self._current_page = page
        if self._exec_scope == "current":
            self._rebuild_runner(page)
        self._refresh_exec_status()
        self._update_exec_button()

    def _on_page_added(self, page: str) -> None:
        """新增页：按 executor.json 映射为其建常驻监听（无热键则跳过）。"""
        hotkeys = self._page_hotkeys()
        hk = hotkeys.get(page, "")
        if hk:
            self._hotkey_listeners[page] = _make_hotkey_listener(
                hk, lambda p=page: self._exec_bridge.hotkey_toggle.emit(p),
                _lone_mod_deferred(hk, [v for v in hotkeys.values() if v]))
            self._hotkey_listeners[page].start()
        self._update_exec_button()

    def _on_page_renamed(self, old: str, new: str) -> None:
        """页重命名：五个按页字典重键（热键映射跟随页名不变）。"""
        for d in (self._runners, self._runner_gens, self._hotkey_listeners,
                  self._step_hooks, self._step_paths):
            if old in d:
                d[new] = d.pop(old)
        if self._current_page == old:
            self._current_page = new
        self._refresh_exec_status()
        self._update_exec_button()

    def _on_page_removed(self, page: str) -> None:
        """删除页：停其监听器、摘钩、清理字典（防悬空热键回调）。"""
        lst = self._hotkey_listeners.pop(page, None)
        if lst is not None:
            lst.stop()
        self._detach_step_hooks(page)
        for d in (self._runners, self._runner_gens):
            d.pop(page, None)
        self._recompute_lock()
        self._refresh_exec_status()
        self._update_exec_button()

    # ---- 执行/设置按钮（活动栏底部） ----
    def _update_exec_button(self) -> None:
        """执行按钮视觉态：全部页待命 → 绿色 checked；未待命 → 复原。

        启用态：执行中（``_exec_locked``，保留关闭待命/停止通道）或当前步骤列表
        无错误/占位卡片时可用；**有错误/占位卡片时禁用**（无法还原或 io 非法的
        步骤禁止执行）。
        """
        if self._exec_btn is None:
            return
        scope_text = "全部列表" if self._exec_scope == "all" else "当前列表"
        armed = self._armed
        self._exec_btn.setChecked(armed)
        # 执行中保留停止通道；否则仅当当前视图无错误/占位卡片时可用
        self._exec_btn.setEnabled(self._exec_locked or self._sl_error_count == 0)
        hk = self._page_hotkeys().get(self._current_page, "")
        if armed:
            self._exec_btn.setToolTip(
                "关闭待命：全部页热键停止监听（执行中的页会同时停止）")
        elif self._sl_error_count > 0:
            self._exec_btn.setToolTip(
                "当前列表有 %d 张错误/占位卡片，禁止执行（修正或删除后即可执行）"
                % self._sl_error_count)
        else:
            self._exec_btn.setToolTip(
                "进入待命（范围：%s，右键切换）：点击后按钮变绿，**全部页**"
                "开始监听各自热键——按该页热键执行、再按停止（%s）。\n"
                "热键勿与步骤按键冲突（模拟按键也会被监听）；"
                "模拟输入到游戏窗口需管理员运行。"
                % (scope_text, self._stop_hint()))

    # ---- 执行范围（全部列表 / 仅当前列表；右键执行按钮切换） ----
    def _on_sl_errors_changed(self, n: int) -> None:
        """当前步骤列表视图错误/占位卡片数变化 → 更新执行按钮启用态。

        ``n > 0``（有 io 非法卡或占位卡）→ 禁止执行（按钮禁用，除非执行中）；
        ``n == 0`` → 恢复可用。占位卡（模板缺失/签名不匹配）与 io 非法卡同等
        计入（见 :meth:`StepListView.error_card_indices`）。
        """
        self._sl_error_count = n
        self._update_exec_button()

    def _on_exec_menu(self, pos) -> None:
        menu = QMenu(self._exec_btn)
        a_all = menu.addAction("执行全部列表")
        a_all.setCheckable(True)
        a_cur = menu.addAction("仅执行当前列表")
        a_cur.setCheckable(True)
        (a_all if self._exec_scope == "all" else a_cur).setChecked(True)
        a = menu.exec_(self._exec_btn.mapToGlobal(pos))
        if a is a_all:
            self._set_exec_scope("all")
        elif a is a_cur:
            self._set_exec_scope("current")

    def _set_exec_scope(self, scope: str) -> None:
        """切换执行范围（作用于当前页）；全部页 READY 的 runner 立即重建，
        执行中的下次待命生效。"""
        if scope == self._exec_scope:
            return
        self._exec_scope = scope
        for page in list(self._runners):
            self._rebuild_runner(page)
        self._update_exec_button()
        LogModel.instance().info(
            "执行范围已设为：%s"
            % ("全部列表" if scope == "all" else "仅当前列表"))

    def _on_exec_list_changed(self, _path: str) -> None:
        """当前页选中列表变化：仅执行当前列表且该页待命 → runner 跟随新列表。"""
        if self._exec_scope == "current":
            self._rebuild_runner(self._current_page)

    def _on_settings_clicked(self) -> None:
        """打开设置弹窗（各页热键表格 + 停止方式）；保存 → .kscp/executor.json。"""
        if self._package is None:
            return
        sl_mgr = self._managers[0]
        assert isinstance(sl_mgr, StepListManagementTree)
        dlg = SettingsDialog(
            sl_mgr.page_store.page_names(), self._page_hotkeys(),
            self._current_stop_mode(), self)
        if dlg.exec_() != QDialog.Accepted:
            return
        self._apply_settings(dlg.hotkeys(), dlg.stop_mode())

    def _page_hotkeys(self) -> Dict[str, str]:
        """当前各页热键映射（页名 → 规范化热键规格或空串）。

        executor.json v2 读 ``pages``；旧格式（无 pages）→ 顶层 ``hotkey``
        归第一页、其余页空；文件缺失/损坏 → 第一页默认 `` ` ``（旧单页 UX），
        其余页空。未知页忽略；非法值（不可解析）按空处理。取值经
        :func:`model.执行.hotkey.normalize_hotkey` 规范化（单字符/命名键/
        组合/单独修饰键均支持）。
        """
        result: Dict[str, str] = {}
        if not self._managers:
            return result
        sl_mgr = self._managers[0]
        if not isinstance(sl_mgr, StepListManagementTree):
            return result
        pages = sl_mgr.page_store.page_names()
        if not pages:
            return result
        data = None
        if self._package is not None and self._package.exists("executor.json"):
            try:
                data = json.loads(
                    self._package.read_file("executor.json").decode("utf-8"))
                if not isinstance(data, dict):
                    data = None
            except (ValueError, UnicodeDecodeError):
                data = None
            if data is None:
                LogModel.instance().warning("executor.json 无法读取，使用默认热键")
        if data is not None and isinstance(data.get("pages"), dict):
            for p in pages:
                hk = data["pages"].get(p)
                result[p] = normalize_hotkey(hk) \
                    if isinstance(hk, str) and normalize_hotkey(hk) else ""
        else:
            # 旧格式（无 pages）：顶层 hotkey 归第一页，其余页空；非法/缺失 → 默认 "`"
            legacy = normalize_hotkey(data.get("hotkey")) \
                if data is not None else None
            first = legacy or "`"
            for i, p in enumerate(pages):
                result[p] = first if i == 0 else ""
        if data is None:
            result[pages[0]] = "`"
        return result

    def _current_stop_mode(self) -> str:
        """当前停止方式：executor.json 的 stop_mode（immediate/after_step）。

        缺失/非法 → 默认 ``after_step``（旧工程 executor.json 无该字段，
        静默回退不打扰；显式非法值才告警）。
        """
        if self._package is not None and self._package.exists("executor.json"):
            try:
                data = json.loads(
                    self._package.read_file("executor.json").decode("utf-8"))
                if isinstance(data, dict):
                    mode = data.get("stop_mode", "after_step")
                    if mode in ("immediate", "after_step"):
                        return mode
                    LogModel.instance().warning(
                        "executor.json 停止方式非法，使用默认（当前步骤结束后停止）")
            except (ValueError, UnicodeDecodeError):
                LogModel.instance().warning(
                    "executor.json 无法读取，使用默认停止方式")
        return "after_step"

    def _stop_hint(self) -> str:
        """停止方式提示文案（状态栏/按钮 tooltip 共用）。"""
        if self._current_stop_mode() == "immediate":
            return "立即停止"
        return "当前步骤结束后停止"

    def _apply_settings(self, hotkeys: Dict[str, str], stop_mode: str) -> None:
        """保存各页热键 + 停止方式到工程包 executor.json（有路径立即落盘 .kscp）。

        不写 setting.json（executor.json 为唯一来源）。保存后按新映射重建
        全部页常驻监听（空热键页不建监听）；各页 READY 执行器按新停止方式
        重建（立即生效；执行中下次待命生效）。
        """
        mode = "immediate" if stop_mode == "immediate" else "after_step"
        pages_map: Dict[str, str] = {}
        if self._managers:
            sl_mgr = self._managers[0]
            if isinstance(sl_mgr, StepListManagementTree):
                pages_map = {p: hotkeys.get(p, "")
                             for p in sl_mgr.page_store.page_names()}
        if self._package is not None:
            first = next(iter(pages_map), None)
            legacy = pages_map.get(first, "") if first else ""
            self._package.write_file(
                "executor.json",
                json.dumps({"hotkey": legacy or "`", "stop_mode": mode,
                            "pages": pages_map},
                           ensure_ascii=False).encode("utf-8"))
            if self._kscp_path:
                try:
                    self._package.save(self._kscp_path)
                except OSError as e:
                    QMessageBox.warning(self, "设置", "工程文件保存失败：%s" % e)
                    LogModel.instance().error("设置保存到 .kscp 失败：%s" % e)
        # 按新映射重建全部常驻监听（旧监听器销毁）
        self._start_page_listeners()
        # 各页待命执行器按新停止方式重建
        for page in list(self._runners):
            if self._runners[page].state is StepRunnerState.READY:
                self._rebuild_runner(page)
        self._refresh_exec_status()
        self._update_exec_button()
        LogModel.instance().info(
            "执行设置已更新：%d 页热键，停止方式 %s" % (len(pages_map), mode))

    def _set_exec_locked(self, locked: bool) -> None:
        """执行期间锁定所有影响执行器的 GUI 编辑入口：

        * 步骤列表树 + 卡片视图 → **只读模式**：条目仍可点击切换查看列表、
          卡片悬停缩放动画保留，但拖拽/右键/Del/勾选/卡片编辑全禁
        * 变量/模板/资源树与其预览 → 整树禁用（无查看需求）
        * 管理菜单（导入模板）、文件菜单新建/打开（换工程）、设置按钮（改热键/停止方式）禁用
        * 执行按钮保留（停止通道）；日志面板与保存只读无害不锁
        """
        if self._exec_locked == locked:
            return
        self._exec_locked = locked
        enabled = not locked
        for m in self._managers:
            if isinstance(m, (StepListManagementTree, CompositeManagementTree)):
                m.set_read_only(locked)
                continue
            # 已构建的树/预览才需要处理（懒构建：未构建的不会出现在屏幕）
            tw = getattr(m, "_vtree", None) or getattr(m, "_stree", None) \
                or getattr(m, "_rtree", None)
            if tw is not None:
                tw.setEnabled(enabled)
            pw = getattr(m, "_preview", None)
            if pw is not None:
                pw.setEnabled(enabled)
        if self._manage_btn is not None:
            # 管理按钮基础态 = 已开包才可用；解锁时不能把它错误启用（未开包场景）
            self._manage_btn.setEnabled(enabled and self._package is not None)
        if self._settings_btn is not None:
            self._settings_btn.setEnabled(enabled)
        for a in (getattr(self, "_a_new", None), getattr(self, "_a_open", None)):
            if a is not None:
                a.setEnabled(enabled)
        # 执行按钮：执行中保留（停止通道）；解锁后按当前错误/占位卡片数重评启用态
        self._update_exec_button()

    def _on_new(self) -> None:
        LogModel.instance().info("新建工程")
        self._open_package(KscpPackage.create_empty(), None)

    def _on_add_template(self, path: str) -> None:
        """模板信息面板「加入当前列表」→ 实例化并追加到当前选中的步骤列表。"""
        sl_mgr = self._managers[0] if self._managers else None
        if isinstance(sl_mgr, StepListManagementTree) \
                and sl_mgr.add_template_to_current(path):
            return
        QMessageBox.information(self, "加入当前列表",
                                "请先在左侧选中一个步骤列表")

    def _on_jump_to_composite(self, ref: str) -> None:
        """右键合成卡片「跳转到合成卡片编辑」→ 切活动栏到合成卡片树并选中该卡片。

        经 :attr:`StepListHost.composite_jump_requested` 触发（步骤列表宿主与
        合成卡片宿主都连）：在任一卡片视图里右键合成卡片即可跳转其编辑界面。
        """
        for i, m in enumerate(self._managers):
            if isinstance(m, CompositeManagementTree):
                assert self._switcher is not None
                self._switcher.set_current_row(i)   # 切面板（_on_switch 切树/预览两栈）
                m.preview_widget()                   # 确保宿主已建（_reset_project_view 已建，幂等）
                m.select_composite(ref)              # 选中树条目 → _on_selected 打开编辑
                return
        LogModel.instance().warning("跳转合成卡片：未找到合成卡片管理树")

    def _on_composite_renamed(self, old_path: str, new_path: str) -> None:
        """合成卡片重命名 → 改指所有引用旧路径的合成卡片条目。

        经 :attr:`CompositeTreeWidget` 的 ``on_rename`` 回调触发（重命名流程在
        ``store.rename`` 成功后、``_changed`` 刷新树前调用，此时合成卡片存储内
        该卡片已在新路径 ``new_path``）。两处存储都扫：

        * **步骤列表存储**：引用旧路径的卡片步骤改指新路径 + 落盘
          ``step_list.json`` + 重绑当前卡片画面（卡片名立即更新——否则步骤里的
          合成卡片名不随重命名变化，且运行时变悬空引用）。
        * **合成卡片存储**：**其它**卡片体内引用旧路径的条目改指 + 落盘
          ``composites.json``（当前编辑卡即被重命名者，其体内不含自引用，画面由
          重命名流程自身刷新，此处不重绑——见 :meth:`CompositeManagementTree.repoint_composite_refs`）。
        """
        for m in self._managers:
            if isinstance(m, StepListManagementTree):
                m.repoint_composite_refs(old_path, new_path)
            elif isinstance(m, CompositeManagementTree):
                m.repoint_composite_refs(old_path, new_path)

    def _on_composite_sig_changed(self, ref: str) -> None:
        """合成卡片签名变更 → 重同步步骤列表内引用该卡的 CompositeCard 步骤 io。

        经 :meth:`CompositeManagementTree._on_signature_changed` 的 ``on_sig_changed``
        回调触发（签名表编辑 / quick-create 局部后）。步骤列表里引用该卡的
        CompositeCard 步骤按新签名重建 io（保留已填值），当前列表有变化则刷新卡片。
        """
        for m in self._managers:
            if isinstance(m, StepListManagementTree):
                m.resync_composite_steps(ref)
                return

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
        card_new = LandingCard("新建", "创建一个空工程")
        card_new.clicked.connect(self._on_new)
        card_open = LandingCard("打开", "打开一个 .kscp 文件")
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
        self._switcher = ActivityBar()
        self._switcher.currentChanged.connect(self._on_switch)
        # 栏位最底：执行（待命/停止监听，checkable 状态钮）与设置（瞬时按钮）
        self._exec_btn = self._switcher.add_bottom_button(
            "执行", make_icon("exec"), self._on_exec_clicked, checkable=True)
        self._exec_btn.setContextMenuPolicy(Qt.CustomContextMenu)
        self._exec_btn.customContextMenuRequested.connect(self._on_exec_menu)
        self._update_exec_button()
        self._settings_btn = self._switcher.add_bottom_button(
            "设置", make_icon("settings"), self._on_settings_clicked)

        # 树栏（标题随当前管理树变化）
        self._tree_stack = QStackedWidget()
        self._tree_panel = TitledPanel("资源树栏", self._tree_stack)
        self._tree_panel.setMinimumWidth(180)

        # 右栏：视图栏在上、日志栏在下（树栏右边、视图栏下边）
        self._preview_stack = QStackedWidget()
        preview_panel = TitledPanel("视图栏", self._preview_stack)
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
            w = self._tree_stack.widget(0)
            self._tree_stack.removeWidget(w)
            w.deleteLater()               # 反复开工程不堆积旧控件（评审#8）
        for _ in range(self._preview_stack.count()):
            w = self._preview_stack.widget(0)
            self._preview_stack.removeWidget(w)
            w.deleteLater()
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
        # 模板树「加入当前列表」闭环：信息面板按钮 → 实例化加入当前列表
        spanel = self._step_mgr.preview_widget()
        assert isinstance(spanel, StepInfoPanel)
        spanel.add_requested.connect(self._on_add_template)
        # 合成卡片存储全局共享一份。v2：先建空壳 + 注入解析器（闭包捕获可变 cstore），
        # 再就地加载（load_from_json 先读 sigs 再走树）——体内合成卡片引用经 from_marker
        # 解码时，解析器即可取到被引卡签名（sigs 已预加载），解决加载期先后顺序问题。
        cstore = CompositeCardStore.create_empty()
        CompositeCard.set_resolver(cstore.get_or_none)
        if package.exists("composites.json"):
            cstore.load_from_json(package.read_file("composites.json"), shared_mgr)
        else:
            package.write_file("composites.json", cstore.to_json_bytes())
        # 卡片视图剪贴板共享：步骤列表与合成卡片体之间可互粘步骤
        shared_clip = StepClipboard()
        # 左侧管理树排序（从上到下）：步骤列表 / 合成卡片 / 全局变量 / 步骤模板 / 资源
        self._managers = [
            StepListManagementTree(package, tree, shared_mgr,
                                   composite_store=cstore, clipboard=shared_clip),
            CompositeManagementTree(package, tree, shared_mgr,
                                    cstore, shared_clip,
                                    on_rename=self._on_composite_renamed,
                                    on_sig_changed=self._on_composite_sig_changed),
            VariableManagementTree(package, tree),
            self._step_mgr,
            ResourceManagementTree(package),
        ]
        # 变量树变化 → 步骤列表与合成卡片重检颜色（io 校验随变量树变）
        var_mgr = self._managers[2]
        sl_mgr = self._managers[0]
        comp_mgr = self._managers[1]
        assert isinstance(var_mgr, VariableManagementTree)
        assert isinstance(sl_mgr, StepListManagementTree)
        assert isinstance(comp_mgr, CompositeManagementTree)
        vtw = var_mgr.tree_widget()
        assert isinstance(vtw, VariableTreeWidget)
        vtw.tree_changed.connect(sl_mgr.refresh_cards)
        vtw.tree_changed.connect(comp_mgr.refresh_cards)
        # 进入工程第一画面：store 非空 → 自动选中第一个步骤列表（显示序 DFS 首个列表）
        # 树/宿主均为懒构建 → 先构建再选中；宿主须在联动前构建，否则列表不显示
        sl_mgr.tree_widget()               # 页容器（标题/下拉/添加页/删除该页 + 每页一棵树）
        sl_tree = sl_mgr.current_tree()
        assert sl_tree is not None
        sl_mgr.preview_widget()
        # 步骤列表视图错误/占位卡片数 → 执行按钮启用态（>0 禁止执行，执行中除外）。
        # 须在首个列表加载（setCurrentItem → errors_changed）前连，否则首列表计数漏收。
        self._sl_error_count = 0          # 重置（重开工程：旧宿主计数作废）
        sl_mgr.preview_widget().errors_changed.connect(self._on_sl_errors_changed)
        sl_mgr.list_selected.connect(self._on_exec_list_changed)   # 跨页统一出口
        first_path = sl_tree.first_list_path()
        if first_path:
            item = sl_tree.find_item(first_path)
            if item is not None:
                sl_tree.setCurrentItem(item)   # 触发 list_selected → 宿主显示
        # 页联动：当前页跟随 + 页增删改同步执行器/监听器字典 + 常驻热键监听
        self._current_page = sl_mgr.current_page
        sl_mgr.page_changed.connect(self._on_page_changed)
        sl_mgr.page_added.connect(self._on_page_added)
        sl_mgr.page_renamed.connect(self._on_page_renamed)
        sl_mgr.page_removed.connect(self._on_page_removed)
        self._start_page_listeners()
        self._refresh_exec_status()
        self._update_exec_button()
        if self._manage_btn is not None:
            self._manage_btn.setEnabled(True)
        if self._project_widget is None:
            self._project_widget = self._build_project_view()
            self._central.addWidget(self._project_widget)
        self._reset_project_view()
        # 右键合成卡片「跳转编辑」：步骤列表宿主与合成卡片宿主都连
        # （在任一卡片视图右键合成卡片 → 切到合成卡片树并打开其编辑）
        sl_mgr.preview_widget().composite_jump_requested.connect(
            self._on_jump_to_composite)
        comp_mgr.host.composite_jump_requested.connect(
            self._on_jump_to_composite)
        self._central.setCurrentWidget(self._project_widget)
        self.setWindowTitle("KScript — %s" % (path or "新工程"))
        if not self._project_sized:          # 首次进入工程视图：窗口 = 屏幕 2/3 并居中
            self.resize(*window_size())
            screen = QApplication.primaryScreen()
            if screen is not None:
                g = screen.availableGeometry()
                self.move(g.left() + (g.width() - self.width()) // 2,
                          g.top() + (g.height() - self.height()) // 2)
            self._project_sized = True
        assert self._switcher is not None
        # 默认管理树 = 步骤列表管理树（_managers 第 1 位；进入工程即见步骤列表）
        self._switcher.set_current_row(0)
        if self._exec_btn is not None:
            self._update_exec_button()      # 按当前错误/占位卡片数决定启用态（不无条件启用）

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
    ensure_qt_plugin_path()   # venv 等独立部署：Qt 插件目录显式指路（须先于 QApplication）
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

    from PyQt5.QtWidgets import QApplication, QInputDialog

    from model.变量.project_variable import ProjectVariable
    from model.步骤.step import StepStatus
    from model.步骤.step_list import StepList
    from model.执行.step_runner import StepRunner, StepRunnerState

    app = QApplication.instance() or QApplication(sys.argv)

    # 模板字节（有效模板；中文/引号内容一律用 .encode("utf-8")，禁用中文 bytes 字面量）
    GOOD = '''# -*- coding: utf-8 -*-
from dataclasses import dataclass
from model.步骤.step import Step

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

    # managers 结构：步骤列表 / 合成卡片 / 全局变量 / 步骤模板 / 资源（5 棵）
    assert len(win._managers) == 5
    sl_mgr = win._managers[0]
    assert isinstance(sl_mgr, StepListManagementTree)
    assert sl_mgr.name == "步骤列表"
    comp_mgr = win._managers[1]
    assert isinstance(comp_mgr, CompositeManagementTree)
    assert comp_mgr.name == "合成卡片"
    assert win._package is not None and win._package.exists("composites.json")
    # 默认管理树 = 步骤列表管理树（切换栏第 1 位高亮）
    assert win._switcher is not None
    assert len(win._switcher._buttons) == 5
    assert win._switcher._buttons[0].isChecked()

    # 共享变量树：变量管理树与步骤列表管理树同树
    var_mgr = win._managers[2]
    assert isinstance(var_mgr, VariableManagementTree)
    vtw = var_mgr.tree_widget()
    assert isinstance(vtw, VariableTreeWidget)
    assert vtw._tree is sl_mgr._tree
    host = sl_mgr.preview_widget()
    assert isinstance(host, StepListHost)
    sl_mgr.tree_widget()                              # 页容器构建
    assert sl_mgr.current_tree() is not None
    assert sl_mgr.current_page == "执行列表1"

    # 空 store → step_list.json 已写盘（镜像 variables.json 模式）
    assert win._package is not None
    assert win._package.exists("step_list.json")
    assert sl_mgr.store.paths() == []

    # 经 store API 添加列表 → 保存落盘（store 与包同实例；v2 顶层 = 页）
    sl = StepList.create_empty()
    s = sl_mgr._mgr.create_step("示例")
    s.io.change_value("input", 0, "5")
    s.io.change_value("output", 0, "n1")
    sl.add(s)
    sl_mgr.store.add_list("主列表", sl)
    sl_mgr._save_store()
    raw = win._package.read_file("step_list.json")
    assert '"主列表"' in raw.decode("utf-8") \
        and '"执行列表1"' in raw.decode("utf-8")

    # list_selected → 宿主视图出现卡片
    tw = sl_mgr.current_tree()
    assert isinstance(tw, StepListTreeWidget)
    tw.refresh()                     # store 经 API 直改（绕过树操作）→ 重建树含「主列表」
    tw.list_selected.emit("主列表")
    assert host.currentIndex() == 1
    assert len(host._view.cards) == 1

    # 变量 tree_changed → refresh_cards 不崩（已接线 host）
    vtw.tree_changed.emit()
    assert len(host._view.cards) == 1

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
    host._view.cards[0].step.tag = "主力"
    host._search_edit.setText("主力")
    host._on_search()
    assert host._toolbar_status.text() == "已定位"

    # 工具栏第二行：错误卡片数量（经 errors_changed 同步）+ 跳转错误
    assert host._error_count.text() == "错误卡片: 0"     # 卡片 io 有效
    host._view.cards[0].step.io.change_value("input", 0, "")
    host._view.refresh_validity()          # 输入字段 blockSignals → 显式重检发计数
    assert host._error_count.text() == "错误卡片: 1"
    # 错误数经 errors_changed 转发 → 左侧树条目红加粗（宿主联动）
    it_main = tw.find_item("主列表")
    assert it_main is not None
    assert it_main.font(0).bold()
    assert it_main.foreground(0).color() == QColor(200, 50, 40)
    host._on_jump_error()
    assert host._toolbar_status.text() == "已定位错误卡片"
    assert host._view._selected is host._view.cards[0]
    host._view.cards[0].step.io.change_value("input", 0, "5")
    host._view.refresh_validity()
    assert host._error_count.text() == "错误卡片: 0"
    assert not it_main.font(0).bold()      # 修复 → 树标记恢复默认
    host._on_jump_error()
    assert host._toolbar_status.text() == "无错误卡片"

    # 当前列表被删 → 宿主回占位页
    sl_mgr.store.remove("主列表")
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
    slm2.store.add_list("乙", sl2)                    # walk 序首位；空列表
    slm2.store.add_group("组甲")
    sl3 = StepList.create_empty()
    sl3.add(s2)
    slm2.store.add_list("组甲/丙", sl3)               # 显示序 DFS 第一个列表
    slm2._save_store()
    pkg2.save(tmp2)

    win2 = MainWindow(tmp2)
    win2.show()
    sl_mgr2 = win2._managers[0]
    assert isinstance(sl_mgr2, StepListManagementTree)
    tw2 = sl_mgr2.current_tree()
    assert isinstance(tw2, StepListTreeWidget)
    assert tw2.first_list_path() == "乙"                # walk 序（= 显示序 = 执行序）首个列表
    host2 = sl_mgr2.preview_widget()
    assert isinstance(host2, StepListHost)
    assert host2.currentIndex() == 1                    # 非占位：自动切到列表视图
    assert len(host2._view.cards) == 0                 # 「乙」为空列表 → 无卡片
    assert sl_mgr2._current == "乙"                     # 树中选中项 = 第一个列表
    assert host2._view._step_list is sl_mgr2.store.get("乙")

    # ---- 模板树「加入当前列表」闭环：信息面板 → 实例化加入当前列表 ----
    spanel2 = win2._step_mgr.preview_widget()
    assert isinstance(spanel2, StepInfoPanel)
    win2._on_add_template("示例")
    assert len(sl_mgr2.store.get("乙").steps) == 1
    assert len(host2._view.cards) == 1                 # 宿主刷新出新卡片
    # 失败路径：未选中列表 → 提示框
    _infos = []
    _orig_info = QMessageBox.information
    QMessageBox.information = staticmethod(
        lambda *a, **k: (_infos.append(1), QMessageBox.Ok)[1])
    try:
        sl_mgr2._current = None
        win2._on_add_template("示例")
    finally:
        QMessageBox.information = _orig_info
    assert _infos == [1]
    sl_mgr2._current = "乙"                             # 复位，不影响后续用例

    # ---- 需求：激活切换双向立刻刷新（树勾选 → 卡片；卡片按钮 → 树勾选框） ----
    it2 = tw2.find_item("组甲/丙")
    assert it2 is not None
    tw2.setCurrentItem(it2)                      # 切到含步骤 s2 的列表
    assert sl_mgr2._current == "组甲/丙"
    assert host2._view._step_list is sl_mgr2.store.get("组甲/丙")
    card2 = host2._view.cards[0]
    assert card2.step is sl_mgr2.store.get("组甲/丙").steps[0]
    assert card2.property("active") is True
    it2.setCheckState(0, Qt.Unchecked)           # 树勾选框：停用列表内全部步骤
    assert host2._view.cards[0].step.enabled is False
    card2 = host2._view.cards[0]                # 宿主重建后的新卡片
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
    win_w, win_h = window_size()
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

    # ---- 执行器接线：按钮/状态栏/锁定/热键 toggle 逻辑（多页） ----
    # 冒烟不得真实全局监听：桩替换监听工厂（__main__ 模块命名空间内直接改全局）
    class _StubListener:
        def __init__(self, hotkey, on_toggle, defer_lone_modifier=False):
            self.hotkey, self.on_toggle = hotkey, on_toggle
            self.defer = defer_lone_modifier
            self.started = False

        def start(self):
            self.started = True

        def stop(self):
            self.started = False

    _orig_mk_listener = _make_hotkey_listener
    _make_hotkey_listener = lambda h, cb, defer=False: _StubListener(h, cb, defer)
    try:
        win_exec = MainWindow()
        win_exec._open_package(KscpPackage.create_empty(), None)
        app.processEvents()
        assert win_exec._runners == {}
        assert win_exec._current_page == "执行列表1"
        # 开包即常驻热键监听：executor.json 缺失 → 第一页默认 "`"
        assert set(win_exec._hotkey_listeners) == {"执行列表1"}
        _lst = win_exec._hotkey_listeners["执行列表1"]
        assert isinstance(_lst, _StubListener) and _lst.started and _lst.hotkey == "`"
        # C1: 状态栏计数监听经桥（worker 线程日志不得同步操作 QLabel）
        assert not any(cb is win_exec._update_status_counts
                       for cb in LogModel.instance()._listeners), \
            "状态栏计数直接注册 _update_status_counts 会在 worker 线程操作 QLabel"
        _spy_counts = []
        win_exec._exec_bridge.log_changed.connect(lambda: _spy_counts.append(1))
        LogModel.instance().info("counts-spy")
        assert len(_spy_counts) == 1, _spy_counts      # 日志变更经桥发出
        # 未开包无执行入口——开包后按钮可用
        assert win_exec._exec_btn is not None and win_exec._exec_btn.isEnabled()
        # 活动栏底部按钮：执行 + 设置存在
        assert win_exec._settings_btn is not None
        assert len(win_exec._switcher._bottom_buttons) == 2
        # 图标放大：48×48 按钮 + 36×36 图标（用户反馈图标太小）
        for _b in (win_exec._exec_btn, win_exec._settings_btn):
            assert _b.size() == QSize(48, 48), _b.size()
            assert _b.iconSize() == QSize(36, 36), _b.iconSize()
        # 点击执行按钮 → **全部页**进入待命（按钮绿），不直接执行步骤
        win_exec._exec_btn.click()
        assert win_exec._armed is True
        assert win_exec._exec_btn.isChecked(), "待命中执行按钮应呈 checked（绿色）"
        assert win_exec._runners == {}                 # 待命不建 runner
        assert "待命" in win_exec._exec_status.text()
        # 热键 toggle：待命中 READY → 建 runner 并 start（空 store 无步骤 → 恒 READY）
        win_exec._exec_bridge.hotkey_toggle.emit("执行列表1")
        assert isinstance(win_exec._runners["执行列表1"], StepRunner)
        assert win_exec._runners["执行列表1"].state is StepRunnerState.READY
        win_exec._exec_bridge.hotkey_toggle.emit("不存在的页")   # 未知页（页已删防御）→ 忽略
        # 再点执行按钮 → 关闭待命（灰）；未待命 → 热键忽略
        win_exec._exec_btn.click()
        assert win_exec._armed is False
        assert not win_exec._exec_btn.isChecked()
        _r0 = win_exec._runners["执行列表1"]
        win_exec._exec_bridge.hotkey_toggle.emit("执行列表1")
        assert win_exec._runners["执行列表1"] is _r0    # 未待命：热键不触发
        # 编辑锁定：步骤列表树走只读模式（可点击查看、禁编辑；不整树禁用——
        # 禁用会吞 hover 事件导致卡片缩放动画消失）；其余树整树禁用
        sl_tree = win_exec._managers[0].current_tree()
        assert sl_tree is not None
        var_tree = win_exec._managers[2].tree_widget()
        win_exec._set_exec_locked(True)
        assert sl_tree._read_only, "步骤列表树应进入只读模式"
        assert not var_tree.isEnabled()                 # 变量树整树禁用
        win_exec._set_exec_locked(False)
        assert not sl_tree._read_only
        assert var_tree.isEnabled()
        # ⑤ 执行期间锁定所有影响执行器的编辑入口（管理菜单/文件新建打开/设置按钮）
        win_exec._set_exec_locked(True)
        assert not win_exec._manage_btn.isEnabled()
        assert not win_exec._settings_btn.isEnabled()
        assert not win_exec._a_new.isEnabled() and not win_exec._a_open.isEnabled()
        assert win_exec._exec_btn.isEnabled()          # 执行按钮保留（停止通道）
        assert not win_exec._exec_locked or win_exec._exec_locked
        win_exec._set_exec_locked(False)
        assert win_exec._manage_btn.isEnabled()        # 已开包 → 解锁后恢复可用
        assert win_exec._settings_btn.isEnabled()
        assert win_exec._a_new.isEnabled() and win_exec._a_open.isEnabled()
        # 未开包：无活动栏 → 执行/设置按钮不存在（无入口，安全）
        win_bare = MainWindow()
        assert win_bare._exec_btn is None and win_bare._settings_btn is None
        # 工具栏菜单按钮：最小宽度 >= 文本度量（防文字被压缩截断）
        fm = win_bare.fontMetrics()
        assert win_bare._manage_btn.minimumWidth() >= fm.horizontalAdvance("管理")
        assert win_bare._manage_btn.toolButtonStyle() == Qt.ToolButtonTextOnly

        # ---- I2: 每页单 runner + toggle 语义（假 runner 状态可控） ----
        class _FakeRunner:
            """桩执行器：状态手动置位，记录 start/request_stop 调用。"""

            def __init__(self, store, only=None, stop_mode="after_step"):
                self.store = store
                self.only = only            # 单列表范围（only_path）
                self.stop_mode = stop_mode  # 停止方式（应来自 executor.json）
                self.state = StepRunnerState.READY
                self.calls = []
                self._listeners = []

            def add_state_listener(self, cb):
                self._listeners.append(cb)

            def add_progress_listener(self, cb):
                pass                        # 桩不产生进度（进度经 _on_progress 直测）

            def start(self):
                self.calls.append("start")

            def request_stop(self):
                self.calls.append("stop")

            def _set(self, st):
                self.state = st
                for cb in list(self._listeners):
                    cb(st)

        _orig_mk_runner = _make_step_runner
        _make_step_runner = lambda store, only=None, stop_mode="after_step": \
            _FakeRunner(store, only, stop_mode)
        try:
            win_i2 = MainWindow()
            win_i2._open_package(KscpPackage.create_empty(), None)
            app.processEvents()
            win_i2._exec_btn.click()                    # 待命（不建 runner）
            assert win_i2._armed is True
            assert win_i2._runners == {}
            win_i2._exec_bridge.hotkey_toggle.emit("执行列表1")   # 热键 → 假 runner + start
            fake1 = win_i2._runners["执行列表1"]
            assert isinstance(fake1, _FakeRunner)
            assert fake1.stop_mode == "after_step"      # executor.json 缺失 → 默认停止方式
            assert fake1.calls == ["start"], fake1.calls
            fake1._set(StepRunnerState.RUNNING)         # 模拟开始执行
            app.processEvents()
            assert "执行中" in win_i2._exec_status.text()
            win_i2._exec_btn.click()                    # 执行中点按钮 → 关闭待命 + request_stop
            assert win_i2._armed is False
            assert win_i2._runners["执行列表1"] is fake1
            assert fake1.calls == ["start", "stop"], fake1.calls
            win_i2._exec_bridge.hotkey_toggle.emit("执行列表1")   # 未待命 → 热键忽略
            assert fake1.calls == ["start", "stop"], fake1.calls
            fake1._set(StepRunnerState.READY)           # 自然结束
            app.processEvents()
            assert win_i2._runners["执行列表1"] is fake1          # READY 后保留复用
            win_i2._exec_btn.click()                    # 再待命
            assert win_i2._armed is True
            win_i2._exec_bridge.hotkey_toggle.emit("执行列表1")   # READY → 重建新 runner
            assert isinstance(win_i2._runners["执行列表1"], _FakeRunner)
            assert win_i2._runners["执行列表1"] is not fake1
            # I3: 含步骤 store → attach 后挂钩、状态变更刷卡片、detach 后清空
            pkg_i3 = KscpPackage.create_empty()
            pkg_i3.write_file("actions/示例.py", GOOD.encode("utf-8"))
            tree_i3 = VariableTree.create_empty()
            tree_i3.add("n1", ProjectVariable.create("number", 100, pkg_i3))
            pkg_i3.write_file("variables.json", tree_i3.to_json_bytes())
            slm_i3 = StepListManagementTree(pkg_i3, tree_i3)
            s_i3 = slm_i3._mgr.create_step("示例")
            s_i3.io.change_value("input", 0, "5")
            s_i3.io.change_value("output", 0, "n1")
            sl_i3 = StepList.create_empty()
            sl_i3.add(s_i3)
            slm_i3.store.add_list("主列表", sl_i3)
            slm_i3._save_store()
            win_i3 = MainWindow()
            win_i3._open_package(pkg_i3, None)
            app.processEvents()
            win_i3._exec_btn.click()                    # 待命
            win_i3._exec_bridge.hotkey_toggle.emit("执行列表1")   # 热键 → 假 runner + hooks + start
            fake3 = win_i3._runners["执行列表1"]
            assert isinstance(fake3, _FakeRunner)
            assert fake3.calls == ["start"], fake3.calls
            assert len(win_i3._step_hooks["执行列表1"]) == 1, win_i3._step_hooks
            fired3 = []
            win_i3._exec_bridge.step_status.connect(lambda _s=None: fired3.append(1))
            step3 = win_i3._step_hooks["执行列表1"][0][0]
            step3.status = StepStatus.RUNNING
            assert len(fired3) == 1, fired3             # 状态变更 → 桥 → 卡片刷新
            app.processEvents()
            stree3 = win_i3._managers[0].current_tree()
            assert stree3 is not None
            assert stree3._running_path == "主列表"      # 树高亮正在执行的列表
            it3 = stree3.find_item("主列表")
            assert it3 is not None and it3.text(0) == "▶ 主列表"
            step3.status = StepStatus.FINISHED
            assert len(fired3) == 2, fired3
            app.processEvents()
            assert stree3._running_path is None         # 无 RUNNING → 清高亮
            assert stree3.find_item("主列表").text(0) == "主列表"
            fake3._set(StepRunnerState.RUNNING)         # 模拟执行中
            app.processEvents()
            fake3._set(StepRunnerState.READY)           # 执行结束 → detach
            app.processEvents()
            assert win_i3._step_hooks.get("执行列表1", []) == [], win_i3._step_hooks
            step3.status = StepStatus.PENDING
            assert len(fired3) == 2, fired3             # detach 后不再通知

            # ---- 执行范围（单列表）：切换 → 待命 runner 重建并携带 only_path ----
            assert win_i3._exec_scope == "all"
            win_i3._set_exec_scope("current")
            assert win_i3._runners["执行列表1"].only == "主列表", \
                win_i3._runners["执行列表1"].only
            # ---- 执行进度：桥 → 状态栏「执行中 i/n」 ----
            win_i3._runners["执行列表1"]._set(StepRunnerState.RUNNING)
            app.processEvents()
            win_i3._on_progress(("执行列表1", 1, 2))
            assert "1/2" in win_i3._exec_status.text(), win_i3._exec_status.text()
            win_i3._runners["执行列表1"]._set(StepRunnerState.READY)
            app.processEvents()
            win_i3._set_exec_scope("all")
            assert win_i3._runners["执行列表1"].only is None

            # ---- 并发多页：双页工程双监听器 + 独立 toggle + 锁定计数 + 页联动 ----
            pkg_mp = KscpPackage.create_empty()
            pkg_mp.write_file("actions/示例.py", GOOD.encode("utf-8"))
            tree_mp = VariableTree.create_empty()
            tree_mp.add("n1", ProjectVariable.create("number", 100, pkg_mp))
            pkg_mp.write_file("variables.json", tree_mp.to_json_bytes())
            slm_mp = StepListManagementTree(pkg_mp, tree_mp)
            _s_mp = slm_mp._mgr.create_step("示例")
            _s_mp.io.change_value("input", 0, "5")
            _s_mp.io.change_value("output", 0, "n1")
            sl_mp1 = StepList.create_empty()
            sl_mp1.add(_s_mp)
            slm_mp.store.add_list("主列表", sl_mp1)
            slm_mp.page_store.add_page("执行列表2")
            slm_mp._save_store()
            pkg_mp.write_file(
                "executor.json",
                json.dumps({"hotkey": "f", "stop_mode": "immediate",
                            "pages": {"执行列表1": "f", "执行列表2": "g"}},
                           ensure_ascii=False).encode("utf-8"))
            win_mp = MainWindow()
            win_mp._open_package(pkg_mp, None)
            app.processEvents()
            assert set(win_mp._hotkey_listeners) == {"执行列表1", "执行列表2"}
            assert win_mp._hotkey_listeners["执行列表1"].hotkey == "F"
            assert win_mp._hotkey_listeners["执行列表2"].hotkey == "G"

            # ---- 组合/命名键/单独修饰键热键：规范化 + 前缀冲突延迟判定 ----
            pkg_hk = KscpPackage.create_empty()
            pkg_hk.write_file(
                "executor.json",
                json.dumps({"hotkey": "F1", "stop_mode": "after_step",
                            "pages": {"执行列表1": "f1", "执行列表2": "ctrl+alt+i",
                                      "执行列表3": "ctrl"}},
                           ensure_ascii=False).encode("utf-8"))
            slm_hk = StepListManagementTree(pkg_hk, VariableTree.create_empty())
            slm_hk.page_store.add_page("执行列表2")
            slm_hk.page_store.add_page("执行列表3")
            slm_hk._save_store()
            win_hk = MainWindow()
            win_hk._open_package(pkg_hk, None)
            app.processEvents()
            assert win_hk._page_hotkeys() == {
                "执行列表1": "F1", "执行列表2": "Ctrl+Alt+I", "执行列表3": "Ctrl"}
            assert win_hk._hotkey_listeners["执行列表1"].hotkey == "F1"
            assert win_hk._hotkey_listeners["执行列表1"].defer is False
            assert win_hk._hotkey_listeners["执行列表2"].hotkey == "Ctrl+Alt+I"
            # Ctrl 与 Ctrl+Alt+I 并存 → 前缀冲突 → Ctrl 延迟到释放判定（组合优先）
            assert win_hk._hotkey_listeners["执行列表3"].defer is True
            # _lone_mod_deferred 纯函数语义
            assert _lone_mod_deferred("Ctrl", ["Ctrl", "Ctrl+Alt+I"]) is True
            assert _lone_mod_deferred("Ctrl", ["Ctrl", "Alt+I"]) is False
            assert _lone_mod_deferred("F1", ["F1", "Ctrl"]) is False
            assert _lone_mod_deferred("Ctrl", ["Ctrl", "Ctrl"]) is False
            # 未待命 → 热键忽略；**一次待命全部页生效**后各自触发
            win_mp._exec_bridge.hotkey_toggle.emit("执行列表1")
            assert "执行列表1" not in win_mp._runners
            win_mp._armed = True
            win_mp._exec_bridge.hotkey_toggle.emit("执行列表1")   # 页1 热键 → runner1
            win_mp._exec_bridge.hotkey_toggle.emit("执行列表2")   # 页2 热键 → runner2
            fake_m1 = win_mp._runners["执行列表1"]
            fake_m2 = win_mp._runners["执行列表2"]
            assert isinstance(fake_m1, _FakeRunner) and isinstance(fake_m2, _FakeRunner)
            assert fake_m1 is not fake_m2
            assert fake_m1.calls == ["start"] and fake_m2.calls == ["start"]
            # 停止中文案随停止方式（immediate）
            fake_m1._set(StepRunnerState.STOPPING)
            app.processEvents()
            assert "立即停止" in win_mp._exec_status.text(), win_mp._exec_status.text()
            # 并发锁定：页1 RUNNING → 锁；页1 READY（页2 仍 RUNNING）→ 仍锁；页2 READY → 解锁
            fake_m1._set(StepRunnerState.RUNNING)
            app.processEvents()
            assert win_mp._exec_locked
            fake_m2._set(StepRunnerState.RUNNING)
            fake_m1._set(StepRunnerState.READY)
            app.processEvents()
            assert win_mp._exec_locked, "页2 仍执行中 → 保持锁定"
            assert "另 1 页执行中" in win_mp._exec_status.text()   # 后台页提示
            fake_m2._set(StepRunnerState.READY)
            app.processEvents()
            assert not win_mp._exec_locked
            # 关闭待命：执行中的**全部页**同时停止
            fake_m1._set(StepRunnerState.RUNNING)
            fake_m2._set(StepRunnerState.RUNNING)
            win_mp._on_exec_clicked()
            assert win_mp._armed is False
            assert fake_m1.calls == ["start", "stop"], fake_m1.calls
            assert fake_m2.calls == ["start", "stop"], fake_m2.calls
            fake_m1._set(StepRunnerState.READY)
            fake_m2._set(StepRunnerState.READY)
            app.processEvents()
            # 页删除联动：停监听 + 清理 + 悬空热键防御
            win_mp._managers[0].page_store.remove_page("执行列表2")   # 管理树已完成删除
            win_mp._on_page_removed("执行列表2")
            assert "执行列表2" not in win_mp._hotkey_listeners
            assert "执行列表2" not in win_mp._runners
            win_mp._exec_bridge.hotkey_toggle.emit("执行列表2")   # 悬空 → 无操作不崩
            assert "执行列表2" not in win_mp._runners
            # 页重命名联动：字典重键 + 当前页跟随
            win_mp._on_page_renamed("执行列表1", "重命名页")
            assert "重命名页" in win_mp._runners and "执行列表1" not in win_mp._runners
            assert win_mp._current_page == "重命名页"
            # 每页独立代际：陈旧页状态迟到 → 忽略（不误锁）
            _gen_now = win_mp._runner_gens["重命名页"]
            win_mp._exec_bridge.runner_state.emit(
                ("重命名页", _gen_now - 1, StepRunnerState.RUNNING))
            app.processEvents()
            assert not win_mp._exec_locked               # 陈旧状态被忽略
        finally:
            _make_step_runner = _orig_mk_runner
    finally:
        _make_hotkey_listener = _orig_mk_listener

    # ---- 设置按钮（活动栏底部）与各页热键/停止方式落盘 ----
    # 设置按钮 = 瞬时按钮（点击后无样式残留）；弹窗细节冒烟见 widgets.通用.settings_dialog
    assert not win_exec._settings_btn.isCheckable()
    # 本段 _apply_settings 会重建监听 → 重新桩替换监听工厂（冒烟不得真实全局监听）
    _orig_mk_listener0 = _make_hotkey_listener
    _make_hotkey_listener = lambda h, cb, defer=False: _StubListener(h, cb, defer)
    try:
        # _apply_settings：只写工程包 executor.json（不碰 setting.json——executor.json 唯一来源）
        win_exec._apply_settings({"执行列表1": "g"}, "immediate")
        assert win_exec._package.exists("executor.json")
        data = json.loads(win_exec._package.read_file("executor.json").decode("utf-8"))
        assert data == {"hotkey": "g", "stop_mode": "immediate",
                        "pages": {"执行列表1": "g"}}, data
        # _page_hotkeys 读回：v2 pages 映射；保存后监听已按新热键重建
        assert win_exec._page_hotkeys() == {"执行列表1": "G"}
        assert win_exec._hotkey_listeners["执行列表1"].hotkey == "G"
        # _current_stop_mode：立即停止 → 停止方式提示文案随之变化
        # （STOPPING 状态栏文案按 runner 实际状态刷新，已在多页假 runner 段验证）
        assert win_exec._current_stop_mode() == "immediate"
        assert win_exec._stop_hint() == "立即停止"
        win_exec._package.remove("executor.json")
        try:
            assert win_exec._page_hotkeys() == {"执行列表1": "`"}   # 缺失 → 第一页默认热键
            assert win_exec._current_stop_mode() == "after_step"
        finally:
            win_exec._package.write_file(
                "executor.json", b'{"hotkey": "g"}')
        # 旧格式（无 pages）→ 顶层 hotkey 归第一页；无 stop_mode → 静默回退 after_step
        assert win_exec._page_hotkeys() == {"执行列表1": "G"}
        assert win_exec._current_stop_mode() == "after_step"
        win_exec._package.write_file(
            "executor.json",
            '{"hotkey": "g", "stop_mode": "bad", "pages": {"执行列表1": "ab"}}'
            .encode("utf-8"))
        assert win_exec._current_stop_mode() == "after_step"        # 非法值 → 回退 + 告警日志
        assert win_exec._page_hotkeys() == {"执行列表1": ""}        # 非法热键（多字符）→ 空

        # ---- 每页代际标记：陈旧 runner 迟到 READY 不覆盖新 runner 状态 ----
        win_exec._package.write_file(
            "executor.json",
            json.dumps({"hotkey": "`", "stop_mode": "after_step",
                        "pages": {"执行列表1": "`"}},
                       ensure_ascii=False).encode("utf-8"))   # 恢复合法配置
        win_exec._exec_btn.click()                       # 待命
        win_exec._exec_bridge.hotkey_toggle.emit("执行列表1")   # 热键 → 新 runner（新代际）
        page = win_exec._current_page
        win_exec._set_exec_status("执行中……（按热键停止）")
        win_exec._set_exec_locked(True)
        stale_gen = win_exec._runner_gens[page] - 1      # 旧代际
        win_exec._exec_bridge.runner_state.emit(
            (page, stale_gen, StepRunnerState.READY))
        assert "执行中" in win_exec._exec_status.text()  # 陈旧 READY 被忽略
        assert win_exec._managers[0].current_tree()._read_only  # 编辑仍锁定（只读模式）
        win_exec._exec_bridge.runner_state.emit(
            (page, win_exec._runner_gens[page], StepRunnerState.READY))
        assert "待命" in win_exec._exec_status.text()    # 当前代际状态正常刷新（解锁）
        assert not win_exec._managers[0].current_tree()._read_only
    finally:
        _make_hotkey_listener = _orig_mk_listener0

    # ---- 右键合成卡片「跳转到编辑」：切活动栏 + 选中卡片 + 打开编辑 ----
    tmp_j = tempfile.mktemp(suffix=".kscp")
    KscpPackage.create_empty().save(tmp_j)
    win_j = MainWindow(tmp_j)
    win_j.show()
    comp_mgr_j = win_j._managers[1]
    assert isinstance(comp_mgr_j, CompositeManagementTree)
    body_x = StepList.create_empty()
    comp_mgr_j.store.add_list("卡X", body_x)      # 内存加一张合成卡片定义
    comp_mgr_j.tree_widget().refresh()             # 树在开包时已建（空 store）→ 重建含卡X
    win_j._on_jump_to_composite("卡X")            # 模拟右键「跳转到合成卡片编辑」
    assert win_j._switcher is not None
    assert win_j._switcher._buttons[1].isChecked()    # 活动栏切到合成卡片面板
    assert comp_mgr_j.current_path == "卡X"           # 树选中卡X
    chost_j = comp_mgr_j.host
    assert chost_j.currentIndex() == 1                # 打开卡X 编辑页
    assert chost_j._view._step_list is body_x
    # 跳转到不存在的卡片 → 不崩（select_composite False，面板切过去但选中不变）
    win_j._on_jump_to_composite("不存在")
    assert comp_mgr_j.current_path == "卡X"

    # ---- 重命名合成卡片 → 引用改指 + 卡片名刷新（修「步骤中命名不随重命名变化」）----
    # win_j 已有合成卡片「卡X」(body_x)；先在步骤列表「L」里引用它，再把 卡X 重命名为
    # 卡Y，验证：引用条目 ref/name 改指卡Y、卡片画面名立即刷新、运行时仍解析到 body_x、
    # 落盘 step_list.json 存的是新标记 @合成卡片:卡Y（引用只存指针 → 改一处处处变）。
    sl_mgr_j = win_j._managers[0]
    assert isinstance(sl_mgr_j, StepListManagementTree)
    listL = StepList.create_empty()
    card_step = CompositeCard("卡X", sl_mgr_j._tree, sl_mgr_j._package)
    listL.add(card_step)
    sl_mgr_j.store.add_list("L", listL)
    sl_mgr_j._save_store()
    sl_tw_j = sl_mgr_j.current_tree()
    sl_tw_j.refresh()
    sl_tw_j.list_selected.emit("L")            # 选中 L → 宿主显示其卡片
    sl_host_j = sl_mgr_j.preview_widget()
    assert sl_host_j.currentIndex() == 1
    assert card_step.ref == "卡X" and card_step.name == "卡X"
    assert sl_host_j._view.cards[0]._name.text() == "卡X"   # 改名前卡片名
    # 重命名 卡X → 卡Y（_on_composite_renamed 经 on_rename 自动改指两处存储）
    assert comp_mgr_j.current_path == "卡X"    # 跳转测试后树仍选中卡X
    _orig_get_text = QInputDialog.getText
    QInputDialog.getText = staticmethod(lambda *a, **k: ("卡Y", True))
    try:
        comp_mgr_j.tree_widget()._act_rename()
    finally:
        QInputDialog.getText = _orig_get_text
    # 定义已改名
    assert "卡Y" in comp_mgr_j.store.paths() and "卡X" not in comp_mgr_j.store.paths()
    # 步骤列表里的引用条目改指 + 卡片画面名刷新（核心修复点）
    assert card_step.ref == "卡Y" and card_step.name == "卡Y"
    assert sl_host_j._view.cards[0]._name.text() == "卡Y"
    # 运行时解析仍指向原定义体（改指未破坏执行）；旧路径已悬空
    assert CompositeCard.resolve_ref("卡Y").body is body_x
    assert CompositeCard.resolve_ref("卡X") is None
    # 落盘的 step_list.json 存新标记（引用只存指针 → 改一处处处变）
    sl_blob = win_j._package.read_file("step_list.json").decode("utf-8")
    assert "@合成卡片:卡Y" in sl_blob and "@合成卡片:卡X" not in sl_blob
    CompositeCard.set_resolver(lambda ref: None)   # 复位，避免影响后续模块冒烟

    # ---- 占位卡片：计入错误数、可定位、禁止执行 ----
    # 工程含一条「格式串不可还原」的步骤 → 加载落为红色占位卡；执行按钮禁用、
    # 错误数含该卡、跳转错误可定位（用户：占位卡应计入错误数并禁止执行）。
    import base64 as _b64
    import json as _json
    from model.步骤.step_io import StepIOWidget
    from model.变量.variable_tree import VariableTree
    from model.合成卡片.placeholder_step import PlaceholderStep
    pkg_e = KscpPackage.create_empty()
    # 一条不可还原的格式串（name「别的步骤」无匹配模板）+ 空列表「干净」作对照
    fake_fmt = _b64.urlsafe_b64encode(_json.dumps(
        {"name": "别的步骤", "in": [], "out": [],
         "io": StepIOWidget([], [], VariableTree.create_empty(),
                            pkg_e).to_format_string(),
         "run": False, "tag": ""}, ensure_ascii=False).encode()).decode().rstrip("=")
    sl_e = {"坏列表": [fake_fmt], "干净": []}
    pkg_e.write_file("step_list.json",
                     json.dumps(sl_e, ensure_ascii=False).encode("utf-8"))
    tmp_e = tempfile.mktemp(suffix=".kscp")
    pkg_e.save(tmp_e)
    win_e = MainWindow(tmp_e)
    win_e.show()
    sl_mgr_e = win_e._managers[0]
    host_e = sl_mgr_e.preview_widget()
    # 首列表「坏列表」自动选中 → 宿主显示占位卡 → errors_changed(1)
    assert win_e._sl_error_count == 1, win_e._sl_error_count
    assert isinstance(host_e._view.cards[0].step, PlaceholderStep)
    assert host_e._view.error_card_indices() == [1]   # 占位卡计入错误数（可定位）
    assert host_e._view.jump_to_error() is True       # 跳转错误可定位到占位卡
    assert win_e._exec_btn is not None and not win_e._exec_btn.isEnabled()  # 禁止执行
    # 切到「干净」列表 → 错误数归零、执行按钮恢复
    sl_mgr_e.current_tree().list_selected.emit("干净")
    assert win_e._sl_error_count == 0
    assert win_e._exec_btn.isEnabled()
    # 切回「坏列表」→ 再次禁用；_exec_has_errors 兜底扫描亦为 True
    sl_mgr_e.current_tree().list_selected.emit("坏列表")
    assert not win_e._exec_btn.isEnabled()
    assert win_e._exec_has_errors() is True

    print("MainWindow smoke OK")
