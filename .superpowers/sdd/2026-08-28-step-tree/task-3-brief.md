# Task 3 Brief: `main_widget.py` 集成(第 4 图标)

> 摘录自实施计划 `docs/superpowers/plans/2026-08-28-step-tree.md`(权威文本)。完整 spec:`docs/superpowers/specs/2026-08-28-step-tree-design.md` §6。

## 本任务在工程中的位置

KScript 是 PyQt5 桌面自动化应用。Task 1 已为 `StepManager` 追加 4 方法;Task 2 已创建 `widgets/step_tree_widget.py`(`StepTreeWidget`/`StepInfoPanel`/`MoveStepDialog`)。本任务把步骤模板树接入 `widgets/main_widget.py`:活动栏**第 4 个图标**「步骤模板」(现有占位「步骤」图标保留)。集成性改动,无「先写失败测试」的独立载体——验证方式 = 带包自检 + 全量回归。

## Global Constraints(全计划适用,本任务必须遵守)

- 非 git 仓库:不提交,「提交」步骤一律替换为「运行冒烟/自检验证」。
- **`step_tree_widget` 不进 `widgets/__init__.py`**(循环导入防线),一律直接模块导入 `from widgets.step_tree_widget import StepTreeWidget`。
- 路径中文合法,勿改目录名。
- `main.py --check` 无输出但 EXIT=0(既有行为,以退出码判定)。

**Files:**
- Modify: `widgets/main_widget.py`(`_make_icon` 加 kind、新增 `StepManagementTree`、managers 列表、import、docstring)

**Interfaces:**
- Consumes: `StepTreeWidget`(Task 2 产出:`StepTreeWidget(package)`、`preview_widget()`)
- Produces: 活动栏第 4 个图标「步骤模板」(占位「步骤」保留);`StepManagementTree` 类

> 红阶段说明:本任务是集成性改动,无「先写失败测试」的独立载体——验证方式为「带包自检 + 全量回归」(与既有 `main --check` 同思路),Step 1-2 合并为直接实现。

## Step 1: 实现 —— `_make_icon` 新增 kind `"template"`(在 `elif kind == "step":` 分支之后、`else:` 之前)

```python
    elif kind == "template":
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#e67e22"))
        p.drawRoundedRect(5, 5, 22, 22, 4, 4)      # 橙色方块（与占位「步骤」裸三横线区分）
        p.setBrush(QColor("#fff3e0"))
        for y in (12, 18, 24):
            p.drawRoundedRect(9, y, 14, 3, 1, 1)   # 方块内三条横线
```

## Step 2: 实现 —— import 行(`from widgets.variable_tree_widget import VariableTreeWidget` 之后)

```python
from widgets.step_tree_widget import StepTreeWidget
```

## Step 3: 实现 —— 新增 `StepManagementTree` 类(在 `VariableManagementTree` 类之后、`PlaceholderManagementTree` 之前)

```python
class StepManagementTree(ManagementTree):
    """步骤模板管理树：``StepTreeWidget`` + 其只读信息面板。"""

    def __init__(self, package: KscpPackage) -> None:
        super().__init__("步骤模板")
        self._package = package
        self._stree: Optional[StepTreeWidget] = None

    def icon(self) -> QIcon:
        return _make_icon("template")

    def tree_widget(self) -> QWidget:
        if self._stree is None:
            self._stree = StepTreeWidget(self._package)
        assert self._stree is not None
        return self._stree

    def preview_widget(self) -> QWidget:
        if self._stree is None:
            self._stree = StepTreeWidget(self._package)
        assert self._stree is not None
        if self._preview is None:
            self._preview = self._stree.preview_widget()
        assert self._preview is not None
        return self._preview
```

## Step 4: 实现 —— `_open_package` 的 managers 列表(占位「步骤」保留,新树追加为第 4 个)

```python
        self._managers = [
            ResourceManagementTree(package),
            VariableManagementTree(package),
            PlaceholderManagementTree("步骤", "step"),
            StepManagementTree(package),
        ]
```

## Step 5: 实现 —— 模块 docstring 第 9-11 行更新为

```python
管理树经 :class:`ManagementTree` 抽象（预留接口）：每个管理树提供左侧树控件
``tree_widget()`` 与中间预览 ``preview_widget()``。当前实现资源/变量/步骤模板
管理树；步骤（列表）管理树用占位项演示「快速切换 + 预留接口」，后续替换为真实
实现即可。步骤模板管理树为活动栏第 4 个图标（占位「步骤」保留）。
```

## Step 6: 验证(替代提交)①—— 空工程自检

Run: `python main.py --check`
Expected: 无输出,EXIT=0(既有行为,以退出码判定)

## Step 7: 验证(替代提交)②—— 带模板工程自检(覆盖第 4 图标真实构建路径)

Run:
```bash
python - <<'PY'
from model.kscp_package import KscpPackage
GOOD = '''# -*- coding: utf-8 -*-
from dataclasses import dataclass
from actions.base import Step

@dataclass
class _In:
    count: "number" = 0

@dataclass
class _Out:
    total: "number" = 0

class DemoStep(Step):
    name = "示例"
    description = "测试模板"
    input_class = _In
    output_class = _Out

    def run(self) -> int:
        return 1
'''
pkg = KscpPackage.create_empty()
pkg.write_file("actions/示例.py", GOOD.encode("utf-8"))
pkg.save("_tmp_check.kscp")
PY
python main.py _tmp_check.kscp --check
rm -f _tmp_check.kscp
```
Expected: 两条命令均 EXIT=0(无输出;若崩溃/异常则以非 0 退出)

## Step 8: 全量回归验证(替代提交)

Run:
```bash
python -m model.step_manager
python -m widgets.step_tree_widget
python -m actions.base
python -m actions.控制流程.time_delay
python -m widgets.step_io_widget
python -m model.kscp_package
python -m model.project_variable
python -m model.variable_tree
python -m model.log_model
python main.py --check
```
Expected: 全部冒烟 OK、`main --check` 无输出但 EXIT=0(以退出码判定)
