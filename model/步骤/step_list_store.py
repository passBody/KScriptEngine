# -*- coding: utf-8 -*-
"""
总步骤列表模型（纯数据模型）
============================

:class:`StepListStore` 管理所有命名 :class:`StepList`：按「组（嵌套）+ 列表」
的字典结构存放，支持 JSON 与 ``step_list.json`` 之间往返，并可将全体
可运行步骤的 do 整合为一个列表。

step_list.json 形态（嵌套字典；列表值=步骤列表（格式串），字典值=组）::

    {
        "打开软件": ["<base64 格式串>", "..."],
        "清理体力": {
            "检查体力": ["<base64 格式串>", "..."]
        }
    }

基本用法
--------
::

    from model.步骤.step_list_store import StepListStore

    store = StepListStore.create_empty()
    store.add_list("打开软件", sl)            # 顶层列表
    store.add_group("清理体力")                # 组
    store.add_list("清理体力/检查体力", sl2)   # 组内列表
    pkg.write_file("step_list.json", store.to_json_bytes())        # 写回工程资源
    store2 = StepListStore.from_json(pkg.read_file("step_list.json"), mgr)  # 读回
    runs = store2.all_do_methods()           # [列表1-do1, ..., 列表n-don]
"""

from typing import Any, Callable, Dict, List, Tuple, Union, TYPE_CHECKING

import json

from model.工程.path_util import normalize, validate_name
from model.步骤.step_list import StepList

if TYPE_CHECKING:
    from model.步骤.step_manager import StepManager

__all__ = ["StepListStore"]

# from_json 接受的输入类型：JSON 串 / 已解析 dict / 字节串（read_file 返回）
JsonInput = Union[str, bytes, bytearray, dict]


