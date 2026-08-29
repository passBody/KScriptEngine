# 变量管理树 + 图片遮罩预览 设计

- 日期：2026-08-28
- 范围：
  - `model/project_variable.py`（小改：加 `description`；`png` 类型全局改名 `image`）
  - `widgets/image_overlay.py`（新：可复用图片遮罩预览）
  - `widgets/resource_tree_widget.py`（加只读选模式 + `pick_resource`；预览改用遮罩；共享 `_ZoomGraphicsView` 外移）
  - `widgets/variable_tree_widget.py`（新：变量管理树 + 编辑卡 + 创建对话框）
  - `widgets/main_widget.py`（接入真实变量管理树）
  - `widgets/__init__.py`（导出）

## 1. 目标

1. 图片预览改为「视图中透明黑色遮罩 + 居中可缩放拖拽」，封装成独立可复用控件（png→image 变量预览、资源树预览共用）。
2. 全局变量管理树 GUI：左树 + 中编辑卡；每种变量类型在视图中有独特显示方式（按类型封装生成 GUI 的函数，预留接口）；可在视图修改变量值；资源类变量只能通过检索工程资源选中后修改。
3. 变量管理树接入主界面切换栏。
4. 创建变量弹对话框：下拉选类型，下拉项含类型描述词（描述加在类型对象上）。
5. 视图无法创建/提交不符合规范的变量（实时校验，禁用提交）。
6. 全过程详细日志写入日志栏。

## 2. 模型改动 `model/project_variable.py`

### 2.1 `VariableType` 加 `description`

- 新类属性 `description: str = ""`（默认空，向后兼容；自定义类型不填则为空）。
- 内置类型填值：
  - `string` → `"文本字符串"`
  - `number` → `"整数或小数"`
  - `image` → `"图片资源（工程 assets 内的 .png/.jpg）"`

### 2.2 `png` 类型全局改名 `image`

- `_PngType` → `_ImageType`，`name = "image"`；`is_resource=True`、`suffixes=(".png",".jpg")` 不变；`normalize`/`is_valid`/`to_actual` 逻辑不变。
- 模块 docstring、`__all__` 无关；冒烟中所有 `"png"` 字面量改 `"image"`（创建、filter、断言）。
- 影响面：`variable_tree.py` 冒烟用 `"png"` 处改 `"image"`；`docs` 无需改（spec 本身用 image）。
- **不保留 `png` 别名**（用户要求全局更名，干净利落）。

无其他模型改动：变量值修改经 `tree.set(path, ProjectVariable.create(type, value, package))` 重建变量实现，不新增 setter。

## 3. 图片遮罩预览 `widgets/image_overlay.py`（新）

### 3.1 共享缩放视图

把 `resource_tree_widget._ZoomGraphicsView`（滚轮缩放 1.25×、`ScrollHandDrag` 拖拽平移、双击 `fit_view`）外移到 `image_overlay.py` 作为共享控件 `_ZoomGraphicsView`。`resource_tree_widget` 删除 `_ImagePreviewDialog` 后不再引用 `_ZoomGraphicsView`，故无需反向 import。

### 3.2 `ImageOverlay(QWidget)`

- 半透明黑色遮罩：`paintEvent` 填 `QColor(0,0,0,160)`；`setFocusPolicy(StrongFocus)`；`installEventFilter` 或重写 `keyPressEvent`（Esc 关闭）。
- 居中放一个 `_ZoomGraphicsView`（带 `QGraphicsPixmapItem`），约占窗口 80%，`showEvent` 调 `fit_view`。
- API：
  - `__init__(self, pixmap: QPixmap, parent: Optional[QWidget] = None)`
  - `show_overlay()`：`setGeometry(parent.rect())` → `raise_()` → `show()` → `setFocus`。
  - `close_overlay()`：`hide()`。
- 交互：滚轮缩放、拖拽平移、双击适配、Esc 关闭、点击遮罩空白处关闭（`mousePressEvent` 命中遮罩本身而非内部 view 时关闭）。
- 底部提示条「滚轮缩放 · 拖拽平移 · 双击适配 · Esc/点击空白 关闭」。

### 3.3 资源树预览改用遮罩

`resource_tree_widget._PreviewPanel._open_image_dialog`：由 `_ImagePreviewDialog(...).exec_()` 改为 `ImageOverlay(self._raw_pixmap, self.window()).show_overlay()`。`_ImagePreviewDialog` 删除。`_ClickableImageLabel` 保留（点击触发遮罩）。

`widgets/__init__.py` 导出 `ImageOverlay`。

## 4. 资源选择器 `widgets/resource_tree_widget.py` 加点

### 4.1 只读选模式

