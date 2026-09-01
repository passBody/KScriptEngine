# -*- coding: utf-8 -*-
"""
合成卡片管理树（GUI 控件）
========================

:class:`CompositeTreeWidget` 是「合成卡片列表模型」
（:class:`model.合成卡片.composite_card_store.CompositeCardStore`）的管理树：组 = 文件夹
图标，叶子 = 合成卡片（只显示键值）。上下文菜单支持添加卡片 / 添加组 / 复制 /
剪切 / 粘贴 / 重命名 / 删除；点击卡片发 :data:`composite_selected`，任何变更后
发 :data:`store_changed` 并调用 ``on_changed`` 回调（上层保存 ``composites.json``）。

与 :class:`widgets.树.step_list_tree_widget.StepListTreeWidget` 同构（结构/拖拽/右键
菜单同款），唯二区别：

* **无激活勾选框**：合成卡片体内步骤的激活在卡片视图编辑（同步骤列表），
  树不提供整卡激活勾选（v1 简化）。
* **无运行高亮**：合成卡片由外层步骤列表的执行器经 :meth:`CompositeCard.run`
  展开，非 ``StepRunner`` 直接驱动单卡，故无「正在执行」前缀。

基本用法
--------
::

    tree = CompositeTreeWidget(store, mgr, clipboard, on_changed)
    tree.composite_selected.connect(show_body)   # 点击卡片 → 视图显示其体内步骤
"""

from __future__ import annotations

from typing import Any, Callable, List, Optional, Tuple

from PyQt5.QtCore import QRect, Qt, pyqtSignal
from PyQt5.QtGui import (
    QColor, QDragLeaveEvent, QDragMoveEvent, QFont, QIcon, QKeySequence,
    QPainter, QPixmap,
)
from PyQt5.QtWidgets import (
    QAbstractItemView, QInputDialog, QMenu, QMessageBox, QShortcut,
    QStyle, QTreeWidget, QTreeWidgetItem, QWidget,
)

from model.步骤.step_list import StepList
from model.合成卡片.composite_card_store import CompositeCardStore
from model.合成卡片.composite_local_tree import build_validation_tree
from model.步骤.step_manager import StepManager
from widgets.卡片.step_list_view import StepClipboard

__all__ = ["CompositeTreeWidget"]

_PATH_ROLE = 0x0100   # Qt.UserRole


def _make_card_icon() -> QIcon:
    """合成卡片叶子小图标：紫色叠层方块（与活动栏 composite 图标同系）。"""
    pm = QPixmap(18, 18)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#8e6db5"))
    p.drawRoundedRect(2, 2, 11, 11, 2, 2)        # 后片
    p.setBrush(QColor("#b290e0"))
    p.drawRoundedRect(5, 5, 11, 11, 2, 2)        # 前片
    p.setBrush(QColor("#fff3e0"))
    for y in (7, 10, 13):
        p.drawRoundedRect(7, y, 7, 1, 0, 0)      # 前片内三条横线
    p.end()
    return QIcon(pm)


