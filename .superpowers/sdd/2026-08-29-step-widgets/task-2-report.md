# Task 2 Report: `StepListStore.remove` / `rename` / `walk` — 管理树支持

**Status: DONE（无阻断）** — 2026-08-29

## 实现了什么

在 `C:\Users\feelnn\Desktop\项目\KScript\model\step_list_store.py` 中：

1. typing 导入行改为 `from typing import Any, Callable, Dict, List, Tuple, Union, TYPE_CHECKING`（新增 `Tuple`）。
2. 在 `get()` 方法之后、`if __name__ == "__main__":` 之前新增「结构 / 变更扩展（管理树 UI 支持）」一节，含四个方法（与简报 Step 3 代码块**逐字一致**，含中文 docstring / 注释）：
   - `remove(path) -> None` —— 删列表或组（组 = 整棵子树）；不存在 → `FileNotFoundError`。
   - `rename(path, new_name) -> None` —— 非法新名 → `ValueError`；不存在 → `FileNotFoundError`；同父重名 → `FileExistsError`；通过重建父 dict（`items()` → 替换 → `clear()` → `update()`）**保持原字典插入位置**。
   - `walk() -> List[Tuple[str, bool]]` —— 全部组与列表路径，插入序先序（组在前、其子树紧随），**含空组**（管理树数据源）。
   - `_collect_walk(node, prefix, out)` 静态方法 —— 递归先序收集。
3. 冒烟块尾部（`print("StepListStore smoke OK")` 之前）追加简报 Step 1 断言块（**逐字一致**）。

## TDD 证据

### RED

命令：`python -m model.step_list_store`（项目根目录，不经过管道）

输出（节选）：

```
  File "...\model\step_list_store.py", line 401, in <module>
    w = store.walk()
        ^^^^^^^^^^
AttributeError: 'StepListStore' object has no attribute 'walk'
EXIT=1
```

符合预期：断言块先于实现加入，第一个 walk 调用即命中目标方法缺失 —— `AttributeError: 'StepListStore' object has no attribute 'walk'`（EXIT=1），正是简报 Step 2 预期的失败原因（目标类方法缺失；此时 remove/rename 尚未实现，但 walk 先被调用，失败点正确）。

### GREEN

命令：`python -m model.step_list_store`

输出：`StepListStore smoke OK`，EXIT=0。

## 依赖链回归

| 命令 | 输出 | EXIT |
|---|---|---|
| `python -m model.step_list` | `StepList smoke OK` | 0 |
| `python -m model.step_manager` | `StepManager smoke OK` | 0 |

回归 2/2 绿。

## 文件变更

- 修改：`C:\Users\feelnn\Desktop\项目\KScript\model\step_list_store.py`
  - 仅三处改动：typing 导入加 `Tuple`；`get()` 后新增 remove/rename/walk/_collect_walk 一节；冒烟块尾部追加断言。
  - 未改动任何既有方法 / API 签名。

## 自审发现 / 疑虑

1. **核心行为断言均通过**：
   - walk 先序含空组：`["打开软件", "清理体力", "清理体力/检查体力", "清理体力/日常", "清理体力/日常/跑图", "前导组", "前导组/临时", "空组"]`，组标记序列 `[False, True, False, True, False, True, False, True]` ✓
   - rename 保持插入位置：`list(store3._root) == ["先组", "改名列表", "后组"]`（重建父 dict 而非删除重插末尾）✓；改组后子树保留且对象引用不变 ✓
   - remove 删组 = 整棵子树 → `paths() == []` ✓；不存在 → `FileNotFoundError` ✓
2. **简报与文件事实的一处出入（无害）**：简报称「`from __future__ import annotations` 已在文件顶部（不要重复加）」，但 `model/step_list_store.py` 实际**没有**该行。按约束第 7 条「不要重复加」未添加；实现运行正常（`dict`/`Tuple`/`List` 均已在运行时可求值，无前向引用问题）。如需统一风格可在后续任务补加，但不属于本任务范围。
3. RED 输出中路径显示为 `C:\Users\feelnn\Desktop\��Ŀ\KScript\...` 是控制台对中文路径的编码显示伪影（GBK 控制台 vs UTF-8 文件名），与代码无关；后续输出（GREEN / 回归）均正常。
4. `python -m model.step_list_store` 运行时未见 `<frozen runpy> RuntimeWarning`，若出现属已知无害。

## 结论

冒烟绿（`StepListStore smoke OK` EXIT=0）+ 依赖链回归 2/2 绿；「提交」验证通过。
