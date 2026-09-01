# -*- coding: utf-8 -*-
"""
执行期可中断睡眠（立即停止支撑）
================================

「立即停止」的机制：执行器在**工作线程内**把停止事件登记到本模块的
**线程本地**存储；步骤内的长时间等待（延时、连击间隔、拖拽插值等）经
:func:`interruptible_sleep` 以 20ms 粒度轮询该事件——停止请求触发后最迟
~20ms 返回，当前步骤随即结束、执行器不再开始下一步。

登记按线程隔离：多个执行器并发（各页独立工作线程）时互不覆盖登记、
互不误停；未登记事件（如编辑器内单跑步骤）时退化为普通 ``time.sleep``，
行为不变。
"""
import threading
import time

__all__ = ["clear_stop_event", "interruptible_sleep", "set_stop_event"]

_local = threading.local()   # 每线程一个停止事件（并发执行器隔离）


def set_stop_event(event: threading.Event) -> None:
    """登记**当前线程**的停止事件（须在会调用 :func:`interruptible_sleep`
    的线程内调用——thread-local 语义要求登记者与睡觉者是同一线程）。"""
    _local.stop_event = event


def clear_stop_event(event: threading.Event) -> None:
    """注销停止事件（执行器工作线程收尾时调用；仅当仍是本人登记时清）。"""
    if getattr(_local, "stop_event", None) is event:
        del _local.stop_event


def interruptible_sleep(seconds: float, poll: float = 0.02) -> bool:
    """可中断睡眠：返回 True = 被立即停止打断（调用方应尽快结束当前步骤）。

    当前线程未登记停止事件时等价 ``time.sleep`` 并返回 False。
    """
    if seconds <= 0:
        return False
    ev = getattr(_local, "stop_event", None)
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
        def _stop_later():
            _t.sleep(0.03)
            _ev.set()
        threading.Thread(target=_stop_later, daemon=True).start()
        _t0 = _t.monotonic()
        assert interruptible_sleep(2.0) is True
        assert _t.monotonic() - _t0 < 0.5          # 远小于 2s 即被中断
    finally:
        clear_stop_event(_ev)

    # 注销后不再受该事件影响
    assert interruptible_sleep(0.02) is False

    # ---- 线程隔离：并发执行器互不覆盖登记、互不误停 ----
    _ev_a = threading.Event()
    _ev_b = threading.Event()
    _res = {}

    def _worker_a():
        set_stop_event(_ev_a)                      # 线程内登记（同 StepRunner 工作线程模式）
        _t0 = _t.monotonic()
        _res["a"] = interruptible_sleep(2.0)
        _res["a_t"] = _t.monotonic() - _t0
        clear_stop_event(_ev_a)

    def _worker_b():
        set_stop_event(_ev_b)
        _t0 = _t.monotonic()
        _res["b"] = interruptible_sleep(0.06)     # B 应睡满（A 的停止不打断 B）
        _res["b_t"] = _t.monotonic() - _t0
        clear_stop_event(_ev_b)

    _ta = threading.Thread(target=_worker_a, daemon=True)
    _ta.start()
    _t.sleep(0.05)                                # A 已进入等待
    _tb = threading.Thread(target=_worker_b, daemon=True)
    _tb.start()
    _t.sleep(0.01)
    _ev_a.set()                                   # 停 A：只应打断 A 的等待
    _ta.join(timeout=3)
    assert not _ta.is_alive(), "A 未被及时打断"
    assert _res["a"] is True and _res["a_t"] < 0.5, _res
    _tb.join(timeout=3)
    assert _res["b"] is False and _res["b_t"] >= 0.055, _res   # B 不受 A 停止影响
    # 主线程未登记 → 普通睡眠（不受已 set 的 _ev_a/_ev_b 影响）
    _t0 = _t.monotonic()
    assert interruptible_sleep(0.03) is False
    assert _t.monotonic() - _t0 >= 0.03

    print("run_interrupt smoke OK")
