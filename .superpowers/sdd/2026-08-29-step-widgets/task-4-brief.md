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
### Task 4: `StepListView` + `TemplateChooserDialog` + `StepClipboard` — 步骤列表视图

**Files:**
- Create: `widgets/step_list_view.py`

**Interfaces:**
- Consumes: T1 的 `StepList.insert_format_strings(index, fmts, mgr)`；T3 的 `StepCard`（`menu_requested(自身, 全局坐标)`、`set_selected`、`refresh`）；`StepManager.template_paths()` / `create_step(path)`；`StepList` 的 `add/insert/remove/__len__/__getitem__/to_format_string`
- Produces（T5 管理树、T7 宿主消费）:
  - `StepClipboard` —— `steps: Optional[List[str]]`（步骤格式串）+ `items: Optional[tuple]`（`(名, 三元组列表)`，T5 用）
  - `TemplateChooserDialog(mgr, parent)` —— `selected_path() -> Optional[str]`；`exec_()` 正常可用
  - `StepListView(mgr, clipboard, parent)` —— `set_list(step_list, mgr=None)` / `refresh()` / `refresh_validity()` / `edited = pyqtSignal()`；`_cards` / `_proxies` / `_hint`（冒烟断言用）

- [ ] **Step 1: 写失败测试**——新文件先只写文件头 + 冒烟块（类未定义 → 红）：

