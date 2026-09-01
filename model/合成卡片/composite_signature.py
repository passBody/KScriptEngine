# -*- coding: utf-8 -*-
"""
合成卡片签名（输入/输出/局部参数的纯数据模型）
================================================

:class:`CompositeSignature` 描述一张合成卡片的形参：**输入/输出/局部**三段，
互不兼任。输入/输出段每项是 :class:`Param`（名 + 类型）；局部段每项是
:class:`LocalVar`（名 + 类型 + 默认值）。签名经 ``to_json``/``from_json`` 与
``composites.json`` 的 ``sigs`` 表往返。

本模块属 model 层：**模块顶层不导入 PyQt5**，纯数据 + 校验 + 序列化。
"""
from dataclasses import dataclass, field
from typing import Any, List

from model.工程.path_util import validate_name
from model.变量.project_variable import ProjectVariable

__all__ = ["Param", "LocalVar", "CompositeSignature"]


@dataclass
class Param:
    """输入/输出参数：名 + 已注册变量类型名。"""
    name: str
    type: str


@dataclass
class LocalVar:
    """局部变量：名 + 类型 + 默认值（运行期建局部树时用）。"""
    name: str
    type: str
    default: Any = None


@dataclass
class CompositeSignature:
    """合成卡片签名：输入/输出/局部三段（互不兼任）。"""
    inputs: List[Param] = field(default_factory=list)
    outputs: List[Param] = field(default_factory=list)
    locals: List[LocalVar] = field(default_factory=list)

    # ---- 只读视图 ----
    def input_types(self) -> List[str]:
        return [p.type for p in self.inputs]

    def output_types(self) -> List[str]:
        return [p.type for p in self.outputs]

    def input_names(self) -> List[str]:
        return [p.name for p in self.inputs]

    def output_names(self) -> List[str]:
        return [p.name for p in self.outputs]

    def local_names(self) -> List[str]:
        return [v.name for v in self.locals]

    def slot_names(self) -> List[str]:
        """全参数名（输入+输出+局部；供选择器列出）。"""
        return ([p.name for p in self.inputs]
                + [p.name for p in self.outputs]
                + [v.name for v in self.locals])

    @classmethod
    def empty(cls) -> "CompositeSignature":
        return cls()

    def is_empty(self) -> bool:
        return not (self.inputs or self.outputs or self.locals)

    # ---- 校验 ----
    def validate(self) -> None:
        """校验：类型须已注册；名字段内唯一、跨段不重名；无非法字符（/ . ..）。

        非法 → ValueError（带具体段/名/原因，便于定位）。
        """
        seen: set = set()
        for label, items in (("输入", self.inputs), ("输出", self.outputs)):
            for p in items:
                validate_name(p.name)                       # 无 / . ..
                if ProjectVariable.type_of(p.type) is None:
                    raise ValueError(
                        "%s参数 %r 的类型未注册: %r（支持: %s）"
                        % (label, p.name, p.type,
                           ProjectVariable.supported_types()))
                if p.name in seen:
                    raise ValueError("参数名跨段重复: %r" % p.name)
                seen.add(p.name)
        for v in self.locals:
            validate_name(v.name)
            if ProjectVariable.type_of(v.type) is None:
                raise ValueError(
                    "局部变量 %r 的类型未注册: %r（支持: %s）"
                    % (v.name, v.type, ProjectVariable.supported_types()))
            if v.name in seen:
                raise ValueError("参数名跨段重复: %r" % v.name)
            seen.add(v.name)

    # ---- 序列化 ----
    def to_json(self) -> dict:
        return {
            "in": [{"name": p.name, "type": p.type} for p in self.inputs],
            "out": [{"name": p.name, "type": p.type} for p in self.outputs],
            "loc": [{"name": v.name, "type": v.type, "default": v.default}
                    for v in self.locals],
        }

    @classmethod
    def from_json(cls, d: Any) -> "CompositeSignature":
        if not isinstance(d, dict):
            raise ValueError("签名必须是对象，而非 %s" % type(d).__name__)
        sig = cls()
        for p in d.get("in", []) or []:
            sig.inputs.append(Param(_req(p, "name"), _req(p, "type")))
        for p in d.get("out", []) or []:
            sig.outputs.append(Param(_req(p, "name"), _req(p, "type")))
        for v in d.get("loc", []) or []:
            sig.locals.append(
                LocalVar(_req(v, "name"), _req(v, "type"), v.get("default")))
        sig.validate()
        return sig


