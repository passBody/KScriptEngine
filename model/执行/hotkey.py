# -*- coding: utf-8 -*-
"""
全局热键监听（执行器触发信号）
================================

pynput 全局键盘监听：按下配置的热键 → ``on_toggle()`` 回调。回调发生在
pynput 监听线程——UI 侧必须经 Qt 信号跨线程桥接。

热键规格（大小写不敏感，经 :func:`normalize_hotkey` 规范化）：
* 单字符（`` ` `` / ``f``）——旧格式，按下即触发；
* 命名键（``F1``…``F12``、``Space``、``Enter``、``Esc`` 等）；
* 组合（``Ctrl+Alt+I``、``Ctrl+Shift+F5``，修饰键 Ctrl/Alt/Shift/Cmd）；
* 单独修饰键（``Ctrl``）——按下即触发；若与含该修饰键的组合并存
  （前缀冲突），由调用方传 ``defer_lone_modifier=True``：按下不触发，
  期间按了其他键则放弃，期间未按其他键就松开才触发（组合优先）。

匹配语义：组合/命名键要求**按住集合与要求集合严格相等**（按着 Ctrl
再按 f 不触发 f 热键）；按住不放的键盘自动重复只触发一次。

**已知限制**（实测确认）：pynput 监听器会捕获 :meth:`InputControl.key_click`
模拟的按键；热键与步骤模拟按键冲突时会误触发。UI 侧以 tooltip 提示避开
（spec 决策：文档提醒方案）。

基本用法
--------
::

    listener = HotkeyListener("Ctrl+Alt+I", lambda: print("toggle"))
    listener.start()          # 后台线程监听
    listener.stop()
"""
from __future__ import annotations

from typing import FrozenSet, Optional, Tuple

__all__ = ["HotkeyListener", "normalize_hotkey", "parse_hotkey"]

# 命名键别名 → 规范名（含 Qt QKeySequence PortableText 的写法）
_ALIASES = {
    "ctrl": "ctrl", "control": "ctrl",
    "alt": "alt", "shift": "shift",
    "cmd": "cmd", "win": "cmd", "meta": "cmd", "command": "cmd",
    "f1": "f1", "f2": "f2", "f3": "f3", "f4": "f4", "f5": "f5", "f6": "f6",
    "f7": "f7", "f8": "f8", "f9": "f9", "f10": "f10", "f11": "f11", "f12": "f12",
    "space": "space", "enter": "enter", "return": "enter",
    "tab": "tab", "esc": "esc", "escape": "esc",
    "backspace": "backspace", "insert": "insert", "ins": "insert",
    "delete": "delete", "del": "delete",
    "home": "home", "end": "end",
    "pageup": "pageup", "pgup": "pageup",
    "pagedown": "pagedown", "pgdown": "pagedown",
    "up": "up", "down": "down", "left": "left", "right": "right",
}

_MODIFIERS = {"ctrl", "alt", "shift", "cmd"}

# 规范名 → 显示名
_DISPLAY = {
    "ctrl": "Ctrl", "alt": "Alt", "shift": "Shift", "cmd": "Cmd",
    "f1": "F1", "f2": "F2", "f3": "F3", "f4": "F4", "f5": "F5", "f6": "F6",
    "f7": "F7", "f8": "F8", "f9": "F9", "f10": "F10", "f11": "F11", "f12": "F12",
    "space": "Space", "enter": "Enter", "tab": "Tab", "esc": "Esc",
    "backspace": "Backspace", "insert": "Insert", "delete": "Delete",
    "home": "Home", "end": "End", "pageup": "PageUp", "pagedown": "PageDown",
    "up": "Up", "down": "Down", "left": "Left", "right": "Right",
}


def _key_id(key) -> Optional[str]:
    """pynput 按键对象 → 稳定标识：``char:x`` 或 ``key:name``；无法识别 → None。"""
    ch = getattr(key, "char", None)
    if ch is not None:
        return "char:" + ch.lower()
    name = getattr(key, "name", None)
    if name is not None:
        return "key:" + name
    return None


