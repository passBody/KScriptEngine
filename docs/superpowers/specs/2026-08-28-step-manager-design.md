# 步骤管理模型设计（StepManager — 模板工厂）

- 日期：2026-08-28
- 位置：`model/step_manager.py`
- 状态：已获用户批准（2026-08-28，经 brainstorming 确认：**纯模板工厂，不保存实例**；增删复制粘贴剪切作用于模板；拷贝入口本期提供）

## 1. 目标

「步骤管理模型」是步骤模板的**工厂**：从 `.kscp` 包内 `actions/` 目录加载步骤模板并管理模板，按需**产出**步骤对象实例。模型**不保存任何实例**——实例的保存与 `step_list.json` 归后续「步骤列表模型」（其内部才保存实例对象）。

- 模板 = `.kscp/actions/` 下的 `.py` 文件（惯例**一文件一步骤类**，如 `actions/控制流程/time_delay.py` 定义 `TimeDelay`）。
- 注册表 = `{路径: (步骤类, 文件相对路径)}`，路径 = `文件夹名/类.name`（顶层文件只有 `name`，如 `"示例"`；子目录如 `"控制流程/延时"`）。
- 为后续左侧「步骤管理树」提供平铺路径数据（树按 `/` 分段构建）。

## 2. 约束与惯例

- 模型层纯逻辑（`PyQt-free`；`create_default` 构造 `StepIOWidget` 需 `QApplication` 的场景只在冒烟出现）。
- 复用 `Step` 既有 API：`create_default(tree, package)`、`to_format_string` / `from_format_string`、`_io_type_lists()`（类级注解预检）。
- **模板文件必须绝对导入项目包**（`from actions.base import Step`），禁用相对导入（动态导入的模块没有真实包结构）。
- 非 git 仓库：冒烟测试写在模块 `__main__`，`python -m model.step_manager` 运行。
- 日志：错误一律 `LogModel.error()`；成功的加载/操作摘要用 `LogModel.info()`。
- 格式化串沿用 `Step` 模式（UTF-8 JSON → urlsafe base64 去填充）。

## 3. 构造与加载

### 3.1 构造

```python
StepManager(package: KscpPackage, tree: VariableTree)
```

- `load()` **显式调用**（构造不自动加载——`.kscp` 可能尚未写入模板）。`load()` **幂等**：每次清空注册表重建。

### 3.2 加载流程 `load()`

1. 遍历 `package` 内 `actions/**/*.py`（子目录 = 文件夹分组；忽略非 `.py`）。
2. 每个文件：读字节 → 解包到临时目录 → `importlib.util.spec_from_file_location` 动态导入。
   - **模块名唯一前缀**：`_kscp%d_actions_<相对路径转点化>`（如 `_kscp1_actions_控制流程.time_delay`），防同名模板文件跨工程串包（`sys.modules` 缓存旧类）。
   - 导入完成即从 `sys.modules` 清理前缀模块（类对象由注册表持有，模块本身不再需要）。
3. **收集**：模块命名空间中所有 `Step` 子类且 ≠ `Step`（输入/输出 dataclass、辅助类自动排除）。条目记录其来源文件相对路径。
4. **类级预检**：每个收集到的类调 `_io_type_lists()`（注解注册校验）——失败 → 日志报错跳过该类，不拖到生成时才报。
5. 注册：路径 = `文件夹名/类.name`；**同目录 name 冲突 → 日志报错跳过后者**（跨目录允许同名）。

### 3.3 错误粒度

| 错误 | 行为 |
|---|---|
| 文件级（语法错误 / 导入失败 / 读取失败） | `LogModel.error` 报错，**跳过整个文件** |
| 类级（注解未注册变量类型） | `LogModel.error` 报错，**跳过该类**，文件内其余类照常 |
| 同目录 name 冲突 | `LogModel.error` 报错，跳过后者 |
| 其余模板 | 照常加载；加载结束 `LogModel.info` 摘要（成功 N 个 / 跳过 M 个） |

## 4. 产出（不保存）

