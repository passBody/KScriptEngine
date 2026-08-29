# 变量管理树 + 图片遮罩预览 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给 KScript 加可复用的图片遮罩预览控件 + 全局变量管理树 GUI（左树 + 中编辑卡，按类型生成编辑器、实时校验禁用提交、资源类经资源选择器改值）+ 创建对话框 + 接入主界面 + 详细日志；同时把 `png` 类型全局更名 `image`、给 `VariableType` 加 `description`。

**Architecture:** 模型层小改（`description` + `png`→`image`）；新增 `widgets/image_overlay.py`（`ImageOverlay`，复用 `_ZoomGraphicsView`）；`resource_tree_widget.py` 加只读选模式 + `pick_resource`、预览改遮罩、删 `_ImagePreviewDialog`；新增 `widgets/variable_tree_widget.py`（`VariableTreeWidget` + `VariableEditPanel` + `CreateVariableDialog` + `VAR_EDITORS` 注册表）；`main_widget.py` 用真实 `VariableManagementTree` 替换占位。所有操作经 `LogModel` 记日志。

**Tech Stack:** Python 3 + PyQt5；无 git（用运行验证替代提交）；冒烟写在各模块 `__main__`，用 `python -m <module>` 运行。

**约定适配：** 本仓库非 git 仓库，每个任务的「提交」步骤一律替换为「运行验证」。冒烟测试即各文件 `__main__` 的 assert 块。GUI 冒烟用 `QApplication.instance() or QApplication(sys.argv)`，`-m` 重导入模块有 `runpy.RuntimeWarning`，用 `grep -v "RuntimeWarning\|not package"` 过滤。

---

## 文件结构

- 改 `model/project_variable.py`：`VariableType` 加 `description`；`_PngType`→`_ImageType`（`name="image"`）；冒烟改 `image`。
- 改 `model/variable_tree.py`：冒烟里 `"png"`→`"image"`。
- 创建 `widgets/image_overlay.py`：`_ZoomGraphicsView`（从 resource_tree 外移）+ `ImageOverlay` + `__main__` 冒烟。
- 改 `widgets/resource_tree_widget.py`：删 `_ZoomGraphicsView`/`_ImagePreviewDialog`，从 image_overlay import `_ZoomGraphicsView`（仅 `_ImagePreviewDialog` 原用它，删后无需）；构造加 `select_mode`；加 `pick_resource`；预览改 `ImageOverlay`；冒烟适配。
- 改 `widgets/__init__.py`：导出 `ImageOverlay`、`VariableTreeWidget`。
- 创建 `widgets/variable_tree_widget.py`：`VAR_EDITORS` + `register_editor` + `VariableTreeWidget` + `VariableEditPanel` + `CreateVariableDialog` + `__main__` 冒烟。
- 改 `widgets/main_widget.py`：加 `VariableManagementTree`、`_open_package` 换占位、imports。

---

### Task 1: 模型 — `VariableType.description` + `png`→`image`

**Files:**
- Modify: `model/project_variable.py`

- [ ] **Step 1: 改 `VariableType` 加 `description`，`_PngType`→`_ImageType`**

把 `model/project_variable.py` 中 `class VariableType:` 的类体顶部加 `description`，并把 `_PngType` 整段改名。具体：

在 `VariableType` 类里 `suffixes: tuple = ()` 那行之后加：

```python
    description: str = ""   # 类型描述词（创建对话框下拉项展示）；默认空，自定义类型可不填
```

把：
```python
class _PngType(VariableType):
    name = "png"
    is_resource = True  # data 为工程资源路径
    suffixes = (".png", ".jpg")  # 接受的图片后缀
```
改为：
```python
class _ImageType(VariableType):
    name = "image"
    is_resource = True  # data 为工程资源路径
    suffixes = (".png", ".jpg")  # 接受的图片后缀
    description = "图片资源（工程 assets 内的 .png/.jpg）"
```
（`normalize`/`is_valid`/`to_actual` 方法体不变，仅类名与 name/description。）

给 `_StringType`、`_NumberType` 加 `description`：
```python
class _StringType(VariableType):
    name = "string"
    description = "文本字符串"
```
```python
class _NumberType(VariableType):
    name = "number"
    description = "整数或小数"
```

把模块底部注册：
```python
ProjectVariable.register_type(_PngType())
```
改为：
```python
ProjectVariable.register_type(_ImageType())
```

- [ ] **Step 2: 改模块 docstring/冒烟里 `png`→`image`**

模块 docstring 中 `png` 类型出现的描述处（如 ``* ``type``  变量类型（``string`` / ``number`` / ``png``…``）``）改为 `image`；冒烟 `if __name__ == "__main__":` 中所有创建/断言用到的 `"png"` 字面量改为 `"image"`（如 `ProjectVariable.create("png", ...)` → `ProjectVariable.create("image", ...)`；`p.is_resource` 等不变；`assert ProjectVariable.supported_types() == ["number", "png", "string"]` → `["image", "number", "string"]`）。注意 `bad_png_*` 局部变量名可保留或顺手改 `bad_image_*`（不影响断言），但 `create("png", ...)` 调用必须改。

- [ ] **Step 3: 改 `model/variable_tree.py` 冒烟里 `png`→`image`**

把 `variable_tree.py` 冒烟中 `ProjectVariable.create("png", ...)` 与 `filter_by_type("png")` 等改为 `"image"`（`v_png`/`png_tree` 等局部变量名可不动）。

- [ ] **Step 4: 运行模型冒烟，确认通过**

Run: `python -m model.project_variable`
Expected: `ProjectVariable smoke OK`，退出码 0。

Run: `python -m model.variable_tree`
Expected: `VariableTree smoke OK`，退出码 0。

- [ ] **Step 5: 运行依赖模型的其他冒烟，确认无 `png` 残留破坏**

Run: `python -m widgets.resource_tree_widget 2>&1 | grep -v "RuntimeWarning\|not package"`
Expected: `ResourceTreeWidget smoke OK`，退出码 0。

Run: `python main.py sample.kscp --check`
Expected: 退出码 0。

---

### Task 2: 图片遮罩预览 `widgets/image_overlay.py`（新）

**Files:**
- Create: `widgets/image_overlay.py`

- [ ] **Step 1: 写完整模块**

把以下内容写入 `widgets/image_overlay.py`：