class StepListStore:
    """总步骤列表模型：嵌套字典（键=列表/组名，值=``StepList`` 或 ``dict``）。

    纯容器，**不持有 manager/package**；格式串还原由调用方传入
    :class:`StepManager`。``from_json`` 时按该 manager 解码并校验。
    """

    # from_json 允许的最大嵌套深度（正常工程远小于此；超深视为损坏/恶意输入）
    _MAX_DEPTH = 128

    def __init__(self) -> None:
        self.root: Dict[str, Any] = {}   # 值: StepList(叶子) 或 dict(组)

    # ================================================================
    # 路径归一化 / 名称校验
    # ================================================================
    @staticmethod
    def _norm_path(path: str) -> str:
        """归一化用户路径（委托 :func:`model.工程.path_util.normalize`）。

        语义与 KscpPackage/VariableTree 统一：反斜杠→正斜杠、去前导 ``/``、
        折叠空段与 ``.``、拒绝 ``..``；根路径（空/纯斜杠）抛 :class:`ValueError`。
        """
        return normalize(path)

    @staticmethod
    def _validate_name(name: str) -> None:
        """校验单个列表/组名：非空、不含 ``/``、不为 ``.``/``..``。"""
        validate_name(name)

    def _parent_of(self, parts: List[str]) -> dict:
        """沿路径段（不含末段）走到底，返回父字典；祖先为列表/不存在 → ValueError。"""
        node = self.root
        for seg in parts[:-1]:
            child = node.get(seg)
            if isinstance(child, StepList):
                raise ValueError("祖先路径 %r 已是列表，无法在其下操作" % seg)
            if not isinstance(child, dict):
                raise ValueError("父分组不存在: %r" % seg)
            node = child
        return node

    # ================================================================
    # 写（变更）
    # ================================================================
    def add_group(self, path: str) -> None:
        """创建组（``path`` 可多层，如 ``"a/b"``）；已存在且为组 → 幂等；已是列表 → FileExistsError。

        空路径 / 仅 ``/`` → :class:`ValueError`（根恒存在，无需创建）。
        """
        parts = self._norm_path(path).split("/")
        node = self._parent_of(parts)
        last = parts[-1]
        if isinstance(node.get(last), StepList):
            raise FileExistsError("目标已是列表: %r" % path)
        if last not in node:
            node[last] = {}

    def add_list(self, path: str, step_list: StepList) -> None:
        """添加命名列表；``path`` 无 ``/`` 时即顶层列表（名单直接作路径，如 ``"打开软件"``），``"a/b"`` = 组 ``a`` 下的列表 ``b``；空串/纯 ``/`` → :class:`ValueError`（列表必须有名字）。

        父组须存在；目标已存在（列表或组）→ :class:`FileExistsError`。
        """
        parts = self._norm_path(path).split("/")
        node = self._parent_of(parts)
        last = parts[-1]
        if last in node:
            raise FileExistsError("目标已存在: %r" % path)
        node[last] = step_list

    # ================================================================
    # JSON 导出 / 还原
    # ================================================================
    def to_json_bytes(self) -> bytes:
        """生成 ``step_list.json`` 的 JSON 字节串（可直接 ``package.write_file``）。"""
        return json.dumps(self._to_node(self.root),
                          ensure_ascii=False).encode("utf-8")

    @staticmethod
    def _to_node(node: dict) -> dict:
        """内存字典（StepList 叶子）→ JSON 字典（格式串列表叶子）。"""
        out: dict = {}
        for key, value in node.items():
            if isinstance(value, StepList):
                out[key] = value.to_format_strings()
            else:
                out[key] = StepListStore._to_node(value)
        return out

    @classmethod
    def from_json(cls, data: JsonInput, manager: "StepManager") -> "StepListStore":
        """由 ``step_list.json`` 生成总步骤列表模型。

        ``data`` 可为 JSON 字符串、已解析 ``dict``、或字节串（如
        :meth:`KscpPackage.read_file` 返回）。``manager`` 用于解码步骤格式串。
        """
        if isinstance(data, dict):
            root = data
        else:
            try:
                root = json.loads(data)  # str/bytes/bytearray；他类型由 json.loads 抛 TypeError
            except (json.JSONDecodeError, UnicodeDecodeError, RecursionError) as e:
                raise ValueError("无效的 step_list.json: %s" % e)
            if not isinstance(root, dict):
                raise ValueError(
                    "step_list.json 顶层必须是对象，而非 %s" % type(root).__name__)
        store = cls()
        store._walk(root, store.root, manager)
        return store

    def _walk(self, node: dict, target: dict,
              manager: "StepManager", depth: int = 0) -> None:
        """递归填充 ``target``：list 值 → StepList；dict 值 → 组字典；其他 → ValueError。

        ``depth`` 超过 :data:`_MAX_DEPTH` 抛 :class:`ValueError`
        （超深嵌套 = 损坏/恶意输入，不触发 RecursionError）。
        """
        if depth > self._MAX_DEPTH:
            raise ValueError(
                "step_list.json 嵌套过深（超过 %d 层）" % self._MAX_DEPTH)
        for key, value in node.items():
            self._validate_name(key)
            if isinstance(value, list):
                target[key] = StepList.from_format_strings(value, manager)
            elif isinstance(value, dict):
                sub: dict = {}
                self._walk(value, sub, manager, depth + 1)
                target[key] = sub
            else:
                raise ValueError(
                    "step_list.json 节点值必须是列表或对象: %r" % key)

    # ================================================================
    # 全体可运行 do 整合
    # ================================================================
    def all_do_methods(self) -> List[Callable[[], int]]:
        """按字典插入序（JSON 存储序）深度优先整合所有列表的可运行 do。

        结果 = ``[列表1-do1, 列表1-do2, ..., 列表n-don]``；
        ``enabled=False`` 的步骤不出现。
        """
        out: List[Callable[[], int]] = []
        self._collect_do(self.root, out)
        return out

    @staticmethod
    def _collect_do(node: dict, out: List[Callable[[], int]]) -> None:
        for value in node.values():
            if isinstance(value, StepList):
                out.extend(value.do_methods())
            else:
                StepListStore._collect_do(value, out)

    # ================================================================
    # 读取
    # ================================================================
    @classmethod
    def create_empty(cls) -> "StepListStore":
        """生成空总步骤列表模型。"""
        return cls()

    def paths(self) -> List[str]:
        """全部列表路径（排序；后续管理树数据源）。"""
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
                StepListStore._collect_paths(value, path, out)

    def get(self, path: str) -> StepList:
        """按路径取列表；不存在或为组 → :class:`FileNotFoundError`。"""
        parts = self._norm_path(path).split("/")
        node = self.root
        for seg in parts[:-1]:
            child = node.get(seg)
            if not isinstance(child, dict):
                raise FileNotFoundError("不存在: %r" % path)
            node = child
        last = parts[-1]
        value = node.get(last)
        if not isinstance(value, StepList):
            raise FileNotFoundError("不存在或不是列表: %r" % path)
        return value

    # ================================================================
    # 结构 / 变更扩展（管理树 UI 支持）
    # ================================================================
    def remove(self, path: str) -> None:
        """删除列表或组（组 = 整棵子树）；不存在 → :class:`FileNotFoundError`。"""
        parts = self._norm_path(path).split("/")
        parent = self._parent_of(parts)
        last = parts[-1]
        if last not in parent:
            raise FileNotFoundError("不存在: %r" % path)
        del parent[last]

    def rename(self, path: str, new_name: str) -> None:
        """重命名列表或组（组 = 改键名，子树不动）；保持原字典插入位置。

        非法新名 → :class:`ValueError`；不存在 → :class:`FileNotFoundError`；
        同父下新名已存在 → :class:`FileExistsError`。
        """
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

    def walk(self) -> List[Tuple[str, bool]]:
        """全部组与列表路径（插入序先序：组在前、其子树紧随）；每项 = ``(路径, 是否为组)``。

        含空组；管理树数据源（树需要组节点，:meth:`paths` 只有叶子）。
        """
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
                StepListStore._collect_walk(value, path, out)

