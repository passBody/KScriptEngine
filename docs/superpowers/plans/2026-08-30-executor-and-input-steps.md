# 执行器与输入步骤 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增「按键」「鼠标点击」「输出日志」三个步骤模板（接入内嵌 key_control，鼠标点击带图片标注辅助），并实现热键驱动的执行器（待命 → 热键执行全部列表 → 再按停止）。

**Architecture:** 两个阶段——阶段 A 输入步骤（内嵌依赖 → StepIOWidget 通知 → 三个模板 → 鼠标自定义视图）；阶段 B 执行器（Settings → StepRunner → HotkeyListener → main_widget 接线）。执行器 = 纯 Python 状态机 + PC 偏移循环，pynput 只在 hotkey.py 引入；UI 经 Qt 信号桥跨线程刷新。

**Tech Stack:** Python 3.14、PyQt5、pynput>=1.7、线程（threading）与 Qt 信号桥；无测试框架（各模块 `__main__` 冒烟）。

**Spec:** `docs/superpowers/specs/2026-08-30-executor-and-input-steps-design.md`

## Global Constraints

- 绝对导入（`from model.xxx import ...`，不用相对导入跨包）。
- 冒烟测试位于各模块 `__main__` 块内，`python -m <module>` 运行，断言驱动；**绝不经过管道**（防吞退出码）。
- 冒烟**不得真实按键/真实全局监听**：模板提供模块级 `_new_control()` 桩工厂，冒烟替换之；HotkeyListener 冒烟不启动真实监听。
- model 层无 Qt：StepRunner/Settings/HotkeyListener 均纯 Python；pynput 只在 `model/hotkey.py` 引入。
- 中文 bytes 字面量禁用——一律 `.encode("utf-8")`。
- 每任务结束 git commit（message 以任务名开头）。
- 路径统一走 `model/path_util.py`（折叠空段与 `.`、拒绝 `..`）。
- 源项目路径：`C:\Users\feelnn\Desktop\项目\MouseAndKeyboardMacros\key_control\base.py`。

## 文件结构

```
libs/key_control/              # 内嵌副本（任务1）
  __init__.py                  # 导出 InputControl
  base.py                      # 从源项目复制
requirements.txt               # pynput>=1.7
model/
  step_io.py                   # 改：add_listener/remove_listener + input_value/output_value getter（任务2）
  settings.py                  # 新：热键配置读写（任务3）
  step_runner.py               # 新：执行器状态机（任务4）
  hotkey.py                    # 新：pynput 热键监听（任务5）
actions/
  __init__.py                  # 改：登记新模板（任务6/7/8）
  输入/
    __init__.py                # 新
    按键.py                    # 新（任务6）
    鼠标.py                    # 新（任务8 + 任务9 自定义视图）
  控制流程/
    输出日志.py                # 新（任务7）
widgets/
  main_widget.py               # 改：执行按钮/状态栏/桥/锁定（任务10）、热键编辑框（任务11）
docs/工程分析.md               # 改：标记完成（任务12）
```

---

### Task 1: 内嵌 key_control 依赖

**Files:**
- Create: `libs/key_control/__init__.py`
- Create: `libs/key_control/base.py`（复制自源项目，改动：文件头 docstring 注明来源）
- Create: `requirements.txt`

**Interfaces:**
- Produces: `from libs.key_control import InputControl` —— `InputControl().key_click(key, duration=None)`、`InputControl().mouse_click(x, y, duration=None)`；任务 6/8 依赖。

- [ ] **Step 1: 复制 base.py 并加来源注释**

复制 `C:\Users\feelnn\Desktop\项目\MouseAndKeyboardMacros\key_control\base.py` 到 `libs/key_control/base.py`，文件头 docstring 第一行后插入：

```python
# 内嵌自 ../MouseAndKeyboardMacros/key_control/base.py（2026-08-30 复制，未修改逻辑）
```

- [ ] **Step 2: 写 __init__.py**

```python
# -*- coding: utf-8 -*-
"""内嵌按键控制库：仅导出 InputControl（源项目 key_control 的最小内嵌）。"""
from .base import InputControl

__all__ = ["InputControl"]
```

- [ ] **Step 3: 写 requirements.txt**

```
pynput>=1.7
```

- [ ] **Step 4: 冒烟——import 与接口存在性**

在 `libs/key_control/base.py` 末尾追加 `__main__` 冒烟块（原文件无）：

```python
if __name__ == "__main__":
    from libs.key_control import InputControl
    from libs.key_control.base import NAMED_KEYS

    ctl = InputControl()
    assert hasattr(ctl, "key_click") and hasattr(ctl, "mouse_click")
    assert hasattr(ctl, "keyboard_control") and hasattr(ctl, "mouse_control")
    # NAMED_KEYS 覆盖 spec 需要的最小集合
    for k in ("space", "enter", "esc", "shift", "ctrl", "alt"):
        assert k in NAMED_KEYS
    print("key_control smoke OK")
```

- [ ] **Step 5: 运行验证**

Run: `python -m libs.key_control.base`
Expected: `key_control smoke OK`（构造 Controller 不按键，无副作用）

- [ ] **Step 6: Commit**

```bash
git add libs/key_control/ requirements.txt
git commit -m "feat: 内嵌 key_control 依赖（InputControl 最小内嵌 + pynput 依赖声明）"
```

---

### Task 2: StepIOWidget 槽值监听与读取接口

**Files:**
- Modify: `model/step_io.py`（类 StepIOWidget）
- Test: `model/step_io.py` 冒烟块

**Interfaces:**
- Consumes: 无
- Produces:
  - `StepIOWidget.add_listener(cb: Callable[[], None]) -> None`
  - `StepIOWidget.remove_listener(cb) -> None`
  - `StepIOWidget.input_value(i: int) -> str`（输入槽原始串；越界 IndexError）
  - `StepIOWidget.output_value(i: int) -> str`（输出槽原始串；越界 IndexError）
  - `StepIOWidget.tree -> "VariableTree"`（只读 property：关联的变量树；模板自定义视图解析 `{{变量}}` 用）
  - 任务 9 依赖。

- [ ] **Step 1: 写失败断言（RED）**

在 `model/step_io.py` 冒烟块的 `print("StepIOWidget smoke OK")` 之前插入：

```python
    # ---- 槽值变更监听 + 读取接口 ----
    # add_listener：change_value 与 GUI 编辑两路写入都通知；remove 后不通知
    events = []
    wl = StepIOWidget(["number"], ["number"], tree, pkg)
    wl.add_listener(lambda: events.append(1))
    wl.change_value("input", 0, "5")
    assert events == [1], events                 # change_value 路径
    cw = wl.gen_widget()
    cw.input_fields[0].setText("7")              # GUI 编辑路径（模拟用户输入）
    assert events == [1, 1], events
    cb2 = lambda: events.append(2)
    wl.add_listener(cb2)
    wl.change_value("input", 0, "3")
    assert events == [1, 1, 1, 2], events        # 多监听者依次通知
    wl.remove_listener(cb2)
    wl.change_value("input", 0, "4")
    assert events == [1, 1, 1, 2, 1], events
    # 监听者异常不中断写入
    def bad_cb():
        raise RuntimeError("boom")
    wl.add_listener(bad_cb)
    wl.change_value("input", 0, "6")             # 不抛
    assert wl.input_value(0) == "6"
    # 读取接口
    assert wl.input_value(0) == "6"
    assert wl.output_value(0) == ""
    for bad_i, fn in ((-1, lambda i: wl.input_value(i)),
                      (1, lambda i: wl.input_value(i))):
        try:
            fn(bad_i)
            raise AssertionError("越界应抛 IndexError")
        except IndexError:
            pass
```

