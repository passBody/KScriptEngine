# -*- coding: utf-8 -*-
"""
步骤执行器（纯 Python 状态机）
==============================

:class:`StepRunner` 按「程序计数器 + 偏移量」逐条执行全部列表的可运行步骤
（:meth:`StepListStore.all_do_methods`，插入序 DFS、enabled 过滤），类似汇编
逐条执行：

* 偏移量 1 = 下一个；2 = 跳一个；0 = 重调用自身；负值 = 回跳。
* ``request_stop()`` 为协作式停止：当前步骤完成后在下一步前退出。
* 任一步骤 do() 抛异常 → 停止整个执行（错误已由 do() 记日志）。
* 步数上限 ``max_steps`` 防 0/负偏移死循环。

线程模型：``start()`` 在调用线程完成复位后，在工作线程（daemon）执行循环；
状态读写经锁保护；监听者回调在状态变更线程发生（UI 需自行桥接）。

基本用法
--------
::

    runner = StepRunner(store)
    runner.add_state_listener(lambda st: print(st))
    runner.start()           # READY -> RUNNING，工作线程执行
    runner.request_stop()    # 当前步骤完成后停止
"""
import threading
from enum import Enum
from typing import Callable, List, Optional, Tuple

from model.log_model import LogModel
from model.run_interrupt import clear_stop_event, set_stop_event
from model.step import StepStatus
from model.step_list_store import StepListStore

__all__ = ["StepRunner", "StepRunnerState"]


class StepRunnerState(Enum):
    """执行器状态：待命 | 执行中 | 停止中。"""
    READY = "待命"
    RUNNING = "执行中"
    STOPPING = "停止中"


