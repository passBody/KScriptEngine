# -*- coding: utf-8 -*-
"""
管理树（主窗口左侧管理树簇）
============================

:class:`ManagementTree` 为管理树抽象：每个管理树提供左侧树控件
``tree_widget()`` 与中间预览 ``preview_widget()``（懒构建并缓存）。
当前实现资源 / 变量 / 步骤模板 / 步骤列表四棵管理树；步骤列表管理树
（:class:`StepListManagementTree`）= 左侧 :class:`StepListTreeWidget` +
宿主 :class:`StepListHost`（承载 :class:`StepListView`），与变量管理树
共享同一棵变量树（变量变更 → 卡片重检颜色）。
"""

from __future__ import annotations

from typing import Callable, Optional

from PyQt5.QtCore import QTimer, Qt, pyqtSignal
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import (
    QHBoxLayout, QLabel, QLineEdit, QPushButton, QStackedWidget, QVBoxLayout,
    QWidget,
)

from model.kscp_package import KscpPackage
from model.log_model import LogModel
from model.step_list import StepList
from model.step_list_store import StepListStore
from model.step_manager import StepManager
from model.variable_tree import VariableTree
from widgets.resource_tree_widget import ResourceTreeWidget
from widgets.variable_tree_widget import VariableTreeWidget
from widgets.step_tree_widget import StepTreeWidget
from widgets.step_list_tree_widget import StepListTreeWidget
from widgets.step_list_view import StepClipboard, StepListView
from widgets.ui_common import make_icon, placeholder

