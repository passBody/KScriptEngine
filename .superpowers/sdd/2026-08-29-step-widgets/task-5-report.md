# Task 5 报告:StepListTreeWidget(步骤列表管理树)

日期:2026-08-29
状态:**DONE**
文件:`C:\Users\feelnn\Desktop\项目\KScript\widgets\step_list_tree_widget.py`(新建)

## 一、实现了什么

新文件 `widgets/step_list_tree_widget.py`,导出(`__all__ = ["StepListTreeWidget"]`),搭载 T2 `StepListStore` 的管理树:

1. **`StepListTreeWidget(store, manager, clipboard, on_changed, parent=None)`**(QTreeWidget 子类):只显示键值(组 = 文件夹图标 + 名,列表 = 自绘橙色图标 + 名);`list_selected = pyqtSignal(str)`(点击列表叶子 → 路径,组/空白不触发,经 `store.get` FileNotFoundError 判定组)、`store_changed = pyqtSignal()`(任何变更后发出)、`on_changed: Callable[[], None]`(变更回调,宿主保存 step_list.json)。构造:header 隐藏、ExtendedSelection、等行高、SimSun 11、自定义右键菜单、`currentItemChanged` 连接、QShortcut(Del → 删除、F2 → 重命名);末尾 `refresh()`。
2. **树构建**:`refresh(current_path=None)` 从 store 重建(保留展开、可指定当前项;blockSignals + 末次手动 `_on_current_changed`);`_fill` 按 `_children_of(prefix)`(直接子项按「组/列表」分组、各自按名排序,组在上、列表在下)填充,组图标 `QStyle.SP_DirIcon` 仅在 `self.style() is not None` 时设置(存根规避);`_walk_items`(生成器)/ `_find_item(path)`(按 `_PATH_ROLE = 0x0100`(Qt.UserRole 整数值)匹配)/ `_expanded_paths`。
3. **右键菜单**:`_on_context_menu`(点击未选中项先选中;`_group_of(item)` = 组项自身 / 叶子父组 / 空白根;按选中顶层集启用 复制/剪切/粘贴/重命名(仅单选)/删除);`_selected_paths_top`(选中集「顶层化」去被包含子项)。
4. **操作**:
   - `_act_add_group(context_group="")`:QInputDialog 组名,校验(空 / 含 `/` / `.` / `..`),`store.add_group`,ValueError/FileExistsError → warning,成功 `_changed(full)`。
   - `_act_copy`:`_clipboard.items = (名, _triples_of(path))`;`_triples_of` 先序三元组 `(相对路径, 是否组, 格式串列表|None)`,组自身 = `("", True, None)`,顶层相对路径 = 空串。
   - `_act_cut` = 复制 + `store.remove`(剪贴板保留,允许多次粘贴——与变量树 cut 清空不同的**有意**设计)。
   - `_act_paste(context_group="")`:`_dedup_name` 同父重名去重 name(1)、name(2)…(返回完整路径);按三元组 `add_group` 或 `add_list(full, StepList.from_format_strings(fmts, self._manager))` 重建(组递归重建、列表经 StepManager 解码);ValueError/FileExistsError → warning 并继续。
   - `_act_rename`:QInputDialog 带初值 `text=name`;校验后 `store.rename`,三种异常 → warning;成功 `_changed(new_path)`(重命名后重新选中新路径)。
   - `_act_delete`:QMessageBox.question 确认(Yes 默认),`store.remove` 顶层集(组 = 整棵子树)。
   - `_changed(current_path=None)`:refresh + `store_changed.emit()` + `_on_changed()`。
5. **图标**:`_make_list_icon()` QPainter 自绘(橙色圆角方块 + 三条浅色横线,18×18),不依赖 QStyle 标准图标枚举(存根规避)。

冒烟块位于文件末尾 `if __name__ == "__main__":`,除两处必要修正外逐字来自简报(见第四节)。全程不调用 `step.do()`。

## 二、TDD 证据

### RED(确认失败)

**第 1 次运行**(简报 Step 1 原样:仅文件头 + docstring + 冒烟块,类未定义):
```
Traceback (most recent call last):
  File "<frozen runpy>", line 203, in _run_module_as_main
  File "<frozen runpy>", line 88, in _run_code
  File "C:\Users\feelnn\Desktop\��Ŀ\KScript\widgets\step_list_tree_widget.py", line 89, in <module>
    tw = StepListTreeWidget(store, mgr, clipboard,
         ^^^^^^^^^^^^^^^^^^
NameError: name 'StepListTreeWidget' is not defined
EXIT=1
```
符合简报 Step 2 预期(简报明确:「RED 阶段 ImportError 与 NameError 等价 = 类缺失」;路径中文在控制台显示为 GBK 乱码,仅显示问题)。

