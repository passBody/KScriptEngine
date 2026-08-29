# -*- coding: utf-8 -*-
"""
应用本地配置（热键等）
======================

``setting.json`` 位于应用目录（与 main.py 同级），**不随 .kscp 分发**——
每台机器各自绑定热键。形态::

    {"hotkey": "`"}

基本用法
--------
::

    from model.settings import Settings

    s = Settings.load()
    s.set_hotkey("f")
    s.save()
"""
from __future__ import annotations

import json
import os
import tempfile
from typing import Optional

from model.log_model import LogModel

__all__ = ["Settings"]

_DEFAULT_HOTKEY = "`"


def _default_path() -> str:
    """应用目录下的 setting.json（model/ 的上一级 = 项目根）。"""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(root, "setting.json")


class Settings:
    """应用本地配置：热键等。"""

    def __init__(self, hotkey: str = _DEFAULT_HOTKEY) -> None:
        self._hotkey = hotkey

    @classmethod
    def load(cls, path: Optional[str] = None) -> "Settings":
        """从 ``setting.json`` 载入；文件缺失/损坏 → 默认值 + 日志警告。"""
        p = path or _default_path()
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and isinstance(data.get("hotkey"), str) \
                    and len(data["hotkey"]) == 1:
                return cls(data["hotkey"])
            LogModel.instance().warning("setting.json 热键配置非法，使用默认值")
        except (OSError, ValueError):
            LogModel.instance().warning("setting.json 无法读取，使用默认值")
        return cls()

    @property
    def hotkey(self) -> str:
        return self._hotkey

    def set_hotkey(self, key: str) -> None:
        """设置热键：任意单字符（含数字）；非法抛 :class:`ValueError`。"""
        if not isinstance(key, str) or len(key) != 1:
            raise ValueError("热键必须是单个字符，而非 %r" % (key,))
        self._hotkey = key

    def save(self, path: Optional[str] = None) -> None:
        """原子写盘（临时文件 + os.replace）。"""
        p = path or _default_path()
        raw = json.dumps({"hotkey": self._hotkey}, ensure_ascii=False)
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(p), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(raw)
            os.replace(tmp, p)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise


# ================================================================
# 冒烟演示：直接 ``python -m model.settings`` 运行
# ================================================================
if __name__ == "__main__":
    import tempfile as _tmp

    LogModel._reset_instance()

    with _tmp.TemporaryDirectory() as td:
        p = os.path.join(td, "setting.json")
        # 默认值
        s = Settings.load(p)
        assert s.hotkey == "`"
        # 设置 + 保存 + 读回
        s.set_hotkey("f")
        s.save(p)
        s2 = Settings.load(p)
        assert s2.hotkey == "f"
        # 非法热键
        for bad in ("", "ab", None, 1):
            try:
                s.set_hotkey(bad)
                raise AssertionError("非法热键应抛 ValueError: %r" % (bad,))
            except ValueError:
                pass
        # 数字热键合法（KScript 无数字选参场景）
        s.set_hotkey("7")
        assert s.hotkey == "7"
        # 损坏文件 → 回退默认 + 日志警告
        with open(p, "w", encoding="utf-8") as f:
            f.write("{broken")
        LogModel.instance().clear()
        s3 = Settings.load(p)
        assert s3.hotkey == "`"
        assert any("无法读取" in e.message for e in LogModel.instance().entries)
        # 结构非法（热键缺失/长度错）→ 回退默认
        with open(p, "w", encoding="utf-8") as f:
            f.write('{"hotkey": "ab"}')
        assert Settings.load(p).hotkey == "`"

    print("Settings smoke OK")