def _req(d: dict, key: str) -> str:
    if not isinstance(d, dict) or key not in d or not isinstance(d[key], str):
        raise ValueError("签名条目缺少字符串键 %r" % key)
    return d[key]


# ================================================================
# 冒烟演示：直接 ``python -m model.合成卡片.composite_signature`` 运行
# ================================================================
if __name__ == "__main__":
    # 空 + 视图
    e = CompositeSignature.empty()
    assert e.is_empty() and e.input_types() == [] and e.slot_names() == []
    assert e.to_json() == {"in": [], "out": [], "loc": []}
    assert CompositeSignature.from_json({"in": [], "out": [], "loc": []}) == e

    # 三段构造 + 视图
    sig = CompositeSignature(
        inputs=[Param("x", "number"), Param("name", "string")],
        outputs=[Param("y", "number")],
        locals=[LocalVar("t", "number", 0)])
    assert sig.input_types() == ["number", "string"]
    assert sig.output_types() == ["number"]
    assert sig.input_names() == ["x", "name"]
    assert sig.output_names() == ["y"]
    assert sig.local_names() == ["t"]
    assert sig.slot_names() == ["x", "name", "y", "t"]
    assert not sig.is_empty()

    # 往返
    raw = sig.to_json()
    assert raw == {"in": [{"name": "x", "type": "number"},
                         {"name": "name", "type": "string"}],
                   "out": [{"name": "y", "type": "number"}],
                   "loc": [{"name": "t", "type": "number", "default": 0}]}
    back = CompositeSignature.from_json(raw)
    assert back == sig
    # from_json 拒绝非 dict（如 str）→ ValueError
    try:
        CompositeSignature.from_json('{"in":[]}')   # str → 非 dict → ValueError
        raise AssertionError("str 输入应抛 ValueError")
    except ValueError:
        pass

    # 校验：类型未注册
    try:
        CompositeSignature(inputs=[Param("x", "audio")]).validate()
        raise AssertionError("未注册类型应抛 ValueError")
    except ValueError as ex:
        assert "x" in str(ex) and "audio" in str(ex)
    # 校验：名字含 /
    try:
        CompositeSignature(inputs=[Param("a/b", "number")]).validate()
        raise AssertionError("名字含 / 应抛 ValueError")
    except ValueError:
        pass
    # 校验：跨段重名
    try:
        CompositeSignature(inputs=[Param("x", "number")],
                           locals=[LocalVar("x", "number", 0)]).validate()
        raise AssertionError("跨段重名应抛 ValueError")
    except ValueError as ex:
        assert "x" in str(ex)
    # 校验：段内重名（构造时手动加）
    bad = CompositeSignature(inputs=[Param("x", "number")])
    bad.inputs.append(Param("x", "number"))
    try:
        bad.validate()
        raise AssertionError("段内重名应抛 ValueError")
    except ValueError:
        pass
    # from_json 内含校验：非法类型 → 抛
    try:
        CompositeSignature.from_json({"in": [{"name": "x", "type": "audio"}]})
        raise AssertionError("from_json 非法类型应抛 ValueError")
    except ValueError:
        pass
    # from_json 缺键 / 非字符串
    try:
        CompositeSignature.from_json({"in": [{"name": "x"}]})
        raise AssertionError("缺 type 应抛 ValueError")
    except ValueError:
        pass
    try:
        CompositeSignature.from_json({"in": [{"name": 1, "type": "number"}]})
        raise AssertionError("非 str 应抛 ValueError")
    except ValueError:
        pass
    # from_json 顶层非对象
    try:
        CompositeSignature.from_json([1, 2, 3])
        raise AssertionError("顶层非对象应抛 ValueError")
    except ValueError:
        pass

    print("CompositeSignature smoke OK")
