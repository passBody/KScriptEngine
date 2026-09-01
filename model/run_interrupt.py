# -*- coding: utf-8 -*-
"""
执行期可中断睡眠（立即停止支撑）
================================

「立即停止」的机制：执行器把**当前**停止事件登记到本模块；步骤内的长时间
等待（延时、连击间隔、拖拽插值等）经 :func:`interruptible_sleep` 以 20ms
粒度轮询该事件——停止请求触发后最迟 ~20ms 返回，当前步骤随即结束、执行器
不再开始下一步。

未登记事件（如编辑器内单跑步骤）时退化为普通 ``time.sleep``，行为不变。
"""
import threading
import time
from typing import Optional

__all__ = ["clear_stop_event", "interruptible_sleep", "set_stop_event"]

_active_stop: Optional[threading.Event] = None
_lock = threading.Lock()


def set_stop_event(event: threading.Event) -> None:
    """登记当前执行器的停止事件（执行器 start 时调用）。"""
    global _active_stop
    with _lock:
        _active_stop = event


def clear_stop_event(event: threading.Event) -> None:
    """注销停止事件（执行器收尾时调用；仅当仍是本人登记时清）。"""
    global _active_stop
    with _lock:
        if _active_stop is event:
            _active_stop = None


def interruptible_sleep(seconds: float, poll: float = 0.02) -> bool:
    """可中断睡眠：返回 True = 被立即停止打断（调用方应尽快结束当前步骤）。

    未登记停止事件时等价 ``time.sleep`` 并返回 False。
    """
    if seconds <= 0:
        return False
    with _lock:
        ev = _active_stop
    if ev is None:
        time.sleep(seconds)
        return False
    end = time.monotonic() + seconds
    while True:
        remaining = end - time.monotonic()
        if remaining <= 0:
            return False
        if ev.is_set():
            return True                       # 立即停止：中断等待
        time.sleep(min(poll, remaining))


# ================================================================
# 冒烟演示：直接 ``python -m model.run_interrupt`` 运行
# ================================================================
if __name__ == "__main__":
    import time as _t

    # 未登记 → 普通睡眠、返回 False
    _t0 = _t.monotonic()
    assert interruptible_sleep(0.05) is False
    assert _t.monotonic() - _t0 >= 0.05

    # 登记事件：未触发 → 睡满返回 False
    _ev = threading.Event()
    set_stop_event(_ev)
    try:
        _t0 = _t.monotonic()
        assert interruptible_sleep(0.05) is False
        assert _t.monotonic() - _t0 >= 0.05
        # 触发 → 提前返回 True（~20ms 粒度）
        _t0 = _t.monotonic()
        _t2 = _t.monotonic()
        import threading as _th

        def _stop_later():
            _t.sleep(0.03)
            _ev.set()
        _th.Thread(target=_stop_later, daemon=True).start()
        assert interruptible_sleep(2.0) is True
        assert _t.monotonic() - _t0 < 0.5          # 远小于 2s 即被中断
    finally:
        clear_stop_event(_ev)

    # 注销后不再受该事件影响
    assert interruptible_sleep(0.02) is False

    print("run_interrupt smoke OK")
