# 日志系统 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给 KScript 加全局日志数据模型（单例、5 级、可清空、可导出 text/json）+ 承载它的日志窗口（显示在视图下方，带级别过滤/清空/导出）+ 主窗口工具栏「窗口」菜单的「显示日志」开关。

**Architecture:** `model/log_model.py` 为 PyQt 无关的单例数据模型，用监听器回调通知变更；`widgets/log_widget.py` 的 `LogWidget` 注册监听器实时刷新 QListWidget；`widgets/main_widget.py` 把现有横向 splitter 与 LogWidget 包进纵向 splitter，工具栏加「窗口」下拉菜单控制日志栏显隐。

**Tech Stack:** Python 3 + PyQt5；无 git（不提交，用运行验证替代）；冒烟测试写在各模块 `__main__`，用 `python -m <module>` 运行。

**约定适配：** 本仓库非 git 仓库，故每个任务的「提交」步骤一律替换为「运行冒烟/自检验证」。冒烟测试即各文件 `__main__` 中的 assert 块。

---

## 文件结构

- 创建 `model/log_model.py`：`LogLevel` 枚举、`LogEntry` 命名元组、`LogModel` 单例（log/clear/export/entries/listener/format_time）+ `__main__` 冒烟。
- 修改 `model/__init__.py`：导出 `LogEntry, LogLevel, LogModel`。
- 创建 `widgets/log_widget.py`：`LogWidget(QWidget)`（列表 + 过滤 + 清空 + 导出，监听刷新）+ `__main__` 冒烟。
- 修改 `widgets/__init__.py`：导出 `LogWidget`。
- 修改 `widgets/main_widget.py`：抽 `_build_columns()`；`_build_project_view` 改返纵向 splitter（含 LogWidget）；`_build_toolbar` 加「窗口」菜单 + 「显示日志」可勾选项；`_on_toggle_log`；`_on_new/_open_file/_on_save` 埋点日志；`__init__` 启动日志 + `_log_widget` 字段。

---

### Task 1: 日志数据模型 `model/log_model.py`

**Files:**
- Create: `model/log_model.py`

- [ ] **Step 1: 写冒烟测试（先红）——建文件，含桩类 + `__main__` 断言**

把以下内容写入 `model/log_model.py`（`LogModel`/`LogLevel`/`LogEntry` 仅留桩，冒烟引用完整 API）：

```python
# -*- coding: utf-8 -*-
"""日志数据模型（单例）。"""
from __future__ import annotations
from typing import Callable, List, NamedTuple, Optional
from enum import Enum


class LogLevel(Enum):
    DEBUG = 10
    INFO = 20
    WARNING = 30
    ERROR = 40
    CRITICAL = 50


class LogEntry(NamedTuple):
    time: float
    level: LogLevel
    message: str


class LogModel:
    _instance: Optional["LogModel"] = None

    def __init__(self) -> None:
        self._entries: List[LogEntry] = []
        self._listeners: List[Callable[[], None]] = []


if __name__ == "__main__":
    import json as _j
    LogModel._reset_instance()
    a = LogModel.instance()
    b = LogModel.instance()
    assert a is b
    a.debug("d"); a.info("i"); a.warning("w"); a.error("e"); a.critical("c")
    assert len(a) == 5
    assert [e.level for e in a.entries] == [
        LogLevel.DEBUG, LogLevel.INFO, LogLevel.WARNING, LogLevel.ERROR, LogLevel.CRITICAL]
    assert a.entries[0].message == "d"
    assert LogModel.format_time(0).startswith("1970") and LogModel.format_time(0).endswith(".000")
    txt = a.export("text")
    assert b"DEBUG" in txt and b"CRITICAL" in txt
    obj = _j.loads(a.export("json"))
    assert len(obj) == 5
    assert obj[1]["level"] == "INFO" and obj[1]["message"] == "i"
    assert obj[4]["level"] == "CRITICAL"
    fired = []
    def cb():
        fired.append("x")
    a.add_listener(cb)
    a.info("again")
    assert len(a) == 6 and fired == ["x"]
    a.clear()
    assert len(a) == 0 and fired == ["x", "x"]
    a.remove_listener(cb)
    a.info("no notify")
    assert len(a) == 1 and fired == ["x", "x"]
    print("LogModel smoke OK")
```

