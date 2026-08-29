# Task 2 Report: `StepListStore` — `model/step_list_store.py`

**Status:** DONE_WITH_CONCERNS — 唯一偏离已获协调者裁定照准(见「偏离与裁定」);T2 评审将核对此偏离。

## What I implemented

Created `C:\Users\feelnn\Desktop\项目\KScript\model\step_list_store.py`:

1. **Step 1 (RED):** 写入仅含模块头 docstring + 冒烟块的完整文件(逐字转录简报 Step 1 代码块),尚无类。
2. **Step 2:** 运行 `python -m model.step_list_store` → RED 确认(见下)。
3. **Step 3:** 在模块头与冒烟块之间加入 `StepListStore` 类(逐字转录简报 Step 3 代码块):
   - 模块级:`from typing import Any, Callable, Dict, List, Union, TYPE_CHECKING`、`import json`、`from model.step_list import StepList`、`if TYPE_CHECKING: from model.step_manager import StepManager`、`__all__ = ["StepListStore"]`、`JsonInput`
   - 路径归一化/校验:`__init__`(`self._root`)、`_norm_path`(staticmethod)、`_validate_name`(staticmethod)、`_parent_of`
   - 写:`add_group` / `add_list`
   - JSON:`to_json_bytes` / `_to_node`(staticmethod)/ `from_json`(classmethod)/ `_walk`
   - 全体 do 整合:`all_do_methods` / `_collect_do`(staticmethod)
   - 读:`create_empty`(classmethod)/ `paths` / `_collect_paths`(staticmethod)/ `get`
4. **Step 4:** GREEN(`StepListStore smoke OK`,EXIT=0)。
5. **Step 5:** 依赖链回归绿(`model.step_list` / `model.step_manager` 均 EXIT=0)。
6. **Step 6:** 全量回归绿(11 模块冒烟 + `main.py --check` 全部 EXIT=0,见下表)。

## TDD evidence

### RED

Command: `python -m model.step_list_store; echo "EXIT=$?"`(仓库根)

Output:
```
Traceback (most recent call last):
  File "<frozen runpy>", line 203, in _run_module_as_main
  File "<frozen runpy>", line 88, in _run_code
  File "...\model\step_list_store.py", line 43, in <module>
    from model.step_list_store import StepListStore
ImportError: cannot import name 'StepListStore' from 'model.step_list_store' (...). Did you mean: 'step_list_store'?
EXIT=1
```

Why expected:类未实现,冒烟块 `from model.step_list_store import StepListStore` 落属性查找失败。与 Task 1 相同,`python -m` 先按真名导入模块(runpy 语义),冒烟内 self-import 报 `ImportError` 而非简报预判的 `NameError`;简报已注明「runpy `ImportError` 与 `NameError` 同义——类缺失」,EXIT=1 符合预期,失败原因正是「类缺失」而非缩进/语法错误,冒烟本身无需修复。

### GREEN

Command: `python -m model.step_list_store; echo "EXIT=$?"`

Output:
```
StepListStore smoke OK
EXIT=0
```

### Step 5 依赖链回归

```
$ python -m model.step_list
StepList smoke OK
EXIT=0

$ python -m model.step_manager
StepManager smoke OK
EXIT=0
```

## 偏离与裁定(重要,评审核对点)

**简报自相矛盾一处:** 简报冒烟原断言 `store.paths() == ["清理体力/日常/跑图", "清理体力/检查体力", "打开软件"]`(逆插入序),而简报同一任务的实现 `paths()` 为 `return sorted(out)`,spec §4 亦明文「全部叶子路径(排序)」,docstring 同言「排序」。实测 Python `sorted()` 对该三串得 `["打开软件", "清理体力/日常/跑图", "清理体力/检查体力"]`(码位:打 U+6253 < 日 U+65E5 < 检 U+68C0)。冒烟期望列表既非排序亦非逆排序,是手写的逆插入序——与 `sorted()` 实现矛盾,按简报原样将永远无法 GREEN。