```python
# -*- coding: utf-8 -*-
"""
图片遮罩预览（可复用控件）
========================

:class:`ImageOverlay` 在父窗口上盖一层半透明黑色遮罩，居中显示一张可滚轮缩放、
拖拽平移、双击适配的图片。资源树预览、image 变量预览共用本控件。

基本用法
--------
::

    from widgets import ImageOverlay
    ov = ImageOverlay(pixmap, parent_window)
    ov.show_overlay()      # 盖到 parent 上
    # 用户：滚轮缩放/拖拽/双击适配；Esc 或点击空白处关闭
"""

from __future__ import annotations

from typing import Optional

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QPainter, QPixmap
from PyQt5.QtWidgets import (
    QGraphicsPixmapItem, QGraphicsScene, QGraphicsView, QHBoxLayout,
    QLabel, QVBoxLayout, QWidget,
)

__all__ = ["ImageOverlay"]


class _ZoomGraphicsView(QGraphicsView):
    """滚轮缩放 + 拖拽平移的图片视图；双击适配窗口。"""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setDragMode(QGraphicsView.ScrollHandDrag)   # 鼠标拖拽平移
        self.setRenderHint(QPainter.Antialiasing)
        self.setResizeAnchor(QGraphicsView.AnchorUnderMouse)
        self.setBackgroundBrush(QColor("#1e1e1e"))
        self._zoom = 1.0

    def wheelEvent(self, event) -> None:  # noqa: N802 (Qt 命名)
        factor = 1.25 if event.angleDelta().y() > 0 else 1 / 1.25
        new = self._zoom * factor
        if 0.05 < new < 50:
            self._zoom = new
            self.scale(factor, factor)

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802 (Qt 命名)
        self.fit_view()

    def fit_view(self) -> None:
        self._zoom = 1.0
        self.resetTransform()
        if self.scene() is not None:
            self.fitInView(self.scene().sceneRect(), Qt.KeepAspectRatio)


class ImageOverlay(QWidget):
    """半透明黑色遮罩 + 居中可缩放拖拽图片。"""

    def __init__(self, pixmap: QPixmap, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._pixmap = pixmap
        self.setWindowFlags(Qt.SubWindow)        # 仍属父窗口，但能盖在兄弟控件上
        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self.setFocusPolicy(Qt.StrongFocus)

        self._view = _ZoomGraphicsView(self)
        self._scene = QGraphicsScene(self)
        self._item = QGraphicsPixmapItem(pixmap)
        self._scene.addItem(self._item)
        self._view.setScene(self._scene)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        bar = QHBoxLayout()
        bar.setContentsMargins(6, 4, 6, 4)
        self._hint = QLabel("滚轮缩放 · 拖拽平移 · 双击适配 · Esc/点击空白 关闭")
        self._hint.setAlignment(Qt.AlignCenter)
        self._hint.setStyleSheet("color:#aaa; background:#1e1e1e; padding:3px;")
        bar.addWidget(self._hint)
        lay.addLayout(bar)
        lay.addWidget(self._view, 1)

    def show_overlay(self) -> None:
        """盖到父窗口全屏并显示。"""
        p = self.parentWidget()
        if p is not None:
            self.setGeometry(p.rect())
        self.raise_()
        self.show()
        self.setFocus()
        self._view.fit_view()

    def close_overlay(self) -> None:
        self.hide()

    def keyPressEvent(self, event) -> None:  # noqa: N802 (Qt 命名)
        if event.key() == Qt.Key_Escape:
            self.close_overlay()
        else:
            super().keyPressEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802 (Qt 命名)
        # 点击遮罩空白（即 _view 之外）→ 关闭
        if event.button() == Qt.LeftButton:
            self.close_overlay()
        super().mousePressEvent(event)


if __name__ == "__main__":
    import sys
    from PyQt5.QtWidgets import QApplication
    from PyQt5.QtGui import QColor, QImage
    from PyQt5.QtCore import QBuffer

    app = QApplication.instance() or QApplication(sys.argv)

    img = QImage(120, 80, QImage.Format_RGB32)
    img.fill(QColor("#3a7bd5"))
    buf = QBuffer(); buf.open(QBuffer.ReadWrite)
    img.save(buf, "PNG")
    pix = QPixmap()
    pix.loadFromData(bytes(buf.data()))

    host = QWidget()
    host.resize(400, 300)
    host.setStyleSheet("background:#fff;")
    ov = ImageOverlay(pix, host)
    ov.show_overlay()
    assert ov.isVisible()
    assert ov._item in ov._scene.items()
    assert not ov._item.pixmap().isNull()
    ov.close_overlay()
    assert not ov.isVisible()
    print("ImageOverlay smoke OK")
```

- [ ] **Step 2: 运行冒烟，确认通过**

Run: `python -m widgets.image_overlay 2>&1 | grep -v "RuntimeWarning\|not package"`
Expected: `ImageOverlay smoke OK`，退出码 0。

---

### Task 3: 资源树 — 删旧预览、改用遮罩、加只读选模式 + `pick_resource`

**Files:**
- Modify: `widgets/resource_tree_widget.py`

- [ ] **Step 1: 删 `_ZoomGraphicsView` 与 `_ImagePreviewDialog`，改 import**

从 `widgets/resource_tree_widget.py` 删除整段 `class _ZoomGraphicsView(...)`（约 75-100 行）与整段 `class _ImagePreviewDialog(QDialog):`（约 103-126 行）。

在文件顶部 import 区，把 `from PyQt5.QtWidgets import (...)` 中不再用的删去（`QDialog`、`QGraphicsPixmapItem`、`QGraphicsScene`、`QGraphicsView` 若删类后无其他引用则删；保留 `QListWidgetItem` 等）。`_ZoomGraphicsView` 已外移到 `image_overlay`，本文件不再引用。

- [ ] **Step 2: `_PreviewPanel._open_image_dialog` 改用 `ImageOverlay`**

把 `_PreviewPanel._open_image_dialog` 方法体改为：

```python
    def _open_image_dialog(self) -> None:
        """点击图片 → 在视图中盖遮罩大图（滚轮缩放/拖拽平移）。"""
        if self._raw_pixmap is None or self._raw_pixmap.isNull():
            return
        from widgets.image_overlay import ImageOverlay
        ImageOverlay(self._raw_pixmap, self.window()).show_overlay()
```

并在文件顶部加：
```python
from widgets.image_overlay import ImageOverlay
```
（或用方法内惰性 import 避免循环；顶部 import 亦可——`image_overlay` 不依赖 `resource_tree_widget`，无环。选顶部 import。）

- [ ] **Step 3: 构造加 `select_mode`**

把 `ResourceTreeWidget.__init__` 签名与开头改为：

