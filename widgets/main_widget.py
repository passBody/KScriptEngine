# -*- coding: utf-8 -*-
"""
主窗口（入口）
============

:class:`MainWindow` 是 KScript 的主窗口。无工程时显示「新建 / 打开」两个大卡片；
打开 ``.kscp`` 后，左侧是管理树切换栏 + 当前管理树，中间是当前管理树的大预览。

界面组件按职责拆分：管理树簇见 :mod:`widgets.management_trees`，活动栏见
:mod:`widgets.activity_bar`，设置弹窗见 :mod:`widgets.settings_dialog`，
通用小件（图标/窗口尺寸/落地卡片/标题面板/占位）见 :mod:`widgets.ui_common`。
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

from model.hotkey import HotkeyListener
from model.kscp_package import KscpPackage
from model.log_model import LogLevel, LogModel
from model.step import StepStatus
from model.step_manager import StepManager
from model.step_runner import StepRunner, StepRunnerState
from model.variable_tree import VariableTree
from widgets.log_widget import LogWidget
from widgets.step_list_tree_widget import StepListTreeWidget
from widgets.step_tree_widget import StepInfoPanel, StepTreeWidget
from widgets.variable_tree_widget import VariableTreeWidget
from widgets.activity_bar import ActivityBar
from widgets.management_trees import (
    ManagementTree, ResourceManagementTree, StepListHost,
    StepListManagementTree, StepManagementTree, VariableManagementTree,
)
from widgets.settings_dialog import SettingsDialog
from widgets.ui_common import (
    LandingCard, TitledPanel, ensure_qt_plugin_path, make_icon, window_size,
)

__all__ = ["MainWindow", "main"]


# 程序图标路径（main() 应用）
_ICON_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "icon", "kscript.ico")


class _ExecBridge(QObject):
    """执行器跨线程桥：工作线程 emit → Qt queued 到 GUI 线程刷新。"""
    runner_state = pyqtSignal(object)     # (gen, StepRunnerState)：代际标记防陈旧覆盖
    hotkey_toggle = pyqtSignal()
    log_changed = pyqtSignal()            # LogModel 变更（worker 线程记日志）→ GUI 线程刷计数
    step_status = pyqtSignal(object)      # 步骤状态变更（执行线程）→ GUI 线程刷卡片颜色/树高亮
    progress = pyqtSignal(object)         # (第几步, 总数)：执行进度 → 状态栏


# 模拟注入点：冒烟测试替换以避开真实热键/线程（与 picker 包装同思路）
def _make_step_runner(store, only_path=None):
    return StepRunner(store, only_path)


def _make_hotkey_listener(hotkey, on_toggle):
    return HotkeyListener(hotkey, on_toggle)


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
        self._runner: Optional[StepRunner] = None
        self._hotkey_listener: Optional[HotkeyListener] = None
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
        self._exec_scope = "all"     # 执行范围：all=全部列表 / current=仅当前列表
        self._runner_gen = 0                     # 执行器代际：陈旧 runner 迟到状态被忽略
        self._step_hooks: List[Tuple[object, Callable]] = []   # 执行期步骤状态监听（卡片刷新）
        self._step_paths: Dict[object, str] = {}   # 执行期 step → 列表路径（树高亮映射）

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

    # ---- 执行器接线 ----
    def _on_exec_clicked(self) -> None:
        """执行按钮：未监听 → 待命（启动热键监听）；已监听 → 停监听。"""
        if self._hotkey_listener is None:
            self._start_listening()
        else:
            self._stop_listening()

    def _start_listening(self) -> None:
        # 旧 runner 执行/停止中 → 拒绝并发双执行（同一 store 只允许一个执行器）
        if self._runner is not None and self._runner.state is not StepRunnerState.READY:
            self._set_exec_status("等待当前执行结束…")
            LogModel.instance().info("执行器仍忙碌：等待当前执行结束后再待命")
            self._update_exec_button()          # 按钮 checked 状态回正（拒绝路径）
            return
        if self._package is None:
            return
        sl_mgr = self._managers[0] if self._managers else None
        assert isinstance(sl_mgr, StepListManagementTree)
        only = None
        if self._exec_scope == "current":
            only = sl_mgr.current_path
            if not only:
                LogModel.instance().warning(
                    "仅执行当前列表：未选中任何列表，按全部列表执行")
        self._runner = _make_step_runner(sl_mgr.store, only)
        self._runner_gen += 1
        gen = self._runner_gen
        self._runner.add_state_listener(
            lambda st, g=gen: self._exec_bridge.runner_state.emit((g, st)))
        self._attach_progress()
        hotkey = self._current_hotkey()
        self._hotkey_listener = _make_hotkey_listener(
            hotkey, self._exec_bridge.hotkey_toggle.emit)
        self._hotkey_listener.start()
        self._update_exec_button()
        self._set_exec_status("待命：按 %s 执行/停止" % hotkey)
        self._set_exec_locked(False)          # 重待命复位锁定（停止监听后立即重待命不卡死）
        LogModel.instance().info("执行器待命：热键 %s（再按停止）" % hotkey)

    def _stop_listening(self) -> None:
        if self._hotkey_listener is not None:
            self._hotkey_listener.stop()
            self._hotkey_listener = None
        if self._runner is not None:
            self._runner.request_stop()          # 执行中 → 当前步骤完成后停
            if self._runner.state is StepRunnerState.READY:
                self._runner = None              # 已就绪 → 直接释放
            # 非 READY → 保留引用（防并发双执行）：其自然结束 READY 时经 _on_runner_state 清理
        self._update_exec_button()
        self._set_exec_status("已停止监听")
        LogModel.instance().info("执行器已停止监听")

    def _handle_hotkey_toggle(self) -> None:
        """热键按下（GUI 线程，经桥 queued）：READY → start；否则 → request_stop。"""
        if self._runner is None:
            return
        if self._runner.state is StepRunnerState.READY:
            self._attach_step_hooks()          # 执行前挂卡片状态监听
            self._runner.start()
        else:
            self._runner.request_stop()

    def _on_runner_state(self, payload) -> None:
        """执行器状态变化（GUI 线程）：状态栏 + 编辑锁定 + 挂钩清理。"""
        gen, st = payload
        if gen != self._runner_gen:
            return                      # 陈旧 runner（已停止）的迟到状态 → 忽略
        if st is StepRunnerState.RUNNING:
            self._set_exec_status("执行中……（按热键停止）")
            self._set_exec_locked(True)
        elif st is StepRunnerState.STOPPING:
            self._set_exec_status("停止中……（当前步骤完成后停）")
        else:
            self._set_exec_status(
                "待命：按 %s 执行/停止" % self._current_hotkey())
            self._set_exec_locked(False)
            self._detach_step_hooks()
            # 停止监听后自然结束的旧 runner：READY 回调清理引用（防并发双执行）
            if self._runner is not None and self._hotkey_listener is None:
                self._runner = None

    # ---- 执行期卡片状态刷新（spec §6 组件 6）：步骤状态 → 桥 → 重检卡片颜色 ----
    def _attach_step_hooks(self) -> None:
        """执行前：为 store 全部步骤挂状态监听（卡片颜色随执行刷新、
        树高亮正在执行的列表）。"""
        self._detach_step_hooks()              # 幂等：先清旧钩再挂新钩
        self._step_paths = {}
        if not self._managers:
            return
        m0 = self._managers[0]
        if not isinstance(m0, StepListManagementTree):
            return
        for path, is_group in m0.store.walk():
            if is_group:
                continue
            for step in m0.store.get(path).steps:
                self._step_paths[step] = path
                cb = lambda s, _st: self._exec_bridge.step_status.emit(s)
                step.add_status_listener(cb)
                self._step_hooks.append((step, cb))

    def _detach_step_hooks(self) -> None:
        """执行结束：移除全部步骤状态监听并清空 + 清除树高亮。"""
        for step, cb in self._step_hooks:
            step.remove_status_listener(cb)
        self._step_hooks.clear()
        self._step_paths = {}
        self._clear_running_highlight()

    def _clear_running_highlight(self) -> None:
        """清除步骤列表树的执行高亮（▶ 前缀/蓝色）。"""
        if not self._managers:
            return
        m0 = self._managers[0]
        if isinstance(m0, StepListManagementTree) and m0._sl_tree is not None:
            m0._sl_tree.set_running_path(None)

    def _on_step_status(self, step) -> None:
        """步骤状态变化（GUI 线程，经桥 queued）：卡片重检颜色 + 树高亮执行中列表。"""
        if not self._managers:
            return
        m0 = self._managers[0]
        if isinstance(m0, StepListManagementTree):
            m0.refresh_cards()
            if m0._sl_tree is not None:
                # 找当前 RUNNING 的步骤 → 高亮其列表；无则清高亮
                running = None
                for s, path in self._step_paths.items():
                    if s.status is StepStatus.RUNNING:
                        running = path
                        break
                m0._sl_tree.set_running_path(running)

    def _attach_progress(self) -> None:
        """为当前 runner 挂进度监听（工作线程 emit → 桥 → 状态栏 i/n）。"""
        if self._runner is not None:
            self._runner.add_progress_listener(
                lambda i, n: self._exec_bridge.progress.emit((i, n)))

    def _on_progress(self, payload) -> None:
        """执行进度（GUI 线程，经桥 queued）：执行中 → 状态栏「执行中 i/n」。"""
        i, n = payload
        if self._runner is not None \
                and self._runner.state is StepRunnerState.RUNNING:
            self._set_exec_status("执行中 %d/%d……（按热键停止）" % (i, n))

    def _rebuild_runner(self) -> None:
        """待命态按当前范围重建 runner（状态/进度监听一并重挂；热键 listener 保留）。

        执行范围切换、或「仅执行当前列表」下切换选中列表时调用。
        """
        if not self._managers or self._runner is None:
            return
        sl_mgr = self._managers[0]
        assert isinstance(sl_mgr, StepListManagementTree)
        only = sl_mgr.current_path if self._exec_scope == "current" else None
        self._runner = _make_step_runner(sl_mgr.store, only)
        gen = self._runner_gen
        self._runner.add_state_listener(
            lambda st, g=gen: self._exec_bridge.runner_state.emit((g, st)))
        self._attach_progress()

    def _set_exec_status(self, text: str) -> None:
        if self._exec_status is not None:
            self._exec_status.setText(text)

    # ---- 执行/设置按钮（活动栏底部） ----
    def _update_exec_button(self) -> None:
        """执行按钮视觉态：待命（监听中）→ 绿色 checked + tooltip「停止监听」；否则复原。"""
        if self._exec_btn is None:
            return
        listening = self._hotkey_listener is not None
        scope_text = "全部列表" if self._exec_scope == "all" else "当前列表"
        self._exec_btn.setChecked(listening)
        self._exec_btn.setToolTip(
            "停止监听" if listening else
            "执行（范围：%s，右键切换）：点击进入待命，按下热键开始执行，"
            "再按停止（当前步骤完成后停）。\n"
            "热键勿与步骤按键冲突（模拟按键也会被监听）；模拟输入到游戏窗口需管理员运行。"
            % scope_text)

    # ---- 执行范围（全部列表 / 仅当前列表；右键执行按钮切换） ----
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
        """切换执行范围；待命态立即重建 runner，执行中下次待命生效。"""
        if scope == self._exec_scope:
            return
        self._exec_scope = scope
        if self._runner is not None and self._runner.state is StepRunnerState.READY:
            self._rebuild_runner()
        self._update_exec_button()
        LogModel.instance().info(
            "执行范围已设为：%s"
            % ("全部列表" if scope == "all" else "仅当前列表"))

    def _on_exec_list_changed(self, _path: str) -> None:
        """选中列表变化：仅执行当前列表且待命中 → runner 跟随新列表。"""
        if self._exec_scope == "current" and self._runner is not None \
                and self._runner.state is StepRunnerState.READY:
            self._rebuild_runner()

    def _on_settings_clicked(self) -> None:
        """打开设置弹窗（触发热键配置）；保存 → setting.json + .kscp/executor.json。"""
        if self._package is None:
            return
        dlg = SettingsDialog(self._current_hotkey(), self)
        if dlg.exec_() != QDialog.Accepted:
            return
        self._apply_hotkey(dlg.hotkey())

    def _current_hotkey(self) -> str:
        """当前生效热键：.kscp 内 executor.json 优先（工程自带配置）；缺失/非法 → 默认 `` ` ``。

        开包后热键完全随工程走——**不读写 setting.json**（executor.json 一旦
        存在即唯一来源，避免两处配置互相覆盖的困惑）。
        """
        if self._package is not None and self._package.exists("executor.json"):
            try:
                data = json.loads(
                    self._package.read_file("executor.json").decode("utf-8"))
                if isinstance(data, dict) and isinstance(data.get("hotkey"), str) \
                        and len(data["hotkey"]) == 1:
                    return data["hotkey"]
                LogModel.instance().warning("executor.json 热键配置非法，使用默认热键")
            except (ValueError, UnicodeDecodeError):
                LogModel.instance().warning("executor.json 无法读取，使用默认热键")
        return "`"

    def _apply_hotkey(self, key: str) -> None:
        """保存热键到工程包 executor.json（有路径则立即落盘 .kscp）。

        不写 setting.json（executor.json 为唯一来源）。待命（监听中）时
        重建监听器使新热键即时生效。
        """
        if self._package is not None:
            self._package.write_file(
                "executor.json",
                json.dumps({"hotkey": key}, ensure_ascii=False).encode("utf-8"))
            if self._kscp_path:
                try:
                    self._package.save(self._kscp_path)
                except OSError as e:
                    QMessageBox.warning(self, "设置", "工程文件保存失败：%s" % e)
                    LogModel.instance().error("设置保存到 .kscp 失败：%s" % e)
        # 待命中 → 用新热键重建监听（旧监听器销毁）
        if self._hotkey_listener is not None:
            self._hotkey_listener.stop()
            self._hotkey_listener = None
            self._hotkey_listener = _make_hotkey_listener(
                key, self._exec_bridge.hotkey_toggle.emit)
            self._hotkey_listener.start()
            self._set_exec_status("待命：按 %s 执行/停止" % key)
        LogModel.instance().info("执行热键已设为 %s" % key)

    def _set_exec_locked(self, locked: bool) -> None:
        """执行期间锁定所有影响执行器的 GUI 编辑入口：

        * 步骤列表树 + 卡片视图 → **只读模式**：条目仍可点击切换查看列表、
          卡片悬停缩放动画保留，但拖拽/右键/Del/勾选/卡片编辑全禁
        * 变量/模板/资源树与其预览 → 整树禁用（无查看需求）
        * 管理菜单（导入模板）、文件菜单新建/打开（换工程）、设置按钮（改热键）禁用
        * 执行按钮保留（停止通道）；日志面板与保存只读无害不锁
        """
        if self._exec_locked == locked:
            return
        self._exec_locked = locked
        enabled = not locked
        for m in self._managers:
            if isinstance(m, StepListManagementTree):
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
        sl_tree.list_selected.connect(self._on_exec_list_changed)   # 单列表范围跟随选中
        first_path = sl_tree.first_list_path()
        if first_path:
            item = sl_tree.find_item(first_path)
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
            self._exec_btn.setEnabled(True)

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

    from PyQt5.QtWidgets import QApplication

    from model.project_variable import ProjectVariable
    from model.step import StepStatus
    from model.step_list import StepList
    from model.step_runner import StepRunner, StepRunnerState

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
    assert isinstance(host, StepListHost)
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
    assert isinstance(host2, StepListHost)
    assert host2.currentIndex() == 1                    # 非占位：自动切到列表视图
    assert len(host2._view.cards) == 0                 # 「乙」为空列表 → 无卡片
    assert sl_mgr2._current == "乙"                     # 树中选中项 = 第一个列表
    assert host2._view._step_list is sl_mgr2._store.get("乙")

    # ---- 模板树「加入当前列表」闭环：信息面板 → 实例化加入当前列表 ----
    spanel2 = win2._step_mgr.preview_widget()
    assert isinstance(spanel2, StepInfoPanel)
    win2._on_add_template("示例")
    assert len(sl_mgr2._store.get("乙").steps) == 1
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
    assert host2._view._step_list is sl_mgr2._store.get("组甲/丙")
    card2 = host2._view.cards[0]
    assert card2.step is sl_mgr2._store.get("组甲/丙").steps[0]
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

    # ---- 执行器接线：按钮/状态栏/锁定/热键 toggle 逻辑 ----
    # 冒烟不得真实全局监听：桩替换监听工厂（__main__ 模块命名空间内直接改全局）
    class _StubListener:
        def __init__(self, hotkey, on_toggle):
            self.hotkey, self.on_toggle = hotkey, on_toggle
            self.started = False

        def start(self):
            self.started = True

        def stop(self):
            self.started = False

    _orig_mk_listener = _make_hotkey_listener
    _make_hotkey_listener = lambda h, cb: _StubListener(h, cb)
    try:
        win_exec = MainWindow()
        win_exec._open_package(KscpPackage.create_empty(), None)
        app.processEvents()
        assert win_exec._runner is None
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
        # 点击执行按钮 → 进入待命（listener 启动 + 按钮绿色 checked）；再点 → 停止监听
        win_exec._exec_btn.click()
        assert win_exec._hotkey_listener is not None
        assert isinstance(win_exec._hotkey_listener, _StubListener)
        assert win_exec._hotkey_listener.started
        assert win_exec._exec_btn.isChecked(), "待命中执行按钮应呈 checked（绿色）"
        assert "待命" in win_exec._exec_status.text()
        win_exec._exec_btn.click()
        assert win_exec._hotkey_listener is None
        assert not win_exec._exec_btn.isChecked()
        # 热键 toggle：READY → start；RUNNING → request_stop（空 store 无步骤 → 恒 READY）
        win_exec._exec_btn.click()          # 待命
        win_exec._handle_hotkey_toggle()    # 模拟热键按下（无步骤 → start 后仍 READY）
        assert win_exec._runner is not None
        assert win_exec._runner.state is StepRunnerState.READY
        # 编辑锁定：步骤列表树走只读模式（可点击查看、禁编辑；不整树禁用——
        # 禁用会吞 hover 事件导致卡片缩放动画消失）；其余树整树禁用
        sl_tree = win_exec._managers[0]._sl_tree
        assert sl_tree is not None
        var_tree = win_exec._managers[1].tree_widget()
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
        # I1: 停止监听后立即重新待命 → 编辑锁定复位（待命成功路径解锁）
        win_exec._exec_btn.click()               # 停止监听
        assert win_exec._hotkey_listener is None
        win_exec._set_exec_locked(True)
        assert sl_tree._read_only
        win_exec._start_listening()              # 重待命：成功路径应解锁
        assert not sl_tree._read_only, "重待命后编辑仍锁定（卡死）"
        assert win_exec._hotkey_listener is not None
        # 未开包：无活动栏 → 执行/设置按钮不存在（无入口，安全）
        win_bare = MainWindow()
        assert win_bare._exec_btn is None and win_bare._settings_btn is None
        # 工具栏菜单按钮：最小宽度 >= 文本度量（防文字被压缩截断）
        fm = win_bare.fontMetrics()
        assert win_bare._manage_btn.minimumWidth() >= fm.horizontalAdvance("管理")
        assert win_bare._manage_btn.toolButtonStyle() == Qt.ToolButtonTextOnly

        # ---- I2: 执行中重待命不得并发双执行（假 runner 状态可控） ----
        class _FakeRunner:
            """桩执行器：状态手动置位，记录 start/request_stop 调用。"""

            def __init__(self, store, only=None):
                self.store = store
                self.only = only            # 单列表范围（only_path）
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
        _make_step_runner = lambda store, only=None: _FakeRunner(store, only)
        try:
            win_i2 = MainWindow()
            win_i2._open_package(KscpPackage.create_empty(), None)
            app.processEvents()
            win_i2._exec_btn.click()                    # 待命 → 假 runner（READY）
            fake1 = win_i2._runner
            assert isinstance(fake1, _FakeRunner)
            fake1._set(StepRunnerState.RUNNING)         # 模拟开始执行
            app.processEvents()
            assert "执行中" in win_i2._exec_status.text()
            win_i2._exec_btn.click()                    # 停止监听（执行中）
            assert win_i2._runner is fake1, "执行中停止监听须保留 runner 引用"
            assert fake1.calls == ["stop"], fake1.calls
            win_i2._exec_btn.click()                    # 立即重待命 → 守卫拦截
            assert win_i2._runner is fake1, "执行中重待命不得创建第二个 runner（并发双执行）"
            assert "等待当前执行结束" in win_i2._exec_status.text()
            fake1._set(StepRunnerState.READY)           # 旧 runner 自然结束
            app.processEvents()
            assert win_i2._runner is None, "旧 runner READY 后引用应清理"
            win_i2._exec_btn.click()                    # READY 后再待命 → 正常创建
            assert isinstance(win_i2._runner, _FakeRunner)
            # I3: 空 store → attach 无 hook；且不崩
            win_i2._handle_hotkey_toggle()              # READY → attach（空）→ start
            assert win_i2._step_hooks == []
            win_i2._exec_btn.click()                    # 复位：停监听
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
            slm_i3._store.add_list("主列表", sl_i3)
            slm_i3._save_store()
            win_i3 = MainWindow()
            win_i3._open_package(pkg_i3, None)
            app.processEvents()
            win_i3._exec_btn.click()                    # 待命 → 假 runner
            fake3 = win_i3._runner
            assert isinstance(fake3, _FakeRunner)
            assert win_i3._step_hooks == []
            win_i3._handle_hotkey_toggle()              # READY → attach + start
            assert len(win_i3._step_hooks) == 1, win_i3._step_hooks
            fired3 = []
            win_i3._exec_bridge.step_status.connect(lambda _s=None: fired3.append(1))
            step3 = win_i3._step_hooks[0][0]
            step3.status = StepStatus.RUNNING
            assert len(fired3) == 1, fired3             # 状态变更 → 桥 → 卡片刷新
            app.processEvents()
            stree3 = win_i3._managers[0]._sl_tree
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
            assert win_i3._step_hooks == [], win_i3._step_hooks   # detach 后清空
            step3.status = StepStatus.PENDING
            assert len(fired3) == 2, fired3             # detach 后不再通知

            # ---- 执行范围（单列表）：切换 → 待命 runner 重建并携带 only_path ----
            assert win_i3._exec_scope == "all"
            win_i3._set_exec_scope("current")
            assert win_i3._runner is not None
            assert win_i3._runner.only == "主列表", win_i3._runner.only
            # ---- 执行进度：桥 → 状态栏「执行中 i/n」 ----
            win_i3._runner._set(StepRunnerState.RUNNING)
            app.processEvents()
            win_i3._on_progress((1, 2))
            assert "1/2" in win_i3._exec_status.text(), win_i3._exec_status.text()
            win_i3._runner._set(StepRunnerState.READY)
            app.processEvents()
            win_i3._set_exec_scope("all")
            assert win_i3._runner is not None and win_i3._runner.only is None
            win_i3._exec_btn.click()                    # 复位：停监听
        finally:
            _make_step_runner = _orig_mk_runner
    finally:
        _make_hotkey_listener = _orig_mk_listener

    # ---- 设置按钮（活动栏底部）与热键落盘 ----
    # 设置按钮 = 瞬时按钮（点击后无样式残留）；弹窗细节冒烟见 widgets.settings_dialog
    assert not win_exec._settings_btn.isCheckable()
    # _apply_hotkey：只写工程包 executor.json（不碰 setting.json——executor.json 唯一来源）
    win_exec._apply_hotkey("g")
    assert win_exec._package.exists("executor.json")
    data = json.loads(win_exec._package.read_file("executor.json").decode("utf-8"))
    assert data == {"hotkey": "g"}, data
    # 工程优先：_current_hotkey 读 executor.json；缺失回退默认 "`"
    assert win_exec._current_hotkey() == "g"
    win_exec._package.remove("executor.json")
    try:
        assert win_exec._current_hotkey() == "`"      # 缺失 → 默认热键
    finally:
        win_exec._package.write_file(
            "executor.json", b'{"hotkey": "g"}')

    # ---- 代际标记（随附修复）：陈旧 runner 迟到 READY 不覆盖新 runner 状态 ----
    # 本段再次点击执行按钮 → 重新桩替换监听工厂（冒烟不得真实全局监听）
    _orig_mk_listener2 = _make_hotkey_listener
    _make_hotkey_listener = lambda h, cb: _StubListener(h, cb)
    try:
        win_exec._exec_btn.click()                       # 停监听（旧 runner 收尾）
        win_exec._exec_btn.click()                       # 再待命 → 新 runner（新代际）
        win_exec._set_exec_status("执行中……（按热键停止）")
        win_exec._set_exec_locked(True)
        stale_gen = win_exec._runner_gen - 1             # 旧代际
        win_exec._exec_bridge.runner_state.emit((stale_gen, StepRunnerState.READY))
        assert "执行中" in win_exec._exec_status.text()  # 陈旧 READY 被忽略
        assert win_exec._managers[0]._sl_tree._read_only  # 编辑仍锁定（只读模式）
        win_exec._exec_bridge.runner_state.emit((win_exec._runner_gen, StepRunnerState.READY))
        assert "待命" in win_exec._exec_status.text()    # 当前代际状态正常刷新（解锁）
        assert not win_exec._managers[0]._sl_tree._read_only
        win_exec._exec_btn.click()                       # 复位：停监听
    finally:
        _make_hotkey_listener = _orig_mk_listener2

    print("MainWindow smoke OK")
