# 活动栏刷新按钮 + 导入进度条 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在活动栏加「刷新」底部按钮（=重进界面，重建 StepManager + 步骤列表，解决导入后步骤对象不刷新），并给「导入步骤模板」加模态进度条（按 .py 文件计数、可取消、成功后自动全量刷新）。

**Architecture:** 复用 `MainWindow._open_package` 作为「重进界面」实现刷新；给 `StepManager.copy_source_templates` 加 `progress_cb` 回调（先收集候选得 total → 逐文件回调，返回 False 取消），`_on_import` 套 `QProgressDialog`（模态 + processEvents），成功后调 `_on_refresh`。刷新按钮在执行器 RUNNING/STOPPING 时禁用。

**Tech Stack:** PyQt5、Python 3.14；无 pytest，每模块 `__main__` 冒烟（`python -m <module>`），全量回归 `python tests/smoke_all.py`；非 git 仓库（无 commit 步骤，用回归冒烟作检查点）。

**Spec:** `docs/superpowers/specs/2026-09-04-refresh-and-import-progress-design.md`

---

## File Structure

| 文件 | 责任 | 改动 |
|---|---|---|
| `widgets/通用/ui_common.py` | 自绘图标工厂 `make_icon` | 新增 `"refresh"` kind（圆弧箭头）+ 导入 `QRect` |
| `model/步骤/step_manager.py` | 步骤模板工厂 | `copy_source_templates` 加 `progress_cb`；抽 `_iter_source_templates` |
| `widgets/树/step_tree_widget.py` | 模板管理树控件 | `import_templates` 透传 `progress_cb` |
| `widgets/main_widget.py` | 主窗口 | 刷新按钮 + `_on_refresh` + `_any_runner_active` + `_refresh_exec_status` 联动；`_on_import` 进度对话框 + 自动刷新 + 执行中守卫；导入 `QProgressDialog` |

依赖顺序：Task 1（图标）独立；Task 2（model）独立；Task 3 依赖 Task 2 签名；Task 4 依赖 Task 1；Task 5 依赖 Tasks 2/3/4。

---

### Task 1: `make_icon` 新增 `"refresh"` 图标

**Files:**
- Modify: `widgets/通用/ui_common.py:17-19`（导入）、`:141-153`（分支 + 缩放集）

- [ ] **Step 1: 在 `ui_common.py` 的 QtCore 导入加 `QRect`**

> 注：`QRect` 属 `PyQt5.QtCore`（`from PyQt5.QtGui import QRect` 会 ImportError），故加到 QtCore 行。

`widgets/通用/ui_common.py:16-19` 改为：

```python
from PyQt5.QtCore import QPoint, QRect, Qt, pyqtSignal
from PyQt5.QtGui import (
    QColor, QCursor, QFont, QIcon, QPainter, QPen, QPixmap, QPolygon,
)
```

- [ ] **Step 2: 在 `make_icon` 的 `"minimize"` 分支后、`else` 之前插 `"refresh"` 分支**

`widgets/通用/ui_common.py:145` 后（`drawRoundedRect(7, 25, 18, 4, 2, 2)` 那行之后、`else:` 之前）插入：

```python
    elif kind == "refresh":
        # 圆弧箭头（刷新语义）：蓝灰圆弧 + 箭头头，与 exec/settings 同为底部功能按钮
        p.setPen(QPen(QColor("#2b5fa0"), 3, cap=Qt.RoundCap))
        p.setBrush(Qt.NoBrush)
        p.drawArc(QRect(6, 6, 20, 20), 30 * 16, 300 * 16)   # 300° 弧，缺口在右上
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#2b5fa0"))
        p.drawPolygon(QPolygon([QPoint(22, 6), QPoint(28, 12), QPoint(16, 12)]))  # 箭头头
```

- [ ] **Step 3: 把 `"refresh"` 加入底部按钮 48px 缩放集**

`widgets/通用/ui_common.py:151` 改为：

```python
    if kind in ("exec", "settings", "refresh"):
        pm = pm.scaled(48, 48, transformMode=Qt.SmoothTransformation)  # 底部功能按钮图标放大
```

- [ ] **Step 4: 在 `ui_common` 冒烟的 `make_icon` 循环加 `"refresh"`**

