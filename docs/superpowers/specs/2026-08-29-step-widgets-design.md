# 步骤卡片 + 步骤列表视图 + 步骤列表管理树 设计

> 日期:2026-08-29
> 前置:`StepList` / `StepListStore`(2026-08-29 已实现,spec §7 明示「删除/重命名组与列表、跨列表移动步骤」留给本 UI 任务)、`Step.enabled`、`Step.info_widget()`、`StepIOWidget`(含 `gen_widget` / `is_valid` / `picker`)、`StepManager`(`template_paths` / `create_step` / `from_format_string`)、`VariableTreeWidget` / `ManagementTree` 接口(`main_widget.py` 的「步骤」占位待替换)。

## §1 目标

在 `@widgets\` 新增三个 GUI 控件并集成进主程序:

1. **`StepCard`(步骤对象卡片)**:搭载 `Step` 模型。顶部显示自定义视图(`info_widget`),下方嵌入输入/输出 GUI(直接编辑 `io` 内部值);背景色随 `step.status` 与 io 校验变化;悬停放大;左上角激活按钮。
2. **`StepListView`(步骤列表视图)**:搭载 `StepList` 模型。水平滚动区域,内部 n 张卡片;滚轮横向滚动;右键菜单支持 添加(头部/尾部/前方/后方,模板树选择)/ 删除 / 复制 / 粘贴 / 剪切。
3. **`StepListTreeWidget`(步骤列表管理树)**:搭载 `StepListStore` 模型。提供 添加组 / 复制 / 粘贴 / 剪切 / 重命名 / 删除 步骤列表;点击列表 → 在视图中显示该列表的 `StepListView`;树中只显示键值。

模型扩展(`StepList` / `StepListStore` 各补方法,见 §3),主窗口集成(替换「步骤」占位,见 §7)。

## §2 概念

* **卡片 / 视图 / 管理树层级**:管理树(左)选列表 → 预览区(中)显示该列表的视图(横排卡片)。管理树操作 `StepListStore`;视图操作其绑定的 `StepList`(即 store 中同一个实例);卡片操作其 `Step`。
* **共享变量树**:步骤卡片内 io 的校验/选择器需要**当前真实变量树**。主窗口加载一棵 `VariableTree` 供「变量管理树」与「步骤列表管理树」共享;`VariableTreeWidget` 增加可选 `tree` 构造参数(缺省保持自加载旧行为),变更后发 `tree_changed` 信号 → 卡片重检颜色。
* **剪贴板**(纯数据,跨列表切换存活):步骤剪贴板 = `List[str]`(格式串);列表/组剪贴板 = `(名, [(相对路径, 是否组, 格式串列表|None)...])`(先序;顶层项相对路径 = 空串)。粘贴时经 `StepManager` 解码重建(列表)或 `add_group` 递归重建(组);顶层重名自动去重 `name(1)`、`name(2)`(与 `VariableTreeWidget._dedup_name` 一致),子树冲突 → 日志 + 警告跳过。**剪切后剪贴板保留**(剪切 = 复制 + 删除,允许多次粘贴)。
* **持久化**(镜像 `variables.json` 模式):打开工程时 `step_list.json` 存在 → `StepListStore.from_json(raw, mgr)`;不存在 → `create_empty` 并写空文件。每次变更 → `package.write_file("step_list.json", store.to_json_bytes())`。
* **状态纯显示**(用户裁定):卡片颜色由 `step.status` + `io.is_valid` 驱动;`status` 由外部(未来执行器)设置,卡片不做任何 `do()` 调用;冒烟直接改 `step.status` 验证颜色。

## §3 模型扩展

### §3.1 `StepList.insert_format_strings(index, fmts, manager)` — `model/step_list.py`

| 项 | 值 |
|---|---|
| 签名 | `insert_format_strings(index: int, fmts: List[str], manager: StepManager) -> None` |
| 行为 | 逐条 `manager.from_format_string` 解码;**先全部解码成功,再统一插入**(事务性:任一条失败不产生部分状态);第 `i` 条插到 `index + i`(保持 `fmts` 顺序);`index` 用 Python `list.insert` 语义(越界钳制、负数回绕) |
| 错误 | 坏条目包装同 `from_format_strings`:`ValueError` 消息带**第 N 条**下标(非法编码 → 「步骤列表第 %d 条格式串无效: %s」;无匹配模板 → 「步骤列表第 %d 条无法还原: 没有可匹配的模板」) |

### §3.2 `StepListStore.remove(path)` — `model/step_list_store.py`

| 项 | 值 |
|---|---|
| 签名 | `remove(path: str) -> None` |
| 行为 | `_norm_path` 归一化;沿路径走到父节点;末段存在(列表**或组**)→ 从父字典移除(组 = 整棵子树,结构保证);不存在 → `FileNotFoundError` |

### §3.3 `StepListStore.rename(path, new_name)` — `model/step_list_store.py`

| 项 | 值 |
|---|---|
| 签名 | `rename(path: str, new_name: str) -> None` |
| 行为 | `new_name` 经 `_validate_name`(非空/无 `/`/非 `.`/`..`,非法 → `ValueError`);`_norm_path` 归一化路径;末段不存在 → `FileNotFoundError`;同父下新名已存在 → `FileExistsError`;成功 → 替换键名,**保持原字典插入位置**(重建父字典,不追加到末尾),值(列表或组子树)不动 |
| 用于 | 列表与组的重命名(组 = 改键名,子树不受影响) |

### §3.4 `StepListStore.walk()` — `model/step_list_store.py`

| 项 | 值 |
|---|---|
| 签名 | `walk() -> List[Tuple[str, bool]]` |
| 行为 | 全部组与列表路径,插入序**先序**(组在前、其子树紧随);每项 = `(路径, 是否为组)`(**含空组**)。管理树数据源——树需要组节点,而 `paths()` 只有叶子 |

## §4 `StepCard` — `widgets/step_card.py`

类:`StepCard(QFrame)`。固定尺寸约 `240 × 340`(宽 240 固定,高 340 固定;内容超高时 io 区压缩)。

**布局**(自上而下):
1. 顶部条:左上**激活按钮**(圆形 `QToolButton`,checkable)+ 步骤名(粗体,右侧留白)。
2. 中部:`step.info_widget(self)` 自定义视图。
3. 底部:`step.io.gen_widget()` 输入输出 GUI(编辑即写回 `io` 数据,复用现有机制)。

**背景色**(`_update_style`,优先级自上而下):

| 条件 | 颜色 |
|---|---|
| `io.is_valid == False`(输入输出 GUI 有不合规的值) | 红 `#e15554`(任何状态优先) |
| `step.status == PENDING`(待运行) | 暗黄 `#d9a83a` |
| `step.status == RUNNING`(运行) | 绿 `#4caf50` |
| `step.status == FINISHED`(运行结束) | 灰 `#bdbdbd` |
| `step.status == ERROR`(运行错误) | 红 `#e15554` |

