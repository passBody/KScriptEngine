# -*- coding: utf-8 -*-
"""
步骤列表管理树（GUI 控件）
========================

:class:`StepListTreeWidget` 是「总步骤列表模型」（:class:`model.step_list_store.StepListStore`）
的管理树：组 = 文件夹图标，叶子 = 步骤列表（只显示键值）。上下文菜单支持
添加组 / 复制 / 剪切 / 粘贴 / 重命名 / 删除；点击列表发 :data:`list_selected`，
任何变更后发 :data:`store_changed` 并调用 ``on_changed`` 回调（上层保存
``step_list.json``）。

剪贴板（:class:`widgets.step_list_view.StepClipboard`）与步骤列表视图共享；
列表/组剪贴板 = ``(名, [(相对路径, 是否组, 格式串列表|None), ...])``，
粘贴时经 :class:`StepManager` 解码重建（列表）或 ``add_group`` 递归重建（组）。

基本用法
--------
::

    tree = StepListTreeWidget(store, mgr, clipboard, on_changed)
    tree.list_selected.connect(show_list)   # 点击列表 → 视图显示
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

from model.step_list import StepList
from model.step_list_store import StepListStore
from model.step_manager import StepManager
from widgets.step_list_view import StepClipboard

__all__ = ["StepListTreeWidget"]

_PATH_ROLE = 0x0100   # Qt.UserRole


def _make_list_icon() -> QIcon:
    """列表叶子小图标：橙色圆角方块内三条浅色横线（与步骤模板树同款）。"""
    pm = QPixmap(18, 18)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#e67e22"))
    p.drawRoundedRect(2, 2, 14, 14, 3, 3)
    p.setBrush(QColor("#fff3e0"))
    for y in (6, 9, 12):
        p.drawRoundedRect(5, y, 8, 2, 1, 1)
    p.end()
    return QIcon(pm)


class StepListTreeWidget(QTreeWidget):
    """步骤列表管理树：只显示键值（组 = 文件夹，列表 = 图标 + 名）。"""

    list_selected = pyqtSignal(str)      # 点击列表叶子 → 路径
    store_changed = pyqtSignal()         # 任何变更后发出（宿主处理当前列表被删等）

    def __init__(self, store: StepListStore, manager: StepManager,
                 clipboard: StepClipboard, on_changed: Callable[[], None],
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._store = store
        self._manager = manager
        self._clipboard = clipboard
        self._on_changed = on_changed

        self.setHeaderHidden(True)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        # 拖拽 = 移动排序（取代默认框选多选；shift/ctrl 多选已够用）：
        # 单条目拖拽换序，多选拖拽 = 批量剪切粘贴；位置语义见 dropEvent/_move_paths
        self.setDragDropMode(QAbstractItemView.InternalMove)
        # 亮线由 paintEvent 自绘（条目尾部/中间/空白处末尾，见 _update_drop_line），
        # 关闭内置指示器避免双线
        self.setDropIndicatorShown(False)
        self._drop_rect: Optional[QRect] = None
        self.setUniformRowHeights(True)
        self.setFont(QFont("SimSun", 11))
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._on_context_menu)
        self.currentItemChanged.connect(self._on_current_changed)
        self.itemChanged.connect(self._on_item_changed)   # 列表勾选框 → 全部步骤激活/停用

        self._shortcut_del = QShortcut(QKeySequence.Delete, self, self._act_delete)
        self._shortcut_f2 = QShortcut("F2", self, self._act_rename)
        self._read_only = False             # 执行期只读：可点击查看，禁编辑操作
        self._running_path: Optional[str] = None   # 正在执行的列表（▶ 前缀 + 蓝色高亮）

        self.refresh()

    def set_read_only(self, ro: bool) -> None:
        """执行期只读：条目仍可点击选中（切换查看列表），但禁拖拽/右键菜单/
        Del/F2 快捷键/勾选框操作。变量/模板/资源树走整树禁用（无查看需求）。"""
        self._read_only = ro
        self.setDragDropMode(QAbstractItemView.NoDragDrop
                             if ro else QAbstractItemView.InternalMove)
        self._shortcut_del.setEnabled(not ro)
        self._shortcut_f2.setEnabled(not ro)

    def set_running_path(self, path: Optional[str]) -> None:
        """高亮正在执行的列表（▶ 前缀 + 蓝色加粗）；None 清除。路径未变不刷新。"""
        if path == self._running_path:
            return
        self._running_path = path
        self.refresh()

    def refresh(self, current_path: Optional[str] = None) -> None:
        """从 store 重建树（组/列表键值）；保留展开，可指定当前项。"""
        expanded = set(self._expanded_paths())
        cur = current_path if current_path is not None else self._current_path()
        # refresh_error_marks 的 setFont/setForeground 走 model setData，
        # 同样会发 itemChanged；若在 blockSignals 外，会误触 _on_item_changed
        # 递归重建，clear() 删除外层正在遍历的 item → RuntimeError。
        # 故整个重建（含错误标记）都处于信号屏蔽内。
        # try/finally：中途异常（如 store 数据损坏）也不残留信号屏蔽，
        # 否则树后 续操作全部静默失效（list_selected 不触发 → 视图不刷新）。
        self.blockSignals(True)
        try:
            self.clear()
            root = self.invisibleRootItem()
            if root is not None:
                self._fill(root, "")
            for it in self._walk_items():
                if it.data(0, _PATH_ROLE) in expanded:
                    it.setExpanded(True)
            target = self._find_item(cur)
            if target is not None:
                self.setCurrentItem(target)
            self.refresh_error_marks()   # 列表/组错误标记随重建同步
        finally:
            self.blockSignals(False)
        self._on_current_changed(self.currentItem(), None)

    def refresh_error_marks(self) -> None:
        """按列表当前 io 校验重标错误条目：出错列表与其所属组（含祖先组）
        红色加粗；合规恢复默认。卡片错误变化时由宿主调用（errors_changed）。"""
        bad: set = set()
        for p, is_group in self._store.walk():
            if is_group:
                continue
            try:
                lst = self._store.get(p)
            except FileNotFoundError:
                continue
            if any(not s.io.is_valid for s in lst.steps):
                bad.add(p)
        mark = set(bad)            # 出错列表 + 各级祖先组
        for p in bad:
            parent = p.rsplit("/", 1)[0] if "/" in p else ""
            while parent:
                mark.add(parent)
                parent = parent.rsplit("/", 1)[0] if "/" in parent else ""
        default_fg = self.palette().text()
        for it in self._walk_items():
            p = it.data(0, _PATH_ROLE)
            if not p:
                continue
            err = p in mark
            running = p == self._running_path and not self._is_group(p)
            f = it.font(0)
            f.setBold(err or running)
            it.setFont(0, f)
            if err:
                fg = QColor(200, 50, 40)          # 错误红（优先于执行蓝）
            elif running:
                fg = QColor(27, 122, 214)          # 执行中蓝（哪个列表在执行）
            else:
                fg = default_fg
            it.setForeground(0, fg)

    def refresh_active_marks(self) -> None:
        """卡片激活按钮切换 → 树勾选框同步（不重建树）。

        聚合规则与 _fill 一致：全激活 → Checked、全停用 → Unchecked、混合 →
        PartiallyChecked（三态）；空列表 all([]) → Checked。blockSignals 包裹：
        setCheckState 走 model setData 会发 itemChanged，若泄漏会误触
        _on_item_changed 全量停用/启用。
        """
        def rec(item) -> None:
            path = item.data(0, _PATH_ROLE)
            if path and not self._is_group(path):
                try:
                    lst = self._store.get(path)
                except FileNotFoundError:
                    pass
                else:
                    en = [s.enabled for s in lst.steps]
                    state = (Qt.Checked if all(en) else
                             Qt.Unchecked if not any(en) else Qt.PartiallyChecked)
                    item.setCheckState(0, state)
            for i in range(item.childCount()):
                ch = item.child(i)
                if ch is not None:
                    rec(ch)
        self.blockSignals(True)
        try:
            for i in range(self.topLevelItemCount()):
                it = self.topLevelItem(i)
                if it is not None:
                    rec(it)
        finally:
            self.blockSignals(False)

    # ---- 树构建 ----
    def _fill(self, parent_item: QTreeWidgetItem, prefix: str) -> None:
        style = self.style()
        for name, is_group in self._children_of(prefix):
            path = name if not prefix else prefix + "/" + name
            item = QTreeWidgetItem(parent_item)
            # 正在执行的列表：▶ 前缀（组条目不加——组不执行）
            item.setText(0, ("▶ " + name) if (not is_group and path == self._running_path)
                         else name)
            item.setData(0, _PATH_ROLE, path)
            if is_group:
                if style is not None:
                    item.setIcon(0, style.standardIcon(QStyle.SP_DirIcon))
                # 默认 flags 含 ItemIsUserCheckable，会显示空勾选框；组移除
                item.setFlags(item.flags() & ~Qt.ItemIsUserCheckable)
                self._fill(item, path)
            else:
                item.setIcon(0, _make_list_icon())
                # 列表勾选框（图标左侧）：勾选 = 列表内全部步骤激活；混合激活
                # 显示半选。三态 flag 必须加：非三态 item 上 PartiallyChecked
                # 会被 Qt 强转为 Checked（半选消失且点击语义错乱）。
                # 点击循环（三态：未勾→勾→半选→未勾）见 _on_item_changed。
                item.setFlags(item.flags()
                              | Qt.ItemIsUserCheckable | Qt.ItemIsTristate)
                try:
                    lst = self._store.get(path)
                except FileNotFoundError:
                    state = Qt.Checked
                else:
                    en = [s.enabled for s in lst.steps]
                    state = (Qt.Checked if all(en) else
                             Qt.Unchecked if not any(en) else Qt.PartiallyChecked)
                item.setCheckState(0, state)

    def _children_of(self, prefix: str) -> List[Tuple[str, bool]]:
        """prefix 的直接子项（walk 序 = 创建序；树显示序 = 执行序）。"""
        out: List[Tuple[str, bool]] = []
        for path, is_group in self._store.walk():
            parent = path.rsplit("/", 1)[0] if "/" in path else ""
            if parent != prefix:
                continue
            out.append((path.rsplit("/", 1)[-1], is_group))
        return out

    def first_list_path(self) -> Optional[str]:
        """树显示序（= walk 序 = 执行序）第一个列表路径；无列表 → None。"""
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

    def _find_item(self, path: Optional[str]) -> Optional[QTreeWidgetItem]:
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
        self.list_selected.emit(path)

    def _on_item_changed(self, item, column) -> None:
        """列表勾选框点击 → 列表内全部步骤激活/停用（切换后保存）。

        半选（混合激活）由程序置入（refresh 全程屏蔽信号，不会触达这里）；
        用户点击三态框按 Qt 循环：未勾→勾→半选→未勾。半选到达这里说明
        用户从「全勾」点了一下（或混合框点成未勾），一律按未勾处理 →
        全部停用。全量刷新由 _changed 重建树完成。
        """
        if self._read_only:
            return                      # 执行期只读：勾选框点击无效
        if column != 0:
            return
        if not (item.flags() & Qt.ItemIsUserCheckable):
            return                       # 组无勾选框
        path = item.data(0, _PATH_ROLE)
        if not path or self._is_group(path):
            return
        try:
            lst = self._store.get(path)
        except FileNotFoundError:
            return
        checked = item.checkState(0) == Qt.Checked
        if all(s.enabled == checked for s in lst.steps):
            return                       # 状态未变（程序重建）→ 不触发保存
        for s in lst.steps:
            s.enabled = checked
        # 不能在这里 refresh()：itemChanged 分发栈上 clear() 删除 item，
        # Qt 侧 setCheckState 返回前仍引用它 → use-after-free（segfault）。
        # 勾选框状态 Qt 已更新、store 已改，无需重建树；仅发信号+保存。
        self.store_changed.emit()
        self._on_changed()

    # ---- 右键菜单 ----
    def _on_context_menu(self, pos) -> None:
        if self._read_only:
            return                      # 执行期只读：右键菜单禁弹
        item = self.itemAt(pos)
        if item is not None and not item.isSelected():
            self.setCurrentItem(item)
        context_group = self._group_of(item)
        tops = self._selected_paths_top()
        # 「前方/后方」锚点：右键项为列表叶子才可用（与视图添加菜单一致）
        anchor = None
        if item is not None:
            p = item.data(0, _PATH_ROLE)
            if p and not self._is_group(p):
                anchor = p

        menu = QMenu(self)
        # 主项 + 子项方式：添加类收进「添加的子项」，粘贴类收进「粘贴的子项」
        # （主菜单只留 复制/剪切/重命名/删除；用户诉求：粘贴与添加同四向）
        sub_add = menu.addMenu("添加的子项")
        # 新建空列表的 4 个位置（总列表顺序 = 执行顺序，创建位置重要）：
        # 头部/尾部 → 右击处所在层的首/末位；「此列表前/后」仅右击列表时提供
        a_new_head = sub_add.addAction("头部添加步骤…")
        a_new_tail = sub_add.addAction("尾部添加步骤…")
        if anchor is not None:                 # 右击列表才提供前/后锚定
            a_new_before = sub_add.addAction("在此列表前添加…")
            a_new_after = sub_add.addAction("在此列表后添加…")
        else:
            a_new_before = a_new_after = None
        sub_add.addSeparator()
        # 新建组同样支持 4 个位置：右击组 →「在此组前/后」；右击列表 →
        # 「在此前/后添加组」（锚定到列表的兄弟位置，与空列表的前/后同序）
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

        # 粘贴 4 个位置与添加一致：列表头/列表尾（右击处所在层首/末位）+
        # 「粘贴到此列表前/后」（仅右击列表时锚定到兄弟位置）
        sub_paste = menu.addMenu("粘贴的子项")
        a_paste_head = sub_paste.addAction("粘贴到列表头")
        a_paste_tail = sub_paste.addAction("粘贴到列表尾")
        if anchor is not None:
            a_paste_before = sub_paste.addAction("粘贴到此列表前")
            a_paste_after = sub_paste.addAction("粘贴到此列表后")
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
            self._act_new_empty_list(context_group, 0)
        elif action is a_new_tail:
            self._act_new_empty_list(context_group, None)
        elif action is a_new_before and anchor is not None:
            self._act_new_empty_list(
                context_group, self._sibling_index(anchor))
        elif action is a_new_after and anchor is not None:
            self._act_new_empty_list(
                context_group, self._sibling_index(anchor) + 1)
        elif action is a_group_head:
            self._act_add_group(context_group, 0)
        elif action is a_group_tail:
            self._act_add_group(context_group, None)
        # 菜单取消时 action 为 None：先验锚非 None 再比（None is None 会误触发）
        elif a_group_before is not None and action is a_group_before:
            self._act_add_group(
                p.rsplit("/", 1)[0] if "/" in p else "",   # 锚的父组
                self._sibling_index(p))
        elif a_group_after is not None and action is a_group_after:
            self._act_add_group(
                p.rsplit("/", 1)[0] if "/" in p else "",   # 锚的父组
                self._sibling_index(p) + 1)
        elif action is a_paste_head:
            self._act_paste(context_group, 0)
        elif action is a_paste_tail:
            self._act_paste(context_group, None)
        elif action is a_paste_before and anchor is not None:
            self._act_paste(context_group, self._sibling_index(anchor))
        elif action is a_paste_after and anchor is not None:
            self._act_paste(
                context_group, self._sibling_index(anchor) + 1)
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
        """路径是否为组（仅对树中真实存在的项调用：get 抛 FileNotFoundError ⇔ 组）。"""
        try:
            self._store.get(path)
        except FileNotFoundError:
            return True
        return False

    def _selected_paths(self) -> List[str]:
        return [it.data(0, _PATH_ROLE) for it in self.selectedItems()
                if it.data(0, _PATH_ROLE)]

    def _selected_paths_top(self) -> List[str]:
        """选中集「顶层化」：去掉被另一选中项包含的子项，按 walk 序输出。

        排序键 = walk 序（= 树显示序 = 执行序）：多选拖拽 = 批量移动时
        插入顺序就是选中顺序。旧实现 sorted(set) 按名称排（Unicode 码点，
        如「乙」<「甲」），拖拽后执行序错乱 → 用户报告的 bug。
        """
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
        """按 walk 序（= 显示序 = 执行序）把 ``(name, value)`` 插到父节点下标
        ``index`` 处（None / 越界 → 尾部追加）；store 无插入 API → 重建定位。"""
        if index is None or index >= len(node):
            node[name] = value
        else:
            items = list(node.items())
            items.insert(max(0, index), (name, value))
            node.clear()
            node.update(items)

    def _act_add_group(self, context_group: str = "",
                       index: Optional[int] = None) -> None:
        """新建组：弹窗输入组名，确认后创建空组（可指定位置，语义同空列表）。"""
        name, ok = QInputDialog.getText(self, "添加组", "组名：")
        if not ok:
            return
        name = name.strip()
        if not name or "/" in name or name in (".", ".."):
            QMessageBox.warning(self, "添加组", "名称非法")
            return
        full = (context_group + "/" + name) if context_group else name
        try:
            self._store.get(full)      # 目标已存在（列表或组）→ 提示
        except FileNotFoundError:
            pass
        else:
            QMessageBox.warning(self, "添加组", "无法添加：已存在 %r" % full)
            return
        node = self._store._root
        if context_group:
            for seg in context_group.split("/"):
                node = node[seg]       # 右键组为真实组 → 节点必为 dict
        self._insert_node(node, name, {}, index)
        self._changed(full)

    def _act_new_empty_list(self, context_group: str = "",
                            index: Optional[int] = None) -> None:
        """新建空列表：先弹窗输入名称，确认后创建无步骤的 :class:`StepList`。

        位置语义与视图「添加步骤」一致：头部=0 / 尾部=None（追加）/
        此列表前=锚下标 / 此列表后=锚下标+1。位置 = walk 序（= 树显示序 =
        执行序，见 ``all_do_methods``）；store 无插入 API → 重建父字典定位插入。
        """
        name, ok = QInputDialog.getText(self, "新建空列表", "列表名称：",
                                        text="新列表")
        if not ok:
            return
        name = name.strip()
        if not name:
            QMessageBox.warning(self, "新建空列表", "名称不能为空")
            return
        full = self._dedup_name(context_group, name)
        node = self._store._root
        if context_group:
            for seg in context_group.split("/"):
                node = node[seg]               # 右键组为真实组 → 节点必为 dict
        name = full.rsplit("/", 1)[-1]
        self._insert_node(node, name, StepList.create_empty(), index)
        self._changed(full)

    def _sibling_index(self, path: str) -> int:
        """path 在父层 walk 序中的下标（「此列表前/后」锚点定位；= 树显示序）。"""
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
        """路径 → 先序三元组 ``(相对路径, 是否组, 格式串|None)``（顶层项相对路径 = 空串）。"""
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
                                self._store.get(child).to_format_strings()))
            return out
        out.append(("", False, self._store.get(path).to_format_strings()))
        return out

    def _act_cut(self) -> None:
        tops = self._selected_paths_top()
        if len(tops) != 1:
            return                       # 剪切 = 复制 + 删除 → 与复制同限单选
        self._act_copy()
        for p in tops:
            try:
                self._store.remove(p)
            except FileNotFoundError:
                continue
        self._changed()

    def _act_paste(self, context_group: str = "",
                   index: Optional[int] = None) -> None:
        """粘贴剪贴板到 ``context_group`` 层；``index`` 同新建列表语义
        （None/越界 → 尾部追加；否则插到该下标，树显示序 = walk 序 = 执行序）。"""
        if self._clipboard.items is None:
            return
        name, triples = self._clipboard.items
        target = self._dedup_name(context_group, name)   # 完整路径（已含组前缀）
        top_name = target.rsplit("/", 1)[-1]
        node = self._store._root
        if context_group:
            for seg in context_group.split("/"):
                node = node[seg]               # 目标组为真实组 → 节点必为 dict
        first_group = triples[0][1]
        if index is None or index >= len(node):
            # 尾部追加：先序逐个 add（顶层节点建好即后续子树可挂）
            if first_group:
                self._store.add_group(target)
            elif triples[0][2] is not None:
                self._store.add_list(
                    target, StepList.from_format_strings(
                        triples[0][2], self._manager))
        else:
            # 指定位置：顶层节点经 _insert_node 插到下标（组 → 空 dict 先占位）
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
        """同父下重名去重：name(1)、name(2)…（与变量树一致）；返回完整路径。"""
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
        self._changed(new_path)

    def _act_delete(self) -> None:
        tops = self._selected_paths_top()
        if not tops:
            return
        if QMessageBox.question(
                self, "删除", "确定删除 %d 项？删除的步骤列表不可恢复。"
                % len(tops),
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes) != QMessageBox.Yes:
            return
        before = [p for p, g in self._store.walk() if not g]   # 删除前列表序（显示/执行序）
        for p in tops:
            try:
                self._store.remove(p)
            except FileNotFoundError:
                continue
        # 删除后显示下一个列表（用户操作不中断：紧邻被删项的下一个，无则前一个）
        self._changed(self._pick_next(before, tops))

    # ---- 拖拽移动（排序 / 批量剪切粘贴） ----
    def dropEvent(self, event) -> None:  # noqa: N802 (Qt 命名)
        """InternalMove 拖拽落点：选中项（含多选）移动到目标位。

        位置语义：OnItem → 目标之后（= 该条目的下一条，亮线在条目尾部）、
        AboveItem/BelowItem → 目标同层前/后、空白（无目标）→ root 尾部。
        非内部拖拽一律忽略。

        移动由 :meth:`_move_paths` 自行完成（store 变更 + refresh 重建树），
        因此内部拖拽**也一律 ignore**：若 accept 为 MoveAction，Qt 的
        ``startDrag`` 收尾会调 ``clearOrRemove()``，其 InternalMove 分支
        把仍选中的拖拽行从树的内部 model 删除 → 树缺行而 store 完好
        （用户报告「拖拽哪个哪个就消失」）。ignore 后 exec 返回
        IgnoreAction，Qt 不再清理，显示与 store 保持一致。
        """
        if event.source() is not self:     # 只接受本树内部拖拽
            event.ignore()
            return
        target = self.itemAt(event.pos())
        target_path = target.data(0, _PATH_ROLE) if target is not None else ""
        paths = self._selected_paths_top()     # 拖拽集 = 当前选中集（多选 = 批量移动）
        try:
            self._move_paths(paths, target_path, self.dropIndicatorPosition())
        except Exception as e:                 # 兜底：意外异常不静默吞掉
            QMessageBox.warning(self, "移动", "移动失败：%s" % e)
        # 一律 ignore：移动已自行完成，不能让 Qt 收尾再删一次行（见 docstring）
        event.ignore()
        self._drop_rect = None             # 落定后清亮线
        self.viewport().update()

    def _move_paths(self, paths: List[str], target_path: str,
                    position: QAbstractItemView.DropIndicatorPosition) -> bool:
        """把 ``paths``（顶层化路径集）移到 ``target_path`` 旁/尾。

        实现 = 「剪切粘贴」：序列化 → 删除 → 按目标位重建（与 _act_paste 同构）。
        位置语义同树显示序（= walk 序 = 执行序）：AboveItem → 目标前、
        BelowItem → 目标后、OnItem → 目标之后（= 该条目的下一条，列表/组
        均适用）、target_path=""（拖到空白）→ root 尾部；多路径保持选中顺序
        连续插入；跨父重名同粘贴去重。返回是否执行（空集/目标在移动集内 →
        False）。
        """
        if not paths:
            return False
        if target_path and (target_path in paths
                            or any(target_path.startswith(p + "/") for p in paths)):
            return False                       # 拖到自身/自身子树 → 拒绝
        if not target_path:
            parent = ""                        # 空白 → root 尾部
        else:
            parent = target_path.rsplit("/", 1)[0] if "/" in target_path else ""
        snap = [(p.rsplit("/", 1)[-1], self._triples_of(p)) for p in paths]
        # 事务性预检：删除源之前先验证全部格式串可还原（模板缺失/未加载 →
        # from_format_strings 抛 ValueError）。旧实现先删后插：异常时源已删、
        # 插入中断 → 列表真丢，异常穿透 dropEvent 被 Qt 吞掉（用户：拖拽哪个
        # 哪个就消失）。预检失败 → 弹窗提示 + 拒绝，任何数据都不动。
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
        node = self._store._root
        if parent:
            for seg in parent.split("/"):
                node = node[seg]
        # 目标下标必须在删除后计算：paths 在目标之前时删除会前移目标
        if not target_path:
            index: Optional[int] = None
        else:
            index = self._sibling_index(target_path)
            if position != QAbstractItemView.AboveItem:
                index += 1                     # BelowItem / OnItem → 目标之后
        first_new: Optional[str] = None        # 第一个插入项的完整新路径
        for i, (name, triples) in enumerate(snap):
            top_name = self._dedup_name(parent, name).rsplit("/", 1)[-1]
            at = None if index is None else max(0, index + i)
            if triples[0][1]:                  # 组：空 dict 占位，子树随后追加
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
        # 传完整路径而非名称（旧实现 snap[0][0] 只是名称）：refresh 的
        # _find_item 按全路径匹配，组内移动时名称解析失败 → list_selected
        # 不触发 → 宿主画面不刷新（用户报告「多选拖拽后画面不显示」）
        self._changed(first_new)
        return True

    # ---- 拖拽亮线（自定义绘制；规则见 _update_drop_line） ----
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
        """按拖拽悬停位置计算亮线矩形（视口坐标）并重绘。

        ``position`` 为 None 时取 Qt 当前 ``dropIndicatorPosition()``
        （dropMoveEvent 路径）；冒烟可显式传（非拖拽态恒 NoPosition）。
        规则：AboveItem → 目标顶部；BelowItem/OnItem → 目标底部
        （OnItem = 插入到该条目的下一条）；空白（无目标）→ 最后一个
        可见条目底部（= 树末尾亮线）。
        """
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

    def dropMoveEvent(self, event: QDragMoveEvent) -> None:  # noqa: N802 (Qt 命名)
        """悬停移动 → 更新亮线（InternalMove 下能进入即内部拖拽）。"""
        self._update_drop_line(event.pos())
        event.accept()

    def dragLeaveEvent(self, event: QDragLeaveEvent) -> None:  # noqa: N802 (Qt 命名)
        """拖拽离开 → 清除亮线。"""
        if self._drop_rect is not None:
            self._drop_rect = None
            self.viewport().update()
        super().dragLeaveEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt 命名)
        super().paintEvent(event)
        if self._drop_rect is not None:
            p = QPainter(self.viewport())
            p.fillRect(self._drop_rect, QColor(72, 128, 220, 255))
            p.end()

    def _pick_next(self, before: List[str], deleted: List[str]) -> Optional[str]:
        """删除后要显示的列表：被删项之后第一个仍存在的；否则之前最后一个；
        否则第一个；无列表 → None。``deleted`` 可含组（其子树列表视为被删）。"""
        dead = set()
        for p in before:
            if any(p == d or p.startswith(d + "/") for d in deleted):
                dead.add(p)
        if not dead:
            # 删的是空组（before 只收集列表，空组不产生 dead）→ 显示删除后首个列表
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
        """刷新树 + 发 store_changed + 回调（上层保存）。"""
        self.refresh(current_path)
        self.store_changed.emit()
        self._on_changed()

if __name__ == "__main__":
    import sys

    from PyQt5.QtWidgets import QApplication, QInputDialog, QMessageBox

    from model.step import Step
    from model.kscp_package import KscpPackage
    from model.project_variable import ProjectVariable
    from model.step_list import StepList
    from model.step_list_store import StepListStore
    from model.step_manager import StepManager
    from model.variable_tree import VariableTree
    from widgets.step_list_view import StepClipboard

    app = QApplication.instance() or QApplication(sys.argv)

    pkg = KscpPackage.create_empty()
    tree = VariableTree.create_empty()
    tree.add("n1", ProjectVariable.create("number", 100, pkg))

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
    pkg.write_file("actions/示例.py", GOOD.encode("utf-8"))
    mgr = StepManager(pkg, tree)
    mgr.load()

    def make_step() -> Step:
        s = mgr.create_step("示例")
        s.io.change_value("input", 0, "5")
        s.io.change_value("output", 0, "n1")
        return s

    store = StepListStore.create_empty()
    sl = StepList.create_empty()
    sl.add(make_step())
    store.add_list("打开软件", sl)
    store.add_group("清理体力")
    slc = StepList.create_empty()
    slc.add(make_step())
    store.add_list("清理体力/检查体力", slc)
    store.add_group("空组")

    changes = []
    clipboard = StepClipboard()
    tw = StepListTreeWidget(store, mgr, clipboard,
                            lambda: changes.append(1))

    # 只显示键值；显示序 = walk 序 = 创建序（= 执行序，非按名排序）
    top = [tw.topLevelItem(i).text(0)
           for i in range(tw.topLevelItemCount())]
    assert top == ["打开软件", "清理体力", "空组"], top
    g = tw._find_item("清理体力")
    assert g is not None and g.childCount() == 1
    assert g.child(0).text(0) == "检查体力"
    assert tw._find_item("清理体力/检查体力") is not None
    assert tw._find_item("空组") is not None
    assert not tw._find_item("打开软件").icon(0).isNull()

    # list_selected 仅叶子触发
    seen = []
    tw.list_selected.connect(seen.append)
    tw.setCurrentItem(tw._find_item("打开软件"))
    assert seen == ["打开软件"]
    tw.setCurrentItem(g)                       # 组不触发
    assert seen == ["打开软件"]

    # 添加组（补丁 QInputDialog）
    orig_dlg = QInputDialog.getText
    QInputDialog.getText = staticmethod(lambda *a, **k: ("新组", True))
    try:
        tw._act_add_group("")
    finally:
        QInputDialog.getText = orig_dlg
    assert "新组" in [tw.topLevelItem(i).text(0)
                      for i in range(tw.topLevelItemCount())]
    assert changes == [1]                      # 变更回调被调

    # 复制列表 → 剪贴板三元组；粘贴到组内（无重名 → 不产生 name(1)）
    tw.setCurrentItem(tw._find_item("打开软件"))
    tw._act_copy()
    assert clipboard.items[0] == "打开软件"
    assert clipboard.items[1] == [("", False, sl.to_format_strings())]
    g = tw._find_item("清理体力")               # 树已重建 → 重新获取
    assert g is not None
    tw.setCurrentItem(g)
    tw._act_paste("清理体力")                   # 右键在组上 → 粘贴进组
    assert "清理体力/打开软件" in store.paths()
    # 组复制 → 整棵子树；粘贴到根 → 顶层重名去重 name(1)
    g = tw._find_item("清理体力")
    tw.setCurrentItem(g)
    tw._act_copy()
    assert clipboard.items[0] == "清理体力"
    assert ("", True, None) in clipboard.items[1]
    assert ("检查体力", False, slc.to_format_strings()) in clipboard.items[1]
    tw.setCurrentItem(None)
    tw._act_paste("")                          # 粘贴到根
    assert "清理体力(1)/检查体力" in store.paths()

    # 剪切 = 复制 + 删除（剪贴板保留）
    tw.setCurrentItem(tw._find_item("清理体力(1)"))
    tw._act_cut()
    assert "清理体力(1)" not in store.paths()
    assert clipboard.items is not None

    # 重命名（补丁 QInputDialog 带初值）
    tw.setCurrentItem(tw._find_item("清理体力/打开软件"))
    orig_dlg = QInputDialog.getText
    QInputDialog.getText = staticmethod(lambda *a, **k: ("改名", True))
    try:
        tw._act_rename()
    finally:
        QInputDialog.getText = orig_dlg
    assert "清理体力/改名" in store.paths()
    assert tw._current_path() == "清理体力/改名"    # 重命名后重新选中新路径

    # 删除（补丁确认框；组 = 整棵子树）
    orig_q = QMessageBox.question
    QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)
    try:
        tw.setCurrentItem(tw._find_item("清理体力/改名"))
        tw._act_delete()
    finally:
        QMessageBox.question = orig_q
    assert "清理体力/改名" not in store.paths()
    assert changes and len(changes) > 1

    # 多选复制/剪切 = no-op（剪贴板单条目契约 → 复制/剪切限单选，防数据丢失）
    a = tw._find_item("打开软件")
    b = tw._find_item("清理体力/检查体力")
    assert a is not None and b is not None
    tw.setCurrentItem(a)
    a.setSelected(True)
    b.setSelected(True)
    assert len(tw._selected_paths()) == 2            # 选中集确含两项
    old_items = clipboard.items
    tw._act_copy()                                   # 多选复制 → no-op
    assert clipboard.items is old_items              # 剪贴板未被覆盖
    paths_before = sorted(store.paths())
    tw._act_cut()                                    # 多选剪切 → no-op
    assert sorted(store.paths()) == paths_before     # 未删除任何项

    # ---- 新建空列表：先弹命名窗；4 位置（头部/尾部/此列表前/后；位置 = walk 序） ----
    store4 = StepListStore.create_empty()
    store4.add_group("组甲")
    store4.add_list("组甲/中列表", StepList.create_empty())
    store4.add_list("组甲/后列表", StepList.create_empty())
    store4.add_list("顶列表", StepList.create_empty())
    changes4 = []
    tw4 = StepListTreeWidget(store4, mgr, StepClipboard(),
                             lambda: changes4.append(1))
    # 命名弹窗（默认建议名「新列表」→ 确认后创建）
    orig_dlg4 = QInputDialog.getText
    QInputDialog.getText = staticmethod(lambda *a, **k: ("新列表", True))
    try:
        # 头部 → 组甲 walk 首位；空内容；新建后树中选中新项
        tw4._act_new_empty_list("组甲", 0)
        assert [p for p, _g in store4.walk()] == [
            "组甲", "组甲/新列表", "组甲/中列表", "组甲/后列表", "顶列表"]
        assert len(store4.get("组甲/新列表")) == 0
        assert tw4._current_path() == "组甲/新列表"
        # 尾部 → 组甲末位；同父重名去重 → 新列表(1)
        tw4._act_new_empty_list("组甲", None)
        assert [p for p, _g in store4.walk()] == [
            "组甲", "组甲/新列表", "组甲/中列表", "组甲/后列表",
            "组甲/新列表(1)", "顶列表"]
        assert len(store4.get("组甲/新列表(1)")) == 0
        # 此列表前/后：以「组甲/中列表」为锚（父层下标 = 1）→ 插到其前/后
        assert tw4._sibling_index("组甲/中列表") == 1
        tw4._act_new_empty_list("组甲", 1)                 # 前方 = 锚下标
        assert [p for p, _g in store4.walk()] == [
            "组甲", "组甲/新列表", "组甲/新列表(2)", "组甲/中列表",
            "组甲/后列表", "组甲/新列表(1)", "顶列表"]
        assert tw4._sibling_index("组甲/中列表") == 2
        tw4._act_new_empty_list("组甲", 3)                 # 后方 = 锚下标 + 1
        assert [p for p, _g in store4.walk()] == [
            "组甲", "组甲/新列表", "组甲/新列表(2)", "组甲/中列表",
            "组甲/新列表(3)", "组甲/后列表", "组甲/新列表(1)", "顶列表"]
        # 根层混合（既有列表 + 组）：头部 → 根 walk 首位；根下「新列表」未被占用 → 不去重
        tw4._act_new_empty_list("", 0)
        assert [p for p, _g in store4.walk()] == [
            "新列表", "组甲", "组甲/新列表", "组甲/新列表(2)", "组甲/中列表",
            "组甲/新列表(3)", "组甲/后列表", "组甲/新列表(1)", "顶列表"]
    finally:
        QInputDialog.getText = orig_dlg4
    assert changes4 and len(changes4) == 5             # 每次新建发变更回调

    # ---- 命名弹窗行为：自定义名创建 / 取消不创建 / 空名警告不创建 ----
    store5 = StepListStore.create_empty()
    changes5 = []
    tw5 = StepListTreeWidget(store5, mgr, StepClipboard(),
                             lambda: changes5.append(1))
    QInputDialog.getText = staticmethod(lambda *a, **k: ("我的列表", True))
    tw5._act_new_empty_list("", 0)
    assert "我的列表" in store5.paths() and changes5 == [1]
    QInputDialog.getText = staticmethod(lambda *a, **k: ("我的列表", True))
    tw5._act_new_empty_list("", None)                  # 重名输入 → 沿用同父去重
    assert "我的列表(1)" in store5.paths()
    QInputDialog.getText = staticmethod(lambda *a, **k: ("取消名", False))
    tw5._act_new_empty_list("", None)                  # 取消 → 不创建
    assert "取消名" not in store5.paths() and len(changes5) == 2
    orig_warn5 = QMessageBox.warning
    QMessageBox.warning = staticmethod(lambda *a, **k: QMessageBox.Ok)
    QInputDialog.getText = staticmethod(lambda *a, **k: ("   ", True))
    try:
        tw5._act_new_empty_list("", None)              # 空名确认 → 警告且不创建
    finally:
        QMessageBox.warning = orig_warn5
    assert len(store5.paths()) == 2 and len(changes5) == 2

    # ---- 用户 bug 复现：头部创建两次都应在首位、尾部创建在末位 ----
    # 修复前树显示按名排序 → 第二次头部创建显示在第二位、尾部创建显示到首位
    store_b = StepListStore.create_empty()
    store_b.add_list("旧列表", StepList.create_empty())
    tw_b = StepListTreeWidget(store_b, mgr, StepClipboard(), lambda: None)
    QInputDialog.getText = staticmethod(lambda *a, **k: ("新列表", True))
    tw_b._act_new_empty_list("", 0)              # 第一次头部 → 首位
    tw_b._act_new_empty_list("", 0)              # 第二次头部 → 仍首位（去重为 新列表(1)）
    assert [p for p, _g in store_b.walk()] == ["新列表(1)", "新列表", "旧列表"]
    tw_b._act_new_empty_list("", None)           # 尾部 → 末位
    assert [p for p, _g in store_b.walk()] == \
        ["新列表(1)", "新列表", "旧列表", "新列表(2)"]
    # 树显示序 = walk 序（用户所见即执行序）
    assert [tw_b.topLevelItem(i).text(0)
            for i in range(tw_b.topLevelItemCount())] == \
        ["新列表(1)", "新列表", "旧列表", "新列表(2)"]

    # ---- 删除后显示下一个列表（用户操作不中断） ----
    store_d = StepListStore.create_empty()
    for nm in ("甲", "乙", "丙"):
        store_d.add_list(nm, StepList.create_empty())
    tw_d = StepListTreeWidget(store_d, mgr, StepClipboard(), lambda: None)
    orig_q = QMessageBox.question
    QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)
    try:
        tw_d.setCurrentItem(tw_d._find_item("乙"))
        tw_d._act_delete()                       # 删中间 → 下一个「丙」
        assert tw_d._current_path() == "丙"
        tw_d.setCurrentItem(tw_d._find_item("丙"))
        tw_d._act_delete()                       # 删末尾 → 前一个「甲」
        assert tw_d._current_path() == "甲"
        tw_d.setCurrentItem(tw_d._find_item("甲"))
        tw_d._act_delete()                       # 删唯一 → 无列表（宿主回占位页）
        assert tw_d._current_path() == ""
    finally:
        QMessageBox.question = orig_q

    # ---- 右键菜单结构：空白 = 头部/尾部；列表 = 额外 此列表前/后 ----
    # python -m 冒烟注意：运行中的 __main__ 是 runpy 临时模块，import 自身
    # 拿不到它（探针证实 globals 不同一），必须用 globals() 替换本模块 QMenu。
    import PyQt5.QtWidgets as _W
    from PyQt5.QtCore import QPoint, QPointF, QMimeData
    from PyQt5.QtGui import QDropEvent

    class _MenuRecorder(_W.QMenu):
        """记录菜单项文本并模拟用户点击（exec_ 不真弹窗；子菜单递归）。"""
        last_texts = []
        chosen = None

        @staticmethod
        def _collect(menu):
            """递归收集菜单项文本；子菜单以 名字 + ">" 前缀标记。"""
            out = []
            for a in menu.actions():
                if a.isSeparator():
                    continue
                if a.menu() is not None:
                    out.append(a.text())
                    out.append(">")
                    out.extend(_MenuRecorder._collect(a.menu()))
                else:
                    out.append(a.text())
            return out

        @staticmethod
        def _find(menu, text):
            """递归查找菜单项（含子菜单内）。"""
            for a in menu.actions():
                if a.text() == text:
                    return a
                if a.menu() is not None:
                    r = _MenuRecorder._find(a.menu(), text)
                    if r is not None:
                        return r
            return None

        def exec_(self, *args):
            _MenuRecorder.last_texts = _MenuRecorder._collect(self)
            if _MenuRecorder.chosen is not None:
                return _MenuRecorder._find(self, _MenuRecorder.chosen)
            return None

    _orig_qmenu = QMenu
    globals()["QMenu"] = _MenuRecorder         # 替换运行中模块的 QMenu（exec_ 为 C++ 方法不可直接 patch）
    _orig_get = QInputDialog.getText
    _g_names = iter(["新组1", "新组2", "新组3", "新组4", "新组5"])
    QInputDialog.getText = staticmethod(lambda *a, **k: (next(_g_names), True))
    try:
        # 空白处右击（空树 → itemAt 恒 None）
        tw_empty = StepListTreeWidget(StepListStore.create_empty(),
                                      mgr, StepClipboard(), lambda: None)
        tw_empty.show()
        app.processEvents()
        _MenuRecorder.chosen = None
        tw_empty._on_context_menu(QPoint(5, 5))
        assert _MenuRecorder.last_texts == [
            "添加的子项", ">", "头部添加步骤…", "尾部添加步骤…",
            "头部添加组…", "尾部添加组…",
            "粘贴的子项", ">", "粘贴到列表头", "粘贴到列表尾",
            "复制", "剪切", "重命名\tF2", "删除\tDel"], \
            _MenuRecorder.last_texts
        tw_empty.close()
        # 列表右击 → 额外「在此列表前/后添加…」；点击「在此列表前添加…」→ 插到锚前
        store_m = StepListStore.create_empty()
        for nm in ("甲", "乙"):
            store_m.add_list(nm, StepList.create_empty())
        tw_m = StepListTreeWidget(store_m, mgr, StepClipboard(), lambda: None)
        tw_m.show()
        app.processEvents()
        it = tw_m._find_item("乙")
        assert it is not None
        pos = tw_m.visualItemRect(it).center()
        _MenuRecorder.chosen = None
        tw_m._on_context_menu(pos)
        assert _MenuRecorder.last_texts == [
            "添加的子项", ">", "头部添加步骤…", "尾部添加步骤…",
            "在此列表前添加…", "在此列表后添加…",
            "头部添加组…", "尾部添加组…",
            "在此前添加组…", "在此后添加组…",
            "粘贴的子项", ">", "粘贴到列表头", "粘贴到列表尾",
            "粘贴到此列表前", "粘贴到此列表后",
            "复制", "剪切", "重命名\tF2", "删除\tDel"], \
            _MenuRecorder.last_texts
        _orig_get_a = QInputDialog.getText
        _orig_warn = QMessageBox.warning
        _m_names = iter(["新列表", "前组"])      # 第 2 次组名不得与列表重名
        QInputDialog.getText = staticmethod(lambda *a, **k: (next(_m_names), True))
        QMessageBox.warning = staticmethod(lambda *a, **k: QMessageBox.Ok)
        try:
            _MenuRecorder.chosen = "在此列表前添加…"
            tw_m._on_context_menu(pos)         # 点击 → 在「乙」前新建
            assert [p for p, _g in store_m.walk()] == ["甲", "新列表", "乙"]
            # 右击列表 → 组前/后选项：点击「在此前添加组…」→ 组插到「乙」前。
            # 注意：插入后树已重排（QTreeWidget 内部 model 变更即重算布局），
            # 旧 item 的 visualItemRect 坐标失效——必须重新定位「乙」再取新 pos，
            # 否则 itemAt 会命中「新列表」行、组被插到错误位置。
            it = tw_m._find_item("乙")
            assert it is not None
            pos = tw_m.visualItemRect(it).center()
            _MenuRecorder.chosen = "在此前添加组…"
            tw_m._on_context_menu(pos)
            assert [p for p, _g in store_m.walk()] == ["甲", "新列表", "前组", "乙"]
            # 粘贴菜单点击:「粘贴到此列表前」→ 插到锚(乙)前（与添加同位置语义）
            tw_m.setCurrentItem(tw_m._find_item("甲"))
            tw_m._act_copy()                   # 复制甲
            it = tw_m._find_item("乙")
            assert it is not None
            pos = tw_m.visualItemRect(it).center()
            _MenuRecorder.chosen = "粘贴到此列表前"
            tw_m._on_context_menu(pos)
            assert [p for p, _g in store_m.walk()] == \
                ["甲", "新列表", "前组", "甲(1)", "乙"], \
                [p for p, _g in store_m.walk()]
        finally:
            QInputDialog.getText = _orig_get_a
            QMessageBox.warning = _orig_warn
        tw_m.close()

        # 右击组 → 额外「在此组前/后添加…」；点击「在此组前添加…」→ 插到锚前
        store_g = StepListStore.create_empty()
        store_g.add_group("组甲")
        store_g.add_list("组甲/列表1", StepList.create_empty())
        store_g.add_group("组甲/组乙")
        tw_g = StepListTreeWidget(store_g, mgr, StepClipboard(), lambda: None)
        tw_g.show()
        tw_g.expandAll()                       # 未展开时子项 visualItemRect 为 0 尺寸
        app.processEvents()
        it_g = tw_g._find_item("组甲/组乙")
        assert it_g is not None
        pos_g = tw_g.visualItemRect(it_g).center()
        _MenuRecorder.chosen = None
        tw_g._on_context_menu(pos_g)
        assert _MenuRecorder.last_texts == [
            "添加的子项", ">", "头部添加步骤…", "尾部添加步骤…",
            "头部添加组…", "尾部添加组…",
            "在此组前添加…", "在此组后添加…",
            "粘贴的子项", ">", "粘贴到列表头", "粘贴到列表尾",
            "复制", "剪切", "重命名\tF2", "删除\tDel"], \
            _MenuRecorder.last_texts
        _MenuRecorder.chosen = "在此组前添加…"
        tw_g._on_context_menu(pos_g)           # 点击 → 在「组乙」前新建组
        assert [p for p, _g in store_g.walk()] == \
            ["组甲", "组甲/列表1", "组甲/新组1", "组甲/组乙"]
        tw_g.close()

        # 组创建位置：头部两次 → 均首位（后插在前）；尾部 → 末位；组内头部 → 组内首
        store_g2 = StepListStore.create_empty()
        tw_g2 = StepListTreeWidget(store_g2, mgr, StepClipboard(), lambda: None)
        tw_g2._act_add_group("", 0)            # 头部（“新组2”）
        tw_g2._act_add_group("", 0)            # 再次头部（“新组3”）→ 插到最前
        assert [p for p, _g in store_g2.walk()] == ["新组3", "新组2"]
        tw_g2._act_add_group("", None)         # 尾部（“新组4”）→ 末位
        assert [p for p, _g in store_g2.walk()] == ["新组3", "新组2", "新组4"]
        store_g3 = StepListStore.create_empty()
        store_g3.add_group("甲组")
        store_g3.add_list("甲组/列表1", StepList.create_empty())
        tw_g3 = StepListTreeWidget(store_g3, mgr, StepClipboard(), lambda: None)
        tw_g3._act_add_group("甲组", 0)        # 组内头部（“新组5”）
        assert [p for p, _g in store_g3.walk()] == \
            ["甲组", "甲组/新组5", "甲组/列表1"]
        # 重名组 → 警告且不创建（getText 固定返回同名 “新组5”）
        _orig_q = QMessageBox.warning
        _orig_get2 = QInputDialog.getText
        QMessageBox.warning = staticmethod(lambda *a, **k: QMessageBox.Ok)
        QInputDialog.getText = staticmethod(lambda *a, **k: ("新组5", True))
        try:
            tw_g3._act_add_group("甲组", None)
            assert [p for p, _g in store_g3.walk()] == \
                ["甲组", "甲组/新组5", "甲组/列表1"]   # 未新增
        finally:
            QMessageBox.warning = _orig_q
            QInputDialog.getText = _orig_get2
    finally:
        globals()["QMenu"] = _orig_qmenu
        QInputDialog.getText = _orig_get

    # ---- 粘贴四向（API 直调）：列表头/尾 + 锚定前/后，位置 = walk 序 ----
    store_p = StepListStore.create_empty()
    for nm in ("甲", "乙"):
        store_p.add_list(nm, StepList.create_empty())
    clip_p = StepClipboard()
    tw_p = StepListTreeWidget(store_p, mgr, clip_p, lambda: None)
    # 粘贴到列表头 → 根层首位（去重 → 乙(1)）
    tw_p.setCurrentItem(tw_p._find_item("乙"))
    tw_p._act_copy()
    tw_p._act_paste("", 0)
    assert [p for p, _g in store_p.walk()] == ["乙(1)", "甲", "乙"], \
        [p for p, _g in store_p.walk()]
    # 粘贴到此列表后 → 锚(乙)下标 + 1 = 3
    tw_p.setCurrentItem(tw_p._find_item("甲"))
    tw_p._act_copy()
    tw_p._act_paste("", 3)
    assert [p for p, _g in store_p.walk()] == \
        ["乙(1)", "甲", "乙", "甲(1)"], [p for p, _g in store_p.walk()]
    # 粘贴到列表尾 → 末位（去重 → 乙(1)(1)）
    tw_p.setCurrentItem(tw_p._find_item("乙(1)"))
    tw_p._act_copy()
    tw_p._act_paste("", None)
    assert [p for p, _g in store_p.walk()] == \
        ["乙(1)", "甲", "乙", "甲(1)", "乙(1)(1)"], \
        [p for p, _g in store_p.walk()]
    # 整组粘贴到指定位置：组节点插下标，子树按序进组内
    store_pg = StepListStore.create_empty()
    store_pg.add_group("组乙")
    store_pg.add_list("组乙/L1", StepList.create_empty())
    store_pg.add_list("组乙/L2", StepList.create_empty())
    store_pg.add_list("顶", StepList.create_empty())
    clip_pg = StepClipboard()
    tw_pg = StepListTreeWidget(store_pg, mgr, clip_pg, lambda: None)
    tw_pg.setCurrentItem(tw_pg._find_item("组乙"))
    tw_pg._act_copy()
    tw_pg._act_paste("", 0)                    # 组粘贴到根层头部（walk 先序：组后紧跟子树）
    assert [p for p, _g in store_pg.walk()] == \
        ["组乙(1)", "组乙(1)/L1", "组乙(1)/L2", "组乙", "组乙/L1", "组乙/L2", "顶"], \
        [p for p, _g in store_pg.walk()]

    # ---- 勾选框：全激活=勾选、全停用=未勾、混合=半选；点击切换全部步骤 ----
    store_c = StepListStore.create_empty()
    sl_on = StepList.create_empty()
    sl_on.add(make_step())                     # enabled=True
    sl_off = StepList.create_empty()
    _s = make_step()
    _s.enabled = False
    sl_off.add(_s)
    sl_mix = StepList.create_empty()
    sl_mix.add(make_step())
    _s2 = make_step()
    _s2.enabled = False
    sl_mix.add(_s2)
    store_c.add_list("全开", sl_on)
    store_c.add_list("全关", sl_off)
    store_c.add_list("混合", sl_mix)
    store_c.add_group("组X")
    store_c.add_list("组X/L", StepList.create_empty())
    changes_c = []
    tw_c = StepListTreeWidget(store_c, mgr, StepClipboard(),
                              lambda: changes_c.append(1))
    assert tw_c._find_item("全开").checkState(0) == Qt.Checked
    assert tw_c._find_item("全关").checkState(0) == Qt.Unchecked
    assert tw_c._find_item("混合").checkState(0) == Qt.PartiallyChecked
    assert not (tw_c._find_item("组X").flags() & Qt.ItemIsUserCheckable)  # 组无框
    # 用户点击（勾选框取消）→ 全部停用 + 保存；树重建后反映为未勾
    tw_c._find_item("全开").setCheckState(0, Qt.Unchecked)
    assert all(not s.enabled for s in sl_on.steps)
    assert changes_c == [1]
    assert tw_c._find_item("全开").checkState(0) == Qt.Unchecked
    # 再点 → 全部激活（回调 append(1)，第 2 次保存 = [1, 1]；
    # 三态 item 从 Unchecked→Checked 发两次 itemChanged，第一次状态未变
    # 被 _on_item_changed 的 early-return 拦截，恰好保存一次）
    tw_c._find_item("全开").setCheckState(0, Qt.Checked)
    assert all(s.enabled for s in sl_on.steps)
    assert changes_c == [1, 1]
    # 半选点击（Qt 三态规则：半选 → 未勾）→ 全部停用
    tw_c._find_item("混合").setCheckState(0, Qt.Unchecked)
    assert all(not s.enabled for s in sl_mix.steps)

    # ---- 拖拽移动（排序/跨组/多选；OnItem=目标之后=下一条、Above/Below=同层前后） ----
    store_dd = StepListStore.create_empty()
    for nm in ("甲", "乙", "丙"):
        store_dd.add_list(nm, StepList.create_empty())
    tw_dd = StepListTreeWidget(store_dd, mgr, StepClipboard(), lambda: None)
    # AboveItem：丙 → 乙前（同层排序）
    assert tw_dd._move_paths(["丙"], "乙", QAbstractItemView.AboveItem)
    assert [p for p, _g in store_dd.walk()] == ["甲", "丙", "乙"]
    # BelowItem：甲 → 丙后
    assert tw_dd._move_paths(["甲"], "丙", QAbstractItemView.BelowItem)
    assert [p for p, _g in store_dd.walk()] == ["丙", "甲", "乙"]
    # OnItem（拖到某条目上）→ 插到该条目之后（用户：亮线在条目尾部，
    # 意味着插入到该条目的下一条）；组也一样 → 甲插到组后
    store_dd.add_group("组")
    tw_dd.refresh()
    assert tw_dd._move_paths(["甲"], "组", QAbstractItemView.OnItem)
    assert [p for p, _g in store_dd.walk()] == ["丙", "乙", "组", "甲"]
    # 多选拖拽 = 批量移动（保持选中顺序；删丙乙后组前移，插位 = 组后）
    assert tw_dd._move_paths(["丙", "乙"], "组", QAbstractItemView.OnItem)
    assert [p for p, _g in store_dd.walk()] == ["组", "丙", "乙", "甲"]
    # OnItem 对列表也合法（拖到列表上 = 插到该列表之后）
    assert tw_dd._move_paths(["甲"], "丙", QAbstractItemView.OnItem)
    assert [p for p, _g in store_dd.walk()] == ["组", "丙", "甲", "乙"]
    # 拖到空白（target=""）→ root 尾部
    assert tw_dd._move_paths(["组"], "", QAbstractItemView.BelowItem)
    assert [p for p, _g in store_dd.walk()] == ["丙", "甲", "乙", "组"]
    # 防御：目标在移动集内 → 拒绝
    assert not tw_dd._move_paths(["组"], "组/甲", QAbstractItemView.OnItem)
    assert not tw_dd._move_paths(["组/甲"], "组/甲", QAbstractItemView.AboveItem)
    # 组（含子树）跨父移动：OnItem = 目标之后（组1 插到组2 后，非组内）
    store_dd2 = StepListStore.create_empty()
    store_dd2.add_group("组1")
    store_dd2.add_list("组1/L", StepList.create_empty())
    store_dd2.add_group("组2")
    store_dd2.add_list("组2/M", StepList.create_empty())
    tw_dd2 = StepListTreeWidget(store_dd2, mgr, StepClipboard(), lambda: None)
    assert tw_dd2._move_paths(["组1"], "组2", QAbstractItemView.OnItem)
    assert [p for p, _g in store_dd2.walk()] == \
        ["组2", "组2/M", "组1", "组1/L"], \
        [p for p, _g in store_dd2.walk()]
    # 跨父重名 → 去重 name(1)
    store_dd3 = StepListStore.create_empty()
    store_dd3.add_list("同名", StepList.create_empty())
    store_dd3.add_group("组")
    store_dd3.add_list("组/同名", StepList.create_empty())
    tw_dd3 = StepListTreeWidget(store_dd3, mgr, StepClipboard(), lambda: None)
    assert tw_dd3._move_paths(["组/同名"], "同名", QAbstractItemView.AboveItem)
    assert [p for p, _g in store_dd3.walk()] == ["同名(1)", "同名", "组"]
    # ---- 多选拖拽：选中集 = 树显示序（walk 序），非名称排序 ----
    # 名称序 ≠ walk 序：Unicode 码点乙(4E59) < 甲(7532)，创建序「甲→乙」
    # 时两者相反——旧实现 sorted(set) 按名称排 → 多选拖拽执行序错乱
    store_ms = StepListStore.create_empty()
    store_ms.add_list("甲", StepList.create_empty())   # walk 序在前
    store_ms.add_list("乙", StepList.create_empty())
    tw_ms = StepListTreeWidget(store_ms, mgr, StepClipboard(), lambda: None)
    tw_ms._find_item("甲").setSelected(True)
    tw_ms._find_item("乙").setSelected(True)
    assert tw_ms._selected_paths_top() == ["甲", "乙"], \
        tw_ms._selected_paths_top()          # 显示序 = 执行序，非名称排序
    # 组内多选（名称序 ≠ walk 序）
    store_ms2 = StepListStore.create_empty()
    store_ms2.add_group("组X")
    store_ms2.add_list("组X/子甲", StepList.create_empty())
    store_ms2.add_list("组X/子乙", StepList.create_empty())
    store_ms2.add_list("尾", StepList.create_empty())
    tw_ms2 = StepListTreeWidget(store_ms2, mgr, StepClipboard(), lambda: None)
    tw_ms2._find_item("组X/子甲").setSelected(True)
    tw_ms2._find_item("组X/子乙").setSelected(True)
    assert tw_ms2._selected_paths_top() == ["组X/子甲", "组X/子乙"], \
        tw_ms2._selected_paths_top()
    # 多选拖拽后：list_selected 收到第一个插入项的完整路径（宿主画面刷新）
    got_ms = []
    tw_ms2.list_selected.connect(lambda p: got_ms.append(p))
    # 组内移动：第一个插入项仍在组内 → 必须发组内完整路径
    # （旧实现传名称「子甲」，_find_item 按全路径匹配失败 → list_selected
    #   不触发 → 宿主画面不显示，即用户报告的 bug）
    assert tw_ms2._move_paths(
        ["组X/子甲"], "组X/子乙", QAbstractItemView.BelowItem)
    assert [p for p, _g in store_ms2.walk()] == \
        ["组X", "组X/子乙", "组X/子甲", "尾"], \
        [p for p, _g in store_ms2.walk()]
    assert got_ms == ["组X/子甲"], got_ms
    # 拖到 root（尾前）：插入项在 root → 发 root 路径（顺序 = 选中 walk 序）
    assert tw_ms2._move_paths(
        ["组X/子乙", "组X/子甲"], "尾", QAbstractItemView.AboveItem)
    assert [p for p, _g in store_ms2.walk()] == \
        ["组X", "子乙", "子甲", "尾"], \
        [p for p, _g in store_ms2.walk()]
    assert got_ms == ["组X/子甲", "子乙"], got_ms

    # ---- 拖拽亮线（自定义：条目尾部/中间/空白处末尾；drop 完成与离开即清除） ----
    # 拖到条目上 → 该条目尾部亮线（OnItem = 插入到下一条，亮线在底部）
    it_dd = tw_dd._find_item("乙")
    assert it_dd is not None
    r = tw_dd.visualItemRect(it_dd)
    tw_dd._drop_rect = None
    tw_dd._update_drop_line(QPoint(r.center().x(), r.center().y()))
    assert tw_dd._drop_rect is not None
    assert tw_dd._drop_rect.top() == r.bottom() + 1 - tw_dd._LINE_H, \
        (tw_dd._drop_rect, r)
    # 拖到两条目中间（AboveItem=目标上半）→ 目标顶部亮线
    tw_dd._update_drop_line(QPoint(r.center().x(), r.center().y()),
                            QAbstractItemView.AboveItem)
    assert tw_dd._drop_rect.top() == r.top(), (tw_dd._drop_rect, r)
    # 拖到空白 → 末尾亮线（最后一个可见条目尾部）
    last = tw_dd._last_visible_item()
    assert last is not None
    rl = tw_dd.visualItemRect(last)
    tw_dd._update_drop_line(QPoint(5, 99999))      # 越界 = 树空白
    assert tw_dd._drop_rect is not None
    assert tw_dd._drop_rect.top() == rl.bottom() + 1 - tw_dd._LINE_H, \
        (tw_dd._drop_rect, rl)
    # 拖拽离开 → 亮线清除
    tw_dd.dragLeaveEvent(QDragLeaveEvent())
    assert tw_dd._drop_rect is None
    # dropMoveEvent 也更新亮线（模拟：QDragMoveEvent 构造 + 空树时无崩溃）
    md_dm = QMimeData()
    dm = QDragMoveEvent(QPoint(5, 5), Qt.CopyAction, md_dm,
                        Qt.LeftButton, Qt.NoModifier)
    tw_dd3.dropMoveEvent(dm)                     # 树非空：亮线在 item 尾部
    assert tw_dd3._drop_rect is not None
    tw_dd3.dragLeaveEvent(QDragLeaveEvent())
    assert tw_dd3._drop_rect is None
    # dropEvent：外部来源拖入 → 忽略（不移动、不接受）
    md = QMimeData()
    ext = QDropEvent(QPointF(0, 0), Qt.CopyAction, md, Qt.LeftButton,
                     Qt.NoModifier)
    tw_dd3.dropEvent(ext)
    assert not ext.isAccepted()
    assert [p for p, _g in store_dd3.walk()] == ["同名(1)", "同名", "组"]

    # ---- 回归：内部拖拽 drop 后必须 ignore（Qt clearOrRemove 删行 bug） ----
    # 旧实现内部拖拽 accept 为 MoveAction：Qt startDrag 收尾调 clearOrRemove，
    # 把仍选中的拖拽行从树的内部 model 删除 → 树缺行、store 完好
    # （用户报告：拖 a3 到 a2 树变 [a1,a2]，再拖 a2 到 a1 树变 [a1,a3]；
    #  数据其实都在，只是显示行被 Qt 删了）。修复：一律 ignore → exec 返回
    #  IgnoreAction → Qt 不再清理 → 树显示与 store 一致。
    # 真实 QDropEvent.source() 由 QDragManager 提供（非拖拽态恒 None），
    # 无法直接构造 source==self 的 QDropEvent → 用最小假事件走 dropEvent。
    class _FakeDrop:
        """最小 QDropEvent 替身：只实现 dropEvent 用到的接口。"""
        def __init__(self, pos, source):
            self._pos, self._source, self._accepted = pos, source, False
        def pos(self):
            return self._pos
        def source(self):
            return self._source
        def accept(self):
            self._accepted = True
        def ignore(self):
            self._accepted = False
        def setDropAction(self, _action):
            pass

    store_reg = StepListStore.create_empty()
    for nm in ("甲", "乙", "丙"):
        store_reg.add_list(nm, StepList.create_empty())
    tw_reg = StepListTreeWidget(store_reg, mgr, StepClipboard(), lambda: None)
    tw_reg._find_item("丙").setSelected(True)          # 真实拖拽：press 即选中
    ev_reg = _FakeDrop(tw_reg.visualItemRect(tw_reg._find_item("乙")).center(),
                       tw_reg)
    tw_reg.dropEvent(ev_reg)
    assert not ev_reg._accepted, "内部拖拽必须 ignore（否则 Qt 收尾删行）"
    # 丙 插到 乙 之后 = 原位 → store 序不变
    assert [p for p, _g in store_reg.walk()] == ["甲", "乙", "丙"], \
        [p for p, _g in store_reg.walk()]
    # 树显示与 store 一致（旧实现此处树缺「丙」）
    shown_reg = [tw_reg.topLevelItem(i).text(0)
                 for i in range(tw_reg.topLevelItemCount())]
    assert shown_reg == ["甲", "乙", "丙"], shown_reg
    # 选中行仍在（旧实现选中行被 Qt 删掉）
    assert [it.data(0, _PATH_ROLE) for it in tw_reg.selectedItems()] == ["丙"]

    # ---- 事务性移动：格式串不可还原（模板缺失/未加载）→ 拒绝且数据不动 ----
    # 旧实现先删源后解码插入：from_format_strings 抛异常时源已删、插入中断
    # → 列表真丢（探针复现），异常穿透 dropEvent 被 Qt 吞 → 「拖拽哪个丢哪个」
    pkg_t = KscpPackage.create_empty()
    tree_t = VariableTree.create_empty()
    mgr_t = StepManager(pkg_t, tree_t)            # 未 load → 注册表空
    store_t = StepListStore.create_empty()
    store_t.add_list("x1", StepList.create_empty())
    store_t.add_list("x2", StepList.create_empty())
    store_t.add_list("x3", StepList.create_empty())
    # x2 放进一个「格式串不可还原」的列表：步骤来自已 load 的 mgr，
    # 目标 mgr_t 未 load → from_format_strings 无匹配模板
    sl_x = StepList.create_empty()
    sl_x.add(mgr.create_step("示例"))              # 来自上文已 load 的 mgr
    store_t.get("x2").add(sl_x[0])
    tw_t = StepListTreeWidget(store_t, mgr_t, StepClipboard(), lambda: None)
    _warn = QMessageBox.warning
    QMessageBox.warning = staticmethod(lambda *a, **k: QMessageBox.Ok)
    try:
        assert not tw_t._move_paths(
            ["x2"], "x1", QAbstractItemView.OnItem)   # 不可还原 → 拒绝
    finally:
        QMessageBox.warning = _warn
    assert [p for p, _g in store_t.walk()] == ["x1", "x2", "x3"], \
        [p for p, _g in store_t.walk()]               # 源未删 → 数据不动

    # ---- 删除空组（无列表）→ 不崩溃，显示删除后首个列表 ----
    store_pn = StepListStore.create_empty()
    store_pn.add_group("空组")
    store_pn.add_list("甲", StepList.create_empty())
    tw_pn = StepListTreeWidget(store_pn, mgr, StepClipboard(), lambda: None)
    before = [p for p, g in store_pn.walk() if not g]
    assert tw_pn._pick_next(before, ["空组"]) == "甲"   # 旧实现 max() 空 → ValueError

    # ---- 错误标记：列表 io 非法 → 列表 + 祖先组条目红色加粗；修复后恢复默认 ----
    store_e = StepListStore.create_empty()
    store_e.add_group("组A")
    store_e.add_group("组A/好组")                # 兄弟组（无坏列表）→ 不标
    bad = StepList.create_empty()
    bad.add(mgr.create_step("示例"))             # 空 io 槽 → 非法
    store_e.add_list("组A/坏列表", bad)
    good_l = StepList.create_empty()
    good_l.add(make_step())                      # 合法
    store_e.add_list("组A/好组/列表", good_l)
    store_e.add_list("好列表", good_l)
    tw_e = StepListTreeWidget(store_e, mgr, StepClipboard(), lambda: None)
    from PyQt5.QtGui import QColor as _QColor
    _RED = _QColor(200, 50, 40)
    it_bad = tw_e._find_item("组A/坏列表")
    it_grp = tw_e._find_item("组A")
    it_sub = tw_e._find_item("组A/好组")
    it_good = tw_e._find_item("好列表")
    assert it_bad is not None and it_grp is not None
    assert it_sub is not None and it_good is not None
    assert it_bad.font(0).bold() and it_bad.foreground(0).color() == _RED
    assert it_grp.font(0).bold() and it_grp.foreground(0).color() == _RED   # 祖先组
    # 兄弟组与合规列表不误伤（「组A/好组」是坏列表的兄弟，非祖先链）
    assert not it_sub.font(0).bold()
    assert it_sub.foreground(0).color() == tw_e.palette().text()
    assert not it_good.font(0).bold()                                       # 合规列表不标
    assert it_good.foreground(0).color() == tw_e.palette().text()
    # 修复坏步骤 → 重标恢复默认（列表 + 各级祖先组）
    s_bad = store_e.get("组A/坏列表").steps[0]
    s_bad.io.change_value("input", 0, "5")
    s_bad.io.change_value("output", 0, "n1")
    tw_e.refresh_error_marks()
    assert not it_bad.font(0).bold()
    assert not it_grp.font(0).bold()
    assert not it_sub.font(0).bold()
    assert it_bad.foreground(0).color() == tw_e.palette().text()

    print("StepListTreeWidget smoke OK")
