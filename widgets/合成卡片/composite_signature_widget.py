# -*- coding: utf-8 -*-
"""
合成卡片签名编辑器（输入/输出/局部 三段表）
==========================================

:class:`CompositeSignatureWidget` 是一个 QWidget：三段表（输入/输出/局部），
每行 名 / 类型(下拉 supported_types) / 局部多 默认值。编辑产生**合法**签名时发
:attr:`signature_changed`；非法态不发（不落盘非法）。

注意：QTableWidgetItem 不是 QObject，无 textChanged 信号。单元格文本变更经
QTableWidget.cellChanged(row, col) 统一捕获（每段表连接一次）；类型下拉(QComboBox)
变更经 currentTextChanged 单独连（cellWidget 变更不触发 cellChanged）。
"""
from typing import Optional

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QPushButton, QStyledItemDelegate, QTabWidget, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from model.合成卡片.composite_signature import CompositeSignature, LocalVar, Param
from model.变量.project_variable import ProjectVariable

__all__ = ["CompositeSignatureDialog", "CompositeSignatureWidget"]


class _CenteredTextDelegate(QStyledItemDelegate):
    """名列文本居中委托：编辑期弹出的 QLineEdit 设居中（显示态由 setTextAlignment）。

    ``QTableWidgetItem.setTextAlignment`` 只管非编辑态显示；双击编辑时 Qt 默认建
    QLineEdit（居左）——故 :meth:`createEditor` 把编辑框也对齐居中，满足「名编辑
    居中」。类型列是 QComboBox（单元格控件），其居中经可编辑 line edit 单独处理
    （见 :meth:`_Section._add_row`）。
    """

    def createEditor(self, parent, option, index):  # noqa: ANN001 (Qt 签名)
        editor = super().createEditor(parent, option, index)
        if isinstance(editor, QLineEdit):
            editor.setAlignment(Qt.AlignCenter)
        return editor


