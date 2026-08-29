# 步骤卡片 + 步骤列表视图 + 步骤列表管理树 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增三个 GUI 控件（步骤对象卡片、步骤列表视图、步骤列表管理树）并集成进主程序——管理树选列表 → 视图横排卡片，卡片颜色随状态/io 校验变化。

**Architecture:** 模型层补三个方法（`StepList.insert_format_strings` 事务性插入、`StepListStore.remove/rename/walk`）；widget 层三个新文件（`step_card.py` / `step_list_view.py` / `step_list_tree_widget.py`），视图用 QGraphicsView + QGraphicsProxyWidget 实现滚轮横滚与悬停缩放；主窗口共享一棵变量树给变量管理树与步骤列表管理树，变量变更 → 卡片重检颜色。

**Tech Stack:** Python 3.14 / PyQt5 5.15（QGraphicsView、QVariantAnimation、QTreeWidget、QSS 内联样式）/ 现有模型（Step、StepIOWidget、StepManager、StepList、StepListStore、VariableTree）

**Spec:** `docs/superpowers/specs/2026-08-29-step-widgets-design.md`（本计划由此展开；冲突时 spec 为准）

## Global Constraints

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

### Task 1: `StepList.insert_format_strings` — 事务性解码插入

**Files:**
- Modify: `model/step_list.py`（`from_format_strings` 之后新增方法；冒烟块尾部追加断言）

**Interfaces:**
- Consumes: `StepManager.from_format_string(fmt) -> Optional[Step]`（非法编码重抛 ValueError；无匹配返回 None 并记日志）
- Produces: `StepList.insert_format_strings(index: int, fmts: List[str], manager: StepManager) -> None` —— 先全部解码成功再统一插入（任一条失败**不产生任何部分插入**）；第 `i` 条插到 `index + i`（保持 fmts 顺序）；`index` 用 Python `list.insert` 语义（越界钳制、负数回绕）。后续 T4 视图粘贴消费。

- [ ] **Step 1: 写失败测试**——在 `model/step_list.py` 冒烟块尾部（`print("StepList smoke OK")` 之前）追加：

```python
    # insert_format_strings：事务性解码后统一插入（保持顺序；list.insert 语义）
    sl4 = StepList.create_empty()
    sl4.insert_format_strings(0, fmts, mgr)          # 头部插入 → [f0, f1]
    assert sl4.to_format_strings() == fmts
    sl4.insert_format_strings(1, [fmts[0]], mgr)     # 中间插入 → [f0, f0, f1]
    assert sl4.to_format_strings() == [fmts[0], fmts[0], fmts[1]]
    sl4.insert_format_strings(99, [fmts[1]], mgr)    # 越界钳制 → 尾部追加
    assert sl4.to_format_strings() == [fmts[0], fmts[0], fmts[1], fmts[1]]
    sl4.insert_format_strings(-1, [fmts[0]], mgr)    # 负数回绕 → 倒数第 2
    assert sl4.to_format_strings() == [fmts[0], fmts[0], fmts[1], fmts[0], fmts[1]]
    # 事务性：坏条目出现在中间 → 一条都不插入
    sl5 = StepList.create_empty()
    sl5.add(s1)
    try:
        sl5.insert_format_strings(1, [fmts[0], "not*valid*", fmts[1]], mgr)
        raise AssertionError("坏条目应抛 ValueError")
    except ValueError as exc:
        assert "第 1 条" in str(exc)
    assert sl5.to_format_strings() == [s1.to_format_string()]   # 无部分插入
    try:
        sl5.insert_format_strings(0, [fake], mgr)    # 无匹配模板（复用上文 fake）
        raise AssertionError("无匹配应抛 ValueError")
    except ValueError as exc:
        assert "第 0 条" in str(exc)
    assert len(sl5) == 1
```

（`fmts`、`fake`、`s1` 均为冒烟块上文已定义的变量，直接复用。）

- [ ] **Step 2: 运行确认失败**

Run: `python -m model.step_list`
Expected: RED —— `AttributeError: 'StepList' object has no attribute 'insert_format_strings'`（EXIT=1）

- [ ] **Step 3: 实现**——在 `model/step_list.py` 的 `from_format_strings` 之后、`create_empty` 之前插入：

```python
    def insert_format_strings(self, index: int, fmts: List[str],
                              manager: "StepManager") -> None:
        """把格式串列表解码后插入到 ``index``（保持顺序）。

        事务性：先全部解码成功，再统一插入——任一条坏条目（非法编码或无匹配）
        → :class:`ValueError`（带「第 N 条」下标），且不产生任何部分插入。
        ``index`` 用 Python ``list.insert`` 语义（越界钳制，负数回绕）。
        """
        decoded: List[Step] = []
        for i, fmt in enumerate(fmts):
            try:
                step = manager.from_format_string(fmt)
            except ValueError as e:
                raise ValueError("步骤列表第 %d 条格式串无效: %s" % (i, e))
            if step is None:
                raise ValueError("步骤列表第 %d 条无法还原: 没有可匹配的模板" % i)
            decoded.append(step)
        for i, step in enumerate(decoded):
            self._steps.insert(index + i, step)
```

