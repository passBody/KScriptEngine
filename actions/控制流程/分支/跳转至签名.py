# -*- coding: utf-8 -*-
"""
跳转至签名步骤（控制流程/分支）
================================

:class:`JumpToTag`：跳转到当前页扁平执行序列中第一个 ``tag`` 匹配签名的步骤。

输入槽
------
* ``签名``（string）：目标步骤的签名（卡片顶部「签名…」栏填写的 tag）。

运行规则
--------
* 由执行器注入的 ``_exec_index``/``_exec_plan`` 定位自身索引，
  在 plan 中按执行序找第一个 ``tag`` 含签名的步骤，返回 ``target - self`` 偏移。
* 未注入执行上下文（编辑期单跑等）或未找到签名：抛 :class:`ValueError`
  （由 do() 置 ERROR 停步）。

自定义视图
----------
* 下拉框列出当前页全部步骤的签名供选择，选中即回填到「签名」输入槽。
  签名来源经宿主注入（``io._jump_tags``）：编辑期由管理树在 ``set_list``
  时把当前页全部 ``tag`` 列表注入各步骤 io（仿 ``_apply_local_picker`` 模式）。
"""
from dataclasses import dataclass
from typing import List, Optional

from PyQt5.QtWidgets import QComboBox, QLabel, QVBoxLayout, QWidget

from model.log_model import LogModel
from model.步骤.step import Step, StepStatus

__all__ = ["JumpToTag"]


@dataclass
class JumpToTagInput:
    """输入：目标签名（string）。"""
    签名: "string" = ""  # type: ignore


@dataclass
class JumpToTagOutput:
    """无输出。"""
    pass


class JumpToTag(Step):
    """跳转至签名步骤：跳到当前页执行序列中匹配签名的步骤。"""

    name = "跳转至签名"
    description = "跳转到当前页执行序列中第一个签名匹配的步骤"
    input_class = JumpToTagInput
    output_class = JumpToTagOutput

    def run(self) -> int:
        plan = self._exec_plan
        idx = self._exec_index
        if plan is None or idx is None:
            raise ValueError("跳转至签名：无执行上下文（仅可在执行流程中使用）")
        sig = self.inputs.签名 or ""
        sig = sig.strip()
        if not sig:
            raise ValueError("跳转至签名：签名为空")
        for i, entry in enumerate(plan):
            if sig in (entry.step.tag or ""):
                return i - idx
        raise ValueError("跳转至签名：未找到签名「%s」" % sig)

    def info_widget(self, parent: Optional[QWidget] = None) -> QWidget:
        """自定义视图：下拉框选择当前页已有签名回填输入槽。"""
        return _JumpTagView(self, parent)


