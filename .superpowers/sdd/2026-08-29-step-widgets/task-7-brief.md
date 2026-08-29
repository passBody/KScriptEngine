# 步骤卡片 + 步骤列表视图 + 步骤列表管理树 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增三个 GUI 控件（步骤对象卡片、步骤列表视图、步骤列表管理树）并集成进主程序——管理树选列表 → 视图横排卡片，卡片颜色随状态/io 校验变化。

**Architecture:** 模型层补三个方法（`StepList.insert_format_strings` 事务性插入、`StepListStore.remove/rename/walk`）；widget 层三个新文件（`step_card.py` / `step_list_view.py` / `step_list_tree_widget.py`），视图用 QGraphicsView + QGraphicsProxyWidget 实现滚轮横滚与悬停缩放；主窗口共享一棵变量树给变量管理树与步骤列表管理树，变量变更 → 卡片重检颜色。

**Tech Stack:** Python 3.14 / PyQt5 5.15（QGraphicsView、QVariantAnimation、QTreeWidget、QSS 内联样式）/ 现有模型（Step、StepIOWidget、StepManager、StepList、StepListStore、VariableTree）

**Spec:** `docs/superpowers/specs/2026-08-29-step-widgets-design.md`（本计划由此展开；冲突时 spec 为准）



- **TDD 红绿循环（冒烟即测试载体）**：每个任务先写冒烟断言 → 运行确认**红**（失败原因 = 目标类/方法缺失，如 `ImportError: cannot import name 'X'` 或 `AttributeError`）→ 实现最小代码 → 运行确认**绿**（输出 `<Name> smoke OK` 且 EXIT=0）→ 跑依赖链冒烟回归。
- **冒烟运行方式**：`python -m <模块>`（如 `python -m widgets.step_card`）；**绝不经过管道**（会吞掉 EXIT code）；成功判据 = 输出 `X smoke OK` 且 EXIT=0；已知无害的 `<frozen runpy> RuntimeWarning` 忽略；RED 阶段 `ImportError: cannot import name 'X'`（python -m runpy 先按真名导入）与 NameError 等价 = 类缺失。
- **模板字节**：`actions/*.py` 模板内容一律 `.encode("utf-8")` 写入包（`pkg.write_file("actions/示例.py", GOOD.encode("utf-8"))`）；**绝不写中文 bytes 字面量**；纯 ASCII 字节（`b"{}"`、`b'[1,2,3]'`）允许。
- **非 git 仓库（既有裁定延续）**：无 commit 步骤；「提交」= 运行验证（冒烟绿 + 依赖链回归）；评审包 = 任务文件清单 + 直接 Read 文件内容。
- **Qt 存根规避（既有模式）**：枚举值取整数值（`_PATH_ROLE = 0x0100` = Qt.UserRole）；`self.style()` 判 `is not None` 后再用；图标用 QPainter 自绘（`_make_step_icon` 风格），不依赖 QStyle 标准图标枚举。
- **新文件一律** `from __future__ import annotations`；docstring/注释中文，与既有文件风格一致；模块内冒烟块放文件末尾 `if __name__ == "__main__":`。
- **状态纯显示**：卡片/视图/管理树**绝不调用** `step.do()`；`step.status` 由外部设置后调 `refresh()` 更新颜色（冒烟直接设 status 验证）。
- **剪贴板**：剪切后剪贴板保留（剪切 = 复制 + 删除，允许多次粘贴；与变量树的 cut 清空不同，这是**有意**设计）。
- **快捷键**：Ctrl+C/X/V 只在管理树注册（F2/Del）；步骤列表视图**不注册**（卡片内文本框焦点冲突，复制文本会被劫持）。
- **类型**：`Tuple` 导入按需加入 typing；不改动任何既有 API 签名（除 T6 的 `VariableTreeWidget.__init__` 增加**可选**参数）。

---
### Task 7: 主窗口集成 — `StepListManagementTree` + 宿主 + 共享变量树

**Files:**
- Modify: `widgets/main_widget.py`（imports；`VariableManagementTree.__init__/tree_widget/preview_widget`；新增 `StepListManagementTree` + `_StepListHost`；`MainWindow._open_package`；`MainWindow._load_shared_tree`；文件末尾新增集成冒烟块）

**Interfaces:**
- Consumes: T4 的 `StepClipboard` / `StepListView`；T5 的 `StepListTreeWidget`；T6 的 `VariableTreeWidget(package, tree)` + `tree_changed`；`StepListStore.from_json/create_empty/to_json_bytes`；`StepManager(package, tree)`；`VariableTree.from_json/create_empty/to_json_bytes`；`_make_icon("step")`（活动栏图标）
- Produces: `StepListManagementTree(package, tree)`（ManagementTree 子类，含 `refresh_cards()`；`tree_widget()` / `preview_widget()` 懒构建）；`_StepListHost`（私有容器，同文件）

- [ ] **Step 1: 写失败测试**——`widgets/main_widget.py` 文件末尾现有 `if __name__ == "__main__":` 块（运行 `main()`，会阻塞）**整体替换**为下方集成冒烟块：

