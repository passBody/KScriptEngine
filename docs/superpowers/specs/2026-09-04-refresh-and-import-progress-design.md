# 活动栏刷新按钮 + 导入进度条 设计

- 日期：2026-09-04
- 范围：`widgets/main_widget.py`、`widgets/通用/ui_common.py`、`widgets/树/step_tree_widget.py`、`model/步骤/step_manager.py`
- 目标：解决「导入 actions 包后步骤列表对象不刷新、须重启软件才生效」的痛点，并给导入过程加进度反馈。

## 背景与根因

### 现状
- 工程打开走 `MainWindow._open_package(package, path)`（`main_widget.py:1183`）：新建 `StepManager` + `load()` 注册模板，再建 5 棵管理树（步骤列表 / 合成卡片 / 变量 / 步骤模板 / 资源），从 `step_list.json` 重解码步骤列表，接信号、重启页热键监听、`_reset_project_view` 重填切换栏与两个栈。**这就是「进入界面」的全部副作用。**
- 导入走 `MainWindow._on_import`（`main_widget.py:237`）→ `StepTreeWidget.import_templates(folder)`（`step_tree_widget.py:215`）→ `StepManager.copy_source_templates(source_dir)`（`step_manager.py:271`）：遍历源文件夹，逐个 `add_template(quiet=True)`（每个文件 write→`load()`→无贡献回滚），返回成功数。`import_templates` 末尾调 `StepTreeWidget.refresh()`，**模板树会刷新**。
- `StepManager` 在导入后**确已**重载注册表（`load()` 用唯一前缀模块名 `_kscp%d_actions_…`，无 `sys.modules` 旧类串包），`shared_mgr.template_paths()` 含新模板。

### 根因
步骤列表里**已存在的步骤对象/卡片**是工程打开时按旧注册表类实例化的；导入后注册表虽更新，但步骤列表不会从 `step_list.json` 重新解码、卡片不重建 → 表现为「对象没刷新」。重启软件 = 重新跑 `_open_package` = 用新注册表重解码 `step_list.json`，所以重启才生效。

### 关键事实（决定方案安全性）
- `KscpPackage` 是**内存模型**（`_files: Dict[str,bytes]`）；各 host 写穿：`StepListManagementTree._save_store`（`management_trees.py:269`）每次变更即 `package.write_file("step_list.json", …)`，变量树同理（`variable_tree_widget.py:158`）。actions 模板文件也是内存写穿。
- 因此**对同一个内存 `KscpPackage` 重跑 `_open_package` 不丢任何内存状态**（落盘的 .kscp ZIP 另由 Ctrl+S 负责，不在本设计范围）。
- `_open_package` 幂等：`_project_widget` 已建则只 `_reset_project_view`（清旧控件 `deleteLater()` 再重填），`_project_sized` 保持 True 不重置窗口尺寸，`_start_page_listeners` 先停后起。

## 功能 1：活动栏刷新按钮

### 位置与图标
在 `_build_project_view`（`main_widget.py:1108`）里，于「设置」与「最小化」之间加底部按钮，复用 `ActivityBar.add_bottom_button`：

```python
self._refresh_btn = self._switcher.add_bottom_button(
    "刷新", make_icon("refresh"), self._on_refresh)
```

底部按钮顺序：执行 → 设置 → **刷新** → 最小化。`add_bottom_button` 按调用顺序追加到栏底，故在 `_settings_btn` 之后、`_min_btn` 之前插入此调用即可。

图标：`widgets/通用/ui_common.py:make_icon` 新增 `"refresh"` kind，画圆弧箭头 ↻（48px，与 exec/settings/minimize 同风格）。不使用 Qt 标准图标，保视觉一致。

### 刷新逻辑
复用 `_open_package`，不另造轮子：

```python
def _on_refresh(self) -> None:
    if self._package is None:
        return
    LogModel.instance().info("刷新工程视图")
    self._open_package(self._package, self._kscp_path)
```

效果：重建 StepManager（含新导入模板）→ 全部管理树 → 从 `step_list.json` 重解码步骤列表（步骤对象刷新）→ 重接信号 → 重启热键监听。窗口标题/尺寸不变。

### 执行中禁用
重跑 `_open_package` 会 `_runners.clear()`（仅清字典，不停运行线程）；执行中刷新有崩溃风险。故执行器有 RUNNING/STOPPING 时禁用刷新按钮。新增谓词，挂到状态变更中央入口 `_refresh_exec_status`（`main_widget.py:545`）：

```python
def _any_runner_active(self) -> bool:
    return any(r.state is not StepRunnerState.READY
               for r in self._runners.values())
```

在 `_refresh_exec_status` 末尾追加：

```python
if self._refresh_btn is not None:
    self._refresh_btn.setEnabled(not self._any_runner_active())
```

`_refresh_exec_status` 已在所有执行态变化处被调用（416/536/685/707/726/933 等），刷新按钮启用态随执行态自动同步。

类属性声明：在 `_min_btn` 声明附近（`main_widget.py:142`）加 `self._refresh_btn: Optional[QToolButton] = None`。

## 功能 2：导入进度条 + 成功后自动刷新

### StepManager 加进度回调
`model/步骤/step_manager.py:copy_source_templates` 加 `progress_cb` 参数，**保持无 Qt 依赖**（可单测）：

```python
from typing import Callable, Optional

def copy_source_templates(
        self, source_dir: str,
        progress_cb: Optional[Callable[[int, int, str], bool]] = None) -> int:
    candidates = list(self._iter_source_templates(source_dir))  # 先收集 → 得 total
    total = len(candidates)
    added = 0
    for i, (src, rel_dir) in enumerate(candidates):
        if progress_cb is not None:
            # done = 第几个（1 基）：与「显示导入第几个」语义对齐，末文件打满
            if not progress_cb(i + 1, total, _rel_label(src, source_dir)):
                break                      # 取消：已导入的保留，跳出
        if self.add_template(src, rel_dir, quiet=True):
            added += 1
    return added
```