- [ ] **Step 2: 运行冒烟，确认失败**

Run: `python -m model.log_model`
Expected: FAIL（`AttributeError: ... 'LogModel' has no attribute '_reset_instance'` / `instance` 等尚未实现）。

- [ ] **Step 3: 实现 `LogLevel` / `LogEntry` / `LogModel`（替换桩类，保留 `__main__` 不变）**

把文件顶部（docstring 之后、`if __name__` 之前）替换为以下完整实现：

```python
# -*- coding: utf-8 -*-
"""
日志数据模型（单例）
==================

:class:`LogModel` 是 KScript 的全局日志模型（单例，经 :meth:`LogModel.instance` 取唯一
实例）。支持 5 个级别（DEBUG/INFO/WARNING/ERROR/CRITICAL）、追加日志、清空、按文本/JSON
导出，并通过监听器回调通知变更（保持 PyQt 无关）。

基本用法
--------
::

    from model import LogModel, LogLevel

    log = LogModel.instance()
    log.info("工程已打开")
    log.error("打开失败：%s" % path)
    log.add_listener(refresh_ui)        # 变更时回调
    data = log.export("text")           # -> bytes
"""

from __future__ import annotations

import json
import time
from enum import Enum
from typing import Callable, List, NamedTuple, Optional


class LogLevel(Enum):
    """日志级别（数值与 Python ``logging`` 一致，便于按严重度比较）。"""
    DEBUG = 10
    INFO = 20
    WARNING = 30
    ERROR = 40
    CRITICAL = 50

    @staticmethod
    def levels() -> List["LogLevel"]:
        """按严重度升序返回全部级别。"""
        return sorted(LogLevel, key=lambda lv: lv.value)


class LogEntry(NamedTuple):
    """一条日志：时间戳（epoch 秒）、级别、消息。"""
    time: float
    level: LogLevel
    message: str


class LogModel:
    """全局日志模型（单例）。请用 :meth:`instance` 取唯一实例。"""

    _instance: Optional["LogModel"] = None

    def __init__(self) -> None:
        self._entries: List[LogEntry] = []
        self._listeners: List[Callable[[], None]] = []

    # ---- 单例 ----
    @classmethod
    def instance(cls) -> "LogModel":
        """返回全局唯一实例（首次调用时构造）。"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def _reset_instance(cls) -> None:
        """清空单例（仅供测试）。"""
        cls._instance = None

    # ---- 写入 ----
    def log(self, level: LogLevel, message: str) -> None:
        """追加一条日志，时间戳取当前 epoch 秒。"""
        self._entries.append(LogEntry(time.time(), level, message))
        self._notify()

    def debug(self, message: str) -> None:
        self.log(LogLevel.DEBUG, message)

    def info(self, message: str) -> None:
        self.log(LogLevel.INFO, message)

    def warning(self, message: str) -> None:
        self.log(LogLevel.WARNING, message)

    def error(self, message: str) -> None:
        self.log(LogLevel.ERROR, message)

    def critical(self, message: str) -> None:
        self.log(LogLevel.CRITICAL, message)

    def clear(self) -> None:
        """清空当前日志。"""
        self._entries.clear()
        self._notify()

    def export(self, fmt: str = "text") -> bytes:
        """导出为 ``bytes``：``"text"`` 每行一条可读日志；``"json"`` 结构化列表。"""
        if fmt == "json":
            data = [{"time": self.format_time(e.time),
                     "level": e.level.name, "message": e.message}
                    for e in self._entries]
            return json.dumps(data, ensure_ascii=False).encode("utf-8")
        lines = ["%s %-8s %s" % (self.format_time(e.time),
                                 e.level.name, e.message) for e in self._entries]
        return "\n".join(lines).encode("utf-8")

    # ---- 读取 ----
    @property
    def entries(self) -> List[LogEntry]:
        """所有日志条目（拷贝，按记录顺序）。"""
        return list(self._entries)

    def __len__(self) -> int:
        return len(self._entries)

    def __iter__(self):
        return iter(self._entries)

    def __bool__(self) -> bool:
        return bool(self._entries)

    # ---- 监听 ----
    def add_listener(self, cb: Callable[[], None]) -> None:
        """注册变更监听器；log/clear 末尾回调（无参）。"""
        self._listeners.append(cb)

    def remove_listener(self, cb: Callable[[], None]) -> None:
        """移除监听器。"""
        if cb in self._listeners:
            self._listeners.remove(cb)

    def _notify(self) -> None:
        for cb in list(self._listeners):
            try:
                cb()
            except Exception:
                pass

    # ---- 静态 ----
    @staticmethod
    def format_time(ts: float) -> str:
        """``epoch 秒 -> "YYYY-MM-DD HH:MM:SS.fff"``。"""
        t = time.localtime(ts)
        return "%s.%03d" % (time.strftime("%Y-%m-%d %H:%M:%S", t),
                            int((ts - int(ts)) * 1000))
```

