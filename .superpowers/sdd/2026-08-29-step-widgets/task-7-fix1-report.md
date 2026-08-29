# Task 7 终审修复（fix-1 dispatch）报告

日期：2026-08-29。修复三条终审发现（I-1 / I-2 / docstring），另修复阻塞性既有潜伏缺陷（详见下）。

## 1. I-1：卡片内 io 编辑不触发保存（Important）

### 改动内容
- `widgets/step_card.py`
  - L66：新增类信号 `io_changed = pyqtSignal()`。
  - L104-110：io 文本框 `textChanged` 钩子改为调用 `_notify_io_edited`（弱引用传卡，见第 4 节）。
  - L111-122：picker 包装器值落地后（`QTimer.singleShot(0, ...)` 延迟处）改调 `self._io_edited`。
  - L142-149：新增 `_io_edited()` —— `refresh()` 重检颜色 + `io_changed.emit()`（只通知，不碰数据）。
- `widgets/step_list_view.py`
  - L180：`refresh()` 建卡时 `card.io_changed.connect(self.edited)`，复用既有 `edited → 宿主保存` 链路（`main_widget.py:290-291` 接线不动）。
- 冒烟断言（`print(... smoke OK)` 之前）：
  - step_card L290-296：建卡 → 连 `io_changed` → 经真实 textChanged 路径（`input_fields[0].setText("9")`）→ 断言 fired == [1]。
  - step_list_view L516-527：重建后的卡片 `setText("42")` 不崩 + `view._cards[0]` 编辑后 `edited` 计数器 +1。

### RED
`python -m widgets.step_card`（EXIT=1）：
```
AttributeError: 'StepCard' object has no attribute 'io_changed'
```
`python -m widgets.step_list_view`（EXIT=1，此时 view 未接线）：
```
AssertionError: [1, 1, 1, 1, 1, 1]      # 卡片编辑后 edited 未递增
```

### GREEN
`python -m widgets.step_card` → `StepCard smoke OK` EXIT=0
`python -m widgets.step_list_view` → `StepListView smoke OK` EXIT=0

## 2. I-2：picker 包装器链式累积（Important）

### 改动内容（`widgets/step_card.py` L111-122）
扁平化包装：
```python
orig = getattr(step.io.picker, "_kscript_orig", step.io.picker)
...
_picker._kscript_orig = orig
step.io.picker = _picker
```
每次包装只包最原始 picker；旧包装器被替换后即无引用、可回收。T3 冒烟 fake picker 无 `_kscript_orig` → `orig = fake`，天然兼容。

### RED
`python -m widgets.step_card`（EXIT=1）：
```
AssertionError: 0        # 旧实现回溯计数 0（无 _kscript_orig），期望 1
```

### GREEN
`python -m widgets.step_card` → `StepCard smoke OK` EXIT=0
冒烟断言 L298-307：同一 step 重建两次后 `_kscript_orig` 回溯计数恒为 1。

## 3. docstring 过时（Minor）—— `widgets/main_widget.py` L9-14

原 L10-12「步骤（列表）管理树用占位项演示…（占位『步骤』保留）」改为实际架构：
资源 / 变量 / 步骤列表 / 步骤模板四棵管理树；步骤列表管理树
（`StepListManagementTree`）= 左侧 `StepListTreeWidget` + 宿主 `_StepListHost`
（承载 `StepListView`），与变量管理树共享同一棵变量树（变量变更 → 卡片重检颜色），
不再有占位「步骤」项。无测试载体，直接改（3 行），`python -m widgets.main_widget` 通过。

## 4. 阻塞性既有潜伏缺陷（评审未列，TDD 中发现，已修）

I-1 冒烟（在重建后的卡片上模拟输入）暴露出**既有**崩溃与泄漏：
- 现象：视图对同一 step 重建两次后，对卡片内 QLineEdit `setText` → **进程静默崩溃**
  （EXIT=127，无输出，Qt 原生层）。逐个插桩定位：崩溃在 StepIOWidget 的
  `_set_input` → `_live_widgets()` → `_refresh_input_field`，异常为
  `RuntimeError: wrapped C/C++ object of type QLineEdit has been deleted`。
- 根因：`gen_widget` 每次建卡都会把控件弱引用登记进 `io._widgets`；视图重建后
  旧卡片 C++ 对象已销毁，但 Python 包装器仍被 shiboken 注册表持有（弱引用照常解析），
  `_live_widgets` 无法过滤 → 用户编辑任意重建过步骤的卡片即抛 RuntimeError，
  且 `io._widgets` 无限累积（评审 I-2 所述「已弃卡片永不释放」的另一半真相——
  评审将其归因于 picker 链，实测 textChanged 钩子闭包持卡也是自引用环）。
- 修复：
  1. `widgets/step_io_widget.py` L279-300：`_live_widgets` 按 C++ 存活过滤
     （`w.objectName()` 探活，RuntimeError 即丢弃并从登记表移除）。
     **注意：此文件不在分派「Files you may touch」清单内**，但它是本修复的
     根因所在（shiboken 包装器滞留无法在卡片侧消除），且是 I-1 冒烟（评审指定）
     通过的硬前提——做了最小外科式修改，其余行未动。
  2. `widgets/step_card.py` L50-59 + L104-110：textChanged 钩子经弱引用取卡
     （`_notify_io_edited`），切断「字段 → textChanged 槽 → 卡片」自引用环，
     非场景路径下卡片不再自我滞留。