`widgets/通用/ui_common.py:250-253`（`__main__` 内 `make_icon` 循环）改为（把 `"refresh"` 加入遍历元组，复用既有 `isNull` 断言，DRY 于单独断言）：

```python
    # make_icon：各类别（含未知回退）生成非空图标；exec/settings/refresh 放大 48px
    for kind in ("resource", "variable", "step", "composite", "template",
                 "exec", "settings", "refresh", "default", "未知"):
        assert not make_icon(kind).isNull(), kind
    assert make_icon("exec").availableSizes()
```

- [ ] **Step 5: 运行冒烟验证通过**

Run: `python -m widgets.通用.ui_common`
Expected: 输出原有冒烟 OK 行（无 AssertionError）。

- [ ] **Step 6: 回归检查点**

Run: `python -m widgets.通用.ui_common`
Expected: PASS（本任务仅动图标工厂，无下游行为变更）。

---

### Task 2: `StepManager.copy_source_templates` 加 `progress_cb`

**Files:**
- Modify: `model/步骤/step_manager.py:28-32`（导入）、`:271-294`（方法重构）、冒烟 `:536-561`

- [ ] **Step 1: 在 `step_manager.py` 的 typing 导入加 `Callable`**

`model/步骤/step_manager.py:32` 改为：

```python
from typing import Callable, Dict, List, Optional, Tuple
```

- [ ] **Step 2: 重写 `copy_source_templates` + 抽 `_iter_source_templates` 生成器**

`model/步骤/step_manager.py:271-294`（原 `copy_source_templates` 整体）替换为：

```python
    def _iter_source_templates(self, source_dir: str):
        """遍历源 ``actions/`` 文件夹，yield ``(src, rel_dir, label)`` 候选。

        跳过 ``base.py``/``__init__.py``/``__main__.py``/``__pycache__``
        （包骨架与自检脚本，无步骤类）。遍历顺序与原 ``copy_source_templates``
        一致：``os.walk`` + ``sorted(files)``。``label`` 为相对源目录的正斜杠显示名
        （如 ``控制流程/延时.py``），供进度回调展示。
        """
        for root, dirs, files in os.walk(source_dir):
            dirs[:] = [d for d in dirs if d != "__pycache__"]
            for name in sorted(files):
                if not name.endswith(".py") \
                        or name in ("base.py", "__init__.py", "__main__.py"):
                    continue
                src = os.path.join(root, name)
                rel_dir = os.path.relpath(root, source_dir)
                rel_dir = "" if rel_dir == "." else rel_dir.replace("\\", "/")
                label = (rel_dir + "/" + name) if rel_dir else name
                yield src, rel_dir, label

    def copy_source_templates(
            self, source_dir: str,
            progress_cb: Optional[Callable[[int, int, str], bool]] = None) -> int:
        """把源码 ``actions/`` 下 .py 模板按相对目录全部加入工程；返回成功数。

        跳过 ``base.py`` / ``__init__.py`` / ``__main__.py`` / ``__pycache__``
        （包骨架与自检脚本，无步骤类——跳过而非回滚报错）。

        逐文件以 ``quiet=True`` 调 :meth:`add_template`：压制每个文件的
        ``load`` 摘要与「添加模板成功」info（N 个文件否则刷出 N×2 行）；
        失败/冲突仍记 ERROR，最终成功数由调用方
        （:meth:`widgets.main_widget.MainWindow._on_import`）打一行摘要。

        ``progress_cb(done, total, label) -> bool``：每导入一个文件**前**调一次，
        ``done`` 为 1 基序号（第几个）、``total`` 为候选总数、``label`` 为显示名；
        返回 False 中止循环（已导入文件保留）。``None``（默认）= 无进度、不可取消，
        行为与未加参数时完全一致。
        """
        candidates = list(self._iter_source_templates(source_dir))
        total = len(candidates)
        added = 0
        for i, (src, rel_dir, label) in enumerate(candidates):
            if progress_cb is not None:
                if not progress_cb(i + 1, total, label):
                    break                      # 取消：已导入的保留，跳出
            if self.add_template(src, rel_dir, quiet=True):
                added += 1
        return added
```