- [ ] **Step 2: 运行确认失败（RED）**

Run: `python -m model.step_io`
Expected: `AttributeError: 'StepIOWidget' object has no attribute 'add_listener'`

- [ ] **Step 3: 实现**

`__init__` 中 `self._widgets: List[...] = []` 行后加：

```python
        self._listeners: List[Callable[[], None]] = []  # 槽值变更监听（任意写入路径均通知）
```

类中新加（放在「类型扩展接口」区块之后）：

```python
    # ================================================================
    # 槽值变更监听（自定义视图刷新预览等用；纯 Python 回调，无 Qt）
    # ================================================================
    def add_listener(self, cb: Callable[[], None]) -> None:
        """注册槽值变更监听：任何输入/输出槽值写入后调用 ``cb()``。"""
        self._listeners.append(cb)

    def remove_listener(self, cb: Callable[[], None]) -> None:
        """移除监听者；未注册静默忽略。"""
        try:
            self._listeners.remove(cb)
        except ValueError:
            pass

    def _notify_listeners(self) -> None:
        for cb in list(self._listeners):   # 拷贝遍历：回调可增删监听者
            try:
                cb()
            except Exception:
                pass                       # 监听者异常不打断数据写入

    def input_value(self, i: int) -> str:
        """读取输入槽原始串（常量或 ``{{变量名}}``）；越界抛 :class:`IndexError`。"""
        return self._input_values[i]

    def output_value(self, i: int) -> str:
        """读取输出槽原始串（变量名）；越界抛 :class:`IndexError`。"""
        return self._output_values[i]

    @property
    def tree(self) -> "VariableTree":
        """关联的变量树（自定义视图解析 ``{{变量}}`` 引用用）。"""
        return self._tree
```

`_set_input` 与 `_set_output` 方法末尾各加一行 `self._notify_listeners()`（两处）。

- [ ] **Step 4: 运行确认通过（GREEN）**

Run: `python -m model.step_io`
Expected: `StepIOWidget smoke OK`

- [ ] **Step 5: 全量相关冒烟**

Run: `python -m model.step && python -m widgets.step_card`
Expected: 均 OK（StepIOWidget 行为向后兼容）

- [ ] **Step 6: Commit**

```bash
git add model/step_io.py
git commit -m "feat: StepIOWidget 槽值变更监听与读取接口"
```

---

### Task 3: Settings 热键配置模型

**Files:**
- Create: `model/settings.py`
- Test: `model/settings.py` 冒烟块

**Interfaces:**
- Consumes: `model.path_util` 无；`model.log_model.LogModel`（损坏回退时告警）
- Produces:
  - `Settings.load(path: Optional[str] = None) -> Settings`
  - `settings.hotkey -> str`（默认 `"`"`）
  - `settings.set_hotkey(key: str) -> None`（单字符 str，含数字；否则 ValueError）
  - `settings.save(path: Optional[str] = None) -> None`
  - 默认路径：`<项目根>/setting.json`（`os.path.dirname(os.path.dirname(os.path.abspath(__file__)))`）
  - 任务 10/11 依赖。

- [ ] **Step 1: 写失败冒烟（RED）**

新文件 `model/settings.py`，先只写冒烟骨架（类未定义 → import 失败即 RED）。完整冒烟块：

```python
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
```

- [ ] **Step 2: 运行确认失败（RED）**

Run: `python -m model.settings`
Expected: `ModuleNotFoundError`（文件不存在）——RED 成立（功能缺失）

- [ ] **Step 3: 运行确认通过（GREEN）**

Run: `python -m model.settings`
Expected: `Settings smoke OK`

- [ ] **Step 4: Commit**

```bash
git add model/settings.py
git commit -m "feat: Settings 热键配置模型（setting.json 读写，不随 .kscp）"
```

---

### Task 4: StepRunner 执行器状态机

**Files:**
- Create: `model/step_runner.py`
- Test: `model/step_runner.py` 冒烟块

**Interfaces:**
- Consumes: `model.step.Step/StepStatus`、`model.step_list_store.StepListStore`（`walk()`/`get(path)`/`all_do_methods()`）、`model.log_model.LogModel`、`model.step_list.StepList`
- Produces:
  - `StepRunnerState`（Enum：READY/RUNNING/STOPPING，值 `"待命"/"执行中"/"停止中"`）
  - `StepRunner(store: StepListStore)`；`max_steps = 10000` 类属性（子类可覆盖）
  - `runner.start() -> None`（仅 READY；复位全部步骤 PENDING 后启动工作线程）
  - `runner.request_stop() -> None`（RUNNING/STOPPING 置停止事件；其余静默）
  - `runner.state -> StepRunnerState`（property，线程安全）
  - `runner.add_state_listener(cb: Callable[[StepRunnerState], None])`
  - 任务 10 依赖。

- [ ] **Step 1: 写完整模块与冒烟（RED：模块不存在）**

新文件 `model/step_runner.py`：

```python
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
from __future__ import annotations

import threading
from enum import Enum
from typing import Callable, List, Optional

from model.log_model import LogModel
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

    def __init__(self, store: StepListStore) -> None:
        self._store = store
        self._state = StepRunnerState.READY
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._listeners: List[Callable[[StepRunnerState], None]] = []

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

    # ---- 控制 ----
    def start(self) -> None:
        """复位全部步骤并启动执行线程；仅 READY 可调用，否则 :class:`RuntimeError`。"""
        with self._lock:
            if self._state is not StepRunnerState.READY:
                raise RuntimeError("执行器非待命状态（当前 %s）" % self._state.value)
        # 复位：全部列表全部步骤（含 enabled=False 的）→ PENDING
        for path, is_group in self._store.walk():
            if is_group:
                continue
            for step in self._store.get(path).steps:
                step.status = StepStatus.PENDING
        prog = self._store.all_do_methods()
        self._stop_event.clear()
        if not prog:
            LogModel.instance().info("无可执行的步骤")
            return                          # 空程序：状态保持 READY
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
                try:
                    offset = prog[pc]()     # do(): input -> run -> output
                except Exception:
                    break                   # 遇错停止（错误日志由 do() 记录）
                pc += offset
                if pc < 0:
                    pc = 0                  # 负偏移回跳，最前钳到 0
        finally:
            self._stop_event.clear()
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
        n: "number" = 0

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
    store = make_store([1, -1], ["a", "b"])
    class _TinyRunner(StepRunner):
        max_steps = 4
    runner = _TinyRunner(store)
    runner.start()
    _wait_ready(runner)
    assert _ProbeStep.calls == ["a", "b", "a", "b"], _ProbeStep.calls

    # ---- 偏移 0 死循环 → 步数上限停止 + 日志 ----
    LogModel.instance().clear()
    store = make_store([0], ["a"])
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
    sl.add(_SlowStep.create_default(None, None))  # type: ignore
    sl.add(_SlowStep.create_default(None, None))  # type: ignore
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
    runner = StepRunner(store)
    runner.start()
    _wait_ready(runner)
    assert _ProbeStep.calls == [], _ProbeStep.calls   # 后续步骤未执行

    # ---- start 复位全部步骤 PENDING；RUNNING 中重复 start → RuntimeError ----
    _SlowStep.count = 0
    store = StepListStore.create_empty()
    sl = StepList.create_empty()
    slow = _SlowStep.create_default(None, None)      # type: ignore
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

    print("StepRunner smoke OK")
```