**处理(先问后行):** 已向协调者(主会话)发送消息说明矛盾 + 暂定方案;同时按证据先行实施暂定方案——实现逐字保留(`sorted`),冒烟期望列表改正为真实排序序。

**裁定(协调者,2026-08-29,任务中途收到):** 照准暂定方案——spec §4 权威,`sorted(out)` 正确,冒烟期望列表为计划手误;已同步修正计划文本与简报(`task-2-brief.md` 该行现为 `["打开软件", "清理体力/日常/跑图", "清理体力/检查体力"]`),并记录 Ruling 于台账;T2 评审将核对此偏离。协调者另确认 `assert "前导组/临时" in store.paths()` 为成员判断,与排序语义无冲突,无需处理。

**最终状态:** 我文件中的冒烟行与(已修正的)简报逐字一致(程序化校验通过,见自评)。

## Files changed

- Created: `C:\Users\feelnn\Desktop\项目\KScript\model\step_list_store.py`(我唯一改动的文件)。
- (协调者侧:`task-2-brief.md` 与计划文档已同步修正该行——非我所改。)

## Self-review findings

- **Completeness(逐字):** 程序化 diff 校验(对照修正后简报):
  - 类代码块逐字包含:`class block verbatim: True`
  - 冒烟主体(含 docstring)逐字一致(仅尾部换行差异,`rstrip` 后完全相等):`True`
  - 修正后的 `paths()` 断言行在文件中存在且与简报一致:`True`
- **Discipline(YAGNI):** 无额外方法/导入/特性;除目标文件外未动任何文件;遵循既有 `model/variable_tree.py` 范式(模块 docstring 带用法示例、`# ====` 分节注释、`@classmethod` 工厂、冒烟置于 `if __name__ == "__main__"`)。实现按简报逐字转录,**未**按简报 Interfaces 段写 staticmethod(与 Task 1 裁定一致:代码块优先,classmethod 子类友好)。
- **Constraints:** 未运行任何 git 命令;冒烟均以 `python -m <module>; echo "EXIT=$?"` 判定(未用 tail/head);模板字节 `GOOD.encode("utf-8")`(无中文 bytes 字面量);严格解码——「第 0 条」断言通过(`from_json` 坏格式串路径);路径归一化语义(反斜杠→正斜杠、去前导 `/`、空段/`.`/`..` → ValueError)由冒烟全量覆盖并通过;中文路径/目录名未动。
- **已知无害告警:** 多个模块冒烟出现 `<frozen runpy>` RuntimeWarning,属全局约束已知且无害,以 OK 标记 + EXIT=0 判定。

## Step 6 全量回归(最终文件态,逐条 EXIT)

| 命令 | EXIT |
|---|---|
| `python -m model.step_list` | 0 |
| `python -m model.step_list_store` | 0 |
| `python -m model.step_manager` | 0 |
| `python -m widgets.step_tree_widget` | 0 |
| `python -m actions.base` | 0 |
| `python -m actions.控制流程.time_delay` | 0 |
| `python -m widgets.step_io_widget` | 0 |
| `python -m model.kscp_package` | 0 |
| `python -m model.project_variable` | 0 |
| `python -m model.variable_tree` | 0 |
| `python -m model.log_model` | 0 |
| `python main.py --check` | 0(无输出,以退出码判定) |

## Concerns

- **唯一偏离(已裁定,评审核对点):** 冒烟 `paths()` 期望列表从简报原手写序(逆插入序)改正为真实码位排序序;协调者已照准并同步计划文本,台账已记录 Ruling。文件最终与修正后简报逐字一致。
- 无其他阻塞项。观察项(不阻塞):冒烟中 `paths()` 的排序断言仅有此一处,且 三态往返断言(`s_bytes.paths() == store.paths()`)在「排序」与「逆插入」两种实现下均成立——即冒烟本身无法区分这两种语义,排序语义由 spec §4/docstring 裁定(已照准)。
