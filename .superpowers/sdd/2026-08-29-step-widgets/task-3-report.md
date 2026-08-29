# Task 3 报告：`StepCard` — 步骤对象卡片

**状态：DONE_WITH_CONCERNS**（见「疑虑」：Python 3.14 与简报逐字冒烟桩的兼容性偏差，已实证并做最小改动）

## 实现了什么

新建 `widgets/step_card.py`（C:\Users\feelnn\Desktop\项目\KScript\widgets\step_card.py）：

- `StepCard(QFrame)`：固定尺寸 240×340，`menu_requested = pyqtSignal(object, object)`（(自身, 全局坐标)，右键菜单由视图统一构建、卡片只发信号）。
- 结构：顶部条（QToolButton 激活按钮 + QLabel 步骤名）、中部 `step.info_widget(self)`、下方 `step.io.gen_widget(self)` 输入/输出 GUI。
- 背景色随 `step.status` 变化（`_STATUS_COLORS`：PENDING `#d9a83a` / RUNNING `#4caf50` / FINISHED `#bdbdbd` / ERROR `#e15554`）；io 校验非法 → `_INVALID_COLOR = "#e15554"` **优先于任何状态色**；`_SELECT_BORDER = "#3a7bd5"` 选中蓝边框（不影响状态背景色）。
- 激活按钮翻转 `step.enabled`：文本 ✓（绿底 `#27ae60`）/ ✗（灰底 `#9e9e9e`），卡片边框 solid / dashed 随 enabled 变化；`refresh()` 重检 io + 状态 + 激活；`set_selected(bool)`；`step` 只读属性；`contextMenuEvent` 发 `menu_requested`（带 noqa 注释）。
- 颜色刷新钩子：QLineEdit 输入即重检（`textChanged`）；picker 包装钩子（选择后重检）。
- 状态纯显示：不调用 `do()`。
- Qt 存根规避：模块级颜色一律字符串值，无 QStyle 枚举依赖。

## TDD 证据

### RED（Step 1→2）

新文件先只写文件头 docstring + 冒烟块（类未定义），运行：

```
$ python -m widgets.step_card
Traceback (most recent call last):
  ...
  File "C:\Users\feelnn\Desktop\项目\KScript\widgets\step_card.py", line 64, in <module>
    card = StepCard(s)
           ^^^^^^^^
NameError: name 'StepCard' is not defined
EXIT=1
```

符合预期：`python -m`（runpy）先按真名导入模块成功（模块级只有 docstring），冒烟执行到第一个 `StepCard` 引用处失败——**类缺失**，`NameError` 与简报所标 `ImportError: cannot import name 'StepCard'` 等价（按任务约束「ImportError 与 NameError 等价 = 类缺失」）；非语法错误。

### GREEN（Step 3→4）

补齐 imports + 颜色表 + `StepCard` 类（类定义在冒烟块之前）后运行：

```
$ python -m widgets.step_card
StepCard smoke OK
EXIT=0
```

核心行为断言全部通过：io 非法红优先（空槽初始即红）→ PENDING/RUNNING/FINISHED/ERROR 四态色 → io 再非法红优先（PENDING 下验证优先级）；激活翻转（✗/dashed → ✓/solid）；`set_selected(True/False)` 蓝边框出现/消失；`menu_requested.emit(card, QPoint(1,2))` 收讫 (自身, 坐标)；尺寸 240×340。

### 逐字核对（程序化比对简报）

- 文件头 + docstring：24/24 行逐字匹配简报 Step 1 代码块。
- 实现块：124/124 行逐字匹配简报 Step 3 代码块（唯一差异：其后多 1 个空行，属冒烟分隔注释前的排版，非代码）。
- 冒烟块：94 行中仅 2 处差异——桩 dataclass 注解去引号（`a: "number"` → `a: number`），见疑虑①。

## 依赖链回归（Step 5）

```
$ python -m actions.base
<frozen runpy>:130: RuntimeWarning: 'actions.base' found in sys.modules ...   ← 已知无害，忽略
Step smoke OK
EXIT=0

$ python -m widgets.step_io_widget
<frozen runpy>:130: RuntimeWarning: 'widgets.step_io_widget' found in sys.modules ...   ← 已知无害，忽略
StepIOWidget smoke OK
EXIT=0
```

回归 2/2 绿。

## 文件变更

- 新建：`widgets/step_card.py`（248 行）。仅此一个文件；未改动任何既有文件/API。

## 自审发现