```python
    def __init__(self, package: KscpPackage,
                 select_mode: bool = False,
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._package = package
        self._select_mode = select_mode
        self._clipboard: Optional[Tuple[List[str], str]] = None  # (paths, "copy"|"cut")
        self._preview: Optional[_PreviewPanel] = None

        self.setHeaderHidden(True)
        self.setSelectionMode(
            QAbstractItemView.SingleSelection if select_mode
            else QAbstractItemView.ExtendedSelection)
        self.setUniformRowHeights(True)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._on_context_menu)
        self.currentItemChanged.connect(self._on_current_changed)

        if not select_mode:
            # 编辑态才装全局快捷键（只读选模式禁用删除/重命名等）
            QShortcut(QKeySequence.Copy, self, self._act_copy)
            QShortcut(QKeySequence.Cut, self, self._act_cut)
            QShortcut(QKeySequence.Paste, self, self._act_paste)
            QShortcut(QKeySequence.Delete, self, self._act_delete)
            QShortcut("F2", self, self._act_rename)

        self.refresh()
```

并在 `_on_context_menu` 开头加：
```python
        if self._select_mode:
            return
```
（只读模式不弹菜单。）

- [ ] **Step 4: 加 `pick_resource` 静态方法**

在 `ResourceTreeWidget` 类中（如 `preview_widget` 之前或末尾）加：

```python
    @staticmethod
    def pick_resource(package: KscpPackage, suffixes: tuple = (),
                      parent: Optional[QWidget] = None) -> Optional[str]:
        """弹对话框嵌入只读 ResourceTreeWidget，按后缀过滤，选中确认返回路径。"""
        from PyQt5.QtWidgets import QDialog, QDialogButtonBox, QVBoxLayout
        dlg = QDialog(parent or None)
        dlg.setWindowTitle("选择资源")
        dlg.resize(600, 500)
        tree = ResourceTreeWidget(package, select_mode=True, parent=dlg)
        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.addWidget(tree)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        lay.addWidget(btns)

        def _accept() -> None:
            # 仅文件且通过后缀过滤才接受
            it = tree.currentItem()
            if it is None:
                return
            p = it.data(0, _PATH_ROLE)
            if not p or not package.is_file(p):
                return
            if suffixes and not p.lower().endswith(tuple(suffixes)):
                return
            dlg.accept()

        btns.accepted.connect(_accept)
        btns.rejected.connect(dlg.reject)
        tree.itemDoubleClicked.connect(
            lambda *_: _accept() if package.is_file(
                (tree.currentItem().data(0, _PATH_ROLE)
                 if tree.currentItem() is not None else "")) else None)

        # 后缀过滤：不匹配的文件项隐藏（文件夹始终可见）
        def _apply_filter() -> None:
            for it in tree._walk_items():
                p = it.data(0, _PATH_ROLE)
                if p and package.is_file(p) and suffixes \
                        and not p.lower().endswith(tuple(suffixes)):
                    it.setHidden(True)

        _apply_filter()

        if dlg.exec_() != QDialog.Accepted:
            return None
        it = tree.currentItem()
        if it is None:
            return None
        p = it.data(0, _PATH_ROLE)
        return p if p and package.is_file(p) else None
```

注意：`_walk_items` 是 `ResourceTreeWidget` 现有方法（返回所有项迭代器），`_PATH_ROLE` 是模块级常量。`itemDoubleClicked` 的双击确认简化为：双击文件项即 `_accept()`（上面 lambda 已处理；若嫌绕可改为在 tree 上连 `itemDoubleClicked`→ 判断是文件则 `dlg.accept()`，最终返回逻辑同 `_accept`）。若 lambda 可读性差，可改为具名函数。

- [ ] **Step 5: 冒烟适配（`_ImagePreviewDialog` 被删，相关断言改 `ImageOverlay`）**

把 `resource_tree_widget.py` 的 `__main__` 冒烟中：
```python
    dlg = _ImagePreviewDialog(pv._raw_pixmap)                 # 构造大图查看器（不 exec）
    assert dlg._item in dlg._scene.items()
    assert not dlg._item.pixmap().isNull()
```
改为：
```python
    from widgets.image_overlay import ImageOverlay
    ov = ImageOverlay(pv._raw_pixmap)
    assert ov._item in ov._scene.items()
    assert not ov._item.pixmap().isNull()
```
（不 `show_overlay`，仅验证构造；冒烟不弹窗。）

- [ ] **Step 6: 运行冒烟，确认通过**

Run: `python -m widgets.resource_tree_widget 2>&1 | grep -v "RuntimeWarning\|not package"`
Expected: `ResourceTreeWidget smoke OK`，退出码 0。

---

### Task 4: 导出 `ImageOverlay`（`widgets/__init__.py`）

**Files:**
- Modify: `widgets/__init__.py`

- [ ] **Step 1: 加导出**

把 `widgets/__init__.py` 改为（暂不含 `VariableTreeWidget`，下个任务加）：

```python
from .step_io_widget import StepIOWidget
from .resource_tree_widget import ResourceTreeWidget
from .log_widget import LogWidget
from .image_overlay import ImageOverlay

__all__ = ["StepIOWidget", "ResourceTreeWidget", "LogWidget", "ImageOverlay"]
```

- [ ] **Step 2: 验证导入**

Run: `python -c "from widgets import ImageOverlay; print('ok')"`
Expected: `ok`，退出码 0。

---

### Task 5: 变量管理树 `widgets/variable_tree_widget.py`（新）

**Files:**
- Create: `widgets/variable_tree_widget.py`

- [ ] **Step 1: 写完整模块**

把以下内容写入 `widgets/variable_tree_widget.py`：

