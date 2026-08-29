# 步骤基类设计（Step + 示例子类）

- 日期：2026-08-28
- 位置：`actions/base.py`（基类 + 状态枚举）、`actions/控制流程/time_delay.py`（示例子类）、`actions/__init__.py`（导出）
- 状态：已获用户批准（2026-08-28，经 brainstorming 确认：dataclass + 字段签名方案；do() 捕获异常置错后重抛）

## 1. 目标

「步骤」是用来执行的：后续会创建步骤列表，点击执行后每个步骤按顺序执行。本 spec 只实现**步骤基类 + 一个示例子类（延时）**；步骤列表 / 步骤管理模型 / 步骤管理树均留待后续。

## 2. 约束与惯例

- 「@actions」文件夹 → Python 包 `actions/`；子类按目录分组（如 `actions/控制流程/`）。
- 步骤依赖既有组件：
  - `widgets/step_io_widget.StepIOWidget`（数据 + GUI 生成器：resolve_inputs / write_outputs / 格式串）
  - `model.log_model.LogModel`（全局日志单例）
- 格式化串沿用 `ProjectVariable` / `StepIOWidget` 模式：UTF-8 JSON → urlsafe base64 去填充。
- 冒烟测试写在各模块 `__main__`，用 `python -m <module>` 运行（非 git 仓库，用运行验证替代提交）。
- 方法名按需求命名为 `input` / `output` / `run` / `do`（类体内遮蔽内建 `input`，属有意为之；调用处均为 `self.input()` 形式）。
- **实例容器命名**：输入/输出类实例属性命名为 `self.inputs` / `self.outputs`（避免与方法 `input()` / `output()` 同名冲突——实例属性会遮蔽方法，两者不能同名）。

## 3. 状态枚举 `StepStatus`（`actions/base.py`）

| 成员 | 值 | 含义 |
|---|---|---|
| `PENDING` | `"未执行"` | 初始状态 |
| `RUNNING` | `"执行中"` | do() 开始执行时置入 |
| `FINISHED` | `"执行结束"` | do() 正常结束 |
| `ERROR` | `"执行错误"` | 异常或 run() 手动置入 |

## 4. 步骤基类 `Step`

### 4.1 类属性（子类覆盖）

- `name: str` —— 该步骤的名称（唯一标识，参与格式串校验）
- `description: str` —— 描述该步骤的作用
- `input_class: type` —— 输入类：dataclass，字段类型注解为变量类型名（`"number"` / `"string"` / `"image"` 等）
- `output_class: type` —— 输出类：dataclass，同上；无输出用空 dataclass

### 4.2 实例属性

- `io: StepIOWidget` —— 步骤输入/输出设置（数据 + GUI 生成器）
- `status: StepStatus` —— 初始 `PENDING`
- `inputs: 输入类实例` / `outputs: 输出类实例` —— 运行时值容器（run() 内 `self.inputs.字段` / `self.outputs.字段` 读写）

### 4.3 方法

| 方法 | 作用 |
|---|---|
| `info_widget(parent=None) -> QWidget` | 信息显示窗口（GUI 生成器）：在步骤列表视图的卡片里生成自定义窗口；默认 `QLabel(description)`，子类可覆盖 |
| `input()` | ① 调用 `io.resolve_inputs()`，按 `dataclasses.fields(input_class)` 顺序把实际值 `setattr` 进 `self.input` |
| `run() -> int` | ② 用来执行并修改（可读写 `self.inputs` / `self.outputs`），返回步骤偏移量：默认 `1`（运行下一个步骤）、`2`（跳过下一个）、`0`（重新调用自身）；子类覆盖 |
| `output()` | ③ 按 `dataclasses.fields(output_class)` 顺序收集 `self.outputs` 字段值，`io.write_outputs(outs)` 写回变量树 |
| `do() -> int` | 整合整个流程，返回 run 的返回值（见 4.4） |
| `to_format_string() -> str` | 生成格式化数据（见第 5 节） |
| `from_format_string(cls, fmt, tree, package) -> Optional[Step]` | 静态方法：通过 base64 码判断能否返回自身（见第 5 节） |
| `create_default(cls, tree, package) -> Step` | 便捷工厂：由字段签名自动推导槽类型，构建含空 io 的默认实例（供「步骤管理」后续添加新步骤用） |

### 4.4 do() 流程

