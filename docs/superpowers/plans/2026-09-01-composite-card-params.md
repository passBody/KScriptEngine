# 合成卡片输入/输出/局部参数 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give composite cards（合成卡片）input/output/local parameters（函数语义）— call sites bind inputs (value or `{{var}}`) + output targets; at runtime the body executes in a pure-local `VariableTree` (no global fallback); outputs write back to the call-site-bound targets.

**Architecture:** Data-model layer (no Qt top-level dependency) holds `CompositeSignature` / `CompositeDefinition` / `build_local_tree`; `CompositeCard` overrides `input()`/`run()`/`output()` to build a per-call local tree, swap body steps' `io._tree` for the run, and restore via `try/finally`. Storage stays v1-tree-compatible: `composites.json` becomes `{"tree": <v1 tree>, "sigs": {path→sig}}` (sigs pre-loaded before tree walk, so `from_marker` can fetch a signature during body decode). Widget layer injects the local picker by setting `step.io.picker` on body steps before `host.set_list` — `step_list_view.py` is NOT modified.

**Tech Stack:** Python 3.13, PyQt5 (QTreeWidget/QTableWidget/QStackedWidget/signals). Tests = embedded `__main__` smoke blocks run via `python -m <module>` (print `… smoke OK`); full regression via `python tests/smoke_all.py`.

> **No git in this project** — "Checkpoint" steps below run the module smoke instead of `git commit`. Verify each task's smoke prints its `… smoke OK` line before moving on. Final regression: `python tests/smoke_all.py` → `ALL N SMOKE + 1 CHECKS OK`.

**Spec:** `docs/superpowers/specs/2026-09-01-composite-card-params-design.md` (approved). Two spec points are refined here for correctness/maintainability, both noted inline at the relevant task:
- §1 tagged `composite_tree_widget.py` as `[改]` but the signature widget mounts in `CompositeManagementTree.preview_widget()` (center panel), not the left tree → the tree widget is **unchanged** for v2.
- §3.2 wrote the ctor as `(ref, signature, io, tree, package, …)`; the plan uses a **backward-compatible** ctor `(ref, tree, package, signature=None, io=None, …)` so the many v1 callers (`CompositeCard(ref, tree, pkg)`) keep working.

---

## File Structure

**New model modules (no Qt top-level):**
- `model/composite_signature.py` — `Param` / `LocalVar` / `CompositeSignature` (pure data + `to/from_json` + validation + `empty()` + name/type views).
- `model/composite_definition.py` — `CompositeDefinition(body: StepList, signature: CompositeSignature)` (pure data bundle).
- `model/composite_local_tree.py` — `build_local_tree(sig, package) -> VariableTree` (runtime local-scope factory).

**Modified model modules:**
- `model/composite_card_store.py` — wrapped `{"tree","sigs"}` JSON; in-place `load_from_json` (sigs first); `get`/`get_body`/`get_signature`/`get_or_none` (partial defn); `add_list(path, body, signature=empty)`; `set_signature`/`rename`/`remove` update sigs.
- `model/composite_card.py` — `CompositeCard` v2: backward-compatible ctor, marker `@合成卡片:<path>:<io_b64>` (bare for v1), `from_marker` fetches signature + builds drift-tolerant typed io, `input()`/`run()`/`output()` overrides with local-tree swap; keeps `repoint_refs` + adds `repoint_param_refs`.

**New widget modules (depend on model interfaces):**
- `widgets/composite_signature_widget.py` — `CompositeSignatureWidget(QWidget)`: 3-section editor (输入/输出/局部), emits `signature_changed(CompositeSignature)`.
- `widgets/composite_local_picker.py` — `make_composite_local_picker(signature, on_new) -> picker` closure + "新建局部变量…" quick-create.

**Modified widget modules:**
- `widgets/management_trees.py` — `CompositeManagementTree`: `preview_widget()` = container (signature widget + `StepListHost`); `_on_selected` uses `get_body`+`get_signature`, injects local picker; `_on_signature_changed` updates sigs + repoints body io + rebuilds picker + refreshes.
- `widgets/main_widget.py` — `_open_package`: create cstore shell → `set_resolver` → in-place `load_from_json` (sigs-first, solves the body-decode chicken-and-egg).

**Test/docs:**
- `tests/smoke_all.py` — register the 5 new modules.
- `docs/工程分析.md` + this plan's spec — document the params feature.

---

## Task 1: `model/composite_signature.py` (NEW)

**Files:**
- Create: `model/composite_signature.py`
- Test: its own `__main__` smoke

- [ ] **Step 1: Write the module + its failing smoke**

Create `model/composite_signature.py`:

```python
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
from typing import Any, List, Optional

from model.path_util import validate_name
from model.project_variable import ProjectVariable

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
# 冒烟演示：直接 ``python -m model.composite_signature`` 运行
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
```

- [ ] **Step 2: Run smoke, verify it passes**

Run: `python -m model.composite_signature`
Expected: `CompositeSignature smoke OK`

- [ ] **Step 3: Checkpoint**

`python -m model.composite_signature` → `CompositeSignature smoke OK`.

---

## Task 2: `model/composite_definition.py` (NEW)

**Files:**
- Create: `model/composite_definition.py`
- Test: its own `__main__` smoke

- [ ] **Step 1: Write the module + smoke**

Create `model/composite_definition.py`:

```python
# -*- coding: utf-8 -*-
"""
合成卡片定义（body + 签名 的纯数据捆绑）
======================================

:class:`CompositeDefinition` 把一张合成卡片的**定义体**（:class:`StepList`）
与其**参数签名**（:class:`CompositeSignature`）捆在一起，供
:class:`CompositeCardStore` 存取与 :class:`CompositeCard` 运行期解析。

本模块属 model 层：顶层不导入 PyQt5。
"""
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from model.composite_signature import CompositeSignature

if TYPE_CHECKING:
    from model.step_list import StepList

__all__ = ["CompositeDefinition"]


@dataclass
class CompositeDefinition:
    """一张合成卡片的定义：体内步骤列表 + 参数签名。"""
    body: "StepList"
    signature: CompositeSignature = field(default_factory=CompositeSignature.empty)


# ================================================================
# 冒烟演示：直接 ``python -m model.composite_definition`` 运行
# ================================================================
if __name__ == "__main__":
    from model.step_list import StepList
    from model.composite_signature import Param

    body = StepList.create_empty()
    d = CompositeDefinition(body, CompositeSignature(inputs=[Param("x", "number")]))
    assert d.body is body
    assert d.signature.input_names() == ["x"]
    # 签名默认空
    d2 = CompositeDefinition(StepList.create_empty())
    assert d2.signature.is_empty()
    print("CompositeDefinition smoke OK")
```

- [ ] **Step 2: Run smoke, verify it passes**

Run: `python -m model.composite_definition`
Expected: `CompositeDefinition smoke OK`

- [ ] **Step 3: Checkpoint**

`python -m model.composite_definition` → `CompositeDefinition smoke OK`.

---

## Task 3: `model/composite_local_tree.py` (NEW)

**Files:**
- Create: `model/composite_local_tree.py`
- Test: its own `__main__` smoke

