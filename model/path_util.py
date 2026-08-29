# -*- coding: utf-8 -*-
"""
路径归一化共享工具
==================

KscpPackage / VariableTree / StepListStore / ProjectVariable 各自曾拷贝一份
路径归一化逻辑且语义不一致（``.`` 折叠 vs 拒绝）。本模块统一收敛：**反斜杠→
正斜杠、去前导 ``/``、折叠空段与 ``.``、拒绝 ``..``**。

基本用法
--------
::

    from model.path_util import norm_maybe_root, normalize, validate_name

    norm_maybe_root("")         # ''（根）
    norm_maybe_root("a\\b/./c")  # 'a/b/c'
    normalize("a//b")            # 'a/b'；根路径抛 ValueError
    validate_name("名")          # 合法通过；'' / 'a/b' / '.' / '..' 抛 ValueError
"""
from __future__ import annotations

__all__ = ["norm_maybe_root", "normalize", "validate_name"]


def norm_maybe_root(path: str) -> str:
    """归一化路径；根目录返回空串。反斜杠→正斜杠、去前导 ``/``、折叠空段与 ``.``、拒绝 ``..``。"""
    p = path.replace("\\", "/").lstrip("/")
    parts = [seg for seg in p.split("/") if seg not in ("", ".")]
    if any(seg == ".." for seg in parts):
        raise ValueError("路径不得包含 '..'（禁止越出根目录）: %r" % path)
    return "/".join(parts)


def normalize(path: str) -> str:
    """归一化为非空路径；根目录在此视为非法（文件/变量/列表操作不接受根）。"""
    n = norm_maybe_root(path)
    if not n:
        raise ValueError("路径不能仅指向根目录: %r" % path)
    return n


def validate_name(name: str) -> None:
    """校验单个名称段（变量名/分组名/列表名）：非空、不含 ``/``、不为 ``.``/``..``。"""
    if not name or "/" in name or name in (".", ".."):
        raise ValueError("非法名称: %r" % name)


# ================================================================
# 冒烟演示：直接 ``python -m model.path_util`` 运行
# ================================================================
if __name__ == "__main__":
    # 根与等价根
    assert norm_maybe_root("") == ""
    assert norm_maybe_root("/") == ""
    assert norm_maybe_root(".") == ""
    # 反斜杠 / 前导 / / 空段 / `.` 折叠
    assert norm_maybe_root("a\\b") == "a/b"
    assert norm_maybe_root("/a/") == "a"
    assert norm_maybe_root("a//b") == "a/b"
    assert norm_maybe_root("a/./b/./c") == "a/b/c"
    # '..' 拒绝
    for bad in ("..", "a/..", "../x", "a/../../x"):
        try:
            norm_maybe_root(bad)
            raise AssertionError("'..' 路径应抛 ValueError: %r" % bad)
        except ValueError:
            pass
    # normalize：非空路径
    assert normalize("a//b") == "a/b"
    for bad in ("", "/", "."):
        try:
            normalize(bad)
            raise AssertionError("根路径应抛 ValueError: %r" % bad)
        except ValueError:
            pass
    # validate_name
    validate_name("名")
    validate_name("_ok")
    for bad in ("", "a/b", ".", ".."):
        try:
            validate_name(bad)
            raise AssertionError("非法名应抛 ValueError: %r" % bad)
        except ValueError:
            pass

    print("path_util smoke OK")