- [ ] **Step 3: 在 `step_manager` 冒烟加 `progress_cb` 断言**

`model/步骤/step_manager.py` `__main__`，在现有 `copy_source_templates(src)` 断言块（`:552-561`，`assert mgr.copy_source_templates(src) == 2` 那段）之后、仍在 `with tempfile.TemporaryDirectory() as td:` 块内，加：

```python
        # ---- copy_source_templates + progress_cb（功能2）----
        # progress_cb=None 行为不变已由上面 == 2 覆盖；下面测回调与取消
        src2 = os.path.join(td, "src2")
        os.makedirs(src2)
        for nm, nm_lit in (("甲.py", "甲"), ("乙.py", "乙")):
            with open(os.path.join(src2, nm), "w", encoding="utf-8") as fh:
                fh.write(LOCAL.replace('name = "本地"', 'name = "%s"' % nm_lit))
        seen = []

        def cb(done, tot, label):
            seen.append((done, tot, label))
            return True

        n = mgr.copy_source_templates(src2, progress_cb=cb)
        assert n == 2
        assert len(seen) == 2
        assert [s[0] for s in seen] == [1, 2]            # done 1 基递增
        assert all(s[1] == 2 for s in seen)             # total 稳定
        assert {s[2] for s in seen} == {"甲.py", "乙.py"}   # 顺序不依赖排序
        assert "甲" in mgr.template_paths() and "乙" in mgr.template_paths()
        # 取消：done=1 继续（导入排序首者），done=2 中止（不导入第二个）
        src3 = os.path.join(td, "src3")
        os.makedirs(src3)
        for nm, nm_lit in (("丙.py", "丙"), ("丁.py", "丁")):
            with open(os.path.join(src3, nm), "w", encoding="utf-8") as fh:
                fh.write(LOCAL.replace('name = "本地"', 'name = "%s"' % nm_lit))
        seen2 = []

        def cb_cancel(done, _tot, label):
            seen2.append((done, label))
            return done == 1                            # 仅第一个继续

        n2 = mgr.copy_source_templates(src3, progress_cb=cb_cancel)
        assert n2 == 1                                 # 只导入排序首者
        assert [s[0] for s in seen2] == [1, 2]
        first_label, second_label = seen2[0][1], seen2[1][1]
        assert {first_label, second_label} == {"丙.py", "丁.py"}
        assert first_label[:-3] in mgr.template_paths()       # 第一个被导入
        assert second_label[:-3] not in mgr.template_paths()  # 第二个被取消
```

- [ ] **Step 4: 运行冒烟验证通过**

Run: `python -m model.步骤.step_manager`
Expected: 输出 `StepManager smoke OK`（无 AssertionError）。

- [ ] **Step 5: 回归检查点**

Run: `python -m model.步骤.step_manager`
Expected: PASS（含原有 `copy_source_templates(src) == 2` 与新 progress_cb 断言）。

---

### Task 3: `StepTreeWidget.import_templates` 透传 `progress_cb`

**Files:**
- Modify: `widgets/树/step_tree_widget.py:215-219`、冒烟 `:737-767`

- [ ] **Step 1: 改 `import_templates` 签名透传 `progress_cb`**

`widgets/树/step_tree_widget.py:215-219` 改为：

```python
    def import_templates(self, source_dir: str, progress_cb=None) -> int:
        """把外部 actions 文件夹的 .py 步骤文件全部导入（递归；覆盖同名；坏文件逐文件回滚）；刷新树并返回成功数。

        ``progress_cb`` 透传给 :meth:`StepManager.copy_source_templates`
        （功能2 进度条）；``None`` = 无进度，行为同前。
        """
        n = self._mgr.copy_source_templates(source_dir, progress_cb)
        self.refresh()
        return n
```

- [ ] **Step 2: 在 `step_tree_widget` 冒烟加 `progress_cb` 透传断言**

`widgets/树/step_tree_widget.py` `__main__`，在现有 `import_templates(tmp)` 断言块（`:753-760`，`n = tree.import_templates(tmp)` … `assert pkg.is_file("actions/导入一.py")`）之后、`finally` 清理 `tmp` 之前，加：