```python
# -*- coding: utf-8 -*-
"""
步骤列表视图（GUI 控件）
======================

:class:`StepListView` 是「步骤列表」（:class:`model.step_list.StepList`）的
可视化视图（QGraphicsView）：横向排布 :class:`StepCard` 卡片
（QGraphicsProxyWidget），滚轮横向滚动，悬停卡片平滑放大（1.06 倍），
右键菜单支持 添加（头部/尾部/前方/后方，经 :class:`TemplateChooserDialog`
模板树选择）/ 复制 / 剪切 / 粘贴 / 删除。

**步骤剪贴板**（:class:`StepClipboard`）：步骤格式串列表，跨列表切换存活，
由宿主（管理树）持有并注入；剪切后剪贴板保留（剪切 = 复制 + 删除，
允许多次粘贴）。

基本用法
--------
::

    view = StepListView(mgr, clipboard)
    view.set_list(step_list, mgr)   # 绑定列表并重建卡片
    view.refresh()                  # 重建（顺序/内容变化后）
    view.refresh_validity()         # 仅重检颜色（变量树变化后）
"""

if __name__ == "__main__":
    import sys

    from PyQt5.QtCore import QEvent, QPoint, QPointF, Qt
    from PyQt5.QtGui import QWheelEvent
    from PyQt5.QtWidgets import QApplication, QDialog, QMessageBox

    from actions.base import Step
    from model.kscp_package import KscpPackage
    from model.project_variable import ProjectVariable
    from model.step_list import StepList
    from model.step_list_store import StepListStore
    from model.step_manager import StepManager
    from model.variable_tree import VariableTree

    app = QApplication.instance() or QApplication(sys.argv)

    pkg = KscpPackage.create_empty()
    tree = VariableTree.create_empty()
    tree.add("n1", ProjectVariable.create("number", 100, pkg))

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
    pkg.write_file("actions/示例.py", GOOD.encode("utf-8"))
    pkg.write_file("actions/控制流程/延时.py",
                   GOOD.replace('name = "示例"', 'name = "延时"'))
    mgr = StepManager(pkg, tree)
    mgr.load()

    def make_step() -> Step:
        s = mgr.create_step("示例")
        s.io.change_value("input", 0, "5")
        s.io.change_value("output", 0, "n1")
        return s

    # 装配 store + 列表
    store = StepListStore.create_empty()
    sl = StepList.create_empty()
    sl.add(make_step())
    sl.add(make_step())
    store.add_list("主列表", sl)
    sl2 = StepList.create_empty()
    store.add_list("空列表", sl2)

    clipboard = StepClipboard()
    view = StepListView(mgr, clipboard)
    view.resize(400, 360)
    edited = []
    view.edited.connect(lambda: edited.append(1))

    # 空列表 → 提示项存在、无卡片
    view.set_list(sl2, mgr)
    assert view._cards == [] and view._hint is not None

    # 绑定列表 → 卡片数 = 步骤数
    view.set_list(sl, mgr)
    assert len(view._cards) == 2 and view._hint is None
    assert view._proxies[0].scale() == 1.0

    # 滚轮（垂直增量）→ 水平滚动条移动
    hsb = view.horizontalScrollBar()
    old = hsb.value()
    ev = QWheelEvent(QPointF(10, 10), QPointF(10, 10), QPoint(0, 0),
                     QPoint(0, -240), Qt.NoButton, Qt.NoModifier)
    view.wheelEvent(ev)
    assert hsb.value() != old
    # 事件过滤器：卡片滚轮转发（同一处理路径）
    assert view.eventFilter(view._cards[0], ev) is True

    # 悬停缩放：Enter → 目标放大；Leave → 还原（不启动事件循环，验证动画参数）
    enter = QEvent(QEvent.Enter)
    leave = QEvent(QEvent.Leave)
    view.eventFilter(view._cards[0], enter)
    assert view._anims[0].endValue() == 1.06
    view.eventFilter(view._cards[0], leave)
    assert view._anims[0].endValue() == 1.0

    # 添加（类级补丁模板对话框；头部/尾部/中间）
    orig_exec = TemplateChooserDialog.exec_
    orig_path = TemplateChooserDialog.selected_path
    TemplateChooserDialog.exec_ = lambda self: QDialog.Accepted
    TemplateChooserDialog.selected_path = lambda self: "示例"
    try:
        view._add_step(0)                      # 头部
        assert len(sl) == 3 and sl[0].name == "示例"
        view._add_step(-1)                     # 尾部
        assert len(sl) == 4
        view._add_step(2)                      # 中间（前方/后方同路径）
        assert len(sl) == 5
    finally:
        TemplateChooserDialog.exec_ = orig_exec
        TemplateChooserDialog.selected_path = orig_path
    assert edited == [1, 1, 1]                 # 每次添加发 edited

    # 复制 → 剪贴板；粘贴 → 插入指定位置（后方）
    view._copy(0)
    assert clipboard.steps == [sl[0].to_format_string()]
    before = len(sl)
    view._paste(1)
    assert len(sl) == before + 1
    assert sl[1].to_format_string() == clipboard.steps[0]

    # 剪切 = 复制 + 删除（补丁确认框；剪贴板保留）
    orig_q = QMessageBox.question
    QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)
    try:
        n = len(sl)
        view._copy(2)
        view._delete_step(2)
        assert len(sl) == n - 1
        assert clipboard.steps is not None          # 剪贴板保留（可再次粘贴）
        view._paste(2)
        assert len(sl) == n
    finally:
        QMessageBox.question = orig_q

    # refresh_validity：不重建（卡片数不变）
    ncards = len(view._cards)
    view.refresh_validity()
    assert len(view._cards) == ncards

    # TemplateChooserDialog：分组 + 叶子 UserRole = 路径（不 exec）
    dlg = TemplateChooserDialog(mgr, None)
    top = [dlg._tw.topLevelItem(i).text(0)
           for i in range(dlg._tw.topLevelItemCount())]
    assert top == ["控制流程", "示例"], top
    delay = dlg._tw.topLevelItem(0)
    assert delay is not None and delay.childCount() == 1
    leaf = delay.child(0)
    assert leaf is not None and leaf.data(0, _PATH_ROLE) == "控制流程/延时"
    assert dlg._tw.topLevelItem(1).data(0, _PATH_ROLE) == "示例"
    # 未选叶子 → 添加禁用；选叶子 → 可选
    assert dlg._ok.isEnabled() is False
    dlg._tw.setCurrentItem(leaf)
    assert dlg.selected_path() == "控制流程/延时"
    assert dlg._ok.isEnabled() is True
    # 选组 → accept 被拒（未选叶子）
    dlg._tw.setCurrentItem(delay)
    dlg.accept()
    assert dlg.result() == 0

    print("StepListView smoke OK")
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m widgets.step_list_view`
Expected: RED —— `ImportError: cannot import name 'StepClipboard'`（EXIT=1）

