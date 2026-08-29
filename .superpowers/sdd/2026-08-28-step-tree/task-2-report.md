# Task 2 Report: `widgets/step_tree_widget.py`(树 + 信息面板 + 移动对话框)

## What I Implemented

Created the single new file `C:\Users\feelnn\Desktop\项目\KScript\widgets\step_tree_widget.py` (611 lines):

- Module docstring(中文,含基本用法示例)
- Imports + `_PATH_ROLE = 0x0100` + `__all__` + `_make_step_icon()`(橙色圆角方块 + 三条浅色横线)
- `StepTreeWidget(QTreeWidget)`:构造(空包自建 `actions/`、`StepManager(package, VariableTree.create_empty())` 纯内存变量树、Del/F2 快捷键)、`refresh(current_path=None)`(保留展开/选中)、`_build_group_map`/`_fill`(目录在前、叶子在后,`name (in→out)` 标签)、`_walk_items`/`_find_item`/`_expanded_paths`/`_selected_paths`/`_selected_paths_top`/`_current_path`、`_on_current_changed`(仅叶子 emit `step_selected`)、`_update_panel`、`preview_widget()`(懒建面板)、`_group_of`、`_on_context_menu`(移动/删除/创建组/重命名组)、`_existing_groups`(递归排序剥 `actions/` 前缀)、`_act_move`/`_act_delete`/`_act_create_group`/`_act_rename_group`(错误路径 `QMessageBox.warning`,不静默吞)
- `StepInfoPanel(QStackedWidget)`:占位页(0)/信息页(1);`_make_column`/`_slot_row`/`_fill_column`(保留表头,动态清空重填)、`load(path)`(类级 `_signature`,零实例)、`show_placeholder(text="")`
- `MoveStepDialog(QDialog)`:可编辑下拉框(「(根目录)」+ 现有组 + 用户可输新组名)、`target()`(去空白/斜杠,空串=根目录)
- 冒烟块(文件末尾,`python -m widgets.step_tree_widget` 直跑,不 import 本模块自身)

## What I Tested and Test Results

All commands run from `C:\Users\feelnn\Desktop\项目\KScript`:

| Command | Result |
|---|---|
| `python -m widgets.step_tree_widget` (Step 2, RED) | `NameError: name 'StepTreeWidget' is not defined`, EXIT=1 — expected |
| `python -m widgets.step_tree_widget` (Step 4, GREEN) | `StepTreeWidget smoke OK`, EXIT=0 |
| `python -m model.step_manager` | `StepManager smoke OK`, EXIT=0 |
| `python -m widgets.step_io_widget` | `StepIOWidget smoke OK`, EXIT=0(见 Concern 2) |
| `python -m actions.base` | `Step smoke OK`, EXIT=0 |
| `python -m py_compile widgets/step_tree_widget.py` | COMPILE OK |

Smoke coverage exercised:空包构造自建 actions/、树结构断言(顶层 `["控制流程", "空组", "示例 (2→1)"]`)、叶子/组 `_find_item`、文件夹图标、坏语法模板不显示、信息面板页切换与名称/分组/描述/签名栏计数(1→1、2→1)、占位页、`step_selected` 信号仅叶子触发、mgr 驱动操作 + `refresh`(`create_group`/`move_template`/`rename_group`/`remove_template` 与 `_current_path` 恢复、空组消失)、`MoveStepDialog.target()` 解析(现有组/根目录/去空白新组名)。

## TDD Evidence

**RED** — command: `python -m widgets.step_tree_widget`(文件仅 docstring + 冒烟块)
```
Traceback (most recent call last):
  File "C:\Users\feelnn\Desktop\项目\KScript\widgets\step_tree_widget.py", line 93, in <module>
    empty = StepTreeWidget(KscpPackage.create_empty())
NameError: name 'StepTreeWidget' is not defined
EXIT=1
```
Why expected: 类未定义(功能缺失红),首个引用处即炸,符合 Step 2 预期。

**GREEN** — command: `python -m widgets.step_tree_widget`(插入全部实现后)
```
StepTreeWidget smoke OK
EXIT=0
```

## Files Changed

- Created: `C:\Users\feelnn\Desktop\项目\KScript\widgets\step_tree_widget.py`(唯一改动;`widgets/__init__.py` 未动,遵守循环导入防线)

## Self-Review Findings

1. **冒烟块唯一偏差**:计划原文 `assert not group.icon().isNull()` 在本机 PyQt5 5.15.11 抛 `TypeError: icon(self, column: int): not enough arguments`(5.15.11 的 `QTreeWidgetItem.icon()` 无默认列参;计划第 333 行同款代码未过真实运行)。改为 `assert not group.icon(0).isNull()`(注释注明原因),断言意图不变(组=文件夹图标)。**实现代码全部逐字照抄,仅冒烟一行因运行环境修正。**
2. **关键约束自查(全部通过)**:全程无 `create_step` 调用(仅 docstring 文字提及);信息数据源 = 模板类级 `_signature`,零实例创建;模板内容绝对导入 `from actions.base import Step`;中文 bytes 一律 `.encode("utf-8")`;冒烟先建 `QApplication`;`VariableTree.create_empty()` 纯内存、无 `write_file` 落盘;`step_tree_widget` 未加入 `widgets/__init__.py`;冒烟块不 import 本模块自身。
3. 面板 `load()` 未知路径抛 ValueError 由 `_update_panel` 捕获回占位页;删除/重命名/移动的 ValueError 均弹窗提示,不静默吞。
4. 快捷键 Del/F2 由 `QShortcut(self)` 托管,构造后自动启用。

## Issues or Concerns

1. **Concern 1(已修,需终审知悉)**:见 Self-Review #1 —— 冒烟断言 `icon()` → `icon(0)` 为对计划的唯一偏差,其余逐字。
2. **Concern 2(非本任务引入,预存)**:`python -m widgets.step_io_widget` 与 `python -m actions.base` 在 stderr 有 Python 3.14 runpy 警告 `'...' found in sys.modules after import of package ...`——因 `widgets/__init__.py`/`actions/__init__.py` 的相对导入先于 runpy 执行模块所致,与本文件无关(本模块未进包 `__init__`),冒烟均 OK、EXIT=0。
3. 无其他未决问题;Task 3 可正常消费 `StepTreeWidget`/`StepInfoPanel`/`MoveStepDialog`。
