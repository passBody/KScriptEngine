# -*- coding: utf-8 -*-
"""
全局变量管理树（GUI 控件）
========================

:class:`VariableTreeWidget` 继承 :class:`QTreeWidget`，管理
:class:`model.variable_tree.VariableTree`（存于工程 ``variables.json``）。左树 +
:class:`VariableEditPanel` 中编辑卡，按变量类型生成专属编辑器（预留接口），
实时校验、禁用提交非法值；image 类变量经资源选择器改值。

基本用法
--------
::

    from model import KscpPackage
    from widgets import VariableTreeWidget
    tree = VariableTreeWidget(pkg)
    tree.preview_widget()   # 编辑卡
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Tuple

from PyQt5.QtCore import Qt, QSize, pyqtSignal
from PyQt5.QtGui import QColor, QFont, QIcon, QKeySequence, QPainter, QPen, QPixmap
from PyQt5.QtWidgets import (
    QAbstractItemView, QDialog, QDialogButtonBox, QHBoxLayout, QInputDialog,
    QLabel, QLineEdit, QMenu, QMessageBox, QPushButton, QShortcut,
    QStackedWidget, QStyle, QToolButton, QTreeWidget, QTreeWidgetItem,
    QVBoxLayout, QWidget,
)

from model.kscp_package import KscpPackage
from model.log_model import LogModel
from model.project_variable import ProjectVariable
from model.variable_tree import VariableTree
from widgets.image_overlay import ImageOverlay
from widgets.resource_tree_widget import ResourceTreeWidget

__all__ = ["VariableTreeWidget", "VariableEditPanel", "CreateVariableDialog"]

_PATH_ROLE = 0x0100


# ----------------------------------------------------------------
# 类型编辑器注册表（预留接口）
# ----------------------------------------------------------------
VAR_EDITORS: Dict[str, Callable[[ProjectVariable, KscpPackage, Callable[[Any], None]],
                                QWidget]] = {}


def register_editor(vtype: str,
                    fn: Callable[[ProjectVariable, KscpPackage, Callable[[Any], None]],
                                 QWidget]) -> None:
    """注册某类型的专属编辑器生成函数（预留接口）。

    ``fn`` 接收 ``(变量, package, on_changed(value))``，返回一个 QWidget；
    编辑卡据此实时校验、控制「确认」按钮。
    """
    VAR_EDITORS[vtype] = fn


def _split_parent(path: str) -> Tuple[str, str]:
    """``路径 -> (父分组, 名)``；无父则父为空串。"""
    if "/" in path:
        parent, name = path.rsplit("/", 1)
    else:
        parent, name = "", path
    return parent, name


def _make_var_icon(vtype: str) -> QIcon:
    """按变量类型绘制小图标：string=横线文本、number=#、image=画框、default=方块。"""
    pm = QPixmap(18, 18)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    if vtype == "string":
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#3a7bd5"))
        for y in (4, 8, 12):
            p.drawRoundedRect(2, y, 14, 2, 1, 1)
    elif vtype == "number":
        p.setPen(QPen(QColor("#27ae60"), 2))
        p.setFont(QFont("Consolas", 10, QFont.Bold))
        p.drawText(pm.rect(), Qt.AlignCenter, "#")
    elif vtype == "image":
        p.setPen(QPen(QColor("#e67e22"), 1.5))
        p.setBrush(QColor("#fff3e0"))
        p.drawRect(2, 2, 14, 14)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#ffd966"))
        p.drawEllipse(4, 4, 5, 5)     # 太阳
        p.setBrush(QColor("#7bbf5e"))
        p.drawRect(3, 12, 12, 3)      # 地面
    else:
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#888888"))
        p.drawRoundedRect(3, 3, 12, 12, 2, 2)
    p.end()
    return QIcon(pm)


