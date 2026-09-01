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

from typing import Callable, Dict, List, Optional

from PyQt5.QtCore import QObject, QTimer, Qt, pyqtSignal
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import (
    QDialog, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QMenu, QPushButton,
    QStackedWidget, QToolButton, QVBoxLayout, QWidget,
)

from model.工程.kscp_package import KscpPackage
from model.log_model import LogModel
from model.步骤.step_list import StepList
from model.步骤.step_list_store import StepListStore
from model.步骤.step_page_store import StepPageStore
from model.步骤.step_manager import StepManager
from model.合成卡片.composite_card import repoint_refs, repoint_param_refs, CompositeCard
from model.合成卡片.composite_card_store import CompositeCardStore
from model.合成卡片.composite_signature import CompositeSignature, LocalVar
from model.合成卡片.composite_local_tree import build_validation_tree
from model.变量.variable_tree import VariableTree
from widgets.树.resource_tree_widget import ResourceTreeWidget
from widgets.树.variable_tree_widget import VariableTreeWidget
from widgets.树.step_tree_widget import StepTreeWidget
from widgets.树.step_list_tree_widget import StepListTreeWidget
from widgets.树.composite_tree_widget import CompositeTreeWidget
from widgets.合成卡片.composite_signature_widget import CompositeSignatureDialog
from widgets.合成卡片.composite_local_picker import make_composite_local_picker
from widgets.卡片.step_list_view import StepClipboard, StepListView
from widgets.通用.ui_common import make_icon, placeholder

__all__ = [
    "ManagementTree", "PlaceholderManagementTree", "ResourceManagementTree",
    "StepListHost", "StepListManagementTree", "StepManagementTree",
    "VariableManagementTree", "CompositeManagementTree",
]


class ManagementTree(QObject):
    """管理树基类（QObject：子类可定义 pyqtSignal）：提供左侧树控件 + 中间预览控件。

    子类实现 :meth:`_build_tree` / :meth:`_build_preview`（或重写
    :meth:`tree_widget` / :meth:`preview_widget`）。控件懒构建并缓存。
    """

    def __init__(self, name: str) -> None:
        super().__init__()
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

    def _ensure(self, attr: str, builder: Callable[[], QWidget]) -> QWidget:
        """懒构建缓存（评审#20）：``attr`` 未建 → ``builder()`` 并缓存后返回。

        各子类的树/预览懒缓存统一经此实现，不再各自重复 if-None 样板。
        """
        w = getattr(self, attr, None)
        if w is None:
            w = builder()
            setattr(self, attr, w)
        return w


class ResourceManagementTree(ManagementTree):
    """资源管理树：``ResourceTreeWidget`` + 其预览面板。"""

    def __init__(self, package: KscpPackage) -> None:
        super().__init__("资源")
        self._package = package
        self._rtree: Optional[ResourceTreeWidget] = None

    def icon(self) -> QIcon:
        return make_icon("resource")

    def tree_widget(self) -> QWidget:
        w = self._ensure("_rtree", lambda: ResourceTreeWidget(self._package))
        assert isinstance(w, ResourceTreeWidget)
        return w

    def preview_widget(self) -> QWidget:
        r = self.tree_widget()
        assert isinstance(r, ResourceTreeWidget)
        return self._ensure("_preview", r.preview_widget)


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
        w = self._ensure(
            "_vtree", lambda: VariableTreeWidget(self._package, self._tree))
        assert isinstance(w, VariableTreeWidget)
        return w

    def preview_widget(self) -> QWidget:
        v = self.tree_widget()
        assert isinstance(v, VariableTreeWidget)
        return self._ensure("_preview", v.preview_widget)


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
        w = self._ensure("_stree", lambda: StepTreeWidget(self._package, self._mgr))
        assert isinstance(w, StepTreeWidget)
        return w

    def preview_widget(self) -> QWidget:
        s = self.tree_widget()
        assert isinstance(s, StepTreeWidget)
        return self._ensure("_preview", s.preview_widget)


