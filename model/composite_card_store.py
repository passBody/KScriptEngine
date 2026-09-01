# -*- coding: utf-8 -*-
"""
合成卡片列表数据模型（纯数据模型）
================================

:class:`CompositeCardStore` 管理所有命名合成卡片定义：按「组（嵌套）+ 卡片」的
字典结构存放，每个合成卡片 = 一个命名 :class:`StepList`（其体内可含普通步骤与
其它合成卡片引用）。支持 JSON 与 ``composites.json`` 之间往返。

``composites.json`` 形态（包装：list 值=合成卡片体内步骤格式串，dict 值=组；
签名旁挂于平铺 ``sigs`` 表）::

    {
        "tree": {
            "登录流程": ["<base64 步骤格式串>", "@合成卡片:组/子卡片", "..."],
            "战斗": {
                "起手": ["<base64 步骤格式串>", "..."]
            }
        },
        "sigs": {
            "登录流程": {"in": [{"name": "x", "type": "number"}],
                        "out": [...], "loc": [...]}
        }
    }

步骤列表（``step_list.json``）里对合成卡片的**引用**存成轻量标记
``@合成卡片:<路径>``（见 :class:`model.composite_card.CompositeCard`），运行时
解码执行——故「改一处定义、所有引用处统统跟着变」（定义单点存于本文件，
引用只存指针）。本模型只管定义体本身的存取；引用标记的编解码在
:class:`StepList` 与 :class:`CompositeCard`。

v1 说明：旧版 ``composites.json`` 顶层直接是树（无 ``tree`` 键），
``from_json``/``load_from_json`` 视为 v1（顶层整树作回 ``tree``，签名全空）。
一旦落盘即升级为包装格式（前向迁移）。

基本用法
--------
::

    from model.composite_card_store import CompositeCardStore

    store = CompositeCardStore.create_empty()
    store.add_list("登录流程", sl)              # 顶层合成卡片
    store.add_group("战斗")                      # 组
    store.add_list("战斗/起手", sl2, signature=sig)   # 组内带签名合成卡片
    pkg.write_file("composites.json", store.to_json_bytes())      # 写回工程资源
    store2 = CompositeCardStore.from_json(pkg.read_file("composites.json"), mgr)
"""

import json
from typing import Any, Callable, Dict, List, Optional, Tuple, Union, TYPE_CHECKING

from model.composite_definition import CompositeDefinition
from model.composite_signature import CompositeSignature
from model.path_util import normalize, validate_name
from model.step_list import StepList

if TYPE_CHECKING:
    from model.step_manager import StepManager

__all__ = ["CompositeCardStore"]

# from_json 接受的输入类型：JSON 串 / 已解析 dict / 字节串（read_file 返回）
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


