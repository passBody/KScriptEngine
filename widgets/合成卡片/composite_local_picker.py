# -*- coding: utf-8 -*-
"""
合成卡片局部变量选择器（picker 钩子闭包）
========================================

:func:`make_composite_local_picker` 返回一个符合 ``StepIOWidget.picker`` 钩子
签名 ``(tree, vtype, parent) -> name|None`` 的闭包：弹**顶层对话框**列出签名中类型
**严格**匹配 ``vtype`` 的输入/输出/局部参数（标「入参/出参/局部」），对话框内
「新建局部变量…」按钮 → 小对话框（名/类型/默认值）→ 调 ``on_new`` 加进签名局部段
→ 返回新参数名。

返回**裸名**（如 ``x``）：输入槽由 ``StepIOWidget._pick_input`` 包成 ``{{x}}``，
输出槽存裸名（= 局部树路径）。``tree`` 参数忽略（纯局部，不经全局树）。

**为何是对话框而不是 QMenu**：卡片活在 QGraphicsView 场景（QGraphicsProxyWidget）里，
``parent`` 是场景内控件 → 该 QMenu **不是**真正的应用级 popup（实测
``QApplication.activePopupWidget()`` 为 None）→ 被内嵌进场景按场景 z 序渲染：透明底、
默认黑字、易被相邻卡片遮挡/点不中。全工程其余菜单的 parent 都是普通窗口控件
（``QMenu(self)`` 的 self 是树/视图），只有这里落在 proxy 内。同
:meth:`StepIOWidget._default_picker` 早已记录的「带 parent 的对话框被 proxy 内嵌渲染、
被相邻卡片遮挡」，故同样用 **parent=None 的顶层窗口**。
"""
from typing import Callable, Optional

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QDialog, QDialogButtonBox, QFormLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QPushButton, QVBoxLayout, QWidget,
)

from model.合成卡片.composite_signature import CompositeSignature

__all__ = ["make_composite_local_picker"]


def _matching_items(signature: CompositeSignature, vtype: str):
    """返回 [(显示文本, 裸名), ...]：签名中类型严格等于 vtype 的参数（标段归属）。

    类型过滤严格相等（spec §5.3：只列 type == vtype 的槽位）——
    不做 number→string 隐式兼容，避免产出运行期类型不符的绑定。
    """
    items = []
    for p in signature.inputs:
        if p.type == vtype:
            items.append(("入参·%s" % p.name, p.name))
    for p in signature.outputs:
        if p.type == vtype:
            items.append(("出参·%s" % p.name, p.name))
    for v in signature.locals:
        if v.type == vtype:
            items.append(("局部·%s" % v.name, v.name))
    return items


def make_composite_local_picker(
        signature: CompositeSignature,
        on_new: Callable[[str, str, object], None]
) -> Callable[..., Optional[str]]:
    """返回 picker 闭包。``on_new(name, type, default)`` 由宿主实现（加局部段 + 落盘）。"""
    def picker(_tree, vtype: str, _parent: QWidget) -> Optional[str]:
        return _pick_dialog(_matching_items(signature, vtype), vtype, on_new)
    return picker


def _pick_dialog(items, vtype: str, on_new) -> Optional[str]:
    """选择对话框：列出 ``items``（显示文本, 裸名）+「新建局部变量…」；取消 → None。"""
    dlg = QDialog(None)          # 顶层：见模块 docstring（带 parent 会被 proxy 内嵌）
    dlg.setWindowTitle("选择变量（%s）" % vtype)
    dlg.resize(300, 340)
    lay = QVBoxLayout(dlg)
    lst = QListWidget()
    for label, name in items:
        it = QListWidgetItem(label)
        it.setData(Qt.UserRole, name)      # 叶子存裸名，显示文本带「入参·」等前缀
        lst.addItem(it)
    if items:
        lst.setCurrentRow(0)
    else:
        lay.addWidget(QLabel("签名中没有 %s 类型的参数，可「新建局部变量」。" % vtype))
    lay.addWidget(lst, 1)
    new_btn = QPushButton("新建局部变量…")
    lay.addWidget(new_btn)
    btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
    ok_btn = btns.button(QDialogButtonBox.Ok)
    if ok_btn is not None:
        ok_btn.setEnabled(bool(items))     # 无参数可挑 → 只能新建或取消
    lay.addWidget(btns)
    chosen = {"name": None}

    def _ok() -> None:
        it = lst.currentItem()
        if it is not None:
            chosen["name"] = it.data(Qt.UserRole)
            dlg.accept()

    def _new() -> None:
        name = _new_local_dialog(vtype, on_new)
        if name:                            # 建好即选中，省一步
            chosen["name"] = name
            dlg.accept()

    lst.itemDoubleClicked.connect(lambda _it: _ok())
    btns.accepted.connect(_ok)
    btns.rejected.connect(dlg.reject)
    new_btn.clicked.connect(_new)
    from widgets.通用.ui_common import run_dialog
    if not run_dialog(dlg):
        return None
    return chosen["name"]


