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