class StepListManagementTree(ManagementTree):
    """步骤列表管理树：执行列表页容器（标题右击重命名 + 下拉切换 +
    添加页/删除该页）+ 每页一棵缓存的 StepListTreeWidget + 共享宿主。

    页信号（main_widget 接线）：``page_changed/page_added/page_renamed/
    page_removed``；``list_selected`` 为当前页选中列表路径的跨页统一出口。
    """

    page_changed = pyqtSignal(str)          # 当前页切换（新页名）
    page_added = pyqtSignal(str)
    page_renamed = pyqtSignal(str, str)     # (old, new)
    page_removed = pyqtSignal(str)
    list_selected = pyqtSignal(str)         # 当前页选中列表路径

    def __init__(self, package: KscpPackage, tree: VariableTree,
                 mgr: Optional[StepManager] = None,
                 composite_store: Optional[CompositeCardStore] = None,
                 clipboard: Optional[StepClipboard] = None) -> None:
        super().__init__("步骤列表")
        self._package = package
        self._tree = tree
        if mgr is not None:
            self._mgr = mgr   # 与步骤模板树共享同一工厂（模板只加载一次）
        else:
            self._mgr = StepManager(package, tree)
            self._mgr.load()
        # step_list.json：v2 = 顶层执行列表页；v1（顶层含列表叶子）自动包成
        # 单页「执行列表1」。文件已存在时打开不改写（v1 文件保持原样，见
        # StepPageStore docstring 的格式检测说明）
        if package.exists("step_list.json"):
            self._page_store = StepPageStore.from_json(
                package.read_file("step_list.json"), self._mgr)
        else:
            self._page_store = StepPageStore.create_empty()
            self._save_store()
        self._page_store.ensure_default_page()
        self._current_page: str = self._page_store.page_names()[0]
        self._cstore = composite_store   # 合成卡片存储（阶段4：选择器插入合成卡片用）
        self._clipboard = clipboard if clipboard is not None else StepClipboard()
        self._page_trees: Dict[str, StepListTreeWidget] = {}   # 页名 → 树（懒建缓存）
        self._page_current: Dict[str, Optional[str]] = {}      # 每页各自记住选中列表
        self._page_container: Optional[QWidget] = None
        self._page_title: Optional[QLabel] = None
        self._page_menu_btn: Optional[QToolButton] = None
        self._page_stack: Optional[QStackedWidget] = None
        self._add_page_btn: Optional[QPushButton] = None
        self._del_page_btn: Optional[QPushButton] = None
        self._host: Optional[StepListHost] = None
        self._current: Optional[str] = None   # 当前页内选中列表路径
        self._read_only = False
        self._save_timer: Optional[QTimer] = None   # 落盘防抖（评审#10）

    # ---- 页/存储访问 ----
    @property
    def page_store(self) -> StepPageStore:
        return self._page_store

    @property
    def current_page(self) -> str:
        return self._current_page

    @property
    def store(self) -> StepListStore:
        """当前页的步骤列表存储（执行器数据源；兼容既有调用方）。"""
        return self._page_store.get_page(self._current_page)

    @property
    def current_path(self) -> Optional[str]:
        """当前页内选中的步骤列表路径（「仅执行当前列表」范围用）；未选 → None。"""
        return self._current

    def current_tree(self) -> Optional[StepListTreeWidget]:
        """当前页的树（未构建 → None）。"""
        return self._page_trees.get(self._current_page)

    def trees(self) -> List[StepListTreeWidget]:
        """全部已构建的页树（执行期只读/高亮清扫用）。"""
        return list(self._page_trees.values())

    def set_read_only(self, ro: bool) -> None:
        """执行期只读：全部页树可点击切换查看（禁拖拽/右键/快捷键/勾选）、
        卡片视图禁编辑保留悬停动画；添加页/删除该页禁用，标题重命名禁用
        （handler 内守卫）；下拉切换保持可用（执行中可查看其他页）。"""
        self._read_only = ro
        for t in self._page_trees.values():
            t.set_read_only(ro)
        if self._host is not None:
            self._host.set_read_only(ro)
        if self._add_page_btn is not None:
            self._add_page_btn.setEnabled(not ro)
            self._del_page_btn.setEnabled(not ro)

    def icon(self) -> QIcon:
        return make_icon("step")

    def _save_store(self) -> None:
        self._package.write_file("step_list.json", self._page_store.to_json_bytes())

    def refresh_cards(self) -> None:
        """变量树变化 → 宿主重检卡片颜色（不重建）。"""
        if self._host is not None:
            self._host.refresh_validity()

    # ---- 页容器构建 ----
    def tree_widget(self) -> QWidget:
        if self._page_container is None:
            self._build_page_container()
        assert self._page_container is not None
        return self._page_container

    def _build_page_container(self) -> None:
        """树面板 = 标题行（标题右击重命名 + 下拉切换）+ 页操作按钮行
        （添加页/删除该页）+ QStackedWidget（每页一棵树）。"""
        box = QWidget()
        lay = QVBoxLayout(box)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)

        title_row = QHBoxLayout()
        self._page_title = QLabel(self._current_page)
        self._page_title.setStyleSheet(
            "font-weight:bold; font-size:14px; color:#333;")
        self._page_title.setToolTip("右击重命名当前执行列表")
        self._page_title.setContextMenuPolicy(Qt.CustomContextMenu)
        self._page_title.customContextMenuRequested.connect(
            self._on_page_title_menu)
        title_row.addWidget(self._page_title)
        title_row.addStretch()
        self._page_menu_btn = QToolButton()
        self._page_menu_btn.setText("切换 ▾")
        self._page_menu_btn.setPopupMode(QToolButton.InstantPopup)
        self._page_menu_btn.setToolTip("切换到其他执行列表")
        self._page_menu_btn.setMenu(self._build_page_menu())
        title_row.addWidget(self._page_menu_btn)
        lay.addLayout(title_row)

        btn_row = QHBoxLayout()
        self._add_page_btn = QPushButton("添加页")
        self._add_page_btn.setToolTip("新建一个执行列表并跳转过去")
        self._add_page_btn.clicked.connect(self._on_add_page_clicked)
        self._del_page_btn = QPushButton("删除该页")
        self._del_page_btn.setToolTip("删除当前执行列表（至少保留一页）")
        self._del_page_btn.clicked.connect(self._on_del_page_clicked)
        btn_row.addWidget(self._add_page_btn)
        btn_row.addWidget(self._del_page_btn)
        btn_row.addStretch()
        lay.addLayout(btn_row)

        self._page_stack = QStackedWidget()
        for name in self._page_store.page_names():
            self._page_stack.addWidget(self._tree_for_page(name))
        lay.addWidget(self._page_stack, 1)
        self._page_container = box

    def _tree_for_page(self, name: str) -> StepListTreeWidget:
        """页名 → 缓存的树实例（闭包携带页名转发信号）。"""
        if name not in self._page_trees:
            tree = StepListTreeWidget(
                self._page_store.get_page(name), self._mgr, self._clipboard,
                self._save_store, None)
            tree.list_selected.connect(
                lambda path, n=name: self._on_list_selected(n, path))
            tree.store_changed.connect(
                lambda n=name: self._on_store_changed(n))
            self._page_trees[name] = tree
        return self._page_trees[name]

    def _build_page_menu(self) -> QMenu:
        """下拉切换菜单：全部页标题、当前页勾选。"""
        menu = QMenu(self._page_menu_btn)
        for name in self._page_store.page_names():
            act = menu.addAction(name)
            act.setCheckable(True)
            act.setChecked(name == self._current_page)
            act.triggered.connect(lambda _=False, n=name: self._activate_page(n))
        return menu

    def _refresh_page_menu(self) -> None:
        if self._page_menu_btn is not None:
            self._page_menu_btn.setMenu(self._build_page_menu())

    # ---- 页操作 ----
    def _activate_page(self, name: str) -> None:
        """切换当前页：栈切树、标题/菜单刷新、恢复该页选中列表（无则首个）、
        宿主重绑、emit page_changed。"""
        if name == self._current_page or name not in self._page_store.page_names():
            return
        self._current_page = name
        tree = self._tree_for_page(name)
        self._page_stack.setCurrentWidget(tree)
        if self._page_title is not None:
            self._page_title.setText(name)
        self._refresh_page_menu()
        if name in self._page_current:
            self._current = self._page_current[name]
            self._show_current()
        else:
            # 首次进入该页：自动选中首个列表（同打开工程行为）；无列表 → 占位
            self._current = None
            first = tree.first_list_path()
            if first:
                item = tree.find_item(first)
                if item is not None:
                    tree.setCurrentItem(item)   # 触发 list_selected → 宿主联动
            else:
                self._show_current()            # 空页 → 宿主回占位页
        self.page_changed.emit(name)

    def _on_page_title_menu(self, pos) -> None:
        """标题右击菜单：重命名（执行期只读守卫）。"""
        if self._read_only or self._page_title is None:
            return
        menu = QMenu(self._page_title)
        a_rename = menu.addAction("重命名")
        a = menu.exec_(self._page_title.mapToGlobal(pos))
        if a is a_rename:
            self._rename_current_page()

    def _rename_current_page(self) -> None:
        """重命名当前页；重名/非法名 → 日志报错并阻止（不落盘、不切换）。"""
        old = self._current_page
        new, ok = QInputDialog.getText(
            self._page_container, "重命名执行列表", "标题：", text=old)
        if not ok or not new.strip() or new.strip() == old:
            return
        new = new.strip()
        try:
            self._page_store.rename_page(old, new)
        except (ValueError, FileExistsError) as e:
            LogModel.instance().error("重命名执行列表失败：%s" % e)
            return
        self._page_trees[new] = self._page_trees.pop(old)     # 缓存树/选中记录重键
        if old in self._page_current:
            self._page_current[new] = self._page_current.pop(old)
        self._current_page = new
        if self._page_title is not None:
            self._page_title.setText(new)
        self._refresh_page_menu()
        self._save_store()
        self.page_renamed.emit(old, new)

    def _on_add_page_clicked(self) -> None:
        """添加页：命名（默认建议「执行列表N」）→ 建页 → 跳转新页。
        重名/非法名 → 日志报错并阻止。"""
        if self._read_only:
            return
        base = "执行列表%d" % (len(self._page_store.page_names()) + 1)
        name, ok = QInputDialog.getText(
            self._page_container, "添加执行列表", "标题：", text=base)
        if not ok or not name.strip():
            return
        name = name.strip()
        try:
            self._page_store.add_page(name)
        except (ValueError, FileExistsError) as e:
            LogModel.instance().error("添加执行列表失败：%s" % e)
            return
        self._page_stack.addWidget(self._tree_for_page(name))
        self._save_store()
        self.page_added.emit(name)
        self._activate_page(name)              # 跳转到新页

    def _on_del_page_clicked(self) -> None:
        """删除当前页（守卫：最后一页拒绝）；成功 → 激活首剩页。"""
        if self._read_only:
            return
        name = self._current_page
        try:
            self._page_store.remove_page(name)
        except (ValueError, FileNotFoundError) as e:
            LogModel.instance().error("删除执行列表失败：%s" % e)
            return
        tree = self._page_trees.pop(name, None)
        if tree is not None:
            self._page_stack.removeWidget(tree)
            tree.deleteLater()
        self._page_current.pop(name, None)
        self._save_store()
        self.page_removed.emit(name)
        self._current_page = ""                # 强制走切换路径
        self._activate_page(self._page_store.page_names()[0])

    # ---- 编辑/落盘 ----
    def _on_edited(self) -> None:
        """视图内容编辑（io/签名/激活切换）→ 防抖落盘 + 树勾选框同步激活态。

        防抖 500ms：连续键入合并为一次写盘（此前每键一次全量序列化——评审#10）。
        """
        t = self.current_tree()
        if t is not None:
            t.refresh_active_marks()
        if self._save_timer is None:
            self._save_timer = QTimer()
            self._save_timer.setSingleShot(True)
            self._save_timer.setInterval(500)
            self._save_timer.timeout.connect(self._save_store)
        self._save_timer.start()

    def preview_widget(self) -> QWidget:
        if self._host is None:
            self._host = StepListHost(
                self._mgr, self._clipboard, self._on_edited, None,
                composite_store=self._cstore)
            # 视图错误数变化 → 重标左侧树错误条目（树可能尚未构建，判空）
            self._host.errors_changed.connect(self._refresh_tree_marks)
        assert self._host is not None
        return self._host

    def _refresh_tree_marks(self, _n: int) -> None:
        """卡片错误数变化 → 按列表 io 校验重标树错误条目（红加粗，见 refresh_error_marks）。"""
        t = self.current_tree()
        if t is not None:
            t.refresh_error_marks()

    # ---- 宿主联动 ----
    def _show_current(self) -> None:
        """按当前页当前选中列表重绑宿主；未选/被删 → 占位页。"""
        if self._host is None:
            return
        if self._current is None:
            self._host.set_list(None)
            return
        try:
            self._host.set_list(self.store.get(self._current), self._mgr)
        except FileNotFoundError:
            self._host.set_list(None)

    def _on_list_selected(self, page: str, path: str) -> None:
        """某页树选中列表：记录该页选中态；当前页 → 联动宿主 + 统一出口信号。"""
        self._page_current[page] = path
        if page != self._current_page:
            return
        self._current = path
        self._show_current()
        self.list_selected.emit(path)

    def _on_store_changed(self, page: str) -> None:
        """当前页树内容变更（勾选激活/添加/粘贴/删除）→ 宿主同步当前列表。

        删除 → 占位页；其余（尤其树勾选框切换激活，list_selected 不触发）
        → 重建卡片画面，激活切换立即刷新视图。后台页变更不联动（宿主只显示当前页）。
        """
        if page != self._current_page or self._host is None or self._current is None:
            return
        try:
            lst = self.store.get(self._current)
        except FileNotFoundError:
            self._host.set_list(None)
        else:
            self._host.set_list(lst, self._mgr)

    def repoint_composite_refs(self, old_path: str, new_path: str) -> int:
        """合成卡片重命名时，把**全部页**内引用 ``old_path`` 的条目改指
        ``new_path``；返回改动数。

        改的是 :class:`CompositeCard` 实例的 ``ref/name``（步骤列表里只存标记串，
        ``to_format_string`` 用 ``self.ref``，故改实例即改未来落盘的标记）。
        改完落盘 ``step_list.json`` 并重建当前卡片画面（卡片名立即更新）。
        """
        n = 0
        for name in self._page_store.page_names():
            n += repoint_refs(self._page_store.get_page(name), old_path, new_path)
        if n:
            self._save_store()
            self._on_store_changed(self._current_page)   # 重绑宿主：卡片名立即更新
        return n

    def resync_composite_steps(self, ref: str) -> None:
        """合成卡片签名变更后，重同步**全部页**内引用该卡的 CompositeCard 步骤 io。

        对 ref 匹配的 CompositeCard 步骤调 resync_io（按新签名重建类型化 io，
        保留已填值）。当前页当前列表有变化 → 刷新宿主卡片（io 变了）。
        """
        current_changed = False
        for name in self._page_store.page_names():
            sl_store = self._page_store.get_page(name)
            for path, is_group in sl_store.walk():
                if is_group:
                    continue
                try:
                    sl = sl_store.get(path)
                except FileNotFoundError:
                    continue
                for step in sl.steps:
                    if isinstance(step, CompositeCard) and step.ref == ref:
                        if step.resync_io() \
                                and name == self._current_page \
                                and path == self._current:
                            current_changed = True
        if current_changed and self._host is not None and self._current is not None:
            try:
                sl = self.store.get(self._current)
            except FileNotFoundError:
                return
            self._host.set_list(sl, self._mgr)

    def add_template_to_current(self, path: str) -> bool:
        """模板树「加入当前列表」闭环：实例化模板并追加到当前页选中列表。

        未选中列表 / 列表被删 / 模板创建失败 → 日志记录并返回 False（不弹窗，
        由调用方决定 UI 提示）；成功刷新宿主卡片与树标记并返回 True。
        """
        if self._current is None:
            LogModel.instance().warning("加入当前列表：未选中任何步骤列表")
            return False
        try:
            step = self._mgr.create_step(path)
            lst = self.store.get(self._current)
        except (ValueError, FileNotFoundError) as e:
            LogModel.instance().error("加入当前列表失败：%s" % e)
            return False
        lst.add(step)
        self._save_store()
        if self._host is not None:
            self._host.set_list(lst, self._mgr)
        t = self.current_tree()
        if t is not None:
            t.refresh_error_marks()
            t.refresh_active_marks()
        LogModel.instance().info("模板「%s」已加入列表「%s」" % (path, self._current))
        return True