```python
# -*- coding: utf-8 -*-
"""
全局变量管理树（GUI 控件）
========================

:class:`VariableTreeWidget` 继承 :class:`QTreeWidget`，管理
:class:`model.variable_tree.VariableTree`（存于工程 ``variables.json``）。左树 +
:class:`VariableEditPanel` 中编辑卡，按变量类型生成专属编辑器（预留接口），
实时校验、禁用提交非法值；image 类变量经资源选择器改值。

基本用法
--------
::

    from model import KscpPackage
    from widgets import VariableTreeWidget
    tree = VariableTreeWidget(pkg)
    tree.preview_widget()   # 编辑卡
"""

from __future__ import annotations

import json
from typing import Any, Callable, Dict, List, Optional, Tuple

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import (
    QAbstractItemView, QComboBox, QDialog, QDialogButtonBox, QFrame,
    QHBoxLayout, QInputDialog, QLabel, QLineEdit, QMessageBox, QShortcut,
    QStackedWidget, QStyle, QToolButton, QTreeWidget, QTreeWidgetItem,
    QVBoxLayout, QWidget,
)

from model.kscp_package import KscpPackage
from model.log_model import LogModel
from model.project_variable import ProjectVariable
from model.variable_tree import VariableTree

__all__ = ["VariableTreeWidget", "VariableEditPanel", "CreateVariableDialog"]

_PATH_ROLE = 0x0100


# ----------------------------------------------------------------
# 类型编辑器注册表（预留接口）
# ----------------------------------------------------------------
VAR_EDITORS: Dict[str, Callable[[ProjectVariable, KscpPackage, Callable[[Any], None]],
                                QWidget]] = {}


def register_editor(vtype: str,
                    fn: Callable[[ProjectVariable, KscpPackage, Callable[[Any], None]],
                                 QWidget]) -> None:
    """注册某类型的专属编辑器生成函数（预留接口）。"""
    VAR_EDITORS[vtype] = fn


# ----------------------------------------------------------------
# 变量树（左）
# ----------------------------------------------------------------
class VariableTreeWidget(QTreeWidget):
    """管理 VariableTree 的 QTreeWidget。"""

    var_selected = __import__("PyQt5").QtCore.pyqtSignal(str)

    def __init__(self, package: KscpPackage,
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._package = package
        self._tree: Optional[VariableTree] = None
        self._edit_panel: Optional[VariableEditPanel] = None

        self.setHeaderHidden(True)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setUniformRowHeights(True)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._on_context_menu)
        self.currentItemChanged.connect(self._on_current_changed)

        QShortcut("F2", self, self._act_rename)
        QShortcut("Del", self, self._act_delete)

        self._load()
        self.refresh()

    # ---- IO ----
    def _load(self) -> None:
        if self._package.exists("variables.json"):
            raw = self._package.read_file("variables.json")
            self._tree = VariableTree.from_json(raw, self._package)
            n = len(self._tree)
        else:
            self._tree = VariableTree.create_empty()
            self._save()
            n = 0
        LogModel.instance().info("载入变量树：%d 个变量" % n)

    def _save(self) -> None:
        assert self._tree is not None
        self._package.write_file("variables.json", self._tree.to_json_bytes())
        LogModel.instance().info("变量已保存（%d 个变量）" % len(self._tree))

    # ---- 树构建 ----
    def refresh(self, current_path: Optional[str] = None) -> None:
        assert self._tree is not None
        expanded = set(self._expanded_paths())
        cur = current_path if current_path is not None else self._current_path()
        self.blockSignals(True)
        self.clear()
        root = self.invisibleRootItem()
        if root is not None:
            self._fill(root, "")
        for it in self._walk_items():
            p = it.data(0, _PATH_ROLE)
            if p in expanded:
                it.setExpanded(True)
        target = self._find_item(cur)
        if target is not None:
            self.setCurrentItem(target)
        self.blockSignals(False)
        self._on_current_changed(self.currentItem(), None)

    def _fill(self, parent_item: QTreeWidgetItem, prefix: str) -> None:
        assert self._tree is not None
        names = list(self._tree.list_dir(prefix or "/"))
        style = self.style()

        def child_of(n: str) -> str:
            return (prefix + "/" + n) if prefix else n

        dirs, files = [], []
        for n in names:
            (dirs if self._tree.is_group(child_of(n)) else files).append(n)
        dirs.sort()
        files.sort()
        for name in dirs + files:
            child = child_of(name)
            item = QTreeWidgetItem(parent_item)
            item.setText(0, name)
            item.setData(0, _PATH_ROLE, child)
            if self._tree.is_variable(child):
                var = self._tree.get(child)
                item.setText(0, "%s  [%s]" % (name, var.type))
                if not var.valid:
                    item.setForeground(0, __import__("PyQt5").QtGui.QColor("#e15554"))
                if style is not None:
                    item.setIcon(0, style.standardIcon(QStyle.SP_FileIcon))
            else:
                if style is not None:
                    item.setIcon(0, style.standardIcon(QStyle.SP_DirIcon))
                self._fill(item, child)

    def _walk_items(self):
        def rec(item):
            for i in range(item.childCount()):
                ch = item.child(i)
                if ch is None:
                    continue
                yield ch
                yield from rec(ch)
        root = self.invisibleRootItem()
        if root is not None:
            yield from rec(root)

    def _find_item(self, path: Optional[str]) -> Optional[QTreeWidgetItem]:
        if not path:
            return None
        for it in self._walk_items():
            if it.data(0, _PATH_ROLE) == path:
                return it
        return None

    def _expanded_paths(self) -> List[str]:
        return [it.data(0, _PATH_ROLE) for it in self._walk_items() if it.isExpanded()]

    def _current_path(self) -> str:
        cur = self.currentItem()
        return cur.data(0, _PATH_ROLE) if cur is not None else ""

    # ---- 选中 ----
    def _on_current_changed(self, cur, _prev) -> None:
        path = cur.data(0, _PATH_ROLE) if cur is not None else ""
        if path:
            self.var_selected.emit(path)
        if self._edit_panel is not None:
            self._edit_panel.load(path)

    # ---- 菜单 ----
    def _on_context_menu(self, pos) -> None:
        item = self.itemAt(pos)
        if item is not None and not item.isSelected():
            self.setCurrentItem(item)
        menu = __import__("PyQt5").QtWidgets.QMenu(self)
        a_add_var = menu.addAction("添加变量…")
        a_add_group = menu.addAction("添加组…")
        menu.addSeparator()
        a_rename = menu.addAction("重命名\tF2")
        a_delete = menu.addAction("删除\tDel")
        has_sel = self._current_path() != ""
        a_rename.setEnabled(has_sel)
        a_delete.setEnabled(has_sel)
        action = menu.exec_(self.viewport().mapToGlobal(pos))
        if action is a_add_var:
            self._act_add_var()
        elif action is a_add_group:
            self._act_add_group()
        elif action is a_rename:
            self._act_rename()
        elif action is a_delete:
            self._act_delete()

    # ---- 操作 ----
    def _act_add_var(self) -> None:
        assert self._tree is not None
        parent_path = self._group_of(self.currentItem())
        dlg = CreateVariableDialog(self._package, self._tree, parent_path, self)
        path, var = dlg.make()
        if path is None or var is None:
            LogModel.instance().debug("创建变量对话框取消")
            return
        try:
            self._tree.add(path, var)
        except (FileExistsError, ValueError) as e:
            LogModel.instance().warning("变量 %s 值不合规，已阻止：%s" % (path, e))
            QMessageBox.warning(self, "添加变量", "无法添加：%s" % e)
            return
        self._save()
        self.refresh(path)
        LogModel.instance().info("添加变量 %s（%s）" % (path, var.type))

    def _act_add_group(self) -> None:
        assert self._tree is not None
        parent_path = self._group_of(self.currentItem())
        name, ok = QInputDialog.getText(self, "添加组", "组名：")
        if not ok:
            return
        name = name.strip()
        if not name or "/" in name or name in (".", ".."):
            QMessageBox.warning(self, "添加组", "名称非法")
            return
        path = (parent_path + "/" + name) if parent_path else name
        try:
            self._tree.add_group(path)
        except (FileExistsError, ValueError) as e:
            QMessageBox.warning(self, "添加组", "无法添加：%s" % e)
            return
        self._save()
        self.refresh(path)
        LogModel.instance().info("添加分组 %s" % path)

    def _act_rename(self) -> None:
        assert self._tree is not None
        old = self._current_path()
        if not old:
            return
        parent, name = (old.rsplit("/", 1) + [""]) if "/" not in old else old.rsplit("/", 1)
        if "/" not in old:
            parent = ""
            name = old
        else:
            parent, name = old.rsplit("/", 1)
        new_name, ok = QInputDialog.getText(self, "重命名", "新名称：", text=name)
        if not ok:
            return
        new_name = new_name.strip()
        if not new_name or "/" in new_name or new_name in (".", ".."):
            QMessageBox.warning(self, "重命名", "名称非法")
            return
        new_path = (parent + "/" + new_name) if parent else new_name
        if new_path == old:
            return
        try:
            self._tree.move(old, new_path)
        except (FileExistsError, FileNotFoundError, ValueError) as e:
            QMessageBox.warning(self, "重命名", "无法重命名：%s" % e)
            return
        self._save()
        self.refresh(new_path)
        LogModel.instance().info("移动变量 %s → %s" % (old, new_path))

    def _act_delete(self) -> None:
        assert self._tree is not None
        path = self._current_path()
        if not path:
            return
        if QMessageBox.question(self, "删除", "确定删除 %s？" % path,
                                QMessageBox.Yes | QMessageBox.No,
                                QMessageBox.Yes) != QMessageBox.Yes:
            return
        try:
            self._tree.remove(path)
        except FileNotFoundError as e:
            QMessageBox.warning(self, "删除", "无法删除：%s" % e)
            return
        self._save()
        self.refresh()
        LogModel.instance().info("删除变量 %s" % path)

    def _group_of(self, item: Optional[QTreeWidgetItem]) -> str:
        """item 所在分组路径：item 是变量则取其父分组；item 是分组则取自身。"""
        assert self._tree is not None
        if item is None:
            return ""
        p = item.data(0, _PATH_ROLE)
        if not p:
            return ""
        if self._tree.is_variable(p):
            return p.rsplit("/", 1)[0] if "/" in p else ""
        return p

    # ---- 预览 ----
    def preview_widget(self) -> "VariableEditPanel":
        if self._edit_panel is None:
            self._edit_panel = VariableEditPanel(self._package, self._tree, self)
            self._edit_panel.load(self._current_path())
        return self._edit_panel


# ----------------------------------------------------------------
# 编辑卡（中）
# ----------------------------------------------------------------
class VariableEditPanel(QStackedWidget):
    """按变量类型生成编辑器，实时校验、禁用提交非法值。"""

    def __init__(self, package: KscpPackage,
                 tree: Optional[VariableTree],
                 tree_widget: VariableTreeWidget,
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._package = package
        self._tree = tree
        self._tree_widget = tree_widget
        self._path: str = ""
        self._cur_value: Any = None

        self._placeholder = QLabel("选择一个变量以编辑")
        self._placeholder.setAlignment(Qt.AlignCenter)
        self._placeholder.setStyleSheet("color:#999; font-size:14px;")
        self._editor_host = QWidget()
        self._host_lay = QVBoxLayout(self._editor_host)
        self._host_lay.setContentsMargins(8, 8, 8, 8)
        self._host_lay.setSpacing(6)
        self._header = QLabel("")
        self._header.setStyleSheet("font-weight:bold;")
        self._editor_slot = QWidget()
        self._editor_slot_lay = QVBoxLayout(self._editor_slot)
        self._editor_slot_lay.setContentsMargins(0, 0, 0, 0)
        self._status = QLabel("")
        self._status.setWordWrap(True)
        self._btns = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Reset)
        self._btns.button(QDialogButtonBox.Save).setText("确认")
        self._btns.button(QDialogButtonBox.Reset).setText("还原")
        self._btns.accepted.connect(self._on_save)
        self._btns.rejected.connect(self._on_reset)
        self._host_lay.addWidget(self._header)
        self._host_lay.addWidget(self._editor_slot)
        self._host_lay.addStretch()
        self._host_lay.addWidget(self._status)
        self._host_lay.addWidget(self._btns)

        self._unsupported = QLabel("该类型暂不支持可视化编辑")
        self._unsupported.setAlignment(Qt.AlignCenter)
        self._unsupported.setStyleSheet("color:#999;")

        self.addWidget(self._placeholder)     # 0
        self.addWidget(self._editor_host)     # 1
        self.addWidget(self._unsupported)    # 2

    def load(self, path: str) -> None:
        self._path = path
        assert self._tree is not None
        if not path or not self._tree.is_variable(path):
            self.setCurrentIndex(0)
            return
        var = self._tree.get(path)
        self._cur_value = var.data
        self._header.setText("%s  ·  %s%s" % (
            path, var.type, "  ·  无效" if not var.valid else ""))
        fn = VAR_EDITORS.get(var.type)
        # 清空旧编辑器
        while self._editor_slot_lay.count():
            w = self._editor_slot_lay.takeAt(0).widget()
            if w is not None:
                w.deleteLater()
        if fn is None:
            self.setCurrentIndex(2)
            return
        editor = fn(var, self._package, self._on_changed)
        self._editor_slot_lay.addWidget(editor)
        self._validate()
        self.setCurrentIndex(1)

    def _on_changed(self, value: Any) -> None:
        self._cur_value = value
        self._validate()

    def _validate(self) -> None:
        assert self._tree is not None
        if not self._path or not self._tree.is_variable(self._path):
            self._btns.button(QDialogButtonBox.Save).setEnabled(False)
            return
        var = self._tree.get(self._path)
        try:
            cand = ProjectVariable.create(var.type, self._cur_value, self._package)
            ok = cand.valid
        except (ValueError, TypeError) as e:
            ok = False
            self._status.setText("值不合规：%s" % e)
        if ok:
            self._status.setText("可保存")
            self._status.setStyleSheet("color:#27ae60;")
        else:
            self._status.setStyleSheet("color:#e15554;")
        self._btns.button(QDialogButtonBox.Save).setEnabled(ok)

    def _on_save(self) -> None:
        assert self._tree is not None
        if not self._path or not self._tree.is_variable(self._path):
            return
        var = self._tree.get(self._path)
        try:
            new_var = ProjectVariable.create(var.type, self._cur_value, self._package)
        except (ValueError, TypeError) as e:
            LogModel.instance().warning("变量 %s 值不合规，已阻止：%s" % (self._path, e))
            return
        if not new_var.valid:
            LogModel.instance().warning("变量 %s 值不合规，已阻止" % self._path)
            return
        self._tree.set(self._path, new_var)
        self._tree_widget._save()
        self._tree_widget.refresh(self._path)
        LogModel.instance().info("修改变量 %s" % self._path)

    def _on_reset(self) -> None:
        self.load(self._path)


# ----------------------------------------------------------------
# 内置编辑器
# ----------------------------------------------------------------
def _string_editor(var: ProjectVariable, package: KscpPackage,
                   on_changed: Callable[[Any], None]) -> QWidget:
    w = QWidget()
    lay = QVBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    edit = QLineEdit(str(var.data) if var.data is not None else "")
    edit.textChanged.connect(on_changed)
    lay.addWidget(QLabel("字符串值："))
    lay.addWidget(edit)
    on_changed(edit.text())
    return w


def _number_editor(var: ProjectVariable, package: KscpPackage,
                   on_changed: Callable[[Any], None]) -> QWidget:
    w = QWidget()
    lay = QVBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    edit = QLineEdit(str(var.data) if var.data is not None else "")
    edit.textChanged.connect(on[1])  # 见下方说明，此处应调 on_changed
    lay.addWidget(QLabel("数值（整数或小数）："))
    lay.addWidget(edit)

    def _on(text: str) -> None:
        try:
            on_changed(int(text))
        except ValueError:
            try:
                on_changed(float(text))
            except ValueError:
                on_changed(text)   # 非数值字符串，校验会判非法
    edit.textChanged.disconnect()
    edit.textChanged.connect(_on)
    _on(edit.text())
    return w


def _image_editor(var: ProjectVariable, package: KscpPackage,
                   on_changed: Callable[[Any], None]) -> QWidget:
    w = QWidget()
    lay = QVBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    from widgets.resource_tree_widget import ResourceTreeWidget
    from widgets.image_overlay import ImageOverlay

    thumb = QLabel()
    thumb.setAlignment(Qt.AlignCenter)
    thumb.setMinimumHeight(120)
    thumb.setStyleSheet("background:#1e1e1e;")

    def _refresh_thumb(path: str) -> None:
        if path and package.is_file(path):
            pix = QPixmap()
            pix.loadFromData(package.read_file(path))
            thumb.setPixmap(pix.scaled(200, 120, Qt.KeepAspectRatio,
                                       Qt.SmoothTransformation))
        else:
            thumb.setText("（无预览）")

    path_lbl = QLabel(str(var.data) if var.data else "（未选资源）")
    path_lbl.setWordWrap(True)
    _refresh_thumb(str(var.data) if var.data else "")

    def _pick() -> None:
        p = ResourceTreeWidget.pick_resource(package, tuple(var.suffixes), w)
        if p is None:
            LogModel.instance().debug("选择资源取消")
            return
        path_lbl.setText(p)
        _refresh_thumb(p)
        on_changed(p)

    btn = QPushButton("选择资源…")
    btn.clicked.connect(_pick)
    lay.addWidget(thumb)
    lay.addWidget(path_lbl)
    lay.addWidget(btn)
    on_changed(var.data)
    return w


# 注册内置编辑器
register_editor("string", _string_editor)
register_editor("number", _number_editor)
register_editor("image", _image_editor)


# ----------------------------------------------------------------
# 创建对话框
# ----------------------------------------------------------------
class CreateVariableDialog(QDialog):
    """选类型（带描述）+ 名称 + 值，实时校验，禁用创建非法变量。"""

    def __init__(self, package: KscpPackage, tree: VariableTree,
                 parent_group: str = "", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("创建变量")
        self.resize(420, 360)
        self._package = package
        self._tree = tree
        self._parent_group = parent_group
        self._cur_value: Any = None

        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(8)

        # 类型下拉（name — description）
        self._type_combo = QComboBox()
        for name in ProjectVariable.supported_types():
            h = ProjectVariable.type_of(name)
            desc = h.description if h is not None else ""
            self._type_combo.addItem("%s — %s" % (name, desc), name)
        self._type_combo.currentIndexChanged.connect(self._on_type_changed)
        lay.addWidget(QLabel("类型："))
        lay.addWidget(self._type_combo)

        # 名称
        self._name_edit = QLineEdit()
        self._name_edit.textChanged.connect(self._validate)
        lay.addWidget(QLabel("名称："))
        lay.addWidget(self._name_edit)

        # 目标分组
        self._group_combo = QComboBox()
        self._group_combo.addItem("（根）", "")
        for g in tree.groups:
            self._group_combo.addItem(g, g)
        if parent_group:
            idx = self._group_combo.findData(parent_group)
            if idx >= 0:
                self._group_combo.setCurrentIndex(idx)
        lay.addWidget(QLabel("目标分组："))
        lay.addWidget(self._group_combo)

        # 编辑器槽
        self._slot = QWidget()
        self._slot_lay = QVBoxLayout(self._slot)
        self._slot_lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self._slot)
        lay.addStretch()

        self._status = QLabel("")
        self._status.setWordWrap(True)
        lay.addWidget(self._status)

        self._btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self._btns.button(QDialogButtonBox.Ok).setText("创建")
        self._btns.accepted.connect(self.accept)
        self._btns.rejected.connect(self.reject)
        lay.addWidget(self._btns)

        self._on_type_changed(0)

    def _on_type_changed(self, _idx: int) -> None:
        vtype = self._type_combo.currentData()
        # 清空旧编辑器
        while self._slot_lay.count():
            w = self._slot_lay.takeAt(0).widget()
            if w is not None:
                w.deleteLater()
        default = {"string": "", "number": "0"}.get(vtype, "")
        var = ProjectVariable.create(vtype, default, self._package)
        fn = VAR_EDITORS.get(vtype)
        if fn is not None:
            editor = fn(var, self._package, self._on_changed)
            self._slot_lay.addWidget(editor)
        self._cur_value = default
        self._validate()

    def _on_changed(self, value: Any) -> None:
        self._cur_value = value
        self._validate()

    def _validate(self) -> None:
        vtype = self._type_combo.currentData()
        name = self._name_edit.text().strip()
        group = self._group_combo.currentData()
        path = (group + "/" + name) if group else name
        ok = True
        reason = ""
        if not name or "/" in name or name in (".", ".."):
            ok = False
            reason = "名称非法"
        elif self._tree.exists(path):
            ok = False
            reason = "名称已存在：%s" % path
        else:
            try:
                cand = ProjectVariable.create(vtype, self._cur_value, self._package)
                if not cand.valid:
                    ok = False
                    reason = "值不合规"
            except (ValueError, TypeError) as e:
                ok = False
                reason = "值不合规：%s" % e
        self._btns.button(QDialogButtonBox.Ok).setEnabled(ok)
        if ok:
            self._status.setText("可创建")
            self._status.setStyleSheet("color:#27ae60;")
        else:
            self._status.setText(reason)
            self._status.setStyleSheet("color:#e15554;")

    def make(self) -> Tuple[Optional[str], Optional[ProjectVariable]]:
        """exec 后返回 (path, var)；取消返回 (None, None)。"""
        if self.exec_() != QDialog.Accepted:
            return None, None
        vtype = self._type_combo.currentData()
        name = self._name_edit.text().strip()
        group = self._group_combo.currentData()
        path = (group + "/" + name) if group else name
        try:
            var = ProjectVariable.create(vtype, self._cur_value, self._package)
        except (ValueError, TypeError):
            return None, None
        if not var.valid:
            return None, None
        LogModel.instance().info("创建变量 %s（%s）" % (path, vtype))
        return path, var


if __name__ == "__main__":
    import sys
    from PyQt5.QtWidgets import QApplication
    from PyQt5.QtGui import QColor, QImage
    from PyQt5.QtCore import QBuffer

    app = QApplication.instance() or QApplication(sys.argv)

    def _png(color):
        img = QImage(40, 30, QImage.Format_RGB32)
        img.fill(QColor(color))
        buf = QBuffer(); buf.open(QBuffer.ReadWrite)
        img.save(buf, "PNG")
        return bytes(buf.data())

    pkg = KscpPackage.create_empty()
    pkg.write_file("assets/a.png", _png("#3a7bd5"))
    pkg.write_file("assets/b.txt", b"hi")

    # 注入变量树
    pkg.write_file("variables.json", VariableTree.create_empty().to_json_bytes())
    tree = VariableTreeWidget(pkg)
    t = tree._tree
    assert t is not None
    t.add("s", ProjectVariable.create("string", "hello", pkg))
    t.add("n", ProjectVariable.create("number", 42, pkg))
    t.add_group("组1")
    t.add("组1/p", ProjectVariable.create("image", "assets/a.png", pkg))
    tree.refresh()

    # 顶层：分组在上、变量在下
    top = [tree.topLevelItem(i).text(0) for i in range(tree.topLevelItemCount())]
    assert top[0].startswith("组1"), top
    assert any(x.startswith("s") for x in top), top

    # 编辑卡加载
    ep = tree.preview_widget()
    tree.setCurrentItem(tree._find_item("组1/p"))
    assert ep.currentIndex() == 1   # image 编辑器页

    # string 编辑器改值并确认
    tree.setCurrentItem(tree._find_item("s"))
    assert ep.currentIndex() == 1
    # 模拟改值：直接调内部
    ep._cur_value = "world"
    assert ep._btns.button(QDialogButtonBox.Save).isEnabled()
    ep._on_save()
    assert tree._tree.get("s").data == "world"

    # 创建对话框：选 string、给名、确认
    cd = CreateVariableDialog(pkg, tree._tree, "", None)
    cd._type_combo.setCurrentIndex(0)   # string
    cd._name_edit.setText("newvar")
    # string 编辑器初值为 ""，非法（空串）→ 创建应禁用；改一个值
    le = cd.findChild(QLineEdit)
    assert le is not None
    le.setText("val")
    assert cd._btns.button(QDialogButtonBox.Ok).isEnabled()
    # 非法名称
    cd._name_edit.setText("a/b")
    assert not cd._btns.button(QDialogButtonBox.Ok).isEnabled()

    print("VariableTreeWidget smoke OK")
```