class _Section(QWidget):
    """一段表（输入/输出/局部）：QTableWidget + 增删行。"""

    def __init__(self, title: str, with_default: bool, parent: QWidget,
                 titled: bool = True) -> None:
        super().__init__(parent)
        self._with_default = with_default
        self._on_changed = None   # 宿主注入的变更回调
        self._muting = False      # _add_row 构造期静音 cellChanged/currentTextChanged
        cols = ["名", "类型"] + (["默认值"] if with_default else [])
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(4)
        head = QHBoxLayout()
        if titled:
            head.addWidget(QLabel(title))
        head.addStretch(1)
        b_add = QPushButton("+")
        b_add.setFixedWidth(32)
        b_rem = QPushButton("−")
        b_rem.setFixedWidth(32)
        head.addWidget(b_rem)
        head.addWidget(b_add)
        lay.addLayout(head)
        self._tw = QTableWidget(0, len(cols))
        self._tw.setHorizontalHeaderLabels(cols)
        vh = self._tw.verticalHeader()
        if vh is not None:
            vh.setVisible(False)
            vh.setDefaultSectionSize(40)     # 行高加大（用户反馈操作空间狭挤）
        h = self._tw.horizontalHeader()
        if h is not None:
            h.setSectionResizeMode(QHeaderView.Stretch)
            h.setMinimumSectionSize(96)
            if with_default:
                self._tw.setColumnWidth(0, 160)
                self._tw.setColumnWidth(1, 120)
                self._tw.setColumnWidth(2, 120)
            else:
                self._tw.setColumnWidth(0, 180)
                self._tw.setColumnWidth(1, 140)
        self._tw.setMinimumHeight(240)       # 每段表足够高，避免滚动条过挤
        # 名列编辑居中：委托把编辑期 QLineEdit 设居中（显示态经 setTextAlignment）
        self._tw.setItemDelegateForColumn(0, _CenteredTextDelegate(self._tw))
        if with_default:
            # 局部段「默认值」列编辑居中（显示态经 setTextAlignment）
            self._tw.setItemDelegateForColumn(2, _CenteredTextDelegate(self._tw))
        self._types = ProjectVariable.supported_types()
        lay.addWidget(self._tw)
        # QTableWidgetItem 不是 QObject、无 textChanged；用 cellChanged 统一捕获文本变更。
        self._tw.cellChanged.connect(self._notify)
        b_add.clicked.connect(lambda: self._add_row(""))
        b_rem.clicked.connect(self._remove_selected)

    def set_on_changed(self, cb) -> None:
        self._on_changed = cb

    def _add_row(self, name: str = "", vtype: str = "", default: str = "") -> None:
        self._muting = True
        try:
            r = self._tw.rowCount()
            self._tw.insertRow(r)
            name_item = QTableWidgetItem(name)
            name_item.setTextAlignment(Qt.AlignCenter)   # 名列显示居中（编辑经委托居中）
            self._tw.setItem(r, 0, name_item)
            combo = QComboBox()
            combo.setEditable(True)                       # 开可编辑 → line edit 存在
            le = combo.lineEdit()
            if le is not None:
                le.setAlignment(Qt.AlignCenter)           # 类型显示居中
                le.setReadOnly(True)                      # 禁手输（类型只能下拉选，防非法串）
            for t in self._types:
                combo.addItem(t)
            if vtype in self._types:
                combo.setCurrentText(vtype)
            self._tw.setCellWidget(r, 1, combo)
            if self._with_default:
                d_item = QTableWidgetItem(default)
                d_item.setTextAlignment(Qt.AlignCenter)   # 默认值列显示居中（编辑经委托居中）
                self._tw.setItem(r, 2, d_item)
            # 类型下拉变更单独连（cellWidget 变更不触发 cellChanged）
            combo.currentTextChanged.connect(self._notify)
        finally:
            self._muting = False
        self._notify()   # 构造期 cellChanged 已被 _muting 静音；此处恰好发一次

    def _remove_selected(self) -> None:
        r = self._tw.currentRow()
        if r >= 0:
            self._tw.removeRow(r)
            self._notify()

    def _notify(self, *_a) -> None:
        if self._muting:
            return
        if self._on_changed is not None:
            self._on_changed()

    def load(self, items) -> None:
        """items: List[Param] 或 List[LocalVar]。"""
        self._tw.setRowCount(0)
        for it in items:
            default = getattr(it, "default", "")
            self._add_row(it.name, it.type,
                          "" if default is None else str(default))

    def collect(self):
        """返回 (List[Param] 或 List[LocalVar], ok: bool)。ok=False 表示有非法行。

        非法行（空名/空类型）不进 out —— 供 current_signature() 丢弃非法行；
        _maybe_emit 仅在 ok=True 时用 out 建签（此时无非法行可丢）。
        """
        out = []
        ok = True
        for r in range(self._tw.rowCount()):
            name_item = self._tw.item(r, 0)
            name = name_item.text().strip() if name_item is not None else ""
            combo = self._tw.cellWidget(r, 1)
            vtype = combo.currentText() if combo is not None else ""
            if not name or not vtype:
                ok = False
                continue            # 丢弃非法行
            if self._with_default:
                d_item = self._tw.item(r, 2)
                default_txt = d_item.text() if d_item is not None else ""
                default = _coerce_default(vtype, default_txt)
                out.append(LocalVar(name, vtype, default))
            else:
                out.append(Param(name, vtype))
        return out, ok


def _coerce_default(vtype: str, text: str):
    text = text.strip()
    if vtype == "number":
        try:
            return int(text) if text else 0
        except ValueError:
            try:
                return float(text)
            except ValueError:
                return 0
    return text