- [ ] **Step 2: 运行确认失败（RED）**

Run: `python -m model.step_runner`
Expected: `ModuleNotFoundError: No module named 'model.step_runner'`

- [ ] **Step 3: 运行确认通过（GREEN）**

Run: `python -m model.step_runner`
Expected: `StepRunner smoke OK`

> 注意：冒烟中 `_wait_ready` 的 `time.sleep` 用于探针/慢步骤测试，与「冒烟不真实按键」约束无关，允许。

- [ ] **Step 4: Commit**

```bash
git add model/step_runner.py
git commit -m "feat: StepRunner 执行器（PC+偏移循环、协作式停止、死循环保护）"
```

---

### Task 5: HotkeyListener 热键监听

**Files:**
- Create: `model/hotkey.py`
- Test: `model/hotkey.py` 冒烟块

**Interfaces:**
- Consumes: 无（pynput 运行时 import）
- Produces: `HotkeyListener(hotkey: str, on_toggle: Callable[[], None])`；`.start() -> None`；`.stop() -> None`；大小写不敏感比较（`char.lower() == hotkey.lower()`）；任务 10 依赖。

- [ ] **Step 1: 写完整模块与冒烟（RED：模块不存在）**

新文件 `model/hotkey.py`：

```python
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
```

- [ ] **Step 2: 运行确认失败（RED）**

Run: `python -m model.hotkey`
Expected: `ModuleNotFoundError: No module named 'model.hotkey'`

- [ ] **Step 3: 运行确认通过（GREEN）**

Run: `python -m model.hotkey`
Expected: `HotkeyListener smoke OK`

- [ ] **Step 4: Commit**

```bash
git add model/hotkey.py
git commit -m "feat: HotkeyListener 单字符热键全局监听"
```

---

### Task 6: 「按键」步骤模板

**Files:**
- Create: `actions/输入/__init__.py`
- Create: `actions/输入/按键.py`
- Modify: `actions/__init__.py`（登记 KeyClick）

**Interfaces:**
- Consumes: `libs.key_control.InputControl`（任务1）、`model.step`（Step/StepStatus）、`model.log_model`
- Produces: `KeyClick`（`name="按键"`；输入 `键名:"string"=""`、`按住时长:"number"=0.05`）；模块级 `_new_control()` 桩工厂（冒烟替换）；任务10间接依赖。

- [ ] **Step 1: 写 actions/输入/__init__.py**

```python
from .按键 import KeyClick

__all__ = ["KeyClick"]
```

- [ ] **Step 2: 写模板与冒烟（RED：模块不存在）**

新文件 `actions/输入/按键.py`：

```python
# -*- coding: utf-8 -*-
"""
按键步骤（输入模拟）
====================

:class:`KeyClick`：模拟键盘按键（基于内嵌 :mod:`libs.key_control` 的
:class:`InputControl`）。键名语义沿用 InputControl：单字符 / 命名键
（space/enter/esc/shift/ctrl/alt 等）/ 多字符 = 同时按下的和弦。

输入槽
------
* ``键名``（string）：按键文本（如 ``'q'`` / ``'space'`` / ``'ae'`` 和弦）。
* ``按住时长``（number，秒）：按下后多久松开。

运行规则
--------
* 键名为空：状态「执行错误」+ 日志报错（不抛异常）。
* 否则：``key_click(键名, 时长 if 时长 > 0 else None)``，返回 1。

> 模拟输入到游戏窗口需以管理员身份运行 KScript。
"""
from dataclasses import dataclass

from libs.key_control import InputControl
from model.log_model import LogModel
from model.step import Step, StepStatus

__all__ = ["KeyClick"]


def _new_control() -> InputControl:
    """创建输入设备控制器（冒烟测试替换为桩，避免真实按键）。"""
    return InputControl()


@dataclass
class KeyClickInput:
    """输入：键名（string）、按住时长（number 秒）。"""
    键名: "string" = ""      # type: ignore
    按住时长: "number" = 0.05 # type: ignore


@dataclass
class KeyClickOutput:
    """无输出。"""
    pass


class KeyClick(Step):
    """按键步骤：模拟键盘按键。"""

    name = "按键"
    description = "模拟键盘按键（单字符/命名键/和弦）"
    input_class = KeyClickInput
    output_class = KeyClickOutput

    def run(self) -> int:
        if not self.inputs.键名:
            self.status = StepStatus.ERROR
            LogModel.instance().error("按键步骤：键名不能为空")
            return 1
        duration = self.inputs.按住时长 if self.inputs.按住时长 > 0 else None
        _new_control().key_click(self.inputs.键名, duration)
        return 1


# ================================================================
# 冒烟演示：直接 ``python -m actions.输入.按键`` 运行
# ================================================================
if __name__ == "__main__":
    import sys

    from PyQt5.QtWidgets import QApplication

    from model.kscp_package import KscpPackage
    from model.log_model import LogModel
    from model.variable_tree import VariableTree

    import actions.输入.按键 as _mod

    app = QApplication.instance() or QApplication(sys.argv)

    pkg = KscpPackage.create_empty()
    tree = VariableTree.create_empty()

    # create_default：槽类型推导
    k = KeyClick.create_default(tree, pkg)
    assert k.io._input_type == ["string", "number"]
    assert k.io._output_type == []
    assert k.name == "按键" and k.status is StepStatus.PENDING

    # run 用桩替换（冒烟不得真实按键）
    called = []

    class _StubCtl:
        def key_click(self, key, duration=None):
            called.append((key, duration))

    _mod._new_control = lambda: _StubCtl()

    # 正常：键名 + 时长
    k.io.change_value("input", 0, "q")
    k.io.change_value("input", 1, "0.1")
    assert k.do() == 1
    assert k.status is StepStatus.FINISHED
    assert called == [("q", 0.1)], called
    # 时长 <= 0 → 传 None（点击）
    called.clear()
    k.io.change_value("input", 1, "0")
    assert k.do() == 1
    assert called == [("q", None)], called
    # 键名为空 → ERROR + 日志（不抛异常）
    LogModel.instance().clear()
    k.io.change_value("input", 0, "")
    assert k.do() == 1
    assert k.status is StepStatus.ERROR
    assert any("键名不能为空" in e.message for e in LogModel.instance().entries)

    # 往返：还原后可继续执行
    fmt = k.to_format_string()
    assert "=" not in fmt and "+" not in fmt and "/" not in fmt
    k2 = KeyClick.from_format_string(fmt, tree, pkg)
    assert isinstance(k2, KeyClick)
    assert k2.io.to_format_string() == k.io.to_format_string()

    print("KeyClick smoke OK")
```

- [ ] **Step 3: 修改 actions/__init__.py 登记**

```python
from .base import Step, StepStatus
from .控制流程.time_delay import TimeDelay
from .输入.按键 import KeyClick

__all__ = ["Step", "StepStatus", "TimeDelay", "KeyClick"]
```