背景色经 QSS 作用于卡片框架(`background-color` + 同色系边框),白字名号条保持可读。

**激活按钮**:选中(激活)= 绿底白「✓」;未选中(未激活)= 灰底白「✗」。点击翻转 `step.enabled`。未激活时(全部以 QSS 实现,**不使用 opacity 效果**):激活按钮灰底、卡片边框**虚线**灰、步骤名变灰,直观区分。

**选中高亮**:`set_selected(bool)` — 视图管理(点击卡片背景 / 右键锚定),选中卡片边框蓝色 `#3a7bd5`(不影响状态背景色)。

**颜色刷新时机**:① `refresh()`(重建/重绑时全量重检);② io 生成控件的 `textChanged`(QLineEdit 槽);③ 包装 `io.picker`(资源类按钮选择后)。`change_value` 程序化改动不实时触发(仅 `refresh()` 时反映,冒烟走 `refresh()`)。

**状态纯显示**:不做 `do()`;`step.status` 由外部设置后调 `refresh()` 更新颜色。

**信号**:`menu_requested = pyqtSignal(object, object)`(自身, 全局坐标)——卡片右键上下文菜单由视图统一构建,卡片只发信号;滚轮由视图安装事件过滤器转发(卡片内 QLineEdit 未消费的滚轮事件会沿父链上浮到卡片,过滤器统一处理)。

