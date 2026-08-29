# Task 1 报告:步骤基类 `actions/base.py`

状态:**DONE_WITH_CONCERNS**(全部冒烟绿;简报原文有 3 处需修正才能运行/通过,详见下文;另有对后续任务的 1 个前瞻顾虑)

工作目录:`C:\Users\feelnn\Desktop\项目\KScript`(非 git,以运行冒烟替代提交)
Python:3.14.7(windows 平台,Qt 平台插件正常)

---

## 各步骤执行情况(红/绿)

### Step 1:建 `actions/__init__.py` + `actions/base.py`(仅 docstring + 冒烟块)

- `actions/__init__.py`:`from .base import Step, StepStatus` + `__all__`(照抄简报)。
- `actions/base.py`:模块 docstring(照抄)+ `__main__` 冒烟块(照抄,唯一修正见下)。

**冒烟块 1 处必须修正(简报原文 SyntaxError,非「功能缺失」类错误,按简报规则「先修复再重新确认」):**

- 简报原文 `_b64.urlsafe_b64encode(b'{"name":"桩步骤"}')` —— bytes 字面量含中文,Python 直接 SyntaxError(整文件无法编译,连红都跑不出来)。
- 修正为 `'{"name":"桩步骤"}'.encode("utf-8")`,意图不变(与冒烟块其余 `fmt.encode()` 风格一致)。

### Step 2:红确认

首次运行即撞上上述 SyntaxError → 先修复 → 重新确认红:

```
$ python -m actions.base
Traceback ... actions/__init__.py, line 1, in <module>
    from .base import Step, StepStatus
ImportError: cannot import name 'Step' from 'actions.base'
EXIT=1
```

红 = 功能缺失(Step/StepStatus 未定义)。

**与简报预期的差异(自检发现):** 简报 Step 2 预期 `NameError: name 'Step' is not defined`(冒烟块 `_StubStep(Step)` 处)。实际在 `actions/__init__.py` 第 1 行就抛 `ImportError`——因为简报指定的 `__init__.py` 在包加载时就 `from .base import Step`,base.py 此时尚无 Step,失败必然在此处冒头,冒烟块根本轮不到执行。两者同为「功能缺失」红,无需再修。

### Step 3:插入类定义

在 docstring 之后、冒烟块之前插入 Step 3 完整代码(`StepStatus`/`Step` 全量,照抄简报)。共两处修正(见下)。

### Step 4:绿确认(历经 3 次运行)

| 运行 | 结果 | 原因 |
|---|---|---|
| 第 1 次 | `AssertionError`(line 251:`s.io._input_type == ["number", "string"]`) | `from __future__ import annotations` 与**引号注解**冲突(见「自检发现 ②」) |
| 第 2 次 | `AssertionError`(line 303:`tree.get("n1").data == 10` `_ManErrStep` 段) | 冒烟桩 `_ManErrStep.run` 漏算 `outputs.total`(见「自检发现 ③」) |
| 第 3 次 | **`Step smoke OK`**,EXIT=0 | 绿 |

```
$ python -m actions.base
Step smoke OK
EXIT=0
```

(stderr 有 `runpy: RuntimeWarning: 'actions.base' found in sys.modules after import of package 'actions' ...`,见「疑问/顾虑 ②」)

### Step 5:依赖链验证

```
$ python -m widgets.step_io_widget
StepIOWidget smoke OK
EXIT=0

$ python -c "import actions; print(actions.Step, actions.StepStatus)"
<class 'actions.base.Step'> <enum 'StepStatus'>
EXIT=0

$ python main.py --check
(无 stdout 输出)
EXIT=0
```

说明:`main.py --check` 由既有 `widgets/main_widget.py` 实现——渲染主窗口后 `QTimer.singleShot(800, app.quit)` 自动退出,**不打印任何文本**(既有行为,非本任务引入)。简报预期字面 `main --check OK` 与既有代码不符;以退出码 0 + 无 traceback 为准(窗口渲染成功、自动退出、无异常)。