class StepRunner:
    """执行器：PC + 偏移量循环执行全部列表的步骤。"""

    max_steps = 10000   # 死循环保护上限（冒烟测试可用小上限子类覆盖）

    def __init__(self, store: StepListStore,
                 only_path: Optional[str] = None,
                 stop_mode: str = "after_step") -> None:
        self._store = store
        self._only_path = only_path   # None = 执行全部列表；否则仅执行该列表
        # 停止方式：after_step=当前步骤结束后停止；immediate=立即停止
        # （停止事件登记到 run_interrupt，步骤内 interruptible_sleep 以 ~20ms
        #   粒度轮询，请求后当前步骤尽快结束）
        self._stop_mode = "immediate" if stop_mode == "immediate" else "after_step"
        self._state = StepRunnerState.READY
        self._lock = threading.RLock()   # 可重入：request_stop 锁内调 _set_state
        self._stop_event = threading.Event()
        self._listeners: List[Callable[[StepRunnerState], None]] = []
        self._progress: Tuple[int, int] = (0, 0)   # (第几步 1-based, 总数)
        self._progress_listeners: List[Callable[[int, int], None]] = []

    # ---- 状态（线程安全 + 监听通知） ----
    @property
    def state(self) -> StepRunnerState:
        with self._lock:
            return self._state

    def _set_state(self, value: StepRunnerState) -> None:
        with self._lock:
            changed = value is not self._state
            self._state = value
        if changed:
            for cb in list(self._listeners):
                try:
                    cb(value)
                except Exception:
                    pass

    def add_state_listener(self, cb: Callable[[StepRunnerState], None]) -> None:
        """注册状态监听：``cb(new_state)``。"""
        self._listeners.append(cb)

    # ---- 进度（线程安全 + 监听通知；回调在工作线程发生，UI 需自行桥接） ----
    @property
    def progress(self) -> Tuple[int, int]:
        """当前执行进度 (第几步 1-based, 总步数)；未执行 = (0, 0)。"""
        with self._lock:
            return self._progress

    def add_progress_listener(self, cb: Callable[[int, int], None]) -> None:
        """注册进度监听：每步执行前 ``cb(第几步, 总数)``。"""
        self._progress_listeners.append(cb)

    def _notify_progress(self, index: int, total: int) -> None:
        with self._lock:
            self._progress = (index, total)
        for cb in list(self._progress_listeners):
            try:
                cb(index, total)
            except Exception:
                pass

    # ---- 控制 ----
    def start(self) -> None:
        """复位全部步骤并启动执行线程；仅 READY 可调用，否则 :class:`RuntimeError`。

        守卫 + 复位 + 收集 + 置 RUNNING 整体在锁内（消除 TOCTOU：并发
        request_stop / 重复 start 不可能在守卫与置 RUNNING 之间插入）；
        RLock 可重入，_set_state 内部取锁安全，通知回调仍在锁外执行。
        线程启动放在锁外（避免子线程在锁上等待）。
        """
        with self._lock:
            if self._state is not StepRunnerState.READY:
                raise RuntimeError("执行器非待命状态（当前 %s）" % self._state.value)
            # 复位：全部列表全部步骤（含 enabled=False 的）→ PENDING
            # （单列表模式只复位该列表——其余列表状态不受本次执行影响）
            if self._only_path is not None:
                try:
                    prog = [s.do for s in self._store.get(self._only_path).steps
                            if s.enabled]
                except FileNotFoundError:
                    LogModel.instance().error(
                        "单列表执行：列表不存在: %s" % self._only_path)
                    return
                reset_paths = [self._only_path]
            else:
                prog = self._store.all_do_methods()
                reset_paths = [p for p, g in self._store.walk() if not g]
            for path in reset_paths:
                for step in self._store.get(path).steps:
                    step.status = StepStatus.PENDING
            self._stop_event.clear()
            self._progress = (0, 0)
            if not prog:
                LogModel.instance().info("无可执行的步骤")
                return                          # 空程序：状态保持 READY
            if self._stop_mode == "immediate":
                set_stop_event(self._stop_event)   # 登记：步骤内可中断睡眠轮询此事件
            self._set_state(StepRunnerState.RUNNING)
        threading.Thread(target=self._run, args=(prog,), daemon=True).start()

    def request_stop(self) -> None:
        """协作式停止：当前步骤完成后退出；非运行态静默忽略。"""
        with self._lock:
            if self._state in (StepRunnerState.RUNNING, StepRunnerState.STOPPING):
                self._stop_event.set()
                self._set_state(StepRunnerState.STOPPING)

    # ---- 执行循环（工作线程） ----
    def _run(self, prog: List[Callable[[], int]]) -> None:
        try:
            pc = 0
            steps_done = 0
            while pc < len(prog) and not self._stop_event.is_set():
                steps_done += 1
                if steps_done > self.max_steps:
                    LogModel.instance().error(
                        "执行步数超过上限 %d，已停止（偏移量 0/负值疑似死循环）"
                        % self.max_steps)
                    break
                self._notify_progress(pc + 1, len(prog))   # 每步执行前报进度
                try:
                    offset = prog[pc]()     # do(): input -> run -> output
                except Exception:
                    break                   # 遇错停止（错误日志由 do() 记录）
                pc += offset
                if pc < 0:
                    pc = 0                  # 负偏移回跳，最前钳到 0
        finally:
            self._stop_event.clear()
            if self._stop_mode == "immediate":
                clear_stop_event(self._stop_event)   # 注销停止事件登记
            self._set_state(StepRunnerState.READY)