class CompositeManagementTree(ManagementTree):
    """合成卡片管理树：左树 + 中（签名按钮 + body 宿主）。

    v2：预览 = 容器（上「编辑签名…」按钮、下 StepListHost）；按钮点开
    :class:`CompositeSignatureDialog` 弹窗编辑签名（右下角确定生效，取代内联表）。
    选中卡片时载入 body，给 body 步骤 ``io.picker`` 换局部选择器 + ``io._tree``
    换校验树（:func:`build_validation_tree`，纯局部校验：绑 ``{{全局}}`` 即时红卡）；
    签名变更 → 更新 sigs + 改指 body 引用 + 重建选择器/校验树 + 刷新 + 按钮文案。
    """

    def __init__(self, package: KscpPackage, tree: VariableTree,
                 mgr: Optional[StepManager],
                 composite_store: CompositeCardStore,
                 clipboard: Optional[StepClipboard] = None,
                 on_rename: Optional[Callable[[str, str], None]] = None,
                 on_sig_changed: Optional[Callable[[str], None]] = None,
                 parent: Optional[QWidget] = None) -> None:
        super().__init__("合成卡片")
        self._package = package
        self._tree = tree
        self._mgr = mgr if mgr is not None else StepManager(package, tree)
        if mgr is None:
            self._mgr.load()
        self._cstore = composite_store
        self._clipboard = clipboard if clipboard is not None else StepClipboard()
        # 重命名后改指引用回调（old_full, new_full）——主窗口借此联动步骤列表存储
        self._on_rename_cb = on_rename
        # 签名变更回调（ref）——主窗口借此重同步步骤列表内引用该卡的步骤 io
        self._on_sig_changed_cb = on_sig_changed
        self._sl_tree: Optional[CompositeTreeWidget] = None
        self._host: Optional[StepListHost] = None
        self._sig_btn: Optional[QPushButton] = None
        self._container: Optional[QWidget] = None
        self._current: Optional[str] = None
        self._save_timer: Optional[QTimer] = None

    @property
    def store(self) -> CompositeCardStore:
        """合成卡片存储（运行时引用解析数据源 + 主窗口落盘用）。"""
        return self._cstore

    @property
    def current_path(self) -> Optional[str]:
        """当前选中的合成卡片路径（编辑期递归排除自身用）；未选 → None。"""
        return self._current

    @property
    def host(self) -> StepListHost:
        """内层 StepListHost（宿主级信号如 composite_jump_requested 经此取）；懒构建。

        v2 ``preview_widget()`` 返回容器（签名表 + host），主窗口连宿主级信号时
        经此取内层 host，而非直接 ``preview_widget()``（其返回的是容器 QWidget）。
        """
        if self._host is None:
            self.preview_widget()
        assert self._host is not None     # preview_widget() 已建 host（同 v1 :258 守卫）
        return self._host

    def set_read_only(self, ro: bool) -> None:
        """执行期只读：树/宿主/签名编辑按钮全部禁编辑。"""
        if self._sl_tree is not None:
            self._sl_tree.set_read_only(ro)
        if self._host is not None:
            self._host.set_read_only(ro)
        if self._sig_btn is not None:
            self._sig_btn.setEnabled(not ro)

    def icon(self) -> QIcon:
        return make_icon("composite")

    def _save_store(self) -> None:
        self._package.write_file("composites.json", self._cstore.to_json_bytes())

    def refresh_cards(self) -> None:
        """变量树变化 → 宿主重检卡片颜色（不重建）。"""
        if self._host is not None:
            self._host.refresh_validity()

    def tree_widget(self) -> QWidget:
        if self._sl_tree is None:
            self._sl_tree = CompositeTreeWidget(
                self._cstore, self._mgr, self._clipboard,
                self._save_store, self._on_rename_cb, None)
            self._sl_tree.composite_selected.connect(self._on_selected)
            self._sl_tree.store_changed.connect(self._on_store_changed)
        assert self._sl_tree is not None
        return self._sl_tree

    def _on_edited(self) -> None:
        """视图内容编辑（io/签名/激活切换）→ 防抖落盘 + 树错误标记同步 + 重应用局部选择器。

        新增/粘贴的 body 步骤 io.picker 默认为全局选择器（StepIOWidget 默认），
        需重置为局部选择器以维持纯局部作用域（spec §5.4）——否则用户可绑全局变量，
        运行期局部树无该名 → 步骤 ERROR。

        ``_apply_local_picker`` 重指 ``io._tree`` 为校验树后，**重同步所有 body 卡片
        的背景与错误标签**（:meth:`refresh_validity`）：背景（``_update_style`` 经
        ``is_valid``）与标签（``error_reasons``）都读 ``io._tree``，但若树在「背景
        已算、标签未算」之间被换，二者会脱节——表现为「修复后不红、但错误提示词
        残留」。重同步保证两者用同一棵（换后的）树，消除脱节。
        """
        if self._sl_tree is not None:
            self._sl_tree.refresh_error_marks()
        if self._host is not None and self._current is not None:
            try:
                body = self._cstore.get_body(self._current)
            except FileNotFoundError:
                pass
            else:
                self._apply_local_picker(body)
                self._host.refresh_validity()   # 背景+标签重同步到换后的 io._tree
        if self._save_timer is None:
            self._save_timer = QTimer()
            self._save_timer.setSingleShot(True)
            self._save_timer.setInterval(500)
            self._save_timer.timeout.connect(self._save_store)
        self._save_timer.start()

    def preview_widget(self) -> QWidget:
        """容器：上「编辑签名…」按钮、下 StepListHost（体编辑复用）。

        签名编辑改为弹窗（:class:`CompositeSignatureDialog`，确定后生效）——取代
        预览栏内联签名表（竖状堆叠拥挤；改弹窗整合输入/输出/局部于一处，可删除/
        添加/重命名，右下角确定生效）。
        """
        if self._container is None:
            self._sig_btn = QPushButton("编辑签名…")
            self._sig_btn.clicked.connect(self._open_signature_dialog)
            self._host = StepListHost(
                self._mgr, self._clipboard, self._on_edited, None,
                composite_store=self._cstore)
            self._host.errors_changed.connect(self._refresh_tree_marks)
            self._container = QWidget()
            lay = QVBoxLayout(self._container)
            lay.setContentsMargins(6, 4, 6, 0)
            lay.setSpacing(4)
            lay.addWidget(self._sig_btn)
            lay.addWidget(self._host, 1)
        assert self._container is not None
        return self._container

    def _open_signature_dialog(self) -> None:
        """「编辑签名…」按钮 → 弹窗编辑当前卡片签名；确定 → 落盘 + 联动。"""
        if self._current is None:
            return
        try:
            sig = self._cstore.get_signature(self._current)
        except FileNotFoundError:
            return
        dlg = CompositeSignatureDialog(sig, self._container)
        if dlg.exec_() == QDialog.Accepted:
            self._on_signature_changed(dlg.signature())

    def _refresh_sig_label(self) -> None:
        """按钮文本反映当前卡片签名参数数（未选 / 已删 → 通用文案）。"""
        if self._sig_btn is None:
            return
        if self._current is None:
            self._sig_btn.setText("编辑签名…")
            return
        try:
            sig = self._cstore.get_signature(self._current)
        except FileNotFoundError:
            self._sig_btn.setText("编辑签名…")
            return
        self._sig_btn.setText("编辑签名…（%d 入 / %d 出 / %d 局）" % (
            len(sig.inputs), len(sig.outputs), len(sig.locals)))

    def _refresh_tree_marks(self, _n: int) -> None:
        if self._sl_tree is not None:
            self._sl_tree.refresh_error_marks()

    def _apply_local_picker(self, body: StepList) -> None:
        """给 body 步骤 io.picker 换局部选择器 + io._tree 换校验树（捕获当前签名）。

        纯局部作用域：body 步骤只能绑签名参数（入参/出参/局部）。换 io._tree 为
        **校验树**（inputs 也预填，区别于运行期 :func:`build_local_tree`）→
        body 步骤绑 ``{{全局}}`` 时 :attr:`~model.步骤.step_io.StepIOWidget.is_valid`
        判 False → 卡片即时红标（与运行期局部树缺失该名 → ERROR 一致，修
        「编辑期不红、运行期才红」的不一致）。
        参数less（空签名）→ body 走全局树（同 v1，运行期不换树）。

        换 picker 时**保留 StepCard 装的包装器**（含 deferred ``_io_edited`` 刷新
        钩子，step_card.py:156）：若 ``io.picker`` 已是包装器（有 ``_kscript_orig``），
        只改其 ``_kscript_orig`` 属性（换底层 picker）；否则直设（卡片未构造，
        StepCard 构造时会包）。**不可** ``s.io.picker = picker`` 顶掉包装器——否则
        之后 ``…`` 按钮选值不再触发刷新，残留错误标签（手输不受影响）。
        """
        sig = (self._cstore.get_signature(self._current)
               if self._current else CompositeSignature.empty())
        picker = make_composite_local_picker(sig, self._on_new_local)
        vtree = (self._tree if sig.is_empty()
                 else build_validation_tree(sig, self._package))
        for s in body.steps:
            cur = s.io.picker
            if hasattr(cur, "_kscript_orig"):
                cur._kscript_orig = picker          # 保留包装器，仅换底层 picker
            else:
                s.io.picker = picker                 # 无包装器（卡片未构造）→ 直设
            s.io._tree = vtree

    def _on_new_local(self, name: str, vtype: str, default: object) -> None:
        """picker「新建局部变量」→ 加进当前签名局部段 + 落盘 + 刷新。

        签名编辑已改弹窗（按需打开、载入即最新），无需同步内联表——旧内联表的
        stale 重建丢局部问题随弹窗化消解：弹窗每次打开都从 store 读最新签名。
        """
        if self._current is None:
            return
        sig = self._cstore.get_signature(self._current)
        # 避免重名
        if name in sig.slot_names():
            return
        new_sig = CompositeSignature(
            inputs=list(sig.inputs), outputs=list(sig.outputs),
            locals=sig.locals + [LocalVar(name, vtype, default)])
        self._on_signature_changed(new_sig)

    # ---- 宿主联动 ----
    def _on_selected(self, path: str) -> None:
        self._current = path
        if self._host is None:
            return
        try:
            body = self._cstore.get_body(path)
        except FileNotFoundError:
            self._host.set_list(None)
            self._refresh_sig_label()
            return
        self._apply_local_picker(body)
        # exclude_ref=path：编辑卡片 A 时排除 A 自身（选择器防直接递归）
        self._host.set_list(body, self._mgr, exclude_ref=path)
        self._refresh_sig_label()

    def _on_store_changed(self) -> None:
        """树内容变更（添加/粘贴/删除）→ 宿主同步当前卡片。"""
        if self._host is None or self._current is None:
            return
        try:
            body = self._cstore.get_body(self._current)
        except FileNotFoundError:
            # 当前卡片已被删除/重命名中 → 清选择 + 宿主回占位 + 按钮文案复位
            # （防 stale 签名编辑经 _on_signature_changed 写孤儿 sigs 条目）
            self._current = None
            self._host.set_list(None)
            self._refresh_sig_label()
        else:
            self._apply_local_picker(body)
            # exclude_ref=self._current：树变更后重绑宿主仍排除当前卡（防自递归）。
            # 创建新卡 → refresh 选中新卡 → _on_selected 设 _current=新卡 + 正确
            # exclude_ref，但紧随的 store_changed → 本方法曾漏 exclude_ref → 顶掉
            # 正确值 → 选择器又列出新卡（可加自身）；点其它再点回才正确。补齐即修。
            self._host.set_list(body, self._mgr, exclude_ref=self._current)
            self._refresh_sig_label()

    def _on_signature_changed(self, sig: CompositeSignature) -> None:
        """签名变更 → 更新 sigs + 改指 body 引用 + 重建选择器 + 刷新卡片 + 按钮文案。

        来源：签名编辑弹窗「确定」/ picker「新建局部变量」。弹窗内编辑不直达
        （仅确定时一次性提交，避免半成品签名落盘）。
        """
        if self._current is None:
            return
        if self._host is None:          # 防御：信号联动保证已建，同 v1 _on_selected 守卫风格
            return
        old = self._cstore.get_signature(self._current)
        self._cstore.set_signature(self._current, sig)
        try:
            body = self._cstore.get_body(self._current)
        except FileNotFoundError:
            return
        repoint_param_refs(body, old, sig)
        self._apply_local_picker(body)          # 捕获新签名重建 picker + 校验树
        self._host.set_list(body, self._mgr, exclude_ref=self._current)
        self._on_edited()                       # 防抖落盘
        self._refresh_sig_label()               # 按钮参数计数随签名刷新
        # 重同步**合成卡片体内**引用本卡的调用点 io（composite→composite）。
        # 步骤列表里的调用点由 on_sig_changed_cb → StepListManagementTree.resync_composite_steps
        # 刷；但合成卡片 A 的 body 里调用了 B，B 签名变后 A 内调用点 io 不会自动
        # 跟变（resync_composite_steps 只遍历 StepListStore，不遍历 CompositeCardStore）。
        self._resync_bodies_for_ref(self._current)
        if self._on_sig_changed_cb is not None:    # 通知步骤列表重同步引用该卡的步骤 io
            self._on_sig_changed_cb(self._current)

    def _resync_bodies_for_ref(self, ref: str) -> None:
        """B 签名变更 → 重同步**合成卡片体内**引用 B 的调用点 io（composite→composite）。

        与 :meth:`StepListManagementTree.resync_composite_steps` 互补：后者刷步骤
        列表（全局作用域）里的调用点，本方法刷合成卡片 body（纯局部作用域）里的
        调用点。遍历所有合成卡片 body，对 ref 匹配的 :class:`CompositeCard` 步骤调
        :meth:`~CompositeCard.resync_io`（按新签名重建类型化 io、保留旧值）。

        ``resync_io`` 把 ``io._tree`` 设全局树；编辑期需校验树（绑 A 的参数在全局
        树找不到会误红）——故随后 :meth:`~CompositeTreeWidget.refresh_error_marks`
        把各 body 步骤 ``io._tree`` 重设为所属卡片的校验树（非空签名）或全局树
        （空签名）。当前编辑卡 B 的 body 正常不含引用 B 自身的步骤（exclude_ref
        防自递归），故本方法不动 B 的 body，宿主画面无需重建。
        """
        for path, is_group in self._cstore.walk():
            if is_group:
                continue
            try:
                body = self._cstore.get_body(path)
            except FileNotFoundError:
                continue
            for step in body.steps:
                if isinstance(step, CompositeCard) and step.ref == ref:
                    step.resync_io()
        if self._sl_tree is not None:
            self._sl_tree.refresh_error_marks()

    def select_composite(self, ref: str) -> bool:
        """选中合成卡片树条目并触发 :meth:`_on_selected`（右键跳转编辑用）。

        树懒构建：先 :meth:`tree_widget` 确保已建。返回是否找到并选中。
        """
        tw = self.tree_widget()
        assert isinstance(tw, CompositeTreeWidget)
        it = tw.find_item(ref)
        if it is None:
            return False
        tw.setCurrentItem(it)        # → _on_current_changed → composite_selected → _on_selected
        return True

    def repoint_composite_refs(self, old_path: str, new_path: str) -> int:
        """合成卡片重命名时，把**其它合成卡片体内**引用 ``old_path`` 的条目改指
        ``new_path``；返回改动数。

        仅改 ``CompositeCard`` 实例的 ``ref/name`` + 落盘 ``composites.json``。
        **不重绑本宿主**：回调触发时 ``self._current`` 仍是旧路径 ``old_path``
        （重命名流程在 :meth:`CompositeTreeWidget._act_rename` 内先发 ``on_rename``
        再 :meth:`_changed` → :meth:`_on_selected` 才把 ``_current`` 更到新路径），
        此时 ``get_body(old_path)`` 会 FileNotFoundError → 误清空宿主；新路径的重绑
        紧随其后由重命名流程自身完成。被改指的卡片若非当前编辑卡，其画面在下次
        选中时自然刷新。
        """
        n = repoint_refs(self._cstore, old_path, new_path)
        if n:
            self._save_store()
        return n


