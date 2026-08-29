# StepIOWidget 设计

- 日期：2026-08-27
- 位置：`widgets/step_io_widget.py`，并在 `widgets/__init__.py` 导出
- 状态：已获用户批准（类名 `StepIOWidget`）

## 修订记录（2026-08-28，依据「接下来的规划.txt」第 1~5 条）

1. **去除 `input_callback` / `output_callback`**：构造签名改为
   `StepIOWidget(input_type, output_type, tree, package)`；输入→计算→输出
   的编排完全交给「步骤对象」内部（`do()` 流程），本对象不再承载回调。
2. **获取输入参数**：沿用 `resolve_inputs()`——按顺序返回输入变量的实际值
   （常量解析 / `{{name}}` 取 `get_actual_data()`），不合规抛 `ValueError`。
3. **设置输出参数**：沿用 `write_outputs(outs)`——输出变量全是工程变量；
   新增合规检查：`ProjectVariable.create` 后 `var.valid` 为 `False` 抛
   `ValueError`（如 number 槽写字符串），变量名不在树中抛 `FileNotFoundError`。
4. **格式化自身**：新增 `to_format_string()`——编码
   【输入类型列表、输出类型列表、输入值（非实际值）列表、输出值（非实际值）列表】
   为 urlsafe base64（去填充），JSON 结构 `{"it","iv","ot","ov"}`，与
   `ProjectVariable.to_format_string` 同款模式。
5. **静态方法还原**：新增 `StepIOWidget.from_format_string(fmt, tree, package)`
   ——反解 base64 返回自身；非法 base64 / 结构缺字段 / 数量不符抛 `ValueError`；
   槽值语义（引用不存在的变量）不抛错，经 `is_valid` 反映当前树状态。

## 目的

以 GUI 方式标记步骤的输入/输出变量或常量，可访问全局变量树 `VariableTree`。**轻量数据对象（不继承 QWidget）**——后续会有大量本对象实例，仅在需要 GUI 时调 `gen_widget` 生成 QWidget 嵌入「步骤对象」卡片；步骤执行函数借助本对象的回调与解析/写回方法完成 输入→计算→输出。对应 `按键操作.txt` 中的「设置输入输出窗口」。

## 构造

```python
StepIOWidget(
    input_type=["string", "number", "png"],   # 输入槽类型列表
    output_type=["number"],                   # 输出槽类型列表
    tree: VariableTree, package: KscpPackage, # 工程资源（树 + 包）
)
# parent 在 gen_widget(parent=None) 时传入
```

## 数据流（对象解析+写回；`run` 不在此提供——由「步骤对象」内部编排，无回调）

```python
resolved = widget.resolve_inputs()        # 常量原值 / {{name}} -> tree.get(name).get_actual_data()
...                                       # run：纯逻辑计算（输入→输出）
widget.write_outputs(outs)                 # 对象：按输出槽类型 ProjectVariable.create + tree.set 写回（检查变量合规）
```

## 槽位模型

- 输入槽存**字符串**（字段文本）：整串匹配 `{{name}}` → 变量引用；否则 → 常量（仅可编辑类型）。
- `_VAR_REF = re.compile(r"^\{\{(.+)\}\}$")`，整串匹配才算引用（不支持串内插值/计算，留作后续）。
- 输出槽存**变量名**字符串（须为树中已有变量）。
- 解析：引用 → `tree.get(name).get_actual_data()`（png→bytes 等）；常量 → 按类型解析（string→原串、number→int/float）。

## 类型扩展接口（预留）

- 编辑器样式直接复用 `VariableType.is_resource`：资源类（png）→ 只能选择（按钮）；非资源类（string/number）→ 可编辑文本 + 选择按钮。
- 常量解析器注册表 `_CONSTANT_PARSERS = {"string": identity, "number": _parse_number}`，`register_constant_parser(type, parser)` 供后续新增可编辑类型。资源类无需注册（自动走选择器）。
- 依赖 `ProjectVariable.type_of(vtype)` 访问类型处理器的 `is_resource`（新增的小访问器）。

## 关键属性与方法

