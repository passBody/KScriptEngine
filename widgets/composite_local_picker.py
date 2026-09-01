# -*- coding: utf-8 -*-
"""
合成卡片局部变量选择器（picker 钩子闭包）
========================================

:func:`make_composite_local_picker` 返回一个符合 ``StepIOWidget.picker`` 钩子
签名 ``(tree, vtype, parent) -> name|None`` 的闭包：弹菜单列出签名中类型**严格**
匹配 ``vtype`` 的输入/输出/局部参数（标「入参/出参/局部」），末项「新建局部变量…」
→ 小对话框（名/类型/默认值）→ 调 ``on_new`` 加进签名局部段 → 返回新参数名。

返回**裸名**（如 ``x``）：输入槽由 ``StepIOWidget._pick_input`` 包成 ``{{x}}``，
输出槽存裸名（= 局部树路径）。``tree`` 参数忽略（纯局部，不经全局树）。
"""
from typing import Callable, Optional

from PyQt5.QtWidgets import (
    QDialog, QDialogButtonBox, QFormLayout, QLineEdit, QMenu, QWidget,
)

from model.composite_signature import CompositeSignature

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
    def picker(_tree, vtype: str, parent: QWidget) -> Optional[str]:
        menu = QMenu(parent)
        for label, _name in _matching_items(signature, vtype):
            menu.addAction(label)
        menu.addSeparator()
        menu.addAction("新建局部变量…")
        pos = parent.mapToGlobal(parent.rect().center()) if parent is not None else None
        act = menu.exec_(pos) if pos is not None else menu.exec_()
        if act is None:
            return None
        if act.text() == "新建局部变量…":
            return _new_local_dialog(vtype, on_new)
        return act.text().split("·", 1)[-1]   # 去掉「入参·」等前缀，取裸名
    return picker


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
    if dlg.exec_() != QDialog.Accepted:
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
# 冒烟演示：直接 ``python -m widgets.composite_local_picker`` 运行
# ================================================================
if __name__ == "__main__":
    import sys
    from PyQt5.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(sys.argv)
    from model.composite_signature import Param, LocalVar

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

    # 3) picker 返回裸名：打桩 QMenu.exec_ 返回「入参·x」→ 去前缀得 x
    created = []
    picker = make_composite_local_picker(sig, lambda n, t, d: created.append((n, t, d)))
    import PyQt5.QtWidgets as _W

    class _StubAct:
        def __init__(self, text): self._t = text
        def text(self): return self._t
    orig_exec = _W.QMenu.exec_
    orig_dlg = QDialog.exec_
    try:
        _W.QMenu.exec_ = lambda self, *a, **k: _StubAct("入参·x")
        name = picker(None, "number", None)
        assert name == "x", name
        # 选「新建局部变量…」→ _new_local_dialog；打桩 QDialog.exec_ 返回 Rejected（取消）→ None
        _W.QMenu.exec_ = lambda self, *a, **k: _StubAct("新建局部变量…")
        QDialog.exec_ = lambda self: QDialog.Rejected
        name2 = picker(None, "number", None)
        assert name2 is None              # 取消 → None，on_new 不被调
    finally:
        _W.QMenu.exec_ = orig_exec
        QDialog.exec_ = orig_dlg
    assert created == [], created          # 取消路径未触发 on_new

    print("CompositeLocalPicker smoke OK")