# ----------------------------------------------------------------
# 变量树（左）
# ----------------------------------------------------------------
class VariableTreeWidget(QTreeWidget):
    """管理 VariableTree 的 QTreeWidget（左树）。"""

    var_selected = pyqtSignal(str)
    tree_changed = pyqtSignal()      # 变量树变更（_save 写盘后发出）→ 步骤卡片重检颜色

    def __init__(self, package: KscpPackage,
                 tree: Optional[VariableTree] = None,
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._package = package
        self._tree = tree
        self._edit_panel: Optional[VariableEditPanel] = None
        self._clipboard: Optional[Tuple[List[str], str]] = None  # (paths, "copy"|"cut")

        self.setHeaderHidden(True)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)  # Ctrl/Shift 多选
        self.setUniformRowHeights(True)
        self.setFont(QFont("SimSun", 11))     # 宋体、稍大
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._on_context_menu)
        self.currentItemChanged.connect(self._on_current_changed)

        QShortcut(QKeySequence.Copy, self, self._act_copy)
        QShortcut(QKeySequence.Cut, self, self._act_cut)
        QShortcut(QKeySequence.Paste, self, self._act_paste)
        QShortcut("F2", self, self._act_rename)
        QShortcut("Del", self, self._act_delete)

        if self._tree is None:
            self._load()
        else:
            LogModel.instance().info("载入变量树：共享 %d 个变量" % len(self._tree))
        self.refresh()

    # ---- IO ----
    def _load(self) -> None:
        if self._package.exists("variables.json"):
            raw = self._package.read_file("variables.json")
            self._tree = VariableTree.from_json(raw, self._package)
            n = len(self._tree)
        else:
            self._tree = VariableTree.create_empty()
            self._save()
            n = 0
        LogModel.instance().info("载入变量树：%d 个变量" % n)

    def _save(self) -> None:
        assert self._tree is not None
        self._package.write_file("variables.json", self._tree.to_json_bytes())
        LogModel.instance().info("变量已保存（%d 个变量）" % len(self._tree))
        self.tree_changed.emit()

    # ---- 树构建 ----
    def refresh(self, current_path: Optional[str] = None) -> None:
        assert self._tree is not None
        expanded = set(self._expanded_paths())
        cur = current_path if current_path is not None else self._current_path()
        self.blockSignals(True)
        self.clear()
        root = self.invisibleRootItem()
        if root is not None:
            self._fill(root, "")
        for it in self._walk_items():
            p = it.data(0, _PATH_ROLE)
            if p in expanded:
                it.setExpanded(True)
        target = self._find_item(cur)
        if target is not None:
            self.setCurrentItem(target)
        self.blockSignals(False)
        self._on_current_changed(self.currentItem(), None)

    def _fill(self, parent_item: QTreeWidgetItem, prefix: str) -> None:
        assert self._tree is not None
        names = list(self._tree.list_dir(prefix or "/"))
        style = self.style()

        def child_of(n: str) -> str:
            return (prefix + "/" + n) if prefix else n

        dirs, files = [], []
        for n in names:
            (dirs if self._tree.is_group(child_of(n)) else files).append(n)
        dirs.sort()
        files.sort()
        for name in dirs + files:
            child = child_of(name)
            item = QTreeWidgetItem(parent_item)
            item.setData(0, _PATH_ROLE, child)
            if self._tree.is_variable(child):
                var = self._tree.get(child)
                item.setText(0, "%s  [%s]" % (name, var.type))
                if not var.valid:
                    item.setForeground(0, QColor("#e15554"))
                item.setIcon(0, _make_var_icon(var.type))
            else:
                item.setText(0, name)
                if style is not None:
                    item.setIcon(0, style.standardIcon(QStyle.SP_DirIcon))
                self._fill(item, child)

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
        return [it.data(0, _PATH_ROLE) for it in self._walk_items() if it.isExpanded()]

    def _current_path(self) -> str:
        cur = self.currentItem()
        return cur.data(0, _PATH_ROLE) if cur is not None else ""

    # ---- 选中 ----
    def _on_current_changed(self, cur, _prev) -> None:
        path = cur.data(0, _PATH_ROLE) if cur is not None else ""
        if path:
            self.var_selected.emit(path)
        if self._edit_panel is not None:
            self._edit_panel.load(path)

    # ---- 菜单 ----
    def _on_context_menu(self, pos) -> None:
        item = self.itemAt(pos)
        if item is not None and not item.isSelected():
            self.setCurrentItem(item)
        context_group = self._group_of(item)
        menu = QMenu(self)
        a_add_var = menu.addAction("添加变量…")
        a_add_group = menu.addAction("添加组…")
        menu.addSeparator()
        a_copy = menu.addAction("复制\tCtrl+C")
        a_cut = menu.addAction("剪切\tCtrl+X")
        a_paste = menu.addAction("粘贴\tCtrl+V")
        menu.addSeparator()
        a_rename = menu.addAction("重命名\tF2")
        a_delete = menu.addAction("删除\tDel")
        tops = self._selected_paths_top()
        has_sel = bool(tops)
        a_copy.setEnabled(has_sel)
        a_cut.setEnabled(has_sel)
        a_paste.setEnabled(self._clipboard is not None)
        a_rename.setEnabled(len(tops) == 1)
        a_delete.setEnabled(has_sel)
        action = menu.exec_(self.viewport().mapToGlobal(pos))
        if action is a_add_var:
            self._act_add_var(context_group)
        elif action is a_add_group:
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

    # ---- 操作 ----
    def _act_add_var(self, context_group: str = "") -> None:
        assert self._tree is not None
        dlg = CreateVariableDialog(self._package, self._tree, context_group, self)
        path, var = dlg.make()
        if path is None or var is None:
            LogModel.instance().debug("创建变量对话框取消")
            return
        try:
            self._tree.add(path, var)
        except (FileExistsError, ValueError) as e:
            LogModel.instance().warning("变量 %s 值不合规，已阻止：%s" % (path, e))
            QMessageBox.warning(self, "添加变量", "无法添加：%s" % e)
            return
        self._save()
        self.refresh(path)
        LogModel.instance().info("添加变量 %s（%s）" % (path, var.type))

    def _act_add_group(self, context_group: str = "") -> None:
        assert self._tree is not None
        name, ok = QInputDialog.getText(self, "添加组", "组名：")
        if not ok:
            return
        name = name.strip()
        if not name or "/" in name or name in (".", ".."):
            QMessageBox.warning(self, "添加组", "名称非法")
            return
        path = (context_group + "/" + name) if context_group else name
        try:
            self._tree.add_group(path)
        except (FileExistsError, ValueError) as e:
            QMessageBox.warning(self, "添加组", "无法添加：%s" % e)
            return
        self._save()
        self.refresh(path)
        LogModel.instance().info("添加分组 %s" % path)

    # ---- 复制 / 剪切 / 粘贴 ----
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

    def _dedup_name(self, group: str, name: str) -> str:
        """若 group/name 已存在，追加 (k) 直到不重名。"""
        assert self._tree is not None
        target = (group + "/" + name) if group else name
        if not self._tree.exists(target):
            return name
        k = 1
        while True:
            cand = "%s(%d)" % (name, k)
            tgt = (group + "/" + cand) if group else cand
            if not self._tree.exists(tgt):
                return cand
            k += 1

    def _copy_var_or_group(self, src: str, dst: str) -> None:
        """复制变量或整棵分组（含子变量）到 dst。"""
        assert self._tree is not None
        if self._tree.is_variable(src):
            var = self._tree.get(src)
            new_var = ProjectVariable.from_format_string(
                var.to_format_string(), self._package)
            self._tree.add(dst, new_var)
        elif self._tree.is_group(src):
            self._tree.add_group(dst)
            for name in self._tree.list_dir(src):
                self._copy_var_or_group(src + "/" + name, dst + "/" + name)

    def _act_copy(self) -> None:
        paths = self._selected_paths_top()
        if paths:
            self._clipboard = (paths, "copy")

    def _act_cut(self) -> None:
        paths = self._selected_paths_top()
        if paths:
            self._clipboard = (paths, "cut")

    def _act_paste(self, context_group: Optional[str] = None) -> None:
        if self._clipboard is None:
            return
        assert self._tree is not None
        if context_group is None:
            context_group = self._group_of(self.currentItem())
        paths, mode = self._clipboard
        for src in paths:
            name = self._dedup_name(context_group, _split_parent(src)[1])
            dst = (context_group + "/" + name) if context_group else name
            try:
                if mode == "copy":
                    self._copy_var_or_group(src, dst)
                else:  # cut
                    self._tree.move(src, dst)
            except (FileExistsError, FileNotFoundError, ValueError) as e:
                LogModel.instance().warning("粘贴 %s 失败：%s" % (src, e))
                continue
        if mode == "cut":
            self._clipboard = None
        self._save()
        self.refresh()
        LogModel.instance().info("粘贴 %d 项到 %s" % (len(paths), context_group or "根"))

    def _act_rename(self) -> None:
        assert self._tree is not None
        old = self._current_path()
        if not old:
            return
        parent, name = _split_parent(old)
        new_name, ok = QInputDialog.getText(self, "重命名", "新名称：", text=name)
        if not ok:
            return
        new_name = new_name.strip()
        if not new_name or "/" in new_name or new_name in (".", ".."):
            QMessageBox.warning(self, "重命名", "名称非法")
            return
        new_path = (parent + "/" + new_name) if parent else new_name
        if new_path == old:
            return
        try:
            self._tree.move(old, new_path)
        except (FileExistsError, FileNotFoundError, ValueError) as e:
            QMessageBox.warning(self, "重命名", "无法重命名：%s" % e)
            return
        self._save()
        self.refresh(new_path)
        LogModel.instance().info("移动变量 %s → %s" % (old, new_path))

    def _act_delete(self) -> None:
        assert self._tree is not None
        path = self._current_path()
        if not path:
            return
        if QMessageBox.question(self, "删除", "确定删除 %s？" % path,
                                QMessageBox.Yes | QMessageBox.No,
                                QMessageBox.Yes) != QMessageBox.Yes:
            return
        try:
            self._tree.remove(path)
        except FileNotFoundError as e:
            QMessageBox.warning(self, "删除", "无法删除：%s" % e)
            return
        self._save()
        self.refresh()
        LogModel.instance().info("删除变量 %s" % path)

    def _group_of(self, item: Optional[QTreeWidgetItem]) -> str:
        """item 所在分组：item 是变量取其父分组；item 是分组取自身。"""
        assert self._tree is not None
        if item is None:
            return ""
        p = item.data(0, _PATH_ROLE)
        if not p:
            return ""
        if self._tree.is_variable(p):
            return _split_parent(p)[0]
        return p

    # ---- 预览 ----
    def preview_widget(self) -> "VariableEditPanel":
        if self._edit_panel is None:
            assert self._tree is not None
            self._edit_panel = VariableEditPanel(self._package, self._tree, self)
            self._edit_panel.load(self._current_path())
        return self._edit_panel