## §5 `StepListView` — `widgets/step_list_view.py`

类:`StepListView(QGraphicsView)`。

**架构**:`QGraphicsScene` 横向排布 `QGraphicsProxyWidget`(每卡一个 `StepCard`);水平滚动条常显;卡片对齐顶部;每卡间距 16;缩放变换原点 = 卡片中心(避免放大时偏移)。

**滚轮**:视图 `wheelEvent` 重写 → 垂直滚轮增量作用于**水平**滚动条;卡片内子控件(如 QLineEdit)滚轮经卡片安装的事件过滤器转发给视图(同一处理)。

**悬停放大**(用户裁定 QGraphicsView 真缩放):`QVariantAnimation` 缩放 proxy `1.0 → 1.06`(`QEasingCurve.OutCubic`,约 160ms),悬停 z 序提升、离开还原;重复进出停止前一个动画再启动。不挤压相邻卡片。

**上下文菜单**:

| 位置 | 菜单项 | 行为 |
|---|---|---|
| 视图空白 | 头部添加… / 尾部添加… / 粘贴 | 添加 → `TemplateChooserDialog`;粘贴 → 尾部追加(剪贴板空则禁用) |
| 卡片 | 添加到此步骤前方… / 添加到此步骤后方… / 复制 / 剪切 / 粘贴 / 删除 | 添加同上,插入到该卡片前后;粘贴到该卡片**后方**;剪切 = 复制 + 删除(剪贴板保留);删除确认后移除 |

**快捷键**:Ctrl+C/X/V 不注册(卡片内文本框焦点冲突,复制文本会被劫持),菜单仅文字提示;F2/Del 属管理树。

添加流程:`TemplateChooserDialog(mgr)` 选中模板路径 → `mgr.create_step(path)`(enabled 默认 True、空 io)→ 插入指定位置 → `refresh()` + 发 `edited` 信号。

复制/剪切:锚定卡片(右键即选中)→ `step.to_format_string()` 收集到步骤剪贴板。粘贴:经 `step_list.insert_format_strings(index, fmts, mgr)` 解码插入(严格,坏串带「第 N 条」报错)。无锚点(右键空白)粘贴 → 尾部。

**空态**:未绑定列表或列表为空 → 场景内提示文字「右键添加步骤（或在左侧管理树选择列表）」。

**API**:`set_list(step_list: Optional[StepList], mgr: Optional[StepManager] = None)` 绑定并重建;`refresh()` 重建卡片(顺序/内容变化时);`refresh_validity()` 仅重检各卡片颜色(变量树变化后调用,**不重建**);`edited = pyqtSignal()`(任何变更步骤的操作后发出,供上层保存);`clipboard: StepClipboard` 构造注入。

**`TemplateChooserDialog(QDialog)`**(同文件):QTreeWidget 按文件夹分组展示 `mgr.template_paths()` 全部已注册模板(组 = 文件夹图标,叶子 = 模板名 + 存路径于 UserRole);仅叶子可确定,选中叶子才启用「添加」;双击叶子或确定返回所选路径;取消返回 `None`。

**`StepClipboard`**(同文件):`steps: Optional[List[str]]`(步骤格式串)+ `items: Optional[Tuple[str, list]]`(列表/组剪贴板 `(名, 三元组列表)`);构造即空。