> **实现注意**（写代码时务必修正）：上面 `_number_editor` 草稿里有一处占位笔误 `edit.textChanged.connect(on[1])`，正确应为不连该行（下方已 `disconnect()` 并重连 `_on`）。最终代码里 `_number_editor` 只保留：创建 edit → 连 `textChanged` 到 `_on` → `_on` 内尝试 int/float/否则原样回传 → 末尾 `_on(edit.text())`。请按此修正，不要保留 `on[1]` 那行。另外 `var_selected` 信号用 `__import__("PyQt5").QtCore.pyqtSignal(str)` 是为了不补 import；更干净的做法是在顶部 `from PyQt5.QtCore import pyqtSignal` 后直接 `var_selected = pyqtSignal(str)` —— 实现时采用后者（顶部 import 区加 `pyqtSignal`）。

- [ ] **Step 2: 修正实现笔误并定稿**

按上面「实现注意」修正：
1. 顶部 import：`from PyQt5.QtCore import Qt, pyqtSignal`，`var_selected = pyqtSignal(str)`（去掉 `__import__` 写法）。
2. 菜单里 `__import__("PyQt5").QtWidgets.QMenu(self)` 改为顶部 `from PyQt5.QtWidgets import QMenu` 后直接用 `QMenu(self)`；`QColor` 同理顶部 `from PyQt5.QtGui import QColor` 后用 `QColor(...)`。
3. `_number_editor` 删掉 `edit.textChanged.connect(on[1])` 那行，仅保留 `edit.textChanged.connect(_on)` 与末尾 `_on(edit.text())`。
4. `_image_editor` 顶部已 `from widgets.resource_tree_widget import ResourceTreeWidget`；`QPushButton` 需在顶部 QtWidgets import 中（当前列表缺 `QPushButton`，补上）。
5. 顶部 QtWidgets import 列表补全：`QInputDialog`（已用）、`QMenu`、`QPushButton`、`QLineEdit`（已用）等，确保都齐。