def parse_hotkey(spec: str) -> Tuple[FrozenSet[str], str]:
    """解析热键规格 → ``(修饰键标识集, 目标键标识)``；非法 → :class:`ValueError`。

    标识与 :func:`_key_id` 同构（``key:ctrl`` / ``char:i``），不依赖 pynput 导入。
    """
    if not isinstance(spec, str):
        raise ValueError("热键规格必须是字符串，而非 %r" % (spec,))
    parts = [p.strip() for p in spec.split("+")]
    if not parts or any(not p for p in parts):
        raise ValueError("非法的热键规格: %r" % spec)
    mods = set()
    target: Optional[str] = None
    for p in parts:
        low = p.lower()
        canonical = _ALIASES.get(low)
        if canonical is not None and canonical in _MODIFIERS:
            mods.add("key:" + canonical)
        elif target is not None:
            raise ValueError("热键含多个按键: %r" % spec)
        elif len(p) == 1:
            target = "char:" + low          # 单字符（旧格式兼容）
        elif canonical is not None:
            target = "key:" + canonical     # 命名键（f1/space/…）
        else:
            raise ValueError("无法识别的按键: %r" % p)
    if target is None:
        # 全为修饰键：仅支持单个修饰键（"Ctrl"）——多修饰键组合（"Ctrl+Alt"）无意义
        if len(mods) != 1:
            raise ValueError("热键不能只有修饰键组合: %r" % spec)
        target = next(iter(mods))
        mods = set()
    return frozenset(mods), target


def normalize_hotkey(spec) -> Optional[str]:
    """解析并返回**规范形式**（修饰键顺序 Ctrl+Alt+Shift+Cmd、命名键大写、
    字母按键大写——与 Qt QKeySequence 显示一致）；非法 → None。
    存盘/查重/比较统一用它（大小写不敏感由解析保证）。"""
    try:
        mods, target = parse_hotkey(spec)
    except ValueError:
        return None
    parts = []
    for m in ("ctrl", "alt", "shift", "cmd"):
        if ("key:" + m) in mods:
            parts.append(_DISPLAY[m])
    if target.startswith("char:"):
        ch = target[5:]
        parts.append(ch.upper() if ch.isalpha() else ch)
    else:
        parts.append(_DISPLAY[target[4:]])
    return "+".join(parts)


class HotkeyListener:
    """全局热键监听：按下配置热键（单字符/命名键/组合/单独修饰键）→ ``on_toggle``。

    ``defer_lone_modifier``：单独修饰键热键存在前缀冲突时传 True（组合优先，
    释放判定）；否则按下即触发。
    """

    def __init__(self, hotkey: str, on_toggle, defer_lone_modifier: bool = False) -> None:
        spec = normalize_hotkey(hotkey)
        if spec is None:
            raise ValueError("非法的热键: %r" % (hotkey,))
        self._hotkey = spec
        self._on_toggle = on_toggle
        self._defer = bool(defer_lone_modifier)
        self._mods, self._target = parse_hotkey(spec)
        self._lone_modifier = not self._mods and self._target in {
            "key:ctrl", "key:alt", "key:shift", "key:cmd"}
        self._held = set()           # 当前按住的键（含修饰键）
        self._pressed = set()        # 已触发过的按下（防键盘自动重复）
        self._pending = False        # defer 修饰键已按下、待释放判定
        self._interrupted = False    # pending 期间按了其他键 → 放弃
        self._listener: Optional[object] = None

    @property
    def hotkey(self) -> str:
        return self._hotkey

    @property
    def defer_lone_modifier(self) -> bool:
        return self._defer

    def start(self) -> None:
        """启动后台监听线程（幂等）。"""
        if self._listener is not None:
            return
        from pynput import keyboard

        self._listener = keyboard.Listener(
            on_press=self._on_press, on_release=self._on_release)
        self._listener.start()

    def stop(self) -> None:
        """停止监听（幂等）。"""
        if self._listener is not None:
            self._listener.stop()
            self._listener = None

    def _on_press(self, key) -> None:
        kid = _key_id(key)
        if kid is None or kid in self._pressed:
            return                     # 不可识别键 / 自动重复去重
        self._pressed.add(kid)
        is_mod = kid in {"key:ctrl", "key:alt", "key:shift", "key:cmd"}
        if is_mod:
            self._held.add(kid)
        if self._lone_modifier and kid == self._target:
            if self._defer:
                self._pending = True   # 组合优先：待释放判定
                self._interrupted = False
            else:
                self._on_toggle()      # 无前缀冲突：按下即触发
            return
        if self._pending:
            self._interrupted = True   # pending 期间按了任何其他键 → 放弃
        # 命名键/单字符/组合：按住集合严格相等 + 目标键相等 → 触发
        if kid == self._target and self._held == self._mods:
            self._on_toggle()

    def _on_release(self, key) -> None:
        kid = _key_id(key)
        if kid is None:
            return
        self._pressed.discard(kid)
        if kid in self._held:
            self._held.discard(kid)
        if self._pending and kid == self._target:
            self._pending = False
            if not self._interrupted:
                self._on_toggle()      # 期间未按其他键 → 单独修饰键生效


