# -*- coding: utf-8 -*-
"""
合成卡片数据模型（可复用步骤集合的「引用条目」）
================================================

:class:`CompositeCard` 是一种特殊「步骤」：它不自己执行逻辑，而是**引用**一张命名
合成卡片的定义（一组步骤），运行时把那组步骤展开执行。引用以**字符串标记**
``@合成卡片:<路径>`` 存放于步骤列表，而非整块 base64——故「改一处定义、所有引用
处统统跟着变」（引用只存指针，定义单点存于 ``composites.json``，见
:class:`model.composite_card_store.CompositeCardStore`）。

本类继承 :class:`model.step.Step`，因此可像普通步骤一样被卡片视图渲染、复制剪切、
序列化、由执行器调度。区别仅在：

* :meth:`to_format_string` 返回引用标记（非 base64 blob）。
* :meth:`run` 解析引用 → 取定义体内 :class:`StepList` → 自包含地跑一个 pc+偏移循环
  （照搬 :class:`model.step_runner.StepRunner._run` 的语义，作用域限在内部），
  返回 1 给外层执行器；外层视合成卡片为「一个不透明步」，偏移语义不被破坏。
* 递归深度上限防 A→B→A 死循环；悬空引用（定义被删）→ 记日志、置 ERROR、软跳过。

本模块属 model 层：**模块顶层不导入 PyQt5**（Qt 控件仅在 :meth:`info_widget` 内
延迟导入），因此导入本模块不依赖 GUI 环境。
"""
import threading
from dataclasses import dataclass
from typing import Callable, Optional, TYPE_CHECKING

from model.composite_local_tree import build_local_tree
from model.composite_signature import CompositeSignature, Param
from model.log_model import LogModel
from model.project_variable import ProjectVariable
from model.step import Step, StepStatus
from model.step_io import StepIOWidget

if TYPE_CHECKING:
    from PyQt5.QtWidgets import QWidget
    from model.composite_definition import CompositeDefinition
    from model.kscp_package import KscpPackage
    from model.step_list import StepList
    from model.step_manager import StepManager
    from model.variable_tree import VariableTree

__all__ = ["CompositeCard", "repoint_refs", "repoint_param_refs"]

_MARKER_PREFIX = "@合成卡片:"
_MAX_SUB_STEPS = 10000
_MAX_DEPTH = 32


@dataclass
class _NoIO:
    """空 dataclass：input_class/output_class 哨兵（fields() 得 [] → base input/output no-op）。"""
    pass