---

## 自检发现与处理(对简报原文的全部偏差)

1. **bytes 字面量含中文(SyntaxError)**:`b'{"name":"桩步骤"}'` → `'{"name":"桩步骤"}'.encode("utf-8")`(base.py 冒烟块,1 行)。
2. **`from __future__ import annotations` 与引号注解冲突**:未来注解模式下,`a: "number" = 0` 的注解以源码文本存为 `"'number'"`(含引号),`dataclasses.fields().type` 返回 `"'number'"`,`_io_type_lists()` 推导出 `["'number'", "'string'"]` → 槽类型断言失败。已实测确认两种模式差异:
   - 有 future import:`f.type == "'number'"`
   - 无 future import:`f.type == "number"` ✓
   处理:**删除 base.py 的 `from __future__ import annotations`(1 行)**。base.py 自身注解均为引号串或已 import 的 typing 名称,无 future import 也全部安全求值;冒烟断言(槽类型为 `["number", "string"]`)与全局约束(「字段类型注解为变量类型名(如 `"number"`)」)由此保持成立。
3. **冒烟桩 `_ManErrStep.run` 漏算输出**:`run` 只 `self.status = StepStatus.ERROR; return 1`,未算 `outputs.total`(默认 0),而 output() 仍执行写回 → n1 被写 0,与断言/注释「写 5*2=10」矛盾。处理:桩 run 补一行 `self.outputs.total = self.inputs.a * 2`(冒烟块,1 行)。

以上 3 处均为「照抄即无法运行/无法通过简报自身断言」的硬伤,按简报规则修复;其余代码(类定义、冒烟断言、`__init__.py`)与简报逐字一致。

---

## 疑问/顾虑

1. **Task 2 会重演 future-annotations 问题(前瞻)**:计划中 `actions/控制流程/time_delay.py` 的 Step 3 代码同样含 `from __future__ import annotations`,且 dataclass 用引号注解 `seconds: "number" = 0.0` → 在该文件内同样会得到 `f.type == "'number'"`,`create_default` 会建出 `["'number'"]` 槽。建议 Task 2 实施时在 `actions/` 各子类文件统一**不用 future annotations**(引号注解即够),或改用裸名注解;并建议同步修订计划文档。
2. **runpy RuntimeWarning + 模块双执行**:简报指定的 `__init__.py` 在包加载时 `from .base import Step`,导致 `python -m actions.base` 时 base.py 被执行两次(先作为 `actions.base`,再作为 `__main__`),stderr 出现 `RuntimeWarning: 'actions.base' found in sys.modules... may result in unpredictable behaviour`。当前功能与冒烟均不受影响(两个类对象互不干扰),属设计固有现象,非本次引入;`python -m widgets.step_io_widget` 也早有同款警告。若日后介意,可考虑 `__init__.py` 延迟导入,但那是超出本任务的既有包结构问题。
3. **`main.py --check` 无文本输出**:以退出码判定,简报的预期输出描述与既有代码不符(见 Step 5 说明)。

## 运行命令与结果汇总

| 命令 | 结果 |
|---|---|
| `python -m actions.base`(红,修复后) | `ImportError: cannot import name 'Step' from 'actions.base'`,EXIT=1 |
| `python -m actions.base`(绿) | `Step smoke OK`,EXIT=0 |
| `python -m widgets.step_io_widget` | `StepIOWidget smoke OK`,EXIT=0 |
| `python -c "import actions; print(actions.Step, actions.StepStatus)"` | `<class 'actions.base.Step'> <enum 'StepStatus'>`,EXIT=0 |
| `python main.py --check` | 无输出,EXIT=0(渲染+自动退出成功) |

交付文件:`actions/__init__.py`(4 行)、`actions/base.py`(382 行,UTF-8,含中文注释)。未改动本任务范围外的任何文件。
