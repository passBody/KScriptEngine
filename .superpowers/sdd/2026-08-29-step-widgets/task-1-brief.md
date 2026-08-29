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

