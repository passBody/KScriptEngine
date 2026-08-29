# Task 1 Report: `StepList.insert_format_strings` — 事务性解码插入

## 实现了什么

在 `C:\Users\feelnn\Desktop\项目\KScript\model\step_list.py` 的 `StepList` 类中，于 `from_format_strings` 之后、`create_empty` 之前新增方法：

```python
def insert_format_strings(self, index: int, fmts: List[str],
                          manager: "StepManager") -> None:
```

语义（与简报 Step 3 逐字一致）：
- **事务性**：先 `manager.from_format_string` 全部解码成功（`decoded: List[Step]`），再统一 `self._steps.insert(index + i, step)`；任一条坏条目 → `ValueError`（带「第 N 条」下标），**不产生任何部分插入**。
- **顺序保持**：第 `i` 条插到 `index + i`，依赖 Python `list.insert` 语义（越界钳制、负数回绕）。
- 非法编码 → `ValueError` 被捕获重抛为「第 %d 条格式串无效: %s」；无匹配模板（`from_format_string` 返回 None）→「第 %d 条无法还原: 没有可匹配的模板」。
- 复用既有 `List`/`Step` 导入与 TYPE_CHECKING 下的 `StepManager` 字符串注解，无新导入；未重复加 `from __future__ import annotations`；本任务不涉及模板字节。

冒烟块尾部（`print("StepList smoke OK")` 之前）追加了简报 Step 1 的断言块，复用既有 `fmts`、`fake`、`s1`、`mgr` 变量：覆盖头部插入、中间插入、越界钳制（99）、负数回绕（-1）、坏条目在中间（事务性零插入，断言「第 1 条」与无部分插入）、无匹配模板（断言「第 0 条」）。

## TDD 证据

### RED（先写断言，后实现）

命令（项目根目录，不经管道）：
```
python -m model.step_list
```

失败输出：
```
Traceback (most recent call last):
  File "<frozen runpy>", line 203, in _run_module_as_main
  File "<frozen runpy>", line 88, in _run_code
  File "...\model\step_list.py", line 235, in <module>
    sl4.insert_format_strings(0, fmts, mgr)          # ...
    ^^^^^^^^^^^^^^^^^^^^^^^^^
AttributeError: 'StepList' object has no attribute 'insert_format_strings'. Did you mean: 'from_format_strings'?
```

EXIT=1。失败点正是新增冒烟断言首次调用目标方法处，失败原因 = 目标方法缺失（AttributeError），与简报 Step 2 预期完全一致——测试先行、确证红色。

### GREEN（实现后）

命令：
```
python -m model.step_list
```

通过输出：
```
StepList smoke OK
```

EXIT=0。实现代码与简报 Step 3 逐字一致（含中文 docstring、注释风格、错误消息文案、「第 N 条」下标、`_steps` 私有访问）。

## 依赖链回归（3 命令）

```
python -m model.step_list_store && python -m model.step_manager && python -m actions.base
```

输出：
```
StepListStore smoke OK
StepManager smoke OK
<frozen runpy>:130: RuntimeWarning: 'actions.base' found in sys.modules after import of package 'actions', but prior to execution of 'actions.base'; this may result in unpredictable behaviour
Step smoke OK
```

3/3 全绿，EXIT=0。`<frozen runpy> RuntimeWarning` 为已知无害警告（约定忽略）；除此以外输出无多余噪音。

## 文件变更

- `C:\Users\feelnn\Desktop\项目\KScript\model\step_list.py`
  - 新增 `StepList.insert_format_strings`（类内 `from_format_strings` 之后、`create_empty` 之前，约第 90-108 行）。
  - 冒烟块尾部追加 insert_format_strings 断言（约第 253-277 行）。
  - 其余文件内容未动。

## 自审发现

- 冒烟断言与简报 Step 1 逐字核对：一致（含行内注释对齐）。
- 实现与简报 Step 3 逐字核对：一致。
- RED 阶段确实先失败再实现（非补测试）。
- 不涉及模板字节/编码约定（无中文 bytes 字面量）。
- `List` 已在文件顶部 typing 导入，未重复导入。

## 疑虑

无。