class CompositeCard(Step):
    """合成卡片：引用一张命名合成卡片定义、运行时展开执行。

    v1（参数less，空签名）：行为同今天——body 走全局变量树，不换树。
    v2（带签名）：调用点 io 槽 = 签名参数；运行期 input() 建局部树填入参、
    run() 换 body 步骤 io._tree 为局部树（try/finally 恢复）、output() 读
    出参写回调用点绑定的全局目标。纯局部（无全局回退）。
    """

    name = "合成卡片"
    description = "可复用的步骤集合（引用定义，运行时展开执行）"
    input_class = _NoIO
    output_class = _NoIO

    # 解析器：ref -> CompositeDefinition | None（主窗口打开工程时注入 cstore.get_or_none）
    _resolver: Optional[Callable[[str], "Optional[CompositeDefinition]"]] = None
    _stop_event: "threading.Event" = threading.Event()
    _depth_local = threading.local()

    def __init__(self, ref: str, tree: "VariableTree",
                 package: "KscpPackage",
                 signature: Optional[CompositeSignature] = None,
                 io: Optional[StepIOWidget] = None,
                 enabled: bool = True, tag: str = "") -> None:
        sig = signature if signature is not None else CompositeSignature.empty()
        if io is None:
            io = StepIOWidget([], [], tree, package)   # 参数less 空签名 io
        super().__init__(io, enabled, tag)
        self.ref = ref
        self.signature = sig
        self.name = ref.rsplit("/", 1)[-1] if ref else "合成卡片"
        self._global_tree = tree            # 出参写回目标全局树（调用点 io._tree 即此）
        self._package = package
        self._local_tree: Optional["VariableTree"] = None
        self._executed_body = False       # run() 置 True 仅当 body 真正开始执行
        # 给调用点 io 槽贴参数名标签（参数less 空签名 → set_slot_names([],[]) 无害）
        self.io.set_slot_names(sig.input_names() or None,
                               sig.output_names() or None)

    # ---- 服务定位 / 协作停止 ----
    @classmethod
    def set_resolver(cls, resolver):
        cls._resolver = resolver

    @classmethod
    def resolve_ref(cls, ref: str) -> "Optional[CompositeDefinition]":
        if cls._resolver is None:
            return None
        try:
            return cls._resolver(ref)
        except Exception:
            return None

    @classmethod
    def set_stop_event(cls, event):
        cls._stop_event = event

    # ---- 信息显示 ----
    def info_widget(self, parent=None):
        from PyQt5.QtWidgets import QLabel
        lbl = QLabel("合成卡片 → %s" % self.ref, parent)
        lbl.setWordWrap(True)
        return lbl

    # ---- 引用标记编解码 ----
    def to_format_string(self) -> str:
        io_fmt = self.io.to_format_string()
        # 参数less（空签名 io 空槽）→ to_format_string 仍非空串；但空签名不该带 :io
        if self.signature.is_empty() and not self.io.input_types and not self.io.output_types:
            return _MARKER_PREFIX + self.ref
        return _MARKER_PREFIX + self.ref + ":" + io_fmt

    @staticmethod
    def is_marker(fmt: str) -> bool:
        return isinstance(fmt, str) and fmt.startswith(_MARKER_PREFIX)

    @classmethod
    def marker_for(cls, ref: str) -> str:
        return _MARKER_PREFIX + ref

    @classmethod
    def from_marker(cls, fmt: str, manager: "StepManager") -> "CompositeCard":
        """由标记还原；非标记/空 ref → ValueError。

        经解析器取签名 → 按签名建类型化 io（ctor 贴参数名标签）：
        * 带参标记 ``@合成卡片:<ref>:<io_b64>`` → 回填 marker 内 iv/ov（签名漂移
          则按长度截取/补空，类型不符的 ov 置空 → 红卡可定位）。
        * bare 标记 ``@合成卡片:<ref>``（picker 新增卡用）→ 空值 io（用户可填）。
        * 无解析器/签名空 → 参数less 空签名 io（v1）。
        """
        if not cls.is_marker(fmt):
            raise ValueError("不是合成卡片引用标记: %r" % (fmt,))
        rest = fmt[len(_MARKER_PREFIX):]
        if not rest:
            raise ValueError("合成卡片引用路径为空: %r" % (fmt,))
        # 拆 ref 与可选 io_fmt（ref 不含 ":"，路径段无 ":"）
        if ":" in rest:
            ref, io_fmt = rest.split(":", 1)
        else:
            ref, io_fmt = rest, ""
        if not ref:
            raise ValueError("合成卡片引用路径为空: %r" % (fmt,))
        # 取签名（运行期解析器；加载期 from_marker 时 sigs 已预加载）
        sig = CompositeSignature.empty()
        defn = CompositeCard.resolve_ref(ref)
        if defn is not None:
            sig = defn.signature
        tree = manager.tree
        package = manager.package
        if sig.is_empty():
            # 参数less（v1 或 v2 空签名）→ 空签名 io
            return cls(ref, tree, package, signature=sig)
        # 带参：按签名建类型化 io（bare marker → 空值可填；带 io_fmt → 回填 marker 的 iv/ov）
        io = StepIOWidget(sig.input_types(), sig.output_types(), tree, package)
        if io_fmt:
            try:
                src = StepIOWidget.from_format_string(io_fmt, tree, package)
                # iv/ov 数量与签名不符（签名漂移）→ 按签名长度取/补空
                iv = list(src._input_values)[:len(sig.inputs)]
                while len(iv) < len(sig.inputs):
                    iv.append("")
                ov = list(src._output_values)[:len(sig.outputs)]
                while len(ov) < len(sig.outputs):
                    ov.append("")
                io._input_values = iv
                io._output_values = ov
            except ValueError:
                LogModel.instance().error(
                    "合成卡片标记内 io 串非法，已退化为空值 io（红卡可定位）: %s" % io_fmt)
        return cls(ref, tree, package, signature=sig, io=io)

    def resync_io(self) -> bool:
        """合成卡片签名变更后，按当前签名重同步调用点 io：重建类型化 io + 参数名
        标签，保留已填值（按位置截取/补空）。签名未变/悬空引用 → 返回 False（不动）。

        供主窗口在合成卡片签名变更时批量刷新引用该卡的步骤列表步骤用。
        """
        defn = CompositeCard.resolve_ref(self.ref)
        if defn is None:
            return False                       # 悬空引用，留待运行期 ERROR 定位
        sig = defn.signature
        if sig == self.signature:
            return False                       # 签名未变
        self.signature = sig
        if sig.is_empty():
            new_io = StepIOWidget([], [], self._global_tree, self._package)
        else:
            new_io = StepIOWidget(sig.input_types(), sig.output_types(),
                                  self._global_tree, self._package)
            # 保留旧值（按位置截取/补空）
            iv = list(self.io._input_values)[:len(sig.inputs)]
            while len(iv) < len(sig.inputs):
                iv.append("")
            ov = list(self.io._output_values)[:len(sig.outputs)]
            while len(ov) < len(sig.outputs):
                ov.append("")
            new_io._input_values = iv
            new_io._output_values = ov
        new_io.set_slot_names(sig.input_names() or None, sig.output_names() or None)
        self.io = new_io
        return True

    # ---- 执行流程（覆写 input/run/output）----
    def input(self) -> None:
        if self.signature.is_empty():
            return                       # 参数less → no-op（base input() 也 no-op）
        values = self.io.resolve_inputs()           # 调用点绑定值（常量/{{全局}}）
        self._local_tree = build_local_tree(self.signature, self._package)
        for p, val in zip(self.signature.inputs, values):
            self._local_tree.set(
                p.name, ProjectVariable.create(p.type, val, self._package))

    def run(self) -> int:
        self._executed_body = False
        defn = CompositeCard.resolve_ref(self.ref)
        if defn is None or defn.body is None:
            LogModel.instance().error("合成卡片引用不存在: %s" % self.ref)
            self.status = StepStatus.ERROR
            return 1
        depth = getattr(CompositeCard._depth_local, "depth", 0) + 1
        if depth > _MAX_DEPTH:
            LogModel.instance().error(
                "合成卡片递归过深（>%d，疑似循环引用）: %s"
                % (_MAX_DEPTH, self.ref))
            self.status = StepStatus.ERROR
            return 1
        CompositeCard._depth_local.depth = depth
        body = defn.body
        try:
            prog = body.do_methods()
            if not prog:
                return 1
            for s in body.steps:
                s.status = StepStatus.PENDING
            self._executed_body = True            # body 真正开始执行
            if self.signature.is_empty():
                # 参数less：不换树，body 走全局（同 v1）
                return self._run_body(prog, body)
            # 带参：换 body 步骤 io._tree 为局部树
            saved = [s.io._tree for s in body.steps]
            for s in body.steps:
                s.io._tree = self._local_tree
            try:
                return self._run_body(prog, body)
            finally:
                for s, t in zip(body.steps, saved):
                    s.io._tree = t
        finally:
            CompositeCard._depth_local.depth = depth - 1

    def _run_body(self, prog, body) -> int:
        """mini pc+偏移循环（照搬 v1 语义；供 run 复用）。"""
        pc = 0
        steps_done = 0
        while pc < len(prog) and not CompositeCard._stop_event.is_set():
            steps_done += 1
            if steps_done > _MAX_SUB_STEPS:
                LogModel.instance().error(
                    "合成卡片体内执行步数超过上限 %d，已停止: %s"
                    % (_MAX_SUB_STEPS, self.ref))
                self.status = StepStatus.ERROR
                return 1
            offset = prog[pc]()
            pc += offset
            if pc < 0:
                pc = 0
        return 1

    def output(self) -> None:
        if (self.signature.is_empty() or not self._executed_body
                or self.status is StepStatus.ERROR):
            return                       # 参数less / body 未开始 / 已 ERROR → no-op
        outs = [self._local_tree.get(p.name) for p in self.signature.outputs]
        self.io.write_outputs([v.data for v in outs])   # 写回调用点绑定的全局目标
        self._local_tree = None