- [ ] **Step 4: 运行确认失败（RED）**

Run: `python -m actions.输入.按键`
Expected: `ModuleNotFoundError: No module named 'actions.输入.按键'`

- [ ] **Step 5: 运行确认通过（GREEN）**

Run: `python -m actions.输入.按键`
Expected: `KeyClick smoke OK`

- [ ] **Step 6: 全量相关冒烟**

Run: `python -m model.step && python -m model.step_manager`
Expected: 均 OK

- [ ] **Step 7: Commit**

```bash
git add actions/输入/ actions/__init__.py
git commit -m "feat: 按键步骤模板（key_click 模拟，键名/时长输入槽）"
```

---

### Task 7: 「输出日志」步骤模板

**Files:**
- Create: `actions/控制流程/输出日志.py`
- Modify: `actions/控制流程/__init__.py`、`actions/__init__.py`（登记 LogStep）

**Interfaces:**
- Consumes: `model.step`、`model.log_model.LogModel`
- Produces: `LogStep`（`name="输出日志"`；输入 `消息:"string"=""`）

- [ ] **Step 1: 写模板与冒烟（RED：模块不存在）**

新文件 `actions/控制流程/输出日志.py`：

```python
# -*- coding: utf-8 -*-
"""
输出日志步骤（控制流程）
========================

:class:`LogStep`：向日志面板输出一条 info 日志。输入 ``消息``（string，
可填 ``{{变量}}`` 引用）。

运行规则
--------
* ``LogModel.instance().info(消息)``，返回 1。
"""
from dataclasses import dataclass

from model.log_model import LogModel
from model.step import Step

__all__ = ["LogStep"]


@dataclass
class LogStepInput:
    """输入：消息（string）。"""
    消息: "string" = ""  # type: ignore


@dataclass
class LogStepOutput:
    """无输出。"""
    pass


class LogStep(Step):
    """输出日志步骤：向日志面板输出一条信息。"""

    name = "输出日志"
    description = "向日志面板输出一条信息"
    input_class = LogStepInput
    output_class = LogStepOutput

    def run(self) -> int:
        LogModel.instance().info(self.inputs.消息)
        return 1


# ================================================================
# 冒烟演示：直接 ``python -m actions.控制流程.输出日志`` 运行
# ================================================================
if __name__ == "__main__":
    import sys

    from PyQt5.QtWidgets import QApplication

    from model.kscp_package import KscpPackage
    from model.log_model import LogModel
    from model.variable_tree import VariableTree

    app = QApplication.instance() or QApplication(sys.argv)

    pkg = KscpPackage.create_empty()
    tree = VariableTree.create_empty()

    # create_default：槽类型推导
    s = LogStep.create_default(tree, pkg)
    assert s.io._input_type == ["string"]
    assert s.io._output_type == []
    assert s.name == "输出日志"

    # run：写入 info 日志
    LogModel.instance().clear()
    s.io.change_value("input", 0, "你好，KScript")
    assert s.do() == 1
    assert s.status.value == "执行结束"
    entries = LogModel.instance().entries
    assert len(entries) == 1 and entries[0].message == "你好，KScript"

    # 往返
    fmt = s.to_format_string()
    assert "=" not in fmt and "+" not in fmt and "/" not in fmt
    s2 = LogStep.from_format_string(fmt, tree, pkg)
    assert isinstance(s2, LogStep)
    assert s2.io.to_format_string() == s.io.to_format_string()

    print("LogStep smoke OK")
```

- [ ] **Step 2: 登记两处 __init__**

`actions/控制流程/__init__.py`：

```python
from .time_delay import TimeDelay
from .输出日志 import LogStep

__all__ = ["TimeDelay", "LogStep"]
```

`actions/__init__.py`：

```python
from .base import Step, StepStatus
from .控制流程.time_delay import TimeDelay
from .控制流程.输出日志 import LogStep
from .输入.按键 import KeyClick

__all__ = ["Step", "StepStatus", "TimeDelay", "LogStep", "KeyClick"]
```

- [ ] **Step 3: 运行确认失败（RED）**

Run: `python -m actions.控制流程.输出日志`
Expected: `ModuleNotFoundError`

- [ ] **Step 4: 运行确认通过（GREEN）**

Run: `python -m actions.控制流程.输出日志 && python -m actions.控制流程.time_delay`
Expected: `LogStep smoke OK`、`TimeDelay smoke OK`

- [ ] **Step 5: Commit**

```bash
git add actions/控制流程/输出日志.py actions/控制流程/__init__.py actions/__init__.py
git commit -m "feat: 输出日志步骤模板（LogModel.info）"
```

---

### Task 8: 「鼠标点击」步骤模板（核心）

**Files:**
- Create: `actions/输入/鼠标.py`
- Modify: `actions/输入/__init__.py`、`actions/__init__.py`（登记 MouseClick）

**Interfaces:**
- Consumes: `libs.key_control.InputControl`、`model.step`、`model.log_model`
- Produces: `MouseClick`（`name="鼠标点击"`；输入 `x:"number"=0`、`y:"number"=0`、`按住时长:"number"=0.05`、`素材图片:"image"=""`）；模块级 `_new_control()` 桩工厂；任务 9 添加 info_widget。

- [ ] **Step 1: 写模板与冒烟（RED：模块不存在）**

新文件 `actions/输入/鼠标.py`（本任务仅核心；info_widget 在任务 9）：

```python
# -*- coding: utf-8 -*-
"""
鼠标点击步骤（输入模拟）
========================

:class:`MouseClick`：在坐标 (x, y) 模拟鼠标左键点击（基于内嵌
:mod:`libs.key_control` 的 :class:`InputControl`）。

输入槽
------
* ``x`` / ``y``（number）：点击坐标（可引用变量，接 image_marker 标注坐标流）。
* ``按住时长``（number，秒）：按下后多久松开。
* ``素材图片``（image）：**编辑期辅助**，仅用于自定义视图的点位标注与预览；
  ``run()`` 不读取它。

> 模拟输入到游戏窗口需以管理员身份运行 KScript。
"""
from dataclasses import dataclass

from libs.key_control import InputControl
from model.step import Step

__all__ = ["MouseClick"]


def _new_control() -> InputControl:
    """创建输入设备控制器（冒烟测试替换为桩，避免真实鼠标移动）。"""
    return InputControl()


@dataclass
class MouseClickInput:
    """输入：坐标 x/y、按住时长（number）、素材图片（image，仅编辑辅助）。"""
    x: "number" = 0        # type: ignore
    y: "number" = 0        # type: ignore
    按住时长: "number" = 0.05 # type: ignore
    素材图片: "image" = ""  # type: ignore


@dataclass
class MouseClickOutput:
    """无输出。"""
    pass


class MouseClick(Step):
    """鼠标点击步骤：在坐标处模拟鼠标左键点击。"""

    name = "鼠标点击"
    description = "在坐标处模拟鼠标左键点击"
    input_class = MouseClickInput
    output_class = MouseClickOutput

    def run(self) -> int:
        duration = self.inputs.按住时长 if self.inputs.按住时长 > 0 else None
        _new_control().mouse_click(self.inputs.x, self.inputs.y, duration)
        return 1


# ================================================================
# 冒烟演示：直接 ``python -m actions.输入.鼠标`` 运行
# ================================================================
if __name__ == "__main__":
    import sys

    from PyQt5.QtWidgets import QApplication

    from model.kscp_package import KscpPackage
    from model.variable_tree import VariableTree

    import actions.输入.鼠标 as _mod

    app = QApplication.instance() or QApplication(sys.argv)

    pkg = KscpPackage.create_empty()
    tree = VariableTree.create_empty()

    # create_default：槽类型推导（含素材图片）
    m = MouseClick.create_default(tree, pkg)
    assert m.io._input_type == ["number", "number", "number", "image"]
    assert m.io._output_type == []
    assert m.name == "鼠标点击" and m.status is not None

    # run 用桩替换（冒烟不得真实鼠标操作）
    called = []

    class _StubCtl:
        def mouse_click(self, x, y, duration=None):
            called.append((x, y, duration))

    _mod._new_control = lambda: _StubCtl()

    # 正常：坐标 + 时长
    m.io.change_value("input", 0, "100")
    m.io.change_value("input", 1, "200")
    m.io.change_value("input", 2, "0.1")
    assert m.do() == 1
    assert called == [(100.0, 200.0, 0.1)], called
    # 时长 <= 0 → None
    called.clear()
    m.io.change_value("input", 2, "0")
    assert m.do() == 1
    assert called == [(100.0, 200.0, None)], called

    # 往返
    fmt = m.to_format_string()
    assert "=" not in fmt and "+" not in fmt and "/" not in fmt
    m2 = MouseClick.from_format_string(fmt, tree, pkg)
    assert isinstance(m2, MouseClick)
    assert m2.io.to_format_string() == m.io.to_format_string()

    print("MouseClick smoke OK")
```