```python
if __name__ == "__main__":
    import sys
    import tempfile

    from PyQt5.QtWidgets import QApplication

    from model.project_variable import ProjectVariable
    from model.step_list import StepList

    app = QApplication.instance() or QApplication(sys.argv)

    # 模板字节（有效模板；中文/引号内容一律用 .encode("utf-8")，禁用中文 bytes 字面量）
    GOOD = '''# -*- coding: utf-8 -*-
from dataclasses import dataclass
from actions.base import Step

@dataclass
class _DemoInput:
    count: "number" = 0

@dataclass
class _DemoOutput:
    total: "number" = 0

class DemoStep(Step):
    name = "示例"
    description = "测试模板"
    input_class = _DemoInput
    output_class = _DemoOutput

    def run(self) -> int:
        self.outputs.total = self.inputs.count * 2
        return 1
'''
    tmp = tempfile.mktemp(suffix=".kscp")
    pkg = KscpPackage.create_empty()
    pkg.write_file("actions/示例.py", GOOD.encode("utf-8"))
    tree = VariableTree.create_empty()
    tree.add("n1", ProjectVariable.create("number", 100, pkg))
    pkg.write_file("variables.json", tree.to_json_bytes())
    pkg.save(tmp)

    win = MainWindow(tmp)
    win.show()                       # 不 exec：构造期已同步构建全部控件

    # managers 结构：第 3 位 = StepListManagementTree（替换占位）
    assert len(win._managers) == 4
    sl_mgr = win._managers[2]
    assert isinstance(sl_mgr, StepListManagementTree)
    assert sl_mgr.name == "步骤列表"

    # 共享变量树：变量管理树与步骤列表管理树同树
    var_mgr = win._managers[1]
    assert isinstance(var_mgr, VariableManagementTree)
    vtw = var_mgr.tree_widget()
    assert isinstance(vtw, VariableTreeWidget)
    assert vtw._tree is sl_mgr._tree
    host = sl_mgr.preview_widget()
    assert isinstance(host, _StepListHost)
    assert isinstance(sl_mgr.tree_widget(), StepListTreeWidget)

    # 空 store → step_list.json 已写盘（镜像 variables.json 模式）
    assert win._package is not None
    assert win._package.exists("step_list.json")
    assert sl_mgr._store.paths() == []

    # 经 store API 添加列表 → 保存落盘（store 与包同实例）
    sl = StepList.create_empty()
    s = sl_mgr._mgr.create_step("示例")
    s.io.change_value("input", 0, "5")
    s.io.change_value("output", 0, "n1")
    sl.add(s)
    sl_mgr._store.add_list("主列表", sl)
    sl_mgr._save_store()
    raw = win._package.read_file("step_list.json")
    assert '"主列表"' in raw.decode("utf-8")

    # list_selected → 宿主视图出现卡片
    tw = sl_mgr.tree_widget()
    assert isinstance(tw, StepListTreeWidget)
    tw.list_selected.emit("主列表")
    assert host.currentIndex() == 1
    assert len(host._view._cards) == 1

    # 变量 tree_changed → refresh_cards 不崩（已接线 host）
    vtw.tree_changed.emit()
    assert len(host._view._cards) == 1

    # 当前列表被删 → 宿主回占位页
    sl_mgr._store.remove("主列表")
    tw.store_changed.emit()
    assert host.currentIndex() == 0

    print("MainWindow smoke OK")
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m widgets.main_widget`
Expected: RED —— `NameError: name 'StepListManagementTree' is not defined`（EXIT=1）

- [ ] **Step 3: 实现**——五处修改：

① imports（`from typing import List, Optional` 改为加 `Callable`；新增模型与 widget imports）：

```python
from typing import Callable, List, Optional
```
并在 `from widgets.variable_tree_widget import VariableTreeWidget` 之后追加：

```python
from model.step_list import StepList
from model.step_list_store import StepListStore
from model.step_manager import StepManager
from model.variable_tree import VariableTree
from widgets.step_list_view import StepClipboard, StepListView
from widgets.step_list_tree_widget import StepListTreeWidget
```

② `VariableManagementTree`（第 151-175 行区域）——加 `tree` 参数并透传：

```python
    def __init__(self, package: KscpPackage,
                 tree: Optional[VariableTree] = None) -> None:
        super().__init__("变量")
        self._package = package
        self._tree = tree
        self._vtree: Optional[VariableTreeWidget] = None
```
`tree_widget()` / `preview_widget()` 两处的 `VariableTreeWidget(self._package)` 改为 `VariableTreeWidget(self._package, self._tree)`。

③ 在 `StepManagementTree` 之后、`PlaceholderManagementTree` 之前新增两个类：