## §6 `StepListTreeWidget` — `widgets/step_list_tree_widget.py`

类:`StepListTreeWidget(QTreeWidget)`。

**展示**:树数据源 = `store.walk()`(组 + 列表路径,`paths()` 只有叶子)。组 = 文件夹图标,列表 = 橙色方块小图标(沿用 `step_tree_widget._make_step_icon` 风格);文本**只显示键值**(组名/列表名,不含步骤数);每层组在上、列表在下(与变量树一致);`F2` 重命名、`Del` 删除快捷键。

**上下文菜单**(列表与组均支持,与 `VariableTreeWidget` 一致):添加组… / 复制 / 剪切 / 粘贴 / 重命名 / 删除。

| 操作 | 行为 |
|---|---|
| 添加组… | `QInputDialog` 取组名(单段:非空、无 `/`、非 `.`/`..`,非法警告)→ `store.add_group(右键所在组/新名)`;冲突 → 警告框 |
| 复制 | 列表:`(名, [("", False, 格式串), ...])`;组:`(名, 先序三元组列表)`(自身 + 整棵子树) |
| 剪切 | 复制 + `store.remove`(剪贴板保留) |
| 粘贴 | 目标 = 右键所在组(空白 → 根);顶层重名去重 `name(1)`…;组 → `add_group`,列表 → `StepList.from_format_strings` → `add_list`;失败(冲突等)→ 警告框 + 继续其余项 |
| 重命名 | `QInputDialog` → `store.rename`;非法/不存在/冲突 → 警告框;重命名项为当前选中 → 刷新后重新选中新路径 |
| 删除 | 确认框(组 = 整棵子树)→ `store.remove` |

每次变更 → `refresh()` + `store_changed.emit()` + 回调 `on_changed()`(上层保存 `step_list.json`)。

**信号**:`list_selected = pyqtSignal(str)`(点击列表叶子,组/空白不触发);`store_changed = pyqtSignal()`(任何变更后发出,宿主据此处理「当前列表被删/改名」)。

**构造**:`StepListTreeWidget(store, manager, clipboard, on_changed, parent)`;`manager` 用于粘贴时解码;`clipboard` 与步骤列表视图共享(`StepClipboard` 定义于 `step_list_view.py`)。

## §7 主窗口集成 — `main_widget.py`

1. **`StepListManagementTree(ManagementTree)`**(新增子类,替换 `PlaceholderManagementTree("步骤")`,活动栏第 3 位,图标沿用 `_make_icon("step")`,名字「步骤列表」):
   - 构造 `(package, tree)`:`mgr = StepManager(package, tree)` + `mgr.load()`;store 按 §2 持久化规则加载;`clipboard = StepClipboard()`;`_current: Optional[str]` 当前选中列表路径。
   - `tree_widget()` → `StepListTreeWidget(store, mgr, clipboard, on_changed=_save_store)`;连接 `list_selected` → `_on_list_selected`(宿主 `set_list(store.get(path), mgr)`),`store_changed` → `_on_store_changed`(当前列表已被删 → 宿主回占位)。
   - `preview_widget()` → `_StepListHost`(私有容器,同文件):`QStackedWidget` = [占位页(「从左侧选择一个步骤列表」), `StepListView`];构造 `(mgr, clipboard, on_edited=_save_store)`;`set_list(None)` → 占位页。
   - `refresh_cards()`:变量树变化 → 宿主 `refresh_validity()`(仅重检颜色,不重建)。