1. **GREEN 首跑失败并定位根因**：完整实现后首次运行失败于 `_StubStep.create_default` → `Step._io_type_lists` → `ValueError: ... 类型注解未注册: 'number'`。实证：Python 3.14 下模块带 `from __future__ import annotations` 时，dataclass 注解 `a: "number"` 存为字符串 `"'number'"`（**含字面引号**，repr 显示 `"'number'"`），`ProjectVariable.type_of("'number'")` 返回 None；而 `actions/base.py` 冒烟能过是因为该模块**没有** future import（其注解 `a: "number"` 存为 `'number'`）。`get_type_hints` 也无法解救（`number` 非运行时名字）。
2. **无模板字节**：本任务不涉及 `write_file`，无中文 bytes 字面量；✓/✗ 为 str 字面量（utf-8 源文件）。
3. 颜色钩子连接时机安全：`gen_widget` 对输入槽 `blockSignals` 写初值、输出槽构造时 setText 不发射 `textChanged`，钩子连接后不会有未预期刷新。

## 疑虑

1. **简报内部冲突（唯一代码偏差）**：约束 7（新文件必须 `from __future__ import annotations`，简报 Step 3 亦含此行）与简报 Step 1 冒烟桩的引号注解 `a: "number"` 在本机 Python 3.14 上**不可同时满足**（引号注解会带引号入库 → type_of 查不到 → 必失败）。解决方案：保留 future import、实现与全部断言逐字，仅将桩 dataclass 注解去引号（`a: number = 0  # type: ignore`，保留 `# type: ignore`）——未来导入下字符串化后即 `'number'`，语义与 base.py 冒烟桩完全一致（简报原文「与 actions/base.py 冒烟同款」的意图）。已实证两方案（保留/去除 future import）均能绿，选择保 future import 因约束 7 是硬性文件要求。**提醒：T4/T5 若在带 future import 的模块里用引号类型名注解定义桩，会踩同一个坑。**
2. 实现块末尾多 1 个空行 + 冒烟分隔注释（`# ==== 冒烟演示 ...`）为排版性补充，与 `widgets/step_io_widget.py` 既有风格一致，非代码差异。
3. 报告期间控制台中文乱码为 GBK 终端显示问题，文件本身 utf-8 无碍。

---

## Round 1 修复：picker 延迟重检（评审 Important 缺陷，计划继承）

### 缺陷与修复

评审确认 `step_card.py` 原（简报 Step 3 逐字）实现缺陷：picker 包装器在包装函数**内部同步**调用 `self.refresh()`，但所选值由调用方**之后**才落地——`StepIOWidget._pick_input`/`_pick_output` 先 `name = self.picker(...)` 再 `self._set_input(...)`（step_io_widget.py:417-427），而 `_refresh_input_field`/`_refresh_output_field` 用 `blockSignals` 抑制了 `textChanged`（step_io_widget.py:353-364）。结果：经 picker 对话框选值后卡片保持旧颜色直到下一次无关刷新，钩子未达成文档用途。

修复（step_card.py 两处）：

1. imports：`from PyQt5.QtCore import QTimer, Qt, pyqtSignal`（新增 `QTimer`）。
2. 包装器：`self.refresh()` → `QTimer.singleShot(0, self.refresh)`（零延迟定时器在 `_set_input` 之后的下一事件循环迭代触发，值已落地再重检）。

### 覆盖性冒烟断言（新增于冒烟块末尾、`print("StepCard smoke OK")` 之前）

- 构造前把 `s.io.picker` 替换为 fake picker（`(tree, vtype, parent)`，内部 `s.io.change_value("input", 0, "")` 使 io 变非法，返回 `None`）；
- 构造第二个 `StepCard(s)`（此时 io 合法）→ `refresh()` → 断言 PENDING 色在 styleSheet；
- 调用 `s.io.picker(None, "number", card2)` 模拟点击资源按钮 → **立即**断言颜色仍是 PENDING（值未落地、同步刷新未发生）；
- `app.processEvents()` 触发零延迟定时器 → 断言 `_INVALID_COLOR` 在 styleSheet（值已落地、延迟重检生效）。

实证说明：`change_value` 经 `_set_input`（blockSignals）不会提前触发 textChanged 钩子，故「立即断言仍 PENDING」成立；`app.processEvents()` 确实触发零延迟定时器（冒烟绿即实证）。

### 验证

```
$ python -m widgets.step_card
StepCard smoke OK
EXIT=0

$ python -m actions.base
Step smoke OK
EXIT=0

$ python -m widgets.step_io_widget
StepIOWidget smoke OK
EXIT=0
```

冒烟 GREEN（含新覆盖断言）+ 回归 2/2 绿。

### 变更说明

- 本轮改动后实现块与简报 Step 3 不再逐字一致：`QTimer` 导入 + 包装器延迟刷新（评审强制修复）+ 冒烟新增 12 行覆盖断言。除此之外（四态色表、`_INVALID_COLOR`/`_SELECT_BORDER`、set_selected 蓝边框、menu_requested 信号、尺寸等）维持逐字。