# ================================================================
# 冒烟演示：直接 ``python -m model.composite_card_store`` 运行
# ================================================================
if __name__ == "__main__":
    import json as _json
    import sys

    from PyQt5.QtWidgets import QApplication

    from model.composite_definition import CompositeDefinition
    from model.composite_signature import CompositeSignature, Param
    from model.kscp_package import KscpPackage
    from model.project_variable import ProjectVariable
    from model.step_list import StepList
    from model.step_manager import StepManager
    from model.variable_tree import VariableTree
    from model.composite_card import CompositeCard

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

    def make_step() -> "Step":
        s = mgr.create_step("示例")
        s.io.change_value("input", 0, "5")
        s.io.change_value("output", 0, "n1")
        return s

    from model.step import Step  # noqa: E402  供类型注解

    # 空 store → 包装格式空树 + 空 sigs（前向迁移后的形态）
    store = CompositeCardStore.create_empty()
    assert (store.paths() == [] and
            _json.loads(store.to_json_bytes()) == {"tree": {}, "sigs": {}})

    # 结构：顶层卡片 + 组 + 组内卡片 + 嵌套组；卡片体内可含普通步骤 + 合成卡片引用
    sl_login = StepList.create_empty()
    sl_login.add(make_step())
    sl_login.add(CompositeCard("战斗/起手", tree, pkg))   # 体内引用其它卡片
    store.add_list("登录流程", sl_login)
    store.add_group("战斗")
    sl_qs = StepList.create_empty()
    sl_qs.add(make_step())
    store.add_list("战斗/起手", sl_qs)
    assert store.paths() == ["战斗/起手", "登录流程"], store.paths()
    assert store.get_body("登录流程") is sl_login
    assert store.get_body("战斗/起手") is sl_qs
    try:
        store.get("战斗")
        raise AssertionError("取组应抛 FileNotFoundError")
    except FileNotFoundError:
        pass

    # 冲突：同名卡片 / 组撞卡片 / 组幂等
    try:
        store.add_list("登录流程", sl_login)
        raise AssertionError("同名卡片应抛 FileExistsError")
    except FileExistsError:
        pass
    try:
        store.add_group("登录流程")
        raise AssertionError("目标已是卡片应抛 FileExistsError")
    except FileExistsError:
        pass
    store.add_group("战斗")           # 已存在且为组 → 幂等

    # 非法路径：空 / 仅斜杠 / .. / 父组不存在 / 祖先为卡片
    for bad in ("", "/", "a/.."):
        try:
            store.add_list(bad, sl_login)
            raise AssertionError("非法路径应抛 ValueError: %r" % bad)
        except ValueError:
            pass
    try:
        store.add_list("不存在组/名", sl_login)
        raise AssertionError("父组不存在应抛 ValueError")
    except ValueError:
        pass
    try:
        store.add_group("登录流程/x")
        raise AssertionError("祖先为卡片应抛 ValueError")
    except ValueError:
        pass

    # 空组
    store.add_group("空组")
    assert _json.loads(store.to_json_bytes())["tree"]["空组"] == {}

    # JSON 三态往返：bytes / str / dict；规范化输出稳定
    raw = store.to_json_bytes()
    assert isinstance(raw, bytes)
    s_bytes = CompositeCardStore.from_json(raw, mgr)
    s_str = CompositeCardStore.from_json(raw.decode("utf-8"), mgr)
    s_dict = CompositeCardStore.from_json(_json.loads(raw), mgr)
    assert s_bytes.to_json_bytes() == raw
    assert s_str.to_json_bytes() == raw
    assert s_dict.to_json_bytes() == raw
    assert s_bytes.paths() == store.paths()
    # 往返后卡片体内仍含合成卡片引用标记（CompositeCard 实例）
    sl_back_login = s_bytes.get_body("登录流程")
    assert isinstance(sl_back_login[1], CompositeCard)
    assert sl_back_login[1].ref == "战斗/起手"

    # v1 树叶子仍是 list；签名旁挂（空签名 → 无 sigs 条目）
    assert isinstance(s_bytes.get_body("登录流程"), StepList)   # get_body 返回 StepList
    # get() 返回 CompositeDefinition
    d_login = s_bytes.get("登录流程")
    assert isinstance(d_login, CompositeDefinition) and d_login.body is sl_back_login
    assert d_login.signature.is_empty()                     # v1 无签名
    # get_body / get_signature
    assert s_bytes.get_body("登录流程") is sl_back_login
    assert s_bytes.get_signature("登录流程").is_empty()

    # ---- v2 带签名：包装格式 {tree, sigs} + 往返 ----
    sig = CompositeSignature(inputs=[Param("x", "number")],
                             outputs=[Param("y", "number")])
    store_sig = CompositeCardStore.create_empty()
    sl_v2 = StepList.create_empty()
    sl_v2.add(make_step())
    store_sig.add_list("带参卡", sl_v2, signature=sig)
    raw_v2 = store_sig.to_json_bytes()
    obj_v2 = _json.loads(raw_v2)
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
    v1_raw = _json.dumps({"登录流程": sl_v2.to_format_strings()},
                         ensure_ascii=False).encode("utf-8")
    v1_store = CompositeCardStore.from_json(v1_raw, mgr)
    assert v1_store.get_signature("登录流程").is_empty()
    assert isinstance(v1_store.get_body("登录流程"), StepList)
    # 落盘后升级为包装格式
    obj_v1_after = _json.loads(v1_store.to_json_bytes())
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
    nc.add_group("组")
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
    try:
        CompositeCardStore.from_json({"a/b": []}, mgr)
        raise AssertionError("键含 '/' 应抛 ValueError")
    except ValueError:
        pass

    # 嵌套深度上限：深层嵌套 → 可控 ValueError（而非 RecursionError）
    deep_s = cur_s = {}
    for _ in range(300):
        nxt = {}
        cur_s["x"] = nxt
        cur_s = nxt
    try:
        CompositeCardStore.from_json(deep_s, mgr)       # dict 输入（不经 json.loads）
        raise AssertionError("过深嵌套应抛 ValueError")
    except ValueError:
        pass

    # ---- 变更扩展：remove / rename / walk / get_or_none ----
    w = store.walk()
    assert [p for p, _g in w] == [
        "登录流程", "战斗", "战斗/起手", "空组"], w
    assert [g for _p, g in w] == [False, True, False, True]

    # remove：删卡片 / 删组（整棵子树）/ 不存在 → FileNotFoundError
    store2 = CompositeCardStore.create_empty()
    store2.add_group("组A")
    store2.add_list("组A/卡片1", sl_login)
    store2.add_list("组A/卡片2", sl_qs)
    store2.remove("组A/卡片1")
    assert "组A/卡片1" not in store2.paths() and "组A/卡片2" in store2.paths()
    store2.remove("组A")                            # 删组 = 整棵子树
    assert store2.paths() == []
    try:
        store2.remove("不存在")
        raise AssertionError("不存在应抛 FileNotFoundError")
    except FileNotFoundError:
        pass

    # rename：改卡片 / 改组（子树保留）/ 保持插入位置 / 非法名 / 不存在 / 重名冲突
    store3 = CompositeCardStore.create_empty()
    store3.add_group("先组")
    store3.add_list("中间卡片", sl_login)
    store3.add_group("后组")
    store3.add_list("后组/子卡片", sl_qs)
    store3.rename("中间卡片", "改名卡片")
    assert list(store3.root) == ["先组", "改名卡片", "后组"]
    store3.rename("后组", "改名组")
    assert "改名组/子卡片" in store3.paths() and store3.get_body("改名组/子卡片") is sl_qs
    for bad in ("", "/", "a/b", ".", ".."):
        try:
            store3.rename("改名卡片", bad)
            raise AssertionError("非法新名应抛 ValueError: %r" % bad)
        except ValueError:
            pass
    try:
        store3.rename("不存在", "x")
        raise AssertionError("不存在应抛 FileNotFoundError")
    except FileNotFoundError:
        pass
    try:
        store3.rename("改名卡片", "先组")
        raise AssertionError("重名冲突应抛 FileExistsError")
    except FileExistsError:
        pass

    # get_or_none：存在 → defn（body=StepList）；不存在/为组 → None（不抛）
    assert store.get_or_none("登录流程").body is sl_login
    assert store.get_or_none("不存在") is None
    assert store.get_or_none("战斗") is None        # 组 → None
    assert store.get_or_none("") is None            # 非法路径 → None

    print("CompositeCardStore smoke OK")
