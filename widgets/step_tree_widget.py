# -*- coding: utf-8 -*-
"""
步骤模板管理树（GUI 控件）
========================

:class:`StepTreeWidget` 继承 :class:`QTreeWidget`,管理
:class:`model.step_manager.StepManager` 注册的步骤模板:左侧树展示模板
(组 = ``actions/`` 目录含空组,叶子 = 已注册模板),右侧 :class:`StepInfoPanel`
显示选中模板的只读信息(名称/描述/分组/输入输出参数**左右两栏对齐**)。

**只展示模板,不创建对象**:本控件绝不调用 ``create_step``;信息数据源为模板
**类**级数据(``_signature``),零实例创建。

操作:叶子右键 → 移动到分组… / 删除;组右键 → 创建组…(组下嵌套) / 重命名组…;
空白区右键 → 创建组…(顶层)。快捷键:Del 删除叶子、F2 重命名组。

基本用法
--------
::

    from model import KscpPackage
    from widgets.step_tree_widget import StepTreeWidget
    tree = StepTreeWidget(pkg)
    tree.preview_widget()   # 信息面板
"""

from __future__ import annotations

from typing import Dict, List, Optional

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QColor, QFont, QIcon, QKeySequence, QPainter, QPixmap
from PyQt5.QtWidgets import (
    QAbstractItemView, QComboBox, QDialog, QDialogButtonBox, QHBoxLayout,
    QInputDialog, QLabel, QMenu, QMessageBox, QShortcut, QStackedWidget,
    QStyle, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from model.kscp_package import KscpPackage
from model.step_manager import StepManager
from model.variable_tree import VariableTree

__all__ = ["StepTreeWidget", "StepInfoPanel", "MoveStepDialog"]

_PATH_ROLE = 0x0100   # Qt.UserRole（取整数值规避存根误报）


def _make_step_icon() -> QIcon:
    """叶子小图标：橙色圆角方块内三条浅色横线（与活动栏「步骤」图标同色系）。"""
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


class StepTreeWidget(QTreeWidget):
    """步骤模板管理树：组 = ``actions/`` 目录（含空组），叶子 = 已注册模板。

    只展示模板不创建对象：数据全部来自 ``StepManager`` 注册表与模板**类**级
    数据（``_signature``），绝不调用 ``create_step``。
    """

    step_selected = pyqtSignal(str)

    def __init__(self, package: KscpPackage,
                 mgr: Optional[StepManager] = None,
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._package = package
        if mgr is not None:
            # 宿主共享同一模板工厂（避免重复 load → 重复「模板加载完成」日志）
            self._mgr = mgr
        else:
            # 展示不需要变量树；仅因 StepManager 构造签名要求，传内存空树（绝不落盘）
            self._mgr = StepManager(package, VariableTree.create_empty())
        self._info_panel: Optional[StepInfoPanel] = None
        self._group_templates: Dict[str, List] = {}

        self.setHeaderHidden(True)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setUniformRowHeights(True)
        self.setFont(QFont("SimSun", 11))
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._on_context_menu)
        self.currentItemChanged.connect(self._on_current_changed)

        QShortcut(QKeySequence.Delete, self, self._act_delete)
        QShortcut("F2", self, self._act_rename_group)

        if not self._package.is_dir("actions"):   # 空包：自建，避免 list_dir 崩溃
            self._package.make_dir("actions")
        if mgr is None:   # 共享 mgr 时宿主已 load 过（幂等，无需重复加载/日志）
            self._mgr.load()
        self.refresh()

    def refresh(self, current_path: Optional[str] = None) -> None:
        """从 package 目录 + 注册表重建树，保留展开/选中；``current_path`` 指定当前项。"""
        expanded = set(self._expanded_paths())
        selected = set(self._selected_paths())
        cur = current_path if current_path is not None else self._current_path()
        self._group_templates = self._build_group_map()
        self.blockSignals(True)
        self.clear()
        root = self.invisibleRootItem()
        if root is not None:
            self._fill(root, "actions")
        for item in self._walk_items():
            p = item.data(0, _PATH_ROLE)
            if p in expanded:
                item.setExpanded(True)
            if p in selected:
                item.setSelected(True)
        target = self._find_item(cur)
        if target is not None:
            self.setCurrentItem(target)
        self.blockSignals(False)
        self._on_current_changed(self.currentItem(), None)

    def _build_group_map(self) -> Dict[str, List]:
        """注册表路径 → {组: [(模板路径, 类), ...]}，组内按路径排序。"""
        m: Dict[str, List] = {}
        for path in self._mgr.template_paths():
            g = path.rsplit("/", 1)[0] if "/" in path else ""
            m.setdefault(g, []).append((path, self._mgr.template_class(path)))
        for v in m.values():
            v.sort(key=lambda t: t[0])
        return m

    def _fill(self, parent_item: QTreeWidgetItem, dir_path: str) -> None:
        """递归填充：目录（含空组）在前，模板叶子（仅已注册）在后。"""
        names = list(self._package.list_dir(dir_path))

        def child_of(n: str) -> str:
            return (dir_path + "/" + n) if dir_path else n

        dirs = sorted(n for n in names if self._package.is_dir(child_of(n)))
        for name in dirs:
            child = child_of(name)
            item = QTreeWidgetItem(parent_item)
            item.setText(0, name)
            item.setData(0, _PATH_ROLE, child)
            style = self.style()
            if style is not None:
                item.setIcon(0, style.standardIcon(QStyle.SP_DirIcon))
            self._fill(item, child)
        group_key = dir_path[len("actions/"):] if dir_path != "actions" else ""
        for path, cls in self._group_templates.get(group_key, []):
            item = QTreeWidgetItem(parent_item)
            item.setText(0, "%s (%d→%d)" % (
                cls.name,
                len(cls._signature(cls.input_class)),
                len(cls._signature(cls.output_class))))
            item.setData(0, _PATH_ROLE, path)
            item.setIcon(0, _make_step_icon())

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

    def _current_path(self) -> str:
        cur = self.currentItem()
        return cur.data(0, _PATH_ROLE) if cur is not None else ""

    def _on_current_changed(self, cur, _prev) -> None:
        path = cur.data(0, _PATH_ROLE) if cur is not None else ""
        if path and not path.startswith("actions/"):
            self.step_selected.emit(path)
        self._update_panel(path)

    def _update_panel(self, path: str) -> None:
        if self._info_panel is None:
            return
        if not path:
            self._info_panel.show_placeholder()
        elif path.startswith("actions/"):
            self._info_panel.show_placeholder("（分组）")
        else:
            try:
                self._info_panel.load(path)
            except ValueError:
                self._info_panel.show_placeholder()

    def preview_widget(self) -> "StepInfoPanel":
        if self._info_panel is None:
            self._info_panel = StepInfoPanel(self._mgr, self)
            self._update_panel(self._current_path())
        return self._info_panel

    def import_templates(self, source_dir: str) -> int:
        """把外部 actions 文件夹的 .py 步骤文件全部导入（递归；覆盖同名；坏文件逐文件回滚）；刷新树并返回成功数。"""
        n = self._mgr.copy_source_templates(source_dir)
        self.refresh()
        return n

    def _group_of(self, item: Optional[QTreeWidgetItem]) -> str:
        """item 所在组：组项取自身（剥 actions/ 前缀），叶子取父组；空白 → 空串。"""
        if item is None:
            return ""
        p = item.data(0, _PATH_ROLE)
        if not p:
            return ""
        if p.startswith("actions/"):
            return p[len("actions/"):]
        return p.rsplit("/", 1)[0] if "/" in p else ""

    def _on_context_menu(self, pos) -> None:
        item = self.itemAt(pos)
        if item is not None and not item.isSelected():
            self.setCurrentItem(item)
        context_group = self._group_of(item)
        path = self._current_path()
        is_leaf = bool(path) and not path.startswith("actions/")
        is_group = bool(path) and path.startswith("actions/")

        menu = QMenu(self)
        a_move = menu.addAction("移动到分组…")
        a_delete = menu.addAction("删除\tDel")
        menu.addSeparator()
        a_create = menu.addAction("创建组…")
        a_rename = menu.addAction("重命名组…\tF2")

        a_move.setEnabled(is_leaf and len(self.selectedItems()) == 1)
        a_delete.setEnabled(bool(self._selected_paths_top()))
        a_rename.setEnabled(is_group and len(self.selectedItems()) == 1)

        action = menu.exec_(self.viewport().mapToGlobal(pos))
        if action is a_move:
            self._act_move()
        elif action is a_delete:
            self._act_delete()
        elif action is a_create:
            self._act_create_group(context_group)
        elif action is a_rename:
            self._act_rename_group()

    def _existing_groups(self) -> List[str]:
        """包内全部组目录（递归、排序），剥 ``actions/`` 前缀。"""
        def rec(dir_path: str) -> List[str]:
            out: List[str] = []
            for n in sorted(self._package.list_dir(dir_path)):
                child = dir_path + "/" + n
                if self._package.is_dir(child):
                    out.append(child[len("actions/"):])
                    out.extend(rec(child))
            return out
        return rec("actions")

    def _act_move(self) -> None:
        path = self._current_path()
        if not path or path.startswith("actions/"):
            return
        name = path.rsplit("/", 1)[-1]
        cur_group = path.rsplit("/", 1)[0] if "/" in path else ""
        dlg = MoveStepDialog(self._existing_groups(), cur_group, self)
        if dlg.exec_() != QDialog.Accepted:
            return
        target = dlg.target()
        try:
            self._mgr.move_template(path, target)
        except ValueError as e:
            QMessageBox.warning(self, "移动到分组", "无法移动：%s" % e)
            return
        self.refresh((target + "/" + name) if target else name)

    def _act_delete(self) -> None:
        leaves = [p for p in self._selected_paths_top()
                  if not p.startswith("actions/")]
        if not leaves:
            return
        if QMessageBox.question(
                self, "删除", "确定删除 %d 项？删除的是步骤模板，不可恢复。" % len(leaves),
                QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes) != QMessageBox.Yes:
            return
        for p in leaves:
            try:
                self._mgr.remove_template(p)
            except ValueError:
                continue
        self.refresh()

    def _act_create_group(self, context_group: str = "") -> None:
        name, ok = QInputDialog.getText(self, "创建组", "组名：")
        if not ok:
            return
        name = name.strip()
        if not name or "/" in name or name in (".", ".."):
            QMessageBox.warning(self, "创建组", "名称非法")
            return
        full = (context_group + "/" + name) if context_group else name
        self._mgr.create_group(full)
        self.refresh("actions/" + full)

    def _act_rename_group(self) -> None:
        path = self._current_path()
        if not path or not path.startswith("actions/"):
            return
        group = path[len("actions/"):]
        parent = group.rsplit("/", 1)[0] if "/" in group else ""
        name = group.rsplit("/", 1)[-1]
        new_name, ok = QInputDialog.getText(self, "重命名组", "新组名：", text=name)
        if not ok:
            return
        new_name = new_name.strip()
        if not new_name or "/" in new_name or new_name in (".", ".."):
            QMessageBox.warning(self, "重命名组", "名称非法")
            return
        try:
            self._mgr.rename_group(group, new_name)
        except ValueError as e:
            QMessageBox.warning(self, "重命名组", "无法重命名：%s" % e)
            return
        new_group = (parent + "/" + new_name) if parent else new_name
        self.refresh("actions/" + new_group)


class StepInfoPanel(QStackedWidget):
    """步骤模板只读信息面板：占位 / 信息两页；数据全部来自模板类（零实例创建）。"""

    def __init__(self, mgr: StepManager,
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._mgr = mgr
        self._placeholder = QLabel("选择一个步骤模板")
        self._placeholder.setAlignment(Qt.AlignCenter)
        self._placeholder.setStyleSheet("color:#999; font-size:14px;")
        self.addWidget(self._placeholder)          # 0

        info = QWidget()
        lay = QVBoxLayout(info)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(8)
        self._name = QLabel("")
        self._name.setStyleSheet("font-size:18px; font-weight:bold;")
        self._group = QLabel("")
        self._group.setStyleSheet("color:#666;")
        self._desc = QLabel("")
        self._desc.setWordWrap(True)

        io_host = QWidget()
        io_lay = QHBoxLayout(io_host)
        io_lay.setContentsMargins(0, 0, 0, 0)
        io_lay.setSpacing(24)
        self._in_col = self._make_column("输入参数")
        self._out_col = self._make_column("输出参数")
        io_lay.addWidget(self._in_col)
        io_lay.addWidget(self._out_col)
        io_lay.addStretch()

        lay.addWidget(self._name)
        lay.addWidget(self._group)
        lay.addWidget(self._desc)
        lay.addWidget(io_host)
        lay.addStretch()
        self.addWidget(info)                        # 1

    @staticmethod
    def _make_column(title: str) -> QWidget:
        """返回带表头的纵向列容器（表头为唯一固定子项）。"""
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        t = QLabel(title)
        t.setStyleSheet("font-weight:bold; color:#555;")
        lay.addWidget(t)
        return w

    @staticmethod
    def _slot_row(name: str, vtype: str) -> QWidget:
        """单槽行：字段名（固定宽度）+ 类型（灰色）。"""
        row = QWidget()
        lay = QHBoxLayout(row)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        n = QLabel(name)
        n.setFixedWidth(96)
        lay.addWidget(n)
        t = QLabel(vtype)
        t.setStyleSheet("color:#888;")
        lay.addWidget(t)
        lay.addStretch()
        return row

    @staticmethod
    def _fill_column(column: QWidget, signature: List[List[str]]) -> None:
        """清空列（保留表头）后按签名填入 ``字段名 类型`` 行。"""
        lay = column.layout()
        assert lay is not None
        while lay.count() > 1:
            item = lay.takeAt(1)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        for name, vtype in signature:
            lay.addWidget(StepInfoPanel._slot_row(name, vtype))

    def load(self, path: str) -> None:
        """按模板路径加载信息页；未知路径抛 ValueError（调用方回占位页）。"""
        cls = self._mgr.template_class(path)
        group = path.rsplit("/", 1)[0] if "/" in path else ""
        self._name.setText(cls.name)
        self._group.setText("分组：%s" % (group or "根目录"))
        self._desc.setText(cls.description or "（无描述）")
        self._fill_column(self._in_col, cls._signature(cls.input_class))
        self._fill_column(self._out_col, cls._signature(cls.output_class))
        self.setCurrentIndex(1)

    def show_placeholder(self, text: str = "选择一个步骤模板") -> None:
        self._placeholder.setText(text)
        self.setCurrentIndex(0)


class MoveStepDialog(QDialog):
    """移动到分组：可编辑下拉框（现有组 + 可输入新组名）；确认返回目标分组。"""

    def __init__(self, groups: List[str], current_group: str = "",
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("移动到分组")
        self.resize(320, 120)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("目标分组："))
        self._combo = QComboBox()
        self._combo.setEditable(True)
        self._combo.addItem("（根目录）")
        for g in groups:
            self._combo.addItem(g)
        if current_group:
            idx = self._combo.findText(current_group)
            if idx > 0:
                self._combo.setCurrentIndex(idx)
        lay.addWidget(self._combo)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.button(QDialogButtonBox.Ok).setText("移动")
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def target(self) -> str:
        """返回目标分组（空串 = 根目录）；用户输入的新组名去空白/斜杠后返回。"""
        text = self._combo.currentText().strip().strip("/")
        if not text or text == "（根目录）":
            return ""
        return text

# ================================================================
# 冒烟演示：直接 ``python -m widgets.step_tree_widget`` 运行
# ================================================================
if __name__ == "__main__":
    import os
    import sys
    import tempfile

    from PyQt5.QtWidgets import QApplication

    from model.kscp_package import KscpPackage

    app = QApplication.instance() or QApplication(sys.argv)

    S2 = '''# -*- coding: utf-8 -*-
from dataclasses import dataclass
from actions.base import Step

@dataclass
class _In:
    count: "number" = 0
    等待: "number" = 0

@dataclass
class _Out:
    total: "number" = 0

class DemoStep(Step):
    name = "示例"
    description = "两个数字相乘"
    input_class = _In
    output_class = _Out

    def run(self) -> int:
        self.outputs.total = self.inputs.count * self.inputs.等待
        return 1
'''

    S1 = '''# -*- coding: utf-8 -*-
from dataclasses import dataclass
from actions.base import Step

@dataclass
class _In:
    ms: "number" = 0

@dataclass
class _Out:
    done: "number" = 0

class TimeDelayStep(Step):
    name = "延时"
    description = "等待指定毫秒数"
    input_class = _In
    output_class = _Out

    def run(self) -> int:
        self.outputs.done = self.inputs.ms
        return 1
'''

    pkg = KscpPackage.create_empty()
    pkg.write_file("actions/示例.py", S2.encode("utf-8"))
    pkg.write_file("actions/控制流程/延时.py", S1.encode("utf-8"))
    pkg.write_file("actions/坏语法.py", b"def broken(:\n")
    pkg.make_dir("actions/空组")

    # 空包（无 actions/）构造不崩：树自建 actions/ 目录
    empty = StepTreeWidget(KscpPackage.create_empty())
    assert empty._package.is_dir("actions")

    # 共享 mgr → 不重复 load/日志（宿主步骤列表/模板两棵树共用同一工厂，
    # 各自自建会打出两条「步骤模板加载完成」并重复加载模板）
    from model.log_model import LogModel
    shared = StepManager(pkg, VariableTree.create_empty())
    shared.load()
    LogModel.instance().clear()
    st2 = StepTreeWidget(pkg, shared)
    assert st2._mgr is shared
    assert not any("步骤模板加载完成" in e.message
                   for e in LogModel.instance().entries)

    tree = StepTreeWidget(pkg)
    # 结构：组 = 包目录（含空组），叶子 = 已注册模板；顶层 目录在上、叶子在下
    top = [tree.topLevelItem(i).text(0) for i in range(tree.topLevelItemCount())]
    assert top == ["控制流程", "空组", "示例 (2→1)"], top
    leaf = tree._find_item("示例")
    assert leaf is not None and leaf.text(0) == "示例 (2→1)"
    delay = tree._find_item("控制流程/延时")
    assert delay is not None and delay.text(0) == "延时 (1→1)"
    group = tree._find_item("actions/控制流程")
    assert group is not None
    assert not group.icon(0).isNull()                     # 组 = 文件夹图标（PyQt5 5.15 icon() 需列参）
    assert tree._find_item("actions/坏语法.py") is None   # 坏语法不显示为叶子

    # 选中叶子 → 面板信息页（名称/分组/描述/字段签名）
    pv = tree.preview_widget()
    tree.setCurrentItem(delay)
    assert pv.currentIndex() == 1
    assert pv._name.text() == "延时"
    assert "控制流程" in pv._group.text()
    assert pv._desc.text() == "等待指定毫秒数"
    # 输入左栏、输出右栏；列内容 = 表头 + 每槽一行
    assert pv._in_col.layout().count() == 2
    assert pv._out_col.layout().count() == 2
    tree.setCurrentItem(leaf)                     # 示例 2→1
    assert pv._in_col.layout().count() == 3
    assert pv._out_col.layout().count() == 2

    # 选中组 → 占位「（分组）」；未选中 → 「选择一个步骤模板」
    tree.setCurrentItem(group)
    assert pv.currentIndex() == 0 and "分组" in pv._placeholder.text()
    tree.setCurrentItem(None)
    assert pv.currentIndex() == 0

    # step_selected 信号（仅叶子）
    seen = []
    tree.step_selected.connect(seen.append)
    tree.setCurrentItem(delay)
    assert seen == ["控制流程/延时"]
    tree.setCurrentItem(group)
    assert seen == ["控制流程/延时"]               # 组不触发

    # 操作驱动 = mgr 方法 + refresh（冒烟不弹真实对话框）
    mgr = tree._mgr
    mgr.create_group("新组")
    tree.refresh()
    assert tree._find_item("actions/新组") is not None
    mgr.move_template("示例", "新组")
    tree.refresh("新组/示例")
    assert tree._current_path() == "新组/示例"
    assert pkg.is_file("actions/新组/示例.py")
    mgr.rename_group("新组", "改名组")
    tree.refresh("actions/改名组")
    assert tree._current_path() == "actions/改名组"
    assert tree._find_item("改名组/示例") is not None
    mgr.remove_template("控制流程/延时")
    tree.refresh()
    assert tree._find_item("控制流程/延时") is None
    assert tree._find_item("actions/控制流程") is None   # 组内最后一个模板被删 → 组消失

    # 移动到分组对话框：现有组列表 + 目标解析（不 exec）
    dlg = MoveStepDialog(tree._existing_groups(), "", None)
    dlg._combo.setCurrentText("改名组")
    assert dlg.target() == "改名组"
    dlg._combo.setCurrentText("（根目录）")
    assert dlg.target() == ""
    dlg._combo.setCurrentText("  新/组  ")
    assert dlg.target() == "新/组"

    # ---- import_templates：导入外部 actions 文件夹（覆盖契约；递归子目录；坏文件回滚） ----
    IMP1 = S2.replace('name = "示例"', 'name = "导入一"').replace("两个数字相乘", "导入一")
    IMP2 = S1.replace('name = "延时"', 'name = "导入二"').replace("等待指定毫秒数", "导入二")
    IMP3 = S1.replace('name = "延时"', 'name = "导入三"').replace("等待指定毫秒数", "导入三")
    tmp = tempfile.mkdtemp(prefix="kscp_import_")
    try:
        with open(os.path.join(tmp, "导入一.py"), "wb") as fh:
            fh.write(IMP1.encode("utf-8"))
        with open(os.path.join(tmp, "导入二.py"), "wb") as fh:
            fh.write(IMP2.encode("utf-8"))
        with open(os.path.join(tmp, "坏.py"), "wb") as fh:
            fh.write(b"def broken(:\n")
        sub = os.path.join(tmp, "子文件夹")
        os.mkdir(sub)
        with open(os.path.join(sub, "导入三.py"), "wb") as fh:
            fh.write(IMP3.encode("utf-8"))
        n = tree.import_templates(tmp)
        assert n == 3, n
        assert tree._find_item("导入一") is not None
        assert tree._find_item("导入二") is not None
        assert tree._find_item("子文件夹/导入三") is not None
        assert tree._find_item("actions/子文件夹") is not None
        assert not pkg.is_file("actions/坏.py")        # 坏文件回滚删除
        assert pkg.is_file("actions/导入一.py")
    finally:
        for root, dirs, files in os.walk(tmp, topdown=False):
            for f in files:
                os.remove(os.path.join(root, f))
            for d in dirs:
                os.rmdir(os.path.join(root, d))
        os.rmdir(tmp)

    print("StepTreeWidget smoke OK")
