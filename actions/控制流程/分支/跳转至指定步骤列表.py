# -*- coding: utf-8 -*-
"""``跳转至指定步骤列表``：列表路径输入，跳到当前页该列表第一个可运行步骤。

输入 ``string`` 列表路径（步骤列表管理树中的路径）；输出无。
run 经执行器注入的执行上下文定位目标列表第一个 enabled 步骤，返回偏移。
自定义视图：下拉框列当前页全部列表路径供选择回填。
"""
from dataclasses import dataclass
from typing import List, Optional

from PyQt5.QtWidgets import QComboBox, QLabel, QVBoxLayout, QWidget

from model.log_model import LogModel
from model.步骤.step import Step, StepStatus

__all__ = ["JumpToList"]


@dataclass
class JumpToListInput:
    """输入：目标列表路径（string）。"""
    列表路径: "string" = ""  # type: ignore


@dataclass
class JumpToListOutput:
    """无输出。"""
    pass


class JumpToList(Step):
    """跳转至指定步骤列表：跳到当前页该列表第一个可运行步骤。"""

    name = "跳转至指定步骤列表"
    description = "跳转到当前页指定步骤列表的第一个可运行步骤"
    input_class = JumpToListInput
    output_class = JumpToListOutput

    def run(self) -> int:
        plan = self._exec_plan
        idx = self._exec_index
        if plan is None or idx is None:
            raise ValueError("跳转至指定步骤列表：无执行上下文（仅可在执行流程中使用）")
        path = (self.inputs.列表路径 or "").strip()
        if not path:
            raise ValueError("跳转至指定步骤列表：列表路径为空")
        for i, entry in enumerate(plan):
            if entry.path == path:
                return i - idx
        raise ValueError("跳转至指定步骤列表：未找到列表路径「%s」" % path)

    def info_widget(self, parent: Optional[QWidget] = None) -> QWidget:
        """自定义视图：下拉框选择当前页已有列表路径回填输入槽。"""
        return _JumpListView(self, parent)


