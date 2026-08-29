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
### Task 3: `StepCard` — 步骤对象卡片

**Files:**
- Create: `widgets/step_card.py`

**Interfaces:**
- Consumes: `Step`（`enabled` / `status: StepStatus` / `name` / `info_widget(parent)` / `io`）、`StepIOWidget`（`gen_widget()` 返回带 `input_fields`/`output_fields` 的 QWidget、`is_valid` property、`picker` 可替换属性）
- Produces（T4 视图消费）:
  - `StepCard(step: Step, parent=None)` —— 固定尺寸 `240 × 340`
  - `menu_requested = pyqtSignal(object, object)` —— `(自身, 全局坐标)`；右键菜单由视图统一构建，卡片只发信号
  - `refresh()` —— 重检 io 校验 + 状态 + 激活 → 重绘颜色
  - `set_selected(bool)` —— 选中高亮（蓝边框 `#3a7bd5`，不影响状态背景色）
  - `step` 属性（只读返回绑定的 Step）
  - 颜色表（模块级）：`_STATUS_COLORS`（PENDING `#d9a83a` / RUNNING `#4caf50` / FINISHED `#bdbdbd` / ERROR `#e15554`）、`_INVALID_COLOR = "#e15554"`、`_SELECT_BORDER = "#3a7bd5"`

- [ ] **Step 1: 写失败测试**——新文件 `widgets/step_card.py` 先只写文件头 + 冒烟块（类未定义 → 红）：