def _new_local_dialog(vtype: str, on_new) -> Optional[str]:
    # 顶层窗口而非 parent：卡片在 QGraphicsView 场景（QGraphicsProxyWidget）中时，
    # 带 parent 的 QDialog 会被 proxy 内嵌渲染、被相邻卡片遮挡（同 _default_picker，step_io.py:702-705）
    dlg = QDialog(None)
    dlg.setWindowTitle("新建局部变量")
    lay = QFormLayout(dlg)
    name_edit = QLineEdit()
    type_edit = QLineEdit(vtype)
    type_edit.setReadOnly(True)   # 预填当前槽位类型（spec §5.3）
    default_edit = QLineEdit("0" if vtype == "number" else "")
    lay.addRow("名称", name_edit)
    lay.addRow("类型", type_edit)
    lay.addRow("默认值", default_edit)
    btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
    btns.accepted.connect(dlg.accept)
    btns.rejected.connect(dlg.reject)
    lay.addRow(btns)
    # 非模态 + 点窗口以外关闭（同 ESC）：模态度下外部点击到不了事件过滤器
    from widgets.通用.ui_common import run_dialog
    if not run_dialog(dlg):
        return None
    name = name_edit.text().strip()
    if not name:
        return None
    vtype2 = type_edit.text().strip() or vtype
    default_txt = default_edit.text().strip()
    default = _coerce(vtype2, default_txt)
    on_new(name, vtype2, default)
    return name


def _coerce(vtype: str, text: str):
    if vtype == "number":
        try:
            return int(text) if text else 0
        except ValueError:
            try:
                return float(text)
            except ValueError:
                return 0
    return text


# ================================================================
# 冒烟演示：直接 ``python -m widgets.合成卡片.composite_local_picker`` 运行
# ================================================================
if __name__ == "__main__":
    import sys
    from PyQt5.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(sys.argv)
    from model.合成卡片.composite_signature import Param, LocalVar

    sig = CompositeSignature(inputs=[Param("x", "number"), Param("s", "string")],
                             outputs=[Param("y", "number")],
                             locals=[LocalVar("t", "number", 0),
                                     LocalVar("u", "string", "")])

    # 1) _matching_items 类型严格过滤（无 number→string 兼容）
    num_items = [n for _, n in _matching_items(sig, "number")]
    assert num_items == ["x", "y", "t"], num_items   # 入参x/出参y/局部t，严格 number
    str_items = [n for _, n in _matching_items(sig, "string")]
    assert str_items == ["s", "u"], str_items        # 入参s/局部u，严格 string
    assert "s" not in num_items and "x" not in str_items   # 不跨类型兼容

    # 2) _coerce 数字/字符串默认值
    assert _coerce("number", "42") == 42
    assert _coerce("number", "") == 0
    assert _coerce("number", "abc") == 0           # 无法解析 → 0
    assert _coerce("string", "hi") == "hi"

    # 3) picker：**顶层对话框**（parent=None，场景内带 parent 会被 proxy 内嵌）
    #    只打桩事件循环（run_dialog），其余全走真控件：列表 → 「确定」→ 裸名
    created = []
    picker = make_composite_local_picker(sig, lambda n, t, d: created.append((n, t, d)))
    import widgets.通用.ui_common as _uic
    from PyQt5.QtWidgets import QDialogButtonBox, QListWidget, QLineEdit as _QLE

    orig_run = _uic.run_dialog
    dlg_seen = []

    def _drive(mode):
        """模拟用户操作真对话框；返回 True = 「确定」语义。"""
        def fake(dlg):
            dlg_seen.append(dlg)
            if mode == "cancel":
                return False
            lst = dlg.findChild(QListWidget)
            lst.setCurrentRow(0)                     # 选第 1 项
            box = dlg.findChild(QDialogButtonBox)
            box.button(QDialogButtonBox.Ok).click()  # 「确定」
            return True
        return fake

    try:
        _uic.run_dialog = _drive("pick")
        name = picker(None, "number", None)
        assert name == "x", name          # 「入参·x」→ 去前缀得裸名
        assert dlg_seen[-1].parent() is None, "必须是顶层对话框（否则被 proxy 内嵌）"
        assert dlg_seen[-1].windowTitle() == "选择变量（number）"

        _uic.run_dialog = _drive("cancel")
        assert picker(None, "number", None) is None      # 取消 → None
    finally:
        _uic.run_dialog = orig_run
    assert created == [], created          # 只选不建 → on_new 未被调

    # 4)「新建局部变量…」→ _new_local_dialog → on_new(名, 类型, 默认值) → 返回新名
    def _drive_new(dlg):
        """外层选择框：点「新建局部变量…」；内层小框：填名 t2 → 确定。"""
        dlg_seen.append(dlg)
        if dlg.windowTitle() == "新建局部变量":
            edits = dlg.findChildren(_QLE)
            edits[0].setText("t2")                       # 名称
            edits[2].setText("7")                        # 默认值（number）
            box = dlg.findChild(QDialogButtonBox)
            box.button(QDialogButtonBox.Ok).click()
            return True
        for b in dlg.findChildren(QPushButton):
            if b.text() == "新建局部变量…":
                b.click()
                break
        return True

    try:
        _uic.run_dialog = _drive_new
        name3 = picker(None, "number", None)
    finally:
        _uic.run_dialog = orig_run
    assert name3 == "t2", name3
    assert created == [("t2", "number", 7)], created     # on_new 收到名/类型/默认值

    # 5) 无匹配参数：仍可打开（列表空 + 「确定」禁用），只留「新建」出路
    empty_picker = make_composite_local_picker(sig, lambda n, t, d: None)

    def _drive_empty(dlg):
        dlg_seen.append(dlg)
        lst = dlg.findChild(QListWidget)
        box = dlg.findChild(QDialogButtonBox)
        assert lst.count() == 0
        assert not box.button(QDialogButtonBox.Ok).isEnabled()
        return False                                       # 取消
    try:
        _uic.run_dialog = _drive_empty
        assert empty_picker(None, "image", None) is None    # 签名里没有 image 参数
    finally:
        _uic.run_dialog = orig_run

    print("CompositeLocalPicker smoke OK")