- [ ] **Step 4: 运行冒烟，确认通过**

Run: `python -m model.log_model`
Expected: 输出 `LogModel smoke OK`，退出码 0。

---

### Task 2: 导出日志模型符号 `model/__init__.py`

**Files:**
- Modify: `model/__init__.py`

- [ ] **Step 1: 加导入与 `__all__`**

把 `model/__init__.py` 替换为：

```python
# -*- coding: utf-8 -*-
"""model 子包：数据结构。"""
from .point_timeline import PointTimeline
from .kscp_package import KscpPackage
from .project_variable import ProjectVariable, VariableType
from .variable_tree import VariableTree
from .log_model import LogEntry, LogLevel, LogModel

__all__ = [
    "PointTimeline",
    "KscpPackage",
    "ProjectVariable",
    "VariableType",
    "VariableTree",
    "LogEntry",
    "LogLevel",
    "LogModel",
]
```

- [ ] **Step 2: 验证导入**

Run: `python -c "from model import LogModel, LogLevel, LogEntry; print('ok')"`
Expected: 输出 `ok`，退出码 0。

---

### Task 3: 日志窗口 `widgets/log_widget.py`

**Files:**
- Create: `widgets/log_widget.py`

- [ ] **Step 1: 写完整模块（类 + `__main__` 冒烟）**

把以下内容写入 `widgets/log_widget.py`：