# ----------------------------------------------------------------
# 编辑卡（中）
# ----------------------------------------------------------------
# 主按钮（确认）：蓝
_BTN_PRIMARY = (
    "QPushButton { padding:6px 18px; min-width:80px; min-height:30px;"
    " border:1px solid #2f6db5; border-radius:6px; background:#3a7bd5; color:#fff; }"
    "QPushButton:hover { background:#2f6db5; }"
    "QPushButton:pressed { background:#285a9e; }"
    "QPushButton:disabled { background:#bcd4ee; border-color:#bcd4ee; color:#f0f6fc; }"
)
# 次按钮（撤销）：灰
_BTN_SECONDARY = (
    "QPushButton { padding:6px 18px; min-width:80px; min-height:30px;"
    " border:1px solid #ccc; border-radius:6px; background:#f7f7f7; color:#333; }"
    "QPushButton:hover { background:#eaeaea; border-color:#b5b5b5; }"
    "QPushButton:pressed { background:#dcdcdc; }"
    "QPushButton:disabled { color:#b0b0b0; background:#f0f0f0; border-color:#e0e0e0; }"
)


class VariableEditPanel(QStackedWidget):
    """按变量类型生成编辑器，实时校验、禁用提交非法值；支持多步撤销。"""

    _UNDO_LIMIT = 100

    def __init__(self, package: KscpPackage,
                 tree: VariableTree,
                 tree_widget: VariableTreeWidget,
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._package = package
        self._tree = tree
        self._tree_widget = tree_widget
        self._path: str = ""
        self._cur_value: Any = None
        self._undo_stack: List[Any] = []

        self._placeholder = QLabel("选择一个变量以编辑")
        self._placeholder.setAlignment(Qt.AlignCenter)
        self._placeholder.setStyleSheet("color:#999; font-size:14px;")

        self._editor_host = QWidget()
        host_lay = QVBoxLayout(self._editor_host)
        host_lay.setContentsMargins(14, 14, 14, 14)
        host_lay.setSpacing(6)
        self._header = QLabel("")
        self._header.setStyleSheet("font-weight:bold;")
        self._editor_slot = QWidget()
        self._editor_slot_lay = QVBoxLayout(self._editor_slot)
        self._editor_slot_lay.setContentsMargins(0, 0, 0, 0)
        self._status = QLabel("")               # 仅出错时显示（去除「可保存」提示）
        self._status.setWordWrap(True)
        self._status.setStyleSheet("color:#e15554;")
        self._status.setVisible(False)

        btn_host = QWidget()
        btn_row = QHBoxLayout(btn_host)
        btn_row.setContentsMargins(0, 0, 0, 0)
        btn_row.setSpacing(8)
        btn_row.addStretch()
        self._btn_undo = QPushButton("撤销")
        self._btn_undo.setToolTip("撤销上一次确认的修改")
        self._btn_undo.setEnabled(False)
        self._btn_undo.setStyleSheet(_BTN_SECONDARY)
        self._btn_undo.clicked.connect(self._on_undo)
        self._btn_save = QPushButton("确认")
        self._btn_save.setStyleSheet(_BTN_PRIMARY)
        self._btn_save.clicked.connect(self._on_save)
        btn_row.addWidget(self._btn_undo)
        btn_row.addWidget(self._btn_save)

        # header 置顶、编辑区吸收全部余量（image 缩略图等随面板高度缩放）、
        # 状态/按钮置底。修复前上下各一 stretch 把编辑区夹在 sizeHint 高度，
        # 面板已显示后再选中变量时缩略图恒卡 200 下限。
        host_lay.addWidget(self._header)
        host_lay.addWidget(self._editor_slot, 1)
        host_lay.addWidget(self._status)
        host_lay.addWidget(btn_host)

        self._unsupported = QLabel("该类型暂不支持可视化编辑")
        self._unsupported.setAlignment(Qt.AlignCenter)
        self._unsupported.setStyleSheet("color:#999;")

        self.addWidget(self._placeholder)     # 0
        self.addWidget(self._editor_host)     # 1
        self.addWidget(self._unsupported)    # 2

    def load(self, path: str) -> None:
        # 仅在切换变量时清空撤销栈；保存/撤销后的同路径重载保留栈
        if path != self._path:
            self._undo_stack = []
        self._path = path
        if not path or not self._tree.is_variable(path):
            self.setCurrentIndex(0)
            self._update_undo_btn()
            return
        var = self._tree.get(path)
        self._cur_value = var.data
        self._header.setText("%s  ·  %s%s" % (
            path, var.type, "  ·  无效" if not var.valid else ""))
        self._rebuild_editor(var.data)
        self._validate()
        self._update_undo_btn()

    def _rebuild_editor(self, value: Any) -> None:
        """用 ``value`` 重建当前变量的编辑器（不清 undo 栈）。"""
        if not self._path or not self._tree.is_variable(self._path):
            self.setCurrentIndex(0)
            return
        var = self._tree.get(self._path)
        fn = VAR_EDITORS.get(var.type)
        while self._editor_slot_lay.count():
            w = self._editor_slot_lay.takeAt(0).widget()
            if w is not None:
                w.deleteLater()
        if fn is None:
            self.setCurrentIndex(2)
            return
        tmp = ProjectVariable.create(var.type, value, self._package)
        editor = fn(tmp, self._package, self._on_changed)
        if var.type == "image":
            # 图片编辑器不限宽且吸满横向余量：缩略图宽度随面板/窗口变化
            # （修复限宽 560 导致「高度随窗口、宽度卡死」；横向 stretch 同垂直一样吸收余量）
            self._editor_slot_lay.addWidget(editor, 1)
        else:
            editor.setMaximumWidth(560)                   # 限宽，避免宽屏下输入框过宽偏左
            self._editor_slot_lay.addWidget(editor)
            # 顶部对齐 + 水平居中：编辑器按 sizeHint 紧凑排布，余量留在底部。
            # 只 AlignHCenter 时编辑器(Preferred)被拉满面板，内部 QLabel 吸收
            # 全部余量 → 描述文本被拉高、与输入框之间出现数百 px 空隙（优化 14f 根因）
            self._editor_slot_lay.setAlignment(editor, Qt.AlignHCenter | Qt.AlignTop)
        self.setCurrentIndex(1)

    def _on_changed(self, value: Any) -> None:
        # 编辑期改动不计入撤销栈；只有点「确认」提交后才入栈
        self._cur_value = value
        self._validate()

    def _on_undo(self) -> None:
        """撤销上一次「确认」的提交：把变量恢复到上一个已提交值。"""
        if not self._undo_stack:
            return
        if not self._path or not self._tree.is_variable(self._path):
            return
        prev = self._undo_stack.pop()
        var = self._tree.get(self._path)
        try:
            restored = ProjectVariable.create(var.type, prev, self._package)
        except (ValueError, TypeError) as e:
            LogModel.instance().warning("撤销 %s 失败：%s" % (self._path, e))
            return
        if not restored.valid:
            LogModel.instance().warning("撤销 %s 失败：值不合规" % self._path)
            return
        self._tree.set(self._path, restored)
        self._tree_widget._save()
        self._tree_widget.refresh(self._path)   # 同路径重载：栈保留、编辑器回到撤销后的值
        LogModel.instance().info("撤销 %s" % self._path)

    def _validate(self) -> None:
        if not self._path or not self._tree.is_variable(self._path):
            self._btn_save.setEnabled(False)
            self._status.setVisible(False)
            return
        var = self._tree.get(self._path)
        try:
            cand = ProjectVariable.create(var.type, self._cur_value, self._package)
            ok = cand.valid
            reason = "" if ok else "值不合规"
        except (ValueError, TypeError) as e:
            ok = False
            reason = "值不合规：%s" % e
        # 值与当前已保存值一致 → 无需确认，禁用按钮（提示「未修改」）
        if ok and self._cur_value == var.data:
            self._btn_save.setEnabled(False)
            self._status.setText("未修改")
            self._status.setStyleSheet("color:#888;")
            self._status.setVisible(True)
        elif ok:
            self._btn_save.setEnabled(True)
            self._status.setVisible(False)       # 合法且已修改：不显示提示
        else:
            self._btn_save.setEnabled(False)
            self._status.setText(reason)
            self._status.setStyleSheet("color:#e15554;")
            self._status.setVisible(True)

    def _update_undo_btn(self) -> None:
        self._btn_undo.setEnabled(bool(self._undo_stack))

    def _on_save(self) -> None:
        if not self._path or not self._tree.is_variable(self._path):
            return
        var = self._tree.get(self._path)
        try:
            new_var = ProjectVariable.create(var.type, self._cur_value, self._package)
        except (ValueError, TypeError) as e:
            LogModel.instance().warning("变量 %s 值不合规，已阻止：%s" % (self._path, e))
            return
        if not new_var.valid:
            LogModel.instance().warning("变量 %s 值不合规，已阻止" % self._path)
            return
        # 记录上一个「已提交值」入撤销栈，再覆盖；只有确认后才入栈
        self._undo_stack.append(var.data)
        if len(self._undo_stack) > self._UNDO_LIMIT:
            self._undo_stack.pop(0)
        self._tree.set(self._path, new_var)
        self._tree_widget._save()
        self._tree_widget.refresh(self._path)   # 同路径重载：栈保留、编辑器回到新值
        LogModel.instance().info("修改变量 %s" % self._path)


# ----------------------------------------------------------------
# 内置编辑器
# ----------------------------------------------------------------
def _string_editor(var: ProjectVariable, package: KscpPackage,
                   on_changed: Callable[[Any], None]) -> QWidget:
    w = QWidget()
    lay = QVBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.addWidget(QLabel("字符串值："))
    edit = QLineEdit(str(var.data) if var.data is not None else "")
    edit.textChanged.connect(on_changed)
    lay.addWidget(edit)
    on_changed(edit.text())
    return w


def _number_editor(var: ProjectVariable, package: KscpPackage,
                   on_changed: Callable[[Any], None]) -> QWidget:
    w = QWidget()
    lay = QVBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.addWidget(QLabel("数值（整数或小数）："))
    edit = QLineEdit(str(var.data) if var.data is not None else "")

    def _on(text: str) -> None:
        try:
            on_changed(int(text))
        except ValueError:
            try:
                on_changed(float(text))
            except ValueError:
                on_changed(text)   # 非数值字符串，校验判非法
    edit.textChanged.connect(_on)
    lay.addWidget(edit)
    _on(edit.text())
    return w


class _ClickableLabel(QLabel):
    """可点击的图片缩略图：存原图，随自身尺寸缩放显示，左键点击发 ``clicked``。"""

    clicked = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._raw: Optional[QPixmap] = None
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumHeight(200)
        self.setStyleSheet("background:#1e1e1e; border:1px solid #333; color:#ccc;")

    def set_raw(self, pix: QPixmap) -> None:
        self._raw = pix
        self._rescale()

    def clear_image(self) -> None:
        self._raw = None
        self.setText("（无预览，点击下方按钮选择资源）")

    def _rescale(self) -> None:
        if self._raw is None or self._raw.isNull():
            return
        w = max(self.width() - 8, 64)
        h = max(self.height() - 8, 64)
        super().setPixmap(self._raw.scaled(w, h, Qt.KeepAspectRatio,
                                           Qt.SmoothTransformation))

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt 命名)
        super().resizeEvent(event)
        self._rescale()

    def mousePressEvent(self, event) -> None:  # noqa: N802 (Qt 命名)
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


