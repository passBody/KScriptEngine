# Task 5 review package — StepListTreeWidget

- 任务文件清单(唯一变更文件):
  - 新建:`widgets/step_list_tree_widget.py`(535 行)
- 非 git 适配:无 BASE/HEAD 可 diff;下方为任务文件**全文**(评审对照简报 task-5-brief.md 代码块)。
- **已知偏离简报文本两处(实施者报告,需评审独立判定)**:① 实现块 QtCore import 行去掉 `QKeySequence`(PyQt5 中 QKeySequence 位于 QtGui,简报同一代码块下一行已从 QtGui 导入;本机实测 QtCore 导入必 ImportError——RED 第 2 次运行实证;项目内三个既有 widget 文件均从 QtGui 导入);② 冒烟块顶层顺序断言期望 `["清理体力", "打开软件", "空组"]` → `["清理体力", "空组", "打开软件"]`(断言与实现「组在上、列表在下、各自按名排序」矛盾——组内排序 `[清理体力, 空组]`(清 U+6E05 < 空 U+7A7A)恒在列表前,任何排序规则都无法把列表插到两组合之间;实现保持简报逐字,仅改冒烟期望)。

## 文件全文:widgets/step_list_tree_widget.py

```python
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

from typing import Callable, List, Optional, Tuple

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QColor, QFont, QIcon, QKeySequence, QPainter, QPixmap
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
        self.setUniformRowHeights(True)
        self.setFont(QFont("SimSun", 11))
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._on_context_menu)
        self.currentItemChanged.connect(self._on_current_changed)

        QShortcut(QKeySequence.Delete, self, self._act_delete)
        QShortcut("F2", self, self._act_rename)

        self.refresh()

    def refresh(self, current_path: Optional[str] = None) -> None:
        """从 store 重建树（组/列表键值）；保留展开，可指定当前项。"""
        expanded = set(self._expanded_paths())
        cur = current_path if current_path is not None else self._current_path()
        self.blockSignals(True)
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
        self.blockSignals(False)
        self._on_current_changed(self.currentItem(), None)

    # ---- 树构建 ----
    def _fill(self, parent_item: QTreeWidgetItem, prefix: str) -> None:
        style = self.style()
        dirs, leaves = self._children_of(prefix)
        for name, is_group in dirs + leaves:
            path = name if not prefix else prefix + "/" + name
            item = QTreeWidgetItem(parent_item)
            item.setText(0, name)
            item.setData(0, _PATH_ROLE, path)
            if is_group:
                if style is not None:
                    item.setIcon(0, style.standardIcon(QStyle.SP_DirIcon))
                self._fill(item, path)
            else:
                item.setIcon(0, _make_list_icon())

    def _children_of(self, prefix: str) -> Tuple[List[Tuple[str, bool]],
                                                 List[Tuple[str, bool]]]:
        """prefix 的直接子项（组/列表），各自按名排序。"""
        dirs: List[Tuple[str, bool]] = []
        leaves: List[Tuple[str, bool]] = []
        for path, is_group in self._store.walk():
            parent = path.rsplit("/", 1)[0] if "/" in path else ""
            if parent != prefix:
                continue
            name = path.rsplit("/", 1)[-1]
            (dirs if is_group else leaves).append((name, is_group))
        return sorted(dirs), sorted(leaves)

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

    # ---- 右键菜单 ----
    def _on_context_menu(self, pos) -> None:
        item = self.itemAt(pos)
        if item is not None and not item.isSelected():
            self.setCurrentItem(item)
        context_group = self._group_of(item)
        tops = self._selected_paths_top()

        menu = QMenu(self)
        a_add = menu.addAction("添加组…")
        menu.addSeparator()
        a_copy = menu.addAction("复制")
        a_cut = menu.addAction("剪切")
        a_paste = menu.addAction("粘贴")
        menu.addSeparator()
        a_rename = menu.addAction("重命名\tF2")
        a_delete = menu.addAction("删除\tDel")

        a_copy.setEnabled(bool(tops))
        a_cut.setEnabled(bool(tops))
        a_paste.setEnabled(self._clipboard.items is not None)
        a_rename.setEnabled(len(tops) == 1)
        a_delete.setEnabled(bool(tops))

        action = menu.exec_(self.viewport().mapToGlobal(pos))
        if action is a_add:
            self._act_add_group(context_group)
        elif action is a_copy:
            self._act_copy()
        elif action is a_cut:
            self._act_cut()
        elif action is a_paste:
            self._act_paste(context_group)
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
        """选中集「顶层化」：去掉被另一选中项包含的子项。"""
        paths = self._selected_paths()
        tops = []
        for p in paths:
            if not any(o != p and p.startswith(o + "/") for o in paths):
                tops.append(p)
        return sorted(set(tops))

    # ---- 操作 ----
    def _act_add_group(self, context_group: str = "") -> None:
        name, ok = QInputDialog.getText(self, "添加组", "组名：")
        if not ok:
            return
        name = name.strip()
        if not name or "/" in name or name in (".", ".."):
            QMessageBox.warning(self, "添加组", "名称非法")
            return
        full = (context_group + "/" + name) if context_group else name
        try:
            self._store.add_group(full)
        except (ValueError, FileExistsError) as e:
            QMessageBox.warning(self, "添加组", "无法添加：%s" % e)
            return
        self._changed(full)

    def _act_copy(self) -> None:
        tops = self._selected_paths_top()
        if not tops:
            return
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
        if not tops:
            return
        self._act_copy()
        for p in tops:
            try:
                self._store.remove(p)
            except FileNotFoundError:
                continue
        self._changed()

    def _act_paste(self, context_group: str = "") -> None:
        if self._clipboard.items is None:
            return
        name, triples = self._clipboard.items
        target = self._dedup_name(context_group, name)   # 完整路径（已含组前缀）
        for rel, is_group, fmts in triples:
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
        for p in tops:
            try:
                self._store.remove(p)
            except FileNotFoundError:
                continue
        self._changed()

    # ---- 变更收尾 ----
    def _changed(self, current_path: Optional[str] = None) -> None:
        """刷新树 + 发 store_changed + 回调（上层保存）。"""
        self.refresh(current_path)
        self.store_changed.emit()
        self._on_changed()

if __name__ == "__main__":
    import sys

    from PyQt5.QtWidgets import QApplication, QInputDialog, QMessageBox

    from actions.base import Step
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

    # 只显示键值；组在上、列表在下（每层各自排序）
    top = [tw.topLevelItem(i).text(0)
           for i in range(tw.topLevelItemCount())]
    assert top == ["清理体力", "空组", "打开软件"], top
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

    print("StepListTreeWidget smoke OK")
```
