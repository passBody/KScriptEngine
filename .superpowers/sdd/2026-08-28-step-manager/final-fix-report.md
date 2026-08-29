# Final-Fix Report — StepManager `_collect` TypeError escape

**Date:** 2026-08-28
**Feature:** StepManager（步骤管理模型）
**File changed:** `C:\Users\feelnn\Desktop\项目\KScript\model\step_manager.py`

---

## 1. Finding addressed

**Final-review Important #1** — In `StepManager._collect` (model/step_manager.py), the class-level precheck `obj._io_type_lists()` was guarded by `except ValueError` only. When a template defines a Step subclass whose `input_class`/`output_class` is not a dataclass (e.g. forgetting the `@dataclass` decoration), `dataclasses.fields(object)` raises `TypeError: must be called with a dataclass type or instance`, which escaped `load()` and crashed the whole model — violating spec §6「全部错误均不抛未预期异常；模型保持可用」and §3.3's class-level skip contract. Since `load()` runs inside every template operation (`_write_template`, `remove_template`), one such file broke all subsequent add/paste/remove.

## 2. Fix applied (TDD)

### RED — regression smoke added first

Two additions in the `__main__` smoke block of `model/step_manager.py`:

1. After the existing `pkg.write_file("actions/坏注解.py", BAD_ANNO.encode("utf-8"))` line — a new template whose containers are `object` (non-dataclass):

```python
NO_DATACLASS = '''from actions.base import Step

class NoDcStep(Step):
    name = "缺容器"
    description = "输入/输出类不是 dataclass"
    input_class = object
    output_class = object
'''
pkg.write_file("actions/缺容器.py", NO_DATACLASS.encode("utf-8"))
```

2. After the existing `assert any("路径冲突" in m for m in errs)` line:

```python
assert any("缺容器" in m for m in errs)   # 非 dataclass 容器 → TypeError 也须类级跳过
```

**RED command:** `python -m model.step_manager`

**RED output** (smoke aborted, EXIT=1 — the uncaught crash the smoke now guards):

```
Traceback (most recent call last):
  File "<frozen runpy>", line 203, in _run_module_as_main
  ...
  File "C:\Users\feelnn\Desktop\项目\KScript\model\step_manager.py", line 336, in <module>
    mgr.load()
  File "...\model\step_manager.py", line 64, in load
    ok, count = self._load_file(rel)
  File "...\model\step_manager.py", line 100, in _load_file
    return True, self._collect(module, folder, rel)
  File "...\model\step_manager.py", line 121, in _collect
    obj._io_type_lists()
  File "...\actions\base.py", line 94, in _io_type_lists
    return (_types_of(cls.input_class, "输入"), ...
  File "...\actions\base.py", line 86, in _types_of
    for f in fields(klass):
  File "...\Python314\Lib\dataclasses.py", line 1465, in fields
    raise TypeError('must be called with a dataclass type or instance') from None
TypeError: must be called with a dataclass type or instance
EXIT=1
```

Failure matched the predicted path exactly (`TypeError` propagating out of `mgr.load()` via `_collect`).

### GREEN — one-line fix

`model/step_manager.py`, `_collect` (line ~122):

```python
# before:
            except ValueError as e:
# after:
            except (ValueError, TypeError) as e:
```

Nothing else in the implementation changed.

**GREEN command:** `python -m model.step_manager`

**GREEN output:** `StepManager smoke OK`, EXIT=0.

The non-dataclass template is now class-level skipped with a log entry「步骤模板注解非法, 跳过: 缺容器（...）」and the registry stays fully usable.

## 3. Regression results

All commands run from `C:\Users\feelnn\Desktop\项目\KScript`; 判定以 EXIT=0. (`python -m` 包模块的 runpy RuntimeWarning 是既有项目级模式,无害；`main.py --check` 无文本输出属既有行为。)

| Command | Result |
|---|---|
| `python -m model.step_manager` | `StepManager smoke OK`, EXIT=0 |
| `python -m actions.base` | `Step smoke OK`, EXIT=0 |
| `python -m actions.控制流程.time_delay` | `TimeDelay smoke OK`, EXIT=0 |
| `python -m widgets.step_io_widget` | `StepIOWidget smoke OK`, EXIT=0 |
| `python -m model.kscp_package` | `KscpPackage smoke OK`, EXIT=0 |
| `python -m model.project_variable` | `ProjectVariable smoke OK`, EXIT=0 |
| `python -m model.variable_tree` | `VariableTree smoke OK`, EXIT=0 |
| `python -m model.log_model` | `LogModel smoke OK`, EXIT=0 |
| `python main.py --check` | EXIT=0, no output (existing behavior) |

## 4. Files changed

- `C:\Users\feelnn\Desktop\项目\KScript\model\step_manager.py`
  - **Line 122:** `except ValueError as e:` → `except (ValueError, TypeError) as e:` (the fix).
  - **Lines ~322–329:** new `NO_DATACLASS` template block + `pkg.write_file("actions/缺容器.py", ...)` (regression smoke).
  - **Line ~344:** new `assert any("缺容器" in m for m in errs)` (regression smoke).

No other files touched. Not a git repo — no commit.