- 构造加 `select_mode: bool = False`；为 True 时：
  - `setSelectionMode(QAbstractItemView.SingleSelection)`（单选）。
  - 不装右键菜单 / 不连复制剪切粘贴删除重命名快捷键（仅保留只读浏览）。
  - 仍可展开/折叠、点选。
- 复用现有 `refresh`/`_fill`/排序逻辑。

### 4.2 `pick_resource`（静态方法）

```
@staticmethod
def pick_resource(package: KscpPackage, suffixes: tuple = (),
                  parent: Optional[QWidget] = None) -> Optional[str]
```

- 弹 `QDialog`（标题「选择资源」，`resize(600,500)`），内嵌一个 `select_mode=True` 的 `ResourceTreeWidget(package)`。
- **后缀过滤**：仅 `suffixes` 匹配的文件可被选中并最终返回；文件夹始终可见（以便展开浏览）；不匹配的文件项 `setHidden` 或置灰不可选。空 `suffixes` 表示不过滤。
- 底部「确认」「取消」；确认时取当前选中项路径，若为文件且通过过滤则返回，否则 None；取消返回 None。
- 双击文件项 = 确认返回该路径（便捷）。

修改 image 变量时：`ResourceTreeWidget.pick_resource(package, var.suffixes, self)`。

## 5. 变量管理树 `widgets/variable_tree_widget.py`（新）

### 5.1 `VariableTreeWidget(QTreeWidget)`

与 `ResourceTreeWidget` 同构（左树），管理 `VariableTree`（`package.read_file("variables.json")` 加载；保存 `package.write_file("variables.json", tree.to_json_bytes())`）。

- 树项：分组用目录图标、变量用文件图标；变量文本旁加类型小标记（如 `名 [image]`）。文件夹在上、文件在下，各自按字符排序（复用资源树 `_fill` 的排序法）。
- 路径角色 `_PATH_ROLE`、`_walk_items`/`_find_item`/`_expanded_paths`/`_selected_paths` 等同资源树。
- 右键菜单：**添加变量**（弹创建对话框）/ **添加组**（输入名）/ **重命名**（F2）/ **删除**（Del）/ **移动**（暂以重命名到新路径实现，YAGNI 拖拽）。
- `currentItemChanged` → 发 `var_selected = pyqtSignal(str)`（路径）。
- `refresh(current_path=None)`：重建树、保留展开/选中、把 `current_path` 设为当前项、驱动编辑卡刷新（同资源树模式）。
- `preview_widget()` 返回缓存的 `VariableEditPanel`。
- 写回：每次 add/set/remove/move 后 `tree` 变更 → `package.write_file("variables.json", tree.to_json_bytes())` → `refresh` → 记日志。

### 5.2 `VariableEditPanel(QStackedWidget)` —— 中编辑卡

`QStackedWidget` 三页：占位(0) / 编辑器(1) / 不支持(2)。

- **类型编辑器注册表**（预留接口）：
  ```
  VAR_EDITORS: Dict[str, Callable[[ProjectVariable, KscpPackage, Callable[[Any], None]], QWidget]] = {}
  register_editor(vtype: str, fn) -> None
  ```
  每个 `fn` 接收（变量、package、`on_changed(value)` 回调），返回一个 QWidget。`on_changed(value)` 在控件值变化时以新值调用，编辑卡据此用 `ProjectVariable.create(type, value, package)` 试建并按 `valid` 实时校验。
- 内置编辑器：
  - `string` → `QLineEdit`；`on_changed(text)`；校验 `isinstance(str) and text != ""`（空串视为非法）。
  - `number` → `QLineEdit` + 校验器；`on_changed(text)`；校验能 `float()` 且非空、非纯 bool 文本。
  - `image` → 缩略图 `QLabel`（点击开 `ImageOverlay`）+ 路径标签 + 「选择资源…」按钮（调 `ResourceTreeWidget.pick_resource(package, var.suffixes, self)`，返回后 `on_changed(path)`）。当前路径为初值。
  - 默认（未注册类型）→ 不支持页「该类型暂不支持可视化编辑，请改用资源选择或其他方式」。
- 顶部显示：变量名 + 类型 + 是否有效标记。
- 底部：「确认」「还原」。**实时校验**：`on_changed` 触发 → 用 `ProjectVariable.create(type, value, package)` 试建（不写入树）→ `valid` 决定「确认」启用/禁用 + 下方红/绿提示（合规：「可保存」；不合规：「值不合规：<原因>」）。**确认仅在 valid 时启用 → 无法提交非法值**。
- 确认 → `tree.set(path, ProjectVariable.create(...))` + 写回 variables.json + `refresh(path)` + 记 `info` 日志。
- 还原 → 重载当前变量值到编辑器。
- 选中分组/无选中 → 占位页「选择一个变量以编辑」。

`widgets/__init__.py` 导出 `VariableTreeWidget`。

### 5.3 `CreateVariableDialog(QDialog)`