- [ ] **Step 2: 登记两处 __init__**

`actions/输入/__init__.py`：

```python
from .按键 import KeyClick
from .鼠标 import MouseClick

__all__ = ["KeyClick", "MouseClick"]
```

`actions/__init__.py` 的 `__all__` 追加 `"MouseClick"`，import 加 `from .输入.鼠标 import MouseClick`。

- [ ] **Step 3: 运行确认失败（RED）**

Run: `python -m actions.输入.鼠标`
Expected: `ModuleNotFoundError`

- [ ] **Step 4: 运行确认通过（GREEN）**

Run: `python -m actions.输入.鼠标 && python -m actions.输入.按键`
Expected: 均 OK

- [ ] **Step 5: Commit**

```bash
git add actions/输入/鼠标.py actions/输入/__init__.py actions/__init__.py
git commit -m "feat: 鼠标点击步骤模板（mouse_click 模拟 + 素材图片槽）"
```

---

### Task 9: 鼠标点击自定义视图（预览 + 设置点位）

**Files:**
- Modify: `actions/输入/鼠标.py`（新增 `info_widget` 与 `_MouseInfoView`）
- Test: `actions/输入/鼠标.py` 冒烟块扩展

**Interfaces:**
- Consumes: `StepIOWidget.input_value/add_listener`（任务2）、`tools.image_marker.mark_image`（返回 `(image, PointTimeline|None)`，`pos.points[0] == (x, y)`）、`widgets.image_overlay.ImageOverlay(pixmap, parent)` + `show_overlay()`、`model.point_timeline`（仅类型）
- Produces: `MouseClick.info_widget(parent) -> QWidget`（提示标签 + 预览 QLabel + 「设置点位」按钮）

- [ ] **Step 1: 写失败断言（RED）**

在 `actions/输入/鼠标.py` 冒烟块 `print("MouseClick smoke OK")` 前插入（冒烟块顶部 import 区补一行 `import base64 as _b64`）：

```python
    # ---- info_widget：提示标签 + 预览 + 设置点位 ----
    pkg.write_file("assets/底图.png", _b64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGNgYGBgAAAABQAB"
        "h6FO1AAAAABJRU5ErkJggg=="))     # 1x1 PNG
    from model.project_variable import ProjectVariable
    tree.add("图", ProjectVariable.create("image", "assets/底图.png", pkg))
    m3 = MouseClick.create_default(tree, pkg)
    m3.io.change_value("input", 3, "{{图}}")
    view = m3.info_widget()
    assert view is not None
    # 三个要素：提示标签文字、预览、设置点位按钮
    from PyQt5.QtWidgets import QLabel, QPushButton
    labels = view.findChildren(QLabel)
    btns = view.findChildren(QPushButton)
    assert any("预览图的画面是通过读输入GUI的参数来生成" in l.text() for l in labels)
    assert any(b.text() == "设置点位" for b in btns)
    btn = [b for b in btns if b.text() == "设置点位"][0]
    # 素材槽变化 → 预览刷新（占位 → 真图）
    assert not view._preview_pixmap().isNull()   # 已有 {{图}} → 非占位
    m3.io.change_value("input", 3, "")
    assert view._preview_pixmap().isNull()       # 空槽 → 占位（null 图）
    m3.io.change_value("input", 3, "{{图}}")
    assert not view._preview_pixmap().isNull()

    # 设置点位：桩替换 mark_image，坐标回写 x/y 槽
    import tools.image_marker as _im
    _orig_mark = _im.mark_image

    class _FakePos:
        points = [(123, 456)]
    _im.mark_image = lambda data, mode: (data, _FakePos())
    try:
        btn.click()
    finally:
        _im.mark_image = _orig_mark
    assert m3.io.input_value(0) == "123" and m3.io.input_value(1) == "456"

    # 素材槽非法（空）→ 点按钮 → 数据不动（无弹窗：冒烟用桩替换 QMessageBox）
    from PyQt5.QtWidgets import QMessageBox
    _warn = QMessageBox.warning
    warned = []
    QMessageBox.warning = staticmethod(lambda *a, **k: warned.append(1) or QMessageBox.Ok)
    try:
        m3.io.change_value("input", 3, "")
        m3.io.change_value("input", 0, "1")
        m3.io.change_value("input", 1, "2")
        _im.mark_image = lambda data, mode: (data, _FakePos())
        btn.click()
    finally:
        _im.mark_image = _orig_mark
        QMessageBox.warning = _warn
    assert warned == [1]
    assert m3.io.input_value(0) == "1" and m3.io.input_value(1) == "2"   # 未改写
```

- [ ] **Step 2: 运行确认失败（RED）**

Run: `python -m actions.输入.鼠标`
Expected: `TypeError`（`info_widget` 返回默认 QLabel，无 `_preview_pixmap`）

- [ ] **Step 3: 实现**

`actions/输入/鼠标.py` 顶部 import 追加：

```python
import re
from typing import Any, Optional

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QImage, QPixmap
from PyQt5.QtWidgets import QLabel, QMessageBox, QPushButton, QVBoxLayout, QWidget
```

`MouseClick` 类内加（run 方法之后）：

```python
    # 素材图片输入槽下标（自定义视图/点位标注用）
    IMAGE_SLOT = 3

    def info_widget(self, parent: Optional[QWidget] = None) -> QWidget:
        """自定义视图：提示 + 标注预览 + 设置点位按钮（见 _MouseInfoView）。"""
        return _MouseInfoView(self, parent)
```

文件末尾（冒烟块之前）加 `_to_pixmap` / `_ClickPreview` / `_MouseInfoView`：