- [ ] **Step 4: 运行确认通过**

Run: `python -m model.step_list`
Expected: GREEN —— `StepList smoke OK` EXIT=0

- [ ] **Step 5: 依赖链回归**

Run: `python -m model.step_list_store` 和 `python -m model.step_manager` 和 `python -m actions.base`
Expected: 三者均输出各自 `smoke OK` EXIT=0（既有冒烟不受影响）

---

### Task 2: `StepListStore.remove` / `rename` / `walk` — 管理树支持

**Files:**
- Modify: `model/step_list_store.py`（typing 导入加 `Tuple`；`get()` 之后新增一节；冒烟块尾部追加断言）

**Interfaces:**
- Consumes: 既有 `_norm_path` / `_validate_name` / `_parent_of`（复用，不改动）
- Produces（T5 管理树消费）:
  - `remove(path: str) -> None` —— 删列表**或组**（组 = 整棵子树）；不存在 → `FileNotFoundError`
  - `rename(path: str, new_name: str) -> None` —— 非法新名 → `ValueError`；不存在 → `FileNotFoundError`；同父重名 → `FileExistsError`；成功**保持原字典插入位置**（重建父 dict，不追加到末尾）
  - `walk() -> List[Tuple[str, bool]]` —— 全部组与列表路径，插入序**先序**（组在前、其子树紧随）；每项 `(路径, 是否为组)`；**含空组**（管理树数据源；`paths()` 只有叶子）

- [ ] **Step 1: 写失败测试**——在 `model/step_list_store.py` 冒烟块尾部（`print("StepListStore smoke OK")` 之前）追加：

```python
    # ---- 变更扩展：remove / rename / walk（管理树 UI 支持） ----
    # walk：先序（组在前、子树紧随）、含空组
    w = store.walk()
    assert [p for p, _g in w] == [
        "打开软件", "清理体力", "清理体力/检查体力", "清理体力/日常",
        "清理体力/日常/跑图", "前导组", "前导组/临时", "空组"]
    assert [g for _p, g in w] == [False, True, False, True,
                                  False, True, False, True]

    # remove：删列表 / 删组（整棵子树）/ 不存在 → FileNotFoundError
    store2 = StepListStore.create_empty()
    store2.add_group("组A")
    store2.add_list("组A/列表1", sl_open)
    store2.add_list("组A/列表2", sl_check)
    store2.remove("组A/列表1")
    assert "组A/列表1" not in store2.paths() and "组A/列表2" in store2.paths()
    store2.remove("组A")                            # 删组 = 整棵子树
    assert store2.paths() == []
    try:
        store2.remove("不存在")
        raise AssertionError("不存在应抛 FileNotFoundError")
    except FileNotFoundError:
        pass

    # rename：改列表 / 改组（子树保留）/ 保持字典插入位置 / 非法名 / 不存在 / 重名冲突
    store3 = StepListStore.create_empty()
    store3.add_group("先组")
    store3.add_list("中间列表", sl_open)
    store3.add_group("后组")
    store3.add_list("后组/子列表", sl_check)
    store3.rename("中间列表", "改名列表")
    assert list(store3._root) == ["先组", "改名列表", "后组"]   # 保持插入位置
    assert "改名列表" in store3.paths()
    store3.rename("后组", "改名组")
    assert list(store3._root) == ["先组", "改名列表", "改名组"]
    assert "改名组/子列表" in store3.paths()                    # 子树保留
    assert store3.get("改名组/子列表") is sl_check
    for bad in ("", "/", "a/b", ".", ".."):
        try:
            store3.rename("改名列表", bad)
            raise AssertionError("非法新名应抛 ValueError: %r" % bad)
        except ValueError:
            pass
    try:
        store3.rename("不存在", "x")
        raise AssertionError("不存在应抛 FileNotFoundError")
    except FileNotFoundError:
        pass
    try:
        store3.rename("改名列表", "先组")
        raise AssertionError("重名冲突应抛 FileExistsError")
    except FileExistsError:
        pass
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m model.step_list_store`
Expected: RED —— `AttributeError: 'StepListStore' object has no attribute 'walk'`（EXIT=1）

- [ ] **Step 3: 实现**——typing 导入行改为 `from typing import Any, Callable, Dict, List, Tuple, Union, TYPE_CHECKING`；在 `get()` 方法之后、`if __name__` 之前新增一节：