class CompositeTreeWidget(QTreeWidget):
    """合成卡片管理树：只显示键值（组 = 文件夹，卡片 = 图标 + 名）。"""

    composite_selected = pyqtSignal(str)   # 点击卡片叶子 → 路径
    store_changed = pyqtSignal()           # 任何变更后发出（宿主处理当前卡片被删等）

    def __init__(self, store: CompositeCardStore, manager: StepManager,
                 clipboard: StepClipboard, on_changed: Callable[[], None],
                 on_rename: Optional[Callable[[str, str], None]] = None,
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._store = store
        self._manager = manager
        self._clipboard = clipboard
        self._on_changed = on_changed
        self._on_rename = on_rename     # 重命名后改指引用（old_full, new_full）

        self.setHeaderHidden(True)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        # 拖拽 = 移动排序（同步骤列表树）：单条换序、多选 = 批量剪切粘贴
        self.setDragDropMode(QAbstractItemView.InternalMove)
        self.setDropIndicatorShown(False)        # 亮线由 paintEvent 自绘
        self._drop_rect: Optional[QRect] = None
        self.setUniformRowHeights(True)
        self.setFont(QFont("SimSun", 11))
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._on_context_menu)
        self.currentItemChanged.connect(self._on_current_changed)
        # 无激活勾选框 → 不连 itemChanged（合成卡片体内步骤激活在卡片视图编辑）

        self._shortcut_del = QShortcut(QKeySequence.Delete, self, self._act_delete)
        self._shortcut_f2 = QShortcut("F2", self, self._act_rename)
        self._read_only = False             # 执行期只读：可点击查看，禁编辑操作

        self.refresh()

    def set_read_only(self, ro: bool) -> None:
        """执行期只读：条目仍可点击选中（切换查看卡片），但禁拖拽/右键菜单/
        Del/F2 快捷键。"""
        self._read_only = ro
        self.setDragDropMode(QAbstractItemView.NoDragDrop
                             if ro else QAbstractItemView.InternalMove)
        self._shortcut_del.setEnabled(not ro)
        self._shortcut_f2.setEnabled(not ro)

    def refresh(self, current_path: Optional[str] = None) -> None:
        """从 store 重建树（组/卡片键值）；保留展开，可指定当前项。"""
        expanded = set(self._expanded_paths())
        cur = current_path if current_path is not None else self._current_path()
        # refresh_error_marks 的 setFont/setForeground 走 model setData；
        # 整个重建处于信号屏蔽内，防中途异常残留屏蔽致后续操作静默失效。
        self.blockSignals(True)
        try:
            self.clear()
            root = self.invisibleRootItem()
            if root is not None:
                self._fill(root, "")
            for it in self._walk_items():
                if it.data(0, _PATH_ROLE) in expanded:
                    it.setExpanded(True)
            target = self.find_item(cur)
            if target is not None:
                self.setCurrentItem(target)
            self.refresh_error_marks()       # 卡片 io 错误标记随重建同步
        finally:
            self.blockSignals(False)
        self._on_current_changed(self.currentItem(), None)

    def refresh_error_marks(self) -> None:
        """按卡片体内 io 校验重标错误条目：出错卡片与其所属组（含祖先组）
        红色加粗；合规恢复默认。卡片错误变化时由宿主调用（errors_changed）。

        纯局部作用域：带参卡片 body 步骤 io._tree 换**校验树**（inputs 预填，
        区别于运行期 build_local_tree）→ 绑 ``{{全局}}`` 判非法 → 红标；参数less
        卡片 body 走全局树（同 v1，运行期不换树）。故未选中的卡片也能被标红
        （与编辑期 _apply_local_picker 一致，避免「树不红、进了编辑才红」）。
        """
        bad: set = set()
        gtree = self._manager.tree
        for p, is_group in self._store.walk():
            if is_group:
                continue
            try:
                lst = self._store.get_body(p)
                sig = self._store.get_signature(p)
            except FileNotFoundError:
                continue
            vtree = (gtree if sig.is_empty()
                     else build_validation_tree(sig, self._manager.package))
            for s in lst.steps:
                s.io._tree = vtree
            if any(not s.io.is_valid for s in lst.steps):
                bad.add(p)
        mark = set(bad)                      # 出错卡片 + 各级祖先组
        for p in bad:
            parent = p.rsplit("/", 1)[0] if "/" in p else ""
            while parent:
                mark.add(parent)
                parent = parent.rsplit("/", 1)[0] if "/" in parent else ""
        default_fg = self.palette().text()
        self.blockSignals(True)
        try:
            for it in self._walk_items():
                p = it.data(0, _PATH_ROLE)
                if not p:
                    continue
                err = p in mark
                f = it.font(0)
                f.setBold(err)
                it.setFont(0, f)
                it.setForeground(0, QColor(200, 50, 40) if err else default_fg)
        finally:
            self.blockSignals(False)

    # ---- 树构建 ----
    def _fill(self, parent_item: QTreeWidgetItem, prefix: str) -> None:
        style = self.style()
        for name, is_group in self._children_of(prefix):
            path = name if not prefix else prefix + "/" + name
            item = QTreeWidgetItem(parent_item)
            item.setText(0, name)
            item.setData(0, _PATH_ROLE, path)
            if is_group:
                if style is not None:
                    item.setIcon(0, style.standardIcon(QStyle.SP_DirIcon))
                self._fill(item, path)
            else:
                item.setIcon(0, _make_card_icon())

    def _children_of(self, prefix: str) -> List[Tuple[str, bool]]:
        """prefix 的直接子项（walk 序 = 创建序；树显示序）。"""
        out: List[Tuple[str, bool]] = []
        for path, is_group in self._store.walk():
            parent = path.rsplit("/", 1)[0] if "/" in path else ""
            if parent != prefix:
                continue
            out.append((path.rsplit("/", 1)[-1], is_group))
        return out

    def first_card_path(self) -> Optional[str]:
        """树显示序（= walk 序）第一个卡片路径；无卡片 → None。"""
        for p, is_group in self._store.walk():
            if not is_group:
                return p
        return None

    def _walk_items(self):
        def rec(item):
            for i in range(item.childCount()):
                ch = item.child(i)
                if ch is None:
                    continue
                yield ch
                yield from rec(ch)
        root = self.invisibleRootItem()
        if root is not None:
            yield from rec(root)

    def find_item(self, path: Optional[str]) -> Optional[QTreeWidgetItem]:
        if not path:
            return None
        for it in self._walk_items():
            if it.data(0, _PATH_ROLE) == path:
                return it
        return None

    def _expanded_paths(self) -> List[str]:
        return [it.data(0, _PATH_ROLE) for it in self._walk_items()
                if it.isExpanded()]

    # ---- 选中 / 信号 ----
    def _current_path(self) -> str:
        cur = self.currentItem()
        return cur.data(0, _PATH_ROLE) if cur is not None else ""

    def _on_current_changed(self, cur, _prev) -> None:
        path = cur.data(0, _PATH_ROLE) if cur is not None else ""
        if not path:
            return
        try:
            self._store.get(path)
        except FileNotFoundError:
            return                       # 组不触发
        self.composite_selected.emit(path)

    # ---- 右键菜单 ----
    def _on_context_menu(self, pos) -> None:
        if self._read_only:
            return
        item = self.itemAt(pos)
        if item is not None and not item.isSelected():
            self.setCurrentItem(item)
        context_group = self._group_of(item)
        tops = self._selected_paths_top()
        # 「前方/后方」锚点：右键项为卡片叶子才可用
        anchor = None
        if item is not None:
            p = item.data(0, _PATH_ROLE)
            if p and not self._is_group(p):
                anchor = p

        menu = QMenu(self)
        sub_add = menu.addMenu("添加的子项")
        a_new_head = sub_add.addAction("头部添加合成卡片…")
        a_new_tail = sub_add.addAction("尾部添加合成卡片…")
        if anchor is not None:
            a_new_before = sub_add.addAction("在此卡片前添加…")
            a_new_after = sub_add.addAction("在此卡片后添加…")
        else:
            a_new_before = a_new_after = None
        sub_add.addSeparator()
        a_group_head = sub_add.addAction("头部添加组…")
        a_group_tail = sub_add.addAction("尾部添加组…")
        if item is not None:
            p = item.data(0, _PATH_ROLE)
            if p and self._is_group(p):
                a_group_before = sub_add.addAction("在此组前添加…")
                a_group_after = sub_add.addAction("在此组后添加…")
            elif p:
                a_group_before = sub_add.addAction("在此前添加组…")
                a_group_after = sub_add.addAction("在此后添加组…")
            else:
                a_group_before = a_group_after = None
        else:
            a_group_before = a_group_after = None

        sub_paste = menu.addMenu("粘贴的子项")
        a_paste_head = sub_paste.addAction("粘贴到卡片头")
        a_paste_tail = sub_paste.addAction("粘贴到卡片尾")
        if anchor is not None:
            a_paste_before = sub_paste.addAction("粘贴到此卡片前")
            a_paste_after = sub_paste.addAction("粘贴到此卡片后")
        else:
            a_paste_before = a_paste_after = None
        menu.addSeparator()
        a_copy = menu.addAction("复制")
        a_cut = menu.addAction("剪切")
        menu.addSeparator()
        a_rename = menu.addAction("重命名\tF2")
        a_delete = menu.addAction("删除\tDel")

        a_copy.setEnabled(len(tops) == 1)
        a_cut.setEnabled(len(tops) == 1)
        sub_paste.setEnabled(self._clipboard.items is not None)
        a_rename.setEnabled(len(tops) == 1)
        a_delete.setEnabled(bool(tops))

        action = menu.exec_(self.viewport().mapToGlobal(pos))
        if action is a_new_head:
            self._act_new_empty_card(context_group, 0)
        elif action is a_new_tail:
            self._act_new_empty_card(context_group, None)
        elif action is a_new_before and anchor is not None:
            self._act_new_empty_card(context_group, self._sibling_index(anchor))
        elif action is a_new_after and anchor is not None:
            self._act_new_empty_card(
                context_group, self._sibling_index(anchor) + 1)
        elif action is a_group_head:
            self._act_add_group(context_group, 0)
        elif action is a_group_tail:
            self._act_add_group(context_group, None)
        elif a_group_before is not None and action is a_group_before:
            self._act_add_group(
                p.rsplit("/", 1)[0] if "/" in p else "",
                self._sibling_index(p))
        elif a_group_after is not None and action is a_group_after:
            self._act_add_group(
                p.rsplit("/", 1)[0] if "/" in p else "",
                self._sibling_index(p) + 1)
        elif action is a_paste_head:
            self._act_paste(context_group, 0)
        elif action is a_paste_tail:
            self._act_paste(context_group, None)
        elif action is a_paste_before and anchor is not None:
            self._act_paste(context_group, self._sibling_index(anchor))
        elif action is a_paste_after and anchor is not None:
            self._act_paste(context_group, self._sibling_index(anchor) + 1)
        elif action is a_copy:
            self._act_copy()
        elif action is a_cut:
            self._act_cut()
        elif action is a_rename:
            self._act_rename()
        elif action is a_delete:
            self._act_delete()

    def _group_of(self, item: Optional[QTreeWidgetItem]) -> str:
        """item 所在组：组项取自身，叶子取父组，空白 → 空串（根）。"""
        if item is None:
            return ""
        p = item.data(0, _PATH_ROLE)
        if not p:
            return ""
        if self._is_group(p):
            return p
        return p.rsplit("/", 1)[0] if "/" in p else ""

    def _is_group(self, path: str) -> bool:
        """路径是否为组（get 抛 FileNotFoundError ⇔ 组）。"""
        try:
            self._store.get(path)
        except FileNotFoundError:
            return True
        return False

    def _selected_paths(self) -> List[str]:
        return [it.data(0, _PATH_ROLE) for it in self.selectedItems()
                if it.data(0, _PATH_ROLE)]

    def _selected_paths_top(self) -> List[str]:
        """选中集「顶层化」：去掉被另一选中项包含的子项，按 walk 序输出。"""
        paths = self._selected_paths()
        tops = []
        for p in paths:
            if not any(o != p and p.startswith(o + "/") for o in paths):
                tops.append(p)
        order = {p: i for i, (p, _g) in enumerate(self._store.walk())}
        return sorted(tops, key=lambda p: order.get(p, len(order)))

    # ---- 操作 ----
    @staticmethod
    def _insert_node(node: dict, name: str, value: Any,
                     index: Optional[int]) -> None:
        """按 walk 序把 ``(name, value)`` 插到父节点下标 ``index`` 处
       （None / 越界 → 尾部追加）。"""
        if index is None or index >= len(node):
            node[name] = value
        else:
            items = list(node.items())
            items.insert(max(0, index), (name, value))
            node.clear()
            node.update(items)

    def _act_add_group(self, context_group: str = "",
                       index: Optional[int] = None) -> None:
        """新建组：弹窗输入组名，确认后创建空组（可指定位置）。"""
        name, ok = QInputDialog.getText(self, "添加组", "组名：")
        if not ok:
            return
        name = name.strip()
        if not name or "/" in name or name in (".", ".."):
            QMessageBox.warning(self, "添加组", "名称非法")
            return
        full = (context_group + "/" + name) if context_group else name
        try:
            self._store.get(full)      # 目标已存在 → 提示
        except FileNotFoundError:
            pass
        else:
            QMessageBox.warning(self, "添加组", "无法添加：已存在 %r" % full)
            return
        node = self._store.root
        if context_group:
            for seg in context_group.split("/"):
                node = node[seg]
        self._insert_node(node, name, {}, index)
        self._changed(full)

    def _act_new_empty_card(self, context_group: str = "",
                            index: Optional[int] = None) -> None:
        """新建空合成卡片：弹窗输入名称，确认后创建无步骤的 :class:`StepList`
        作卡片体。位置语义同步骤列表树（头部=0 / 尾部=None / 此卡片前=锚下标 /
        此卡片后=锚下标+1）；位置 = walk 序（树显示序）。"""
        name, ok = QInputDialog.getText(self, "新建合成卡片", "卡片名称：",
                                        text="新卡片")
        if not ok:
            return
        name = name.strip()
        if not name:
            QMessageBox.warning(self, "新建合成卡片", "名称不能为空")
            return
        full = self._dedup_name(context_group, name)
        node = self._store.root
        if context_group:
            for seg in context_group.split("/"):
                node = node[seg]
        name = full.rsplit("/", 1)[-1]
        self._insert_node(node, name, StepList.create_empty(), index)
        self._changed(full)

    def _sibling_index(self, path: str) -> int:
        """path 在父层 walk 序中的下标（「此卡片前/后」锚点定位）。"""
        parent = path.rsplit("/", 1)[0] if "/" in path else ""
        idx = 0
        for p, _is_group in self._store.walk():
            pp = p.rsplit("/", 1)[0] if "/" in p else ""
            if pp != parent:
                continue
            if p == path:
                return idx
            idx += 1
        return idx

    def _act_copy(self) -> None:
        tops = self._selected_paths_top()
        if len(tops) != 1:
            return                       # 剪贴板单条目契约 → 复制限单选
        path = tops[0]
        name = path.rsplit("/", 1)[-1]
        self._clipboard.items = (name, self._triples_of(path))

    def _triples_of(self, path: str) -> List[Tuple[str, bool, Optional[List[str]]]]:
        """路径 → 先序三元组 ``(相对路径, 是否组, 格式串|None)``。"""
        out: List[Tuple[str, bool, Optional[List[str]]]] = []
        try:
            self._store.get(path)
        except FileNotFoundError:
            out.append(("", True, None))                 # 组自身
            for child, is_group in self._store.walk():
                if not child.startswith(path + "/"):
                    continue
                rel = child[len(path) + 1:]
                if is_group:
                    out.append((rel, True, None))
                else:
                    out.append((rel, False,
                                self._store.get_body(child).to_format_strings()))
            return out
        out.append(("", False, self._store.get_body(path).to_format_strings()))
        return out

    def _act_cut(self) -> None:
        tops = self._selected_paths_top()
        if len(tops) != 1:
            return
        self._act_copy()
        for p in tops:
            try:
                self._store.remove(p)
            except FileNotFoundError:
                continue
        self._changed()

    def _act_paste(self, context_group: str = "",
                   index: Optional[int] = None) -> None:
        """粘贴剪贴板到 ``context_group`` 层；``index`` 同新建卡片语义。"""
        if self._clipboard.items is None:
            return
        name, triples = self._clipboard.items
        target = self._dedup_name(context_group, name)
        top_name = target.rsplit("/", 1)[-1]
        node = self._store.root
        if context_group:
            for seg in context_group.split("/"):
                node = node[seg]
        first_group = triples[0][1]
        if index is None or index >= len(node):
            if first_group:
                self._store.add_group(target)
            elif triples[0][2] is not None:
                self._store.add_list(
                    target, StepList.from_format_strings(
                        triples[0][2], self._manager))
        else:
            if first_group:
                self._insert_node(node, top_name, {}, max(0, index))
            elif triples[0][2] is not None:
                self._insert_node(
                    node, top_name,
                    StepList.from_format_strings(triples[0][2], self._manager),
                    max(0, index))
        for rel, is_group, fmts in triples[1:]:
            full = (target + "/" + rel) if rel else target
            try:
                if is_group:
                    self._store.add_group(full)
                else:
                    if fmts is None:
                        continue
                    self._store.add_list(
                        full, StepList.from_format_strings(fmts, self._manager))
            except (ValueError, FileExistsError) as e:
                QMessageBox.warning(self, "粘贴", "粘贴 %s 失败：%s" % (full, e))
                continue
        self._changed(target)

    def _dedup_name(self, parent: str, name: str) -> str:
        """同父下重名去重：name(1)、name(2)…；返回完整路径。"""
        known = {p for p, _ in self._store.walk()}

        def exists(candidate: str) -> bool:
            p = (parent + "/" + candidate) if parent else candidate
            return p in known

        def full(candidate: str) -> str:
            return (parent + "/" + candidate) if parent else candidate

        if not exists(name):
            return full(name)
        i = 1
        while exists("%s(%d)" % (name, i)):
            i += 1
        return full("%s(%d)" % (name, i))

    def _act_rename(self) -> None:
        old = self._current_path()
        if not old:
            return
        name = old.rsplit("/", 1)[-1]
        new_name, ok = QInputDialog.getText(self, "重命名", "新名称：", text=name)
        if not ok:
            return
        new_name = new_name.strip()
        if not new_name or "/" in new_name or new_name in (".", ".."):
            QMessageBox.warning(self, "重命名", "名称非法")
            return
        parent = old.rsplit("/", 1)[0] if "/" in old else ""
        new_path = (parent + "/" + new_name) if parent else new_name
        if new_path == old:
            return
        try:
            self._store.rename(old, new_name)
        except (ValueError, FileExistsError, FileNotFoundError) as e:
            QMessageBox.warning(self, "重命名", "无法重命名：%s" % e)
            return
        # 定义路径已变 → 改指所有引用旧路径的步骤列表内合成卡片条目
        # （步骤列表树与其它合成卡片体内皆含），否则卡片名不更新且运行时变悬空。
        if self._on_rename is not None:
            self._on_rename(old, new_path)
        self._changed(new_path)

    def _act_delete(self) -> None:
        tops = self._selected_paths_top()
        if not tops:
            return
        if QMessageBox.question(
                self, "删除", "确定删除 %d 项？删除的合成卡片不可恢复。"
                % len(tops),
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes) != QMessageBox.Yes:
            return
        before = [p for p, g in self._store.walk() if not g]   # 删除前卡片序
        for p in tops:
            try:
                self._store.remove(p)
            except FileNotFoundError:
                continue
        self._changed(self._pick_next(before, tops))

    # ---- 拖拽移动（排序 / 批量剪切粘贴） ----
    def dropEvent(self, event) -> None:  # noqa: N802 (Qt 命名)
        """InternalMove 拖拽落点：选中项（含多选）移动到目标位。

        位置语义同步骤列表树：OnItem → 目标之后、AboveItem/BelowItem → 同层前/后、
        空白 → root 尾部。移动由 :meth:`_move_paths` 自行完成（store 变更 +
        refresh 重建），因此内部拖拽**也一律 ignore**（否则 Qt 收尾 clearOrRemove
        删行 → 树缺行而 store 完好）。
        """
        if event.source() is not self:
            event.ignore()
            return
        target = self.itemAt(event.pos())
        target_path = target.data(0, _PATH_ROLE) if target is not None else ""
        paths = self._selected_paths_top()
        try:
            self._move_paths(paths, target_path, self.dropIndicatorPosition())
        except Exception as e:
            QMessageBox.warning(self, "移动", "移动失败：%s" % e)
        event.ignore()
        self._drop_rect = None
        self.viewport().update()

    def _move_paths(self, paths: List[str], target_path: str,
                    position: QAbstractItemView.DropIndicatorPosition) -> bool:
        """把 ``paths`` 移到 ``target_path`` 旁/尾。实现 = 「剪切粘贴」：
        序列化 → 删除 → 按目标位重建（与 _act_paste 同构）。

        事务性预检：删除源之前先验证全部格式串可还原（模板缺失 → 抛
        ValueError）→ 弹窗 + 拒绝，数据不动。返回是否执行。
        """
        if not paths:
            return False
        if target_path and (target_path in paths
                            or any(target_path.startswith(p + "/") for p in paths)):
            return False                       # 拖到自身/自身子树 → 拒绝
        if not target_path:
            parent = ""
        else:
            parent = target_path.rsplit("/", 1)[0] if "/" in target_path else ""
        snap = [(p.rsplit("/", 1)[-1], self._triples_of(p)) for p in paths]
        for _n, triples in snap:
            for _rel, is_group, fmts in triples:
                if is_group or fmts is None:
                    continue
                try:
                    StepList.from_format_strings(fmts, self._manager)
                except ValueError as e:
                    QMessageBox.warning(self, "移动", "移动失败：%s" % e)
                    return False
        for p in paths:
            try:
                self._store.remove(p)
            except FileNotFoundError:
                continue
        node = self._store.root
        if parent:
            for seg in parent.split("/"):
                node = node[seg]
        if not target_path:
            index: Optional[int] = None
        else:
            index = self._sibling_index(target_path)
            if position != QAbstractItemView.AboveItem:
                index += 1                     # BelowItem / OnItem → 目标之后
        first_new: Optional[str] = None
        for i, (name, triples) in enumerate(snap):
            top_name = self._dedup_name(parent, name).rsplit("/", 1)[-1]
            at = None if index is None else max(0, index + i)
            if triples[0][1]:
                self._insert_node(node, top_name, {}, at)
            else:
                self._insert_node(
                    node, top_name,
                    StepList.from_format_strings(triples[0][2], self._manager),
                    at)
            target = (parent + "/" + top_name) if parent else top_name
            if first_new is None:
                first_new = target
            for rel, is_group, fmts in triples[1:]:
                full = (target + "/" + rel) if rel else target
                if is_group:
                    self._store.add_group(full)
                else:
                    if fmts is None:
                        continue
                    self._store.add_list(
                        full, StepList.from_format_strings(fmts, self._manager))
        self._changed(first_new)
        return True

    # ---- 拖拽亮线（自定义绘制） ----
    _LINE_H = 3

    def _last_visible_item(self) -> Optional[QTreeWidgetItem]:
        """最后一个可见（展开链上）条目；空树 → None。"""
        last = None
        it = self.topLevelItem(0)
        while it is not None:
            last = it
            it = self.itemBelow(it)
        return last

    def _update_drop_line(self, pos, position: Optional[int] = None) -> None:
        """按拖拽悬停位置计算亮线矩形并重绘（同步骤列表树规则）。"""
        if position is None:
            position = self.dropIndicatorPosition()
        target = self.itemAt(pos)
        if target is not None:
            r = self.visualItemRect(target)
            if position == QAbstractItemView.AboveItem:
                rect = QRect(0, r.top(), self.viewport().width(), self._LINE_H)
            else:   # BelowItem / OnItem → 条目尾部
                rect = QRect(0, r.bottom() + 1 - self._LINE_H,
                             self.viewport().width(), self._LINE_H)
        else:
            last = self._last_visible_item()
            if last is not None:
                r = self.visualItemRect(last)
                rect = QRect(0, r.bottom() + 1 - self._LINE_H,
                             self.viewport().width(), self._LINE_H)
            else:
                rect = QRect(0, 0, self.viewport().width(), self._LINE_H)
        if rect != self._drop_rect:
            old, self._drop_rect = self._drop_rect, rect
            vp = self.viewport()
            if old is not None:
                vp.update(old)
            if rect is not None:
                vp.update(rect)

    def dropMoveEvent(self, event: QDragMoveEvent) -> None:  # noqa: N802
        self._update_drop_line(event.pos())
        event.accept()

    def dragLeaveEvent(self, event: QDragLeaveEvent) -> None:  # noqa: N802
        if self._drop_rect is not None:
            self._drop_rect = None
            self.viewport().update()
        super().dragLeaveEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802
        super().paintEvent(event)
        if self._drop_rect is not None:
            p = QPainter(self.viewport())
            p.fillRect(self._drop_rect, QColor(72, 128, 220, 255))
            p.end()

    def _pick_next(self, before: List[str], deleted: List[str]) -> Optional[str]:
        """删除后要显示的卡片：被删项之后第一个仍存在的；否则之前最后一个；
        否则第一个；无卡片 → None。"""
        dead = set()
        for p in before:
            if any(p == d or p.startswith(d + "/") for d in deleted):
                dead.add(p)
        if not dead:
            after = [p for p, g in self._store.walk() if not g]
            return after[0] if after else None
        last_del = max(i for i, p in enumerate(before) if p in dead)
        for p in before[last_del + 1:]:
            if p not in dead:
                return p
        first_del = min(i for i, p in enumerate(before) if p in dead)
        for p in reversed(before[:first_del]):
            if p not in dead:
                return p
        after = [p for p, g in self._store.walk() if not g]
        return after[0] if after else None

    # ---- 变更收尾 ----
    def _changed(self, current_path: Optional[str] = None) -> None:
        """刷新树 + 发 store_changed + 回调（上层保存 composites.json）。"""
        self.refresh(current_path)
        self.store_changed.emit()
        self._on_changed()


