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

