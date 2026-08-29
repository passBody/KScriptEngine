# Task 2 Brief: 示例子类 `actions/控制流程/time_delay.py`

(摘自 `docs/superpowers/plans/2026-08-28-step-base-class.md` Task 2,实施者以此为准,精确值照抄)

## Global Constraints(本项目全局约束,全部任务适用)

- 非 git 仓库:不提交,用运行冒烟验证替代。冒烟测试即各文件 `__main__` 中的 assert 块,`python -m <module>` 运行。
- 格式化串:UTF-8 JSON → urlsafe base64 去填充(与 `ProjectVariable`/`StepIOWidget` 一致)。
- 输入/输出 dataclass 字段必须带默认值(基类以无参方式实例化空容器)。
- 输入/输出类实例属性命名 `self.inputs` / `self.outputs`(方法 `input()`/`output()` 不能与实例属性同名——实例属性会遮蔽方法)。
- 冒烟测试用到 `QApplication` 时必须先创建(`QApplication.instance() or QApplication(sys.argv)`)。
- 路径中文包名合法(`actions.控制流程.time_delay`),勿改目录名。
- **禁用 `from __future__ import annotations`**(Task 1 裁定):引号注解需保持真实值;未来注解模式会把它存成含引号串 `"'number'"`,使 `dataclasses.fields().type` 推导出错误槽类型,冒烟断言必挂。

## 前置状态(Task 1 已完成)

`actions/` 包已存在:`actions/__init__.py`(导出 Step/StepStatus)、`actions/base.py`(Step 基类,含 `StepStatus` 枚举、`create_default`、`do`、`to_format_string`/`from_format_string`)。Task 1 的冒烟 `python -m actions.base` 输出 `Step smoke OK`。

**Files:**
- Create: `actions/控制流程/__init__.py`
- Create: `actions/控制流程/time_delay.py`
- Modify: `actions/__init__.py`(追加 TimeDelay 导出)

**Interfaces:**
- Consumes: `actions.base.Step`、`StepStatus`、`LogModel`(Task 1 产出;`Step` 类属性 name/description/input_class/output_class,`create_default(tree, package)`, `do()`, `to_format_string`/`from_format_string`;`StepStatus.ERROR`;`LogModel.instance().error(msg)`)
- Produces: `TimeDelay`(name="延时"、description="用于延时（单位s）"、input_class=TimeDelayInput(seconds: "number")、output_class=TimeDelayOutput(空))

---

- [ ] **Step 1: 写失败测试(先红)——建 `actions/控制流程/__init__.py` + `time_delay.py`(仅 docstring + 冒烟块)**

`actions/控制流程/__init__.py`:

```python
from .time_delay import TimeDelay

__all__ = ["TimeDelay"]
```

`actions/控制流程/time_delay.py`(此刻不含 `TimeDelay` 类定义,只有模块 docstring 与冒烟块):

```python
# -*- coding: utf-8 -*-
"""
延时步骤（控制流程）
====================

:class:`TimeDelay`：延时指定秒数（单位 s）。输入 ``seconds``（number），无输出。

运行规则
--------
* ``seconds > 0``：``time.sleep(seconds)``，返回偏移量 1。
* ``seconds <= 0``：状态切换为「执行错误」，日志报错（不抛异常）。

基本用法
--------
::

    step = TimeDelay.create_default(tree, pkg)
    step.io.change_value("input", 0, "2")    # 延时 2 秒
    offset = step.do()                        # 1
"""
```

然后在文件末尾追加(先只写冒烟块,类定义留到 Step 3):

