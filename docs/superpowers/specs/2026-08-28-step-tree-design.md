# 步骤管理树 设计说明

- 日期: 2026-08-28
- 状态: 已评审(分节获批)
- 前置: `docs/superpowers/specs/2026-08-28-step-manager-design.md`(步骤管理模型,本 spec 的模型基础;下文简称「模型 spec」)

## 1. 背景与目标

KScript 主窗口左侧活动栏当前有 3 个图标:资源、变量、「步骤」占位(显示「步骤管理树」待实现)。
本需求新增**步骤管理树**:展示工程当前拥有的步骤模板,作为活动栏**第 4 个图标**(用户裁定:
**保留**现有「步骤」占位图标,新树作为第 4 个图标,名称「步骤模板」)。

目标:

- 树展示 `StepManager` 注册的模板(路径 = 文件夹名/类.name,沿用模型 spec §3.2)。
- 可更改步骤模板的**位置**(移动到其他分组)与**组名**(分组重命名)。
- 可**创建**分组(空组在树中可见,为后续模板做组织)。
- 可**删除**步骤模板。
- 右侧视图显示选中步骤模板的信息(名称/描述/分组/输入输出参数),输入输出参数**左右对齐**(用户裁定:**独立两栏**,不按索引配对)。
- **只展示模板,不创建对象**:任何路径不得调用 `create_step`;信息数据源为模板**类**级数据。
- 后续「添加步骤」流程会用这个树选择要创建的步骤对象 —— 本期仅预留选择信号钩子,无消费者。

## 2. 概念

| 术语 | 含义 |
|---|---|
| 模板路径 | `文件夹名/类.name`(顶层文件只有 `name`;如 `"控制流程/示例"`、`"示例"`)。文件夹名可嵌套(如 `"a/b/示例"`) |
| 组 | `actions/` 下的目录(可能为多层);树中的文件夹节点。树显示**全部**包内目录(含空目录),与资源树同款;叶子仅显示已注册模板 |
| 模板文件 | `.kscp/actions/**/*.py`,注册的最小单位是文件内步骤类,但**移动单位是文件**(一个文件可含多个步骤类,一起移动) |
| 模板类 | 注册表 `_registry[路径] = (步骤类, 文件相对路径)` 中的类 |

## 3. 模型扩展(`model/step_manager.py`)

在既有模板操作(模型 spec §5)基础上追加 3 个方法。

### 3.1 `template_class(path: str) -> type`

只读返回路径对应的模板**类**(信息面板数据源;不产出实例)。

- 未知路径 → 抛 `ValueError`(与 `remove_template` 同款文案)。

### 3.2 `move_template(path: str, target_dir: str = "") -> None`

把模板**文件**移动到 `actions/<target_dir>/` 下。

规则:

1. 未知路径 → 抛 `ValueError`。
2. 目标 = `actions/<target_dir>/<原文件名>`;`target_dir` 空串 = 顶层(与 `paste_template` 的 `target_dir` 语义一致)。
3. 目标文件已存在 → `LogModel.error` 报错并**返回**(不覆盖,与 `paste_template` 同语义)。
4. 移动单位是文件:文件内所有步骤类随文件一起移动。
5. 移动后 `load()` 刷新注册表;成功 → `LogModel.info`。
6. 移动后若目标目录内存在**其他文件**的同名步骤类 → 走既有 `load()` 同目录重名跳过规则(后者被跳,日志可见);本方法不做额外处理。

### 3.3 `rename_group(group: str, new_name: str) -> None`

把分组 `actions/<group>/` 整棵子树重命名为 `actions/<new_name>/`。

规则:

1. `new_name` 非法(空串、含 `/`、为 `.`/`..`)→ 抛 `ValueError`。
2. `group` 为空串或包内不存在 `actions/<group>/` 目录 → 抛 `ValueError`。
3. `actions/<new_name>/` 已存在 → `LogModel.error` 报错并**返回**(不合并)。
4. 子树移动(含嵌套组、空目录)→ `KscpPackage.move`;移动后 `load()` 刷新;成功 → `LogModel.info`。
5. 组内所有模板路径同步更新(如 `"a/示例"` → `"新名/示例"`,`"a/b/示例"` → `"新名/b/示例"`)。

### 3.4 `create_group(name: str) -> None`

创建分组 `actions/<name>/`。

规则:

