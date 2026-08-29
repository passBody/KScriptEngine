# KscpPackage 数据模型设计

- 日期：2026-08-26
- 位置：`model/kscp_package.py`，并在 `model/__init__.py` 导出
- 状态：已获用户批准

## 目的

KScript 的工程文件 `.kscp` 是一个压缩包，根目录存放多个 JSON（`step_list.json`、`variables.json` 等）及其余资源目录（`assets/...`）。本模型负责管理这个压缩包的**目录结构**——对文件进行访问、删除、修改、移动、添加。

## 职责边界（已确认）

本模型是**纯资源树**：把所有文件（含两个根 JSON）当作不透明字节流处理，**不**解析 JSON 内容。`step_list.json` 的步骤语义、`variables.json` 的变量语义，由各自的兄弟数据模型承担。对应 `按键操作.txt` 中的「全局资源树」角色。

## 格式模型

- `.kscp` 即 ZIP 归档，使用 `zipfile` + `ZIP_DEFLATED`。
- 文件名采用正斜杠、UTF-8 编码（支持 `音乐` 等中文目录）。zipfile 会自动置位 UTF-8 标志位，往返无损。
- 空目录以「以 `/` 结尾、内容为空」的条目存储，读回时用 `ZipInfo.is_dir()` 识别。

## 内存表示（方案 A：扁平路径→字节）

- `_files: dict[str, bytes]` —— 归一化路径 → 文件内容。
- `_dirs: set[str]` —— 显式空目录的归一化路径（不带尾随 `/`）。含文件的目录由文件路径前缀派生，无需显式记录；此集合仅用于让空目录能往返存活。

### 路径归一化

`_normalize(rel_path) -> str`：反斜杠→正斜杠；去前导 `/`；折叠 `.` 段；**拒绝 `..`**（防止越出根目录，抛 `ValueError`）；统一存正斜杠、无尾随斜杠（目录亦然）。

## 生命周期（满足要求 2、3）

- `KscpPackage()` —— 空包。
- 类方法 `from_kscp(path) -> KscpPackage` —— 打开 `.kscp`(zip)，读全部条目：目录条目入 `_dirs`，文件条目入 `_files`。**通过 .kscp 生成对象。**
- `save(path)` —— 原子写入（临时文件 + `os.replace`），条目按名排序保证确定性输出。**通过对象生成 .kscp。**

## API

### 生命周期 / IO
| 成员 | 作用 |
| --- | --- |
| `KscpPackage()` | 构造空包 |
| `classmethod from_kscp(path)` | 从 `.kscp` 文件载入 |
| `save(path)` | 写出 `.kscp` 文件（原子写入） |

### 读
| 成员 | 作用 | 失败 |
| --- | --- | --- |
| `read_file(path) -> bytes` | 访问文件内容（访问） | 缺失抛 `FileNotFoundError` |
| `exists(path) -> bool` | 文件或目录是否存在 | — |
| `is_file(path)` / `is_dir(path)` | 判定 | — |
| `list_dir(path='/') -> list[str]` | 直系子项名（文件+子目录） | 路径非目录抛 `ValueError` |
| `files` 属性 / `dirs` 属性 | 全部文件路径 / 全部目录路径 | — |

### 写（变更）
| 成员 | 作用 | 失败 |
| --- | --- | --- |
| `add_file(path, data)` | 添加文件（添加） | 已存在抛 `FileExistsError` |
| `write_file(path, data)` | upsert：存在覆盖、不存在新增（修改/添加） | — |
| `make_dir(path)` | 创建空目录 | 已是文件抛 `FileExistsError` |
| `remove(path)` | 删除：文件删文件，目录递归删整棵子树（删除） | 缺失抛 `FileNotFoundError` |
| `move(src, dst)` | 移动：文件重命名；目录则把 `src/` 下全部条目改写到 `dst/`（含显式目录条目）（移动） | `src` 缺失或 `dst` 已存在抛错 |

### 双下方法
`__contains__(path)`、`__len__()`（文件数）、`__iter__()`（遍历文件路径）、`__repr__()`。

## 错误处理

沿用标准异常：`FileNotFoundError`、`FileExistsError`、`ValueError`（坏路径/越界/类型不符），与 `pathlib`/`shutil` 一致。

## 测试

项目当前无测试目录/框架（`PointTimeline` 亦无测试文件），故不新增测试基础设施。在模块 `if __name__ == '__main__'` 下放一段往返冒烟演示：建包 → 加文件 + 中文目录 → 目录级 `move` → `save` → `from_kscp` 重载 → 断言内容与结构一致。与现有项目「直接跑 Python」习惯一致。

## 非目标（YAGNI）

- 不解析/校验 `step_list.json`、`variables.json` 的 JSON 内容。
- 不做并发控制、不增量读写（全文载入内存后整体写回）。
- 不绑定 `.kscp` 扩展名（`save` 写 zip 到给定路径，由调用方命名）。