def _image_editor(var: ProjectVariable, package: KscpPackage,
                  on_changed: Callable[[Any], None]) -> QWidget:
    """image 变量编辑器：缩略图（随尺寸缩放、点击查看大图）+ 选择资源按钮（无编辑框）。

    大图遮罩只盖「视图」：编辑卡内取 VariableEditPanel 作父；创建对话框内
    （无编辑卡）退而盖对话框。当前路径存于可变 ``state``，选择后实时刷新，
    故「查看大图」始终基于最新选中资源。缩略图吸收纵向余量、按钮固定高度，
    避免按钮过高挤占图片。
    """
    w = QWidget()
    lay = QVBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(6)
    state = {"path": str(var.data) if var.data else ""}

    thumb = _ClickableLabel()
    thumb.setCursor(Qt.PointingHandCursor)
    thumb.setToolTip("点击查看大图（滚轮缩放 / 拖拽平移 / 双击或 Esc 关闭）")

    def _refresh(path: str) -> None:
        state["path"] = path
        if path and package.is_file(path):
            pix = QPixmap()
            pix.loadFromData(package.read_file(path))
            thumb.set_raw(pix)
        else:
            thumb.clear_image()

    def _view_big() -> None:
        p = state["path"]
        if not (p and package.is_file(p)):
            return
        pix = QPixmap()
        pix.loadFromData(package.read_file(p))
        host = w
        while host is not None and not isinstance(host, VariableEditPanel):
            host = host.parentWidget()
        ImageOverlay(pix, host if host is not None else w.window()).show_overlay()

    thumb.clicked.connect(_view_big)

    btn_pick = QPushButton("选择资源…")
    btn_pick.setFixedHeight(32)            # 紧凑按钮，避免过高挤占缩略图

    def _pick() -> None:
        p = ResourceTreeWidget.pick_resource(package, tuple(var.suffixes), w)
        if p is None:
            LogModel.instance().debug("选择资源取消")
            return
        _refresh(p)
        on_changed(p)

    btn_pick.clicked.connect(_pick)

    _refresh(state["path"])
    lay.addWidget(thumb, 1)                # 缩略图吸收纵向余量
    lay.addWidget(btn_pick)                # 按钮固定高度
    on_changed(var.data)
    return w


