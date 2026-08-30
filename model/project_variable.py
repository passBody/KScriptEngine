# -*- coding: utf-8 -*-
"""
工程变量（数据结构）
====================

:class:`ProjectVariable` 描述一个 KScript 工程变量。变量可以访问工程资源
（``.kscp`` 包，即 :class:`model.kscp_package.KscpPackage`）中 ``assets/`` 目录下的文件。

属性
----
* ``type``  变量类型（``string`` / ``number`` / ``image``，可扩展）。
* ``data``  变量数据（image 类型为工程资源路径，其余为字面值）。
* ``valid`` 变量是否有效——创建时按类型校验数据是否合规，不合规则为 ``False``。
* ``is_resource`` 是否为资源类变量——``data`` 为工程资源（如 png 的资源路径）时
  为 ``True``，字面值类型为 ``False``；由类型的 ``is_resource`` 决定。
* ``suffixes`` 资源后缀列表——资源类变量接受的后缀（如 png 为 ``['.png', '.jpg']``）；
  非资源类为 ``[]``；由类型的 ``suffixes`` 决定，并用于后缀校验。

类型与预留接口
--------------
每种类型是 :class:`VariableType` 的一个子类实例，注册到 ``ProjectVariable``
的类级注册表。新增类型：子类化 :class:`VariableType`（实现 ``is_valid`` /
``to_actual``，可选 ``normalize``），再 ``ProjectVariable.register_type(实例)``。

基本用法
--------
::

    from model import KscpPackage, ProjectVariable

    pkg = KscpPackage.create_empty()
    pkg.write_file("assets/1.png", png_bytes)

    s = ProjectVariable.create("string", "hello", pkg)
    n = ProjectVariable.create("number", 42, pkg)
    p = ProjectVariable.create("image","assets/1.png", pkg)
    assert p.valid and p.get_actual_data() == png_bytes

    fmt = p.to_format_string()                  # 生成格式化字符串（base64）
    p2 = ProjectVariable.from_format_string(fmt, pkg)  # 反向还原
    assert p2.type == "png" and p2.data == "assets/1.png"
"""

from __future__ import annotations

import base64
import json
from typing import Any, ClassVar, Dict, List, Optional, TYPE_CHECKING

from .path_util import norm_maybe_root

if TYPE_CHECKING:
    from .kscp_package import KscpPackage

__all__ = ["VariableType", "ProjectVariable"]


class VariableType:
    """变量类型基类（预留接口）。

    新增类型：子类化本类、设置 ``name``、``is_resource``、``suffixes``，实现
    ``is_valid`` 与 ``to_actual``（可选重写 ``normalize``），再以
    ``ProjectVariable.register_type(实例)`` 注册。
    """

    name: str = ""
    is_resource: bool = False  # 本类型 data 是否为工程资源（如文件路径）；字面值类型为 False
    suffixes: tuple = ()      # 资源类接受的后缀（小写、含点，如 ('.png', '.jpg')）；非资源为空
    description: str = ""    # 类型描述词（创建对话框下拉项展示）；默认空，自定义类型可不填

    def normalize(self, data: Any) -> Any:
        """规范 ``data`` 的存储形式；默认原样返回。在 ``create`` 时先调用。"""
        return data

    def is_valid(self, data: Any, package: "KscpPackage") -> bool:
        """判定 ``data`` 对本类型是否合规。"""
        raise NotImplementedError

    def to_actual(self, data: Any, package: "KscpPackage") -> Any:
        """由记录的 ``data`` 取实际/完整数据。"""
        raise NotImplementedError


# ----------------------------------------------------------------
# 内置类型
# ----------------------------------------------------------------
class _StringType(VariableType):
    name = "string"
    description = "文本字符串"

    def is_valid(self, data: Any, package: "KscpPackage") -> bool:
        return isinstance(data, str)

    def to_actual(self, data: Any, package: "KscpPackage") -> Any:
        return data


class _NumberType(VariableType):
    name = "number"
    description = "整数或小数"

    def is_valid(self, data: Any, package: "KscpPackage") -> bool:
        # bool 是 int 的子类，需排除，避免 True/False 被当作 number
        return isinstance(data, (int, float)) and not isinstance(data, bool)

    def to_actual(self, data: Any, package: "KscpPackage") -> Any:
        return data