class StepListHost(QStackedWidget):
    """步骤列表视图宿主：占位页 + 工具栏 + StepListView（视图编辑 → 保存回调）。

    工具栏两行：「跳转序号 / 搜索标签定位」（卡片过多时定位用，
    经 :meth:`StepListView.jump_to_index` / :meth:`StepListView.locate_by_tag`）；
    下方「错误卡片: N + 跳转错误」（错误数随视图刷新经
    :attr:`StepListView.errors_changed` 同步，跳转经 :meth:`StepListView.jump_to_error`）。
    错误数同时经 :attr:`errors_changed` 转发给宿主（步骤列表管理树 → 树条目红标记）。
    """

    errors_changed = pyqtSignal(int)   # 错误卡片数（转发自 StepListView）
    composite_jump_requested = pyqtSignal(str)   # 右键合成卡片 → 跳转其编辑（转发）

    def __init__(self, mgr: StepManager, clipboard: StepClipboard,
                 on_edited: Callable[[], None],
                 parent: Optional[QWidget] = None,
                 composite_store: Optional[CompositeCardStore] = None) -> None:
        super().__init__(parent)
        self._placeholder = QLabel("从左侧选择一个步骤列表")
        self._placeholder.setAlignment(Qt.AlignCenter)
        self._placeholder.setStyleSheet("color:#999; font-size:15px;")
        self.addWidget(self._placeholder)          # 0
        self._view = StepListView(mgr, clipboard, None, composite_store)
        self._view.edited.connect(on_edited)
        self._view.errors_changed.connect(self._on_errors_changed)
        self._view.errors_changed.connect(self.errors_changed)
        self._view.composite_jump_requested.connect(self.composite_jump_requested)
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
        total = len(self._view.cards)
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
                 mgr: Optional[StepManager] = None,
                 exclude_ref: Optional[str] = None) -> None:
        self._view.set_list(step_list, mgr, exclude_ref)
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
# 冒烟演示：直接 ``python -m widgets.树.management_trees`` 运行
# ================================================================
if __name__ == "__main__":
    import sys

    from PyQt5.QtWidgets import QApplication, QLabel

    from model.工程.kscp_package import KscpPackage
    from model.变量.project_variable import ProjectVariable
    from model.步骤.step_list import StepList
    from model.步骤.step_manager import StepManager
    from model.变量.variable_tree import VariableTree
    from model.合成卡片.composite_card import CompositeCard
    from model.合成卡片.composite_card_store import CompositeCardStore
    from widgets.树.composite_tree_widget import CompositeTreeWidget
    from widgets.卡片.step_list_view import StepClipboard

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
    _box = slm.tree_widget()
    assert isinstance(_box, QWidget)                # 树面板 = 页容器
    assert slm.current_page == "执行列表1"           # 空工程 → 默认单页
    assert isinstance(slm.current_tree(), StepListTreeWidget)
    assert slm._page_title is not None and slm._page_title.text() == "执行列表1"
    assert slm._page_menu_btn is not None and slm._page_menu_btn.menu() is not None
    assert slm._add_page_btn is not None and slm._del_page_btn is not None
    assert slm.store is slm._page_store.get_page("执行列表1")   # store = 当前页
    host = slm.preview_widget()
    assert isinstance(host, StepListHost)
    assert host.currentIndex() == 0                 # 未选列表 → 占位页

    # 列表选择联动：添加列表 → 刷新树 → 选中 → 宿主切换（跨页出口信号同发）
    sl = StepList.create_empty()
    slm.store.add_list("主列表", sl)
    slm._save_store()
    tw = slm.current_tree()
    tw.refresh()
    _sel = []
    slm.list_selected.connect(_sel.append)
    tw.list_selected.emit("主列表")
    assert host.currentIndex() == 1
    assert host._view._step_list is sl
    assert _sel == ["主列表"]
    assert slm.current_path == "主列表"

    # ---- 页操作（QInputDialog 打桩）：添加页跳转 / 重命名 / 删除该页 / 查重阻止 ----
    from PyQt5.QtWidgets import QInputDialog as _QID
    _orig_get_text = _QID.getText
    _dlg_vals = []

    def _get_text_seq(_parent, _title, _label, **_k):
        return (_dlg_vals.pop(0), True)

    _QID.getText = staticmethod(_get_text_seq)
    # ① 添加页：建议名（弹窗返回「坐标页」）→ 新页创建并跳转
    _dlg_vals.append("坐标页")
    _page_added = []
    _page_changed = []
    slm.page_added.connect(_page_added.append)
    slm.page_changed.connect(_page_changed.append)
    slm._on_add_page_clicked()
    assert slm.page_store.page_names() == ["执行列表1", "坐标页"]
    assert slm.current_page == "坐标页", slm.current_page
    assert slm._page_title.text() == "坐标页"
    assert _page_added == ["坐标页"] and _page_changed == ["坐标页"]
    assert isinstance(slm.current_tree(), StepListTreeWidget)
    assert slm.current_tree() is not tw                 # 每页一棵缓存树
    # ② 查重阻止：重名 → 日志报错、不落盘
    LogModel.instance().clear()
    _dlg_vals.append("执行列表1")
    slm._on_add_page_clicked()
    assert slm.page_store.page_names() == ["执行列表1", "坐标页"]
    assert any("已存在" in e.message for e in LogModel.instance().entries)
    # ③ 重命名当前页：成功 + 缓存重键 + 落盘
    _dlg_vals.append("坐标采集")
    _renamed = []
    slm.page_renamed.connect(lambda o, n: _renamed.append((o, n)))
    slm._rename_current_page()
    assert slm.current_page == "坐标采集"
    assert _renamed == [("坐标页", "坐标采集")]
    assert slm._page_trees.get("坐标采集") is not None
    assert slm._page_trees.get("坐标页") is None
    assert '"坐标采集"' in pkg.read_file("step_list.json").decode("utf-8")
    # ④ 重命名查重阻止
    LogModel.instance().clear()
    _dlg_vals.append("执行列表1")
    slm._rename_current_page()
    assert slm.current_page == "坐标采集"
    assert any("已存在" in e.message for e in LogModel.instance().entries)
    # ⑤ 切回第一页：选中态各自保留
    slm._activate_page("执行列表1")
    assert slm.current_page == "执行列表1"
    assert slm.current_path == "主列表"                # 第一页的选中态还在
    assert host._view._step_list is sl
    # ⑥ 删除该页：删当前页（执行列表1）→ 激活首剩页；最后一页守卫
    slm._on_del_page_clicked()
    assert slm.page_store.page_names() == ["坐标采集"]
    assert slm.current_page == "坐标采集"
    LogModel.instance().clear()
    slm._on_del_page_clicked()                        # 最后一页 → 拒绝 + 日志
    assert slm.page_store.page_names() == ["坐标采集"]
    assert any("至少保留" in e.message for e in LogModel.instance().entries)
    # ⑦ 只读：全部页树只读 + 页操作按钮禁用 + 下拉切换保持可用
    slm.set_read_only(True)
    assert all(t._read_only for t in slm.trees())
    assert not slm._add_page_btn.isEnabled() and not slm._del_page_btn.isEnabled()
    assert slm._page_menu_btn.isEnabled()
    assert host._view._read_only
    slm.set_read_only(False)
    assert not slm._page_title is None
    _QID.getText = _orig_get_text

    # 落盘防抖（评审#10）：编辑 → 500ms 单发定时器，到期才写盘
    slm._on_edited()
    assert slm._save_timer is not None and slm._save_timer.isActive()
    assert slm._save_timer.interval() == 500 and slm._save_timer.isSingleShot()
    slm._save_timer.stop()
    slm._save_timer.timeout.emit()          # 模拟防抖到期 → 落盘（不崩）

    # ---- add_template_to_current：模板树「加入当前列表」闭环 ----
    _GOOD = '''# -*- coding: utf-8 -*-
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
    slm2.store.add_list("主列表", sl2)
    slm2._save_store()
    host2 = slm2.preview_widget()               # 先建宿主再选中（联动发生在选中时）
    slm2.tree_widget()                          # 构建页容器（懒建每页树）
    tw2 = slm2.current_tree()
    tw2.refresh()
    tw2.list_selected.emit("主列表")
    assert host2.currentIndex() == 1
    assert slm2.add_template_to_current("示例") is True
    assert len(sl2.steps) == 1
    assert len(host2._view.cards) == 1              # 宿主刷新出新卡片
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

    # ---- CompositeManagementTree：树 + 宿主（复用 StepListHost）+ 落盘 + 引用解析 ----
    pkg_c = KscpPackage.create_empty()
    pkg_c.write_file("actions/示例.py", _GOOD.encode("utf-8"))
    tree_c = VariableTree.create_empty()
    mgr_c = StepManager(pkg_c, tree_c)
    mgr_c.load()
    cstore = CompositeCardStore.create_empty()
    body = StepList.create_empty()
    cstore.add_list("登录", body)
    pkg_c.write_file("composites.json", cstore.to_json_bytes())
    CompositeCard.set_resolver(cstore.get_or_none)
    cmgr = CompositeManagementTree(pkg_c, tree_c, mgr_c, cstore)
    assert cmgr.name == "合成卡片" and not cmgr.icon().isNull()
    assert isinstance(cmgr.tree_widget(), CompositeTreeWidget)
    cmgr.preview_widget()                                  # 构建容器（按钮 + host）
    assert isinstance(cmgr._host, StepListHost)
    assert cmgr._host.currentIndex() == 0                  # 未选卡片 → 占位页
    assert cmgr.store is cstore
    assert cmgr.current_path is None
    # 卡片选择联动：选中 → 宿主切到编辑页，显示该卡片体内 StepList
    ctw = cmgr.tree_widget()
    ctw.refresh()
    ctw.composite_selected.emit("登录")
    assert cmgr.current_path == "登录"
    assert cmgr._host.currentIndex() == 1
    assert cmgr._host._view._step_list is body
    # 落盘防抖：编辑 → 500ms 单发定时器 → 写 composites.json
    cmgr._on_edited()
    assert cmgr._save_timer is not None and cmgr._save_timer.isActive()
    cmgr._save_timer.stop()
    cmgr._save_timer.timeout.emit()                       # 模拟到期落盘（不崩）
    # select_composite：选中树条目并触发联动（右键跳转编辑用）
    assert cmgr.select_composite("登录") is True
    assert cmgr.current_path == "登录"
    assert cmgr.select_composite("不存在") is False
    # 变量树变化 → refresh_cards 不崩
    cmgr.refresh_cards()
    # 只读切换：不抛
    cmgr.set_read_only(True)
    cmgr.set_read_only(False)
    # v2：选中带参卡片 → 签名表载入 + body 宿主 + 局部选择器（不抛）
    from model.合成卡片.composite_signature import Param, CompositeSignature
    sig = CompositeSignature(inputs=[Param("x", "number")],
                             outputs=[Param("y", "number")])
    bodyP = StepList.create_empty()
    cstore.add_list("带参", bodyP, signature=sig)
    ctw.refresh()
    ctw.composite_selected.emit("带参")
    assert cmgr.current_path == "带参"
    assert cmgr._host.currentIndex() == 1
    # 签名载入：按钮文案反映参数数 + store 持有签名
    assert "编辑签名…（1 入 / 1 出 / 0 局）" in cmgr._sig_btn.text()
    assert cstore.get_signature("带参").input_names() == ["x"]
    # 签名变更 → 落盘（防抖到期后）
    new_sig = CompositeSignature(inputs=[Param("a", "number")],
                                 outputs=[Param("b", "number")])
    cmgr._on_signature_changed(new_sig)
    assert cstore.get_signature("带参").input_names() == ["a"]
    # _on_new_local：加局部变量 → 签名局部段 +1
    cmgr._on_new_local("t", "number", 0)
    assert "t" in cstore.get_signature("带参").local_names()
    # quick-create 后 store 已更新；弹窗按需打开、载入即最新（无需同步内联表）
    assert "1 局" in cmgr._sig_btn.text()
    # 弹窗编辑：_open_signature_dialog → 确定 → _on_signature_changed 落盘
    # （打桩 exec_：返回 Accepted 前先编辑弹窗内 widget，模拟用户「确定」）
    from PyQt5.QtWidgets import QDialog as _QDialog
    from widgets.合成卡片.composite_signature_widget import (
        CompositeSignatureDialog as _CSD)
    _orig_exec = _CSD.exec_
    try:
        def _fake_exec(_self):
            _self._sig_widget._in._add_row("c", "number")   # 模拟用户加输入 c
            return _QDialog.Accepted
        _CSD.exec_ = _fake_exec
        cmgr._open_signature_dialog()
        assert "c" in cstore.get_signature("带参").input_names()
    finally:
        _CSD.exec_ = _orig_exec
    # Fix 1: 新增 body 步骤 → _on_edited 重应用局部选择器（纯局部，非全局）
    step_demo = mgr_c.create_step("示例")        # mgr_c 已加载"示例"模板
    bodyP.add(step_demo)                          # StepList.add 追加一步
    bodyP.steps[-1].io.picker = None              # 模拟新增步骤未应用 picker（如 _add_step 默认）
    cmgr._on_edited()                             # 模拟 body 编辑 → _on_edited 重应用
    assert bodyP.steps[-1].io.picker is not None  # Fix 1: _on_edited 重应用了局部 picker

    # 回归：_apply_local_picker 不得顶掉 StepCard 装的 picker 包装器
    # （包装器含 deferred _io_edited 刷新钩子；顶掉后 … 按钮选值不再刷新 → 残留错误标签）。
    # 选中带 body 的卡片 → set_list 建卡（装包装器）→ _on_edited → _apply_local_picker
    # 应保留包装器（仅改 _kscript_orig），而非裸替换。
    wrap_body = StepList.create_empty()
    wrap_step = mgr_c.create_step("示例")
    wrap_step.io.change_value("output", 0, "y")
    wrap_step.io.change_value("input", 0, "{{x}}")
    wrap_body.add(wrap_step)
    cstore.add_list("wrap", wrap_body,
                    signature=CompositeSignature(inputs=[Param("x", "number")],
                                                  outputs=[Param("y", "number")]))
    ctw.refresh()
    ctw.composite_selected.emit("wrap")          # _on_selected → _apply_local_picker + set_list（建卡装包装器）
    assert hasattr(wrap_step.io.picker, "_kscript_orig"), "选中后 picker 应是包装器"
    cmgr._on_edited()                             # 模拟 body 编辑 → _apply_local_picker 重应用
    assert hasattr(wrap_step.io.picker, "_kscript_orig"), \
        "_apply_local_picker 不得顶掉包装器（否则 … 按钮选值后错误标签残留）"
    assert cmgr.current_path == "wrap"            # 仍选中 wrap（_on_edited 不改 _current）
    ctw.composite_selected.emit("带参")           # 复位选中（后续删除测试假设 _current=带参）

    # (a) 合成卡片签名变更 → 步骤列表内引用该卡的 CompositeCard 步骤 io 自动重同步
    slm_c = StepListManagementTree(pkg_c, tree_c, mgr_c, composite_store=cstore)
    cstore.add_list("SRC", StepList.create_empty(),
                    signature=CompositeSignature(inputs=[Param("x", "number")],
                                                  outputs=[Param("y", "number")]))
    call_step = CompositeCard.from_marker("@合成卡片:SRC", mgr_c)   # bare marker → 类型化 io
    call_step.io.change_value("input", 0, "5")
    call_step.io.change_value("output", 0, "n1")
    use_list = StepList.create_empty(); use_list.add(call_step)
    slm_c.store.add_list("用卡", use_list)
    slm_c.tree_widget()                            # 构建页容器（懒建每页树）
    sltw_c = slm_c.current_tree(); sltw_c.refresh()
    sltw_c.list_selected.emit("用卡")              # → _on_list_selected → _current = "用卡"
    assert slm_c.current_path == "用卡"
    assert call_step.io.output_types == ["number"]
    # SRC 签名变更（加输出 z）→ resync_composite_steps → 步骤 io 按新签名重建（保留值）
    sigZ = CompositeSignature(inputs=[Param("x", "number")],
                              outputs=[Param("y", "number"), Param("z", "number")])
    cstore.set_signature("SRC", sigZ)
    slm_c.resync_composite_steps("SRC")
    assert call_step.io.output_types == ["number", "number"]   # 新增 z 槽
    assert call_step.io._input_values == ["5"]                  # 旧值保留
    assert call_step.io._output_values == ["n1", ""]           # 旧值保留 + 新槽空
    CompositeCard.set_resolver(lambda ref: None)           # 复位，避免影响后续模块冒烟

    # 删除当前卡片 → _current 清空 + 按钮文案复位（防 stale sig 编辑写孤儿 sigs）
    cstore.remove("带参")
    cmgr._on_store_changed()
    assert cmgr.current_path is None
    assert cmgr._sig_btn.text() == "编辑签名…"
    # 防抖归位（与上文 _on_edited 落盘一致，不崩）
    assert cmgr._save_timer is not None
    cmgr._save_timer.stop()
    cmgr._save_timer.timeout.emit()

    # ---- 回归 Bug1：_on_store_changed 须传 exclude_ref=self._current ----
    # 创建新卡 → refresh 选中新卡 → _on_selected 设 _current=新卡 + 正确 exclude_ref，
    # 但紧随的 store_changed → _on_store_changed 曾漏 exclude_ref → 顶掉正确值 →
    # 选择器又列出新卡（可加自身）；点其它再点回才正确。补 exclude_ref 即修。
    ctw.composite_selected.emit("登录")           # _current = "登录"
    assert cmgr.current_path == "登录"
    _rec = []
    _orig_set_list = cmgr._host.set_list
    def _spy_set_list(sl, mgr, exclude_ref=None):
        _rec.append(exclude_ref)
        return _orig_set_list(sl, mgr, exclude_ref)
    cmgr._host.set_list = _spy_set_list
    try:
        cmgr._on_store_changed()                  # 模拟树变更（如新建卡片）→ 重绑宿主
    finally:
        cmgr._host.set_list = _orig_set_list
    assert _rec and _rec[-1] == "登录", \
        "_on_store_changed 须传 exclude_ref=self._current（否则创建新卡后可加自身）"

    # ---- 回归 Bug2：合成卡片签名变 → 体内调用点 io 重同步（composite→composite） ----
    # （与 (a) 步骤列表调用点互补；Bug2 根因：_on_signature_changed 只经
    #   on_sig_changed_cb 走 StepListStore 重同步，未刷 CompositeCardStore 体内调用点。）
    CompositeCard.set_resolver(cstore.get_or_none)   # 复位（(a) 末尾改成了 lambda None）
    cstore.add_list("B卡", StepList.create_empty(),
                    signature=CompositeSignature(inputs=[Param("x", "number")],
                                                  outputs=[Param("y", "number")]))
    a_call = CompositeCard.from_marker("@合成卡片:B卡", mgr_c)   # B 当前签名：1 入 x / 1 出 y
    a_call.io.change_value("input", 0, "9")
    a_call.io.change_value("output", 0, "out")
    a_body = StepList.create_empty(); a_body.add(a_call)
    cstore.add_list("A卡", a_body,
                    signature=CompositeSignature(inputs=[Param("p", "number")],
                                                  outputs=[Param("q", "number")]))
    assert a_call.io.output_types == ["number"]                  # B 当前：1 输出
    ctw.refresh()
    ctw.composite_selected.emit("A卡")                           # 选中 A（建卡装包装器）
    assert cmgr.current_path == "A卡"
    ctw.composite_selected.emit("B卡")                           # 选中 B → 准备改 B 签名
    assert cmgr.current_path == "B卡"
    sigB2 = CompositeSignature(inputs=[Param("x", "number")],
                               outputs=[Param("y", "number"), Param("z", "number")])
    cmgr._on_signature_changed(sigB2)                            # → _resync_bodies_for_ref("B卡")
    # A 的 body 内调用 B 的卡片 io 已按 B 新签名重建（新增 z 槽，旧值保留）
    assert a_call.io.output_types == ["number", "number"], \
        "B 签名变 → A 体内调用点 io 应重同步（composite→composite）"
    assert a_call.io._input_values == ["9"]                      # 旧值保留
    assert a_call.io._output_values == ["out", ""]               # 旧值保留 + 新槽空
    CompositeCard.set_resolver(lambda ref: None)                 # 复位，避免影响后续模块冒烟

    print("management_trees smoke OK")
