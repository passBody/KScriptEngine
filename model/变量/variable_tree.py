# -*- coding: utf-8 -*-
"""
全局变量树（数据结构）
======================

:class:`VariableTree` 管理一个工程中的所有 :class:`ProjectVariable`，支持
添加、修改、删除、移动、查询，并能在对象与 ``variables.json`` 之间往返转换。

variables.json 形态（嵌套字典；字符串值=变量，字典值=分组；无保留关键字）::

    {
        "变量名1": "<base64 格式串>",
        "循环系列": { "变量名2": "<base64 格式串>" }
    }

基本用法
--------
::

    from model import KscpPackage, ProjectVariable, VariableTree

    pkg = KscpPackage.create_empty()
    pkg.write_file("assets/1.png", png_bytes)

    tree = VariableTree.create_empty()
    tree.add("x", ProjectVariable.create("string", "hi", pkg))
    tree.add("循环系列/y", ProjectVariable.create("image","assets/1.png", pkg))

    pkg.write_file("variables.json", tree.to_json_bytes())              # 写回工程资源
    tree2 = VariableTree.from_json(pkg.read_file("variables.json"), pkg)  # 从工程资源读
"""

from __future__ import annotations

import json
from typing import Dict, Iterator, List, Optional, Set, Tuple, Union, TYPE_CHECKING

from .project_variable import ProjectVariable
from ..工程.path_util import norm_maybe_root, normalize, validate_name

if TYPE_CHECKING:
    from .kscp_package import KscpPackage

__all__ = ["VariableTree"]

# from_json 接受的输入类型：JSON 串 / 已解析 dict / 字节串（read_file 返回）
JsonInput = Union[str, bytes, bytearray, dict]