class _ImageType(VariableType):
    name = "image"
    is_resource = True  # data 为工程资源路径
    suffixes = (".png", ".jpg")  # 接受的图片后缀
    description = "图片资源（工程 assets 内的 .png/.jpg）"

    def normalize(self, data: Any) -> Any:
        """把路径规范成正斜杠、去前导 ``/``、折叠 ``.``、拒 ``..``（委托 :func:`model.path_util.norm_maybe_root`）。"""
        if not isinstance(data, str):
            return data
        return norm_maybe_root(data)

    def is_valid(self, data: Any, package: "KscpPackage") -> bool:
        if not isinstance(data, str):
            return False
        if not data.startswith("assets/"):
            return False
        if not any(data.lower().endswith(s) for s in self.suffixes):
            return False
        return package.is_file(data)

    def to_actual(self, data: Any, package: "KscpPackage") -> Any:
        return package.read_file(data)


class ProjectVariable:
    """一个工程变量：``type`` + ``data`` + ``valid`` + ``is_resource``，并可访问工程资源。"""

    # 类级类型注册表：类型名 -> 类型处理器
    _TYPES: ClassVar[Dict[str, VariableType]] = {}

    def __init__(self) -> None:
        self._type: str = ""
        self._data: Any = None
        self._valid: bool = False
        self._package: Optional["KscpPackage"] = None

    # ================================================================
    # 类型注册（预留接口）
    # ================================================================
    @classmethod
    def register_type(cls, handler: VariableType) -> None:
        """注册一个变量类型处理器（预留接口）。"""
        if not handler.name:
            raise ValueError("类型处理器缺少 name")
        cls._TYPES[handler.name] = handler

    @classmethod
    def supported_types(cls) -> List[str]:
        """所支持的变量类型列表（按字典序）。"""
        return sorted(cls._TYPES)

    @classmethod
    def type_of(cls, vtype: str) -> "Optional[VariableType]":
        """返回类型名对应的类型处理器（未注册返回 ``None``）。

        供外部按类型查询 ``is_resource`` / ``suffixes`` 等，无需访问私有注册表。
        """
        return cls._TYPES.get(vtype)

    # ================================================================
    # 创建
    # ================================================================
    @classmethod
    def create(cls, vtype: str, data: Any,
               package: "KscpPackage") -> "ProjectVariable":
        """静态生成单个变量。

        ``vtype`` 为类型名、``data`` 为数据（文件类只能来自工程资源 ``package``）。
        未知类型抛 :class:`ValueError`；数据不合规不抛错、置 ``valid=False``。
        """
        if vtype not in cls._TYPES:
            raise ValueError(
                "不支持的变量类型: %r（支持: %s）" % (vtype, cls.supported_types()))
        handler = cls._TYPES[vtype]
        ndata = handler.normalize(data)
        var = cls()
        var._type = vtype
        var._data = ndata
        var._package = package
        var._valid = bool(handler.is_valid(ndata, package))
        return var

    @classmethod
    def from_format_string(cls, fmt: str,
                           package: "KscpPackage") -> "ProjectVariable":
        """由格式化字符串（base64）反解出 ``(type, data)``，再 ``create`` 还原对象。

        经 ``create`` 重新校验，故 ``valid`` 反映当前 ``package`` 的真实状态。
        """
        obj = cls._decode(fmt)
        return cls.create(obj["t"], obj["d"], package)

    # ================================================================
    # 属性
    # ================================================================
    @property
    def type(self) -> str:
        """变量类型名。"""
        return self._type

    @property
    def data(self) -> Any:
        """变量数据（规范化后存储）。"""
        return self._data

    @property
    def valid(self) -> bool:
        """变量是否有效（创建时校验）。"""
        return self._valid

    @property
    def is_resource(self) -> bool:
        """是否为资源类变量：``data`` 为工程资源（如 png 的资源路径）时为 ``True``，字面值类型为 ``False``。"""
        return self._TYPES[self._type].is_resource

    @property
    def suffixes(self) -> List[str]:
        """资源后缀列表：资源类变量接受的后缀（如 png 为 ``['.png', '.jpg']``）；非资源类为 ``[]``。"""
        return list(self._TYPES[self._type].suffixes)

    # ================================================================
    # 格式化字符串
    # ================================================================
    def to_format_string(self) -> str:
        """提取 ``type``+``data`` 生成 base64 格式化字符串。

        格式：``json({"t": type, "d": data})`` 经 UTF-8、urlsafe base64 去填充。
        ``valid`` 不入串——还原时重新校验。
        """
        raw = json.dumps({"t": self._type, "d": self._data}, ensure_ascii=False)
        return base64.urlsafe_b64encode(
            raw.encode("utf-8")).decode("ascii").rstrip("=")

    @staticmethod
    def _decode(fmt: str) -> Dict[str, Any]:
        """反解格式化字符串为 ``{"t": ..., "d": ...}``。"""
        if not isinstance(fmt, str) or not fmt:
            raise ValueError("无效的变量格式化字符串: %r" % (fmt,))
        pad = "=" * (-len(fmt) % 4)
        try:
            raw = base64.urlsafe_b64decode((fmt + pad).encode("ascii"))
            obj = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as e:
            raise ValueError("无效的变量格式化字符串: %r（%s）" % (fmt, e))
        if not isinstance(obj, dict) or "t" not in obj or "d" not in obj:
            raise ValueError("无效的变量格式化字符串: %r" % (fmt,))
        return obj

    # ================================================================
    # 实际数据
    # ================================================================
    def get_actual_data(self) -> Any:
        """获取实际/完整数据。

        ``string``→原字符串；``number``→数值；``png``→经 ``package`` 读取的文件字节。
        ``valid=False`` 时抛 :class:`ValueError`。
        """
        if not self._valid:
            raise ValueError("变量数据不合规，无法获取实际数据")
        handler = self._TYPES[self._type]
        # create() 总会设置 _package；valid=True 隐含校验已用过它，此处必非 None
        if self._package is None:  # pragma: no cover - 防御性
            raise ValueError("变量缺少工程资源上下文")
        return handler.to_actual(self._data, self._package)

    # ================================================================
    # 双下方法
    # ================================================================
    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ProjectVariable):
            return NotImplemented
        return (self._type, self._data, self._valid) == (
            other._type, other._data, other._valid)

    def __hash__(self) -> int:
        # __eq__ 已定义则必须配套 __hash__（评审#14）：否则对象不可哈希，
        # 不能作 dict key / set 元素
        return hash((self._type, self._data, self._valid))

    def __repr__(self) -> str:
        return "ProjectVariable(type=%r, data=%r, valid=%r)" % (
            self._type, self._data, self._valid)