放 `variable_tree_widget.py` 内。

- 类型下拉 `QComboBox`：项 = `"%s — %s" % (name, description)`，`description` 取自 `VariableType.description`（经 `ProjectVariable.type_of`）。选中类型时下方动态切换对应编辑器（复用 `VAR_EDITORS`）：用该类型的合理默认值（string→""、number→"0"、image→""）构造一个临时 `ProjectVariable.create(type, default, package)`（可能 invalid）作为编辑器入参；编辑器以 `var.data` 为初值显示，用户编辑经 `on_changed(value)` 回传。
- 名称输入 `QLineEdit`（校验：非空、不含 `/`、不为 `.`/`..`、不与既有重名）。
- 目标分组下拉（可选，默认根；列出现有分组）。
- 实时校验：`on_changed` 最新值 + 名称合法 → `ProjectVariable.create(type, value, package).valid==True` 才启用「创建」+ 下方红/绿提示。
- 创建 → `ProjectVariable.create(type, value, package)`；返回 `(path, var)`；取消 → None。
- 返回值交给 `VariableTreeWidget` 执行 `tree.add(path, var)` + 写回 + 日志。

## 6. 主窗口集成 `widgets/main_widget.py`

- `PlaceholderManagementTree("变量")` → 真实 `VariableManagementTree(package)`：
  ```
  class VariableManagementTree(ManagementTree):
      def __init__(self, package): super().__init__("变量"); self._package=package; self._vtree=None
      def icon(self): return _make_icon("variable")
      def tree_widget(self): 懒建 ResourceTreeWidget→VariableTreeWidget(package)
      def preview_widget(self): 懒建 VariableEditPanel（与树联动）
  ```
- `_open_package` 的 managers 列表把 `PlaceholderManagementTree("变量","variable")` 换成 `VariableManagementTree(package)`；步骤树仍占位。
- 变量树 `var_selected(path)` → 主窗口转发给当前 `VariableEditPanel.load(path)`（或在 `preview_widget` 里直接连树信号到编辑卡）。编辑卡与树同处一个 manager，互连即可。
- 切换到「变量」树时，视图栏显示该编辑卡；与资源树体验一致。

## 7. 日志（item 6）

所有变量操作经 `LogModel.instance()` 记录：

| 事件 | 级别 | 文案 |
|---|---|---|
| 载入 variables.json | INFO | `载入变量树：%d 个变量` |
| 写回 variables.json | INFO | `变量已保存（%d 个变量）` |
| 添加变量 | INFO | `添加变量 %s（%s）` |
| 修改变量 | INFO | `修改变量 %s` |
| 删除变量 | INFO | `删除变量 %s` |
| 重命名/移动 | INFO | `移动变量 %s → %s` |
| 添加组 | INFO | `添加分组 %s` |
| 创建对话框确认 | INFO | `创建变量 %s（%s）` |
| 值不合规被阻止 | WARNING | `变量 %s 值不合规，已阻止` |
| 创建取消 | DEBUG | `创建变量对话框取消` |
| 选资源取消 | DEBUG | `选择资源取消` |

状态栏错误/警告计数随之联动（既有机制，无需改）。

## 8. 验证规则（item 5 落点）

- 创建对话框：类型必选、名称合法、值 `ProjectVariable.create(...).valid==True` 三者皆满足才启用「创建」。
- 编辑卡：`on_changed` → 试建变量 → `valid` 才启用「确认」。
- 资源类（image）：值只能来自 `pick_resource`（不能手输路径），从源头杜绝非法路径；选中的路径必经 `_ImageType.is_valid`（前缀 `assets/`、后缀、存在性）。
- 故**无法通过视图创建/提交不合规变量**。

## 9. 测试

- `python -m model.project_variable`：`png`→`image` 改名后全部断言通过（含 `supported_types` 含 `image`、`is_resource`、`suffixes`、往返）。
- `python -m model.variable_tree`：`"png"`→`"image"` 处改后通过。
- `python -m widgets.image_overlay`：构造 `ImageOverlay`（不 show）、`show_overlay`/`close_overlay` 不抛错（需 QApplication）。
- `python -m widgets.variable_tree_widget`：构造树、注入变量、断言树项数；选变量→编辑卡加载；改 string 值确认→写回；image 变量选资源；创建对话框流程（直接构造、设值、`accept`）。
- `python main.py sample.kscp --check`：退出 0；切到「变量」树渲染编辑卡（需 sample.kscp 含 variables.json 或空树）。

## 10. 不做（YAGNI）

- 不做变量拖拽移动（重命名到新路径即可）。
- 不做 `png` 兼容别名（全局更名）。
- 不做多变量批量编辑。
- 不做变量树多选。
- 不把 `_ZoomGraphicsView` 改公开 API（内部共享即可）。
