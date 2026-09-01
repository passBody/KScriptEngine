# -*- coding: utf-8 -*-
"""
合成卡片局部树（运行期纯局部作用域工厂）
======================================

:func:`build_local_tree` 为一次带参合成卡片调用建一棵普通 :class:`VariableTree`，
预填**局部变量**（默认值）与**输出参数**（类型默认空值，供 body 步骤
``write_outputs`` 的成员校验通过）；**输入参数不预填**——由
:meth:`CompositeCard.input` 解析调用点入参后 ``set`` 进来。

纯局部：无 parent、无全局回退。body 步骤若引用不在局部树的名字 → ``resolve_inputs``
抛 ``FileNotFoundError`` → 该步骤 ERROR（同普通步骤解析失败）。

本模块属 model 层：顶层不导入 PyQt5。
"""
from typing import TYPE_CHECKING

from model.composite_signature import CompositeSignature
from model.project_variable import ProjectVariable
from model.variable_tree import VariableTree

if TYPE_CHECKING:
    from model.kscp_package import KscpPackage

__all__ = ["build_local_tree", "build_validation_tree", "default_value_for"]


def default_value_for(vtype: str) -> object:
    """类型的空默认值（number→0、string→""、资源类→""）。"""
    if vtype == "number":
        return 0
    return ""


def build_local_tree(sig: CompositeSignature,
                     package: "KscpPackage") -> VariableTree:
    """建局部树：locals 填默认值、outputs 填类型默认空值；inputs 不预填。

    inputs 不预填——由 :meth:`CompositeCard.input` 解析调用点入参后 ``set`` 进来
    （故编辑期拿这棵树校验 ``{{输入参数}}`` 会误判非法）。**运行期专用**。
    """
    tree = VariableTree.create_empty()
    for v in sig.locals:
        tree.add(v.name, ProjectVariable.create(v.type, v.default, package))
    for p in sig.outputs:
        tree.add(p.name, ProjectVariable.create(p.type, default_value_for(p.type),
                                                package))
    return tree


def build_validation_tree(sig: CompositeSignature,
                         package: "KscpPackage") -> VariableTree:
    """编辑期校验树：inputs/locals/outputs **全部**预填类型默认值。

    与 :func:`build_local_tree` 的区别——inputs 也预填：运行期 inputs 由
    :meth:`CompositeCard.input` 注入，但**编辑期**需让 body 步骤绑
    ``{{输入参数}}`` 判合法（否则误红）。纯局部、无全局回退 → body 步骤绑
    ``{{全局变量}}`` 时 :attr:`model.step_io.StepIOWidget.is_valid` 判 False
    → 卡片**即时红标**，与运行期局部树缺失该名 → ``resolve_inputs`` 抛
    ``FileNotFoundError`` → 步骤 ERROR 一致（修「编辑期不红、运行期才红」
    的不一致）。

    空签名 → 空树（参数less 卡片 body 走全局树，调用方应守卫不调本函数）。
    """
    tree = VariableTree.create_empty()
    for p in sig.inputs:
        tree.add(p.name, ProjectVariable.create(p.type, default_value_for(p.type),
                                                package))
    for v in sig.locals:
        tree.add(v.name, ProjectVariable.create(v.type, v.default, package))
    for p in sig.outputs:
        tree.add(p.name, ProjectVariable.create(p.type, default_value_for(p.type),
                                                package))
    return tree


# ================================================================
# 冒烟演示：直接 ``python -m model.composite_local_tree`` 运行
# ================================================================
if __name__ == "__main__":
    from model.kscp_package import KscpPackage
    from model.composite_signature import Param, LocalVar

    pkg = KscpPackage.create_empty()
    sig = CompositeSignature(
        inputs=[Param("x", "number")],
        outputs=[Param("y", "number")],
        locals=[LocalVar("t", "number", 7)])
    t = build_local_tree(sig, pkg)
    # 局部已填默认值
    assert t.get("t").data == 7 and t.get("t").valid
    # 输出预填类型默认（number → 0）
    assert t.get("y").data == 0 and t.get("y").valid
    # 输入未预填 → get 抛 FileNotFoundError
    try:
        t.get("x")
        raise AssertionError("输入不应预填")
    except FileNotFoundError:
        pass
    # set 输入（input() 路径）→ upsert
    from model.project_variable import ProjectVariable as _PV
    t.set("x", _PV.create("number", 42, pkg))
    assert t.get("x").data == 42
    # 空签名 → 空树
    assert len(build_local_tree(CompositeSignature.empty(), pkg)) == 0

    # build_validation_tree：inputs/locals/outputs 全部预填（编辑期校验用）
    vt = build_validation_tree(sig, pkg)
    assert vt.is_variable("x") and vt.is_variable("y") and vt.is_variable("t")
    assert vt.get("x").data == 0 and vt.get("x").type == "number"   # input 预填类型默认
    assert vt.get("t").data == 7                                    # local 用自定义默认
    # 全局名不在校验树 → body 步骤绑 {{n1}} 时 is_variable 判 False（红卡根因）
    assert not vt.is_variable("n1")
    # 空签名 → 空树
    assert len(build_validation_tree(CompositeSignature.empty(), pkg)) == 0
    print("CompositeLocalTree smoke OK")
