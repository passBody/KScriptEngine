# VariableTree 数据模型设计

- 日期：2026-08-27
- 位置：`model/variable_tree.py`，并在 `model/__init__.py` 导出
- 状态：已获用户批准

## 目的

管理一个工程中的所有 `ProjectVariable`，支持添加、修改、删除、移动、查询，并在对象与 `variables.json` 之间往返转换。对应 `按键操作.txt` 中的「全局变量树」。

## JSON 形态

`variables.json` 是嵌套字典；**字符串值=叶子变量**（`ProjectVariable.to_format_string()` 的 base64），**字典值=分组**（递归子树）。无保留关键字（`循环系列` 只是示例分组名）::

    {
        "变量名1": "<base64 格式串>",
        "循环系列": { "变量名2": "<base64 格式串>" }
    }

## 内存表示（扁平路径，对齐 `KscpPackage`）

- `_vars: dict[str, ProjectVariable]` —— 路径 → 变量
- `_groups: set[str]` —— 显式空分组；含变量的分组由路径前缀隐含
- 路径：`/` 为分组分隔符；名字不得含 `/`、不得为空、不得为 `.`/`..`（与 `KscpPackage`/`ProjectVariable.png` 同款小归一化，各自私有，保持解耦）

## 生命周期 / IO

- `VariableTree()` —— 空树。
- 类方法 `from_json(data, package) -> VariableTree` —— **要求 1 + 要求3-入**。`data` 为 `str | dict | bytes`（bytes 即 `KscpPackage.read_file` 返回类型）。遍历嵌套字典：str→叶子（`ProjectVariable.from_format_string(value, package)` 解码并按 `package` 重新校验 png），dict→分组（递归；空 `{}` 登记为显式空分组）。
- 类方法 `create_empty() -> VariableTree` —— **要求 2**。无 package。
- `to_json_bytes() -> bytes` —— **要求3-出**。返回 UTF-8 JSON 字节串，可直接 `package.write_file("variables.json", tree.to_json_bytes())`。

## 操作（添加/修改/删除/移动/查询）

树接收**已创建的 `ProjectVariable`**（纯容器，不持有 package；变量创建与合规校验由 `ProjectVariable.create` 负责）。

读：`get(path) -> ProjectVariable`（查询）、`exists`、`is_variable`、`is_group`、`list_dir(path='/')`、`variables`(路径列表)、`groups`、`items()`。
写：
- `add(path, var)`（添加；已存在抛 `FileExistsError`）
- `set(path, var)`（修改；upsert，分组路径抛 `ValueError`）
- `add_group(path)`（空分组，幂等）
- `remove(path)`（删除；变量或整棵子树）
- `move(src, dst)`（移动；变量或分组子树，前缀改写）

不变量：任一路径要么是变量、要么是分组、要么空；变量与分组互不为祖先后代（`_assert_placeable` + 存在性检查保证）。

## 筛选器（要求 4）

- `filter_by_type(vtype) -> VariableTree` —— 返回**同类型对象**，只含 `var.type == vtype` 的变量，保留各自原路径（分组按需隐含，空分组丢弃）。未知类型抛 `ValueError`。无 package；可 `to_json_bytes`/`get`/`list_dir`。

## 错误处理 / 往返

标准异常（`FileNotFoundError`/`FileExistsError`/`ValueError`/`TypeError`），与 `KscpPackage` 一致。`__eq__` 比较 `_vars` 与 `_all_groups()`（显式+隐含，规范化），不受冗余 `_groups` 条目影响；`to_json_bytes` 输出同样规范化。

资源树往返：`tree.to_json_bytes()`(bytes) → `package.write_file("variables.json", …)` → `package.read_file("variables.json")`(bytes) → `VariableTree.from_json(bytes, package)`。

## 测试

`if __name__=='__main__'` 冒烟：建树→加变量+嵌套分组（含中文）→`to_json_bytes`/`from_json`(bytes/str/dict) 往返→经 `KscpPackage` 读写往返→`move`/`remove`/`add_group`→`filter_by_type`（png 子集可 `get`/`to_json_bytes`）→非法 JSON/越界路径报错。

## 非目标（YAGNI）

- 不创建/校验变量（`ProjectVariable.create` 的职责）。
- 不解释「循环系列」的循环语义（由更高层模型负责）。
- 不做模板 `{{}}` 解析。