```python
_VAR_REF = re.compile(r"^\{\{(.+)\}\}$")
_PREVIEW_H = 120


def _to_pixmap(image: Any) -> Optional[QPixmap]:
    """mark_image 返回的多种类型 → QPixmap；不可解析 → None。"""
    if isinstance(image, QPixmap):
        return image
    if isinstance(image, QImage):
        return QPixmap.fromImage(image)
    if isinstance(image, (bytes, bytearray)):
        pix = QPixmap()
        return pix if pix.loadFromData(bytes(image)) else None
    # numpy.ndarray(HxWx3, uint8)：bytes 输入时 mark_image 优先返回该类型
    if hasattr(image, "tobytes") and getattr(image, "ndim", 0) == 3:
        h, w = image.shape[0], image.shape[1]
        qimg = QImage(image.tobytes(), w, h, w * image.shape[2],
                      QImage.Format_RGB888)
        return QPixmap.fromImage(qimg.copy())
    return None


class _ClickPreview(QLabel):
    """可点击预览图：左键点击发出 :data:`clicked`。"""

    clicked = pyqtSignal()

    def mousePressEvent(self, event) -> None:  # noqa: N802 (Qt 命名)
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class _MouseInfoView(QWidget):
    """鼠标点击步骤的自定义卡片视图。

    布局：
    * 提示标签：「自定义视图中的预览图的画面是通过读输入GUI的参数来生成」
    * 预览图（点击 → ImageOverlay 大图）；数据源 = 素材图片输入槽
    * 「设置点位」按钮 → mark_image('dot') → 坐标回写 x/y 输入槽
    """

    def __init__(self, step: "MouseClick", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._step = step
        self._marked: Optional[QPixmap] = None   # 标注结果（内存，槽未变时保持）

        hint = QLabel("自定义视图中的预览图的画面是通过读输入GUI的参数来生成")
        hint.setStyleSheet("color:#888;")
        hint.setWordWrap(True)

        self._preview = _ClickPreview()
        self._preview.setAlignment(Qt.AlignCenter)
        self._preview.setMinimumHeight(_PREVIEW_H)
        self._preview.setStyleSheet("background:#1e1e1e; border:1px solid #444;")
        self._preview.clicked.connect(self._open_overlay)

        self._btn_mark = QPushButton("设置点位")
        self._btn_mark.clicked.connect(self._on_mark)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        lay.addWidget(hint)
        lay.addWidget(self._preview)
        lay.addWidget(self._btn_mark)

        step.io.add_listener(self._on_io_changed)   # 素材槽变化 → 刷新预览
        self._on_io_changed()

    # ---- 预览 ----
    def _slot_value(self) -> str:
        return self._step.io.input_value(MouseClick.IMAGE_SLOT)

    def _image_bytes(self) -> Optional[bytes]:
        """素材图片槽 → 实际图片字节；槽为空/非引用/变量缺失 → None。"""
        raw = self._slot_value()
        m = _VAR_REF.match(raw) if isinstance(raw, str) else None
        if not m:
            return None
        try:
            return self._step.io.tree.get(m.group(1)).get_actual_data()
        except (FileNotFoundError, ValueError):
            return None

    def _preview_pixmap(self) -> QPixmap:
        """当前预览画面：标注图（素材槽未变时）优先，否则素材原图；无素材 → null。"""
        if self._marked is not None:
            return QPixmap(self._marked)
        data = self._image_bytes()
        if not data:
            return QPixmap()                      # null → 占位
        pix = QPixmap()
        pix.loadFromData(bytes(data))
        return pix

    def _refresh_preview(self) -> None:
        pix = self._preview_pixmap()
        if pix.isNull():
            self._preview.setText("无素材")
        else:
            self._preview.setText("")
            self._preview.setPixmap(pix.scaledToHeight(
                _PREVIEW_H - 8, Qt.SmoothTransformation))

    def _open_overlay(self) -> None:
        pix = self._preview_pixmap()
        if pix.isNull():
            return
        from widgets.image_overlay import ImageOverlay
        host = self.window() or self
        ov = ImageOverlay(pix, host)
        ov.show_overlay()
        self._overlay = ov                      # 持有引用防回收（关闭后由用户行为自然释放）

    # ---- 槽变化 ----
    def _on_io_changed(self) -> None:
        # 素材槽变化 → 标注结果失效，回到原图预览
        self._marked = None
        self._refresh_preview()

    # ---- 设置点位 ----
    def _on_mark(self) -> None:
        data = self._image_bytes()
        if not data:
            QMessageBox.warning(self, "设置点位", "请先在输入 GUI 中为「素材图片」选择图片变量")
            return
        from tools.image_marker import mark_image
        try:
            marked_img, pos = mark_image(data, "dot")
        except (ValueError, TypeError) as e:
            QMessageBox.warning(self, "设置点位", "标注失败：%s" % e)
            return
        if pos is None or not pos.points:
            return                                   # 取消 / 尺寸超屏 → 数据不动
        x, y = pos.points[0]
        # change_value 触发 io 监听 → _on_io_changed 先把 _marked 置空刷新原图，
        # 随后用标注图覆盖（带红点回显）
        self._step.io.change_value("input", 0, str(int(x)))
        self._step.io.change_value("input", 1, str(int(y)))
        pix = _to_pixmap(marked_img)
        if pix is not None and not pix.isNull():
            self._marked = pix
        self._refresh_preview()
```

- [ ] **Step 4: 运行确认通过（GREEN）**

Run: `python -m actions.输入.鼠标`
Expected: `MouseClick smoke OK`

- [ ] **Step 5: 全量相关冒烟**

Run: `python -m model.step && python -m model.step_io && python -m widgets.step_card && python -m widgets.image_overlay && python -m tools.image_marker`
Expected: 均 OK

- [ ] **Step 6: Commit**

```bash
git add actions/输入/鼠标.py
git commit -m "feat: 鼠标点击自定义视图（标注预览 + 设置点位回写坐标）"
```

---

### Task 10: 执行器 UI 接线（执行按钮 / 状态栏 / 桥 / 编辑锁定）

**Files:**
- Modify: `widgets/main_widget.py`（MainWindow 类 + 新 `_ExecBridge` QObject）
- Test: `widgets/main_widget.py` 冒烟块扩展

**Interfaces:**
- Consumes: `model.step_runner.StepRunner/StepRunnerState`（任务4）、`model.hotkey.HotkeyListener`（任务5）、`model.settings.Settings`（任务3）、`model.step.StepStatus`
- Produces: MainWindow 成员——`self._runner: Optional[StepRunner]`、`self._hotkey_listener: Optional[HotkeyListener]`、`self._exec_btn: Optional[QToolButton]`、`self._exec_status: Optional[QLabel]`、`self._exec_locked: bool`；方法 `_start_listening()/_stop_listening()/_handle_hotkey_toggle()/_set_exec_locked(locked)`；任务 11 依赖。

- [ ] **Step 1: 写失败断言（RED）**

在 main_widget 冒烟块 `print("MainWindow smoke OK")` 前插入（需要 import：`from model.step_runner import StepRunner, StepRunnerState`）：