1. `name` 非法(空串、任一段为 `.`/`..` 或空段,如 `"a//b"`、`"/a"`、`"a/"`)→ 抛 `ValueError`。
2. `name` 可为多层组(如 `"a/b"`):父组 `a` 必须已存在,否则抛 `ValueError`(`make_dir` 不建中间目录)。
3. `actions/<name>/` 已存在(文件或目录)→ `LogModel.error` 报错并**返回**(不覆盖)。
4. 成功 → `KscpPackage.make_dir` + `LogModel.info`;不调用 `load()`(空组不影响注册表)。

### 3.5 冒烟测试

`step_manager.py` 的 `__main__` 块追加断言:

- `move_template`:顶层 → 子目录成功(路径变、`is_file` 变);目标文件已存在 → 返回且日志含报错、文件不变;未知路径 → `ValueError`。
- `rename_group`:成功(含嵌套组路径同步);目标组已存在 → 日志报错、原组不变;非法名(`""`、`"a/b"`、`".."`)→ `ValueError`。
- `create_group`:成功(`pkg.is_dir("actions/<name>")` 为真);重名 → 返回且日志含报错;非法名(`""`、`"a/b"`、`".."`)→ `ValueError`。
- `template_class`:返回类(断言 `isinstance(..., type)` 与 `name` 属性);未知路径 → `ValueError`。

## 4. 树 widget(`widgets/step_tree_widget.py`)

仿 `VariableTreeWidget` / `ResourceTreeWidget` 既有模式(自定义上下文菜单、`_PATH_ROLE` 存路径、`refresh()` 保留展开/选中状态)。

### 4.1 `StepTreeWidget(QTreeWidget)`

- 构造 `StepTreeWidget(package)`:内部持有 `StepManager(package, VariableTree.create_empty())`。
  - 展示不需要变量树;仅因 `StepManager` 构造签名要求,传入**内存空树**;绝不写入 `variables.json`、绝不调用 `create_step`。
  - 包内无 `actions/` 目录时自建(与 `create_empty` 预建 `assets/` 同理):`KscpPackage.is_dir("actions")` 只认显式目录与文件后代,空包上为 `False`,不建则树刷新崩溃。
  - **不进 `widgets/__init__.py` 重导出**(循环导入防线:step_manager → actions.base → step_io_widget → 包 `__init__`;直接 `from widgets.step_tree_widget import StepTreeWidget`)。
- 多选:`setSelectionMode(QAbstractItemView.ExtendedSelection)`(与资源/变量树一致)。
- `refresh(current_path=None)`:组节点来自**包目录**(递归 `package.list_dir("actions")`,含空目录),叶子节点来自**注册表**(仅已注册模板);组 = `SP_DirIcon` 文件夹图标,叶子 = 自绘步骤图标;叶子文本 = **`名称 (输入数→输出数)`**(如 `延时 (2→1)`;输入输出数 = `len(cls._signature(cls.input_class))` / `len(cls._signature(cls.output_class))`,与面板同源);保留展开/选中,`current_path` 指定重建后的当前项。
- `step_selected = pyqtSignal(str)`:选中**叶子**时发出完整模板路径(后续「添加步骤」选择器钩子;本期无消费者)。
- 无模板时树仅剩目录结构(右侧面板提示,见 §5)。

### 4.2 操作菜单

**模板叶子右键:**

- **移动到分组…** → 迷你对话框(§4.3)→ `mgr.move_template(path, target)` → `refresh(新路径)` 并选中。
  - 未知路径 `ValueError` → `QMessageBox.warning`;目标文件已存在 → 模型日志报错不覆盖(底部日志栏可见,不弹窗)。
- **删除** → `QMessageBox.question` 确认(支持多选;选中集顶层化,确认文案「确定删除 N 项?」,与资源树一致)→ 逐个 `mgr.remove_template` → `refresh()`。

**组节点右键:**

- **创建组…** → `QInputDialog.getText`(裸名,校验非空、无 `/`、非 `.`/`..`,与变量树同款)→ 在**该组下**创建(`mgr.create_group(该组 + "/" + 名)`,嵌套)→ `refresh(新组路径)` 并选中。已存在 → 模型日志报错,不弹窗。
- **重命名组…** → `QInputDialog.getText`,名称校验同上 → `mgr.rename_group` → `refresh(新组路径)` 并选中。
  - 目标组已存在 → 模型日志报错不合并,不弹窗;非法名 → `QMessageBox.warning`。

**空白区右键:** **创建组…**(顶层组,与资源树「添加组」同思路)。

**快捷键:** `Del` 删除叶子(多选生效);`F2` 仅当当前项为组时触发重命名组。

**非目标(本期不做):** 复制/剪切/粘贴菜单入口(模型已支持,后续「添加步骤」流程需要时再加);添加模板(模型 `add_template`/`copy_source_templates` 已有,导入流程后续单独设计);组删除;拖拽移动。

