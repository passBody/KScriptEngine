# ProjectVariable 数据模型设计

- 日期：2026-08-26
- 位置：`model/project_variable.py`，并在 `model/__init__.py` 导出
- 状态：已获用户批准

## 目的

描述一个 KScript 工程变量。变量可以访问工程资源（`.kscp` 包）中 `assets/` 目录下的文件。对应 `按键操作.txt` 中的「变量结构」。

## 类型系统与预留接口

抽象基类 `VariableType`，每个类型是一个子类实例，注册到 `ProjectVariable` 的类级注册表 `_TYPES: dict[str, VariableType]`。

```python
class VariableType:
    name: str = ""
    is_resource: bool = False  # 本类型 data 是否为工程资源（如文件路径）；字面值类型为 False
    suffixes: tuple = ()      # 资源类接受的后缀（小写、含点）；非资源为空
    def normalize(self, data): ...                 # 规范 data 存储形式（默认原样）
    def is_valid(self, data, package) -> bool: ...  # 合规判定
    def to_actual(self, data, package): ...         # 取实际数据
```

- `ProjectVariable.register_type(handler)` —— 注册新类型（**预留接口**：新增类型只需子类化 `VariableType` + 注册）。
- `ProjectVariable.supported_types() -> list[str]` —— 已注册类型名（要求 5）。

`package` 经 `TYPE_CHECKING` 仅作类型注解，运行期鸭子类型（只需 `is_file`/`read_file`），避免运行期耦合/循环导入。

## 三种内置类型

| 类型 | data | `is_resource` | `suffixes` | `is_valid` | `to_actual` |
|---|---|---|---|---|---|
| `string` | `str` | `False` | `[]` | `isinstance(data, str)` | 原字符串 |
| `number` | `int`/`float`（排除 `bool`） | `False` | `[]` | `isinstance(data,(int,float)) and not isinstance(data,bool)` | 该数值 |
| `png` | 工程资源路径 `str` | `True` | `['.png','.jpg']` | 规范化后 `startswith("assets/")`、后缀属于 `suffixes`、`package.is_file(path)` 真实存在 | `package.read_file(path)` → 文件字节 |

- png 的 `normalize`：反斜杠→正斜杠、去前导 `/`、折叠 `.`、拒 `..`（与 `KscpPackage` 一致），**存储规范化后路径**，保证往返一致。
- number 严格只接 `int`/`float`；字符串 `"123"` 视为不合规（调用方需先解析）。

## 属性

| 属性 | 含义 |
|---|---|
| `type: str` | 变量类型名 |
| `data: Any` | 变量数据（规范化后存储） |
| `valid: bool` | 创建时经 `is_valid` 判定；不合规为 `False`（对象仍创建） |
| `is_resource: bool` | 是否为资源类变量：`data` 为工程资源（如 png 资源路径）时 `True`，字面值类型 `False`；由类型的 `is_resource` 决定 |
| `suffixes: list[str]` | 资源后缀列表：资源类接受的后缀（如 png 为 `['.png','.jpg']`）；非资源类为 `[]`；由类型的 `suffixes` 决定并用于后缀校验 |

对象持有 `_package` 引用（创建时传入），供 `get_actual_data` 用。

## API

- `ProjectVariable.create(vtype, data, package)` —— 静态生成单个变量（要求 1）。未知类型抛 `ValueError`；不合规不抛错、置 `valid=False`。
- `to_format_string() -> str` —— 提取 `type`+`data` 生成 base64 字符串（要求 2）。
- `ProjectVariable.from_format_string(fmt, package) -> ProjectVariable` —— 反解 base64 拿 `(type,data)`，再 `create`（重新校验）还原对象（要求 3）。
- `get_actual_data()` —— 返回实际/完整数据：string→str、number→数值、png→文件字节（要求 4）。`valid=False` 时抛 `ValueError`。
- `ProjectVariable.supported_types() -> list[str]`（要求 5）。

## base64 格式

`json.dumps({"t": type, "d": data})` → UTF-8 → **urlsafe base64 去填充**（`.rstrip("=")`；解码时 `pad = "="*(-len%4)` 补回）。选 urlsafe+去填充是为让格式化字符串可安全嵌入模板 `{{...}}`（不含 `+ / =`）。

base64 只携带 `type`+`data`；`valid` 不入串，`from_format_string` 经 `create` 重新校验得到。

## 测试

`if __name__ == "__main__"` 冒烟：建包+加 `assets/1.png` → 三类型 `create` 与 `valid` → 非法 png 路径 `valid=False` → `to/from_format_string` 三类型往返 → `get_actual_data` 各类型返回 → 未知类型报错 → 注册自定义类型后 `supported_types` 含它。

## 非目标（YAGNI）

- 不管理「变量名→变量」的映射（那是「变量树」兄弟模型的职责）。
- 不持久化为 variables.json（由变量树模型负责）。
- 不做模板 `{{}}` 解析（由使用方负责）。