class CompositeSignatureWidget(QWidget):
    """三段签名编辑器：输入/输出/局部，互不兼任。"""

    signature_changed = pyqtSignal(CompositeSignature)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._loading = False
        self._in = _Section("输入", False, self, titled=False)
        self._out = _Section("输出", False, self, titled=False)
        self._loc = _Section("局部", True, self, titled=False)
        self._in.set_on_changed(self._maybe_emit)
        self._out.set_on_changed(self._maybe_emit)
        self._loc.set_on_changed(self._maybe_emit)
        # 三段切换：输入/输出/局部 各一标签页（点击查看，避免竖状堆叠拥挤）
        self._tabs = QTabWidget(self)
        self._tabs.addTab(self._in, "输入")
        self._tabs.addTab(self._out, "输出")
        self._tabs.addTab(self._loc, "局部")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(4)
        lay.addWidget(self._tabs)
        lay.addStretch(1)

    def set_signature(self, sig: CompositeSignature) -> None:
        self._loading = True
        try:
            self._in.load(sig.inputs)
            self._out.load(sig.outputs)
            self._loc.load(sig.locals)
        finally:
            self._loading = False

    def _maybe_emit(self, *_a) -> None:
        if self._loading:
            return
        ins, ok1 = self._in.collect()
        outs, ok2 = self._out.collect()
        locs, ok3 = self._loc.collect()
        if not (ok1 and ok2 and ok3):
            return                  # 有非法行 → 不发
        sig = CompositeSignature(inputs=ins, outputs=outs, locals=locs)
        try:
            sig.validate()          # 跨段重名/类型未注册 → 不发
        except ValueError:
            return
        self.signature_changed.emit(sig)

    def current_signature(self) -> CompositeSignature:
        """当前（可能非法）签名；非法行被丢弃。供宿主读取当前态。"""
        ins, _ = self._in.collect()
        outs, _ = self._out.collect()
        locs, _ = self._loc.collect()
        return CompositeSignature(inputs=ins, outputs=outs, locals=locs)


class CompositeSignatureDialog(QDialog):
    """签名编辑弹窗：内嵌 :class:`CompositeSignatureWidget` + 确定/取消。

    取代预览栏内联签名表——把输入/输出/局部三段**整合**到一个弹窗里编辑。
    打开时 :meth:`set_signature` 静默载入；用户在弹窗内增删行（``+``/``−``）、
    重命名（单元格编辑）、改类型/默认值；**右下角「确定」生效**——调用方读取
    :meth:`signature`（合法子集，非法行被 collect 丢弃）后落盘；取消则丢弃。

    ``CompositeSignatureWidget`` 的实时 ``signature_changed`` 信号仅用于消除红字
    提示（签名变合法即清除）；编辑不直达宿主，仅确定时一次性提交。**确定时**
    :meth:`_validate` 校验签名（重名/非法字符/未注册类型 → 红字提示并阻止
    accept），避免非法签名流入 :func:`build_validation_tree` 触发
    ``FileExistsError``（修重名崩溃）。
    """

    def __init__(self, sig: CompositeSignature,
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("编辑签名")
        # 操作空间充裕（用户反馈：原自动尺寸狭挤、UI 显示不全）
        self.resize(640, 540)
        self.setMinimumSize(560, 480)
        # 字体放大 + 控件圆角（用户反馈：原默认字体偏小、控件无圆角）。
        # 注：dialog 一旦设 QSS，setFont 的字体不再向子控件传播（QSS 引擎接管、
        # 非规则子控件回退应用默认字体），故字体须在 QSS 用显式选择器逐类型设
        # font-size（QPushButton/QComboBox/QTableWidget/QLabel/QTabBar…）。
        self.setStyleSheet(
            "QDialog, QLabel, QTabBar, QTableWidget, QTableWidget::item,"
            " QComboBox, QPushButton, QLineEdit { font-family: \"SimSun\"; font-size: 13pt; }"
            "QPushButton { border: 1px solid #c4c4c4; border-radius: 6px;"
            " padding: 4px 12px; background: #fafafa; }"
            "QPushButton:hover { background: #eef2f7; border-color: #9bb8d6; }"
            "QPushButton:pressed { background: #e1ecf4; }"
            "QPushButton:disabled { color: #a0a0a0; background: #f5f5f5;"
            " border-color: #d8d8d8; }"
            "QComboBox { border: 1px solid #c4c4c4; border-radius: 6px;"
            " padding: 2px 6px; background: #fafafa; }"
            "QTabWidget::pane { border: 1px solid #d0d0d0; border-radius: 6px; }")
        self._sig_widget = CompositeSignatureWidget(self)
        self._sig_widget.set_signature(sig)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(8)
        lay.addWidget(self._sig_widget)
        # 红字错误提示：确定时校验失败 → 显示；签名变合法 → 消除
        self._error_label = QLabel(self)
        self._error_label.setStyleSheet(
            "QLabel { color: #c8564c; background: #fbeae7;"
            " border: 1px solid #e3b3ac; border-radius: 4px;"
            " padding: 4px 6px; }")
        self._error_label.hide()
        lay.addWidget(self._error_label)
        # 右下角确定/取消（QDialogButtonBox 默认右对齐）
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self._on_ok)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)
        # 签名变合法（signature_changed 仅在合法时发）→ 消除红字
        self._sig_widget.signature_changed.connect(self._clear_error)

    def _validate(self) -> Optional[str]:
        """当前签名是否合法：合法返回 None，非法返回错误信息。

        ``current_signature`` 丢弃空名/空类型行；重名/非法字符/未注册类型 →
        :meth:`CompositeSignature.validate` 抛 ValueError → 返回其信息。
        """
        sig = self._sig_widget.current_signature()
        try:
            sig.validate()
        except ValueError as ex:
            return str(ex)
        return None

    def _on_ok(self) -> None:
        """确定：校验签名；非法 → 红字提示并阻止 accept，合法 → accept。"""
        err = self._validate()
        if err is not None:
            self._error_label.setText(err)
            self._error_label.show()
            return
        self._clear_error()
        self.accept()

    def _clear_error(self, *_a) -> None:
        """消除红字：签名变合法（signature_changed）或成功 accept 时调用。"""
        self._error_label.setText("")
        self._error_label.hide()

    def signature(self) -> CompositeSignature:
        """确定后由调用方读取：当前（合法子集）签名。"""
        return self._sig_widget.current_signature()