`build_local_tree` pre-fills **locals** (with their defaults) and **outputs** (with type-appropriate empty defaults, so body steps' `write_outputs` membership check passes). Inputs are NOT pre-filled — `CompositeCard.input()` sets them via `set` (upsert) after resolving call-site values.

- [ ] **Step 1: Write the module + smoke**

Create `model/composite_local_tree.py`:

```python
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

__all__ = ["build_local_tree", "default_value_for"]


def default_value_for(vtype: str) -> object:
    """类型的空默认值（number→0、string→""、资源类→""）。"""
    if vtype == "number":
        return 0
    return ""


def build_local_tree(sig: CompositeSignature,
                     package: "KscpPackage") -> VariableTree:
    """建局部树：locals 填默认值、outputs 填类型默认空值；inputs 不预填。"""
    tree = VariableTree.create_empty()
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
    print("CompositeLocalTree smoke OK")
```

- [ ] **Step 2: Run smoke, verify it passes**

Run: `python -m model.composite_local_tree`
Expected: `CompositeLocalTree smoke OK`

- [ ] **Step 3: Checkpoint**

`python -m model.composite_local_tree` → `CompositeLocalTree smoke OK`.

---

## Task 4: `model/composite_card_store.py` (MODIFY — wrapped `{"tree","sigs"}` storage)

**Files:**
- Modify: `model/composite_card_store.py` (full file rewrite of the storage layer; keep the public smoke extended)
- Test: extended `__main__` smoke

Goal: tree stays pure v1 (list=leaf, dict=group, `_walk` unchanged); signatures ride in a parallel `sigs: Dict[str, CompositeSignature]` map. Add in-place `load_from_json` that reads `sigs` FIRST, so `from_marker` (called during body decode) can fetch a signature before the referenced composite's body is decoded. `get_or_none` returns a `CompositeDefinition` whose `body` may be `None` (during load) but whose `signature` is always the pre-loaded sig.

- [ ] **Step 1: Replace the imports + class body**

At the top, add imports + change the docstring's JSON example. Replace the whole `CompositeCardStore` class with:

```python
import json
from typing import Any, Callable, Dict, List, Optional, Tuple, Union, TYPE_CHECKING

from model.composite_definition import CompositeDefinition
from model.composite_signature import CompositeSignature
from model.path_util import normalize, validate_name
from model.step_list import StepList

if TYPE_CHECKING:
    from model.step_manager import StepManager

__all__ = ["CompositeCardStore"]

JsonInput = Union[str, bytes, bytearray, dict]


class CompositeCardStore:
    """合成卡片列表模型：v1 树（叶子=StepList / dict=组）+ 平铺 sigs 表。

    composites.json 形态（包装）::

        {
          "tree": {"组/卡片A": ["<fmt>", ...], "组": {"子卡片": [...]}},
          "sigs": {"组/卡片A": {"in": [...], "out": [...], "loc": [...]}}
        }

    v1 文件顶层直接是树（无 ``tree`` 键）→ ``from_json``/``load_from_json`` 视为
    v1，签名全空。一旦落盘即升级为包装格式（前向迁移）。
    """

    _MAX_DEPTH = 128

    def __init__(self) -> None:
        self.root: Dict[str, Any] = {}     # StepList(叶子) | dict(组) —— v1 不变
        self.sigs: Dict[str, CompositeSignature] = {}   # path -> 签名（旁挂）

    @staticmethod
    def _norm_path(path: str) -> str:
        return normalize(path)

    @staticmethod
    def _validate_name(name: str) -> None:
        validate_name(name)

    def _parent_of(self, parts: List[str]) -> dict:
        node = self.root
        for seg in parts[:-1]:
            child = node.get(seg)
            if isinstance(child, StepList):
                raise ValueError("祖先路径 %r 已是卡片，无法在其下操作" % seg)
            if not isinstance(child, dict):
                raise ValueError("父分组不存在: %r" % seg)
            node = child
        return node

    # ---- 写 ----
    def add_group(self, path: str) -> None:
        parts = self._norm_path(path).split("/")
        node = self._parent_of(parts)
        last = parts[-1]
        if isinstance(node.get(last), StepList):
            raise FileExistsError("目标已是卡片: %r" % path)
        if last not in node:
            node[last] = {}

    def add_list(self, path: str, step_list: StepList,
                 signature: CompositeSignature = CompositeSignature.empty()) -> None:
        n = self._norm_path(path)               # 归一化：sigs 键与树写同源
        parts = n.split("/")
        node = self._parent_of(parts)
        last = parts[-1]
        if last in node:
            raise FileExistsError("目标已存在: %r" % path)
        node[last] = step_list
        if not signature.is_empty():
            self.sigs[n] = signature

    def set_signature(self, path: str, signature: CompositeSignature) -> None:
        """更新/设置某卡片的签名（编辑期 signature_changed 用）。"""
        n = self._norm_path(path)
        if not signature.is_empty():
            self.sigs[n] = signature
        else:
            self.sigs.pop(n, None)

    # ---- JSON 导出 ----
    def to_json_bytes(self) -> bytes:
        return json.dumps(self._to_node(), ensure_ascii=False).encode("utf-8")

    def _to_node(self) -> dict:
        """输出包装 {"tree": <v1 树>, "sigs": {path: sig.to_json()}}。"""
        tree = self._to_tree_node(self.root)
        sigs = {p: s.to_json() for p, s in self.sigs.items()}
        return {"tree": tree, "sigs": sigs}

    @staticmethod
    def _to_tree_node(node: dict) -> dict:
        out: dict = {}
        for key, value in node.items():
            if isinstance(value, StepList):
                out[key] = value.to_format_strings()
            else:
                out[key] = CompositeCardStore._to_tree_node(value)
        return out

    # ---- 还原 ----
    @classmethod
    def from_json(cls, data: JsonInput,
                  manager: "StepManager") -> "CompositeCardStore":
        s = cls()
        s.load_from_json(data, manager)
        return s

    def load_from_json(self, data: JsonInput,
                      manager: "StepManager") -> None:
        """就地加载（保留 self.root/self.sigs 引用 → 解析器闭包可见）。

        **先读 sigs，再走树**：树体内若含合成卡片引用，``from_marker`` 解码时
        经解析器取被引卡签名——此时 sigs 已就绪（即便被引卡 body 尚未走到）。
        """
        if isinstance(data, dict):
            root_in = data
        else:
            try:
                root_in = json.loads(data)
            except (json.JSONDecodeError, UnicodeDecodeError, RecursionError) as e:
                raise ValueError("无效的 composites.json: %s" % e)
        if not isinstance(root_in, dict):
            raise ValueError(
                "composites.json 顶层必须是对象，而非 %s" % type(root_in).__name__)
        # 包装检测：顶层含 tree → 新格式；否则 v1（整顶层作树，sigs 空）
        if isinstance(root_in.get("tree"), dict):
            tree_in = root_in["tree"]
            sigs_in = root_in.get("sigs") or {}
            if not isinstance(sigs_in, dict):
                raise ValueError("composites.json 的 sigs 必须是对象")
        else:
            tree_in = root_in
            sigs_in = {}
        # 先读 sigs（from_marker 在走树时可取到）
        self.sigs = {}
        for path, sd in sigs_in.items():
            n = self._norm_path(path)   # 校验路径合法 + 归一化为 sigs 键
            self.sigs[n] = CompositeSignature.from_json(sd)
        # 再走树（叶子 StepList 由 manager 解码，体内合成卡片引用经 from_marker）
        self.root = {}
        self._walk(tree_in, self.root, manager)

    def _walk(self, node: dict, target: dict,
              manager: "StepManager", depth: int = 0) -> None:
        if depth > self._MAX_DEPTH:
            raise ValueError("composites.json 嵌套过深（超过 %d 层）" % self._MAX_DEPTH)
        for key, value in node.items():
            self._validate_name(key)
            if isinstance(value, list):
                target[key] = StepList.from_format_strings(value, manager)
            elif isinstance(value, dict):
                sub: dict = {}
                self._walk(value, sub, manager, depth + 1)
                target[key] = sub
            else:
                raise ValueError("composites.json 节点值必须是列表或对象: %r" % key)

    # ---- 读取 ----
    @classmethod
    def create_empty(cls) -> "CompositeCardStore":
        return cls()

    def _get_body_or_none(self, path: str) -> Optional[StepList]:
        """树叶子 StepList；不是叶子/不存在/组 → None。"""
        parts = self._norm_path(path).split("/")
        node: Any = self.root
        for seg in parts[:-1]:
            child = node.get(seg) if isinstance(node, dict) else None
            if not isinstance(child, dict):
                return None
            node = child
        last = parts[-1]
        val = node.get(last) if isinstance(node, dict) else None
        return val if isinstance(val, StepList) else None

    def get_signature(self, path: str) -> CompositeSignature:
        """取签名；无条目 → 空签名（v1 参数less）。"""
        return self.sigs.get(self._norm_path(path), CompositeSignature.empty())

    def get_body(self, path: str) -> StepList:
        """取定义体 StepList；不存在/为组 → FileNotFoundError。"""
        body = self._get_body_or_none(path)
        if body is None:
            raise FileNotFoundError("不存在或不是卡片: %r" % path)
        return body

    def get(self, path: str) -> CompositeDefinition:
        """取完整定义（body + signature）；body 不存在 → FileNotFoundError。"""
        body = self.get_body(path)
        return CompositeDefinition(body, self.get_signature(path))

    def get_or_none(self, path: str) -> Optional[CompositeDefinition]:
        """取定义；body 与 sig 均无 → None。body 可能 None（加载期未走到），
        sig 由预加载的 sigs 提供——from_marker 只需 sig，故加载期可用。"""
        try:
            n = self._norm_path(path)
        except ValueError:
            return None
        body = self._get_body_or_none(path)
        sig = self.sigs.get(n)
        if body is None and sig is None:
            return None
        return CompositeDefinition(
            body if body is not None else StepList.create_empty(),
            sig if sig is not None else CompositeSignature.empty())

    def paths(self) -> List[str]:
        out: List[str] = []
        self._collect_paths(self.root, "", out)
        return sorted(out)

    @staticmethod
    def _collect_paths(node: dict, prefix: str, out: List[str]) -> None:
        for key, value in node.items():
            path = key if not prefix else prefix + "/" + key
            if isinstance(value, StepList):
                out.append(path)
            else:
                CompositeCardStore._collect_paths(value, path, out)

    # ---- 结构 / 变更扩展 ----
    def remove(self, path: str) -> None:
        parts = self._norm_path(path).split("/")
        parent = self._parent_of(parts)
        last = parts[-1]
        if last not in parent:
            raise FileNotFoundError("不存在: %r" % path)
        del parent[last]
        n = self._norm_path(path)
        self.sigs.pop(n, None)                       # 签名随卡片走
        prefix = n + "/"                              # 子树签名一并清除
        for k in [k for k in self.sigs if k.startswith(prefix)]:
            self.sigs.pop(k, None)

    def rename(self, path: str, new_name: str) -> None:
        self._validate_name(new_name)
        parts = self._norm_path(path).split("/")
        parent = self._parent_of(parts)
        last = parts[-1]
        if last not in parent:
            raise FileNotFoundError("不存在: %r" % path)
        if new_name in parent:
            raise FileExistsError("目标已存在: %r" % new_name)
        items = list(parent.items())
        for i, (k, v) in enumerate(items):
            if k == last:
                items[i] = (new_name, v)
                break
        parent.clear()
        parent.update(items)
        # 签名键随路径迁移（含子树）
        old_n = self._norm_path(path)
        parent_path = "/".join(parts[:-1])
        new_n = (parent_path + "/" + new_name) if parent_path else new_name
        if old_n in self.sigs:
            self.sigs[new_n] = self.sigs.pop(old_n)
        old_prefix = old_n + "/"
        new_prefix = new_n + "/"
        for k in list(self.sigs):
            if k.startswith(old_prefix):
                self.sigs[new_prefix + k[len(old_prefix):]] = self.sigs.pop(k)

    def walk(self) -> List[Tuple[str, bool]]:
        out: List[Tuple[str, bool]] = []
        self._collect_walk(self.root, "", out)
        return out

    @staticmethod
    def _collect_walk(node: dict, prefix: str,
                      out: List[Tuple[str, bool]]) -> None:
        for key, value in node.items():
            path = key if not prefix else prefix + "/" + key
            if isinstance(value, StepList):
                out.append((path, False))
            else:
                out.append((path, True))
                CompositeCardStore._collect_walk(value, path, out)
```

- [ ] **Step 2: Update the `__main__` smoke**

Replace the existing smoke body's `store.get(...)`/`add_list(...)` expectations to use the new API (`.body`, signature arg) and add wrapped-format + v1-back-compat assertions. The smoke file already builds `sl_login`/`sl_qs` etc.; update assertions:

```python
    # v1 树叶子仍是 list；签名旁挂（空签名 → 无 sigs 条目）
    assert isinstance(s_bytes.get("登录流程"), StepList)   # get_body 返回 StepList
    # get() 返回 CompositeDefinition
    d_login = s_bytes.get("登录流程")
    assert isinstance(d_login, CompositeDefinition) and d_login.body is sl_back_login
    assert d_login.signature.is_empty()                     # v1 无签名
    # get_body / get_signature
    assert s_bytes.get_body("登录流程") is sl_back_login
    assert s_bytes.get_signature("登录流程").is_empty()

    # ---- v2 带签名：包装格式 {tree, sigs} + 往返 ----
    from model.composite_signature import Param, CompositeSignature
    sig = CompositeSignature(inputs=[Param("x", "number")],
                             outputs=[Param("y", "number")])
    store_sig = CompositeCardStore.create_empty()
    sl_v2 = StepList.create_empty()
    sl_v2.add(make_step())
    store_sig.add_list("带参卡", sl_v2, signature=sig)
    raw_v2 = store_sig.to_json_bytes()
    import json as _j2
    obj_v2 = _j2.loads(raw_v2)
    assert set(obj_v2) == {"tree", "sigs"}                  # 包装格式
    assert obj_v2["tree"]["带参卡"] == sl_v2.to_format_strings()
    assert obj_v2["sigs"]["带参卡"]["in"] == [{"name": "x", "type": "number"}]
    # 往返：签名保持
    back_v2 = CompositeCardStore.from_json(raw_v2, mgr)
    assert back_v2.get_signature("带参卡").input_names() == ["x"]
    assert back_v2.get_body("带参卡").to_format_strings() == sl_v2.to_format_strings()
    assert isinstance(back_v2.get("带参卡"), CompositeDefinition)
    # get_or_none：带签名卡 → defn（body + sig）
    d_v2 = back_v2.get_or_none("带参卡")
    assert d_v2 is not None and d_v2.signature.input_names() == ["x"]

    # ---- v1 向后兼容：旧格式（顶层直接是树，无 tree/sigs）→ 签名全空 ----
    v1_raw = _j2.dumps({"登录流程": sl_v2.to_format_strings()},
                       ensure_ascii=False).encode("utf-8")
    v1_store = CompositeCardStore.from_json(v1_raw, mgr)
    assert v1_store.get_signature("登录流程").is_empty()
    assert isinstance(v1_store.get_body("登录流程"), StepList)
    # 落盘后升级为包装格式
    obj_v1_after = _j2.loads(v1_store.to_json_bytes())
    assert set(obj_v1_after) == {"tree", "sigs"} and obj_v1_after["sigs"] == {}

    # ---- rename / remove 同步 sigs ----
    rs = CompositeCardStore.create_empty()
    rs.add_list("卡A", sl_v2, signature=sig)
    rs.rename("卡A", "卡B")
    assert "卡B" in rs.sigs and "卡A" not in rs.sigs
    assert rs.get_signature("卡B").input_names() == ["x"]
    rs.remove("卡B")
    assert rs.paths() == [] and rs.sigs == {}

    # ---- 非规范路径（// 折叠）签名键归一化：写 组//卡、读 组/卡 均能取到 ----
    nc = CompositeCardStore.create_empty()
    nc.add_list("组//卡", sl_v2, signature=sig)
    assert nc.get_signature("组/卡").input_names() == ["x"]
    nc.remove("组/卡")
    assert nc.sigs == {} and nc.paths() == []

    # ---- 组 rename/remove 级联子树签名 ----
    gc = CompositeCardStore.create_empty()
    gc.add_group("组")
    gc.add_list("组/子卡", sl_v2, signature=sig)
    gc.rename("组", "改名组")
    assert gc.get_signature("改名组/子卡").input_names() == ["x"]  # 子树签名跟随
    assert "组/子卡" not in gc.sigs
    gc.remove("改名组")
    assert gc.sigs == {} and gc.paths() == []                    # 子树签名清空

    # ---- 结构校验仍抛：顶层非对象 / 节点值非法 / 键含 / ----
    try:
        CompositeCardStore.from_json(b'[1,2,3]', mgr)
        raise AssertionError("顶层非对象应抛 ValueError")
    except ValueError:
        pass
    try:
        CompositeCardStore.from_json({"x": 123}, mgr)   # v1 视图：节点值非法
        raise AssertionError("节点值非法应抛 ValueError")
    except ValueError:
        pass
    # 包装格式但 tree 节点非法
    try:
        CompositeCardStore.from_json({"tree": {"x": 123}}, mgr)
        raise AssertionError("tree 节点非法应抛 ValueError")
    except ValueError:
        pass

    # ---- get_or_none：组 / 不存在 → None ----
    assert store.get_or_none("战斗") is None            # 组 → None
    assert store.get_or_none("不存在") is None
    assert store.get_or_none("") is None
```

Keep the existing structural assertions that still hold (paths, walk, remove, rename basic, get_or_none for v1). Adjust any old `assert store.get("登录流程") is sl_login` → `assert store.get_body("登录流程") is sl_login` (v1 in-memory store, not the round-tripped `s_bytes`). Re-run and fix any leftover old-API assertions the smoke still has — the rule: `get()` now returns `CompositeDefinition`; old `is sl_x` checks become `get_body(...) is sl_x`.

- [ ] **Step 3: Run smoke, verify it passes**

Run: `python -m model.composite_card_store`
Expected: `CompositeCardStore smoke OK`

- [ ] **Step 4: Checkpoint**

`python -m model.composite_card_store` → `CompositeCardStore smoke OK`. Also confirm `python -m model.step_list` still passes (it references `CompositeCard` markers, store unchanged import-wise).

---

## Task 5: `model/composite_card.py` (MODIFY — v2 `CompositeCard`)

**Files:**
- Modify: `model/composite_card.py` (rewrite `CompositeCard` + add `repoint_param_refs`; keep `repoint_refs`)
- Test: extended `__main__` smoke

Backward-compatible ctor: `(ref, tree, package, signature=None, io=None, enabled=True, tag="")`. When `signature` is None/empty → parameterless (v1 path, empty io). When `io` is None → build empty `StepIOWidget([], [], tree, package)`. `from_marker` fetches the signature via `resolve_ref` and builds a drift-tolerant typed io (signature's types + marker's values, type-mismatched `ov` slots left empty → red card).

- [ ] **Step 1: Replace imports + the `CompositeCard` class**

Top imports: add `StepIOWidget` is already imported; add `ProjectVariable`, `CompositeSignature`, `CompositeDefinition`, `build_local_tree`, `base64`, `json`, `List`. Replace the class with:

```python
import base64
import json
import threading
from dataclasses import dataclass
from typing import Callable, List, Optional, TYPE_CHECKING

from model.composite_local_tree import build_local_tree
from model.composite_signature import CompositeSignature, Param
from model.log_model import LogModel
from model.project_variable import ProjectVariable
from model.step import Step, StepStatus
from model.step_io import StepIOWidget

if TYPE_CHECKING:
    from PyQt5.QtWidgets import QWidget
    from model.composite_definition import CompositeDefinition
    from model.kscp_package import KscpPackage
    from model.step_list import StepList
    from model.step_manager import StepManager
    from model.variable_tree import VariableTree

__all__ = ["CompositeCard", "repoint_refs", "repoint_param_refs"]

_MARKER_PREFIX = "@合成卡片:"
_MAX_SUB_STEPS = 10000
_MAX_DEPTH = 32


@dataclass
class _NoIO:
    """空 dataclass：input_class/output_class 哨兵（fields() 得 [] → base input/output no-op）。"""
    pass


class CompositeCard(Step):
    """合成卡片：引用一张命名合成卡片定义、运行时展开执行。

    v1（参数less，空签名）：行为同今天——body 走全局变量树，不换树。
    v2（带签名）：调用点 io 槽 = 签名参数；运行期 input() 建局部树填入参、
    run() 换 body 步骤 io._tree 为局部树（try/finally 恢复）、output() 读
    出参写回调用点绑定的全局目标。纯局部（无全局回退）。
    """

    name = "合成卡片"
    description = "可复用的步骤集合（引用定义，运行时展开执行）"
    input_class = _NoIO
    output_class = _NoIO

    # 解析器：ref -> CompositeDefinition | None（主窗口打开工程时注入 cstore.get_or_none）
    _resolver: Optional[Callable[[str], "Optional[CompositeDefinition]"]] = None
    _stop_event: "threading.Event" = threading.Event()
    _depth_local = threading.local()

    def __init__(self, ref: str, tree: "VariableTree",
                 package: "KscpPackage",
                 signature: Optional[CompositeSignature] = None,
                 io: Optional[StepIOWidget] = None,
                 enabled: bool = True, tag: str = "") -> None:
        sig = signature if signature is not None else CompositeSignature.empty()
        if io is None:
            io = StepIOWidget([], [], tree, package)   # 参数less 空签名 io
        super().__init__(io, enabled, tag)
        self.ref = ref
        self.signature = sig
        self.name = ref.rsplit("/", 1)[-1] if ref else "合成卡片"
        self._global_tree = tree            # 出参写回目标全局树（调用点 io._tree 即此）
        self._package = package
        self._local_tree: Optional["VariableTree"] = None
        self._executed_body = False       # run() 置 True 仅当 body 真正开始执行（软跳过时 output() 不写幻影默认值）
        # 给调用点 io 槽贴参数名标签（参数less 空签名 → set_slot_names([],[]) 无害）
        self.io.set_slot_names(sig.input_names() or None,
                               sig.output_names() or None)

    # ---- 服务定位 / 协作停止 ----
    @classmethod
    def set_resolver(cls, resolver):
        cls._resolver = resolver

    @classmethod
    def resolve_ref(cls, ref: str) -> "Optional[CompositeDefinition]":
        if cls._resolver is None:
            return None
        try:
            return cls._resolver(ref)
        except Exception:
            return None

    @classmethod
    def set_stop_event(cls, event):
        cls._stop_event = event

    # ---- 信息显示 ----
    def info_widget(self, parent=None):
        from PyQt5.QtWidgets import QLabel
        lbl = QLabel("合成卡片 → %s" % self.ref, parent)
        lbl.setWordWrap(True)
        return lbl

    # ---- 引用标记编解码 ----
    def to_format_string(self) -> str:
        io_fmt = self.io.to_format_string()
        # 参数less（空签名 io 空槽）→ to_format_string 仍非空串；但空签名不该带 :io
        if self.signature.is_empty() and not self.io.input_types and not self.io.output_types:
            return _MARKER_PREFIX + self.ref
        return _MARKER_PREFIX + self.ref + ":" + io_fmt

    @staticmethod
    def is_marker(fmt: str) -> bool:
        return isinstance(fmt, str) and fmt.startswith(_MARKER_PREFIX)

    @classmethod
    def marker_for(cls, ref: str) -> str:
        return _MARKER_PREFIX + ref

    @classmethod
    def from_marker(cls, fmt: str, manager: "StepManager") -> "CompositeCard":
        """由标记还原；非标记/空 ref → ValueError。

        带参标记 ``@合成卡片:<ref>:<io_b64>``：经解析器取签名 → 按签名建类型化
        io → 回填 marker 内的 iv/ov 值（类型不符的 ov 置空 → 红卡可定位）。
        无解析器/签名空 → 参数less 空签名 io（v1）。
        """
        if not cls.is_marker(fmt):
            raise ValueError("不是合成卡片引用标记: %r" % (fmt,))
        rest = fmt[len(_MARKER_PREFIX):]
        if not rest:
            raise ValueError("合成卡片引用路径为空: %r" % (fmt,))
        # 拆 ref 与可选 io_fmt（ref 不含 ":"，路径段无 ":"）
        if ":" in rest:
            ref, io_fmt = rest.split(":", 1)
        else:
            ref, io_fmt = rest, ""
        if not ref:
            raise ValueError("合成卡片引用路径为空: %r" % (fmt,))
        # 取签名（运行期解析器；加载期 from_marker 时 sigs 已预加载）
        sig = CompositeSignature.empty()
        defn = CompositeCard.resolve_ref(ref)
        if defn is not None:
            sig = defn.signature
        tree = manager.tree
        package = manager.package
        if sig.is_empty() or not io_fmt:
            # 参数less（v1 或 v2 空签名）
            return cls(ref, tree, package, signature=sig)
        # 带参：按签名建类型化 io，回填 marker 的 iv/ov（类型按签名，值取 marker）
        io = StepIOWidget(sig.input_types(), sig.output_types(), tree, package)
        try:
            src = StepIOWidget.from_format_string(io_fmt, tree, package)
            # iv/ov 数量与签名不符（签名漂移）→ 按签名长度取/补空
            iv = list(src._input_values)[:len(sig.inputs)]
            while len(iv) < len(sig.inputs):
                iv.append("")
            ov = list(src._output_values)[:len(sig.outputs)]
            while len(ov) < len(sig.outputs):
                ov.append("")
            io._input_values = iv
            io._output_values = ov
        except ValueError:
            # marker 内 io_fmt 非法 → 退化为空值 io（红卡可定位，不崩）；记日志便于诊断
            LogModel.instance().error(
                "合成卡片标记内 io 串非法，已退化为空值 io（红卡可定位）: %s" % io_fmt)
        return cls(ref, tree, package, signature=sig, io=io)

    # ---- 执行流程（覆写 input/run/output）----
    def input(self) -> None:
        if self.signature.is_empty():
            return                       # 参数less → no-op（base input() 也 no-op）
        values = self.io.resolve_inputs()           # 调用点绑定值（常量/{{全局}}）
        self._local_tree = build_local_tree(self.signature, self._package)
        for p, val in zip(self.signature.inputs, values):
            self._local_tree.set(
                p.name, ProjectVariable.create(p.type, val, self._package))

    def run(self) -> int:
        self._executed_body = False       # 复位：软跳过路径（悬空/递归/空体）保持 False → output() 不写
        defn = CompositeCard.resolve_ref(self.ref)
        if defn is None or defn.body is None:
            LogModel.instance().error("合成卡片引用不存在: %s" % self.ref)
            self.status = StepStatus.ERROR
            return 1
        depth = getattr(CompositeCard._depth_local, "depth", 0) + 1
        if depth > _MAX_DEPTH:
            LogModel.instance().error(
                "合成卡片递归过深（>%d，疑似循环引用）: %s"
                % (_MAX_DEPTH, self.ref))
            self.status = StepStatus.ERROR
            return 1
        CompositeCard._depth_local.depth = depth
        body = defn.body
        try:
            prog = body.do_methods()
            if not prog:
                return 1
            for s in body.steps:
                s.status = StepStatus.PENDING
            self._executed_body = True    # body 即将开始执行（过了 not prog 检查）
            if self.signature.is_empty():
                # 参数less：不换树，body 走全局（同 v1）
                return self._run_body(prog, body)
            # 带参：换 body 步骤 io._tree 为局部树
            saved = [s.io._tree for s in body.steps]
            for s in body.steps:
                s.io._tree = self._local_tree
            try:
                return self._run_body(prog, body)
            finally:
                for s, t in zip(body.steps, saved):
                    s.io._tree = t
        finally:
            CompositeCard._depth_local.depth = depth - 1

    def _run_body(self, prog, body) -> int:
        """mini pc+偏移循环（照搬 v1 语义；供 run 复用）。"""
        pc = 0
        steps_done = 0
        while pc < len(prog) and not CompositeCard._stop_event.is_set():
            steps_done += 1
            if steps_done > _MAX_SUB_STEPS:
                LogModel.instance().error(
                    "合成卡片体内执行步数超过上限 %d，已停止: %s"
                    % (_MAX_SUB_STEPS, self.ref))
                self.status = StepStatus.ERROR
                return 1
            offset = prog[pc]()
            pc += offset
            if pc < 0:
                pc = 0
        return 1

    def output(self) -> None:
        # 空签名（v1）/ body 未真正执行（软跳过：悬空、递归过深、空体）/ ERROR 态 →
        # 不写出参（避免把 build_local_tree 预填的类型默认值 0/"" 幻影写回全局目标）
        if (self.signature.is_empty() or not self._executed_body
                or self.status is StepStatus.ERROR):
            return
        outs = [self._local_tree.get(p.name) for p in self.signature.outputs]
        self.io.write_outputs([v.data for v in outs])   # 写回调用点绑定的全局目标
        self._local_tree = None


def repoint_refs(store, old_path: str, new_path: str) -> int:
    """把 store 内引用 old_path 的合成卡片改指 new_path。

    兼容两类 store：``CompositeCardStore``（v2，``get_body``→StepList）与
    ``StepListStore``（v1，``get``→StepList）——鸭子类型取 ``get_body``，无则退
    ``get``。这样步骤列表（step_list.json，引用条目的主存放处）与合成卡片定义体
    （composites.json，体内嵌套引用）两处改指都能用同一函数。
    """
    count = 0
    new_leaf = new_path.rsplit("/", 1)[-1] if new_path else "合成卡片"
    for path, is_group in store.walk():
        if is_group:
            continue
        try:
            sl = store.get_body(path) if hasattr(store, "get_body") else store.get(path)
        except FileNotFoundError:
            continue
        for step in sl.steps:
            if isinstance(step, CompositeCard) and step.ref == old_path:
                step.ref = new_path
                step.name = new_leaf
                count += 1
    return count


def repoint_param_refs(body: "StepList",
                      old_sig: CompositeSignature,
                      new_sig: CompositeSignature) -> int:
    """改名参数后，改指 body 步骤 io 槽引用旧参数名的绑定；返回改动数。

    按位置对齐（签名表改名=原地编辑名）。**仅在段长度不变时**改指：增删参数（长
    度变）→ 位置对齐不可靠 → 跳过该段改指（绑定悬空 → 运行期 ERROR 可定位），
    符合 spec §6「删参数 → 不改；绑定悬空」。删除的参数仍被 body 引用 → 该引用
    悬空（resolve_inputs 抛 → 步骤 ERROR）——签名表删行时弹确认。
    """
    count = 0
    in_renames = {}
    if len(old_sig.inputs) == len(new_sig.inputs):
        for a, b in zip(old_sig.inputs, new_sig.inputs):
            if a.name != b.name:
                in_renames[a.name] = b.name
    else:
        LogModel.instance().error(
            "合成卡片输入参数个数已改变（增删），已跳过输入改指（绑定可能悬空）")
    out_renames = {}
    if len(old_sig.outputs) == len(new_sig.outputs):
        for a, b in zip(old_sig.outputs, new_sig.outputs):
            if a.name != b.name:
                out_renames[a.name] = b.name
    else:
        LogModel.instance().error(
            "合成卡片输出参数个数已改变（增删），已跳过输出改指（绑定可能悬空）")
    if not in_renames and not out_renames:
        return 0
    for step in body.steps:
        io = step.io
        for i in range(len(io._input_values)):
            val = io._input_values[i]
            if not isinstance(val, str):
                continue
            for old, new in in_renames.items():
                if val == "{{%s}}" % old:
                    io.change_value("input", i, "{{%s}}" % new)
                    count += 1
                    break
        for i in range(len(io._output_values)):
            val = io._output_values[i]
            if val in out_renames:
                io.change_value("output", i, out_renames[val])
                count += 1
    return count
```

- [ ] **Step 2: Extend the `__main__` smoke for v2**

Add (after the existing v1 smoke, before `print("CompositeCard smoke OK")`):

```python
    # ---- v2 带参：marker 含 io_b64；from_marker 取签名建类型化 io ----
    from model.composite_signature import CompositeSignature, Param
    from model.composite_definition import CompositeDefinition
    from model.composite_card_store import CompositeCardStore

    sig = CompositeSignature(inputs=[Param("x", "number")],
                              outputs=[Param("y", "number")])
    bodyP = StepList.create_empty()
    # body 用一个探针：x*2 → y（体内引用局部 x/y）
    @dataclass
    class _DIn:
        n: "number" = 0
    @dataclass
    class _DOut:
        m: "number" = 0
    class _Double(Step):
        name = "翻倍"
        description = "y = x*2"
        input_class = _DIn
        output_class = _DOut
        def run(self):
            self.outputs.m = self.inputs.n * 2
            return 1
    dstep = _Double.create_default(tree, pkg)
    dstep.io.set_slot_names(["x"], ["y"])        # 标签贴参数名（编辑期由 picker 包办）
    dstep.io.change_value("input", 0, "{{x}}")   # 输入槽绑局部 x
    dstep.io.change_value("output", 0, "y")      # 输出槽绑局部 y
    bodyP.add(dstep)

    cstore = CompositeCardStore.create_empty()
    cstore.add_list("加倍卡", bodyP, signature=sig)
    CompositeCard.set_resolver(lambda ref: cstore.get_or_none(ref))

    # 调用点：入参 x=5，出参写回全局 n1
    call = CompositeCard("加倍卡", tree, pkg, signature=sig,
                         io=StepIOWidget(["number"], ["number"], tree, pkg))
    call.io.change_value("input", 0, "5")
    call.io.change_value("output", 0, "n1")
    fmt = call.to_format_string()
    assert fmt == "@合成卡片:加倍卡:" + call.io.to_format_string(), fmt
    assert CompositeCard.is_marker(fmt)
    # from_marker 往返：取签名建 io，iv/ov 回填
    back = CompositeCard.from_marker(fmt, mgr)
    assert isinstance(back, CompositeCard) and back.ref == "加倍卡"
    assert back.signature.input_names() == ["x"]
    assert back.io.input_types == ["number"] and back.io.output_types == ["number"]
    assert back.io._input_values == ["5"] and back.io._output_values == ["n1"]
    # 端到端：do() → body 在局部树跑 → y=10 → 写回 n1
    assert back.do() == 1
    assert back.status is StepStatus.FINISHED
    assert tree.get("n1").data == 10

    # 纯局部：body 步骤引用全局名 → resolve 抛 → ERROR
    dstep2 = _Double.create_default(tree, pkg)
    dstep2.io.change_value("input", 0, "{{n1}}")   # 误绑全局（局部树无 n1）
    dstep2.io.change_value("output", 0, "y")
    bodyBad = StepList.create_empty(); bodyBad.add(dstep2)
    cstoreB = CompositeCardStore.create_empty(); cstoreB.add_list("坏卡", bodyBad, signature=sig)
    CompositeCard.set_resolver(lambda ref: cstoreB.get_or_none(ref))
    callB = CompositeCard("坏卡", tree, pkg, signature=sig,
                          io=StepIOWidget(["number"], ["number"], tree, pkg))
    callB.io.change_value("input", 0, "5")
    callB.io.change_value("output", 0, "n1")
    LogModel.instance().clear()
    try:
        callB.do()
    except Exception:
        pass   # body 步骤 resolve_inputs 抛 FileNotFoundError → do 置 ERROR 重抛
    assert callB.status is StepStatus.ERROR

    # 换树 try/finally 恢复：body 抛错后 body 步骤 io._tree 复位全局
    saved_tree = dstep2.io._tree
    # 上面 do() 抛错后 io._tree 应仍是全局树（finally 恢复）
    assert dstep2.io._tree is saved_tree

    # 签名漂移：旧 marker（1 入 1 出）+ 新签名（2 出）→ 多出的 ov 置空（红卡）
    sig2 = CompositeSignature(inputs=[Param("x", "number")],
                              outputs=[Param("y", "number"), Param("z", "number")])
    bodyP2 = StepList.create_empty()
    d2 = _Double.create_default(tree, pkg)
    d2.io.change_value("input", 0, "{{x}}")
    d2.io.change_value("output", 0, "y")
    bodyP2.add(d2)
    cstoreC = CompositeCardStore.create_empty(); cstoreC.add_list("漂移卡", bodyP2, signature=sig2)
    CompositeCard.set_resolver(lambda ref: cstoreC.get_or_none(ref))
    callC = CompositeCard("漂移卡", tree, pkg, signature=sig2,
                          io=StepIOWidget(["number"], ["number", "number"], tree, pkg))
    callC.io.change_value("input", 0, "5")
    callC.io.change_value("output", 0, "n1")
    callC.io.change_value("output", 1, "")        # 第二输出未绑 → 不合规
    assert not callC.io.is_valid

    # ---- repoint_param_refs：改名参数后改指 body 引用 ----
    bodyR = StepList.create_empty()
    dr = _Double.create_default(tree, pkg)
    dr.io.change_value("input", 0, "{{x}}")
    dr.io.change_value("output", 0, "y")
    bodyR.add(dr)
    old_sig = CompositeSignature(inputs=[Param("x", "number")],
                                outputs=[Param("y", "number")])
    new_sig = CompositeSignature(inputs=[Param("a", "number")],
                                 outputs=[Param("b", "number")])
    n = repoint_param_refs(bodyR, old_sig, new_sig)
    assert n == 2
    assert dr.io._input_values[0] == "{{a}}"
    assert dr.io._output_values[0] == "b"

    # ---- 删参数（长度变）→ 位置对齐不可靠 → 跳过改指，旧绑定悬空 ----
    bodyD = StepList.create_empty()
    dd = _Double.create_default(tree, pkg)
    dd.io.change_value("input", 0, "{{x}}")
    dd.io.change_value("output", 0, "y")
    bodyD.add(dd)
    old_del = CompositeSignature(inputs=[Param("x", "number"), Param("y", "number")],
                                  outputs=[Param("z", "number")])
    new_del = CompositeSignature(inputs=[Param("y", "number")],   # 删了 x（2→1）
                                  outputs=[Param("z", "number")])
    LogModel.instance().clear()
    n_del = repoint_param_refs(bodyD, old_del, new_del)
    assert n_del == 0                                    # 长度变 → 跳过，未改指
    assert dd.io._input_values[0] == "{{x}}"             # 仍指 x（悬空，未误改指 y）
    assert any("个数已改变" in e.message for e in LogModel.instance().entries)

    # ---- 软跳过（空体 / 悬空）→ output() 不写幻影默认值到全局目标 ----
    tree.set("n1", ProjectVariable.create("number", 999, pkg))
    bodyE = StepList.create_empty()                      # 空体
    cstoreE = CompositeCardStore.create_empty(); cstoreE.add_list("空体卡", bodyE, signature=sig)
    CompositeCard.set_resolver(lambda ref: cstoreE.get_or_none(ref))
    callE = CompositeCard("空体卡", tree, pkg, signature=sig,
                          io=StepIOWidget(["number"], ["number"], tree, pkg))
    callE.io.change_value("input", 0, "5")
    callE.io.change_value("output", 0, "n1")
    callE.do()
    assert tree.get("n1").data == 999                    # 未被幻影默认 0 覆盖
    tree.set("n1", ProjectVariable.create("number", 777, pkg))
    CompositeCard.set_resolver(lambda ref: None)        # 定义全删
    callG = CompositeCard("已删卡", tree, pkg, signature=sig,
                          io=StepIOWidget(["number"], ["number"], tree, pkg))
    callG.io.change_value("input", 0, "5")
    callG.io.change_value("output", 0, "n1")
    LogModel.instance().clear()
    callG.do()
    assert callG.status is StepStatus.ERROR
    assert tree.get("n1").data == 777                   # 未被幻影默认 0 覆盖

    # v1 参数less 回归（空签名 → 行为同今天，marker 无 :io）
    v1c = CompositeCard("组/卡片A", tree, pkg)
    assert v1c.signature.is_empty()
    assert v1c.to_format_string() == "@合成卡片:组/卡片A"
    CompositeCard.set_resolver(lambda ref: None)   # 复位
```

- [ ] **Step 3: Run smoke, fix leftover issues, verify it passes**

Run: `python -m model.composite_card`
Expected: `CompositeCard smoke OK`. **The existing v1 smoke is NOT untouched** — the v2 contract change (spec §3.4: resolver now returns `CompositeDefinition`, not raw `StepList`) requires updating the v1 smoke's three runtime resolvers (`bodyA`/`bodySelf`/`bodyStop` lines: `set_resolver(lambda ref: bodyX if ref == ... else None)`) to wrap their `StepList` in `CompositeDefinition(bodyX, CompositeSignature.empty())`. Add `from model.composite_definition import CompositeDefinition` to the smoke header (CompositeSignature/Param are already module-level). The v1 `repoint_refs` test stays on `StepListStore` as-is — `repoint_refs` is duck-typed (`get_body` if present else `get`) so it works on both stores. Also drop the now-unused module imports `base64`/`json`/`List` (the v2 marker embeds the raw io format string, not base64).

- [ ] **Step 4: Checkpoint**

`python -m model.composite_card` → `CompositeCard smoke OK`. Also `python -m model.step_list` (uses `CompositeCard.from_marker`) still passes.

---

## Task 6: `widgets/composite_signature_widget.py` (NEW)

**Files:**
- Create: `widgets/composite_signature_widget.py`
- Test: its own `__main__` smoke

A `QWidget` with 3 sections (输入/输出/局部). Each section: a labeled `QTableWidget` (columns: 名 / 类型 [/ 默认值 for locals]) + add/remove buttons. Emits `signature_changed(CompositeSignature)` only when the current edit is a *valid* signature (invalid rows → no emit). `set_signature(sig)` loads an existing signature into the tables.

- [ ] **Step 1: Write the module + smoke**

Create `widgets/composite_signature_widget.py`:

```python
# -*- coding: utf-8 -*-
"""
合成卡片签名编辑器（输入/输出/局部 三段表）
==========================================

:class:`CompositeSignatureWidget` 是一个 QWidget：三段表（输入/输出/局部），
每行 名(QLineEdit) / 类型(下拉 supported_types) / 局部多 默认值(QLineEdit)。
编辑产生**合法**签名时发 :attr:`signature_changed`；非法态不发（不落盘非法）。
"""
from typing import Optional

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import (
    QComboBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QPushButton,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from model.composite_signature import CompositeSignature, LocalVar, Param
from model.project_variable import ProjectVariable

__all__ = ["CompositeSignatureWidget"]


class _Section(QWidget):
    """一段表（输入/输出/局部）：QTableWidget + 增删行。"""

    def __init__(self, title: str, with_default: bool, parent: QWidget) -> None:
        super().__init__(parent)
        self._with_default = with_default
        cols = ["名", "类型"] + (["默认值"] if with_default else [])
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)
        head = QHBoxLayout()
        head.addWidget(QLabel(title))
        head.addStretch(1)
        b_add = QPushButton("+")
        b_add.setFixedWidth(28)
        b_rem = QPushButton("−")
        b_rem.setFixedWidth(28)
        head.addWidget(b_rem)
        head.addWidget(b_add)
        lay.addLayout(head)
        self._tw = QTableWidget(0, len(cols))
        self._tw.setHorizontalHeaderLabels(cols)
        self._tw.verticalHeader().setVisible(False)
        h = self._tw.horizontalHeader()
        if h is not None:
            h.setSectionResizeMode(QHeaderView.Stretch)
        self._types = ProjectVariable.supported_types()
        lay.addWidget(self._tw)
        b_add.clicked.connect(lambda: self._add_row(""))
        b_rem.clicked.connect(self._remove_selected)
        self._on_changed = None   # 宿主注入的变更回调

    def set_on_changed(self, cb) -> None:
        self._on_changed = cb

    def _add_row(self, name: str = "", vtype: str = "", default: str = "") -> None:
        r = self._tw.rowCount()
        self._tw.insertRow(r)
        name_item = QTableWidgetItem(name)
        self._tw.setItem(r, 0, name_item)
        combo = QComboBox()
        for t in self._types:
            combo.addItem(t)
        if vtype in self._types:
            combo.setCurrentText(vtype)
        self._tw.setCellWidget(r, 1, combo)
        if self._with_default:
            self._tw.setItem(r, 2, QTableWidgetItem(default))
        # 编辑即通知
        name_item.textChanged.connect(self._notify)
        combo.currentTextChanged.connect(self._notify)
        if self._with_default:
            self._tw.item(r, 2).textChanged.connect(self._notify)
        self._notify()

    def _remove_selected(self) -> None:
        r = self._tw.currentRow()
        if r >= 0:
            self._tw.removeRow(r)
            self._notify()

    def _notify(self, *_a) -> None:
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
        """返回 (List[Param] 或 List[LocalVar], ok: bool)。ok=False 表示有非法行。"""
        out = []
        ok = True
        for r in range(self._tw.rowCount()):
            name_item = self._tw.item(r, 0)
            name = name_item.text().strip() if name_item is not None else ""
            combo = self._tw.cellWidget(r, 1)
            vtype = combo.currentText() if combo is not None else ""
            if not name or not vtype:
                ok = False
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
        self._in = _Section("输入", False, self)
        self._out = _Section("输出", False, self)
        self._loc = _Section("局部", True, self)
        self._in.set_on_changed(self._maybe_emit)
        self._out.set_on_changed(self._maybe_emit)
        self._loc.set_on_changed(self._maybe_emit)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(4)
        lay.addWidget(self._in)
        lay.addWidget(self._out)
        lay.addWidget(self._loc)
        lay.addStretch(1)

    def set_signature(self, sig: CompositeSignature) -> None:
        self._in.load(sig.inputs)
        self._out.load(sig.outputs)
        self._loc.load(sig.locals)

    def _maybe_emit(self, *_a) -> None:
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


# ================================================================
# 冒烟演示：直接 ``python -m widgets.composite_signature_widget`` 运行
# ================================================================
if __name__ == "__main__":
    import sys
    from PyQt5.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(sys.argv)
    from model.composite_signature import Param, LocalVar

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
    # set_signature 不发 changed（程序化装载，非用户编辑）
    # 但 _add_row 在 load 内触发 _notify → 发；清理：
    received.clear()

    # 用户编辑：加一行输入 → 发合法签名
    w._in._add_row("a", "string")
    assert len(received) >= 1
    last = received[-1]
    assert last.input_names() == ["x", "a"] and last.output_names() == ["y"]
    # 非法行（空名）→ 不发
    n0 = len(received)
    w._in._add_row("", "number")   # 空名 → collect ok=False → 不发
    assert len(received) == n0
    # 删行 → 发
    w._in._tw.setCurrentCell(2, 0)
    w._in._remove_selected()
    assert received[-1].input_names() == ["x"]

    # 跨段重名 → validate 失败 → 不发
    n1 = len(received)
    w._loc._add_row("x", "number", "0")   # x 与输入 x 重名
    assert len(received) == n1, received[n1:]
    # current_signature：读当前态（非法行丢弃）
    cur = w.current_signature()
    assert "x" in cur.input_names()

    print("CompositeSignatureWidget smoke OK")
```

> `set_signature` calls `_add_row` which calls `_notify` → emits during load. The smoke clears `received` right after. If you want load to be silent, set a `_loading` guard in `_maybe_emit`. **Add the guard** — it's cleaner: in `CompositeSignatureWidget.__init__` add `self._loading = False`; in `set_signature` wrap `self._loading = True` / `...` / `self._loading = False`; in `_maybe_emit` first line `if self._loading: return`. Apply this guard (recommended) — then the `received.clear()` line can stay or go.

- [ ] **Step 2: Add the `_loading` guard (recommended refinement)**

Edit `CompositeSignatureWidget`: add `self._loading = False` in `__init__`; in `set_signature` set `self._loading = True` before the three `load` calls and `False` after; in `_maybe_emit` add `if self._loading: return` as the first line. (Keeps programmatic loads silent.)

- [ ] **Step 3: Run smoke, verify it passes**

Run: `python -m widgets.composite_signature_widget`
Expected: `CompositeSignatureWidget smoke OK`

- [ ] **Step 4: Checkpoint**

`python -m widgets.composite_signature_widget` → `CompositeSignatureWidget smoke OK`.

---

## Task 7: `widgets/composite_local_picker.py` (NEW)

**Files:**
- Create: `widgets/composite_local_picker.py`
- Test: its own `__main__` smoke

`make_composite_local_picker(signature, on_new) -> picker`. The picker (signature `picker(tree, vtype, parent) -> name|None`) ignores `tree`, pops a `QMenu` listing signature params whose type matches `vtype` (labeled 入参/出参/局部) + a "新建局部变量…" entry → small dialog (name/type/default) → calls `on_new(name, type, default)` → returns `name`. Returns the bare name (the `io._pick_input` wraps inputs as `{{name}}`; outputs store bare).

- [ ] **Step 1: Write the module + smoke**

Create `widgets/composite_local_picker.py`:

```python
# -*- coding: utf-8 -*-
"""
合成卡片局部变量选择器（picker 钩子闭包）
========================================

:func:`make_composite_local_picker` 返回一个符合 ``StepIOWidget.picker`` 钩子
签名 ``(tree, vtype, parent) -> name|None`` 的闭包：弹菜单列出签名中类型匹配
``vtype`` 的输入/输出/局部参数（标「入参/出参/局部」），末项「新建局部变量…」
→ 小对话框（名/类型/默认值）→ 调 ``on_new`` 加进签名局部段 → 返回新参数名。

返回**裸名**（如 ``x``）：输入槽由 ``StepIOWidget._pick_input`` 包成 ``{{x}}``，
输出槽存裸名（= 局部树路径）。``tree`` 参数忽略（纯局部，不经全局树）。
"""
from typing import Callable, Optional

from PyQt5.QtWidgets import (
    QDialog, QDialogButtonBox, QFormLayout, QLineEdit, QMenu, QWidget,
)

from model.composite_signature import CompositeSignature
from model.project_variable import ProjectVariable

__all__ = ["make_composite_local_picker"]


def make_composite_local_picker(
        signature: CompositeSignature,
        on_new: Callable[[str, str, object], None]
) -> Callable[..., Optional[str]]:
    """返回 picker 闭包。``on_new(name, type, default)`` 由宿主实现（加局部段 + 落盘）。"""
    def picker(_tree, vtype: str, parent: QWidget) -> Optional[str]:
        menu = QMenu(parent)
        items = []   # (显示文本, 裸名)
        for p in signature.inputs:
            if p.type == vtype or (vtype == "string" and p.type == "number"):
                items.append(("入参·%s" % p.name, p.name))
        for p in signature.outputs:
            if p.type == vtype or (vtype == "string" and p.type == "number"):
                items.append(("出参·%s" % p.name, p.name))
        for v in signature.locals:
            if v.type == vtype or (vtype == "string" and v.type == "number"):
                items.append(("局部·%s" % v.name, v.name))
        for label, name in items:
            menu.addAction(label, lambda n=name: n)   # 闭包捕获 n
        menu.addSeparator()
        menu.addAction("新建局部变量…", lambda: None)   # 占位，下方特判
        act = menu.exec_(parent.mapToGlobal(parent.rect().center()) if parent is not None else None)
        if act is None:
            return None
        if act.text() == "新建局部变量…":
            return _new_local_dialog(vtype, on_new, parent)
        # 取出裸名（去掉「入参·」等前缀）
        return act.text().split("·", 1)[-1]
    return picker


def _new_local_dialog(vtype: str, on_new, parent) -> Optional[str]:
    dlg = QDialog(parent)
    dlg.setWindowTitle("新建局部变量")
    lay = QFormLayout(dlg)
    name_edit = QLineEdit()
    type_edit = QLineEdit(vtype)
    type_edit.setReadOnly(True)   # 预填当前槽位类型
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

    sig = CompositeSignature(inputs=[Param("x", "number")],
                             outputs=[Param("y", "number")],
                             locals=[LocalVar("t", "number", 0)])
    created = []
    picker = make_composite_local_picker(sig, lambda n, t, d: created.append((n, t, d)))

    # 类型过滤：number 槽列出 x/y/t；string 槽也兼容 number → 同列（无 string 参数）
    # 用打桩 QMenu.exec_：返回首项
    import PyQt5.QtWidgets as _W
    orig_exec = _W.QMenu.exec_
    calls = []

    class _StubAct:
        def __init__(self, text): self._t = text
        def text(self): return self._t
    _W.QMenu.exec_ = lambda self, *a, **k: (calls.append([a[0] if a else None]),
                                           _StubAct("入参·x"))[1]
    try:
        name = picker(None, "number", None)
        assert name == "x", name
        # 选「新建局部变量…」→ 弹对话框；打桩对话框直接 accept（名=zz）
        _W.QMenu.exec_ = lambda self, *a, **k: _StubAct("新建局部变量…")
        orig_dlg = QDialog.exec_
        QDialog.exec_ = lambda self: QDialog.Accepted
        # 预填名：在 dlg 建好后注入（_new_local_dialog 内部建 dlg → exec_ 返回 Accepted）
        # 由于 name_edit 默认空 → on_new 不被调（空名返回 None）
        name2 = picker(None, "number", None)
        assert name2 is None              # 空名 → None
    finally:
        _W.QMenu.exec_ = orig_exec
        QDialog.exec_ = orig_dlg
    # on_new 回调
    assert created == [], created          # 空名未触发 on_new

    print("CompositeLocalPicker smoke OK")
```

> The smoke is intricate due to modal-dialog stubbing. If the `name2` path is flaky under stubbing, simplify: just assert the picker returns `"x"` for the first stub and that `created` stays empty for the empty-name path. The essential behavior (type-filter list + return bare name) is what matters; the "新建" dialog is UI-tested manually.

- [ ] **Step 2: Run smoke, verify it passes**

Run: `python -m widgets.composite_local_picker`
Expected: `CompositeLocalPicker smoke OK`. (If the dialog-stub path is flaky, simplify the smoke to only the first stub assertion — note it in a comment.)

- [ ] **Step 3: Checkpoint**

`python -m widgets.composite_local_picker` → `CompositeLocalPicker smoke OK`.

---

## Task 8: `widgets/management_trees.py` (MODIFY — `CompositeManagementTree` v2)

**Files:**
- Modify: `widgets/management_trees.py` (`CompositeManagementTree` + its smoke section)
- Test: extended `__main__` smoke

Changes: `preview_widget()` returns a container (signature widget on top + `StepListHost` below). `_on_selected` uses `get_body`+`get_signature`, loads the signature widget, injects the local picker on body steps, then `host.set_list`. Add `_on_signature_changed` (update sigs + `repoint_param_refs` + rebuild picker + refresh host). `_on_store_changed` uses `get_body`.

- [ ] **Step 1: Add imports + a `_apply_local_picker` helper**

At the top of `management_trees.py`, add to imports:

```python
from model.composite_signature import CompositeSignature
from model.composite_definition import CompositeDefinition
from widgets.composite_signature_widget import CompositeSignatureWidget
from widgets.composite_local_picker import make_composite_local_picker
from model.composite_card import repoint_param_refs
```

- [ ] **Step 2: Rewrite `CompositeManagementTree` (replace the whole class)**

```python
class CompositeManagementTree(ManagementTree):
    """合成卡片管理树：左树 + 中（签名表 + body 宿主）。

    v2：预览 = 容器（上 CompositeSignatureWidget、下 StepListHost）；选中卡片时
    载入签名 + body，给 body 步骤 io.picker 换成局部选择器（经 io.picker 钩子，
    不改 StepListView）；签名变更 → 更新 sigs + 改指 body 引用 + 重建选择器 + 刷新。
    """

    def __init__(self, package, tree, mgr, composite_store, clipboard=None,
                 on_rename=None, parent=None):
        super().__init__("合成卡片")
        self._package = package
        self._tree = tree
        self._mgr = mgr if mgr is not None else StepManager(package, tree)
        if mgr is None:
            self._mgr.load()
        self._cstore = composite_store
        self._clipboard = clipboard if clipboard is not None else StepClipboard()
        self._on_rename_cb = on_rename
        self._sl_tree = None
        self._host = None
        self._sig_widget = None
        self._container = None
        self._current = None
        self._save_timer = None

    @property
    def store(self):
        return self._cstore

    @property
    def current_path(self):
        return self._current

    def set_read_only(self, ro):
        if self._sl_tree is not None:
            self._sl_tree.set_read_only(ro)
        if self._host is not None:
            self._host.set_read_only(ro)
        if self._sig_widget is not None:
            self._sig_widget.setEnabled(not ro)

    def icon(self):
        return make_icon("composite")

    def _save_store(self):
        self._package.write_file("composites.json", self._cstore.to_json_bytes())

    def refresh_cards(self):
        if self._host is not None:
            self._host.refresh_validity()

    def tree_widget(self):
        if self._sl_tree is None:
            self._sl_tree = CompositeTreeWidget(
                self._cstore, self._mgr, self._clipboard,
                self._save_store, self._on_rename_cb, None)
            self._sl_tree.composite_selected.connect(self._on_selected)
            self._sl_tree.store_changed.connect(self._on_store_changed)
        return self._sl_tree

    def _on_edited(self):
        if self._sl_tree is not None:
            self._sl_tree.refresh_error_marks()
        if self._save_timer is None:
            self._save_timer = QTimer()
            self._save_timer.setSingleShot(True)
            self._save_timer.setInterval(500)
            self._save_timer.timeout.connect(self._save_store)
        self._save_timer.start()

    def preview_widget(self):
        if self._container is None:
            self._sig_widget = CompositeSignatureWidget()
            self._sig_widget.signature_changed.connect(self._on_signature_changed)
            self._host = StepListHost(
                self._mgr, self._clipboard, self._on_edited, None,
                composite_store=self._cstore)
            self._host.errors_changed.connect(self._refresh_tree_marks)
            self._container = QWidget()
            lay = QVBoxLayout(self._container)
            lay.setContentsMargins(0, 0, 0, 0)
            lay.setSpacing(0)
            lay.addWidget(self._sig_widget)
            lay.addWidget(self._host, 1)
        return self._container

    def _refresh_tree_marks(self, _n):
        if self._sl_tree is not None:
            self._sl_tree.refresh_error_marks()

    def _apply_local_picker(self, body):
        """给 body 步骤 io.picker 换局部选择器（捕获当前签名）。"""
        sig = (self._cstore.get_signature(self._current)
               if self._current else CompositeSignature.empty())
        picker = make_composite_local_picker(sig, self._on_new_local)
        for s in body.steps:
            s.io.picker = picker

    def _on_new_local(self, name, vtype, default):
        """picker「新建局部变量」→ 加进当前签名局部段 + 落盘 + 刷新。"""
        if self._current is None:
            return
        sig = self._cstore.get_signature(self._current)
        # 避免重名
        if name in sig.slot_names():
            return
        sig.locals.append(LocalVar_proxy(name, vtype, default)) if False else None
        # 直接构造新签名
        from model.composite_signature import LocalVar
        new_sig = CompositeSignature(
            inputs=list(sig.inputs), outputs=list(sig.outputs),
            locals=sig.locals + [LocalVar(name, vtype, default)])
        self._on_signature_changed(new_sig)

    # ---- 宿主联动 ----
    def _on_selected(self, path):
        self._current = path
        if self._host is None:
            return
        try:
            body = self._cstore.get_body(path)
            sig = self._cstore.get_signature(path)
        except FileNotFoundError:
            self._host.set_list(None)
            self._sig_widget.set_signature(CompositeSignature.empty())
            return
        self._sig_widget.set_signature(sig)
        self._apply_local_picker(body)
        self._host.set_list(body, self._mgr, exclude_ref=path)

    def _on_store_changed(self):
        if self._host is None or self._current is None:
            return
        try:
            body = self._cstore.get_body(self._current)
        except FileNotFoundError:
            self._host.set_list(None)
        else:
            self._apply_local_picker(body)
            self._host.set_list(body, self._mgr)

    def _on_signature_changed(self, sig):
        """签名表变更 → 更新 sigs + 改指 body 引用 + 重建选择器 + 刷新卡片。"""
        if self._current is None:
            return
        old = self._cstore.get_signature(self._current)
        self._cstore.set_signature(self._current, sig)
        try:
            body = self._cstore.get_body(self._current)
        except FileNotFoundError:
            return
        repoint_param_refs(body, old, sig)
        self._apply_local_picker(body)          # 捕获新签名重建 picker
        self._host.set_list(body, self._mgr, exclude_ref=self._current)
        self._on_edited()                       # 防抖落盘

    def select_composite(self, ref):
        tw = self.tree_widget()
        it = tw.find_item(ref)
        if it is None:
            return False
        tw.setCurrentItem(it)
        return True

    def repoint_composite_refs(self, old_path, new_path):
        n = repoint_refs(self._cstore, old_path, new_path)
        if n:
            self._save_store()
        return n
```

> **Remove the dead line** `sig.locals.append(LocalVar_proxy(name, vtype, default)) if False else None` in `_on_new_local` — it's a scaffold marker (the real logic is the `new_sig` construction below it). Also remove the unused `from model.composite_signature import LocalVar` inside `_on_new_local` and hoist it to the top imports instead (already added `CompositeSignature`; add `LocalVar` too).

- [ ] **Step 3: Update the `__main__` smoke's `CompositeManagementTree` section**

In the smoke, after `cstore.add_list("登录", body)` + setting up `cmgr`, extend:

```python
    # v2：选中带参卡片 → 签名表载入 + body 宿主 + 局部选择器（不抛）
    from model.composite_signature import Param, CompositeSignature
    sig = CompositeSignature(inputs=[Param("x", "number")],
                             outputs=[Param("y", "number")])
    bodyP = StepList.create_empty()
    cstore.add_list("带参", bodyP, signature=sig)
    ctw = cmgr.tree_widget()
    ctw.refresh()
    ctw.composite_selected.emit("带参")
    assert cmgr.current_path == "带参"
    assert chost.currentIndex() == 1
    # 签名表载入
    assert cmgr._sig_widget._in._tw.rowCount() == 1
    assert cmgr._sig_widget._out._tw.rowCount() == 1
    # 签名变更 → 落盘（防抖到期后）
    new_sig = CompositeSignature(inputs=[Param("a", "number")],
                                 outputs=[Param("b", "number")])
    cmgr._on_signature_changed(new_sig)
    assert cstore.get_signature("带参").input_names() == ["a"]
    # _on_new_local：加局部变量 → 签名局部段 +1
    cmgr._on_new_local("t", "number", 0)
    assert "t" in cstore.get_signature("带参").local_names()
    CompositeCard.set_resolver(lambda ref: None)
```

- [ ] **Step 4: Run smoke, verify it passes**

Run: `python -m widgets.management_trees`
Expected: `management_trees smoke OK`. Fix any leftover old-API references (e.g., the existing v1 smoke line `assert chost._view._step_list is body` for "登录" — still valid since `get_body("登录") is body`).

- [ ] **Step 5: Checkpoint**

`python -m widgets.management_trees` → `management_trees smoke OK`.

---

## Task 9: `widgets/main_widget.py` (MODIFY — `_open_package` reorder)

**Files:**
- Modify: `widgets/main_widget.py:796-804` (the cstore creation block)
- Test: existing `__main__` smoke (no new smoke; verified by smoke_all)

Reorder so the resolver captures the mutable cstore shell BEFORE the in-place load (sigs-first), so `from_marker` during body decode can fetch signatures.

- [ ] **Step 1: Edit the cstore-creation block**

Replace lines 796-804:

```python
        # 合成卡片存储全局共享一份（步骤列表与合成卡片树共用）：
        # 存在 composites.json → 读回；否则空 + 写盘（同 variables.json 套路）
        if package.exists("composites.json"):
            cstore = CompositeCardStore.from_json(
                package.read_file("composites.json"), shared_mgr)
        else:
            cstore = CompositeCardStore.create_empty()
            package.write_file("composites.json", cstore.to_json_bytes())
        # 运行时引用解析：合成卡片 do() 经此取定义体（引用只存指针 → 改一处处处变）
        CompositeCard.set_resolver(cstore.get_or_none)
```

with:

```python
        # 合成卡片存储全局共享一份。v2：先建空壳 + 注入解析器（闭包捕获可变 cstore），
        # 再就地加载（load_from_json 先读 sigs 再走树）——体内合成卡片引用经 from_marker
        # 解码时，解析器即可取到被引卡签名（sigs 已预加载），解加载期先后顺序问题。
        cstore = CompositeCardStore.create_empty()
        CompositeCard.set_resolver(cstore.get_or_none)
        if package.exists("composites.json"):
            cstore.load_from_json(package.read_file("composites.json"), shared_mgr)
        else:
            package.write_file("composites.json", cstore.to_json_bytes())
        # 运行时停止事件桥接（与 StepRunner 共享；合成卡片体内循环每步前检查）
        # （若 main_widget 已有 set_stop_event 注入点则保持；否则此处可省略——v1 未改）
```

- [ ] **Step 2: Run main_widget smoke, verify it passes**

Run: `python -m widgets.main_widget`
Expected: `main_widget smoke OK` (the existing smoke opens a package + builds the CompositeManagementTree; the reorder must not break it). If the existing smoke asserts `CompositeCard.set_resolver` was called with `cstore.get_or_none` — still true (same call, earlier).

- [ ] **Step 3: Checkpoint**

`python -m widgets.main_widget` → `main_widget smoke OK`.

---

## Task 10: `tests/smoke_all.py` (MODIFY — register new modules)

**Files:**
- Modify: `tests/smoke_all.py` (MODULES list)
- Test: `python tests/smoke_all.py`

- [ ] **Step 1: Add the 5 new modules to MODULES**

In `tests/smoke_all.py`, after the existing model block, add (alphabetical-ish within their group):

```python
    "model.composite_card", "model.composite_card_store",
    "model.composite_definition",      # NEW
    "model.composite_local_tree",      # NEW
    "model.composite_signature",       # NEW
    "model.placeholder_step",
```

And in the widgets block:

```python
    "widgets.composite_local_picker",        # NEW
    "widgets.composite_signature_widget",    # NEW
    "widgets.composite_tree_widget",
```

- [ ] **Step 2: Run full regression**

Run: `python tests/smoke_all.py`
Expected: `ALL N SMOKE + 1 CHECKS OK` (N = previous count + 5). No failures.

- [ ] **Step 3: Checkpoint**

`python tests/smoke_all.py` → `ALL N SMOKE + 1 CHECKS OK`.

---

## Task 11: Docs update (requirement #2)

**Files:**
- Modify: `docs/工程分析.md` (composite-card section)
- Modify: `docs/superpowers/specs/2026-09-01-composite-card-params-design.md` (note v2 implemented)

- [ ] **Step 1: Update `docs/工程分析.md`**

In the composite-card section, add a subsection "输入/输出/局部参数（纯局部作用域）" describing: signature table (3 sections), call-site io binds inputs (`{{global}}`/constant) + output targets; runtime builds a local `VariableTree` (`build_local_tree`), swaps body steps' `io._tree` for the run (`try/finally` restore), outputs write back to global targets; storage `{"tree","sigs"}`; marker `@合成卡片:<path>:<io_b64>` (bare for parameterless). One paragraph + the marker/storage examples.

- [ ] **Step 2: Mark the spec as implemented**

In `docs/superpowers/specs/2026-09-01-composite-card-params-design.md`, change the status line `> 状态：已批准（待写实现计划）` → `> 状态：已实现（2026-09-01）；见 plans/2026-09-01-composite-card-params.md`. Add a one-line note under §1 that `composite_tree_widget.py` is in fact unchanged for v2 (signature widget lives in `CompositeManagementTree.preview_widget`), and under §3.2 that the ctor is backward-compatible `(ref, tree, package, signature=None, io=None, …)`.

- [ ] **Step 3: Checkpoint**

Docs updated. (No smoke for docs — verify the markdown renders the examples correctly by eye.)

---

## Self-Review (run after writing, before handing off)

**Spec coverage:** §0 goals → Tasks 1-9. §1 module layout → all 8 modules present (composite_tree_widget correctly treated as unchanged). §2 data model → Tasks 1-2,4. §3 CompositeCard → Task 5. §4 runtime local scope → Task 3+5. §5 editor UI → Tasks 6-8. §6 backward compat + errors → Task 5 (drift/dangling) + Task 4 (v1 compat). §7 testing → every task's smoke + Task 10. §8 docs → Task 11. §9 risks → addressed (try/finally Task 5; drift Task 5; dangling Task 5/`repoint_param_refs`).

**Placeholder scan:** the scaffold markers flagged inline ("remove this dead block" / "remove these two lines") MUST be cleaned during implementation — they are explicit, not hidden TBDs.

**Type consistency:** `CompositeSignature.empty()`/`is_empty()`/`input_names()`/`output_names()`/`slot_names()`/`input_types()`/`output_types()`/`validate()`/`to_json`/`from_json` — used consistently across Tasks 1,3,4,5,6,7,8. `CompositeDefinition(body, signature)` — Tasks 2,4,5. `build_local_tree(sig, package)` — Tasks 3,5. `make_composite_local_picker(signature, on_new)` — Tasks 7,8. `repoint_param_refs(body, old, new)` — Tasks 5,8. `cstore.get_body`/`get_signature`/`set_signature`/`get_or_none`/`add_list(path, body, signature=)`/`load_from_json` — Tasks 4,8,9. `CompositeCard(ref, tree, package, signature=, io=, enabled=, tag=)` — Tasks 5,8. `CompositeSignatureWidget.set_signature`/`signature_changed`/`current_signature` — Tasks 6,8. ✓

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-09-01-composite-card-params.md`. Two execution options:

1. **Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration.
2. **Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints.

Which approach?