class _JumpTagView(QWidget):
    """跳转至签名步骤的自定义卡片视图：下拉框 + 提示。

    下拉项来源 ``io._jump_tags``（宿主注入的当前页全部 tag 列表，已去空去重）。
    选中即经 ``io.change_value`` 写回「签名」输入槽；空列表时提示用户先为
    其它步骤设置签名。
    """

    def __init__(self, step: "JumpToTag", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._step = step

        self._hint = QLabel("选择已有签名填入「签名」输入槽")
        self._hint.setStyleSheet("color:#888;")
        self._hint.setWordWrap(True)

        self._combo = QComboBox()
        self._combo.setEditable(True)
        self._combo.setToolTip("下拉选择当前页已有签名，或直接编辑")
        self._combo.currentTextChanged.connect(self._on_changed)
        self._syncing = False          # 回写循环阻塞标志（须在 _sync 前置位）
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        lay.addWidget(self._hint)
        lay.addWidget(self._combo)
        self._sync()

        # io 槽值变化 → 同步下拉显示
        step.io.add_listener(self._sync)

    # ---- 数据 ----
    def _tags(self) -> List[str]:
        """当前页全部签名（去空去重，保持插入序）；未注入 → 空列表。"""
        raw = getattr(self._step.io, "_jump_tags", None) or []
        seen = set()
        out = []
        for t in raw:
            if not isinstance(t, str) or not t.strip():
                continue
            if t in seen:
                continue
            seen.add(t)
            out.append(t)
        return out

    def _sync(self) -> None:
        """刷新下拉项 + 当前显示 = 输入槽当前值（阻塞回写避免循环）。"""
        if self._syncing:
            return
        self._syncing = True
        try:
            self._combo.blockSignals(True)
            cur = self._step.io.input_value(0) or ""
            tags = self._tags()
            self._combo.clear()
            if tags:
                self._combo.addItems(tags)
            self._combo.setEditText(cur)
            self._hint.setText("选择已有签名填入「签名」输入槽（当前页 %d 个签名）"
                               % len(tags))
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
# 冒烟演示：直接 ``python -m actions.控制流程.分支.跳转至签名`` 运行
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

    # 构造一个目标步骤（带签名），与跳转步骤同处一个列表
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

    store = StepListStore.create_empty()
    store.add_group("组")
    sl = StepList.create_empty()
    target = _ProbeStep.create_default(tree, pkg)
    target.tag = "目标签名"
    sl.add(target)
    jmp = JumpToTag.create_default(tree, pkg)
    jmp.io.change_value("input", 0, "目标签名")
    sl.add(jmp)
    after = _ProbeStep.create_default(tree, pkg)
    after.tag = "后置"
    sl.add(after)
    store.add_list("组/列表", sl)

    # create_default：槽类型推导
    assert jmp.io._input_type == ["string"]
    assert jmp.io._output_type == []
    assert jmp.name == "跳转至签名"

    # 手动注入执行上下文（模拟 StepRunner）：扁平序列 = [target, jmp, after]
    plan = [type("E", (), {"step": s, "path": "组/列表"})() for s in (target, jmp, after)]
    jmp._exec_index = 1
    jmp._exec_plan = plan
    jmp.io.change_value("input", 0, "目标签名")
    jmp.input()                                 # 模拟 do 的 input 步骤
    # run 返回 target(0) - self(1) = -1（回跳到目标）
    assert jmp.run() == -1, jmp.run()
    # 模糊匹配：签名是目标的子串
    jmp.io.change_value("input", 0, "目标")
    jmp.input()
    assert jmp.run() == -1
    # 前向跳转：把目标放后面
    plan2 = [type("E", (), {"step": after, "path": "组/列表"})(),
             type("E", (), {"step": jmp, "path": "组/列表"})(),
             type("E", (), {"step": target, "path": "组/列表"})()]
    jmp._exec_index = 1
    jmp._exec_plan = plan2
    jmp.io.change_value("input", 0, "目标签名")
    jmp.input()
    assert jmp.run() == 1   # target(2) - self(1)
    jmp._exec_index = None
    jmp._exec_plan = None

    # 未注入执行上下文 → ValueError（编辑期单跑等）
    try:
        jmp.input()
        jmp.run()
        raise AssertionError("无上下文应抛 ValueError")
    except ValueError:
        pass

    # 未找到签名 → ValueError
    jmp._exec_index = 1
    jmp._exec_plan = plan2
    jmp.io.change_value("input", 0, "不存在")
    jmp.input()
    try:
        jmp.run()
        raise AssertionError("未找到签名应抛 ValueError")
    except ValueError:
        pass
    jmp._exec_index = None
    jmp._exec_plan = None

    # do() 整合：注入后返回偏移、状态 FINISHED
    jmp._exec_index = 1
    jmp._exec_plan = plan2
    jmp.io.change_value("input", 0, "目标签名")
    assert jmp.do() == 1
    assert jmp.status is StepStatus.FINISHED
    jmp._exec_index = None
    jmp._exec_plan = None

    # do() 失败：未注入 → ERROR + 日志
    LogModel.instance().clear()
    jmp2 = JumpToTag.create_default(tree, pkg)
    jmp2.io.change_value("input", 0, "目标签名")
    try:
        jmp2.do()
        raise AssertionError("无上下文 do 应抛 ValueError 停步")
    except ValueError:
        pass
    assert jmp2.status is StepStatus.ERROR
    assert any("跳转至签名" in e.message for e in LogModel.instance().entries)

    # ---- 卡片体内跳转：合成卡片自跑 pc 循环，须自行注入执行上下文 ----
    # 回归（2026-09-23 实测报错「跳转至签名：无执行上下文」）：卡片体内步骤
    # 不归 StepRunner 管，_run_body 不注入就整类跳转失效。此处走真实执行路径：
    # 体内第 0 步跳「落点」→ 中间那步必须被跳过。
    from model.合成卡片.composite_card import CompositeCard
    from model.合成卡片.composite_definition import CompositeDefinition
    from model.合成卡片.composite_signature import CompositeSignature

    ran = []

    class _RecStep(_ProbeStep):
        name = "记录探针"

        def run(self) -> int:
            ran.append(self.tag)
            return 1

    body = StepList.create_empty()
    j_in = JumpToTag.create_default(tree, pkg)
    j_in.io.change_value("input", 0, "落点")
    j_in.tag = "跳"
    body.add(j_in)
    skipped = _RecStep.create_default(tree, pkg)
    skipped.tag = "被跳过"
    body.add(skipped)
    landed = _RecStep.create_default(tree, pkg)
    landed.tag = "落点"
    body.add(landed)

    CompositeCard.set_resolver(
        lambda ref: CompositeDefinition(body, CompositeSignature.empty()))
    card = CompositeCard("组/卡片", tree, pkg)
    assert card.do() == 1
    assert card.status is StepStatus.FINISHED, card.status
    assert ran == ["落点"], ran            # 跳转生效：中间的「被跳过」没跑

    # ---- info_widget：下拉框列签名 + 选中回填 ----
    jmp.io.change_value("input", 0, "")
    jmp.io._jump_tags = ["目标签名", "后置", "目标签名"]   # 含重复，应去重
    view = jmp.info_widget()
    assert view is not None
    combo = view.findChild(QComboBox)
    assert combo is not None
    # 下拉项 = 去重后的两个签名
    assert [combo.itemText(i) for i in range(combo.count())] == ["目标签名", "后置"]
    # 选中 → 回填输入槽
    combo.setCurrentText("后置")
    assert jmp.io.input_value(0) == "后置", jmp.io.input_value(0)
    # 输入槽被外部改 → 下拉显示同步
    jmp.io.change_value("input", 0, "目标签名")
    assert combo.currentText() == "目标签名"
    # 空 tag 列表 → 提示先设置签名
    jmp.io._jump_tags = []
    view._sync()
    assert "0 个签名" in view._hint.text()
    del jmp.io._jump_tags   # 清理注入

    # 往返
    jmp.io.change_value("input", 0, "目标签名")
    fmt = jmp.to_format_string()
    assert "=" not in fmt and "+" not in fmt and "/" not in fmt
    jmp3 = JumpToTag.from_format_string(fmt, tree, pkg)
    assert isinstance(jmp3, JumpToTag)
    assert jmp3.io.to_format_string() == jmp.io.to_format_string()

    print("JumpToTag smoke OK")