```
self.status = RUNNING
try:
    ① self.input()    # 从 io 获取输入数据并写入输入类
    ② offset = self.run()  # 调用并可修改输出类
    ③ self.output()   # 输出类数据传入 io，修改全局变量
except Exception as e:
    self.status = ERROR
    LogModel.instance().error(...)
    raise             # 异常重抛，由步骤列表引擎统一处理
if self.status is not ERROR:
    self.status = FINISHED
return offset         # ④ 返回偏移量
```

- run() 可手动置 `ERROR`（如延时秒数 ≤ 0），do() 不覆盖。
- run() 抛异常时 output() 不执行（不写回脏数据）。

### 4.5 槽类型推导与字段映射

- `StepIOWidget` 的 `input_type` / `output_type` 由 `input_class` / `output_class` 的字段类型注解列表推导（顺序一致）。
- 字段填充 / 收集均按 `dataclasses.fields()` 顺序。
- 签名 = `[(字段名, 类型注解), ...]` 列表。
- **注解必须为已注册的变量类型名**（`ProjectVariable.type_of` 可查；内置 `string` / `number` / `image`）。未注册 → `create_default` / `from_format_string` 处抛 `ValueError`（带步骤名/字段名/支持列表，即时定位）。（2026-08-28 落地，依据终审 Important #1）

## 5. 格式化串

```
json({"name": <名称>, "in": <输入类签名>, "out": <输出类签名>, "io": <io 格式串>})
→ UTF-8 → urlsafe base64 去填充
```

`from_format_string` 判定顺序：

1. 非法 base64 / JSON / 结构缺字段 / 字段非列表 / 数量不符 → 抛 `ValueError`（与其它模型一致）。
2. `obj["name"] != cls.name` → 返回 `None`（步骤名称不对）。
3. `obj["in"]` / `obj["out"]` 与 `cls` 的输入 / 输出类签名不一致 → 返回 `None`（签名不匹配）。
4. 通过 → `StepIOWidget.from_format_string(obj["io"], tree, package)` 还原 io，**校验 io 的槽类型列表与签名推导一致**（不一致 → `None`），返回 `cls(io)`。

## 6. 示例子类 `actions/控制流程/time_delay.py`

```
名称：延时
描述：用于延时（单位s）
输入类：seconds: "number"（默认值 0.0；dataclass 字段须带默认值，实例化空容器用）
输出类：（空 dataclass）
run():
    if self.inputs.seconds <= 0:
        self.status = StepStatus.ERROR
        LogModel.instance().error("延时秒数必须大于 0: %r" % self.inputs.seconds)
    else:
        time.sleep(self.inputs.seconds)
    return 1
```

## 7. 错误处理

- `do()`：任何异常 → 状态置 `ERROR` + `LogModel.error` + 重抛。
- `from_format_string`：非法编码 → `ValueError`；名称 / 签名不匹配 → `None`。
- 非法输入数据（如 resolve_inputs 不合规）由 `StepIOWidget` 既有语义抛 `ValueError`。
- 类定义错误（字段注解未注册变量类型）→ 类使用处（`create_default` / `from_format_string`）即时抛 `ValueError`，不静默。（2026-08-28 落地）

## 8. 测试（各模块 `__main__` 冒烟）

`actions/base.py`（桩子类：输入 number + 输出 number）：

- `create_default` 槽类型推导正确；`info_widget` 生成 QLabel。
- `do()` 全流程：输入解析 → run → 输出写回变量树，状态 `FINISHED`，返回偏移量。
- 异常：run 抛错 → 状态 `ERROR` + 日志记录 + 异常重抛；output 未执行（树未被写）。
- run 手动置 `ERROR` → do() 后状态保持 `ERROR`。
- 偏移量：默认 1；子类返回 2 / 0 时 do() 原样返回。
- `to_format_string` / `from_format_string` 往返（类型与值一致、规范化输出稳定）。
- 名称不匹配 → `None`；签名不匹配 → `None`；非法编码 → `ValueError`；io 槽类型与签名不符 → `None`。

`actions/控制流程/time_delay.py`：

- 正常：seconds=0.05，do() 返回 1、状态 `FINISHED`、耗时 ≥ 0.05s。
- 非法：seconds ≤ 0 → 状态 `ERROR`、日志含错误信息、无异常重抛（run 内处理）。

## 9. 非目标（YAGNI）

- 不做步骤列表 / 步骤管理模型 / 步骤管理树（后续任务）。
- 不做 `.kscp` 内 `actions/` 文件夹读取（步骤管理模型职责）。
- 不做步骤间数据共享 / 循环展开（偏移量机制已预留，语义由步骤列表引擎定义）。
- `info_widget` 默认只显示描述，不做复杂卡片布局。
