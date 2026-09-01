# -*- coding: utf-8 -*-
"""
KScript 工程文件 .kscp 的资源树（数据结构）
============================================

:class:`KscpPackage` 在内存中表示一个 ``.kscp`` 压缩包的目录结构，支持对其中
文件的创建、访问、添加、修改、删除、移动，并能在「.kscp 文件」与「数据模型对象」之间
往返转换。

.kscp 本质是一个 ZIP 归档，其根目录示例::

    .kscp
    │  step_list.json
    │  variables.json
    └─assets
        │  1.png
        │  data.bin
        └─音乐
                2.mp3

职责边界
--------
本模型是**纯资源树**：把所有文件（含 ``step_list.json``、``variables.json``）
都当作不透明字节流处理，**不**解析其 JSON 内容。这两个根 JSON 的内容语义由各自
的兄弟数据模型（步骤列表、变量树）承担；本模型只管目录结构与文件字节。

基本用法
--------
::

    new = KscpPackage.create_empty()           # 新建空工程骨架（两个根 JSON + assets/）
    pkg = KscpPackage.from_kscp("proj.kscp")   # 由 .kscp 生成对象
    data = pkg.read_file("assets/1.png")       # 访问
    pkg.write_file("assets/1.png", new_bytes)  # 修改（不存在则添加）
    pkg.add_file("assets/3.png", png_bytes)     # 添加（已存在则报错）
    pkg.add_file_from_local("assets/3.png", "/path/to/3.png")  # 从本地文件添加
    pkg.move("assets/音乐", "assets/曲库")       # 移动（文件或整棵子树）
    pkg.remove("assets/data.bin")              # 删除（文件或整棵子树）
    pkg.save("proj.kscp")                       # 由对象生成 .kscp
"""

from __future__ import annotations

import os
import tempfile
import zipfile
from typing import Dict, Iterator, List, Optional, Set

from model.path_util import norm_maybe_root, normalize

__all__ = ["KscpPackage"]


