# -*- coding: utf-8 -*-
"""
全局热键监听（执行器触发信号）
================================

pynput 全局键盘监听：按下配置的单字符热键 → ``on_toggle()`` 回调。
回调发生在 pynput 监听线程——UI 侧必须经 Qt 信号跨线程桥接。

**已知限制**（实测确认）：pynput 监听器会捕获 :meth:`InputControl.key_click`
模拟的按键；热键与步骤模拟的按键字符冲突时会误触发停止。UI 侧以 tooltip
提示用户避开步骤用键（spec 决策：文档提醒方案）。

基本用法
--------
::

    listener = HotkeyListener("`", lambda: print("toggle"))
    listener.start()          # 后台线程监听
    listener.stop()
"""
from __future__ import annotations

from typing import Callable, Optional

__all__ = ["HotkeyListener"]


class HotkeyListener:
    """单字符热键全局监听；按下即回调 ``on_toggle``（大小写不敏感）。"""

    def __init__(self, hotkey: str, on_toggle: Callable[[], None]) -> None:
        if not isinstance(hotkey, str) or len(hotkey) != 1:
            raise ValueError("热键必须是单个字符，而非 %r" % (hotkey,))
        self._hotkey = hotkey
        self._on_toggle = on_toggle
        self._listener: Optional[object] = None

    @property
    def hotkey(self) -> str:
        return self._hotkey

    def start(self) -> None:
        """启动后台监听线程（幂等）。"""
        if self._listener is not None:
            return
        from pynput import keyboard

        self._listener = keyboard.Listener(on_press=self._on_press)
        self._listener.start()

    def stop(self) -> None:
        """停止监听（幂等）。"""
        if self._listener is not None:
            self._listener.stop()
            self._listener = None

    def _on_press(self, key) -> None:
        ch = getattr(key, "char", None)
        if ch is not None and ch.lower() == self._hotkey.lower():
            self._on_toggle()


# ================================================================
# 冒烟演示：直接 ``python -m model.hotkey`` 运行（不启动真实监听）
# ================================================================
if __name__ == "__main__":
    class _FakeKey:
        def __init__(self, ch):
            self.char = ch

    # 构造校验
    for bad in ("", "ab", None, 1):
        try:
            HotkeyListener(bad, lambda: None)
            raise AssertionError("非法热键应抛 ValueError: %r" % (bad,))
        except ValueError:
            pass
    # 按键解析：匹配（大小写不敏感）/ 不匹配 / 功能键无 char
    toggles = []
    l = HotkeyListener("f", lambda: toggles.append(1))
    assert l.hotkey == "f"
    l._on_press(_FakeKey("f"))
    l._on_press(_FakeKey("F"))
    l._on_press(_FakeKey("g"))
    l._on_press(_FakeKey(None))          # 功能键（如 F1）char=None → 忽略
    assert toggles == [1, 1], toggles
    # stop 幂等（未启动也安全）
    l.stop()

    print("HotkeyListener smoke OK")