```python
    # ================================================================
    # 结构 / 变更扩展（管理树 UI 支持）
    # ================================================================
    def remove(self, path: str) -> None:
        """删除列表或组（组 = 整棵子树）；不存在 → :class:`FileNotFoundError`。"""
        parts = self._norm_path(path).split("/")
        parent = self._parent_of(parts)
        last = parts[-1]
        if last not in parent:
            raise FileNotFoundError("不存在: %r" % path)
        del parent[last]

    def rename(self, path: str, new_name: str) -> None:
        """重命名列表或组（组 = 改键名，子树不动）；保持原字典插入位置。

        非法新名 → :class:`ValueError`；不存在 → :class:`FileNotFoundError`；
        同父下新名已存在 → :class:`FileExistsError`。
        """
        self._validate_name(new_name)
        parts = self._norm_path(path).split("/")
        parent = self._parent_of(parts)
        last = parts[-1]
        if last not in parent:
            raise FileNotFoundError("不存在: %r" % path)
        if new_name in parent:
            raise FileExistsError("目标已存在: %r" % new_name)
        items = list(parent.items())
        for i, (k, v) in enumerate(items):
            if k == last:
                items[i] = (new_name, v)
                break
        parent.clear()
        parent.update(items)

    def walk(self) -> List[Tuple[str, bool]]:
        """全部组与列表路径（插入序先序：组在前、其子树紧随）；每项 = ``(路径, 是否为组)``。

        含空组；管理树数据源（树需要组节点，:meth:`paths` 只有叶子）。
        """
        out: List[Tuple[str, bool]] = []
        self._collect_walk(self._root, "", out)
        return out

    @staticmethod
    def _collect_walk(node: dict, prefix: str,
                      out: List[Tuple[str, bool]]) -> None:
        for key, value in node.items():
            path = key if not prefix else prefix + "/" + key
            if isinstance(value, StepList):
                out.append((path, False))
            else:
                out.append((path, True))
                StepListStore._collect_walk(value, path, out)
```

- [ ] **Step 4: 运行确认通过**

Run: `python -m model.step_list_store`
Expected: GREEN —— `StepListStore smoke OK` EXIT=0

- [ ] **Step 5: 依赖链回归**

Run: `python -m model.step_list` 和 `python -m model.step_manager`
Expected: 各自 `smoke OK` EXIT=0

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

### Task 5: `StepListTreeWidget` — 步骤列表管理树

**Files:**
- Create: `widgets/step_list_tree_widget.py`

**Interfaces:**
- Consumes: T2 的 `StepListStore.remove/rename/walk/get/add_group/add_list`；T4 的 `StepClipboard`；`StepList.from_format_strings(fmts, mgr)`；`StepManager`
- Produces（T7 宿主消费）:
  - `StepListTreeWidget(store, manager, clipboard, on_changed, parent)`
  - `list_selected = pyqtSignal(str)`（点击列表叶子 → 路径；组/空白不触发）
  - `store_changed = pyqtSignal()`（任何变更后发出）
  - `on_changed: Callable[[], None]`（变更回调，宿主保存 step_list.json）
  - `_PATH_ROLE = 0x0100`（模块级）

- [ ] **Step 1: 写失败测试**——新文件先只写文件头 + 冒烟块（类未定义 → 红）：

