# 日志系统设计（LogModel + LogWidget + 工具栏集成）

- 日期：2026-08-28
- 范围：`model/log_model.py`（数据模型，单例）、`widgets/log_widget.py`（日志窗口）、`widgets/main_widget.py`（布局集成 + 工具栏「窗口」菜单）

## 1. 目标

1. 提供工程级日志数据模型：多级别、可导出、可清空、单例。
2. 提供承载该模型的窗口，显示在主视图下方，支持级别过滤 / 清空 / 导出。
3. 主窗口工具栏加「窗口」下拉菜单，含「显示日志」可勾选项，控制日志栏显隐。

## 2. 约束与惯例

- `model/` 保持 PyQt 无关（与 `PointTimeline` / `VariableTree` / `KscpPackage` 一致）。日志模型的实时通知用**监听器回调**实现，不用 Qt signal。
- 数据模型风格沿用 `PointTimeline`：模块级中文 docstring + 用例、`# ---- 写入 ----` / `# ---- 读取 ----` 分节、类型注解、`clear()`、属性返回拷贝、`__len__`/`__iter__`/`__bool__` 协议。
- 字节 I/O 惯例：导出返回 `bytes`（同 `VariableTree.to_json_bytes`）；文件落盘由控件负责。

## 3. 数据模型 `model/log_model.py`

### 3.1 `LogLevel(Enum)`

- `DEBUG=10`、`INFO=20`、`WARNING=30`、`ERROR=40`、`CRITICAL=50`（数值与 Python `logging` 一致，便于按严重度比较）。
- 静态 `levels() -> List[LogLevel]`：按严重度升序返回全部级别。

### 3.2 `LogEntry`（`NamedTuple`）

- 字段：`time: float`（epoch 秒，源真相）、`level: LogLevel`、`message: str`。
- 不可变；导出/显示时由 `LogModel.format_time` 格式化时间。

### 3.3 `LogModel`（单例）

- 单例：私有 `_instance: Optional[LogModel]`；`instance() -> LogModel` 类方法（首次构造并缓存）。`__init__` 公开但文档标注「请用 `instance()`」；`_reset_instance()` 类方法供测试清空单例。
- 内部状态：`_entries: List[LogEntry]`、`_listeners: List[Callable[[], None]]`。

```
# ---- 写入 ----
log(level, message)                         # 追加一条，time=time.time()
debug / info / warning / error / critical(message)   # 便捷方法
clear()                                      # 清空当前日志
export(fmt="text") -> bytes                 # "text" | "json"
# ---- 读取 ----
entries -> List[LogEntry]                   # 拷贝
__len__ / __iter__ / __bool__
# ---- 监听 ----
add_listener(cb) / remove_listener(cb)      # log/clear 末尾 _notify()
# ---- 静态 ----
format_time(ts) -> str                      # "2026-08-28 14:30:05.123"
levels() -> List[LogLevel]
```

### 3.4 导出格式

- `export("text")`：每行 `"{format_time(t)} {level.name:<8} {message}"`，UTF-8 编码为 bytes。
- `export("json")`：`[{"time": "<fmt>", "level": "<name>", "message": "..."}, ...]`，`json.dumps(..., ensure_ascii=False)` → UTF-8 bytes。
- `time` 字段在 JSON 中也用格式化字符串（人读友好、与文本一致）。

### 3.5 监听器

- `log()` 与 `clear()` 末尾调 `_notify()`：遍历 `_listeners` 副本逐个调用（无参）。
- 监听器异常被捕获并忽略（单条失败不影响其他监听器）。

## 4. 日志窗口 `widgets/log_widget.py` — `LogWidget(QWidget)`

### 4.1 布局

```
┌ 日志                            [级别: 全部▾] [清空] [导出…] ┐
│ <QListWidget，每条一行>                                       │
└────────────────────────────────────────────────────────────────┘
```