if __name__ == "__main__":
    import json as _json
    import sys

    from PyQt5.QtWidgets import QApplication

    from model.步骤.step import Step
    from model.工程.kscp_package import KscpPackage
    from model.变量.project_variable import ProjectVariable
    from model.步骤.step_list import StepList
    from model.步骤.step_list_store import StepListStore
    from model.步骤.step_manager import StepManager
    from model.变量.variable_tree import VariableTree

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

    def make_step(enable: bool = True) -> Step:
        """产出一个可执行步骤实例（io 已配置）；enable=False 则禁用。"""
        s = mgr.create_step("示例")
        s.enabled = enable
        s.io.change_value("input", 0, "5")
        s.io.change_value("output", 0, "n1")
        return s

    # 空 store
    store = StepListStore.create_empty()
    assert store.paths() == [] and store.to_json_bytes() == b"{}"

    # 结构：顶层列表 + 组 + 组内列表 + 嵌套组
    sl_open = StepList.create_empty()
    sl_open.add(make_step())              # 打开软件-do1
    sl_open.add(make_step(False))         # 禁用 → 不出现在 do 导出
    sl_open.add(make_step())              # 打开软件-do2
    store.add_list("打开软件", sl_open)
    store.add_group("清理体力")
    sl_check = StepList.create_empty()
    sl_check.add(make_step())             # 检查体力-do1
    store.add_list("清理体力/检查体力", sl_check)
    store.add_group("清理体力/日常")
    sl_run = StepList.create_empty()
    sl_run.add(make_step())               # 跑图-do1
    store.add_list("清理体力/日常/跑图", sl_run)
    assert store.paths() == ["打开软件", "清理体力/日常/跑图", "清理体力/检查体力"]
    assert store.get("打开软件") is sl_open
    assert store.get("清理体力/日常/跑图") is sl_run
    try:
        store.get("清理体力")
        raise AssertionError("取组应抛 FileNotFoundError")
    except FileNotFoundError:
        pass

    # 冲突：同名列表 / 组撞列表 / 组幂等
    try:
        store.add_list("打开软件", sl_open)
        raise AssertionError("同名列表应抛 FileExistsError")
    except FileExistsError:
        pass
    try:
        store.add_group("打开软件")
        raise AssertionError("目标已是列表应抛 FileExistsError")
    except FileExistsError:
        pass
    store.add_group("清理体力")           # 已存在且为组 → 幂等

    # 非法路径：空 / 仅斜杠 / .. / 父组不存在 / 祖先为列表
    for bad in ("", "/", "a/.."):
        try:
            store.add_list(bad, sl_open)
            raise AssertionError("非法路径应抛 ValueError: %r" % bad)
        except ValueError:
            pass
    # 路径归一化统一（path_util）：空段与 `.` 折叠（与 KscpPackage/VariableTree 一致）
    store_norm = StepListStore.create_empty()
    store_norm.add_group("a")
    store_norm.add_list("a//b", sl_open)       # 空段折叠 → a/b
    store_norm.add_list("a/./c", sl_open)      # `.` 折叠 → a/c
    assert store_norm.paths() == ["a/b", "a/c"], store_norm.paths()
    try:
        store.add_list("不存在组/名", sl_open)
        raise AssertionError("父组不存在应抛 ValueError")
    except ValueError:
        pass
    try:
        store.add_group("打开软件/x")
        raise AssertionError("祖先为列表应抛 ValueError")
    except ValueError:
        pass
    try:
        store.add_group("a/..")
        raise AssertionError("非法组路径应抛 ValueError")
    except ValueError:
        pass

    # 路径归一化：前导 / 与反斜杠
    store.add_group("/前导组")
    sl_tmp = StepList.create_empty()
    store.add_list("前导组\\临时", sl_tmp)     # 反斜杠 → 正斜杠
    assert "前导组/临时" in store.paths()

    # 空组
    store.add_group("空组")
    assert _json.loads(store.to_json_bytes())["空组"] == {}

    # JSON 三态往返：bytes / str / dict；规范化输出稳定
    raw = store.to_json_bytes()
    assert isinstance(raw, bytes)
    s_bytes = StepListStore.from_json(raw, mgr)
    s_str = StepListStore.from_json(raw.decode("utf-8"), mgr)
    s_dict = StepListStore.from_json(_json.loads(raw), mgr)
    assert s_bytes.to_json_bytes() == raw
    assert s_str.to_json_bytes() == raw
    assert s_dict.to_json_bytes() == raw
    assert s_bytes.paths() == store.paths()

    # 全体可运行 do 整合：插入序 DFS；enabled 过滤
    runs = store.all_do_methods()
    assert len(runs) == 4                 # 打开软件2 + 检查体力1 + 跑图1（禁用被过滤）
    assert [f() for f in runs] == [1, 1, 1, 1]
    assert s_bytes.all_do_methods() and len(s_bytes.all_do_methods()) == 4

    # from_json 结构校验：顶层非对象 / 节点值类型非法 / 键含 / / 列表内坏格式串
    try:
        StepListStore.from_json(b'[1,2,3]', mgr)
        raise AssertionError("顶层非对象应抛 ValueError")
    except ValueError:
        pass
    try:
        StepListStore.from_json({"x": 123}, mgr)
        raise AssertionError("节点值类型非法应抛 ValueError")
    except ValueError:
        pass
    try:
        StepListStore.from_json({"a/b": []}, mgr)
        raise AssertionError("键含 '/' 应抛 ValueError")
    except ValueError:
        pass
    # 坏格式串 → 不再抛错，而是落为红色占位卡片（resilient；详见 model.步骤.step_list 冒烟）
    bad_store = StepListStore.from_json({"坏": ["not*valid*"]}, mgr)
    from model.合成卡片.placeholder_step import PlaceholderStep
    assert isinstance(bad_store.get("坏")[0], PlaceholderStep)

    # 嵌套深度上限：深层嵌套 → 可控 ValueError（而非 RecursionError）
    deep_s = cur_s = {}
    for _ in range(300):
        nxt = {}
        cur_s["x"] = nxt
        cur_s = nxt
    try:
        StepListStore.from_json(deep_s, mgr)       # dict 输入（不经 json.loads）
        raise AssertionError("过深嵌套应抛 ValueError")
    except ValueError:
        pass
    deep_s_str = b'{"x":' * 2000 + b'[]' + b'}' * 2000   # json.loads 自身递归爆炸
    try:
        StepListStore.from_json(deep_s_str, mgr)
        raise AssertionError("过深嵌套 JSON 串应抛 ValueError")
    except ValueError:
        pass

    # ---- 变更扩展：remove / rename / walk（管理树 UI 支持） ----
    # walk：先序（组在前、子树紧随）、含空组
    w = store.walk()
    assert [p for p, _g in w] == [
        "打开软件", "清理体力", "清理体力/检查体力", "清理体力/日常",
        "清理体力/日常/跑图", "前导组", "前导组/临时", "空组"]
    assert [g for _p, g in w] == [False, True, False, True,
                                  False, True, False, True]

    # remove：删列表 / 删组（整棵子树）/ 不存在 → FileNotFoundError
    store2 = StepListStore.create_empty()
    store2.add_group("组A")
    store2.add_list("组A/列表1", sl_open)
    store2.add_list("组A/列表2", sl_check)
    store2.remove("组A/列表1")
    assert "组A/列表1" not in store2.paths() and "组A/列表2" in store2.paths()
    store2.remove("组A")                            # 删组 = 整棵子树
    assert store2.paths() == []
    try:
        store2.remove("不存在")
        raise AssertionError("不存在应抛 FileNotFoundError")
    except FileNotFoundError:
        pass

    # rename：改列表 / 改组（子树保留）/ 保持字典插入位置 / 非法名 / 不存在 / 重名冲突
    store3 = StepListStore.create_empty()
    store3.add_group("先组")
    store3.add_list("中间列表", sl_open)
    store3.add_group("后组")
    store3.add_list("后组/子列表", sl_check)
    store3.rename("中间列表", "改名列表")
    assert list(store3.root) == ["先组", "改名列表", "后组"]   # 保持插入位置
    assert "改名列表" in store3.paths()
    store3.rename("后组", "改名组")
    assert list(store3.root) == ["先组", "改名列表", "改名组"]
    assert "改名组/子列表" in store3.paths()                    # 子树保留
    assert store3.get("改名组/子列表") is sl_check
    for bad in ("", "/", "a/b", ".", ".."):
        try:
            store3.rename("改名列表", bad)
            raise AssertionError("非法新名应抛 ValueError: %r" % bad)
        except ValueError:
            pass
    try:
        store3.rename("不存在", "x")
        raise AssertionError("不存在应抛 FileNotFoundError")
    except FileNotFoundError:
        pass
    try:
        store3.rename("改名列表", "先组")
        raise AssertionError("重名冲突应抛 FileExistsError")
    except FileExistsError:
        pass

    print("StepListStore smoke OK")