```python
        # ---- import_templates 透传 progress_cb（功能2）----
        seen = []

        def cb(done, tot, label):
            seen.append((done, tot, label))
            return True

        n2 = tree.import_templates(tmp, progress_cb=cb)
        assert n2 == 3                                 # 与无 cb 一致（坏.py 回滚不计）
        assert [s[0] for s in seen] == [1, 2, 3, 4]   # 4 候选（含坏.py），done 1 基递增
        assert all(s[1] == 4 for s in seen)           # total 稳定
        assert {s[2] for s in seen} == \
            {"导入一.py", "导入二.py", "坏.py", "子文件夹/导入三.py"}
```

- [ ] **Step 3: 运行冒烟验证通过**

Run: `python -m widgets.树.step_tree_widget`
Expected: 输出 `StepTreeWidget smoke OK`。

- [ ] **Step 4: 回归检查点**

Run: `python -m widgets.树.step_tree_widget`
Expected: PASS。

---

### Task 4: 活动栏刷新按钮 + `_on_refresh` + 执行中禁用

**Files:**
- Modify: `widgets/main_widget.py:31-35`（导入）、`:142`（属性）、`:237-254`（加 `_on_refresh`）、`:545-568`（`_any_runner_active` + 联动）、`:1116-1124`（加按钮）

- [ ] **Step 1: 在 `main_widget.py` 的 QtWidgets 导入加 `QProgressDialog`**

`widgets/main_widget.py:31-35` 改为：

```python
from PyQt5.QtWidgets import (
    QApplication, QDialog, QFileDialog, QHBoxLayout, QLabel,
    QMainWindow, QMenu, QMessageBox, QProgressDialog, QSplitter,
    QStackedWidget, QSystemTrayIcon, QToolButton, QWidget,
)
```

- [ ] **Step 2: 加 `_refresh_btn` 属性声明**

`widgets/main_widget.py:142`（`self._min_btn: Optional[QToolButton] = None` 那行）后加：

```python
        self._refresh_btn: Optional[QToolButton] = None   # 活动栏底部「刷新」按钮
```

- [ ] **Step 3: 在 `_build_project_view` 加刷新按钮（设置与最小化之间）**

`widgets/main_widget.py:1121-1124`（`_settings_btn` 与 `_min_btn` 之间）改为：

```python
        self._settings_btn = self._switcher.add_bottom_button(
            "设置", make_icon("settings"), self._on_settings_clicked)
        self._refresh_btn = self._switcher.add_bottom_button(
            "刷新", make_icon("refresh"), self._on_refresh)
        self._min_btn = self._switcher.add_bottom_button(
            "最小化", make_icon("minimize"), self._on_minimize_clicked)
```

- [ ] **Step 4: 加 `_on_refresh` 方法（复用 `_open_package`）**

`widgets/main_widget.py` 在 `_on_import` 方法（`:237`）之后加：

```python
    def _on_refresh(self) -> None:
        """活动栏「刷新」按钮：重跑 _open_package（=重进界面）。

        重建 StepManager（含新导入模板）+ 全部管理树 + 从 step_list.json 重解码
        步骤列表（步骤对象随之刷新）+ 重接信号 + 重启热键监听。内存包已写穿，
        无内存数据丢失；窗口标题/尺寸不变。执行中由按钮禁用规避（见
        _refresh_exec_status 末尾）。
        """
        if self._package is None:
            return
        LogModel.instance().info("刷新工程视图")
        self._open_package(self._package, self._kscp_path)
```

- [ ] **Step 5: 加 `_any_runner_active` 谓词 + DRY `_recompute_lock` + `_refresh_exec_status` 联动**

> 实测发现 `_recompute_lock`（`main_widget.py:538`）已内联同一谓词 `any(r.state is not READY …)`。故把谓词抽成 `_any_runner_active`，`_recompute_lock` 改用它（单一真源），并在 `_refresh_exec_status` 末尾用它驱动刷新按钮。

`widgets/main_widget.py` 把 `_recompute_lock`（`:538-543`）替换为谓词方法 + 瘦身后调用：