```python
# -*- coding: utf-8 -*-
"""
步骤列表管理树（GUI 控件）
========================

:class:`StepListTreeWidget` 是「总步骤列表模型」（:class:`model.step_list_store.StepListStore`）
的管理树：组 = 文件夹图标，叶子 = 步骤列表（只显示键值）。上下文菜单支持
添加组 / 复制 / 剪切 / 粘贴 / 重命名 / 删除；点击列表发 :data:`list_selected`，
任何变更后发 :data:`store_changed` 并调用 ``on_changed`` 回调（上层保存
``step_list.json``）。

剪贴板（:class:`widgets.step_list_view.StepClipboard`）与步骤列表视图共享；
列表/组剪贴板 = ``(名, [(相对路径, 是否组, 格式串列表|None), ...])``，
粘贴时经 :class:`StepManager` 解码重建（列表）或 ``add_group`` 递归重建（组）。

基本用法
--------
::

    tree = StepListTreeWidget(store, mgr, clipboard, on_changed)
    tree.list_selected.connect(show_list)   # 点击列表 → 视图显示
"""

if __name__ == "__main__":
    import sys

    from PyQt5.QtWidgets import QApplication, QInputDialog, QMessageBox

    from actions.base import Step
    from model.kscp_package import KscpPackage
    from model.project_variable import ProjectVariable
    from model.step_list import StepList
    from model.step_list_store import StepListStore
    from model.step_manager import StepManager
    from model.variable_tree import VariableTree
    from widgets.step_list_view import StepClipboard

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
    mgr = StepManager(pkg, tree)
    mgr.load()

    def make_step() -> Step:
        s = mgr.create_step("示例")
        s.io.change_value("input", 0, "5")
        s.io.change_value("output", 0, "n1")
        return s

    store = StepListStore.create_empty()
    sl = StepList.create_empty()
    sl.add(make_step())
    store.add_list("打开软件", sl)
    store.add_group("清理体力")
    slc = StepList.create_empty()
    slc.add(make_step())
    store.add_list("清理体力/检查体力", slc)
    store.add_group("空组")

    changes = []
    clipboard = StepClipboard()
    tw = StepListTreeWidget(store, mgr, clipboard,
                            lambda: changes.append(1))

    # 只显示键值；组在上、列表在下（每层各自排序）
    top = [tw.topLevelItem(i).text(0)
           for i in range(tw.topLevelItemCount())]
    assert top == ["清理体力", "打开软件", "空组"], top
    g = tw._find_item("清理体力")
    assert g is not None and g.childCount() == 1
    assert g.child(0).text(0) == "检查体力"
    assert tw._find_item("清理体力/检查体力") is not None
    assert tw._find_item("空组") is not None
    assert not tw._find_item("打开软件").icon(0).isNull()

    # list_selected 仅叶子触发
    seen = []
    tw.list_selected.connect(seen.append)
    tw.setCurrentItem(tw._find_item("打开软件"))
    assert seen == ["打开软件"]
    tw.setCurrentItem(g)                       # 组不触发
    assert seen == ["打开软件"]

    # 添加组（补丁 QInputDialog）
    orig_dlg = QInputDialog.getText
    QInputDialog.getText = staticmethod(lambda *a, **k: ("新组", True))
    try:
        tw._act_add_group("")
    finally:
        QInputDialog.getText = orig_dlg
    assert "新组" in [tw.topLevelItem(i).text(0)
                      for i in range(tw.topLevelItemCount())]
    assert changes == [1]                      # 变更回调被调

    # 复制列表 → 剪贴板三元组；粘贴到组内（无重名 → 不产生 name(1)）
    tw.setCurrentItem(tw._find_item("打开软件"))
    tw._act_copy()
    assert clipboard.items[0] == "打开软件"
    assert clipboard.items[1] == [("", False, sl.to_format_strings())]
    g = tw._find_item("清理体力")               # 树已重建 → 重新获取
    assert g is not None
    tw.setCurrentItem(g)
    tw._act_paste("清理体力")                   # 右键在组上 → 粘贴进组
    assert "清理体力/打开软件" in store.paths()
    # 组复制 → 整棵子树；粘贴到根 → 顶层重名去重 name(1)
    g = tw._find_item("清理体力")
    tw.setCurrentItem(g)
    tw._act_copy()
    assert clipboard.items[0] == "清理体力"
    assert ("", True, None) in clipboard.items[1]
    assert ("检查体力", False, slc.to_format_strings()) in clipboard.items[1]
    tw.setCurrentItem(None)
    tw._act_paste("")                          # 粘贴到根
    assert "清理体力(1)/检查体力" in store.paths()

    # 剪切 = 复制 + 删除（剪贴板保留）
    tw.setCurrentItem(tw._find_item("清理体力(1)"))
    tw._act_cut()
    assert "清理体力(1)" not in store.paths()
    assert clipboard.items is not None

    # 重命名（补丁 QInputDialog 带初值）
    tw.setCurrentItem(tw._find_item("清理体力/打开软件"))
    orig_dlg = QInputDialog.getText
    QInputDialog.getText = staticmethod(lambda *a, **k: ("改名", True))
    try:
        tw._act_rename()
    finally:
        QInputDialog.getText = orig_dlg
    assert "清理体力/改名" in store.paths()
    assert tw._current_path() == "清理体力/改名"    # 重命名后重新选中新路径

    # 删除（补丁确认框；组 = 整棵子树）
    orig_q = QMessageBox.question
    QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)
    try:
        tw.setCurrentItem(tw._find_item("清理体力/改名"))
        tw._act_delete()
    finally:
        QMessageBox.question = orig_q
    assert "清理体力/改名" not in store.paths()
    assert changes and len(changes) > 1

    # 多选复制/剪切 = no-op（剪贴板单条目契约 → 复制/剪切限单选，防数据丢失）
    a = tw._find_item("打开软件")
    b = tw._find_item("清理体力/检查体力")
    assert a is not None and b is not None
    tw.setCurrentItem(a)
    a.setSelected(True)
    b.setSelected(True)
    assert len(tw._selected_paths()) == 2            # 选中集确含两项
    old_items = clipboard.items
    tw._act_copy()                                   # 多选复制 → no-op
    assert clipboard.items is old_items              # 剪贴板未被覆盖
    paths_before = sorted(store.paths())
    tw._act_cut()                                    # 多选剪切 → no-op
    assert sorted(store.paths()) == paths_before     # 未删除任何项

    print("StepListTreeWidget smoke OK")
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m widgets.step_list_tree_widget`
Expected: RED —— `ImportError: cannot import name 'StepListTreeWidget'`（EXIT=1）