### 4.1 `create_step(path: str) -> Step`

- 注册表查路径 → `create_default(tree, package)` → 返回新实例（空 io、`PENDING`、未加入任何集合）。
- 未知路径 → 抛 `ValueError`（消息带现有路径列表，与 `ProjectVariable.create` 未知类型风格一致）。

### 4.2 `from_format_string(fmt: str) -> Optional[Step]`

- 遍历注册表各类 `from_format_string(fmt, tree, package)`（`None` 即不匹配，换下一个类）。
- `fmt` 非法编码 → 立即重抛 `ValueError`（格式串问题，非匹配问题）。
- 全部不匹配 → `LogModel.error` + 返回 `None`。

## 5. 模板操作（对 `.py` 文件，操作后自动重新 `load()` 刷新注册表）

| 方法 | 行为 |
|---|---|
| `template_paths() -> List[str]` | 排序后的注册表路径列表（树 UI 数据源） |
| `add_template(src_py, dest_dir="") -> bool` | 读本地 `.py` → 写入 `actions/<dest_dir>/<文件名>` → `load()` → **无贡献则回滚删除 + error 日志**（文件内无 Step 子类 / 重名被跳）；成功 → `info`；返回是否成功（`copy_source_templates` 统计用） |
| `remove_template(path)` | 注册表条目 → `package.remove(文件)` → `load()`；未知路径 → `ValueError` |
| `copy_template(path)` | 剪贴板 ←（文件名, 文件字节）；未知路径 → `ValueError` |
| `cut_template(path)` | = `copy_template` + `remove_template` |
| `paste_template(target_dir="")` | 剪贴板空 → `ValueError`；目标 `actions/<target_dir>/<剪贴板文件名>` 已存在 → `error` 不覆盖；写盘 → `load()` → 无贡献回滚（同 add）；成功 → `info` |
| `copy_source_templates(source_dir)` | 遍历源码 `actions/` 下 `.py`（跳过 `base.py`/`__init__.py`/`__pycache__`），逐个 `add_template`，保持相对目录 |

- **剪贴板单槽**：`(文件名, bytes)`；复制/剪切覆盖旧值；粘贴不清空（可重复粘）。
- 模板操作粒度 = 文件；某文件含多个步骤类时，`remove_template(任一路径)` 删除整个文件（文件内所有类一并消失，`load()` 后一致）。

## 6. 错误处理汇总

- 未知路径（create_step / remove / copy）→ `ValueError`。
- 剪贴板空（paste）→ `ValueError`。
- 模板文件写入失败 / 导入失败 / 无贡献回滚 / 重名 / 注解非法 → `LogModel.error` + 该模板不生效（不影响其它模板）。
- 全部错误均不抛未预期异常；模型保持可用。

## 7. 测试（模块 `__main__` 冒烟）

- 临时 `.kscp`（`KscpPackage.create_empty()` 内存包）+ 手工写入模板文件字节：
  - 有效模板（`from actions.base import Step` 绝对导入的桩步骤类）
  - 坏语法文件、注解非法类文件、同目录重名文件 → 验证注册表内容与跳过日志。
- `create_step`：子目录路径 / 顶层路径 / 未知路径 `ValueError`。
- `from_format_string`：还原成功 / 非法编码重抛 / 无匹配返回 `None` + 日志。
- 模板操作全链路：`add_template`（成功 + 无贡献回滚）→ `copy_template` + `cut_template`（注册表消失）→ `paste_template`（恢复）→ 重名粘贴报错 → `remove_template`。
- `copy_source_templates` 后 `load()` 成功。
- 冒烟含 `QApplication`（`create_default` 需要）。

## 8. 非目标（YAGNI）

- 不保存步骤实例、不做 `step_list.json` 读写（后续「步骤列表模型」职责）。
- 不做执行引擎（偏移量语义由引擎定义）。
- 不做树 UI（本模型只暴露 `template_paths()`）。
- 不做模板内容编辑 / 改名（后续任务）。
- 不做热重载（`load()` 随时可重跑即刷新）。