```python
# -*- coding: utf-8 -*-
"""
步骤对象卡片（GUI 控件）
======================

:class:`StepCard` 是「步骤对象」的可视化卡片：顶部条 = 激活按钮 + 步骤名，
中部 = 步骤自定义视图（:meth:`Step.info_widget`），下方 = 输入/输出 GUI
（:meth:`StepIOWidget.gen_widget`，编辑即写回 io 数据）。背景色随步骤状态
（:attr:`Step.status`）与 io 校验（:attr:`StepIOWidget.is_valid`）变化；
左上角激活按钮翻转 :attr:`Step.enabled`（未激活时按钮灰底、卡片边框虚线）。

**状态纯显示**：卡片不执行 ``do()``；``status`` 由外部（后续执行器）设置后
调 :meth:`refresh` 更新颜色。io 非法（输入输出 GUI 有不合规的值）→ 红色，
优先于任何状态色。

基本用法
--------
::

    card = StepCard(step)
    card.refresh()            # 重检 io 校验 + 状态 + 激活 → 重绘颜色
    card.set_selected(True)   # 选中高亮（视图管理）
"""

if __name__ == "__main__":
    import sys

    from PyQt5.QtCore import QPoint
    from PyQt5.QtWidgets import QApplication

    from actions.base import Step
    from model.kscp_package import KscpPackage
    from model.project_variable import ProjectVariable
    from model.variable_tree import VariableTree

    app = QApplication.instance() or QApplication(sys.argv)

    # 桩步骤（与 actions.base 冒烟同款）
    from dataclasses import dataclass

    @dataclass
    class _StubInput:
        a: number = 0  # type: ignore

    @dataclass
    class _StubOutput:
        total: number = 0  # type: ignore

    class _StubStep(Step):
        name = "桩步骤"
        description = "测试用桩步骤"
        input_class = _StubInput
        output_class = _StubOutput

        def run(self) -> int:
            self.outputs.total = self.inputs.a * 2
            return 1

    pkg = KscpPackage.create_empty()
    tree = VariableTree.create_empty()
    tree.add("n1", ProjectVariable.create("number", 100, pkg))

    s = _StubStep.create_default(tree, pkg)
    card = StepCard(s)

    # io 非法（空槽）→ 红优先于状态色
    assert _INVALID_COLOR in card.styleSheet()
    # 配置 io → PENDING 暗黄
    s.io.change_value("input", 0, "5")
    s.io.change_value("output", 0, "n1")
    card.refresh()
    assert _STATUS_COLORS[StepStatus.PENDING] in card.styleSheet()
    # 状态色：RUNNING 绿 / FINISHED 灰 / ERROR 红
    s.status = StepStatus.RUNNING
    card.refresh()
    assert _STATUS_COLORS[StepStatus.RUNNING] in card.styleSheet()
    s.status = StepStatus.FINISHED
    card.refresh()
    assert _STATUS_COLORS[StepStatus.FINISHED] in card.styleSheet()
    s.status = StepStatus.ERROR
    card.refresh()
    assert _STATUS_COLORS[StepStatus.ERROR] in card.styleSheet()
    # io 变非法 → 红优先（PENDING 状态验证优先级）
    s.status = StepStatus.PENDING
    s.io.change_value("input", 0, "")
    card.refresh()
    assert _INVALID_COLOR in card.styleSheet()

    # 激活按钮：翻转 enabled + 按钮样式/边框虚线
    s.io.change_value("input", 0, "5")
    card.refresh()
    assert s.enabled is True
    assert "solid" in card.styleSheet()
    card._btn_active.setChecked(False)
    card._on_active_toggled(False)
    assert s.enabled is False
    assert "dashed" in card.styleSheet()
    assert card._btn_active.text() == "✗"      # 未激活 = 灰底「✗」
    card._on_active_toggled(True)
    assert s.enabled is True and "solid" in card.styleSheet()
    assert card._btn_active.text() == "✓"      # 激活 = 绿底「✓」

    # 选中高亮：蓝边框；不影响状态背景色
    card.set_selected(True)
    assert _SELECT_BORDER in card.styleSheet()
    card.set_selected(False)
    assert _SELECT_BORDER not in card.styleSheet()

    # menu_requested 信号：右键发出（自身, 坐标）
    got = []
    card.menu_requested.connect(lambda c, p: got.append((c, p)))
    card.menu_requested.emit(card, QPoint(1, 2))
    assert got == [(card, QPoint(1, 2))]

    # 尺寸
    assert card.width() == 240 and card.height() == 340

    # picker 延迟重检：fake picker 让 io 变非法；refresh 延迟到值落地后
    def fake_picker(tree, vtype, parent):
        s.io.change_value("input", 0, "")
        return None

    s.io.picker = fake_picker                     # 构造前替换（card2 构造时会被包装）
    card2 = StepCard(s)                           # 此时 io 合法
    card2.refresh()
    assert _STATUS_COLORS[StepStatus.PENDING] in card2.styleSheet()
    s.io.picker(None, "number", card2)            # 模拟点击资源类「选择变量」按钮
    # 值已落地但重检被延迟到下一事件循环迭代 → 颜色仍是 PENDING（同步刷新未发生）
    assert _STATUS_COLORS[StepStatus.PENDING] in card2.styleSheet()
    app.processEvents()                           # 触发零延迟定时器
    assert _INVALID_COLOR in card2.styleSheet()   # 值已落地、延迟重检生效

    print("StepCard smoke OK")
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m widgets.step_card`
Expected: RED —— `ImportError: cannot import name 'StepCard'`（EXIT=1）

- [ ] **Step 3: 实现**——在冒烟块前补齐完整文件（类定义放冒烟块之前，imports 放模块头）：