- [ ] **Step 3: 实现**——在冒烟块前补齐完整文件（imports 放模块头）：

```python
from __future__ import annotations

from typing import Callable, List, Optional, Tuple

from PyQt5.QtCore import Qt, QKeySequence, pyqtSignal
from PyQt5.QtGui import QColor, QFont, QIcon, QKeySequence, QPainter, QPixmap
from PyQt5.QtWidgets import (
    QAbstractItemView, QInputDialog, QMenu, QMessageBox, QShortcut,
    QStyle, QTreeWidget, QTreeWidgetItem, QWidget,
)

from model.step_list import StepList
from model.step_list_store import StepListStore
from model.step_manager import StepManager
from widgets.step_list_view import StepClipboard

__all__ = ["StepListTreeWidget"]

_PATH_ROLE = 0x0100   # Qt.UserRole


def _make_list_icon() -> QIcon:
    """列表叶子小图标：橙色圆角方块内三条浅色横线（与步骤模板树同款）。"""
    pm = QPixmap(18, 18)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#e67e22"))
    p.drawRoundedRect(2, 2, 14, 14, 3, 3)
    p.setBrush(QColor("#fff3e0"))
    for y in (6, 9, 12):
        p.drawRoundedRect(5, y, 8, 2, 1, 1)
    p.end()
    return QIcon(pm)


class StepListTreeWidget(QTreeWidget):
    """步骤列表管理树：只显示键值（组 = 文件夹，列表 = 图标 + 名）。"""

    list_selected = pyqtSignal(str)      # 点击列表叶子 → 路径
    store_changed = pyqtSignal()         # 任何变更后发出（宿主处理当前列表被删等）

    def __init__(self, store: StepListStore, manager: StepManager,
                 clipboard: StepClipboard, on_changed: Callable[[], None],
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._store = store
        self._manager = manager
        self._clipboard = clipboard
        self._on_changed = on_changed

        self.setHeaderHidden(True)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setUniformRowHeights(True)
        self.setFont(QFont("SimSun", 11))
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._on_context_menu)
        self.currentItemChanged.connect(self._on_current_changed)

        QShortcut(QKeySequence.Delete, self, self._act_delete)
        QShortcut("F2", self, self._act_rename)

        self.refresh()

    def refresh(self, current_path: Optional[str] = None) -> None:
        """从 store 重建树（组/列表键值）；保留展开，可指定当前项。"""
        expanded = set(self._expanded_paths())
        cur = current_path if current_path is not None else self._current_path()
        self.blockSignals(True)
        self.clear()
        root = self.invisibleRootItem()
        if root is not None:
            self._fill(root, "")
        for it in self._walk_items():
            if it.data(0, _PATH_ROLE) in expanded:
                it.setExpanded(True)
        target = self._find_item(cur)
        if target is not None:
            self.setCurrentItem(target)
        self.blockSignals(False)
        self._on_current_changed(self.currentItem(), None)

    # ---- 树构建 ----
    def _fill(self, parent_item: QTreeWidgetItem, prefix: str) -> None:
        style = self.style()
        dirs, leaves = self._children_of(prefix)
        for name, is_group in dirs + leaves:
            path = name if not prefix else prefix + "/" + name
            item = QTreeWidgetItem(parent_item)
            item.setText(0, name)
            item.setData(0, _PATH_ROLE, path)
            if is_group:
                if style is not None:
                    item.setIcon(0, style.standardIcon(QStyle.SP_DirIcon))
                self._fill(item, path)
            else:
                item.setIcon(0, _make_list_icon())

    def _children_of(self, prefix: str) -> Tuple[List[Tuple[str, bool]],
                                                 List[Tuple[str, bool]]]:
        """prefix 的直接子项（组/列表），各自按名排序。"""
        dirs: List[Tuple[str, bool]] = []
        leaves: List[Tuple[str, bool]] = []
        for path, is_group in self._store.walk():
            parent = path.rsplit("/", 1)[0] if "/" in path else ""
            if parent != prefix:
                continue
            name = path.rsplit("/", 1)[-1]
            (dirs if is_group else leaves).append((name, is_group))
        return sorted(dirs), sorted(leaves)

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
        return [it.data(0, _PATH_ROLE) for it in self._walk_items()
                if it.isExpanded()]

    # ---- 选中 / 信号 ----
    def _current_path(self) -> str:
        cur = self.currentItem()
        return cur.data(0, _PATH_ROLE) if cur is not None else ""

    def _on_current_changed(self, cur, _prev) -> None:
        path = cur.data(0, _PATH_ROLE) if cur is not None else ""
        if not path:
            return
        try:
            self._store.get(path)
        except FileNotFoundError:
            return                       # 组不触发
        self.list_selected.emit(path)

    # ---- 右键菜单 ----
    def _on_context_menu(self, pos) -> None:
        item = self.itemAt(pos)
        if item is not None and not item.isSelected():
            self.setCurrentItem(item)
        context_group = self._group_of(item)
        tops = self._selected_paths_top()

        menu = QMenu(self)
        a_add = menu.addAction("添加组…")
        menu.addSeparator()
        a_copy = menu.addAction("复制")
        a_cut = menu.addAction("剪切")
        a_paste = menu.addAction("粘贴")
        menu.addSeparator()
        a_rename = menu.addAction("重命名\tF2")
        a_delete = menu.addAction("删除\tDel")

        a_copy.setEnabled(len(tops) == 1)
        a_cut.setEnabled(len(tops) == 1)
        a_paste.setEnabled(self._clipboard.items is not None)
        a_rename.setEnabled(len(tops) == 1)
        a_delete.setEnabled(bool(tops))

        action = menu.exec_(self.viewport().mapToGlobal(pos))
        if action is a_add:
            self._act_add_group(context_group)
        elif action is a_copy:
            self._act_copy()
        elif action is a_cut:
            self._act_cut()
        elif action is a_paste:
            self._act_paste(context_group)
        elif action is a_rename:
            self._act_rename()
        elif action is a_delete:
            self._act_delete()

    def _group_of(self, item: Optional[QTreeWidgetItem]) -> str:
        """item 所在组：组项取自身，叶子取父组，空白 → 空串（根）。"""
        if item is None:
            return ""
        p = item.data(0, _PATH_ROLE)
        if not p:
            return ""
        if self._is_group(p):
            return p
        return p.rsplit("/", 1)[0] if "/" in p else ""

    def _is_group(self, path: str) -> bool:
        """路径是否为组（仅对树中真实存在的项调用：get 抛 FileNotFoundError ⇔ 组）。"""
        try:
            self._store.get(path)
        except FileNotFoundError:
            return True
        return False

    def _selected_paths(self) -> List[str]:
        return [it.data(0, _PATH_ROLE) for it in self.selectedItems()
                if it.data(0, _PATH_ROLE)]

    def _selected_paths_top(self) -> List[str]:
        """选中集「顶层化」：去掉被另一选中项包含的子项。"""
        paths = self._selected_paths()
        tops = []
        for p in paths:
            if not any(o != p and p.startswith(o + "/") for o in paths):
                tops.append(p)
        return sorted(set(tops))

    # ---- 操作 ----
    def _act_add_group(self, context_group: str = "") -> None:
        name, ok = QInputDialog.getText(self, "添加组", "组名：")
        if not ok:
            return
        name = name.strip()
        if not name or "/" in name or name in (".", ".."):
            QMessageBox.warning(self, "添加组", "名称非法")
            return
        full = (context_group + "/" + name) if context_group else name
        try:
            self._store.add_group(full)
        except (ValueError, FileExistsError) as e:
            QMessageBox.warning(self, "添加组", "无法添加：%s" % e)
            return
        self._changed(full)

    def _act_copy(self) -> None:
        tops = self._selected_paths_top()
        if len(tops) != 1:
            return                       # 剪贴板单条目契约 → 复制限单选
        path = tops[0]
        name = path.rsplit("/", 1)[-1]
        self._clipboard.items = (name, self._triples_of(path))

    def _triples_of(self, path: str) -> List[Tuple[str, bool, Optional[List[str]]]]:
        """路径 → 先序三元组 ``(相对路径, 是否组, 格式串|None)``（顶层项相对路径 = 空串）。"""
        out: List[Tuple[str, bool, Optional[List[str]]]] = []
        try:
            self._store.get(path)
        except FileNotFoundError:
            out.append(("", True, None))                 # 组自身
            for child, is_group in self._store.walk():
                if not child.startswith(path + "/"):
                    continue
                rel = child[len(path) + 1:]
                if is_group:
                    out.append((rel, True, None))
                else:
                    out.append((rel, False,
                                self._store.get(child).to_format_strings()))
            return out
        out.append(("", False, self._store.get(path).to_format_strings()))
        return out

    def _act_cut(self) -> None:
        tops = self._selected_paths_top()
        if len(tops) != 1:
            return                       # 剪切 = 复制 + 删除 → 与复制同限单选
        self._act_copy()
        for p in tops:
            try:
                self._store.remove(p)
            except FileNotFoundError:
                continue
        self._changed()

    def _act_paste(self, context_group: str = "") -> None:
        if self._clipboard.items is None:
            return
        name, triples = self._clipboard.items
        target = self._dedup_name(context_group, name)   # 完整路径（已含组前缀）
        for rel, is_group, fmts in triples:
            full = (target + "/" + rel) if rel else target
            try:
                if is_group:
                    self._store.add_group(full)
                else:
                    if fmts is None:
                        continue
                    self._store.add_list(
                        full, StepList.from_format_strings(fmts, self._manager))
            except (ValueError, FileExistsError) as e:
                QMessageBox.warning(self, "粘贴", "粘贴 %s 失败：%s" % (full, e))
                continue
        self._changed(target)

    def _dedup_name(self, parent: str, name: str) -> str:
        """同父下重名去重：name(1)、name(2)…（与变量树一致）；返回完整路径。"""
        known = {p for p, _ in self._store.walk()}

        def exists(candidate: str) -> bool:
            p = (parent + "/" + candidate) if parent else candidate
            return p in known

        def full(candidate: str) -> str:
            return (parent + "/" + candidate) if parent else candidate

        if not exists(name):
            return full(name)
        i = 1
        while exists("%s(%d)" % (name, i)):
            i += 1
        return full("%s(%d)" % (name, i))

    def _act_rename(self) -> None:
        old = self._current_path()
        if not old:
            return
        name = old.rsplit("/", 1)[-1]
        new_name, ok = QInputDialog.getText(self, "重命名", "新名称：", text=name)
        if not ok:
            return
        new_name = new_name.strip()
        if not new_name or "/" in new_name or new_name in (".", ".."):
            QMessageBox.warning(self, "重命名", "名称非法")
            return
        parent = old.rsplit("/", 1)[0] if "/" in old else ""
        new_path = (parent + "/" + new_name) if parent else new_name
        if new_path == old:
            return
        try:
            self._store.rename(old, new_name)
        except (ValueError, FileExistsError, FileNotFoundError) as e:
            QMessageBox.warning(self, "重命名", "无法重命名：%s" % e)
            return
        self._changed(new_path)

    def _act_delete(self) -> None:
        tops = self._selected_paths_top()
        if not tops:
            return
        if QMessageBox.question(
                self, "删除", "确定删除 %d 项？删除的步骤列表不可恢复。"
                % len(tops),
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes) != QMessageBox.Yes:
            return
        for p in tops:
            try:
                self._store.remove(p)
            except FileNotFoundError:
                continue
        self._changed()

    # ---- 变更收尾 ----
    def _changed(self, current_path: Optional[str] = None) -> None:
        """刷新树 + 发 store_changed + 回调（上层保存）。"""
        self.refresh(current_path)
        self.store_changed.emit()
        self._on_changed()
```