- 回调签名 `(done: int, total: int, current_label: str) -> bool`；返回 False = 取消。
- 抽 `_iter_source_templates(source_dir) -> Iterator[Tuple[str, str]]` 私有生成器：复刻原 `os.walk` + `dirs[:] = [d for d in dirs if d != "__pycache__"]` + `sorted(files)` + 跳过 `base.py`/`__init__.py`/`__main__.py`，yield `(src_abspath, rel_dir)`。遍历顺序与现状一致。
- `_rel_label(src, source_dir)`：取相对源目录的显示名（如 `控制流程/延时.py`），用于进度文案。私有辅助。
- `progress_cb=None`（默认）= 无进度、不可取消，**行为与现在完全一致**；现有冒烟断言（`step_manager.py` 末尾 `copy_source_templates` 用例）保持通过。
- 每文件仍 `add_template` → `_write_template` → `load(quiet=True)`（逐文件回滚语义不变，O(N²) load 维持现状，进度条让大包导入可容忍）。

### StepTreeWidget 透传
`widgets/树/step_tree_widget.py:import_templates`（`:215`）：

```python
def import_templates(self, source_dir: str,
                     progress_cb=None) -> int:
    n = self._mgr.copy_source_templates(source_dir, progress_cb)
    self.refresh()
    return n
```

### _on_import 套进度对话框
`widgets/main_widget.py:_on_import`（`:237`）：

```python
from PyQt5.QtWidgets import QProgressDialog

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
        self._on_refresh()          # 自动全量重载（=重进界面）
```

要点：
- 进度对话框初始不确定模式（`setRange(0,1); setValue(0)`），第一次回调拿到 `tot` 后切确定模式（不重复 walk，候选收集只在 `copy_source_templates` 内一次）。
- 取消语义：`cb` 返回 False → 循环在下一个文件前跳出；已导入文件保留（`add_template` 原子：write+load+rollback）；当前在途文件已 `add_template` 完成或回滚。取消时若 `n>0` 仍 `_on_refresh()`（UI 与注册表一致）。
- 空文件夹 `tot=0`：`setRange(0,1); setValue(0)` 不崩，文案落到「没有可导入的步骤模板」。
- 成功（`n>0`）自动 `_on_refresh()`，复用功能 1 的全量重载，步骤对象随之刷新。
- 执行中守卫放最前（选文件夹之前），避免执行中触发导入。

## 改动文件清单

| 文件 | 改动 |
|---|---|
| `widgets/通用/ui_common.py` | `make_icon` 新增 `"refresh"` kind（圆弧箭头 48px） |
| `widgets/main_widget.py` | 加 `_refresh_btn` 属性声明；`_build_project_view` 加刷新按钮；新增 `_on_refresh`、`_any_runner_active`；`_refresh_exec_status` 末尾更新刷新按钮启用态；`_on_import` 套进度对话框 + 成功后自动刷新 + 执行中守卫；导入 `QProgressDialog` |
| `model/步骤/step_manager.py` | `copy_source_templates` 加 `progress_cb`；抽 `_iter_source_templates`、`_rel_label` 私有辅助 |
| `widgets/树/step_tree_widget.py` | `import_templates` 透传 `progress_cb` |

## 测试（沿用每模块 `__main__` 冒烟 + `tests/smoke_all.py`）

### `model/步骤/step_manager.py` 冒烟
- `copy_source_templates(src, progress_cb=cb)`：`cb` 收到 `(done, total, label)`；`total` == 候选 .py 数；`done` 单调不降；`label` 含文件名。
- `cb` 返回 False → 中止，返回值 == 已成功数（< total）；已导入文件在 `template_paths()` 中。
- `progress_cb=None`：行为与现状一致（现有 `assert mgr.copy_source_templates(src) == 2` 等断言保留通过）。

### `widgets/main_widget.py` 冒烟
- 活动栏底部 4 按钮：执行 / 设置 / 刷新 / 最小化（顺序正确）。
- 刷新按钮存在、可点击；点击触发 `_open_package` 重建（用临时工程 + 假模板验证重建后步骤列表仍可见、不崩）。
- runner 置 RUNNING → `_refresh_btn.isEnabled() is False`；置 READY → 恢复 True。
- `_on_import` 用临时 actions 文件夹 + 进度回调导入 → `n>0` 且 `_on_refresh` 被调用（可用标志位或重建后 `_step_mgr` 引用变化验证）。

### `widgets/树/step_tree_widget.py` 冒烟
- `import_templates(folder, progress_cb=cb)`：透传 cb 被调用、返回成功数与无 cb 时一致。

## 边界与风险
- **刷新打断执行**：靠执行中禁用刷新按钮规避；`_open_package` 本身 `_runners.clear()` 不停线程，禁用是必要守卫。
- **取消导入**：`add_template` 原子性保证无半成品；取消后 `n>0` 仍 refresh 保证 UI/注册表一致；`n=0` 不 refresh（无变化）。
- **进度 total=0**：空文件夹，`setRange(0,1)` 不崩，文案兜底。
- **`_open_package` 重跑副作用**：重启页热键监听（先停后起）、`_reset_project_view` 旧控件 `deleteLater()`——均为既有行为（切工程时已如此），刷新同工程无额外风险。
- **`make_icon("refresh")` 画法**：32×32 画布缩放到 48px，蓝色圆弧 + 箭头头，与既有底部按钮同一 `QPainter` 风格。