```python
    def _any_runner_active(self) -> bool:
        """是否有执行器处于 RUNNING/STOPPING（刷新/导入须避开，避免重载打断运行线程）。"""
        return any(r.state is not StepRunnerState.READY
                   for r in self._runners.values())

    def _recompute_lock(self) -> None:
        """按活跃执行器集合重算 UI 锁定（任一页非 READY → 锁定；不用加减计数防漏算）。"""
        active = self._any_runner_active()
        self._set_exec_locked(active)
        self._update_exec_button()
```

`_refresh_exec_status` 末尾（`:568` `self._set_exec_status(text)` 之后）追加：

```python
        if self._refresh_btn is not None:
            self._refresh_btn.setEnabled(not self._any_runner_active())
```

- [ ] **Step 6: 在 `main_widget` 冒烟加刷新按钮断言**

`widgets/main_widget.py` `__main__` 末尾（最终 `print` 之前）加。用**新窗口** `win2`（`win` 经前面大量断言已被改得复杂，复用干净工程文件 `tmp` 重建一个，状态可控）：

```python
    # ---- 功能1：活动栏刷新按钮 ----
    win2 = MainWindow(tmp)                            # 复用已存盘工程，干净窗口
    win2.show()
    assert win2._refresh_btn is not None
    # 底部按钮顺序：执行 / 设置 / 刷新 / 最小化
    assert win2._switcher._bottom_buttons == \
        [win2._exec_btn, win2._settings_btn, win2._refresh_btn, win2._min_btn]
    # 点击刷新 → _open_package 重建（_managers[0] 与 _step_mgr 换新实例）
    old_sl = win2._managers[0]
    old_step_mgr = win2._step_mgr
    win2._on_refresh()
    assert win2._managers[0] is not old_sl
    assert win2._step_mgr is not old_step_mgr
    assert len(win2._managers) == 5                   # 重建后结构不变
    # 执行中（runner RUNNING）→ 刷新按钮禁用；清空后恢复
    import types as _types
    win2._runners.clear()
    assert win2._any_runner_active() is False
    assert win2._refresh_btn.isEnabled()
    win2._runners["别的页"] = _types.SimpleNamespace(state=StepRunnerState.RUNNING)
    assert win2._any_runner_active() is True
    win2._refresh_exec_status()
    assert not win2._refresh_btn.isEnabled()
    win2._runners.clear()
    win2._refresh_exec_status()
    assert win2._refresh_btn.isEnabled()
```

- [ ] **Step 7: 运行冒烟验证通过**

Run: `python -m widgets.main_widget`
Expected: 输出原有冒烟 OK 行 + 新断言通过（无 AssertionError）。

- [ ] **Step 8: 回归检查点**

Run: `python -m widgets.main_widget`
Expected: PASS。

---

### Task 5: `_on_import` 进度对话框 + 成功后自动刷新 + 执行中守卫

**Files:**
- Modify: `widgets/main_widget.py:237-254`（`_on_import` 重写）、冒烟（接 Task 4 的 `win`）

- [ ] **Step 1: 重写 `_on_import` 套进度对话框 + 自动刷新 + 守卫**

`widgets/main_widget.py:237-254`（整个 `_on_import`）替换为：

```python
    def _on_import(self) -> None:
        if self._package is None or self._step_mgr is None:
            return
        if self._any_runner_active():
            QMessageBox.warning(self, "导入步骤模板", "执行中，请先停止再导入")
            return
        folder = QFileDialog.getExistingDirectory(
            self, "导入步骤模板 — 选择 actions 文件夹", "")
        if not folder:
            return
        stree = self._step_mgr.tree_widget()
        assert isinstance(stree, StepTreeWidget)
        prog = QProgressDialog("导入步骤模板…", "取消", 0, 1, self)
        prog.setWindowModality(Qt.WindowModal)
        prog.setMinimumDuration(0)
        prog.setValue(0)

        def cb(done: int, tot: int, label: str) -> bool:
            prog.setRange(0, max(tot, 1))
            prog.setValue(done)
            prog.setLabelText("当前: %s" % label)
            QApplication.processEvents()
            return not prog.wasCanceled()

        n = stree.import_templates(folder, cb)
        prog.close()

        sb = self.statusBar()
        assert sb is not None
        if prog.wasCanceled() and n > 0:
            sb.showMessage("已取消，已导入 %d 个步骤模板" % n, 5000)
            LogModel.instance().warning("导入步骤模板已取消: 已导入 %d 个" % n)
        elif prog.wasCanceled():
            sb.showMessage("已取消导入", 5000)
            LogModel.instance().warning("导入步骤模板已取消")
        elif n:
            sb.showMessage("已导入 %d 个步骤模板" % n, 5000)
            LogModel.instance().info("导入步骤模板完成: 成功 %d 个" % n)
        else:
            sb.showMessage("没有可导入的步骤模板", 5000)
            LogModel.instance().warning("导入步骤模板: 没有成功导入任何模板（详见日志）")

        if n > 0:
            self._on_refresh()          # 自动全量重载（=重进界面，步骤对象刷新）
```