class VariableTree:
    """全局变量树：扁平路径→``ProjectVariable`` + 显式空分组。

    树是纯容器，**不持有 package**；变量的创建与合规校验由
    :meth:`ProjectVariable.create` 负责。``from_json`` 时按传入的 ``package``
    重新解码并校验变量。
    """

    # from_json 允许的最大嵌套深度（正常工程远小于此；超深视为损坏/恶意输入）
    _MAX_DEPTH = 128

    def __init__(self) -> None:
        self._vars: Dict[str, ProjectVariable] = {}   # 路径 -> 变量
        self._groups: Set[str] = set()                 # 显式空分组

    # ================================================================
    # 路径归一化
    # ================================================================
    @staticmethod
    def _norm_maybe_root(path: str) -> str:
        """归一化路径；根目录返回空串（委托 :func:`model.工程.path_util.norm_maybe_root`）。"""
        return norm_maybe_root(path)

    @staticmethod
    def _normalize(path: str) -> str:
        """归一化为非空路径；根目录在此视为非法。"""
        return normalize(path)

    @staticmethod
    def _validate_name(name: str) -> None:
        """校验单个变量/分组名：非空、不含 ``/``、不为 ``.``/``..``。"""
        validate_name(name)

    def _file_ancestor(self, norm: str) -> Optional[str]:
        """若 ``norm`` 的某个祖先是变量，返回该祖先；否则 ``None``。"""
        parts = norm.split("/")
        for i in range(len(parts) - 1, 0, -1):
            anc = "/".join(parts[:i])
            if anc and anc in self._vars:
                return anc
        return None

    def _assert_placeable(self, norm: str) -> None:
        """断言可在 ``norm`` 放置变量：没有祖先是变量（否则树会矛盾）。"""
        anc = self._file_ancestor(norm)
        if anc is not None:
            raise ValueError("祖先路径 %r 已是变量，无法在其下放置 %r" % (anc, norm))

    def _is_group(self, norm: str) -> bool:
        """归一化路径是否为分组（显式空分组 或 含变量的分组）。"""
        if not norm:
            return True  # 根总是分组
        if norm in self._groups:
            return True
        prefix = norm + "/"
        return any(v.startswith(prefix) for v in self._vars)

    def _exists(self, norm: str) -> bool:
        """归一化路径是否存在（变量或分组）；根恒存在。"""
        if not norm:
            return True
        return norm in self._vars or self._is_group(norm)

    def _all_groups(self) -> Set[str]:
        """全部分组：显式空分组 ∪ 所有变量路径的祖先分组（规范化集合）。"""
        groups: Set[str] = set(self._groups)
        for v in self._vars:
            parts = v.split("/")
            for i in range(len(parts) - 1):
                groups.add("/".join(parts[: i + 1]))
        return groups

    # ================================================================
    # 生命周期 / IO
    # ================================================================
    @classmethod
    def from_json(cls, data: JsonInput,
                  package: "KscpPackage") -> "VariableTree":
        """由 ``variables.json`` 生成变量树（要求 1 + 要求3-入）。

        ``data`` 可为 JSON 字符串、已解析 ``dict``、或字节串（如
        :meth:`KscpPackage.read_file` 返回）。``package`` 用于解码变量格式串时
        重新校验 image 资源路径。
        """
        if isinstance(data, dict):
            root = data
        else:
            try:
                root = json.loads(data)  # str/bytes/bytearray；他类型由 json.loads 抛 TypeError
            except (json.JSONDecodeError, UnicodeDecodeError, RecursionError) as e:
                raise ValueError("无效的 variables.json: %s" % e)
            if not isinstance(root, dict):
                raise ValueError(
                    "variables.json 顶层必须是对象，而非 %s" % type(root).__name__)
        tree = cls()
        tree._walk(root, "", package)
        return tree

    def _walk(self, node: dict, prefix: str,
              package: "KscpPackage", depth: int = 0) -> None:
        """递归遍历嵌套字典，填入 ``_vars`` / ``_groups``。

        ``depth`` 超过 :data:`_MAX_DEPTH` 抛 :class:`ValueError`
        （超深嵌套 = 损坏/恶意输入，不触发 RecursionError）。
        """
        if depth > self._MAX_DEPTH:
            raise ValueError(
                "variables.json 嵌套过深（超过 %d 层）" % self._MAX_DEPTH)
        for key, value in node.items():
            self._validate_name(key)
            path = key if not prefix else prefix + "/" + key
            if isinstance(value, str):
                self._vars[path] = ProjectVariable.from_format_string(value, package)
            elif isinstance(value, dict):
                self._groups.add(path)  # 记录分组（空与非空都记，空分组靠它存活）
                if value:
                    self._walk(value, path, package, depth + 1)
            else:
                raise ValueError(
                    "variables.json 节点值必须是字符串或字典: %r" % key)

    @classmethod
    def create_empty(cls) -> "VariableTree":
        """生成空变量树（要求 2）。"""
        return cls()

    def to_json_bytes(self) -> bytes:
        """生成 ``variables.json`` 的 JSON 字节串（要求3-出）。

        返回 UTF-8 JSON 字节串，可直接 ``package.write_file("variables.json", …)``。
        """
        root: dict = {}
        # 先放置变量（顺带用 setdefault 建出分组字典）
        for path, var in self._vars.items():
            parts = path.split("/")
            node = root
            for p in parts[:-1]:
                nxt = node.get(p)
                if not isinstance(nxt, dict):
                    nxt = {}
                    node[p] = nxt
                node = nxt
            node[parts[-1]] = var.to_format_string()
        # 再补空分组（无变量其下的分组）为 {}
        for g in self._groups:
            parts = g.split("/")
            node = root
            for p in parts:
                nxt = node.get(p)
                if not isinstance(nxt, dict):
                    nxt = {}
                    node[p] = nxt
                node = nxt
        return json.dumps(root, ensure_ascii=False).encode("utf-8")

    # ================================================================
    # 读
    # ================================================================
    def get(self, path: str) -> ProjectVariable:
        """查询变量；不存在抛 :class:`FileNotFoundError`。"""
        n = self._normalize(path)
        if n not in self._vars:
            raise FileNotFoundError("变量不存在: %r" % path)
        return self._vars[n]

    def exists(self, path: str) -> bool:
        """变量或分组是否存在（根恒为 ``True``）。"""
        return self._exists(self._norm_maybe_root(path))

    def is_variable(self, path: str) -> bool:
        """是否为变量。"""
        return self._normalize(path) in self._vars

    def is_group(self, path: str) -> bool:
        """是否为分组（根恒为 ``True``）。"""
        return self._is_group(self._norm_maybe_root(path))

    def list_dir(self, path: str = "/") -> List[str]:
        """列出某分组的直系子项名（变量 + 子分组，按字典序）。

        ``path`` 为根可传 ``"/"``、``""``、``"."``。路径不是分组时抛
        :class:`ValueError`。
        """
        norm = self._norm_maybe_root(path)
        if norm and not self._is_group(norm):
            raise ValueError("不是分组: %r" % path)
        prefix = (norm + "/") if norm else ""
        children: Set[str] = set()
        for v in self._vars:
            if not v.startswith(prefix):
                continue
            rest = v[len(prefix):]
            if rest:
                children.add(rest.split("/", 1)[0])
        for g in self._groups:
            if not g.startswith(prefix):
                continue
            rest = g[len(prefix):]
            if rest:
                children.add(rest.split("/", 1)[0])
        return sorted(children)

    @property
    def variables(self) -> List[str]:
        """全部变量路径（按字典序）。"""
        return sorted(self._vars)

    @property
    def groups(self) -> List[str]:
        """全部分组路径（含隐含分组，按字典序）。"""
        return sorted(self._all_groups())

    def items(self) -> List[Tuple[str, ProjectVariable]]:
        """``[(路径, 变量), ...]``（按路径字典序）。"""
        return [(p, self._vars[p]) for p in sorted(self._vars)]

    # ================================================================
    # 写（变更）
    # ================================================================
    def add(self, path: str, var: ProjectVariable) -> None:
        """添加变量；已存在（变量或分组）抛 :class:`FileExistsError`。"""
        n = self._normalize(path)
        if n in self._vars:
            raise FileExistsError("变量已存在: %r" % path)
        if self._is_group(n):
            raise FileExistsError("目标已是分组: %r" % path)
        self._assert_placeable(n)
        self._vars[n] = var

    def set(self, path: str, var: ProjectVariable) -> None:
        """修改变量；不存在则添加（upsert）。``path`` 是分组则抛 :class:`ValueError`。"""
        n = self._normalize(path)
        if n not in self._vars and self._is_group(n):
            raise ValueError("目标已是分组，不能当变量写: %r" % path)
        self._assert_placeable(n)
        self._vars[n] = var

    def add_group(self, path: str) -> None:
        """创建空分组；已是分组则幂等返回，已是变量则抛 :class:`FileExistsError`。"""
        n = self._normalize(path)
        if n in self._vars:
            raise FileExistsError("目标已是变量: %r" % path)
        if self._is_group(n):
            return  # 幂等
        self._assert_placeable(n)
        self._groups.add(n)

    def remove(self, path: str) -> None:
        """删除：变量删变量，分组则递归删整棵子树；不存在抛 :class:`FileNotFoundError`。"""
        n = self._normalize(path)
        if n in self._vars:
            del self._vars[n]
            return
        if self._is_group(n):
            prefix = n + "/"
            for v in [v for v in self._vars if v.startswith(prefix)]:
                del self._vars[v]
            for x in [x for x in self._groups if x == n or x.startswith(prefix)]:
                self._groups.discard(x)
            return
        raise FileNotFoundError("不存在: %r" % path)

    def move(self, src: str, dst: str) -> None:
        """移动/重命名：源是变量则改路径，是分组则把整棵子树改写到 ``dst`` 下。

        ``src`` 不存在抛 :class:`FileNotFoundError`；``dst`` 已存在抛
        :class:`FileExistsError`。
        """
        s = self._normalize(src)
        d = self._normalize(dst)
        if s == d:
            return
        if d.startswith(s + "/"):
            raise ValueError(
                "目标 %r 在源 %r 子树内，无法自嵌套移动" % (dst, src))
        self._assert_placeable(d)
        if s in self._vars:
            if self._exists(d):
                raise FileExistsError("目标已存在: %r" % dst)
            self._vars[d] = self._vars.pop(s)
        elif self._is_group(s):
            if self._exists(d):
                raise FileExistsError("目标已存在: %r" % dst)
            sprefix, dprefix = s + "/", d + "/"
            for v in [v for v in self._vars if v.startswith(sprefix)]:
                self._vars[dprefix + v[len(sprefix):]] = self._vars.pop(v)
            for x in [x for x in self._groups if x == s or x.startswith(sprefix)]:
                newx = d if x == s else dprefix + x[len(sprefix):]
                self._groups.discard(x)
                self._groups.add(newx)
        else:
            raise FileNotFoundError("源不存在: %r" % src)

    # ================================================================
    # 筛选器
    # ================================================================
    def filter_by_type(self, vtype: str) -> "VariableTree":
        """返回只含指定类型变量的同类型对象（要求 4）。

        保留各变量原路径（分组按需隐含，空分组丢弃）。未知类型抛
        :class:`ValueError`。返回的树无 package，可 ``to_json_bytes``/``get``/``list_dir``。
        """
        return self.filter_by_types(vtype)

    def filter_by_types(self, *types: str) -> "VariableTree":
        """返回只含指定多个类型变量的同类型对象（:meth:`filter_by_type` 的单类型特例）。

        语义与 :meth:`filter_by_type` 相同；任一类型未知抛 :class:`ValueError`。
        """
        for t in types:
            if t not in ProjectVariable.supported_types():
                raise ValueError(
                    "不支持的变量类型: %r（支持: %s）"
                    % (t, ProjectVariable.supported_types()))
        tree = VariableTree()
        for path, var in self._vars.items():
            if var.type in types:
                tree._vars[path] = var  # 复制引用；分组由路径隐含
        return tree

    # ================================================================
    # 双下方法
    # ================================================================
    def __contains__(self, path: object) -> bool:
        if not isinstance(path, str):
            return False
        return self._exists(self._norm_maybe_root(path))

    def __len__(self) -> int:
        return len(self._vars)

    def __iter__(self) -> Iterator[str]:
        return iter(sorted(self._vars))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, VariableTree):
            return NotImplemented
        # 用 _all_groups()（显式+隐含）规范化比较，不受冗余 _groups 条目影响
        return self._vars == other._vars and self._all_groups() == other._all_groups()

    def __repr__(self) -> str:
        return "VariableTree(vars=%d, groups=%d)" % (
            len(self._vars), len(self._all_groups()))