__all__ = [
    "ManagementTree", "PlaceholderManagementTree", "ResourceManagementTree",
    "StepListHost", "StepListManagementTree", "StepManagementTree",
    "VariableManagementTree",
]


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
        return make_icon("default")

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
        return make_icon("resource")

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
        return make_icon("variable")

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
        return make_icon("template")

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
        self._host: Optional[StepListHost] = None
        self._current: Optional[str] = None
        self._save_timer: Optional[QTimer] = None   # 落盘防抖（评审#10）

    @property
    def store(self) -> StepListStore:
        """步骤列表存储（执行器数据源）。"""
        return self._store

    @property
    def current_path(self) -> Optional[str]:
        """当前选中的步骤列表路径（「仅执行当前列表」范围用）；未选 → None。"""
        return self._current

    def set_read_only(self, ro: bool) -> None:
        """执行期只读：树可点击切换查看列表（禁拖拽/右键/快捷键/勾选），
        卡片视图禁编辑保留悬停动画。"""
        if self._sl_tree is not None:
            self._sl_tree.set_read_only(ro)
        if self._host is not None:
            self._host.set_read_only(ro)

    def icon(self) -> QIcon:
        return make_icon("step")

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
        """视图内容编辑（io/签名/激活切换）→ 防抖落盘 + 树勾选框同步激活态。

        防抖 500ms：连续键入合并为一次写盘（此前每键一次全量序列化——评审#10）。
        """
        if self._sl_tree is not None:
            self._sl_tree.refresh_active_marks()
        if self._save_timer is None:
            self._save_timer = QTimer()
            self._save_timer.setSingleShot(True)
            self._save_timer.setInterval(500)
            self._save_timer.timeout.connect(self._save_store)
        self._save_timer.start()

    def preview_widget(self) -> QWidget:
        if self._host is None:
            self._host = StepListHost(
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

    def add_template_to_current(self, path: str) -> bool:
        """模板树「加入当前列表」闭环：实例化模板并追加到当前选中列表。

        未选中列表 / 列表被删 / 模板创建失败 → 日志记录并返回 False（不弹窗，
        由调用方决定 UI 提示）；成功刷新宿主卡片与树标记并返回 True。
        """
        if self._current is None:
            LogModel.instance().warning("加入当前列表：未选中任何步骤列表")
            return False
        try:
            step = self._mgr.create_step(path)
            lst = self._store.get(self._current)
        except (ValueError, FileNotFoundError) as e:
            LogModel.instance().error("加入当前列表失败：%s" % e)
            return False
        lst.add(step)
        self._save_store()
        if self._host is not None:
            self._host.set_list(lst, self._mgr)
        if self._sl_tree is not None:
            self._sl_tree.refresh_error_marks()
            self._sl_tree.refresh_active_marks()
        LogModel.instance().info("模板「%s」已加入列表「%s」" % (path, self._current))
        return True


class StepListHost(QStackedWidget):
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

    def set_read_only(self, ro: bool) -> None:
        """执行期只读转发：卡片视图禁编辑但保留悬停动画。"""
        self._view.set_read_only(ro)


class PlaceholderManagementTree(ManagementTree):
    """占位管理树：演示切换 + 预留接口，后续替换为真实实现。"""

    def __init__(self, name: str, icon_kind: str = "default") -> None:
        super().__init__(name)
        self._icon_kind = icon_kind

    def icon(self) -> QIcon:
        return make_icon(self._icon_kind)

    def _build_tree(self) -> QWidget:
        return placeholder("「%s管理树」待实现" % self._name)

    def _build_preview(self) -> QWidget:
        return placeholder("「%s管理树」预览 待实现" % self._name)


# ================================================================
# 冒烟演示：直接 ``python -m widgets.management_trees`` 运行
# ================================================================
if __name__ == "__main__":
    import sys

    from PyQt5.QtWidgets import QApplication, QLabel

    from model.kscp_package import KscpPackage
    from model.project_variable import ProjectVariable
    from model.step_list import StepList
    from model.variable_tree import VariableTree

    app = QApplication.instance() or QApplication(sys.argv)

    pkg = KscpPackage.create_empty()
    tree = VariableTree.create_empty()
    tree.add("n1", ProjectVariable.create("number", 100, pkg))

    # 四棵管理树：名称 + 图标 + 懒构建（tree_widget 返回对应控件）
    r = ResourceManagementTree(pkg)
    assert r.name == "资源" and not r.icon().isNull()
    assert isinstance(r.tree_widget(), ResourceTreeWidget)
    assert r.preview_widget() is r._preview          # 懒构建缓存

    v = VariableManagementTree(pkg, tree)
    assert v.name == "变量"
    assert isinstance(v.tree_widget(), VariableTreeWidget)

    t = StepManagementTree(pkg)
    assert t.name == "步骤模板"
    assert isinstance(t.tree_widget(), StepTreeWidget)

    slm = StepListManagementTree(pkg, tree)
    assert slm.name == "步骤列表"
    assert isinstance(slm.tree_widget(), StepListTreeWidget)
    host = slm.preview_widget()
    assert isinstance(host, StepListHost)
    assert host.currentIndex() == 0                 # 未选列表 → 占位页

    # 列表选择联动：添加列表 → 刷新树 → 选中 → 宿主切换
    sl = StepList.create_empty()
    slm._store.add_list("主列表", sl)
    slm._save_store()
    tw = slm.tree_widget()
    tw.refresh()
    tw.list_selected.emit("主列表")
    assert host.currentIndex() == 1
    assert host._view._step_list is sl

    # 落盘防抖（评审#10）：编辑 → 500ms 单发定时器，到期才写盘
    slm._on_edited()
    assert slm._save_timer is not None and slm._save_timer.isActive()
    assert slm._save_timer.interval() == 500 and slm._save_timer.isSingleShot()
    slm._save_timer.stop()
    slm._save_timer.timeout.emit()          # 模拟防抖到期 → 落盘（不崩）

    # ---- add_template_to_current：模板树「加入当前列表」闭环 ----
    _GOOD = '''# -*- coding: utf-8 -*-
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
    description = "演示模板"
    input_class = _DemoInput
    output_class = _DemoOutput

    def run(self) -> int:
        self.outputs.total = self.inputs.count * 2
        return 1
'''
    pkg2 = KscpPackage.create_empty()
    pkg2.write_file("actions/示例.py", _GOOD.encode("utf-8"))
    tree2 = VariableTree.create_empty()
    slm2 = StepListManagementTree(pkg2, tree2)
    sl2 = StepList.create_empty()
    slm2._store.add_list("主列表", sl2)
    slm2._save_store()
    host2 = slm2.preview_widget()               # 先建宿主再选中（联动发生在选中时）
    tw2 = slm2.tree_widget()
    tw2.refresh()
    tw2.list_selected.emit("主列表")
    assert host2.currentIndex() == 1
    assert slm2.add_template_to_current("示例") is True
    assert len(sl2.steps) == 1
    assert len(host2._view._cards) == 1              # 宿主刷新出新卡片
    # 未选中列表 → False + 日志（不弹窗）
    LogModel.instance().clear()
    slm2._current = None
    assert slm2.add_template_to_current("示例") is False
    assert any("未选中任何步骤列表" in e.message
               for e in LogModel.instance().entries)

    # 占位管理树：占位页含「待实现」提示
    ph = PlaceholderManagementTree("演示")
    assert ph.name == "演示" and not ph.icon().isNull()
    lbl = ph.tree_widget().findChild(QLabel)
    assert lbl is not None and "待实现" in lbl.text()

    print("management_trees smoke OK")