# ================================================================
# 冒烟演示：直接 ``python -m widgets.合成卡片.composite_signature_widget`` 运行
# ================================================================
if __name__ == "__main__":
    import sys
    from PyQt5.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(sys.argv)

    w = CompositeSignatureWidget()
    received = []
    w.signature_changed.connect(lambda s: received.append(s))

    sig = CompositeSignature(inputs=[Param("x", "number")],
                             outputs=[Param("y", "number")],
                             locals=[LocalVar("t", "number", 0)])
    w.set_signature(sig)
    assert w._in._tw.rowCount() == 1
    assert w._out._tw.rowCount() == 1
    assert w._loc._tw.rowCount() == 1
    # set_signature 在 _loading 守卫内 → 不发
    assert received == []

    # 用户编辑：加一行输入 → 发合法签名
    w._in._add_row("a", "string")
    assert len(received) >= 1
    last = received[-1]
    assert last.input_names() == ["x", "a"] and last.output_names() == ["y"]
    # 名/类型列居中：名 QTableWidgetItem 显示居中，类型 QComboBox 经可编辑只读
    # line edit 居中显示（编辑居中由 _CenteredTextDelegate 把编辑框设居中保证）
    _n = w._in._tw.item(1, 0)
    assert int(_n.textAlignment()) == int(Qt.AlignCenter)
    _c = w._in._tw.cellWidget(1, 1)
    assert _c.isEditable() and _c.lineEdit().isReadOnly()
    assert int(_c.lineEdit().alignment()) == int(Qt.AlignCenter)
    # 非法行（空名）→ 不发
    n0 = len(received)
    w._in._add_row("", "number")   # 空名 → collect ok=False → 不发
    assert len(received) == n0
    # req 7: current_signature 丢弃非法行（空名行不入 input_names）
    assert "" not in w.current_signature().input_names()
    # 删空行 → 恢复合法 [x, a] → 发
    w._in._tw.setCurrentCell(2, 0)
    w._in._remove_selected()
    assert received[-1].input_names() == ["x", "a"]
    # 删 a 行 → 签名缩减 [x] → 发
    w._in._tw.setCurrentCell(1, 0)
    w._in._remove_selected()
    assert received[-1].input_names() == ["x"]

    # req 8: 局部加合法行恰好发一次（构造期 cellChanged 被 _muting 静音）
    n2 = len(received)
    w._loc._add_row("z", "number", "0")   # 局部 z，无跨段重名
    assert len(received) == n2 + 1, received[n2:]

    # 跨段重名 → validate 失败 → 不发
    n1 = len(received)
    w._loc._add_row("x", "number", "0")   # x 与输入 x 重名
    assert len(received) == n1, received[n1:]
    # current_signature：读当前态（非法行丢弃）
    cur = w.current_signature()
    assert "x" in cur.input_names()

    # ---- CompositeSignatureDialog：弹窗载入 + 内嵌编辑 + signature() 读取 ----
    # 不调 exec_（模态会阻塞）：直接构造 + 操控内嵌 widget + 读 signature()。
    dlg = CompositeSignatureDialog(sig)
    # 操作空间充裕（用户反馈原自动尺寸狭挤）：最小 560×480
    assert dlg.minimumWidth() >= 560 and dlg.minimumHeight() >= 480
    assert dlg._sig_widget._in._tw.rowCount() == 1     # 载入：输入段 1 行（x）
    assert dlg._sig_widget._out._tw.rowCount() == 1    # 输出段 1 行（y）
    assert dlg._sig_widget._loc._tw.rowCount() == 1    # 局部段 1 行（t）
    # 弹窗内编辑：加输入 a → signature() 读到 [x, a]（确定时提交的就是这个）
    dlg._sig_widget._in._add_row("a", "string")
    assert dlg.signature().input_names() == ["x", "a"]
    # 非法行（空名）→ signature() 丢弃
    dlg._sig_widget._in._add_row("", "number")
    assert dlg.signature().input_names() == ["x", "a"]
    # 删行 → signature() 反映
    dlg._sig_widget._in._tw.setCurrentCell(1, 0)   # 删 a 行
    dlg._sig_widget._in._remove_selected()
    assert dlg.signature().input_names() == ["x"]

    # ---- Fix：弹窗确定时校验签名，重名/非法 → 阻止 + 红字，修正后红字消除 ----
    # 复现：输入段加同名参数 x → _validate 判非法 → _on_ok 阻止 accept + 红字
    dlg2 = CompositeSignatureDialog(
        CompositeSignature(inputs=[Param("x", "number")],
                            outputs=[Param("y", "number")],
                            locals=[LocalVar("t", "number", 0)]))
    assert dlg2._validate() is None                  # 初始合法
    dlg2._sig_widget._in._add_row("x", "number")    # 同名输入 x → 重名
    err = dlg2._validate()
    assert err is not None and "x" in err            # 判非法（含重名 x）
    dlg2._on_ok()                                    # 阻止 accept + 设红字
    assert dlg2.result() != QDialog.Accepted        # 未 accept（仍 Rejected）
    assert dlg2._error_label.text() and "x" in dlg2._error_label.text()
    # 修正：改名 x→a → signature_changed → 红字消除
    dlg2._sig_widget._in._tw.item(1, 0).setText("a")
    assert dlg2._error_label.text() == ""            # 红字已消除
    dlg2._on_ok()                                    # 合法 → accept
    assert dlg2.result() == QDialog.Accepted

    # ---- Fix：局部段「默认值」列居中（名/类型已居中，默认值原居左） ----
    w_loc = CompositeSignatureWidget()
    w_loc.set_signature(CompositeSignature(locals=[LocalVar("t", "number", 0)]))
    _d = w_loc._loc._tw.item(0, 2)
    assert int(_d.textAlignment()) == int(Qt.AlignCenter), "局部默认值列应居中"
    assert isinstance(w_loc._loc._tw.itemDelegateForColumn(2),
                      _CenteredTextDelegate), "默认值列编辑应居中"

    # ---- 优化：签名编辑弹窗字体放大 / 表格行高加高 / 控件圆角 ----
    dlg3 = CompositeSignatureDialog(
        CompositeSignature(inputs=[Param("x", "number")],
                            outputs=[Param("y", "number")],
                            locals=[LocalVar("t", "number", 0)]))
    # 字体放大（默认 9pt → ≥11pt）
    assert dlg3._sig_widget._in._tw.font().pointSize() >= 11, "签名弹窗字体应放大"
    # 表格行高加高（原 32 → ≥38）+ 表格整体加高（原 200 → ≥220）
    _vh3 = dlg3._sig_widget._in._tw.verticalHeader()
    assert _vh3 is not None and _vh3.defaultSectionSize() >= 38, "表格行高应加高"
    assert dlg3._sig_widget._in._tw.minimumHeight() >= 220, "表格整体应加高"
    # 控件圆角（弹窗 QSS 含 QPushButton + border-radius）
    _ss3 = dlg3.styleSheet()
    assert "border-radius" in _ss3 and "QPushButton" in _ss3, "弹窗控件应加圆角"
    # 字体改为宋体
    assert "SimSun" in _ss3, "签名弹窗字体应为宋体"

    print("CompositeSignatureWidget smoke OK")