- [ ] **Step 3: 实现**——在冒烟块前补齐完整文件（imports 放模块头）：

```python
from __future__ import annotations

from typing import Dict, List, Optional

from PyQt5.QtCore import (
    QEasingCurve, QEvent, QPointF, Qt, QVariantAnimation, pyqtSignal,
)
from PyQt5.QtGui import QPainter
from PyQt5.QtWidgets import (
    QAbstractItemView, QDialog, QDialogButtonBox, QGraphicsProxyWidget,
    QGraphicsScene, QGraphicsSimpleTextItem, QGraphicsView, QMenu,
    QMessageBox, QStyle, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from model.step_list import StepList
from model.step_manager import StepManager
from widgets.step_card import StepCard

__all__ = ["StepClipboard", "StepListView", "TemplateChooserDialog"]

_PATH_ROLE = 0x0100   # Qt.UserRole
_CARD_GAP = 16        # 卡片间距
_SCALE_MAX = 1.06     # 悬停放大倍数


class StepClipboard:
    """步骤 / 列表剪贴板（纯数据；跨视图与列表存活）。"""

    def __init__(self) -> None:
        self.steps: Optional[List[str]] = None          # 步骤格式串
        self.items: Optional[tuple] = None              # (名, 三元组列表)；列表/组剪贴板


class TemplateChooserDialog(QDialog):
    """添加步骤：模板树选择。按文件夹分组展示全部已注册模板，叶子才可确定。"""

    def __init__(self, mgr: StepManager,
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("选择步骤模板")
        self.resize(360, 420)
        self._path: Optional[str] = None
        self._mgr = mgr
        lay = QVBoxLayout(self)
        self._tw = QTreeWidget()
        self._tw.setHeaderHidden(True)
        self._tw.setSelectionMode(QAbstractItemView.SingleSelection)
        self._tw.itemDoubleClicked.connect(lambda *_: self.accept())
        self._tw.currentItemChanged.connect(lambda *_: self._update_ok())
        lay.addWidget(self._tw)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self._ok = btns.button(QDialogButtonBox.Ok)
        self._ok.setText("添加")
        self._ok.setEnabled(False)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)
        self._build_tree()

    def selected_path(self) -> Optional[str]:
        """返回选中的模板路径；未选（或选的是组）→ None。"""
        return self._path

    def _build_tree(self) -> None:
        style = self.style()
        root = self._tw.invisibleRootItem()
        if root is None:
            return
        for path in self._mgr.template_paths():
            item = root
            segs = path.split("/")
            for i, seg in enumerate(segs):
                found = None
                for c in range(item.childCount()):
                    ch = item.child(c)
                    if ch is not None and ch.text(0) == seg:
                        found = ch
                        break
                if found is None:
                    found = QTreeWidgetItem(item)
                    found.setText(0, seg)
                    if i < len(segs) - 1 and style is not None:
                        found.setIcon(0, style.standardIcon(QStyle.SP_DirIcon))
                item = found
            item.setData(0, _PATH_ROLE, path)

    def _update_ok(self) -> None:
        it = self._tw.currentItem()
        path = it.data(0, _PATH_ROLE) if it is not None else None
        self._path = path
        self._ok.setEnabled(path is not None)

    def accept(self) -> None:  # noqa: N802 (Qt 命名)
        if self._path is None:
            return                     # 未选叶子 → 不关闭
        super().accept()


class StepListView(QGraphicsView):
    """水平步骤列表视图：卡片横排、滚轮横向滚动、悬停放大、右键菜单。"""

    edited = pyqtSignal()

    def __init__(self, mgr: StepManager, clipboard: StepClipboard,
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._mgr = mgr
        self._clipboard = clipboard
        self._step_list: Optional[StepList] = None
        self._cards: List[StepCard] = []
        self._proxies: List[QGraphicsProxyWidget] = []
        self._anims: Dict[int, QVariantAnimation] = {}
        self._selected: Optional[StepCard] = None
        self._hint: Optional[QGraphicsSimpleTextItem] = None

        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._on_context_menu)
        self.setRenderHint(QPainter.Antialiasing)
        self.refresh()

    # ---- 绑定 / 刷新 ----
    def set_list(self, step_list: Optional[StepList],
                 mgr: Optional[StepManager] = None) -> None:
        """绑定列表并重建卡片；``mgr`` 可选更新（同一实例常可省略）。"""
        self._step_list = step_list
        if mgr is not None:
            self._mgr = mgr
        self.refresh()

    def refresh(self) -> None:
        """按当前列表重建卡片（顺序/内容变化后调用）。"""
        for proxy in self._proxies:
            self._scene.removeItem(proxy)
        self._proxies = []
        self._cards = []
        self._selected = None
        self._anims.clear()
        if self._hint is not None:
            self._scene.removeItem(self._hint)
            self._hint = None
        sl = self._step_list
        if sl is None or len(sl) == 0:
            self._hint = self._scene.addSimpleText(
                "右键添加步骤（或在左侧管理树选择列表）")
            if self._hint is not None:
                self._hint.setPos(24, 24)
            return
        x = 16.0
        for step in sl:
            card = StepCard(step)
            card.menu_requested.connect(self._on_card_menu)
            card.installEventFilter(self)   # 滚轮转发 / 悬停缩放 / 点击选中
            proxy = self._scene.addWidget(card)
            proxy.setPos(QPointF(x, 12.0))
            proxy.setTransformOriginPoint(
                QPointF(card.width() / 2.0, card.height() / 2.0))
            self._cards.append(card)
            self._proxies.append(proxy)
            x += card.width() + _CARD_GAP
        self._scene.setSceneRect(0, 0, x + 16.0, 400.0)

    def refresh_validity(self) -> None:
        """仅重检各卡片颜色（io 校验可能随变量树变化），不重建。"""
        for card in self._cards:
            card.refresh()

    # ---- 滚轮（横向）----
    def wheelEvent(self, event) -> None:  # noqa: N802 (Qt 命名)
        delta = event.angleDelta().y()
        sb = self.horizontalScrollBar()
        sb.setValue(sb.value() - delta)
        event.accept()

    def eventFilter(self, obj, event) -> bool:
        """卡片事件过滤：滚轮转发 / 悬停缩放 / 点击选中。"""
        if event.type() == QEvent.Wheel:
            self.wheelEvent(event)  # type: ignore[arg-type]
            return True
        if obj in self._cards:
            idx = self._cards.index(obj)
            if event.type() == QEvent.Enter:
                self._animate_scale(idx, _SCALE_MAX)
            elif event.type() == QEvent.Leave:
                self._animate_scale(idx, 1.0)
            elif event.type() == QEvent.MouseButtonPress:
                self._select(obj)
        return super().eventFilter(obj, event)

    def _animate_scale(self, idx: int, target: float) -> None:
        proxy = self._proxies[idx]
        old = self._anims.pop(idx, None)
        if old is not None:
            old.stop()
        anim = QVariantAnimation(self)
        anim.setDuration(160)
        anim.setStartValue(proxy.scale())
        anim.setEndValue(target)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.valueChanged.connect(lambda v, p=proxy: p.setScale(float(v)))
        anim.finished.connect(anim.deleteLater)
        proxy.setZValue(1 if target > 1.0 else 0)
        self._anims[idx] = anim
        anim.start()

    def _select(self, card: StepCard) -> None:
        if self._selected is card:
            return
        if self._selected is not None:
            self._selected.set_selected(False)
        self._selected = card
        card.set_selected(True)

    # ---- 右键菜单 ----
    def _on_context_menu(self, pos) -> None:
        card = self._card_at(pos)
        if card is not None:
            self._card_menu(card, pos)
            return
        menu = QMenu(self)
        a_head = menu.addAction("头部添加…")
        a_tail = menu.addAction("尾部添加…")
        menu.addSeparator()
        a_paste = menu.addAction("粘贴")
        a_paste.setEnabled(bool(self._clipboard.steps))
        action = menu.exec_(self.viewport().mapToGlobal(pos))
        if action is a_head:
            self._add_step(0)
        elif action is a_tail:
            self._add_step(-1)   # 尾部哨兵
        elif action is a_paste:
            self._paste(len(self._step_list) if self._step_list is not None else 0)

    def _on_card_menu(self, card: StepCard, pos) -> None:
        self._card_menu(card, pos)

    def _card_menu(self, card: StepCard, pos) -> None:
        self._select(card)
        idx = self._cards.index(card)
        menu = QMenu(self)
        a_before = menu.addAction("添加到此步骤前方…")
        a_after = menu.addAction("添加到此步骤后方…")
        menu.addSeparator()
        a_copy = menu.addAction("复制")
        a_cut = menu.addAction("剪切")
        a_paste = menu.addAction("粘贴")
        menu.addSeparator()
        a_del = menu.addAction("删除")
        a_paste.setEnabled(bool(self._clipboard.steps))
        action = menu.exec_(pos)
        if action is a_before:
            self._add_step(idx)
        elif action is a_after:
            self._add_step(idx + 1)
        elif action is a_copy:
            self._copy(idx)
        elif action is a_cut:
            self._copy(idx)
            self._delete_step(idx)
        elif action is a_paste:
            self._paste(idx + 1)
        elif action is a_del:
            self._delete_step(idx)

    def _card_at(self, pos) -> Optional[StepCard]:
        item = self.itemAt(pos)
        if isinstance(item, QGraphicsProxyWidget):
            w = item.widget()
            if isinstance(w, StepCard):
                return w
        return None

    # ---- 操作 ----
    def _add_step(self, index: int) -> None:
        dlg = TemplateChooserDialog(self._mgr, self)
        if dlg.exec_() != QDialog.Accepted:
            return
        path = dlg.selected_path()
        if not path:
            return
        step = self._mgr.create_step(path)
        sl = self._step_list
        if sl is None:
            return
        if index == -1 or index >= len(sl):
            sl.add(step)
        else:
            sl.insert(index, step)
        self.refresh()
        self.edited.emit()

    def _copy(self, index: int) -> None:
        sl = self._step_list
        if sl is None:
            return
        self._clipboard.steps = [sl[index].to_format_string()]

    def _paste(self, index: int) -> None:
        if not self._clipboard.steps or self._step_list is None:
            return
        try:
            self._step_list.insert_format_strings(
                index, self._clipboard.steps, self._mgr)
        except ValueError as e:
            QMessageBox.warning(self, "粘贴", "无法粘贴：%s" % e)
            return
        self.refresh()
        self.edited.emit()

    def _delete_step(self, index: int) -> None:
        sl = self._step_list
        if sl is None:
            return
        if QMessageBox.question(
                self, "删除", "确定删除该步骤？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes) != QMessageBox.Yes:
            return
        sl.remove(index)
        self.refresh()
        self.edited.emit()
```

- [ ] **Step 4: 运行确认通过**

Run: `python -m widgets.step_list_view`
Expected: GREEN —— `StepListView smoke OK` EXIT=0

- [ ] **Step 5: 依赖链回归**

Run: `python -m widgets.step_card` 和 `python -m model.step_list` 和 `python -m model.step_list_store`
Expected: 各自 `smoke OK` EXIT=0

---