- [ ] **Step 4: 运行确认通过**

Run: `python -m widgets.step_list_tree_widget`
Expected: GREEN —— `StepListTreeWidget smoke OK` EXIT=0

- [ ] **Step 5: 依赖链回归**

Run: `python -m widgets.step_list_view` 和 `python -m model.step_list_store`
Expected: 各自 `smoke OK` EXIT=0

---

### Task 6: `VariableTreeWidget` 共享树 + `tree_changed` 信号

**Files:**
- Modify: `widgets/variable_tree_widget.py`（`__init__` 签名、`_load` 调用点、`_save`、类信号；冒烟块尾部追加断言）

**Interfaces:**
- Consumes: `VariableTree`（`from_json(raw, package)` / `create_empty()` / `to_json_bytes()`）
- Produces（T7 消费）:
  - `VariableTreeWidget.__init__(self, package, tree: Optional[VariableTree] = None, parent=None)` —— `tree` 缺省 None = **旧行为不变**（自加载 variables.json）；给定 → 使用共享树（不读盘、不写空文件）
  - `tree_changed = pyqtSignal()` —— `_save()` 写盘后发出（变量树变了 → 卡片重检颜色）

- [ ] **Step 1: 写失败测试**——在 `widgets/variable_tree_widget.py` 冒烟块尾部（`print("VariableTreeWidget smoke OK")` 之前）追加：