| 成员 | 作用 |
|---|---|
| `is_valid` (属性) | 是否合规：输入引用须名在树中且类型匹配槽类型；常量非空且可解析；资源类不可为常量；输出名须在树中。任一不符则 `False` |
| `resolve_inputs() -> list` | 获取输入参数：按顺序返回输入变量的实际值；不合规抛 `ValueError` |
| `write_outputs(outs)` | 设置输出参数：按输出槽类型 `ProjectVariable.create(type, value, package)` + `tree.set(name, var)` 写回；创建的变量不合规（`valid=False`）抛 `ValueError`，变量名不在树中抛 `FileNotFoundError` |
| `to_format_string() -> str` | 格式化自身：编码【输入类型、输出类型、输入值（非实际值）、输出值（非实际值）】为 urlsafe base64（去填充），JSON 结构 `{"it","iv","ot","ov"}` |
| `from_format_string(fmt, tree, package)` (static) | 通过 base64 编码返回自身；非法 base64 / 结构缺字段 / 数量不符抛 `ValueError`；槽值语义不抛错，经 `is_valid` 反映当前树状态 |
| `gen_widget(parent=None) -> QWidget` | 按槽类型动态生成一个 QWidget（输入区+输出区）返回；可多次调用，各控件经弱引用互相同步 |
| `change_value(kind, index, value)` | 手动改槽位：`kind∈{"input","output"}`；input 的 value 为字段串（常量/`{{name}}`），output 的为变量名；同步刷新所有已生成控件 |
| `picker` (属性) | 变量选择器钩子（可写），签名 `picker(tree, vtype, parent) -> str|None`；默认内置极简选择器 |

注：`run()` 与回调均已移除——编排（input→run→output）是「步骤对象」的内部方法职责，本对象只提供 `resolve_inputs`（取输入实际值）与 `write_outputs`（写回输出）。本对象是普通对象（不继承 QWidget），未生成控件前即可 `change_value`/`is_valid`/`resolve_inputs`/`write_outputs`/`to_format_string`。控件内编辑经弱引用登记，写回对象数据并同步其它已生成控件。

## GUI 布局（紧凑卡片）

`QVBoxLayout`：上方「输入」区、下方「输出」区，各带小标题。每行 `QHBoxLayout`：
- string/number 输入：`QLineEdit`（可编辑，显示常量或 `{{name}}`）+ `QPushButton("…")`（开选择器，按槽类型筛选）。
- png 输入：仅 `QPushButton`（文案=已选名或"选择变量…"），点开选择器（筛选 png）。无可编辑框。
- 输出（各类型）：`QLineEdit`(只读，显示变量名) + `QPushButton("…")`（开选择器，按槽类型筛选）。
样式表控小尺寸（min-height/小字号），适配小卡片。

## 变量选择器（内置极简 + 钩子）

- 内置默认 `_default_picker(tree, vtype, parent) -> str|None`：`QDialog` + `QTreeWidget`，展示 `tree.filter_by_type(vtype)` 的变量（按分组嵌套），单选返回路径，取消返回 `None`。
- `picker` 属性（默认=内置）：外部可替换为未来的「树资源管理器」，签名一致即插即用。

## 错误处理

标准异常：`ValueError`（不合规/坏 kind/输出值数量不符）、`IndexError`（槽位越界）、`FileNotFoundError`（输出变量不在树中）。

## 测试

`if __name__=='__main__'`：建 `KscpPackage`+`VariableTree`+若干变量 → 无回调构造对象（断言非 QWidget 子类）→ `change_value` 设常量/引用（含中文/资源）→ `is_valid` 各情形 → `resolve_inputs`（png→bytes）→ `write_outputs` 写回树（断言树中变量已更新；变量不在树中/值不合规/数量不符各抛错）→ `to_format_string`/`from_format_string` 往返（断言类型与值一致、规范化输出稳定、还原后可继续写回；非法 base64/缺字段/数量不符抛错；引用不存在变量则 `is_valid=False`）→ `gen_widget` 生成 QWidget、`change_value` 同步字段、多控件同步 → `picker` 钩子替换 stub 经控件触发 → 不合规 `resolve_inputs` 抛错。

## 非目标（YAGNI）

- 不实现「步骤对象」（更高层职责）。
- 不实现串内插值/计算（`{{}}` 仅整串引用）。
- 不实现完整「树资源管理器」（仅内置极简选择器 + 钩子，留待后续）。