# 注册内置编辑器
register_editor("string", _string_editor)
register_editor("number", _number_editor)
register_editor("image", _image_editor)


# ----------------------------------------------------------------
# 创建对话框
# ----------------------------------------------------------------
class CreateVariableDialog(QDialog):
    """选类型（卡片式）+ 名称 + 值，实时校验，禁用创建非法变量。

    变量在调用方右击的分组 ``parent_group`` 下创建（无需选分组）。
    """

    def __init__(self, package: KscpPackage, tree: VariableTree,
                 parent_group: str = "", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("创建变量")
        self.resize(440, 400)
        self._package = package
        self._tree = tree
        self._parent_group = parent_group
        self._cur_value: Any = None
        self._vtype: str = ""

        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(8)

        # 类型卡片：可勾选、互斥（避免下拉框滚动跳太远）
        lay.addWidget(QLabel("类型："))
        type_row = QHBoxLayout()
        type_row.setSpacing(6)
        self._type_buttons: Dict[str, QToolButton] = {}
        for name in ProjectVariable.supported_types():
            h = ProjectVariable.type_of(name)
            desc = h.description if h is not None else ""
            btn = QToolButton(self)
            btn.setCheckable(True)
            btn.setAutoExclusive(True)
            btn.setAutoRaise(True)
            btn.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
            btn.setIcon(_make_var_icon(name))
            btn.setIconSize(QSize(20, 20))
            btn.setText(name)
            btn.setToolTip(desc)
            btn.setMinimumHeight(40)
            btn.setMinimumWidth(96)
            btn.toggled.connect(lambda checked, n=name: self._on_type_toggled(checked, n))
            type_row.addWidget(btn)
            self._type_buttons[name] = btn
        type_row.addStretch()
        lay.addLayout(type_row)

        self._type_desc = QLabel("")
        self._type_desc.setStyleSheet("color:#666; padding-left:4px;")
        self._type_desc.setWordWrap(True)
        lay.addWidget(self._type_desc)

        self._name_edit = QLineEdit()
        self._name_edit.textChanged.connect(self._validate)
        lay.addWidget(QLabel("名称："))
        lay.addWidget(self._name_edit)

        self._slot = QWidget()
        self._slot_lay = QVBoxLayout(self._slot)
        self._slot_lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self._slot)
        lay.addStretch()

        self._status = QLabel("")
        self._status.setWordWrap(True)
        lay.addWidget(self._status)

        self._btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self._btns.button(QDialogButtonBox.Ok).setText("创建")
        self._btns.accepted.connect(self.accept)
        self._btns.rejected.connect(self.reject)
        lay.addWidget(self._btns)

        # 默认选 string（最常用）
        first = "string" if "string" in self._type_buttons \
            else ProjectVariable.supported_types()[0]
        self._type_buttons[first].setChecked(True)

    def _on_type_toggled(self, checked: bool, name: str) -> None:
        if not checked:
            return
        self._vtype = name
        h = ProjectVariable.type_of(name)
        self._type_desc.setText(h.description if h is not None else "")
        while self._slot_lay.count():
            w = self._slot_lay.takeAt(0).widget()
            if w is not None:
                w.deleteLater()
        default = {"string": "", "number": "0"}.get(name, "")
        var = ProjectVariable.create(name, default, self._package)
        fn = VAR_EDITORS.get(name)
        if fn is not None:
            self._slot_lay.addWidget(fn(var, self._package, self._on_changed))
            # 编辑器内部已调 on_changed 设好 _cur_value；不再覆盖（修复 number 默认 0 被判非法）
        else:
            self._cur_value = default
        self._validate()

    def _on_changed(self, value: Any) -> None:
        self._cur_value = value
        self._validate()

    def _validate(self) -> None:
        name = self._name_edit.text().strip()
        path = (self._parent_group + "/" + name) if self._parent_group else name
        ok = True
        reason = ""
        if not name or "/" in name or name in (".", ".."):
            ok = False
            reason = "名称非法"
        elif self._tree.exists(path):
            ok = False
            reason = "名称已存在：%s" % path
        else:
            try:
                cand = ProjectVariable.create(self._vtype, self._cur_value, self._package)
                if not cand.valid:
                    ok = False
                    reason = "值不合规"
            except (ValueError, TypeError) as e:
                ok = False
                reason = "值不合规：%s" % e
        self._btns.button(QDialogButtonBox.Ok).setEnabled(ok)
        if ok:
            self._status.setText("可创建")
            self._status.setStyleSheet("color:#27ae60;")
        else:
            self._status.setText(reason)
            self._status.setStyleSheet("color:#e15554;")

    def make(self) -> Tuple[Optional[str], Optional[ProjectVariable]]:
        """exec 后返回 ``(path, var)``；取消或非法返回 ``(None, None)``。"""
        if self.exec_() != QDialog.Accepted:
            return None, None
        name = self._name_edit.text().strip()
        path = (self._parent_group + "/" + name) if self._parent_group else name
        try:
            var = ProjectVariable.create(self._vtype, self._cur_value, self._package)
        except (ValueError, TypeError):
            return None, None
        if not var.valid:
            return None, None
        LogModel.instance().info("创建变量 %s（%s）" % (path, self._vtype))
        return path, var