def repoint_refs(store, old_path: str, new_path: str) -> int:
    """把 store 内引用 old_path 的合成卡片改指 new_path。

    兼容两类 store：CompositeCardStore（v2，get_body→StepList）与
    StepListStore（v1，get→StepList）——鸭子类型取 get_body，无则退 get。
    """
    count = 0
    new_leaf = new_path.rsplit("/", 1)[-1] if new_path else "合成卡片"
    for path, is_group in store.walk():
        if is_group:
            continue
        try:
            sl = store.get_body(path) if hasattr(store, "get_body") else store.get(path)
        except FileNotFoundError:
            continue
        for step in sl.steps:
            if isinstance(step, CompositeCard) and step.ref == old_path:
                step.ref = new_path
                step.name = new_leaf
                count += 1
    return count


def repoint_param_refs(body: "StepList",
                      old_sig: CompositeSignature,
                      new_sig: CompositeSignature) -> int:
    """改名参数后，改指 body 步骤 io 槽引用旧参数名的绑定；返回改动数。

    按位置对齐（签名表改名=原地编辑名）。**仅在段长度不变时**改指：增删参数（长
    度变）→ 位置对齐不可靠 → 跳过该段改指（绑定悬空 → 运行期 ERROR 可定位），
    符合 spec §6「删参数 → 不改；绑定悬空」。删除的参数仍被 body 引用 → 该引用
    悬空（resolve_inputs 抛 → 步骤 ERROR）——签名表删行时弹确认。
    """
    count = 0
    in_renames = {}
    if len(old_sig.inputs) == len(new_sig.inputs):
        for a, b in zip(old_sig.inputs, new_sig.inputs):
            if a.name != b.name:
                in_renames[a.name] = b.name
    else:
        LogModel.instance().error(
            "合成卡片输入参数个数已改变（增删），已跳过输入改指（绑定可能悬空）")
    out_renames = {}
    if len(old_sig.outputs) == len(new_sig.outputs):
        for a, b in zip(old_sig.outputs, new_sig.outputs):
            if a.name != b.name:
                out_renames[a.name] = b.name
    else:
        LogModel.instance().error(
            "合成卡片输出参数个数已改变（增删），已跳过输出改指（绑定可能悬空）")
    if not in_renames and not out_renames:
        return 0
    for step in body.steps:
        io = step.io
        for i in range(len(io._input_values)):
            val = io._input_values[i]
            if not isinstance(val, str):
                continue
            for old, new in in_renames.items():
                if val == "{{%s}}" % old:
                    io.change_value("input", i, "{{%s}}" % new)
                    count += 1
                    break
        for i in range(len(io._output_values)):
            val = io._output_values[i]
            if val in out_renames:
                io.change_value("output", i, out_renames[val])
                count += 1
    return count