```python
    # ---- 执行器接线：按钮/状态栏/锁定/热键 toggle 逻辑 ----
    # 冒烟不得真实全局监听：桩替换监听工厂（__main__ 模块命名空间内直接改全局）
    class _StubListener:
        def __init__(self, hotkey, on_toggle):
            self.hotkey, self.on_toggle = hotkey, on_toggle
            self.started = False

        def start(self):
            self.started = True

        def stop(self):
            self.started = False

    _orig_mk_listener = _make_hotkey_listener
    _make_hotkey_listener = lambda h, cb: _StubListener(h, cb)
    try:
        win_exec = MainWindow()
        win_exec._open_package(KscpPackage.create_empty(), None)
        app.processEvents()
        assert win_exec._runner is None
        # 未开包无执行入口——开包后按钮可用
        assert win_exec._exec_btn is not None and win_exec._exec_btn.isEnabled()
        # 点击执行按钮 → 进入待命（listener 启动）；再点 → 停止监听
        win_exec._exec_btn.click()
        assert win_exec._hotkey_listener is not None
        assert isinstance(win_exec._hotkey_listener, _StubListener)
        assert win_exec._hotkey_listener.started
        assert "待命" in win_exec._exec_status.text()
        win_exec._exec_btn.click()
        assert win_exec._hotkey_listener is None
        # 热键 toggle：READY → start；RUNNING → request_stop（空 store 无步骤 → 恒 READY）
        win_exec._exec_btn.click()          # 待命
        win_exec._handle_hotkey_toggle()    # 模拟热键按下（无步骤 → start 后仍 READY）
        assert win_exec._runner is not None
        assert win_exec._runner.state is StepRunnerState.READY
        # 编辑锁定：锁定时树面板禁用，解锁恢复
        win_exec._set_exec_locked(True)
        assert not win_exec._tree_stack.isEnabled()
        win_exec._set_exec_locked(False)
        assert win_exec._tree_stack.isEnabled()
        # 未开包点执行按钮 → 不启动（安全）
        win_bare = MainWindow()
        win_bare._exec_btn.click()
        assert win_bare._hotkey_listener is None
    finally:
        _make_hotkey_listener = _orig_mk_listener
```

- [ ] **Step 2: 运行确认失败（RED）**

Run: `python -m widgets.main_widget`
Expected: `AttributeError: '_MainWindow' object has no attribute '_exec_btn'`（或 None 断言失败）

- [ ] **Step 3: 实现**

3a. 文件顶部 import 区加：

```python
from model.hotkey import HotkeyListener
from model.settings import Settings
from model.step_runner import StepRunner, StepRunnerState
```

3b. 模块级（_TitledPanel 等类附近）加桥对象：

```python
class _ExecBridge(QObject):
    """执行器跨线程桥：工作线程 emit → Qt queued 到 GUI 线程刷新。"""
    runner_state = pyqtSignal(object)     # StepRunnerState
    hotkey_toggle = pyqtSignal()


# 模拟注入点：冒烟测试替换以避开真实热键/线程（与 picker 包装同思路）
def _make_step_runner(store):
    return StepRunner(store)


def _make_hotkey_listener(hotkey, on_toggle):
    return HotkeyListener(hotkey, on_toggle)
```

> 文件头 import 行改为（补 `QObject`；`pyqtSignal`/`QLineEdit`/`QToolButton` 均已存在）：

```python
from PyQt5.QtCore import QObject, Qt, QSize, QTimer, pyqtSignal
```

3c. `MainWindow.__init__` 中（`self._manage_btn` 行附近）加成员初始化：

```python
        self._runner: Optional[StepRunner] = None
        self._hotkey_listener: Optional[HotkeyListener] = None
        self._exec_btn: Optional[QToolButton] = None
        self._exec_status: Optional[QLabel] = None
        self._exec_bridge = _ExecBridge()
        self._exec_bridge.runner_state.connect(self._on_runner_state)
        self._exec_bridge.hotkey_toggle.connect(self._handle_hotkey_toggle)
        self._exec_locked = False
```

3d. `_build_toolbar` 末尾（窗口菜单之后）加：

```python
        tb.addSeparator()
        self._exec_btn = QToolButton(self)
        self._exec_btn.setText("执行")
        self._exec_btn.setToolTip(
            "点击进入待命：按下热键开始执行全部列表，再按停止（当前步骤完成后停）。\n"
            "热键勿与步骤按键冲突（模拟按键也会被监听）；模拟输入到游戏窗口需管理员运行。")
        self._exec_btn.clicked.connect(self._on_exec_clicked)
        self._exec_btn.setEnabled(False)          # 未开包不可用
        tb.addWidget(self._exec_btn)
```

3e. `_setup_statusbar` 末尾加：

```python
        self._exec_status = QLabel("")
        sb.addPermanentWidget(self._exec_status)
```

3f0. `StepListManagementTree` 类加 store 只读属性（放在 `icon()` 之前）：

```python
    @property
    def store(self) -> StepListStore:
        """步骤列表存储（执行器数据源）。"""
        return self._store
```

3f. `MainWindow` 内加执行器方法（放在 `_update_status_counts` 之后）：

```python
    # ---- 执行器接线 ----
    def _on_exec_clicked(self) -> None:
        """执行按钮：未监听 → 待命（启动热键监听）；已监听 → 停监听。"""
        if self._hotkey_listener is None:
            self._start_listening()
        else:
            self._stop_listening()

    def _start_listening(self) -> None:
        if self._package is None:
            return
        sl_mgr = self._managers[0] if self._managers else None
        assert isinstance(sl_mgr, StepListManagementTree)
        self._runner = _make_step_runner(sl_mgr.store)
        self._runner.add_state_listener(self._exec_bridge.runner_state.emit)
        settings = Settings.load()
        self._hotkey_listener = _make_hotkey_listener(
            settings.hotkey, self._exec_bridge.hotkey_toggle.emit)
        self._hotkey_listener.start()
        assert self._exec_btn is not None
        self._exec_btn.setText("停止监听")
        self._set_exec_status("待命：按 %s 执行/停止" % settings.hotkey)
        LogModel.instance().info("执行器待命：热键 %s（再按停止）" % settings.hotkey)

    def _stop_listening(self) -> None:
        if self._hotkey_listener is not None:
            self._hotkey_listener.stop()
            self._hotkey_listener = None
        if self._runner is not None:
            self._runner.request_stop()          # 执行中 → 当前步骤完成后停
            self._runner = None
        assert self._exec_btn is not None
        self._exec_btn.setText("执行")
        self._set_exec_status("已停止监听")
        LogModel.instance().info("执行器已停止监听")

    def _handle_hotkey_toggle(self) -> None:
        """热键按下（GUI 线程，经桥 queued）：READY → start；否则 → request_stop。"""
        if self._runner is None:
            return
        if self._runner.state is StepRunnerState.READY:
            self._runner.start()
        else:
            self._runner.request_stop()

    def _on_runner_state(self, st) -> None:
        """执行器状态变化（GUI 线程）：状态栏 + 编辑锁定。"""
        if st is StepRunnerState.RUNNING:
            self._set_exec_status("执行中……（按热键停止）")
            self._set_exec_locked(True)
        elif st is StepRunnerState.STOPPING:
            self._set_exec_status("停止中……（当前步骤完成后停）")
        else:
            self._set_exec_status(
                "待命：按 %s 执行/停止" % Settings.load().hotkey)
            self._set_exec_locked(False)

    def _set_exec_status(self, text: str) -> None:
        if self._exec_status is not None:
            self._exec_status.setText(text)

    def _set_exec_locked(self, locked: bool) -> None:
        """执行期间锁定编辑：左侧树面板禁用；预览栈与日志不锁（只读展示）。"""
        if self._exec_locked == locked:
            return
        self._exec_locked = locked
        if self._tree_stack is not None:
            self._tree_stack.setEnabled(not locked)
```