### 4.3 移动到分组对话框

小对话框(`QDialog`):

- 可编辑 `QComboBox`:首项「(根目录)」,其后列出全部现有分组(包内全部组目录,递归去重、排序);用户可直接输入新组名(隐式创建新组)。
- 确认后返回目标分组串(空串 = 根目录)。

## 5. 信息面板(`StepInfoPanel`)

右侧预览,`QStackedWidget` 两页(仿 `_PreviewPanel` 模式):

- **页 0(占位)**:未选中 / 选中组 / 未知路径 → 「选择一个步骤模板」(居中灰色;选中组显示「（分组）」,与资源树同思路)。
- **页 1(信息页)**,自上而下:
  - 名称:大号加粗。
  - 分组:路径的组部分(顶层显示「根目录」)。
  - 描述:自动换行;为空显示「（无描述）」。
  - IO 区(**独立两栏**):`QHBoxLayout` 左右两栏 —— 左栏表头「输入参数」、右栏表头「输出参数」;每槽一行两个 `QLabel`(字段名固定宽度 + 类型灰色),列内左对齐;数据来自 `cls._signature(cls.input_class)` / `cls._signature(cls.output_class)`(**类级**,零实例创建)。

`load(path)` 为唯一入口:未知路径 → 回占位页。

## 6. 集成(`widgets/main_widget.py`)

- `_make_icon` 新增 kind `"template"`:自绘「模板」图标(橙色方块内三条横线,与占位图标的裸三横线区分)。
- 新增 `StepManagementTree(ManagementTree)`:名称 **「步骤模板」**、专属图标;`tree_widget()` → `StepTreeWidget(package)`、`preview_widget()` → 其信息面板(懒构建缓存,照抄 `ResourceManagementTree`/`VariableManagementTree` 模式)。
- `_open_package` 的 managers 列表:`[资源, 变量, 步骤(占位), 步骤模板]` —— 第 4 个图标。
- 模块 docstring 同步更新(「步骤模板管理树已实现,步骤(列表)管理树仍为占位」)。

## 7. 错误处理汇总

| 场景 | 行为 |
|---|---|
| 未知模板路径(move/remove/template_class) | `ValueError` 抛出;widget 弹 `QMessageBox.warning` |
| 目标文件已存在(move / paste 同款) | 模型 `LogModel.error` + 返回;widget 不弹窗(底部日志可见) |
| 目标组已存在(rename_group) | 模型 `LogModel.error` + 返回 |
| 非法组名 / 空组 / 组不存在(rename_group) | `ValueError` 抛出;widget 弹 `QMessageBox.warning` |
| 创建组:名称非法 | `ValueError` 抛出;widget 弹 `QMessageBox.warning` |
| 创建组:目标组已存在 | 模型 `LogModel.error` + 返回 |
| 移动后类名冲突 | 既有 `load()` 同目录重名跳过规则,日志可见 |
| 删除 | 确认对话框;`remove_template` 未知路径 `ValueError`(正常流程不可达) |

## 8. 测试

- `step_manager.py` 冒烟:§3.4 断言(模型层)。
- `step_tree_widget.py` `__main__` 冒烟(临时 `.kscp` + 模板字节,与既有 widget 冒烟同款):
  - 树结构:组/叶子/嵌套、**空组也显示**、叶子文本 `名称 (in→out)`、组图标为文件夹。
  - 空包(无 `actions/`)构造不崩:树自建 `actions/` 目录。
  - 选中叶子 → 面板信息页(名称/描述/字段签名);选中组/空 → 占位页。
  - 操作驱动 = 直接调 `mgr` 方法 + `tree.refresh()`(冒烟不弹真实对话框,与 `VariableTreeWidget` 冒烟同思路);`mgr.move_template` 后树刷新、路径更新。
  - `step_selected` 信号在叶子选中时发出。
- 回归:`main.py --check` EXIT=0 + 全量模块冒烟(9 命令)。

## 9. 非目标(明确不做)

1. 模板**重命名**(spec 模型 §8 继续有效:模板不可重命名;名称 = 类.name)。
2. 步骤**实例**创建/保存(归未来「步骤列表模型」);本树绝不 `create_step`。
3. 复制/剪切/粘贴菜单入口、添加模板/添加组、组删除、拖拽移动。
4. 树的选择器复用(「添加步骤」流程)—— 本期仅预留 `step_selected` 信号。
5. 热加载:模板文件被外部修改后需重开工程或重载,不做监听。