# ================================================================
# 冒烟演示：直接 ``python -m model.step_runner`` 运行
# ================================================================
if __name__ == "__main__":
    import time
    from dataclasses import dataclass

    from model.log_model import LogModel
    from model.step import Step, StepStatus
    from model.step_list import StepList
    from model.step_list_store import StepListStore

    def _wait_ready(runner: StepRunner, timeout: float = 5.0) -> None:
        """轮询等待执行器回到 READY（工作线程收尾）。"""
        t0 = time.monotonic()
        while runner.state is not StepRunnerState.READY:
            assert time.monotonic() - t0 < timeout, "执行器超时未回到 READY"
            time.sleep(0.01)

    @dataclass
    class _In:
        n: "number" = 0  # type: ignore

    @dataclass
    class _Out:
        pass

    class _ProbeStep(Step):
        """探针步骤：run 记录执行序号，返回预设偏移；不写变量（无输出槽）。"""
        name = "探针"
        description = "测试探针"
        input_class = _In
        output_class = _Out
        calls = []
        offsets = []

        def run(self) -> int:
            type(self).calls.append(self.tag)
            return type(self).offsets[len(type(self).calls) - 1]

    def make_store(offsets, tags):
        _ProbeStep.calls = []
        _ProbeStep.offsets = list(offsets)
        store = StepListStore.create_empty()
        sl = StepList.create_empty()
        for i, t in enumerate(tags):
            s = _ProbeStep.create_default(None, None)  # type: ignore  # 无 io 需求
            s.io._input_values = [str(i)]
            s.tag = t
            sl.add(s)
        store.add_list("L", sl)
        return store

    # ---- 顺序执行：偏移 1 逐条 ----
    store = make_store([1, 1, 1], ["a", "b", "c"])
    runner = StepRunner(store)
    states = []
    runner.add_state_listener(states.append)
    runner.start()
    assert runner.state in (StepRunnerState.RUNNING, StepRunnerState.READY)
    _wait_ready(runner)
    assert _ProbeStep.calls == ["a", "b", "c"], _ProbeStep.calls
    assert states[-1] is StepRunnerState.READY

    # ---- 偏移 2 跳一步；负偏移回跳 ----
    store = make_store([2, 1], ["a", "b"])      # a 跳 b → 只跑 a；b 后越界结束
    runner = StepRunner(store)
    runner.start()
    _wait_ready(runner)
    assert _ProbeStep.calls == ["a"], _ProbeStep.calls
    # 负偏移：b 回跳到 a（a 偏移 1 → b → 再回跳…）
    store = make_store([1, -1, 1, -1], ["a", "b"])
    class _TinyRunner(StepRunner):
        max_steps = 4
    runner = _TinyRunner(store)
    runner.start()
    _wait_ready(runner)
    assert _ProbeStep.calls == ["a", "b", "a", "b"], _ProbeStep.calls

    # ---- 偏移 0 死循环 → 步数上限停止 + 日志 ----
    LogModel.instance().clear()
    store = make_store([0, 0, 0, 0], ["a"])
    runner = _TinyRunner(store)
    runner.start()
    _wait_ready(runner)
    assert len(_ProbeStep.calls) == 4, _ProbeStep.calls
    assert any("超过上限" in e.message for e in LogModel.instance().entries)

    # ---- 协作式停止：当前步骤完成后退出，不开始下一步 ----
    class _SlowStep(Step):
        name = "慢步骤"
        description = "慢"
        input_class = _In
        output_class = _Out
        count = 0

        def run(self) -> int:
            type(self).count += 1
            time.sleep(0.15)
            return 1

    store = StepListStore.create_empty()
    sl = StepList.create_empty()
    slow1 = _SlowStep.create_default(None, None)  # type: ignore
    slow1.io._input_values = ["0"]                 # 合法输入 → 错误不会发生在 input()
    sl.add(slow1)
    slow2 = _SlowStep.create_default(None, None)  # type: ignore
    slow2.io._input_values = ["0"]
    sl.add(slow2)
    store.add_list("L", sl)
    _SlowStep.count = 0
    runner = StepRunner(store)
    runner.start()
    time.sleep(0.05)                 # 第一步执行中
    runner.request_stop()
    assert runner.state is StepRunnerState.STOPPING
    _wait_ready(runner)
    assert _SlowStep.count == 1, _SlowStep.count   # 第二步未执行（完成后才停）

    # ---- 遇错停止：do() 抛异常 → 停止整个执行 ----
    class _ErrStep(Step):
        name = "错误步骤"
        description = "错"
        input_class = _In
        output_class = _Out

        def run(self) -> int:
            raise ValueError("boom")

    store = StepListStore.create_empty()
    sl = StepList.create_empty()
    e = _ErrStep.create_default(None, None)          # type: ignore
    e.io._input_values = ["0"]                       # 合法输入 → 错误发生在 run()
    sl.add(e)
    sl.add(_ProbeStep.create_default(None, None))    # type: ignore
    store.add_list("L", sl)
    _ProbeStep.calls = []                            # 清空上次执行残留 → 只统计本次
    runner = StepRunner(store)
    runner.start()
    _wait_ready(runner)
    assert _ProbeStep.calls == [], _ProbeStep.calls   # 后续步骤未执行

    # ---- start 复位全部步骤 PENDING；RUNNING 中重复 start → RuntimeError ----
    _SlowStep.count = 0
    store = StepListStore.create_empty()
    sl = StepList.create_empty()
    slow = _SlowStep.create_default(None, None)      # type: ignore
    slow.io._input_values = ["0"]
    sl.add(slow)
    store.add_list("L", sl)
    runner = StepRunner(store)
    runner.start()
    try:
        runner.start()                               # RUNNING 中重复 start
        raise AssertionError("RUNNING 中重复 start 应抛 RuntimeError")
    except RuntimeError:
        pass
    _wait_ready(runner)
    assert slow.status is StepStatus.FINISHED
    # 再次 start：复位 PENDING 后从头执行（手动弄脏状态 → 重跑后回到 FINISHED）
    slow.status = StepStatus.ERROR
    _SlowStep.count = 0
    runner.start()
    _wait_ready(runner)
    assert _SlowStep.count == 1
    assert slow.status is StepStatus.FINISHED        # 复位 PENDING → 重跑完成

    # ---- 空程序：start 保持 READY，不创建线程 ----
    store = StepListStore.create_empty()
    runner = StepRunner(store)
    runner.start()
    assert runner.state is StepRunnerState.READY

    # ---- 停止方式：immediate=可中断睡眠提前结束；after_step=当前步骤完成 ----
    class _SlowInterruptStep(Step):
        name = "可中断慢步骤"
        description = ""
        input_class = _In
        output_class = _Out
        count = 0

        def run(self) -> int:
            type(self).count += 1
            from model.run_interrupt import interruptible_sleep
            if interruptible_sleep(1.0):
                type(self).count += 100     # 标记：等待被打断
            return 1

    def _mk_slow():
        store = StepListStore.create_empty()
        sl = StepList.create_empty()
        s = _SlowInterruptStep.create_default(None, None)  # type: ignore
        s.io._input_values = ["0"]
        sl.add(s)
        store.add_list("L", sl)
        return store

    # immediate：request_stop 后当前步骤的等待被中断 → 远小于 1s 结束
    _SlowInterruptStep.count = 0
    store = _mk_slow()
    runner = StepRunner(store, stop_mode="immediate")
    runner.start()
    time.sleep(0.05)
    t0 = time.monotonic()
    runner.request_stop()
    _wait_ready(runner)
    assert time.monotonic() - t0 < 0.6, "immediate 应打断 1s 等待"
    assert _SlowInterruptStep.count == 101

    # after_step（默认）：睡满 1s 才结束
    _SlowInterruptStep.count = 0
    store = _mk_slow()
    runner = StepRunner(store)
    runner.start()
    time.sleep(0.05)
    t0 = time.monotonic()
    runner.request_stop()
    _wait_ready(runner, timeout=3.0)
    assert time.monotonic() - t0 >= 0.9, "after_step 应等当前步骤完成"
    assert _SlowInterruptStep.count == 1

    # ---- 执行进度：每步执行前通知 (第几步, 总数) ----
    store = make_store([1, 1, 1], ["a", "b", "c"])
    runner = StepRunner(store)
    progs = []
    runner.add_progress_listener(lambda i, n: progs.append((i, n)))
    runner.start()
    _wait_ready(runner)
    assert progs == [(1, 3), (2, 3), (3, 3)], progs
    assert runner.progress == (3, 3)
    # 跳转（偏移 2）→ 只执行第 1 步
    store = make_store([2, 1], ["a", "b"])
    runner = StepRunner(store)
    progs = []
    runner.add_progress_listener(lambda i, n: progs.append((i, n)))
    runner.start()
    _wait_ready(runner)
    assert progs == [(1, 2)], progs

    # ---- 单列表执行（only_path）：只跑该列表、只复位该列表 ----
    store = StepListStore.create_empty()
    sl1 = StepList.create_empty()
    s1 = _ProbeStep.create_default(None, None)  # type: ignore
    s1.io._input_values = ["0"]                 # 合法输入（同 make_store）
    s1.tag = "L1"
    sl1.add(s1)
    store.add_list("列表1", sl1)
    sl2 = StepList.create_empty()
    s2 = _ProbeStep.create_default(None, None)  # type: ignore
    s2.io._input_values = ["0"]
    s2.tag = "L2"
    sl2.add(s2)
    store.add_list("列表2", sl2)
    _ProbeStep.calls = []
    _ProbeStep.offsets = [1, 1]
    runner = StepRunner(store, only_path="列表1")
    runner.start()
    _wait_ready(runner)
    assert _ProbeStep.calls == ["L1"], _ProbeStep.calls   # 仅列表1执行
    assert sl2.steps[0].status is StepStatus.PENDING      # 列表2未被复位触碰
    # 不存在的列表 → 不执行 + 错误日志（保持 READY）
    LogModel.instance().clear()
    runner = StepRunner(store, only_path="不存在")
    runner.start()
    assert runner.state is StepRunnerState.READY
    assert any("列表不存在" in e.message for e in LogModel.instance().entries)

    print("StepRunner smoke OK")