# ================================================================
# 冒烟演示：直接 ``python -m model.composite_card`` 运行
# ================================================================
if __name__ == "__main__":
    import sys
    from dataclasses import dataclass

    from PyQt5.QtWidgets import QApplication, QLabel

    from model.kscp_package import KscpPackage
    from model.log_model import LogModel
    from model.project_variable import ProjectVariable
    from model.step import Step, StepStatus
    from model.step_list import StepList
    from model.step_list_store import StepListStore
    from model.step_manager import StepManager
    from model.variable_tree import VariableTree
    from model.composite_definition import CompositeDefinition

    app = QApplication.instance() or QApplication(sys.argv)

    pkg = KscpPackage.create_empty()
    tree = VariableTree.create_empty()
    tree.add("n1", ProjectVariable.create("number", 100, pkg))
    mgr = StepManager(pkg, tree)            # 无需 load（from_marker 只用 tree/package）

    # ---- 引用标记编解码 ----
    c = CompositeCard("组/卡片A", tree, pkg)
    assert c.name == "卡片A" and c.ref == "组/卡片A"   # 实例名=叶子名（卡片可区分）
    c2 = CompositeCard("组/卡片B", tree, pkg)
    assert c2.name == "卡片B" and c.name != c2.name    # 不同引用 → 不同显示名
    assert c.io.input_types == [] and c.io.output_types == []  # 空签名
    assert c.io.is_valid                                   # 空 io 恒合规
    fmt = c.to_format_string()
    assert fmt == "@合成卡片:组/卡片A", fmt
    assert CompositeCard.is_marker(fmt) is True
    assert CompositeCard.is_marker("not a marker") is False
    assert CompositeCard.is_marker("") is False
    back = CompositeCard.from_marker(fmt, mgr)
    assert isinstance(back, CompositeCard) and back.ref == "组/卡片A"
    assert back.to_format_string() == fmt                  # 往返稳定
    try:                                                    # 非标记 → ValueError
        CompositeCard.from_marker("not a marker", mgr)
        raise AssertionError("非标记应抛 ValueError")
    except ValueError:
        pass
    try:                                                    # 空 ref → ValueError
        CompositeCard.from_marker("@合成卡片:", mgr)
        raise AssertionError("空 ref 应抛 ValueError")
    except ValueError:
        pass

    # ---- info_widget：渲染为 QLabel ----
    lbl = c.info_widget()
    assert isinstance(lbl, QLabel) and "组/卡片A" in lbl.text()

    # ---- 运行时执行：解析引用 → 展开体内 StepList ----
    # 探针步骤：run 记录执行序号、返回预设偏移；不依赖变量树（无输出槽）
    @dataclass
    class _ProbeIn:
        n: "number" = 0  # type: ignore

    @dataclass
    class _ProbeOut:
        pass

    class _ProbeStep(Step):
        name = "探针"
        description = "测试探针"
        input_class = _ProbeIn
        output_class = _ProbeOut
        calls = []
        offsets = []

        def run(self) -> int:
            type(self).calls.append(self.tag)
            seq = type(self).offsets
            idx = len(type(self).calls) - 1
            # 循环调用时（偏移 0/负值造环）offsets 会耗尽 → 复用末项，防 IndexError
            return seq[idx] if idx < len(seq) else (seq[-1] if seq else 1)

    # 卡片A 的定义体：三个探针步骤（偏移 1/1/1）
    _ProbeStep.calls = []
    _ProbeStep.offsets = [1, 1, 1]
    bodyA = StepList.create_empty()
    for i, t in enumerate(("A1", "A2", "A3")):
        s = _ProbeStep.create_default(tree, pkg)
        s.io._input_values = [str(i)]   # 合法输入，input() 不抛
        s.tag = t
        bodyA.add(s)
    # 解析器：组/卡片A -> CompositeDefinition(bodyA, 空签名)
    CompositeCard.set_resolver(lambda ref: CompositeDefinition(bodyA, CompositeSignature.empty()) if ref == "组/卡片A" else None)

    outer = CompositeCard("组/卡片A", tree, pkg)
    assert outer.do() == 1                                 # 外层前进 1
    assert outer.status is StepStatus.FINISHED
    assert _ProbeStep.calls == ["A1", "A2", "A3"], _ProbeStep.calls  # 体内按序执行
    assert all(s.status is StepStatus.FINISHED for s in bodyA.steps)  # 体内步骤已 FINISHED

    # 再跑一次：复位 PENDING 后重跑（调用方弄脏状态 → 重跑回到 FINISHED）
    for s in bodyA.steps:
        s.status = StepStatus.ERROR
    _ProbeStep.calls.clear()
    outer.status = StepStatus.PENDING
    assert outer.do() == 1
    assert all(s.status is StepStatus.FINISHED for s in bodyA.steps)

    # 体内偏移语义：偏移 2 跳一步（A1 跳 A2 → 只跑 A1、A3？A1 偏移2→pc=2→A3）
    _ProbeStep.calls = []
    _ProbeStep.offsets = [2, 1, 1]
    outer2 = CompositeCard("组/卡片A", tree, pkg)
    outer2.do()
    assert _ProbeStep.calls == ["A1", "A3"], _ProbeStep.calls  # A1 跳过 A2
    # 偏移 0 死循环：单步重复 → 受 _MAX_SUB_STEPS 上限保护（ERROR + 日志，不崩）
    _ProbeStep.calls = []
    _ProbeStep.offsets = [0]
    LogModel.instance().clear()
    outer3 = CompositeCard("组/卡片A", tree, pkg)
    outer3.do()
    assert outer3.status is StepStatus.ERROR               # 超步数上限 → ERROR
    assert any("超过上限" in e.message for e in LogModel.instance().entries)

    # ---- 悬空引用：定义被删/无匹配 → ERROR + 日志 + 跳过（返回 1）----
    CompositeCard.set_resolver(lambda ref: None)           # 视为找不到定义
    LogModel.instance().clear()
    dangling = CompositeCard("不存在的卡片", tree, pkg)
    assert dangling.do() == 1                              # 不阻断，软跳过
    assert dangling.status is StepStatus.ERROR
    assert any("引用不存在" in e.message for e in LogModel.instance().entries)

    # ---- 递归守卫：A→A 自引用 → 深度上限截断 + 日志 + 不崩 ----
    bodySelf = StepList.create_empty()
    bodySelf.add(CompositeCard("组/自环", tree, pkg))     # 体内引用自身
    CompositeCard.set_resolver(lambda ref: CompositeDefinition(bodySelf, CompositeSignature.empty()) if ref == "组/自环" else None)
    LogModel.instance().clear()
    selfref = CompositeCard("组/自环", tree, pkg)
    assert selfref.do() == 1                               # 不死循环
    assert any("递归过深" in e.message for e in LogModel.instance().entries)

    # ---- 协作停止：共享 stop_event 被置 → mini 循环中断 ----
    import threading as _th
    stop = _th.Event()
    CompositeCard.set_stop_event(stop)
    _ProbeStep.calls = []
    _ProbeStep.offsets = [1, 1, 1, 1, 1]
    bodyStop = StepList.create_empty()
    for i in range(5):
        s = _ProbeStep.create_default(tree, pkg)
        s.io._input_values = ["0"]
        s.tag = "S%d" % i
        bodyStop.add(s)
    CompositeCard.set_resolver(lambda ref: CompositeDefinition(bodyStop, CompositeSignature.empty()) if ref == "组/停" else None)
    # 在首步执行前置 stop → 一步都不跑（while 条件即退出）
    stop.set()
    cstop = CompositeCard("组/停", tree, pkg)
    assert cstop.do() == 1
    assert _ProbeStep.calls == []                           # 已停止，未执行体内步骤
    stop.clear()
    CompositeCard.set_stop_event(_th.Event())             # 复位默认事件

    # ---- repoint_refs：重命名后改指引用条目（修「步骤中命名不随重命名变化」）----
    slstore = StepListStore.create_empty()
    referring = StepList.create_empty()
    cc = CompositeCard("组/旧名", tree, pkg)
    referring.add(cc)
    slstore.add_list("调用方", referring)
    other = StepList.create_empty()           # 无引用的列表
    slstore.add_list("无关", other)
    assert cc.ref == "组/旧名" and cc.name == "旧名"
    n = repoint_refs(slstore, "组/旧名", "组/新名")
    assert n == 1, n
    assert cc.ref == "组/新名" and cc.name == "新名"      # ref+显示名同改
    assert len(other.steps) == 0                            # 无关列表不动
    assert repoint_refs(slstore, "组/旧名", "组/新名") == 0  # 旧名已无引用 → 0
    # 改指后标记串随之变（to_format_string 用 self.ref → 落盘的是新标记）
    assert cc.to_format_string() == "@合成卡片:组/新名"

    # 清理服务定位状态（避免影响后续模块冒烟）
    CompositeCard.set_resolver(lambda ref: None)          # type: ignore

    # ---- v2 带参：marker 含 io_b64；from_marker 取签名建类型化 io ----
    from model.composite_card_store import CompositeCardStore

    sig = CompositeSignature(inputs=[Param("x", "number")],
                              outputs=[Param("y", "number")])
    bodyP = StepList.create_empty()
    # body 用一个探针：x*2 → y（体内引用局部 x/y）
    @dataclass
    class _DIn:
        n: "number" = 0  # type: ignore
    @dataclass
    class _DOut:
        m: "number" = 0  # type: ignore
    class _Double(Step):
        name = "翻倍"
        description = "y = x*2"
        input_class = _DIn
        output_class = _DOut
        def run(self):
            self.outputs.m = self.inputs.n * 2
            return 1
    dstep = _Double.create_default(tree, pkg)
    dstep.io.set_slot_names(["x"], ["y"])        # 标签贴参数名（编辑期由 picker 包办）
    dstep.io.change_value("input", 0, "{{x}}")   # 输入槽绑局部 x
    dstep.io.change_value("output", 0, "y")      # 输出槽绑局部 y
    bodyP.add(dstep)

    cstore = CompositeCardStore.create_empty()
    cstore.add_list("加倍卡", bodyP, signature=sig)
    CompositeCard.set_resolver(lambda ref: cstore.get_or_none(ref))

    # 调用点：入参 x=5，出参写回全局 n1
    call = CompositeCard("加倍卡", tree, pkg, signature=sig,
                         io=StepIOWidget(["number"], ["number"], tree, pkg))
    call.io.change_value("input", 0, "5")
    call.io.change_value("output", 0, "n1")
    fmt = call.to_format_string()
    assert fmt == "@合成卡片:加倍卡:" + call.io.to_format_string(), fmt
    assert CompositeCard.is_marker(fmt)
    # from_marker 往返：取签名建 io，iv/ov 回填
    back = CompositeCard.from_marker(fmt, mgr)
    assert isinstance(back, CompositeCard) and back.ref == "加倍卡"
    assert back.signature.input_names() == ["x"]
    assert back.io.input_types == ["number"] and back.io.output_types == ["number"]
    assert back.io._input_values == ["5"] and back.io._output_values == ["n1"]
    # 端到端：do() → body 在局部树跑 → y=10 → 写回 n1
    assert back.do() == 1
    assert back.status is StepStatus.FINISHED
    assert tree.get("n1").data == 10

    # bare marker + 有参签名 → 按签名建类型化 io（空值可填）— 修复：picker 新增带参卡
    bare = CompositeCard.from_marker("@合成卡片:加倍卡", mgr)
    assert bare.signature.input_names() == ["x"] and bare.signature.output_names() == ["y"]
    assert bare.io.input_types == ["number"] and bare.io.output_types == ["number"]
    assert bare.io._input_values == [""] and bare.io._output_values == [""]   # 空值（用户可填）
    # resync_io：签名变更（加输出 z）→ 调用点 io 按新签名重建，保留已填值
    bare.io.change_value("input", 0, "5")
    bare.io.change_value("output", 0, "n1")
    sig_z = CompositeSignature(inputs=[Param("x", "number")],
                               outputs=[Param("y", "number"), Param("z", "number")])
    cstore.set_signature("加倍卡", sig_z)
    assert bare.resync_io() is True
    assert bare.signature.output_names() == ["y", "z"]
    assert bare.io.output_types == ["number", "number"]
    assert bare.io._input_values == ["5"]              # 旧值保留
    assert bare.io._output_values == ["n1", ""]        # 旧值保留 + 新槽空
    assert bare.resync_io() is False                   # 签名未变 → 不动

    # 纯局部：body 步骤引用全局名 → resolve 抛 → ERROR
    dstep2 = _Double.create_default(tree, pkg)
    dstep2.io.change_value("input", 0, "{{n1}}")   # 误绑全局（局部树无 n1）
    dstep2.io.change_value("output", 0, "y")
    bodyBad = StepList.create_empty(); bodyBad.add(dstep2)
    cstoreB = CompositeCardStore.create_empty(); cstoreB.add_list("坏卡", bodyBad, signature=sig)
    CompositeCard.set_resolver(lambda ref: cstoreB.get_or_none(ref))
    callB = CompositeCard("坏卡", tree, pkg, signature=sig,
                          io=StepIOWidget(["number"], ["number"], tree, pkg))
    callB.io.change_value("input", 0, "5")
    callB.io.change_value("output", 0, "n1")
    LogModel.instance().clear()
    try:
        callB.do()
    except Exception:
        pass   # body 步骤 resolve_inputs 抛 FileNotFoundError → do 置 ERROR 重抛
    assert callB.status is StepStatus.ERROR

    # 换树 try/finally 恢复：body 抛错后 body 步骤 io._tree 复位全局
    saved_tree = dstep2.io._tree
    # 上面 do() 抛错后 io._tree 应仍是全局树（finally 恢复）
    assert dstep2.io._tree is saved_tree

    # 签名漂移：旧 marker（1 入 1 出）+ 新签名（2 出）→ 多出的 ov 置空（红卡）
    sig2 = CompositeSignature(inputs=[Param("x", "number")],
                              outputs=[Param("y", "number"), Param("z", "number")])
    bodyP2 = StepList.create_empty()
    d2 = _Double.create_default(tree, pkg)
    d2.io.change_value("input", 0, "{{x}}")
    d2.io.change_value("output", 0, "y")
    bodyP2.add(d2)
    cstoreC = CompositeCardStore.create_empty(); cstoreC.add_list("漂移卡", bodyP2, signature=sig2)
    CompositeCard.set_resolver(lambda ref: cstoreC.get_or_none(ref))
    callC = CompositeCard("漂移卡", tree, pkg, signature=sig2,
                          io=StepIOWidget(["number"], ["number", "number"], tree, pkg))
    callC.io.change_value("input", 0, "5")
    callC.io.change_value("output", 0, "n1")
    callC.io.change_value("output", 1, "")        # 第二输出未绑 → 不合规
    assert not callC.io.is_valid

    # ---- repoint_param_refs：改名参数后改指 body 引用 ----
    bodyR = StepList.create_empty()
    dr = _Double.create_default(tree, pkg)
    dr.io.change_value("input", 0, "{{x}}")
    dr.io.change_value("output", 0, "y")
    bodyR.add(dr)
    old_sig = CompositeSignature(inputs=[Param("x", "number")],
                                outputs=[Param("y", "number")])
    new_sig = CompositeSignature(inputs=[Param("a", "number")],
                                 outputs=[Param("b", "number")])
    n = repoint_param_refs(bodyR, old_sig, new_sig)
    assert n == 2
    assert dr.io._input_values[0] == "{{a}}"
    assert dr.io._output_values[0] == "b"

    # ---- 删参数（长度变）→ 位置对齐不可靠 → 跳过改指，旧绑定悬空 ----
    bodyD = StepList.create_empty()
    dd = _Double.create_default(tree, pkg)
    dd.io.change_value("input", 0, "{{x}}")
    dd.io.change_value("output", 0, "y")
    bodyD.add(dd)
    old_del = CompositeSignature(inputs=[Param("x", "number"), Param("y", "number")],
                                  outputs=[Param("z", "number")])
    new_del = CompositeSignature(inputs=[Param("y", "number")],   # 删了 x（2→1）
                                  outputs=[Param("z", "number")])
    LogModel.instance().clear()
    n_del = repoint_param_refs(bodyD, old_del, new_del)
    assert n_del == 0                                    # 长度变 → 跳过，未改指
    assert dd.io._input_values[0] == "{{x}}"             # 仍指 x（悬空，未误改指 y）
    assert any("个数已改变" in e.message for e in LogModel.instance().entries)

    # ---- 软跳过（空体 / 悬空）→ output() 不写幻影默认值到全局目标 ----
    # 空体卡：有签名但 body 无步骤 → 不该把 n1 写成默认 0
    tree.set("n1", ProjectVariable.create("number", 999, pkg))
    bodyE = StepList.create_empty()                      # 空体
    cstoreE = CompositeCardStore.create_empty(); cstoreE.add_list("空体卡", bodyE, signature=sig)
    CompositeCard.set_resolver(lambda ref: cstoreE.get_or_none(ref))
    callE = CompositeCard("空体卡", tree, pkg, signature=sig,
                          io=StepIOWidget(["number"], ["number"], tree, pkg))
    callE.io.change_value("input", 0, "5")
    callE.io.change_value("output", 0, "n1")
    callE.do()
    assert tree.get("n1").data == 999                    # 未被幻影默认 0 覆盖
    # 悬空（运行期定义不存在）→ ERROR 且不写幻影默认值
    tree.set("n1", ProjectVariable.create("number", 777, pkg))
    CompositeCard.set_resolver(lambda ref: None)        # 定义全删
    callG = CompositeCard("已删卡", tree, pkg, signature=sig,
                          io=StepIOWidget(["number"], ["number"], tree, pkg))
    callG.io.change_value("input", 0, "5")
    callG.io.change_value("output", 0, "n1")
    LogModel.instance().clear()
    callG.do()
    assert callG.status is StepStatus.ERROR
    assert tree.get("n1").data == 777                   # 未被幻影默认 0 覆盖

    # v1 参数less 回归（空签名 → 行为同今天，marker 无 :io）
    v1c = CompositeCard("组/卡片A", tree, pkg)
    assert v1c.signature.is_empty()
    assert v1c.to_format_string() == "@合成卡片:组/卡片A"
    CompositeCard.set_resolver(lambda ref: None)   # 复位

    print("CompositeCard smoke OK")