```python
# -*- coding: utf-8 -*-
"""
日志窗口（GUI 控件）
==================

:class:`LogWidget` 承载 :class:`model.log_model.LogModel`（单例），以列表形式显示日志，
支持级别过滤、清空、导出，监听模型变更实时刷新。

基本用法
--------
::

    from PyQt5.QtWidgets import QApplication
    from widgets import LogWidget
    from model import LogModel

    app = QApplication([])
    w = LogWidget()
    w.show()
    LogModel.instance().info("启动完成")
    app.exec_()
"""

from __future__ import annotations

from typing import Optional

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QFont
from PyQt5.QtWidgets import (
    QComboBox, QFileDialog, QHBoxLayout, QLabel, QListWidget,
    QListWidgetItem, QPushButton, QVBoxLayout, QWidget,
)

from model.log_model import LogEntry, LogLevel, LogModel

__all__ = ["LogWidget"]

_LEVEL_COLOR = {
    LogLevel.DEBUG: QColor("#888888"),
    LogLevel.INFO: QColor("#333333"),
    LogLevel.WARNING: QColor("#e67e22"),
    LogLevel.ERROR: QColor("#e15554"),
    LogLevel.CRITICAL: QColor("#b03a2e"),
}


class LogWidget(QWidget):
    """承载 LogModel 的日志窗口：列表 + 级别过滤 + 清空 + 导出。"""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._model = LogModel.instance()
        self._filter: Optional[LogLevel] = None     # None = 全部

        bar = QHBoxLayout()
        bar.setContentsMargins(6, 4, 6, 4)
        title = QLabel("日志")
        title.setStyleSheet("font-weight:bold;")
        bar.addWidget(title)
        bar.addStretch()
        self._combo = QComboBox()
        self._combo.addItem("全部")
        for lv in LogLevel.levels():
            self._combo.addItem(lv.name, lv)
        self._combo.currentIndexChanged.connect(self._on_filter)
        bar.addWidget(self._combo)
        self._btn_clear = QPushButton("清空")
        self._btn_clear.clicked.connect(self._on_clear)
        bar.addWidget(self._btn_clear)
        self._btn_export = QPushButton("导出…")
        self._btn_export.clicked.connect(self._on_export)
        bar.addWidget(self._btn_export)

        self._list = QListWidget()
        self._list.setFont(QFont("Consolas", 9))
        self._list.setUniformItemSizes(True)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addLayout(bar)
        lay.addWidget(self._list, 1)

        self._model.add_listener(self._refresh)
        self._refresh()

    # ---- 刷新 ----
    def _refresh(self) -> None:
        self._list.clear()
        for e in self._model.entries:
            self._add_item(e)
        self._list.scrollToBottom()

    def _add_item(self, e: LogEntry) -> None:
        text = "%s %-8s %s" % (LogModel.format_time(e.time), e.level.name, e.message)
        item = QListWidgetItem(text)
        item.setForeground(_LEVEL_COLOR.get(e.level, QColor("#333333")))
        if self._filter is not None and e.level != self._filter:
            item.setHidden(True)
        self._list.addItem(item)

    # ---- 控件回调 ----
    def _on_filter(self, _idx: int) -> None:
        self._filter = self._combo.currentData()
        self._refresh()

    def _on_clear(self) -> None:
        self._model.clear()        # 监听器触发 _refresh

    def _on_export(self) -> None:
        path, filt = QFileDialog.getSaveFileName(
            self, "导出日志", "kscript.log",
            "文本日志 (*.log);;JSON (*.json)")
        if not path:
            return
        fmt = "json" if filt.startswith("JSON") else "text"
        try:
            with open(path, "wb") as f:
                f.write(self._model.export(fmt))
            self._model.info("日志已导出：%s" % path)
        except OSError as e:
            self._model.error("导出失败：%s" % e)

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt 命名)
        self._model.remove_listener(self._refresh)
        super().closeEvent(event)


if __name__ == "__main__":
    import sys
    from PyQt5.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(sys.argv)
    LogModel._reset_instance()
    w = LogWidget()
    m = LogModel.instance()
    m.info("a"); m.debug("b"); m.error("c")
    assert w._list.count() == 3
    # 过滤到 ERROR
    w._combo.setCurrentIndex(1 + LogLevel.levels().index(LogLevel.ERROR))
    visible = [w._list.item(i) for i in range(w._list.count())
               if not w._list.item(i).isHidden()]
    assert len(visible) == 1 and "ERROR" in visible[0].text()
    # 全部
    w._combo.setCurrentIndex(0)
    assert all(not w._list.item(i).isHidden() for i in range(w._list.count()))
    # 清空
    w._btn_clear.click()
    assert w._list.count() == 0
    print("LogWidget smoke OK")
```

- [ ] **Step 2: 运行冒烟，确认通过**

Run: `python -m widgets.log_widget 2>&1 | grep -v "RuntimeWarning\|not package"`
Expected: 输出 `LogWidget smoke OK`（runpy 警告已过滤），退出码 0。

---

### Task 4: 导出 LogWidget `widgets/__init__.py`

**Files:**
- Modify: `widgets/__init__.py`

- [ ] **Step 1: 加导入与 `__all__`**

把 `widgets/__init__.py` 替换为：

```python
from .step_io_widget import StepIOWidget
from .resource_tree_widget import ResourceTreeWidget
from .log_widget import LogWidget

__all__ = ["StepIOWidget", "ResourceTreeWidget", "LogWidget"]
```

- [ ] **Step 2: 验证导入**

Run: `python -c "from widgets import LogWidget; print('ok')"`
Expected: 输出 `ok`，退出码 0。

---

### Task 5: 主窗口集成 `widgets/main_widget.py`

**Files:**
- Modify: `widgets/main_widget.py`（imports、`__init__`、`_build_toolbar`、`_build_project_view`、新增 `_build_columns`、`_on_new`/`_open_file`/`_on_save`、新增 `_on_toggle_log`）