# ================================================================
# 冒烟演示：直接 ``python -m model.执行.hotkey`` 运行（不启动真实监听）
# ================================================================
if __name__ == "__main__":
    class _FakeKey:
        """假按键对象：char（KeyCode）或 name（Key.xxx）。"""

        def __init__(self, ch=None, name=None):
            self.char = ch
            self.name = name

    # ---- normalize / parse ----
    assert normalize_hotkey("F1") == "F1"
    assert normalize_hotkey("f1") == "F1"
    assert normalize_hotkey("Ctrl+Alt+I") == "Ctrl+Alt+I"
    assert normalize_hotkey("ctrl+alt+i") == "Ctrl+Alt+I"
    assert normalize_hotkey("CTRL + ALT + I") == "Ctrl+Alt+I"
    assert normalize_hotkey("Ctrl") == "Ctrl"
    assert normalize_hotkey("control") == "Ctrl"        # 别名
    assert normalize_hotkey("`") == "`"
    assert normalize_hotkey("F") == "F"                 # 字母按键大写（与 Qt 显示一致）
    assert normalize_hotkey("Ctrl+Shift+Alt+F5") == "Ctrl+Alt+Shift+F5"   # 顺序规范
    assert normalize_hotkey("Return") == "Enter"        # Qt 名别名
    assert normalize_hotkey("PgUp") == "PageUp"
    assert normalize_hotkey("Cmd+Win+X") == "Cmd+X"     # 重复修饰键去重
    for bad in ("", None, 1, "ab", "Ctrl+Alt", "Ctrl+Alt+", "++",
                "F13", "Ctrl+Alt+I+J", "Ctrl+Xxx", "a+b"):
        assert normalize_hotkey(bad) is None, bad
    mods, target = parse_hotkey("Ctrl+Alt+I")
    assert mods == frozenset({"key:ctrl", "key:alt"}) and target == "char:i"
    assert parse_hotkey("Ctrl") == (frozenset(), "key:ctrl")
    assert parse_hotkey("F1") == (frozenset(), "key:f1")

    def _mk(spec, defer=False):
        toggles = []
        l = HotkeyListener(spec, lambda: toggles.append(1), defer)
        return l, toggles

    # ---- F1：按下触发；自动重复只一次；释放后再按再触发 ----
    l, tg = _mk("F1")
    assert l.hotkey == "F1"
    l._on_press(_FakeKey(name="f1"))
    l._on_press(_FakeKey(name="f1"))                    # 按住自动重复 → 忽略
    assert tg == [1]
    l._on_release(_FakeKey(name="f1"))
    l._on_press(_FakeKey(name="f1"))
    assert tg == [1, 1]

    # ---- Ctrl+Alt+I：修饰集严格相等 + 目标键 ----
    l, tg = _mk("Ctrl+Alt+I")
    l._on_press(_FakeKey(name="ctrl"))
    l._on_press(_FakeKey(name="alt"))
    l._on_press(_FakeKey(ch="i"))
    assert tg == [1]
    l._on_press(_FakeKey(ch="i"))                       # 按住不放重复 → 忽略
    l._on_press(_FakeKey(ch="j"))                       # 目标不符
    assert tg == [1]
    l._on_release(_FakeKey(ch="i"))
    l._on_press(_FakeKey(ch="i"))                       # 释放后再按 → 再触发
    assert tg == [1, 1]
    # 按住集合多一个 shift → 不触发
    l._on_press(_FakeKey(name="shift"))
    l._on_press(_FakeKey(ch="i"))
    assert tg == [1, 1]
    l._on_release(_FakeKey(ch="i"))
    l._on_release(_FakeKey(name="shift"))
    l._on_release(_FakeKey(name="alt"))
    l._on_release(_FakeKey(name="ctrl"))

    # ---- 单字符（旧格式）：按下触发；按着 Ctrl 按 f 不再触发（严格匹配） ----
    l, tg = _mk("f")
    l._on_press(_FakeKey(ch="f"))
    assert tg == [1]
    l._on_release(_FakeKey(ch="f"))
    l._on_press(_FakeKey(name="ctrl"))
    l._on_press(_FakeKey(ch="f"))
    l._on_release(_FakeKey(ch="f"))
    l._on_release(_FakeKey(name="ctrl"))
    assert tg == [1], tg

    # ---- 单独修饰键：无冲突按下即触发；有冲突（defer）按下不触发 ----
    l, tg = _mk("Ctrl")
    l._on_press(_FakeKey(name="ctrl"))
    assert tg == [1], tg
    l._on_release(_FakeKey(name="ctrl"))

    l, tg = _mk("Ctrl", defer=True)
    assert l.defer_lone_modifier is True
    # 单独按 Ctrl → 释放时触发
    l._on_press(_FakeKey(name="ctrl"))
    assert tg == []
    l._on_release(_FakeKey(name="ctrl"))
    assert tg == [1]
    # 组合优先：按下 Ctrl 后按了 Alt 再按 I → 中断，释放 Ctrl 不触发
    l._on_press(_FakeKey(name="ctrl"))
    l._on_press(_FakeKey(name="alt"))
    l._on_press(_FakeKey(ch="i"))
    l._on_release(_FakeKey(ch="i"))
    l._on_release(_FakeKey(name="alt"))
    l._on_release(_FakeKey(name="ctrl"))
    assert tg == [1], tg
    # 组合监听器视角：Ctrl+Alt+I 全程各触发一次
    lc, tgc = _mk("Ctrl+Alt+I")
    lc._on_press(_FakeKey(name="ctrl"))
    lc._on_press(_FakeKey(name="alt"))
    lc._on_press(_FakeKey(ch="i"))
    assert tgc == [1]
    lc._on_release(_FakeKey(ch="i"))
    lc._on_release(_FakeKey(name="alt"))
    lc._on_release(_FakeKey(name="ctrl"))

    # ---- 构造校验：非法规格抛 ValueError ----
    for bad in ("", "ab", "F13", "Ctrl+Alt", None, 1):
        try:
            HotkeyListener(bad, lambda: None)
            raise AssertionError("非法热键应抛 ValueError: %r" % (bad,))
        except ValueError:
            pass
    # 功能键无 char 无 name → _key_id None → 忽略不崩
    l, tg = _mk("F1")
    l._on_press(_FakeKey())
    assert tg == []
    # stop 幂等（未启动也安全）
    l.stop()

    print("HotkeyListener smoke OK")
