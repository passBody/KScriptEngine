# 步骤列表模型 + 总步骤列表模型 设计

> 日期:2026-08-29
> 前置:步骤基类 `Step.enabled`(是否运行,默认 `True`,2026-08-29 已实现并参与 `to/from_format_string` 的 `"run"` 键)、`Step.to/from_format_string`、`StepManager.from_format_string`(遍历模板注册表还原步骤,持有 tree + package)。

## §1 目标

在 `@model\` 新增两个**纯数据模型**:

1. `StepList`(步骤列表模型):有序 `Step` 对象列表。提供可运行 do 导出、base64 格式串导出/还原、空列表工厂、增删插移。
2. `StepListStore`(总步骤列表模型):管理所有命名 `StepList`,按「组(嵌套)+ 列表」的字典结构存放。提供 JSON 导出/还原、全体可运行 do 整合、添加组、组内添加列表。

两者均不持有 package / tree / manager 引用(除方法参数);UI 集成(步骤列表管理树)不在本次范围。

## §2 概念

* **步骤列表** = 有序 `Step` 对象列表(纯数据,`List[Step]`)。名字**不**存在列表对象内,而存在 store 的字典键上。
* **store 结构** = 嵌套字典:键 = 列表名或组名,值 = `StepList`(叶子)或 `dict`(组)。**根级可同时存在列表与组**(如示例的 `打开软件` 顶层列表 + `清理体力` 顶层组)。
* **组嵌套** = 路径用 `/` 分隔(如 `清理体力/日常/检查体力`),深度不限。路径语义与 `VariableTree` / 步骤管理树 / `StepManager` 一致。
* **JSON 契约**(`step_list.json`,与 `variables.json` 同构)::

    ```json
    {
        "打开软件": ["<base64 格式串>", "..."],
        "清理体力": {
            "检查体力": ["<base64 格式串>", "..."]
        }
    }
    ```

  叶子值 = 格式串**列表**(空列表合法),组值 = 嵌套对象。

## §3 `StepList` — `model/step_list.py`

类:`StepList`。内部 `self._steps: List[Step]`。

| 方法 | 签名 | 行为 |
|---|---|---|
| 追加 | `add(step: Step) -> None` | 追加到末尾 |
| 插入 | `insert(index: int, step: Step) -> None` | Python `list.insert` 语义(越界钳制,负数回绕) |
| 删除 | `remove(index: int) -> None` | 按下标删除;越界抛 `IndexError` |
| 移动 | `move(src: int, dst: int) -> None` | 同列表内移动:`pop(src)` 后 `insert(dst, ...)`;`src == dst` 空操作;越界抛 `IndexError` |
| ①可运行 do 导出 | `do_methods() -> List[Callable[[], int]]` | 按序收集 `step.enabled is True` 的绑定 `step.do`(导出时刻快照,非引用) |
| ②格式串导出 | `to_format_strings() -> List[str]` | `[step.to_format_string() for step in self._steps]` |
| ③格式串还原 | `from_format_strings(fmts: List[str], manager: StepManager) -> "StepList"`(staticmethod) | 逐条 `manager.from_format_string`;坏条目**严格报错**(见 §5) |
| ④空列表 | `create_empty() -> "StepList"`(staticmethod) | 空列表 |
| 读取 | `steps` 属性(拷贝) | 只读视图 |
| 双下 | `__len__` / `__iter__` / `__getitem__(i)` | 代理 `self._steps` |

依赖:`actions.base.Step`(类型)、`model.step_manager.StepManager`(还原)。无循环导入(step_manager 不依赖本模块)。

## §4 `StepListStore` — `model/step_list_store.py`

类:`StepListStore`。内部 `self._root: Dict[str, Union[StepList, dict]]`(嵌套字典,直映 JSON;`dict` 插入序即存储序,Python 3.7+ 保证)。

| 方法 | 签名 | 行为 |
|---|---|---|
| ④添加组 | `add_group(path: str) -> None` | `path` 空串或仅 `/` → `ValueError`;逐段校验名单;父组须存在(祖先为列表 → `ValueError`);已存在且为组 → **幂等返回**;已存在且为列表 → `FileExistsError`;否则建空 `dict` |
| ⑤组内添加列表 | `add_list(path: str, step_list: StepList) -> None` | `path` 无 `/` 时即**顶层列表**(名单直接作路径,如 `打开软件`);`"a/b"` = 组 `a` 下的列表 `b`;`path` 为空串或纯 `/` → `ValueError`(列表必须有名字);逐段校验名单;父组须存在(祖先为列表 → `ValueError`);目标已存在(列表或组)→ `FileExistsError` |
| ①JSON 导出 | `to_json_bytes() -> bytes` | DFS:组 → 嵌套 `dict`,列表 → `[格式串...]`;`json.dumps(root, ensure_ascii=False).encode("utf-8")`,可直接 `package.write_file("step_list.json", ...)` |
| ②JSON 还原 | `from_json(data: JsonInput, manager: StepManager) -> "StepListStore"`(staticmethod) | `data` 三态:`dict` / `str` / `bytes`(与 `VariableTree.from_json` 同款);顶层非 dict、键非法、节点值非 list/dict、格式串坏 → `ValueError`(见 §5) |
| ③全体可运行 do 整合 | `all_do_methods() -> List[Callable[[], int]]` | 按 `dict` 插入序(即 JSON 存储序)深度优先遍历;每遇列表 → `extend(其 do_methods())`;结果 = `[列表1-do1, 列表1-do2, ..., 列表n-don]`,`enabled=False` 的步骤不出现 |
| 空 store | `create_empty() -> "StepListStore"`(staticmethod) | 空根 |
| 读取 | `paths() -> List[str]` | 全部叶子路径(排序;后续管理树数据源) |
| 读取 | `get(path: str) -> StepList` | 按路径取列表;不存在或为组 → `FileNotFoundError` |

依赖:`model.step_list.StepList`、`model.step_manager.StepManager`。无循环导入。

## §5 校验与错误表

名单规则(与 `VariableTree` 一致):单段名非空、不含 `/`、不为 `.`/`..`;多段路径逐段校验。
路径归一化:反斜杠 → 正斜杠、去前导 `/`;含 `.` 或 `..` 段 → `ValueError`(不折叠——刻意严于 `VariableTree._norm_maybe_root` 的折叠语义,与下方错误表一致,冒烟已钉住 `a/./b` → ValueError)。归一化后为空(纯根路径)对 `add_group` 与 `add_list` 均 → `ValueError`(根恒存在、列表必须有名字);「顶层列表」= 无 `/` 的名单直接作路径。

| 情形 | 异常 |
|---|---|
| 名单非法(空段 / `/` / `.` / `..`) | `ValueError` |
| 父组不存在(含祖先路径为列表) | `ValueError` |
| 目标已存在(列表 vs 列表 / 列表 vs 组) | `FileExistsError` |
| 组已存在 | `add_group` 幂等返回 |
| `remove`/`move` 下标越界 | `IndexError`(Python 语义) |
| `from_json`:顶层非 dict / 节点值非 list/dict / 键非法 | `ValueError` |
| `from_format_strings` / `from_json`:格式串编码非法 | `ValueError`,消息带**第 N 条**下标 |
| `from_format_strings` / `from_json`:格式串无匹配模板(`None`) | `ValueError`,消息带**第 N 条**下标(尽管 `StepManager.from_format_string` 已记日志) |

## §6 测试(TDD,冒烟即载体)

**`model/step_list.py` 冒烟**(红 = `ModuleNotFoundError`/`NameError`,新模块未建):

1. `create_empty()`:空;`do_methods()` / `to_format_strings()` / `steps` 均空。
2. `add` / `insert` / `remove` / `move` 顺序与内容断言;`remove(99)` → `IndexError`。
3. `enabled` 过滤:3 步(其一 `enabled=False`)→ `do_methods()` 长度 2 且顺序保持(复用 `_StubStep` 类桩,与 `actions.base` 冒烟同款)。
4. 格式串往返:先 `to_format_strings()` → `from_format_strings(fmts, mgr)` → 再 `to_format_strings()` 完全一致(规范化);还原实例的 `enabled` 保留。
5. 坏条目:非法 base64 串 → `ValueError` 且消息含「第 0 条」;伪造 name 的合法串(无匹配)→ `ValueError`。

**`model/step_list_store.py` 冒烟**(红 = 新模块未建):

1. `create_empty()`:`paths() == []`,`to_json_bytes() == b"{}"`。
2. 结构:顶层 `add_list("打开软件", sl)`;`add_group("清理体力")`;组内 `add_list("清理体力/检查体力", sl2)`;嵌套 `add_group("清理体力/日常")` + `add_list("清理体力/日常/跑图", sl3)`;`paths()` 排序正确;`get()` 取回。
3. 冲突:同名 `add_list` → `FileExistsError`;`add_group("打开软件")` → `FileExistsError`(已是列表);`add_group("清理体力")` 幂等。
4. 非法:`add_list("不存在组/名", ...)` → `ValueError`;`add_group("a//b")` → `ValueError`;`add_group("打开软件/x")`(祖先为列表)→ `ValueError`。
5. JSON 三态往返:`to_json_bytes()` → `from_json(bytes / str / dict)` 三者与原件行为一致,且 `to_json_bytes()` 输出字节稳定(规范化输出)。
6. 结构校验:顶层非 dict → `ValueError`;节点值 `123` → `ValueError`;键含 `/` → `ValueError`;列表内含坏格式串 → `ValueError`(带第 N 条)。
7. `all_do_methods()`:多列表顺序 = `打开软件-do1..do2` → `检查体力-do1..` → `跑图-do1..`;`enabled=False` 步骤被过滤。

**回归**:全量模块冒烟(9 模块)+ `main.py --check` EXIT=0。

## §7 非目标(本次不做)

* 删除 / 重命名组与列表、移动列表、跨列表移动步骤(留给后续「步骤列表管理树」UI 需求)。
* kscp 包内 `step_list.json` 的读写集成(模型只产出 bytes;与 `VariableTree` 模式一致,集成留给 UI 任务)。
* 步骤列表执行器(按 `all_do_methods()` 顺序真正调用 do 的运行时)——本次只导出 do 列表。