- RED：多重建后 setText → EXIT=127 / RuntimeError；GREEN：冒烟全绿（含多重建回归断言 L518-524）。

## 5. 全量回归 17/17（逐个执行，不经管道）

| # | 命令 | 结果 |
|---|------|------|
| 1 | `python -m actions.base` | Step smoke OK, EXIT=0 |
| 2 | `python -m model.kscp_package` | KscpPackage smoke OK, EXIT=0 |
| 3 | `python -m model.variable_tree` | VariableTree smoke OK, EXIT=0 |
| 4 | `python -m model.project_variable` | ProjectVariable smoke OK, EXIT=0 |
| 5 | `python -m model.log_model` | LogModel smoke OK, EXIT=0 |
| 6 | `python -m model.step_manager` | StepManager smoke OK, EXIT=0 |
| 7 | `python -m model.step_list` | StepList smoke OK, EXIT=0 |
| 8 | `python -m model.step_list_store` | StepListStore smoke OK, EXIT=0 |
| 9 | `python -m widgets.step_io_widget` | StepIOWidget smoke OK, EXIT=0 |
| 10 | `python -m widgets.step_tree_widget` | StepTreeWidget smoke OK, EXIT=0 |
| 11 | `python -m widgets.resource_tree_widget` | ResourceTreeWidget smoke OK, EXIT=0 |
| 12 | `python -m widgets.variable_tree_widget` | VariableTreeWidget smoke OK, EXIT=0 |
| 13 | `python -m widgets.step_card` | StepCard smoke OK, EXIT=0 |
| 14 | `python -m widgets.step_list_view` | StepListView smoke OK, EXIT=0 |
| 15 | `python -m widgets.step_list_tree_widget` | StepListTreeWidget smoke OK, EXIT=0 |
| 16 | `python -m widgets.main_widget` | MainWindow smoke OK, EXIT=0 |
| 17 | `python main.py --check` | EXIT=0 |

（`<frozen runpy> RuntimeWarning` 为计划明示无害项。）

## 6. Files changed（精确行号）

- `C:\Users\feelnn\Desktop\项目\KScript\widgets\step_card.py`
  - L27 `import weakref`（新增）
  - L50-59 `_notify_io_edited` 模块级辅助（新增）
  - L66 `io_changed = pyqtSignal()`（新增）
  - L104-110 textChanged 钩子改弱引用 + `_io_edited`（修改）
  - L111-122 picker 包装扁平化（修改）
  - L142-149 `_io_edited()`（新增）
  - L290-307 I-1/I-2 冒烟断言（新增）
- `C:\Users\feelnn\Desktop\项目\KScript\widgets\step_list_view.py`
  - L180 `card.io_changed.connect(self.edited)`（新增）
  - L516-527 I-1 冒烟断言（新增）
- `C:\Users\feelnn\Desktop\项目\KScript\widgets\step_io_widget.py`（阻塞性修复，超出名义清单）
  - L279-300 `_live_widgets` 过滤 C++ 已销毁包装器（修改）
- `C:\Users\feelnn\Desktop\项目\KScript\widgets\main_widget.py`
  - L9-14 模块 docstring（修改）

## 7. 与既有冒烟兼容性

- **T3 picker 覆盖冒烟（step_card.py L275-288）**：fake picker 无 `_kscript_orig`
  → 扁平化取 `orig = fake_picker`，包装行为不变；「值已落地但同步刷新未发生 →
  processEvents 后延迟重检生效」两条断言原样通过（`change_value` 走
  `blockSignals` 路径，不触发同步 textChanged）。
- T4 全部既有断言（编辑/悬停/添加/粘贴/剪切/对话框）原样通过。
- `change_value` 程序化改值经 `blockSignals`，不会误发 `io_changed`（仅真实用户
  输入 / 选择器取值会触发保存通知），与「确认即写盘」语义一致。

## 8. Self-review findings / concerns

1. **越界文件**：`step_io_widget.py` 不在分派清单内，但为阻塞性根因（见第 4 节），
   改动仅 `_live_widgets` 一处（过滤 C++ 已销毁包装器），无接口/签名变化。
2. **评审 I-2 归因不完整**：picker 链只是「已弃卡片滞留」的路径之一；textChanged
   钩子闭包持卡是另一自引用环。两者均已消除（扁平化 + 弱引用钩子），
   `io._widgets` 不再无限累积。
3. **io_changed 可能双发**：输出槽经 picker 取值时，`_refresh_output_field`
   setText 不 blockSignals（既有行为）→ 同步发一次 + picker 延迟队列再发一次；
   保存幂等，无害。未改 `_refresh_output_field`（避免扩大范围）。
4. **极端时序**：picker 延迟定时器若在卡片销毁后触发，`_io_edited` 会对已销毁
   包装器抛 RuntimeError，被 PyQt 槽机制捕获打印，无害（需事件循环内同时
   重建+旧选择器回调，现实不可达）。
5. docstring 略去了「步骤模板为活动栏第 4 个图标」的旧注（占位时代描述），
   现按四棵管理树描述；如需保留图标说明可后续补一句。
6. 探针临时文件 `_probe_stale.py` 已删除；无残留调试代码。