最终顶部 import 段：
```python
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QColor, QPixmap
from PyQt5.QtWidgets import (
    QAbstractItemView, QComboBox, QDialog, QDialogButtonBox, QInputDialog,
    QLabel, QLineEdit, QMenu, QMessageBox, QPushButton, QShortcut,
    QStackedWidget, QStyle, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)
```

- [ ] **Step 3: 运行冒烟，确认通过**

Run: `python -m widgets.variable_tree_widget 2>&1 | grep -v "RuntimeWarning\|not package"`
Expected: `VariableTreeWidget smoke OK`，退出码 0。

- [ ] **Step 4: 导出 `VariableTreeWidget`（`widgets/__init__.py`）**

把 `widgets/__init__.py` 改为：

```python
from .step_io_widget import StepIOWidget
from .resource_tree_widget import ResourceTreeWidget
from .log_widget import LogWidget
from .image_overlay import ImageOverlay
from .variable_tree_widget import VariableTreeWidget

__all__ = ["StepIOWidget", "ResourceTreeWidget", "LogWidget",
           "ImageOverlay", "VariableTreeWidget"]
```

Run: `python -c "from widgets import VariableTreeWidget; print('ok')"`
Expected: `ok`，退出码 0。

---

### Task 6: 主窗口接入真实变量管理树

