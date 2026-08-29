# Task 7 报告 — 主窗口集成：StepListManagementTree + 宿主 + 共享变量树

- 实施者状态：**DONE**
- 唯一变更文件：`widgets/main_widget.py`
- 日期：2026-08-29

## What I implemented

按简报的五处修改逐字实现（**全部代码块与简报逐字节一致**，经程序化比对验证，见「Self-review」）：

1. **① imports**：`from typing import List, Optional` → `from typing import Callable, List, Optional`；在 `from widgets.variable_tree_widget import VariableTreeWidget` 之后追加六行 import（`StepList` / `StepListStore` / `StepManager` / `VariableTree` / `StepClipboard, StepListView` / `StepListTreeWidget`）。
2. **② `VariableManagementTree`**：`__init__` 增加可选 `tree: Optional[VariableTree] = None` 参数并存储 `self._tree`；`tree_widget()` / `preview_widget()` 两处 `VariableTreeWidget(self._package)` → `VariableTreeWidget(self._package, self._tree)`。
3. **③ 新类**（`StepManagementTree` 之后、`PlaceholderManagementTree` 之前）：
   - `StepListManagementTree(ManagementTree)`：名「步骤列表」，自建 `StepManager` + `load()`，`step_list.json` 存在则 `from_json` 读回、否则 `create_empty()` + `_save_store()` 写盘（镜像 variables.json 模式）；持有共享 `_tree` / `StepClipboard` / 懒构建 `_sl_tree`、`_host`、`_current`；`icon()` = `_make_icon("step")`；`refresh_cards()` → 宿主 `refresh_validity()`；`tree_widget()` 接线 `list_selected → _on_list_selected`、`store_changed → _on_store_changed`；`_on_list_selected` 取列表 → `host.set_list(list, mgr)`，`FileNotFoundError` → `set_list(None)`；`_on_store_changed` 当前列表消失 → 宿主回占位页。
   - `_StepListHost(QStackedWidget)`：页 0 = 占位 QLabel「从左侧选择一个步骤列表」；页 1 = `StepListView(mgr, clipboard, None)` 且 `edited → on_edited`（即 `_save_store`）；`set_list` / `refresh_validity` 透传。
4. **④ `MainWindow._open_package` 头部**：共享树 `tree = self._load_shared_tree(package)`；`_managers` 第 3 位 `PlaceholderManagementTree("步骤","step")` → `StepListManagementTree(package, tree)`；`VariableManagementTree(package, tree)` 传入同树；接线 `vtw.tree_changed.connect(sl_mgr.refresh_cards)`（变量树变化 → 卡片重检颜色）。`_manage_btn` 起原样保留。
5. **⑤ `_load_shared_tree`**（静态方法，置于 `_open_package` 之后）：`variables.json` 存在 → `from_json` 读回；否则 `create_empty()` + 写盘。

文件末尾 `if __name__ == "__main__":` 块：原 `main()` 阻塞块**整体替换**为简报 Step 1 集成冒烟块（逐字，含 `GOOD` 模板 `.encode("utf-8")` 写盘，无中文 bytes 字面量）。

## TDD Evidence

### RED（Step 2）

- 命令：`python -m widgets.main_widget`
- 失败输出（截取）：

```
Traceback (most recent call last):
  File "<frozen runpy>", line 203, in _run_module_as_main
  File "<frozen runpy>", line 88, in _run_code
  File "...\widgets\main_widget.py", line 665, in <module>
    assert isinstance(sl_mgr, StepListManagementTree)
                              ^^^^^^^^^^^^^^^^^^^^^^
NameError: name 'StepListManagementTree' is not defined. Did you mean: 'StepManagementTree'?
EXIT=1
```

- 为何符合预期：失败点 = 冒烟首条新特性断言（managers 第 3 位应为 `StepListManagementTree`），根因 = 集成类缺失（`_open_package` 仍以占位实现），错误类型与简报 Step 2 预期一致；`<frozen runpy>` 帧系已知无害的 runpy 包装，EXIT=1 且无 `MainWindow smoke OK`。
- **实施记录（一处编排偏差，透明说明）**：简报 Step 1 只要求整体替换 `__main__` 块、① imports 列在 Step 3。若严格先只替换 `__main__` 块，模块级 `VariableTree`（冒烟块依赖、当前文件未导入）会先行 `NameError: name 'VariableTree' is not defined`，RED 失败点无法落在简报明确预期的 `StepListManagementTree` 上。为让 RED 严格呈现简报 Step 2 的文档化预期（`NameError: name 'StepListManagementTree' is not defined`），我在「写失败测试」一步同时应用了 __main__ 块替换 + ① imports（imports 属测试载体本身）。RED 失败根因仍唯一 = 特性类缺失，判定不变。

### GREEN（Step 4）