- [ ] **Step 2: 在 `main_widget` 冒烟加导入进度 + 自动刷新断言**

`widgets/main_widget.py` `__main__`，接 Task 4 Step 6 的断言块之后（`win2` 此时 `_runners` 已清空、刷新按钮可用）加。沿用本文件既有 `QMessageBox.information` 打补丁写法（类属性赋值 + finally 还原）：

```python
    # ---- 功能2：导入进度条 + 成功后自动刷新 ----
    IMP = GOOD.replace('name = "示例"', 'name = "导入甲"').replace("测试模板", "导入甲")
    imp_dir = tempfile.mkdtemp(prefix="kscript_imp_")
    try:
        with open(os.path.join(imp_dir, "导入甲.py"), "w", encoding="utf-8") as fh:
            fh.write(IMP)
        _orig_ged = QFileDialog.getExistingDirectory
        QFileDialog.getExistingDirectory = lambda *a, **k: imp_dir
        pre_import_sl = win2._managers[0]
        try:
            win2._on_import()
        finally:
            QFileDialog.getExistingDirectory = _orig_ged
        # 自动刷新：_managers[0] 又换新；新模板在重建后的 shared mgr 中
        assert win2._managers[0] is not pre_import_sl
        assert "导入甲" in win2._managers[0]._mgr.template_paths()
    finally:
        import shutil as _shutil
        _shutil.rmtree(imp_dir, ignore_errors=True)
```

- [ ] **Step 3: 运行冒烟验证通过**

Run: `python -m widgets.main_widget`
Expected: 输出原有冒烟 OK 行 + Task 4 与本任务新断言通过。

- [ ] **Step 4: 全量回归**

Run: `python tests/smoke_all.py`
Expected: 55 模块冒烟 + 2 自检全过，非零退出码表示失败。本任务改了 4 个模块（ui_common / step_manager / step_tree_widget / main_widget），其冒烟含新断言；其余模块不受影响。

---

## Self-Review

**1. Spec coverage:**
- 功能1 刷新按钮：Task 4（位置/图标/`_on_refresh`/执行中禁用）✓
- 功能2 进度条：Task 2（`progress_cb`）+ Task 3（透传）+ Task 5（`QProgressDialog` + 取消 + 自动刷新 + 守卫）✓
- 改动文件清单 4 文件：Task 1/2/3/4+5 覆盖 ✓
- 测试：每任务 `__main__` 冒烟 + Task 5 末尾 `smoke_all.py` ✓

**2. Placeholder scan:** 无 TBD/TODO/「适当处理」；每步含完整代码 ✓

**3. Type/signature consistency:**
- `progress_cb: Optional[Callable[[int,int,str], bool]]`（Task 2）→ `import_templates(source_dir, progress_cb=None)`（Task 3）→ `stree.import_templates(folder, cb)`（Task 5）签名一致 ✓
- 回调 `(done, tot, label)`：Task 2 `progress_cb(i+1, total, label)`；Task 3 透传；Task 5 `cb(done, tot, label)` 一致 ✓
- `_on_refresh`（Task 4）被 Task 5 `self._on_refresh()` 调用 ✓
- `_any_runner_active`（Task 4）被 Task 5 `_on_import` 守卫调用 ✓
- `make_icon("refresh")`（Task 1）被 Task 4 `add_bottom_button("刷新", make_icon("refresh"), …)` 调用 ✓
- spec 提的 `_rel_label` 辅助已折进 `_iter_source_templates` 的 `label`（plan 比 spec 更简，一致性在 plan 内自洽）✓