```python
    # ---- 共享树 + tree_changed（步骤列表管理树支持） ----
    # 缺省构造（tree=None）旧行为不变：自加载 variables.json（既有断言已覆盖）
    # 给定共享树 → 使用传入实例（不读盘/不写空文件）
    shared = VariableTree.create_empty()
    shared.add("n", ProjectVariable.create("number", 7, pkg))
    vtw = VariableTreeWidget(pkg, shared)
    assert vtw._tree is shared
    assert vtw._tree.get("n").data == 7
    # _save → tree_changed 发出
    fired = []
    vtw.tree_changed.connect(lambda: fired.append(1))
    vtw._save()
    assert fired == [1]
    # 缺省构造走 _load（文件在）→ 与共享树互不影响
    assert tree._tree is not None and tree._tree.get("s").data == "world"
```

（`tree` 是冒烟块上文已有的缺省构造实例；`pkg` 已有 variables.json。）

- [ ] **Step 2: 运行确认失败**

Run: `python -m widgets.variable_tree_widget`
Expected: RED —— `TypeError: __init__() takes from 2 to 3 positional arguments but 4 were given`（新签名缺失；EXIT=1）

- [ ] **Step 3: 实现**——三处修改：

① 类信号（`var_selected = pyqtSignal(str)` 之后加一行）：

