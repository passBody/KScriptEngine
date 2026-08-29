# ResourceTreeWidget 设计

- 日期：2026-08-27
- 位置：`widgets/resource_tree_widget.py`，并在 `widgets/__init__.py` 导出
- 状态：已获用户批准（含 Ctrl/Shift 多选）

## 目的

继承 `QTreeWidget`，管理 `KscpPackage` 对象中 `assets/` 目录的资源。支持 Ctrl/Shift 多选、右键上下文菜单（复制/粘贴/剪切/重命名/删除/添加）、预览面板。对应 `按键操作.txt` 中的「全局资源管理树」。

## 构造与显示

`ResourceTreeWidget(package: KscpPackage, parent=None)`。
- 不可见根 = `assets`；顶层项 = `package.list_dir("assets")` 子项，分组递归。项 `data(UserRole)` 存全路径 `assets/...`。
- `ExtendedSelection` → Ctrl/Shift 多选。目录/文件图标用 `QStyle.SP_DirIcon`/`SP_FileIcon`；单列、隐藏表头。刷新保留展开/选中。

## 上下文菜单（右击背景或项）

`itemAt(pos)` → `path`（None=背景）；若项不在当前选中集则仅选该项。`context_dir` = 分组路径 / 文件父路径 / `assets`（背景）。选中集「顶层化」（去掉被另一选中项包含的子项）后作为操作对象。

| 操作 | 快捷键 | 激活 | 行为 |
|---|---|---|---|
| 复制 | Ctrl+C | 选中≥1 | `clipboard=(paths,"copy")`，粘贴后保留 |
| 剪切 | Ctrl+X | 选中≥1 | `clipboard=(paths,"cut")`，粘贴后清除 |
| 粘贴 | Ctrl+V | clipboard 非空 | 粘入 `context_dir`，逐项去重 |
| 重命名 | F2 | 选中恰1 | 弹输入框 → `package.move`（同父去重） |
| 删除 | Del | 选中≥1 | `package.remove`（组递归删） |
| 添加 | — | 始终 | 子菜单：添加文件…（`QFileDialog`→`add_file_from_local`）/ 添加组…（`make_dir`），均去重 |

**解读说明**：原描述仅限定删除/复制为「右击项才激活」、其余「针对根目录生效」。剪切/重命名作用于具体项才合理，故我将其设为「选中≥1（重命名恰1）」；粘贴/添加作用于 `context_dir`。符合文件管理器直觉。

## 粘贴去重

目标名若已存在于 `context_dir`，扩展名前插 `(k)`：`1.txt`→`1(1).txt`；无扩展→`name(1)`，递增直到不重。粘贴 `1.txt` 三次 → `1(1).txt`、`1(2).txt`、`1(3).txt`（原 `1.txt` 不动）。

## 复制/剪切/粘贴

- 复制=复制（文件 `read_file`+`add_file`；组递归 `read`+`add`/`make_dir`，含空子目录）。
- 剪切=移动（`package.move`，按去重新名）。复制粘贴后保留 clipboard；剪切粘贴后清除。

## 预览（req 3）

`preview_widget() -> QWidget`：缓存 `QStackedWidget`（占位/图片 `QLabel`/只读 `QTextEdit`）。`currentItemChanged` 时更新：png/jpg 等 → `QPixmap.loadFromData` 按比例缩放适配（含 resize 重缩）；文本（utf-8 可解码）→ 只读文本；二进制 → 「（二进制，无法预览）」+大小；目录/无 → 「（目录）」/「（无预览）」。

## 信号

`path_selected(str)`——选中当前项时发射，供主界面左侧面板等外部使用。

## 测试

冒烟：建 `KscpPackage`（png/txt/bin/嵌套中文组）→ 构造树 → 断言显示 → `_dedup_name`/`_copy_resource` → 复制+三次粘贴得 `1(1..3).png` → 剪切移动且 clipboard 清除 → 重命名/删除/添加组 → 预览 png/文本/二进制/目录各态。

## 非目标（YAGNI）

- 不管理根 JSON（`step_list.json`/`variables.json`）。
- 不做串内插值/计算。
- 完整「树资源管理器」即本控件 + 后续主界面集成。