**第 2 次运行**(实现逐字转录后,简报 bug #1 暴露):
```
Traceback (most recent call last):
  ...
  File "C:\Users\feelnn\Desktop\��Ŀ\KScript\widgets\step_list_tree_widget.py", line 28, in <module>
    from PyQt5.QtCore import Qt, QKeySequence, pyqtSignal
ImportError: cannot import name 'QKeySequence' from 'PyQt5.QtCore' (C:\0_self\bin\Python314\Lib\site-packages\PyQt5\QtCore.pyd)
EXIT=1
```

**第 3 次运行**(修正 #1 后,简报 bug #2 暴露):
```
Traceback (most recent call last):
  ...
  File ".../widgets/step_list_tree_widget.py", line 458, in <module>
    assert top == ["��������", "������", "����"], top
AssertionError: ['��������', '����', '������']
EXIT=1
```
实际顶层顺序 = `['清理体力', '空组', '打开软件']`(组在上、各自按名排序的**正确**结果),与简报冒烟断言的 `['清理体力', '打开软件', '空组']` 不符。

### GREEN(修正后)

```
StepListTreeWidget smoke OK
EXIT=0
```

### 简报代码块逐字核对(机械 diff)

对简报 Step 1 冒烟块 / Step 3 实现块与落地文件逐行做机械 diff(忽略行尾空白与 markdown 定界符):

- **实现代码块**(简报 Step 3):**320/320 行一致**,唯一差异 1 处 = 简报 `from PyQt5.QtCore import Qt, QKeySequence, pyqtSignal` 去掉 `QKeySequence`(修正 #1,见下);其余 imports、`_make_list_icon`、类定义、全部方法体、注释、docstring 逐字一致。
- **冒烟代码块**(简报 Step 1):**128/128 行一致**,唯一差异 1 处 = `assert top == [...]` 期望列表由 `["清理体力", "打开软件", "空组"]` 改为 `["清理体力", "空组", "打开软件"]`(修正 #2,见下);其余断言、数值、补丁点、调用顺序逐字一致。

## 三、依赖链回归输出

```
python -m widgets.step_list_view        → StepListView smoke OK   EXIT=0
python -m model.step_list_store         → StepListStore smoke OK  EXIT=0
```
(简报 Step 5 指定两项;附加全链覆盖)
```
python -m widgets.step_card             → StepCard smoke OK       EXIT=0
python -m model.step_list               → StepList smoke OK       EXIT=0
```
全部无管道直跑(EXIT 直接判定),`<frozen runpy>` 帧仅出现在 traceback 中,无 RuntimeWarning。

## 四、文件变更清单

| 文件 | 变更 |
|---|---|
| `C:\Users\feelnn\Desktop\项目\KScript\widgets\step_list_tree_widget.py` | **新建**:StepListTreeWidget 实现 + 冒烟块(约 480 行) |

## 五、自审发现(简报必要修正)

1. **简报 import bug(`QKeySequence` 不在 QtCore)**:简报 Step 3 首行 `from PyQt5.QtCore import Qt, QKeySequence, pyqtSignal` 在本机 PyQt5 5.15 下 ImportError——Qt5/PyQt5 中 `QKeySequence` 位于 `PyQt5.QtGui`(简报下一行 `from PyQt5.QtGui import ... QKeySequence ...` 已覆盖)。既有三个 widget 文件(`step_tree_widget.py` / `variable_tree_widget.py` / `resource_tree_widget.py`)全部从 QtGui 导入,项目内无任何 `QtCore.QKeySequence` 先例。修正:QtCore 行去掉 `QKeySequence`,保留 QtGui 行,行为不变。
2. **简报冒烟断言期望顺序不可能成立**:断言 `top == ["清理体力", "打开软件", "空组"]` 与实现(及实现自身注释「组在上、列表在下(每层各自排序)」/「各自按名排序」)矛盾——`sorted([清理体力, 空组]) = [清理体力, 空组]`(清 U+6E05 < 空 U+7A7A),列表 `[打开软件]` 恒在其后,顶层必为 `[清理体力, 空组, 打开软件]`;任何排序规则(码点、插入序、拼音、组先于列表)都无法把列表插到两个组之间。修正:断言期望改为 `["清理体力", "空组", "打开软件"]`(实现保持简报逐字不变)。其余冒烟断言全部路径化/成员判断(`_find_item` / `setCurrentItem` / `in`),与顶层顺序无关,已由 GREEN 全覆盖验证。
3. **PEP 563 注解陷阱规避**:`_DemoInput/_DemoOutput` 仅在模板字符串内(写入包后由 StepManager 编译,无 future import),模块级无任何 dataclass 桩,引号注解安全——已按先决信息处理。
4. 模板字节一律 `GOOD.encode("utf-8")` 写入;冒烟直跑不经管道;`_PATH_ROLE` 用整数值 0x0100;`self.style()` 判 `is not None`;图标 QPainter 自绘;`from __future__ import annotations` 置首;全程无 `step.do()`——均符合 Global Constraints。
5. 补丁点两处均被冒烟真实走到:`QInputDialog.getText` 的 3 参调用(`_act_add_group`)与 `text=` 关键字调用(`_act_rename`)均由同一 `staticmethod(lambda *a, **k: ...)` 补丁覆盖;`QMessageBox.question` 补丁覆盖 `_act_delete`。

## 六、疑虑

1. 两处简报偏差均以「修正冒烟/最小改实现」方式处理,与 T4 报告先例一致(逐字核对 + 偏差清单);若计划作者本意是其他排序规则,应回改冒烟断言并同步实现,当前 GREEN 已锁定「组在上、列表在下、各自按名排序」语义。
2. `QShortcut(QKeySequence.Delete, ...)` 与 `QShortcut("F2", ...)` 沿用 `step_tree_widget.py` 既有写法,冒烟未真实触发快捷键(只验证 `_act_*` 方法本身),快捷键绑定风险低但 T7 集成时值得目验。
3. T7 宿主集成(管理树 ↔ 视图联动、step_list.json 保存)不在本任务范围,`list_selected` / `store_changed` 信号语义已由冒烟覆盖(list_selected 仅叶子、组不触发;store_changed + on_changed 由 `changes` 计数验证)。

---

# 修复 Round 1(评审 Important 缺陷,控制器裁定)

日期:2026-08-29(同日追加)

## 缺陷

`widgets/step_list_tree_widget.py` `_on_context_menu` + `_act_copy` + `_act_cut`:**多选复制/剪切不一致导致数据丢失**。`_act_copy` 只把 `tops[0]` 存入剪贴板,而 `_act_cut` 删除**全部** tops;控件已启用 ExtendedSelection,菜单对任意非空选中集启用 复制/剪切——用户双选两个列表按剪切,第二个永久丢失,违反「剪切 = 复制 + 删除」约束。代码逐字来自简报 Step 3,系计划缺陷,原冒烟未覆盖多选。

## 修复方案(控制器裁定:限制复制/剪切为单选,与「重命名仅单选」UI 模式一致)

1. `_on_context_menu`:`a_copy.setEnabled(bool(tops))` → `a_copy.setEnabled(len(tops) == 1)`;`a_cut.setEnabled(bool(tops))` → `a_cut.setEnabled(len(tops) == 1)`。删除保持多选可用(删除无丢失问题,行为不变)。
2. `_act_copy` / `_act_cut` 入口守卫:`if not tops: return` → `if len(tops) != 1: return`(防御性,与重命名模式一致),各带一行注释说明「剪贴板单条目契约」。
3. 冒烟块新增覆盖性断言(删除断言之后、`print(...)` 之前):
   - `setCurrentItem(a)` + `a.setSelected(True)` + `b.setSelected(True)` 构造双选(选中集 = 打开软件 + 清理体力/检查体力,`assert len(tw._selected_paths()) == 2`);
   - `tw._act_copy()` → `assert clipboard.items is old_items`(no-op,剪贴板未被覆盖);
   - `tw._act_cut()` → `assert sorted(store.paths()) == paths_before`(no-op,未删除任何项);
   - 单选路径仍正常:原有冒烟断言(单选复制「打开软件」、单选剪切「清理体力(1)」)在本修复代码下重新执行通过,未破坏。

## 覆盖性测试命令 + 输出

```
python -m widgets.step_list_tree_widget
StepListTreeWidget smoke OK
EXIT=0
```
(新增双选 no-op 断言随冒烟通过;多选设置恰在调用前完成,规避树重建重置选中。)

## 回归结果

```
python -m widgets.step_list_view        → StepListView smoke OK   EXIT=0
python -m model.step_list_store         → StepListStore smoke OK  EXIT=0
```