3g. `_open_package` 末尾（`self._switcher.set_current_row(0)` 之后）加：

```python
        if self._exec_btn is not None:
            self._exec_btn.setEnabled(True)
```

- [ ] **Step 4: 运行确认通过（GREEN）**

Run: `python -m widgets.main_widget`
Expected: `MainWindow smoke OK`

- [ ] **Step 5: 全量相关冒烟**

Run: `python -m model.step_runner && python -m model.hotkey && python -m model.settings`
Expected: 均 OK

- [ ] **Step 6: Commit**

```bash
git add widgets/main_widget.py
git commit -m "feat: 执行器 UI 接线（执行按钮/状态栏/跨线程桥/编辑锁定）"
```

---

### Task 11: 热键设置输入框

**Files:**
- Modify: `widgets/main_widget.py`（工具栏加热键编辑框 + `_HotkeyEdit` 小控件）
- Test: `widgets/main_widget.py` 冒烟块扩展

**Interfaces:**
- Consumes: `model.settings.Settings`（任务3）
- Produces: `_HotkeyEdit(QLineEdit)`——聚焦后按任意键绑定并保存到 setting.json；MainWindow 工具栏显示当前热键。

- [ ] **Step 1: 写失败断言（RED）**

在 main_widget 冒烟块插入（在任务 10 冒烟块之后）：

```python
    # ---- 热键设置输入框 ----
    assert win_exec._hotkey_edit is not None
    # 冒烟不得改写真实 setting.json：替换编辑框的 Settings 为内存桩（save 空操作）
    _fake_settings = Settings()
    _fake_settings.save = lambda path=None: None
    win_exec._hotkey_edit._settings = _fake_settings
    win_exec._hotkey_edit.setText(win_exec._hotkey_edit._settings.hotkey)
    assert win_exec._hotkey_edit.text() == "`"
    # 直接调用绑定逻辑（不真实按键）：合法单字符保存、非法拒绝
    assert win_exec._hotkey_edit._apply_key("f")
    assert _fake_settings.hotkey == "f"
    assert win_exec._hotkey_edit.text() == "f"
    assert not win_exec._hotkey_edit._apply_key("ab")
    assert _fake_settings.hotkey == "f"       # 非法不落盘
    assert win_exec._hotkey_edit.text() == "f"
```

- [ ] **Step 2: 运行确认失败（RED）**

Run: `python -m widgets.main_widget`
Expected: `AttributeError: '_MainWindow' object has no attribute '_hotkey_edit'`

- [ ] **Step 3: 实现**

3a. 模块级（_ExecBridge 附近）加：

```python
class _HotkeyEdit(QLineEdit):
    """热键编辑框：聚焦后按任意键绑定并保存到 setting.json；Esc 还原。"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setReadOnly(True)
        self.setFixedWidth(42)
        self.setAlignment(Qt.AlignCenter)
        self.setToolTip(
            "点击后按下任意单字符键绑定执行热键（保存到 setting.json）。\n"
            "热键勿与步骤按键冲突（模拟按键也会被监听）。")
        self._settings = Settings.load()
        self.setText(self._settings.hotkey)

    def mousePressEvent(self, event) -> None:  # noqa: N802 (Qt 命名)
        self.setText("…")                     # 提示等待按键
        super().mousePressEvent(event)

    def keyPressEvent(self, event) -> None:  # noqa: N802 (Qt 命名)
        if event.key() == Qt.Key_Escape:
            self.setText(self._settings.hotkey)   # 取消还原
            return
        ch = event.text()
        if ch:
            self._apply_key(ch)

    def _apply_key(self, key: str) -> bool:
        """绑定热键并保存；非法（非单字符）→ False 且还原显示。"""
        try:
            self._settings.set_hotkey(key)
        except ValueError:
            self.setText(self._settings.hotkey)
            return False
        self._settings.save()
        self.setText(self._settings.hotkey)
        LogModel.instance().info("执行热键已设为 %s" % self._settings.hotkey)
        return True
```

3b. `_build_toolbar` 中执行按钮之后加：

```python
        self._hotkey_edit = _HotkeyEdit(self)
        tb.addWidget(self._hotkey_edit)
```

3c. `MainWindow.__init__` 成员区加 `self._hotkey_edit: Optional[QLineEdit] = None`。

- [ ] **Step 4: 运行确认通过（GREEN）**

Run: `python -m widgets.main_widget`
Expected: `MainWindow smoke OK`

- [ ] **Step 5: Commit**

```bash
git add widgets/main_widget.py
git commit -m "feat: 热键设置输入框（按任意键绑定，保存 setting.json）"
```

---

### Task 12: 全量回归与文档更新

**Files:**
- Modify: `docs/工程分析.md`（第 8 节状态、未完成清单）
- 无代码变更。

- [ ] **Step 1: 全量冒烟回归（22 个模块）**

```bash
for m in model.path_util model.kscp_package model.project_variable model.variable_tree model.log_model model.point_timeline model.step_io model.step model.step_manager model.step_list model.step_list_store model.step_runner model.hotkey model.settings actions.控制流程.time_delay actions.控制流程.输出日志 actions.输入.按键 actions.输入.鼠标 widgets.step_card widgets.step_list_view widgets.step_list_tree_widget widgets.step_tree_widget widgets.variable_tree_widget widgets.resource_tree_widget widgets.main_widget widgets.log_widget widgets.image_overlay; do python -m "$m" || exit 1; done
```

Expected: 全部 `smoke OK`。

- [ ] **Step 2: 端到端检查**

Run: `python main.py sample.kscp --check; echo EXIT=$?`
Expected: `EXIT=0`（执行器 UI 在 --check 模式下正常构建与退出）

- [ ] **Step 3: 更新 docs/工程分析.md**

第 8 节：「第 3 层：写执行器 spec 并实现」标记为 ✅ 已完成（2026-08-30，commit 列表）；「第 2 层中断机制」标记 ✅（StepRunner 协作式停止 + 步数上限；线程模型 = 工作线程 + pynput 监听线程）。第 7.1 节「最大的缺口：执行器」标记 ✅ 已实现，简述组件。

- [ ] **Step 4: Commit**

```bash
git add docs/工程分析.md
git commit -m "docs: 工程分析——执行器与输入步骤已落地"
```

---

## 自审记录

- **Spec 覆盖**：§3 组件 1-6 → 任务 1/2/6-9/4-5/3/10-11；§4 错误表逐条落入对应任务冒烟；§5 冒烟清单 1-9 → 任务 3/2/4/6/9/7/5/10/12。
- **占位符扫描**：无 TBD/TODO；所有步骤含完整代码。
- **类型一致性**：`StepRunnerState`/`add_state_listener`/`input_value`/`_new_control` 等跨任务签名已核对一致；`PointTimeline.points[0]` 为 `(x, y)` 元组（与 model/point_timeline.py 一致）。
- **依赖顺序**：任务 1→6/8，2→9，3→10/11，4/5→10；无环。