class KscpPackage:
    """``.kscp`` 压缩包目录结构的内存模型（扁平路径→字节）。

    内部用 ``_files`` 存「归一化路径→文件字节」、``_dirs`` 存「显式空目录」。
    含文件的目录由文件路径前缀隐含，无需显式登记；空目录靠 ``_dirs`` 才能往返存活。
    所有路径统一为正斜杠、相对、无 ``..`` 的归一化形式。
    """

    def __init__(self) -> None:
        self._files: Dict[str, bytes] = {}   # 归一化路径 -> 文件内容
        self._dirs: Set[str] = set()         # 显式空目录的归一化路径

    # ================================================================
    # 路径归一化
    # ================================================================
    @staticmethod
    def _norm_maybe_root(path: str) -> str:
        """归一化路径；根目录返回空串（委托 :func:`model.path_util.norm_maybe_root`）。"""
        return norm_maybe_root(path)

    @staticmethod
    def _normalize(path: str) -> str:
        """归一化为非空路径；根目录在此视为非法（文件操作不接受根）。"""
        return normalize(path)

    def _file_ancestor(self, norm: str) -> Optional[str]:
        """若 ``norm`` 的某个祖先路径是文件，返回该祖先；否则 ``None``。"""
        parts = norm.split("/")
        for i in range(len(parts) - 1, 0, -1):
            anc = "/".join(parts[:i])
            if anc and anc in self._files:
                return anc
        return None

    def _assert_placeable(self, norm: str) -> None:
        """断言可在 ``norm`` 放置文件：没有祖先是文件（否则树会矛盾）。"""
        anc = self._file_ancestor(norm)
        if anc is not None:
            raise ValueError("祖先路径 %r 已是文件，无法在其下放置 %r" % (anc, norm))

    def _is_dir(self, norm: str) -> bool:
        """归一化路径是否为目录（显式空目录 或 含文件的目录）。"""
        if not norm:
            return True  # 根总是目录
        if norm in self._dirs:
            return True
        prefix = norm + "/"
        return any(f.startswith(prefix) for f in self._files)

    def _exists(self, norm: str) -> bool:
        """归一化路径是否存在（文件或目录）；根恒存在。"""
        if not norm:
            return True
        return norm in self._files or self._is_dir(norm)

    def _all_dirs(self) -> Set[str]:
        """全部目录：显式空目录 ∪ 所有文件路径的祖先目录。"""
        dirs: Set[str] = set(self._dirs)
        for f in self._files:
            parts = f.split("/")
            for i in range(len(parts) - 1):
                dirs.add("/".join(parts[: i + 1]))
        return dirs

    # ================================================================
    # 生命周期 / IO
    # ================================================================
    @classmethod
    def from_kscp(cls, path: str) -> "KscpPackage":
        """从 ``.kscp``(zip) 文件载入，生成模型对象。

        目录条目（以 ``/`` 结尾）登记为显式目录，文件条目按原字节读入。
        所有条目路径经 :func:`model.path_util.norm_maybe_root` 归一化
        （正斜杠、相对、无 ``..``）；含 ``..`` 的条目抛 :class:`ValueError`
        ——异常/恶意 zip 不得破坏模型的不变量。
        """
        pkg = cls()
        with zipfile.ZipFile(path, "r") as zf:
            for info in zf.infolist():
                name = norm_maybe_root(info.filename)
                if not name:
                    continue           # 根目录条目（"/" 等）无实际内容
                if info.is_dir():
                    d = name.rstrip("/")
                    if d:
                        pkg._dirs.add(d)
                else:
                    pkg._files[name] = zf.read(info)
        return pkg

    @classmethod
    def create_empty(cls) -> "KscpPackage":
        """新建空工程骨架并返回模型对象。

        结构::

            │  step_list.json    (b"{}")
            │  variables.json    (b"{}")
            │  composites.json   (b"{}")
            └─assets            (空目录)

        三个根 JSON 以空对象 ``{}`` 初始化，方便后续步骤列表、变量树、合成卡片
        等兄弟模型直接载入；``assets/`` 为空目录。随后可 ``save(path)`` 落盘为
        ``.kscp``。
        """
        pkg = cls()
        pkg.add_file("step_list.json", b"{}")
        pkg.add_file("variables.json", b"{}")
        pkg.add_file("composites.json", b"{}")
        pkg.make_dir("assets")
        return pkg

    def save(self, path: str) -> None:
        """把模型写出为 ``.kscp``(zip) 文件。

        原子写入（临时文件 + ``os.replace``），条目按名排序保证确定性输出。
        """
        dir_entries = sorted(d + "/" for d in self._dirs)
        file_items = sorted(self._files.items(), key=lambda kv: kv[0])
        parent = os.path.dirname(os.path.abspath(path))
        os.makedirs(parent, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as raw, \
                    zipfile.ZipFile(raw, "w", zipfile.ZIP_DEFLATED) as zf:
                for entry in dir_entries:
                    zf.writestr(entry, b"")
                for name, data in file_items:
                    zf.writestr(name, data)
            os.replace(tmp, path)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    # ================================================================
    # 读
    # ================================================================
    def read_file(self, path: str) -> bytes:
        """访问文件内容；不存在抛 :class:`FileNotFoundError`。"""
        n = self._normalize(path)
        if n not in self._files:
            raise FileNotFoundError("文件不存在: %r" % path)
        return self._files[n]

    def exists(self, path: str) -> bool:
        """文件或目录是否存在（根恒为 ``True``）。"""
        return self._exists(self._norm_maybe_root(path))

    def is_file(self, path: str) -> bool:
        """是否为文件。"""
        return self._normalize(path) in self._files

    def is_dir(self, path: str) -> bool:
        """是否为目录（根恒为 ``True``）。"""
        return self._is_dir(self._norm_maybe_root(path))

    def list_dir(self, path: str = "/") -> List[str]:
        """列出某目录的直系子项名（文件 + 子目录，按字典序）。

        ``path`` 为根可传 ``"/"``、``""``、``"."``。路径不是目录时抛
        :class:`ValueError`。
        """
        norm = self._norm_maybe_root(path)
        if norm and not self._is_dir(norm):
            raise ValueError("不是目录: %r" % path)
        prefix = (norm + "/") if norm else ""
        children: Set[str] = set()
        for f in self._files:
            if not f.startswith(prefix):
                continue
            rest = f[len(prefix):]
            if rest:
                children.add(rest.split("/", 1)[0])
        for d in self._dirs:
            if not d.startswith(prefix):
                continue
            rest = d[len(prefix):]
            if rest:
                children.add(rest.split("/", 1)[0])
        return sorted(children)

    @property
    def files(self) -> List[str]:
        """全部文件路径（按字典序）。"""
        return sorted(self._files)

    @property
    def dirs(self) -> List[str]:
        """全部目录路径（含隐含目录，按字典序）。"""
        return sorted(self._all_dirs())

    # ================================================================
    # 写（变更）
    # ================================================================
    def add_file(self, path: str, data: bytes) -> None:
        """添加文件；已存在（文件或目录）抛 :class:`FileExistsError`。"""
        n = self._normalize(path)
        if n in self._files:
            raise FileExistsError("文件已存在: %r" % path)
        if self._is_dir(n):
            raise FileExistsError("目标已是目录: %r" % path)
        self._assert_placeable(n)
        self._files[n] = bytes(data)

    def write_file(self, path: str, data: bytes) -> None:
        """修改文件内容；不存在则添加（upsert）。

        若 ``path`` 是目录则抛 :class:`ValueError`。
        """
        n = self._normalize(path)
        if n not in self._files and self._is_dir(n):
            raise ValueError("目标已是目录，不能当文件写: %r" % path)
        self._assert_placeable(n)
        self._files[n] = bytes(data)

    def add_file_from_local(self, path: str, local_path: str) -> None:
        """从本地磁盘文件读取字节并添加到包内 ``path``。

        已存在（文件或目录）抛 :class:`FileExistsError`；本地路径不存在抛
        :class:`FileNotFoundError`、是目录抛 :class:`IsADirectoryError`。
        """
        self.add_file(path, self._read_local(local_path))

    def write_file_from_local(self, path: str, local_path: str) -> None:
        """从本地磁盘文件读取字节并写入包内 ``path``（upsert：存在覆盖、不存在新增）。

        ``path`` 是目录则抛 :class:`ValueError`；本地路径不存在抛
        :class:`FileNotFoundError`、是目录抛 :class:`IsADirectoryError`。
        """
        self.write_file(path, self._read_local(local_path))

    @staticmethod
    def _read_local(local_path: str) -> bytes:
        """读取本地磁盘文件的字节。

        用 ``os.path.isdir`` 预检目录，避免在 Windows 上以 ``rb`` 打开目录时
        抛出 ``PermissionError`` 而非 ``IsADirectoryError`` 的差异。
        """
        if os.path.isdir(local_path):
            raise IsADirectoryError("本地路径是目录，不是文件: %r" % local_path)
        if not os.path.exists(local_path):
            raise FileNotFoundError("本地文件不存在: %r" % local_path)
        with open(local_path, "rb") as f:
            return f.read()

    def make_dir(self, path: str) -> None:
        """创建空目录；已是目录则幂等返回，已是文件则抛 :class:`FileExistsError`。"""
        n = self._normalize(path)
        if n in self._files:
            raise FileExistsError("目标已是文件: %r" % path)
        if self._is_dir(n):
            return  # 幂等
        self._assert_placeable(n)
        self._dirs.add(n)

    def remove(self, path: str) -> None:
        """删除：文件删文件，目录则递归删整棵子树；不存在抛 :class:`FileNotFoundError`。"""
        n = self._normalize(path)
        if n in self._files:
            del self._files[n]
            return
        if self._is_dir(n):
            prefix = n + "/"
            for f in [f for f in self._files if f.startswith(prefix)]:
                del self._files[f]
            for x in [x for x in self._dirs if x == n or x.startswith(prefix)]:
                self._dirs.discard(x)
            return
        raise FileNotFoundError("不存在: %r" % path)

    def move(self, src: str, dst: str) -> None:
        """移动/重命名：源是文件则改路径，是目录则把整棵子树改写到 ``dst`` 下。

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
        if s in self._files:
            # 文件移动
            if self._exists(d):
                raise FileExistsError("目标已存在: %r" % dst)
            self._files[d] = self._files.pop(s)
        elif self._is_dir(s):
            # 目录移动：改写 src/ 下全部文件与显式目录条目到 dst/ 下
            if self._exists(d):
                raise FileExistsError("目标已存在: %r" % dst)
            sprefix, dprefix = s + "/", d + "/"
            for f in [f for f in self._files if f.startswith(sprefix)]:
                self._files[dprefix + f[len(sprefix):]] = self._files.pop(f)
            for x in [x for x in self._dirs if x == s or x.startswith(sprefix)]:
                newx = d if x == s else dprefix + x[len(sprefix):]
                self._dirs.discard(x)
                self._dirs.add(newx)
        else:
            raise FileNotFoundError("源不存在: %r" % src)

    # ================================================================
    # 双下方法
    # ================================================================
    def __contains__(self, path: object) -> bool:
        if not isinstance(path, str):
            return False
        return self._exists(self._norm_maybe_root(path))

    def __len__(self) -> int:
        return len(self._files)

    def __iter__(self) -> Iterator[str]:
        return iter(sorted(self._files))

    def __repr__(self) -> str:
        return "KscpPackage(files=%d, dirs=%d)" % (
            len(self._files), len(self._all_dirs()))


# ================================================================
# 冒烟演示：直接 ``python -m model.kscp_package`` 运行
# ================================================================
if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as td:
        kscp = os.path.join(td, "demo.kscp")

        pkg = KscpPackage()
        pkg.add_file("step_list.json", b"{}")
        pkg.add_file("variables.json", b"{}")
        pkg.write_file("assets/1.png", b"\x89PNG\r\n\x1a\n")
        pkg.write_file("assets/data.bin", b"\x00\x01\x02")
        pkg.make_dir("assets/音乐")              # assets/音乐
        pkg.write_file("assets/音乐/2.mp3", b"ID3")
        pkg.move("assets/音乐", "assets/曲库")  # 音乐 -> 曲库
        pkg.remove("assets/data.bin")
        pkg.save(kscp)

        pkg2 = KscpPackage.from_kscp(kscp)
        assert pkg2.read_file("step_list.json") == b"{}"
        assert pkg2.read_file("assets/1.png") == b"\x89PNG\r\n\x1a\n"
        assert pkg2.read_file("assets/曲库/2.mp3") == b"ID3"
        assert "assets/data.bin" not in pkg2
        assert "assets/1.png" in pkg2
        assert not pkg2.is_dir("assets/音乐")
        assert pkg2.is_dir("assets/曲库")
        assert pkg2.list_dir("assets") == ["1.png", "曲库"]
        assert sorted(pkg2.files) == sorted([
            "step_list.json", "variables.json",
            "assets/1.png", "assets/曲库/2.mp3"])
        # 空目录往返
        pkg2.make_dir("empty")
        pkg2.save(kscp)
        pkg3 = KscpPackage.from_kscp(kscp)
        assert pkg3.is_dir("empty")
        assert "empty" in pkg3.dirs
        # 拒绝越界路径
        try:
            pkg3.add_file("../escape.txt", b"x")
            raise AssertionError("应当拒绝 '..' 路径")
        except ValueError:
            pass

        # from_kscp 归一化（恶意/异常 zip）：
        # 含 '..' 条目 → 加载即拒绝（ValueError），不产生不一致状态
        evil_kscp = os.path.join(td, "evil.kscp")
        with zipfile.ZipFile(evil_kscp, "w") as zf:
            zf.writestr("../evil.txt", b"x")
        try:
            KscpPackage.from_kscp(evil_kscp)
            raise AssertionError("含 '..' 条目的 zip 应拒绝加载")
        except ValueError:
            pass
        # 可归一条目（反斜杠 / 空段 / 前导 /）→ 归一化入库
        messy_kscp = os.path.join(td, "messy.kscp")
        with zipfile.ZipFile(messy_kscp, "w") as zf:
            zf.writestr("a//b.txt", b"x")
            zf.writestr("\\c.txt", b"y")
            zf.writestr("/d.txt", b"z")
        pkg4 = KscpPackage.from_kscp(messy_kscp)
        assert pkg4.read_file("a/b.txt") == b"x"
        assert pkg4.read_file("c.txt") == b"y"
        assert pkg4.read_file("d.txt") == b"z"
        assert "../" not in pkg4.files and not any(
            f.startswith("/") for f in pkg4.files)

        # move 自嵌套：目标在源子树内（含目标不存在的情况）→ 拒绝
        pkg_m = KscpPackage.create_empty()
        pkg_m.make_dir("assets/子")
        pkg_m.write_file("assets/子/1.png", b"x")
        try:
            pkg_m.move("assets", "assets/新目录")
            raise AssertionError("目标在源子树内应抛 ValueError")
        except ValueError:
            pass
        assert pkg_m.read_file("assets/子/1.png") == b"x"   # 源未被改写

        # 本地文件方式添加 / 修改
        local_png = os.path.join(td, "local.png")
        local_bin = os.path.join(td, "data.bin")
        with open(local_png, "wb") as f:
            f.write(b"\x89PNG-local")
        with open(local_bin, "wb") as f:
            f.write(b"\x00\xFF")
        pkg3.add_file_from_local("assets/local.png", local_png)   # 添加
        assert pkg3.read_file("assets/local.png") == b"\x89PNG-local"
        pkg3.write_file_from_local("assets/local.png", local_bin)  # 覆盖
        assert pkg3.read_file("assets/local.png") == b"\x00\xFF"
        pkg3.write_file_from_local("assets/new.bin", local_bin)   # 新增
        assert pkg3.read_file("assets/new.bin") == b"\x00\xFF"
        try:  # add 已存在 → FileExistsError
            pkg3.add_file_from_local("assets/new.bin", local_bin)
            raise AssertionError("已存在应抛 FileExistsError")
        except FileExistsError:
            pass
        try:  # 本地文件不存在 → FileNotFoundError
            pkg3.add_file_from_local("assets/x", os.path.join(td, "nope"))
            raise AssertionError("本地不存在应抛 FileNotFoundError")
        except FileNotFoundError:
            pass
        try:  # 本地路径是目录 → IsADirectoryError
            pkg3.add_file_from_local("assets/x", td)
            raise AssertionError("本地是目录应抛 IsADirectoryError")
        except IsADirectoryError:
            pass

    # create_empty：空工程骨架
    empty = KscpPackage.create_empty()
    assert empty.files == ["composites.json", "step_list.json", "variables.json"]
    assert "assets" in empty.dirs
    assert empty.read_file("step_list.json") == b"{}"
    assert empty.read_file("variables.json") == b"{}"
    assert empty.read_file("composites.json") == b"{}"
    assert empty.list_dir("/") == ["assets", "composites.json",
                                   "step_list.json", "variables.json"]
    with tempfile.TemporaryDirectory() as td:
        empty_kscp = os.path.join(td, "empty.kscp")
        empty.save(empty_kscp)
        empty2 = KscpPackage.from_kscp(empty_kscp)
        assert empty2.files == ["composites.json", "step_list.json",
                                "variables.json"]
        assert empty2.is_dir("assets")
        assert empty2.read_file("variables.json") == b"{}"
        assert empty2.read_file("composites.json") == b"{}"

    print("KscpPackage smoke OK")
