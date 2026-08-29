# Task 7 review package — 主窗口集成:StepListManagementTree + 宿主 + 共享变量树

- 任务:widgets/main_widget.py(既有文件修改,计划最后一个任务)
- 唯一变更文件:`widgets/main_widget.py`
- 非 git 适配:无 BASE/HEAD 可 diff;下方「磁盘现状」为控制器已 Read 核实的行号区域(与简报代码块逐字对照),评审应独立 Read 磁盘文件抽查。

## 实施者报告摘要

- 状态 **DONE**;RED `NameError: name 'StepListManagementTree' is not defined`(EXIT=1,失败点 = 冒烟首条新特性断言)→ GREEN `MainWindow smoke OK` EXIT=0 → 全量回归 **17/17 全绿**(逐命令,不经管道);另附 `py_compile` OK
- 五处修改 + 冒烟块与简报**逐字节一致**(实施者程序化比对:`_cmp_t7.py` 比对后已删)
- `_open_package` 尾部(`_manage_btn` 起)原样保留,不再引用 `PlaceholderManagementTree`
- 疑虑:无

## 实施者报告的 3 项观察 + 1 项编排偏差(待评审独立判定)

1. **RED 编排偏差**:简报 Step 1 只替换 `__main__` 块、imports 在 Step 3。若严格先只替换 `__main__` 块,模块级 `VariableTree`(冒烟块依赖、当前文件未导入)会先行 NameError,RED 失败点落不到简报预期的 `StepListManagementTree`。实施者将 ① imports 与 __main__ 块替换同一步应用(imports 属测试载体),换取简报 Step 2 文档化 RED 错误逐字成立;RED 失败根因仍唯一 = 特性类缺失。
2. **模块 docstring 过时**:文件头 docstring 仍描述「占位『步骤』」。简报五处修改未含 docstring,按「不顺手重构」未动。
3. **`PlaceholderManagementTree` 类保留但不再被引用**(简报 ③ 仅要求在其前插入新类,未要求删除;未用代码,不影响运行)。

## 磁盘现状(控制器已核对,评审可抽查)

- imports `:25` `from typing import Callable, List, Optional`;`:40-45` 六个新 import 追加于 `from widgets.variable_tree_widget import VariableTreeWidget`(:39)之后(StepList/StepListStore/StepManager/VariableTree/StepClipboard+StepListView/StepListTreeWidget)
- `VariableManagementTree` `:157-183`:`__init__(package, tree: Optional[VariableTree] = None)` + `self._tree = tree`;`tree_widget()`/`preview_widget()` 两处 `VariableTreeWidget(self._package, self._tree)`
- `StepListManagementTree` `:213-276`:构造(自建 mgr + load;step_list.json 存在 → from_json,否则 create_empty + _save_store;clipboard/懒构建三字段)、`icon()` = `_make_icon("step")`、`_save_store` 写盘、`refresh_cards` → 宿主 `refresh_validity`(不重建)、`tree_widget()` 接线 `list_selected → _on_list_selected` + `store_changed → _on_store_changed`、`_on_list_selected`(get → set_list(list, mgr);FileNotFoundError → set_list(None))、`_on_store_changed`(当前列表消失 → 宿主回占位)
- `_StepListHost` `:279-301`:QStackedWidget,页 0 = 占位 QLabel「从左侧选择一个步骤列表」,页 1 = `StepListView(mgr, clipboard, None)` + `edited.connect(on_edited)`;`set_list` 透传 + 切页;`refresh_validity` 透传
- `MainWindow._open_package` `:668-704`:头部共享树 `tree = self._load_shared_tree(package)`;`_managers` = [Resource, Variable(package, tree), StepList(package, tree), Step] 4 位;接线 `vtw.tree_changed.connect(sl_mgr.refresh_cards)`(:686);:687 起 `_manage_btn` 原样保留
- `_load_shared_tree` `:706-714`:静态方法,variables.json 存在 → from_json 读回;否则 create_empty + 写盘
- `__main__` 块 `:729-822`:整体替换为集成冒烟块(逐字;`GOOD` 模板 `.encode("utf-8")` 写盘;`win = MainWindow(tmp)` + `win.show()` 不 exec;9 组断言 + `print("MainWindow smoke OK")`)
- `PlaceholderManagementTree` `:304` 仍在(未引用);`main()` 入口 `:720` 未动;`__all__` `:48` 未动

## 冒烟断言要点(逐字见简报 Step 1)

managers 结构(4 位、第 3 位 StepListManagementTree、name=「步骤列表」)→ 共享树同一性(`vtw._tree is sl_mgr._tree`)+ host/tree_widget 类型 → 空 store 已写盘 `step_list.json` + `paths() == []` → store API 添加列表 + `_save_store()` → `'"主列表"' in raw.decode("utf-8")` → `list_selected.emit("主列表")` → `host.currentIndex()==1` + `len(_view._cards)==1` → `tree_changed.emit()` → refresh_cards 不崩、卡片数不变 → `store.remove + store_changed.emit()` → `host.currentIndex()==0`。

## 当前文件

- `widgets/main_widget.py`(约 822 行)——变更区域 :21-46、:157-183、:213-301、:668-714、:729-822;其余为既有代码(ManagementTree 基类 :93、_make_icon :54、MainWindow :437、main :720)。
- 消费方接口(前序任务产出,报告/冒烟已实证):StepListTreeWidget(store, mgr, clipboard, on_changed) + list_selected/store_changed;StepListView(mgr, clipboard, parent) + edited/refresh_validity/set_list;VariableTreeWidget(package, tree) + tree_changed;StepListStore.from_json/create_empty/to_json_bytes/add_list/remove/get/paths;StepManager(package, tree) + load/create_step。