# ================================================================
# 冒烟演示：直接 ``python -m widgets.树.composite_tree_widget`` 运行
# ================================================================
if __name__ == "__main__":
    import sys

    from PyQt5.QtWidgets import QApplication, QInputDialog, QMessageBox

    from model.工程.kscp_package import KscpPackage
    from model.变量.project_variable import ProjectVariable
    from model.步骤.step import Step
    from model.步骤.step_list import StepList
    from model.步骤.step_manager import StepManager
    from model.变量.variable_tree import VariableTree
    from model.合成卡片.composite_card import CompositeCard
    from model.合成卡片.composite_card_store import CompositeCardStore
    from widgets.卡片.step_list_view import StepClipboard

    app = QApplication.instance() or QApplication(sys.argv)

    pkg = KscpPackage.create_empty()
    tree = VariableTree.create_empty()
    tree.add("n1", ProjectVariable.create("number", 100, pkg))

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
    pkg.write_file("actions/示例.py", GOOD.encode("utf-8"))
    mgr = StepManager(pkg, tree)
    mgr.load()

    def make_step() -> Step:
        s = mgr.create_step("示例")
        s.io.change_value("input", 0, "5")
        s.io.change_value("output", 0, "n1")
        return s

    store = CompositeCardStore.create_empty()
    sl = StepList.create_empty()
    sl.add(make_step())
    store.add_list("登录", sl)
    store.add_group("战斗")
    slc = StepList.create_empty()
    slc.add(make_step())
    store.add_list("战斗/起手", slc)
    store.add_group("空组")

    changes = []
    clip = StepClipboard()
    tw = CompositeTreeWidget(store, mgr, clip, lambda: changes.append(1))

    # 显示序 = walk 序 = 创建序
    top = [tw.topLevelItem(i).text(0)
           for i in range(tw.topLevelItemCount())]
    assert top == ["登录", "战斗", "空组"], top
    g = tw.find_item("战斗")
    assert g is not None and g.childCount() == 1
    assert tw.find_item("战斗/起手") is not None
    assert not tw.find_item("登录").icon(0).isNull()

    # composite_selected 仅叶子触发；组不触发
    seen = []
    tw.composite_selected.connect(seen.append)
    tw.setCurrentItem(tw.find_item("登录"))
    assert seen == ["登录"]
    tw.setCurrentItem(g)                       # 组不触发
    assert seen == ["登录"]

    # 新建合成卡片（补丁命名弹窗）
    orig_dlg = QInputDialog.getText
    QInputDialog.getText = staticmethod(lambda *a, **k: ("新卡", True))
    try:
        tw._act_new_empty_card("", 0)
    finally:
        QInputDialog.getText = orig_dlg
    assert "新卡" in store.paths() and changes == [1]

    # 复制卡片 → 剪贴板三元组；粘贴到组内（无重名）
    tw.setCurrentItem(tw.find_item("登录"))
    tw._act_copy()
    assert clip.items[0] == "登录"
    assert clip.items[1] == [("", False, sl.to_format_strings())]
    g = tw.find_item("战斗")
    assert g is not None
    tw.setCurrentItem(g)
    tw._act_paste("战斗")
    assert "战斗/登录" in store.paths()

    # 组复制 → 整棵子树；粘贴到根 → 顶层重名去重
    g = tw.find_item("战斗")
    tw.setCurrentItem(g)
    tw._act_copy()
    assert ("", True, None) in clip.items[1]
    tw.setCurrentItem(None)
    tw._act_paste("")
    assert "战斗(1)/起手" in store.paths()

    # 剪切 = 复制 + 删除
    tw.setCurrentItem(tw.find_item("战斗(1)"))
    tw._act_cut()
    assert "战斗(1)" not in store.paths()

    # 重命名
    tw.setCurrentItem(tw.find_item("战斗/登录"))
    QInputDialog.getText = staticmethod(lambda *a, **k: ("改名", True))
    try:
        tw._act_rename()
    finally:
        QInputDialog.getText = orig_dlg
    assert "战斗/改名" in store.paths()
    assert tw._current_path() == "战斗/改名"

    # 删除（组 = 整棵子树）
    orig_q = QMessageBox.question
    QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)
    try:
        tw.setCurrentItem(tw.find_item("战斗/改名"))
        tw._act_delete()
    finally:
        QMessageBox.question = orig_q
    assert "战斗/改名" not in store.paths()

    # ---- 新建空卡片：4 位置（walk 序）；同父重名去重 ----
    store4 = CompositeCardStore.create_empty()
    store4.add_group("组甲")
    store4.add_list("组甲/中卡", StepList.create_empty())
    store4.add_list("组甲/后卡", StepList.create_empty())
    store4.add_list("顶卡", StepList.create_empty())
    tw4 = CompositeTreeWidget(store4, mgr, StepClipboard(), lambda: None)
    QInputDialog.getText = staticmethod(lambda *a, **k: ("新卡", True))
    try:
        tw4._act_new_empty_card("组甲", 0)        # 头部 → 组甲首位
        assert [p for p, _g in store4.walk()] == \
            ["组甲", "组甲/新卡", "组甲/中卡", "组甲/后卡", "顶卡"]
        tw4._act_new_empty_card("组甲", None)     # 尾部 → 去重 新卡(1)
        assert "组甲/新卡(1)" in store4.paths()
    finally:
        QInputDialog.getText = orig_dlg

    # ---- 删除后显示下一个卡片 ----
    store_d = CompositeCardStore.create_empty()
    for nm in ("甲", "乙", "丙"):
        store_d.add_list(nm, StepList.create_empty())
    tw_d = CompositeTreeWidget(store_d, mgr, StepClipboard(), lambda: None)
    QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)
    try:
        tw_d.setCurrentItem(tw_d.find_item("乙"))
        tw_d._act_delete()                       # 删中间 → 下一个「丙」
        assert tw_d._current_path() == "丙"
    finally:
        QMessageBox.question = orig_q

    # ---- 拖拽移动（AboveItem=同层前、BelowItem=同层后、OnItem=目标之后） ----
    store_dd = CompositeCardStore.create_empty()
    for nm in ("甲", "乙", "丙"):
        store_dd.add_list(nm, StepList.create_empty())
    tw_dd = CompositeTreeWidget(store_dd, mgr, StepClipboard(), lambda: None)
    assert tw_dd._move_paths(["丙"], "乙", QAbstractItemView.AboveItem)
    assert [p for p, _g in store_dd.walk()] == ["甲", "丙", "乙"]
    assert tw_dd._move_paths(["甲"], "丙", QAbstractItemView.BelowItem)
    assert [p for p, _g in store_dd.walk()] == ["丙", "甲", "乙"]
    # 拖到自身/自身子树 → 拒绝
    assert not tw_dd._move_paths(["甲"], "甲", QAbstractItemView.OnItem)

    # ---- 错误标记：卡片体内 io 非法 → 卡片 + 祖先组红色加粗 ----
    store_e = CompositeCardStore.create_empty()
    store_e.add_group("组A")
    bad = StepList.create_empty()
    bad.add(mgr.create_step("示例"))             # 空 io 槽 → 非法
    store_e.add_list("组A/坏卡", bad)
    tw_e = CompositeTreeWidget(store_e, mgr, StepClipboard(), lambda: None)
    from PyQt5.QtGui import QColor as _QColor
    _RED = _QColor(200, 50, 40)
    it_bad = tw_e.find_item("组A/坏卡")
    it_grp = tw_e.find_item("组A")
    assert it_bad is not None and it_grp is not None
    assert it_bad.font(0).bold() and it_bad.foreground(0).color() == _RED
    assert it_grp.font(0).bold() and it_grp.foreground(0).color() == _RED
    # 修复坏步骤 → 重标恢复默认
    s_bad = store_e.get_body("组A/坏卡").steps[0]
    s_bad.io.change_value("input", 0, "5")
    s_bad.io.change_value("output", 0, "n1")
    tw_e.refresh_error_marks()
    assert not it_bad.font(0).bold()
    assert not it_grp.font(0).bold()

    # ---- Issue 2：带参卡片 body 步骤绑 {{全局}} → 校验树无该名 → 红卡
    # （编辑期即红，与运行期局部树缺失 → ERROR 一致，修「编辑期不红、运行期才红」）；
    # 绑 {{输入参数}} → 合规（校验树 inputs 预填）----
    from model.合成卡片.composite_signature import Param, CompositeSignature
    sig2 = CompositeSignature(inputs=[Param("x", "number")],
                              outputs=[Param("y", "number")])
    bodyP = StepList.create_empty()
    bodyP.add(mgr.create_step("示例"))
    store_e.add_list("参数卡", bodyP, signature=sig2)
    tw_e.refresh()                       # 新增卡片入树
    sp = store_e.get_body("参数卡").steps[0]
    sp.io.change_value("output", 0, "y")         # 输出绑输出参数 y（合规：校验树有 y）
    sp.io.change_value("input", 0, "{{n1}}")     # 输入绑全局 n1（全局树有，校验树无）
    tw_e.refresh_error_marks()
    it_p = tw_e.find_item("参数卡")
    assert it_p is not None and it_p.font(0).bold()   # 红卡
    assert not sp.io.is_valid                            # 校验树无 n1 → 非法
    # 改绑 {{x}}（输入参数，number）→ 校验树有 x → 合规
    sp.io.change_value("input", 0, "{{x}}")
    tw_e.refresh_error_marks()
    assert sp.io.is_valid
    assert not it_p.font(0).bold()

    # ---- 只读切换：不抛 ----
    tw.set_read_only(True)
    tw.set_read_only(False)

    print("CompositeTreeWidget smoke OK")