```python
    var_selected = pyqtSignal(str)
    tree_changed = pyqtSignal()      # 变量树变更（_save 写盘后发出）→ 步骤卡片重检颜色
```

② `__init__` 签名与加载分支（第 113-136 行区域）：

```python
    def __init__(self, package: KscpPackage,
                 tree: Optional[VariableTree] = None,
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._package = package
        self._tree = tree
        self._edit_panel: Optional[VariableEditPanel] = None
        self._clipboard: Optional[Tuple[List[str], str]] = None  # (paths, "copy"|"cut")

        ...（setHeaderHidden 等中间行不动）...

        if self._tree is None:
            self._load()
        else:
            LogModel.instance().info("载入变量树：共享 %d 个变量" % len(self._tree))
        self.refresh()
```

（`_clipboard` 初始化保留原样；中间的控件配置行不变。）

③ `_save` 尾部追加信号发出（第 150-153 行区域）：

```python
    def _save(self) -> None:
        assert self._tree is not None
        self._package.write_file("variables.json", self._tree.to_json_bytes())
        LogModel.instance().info("变量已保存（%d 个变量）" % len(self._tree))
        self.tree_changed.emit()
```

- [ ] **Step 4: 运行确认通过**

Run: `python -m widgets.variable_tree_widget`
Expected: GREEN —— `VariableTreeWidget smoke OK` EXIT=0（既有全部断言 + 新增断言）

- [ ] **Step 5: 依赖链回归**

Run: `python -m widgets.resource_tree_widget` 和 `python main.py --check`
Expected: 各自 `smoke OK` / EXIT=0（main --check 确认 landing 不受影响）

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

## Self-Review（计划自检）

**1. Spec 覆盖**：
- §3.1 → T1；§3.2/§3.3/§3.4 → T2（walk 含空组、先序钉住）。
- §4（StepCard：固定尺寸/激活按钮/四态色/io 非法红优先/未激活虚线+灰/选中蓝边框/textChanged+picker 刷新钩子/menu_requested 带坐标）→ T3 逐项落断言。
- §5（滚轮横滚、悬停 1.06 缩放、菜单六项、模板树对话框、StepClipboard、空态提示、set_list/refresh/refresh_validity/edited、无 Ctrl+C/X/V 快捷键）→ T4 全覆盖；「粘贴 = insert_format_strings（T1 产物）」依赖链闭合。
- §6（walk 数据源、只显示键值、组上列表下、F2/Del、六操作、list_selected/store_changed、on_changed 保存、去重 name(1)、剪切保留）→ T5 全覆盖。
- §7（StepListManagementTree 替换占位、共享变量树 + 写空文件镜像、VariableTreeWidget tree 参数 + tree_changed、tree_changed → refresh_cards）→ T6 + T7 覆盖。
- §8 每项冒烟均落为具体断言（含 main_widget 集成冒烟与全量回归清单）。

**2. Placeholder scan**：无 TBD/TODO；每任务含完整代码块与运行命令；「…中间行不动…」均指向已存在的明确代码区域（锚点行号来自当前文件）。

**3. Type consistency**：
- `insert_format_strings(index, fmts, manager)` T1 定义 = T4 `_paste` 调用（`index, self._clipboard.steps, self._mgr`）✓。
- `StepCard.menu_requested(object, object)` T3 定义 = T4 `_on_card_menu(card, pos)` 连接 ✓；`set_selected` / `refresh` 均存在 ✓。
- `StepClipboard.steps/items` T4 定义 = T5 消费（`clipboard.items`）+ T7 注入 ✓。
- `StepListStore.remove/rename/walk` T2 签名 = T5 调用（`remove(p)`、`rename(old, new_name)`、`walk()`）✓；`get` 抛 FileNotFoundError 被 T5 `_is_group`/`_on_current_changed` 依赖（既有行为）✓。
- `VariableTreeWidget(package, tree=None)` T6 = T7 构造（`VariableTreeWidget(self._package, self._tree)`）+ VariableManagementTree 透传 ✓；`tree_changed` 信号连接 `sl_mgr.refresh_cards` ✓。
- T4/T5 冒烟里 `_PATH_ROLE` 均在本文件定义 ✓；T4 冒烟 `view._anims[0]` 与实现 `_anims: Dict[int, QVariantAnimation]` ✓。
- T5 `_act_paste` 中 `store.add_group(full)` 幂等语义（spec §2 组已存在幂等）与 `add_list` 冲突 → 警告跳过 ✓。