```python
from __future__ import annotations

from typing import Optional

from PyQt5.QtCore import QTimer, Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QLineEdit, QToolButton, QVBoxLayout, QWidget,
)

from actions.base import Step, StepStatus

__all__ = ["StepCard"]

# 状态 → 背景色（io 非法时红优先）
_STATUS_COLORS = {
    StepStatus.PENDING: "#d9a83a",
    StepStatus.RUNNING: "#4caf50",
    StepStatus.FINISHED: "#bdbdbd",
    StepStatus.ERROR: "#e15554",
}
_INVALID_COLOR = "#e15554"   # io 非法（任何状态优先）
_SELECT_BORDER = "#3a7bd5"   # 选中高亮边框


class StepCard(QFrame):
    """步骤对象卡片：激活按钮 + 自定义视图 + 输入/输出 GUI；背景色随状态/校验变化。"""

    menu_requested = pyqtSignal(object, object)   # (自身, 全局坐标)；菜单由视图统一构建

    def __init__(self, step: Step, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._step = step
        self._selected = False
        self.setFixedSize(240, 340)
        self.setCursor(Qt.PointingHandCursor)

        self._btn_active = QToolButton(self)
        self._btn_active.setCheckable(True)
        self._btn_active.setChecked(step.enabled)
        self._btn_active.setFixedSize(26, 26)
        self._btn_active.setToolTip("激活（勾选运行）/ 停用")
        self._btn_active.clicked.connect(self._on_active_toggled)

        self._name = QLabel(step.name)
        self._name.setStyleSheet(
            "font-weight:bold; font-size:15px; color:#333;"
            " background:transparent; border:none;")

        top = QHBoxLayout()
        top.setContentsMargins(8, 8, 8, 0)
        top.setSpacing(8)
        top.addWidget(self._btn_active)
        top.addWidget(self._name, 1)

        self._info = step.info_widget(self)
        self._io_widget = step.io.gen_widget(self)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 8)
        lay.setSpacing(4)
        lay.addLayout(top)
        lay.addWidget(self._info)
        lay.addWidget(self._io_widget)
        lay.addStretch()

        # 颜色刷新钩子①：io 文本框编辑（QLineEdit 输入即重检）
        for fld in (list(self._io_widget.input_fields)
                    + list(self._io_widget.output_fields)):
            if isinstance(fld, QLineEdit):
                fld.textChanged.connect(lambda *_: self.refresh())
        # 颜色刷新钩子②：资源类按钮经 picker 选择后重检
        orig_picker = step.io.picker

        def _picker(tree, vtype, parent):
            result = orig_picker(tree, vtype, parent)
            QTimer.singleShot(0, self.refresh)   # 延迟到值落地后（下一事件循环迭代）重检
            return result

        step.io.picker = _picker
        self.refresh()

    @property
    def step(self) -> Step:
        return self._step

    def refresh(self) -> None:
        """重检 io 校验 + 状态 + 激活 → 重绘背景色与按钮样式。"""
        self._btn_active.setChecked(self._step.enabled)
        self._update_style()

    def set_selected(self, selected: bool) -> None:
        """选中高亮（视图管理）：选中卡片边框变蓝，不影响状态背景色。"""
        self._selected = selected
        self._update_style()

    # ================================================================
    # 内部
    # ================================================================
    def _on_active_toggled(self, checked: bool) -> None:
        self._step.enabled = checked
        self._update_style()

    def _update_style(self) -> None:
        color = _INVALID_COLOR if not self._step.io.is_valid \
            else _STATUS_COLORS.get(self._step.status,
                                    _STATUS_COLORS[StepStatus.PENDING])
        border = _SELECT_BORDER if self._selected else color
        border_style = "dashed" if not self._step.enabled else "solid"
        self.setStyleSheet(
            "StepCard { background:%s; border:2px %s %s; border-radius:10px; }"
            % (color, border_style, border))
        name_color = "#777" if not self._step.enabled else "#333"
        self._name.setStyleSheet(
            "font-weight:bold; font-size:15px; color:%s;"
            " background:transparent; border:none;" % name_color)
        self._btn_active.setText("✓" if self._step.enabled else "✗")
        self._btn_active.setStyleSheet(
            "QToolButton { border:none; border-radius:13px; color:#fff;"
            " font-weight:bold; font-size:15px; background:%s; }"
            % ("#27ae60" if self._step.enabled else "#9e9e9e"))

    def contextMenuEvent(self, event) -> None:  # noqa: N802 (Qt 命名)
        self.menu_requested.emit(self, event.globalPos())
        event.accept()
```

- [ ] **Step 4: 运行确认通过**

Run: `python -m widgets.step_card`
Expected: GREEN —— `StepCard smoke OK` EXIT=0

- [ ] **Step 5: 依赖链回归**

Run: `python -m actions.base` 和 `python -m widgets.step_io_widget`
Expected: 各自 `smoke OK` EXIT=0

---