2. **共享变量树**:`MainWindow._open_package` 加载一次 `VariableTree`(存在 `variables.json` → `from_json(raw, package)`;否则 `create_empty` + 写盘,与 `VariableTreeWidget._load` 旧行为一致);`VariableManagementTree(package, tree)` 与 `StepListManagementTree(package, tree)` 同树。
3. **`VariableTreeWidget` 改造**:构造增加 `tree: Optional[VariableTree] = None`(None → 自加载旧行为;给定 → 使用共享树,不再 `_load`);新增 `tree_changed = pyqtSignal()`,`_save()` 写盘后发出。`VariableManagementTree` 透传 tree。
4. **卡片颜色联动**:`MainWindow` 连接变量树 widget 的 `tree_changed` → `StepListManagementTree.refresh_cards()`(变量树变了,io 校验可能变,颜色跟着变)。

## §8 测试(TDD,冒烟即载体)

**模型扩展冒烟**(红 = 新方法未实现):
- `insert_format_strings`:插入位置(中/越界/负数)/ 顺序保持 / 事务性(坏条目不产生部分插入)/ 第 N 条包装(非法编码 + 无匹配)。
- `remove`:删列表 / 删组(整棵子树,含组内列表)/ 不存在 → `FileNotFoundError`。
- `rename`:改列表 / 改组(子树保留)/ 保持字典插入位置(以内部 `_root` 键序断言)/ 非法名 / 不存在 / 重名冲突。
- `walk`:组在前子树紧随(先序)/ 含空组 / 仅列表时无组项。

**`widgets/step_card.py` 冒烟**:复用 `_StubStep` 桩(含 io 槽);四态颜色断言(直接设 `step.status` + `refresh()` → `styleSheet` 含对应色值);io 非法(空槽)→ 红优先于状态色;激活按钮翻转 `step.enabled` + 按钮样式/边框虚线;`set_selected` 蓝边框;`menu_requested` 信号发出。

**`widgets/step_list_view.py` 冒烟**:包 + 模板 + 变量树 + store 装配(模板字节 `.encode("utf-8")` 约定);`set_list` 后 scene 代理数 = 卡片数;空列表 → 提示项存在;滚轮事件 → 水平滚动条值变化;添加(头部/尾部/前后方,类级补丁 `TemplateChooserDialog.exec_`/`selected_path` 规避真实对话框)、复制 → 剪贴板内容、粘贴 → 插入后方、剪切/删除(补丁 `QMessageBox.question`)全 API 路径;`TemplateChooserDialog` 不 exec 断言树结构(组/叶子来自 `template_paths`,叶子 UserRole = 路径);`edited` 信号;`refresh_validity` 不重建(卡片数不变)。

**`widgets/step_list_tree_widget.py` 冒烟**:树项文本只显示键值;添加组 / 复制 / 粘贴(去重 `name(1)`)/ 剪切 / 重命名 / 删除 全 API 路径(补丁 `QInputDialog.getText` / `QMessageBox.question`);组粘贴递归(整棵子树);`list_selected` 仅叶子触发;`store_changed` + `on_changed` 回调被调。

**`widgets/variable_tree_widget.py` 冒烟(扩展现有)**:缺省构造旧行为不变(现有断言全保留);共享树构造 → `_tree is` 传入实例;`_save` → `tree_changed` 发出。

**`widgets/main_widget.py` 集成冒烟**:临时 `.kscp`(含模板 + variables.json)→ `MainWindow(path)` 构造 → 断言 managers 结构(第 3 位 = `StepListManagementTree`);经树 widget API 添加组/列表 → `step_list.json` 已写盘(store 与包同实例);`list_selected` → 宿主视图出现卡片;变量 `_save` → 卡片 `refresh_validity` 不崩。

**回归**:全量模块冒烟(既有 12 命令 + 新增 3)+ `main.py --check` EXIT=0。

## §9 非目标(本次不做)

* 步骤列表执行器(顺序调用 `all_do_methods()` 的运行时)——状态颜色已就绪,等待执行器任务。
* 卡片拖动排序、跨列表移动步骤、步骤搜索/过滤、列表内步骤顺序拖拽。
* 管理树与视图外的其他 UI 形态(如弹窗式列表编辑)。