```python
class StepListManagementTree(ManagementTree):
    """步骤列表管理树：StepListTreeWidget + 宿主（占位/列表视图）。"""

    def __init__(self, package: KscpPackage, tree: VariableTree) -> None:
        super().__init__("步骤列表")
        self._package = package
        self._tree = tree
        self._mgr = StepManager(package, tree)
        self._mgr.load()
        if package.exists("step_list.json"):
            self._store = StepListStore.from_json(
                package.read_file("step_list.json"), self._mgr)
        else:
            self._store = StepListStore.create_empty()
            self._save_store()
        self._clipboard = StepClipboard()
        self._sl_tree: Optional[StepListTreeWidget] = None
        self._host: Optional[_StepListHost] = None
        self._current: Optional[str] = None

    def icon(self) -> QIcon:
        return _make_icon("step")

    def _save_store(self) -> None:
        self._package.write_file("step_list.json", self._store.to_json_bytes())

    def refresh_cards(self) -> None:
        """变量树变化 → 宿主重检卡片颜色（不重建）。"""
        if self._host is not None:
            self._host.refresh_validity()

    def tree_widget(self) -> QWidget:
        if self._sl_tree is None:
            self._sl_tree = StepListTreeWidget(
                self._store, self._mgr, self._clipboard,
                self._save_store, None)
            self._sl_tree.list_selected.connect(self._on_list_selected)
            self._sl_tree.store_changed.connect(self._on_store_changed)
        assert self._sl_tree is not None
        return self._sl_tree

    def preview_widget(self) -> QWidget:
        if self._host is None:
            self._host = _StepListHost(
                self._mgr, self._clipboard, self._save_store, None)
        assert self._host is not None
        return self._host

    # ---- 宿主联动 ----
    def _on_list_selected(self, path: str) -> None:
        self._current = path
        if self._host is not None:
            try:
                self._host.set_list(self._store.get(path), self._mgr)
            except FileNotFoundError:
                self._host.set_list(None)

    def _on_store_changed(self) -> None:
        if self._host is None or self._current is None:
            return
        try:
            self._store.get(self._current)
        except FileNotFoundError:
            self._host.set_list(None)


class _StepListHost(QStackedWidget):
    """步骤列表视图宿主：占位页 + StepListView（视图编辑 → 保存回调）。"""

    def __init__(self, mgr: StepManager, clipboard: StepClipboard,
                 on_edited: Callable[[], None],
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._placeholder = QLabel("从左侧选择一个步骤列表")
        self._placeholder.setAlignment(Qt.AlignCenter)
        self._placeholder.setStyleSheet("color:#999; font-size:15px;")
        self.addWidget(self._placeholder)          # 0
        self._view = StepListView(mgr, clipboard, None)
        self._view.edited.connect(on_edited)
        self.addWidget(self._view)                 # 1
        self.setCurrentIndex(0)

    def set_list(self, step_list: Optional[StepList],
                 mgr: Optional[StepManager] = None) -> None:
        self._view.set_list(step_list, mgr)
        self.setCurrentIndex(1 if step_list is not None else 0)

    def refresh_validity(self) -> None:
        self._view.refresh_validity()
```

④ `MainWindow._open_package`（第 569-578 行区域）——共享树 + 替换占位 + 接线：

```python
    def _open_package(self, package: KscpPackage, path: Optional[str]) -> None:
        self._package = package
        self._kscp_path = path
        tree = self._load_shared_tree(package)
        self._step_mgr = StepManagementTree(package)
        self._managers = [
            ResourceManagementTree(package),
            VariableManagementTree(package, tree),
            StepListManagementTree(package, tree),
            self._step_mgr,
        ]
        # 变量树变化 → 步骤卡片重检颜色（io 校验随变量树变）
        var_mgr = self._managers[1]
        sl_mgr = self._managers[2]
        assert isinstance(var_mgr, VariableManagementTree)
        assert isinstance(sl_mgr, StepListManagementTree)
        vtw = var_mgr.tree_widget()
        assert isinstance(vtw, VariableTreeWidget)
        vtw.tree_changed.connect(sl_mgr.refresh_cards)
        ...（其余行不动：_manage_btn 起原样保留）...
```

⑤ 新增 `_load_shared_tree`（放在 `_open_package` 之后）：

```python
    @staticmethod
    def _load_shared_tree(package: KscpPackage) -> VariableTree:
        """加载一棵共享变量树（存在 variables.json → 读回；否则空树 + 写盘）。"""
        if package.exists("variables.json"):
            return VariableTree.from_json(
                package.read_file("variables.json"), package)
        tree = VariableTree.create_empty()
        package.write_file("variables.json", tree.to_json_bytes())
        return tree
```

- [ ] **Step 4: 运行确认通过**

Run: `python -m widgets.main_widget`
Expected: GREEN —— `MainWindow smoke OK` EXIT=0

- [ ] **Step 5: 全量回归**

Run（逐个执行，不经过管道）: `python -m actions.base`、`python -m model.kscp_package`、`python -m model.variable_tree`、`python -m model.project_variable`、`python -m model.log_model`、`python -m model.step_manager`、`python -m model.step_list`、`python -m model.step_list_store`、`python -m widgets.step_io_widget`、`python -m widgets.step_tree_widget`、`python -m widgets.resource_tree_widget`、`python -m widgets.variable_tree_widget`、`python -m widgets.step_card`、`python -m widgets.step_list_view`、`python -m widgets.step_list_tree_widget`、`python -m widgets.main_widget`、`python main.py --check`
Expected: 全部 `smoke OK` / EXIT=0

---