# ================================================================
# 冒烟演示：直接 ``python -m model.变量.variable_tree`` 运行
# ================================================================
if __name__ == "__main__":
    import json as _json
    import tempfile

    from model.工程.kscp_package import KscpPackage

    with tempfile.TemporaryDirectory() as td:
        # 工程资源 + 几个变量
        pkg = KscpPackage.create_empty()
        pkg.write_file("assets/1.png", b"\x89PNG-demo")
        pkg.write_file("assets/2.jpg", b"JPG")
        v_str = ProjectVariable.create("string", "你好", pkg)
        v_num = ProjectVariable.create("number", 42, pkg)
        v_png = ProjectVariable.create("image","assets/1.png", pkg)
        v_png2 = ProjectVariable.create("image","assets/2.jpg", pkg)

        # 建树：加变量 + 嵌套分组（含中文）
        tree = VariableTree.create_empty()
        tree.add("s", v_str)
        tree.add("n", v_num)
        tree.add_group("循环系列")
        tree.add("循环系列/p1", v_png)
        tree.add("循环系列/子/p2", v_png2)
        assert set(tree.list_dir("/")) == {"s", "n", "循环系列"}
        assert tree.list_dir("循环系列") == ["p1", "子"]
        assert tree.get("循环系列/p1") is v_png
        assert tree.is_group("循环系列") and tree.is_variable("s")
        assert len(tree) == 4

        # to_json_bytes -> bytes；from_json 接收 bytes/str/dict 三态往返
        raw = tree.to_json_bytes()
        assert isinstance(raw, bytes)
        t_bytes = VariableTree.from_json(raw, pkg)
        t_str = VariableTree.from_json(raw.decode("utf-8"), pkg)
        t_dict = VariableTree.from_json(_json.loads(raw), pkg)
        assert t_bytes == t_str == t_dict == tree
        assert t_bytes.to_json_bytes() == raw  # 规范化输出稳定

        # 经工程资源往返：write_file(bytes) <-> read_file(bytes)
        pkg.write_file("variables.json", raw)
        t_pkg = VariableTree.from_json(pkg.read_file("variables.json"), pkg)
        assert t_pkg == tree
        assert t_pkg.get("循环系列/子/p2").get_actual_data() == b"JPG"

        # move / remove
        t2 = VariableTree.from_json(raw, pkg)
        t2.move("循环系列/p1", "循环系列/移后")
        assert t2.get("循环系列/移后") is not None
        assert "循环系列/p1" not in t2
        t2.move("循环系列", "循环2")
        assert t2.get("循环2/子/p2") is not None
        t2.remove("循环2/子")
        assert "循环2/子/p2" not in t2
        assert "循环2/子" not in t2.groups

        # move 自嵌套：目标在源子树内（含目标不存在的情况）→ 拒绝
        t_m = VariableTree.from_json(raw, pkg)
        try:
            t_m.move("循环系列", "循环系列/新组")
            raise AssertionError("目标在源子树内应抛 ValueError")
        except ValueError:
            pass
        assert t_m.get("循环系列/子/p2") is not None   # 源未被改写

        # filter_by_type：png 子集
        png_tree = tree.filter_by_type("image")
        assert isinstance(png_tree, VariableTree)
        assert sorted(png_tree.variables) == ["循环系列/p1", "循环系列/子/p2"]
        assert png_tree.get("循环系列/p1").get_actual_data() == b"\x89PNG-demo"
        assert png_tree.list_dir("/") == ["循环系列"]
        # 非法类型
        try:
            tree.filter_by_type("audio")
            raise AssertionError("未知类型应抛 ValueError")
        except ValueError:
            pass

        # filter_by_types：多类型合并（string 槽兼容 number 的选择器用）
        mix = tree.filter_by_types("string", "image")
        assert sorted(mix.variables) == ["s", "循环系列/p1", "循环系列/子/p2"]
        try:
            tree.filter_by_types("number", "audio")
            raise AssertionError("filter_by_types 未知类型应抛 ValueError")
        except ValueError:
            pass

        # 空分组往返
        e = VariableTree.create_empty()
        e.add_group("空组")
        e_raw = e.to_json_bytes()
        assert _json.loads(e_raw) == {"空组": {}}
        assert VariableTree.from_json(e_raw, pkg).is_group("空组")

        # 非法输入
        try:  # 顶层非对象
            VariableTree.from_json(b'[1,2,3]', pkg)
            raise AssertionError("顶层非对象应抛错")
        except ValueError:
            pass
        try:  # 节点值类型非法
            VariableTree.from_json({"x": 123}, pkg)
            raise AssertionError("非法值类型应抛错")
        except ValueError:
            pass
        try:  # 名字含 '/'
            VariableTree.from_json({"a/b": "x"}, pkg)
            raise AssertionError("名字含 '/' 应抛错")
        except ValueError:
            pass
        try:  # 越界路径
            tree.add("../x", v_str)
            raise AssertionError("'..' 路径应抛错")
        except ValueError:
            pass

        # 嵌套深度上限：深层嵌套 → 可控 ValueError（而非 RecursionError）
        deep = cur = {}
        for _ in range(300):
            nxt = {}
            cur["x"] = nxt
            cur = nxt
        try:
            VariableTree.from_json(deep, pkg)      # dict 输入（不经 json.loads）
            raise AssertionError("过深嵌套应抛 ValueError")
        except ValueError:
            pass
        deep_str = b'{"x":' * 2000 + b'{}' + b'}' * 2000   # json.loads 自身递归爆炸
        try:
            VariableTree.from_json(deep_str, pkg)
            raise AssertionError("过深嵌套 JSON 串应抛 ValueError")
        except ValueError:
            pass

    print("VariableTree smoke OK")