```python
# ================================================================
# 冒烟演示：直接 ``python -m actions.控制流程.time_delay`` 运行
# ================================================================
if __name__ == "__main__":
    import sys
    import time

    from PyQt5.QtWidgets import QApplication

    from model.kscp_package import KscpPackage
    from model.log_model import LogModel
    from model.variable_tree import VariableTree

    app = QApplication.instance() or QApplication(sys.argv)

    pkg = KscpPackage.create_empty()
    tree = VariableTree.create_empty()

    # create_default：槽类型由字段签名推导
    t = TimeDelay.create_default(tree, pkg)
    assert t.io._input_type == ["number"]
    assert t.io._output_type == []
    assert t.name == "延时" and t.description == "用于延时（单位s）"
    assert t.status is StepStatus.PENDING

    # 正常：延时 0.05s，状态 FINISHED，偏移量 1
    t.io.change_value("input", 0, "0.05")
    t0 = time.monotonic()
    assert t.do() == 1
    assert time.monotonic() - t0 >= 0.05
    assert t.status is StepStatus.FINISHED

    # 非法：seconds <= 0 → 状态 ERROR + 日志报错（不抛异常）
    LogModel.instance().clear()
    t.io.change_value("input", 0, "0")
    assert t.do() == 1
    assert t.status is StepStatus.ERROR
    assert any("延时秒数必须大于 0" in e.message
               for e in LogModel.instance().entries)
    assert len(LogModel.instance().entries) == 1

    # 负值同样报错
    t.io.change_value("input", 0, "-1")
    assert t.do() == 1
    assert t.status is StepStatus.ERROR

    # 往返：还原后可继续执行
    fmt = t.to_format_string()
    assert "=" not in fmt and "+" not in fmt and "/" not in fmt
    t2 = TimeDelay.from_format_string(fmt, tree, pkg)
    assert isinstance(t2, TimeDelay)
    assert t2.io.to_format_string() == t.io.to_format_string()
    t2.io.change_value("input", 0, "0.05")
    assert t2.do() == 1 and t2.status is StepStatus.FINISHED

    print("TimeDelay smoke OK")
```

- [ ] **Step 2: 运行确认失败(红)**

Run: `python -m actions.控制流程.time_delay`
Expected: `ImportError: cannot import name 'TimeDelay' from 'actions.控制流程.time_delay'`(包加载时 `actions/控制流程/__init__.py` 第 1 行 `from .time_delay import TimeDelay` 即抛,time_delay.py 尚无 TimeDelay;与 Task 1 同型「功能缺失」红,ImportError/NameError 等价,无需再修)

- [ ] **Step 3: 实现最小代码 —— 在 `time_delay.py` 的 docstring 之后、冒烟块之前插入类定义**

```python
import time
from dataclasses import dataclass

from actions.base import Step, StepStatus
from model.log_model import LogModel

__all__ = ["TimeDelay"]


@dataclass
class TimeDelayInput:
    """输入：延时秒数（number）。"""
    seconds: "number" = 0.0


@dataclass
class TimeDelayOutput:
    """无输出。"""
    pass


class TimeDelay(Step):
    """延时步骤：用于延时（单位s）。"""

    name = "延时"
    description = "用于延时（单位s）"
    input_class = TimeDelayInput
    output_class = TimeDelayOutput

    def run(self) -> int:
        if self.inputs.seconds <= 0:
            self.status = StepStatus.ERROR
            LogModel.instance().error(
                "延时秒数必须大于 0: %r" % self.inputs.seconds)
        else:
            time.sleep(self.inputs.seconds)
        return 1
```

- [ ] **Step 4: 运行确认通过(绿)**

Run: `python -m actions.控制流程.time_delay`
Expected: `TimeDelay smoke OK`

- [ ] **Step 5: 更新 `actions/__init__.py` 导出 TimeDelay**

```python
from .base import Step, StepStatus
from .控制流程.time_delay import TimeDelay

__all__ = ["Step", "StepStatus", "TimeDelay"]
```

Run: `python -c "import actions; print(actions.TimeDelay.name, actions.StepStatus.RUNNING.value)"`
Expected: `延时 执行中`

- [ ] **Step 6: 全量回归验证(替代提交)**

Run:
```bash
python -m actions.base
python -m actions.控制流程.time_delay
python -m widgets.step_io_widget
python -m model.kscp_package
python -m model.project_variable
python -m model.variable_tree
python -m model.log_model
python main.py --check
```
Expected: 全部冒烟 OK、`main --check OK`,无输出错误。

## 实施者报告契约

完成全部步骤后,把完整报告写入 `.superpowers/sdd/2026-08-28-step-base-class/task-2-report.md`,包含:
- 各步骤执行情况(红/绿输出摘要)
- 冒烟运行命令与结果
- 自检发现与处理
- 疑问/顾虑

向控制器返回:状态(DONE / DONE_WITH_CONCERNS / NEEDS_CONTEXT / BLOCKED)+ 一行测试摘要 + 关注点。**不得派生子代理。**
