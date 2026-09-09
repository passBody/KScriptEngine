# -*- coding: utf-8 -*-
"""
数据视图弹窗（只读表格展示所有 number/string 变量当前值）
========================================================

:class:`DataViewDialog` 为模态弹窗：用 ``QTableWidget`` 三列（变量名 / 类型 /
当前值）只读展示调用方传入的 ``number``/``string`` 变量。

筛选
----
顶部筛选栏两路并行（变量名路径正则 与 变量类型多选 取交集）：

* **变量名路径**：``QLineEdit`` 输入正则，对变量路径 ``re.search``（大小写不敏感）。
  非法正则时整框标红 + tooltip 提示，并放宽为不过滤。
* **变量类型**：``QComboBox`` 多选下拉（含「全部」），按勾选类型过滤。

列宽
----
三列均可拖拽（``Interactive``）；变量名 / 值列初始按内容自适应并保留余量，
类型列固定窄。值列仍 ``wordWrap``，长值换行不截断。只读（``NoEditTriggers``），
``Close`` 关闭。弹窗不落盘、不持 tree/package 引用（与 :class:`SettingsDialog`
同范式：调用方传纯数据）。
"""
from __future__ import annotations

import re
from typing import List, Optional, Tuple

from PyQt5.QtCore import QEvent, Qt
from PyQt5.QtWidgets import (
    QAbstractItemView, QComboBox, QDialog, QDialogButtonBox, QGridLayout,
    QHeaderView, QLabel, QLineEdit, QStyle, QStyleOptionComboBox,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from model.变量.project_variable import ProjectVariable

__all__ = ["DataViewDialog"]

# 筛选区输入框非法态样式（红框提示）
_BAD_STYLE = "QLineEdit { border:1px solid #e57373; background:#fff0f0; }"


class _CheckableComboBox(QComboBox):
    """多选下拉：点条目翻转勾选态，不切 currentIndex、不关弹层。

    标准 ``QComboBox`` 点条目会切 ``currentIndex`` 并关闭弹层、不翻转
    ``checkState``，无法做多选。这里在 popup 视图 viewport 上装事件过滤器：
    点条目时翻转该项 ``checkState`` 并吞掉 release → 不发 ``activated`` →
    不关弹层、不切 ``currentIndex``，供连续多选。点弹层外 / Esc 仍照常关闭。

    折叠态标签 = item 0 的 text（``currentIndex`` 恒 0），由外部
    :meth:`DataViewDialog._sync_combo_text` 动态改写为「全部 / 已选 N 项 /
    （未选）」。勾选态翻转经 ``model().itemChanged`` 触发外部联动。
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        # popup 视图 viewport 装事件过滤器，点条目翻转勾选、吞 release
        view = self.view()
        if view is not None and view.viewport() is not None:
            view.viewport().installEventFilter(self)

    def eventFilter(self, obj, event):  # noqa: N802 (Qt 命名)
        if event.type() == QEvent.MouseButtonRelease:
            view = self.view()
            if view is not None and obj is view.viewport():
                idx = view.indexAt(event.pos())
                if idx.isValid():
                    it = self.model().item(idx.row(), idx.column())
                    if it is not None:
                        it.setCheckState(
                            Qt.Unchecked if it.checkState() == Qt.Checked
                            else Qt.Checked)
                return True   # 吞 release → 不发 activated → 不关弹层
        return super().eventFilter(obj, event)


class DataViewDialog(QDialog):
    """数据视图：只读表格展示所有 number/string 变量的当前值。

    列：变量名（path）| 类型 | 当前值。三列均可拖拽调宽（``Interactive``），
    变量名 / 值列初始按内容自适应，值列 ``wordWrap`` 长值换行。只读
    （``NoEditTriggers``）。顶部筛选：正则匹配变量名路径 + 多选变量类型。
    ``Close`` 按钮关闭。
    """

    def __init__(self, items: List[Tuple[str, ProjectVariable]],
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("数据视图")
        self.resize(720, 460)
        self.setMinimumWidth(560)              # 比 SettingsDialog(420) 宽，值列有空间

        # 缓存原始条目（筛选在内存里反复，不重新取数）
        self._all_items: List[Tuple[str, ProjectVariable]] = list(items)
        # _sync_combo_text 改 item0 文本时设此守卫，防 _on_type_check_changed
        # 把 setText 触发的 itemChanged 当作勾选态变化重入处理
        self._syncing: bool = False

        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(8)

        hint = QLabel("展示所有数值 / 字符串变量的当前值（只读）。改值请在左侧「变量」树编辑。")
        hint.setStyleSheet("color:#666; font-size:12px;")
        hint.setWordWrap(True)
        lay.addWidget(hint)

        lay.addWidget(self._build_filter())

        self._table = QTableWidget(0, 3)
        self._table.setHorizontalHeaderLabels(["变量名", "类型", "当前值"])
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)   # 只读
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setWordWrap(True)
        self._table.verticalHeader().setVisible(False)
        self._table.verticalHeader().setDefaultSectionSize(28)
        self._table.horizontalHeader().setMinimumSectionSize(80)
        # 列宽策略：三列均可拖拽（Interactive）。变量名/值列初始按内容自适应，
        # 类型列固定窄；拖拽后用户调整保留（Interactive 不被 ResizeToContents 覆盖）。
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.resizeSection(1, 80)
        self._table.setStyleSheet(
            "QTableWidget { gridline-color:#e0e0e0; }"
            "QHeaderView::section { background:#f0f0f0; padding:6px; border:none;"
            " border-bottom:1px solid #ddd; font-weight:bold; }")
        lay.addWidget(self._table)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

        self._fill(self._all_items)
        # 初始列宽需在表格已进布局、有可视宽度后算；首次 show 后再校准一次
        self._auto_size_name_value_columns()

    # ----------------------------------------------------------------
    # 筛选区
    # ----------------------------------------------------------------
    def _build_filter(self) -> QWidget:
        """构建筛选栏：正则变量名 + 多选类型下拉。"""
        bar = QWidget()
        grid = QGridLayout(bar)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(4)

        name_lbl = QLabel("变量名（正则）:")
        name_lbl.setStyleSheet("color:#555;")
        grid.addWidget(name_lbl, 0, 0)

        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("输入正则匹配变量名路径，留空显示全部")
        self._name_edit.setClearButtonEnabled(True)
        self._name_edit.textChanged.connect(self._apply_filter)
        grid.addWidget(self._name_edit, 0, 1)

        type_lbl = QLabel("类型:")
        type_lbl.setStyleSheet("color:#555;")
        grid.addWidget(type_lbl, 1, 0)

        # 多选类型下拉：_CheckableComboBox 内嵌勾选框，点条目翻转勾选、
        # 弹层保持打开供连续多选。「全部」勾选 = 不过滤类型；其余按勾选交集。
        self._type_combo = _CheckableComboBox()
        self._type_items: List[str] = sorted({
            var.type for _path, var in self._all_items
        })
        self._type_combo.addItem("全部")
        for t in self._type_items:
            self._type_combo.addItem(t)
        model = self._type_combo.model()
        for i in range(model.rowCount()):
            it = model.item(i)
            if it is not None:
                it.setCheckState(Qt.Checked if i == 0 else Qt.Unchecked)
        # 勾选态翻转（含 _CheckableComboBox 点选触发的）→ 联动 + 过滤 + 刷新显示
        model.itemChanged.connect(self._on_type_check_changed)
        grid.addWidget(self._type_combo, 1, 1)
        self._sync_combo_text()

        grid.setColumnStretch(1, 1)
        return bar

    def _on_type_check_changed(self, item) -> None:
        """勾选框变化：「全部」联动全选/全不选；其余勾选则更新「全部」态。

        ``_CheckableComboBox`` 点选翻转 checkState、或程序性 ``setCheckState``
        都经 ``model.itemChanged`` 进此。阻断 **model** 信号（而非 combo 信号）：
        联动设其余项 checkState 时不再递归 itemChanged。``_syncing`` 守卫忽略
        ``_sync_combo_text`` 改 item0 文本触发的 itemChanged（非勾选态变化）。
        """
        if self._syncing:
            return
        model = self._type_combo.model()
        all_item = model.item(0)
        model.blockSignals(True)
        try:
            if item is all_item:
                state = item.checkState()
                for i in range(1, model.rowCount()):
                    it = model.item(i)
                    if it is not None:
                        it.setCheckState(state)
            elif all_item is not None:
                rest_checked = all(
                    model.item(i) is not None
                    and model.item(i).checkState() == Qt.Checked
                    for i in range(1, model.rowCount()))
                all_item.setCheckState(Qt.Checked if rest_checked
                                       else Qt.Unchecked)
        finally:
            model.blockSignals(False)
        self._sync_combo_text()
        self._apply_filter()

    def _sync_combo_text(self) -> None:
        """刷新「全部」行（item 0）的显示文本：全部 / 已选 N 项 / （未选）。

        item 0 是 ``currentIndex``（折叠态标签来源）。``setText`` 会发 itemChanged，
        用 ``_syncing`` 守卫让 ``_on_type_check_changed`` 跳过这次（非勾选态变化）。
        """
        n = len(self._selected_types())
        total = len(self._type_items)
        if n == total:
            text = "全部"
        elif n == 0:
            text = "（未选）"
        else:
            text = "已选 %d 项" % n
        self._syncing = True
        try:
            it = self._type_combo.model().item(0)
            if it is not None:
                it.setText(text)
        finally:
            self._syncing = False

    def _selected_types(self) -> List[str]:
        """当前勾选的类型列表（不含「全部」）；「全部」勾选 → 返回全部类型。"""
        model = self._type_combo.model()
        all_item = model.item(0)
        if all_item is not None and all_item.checkState() == Qt.Checked:
            return list(self._type_items)
        out: List[str] = []
        for i in range(1, model.rowCount()):
            it = model.item(i)
            if it is not None and it.checkState() == Qt.Checked:
                out.append(it.text())
        return out

    def _apply_filter(self, *_args) -> None:
        """按正则变量名 + 勾选类型过滤，重填表格。非法正则放宽为不过滤并标红。

        类型语义：「全部」勾选 → 不过滤类型；否则按勾选类型交集过滤
        （一个都没勾则结果为空，与「全部」明确区分）。
        """
        raw = self._name_edit.text()
        pattern: Optional["re.Pattern[str]"] = None
        if raw.strip():
            try:
                pattern = re.compile(raw, re.IGNORECASE)
                self._name_edit.setStyleSheet("")
                self._name_edit.setToolTip("")
            except re.error as e:
                self._name_edit.setStyleSheet(_BAD_STYLE)
                self._name_edit.setToolTip("正则非法：%s（已忽略名称筛选）" % e)
        # 类型：全部勾选 → 不过滤；否则按勾选集合（可能为空 → 匹配无）
        model = self._type_combo.model()
        all_item = model.item(0)
        type_all = all_item is not None and all_item.checkState() == Qt.Checked
        types: Optional[set] = None if type_all else set(self._selected_types())
        kept: List[Tuple[str, ProjectVariable]] = []
        for path, var in self._all_items:
            if types is not None and var.type not in types:
                continue
            if pattern is not None and not pattern.search(path):
                continue
            kept.append((path, var))
        self._fill(kept)
        self._auto_size_name_value_columns()

    # ----------------------------------------------------------------
    # 填表
    # ----------------------------------------------------------------
    def _fill(self, items: List[Tuple[str, ProjectVariable]]) -> None:
        """填表：变量名 / 类型 / 当前值（空值占位「（空）」）。"""
        self._table.setRowCount(len(items))
        for row, (path, var) in enumerate(items):
            name_item = QTableWidgetItem(path)
            name_item.setTextAlignment(Qt.AlignVCenter | Qt.AlignLeft)
            type_item = QTableWidgetItem(var.type)
            type_item.setTextAlignment(Qt.AlignVCenter | Qt.AlignCenter)
            data = var.data
            text = "（空）" if data == "" or data is None else str(data)
            val_item = QTableWidgetItem(text)
            val_item.setTextAlignment(Qt.AlignVCenter | Qt.AlignLeft)
            self._table.setItem(row, 0, name_item)
            self._table.setItem(row, 1, type_item)
            self._table.setItem(row, 2, val_item)
        self._table.resizeRowsToContents()    # wordWrap 下长值行自适应高

    def _auto_size_name_value_columns(self) -> None:
        """变量名/值列按内容自适应宽（保留余量），且不挤没类型列。

        ``Interactive`` 模式下 ``resizeColumnsToContents`` 按内容收紧；再加 24px
        余量防贴边，并钳到 [80, 可视宽一半] 防类型/值列被挤没。类型列保持 80px
        （已在 __init__ 设定，此方法不动它）。仅当有数据时才调。
        """
        if not self._all_items:
            return
        self._table.resizeColumnsToContents()
        header = self._table.horizontalHeader()
        vw = max(self._table.viewport().width(), self._table.width() - 30)
        for col in (0, 2):
            w = header.sectionSize(col) + 24
            w = max(80, min(w, max(120, vw // 2)))
            header.resizeSection(col, w)

    # ----------------------------------------------------------------
    def showEvent(self, event) -> None:  # noqa: N802 (Qt 命名)
        """首次显示后可视宽已知，校准一次列宽（构造期 viewport 宽尚不可靠）。"""
        super().showEvent(event)
        self._auto_size_name_value_columns()


# ================================================================
# 冒烟演示：直接 ``python -m widgets.通用.data_view_dialog`` 运行
# ================================================================
if __name__ == "__main__":
    import sys

    from PyQt5.QtWidgets import QApplication

    from model.工程.kscp_package import KscpPackage
    from model.变量.project_variable import ProjectVariable
    from model.变量.variable_tree import VariableTree

    app = QApplication.instance() or QApplication(sys.argv)

    pkg = KscpPackage.create_empty()
    tree = VariableTree.create_empty()
    tree.add("n1", ProjectVariable.create("number", 100, pkg))
    tree.add("s1", ProjectVariable.create("string", "hello", pkg))
    tree.add("long", ProjectVariable.create("string", "X" * 200, pkg))   # 超长值
    tree.add("empty", ProjectVariable.create("string", "", pkg))         # 空值
    tree.add("img", ProjectVariable.create("image", "assets/x.png", pkg))  # 应被滤掉
    tree.add("组1/n2", ProjectVariable.create("number", 3.14, pkg))
    tree.add("组1/s2", ProjectVariable.create("string", "world", pkg))

    items = tree.filter_by_types("number", "string").items()
    # image 被滤掉：7 个里剩 6 个（n1/s1/long/empty/组1-n2/组1-s2）
    assert len(items) == 6, len(items)

    dlg = DataViewDialog(items)
    assert dlg.windowTitle() == "数据视图"
    assert dlg.minimumWidth() >= 560, dlg.minimumWidth()
    assert dlg._table.columnCount() == 3
    assert [dlg._table.horizontalHeaderItem(i).text() for i in range(3)] == \
           ["变量名", "类型", "当前值"]
    assert dlg._table.rowCount() == 6
    assert dlg._table.editTriggers() == QAbstractItemView.NoEditTriggers

    # 三列均可拖拽（Interactive）
    hm = dlg._table.horizontalHeader()
    for col in range(3):
        assert hm.sectionResizeMode(col) == QHeaderView.Interactive, col

    cell = lambda r, c: dlg._table.item(r, c).text()   # noqa: E731
    texts = {cell(r, 0): cell(r, 2) for r in range(6)}
    assert texts["n1"] == "100"
    assert texts["s1"] == "hello"
    assert texts["long"] == "X" * 200
    assert texts["empty"] == "（空）"
    assert texts["组1/n2"] == "3.14"
    types = {cell(r, 0): cell(r, 1) for r in range(6)}
    assert types["n1"] == "number" and types["s1"] == "string"

    # 超长值行高 >= 普通行高（wordWrap 自适应）
    rows_by_name = {cell(r, 0): r for r in range(6)}
    h_long = dlg._table.rowHeight(rows_by_name["long"])
    h_short = dlg._table.rowHeight(rows_by_name["n1"])
    assert h_long >= h_short, (h_long, h_short)

    # ---- 筛选：正则变量名（re.search 路径，大小写不敏感）----
    dlg._name_edit.setText("组1")
    assert dlg._table.rowCount() == 2, dlg._table.rowCount()
    assert {cell(r, 0) for r in range(dlg._table.rowCount())} == \
           {"组1/n2", "组1/s2"}
    dlg._name_edit.setText("")
    assert dlg._table.rowCount() == 6

    # 路径以 n+数字 结尾（n1 / 组1/n2；排除 s1 / 组1/s2 也以数字结尾）
    dlg._name_edit.setText(r"n\d+$")
    assert {cell(r, 0) for r in range(dlg._table.rowCount())} == \
           {"n1", "组1/n2"}
    dlg._name_edit.setText("")

    # ---- 筛选：类型多选 ----
    # 默认「全部」勾选 → 6 行
    assert dlg._table.rowCount() == 6
    model = dlg._type_combo.model()
    # 取消「全部」→ 0 行（无类型勾选）
    model.item(0).setCheckState(Qt.Unchecked)
    assert dlg._table.rowCount() == 0, dlg._table.rowCount()
    # 类型条目顺序 = sorted({types})：number 在 string 前
    model.item(1).setCheckState(Qt.Checked)   # number
    assert {cell(r, 0) for r in range(dlg._table.rowCount())} == \
           {"n1", "组1/n2"}
    # 勾「全部」→ 联动全选恢复 6 行
    model.item(0).setCheckState(Qt.Checked)
    assert dlg._table.rowCount() == 6

    # ---- 真实点选路径（_CheckableComboBox 事件过滤器）：点类型条目翻转勾选 ----
    # 回归覆盖：此前标准 QComboBox 点条目只切 currentIndex、不翻转 checkState，
    # 类型筛失效（用户报告「类型无法筛选，只能是全部」）。
    from PyQt5.QtCore import QPoint
    from PyQt5.QtGui import QMouseEvent

    combo = dlg._type_combo
    view = combo.view()
    vp = view.viewport()
    label = lambda: combo.model().item(0).text()   # noqa: E731 (折叠态标签=item0 文本)
    # 先清成已知态：全部未勾（联动清空所有）→ 0 行、显示「（未选）」
    model.item(0).setCheckState(Qt.Unchecked)
    assert dlg._table.rowCount() == 0
    assert label() == "（未选）", label()
    # 点「number」(item 1)：未勾 → 勾选；「全部」仍不勾（非全选）
    idx_num = combo.model().index(1, 0)
    view.indexAt = lambda _pos: idx_num   # type: ignore[method-assign]
    ev = QMouseEvent(QEvent.MouseButtonRelease, QPoint(0, 0),
                     Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
    assert combo.eventFilter(vp, ev) is True        # 吞 release → 不关弹层
    assert combo.model().item(1).checkState() == Qt.Checked
    assert combo.model().item(0).checkState() == Qt.Unchecked   # 非全选
    assert label() == "已选 1 项", label()
    assert {cell(r, 0) for r in range(dlg._table.rowCount())} == {"n1", "组1/n2"}
    # 再点「number」→ 翻回未勾；无类型勾选 → 0 行、显示「（未选）」
    assert combo.eventFilter(vp, ev) is True
    assert combo.model().item(1).checkState() == Qt.Unchecked
    assert label() == "（未选）", label()
    assert dlg._table.rowCount() == 0
    # 点「全部」(item 0) → 联动全勾、6 行、显示「全部」
    idx_all = combo.model().index(0, 0)
    view.indexAt = lambda _pos: idx_all   # type: ignore[method-assign]
    assert combo.eventFilter(vp, ev) is True
    assert combo.model().item(0).checkState() == Qt.Checked
    assert combo.model().item(1).checkState() == Qt.Checked   # 联动勾上
    assert label() == "全部", label()
    assert dlg._table.rowCount() == 6

    # ---- 筛选：非法正则放宽为不过滤 + 标红 ----
    dlg._name_edit.setText("(unclosed")
    assert dlg._table.rowCount() == 6          # 非法 → 不过滤
    assert "e57373" in dlg._name_edit.styleSheet()   # 红框
    assert "正则非法" in (dlg._name_edit.toolTip() or "")
    dlg._name_edit.setText("")

    # ---- 正则 + 类型 组合（交集）----
    dlg._name_edit.setText("s")                # 路径含 s：s1 / 组1/s2
    assert {cell(r, 0) for r in range(dlg._table.rowCount())} == \
           {"s1", "组1/s2"}
    model.item(0).setCheckState(Qt.Unchecked)
    model.item(2).setCheckState(Qt.Checked)     # 仅 string
    assert {cell(r, 0) for r in range(dlg._table.rowCount())} == \
           {"s1", "组1/s2"}
    model.item(0).setCheckState(Qt.Checked)     # 恢复全部
    dlg._name_edit.setText("")

    # ---- 列宽可拖拽（Interactive 下 resizeSection 生效且不被覆盖）----
    hm.resizeSection(0, 300)
    assert hm.sectionSize(0) == 300
    hm.resizeSection(2, 400)
    assert hm.sectionSize(2) == 400

    # 空列表不崩
    empty_dlg = DataViewDialog([])
    assert empty_dlg._table.rowCount() == 0

    print("DataViewDialog smoke OK")
