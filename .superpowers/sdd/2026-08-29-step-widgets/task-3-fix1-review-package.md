# Task 3 fix round 1 — scoped re-review package

- 任务:widgets/step_card.py(StepCard,新建于 T3)
- 修复轮次:1/5(恢复原实施者)
- 变更文件(唯一):`widgets/step_card.py`
- 非 git 适配:无 BASE/HEAD 可 diff;下方「变更区域 before/after」为修复前后对照(旧文 = T3 评审所见简报逐字代码;新文 = 磁盘现状),另附当前文件全文。

## Findings under verification(上一评审的 Important #1,逐字核心句)

> step_card.py:96-101 — the picker wrapper calls `self.refresh()` inside the wrapper, but the picked value is only applied by the caller afterwards: `_pick_input`/`_pick_output` do `name = self.picker(...)` then `self._set_input(...)` (step_io_widget.py:417-427), and the follow-up `_refresh_input_field`/`_refresh_output_field` suppress textChanged via blockSignals (step_io_widget.py:353-364). Result: after choosing a variable through the picker dialog, the card keeps its old color until an unrelated refresh — the hook fails its documented purpose (spec §4 ③「资源类按钮经 picker 选择后重检」). Minimal fix: defer with `QTimer.singleShot(0, self.refresh)` inside the wrapper. Worth amending at plan level, since T4's view will inherit the stale-color behavior.

修复要求(派发原文):包装器内 `self.refresh()` → `QTimer.singleShot(0, self.refresh)`;补覆盖性冒烟断言(fake picker 使 io 变非法 → 调用后同步仍旧色 → `app.processEvents()` 冲刷 zero-timer 后变红);重新运行冒烟 + 回归;修复报告追加到 task-3-report.md。

## 变更区域 before/after

### imports(旧)
```python
from PyQt5.QtCore import Qt, pyqtSignal
```
### imports(新,step_card.py:29)
```python
from PyQt5.QtCore import QTimer, Qt, pyqtSignal
```

### 包装器(旧,简报逐字)
```python
        orig_picker = step.io.picker

        def _picker(tree, vtype, parent):
            result = orig_picker(tree, vtype, parent)
            self.refresh()
            return result

        step.io.picker = _picker
```
### 包装器(新,step_card.py:96-103)
```python
        orig_picker = step.io.picker

        def _picker(tree, vtype, parent):
            result = orig_picker(tree, vtype, parent)
            QTimer.singleShot(0, self.refresh)   # 延迟到值落地后(下一事件循环迭代)重检
            return result

        step.io.picker = _picker
```

### 冒烟新增断言(step_card.py:247-260,位于 `print("StepCard smoke OK")` 之前)
```python
    # picker 延迟重检:fake picker 让 io 变非法;refresh 延迟到值落地后
    def fake_picker(tree, vtype, parent):
        s.io.change_value("input", 0, "")
        return None

    s.io.picker = fake_picker                     # 构造前替换(card2 构造时会被包装)
    card2 = StepCard(s)                           # 此时 io 合法
    card2.refresh()
    assert _STATUS_COLORS[StepStatus.PENDING] in card2.styleSheet()
    s.io.picker(None, "number", card2)            # 模拟点击资源类「选择变量」按钮
    # 值已落地但重检被延迟到下一事件循环迭代 → 颜色仍是 PENDING(同步刷新未发生)
    assert _STATUS_COLORS[StepStatus.PENDING] in card2.styleSheet()
    app.processEvents()                           # 触发零延迟定时器
    assert _INVALID_COLOR in card2.styleSheet()   # 值已落地、延迟重检生效
```

## 当前文件全文

见 `widgets/step_card.py`(262 行)——控制器已直接 Read,评审者请自行 Read 该文件核对(修复区域 :29、:96-103、:247-260;其余区域 T3 评审已过,只需关注 fix diff 波及处:imports 行、包装器、冒烟末尾)。