- [ ] **Step 1: 加 imports**

在 `widgets/main_widget.py` 顶部 import 区，把 QtWidgets 那行加 `QMenu`，并新增 `LogModel` / `LogWidget` 两行：

```python
from PyQt5.QtWidgets import (
    QAction, QApplication, QFileDialog, QFrame, QHBoxLayout, QLabel,
    QMainWindow, QMenu, QMessageBox, QSplitter, QStackedWidget, QToolButton,
    QVBoxLayout, QWidget,
)
from model.kscp_package import KscpPackage
from model.log_model import LogModel
from widgets.resource_tree_widget import ResourceTreeWidget
from widgets.log_widget import LogWidget
```

- [ ] **Step 2: `__init__` 加启动日志与 `_log_widget` 字段**

在 `__init__` 中，把 `self.resize(600, 350)` 那一段之后、`self._build_toolbar()` 之前，加 `_log_widget` 字段；并在 `_build_toolbar()` 之后加启动日志：

```python
        self.setWindowTitle("KScript")
        self.resize(600, 350)            # landing 默认尺寸；打开工程时再放大
        self._project_sized = False
        self._log_widget: Optional[LogWidget] = None

        self._central = QStackedWidget()
        self.setCentralWidget(self._central)
        self._central.addWidget(self._build_landing())    # page 0
        self._project_widget: Optional[QWidget] = None
        self._switcher: Optional[_ActivityBar] = None
        self._tree_stack: Optional[QStackedWidget] = None
        self._preview_stack: Optional[QStackedWidget] = None
        self._tree_panel: Optional[_TitledPanel] = None

        self._build_toolbar()
        LogModel.instance().info("KScript 启动")
        if path:
            self._open_file(path)   # 失败则停在 landing
```

- [ ] **Step 3: 工具栏加「窗口」菜单**

在 `_build_toolbar` 末尾（`tb.addAction(a_save)` 之后）追加：

```python
        # 窗口菜单：显示日志开关
        win_btn = QToolButton(self)
        win_btn.setText("窗口")
        win_btn.setPopupMode(QToolButton.InstantPopup)
        win_menu = QMenu(win_btn)
        self._a_show_log = win_menu.addAction("显示日志")
        self._a_show_log.setCheckable(True)
        self._a_show_log.setChecked(True)
        self._a_show_log.toggled.connect(self._on_toggle_log)
        win_btn.setMenu(win_menu)
        tb.addWidget(win_btn)
```

并新增方法（放在 `_build_toolbar` 之后）：

```python
    def _on_toggle_log(self, checked: bool) -> None:
        if self._log_widget is not None:
            self._log_widget.setVisible(checked)
```

- [ ] **Step 4: 抽 `_build_columns` + 改 `_build_project_view` 为纵向 splitter**

把现有 `_build_project_view`（横向 splitter）整段替换为：`_build_project_view` 返回纵向 splitter（含 LogWidget），`_build_columns` 保留原横向逻辑：

```python
    def _build_project_view(self) -> QWidget:
        vsp = QSplitter(Qt.Vertical)
        vsp.setChildrenCollapsible(False)
        vsp.addWidget(self._build_columns())     # 横向 splitter
        self._log_widget = LogWidget()
        vsp.addWidget(self._log_widget)
        # 纵向缩放：上方吸收（1），日志栏高度稳定（0），仅手动拖动改变
        vsp.setStretchFactor(0, 1)
        vsp.setStretchFactor(1, 0)
        vsp.setSizes([540, 160])
        return vsp

    def _build_columns(self) -> QWidget:
        sp = QSplitter()
        sp.setChildrenCollapsible(False)      # 防止拖到极小时栏「突然消失」

        # 切换栏（VSCode 风格图标条，无标题，悬停显示功能名）
        self._switcher = _ActivityBar()
        self._switcher.currentChanged.connect(self._on_switch)

        # 树栏（标题随当前管理树变化）
        self._tree_stack = QStackedWidget()
        self._tree_panel = _TitledPanel("资源树栏", self._tree_stack)
        self._tree_panel.setMinimumWidth(180)

        # 视图栏
        self._preview_stack = QStackedWidget()
        preview_panel = _TitledPanel("视图栏", self._preview_stack)
        preview_panel.setMinimumWidth(200)

        sp.addWidget(self._switcher)
        sp.addWidget(self._tree_panel)
        sp.addWidget(preview_panel)
        sp.setStretchFactor(0, 0)
        sp.setStretchFactor(1, 0)
        sp.setStretchFactor(2, 1)
        sp.setSizes([56, 220, 700])
        return sp
```