# 注册内置类型
ProjectVariable.register_type(_StringType())
ProjectVariable.register_type(_NumberType())
ProjectVariable.register_type(_ImageType())


# ================================================================
# 冒烟演示：直接 ``python -m model.project_variable`` 运行
# ================================================================
if __name__ == "__main__":
    import tempfile

    from model.kscp_package import KscpPackage

    with tempfile.TemporaryDirectory() as td:
        # 工程资源
        pkg = KscpPackage.create_empty()
        png_bytes = b"\x89PNG\r\n\x1a\n" + bytes(range(8))
        pkg.write_file("assets/1.png", png_bytes)
        pkg.write_file("assets/曲库/2.png", b"IMG2")  # 含中文子目录

        # 三类型 create + valid
        s = ProjectVariable.create("string", "你好", pkg)
        n = ProjectVariable.create("number", 42, pkg)
        f = ProjectVariable.create("number", 3.14, pkg)
        p = ProjectVariable.create("image","assets/1.png", pkg)
        pcn = ProjectVariable.create("image","assets/曲库/2.png", pkg)
        assert s.valid and n.valid and f.valid and p.valid and pcn.valid
        assert s.data == "你好" and n.data == 42 and f.data == 3.14
        assert p.data == "assets/1.png"
        # is_resource：资源类（image）为 True，字面值（string/number）为 False
        assert not s.is_resource and not n.is_resource and not f.is_resource
        assert p.is_resource and pcn.is_resource
        # suffixes：image 接受 .png/.jpg；字面值类型为 []
        assert p.suffixes == [".png", ".jpg"]
        assert s.suffixes == [] and n.suffixes == []
        pkg.write_file("assets/photo.jpg", b"JPG")
        jpg = ProjectVariable.create("image","assets/photo.jpg", pkg)
        assert jpg.valid and jpg.is_resource and jpg.suffixes == [".png", ".jpg"]
        assert jpg.get_actual_data() == b"JPG"

        # 不合规
        bad_str = ProjectVariable.create("string", 123, pkg)
        bad_num = ProjectVariable.create("number", "123", pkg)   # 字符串非数值
        bad_bool = ProjectVariable.create("number", True, pkg)    # bool 不算 number
        bad_png_missing = ProjectVariable.create("image","assets/nope.png", pkg)
        bad_png_suffix = ProjectVariable.create("image","assets/1.txt", pkg)
        bad_png_prefix = ProjectVariable.create("image","imgs/1.png", pkg)
        bad_png_backslash = ProjectVariable.create("image","assets\\1.png", pkg)
        assert not bad_str.valid
        assert not bad_num.valid
        assert not bad_bool.valid
        assert not bad_png_missing.valid
        assert not bad_png_suffix.valid
        assert not bad_png_prefix.valid
        assert bad_png_backslash.valid and bad_png_backslash.data == "assets/1.png"

        # 未知类型
        try:
            ProjectVariable.create("audio", "x", pkg)
            raise AssertionError("未知类型应抛 ValueError")
        except ValueError:
            pass

        # to / from_format_string 往返（三类型）
        for var in (s, n, f, p, pcn):
            fmt = var.to_format_string()
            assert "=" not in fmt and "+" not in fmt and "/" not in fmt  # 去填充、urlsafe
            back = ProjectVariable.from_format_string(fmt, pkg)
            assert back.type == var.type and back.data == var.data
            assert back.valid == var.valid
            assert back == var

        # 非法变量的格式化串仍可编码、还原（还原后仍非法）
        fmt_bad = bad_png_missing.to_format_string()
        back_bad = ProjectVariable.from_format_string(fmt_bad, pkg)
        assert back_bad.type == "image" and back_bad.data == "assets/nope.png"
        assert not back_bad.valid

        # 非法 base64
        try:
            ProjectVariable.from_format_string("not*valid*", pkg)
            raise AssertionError("非法 base64 应抛 ValueError")
        except ValueError:
            pass

        # get_actual_data
        assert s.get_actual_data() == "你好"
        assert n.get_actual_data() == 42
        assert f.get_actual_data() == 3.14
        assert p.get_actual_data() == png_bytes
        assert pcn.get_actual_data() == b"IMG2"
        try:  # 非法变量取实际数据应抛错
            bad_png_missing.get_actual_data()
            raise AssertionError("非法变量取实际数据应抛 ValueError")
        except ValueError:
            pass

        # supported_types
        assert ProjectVariable.supported_types() == ["image", "number", "string"]

        # 预留接口：注册自定义类型
        class _JsonType(VariableType):
            name = "json"
            def is_valid(self, data, package):
                return isinstance(data, str)
            def to_actual(self, data, package):
                return json.loads(data)
        ProjectVariable.register_type(_JsonType())
        assert "json" in ProjectVariable.supported_types()
        j = ProjectVariable.create("json", '{"a":1}', pkg)
        assert j.valid and j.get_actual_data() == {"a": 1}
        assert not j.is_resource  # 自定义字面值类型默认不是资源类
        # 自定义类型也能往返
        jb = ProjectVariable.from_format_string(j.to_format_string(), pkg)
        assert jb == j

        # 预留接口：自定义资源类类型（is_resource=True）
        class _AudioType(VariableType):
            name = "audio"
            is_resource = True
            def is_valid(self, data, package):
                return isinstance(data, str) and package.is_file(data)
            def to_actual(self, data, package):
                return package.read_file(data)
        ProjectVariable.register_type(_AudioType())
        pkg.write_file("assets/bgm.mp3", b"MP3")
        a = ProjectVariable.create("audio", "assets/bgm.mp3", pkg)
        assert a.is_resource and a.valid and a.get_actual_data() == b"MP3"
        ab = ProjectVariable.from_format_string(a.to_format_string(), pkg)
        assert ab.is_resource and ab == a

    # 评审#14：__eq__ 配套 __hash__ —— 可作 dict key / set 元素（相等 → 同哈希）
    _v1 = ProjectVariable.create("number", 42, pkg)
    _v2 = ProjectVariable.from_format_string(_v1.to_format_string(), pkg)
    assert hash(_v1) == hash(_v2)
    assert len({_v1: "x", _v2: "y"}) == 1            # 相等对象同键
    assert _v1 in {_v2}

    print("ProjectVariable smoke OK")