**Files:**
- Modify: `widgets/main_widget.py`

- [ ] **Step 1: 加 `VariableManagementTree` 类 + imports**

在 `widgets/main_widget.py` 顶部 import 区加：

```python
from widgets.log_widget import LogWidget
from widgets.variable_tree_widget import VariableTreeWidget
```

在 `ResourceManagementTree` 类之后、`PlaceholderManagementTree` 之前，加：

```python
class VariableManagementTree(ManagementTree):
    """变量管理树：``VariableTreeWidget`` + 其编辑卡。"""

    def __init__(self, package: KscpPackage) -> None:
        super().__init__("变量")
        self._package = package
        self._vtree: Optional[VariableTreeWidget] = None

    def icon(self) -> QIcon:
        return _make_icon("variable")

    def tree_widget(self) -> QWidget:
        if self._vtree is None:
            self._vtree = VariableTreeWidget(self._package)
        assert self._vtree is not None
        return self._vtree

    def preview_widget(self) -> QWidget:
        if self._vtree is None:
            self._vtree = VariableTreeWidget(self._package)
        assert self._vtree is not None
        if self._preview is None:
            self._preview = self._vtree.preview_widget()
        assert self._preview is not None
        return self._preview
```

- [ ] **Step 2: `_open_package` 换占位为真实**