- [ ] **Step 5: 埋点日志（`_on_new` / `_open_file` / `_on_save`）**

把 `_on_new` 替换为：

```python
    def _on_new(self) -> None:
        LogModel.instance().info("新建工程")
        self._open_package(KscpPackage.create_empty(), None)
```

把 `_open_file` 替换为：

```python
    def _open_file(self, path: str) -> None:
        try:
            pkg = KscpPackage.from_kscp(path)
        except Exception as e:  # 文件缺失/损坏等，统一提示并停在 landing
            QMessageBox.critical(self, "打开失败", "无法打开 %s：%s" % (path, e))
            LogModel.instance().error("打开失败：%s：%s" % (path, e))
            return
        LogModel.instance().info("打开工程：%s" % path)
        self._open_package(pkg, path)
```

在 `_on_save` 末尾（`sb.showMessage(...)` 之后）追加一行：

```python
        LogModel.instance().info("已保存：%s" % path)
```

- [ ] **Step 6: 运行自检（landing + project）**

Run: `python main.py --check`
Expected: 退出码 0（landing 600×350 渲染后自动退出）。

Run: `python main.py sample.kscp --check`
Expected: 退出码 0（工程视图含日志栏渲染后自动退出；日志栏有「KScript 启动」「打开工程：sample.kscp」条目）。

---

### Task 6: 端到端验证

**Files:** 无（仅运行）

- [ ] **Step 1: 模型冒烟**

Run: `python -m model.log_model`
Expected: `LogModel smoke OK`，退出码 0。

- [ ] **Step 2: 控件冒烟**

Run: `python -m widgets.log_widget 2>&1 | grep -v "RuntimeWarning\|not package"`
Expected: `LogWidget smoke OK`，退出码 0。

- [ ] **Step 3: 主窗口两态自检**

Run: `python main.py --check && python main.py sample.kscp --check`
Expected: 两条均退出码 0。

---

## 自检（Self-Review）

**1. 规格覆盖：**
- 导出函数 → Task 1 `export(fmt)` ✓
- 清空当前日志 → Task 1 `clear()` + Task 3 「清空」按钮 ✓
- 多种级别 → Task 1 `LogLevel` 5 级 + 便捷方法 + Task 3 过滤下拉 ✓
- 单例模式 → Task 1 `instance()` + `_instance` ✓
- widgets 承载窗口、显示在视图下方 → Task 3 `LogWidget` + Task 5 纵向 splitter ✓
- 工具栏「窗口」选项展开 + 是否显示日志 → Task 5 `QToolButton`+`QMenu`+可勾选 `QAction` ✓

**2. 占位符扫描：** 无 TBD/TODO；每步含完整代码 ✓

**3. 类型一致性：**
- `LogModel.instance()`、`_reset_instance()`、`export(fmt)->bytes`、`format_time(ts)->str`、`entries`、`add_listener/remove_listener`、`debug/info/warning/error/critical` 全程一致 ✓
- `LogLevel.levels()` 仅定义在 `LogLevel`（枚举）上；Task 3 与 Task 1 冒烟均用 `LogLevel.levels()` ✓（规格 3.3 列了 `LogModel.levels()`，实现中收敛到 `LogLevel.levels()`，控件冒烟与主窗口均一致）
- `LogWidget._refresh` 在 `add_listener`/`remove_listener`/`closeEvent` 中引用一致 ✓
- 主窗口字段 `self._log_widget` / `self._a_show_log` 在 `__init__`/`_build_toolbar`/`_on_toggle_log`/`_build_project_view` 一致 ✓