- 顶部一行：`QLabel("日志")` + 弹簧 + `QComboBox`（级别过滤）+ `QPushButton("清空")` + `QPushButton("导出…")`。
- 下方：`QListWidget`，等宽字体（如 Consolas），每条文本 `"{fmt} {level:<8} {msg}"`。
- 按级别上色（`item.setForeground`）：DEBUG 灰 `#888`、INFO 默认、WARNING 橙 `#e67e22`、ERROR 红 `#e15554`、CRITICAL 暗红 `#b03a2e`。

### 4.2 行为

- **实时刷新**：构造时 `LogModel.instance().add_listener(self._refresh)`；`_refresh()` 重读 `entries`，重建列表项并应用当前过滤；新条目自动 `scrollToBottom`。
- **级别过滤**：`QComboBox` 项 = `["全部"] + [level.name for level in LogModel.levels()]`。选中「全部」显示所有；选中某级则隐藏其余项（`item.setHidden(True)`）。
- **清空**：调 `model.clear()`（监听器触发 `_refresh` → 列表清空）。
- **导出**：`QFileDialog.getSaveFileName`，过滤器 `"文本日志 (*.log);;JSON (*.json)"`；按所选过滤器调 `model.export("text"/"json")`，写盘；成功/失败各 info/error 一条日志。
- **生命周期**：`closeEvent` 调 `model.remove_listener(self._refresh)` 防监听器泄漏。

### 4.3 导出

`widgets/__init__.py` 导出 `LogWidget`。

## 5. 主窗口集成 `widgets/main_widget.py`

### 5.1 布局

- `_build_project_view` 改为返回一个**纵向 `QSplitter`**：
  - 子 0：现有横向 splitter（活动栏 / 资源树栏 / 视图栏）——抽到 `_build_columns()` 私有方法。
  - 子 1：`LogWidget`（`self._log_widget`）。
- 纵向 splitter：`setChildrenCollapsible(False)`；`setStretchFactor(0, 1)`（上方吸收纵向缩放）、`setStretchFactor(1, 0)`（日志栏高度稳定，仅手动拖动改变）；`setSizes([540, 160])`。
- 字段：`self._log_widget: Optional[LogWidget] = None`。

### 5.2 工具栏「窗口」菜单

- `QToolButton`（文本「窗口」，`setPopupMode(QToolButton.InstantPopup)`）+ `QMenu`，`tb.addWidget` 入工具栏。
- 菜单项：`QAction("显示日志")`，`setCheckable(True)`、默认 `setChecked(True)`（即默认显示日志栏）。
- `toggled` → `self._on_toggle_log(checked)`：`if self._log_widget is not None: self._log_widget.setVisible(checked)`。
- 隐藏时纵向 splitter 自动把高度让给上方视图。

### 5.3 示例日志埋点

- `_on_new`：`info("新建工程")`。
- `_open_file` 成功：`info("打开工程：%s" % path)`；失败：`error("打开失败：%s：%s" % (path, e))`。
- `_on_save`：`info("已保存：%s" % path)`。
- 启动可加一条 `info("KScript 启动")`（可选）。

## 6. 测试

- `model/log_model.py` 的 `__main__` 冒烟：
  - `instance() is instance()`（单例唯一）；`_reset_instance()` 后取到新实例。
  - 5 个便捷方法各追加一条，`len`/`entries` 断言。
  - `clear()` 后 `len == 0`。
  - `export("text")` / `export("json")` 内容断言（含级别名、消息、format_time 格式）。
  - 监听器：`add_listener` 后 `log`/`clear` 各触发一次。
- `python main.py --check` 与 `python main.py sample.kscp --check` 退出 0。
- `python -m widgets.log_widget` 冒烟（可选）：构造 LogWidget、注入几条日志、验证列表项数与过滤。

## 7. 不做（YAGNI）

- 不做日志条目上限 / 滚动暂停跟随 / 多线程安全（当前为单线程 GUI）。
- 模型不提供 `filter_by_level`（过滤由控件客户端完成）。
- 不接入 Python `logging` 框架（自建轻量模型即可）。