- 命令：`python -m widgets.main_widget`
- 输出：`MainWindow smoke OK`，EXIT=0
- 冒烟断言全过：managers 结构（4 位、第 3 位 `StepListManagementTree`、name=「步骤列表」）；共享变量树（`vtw._tree is sl_mgr._tree`，host = `_StepListHost`，tree_widget = `StepListTreeWidget`）；空 store → `step_list.json` 已写盘且 `paths() == []`；store API 添加列表 → `_save_store()` 落盘且 `'"主列表"' in raw`；`list_selected.emit("主列表")` → 宿主 `currentIndex()==1` 且 `len(_view._cards)==1`；`tree_changed.emit()` → `refresh_cards` 不崩且卡片数不变；`store.remove + store_changed.emit()` → 宿主回占位页（`currentIndex()==0`）。

### 全量回归（Step 5）— 17/17 全绿

逐命令执行（不经过管道；`rc=$?` 于每条 python 命令后立即捕获）：

| # | 命令 | 结果 |
|---|---|---|
| 1 | `python -m actions.base` | `Step smoke OK` EXIT=0 |
| 2 | `python -m model.kscp_package` | `KscpPackage smoke OK` EXIT=0 |
| 3 | `python -m model.variable_tree` | `VariableTree smoke OK` EXIT=0 |
| 4 | `python -m model.project_variable` | `ProjectVariable smoke OK` EXIT=0 |
| 5 | `python -m model.log_model` | `LogModel smoke OK` EXIT=0 |
| 6 | `python -m model.step_manager` | `StepManager smoke OK` EXIT=0 |
| 7 | `python -m model.step_list` | `StepList smoke OK` EXIT=0 |
| 8 | `python -m model.step_list_store` | `StepListStore smoke OK` EXIT=0 |
| 9 | `python -m widgets.step_io_widget` | `StepIOWidget smoke OK` EXIT=0 |
| 10 | `python -m widgets.step_tree_widget` | `StepTreeWidget smoke OK` EXIT=0 |
| 11 | `python -m widgets.resource_tree_widget` | `ResourceTreeWidget smoke OK` EXIT=0 |
| 12 | `python -m widgets.variable_tree_widget` | `VariableTreeWidget smoke OK` EXIT=0 |
| 13 | `python -m widgets.step_card` | `StepCard smoke OK` EXIT=0 |
| 14 | `python -m widgets.step_list_view` | `StepListView smoke OK` EXIT=0 |
| 15 | `python -m widgets.step_list_tree_widget` | `StepListTreeWidget smoke OK` EXIT=0 |
| 16 | `python -m widgets.main_widget` | `MainWindow smoke OK` EXIT=0 |
| 17 | `python main.py --check` | EXIT=0（无 stdout——landing 渲染 + 800ms 定时自动退出，`main()` 成功路径本无输出，与 T6 回归同判据） |

另附：`python -m py_compile widgets/main_widget.py` OK（最终确认后重跑冒烟仍绿）。

## Files changed

- `C:\Users\feelnn\Desktop\项目\KScript\widgets\main_widget.py`（唯一变更文件；imports / `VariableManagementTree` / 两个新类 / `_open_package` 头部 + `_load_shared_tree` / `__main__` 冒烟块）

## Self-review findings

程序化逐字节比对（简报代码围栏 vs 磁盘文件）全部通过：

- 冒烟块、`_open_package` 头部、`_load_shared_tree`、`VariableManagementTree.__init__`、新类块、六个 import 行 —— **逐字节一致**；`_open_package` 尾部（`_manage_btn` 起）原样保留，不再引用 `PlaceholderManagementTree`。
- 约束抽查：无中文 bytes 字面量；新增代码无 `step.do()` 调用（`refresh_cards` → `refresh_validity` 仅重检颜色）；唯一变更文件 = `main_widget.py`；新代码中文注释与既有风格一致。
- 已知行为知悉：T5 `StepListTreeWidget.refresh()` 末行手动触发 `_on_current_changed` → `list_selected` 联动宿主 —— 宿主 `set_list` 对重复/同值调用幂等（`setCurrentIndex`/`refresh` 重复执行无害），冒烟与既有 T5 冒烟均实证无冲突。

观察项（未改，供评审/终审分诊，均不影响功能）：

1. **模块 docstring 已过时**：文件头 docstring 仍描述「步骤（列表）管理树用占位项演示…（占位『步骤』保留）」。简报五处修改未包含 docstring 更新，按「不顺手重构」约束未动。
2. **`PlaceholderManagementTree` 类保留但不再被引用**：简报 ③ 仅要求在其之前插入新类，未要求删除；保留不影响运行（未用代码）。
3. **RED 编排偏差（见上）**：① imports 提前到「写失败测试」一步，换取简报 Step 2 的文档化 RED 错误逐字成立；若评审认为必须严格分步，则纯 Step 1 的 RED 会是 `NameError: name 'VariableTree' is not defined`（同类缺失等价错误，EXIT=1）。

## Issues / Concerns

- 无阻塞项。`VariableManagementTree.__init__` 增加可选参数属简报 ② 明示修改，既有调用方（本文件 `_open_package`）同步更新；全库无其他调用点。
- 冒烟写入的临时 `.kscp` 位于系统 temp 目录（`tempfile.mktemp`），不污染仓库；自检用临时脚本 `_cmp_t7.py` 已删除。