在 `_open_package` 中把 managers 列表：
```python
        self._managers = [
            ResourceManagementTree(package),
            PlaceholderManagementTree("变量", "variable"),
            PlaceholderManagementTree("步骤", "step"),
        ]
```
改为：
```python
        self._managers = [
            ResourceManagementTree(package),
            VariableManagementTree(package),
            PlaceholderManagementTree("步骤", "step"),
        ]
```

- [ ] **Step 3: 运行自检**

Run: `python main.py --check`
Expected: 退出码 0。

Run: `python main.py sample.kscp --check`
Expected: 退出码 0（切到「变量」树渲染编辑卡；sample.kscp 无 variables.json 时建空树并记「载入变量树：0 个变量」日志）。

---

### Task 7: 端到端验证

**Files:** 无（仅运行）

- [ ] **Step 1: 全部冒烟**

Run: `python -m model.project_variable && python -m model.variable_tree && python -m widgets.image_overlay 2>&1 | grep -v "RuntimeWarning\|not package" && python -m widgets.resource_tree_widget 2>&1 | grep -v "RuntimeWarning\|not package" && python -m widgets.variable_tree_widget 2>&1 | grep -v "RuntimeWarning\|not package"`
Expected: 五条 `... smoke OK`，均退出码 0。

- [ ] **Step 2: 主窗口两态**

Run: `python main.py --check && python main.py sample.kscp --check`
Expected: 退出码 0。

- [ ] **Step 3: 手动确认（人工）**

启动 `python main.py sample.kscp`，切到「变量」树：右键添加变量 → 选类型（下拉含描述）→ 输名 → 给值 → 创建；选中变量在右侧编辑卡改值；image 变量点「选择资源…」弹资源选择器。日志栏全程有详细记录，状态栏错误/警告计数联动。

---

## 自检（Self-Review）

**1. 规格覆盖：**
- 图片遮罩预览（item 1）→ Task 2 `ImageOverlay` + Task 3 资源树改用遮罩 ✓
- 变量管理树 + 按类型生成 GUI + 预留接口（item 2）→ Task 5 `VAR_EDITORS`/`register_editor` + 三内置编辑器 ✓
- 资源类变量只能检索工程资源选中后改（item 2）→ Task 3 `pick_resource` + Task 5 `_image_editor` 仅按钮无手输 ✓
- 视图内容美观 → 编辑卡带 header/状态/按钮样式、缩略图 ✓
- 接入主界面（item 3）→ Task 6 `VariableManagementTree` + `_open_package` ✓
- 创建对话框 + 类型描述（item 4）→ Task 5 `CreateVariableDialog` + Task 1 `description` ✓
- 无法创建不合规变量（item 5）→ 创建对话框与编辑卡均实时校验、禁用按钮 ✓
- 详细日志（item 6）→ Task 5 各操作 `LogModel` 记录 + Task 6 载入日志 ✓
- `png`→`image` + `description` → Task 1 ✓

**2. 占位符扫描：** Task 5 Step1 代码含一处明确标注的笔误（`on[1]`），已在 Step 2 显式要求修正，非遗留占位；其余无 TBD/TODO。

**3. 类型一致性：**
- `VariableType.description`（Task 1）↔ `CreateVariableDialog` 读 `h.description`（Task 5）✓
- `ProjectVariable.create/type_of/supported_types/is_resource/suffixes` 全程一致 ✓
- `VariableTree.from_json/to_json_bytes/add/set/add_group/remove/move/get/is_variable/is_group/list_dir/groups/exists` 与 Task 5 调用一致 ✓
- `ResourceTreeWidget.pick_resource(package, suffixes, parent)`（Task 3）↔ `_image_editor` 调 `pick_resource(package, tuple(var.suffixes), w)`（Task 5）✓
- `ImageOverlay(pixmap, parent).show_overlay()`（Task 2）↔ Task 3 `_PreviewPanel._open_image_dialog` 调法一致 ✓
- `var_selected = pyqtSignal(str)`（Task 5 定稿）✓
- `VariableEditPanel.load(path)` / `_on_changed` / `_validate` / `_on_save` 内部一致 ✓