if __name__ == "__main__":
    import sys
    from PyQt5.QtWidgets import QApplication, QHBoxLayout
    from PyQt5.QtGui import QColor, QImage
    from PyQt5.QtCore import QBuffer

    app = QApplication.instance() or QApplication(sys.argv)

    def _png(color: str) -> bytes:
        img = QImage(40, 30, QImage.Format_RGB32)
        img.fill(QColor(color))
        buf = QBuffer(); buf.open(QBuffer.ReadWrite)
        img.save(buf, "PNG")
        return bytes(buf.data())

    pkg = KscpPackage.create_empty()
    pkg.write_file("assets/a.png", _png("#3a7bd5"))
    pkg.write_file("assets/b.txt", b"hi")

    # 注入变量树（空 → 加几个变量 → 写回）
    pkg.write_file("variables.json", VariableTree.create_empty().to_json_bytes())
    tree = VariableTreeWidget(pkg)
    t = tree._tree
    assert t is not None
    t.add("s", ProjectVariable.create("string", "hello", pkg))
    t.add("n", ProjectVariable.create("number", 42, pkg))
    t.add_group("组1")
    t.add("组1/p", ProjectVariable.create("image", "assets/a.png", pkg))
    tree.refresh()

    # 顶层：分组在上、变量在下
    top = [tree.topLevelItem(i).text(0) for i in range(tree.topLevelItemCount())]
    assert top[0].startswith("组1"), top
    assert any(x.startswith("s") for x in top), top

    # 编辑卡加载 image 变量
    ep = tree.preview_widget()
    tree.setCurrentItem(tree._find_item("组1/p"))
    assert ep.currentIndex() == 1   # image 编辑器页

    # image 编辑器：无编辑框，只有可点击缩略图 + 选择资源按钮（查看大图按钮已移除）
    img_ed = (ep._editor_slot_lay.itemAt(0).widget()
              if ep._editor_slot_lay.count() else None)
    assert img_ed is not None
    thumbs = img_ed.findChildren(_ClickableLabel)
    assert len(thumbs) == 1
    assert not thumbs[0].pixmap().isNull()        # 已加载 a.png
    btns = img_ed.findChildren(QPushButton)
    assert any(b.text() == "选择资源…" for b in btns)
    assert not any(b.text() == "查看大图" for b in btns)

    # image 缩略图随编辑卡余量吸高（真实路径：面板已显示后再选中变量；
    # 修复前 editor_slot 被上下 stretch 夹在 sizeHint 高度 → 缩略图恒 200 下限）
    ep.show()
    app.processEvents()
    ep.resize(ep.width(), 800)
    app.processEvents()
    tree.setCurrentItem(tree._find_item("组1/p"))    # 已显示后重建 image 编辑器
    app.processEvents()
    img_ed2 = ep._editor_slot_lay.itemAt(0).widget()
    assert img_ed2 is not None
    th_big = img_ed2.findChildren(_ClickableLabel)[0]
    assert th_big.height() > 300, th_big.height()    # 高面板 → 明显超过 200 下限
    ep.resize(ep.width(), 500)
    app.processEvents()
    assert 200 < th_big.height() < 600, th_big.height()  # 随面板变矮同步收缩
    ep.resize(ep.width(), 800)
    app.processEvents()

    # ---- 14e：缩略图宽度随面板（修复 image 编辑器限宽 560 → 高度变宽度不变） ----
    assert img_ed2.maximumWidth() > 1000, img_ed2.maximumWidth()  # image 不再设 560 限宽
    ep.resize(1000, 800)                     # 宽面板
    app.processEvents()
    assert th_big.width() > 700, th_big.width()    # 吸满面板宽（修复前恒 552）
    ep.resize(700, 800)                      # 变窄
    app.processEvents()
    assert 300 < th_big.width() < 1000, th_big.width()  # 缩略图同步收缩
    ep.resize(ep.width(), 500)
    app.processEvents()
    ep.hide()

    # ---- 14f：描述与编辑框紧邻（修复编辑区吸满面板 → 内部 QLabel 被拉高、数百 px 空隙） ----
    ep.show()
    app.processEvents()
    ep.resize(700, 600)                        # 高面板：余量最大的场景
    app.processEvents()
    tree.setCurrentItem(tree._find_item("s"))  # 真实路径重建 string 编辑器
    app.processEvents()
    ed_str = ep._editor_slot_lay.itemAt(0).widget()
    lab_str = [l for l in ed_str.findChildren(QLabel) if "字符串值" in l.text()][0]
    inp_str = ed_str.findChildren(QLineEdit)[0]
    gap = inp_str.geometry().top() - lab_str.geometry().bottom()
    assert 0 <= gap <= 20, gap                 # 修复前：QLabel 拉伸到 437px → 描述与输入框隔数百 px
    assert ed_str.height() < 150, ed_str.height()   # 编辑器紧凑排布，余量留在底部
    tree.setCurrentItem(tree._find_item("n"))  # number 同样
    app.processEvents()
    ed_num = ep._editor_slot_lay.itemAt(0).widget()
    lab_num = [l for l in ed_num.findChildren(QLabel) if "数值" in l.text()][0]
    inp_num = ed_num.findChildren(QLineEdit)[0]
    gap2 = inp_num.geometry().top() - lab_num.geometry().bottom()
    assert 0 <= gap2 <= 20, gap2
    assert ed_num.height() < 150, ed_num.height()
    tree.setCurrentItem(tree._find_item("组1/p"))   # image 仍吸满（14d/14e 不回归）
    app.processEvents()
    ed_img = ep._editor_slot_lay.itemAt(0).widget()
    assert ed_img.height() > 400, ed_img.height()
    ep.hide()

    # string：编辑期不入栈；确认后才入栈；撤销回退上一次确认（可多次）
    tree.setCurrentItem(tree._find_item("s"))     # s = "hello"
    assert ep.currentIndex() == 1
    assert not ep._btn_undo.isEnabled()           # 无确认历史
    # 值与当前一致 → 禁用确认（未修改）；改为不同值 → 启用
    ep._on_changed("hello")                       # 与当前值一致
    assert not ep._btn_save.isEnabled()           # 未修改 → 禁用确认
    assert ep._status.text() == "未修改"          # 提示「未修改」
    ep._on_changed("world")                       # 未确认编辑（改值）
    assert ep._btn_save.isEnabled()
    assert not ep._btn_undo.isEnabled()           # 未确认 → 仍不可撤销
    assert ep._undo_stack == []
    ep._on_save()                                 # 确认 hello→world，入栈 hello
    assert tree._tree.get("s").data == "world"
    assert ep._btn_undo.isEnabled()
    assert ep._undo_stack == ["hello"]
    ep._on_changed("foo")                         # 未确认编辑（不入栈）
    assert ep._undo_stack == ["hello"]
    ep._on_save()                                 # 确认 world→foo，入栈 world
    assert ep._undo_stack == ["hello", "world"]
    ep._on_undo()                                 # 撤销 foo→world
    assert tree._tree.get("s").data == "world"
    assert ep._btn_undo.isEnabled()
    ep._on_undo()                                 # 撤销 world→hello
    assert tree._tree.get("s").data == "hello"
    assert not ep._btn_undo.isEnabled()           # 栈空 → 禁用
    # 恢复 s=world，供后续复制/粘贴冒烟沿用
    ep._on_changed("world")
    ep._on_save()
    assert tree._tree.get("s").data == "world"

    # 创建对话框：卡片选类型、实时校验、禁用非法
    cd = CreateVariableDialog(pkg, tree._tree, "", None)
    cd._type_buttons["string"].setChecked(True)   # 选 string
    cd._name_edit.setText("newvar")
    cd._on_changed("val")                         # 合法字符串值 → 启用
    assert cd._btns.button(QDialogButtonBox.Ok).isEnabled()
    cd._name_edit.setText("a/b")                  # 非法名 → 禁用
    assert not cd._btns.button(QDialogButtonBox.Ok).isEnabled()

    # number：默认值 0 应判合法（修复 bug）；非数值 → 禁用；合法 → 启用
    cd._type_buttons["number"].setChecked(True)
    cd._name_edit.setText("okname")
    assert cd._btns.button(QDialogButtonBox.Ok).isEnabled()   # 默认 0 合法
    cd._on_changed("notnum")                      # 非数值 → 禁用
    assert not cd._btns.button(QDialogButtonBox.Ok).isEnabled()
    cd._on_changed(3.14)                          # 合法 → 启用
    assert cd._btns.button(QDialogButtonBox.Ok).isEnabled()

    # 在分组下创建（parent_group 决定路径，无分组选择器）
    cd2 = CreateVariableDialog(pkg, tree._tree, "组1", None)
    assert cd2._parent_group == "组1"

    # ---- 14e：创建对话框内 image 缩略图宽度随对话框（创建处无 560 限宽） ----
    cd3 = CreateVariableDialog(pkg, tree._tree, "", None)
    cd3._type_buttons["image"].setChecked(True)      # 切到 image 编辑器
    cd3.show()
    app.processEvents()
    th_dlg = cd3.findChildren(_ClickableLabel)
    assert len(th_dlg) == 1
    w0 = th_dlg[0].width()
    cd3.resize(700, cd3.height())                    # 拉宽对话框
    app.processEvents()
    assert th_dlg[0].width() > w0 + 80, (w0, th_dlg[0].width())  # 缩略图同步变宽
    cd3.hide()

    # 复制/粘贴 + 去重：复制 s，粘到根 → s(1)、s(2)
    tree.clearSelection()
    tree._find_item("s").setSelected(True)
    tree.setCurrentItem(tree._find_item("s"))
    tree._act_copy()
    assert tree._clipboard == (["s"], "copy")
    tree._act_paste("")                # 粘到根
    assert tree._tree.exists("s(1)")
    assert tree._tree.get("s(1)").data == "world"   # s 当前值 world
    tree._act_paste("")                # 再粘 → s(2)
    assert tree._tree.exists("s(2)")

    # 剪切+粘贴：把 s(1) 移到 组1（剪切后 clipboard 清空）
    tree.setCurrentItem(tree._find_item("s(1)"))
    tree._act_cut()
    tree._act_paste("组1")
    assert tree._tree.exists("组1/s(1)")
    assert not tree._tree.exists("s(1)")
    assert tree._clipboard is None

    # ---- 共享树 + tree_changed（步骤列表管理树支持） ----
    # 缺省构造（tree=None）旧行为不变：自加载 variables.json（既有断言已覆盖）
    # 给定共享树 → 使用传入实例（不读盘/不写空文件）
    shared = VariableTree.create_empty()
    shared.add("n", ProjectVariable.create("number", 7, pkg))
    vtw = VariableTreeWidget(pkg, shared)
    assert vtw._tree is shared
    assert vtw._tree.get("n").data == 7
    # _save → tree_changed 发出
    fired = []
    vtw.tree_changed.connect(lambda: fired.append(1))
    vtw._save()
    assert fired == [1]
    # 缺省构造走 _load（文件在）→ 与共享树互不影响
    assert tree._tree is not None and tree._tree.get("s").data == "world"

    print("VariableTreeWidget smoke OK")