class _JumpListView(QWidget):
    """跳转至指定步骤列表的自定义卡片视图：下拉框 + 提示。

    下拉项来源 ``io._jump_paths``（宿主注入的当前页全部列表路径）。
    选中即经 ``io.change_value`` 写回「列表路径」输入槽。
    """

    def __init__(self, step: "JumpToList", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._step = step

        self._hint = QLabel("选择已有步骤列表路径填入「列表路径」输入槽")
        self._hint.setStyleSheet("color:#888;")
        self._hint.setWordWrap(True)

        self._combo = QComboBox()
        self._combo.setEditable(True)
        self._combo.setToolTip("下拉选择当前页已有列表路径，或直接编辑")
        self._combo.currentTextChanged.connect(self._on_changed)
        self._syncing = False          # 回写循环阻塞标志（须在 _sync 前置位）
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        lay.addWidget(self._hint)
        lay.addWidget(self._combo)
        self._sync()

        step.io.add_listener(self._sync)

    def _paths(self) -> List[str]:
        raw = getattr(self._step.io, "_jump_paths", None) or []
        seen = set()
        out = []
        for p in raw:
            if not isinstance(p, str) or not p.strip():
                continue
            if p in seen:
                continue
            seen.add(p)
            out.append(p)
        return out

    def _sync(self) -> None:
        if self._syncing:
            return
        self._syncing = True
        try:
            self._combo.blockSignals(True)
            cur = self._step.io.input_value(0) or ""
            paths = self._paths()
            self._combo.clear()
            if paths:
                self._combo.addItems(paths)
            self._combo.setEditText(cur)
            self._hint.setText("选择已有步骤列表路径填入「列表路径」输入槽（当前页 %d 个列表）"
                               % len(paths))
        finally:
            self._combo.blockSignals(False)
            self._syncing = False

    def _on_changed(self, text: str) -> None:
        if self._syncing:
            return
        self._syncing = True
        try:
            self._step.io.change_value("input", 0, text)
        finally:
            self._syncing = False


# ================================================================
# 冒烟演示：直接 ``python -m actions.控制流程.分支.跳转至指定步骤列表`` 运行
# ================================================================
if __name__ == "__main__":
    import sys

    from PyQt5.QtWidgets import QApplication

    from model.工程.kscp_package import KscpPackage
    from model.步骤.step import Step, StepStatus
    from model.步骤.step_list import StepList
    from model.步骤.step_list_store import StepListStore
    from model.变量.variable_tree import VariableTree

    _mod = sys.modules[__name__]

    app = QApplication.instance() or QApplication(sys.argv)

    pkg = KscpPackage.create_empty()
    tree = VariableTree.create_empty()

    from dataclasses import dataclass as _dc

    @_dc
    class _ProbeInput:
        pass

    @_dc
    class _ProbeOutput:
        pass

    class _ProbeStep(Step):
        name = "探针"
        description = "测试目标"
        input_class = _ProbeInput
        output_class = _ProbeOutput

        def run(self) -> int:
            return 1

    # 当前页两个列表：组/列表A（2 步）、组/列表B（1 步）
    store = StepListStore.create_empty()
    store.add_group("组")
    sl_a = StepList.create_empty()
    a1 = _ProbeStep.create_default(tree, pkg); sl_a.add(a1)
    a2 = _ProbeStep.create_default(tree, pkg); sl_a.add(a2)
    store.add_list("组/列表A", sl_a)
    sl_b = StepList.create_empty()
    b1 = _ProbeStep.create_default(tree, pkg); sl_b.add(b1)
    store.add_list("组/列表B", sl_b)

    # 跳转步骤本身放在列表A的第二步
    jmp = JumpToList.create_default(tree, pkg)
    jmp.io.change_value("input", 0, "组/列表B")
    sl_a.add(jmp)

    # create_default：槽类型推导
    assert jmp.io._input_type == ["string"]
    assert jmp.io._output_type == []
    assert jmp.name == "跳转至指定步骤列表"

    # 扁平执行序列（模拟 StepRunner）：[a1, a2, jmp, b1]
    plan = [type("E", (), {"step": a1, "path": "组/列表A"})(),
            type("E", (), {"step": a2, "path": "组/列表A"})(),
            type("E", (), {"step": jmp, "path": "组/列表A"})(),
            type("E", (), {"step": b1, "path": "组/列表B"})()]
    jmp._exec_index = 2
    jmp._exec_plan = plan
    # 目标列表B第一个可运行步骤 b1 在索引3，self 在 2 → 偏移 1
    jmp.input()                                 # 模拟 do 的 input 步骤
    assert jmp.run() == 1, jmp.run()
    # 跳到列表A第一步 a1：偏移 -2
    jmp.io.change_value("input", 0, "组/列表A")
    jmp.input()
    assert jmp.run() == -2, jmp.run()
    jmp._exec_index = None
    jmp._exec_plan = None

    # 未注入上下文 → ValueError
    try:
        jmp.input()
        jmp.run()
        raise AssertionError("无上下文应抛 ValueError")
    except ValueError:
        pass

    # 未找到路径 → ValueError
    jmp._exec_index = 2
    jmp._exec_plan = plan
    jmp.io.change_value("input", 0, "不存在/列表")
    jmp.input()
    try:
        jmp.run()
        raise AssertionError("未找到路径应抛 ValueError")
    except ValueError:
        pass
    jmp._exec_index = None
    jmp._exec_plan = None

    # do() 失败：未注入 → ERROR + 日志
    LogModel.instance().clear()
    jmp2 = JumpToList.create_default(tree, pkg)
    jmp2.io.change_value("input", 0, "组/列表B")
    try:
        jmp2.do()
        raise AssertionError("无上下文 do 应抛 ValueError 停步")
    except ValueError:
        pass
    assert jmp2.status is StepStatus.ERROR
    assert any("跳转至指定步骤列表" in e.message for e in LogModel.instance().entries)

    # ---- info_widget：下拉框列路径 + 选中回填 ----
    jmp.io.change_value("input", 0, "")
    jmp.io._jump_paths = ["组/列表A", "组/列表B", "组/列表B"]   # 含重复，应去重
    view = jmp.info_widget()
    assert view is not None
    combo = view.findChild(QComboBox)
    assert combo is not None
    assert [combo.itemText(i) for i in range(combo.count())] == ["组/列表A", "组/列表B"]
    combo.setCurrentText("组/列表B")
    assert jmp.io.input_value(0) == "组/列表B", jmp.io.input_value(0)
    jmp.io.change_value("input", 0, "组/列表A")
    assert combo.currentText() == "组/列表A"
    del jmp.io._jump_paths

    # 往返
    jmp.io.change_value("input", 0, "组/列表B")
    fmt = jmp.to_format_string()
    assert "=" not in fmt and "+" not in fmt and "/" not in fmt
    jmp3 = JumpToList.from_format_string(fmt, tree, pkg)
    assert isinstance(jmp3, JumpToList)
    assert jmp3.io.to_format_string() == jmp.io.to_format_string()

    print("JumpToList smoke OK")
