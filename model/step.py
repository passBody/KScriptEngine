# -*- coding: utf-8 -*-
"""
步骤基类（数据结构 + 执行流程）
==============================

:class:`Step` 是所有「步骤」的基类：步骤是用来执行的，后续会创建步骤列表，
点击执行后每个步骤按顺序执行。子类在 ``actions/`` 下按目录分组
（如 ``actions/控制流程/time_delay.py``）。

本模块属 model 层：**模块顶层不导入 PyQt5**，Qt 控件仅在
:meth:`info_widget` 内延迟导入，因此导入本模块不依赖 GUI 环境。

基类职责
--------
* 持有「步骤输入/输出设置（数据 + GUI 生成器）」（:class:`StepIOWidget`）。
* 提供 :meth:`do` 整合执行流程：input → run → output → 返回偏移量。
* 提供 :meth:`to_format_string` / :meth:`from_format_string` 编码还原自身。

子类需覆盖
----------
* ``name`` / ``description``：步骤名称与描述。
* ``input_class`` / ``output_class``：dataclass，字段类型注解为**已注册的
  变量类型名**（如 ``"number"``；未注册的类型名在 :meth:`create_default`
  时抛 :class:`ValueError`），字段需带默认值（实例化空容器用）。
* :meth:`run`：执行逻辑，返回步骤偏移量（默认 1 = 运行下一个步骤、
  2 = 运行之后第二个、0 = 重新调用自身）。

基本用法
--------
::

    step = TimeDelay.create_default(tree, pkg)   # 由字段签名自动构建空 io
    step.io.change_value("input", 0, "5")        # 配置输入槽
    offset = step.do()                           # 执行：input→run→output
"""
import base64
import json
from dataclasses import fields
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple, TYPE_CHECKING

from model.log_model import LogModel
from model.project_variable import ProjectVariable
from model.step_io import StepIOWidget

if TYPE_CHECKING:
    from PyQt5.QtWidgets import QLabel, QWidget

    from model.kscp_package import KscpPackage
    from model.variable_tree import VariableTree

__all__ = ["Step", "StepStatus"]


class StepStatus(Enum):
    """步骤状态：未执行 | 执行中 | 执行结束 | 执行错误。"""
    PENDING = "未执行"
    RUNNING = "执行中"
    FINISHED = "执行结束"
    ERROR = "执行错误"


class Step:
    """步骤基类：子类覆盖 name / description / input_class / output_class / run。"""

    name: str = ""                 # 该步骤的名称
    description: str = ""          # 描述该步骤的作用
    input_class: type = object     # 输入类：dataclass，字段类型注解为变量类型名
    output_class: type = object    # 输出类：dataclass，同上

    def __init__(self, io: StepIOWidget, enabled: bool = True,
                 tag: str = "") -> None:
        self.io = io                     # 步骤输入/输出设置（数据 + GUI 生成器）
        # 槽标签显示参数名（dataclass 字段名，如 x/y）而非类型名
        self.io.set_slot_names(
            [f.name for f in fields(self.input_class)] if self.input_class is not object else None,
            [f.name for f in fields(self.output_class)] if self.output_class is not object else None)
        self.enabled = enabled           # 是否运行（勾选运行；默认运行）
        self.tag = tag                   # 标签/签名（用户标记；卡片上方可编辑）
        self._status = StepStatus.PENDING    # 经 status 属性读写（变更即通知监听者）
        self._status_listeners: List[Callable[["Step", StepStatus], None]] = []
        self.inputs = self.input_class()     # 输入类实例（运行时值容器）
        self.outputs = self.output_class()   # 输出类实例（运行时值容器）

    # ================================================================
    # 状态（property：每次变更通知监听者，供执行器推 UI 刷新）
    # ================================================================
    @property
    def status(self) -> StepStatus:
        """步骤状态：未执行 | 执行中 | 执行结束 | 执行错误。"""
        return self._status

    @status.setter
    def status(self, value: StepStatus) -> None:
        """置状态；与当前相同则不通知（重复赋值静默）。"""
        if value is self._status:
            return
        self._status = value
        for cb in list(self._status_listeners):  # 拷贝遍历：回调可增删监听者
            try:
                cb(self, value)
            except Exception:
                pass  # 监听者异常不打断状态流转（与 LogModel 通知策略一致）

    def add_status_listener(self,
                            cb: Callable[["Step", StepStatus], None]) -> None:
        """注册状态变更监听：``cb(step, new_status)``，每次状态变更调用一次。

        纯 Python 回调，model 层不依赖 Qt（执行器/UI 自行经信号桥接刷新）。
        """
        self._status_listeners.append(cb)

    def remove_status_listener(self,
                               cb: Callable[["Step", StepStatus], None]) -> None:
        """移除已注册的监听者；未注册则静默忽略。"""
        try:
            self._status_listeners.remove(cb)
        except ValueError:
            pass

    # ================================================================
    # 槽类型推导 / 签名
    # ================================================================
    @staticmethod
    def _safe_fields(klass: type) -> List[Any]:
        """dataclass 字段列表；``object``（无输入/输出哨兵）→ 空列表。

        非 dataclass → ValueError（原 ``fields()`` 抛 TypeError，与文档承诺
        不符——评审#19；基类 ``input_class=object`` 属合法空签名）。
        """
        if klass is object:
            return []
        try:
            return list(fields(klass))
        except TypeError:
            raise ValueError("输入/输出类 %r 不是 dataclass" % (klass,))

    @classmethod
    def _io_type_lists(cls) -> Tuple[List[str], List[str]]:
        """由输入/输出 dataclass 字段的类型注解推导 io 槽类型列表（顺序一致）。

        注解必须是已注册的变量类型名（见 :meth:`ProjectVariable.type_of`）；
        未注册 → 抛 :class:`ValueError`（带步骤名/字段名/支持列表，便于定位）。
        """
        def _types_of(klass: type, role: str) -> List[str]:
            types = []
            for f in cls._safe_fields(klass):
                if ProjectVariable.type_of(f.type) is None:
                    raise ValueError(
                        "步骤 %s 的%s类字段 %r 的类型注解未注册: %r（支持: %s）"
                        % (cls.name, role, f.name, f.type,
                           ProjectVariable.supported_types()))
                types.append(f.type)
            return types
        return (_types_of(cls.input_class, "输入"),
                _types_of(cls.output_class, "输出"))

    @classmethod
    def _signature(cls, klass: type) -> List[List[str]]:
        """dataclass 签名：[(字段名, 类型注解), ...]。"""
        return [[f.name, f.type] for f in cls._safe_fields(klass)]

    # ================================================================
    # 工厂
    # ================================================================
    @classmethod
    def create_default(cls, tree: "VariableTree",
                       package: "KscpPackage") -> "Step":
        """由字段签名自动构建含空 io 的默认实例（供「步骤管理」添加新步骤用）。"""
        in_types, out_types = cls._io_type_lists()
        return cls(StepIOWidget(in_types, out_types, tree, package))

    # ================================================================
    # 信息显示窗口（GUI 生成器）
    # ================================================================
    def info_widget(self, parent: Optional["QWidget"] = None) -> "QWidget":
        """信息显示窗口：可在步骤列表视图的卡片里生成自定义窗口；默认显示描述。"""
        from PyQt5.QtWidgets import QLabel

        lbl = QLabel(self.description, parent)
        lbl.setWordWrap(True)
        return lbl

    # ================================================================
    # 执行流程
    # ================================================================
    def input(self) -> None:
        """① 调用 io 获取输入实际值，按字段序写入输入类实例。"""
        values = self.io.resolve_inputs()
        for f, v in zip(fields(self.input_class), values):
            setattr(self.inputs, f.name, v)

    def run(self) -> int:
        """② 用来执行并修改（可读写 inputs / outputs）；返回步骤偏移量。

        执行器以「程序计数器 + 偏移量」逐条推进（类似汇编逐条执行）：
        默认 1：运行下一个步骤；返回 2：跳过下一个；返回 0：重新调用自身；
        **负值：回跳**（如 ``-1`` 回到上一步，实现循环/重试）。
        """
        return 1

    def output(self) -> None:
        """③ 按字段序收集输出类实例的值，经 io 写回变量树（影响全局数据）。"""
        outs = [getattr(self.outputs, f.name) for f in fields(self.output_class)]
        self.io.write_outputs(outs)

    def do(self) -> int:
        """整合整个流程，返回值是 run 的返回值。

        ① input → ② offset = run → ③ output → ④ return offset。
        任何异常：状态置「执行错误」+ 日志记录 + 重抛；run 手动置
        「执行错误」则不覆盖为「执行结束」。

        偏移量必须是 int（bool 是 int 子类，显式排除），否则按执行错误
        处理——执行器依赖偏移量做跳转，非法值难定位。**负值合法**：
        执行器 = 程序计数器 + 偏移，负值即回跳（如汇编跳转指令）。
        """
        self.status = StepStatus.RUNNING
        try:
            self.input()
            offset = self.run()
            if not isinstance(offset, int) or isinstance(offset, bool):
                raise ValueError(
                    "%s 的 run() 返回了非法偏移量（需 int）: %r"
                    % (self.name, offset))
            self.output()
        except Exception as e:
            self.status = StepStatus.ERROR
            LogModel.instance().error("%s 执行错误: %s" % (self.name, e))
            raise
        if self.status is not StepStatus.ERROR:
            self.status = StepStatus.FINISHED
        return offset

    # ================================================================
    # 格式化字符串
    # ================================================================
    def to_format_string(self) -> str:
        """生成格式化数据：base64 编码【名称，输入/输出类签名，io 格式串，是否运行，标签】。"""
        raw = json.dumps({
            "name": self.name,
            "in": self._signature(self.input_class),
            "out": self._signature(self.output_class),
            "io": self.io.to_format_string(),
            "run": self.enabled,
            "tag": self.tag,
        }, ensure_ascii=False)
        return base64.urlsafe_b64encode(
            raw.encode("utf-8")).decode("ascii").rstrip("=")

    @classmethod
    def from_format_string(cls, fmt: str, tree: "VariableTree",
                           package: "KscpPackage") -> Optional["Step"]:
        """静态方法：通过 base64 码判断能否返回自身。

        名称不对、输入/输出类签名不匹配、io 槽类型与签名推导不符 → 返回
        ``None``；非法编码 / 结构缺字段 → 抛 :class:`ValueError`。
        """
        obj = cls._decode(fmt)
        if obj["name"] != cls.name:
            return None
        if obj["in"] != cls._signature(cls.input_class):
            return None
        if obj["out"] != cls._signature(cls.output_class):
            return None
        io = StepIOWidget.from_format_string(obj["io"], tree, package)
        if io.input_types != cls._io_type_lists()[0] \
                or io.output_types != cls._io_type_lists()[1]:
            return None
        return cls(io, enabled=obj.get("run", True),    # 旧格式串无 run 键 → 默认运行
                   tag=obj.get("tag", ""))              # 旧格式串无 tag 键 → 默认空

    @staticmethod
    def _decode(fmt: str) -> Dict[str, Any]:
        """反解格式化字符串为 ``{"name","in","out","io","run"(可选)}``。"""
        if not isinstance(fmt, str) or not fmt:
            raise ValueError("无效的步骤格式化字符串: %r" % (fmt,))
        pad = "=" * (-len(fmt) % 4)
        try:
            raw = base64.urlsafe_b64decode((fmt + pad).encode("ascii"))
            obj = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as e:
            raise ValueError("无效的步骤格式化字符串: %r（%s）" % (fmt, e))
        if not isinstance(obj, dict) or not {"name", "in", "out", "io"} <= set(obj):
            raise ValueError("无效的步骤格式化字符串: %r" % (fmt,))
        if not isinstance(obj["name"], str) \
                or not isinstance(obj["in"], list) \
                or not isinstance(obj["out"], list) \
                or not isinstance(obj["io"], str):
            raise ValueError("无效的步骤格式化字符串: %r" % (fmt,))
        if "run" in obj and not isinstance(obj["run"], bool):
            raise ValueError("无效的步骤格式化字符串: %r（run 键必须为 bool）" % (fmt,))
        if "tag" in obj and not isinstance(obj["tag"], str):
            raise ValueError("无效的步骤格式化字符串: %r（tag 键必须为 str）" % (fmt,))
        return obj

# ================================================================
# 冒烟演示：直接 ``python -m model.step`` 运行
# ================================================================
if __name__ == "__main__":
    import base64 as _b64
    import json as _json
    import sys

    from PyQt5.QtWidgets import QApplication, QLabel

    from model.kscp_package import KscpPackage
    from model.log_model import LogModel
    from model.project_variable import ProjectVariable
    from model.step_io import StepIOWidget
    from model.variable_tree import VariableTree

    app = QApplication.instance() or QApplication(sys.argv)

    # 工程资源 + 变量树
    pkg = KscpPackage.create_empty()
    tree = VariableTree.create_empty()
    tree.add("n1", ProjectVariable.create("number", 100, pkg))
    tree.add("s1", ProjectVariable.create("string", "hello", pkg))

    # 桩子类：输入 number+string，输出 number
    from dataclasses import dataclass

    @dataclass
    class _StubInput:
        a: "number" = 0  # type: ignore
        b: "string" = ""  # type: ignore

    @dataclass
    class _StubOutput:
        total: "number" = 0  # type: ignore

    class _StubStep(Step):
        name = "桩步骤"
        description = "测试用桩步骤"
        input_class = _StubInput
        output_class = _StubOutput

        def run(self) -> int:
            self.outputs.total = self.inputs.a * 2
            return 1

    # create_default：槽类型由字段签名推导；info_widget 默认 QLabel(描述)
    s = _StubStep.create_default(tree, pkg)
    assert s.io.input_types == ["number", "string"]
    assert s.io.output_types == ["number"]
    assert s.status is StepStatus.PENDING
    assert s.inputs.a == 0 and s.inputs.b == "" and s.outputs.total == 0
    card = s.info_widget()
    assert isinstance(card, QLabel)
    assert card.text() == "测试用桩步骤"

    # 评审#19：基类 Step（input_class=object 哨兵）create_default 不抛 TypeError——
    # object 视为空签名；非 dataclass 输入类 → ValueError（与文档承诺一致）
    s_base = Step.create_default(tree, pkg)
    assert s_base.io.input_types == [] and s_base.io.output_types == []

    class _NotDataclass:
        pass

    _BadStep = type("_BadStep", (Step,), {
        "name": "坏步骤", "description": "",
        "input_class": _NotDataclass, "output_class": object})
    try:
        _BadStep.create_default(tree, pkg)
        raise AssertionError("非 dataclass 输入类应抛 ValueError")
    except ValueError:
        pass

    # do() 全流程：输入解析 → run → 输出写回变量树
    s.io.change_value("input", 0, "5")          # number 常量
    s.io.change_value("input", 1, "{{s1}}")     # string 引用
    s.io.change_value("output", 0, "n1")        # 输出到 n1
    assert s.do() == 1
    assert s.status is StepStatus.FINISHED
    assert s.inputs.a == 5 and s.inputs.b == "hello"
    assert s.outputs.total == 10
    assert tree.get("n1").data == 10            # 写回变量树

    # 异常：run 抛错 → 状态 ERROR + 日志记录 + 重抛；output 未执行（树未被写）
    class _ErrStep(_StubStep):
        name = "抛错步骤"

        def run(self) -> int:
            raise ValueError("boom")

    e = _ErrStep.create_default(tree, pkg)
    e.io.change_value("input", 0, "5")
    e.io.change_value("input", 1, "{{s1}}")
    e.io.change_value("output", 0, "n1")
    LogModel.instance().clear()
    try:
        e.do()
        raise AssertionError("run 抛错应重抛")
    except ValueError:
        pass
    assert e.status is StepStatus.ERROR
    assert any("抛错步骤 执行错误" in x.message and "boom" in x.message
               for x in LogModel.instance().entries)
    assert tree.get("n1").data == 10            # output 未执行，值保持

    # run 手动置 ERROR → do() 后状态保持（不覆盖为 FINISHED）
    class _ManErrStep(_StubStep):
        name = "手动错误步骤"

        def run(self) -> int:
            self.outputs.total = self.inputs.a * 2
            self.status = StepStatus.ERROR
            return 1

    m = _ManErrStep.create_default(tree, pkg)
    m.io.change_value("input", 0, "5")
    m.io.change_value("input", 1, "{{s1}}")
    m.io.change_value("output", 0, "n1")
    assert m.do() == 1
    assert m.status is StepStatus.ERROR
    assert tree.get("n1").data == 10            # output 仍执行（写 5*2=10）

    # 偏移量：run 返回 2 / 0 → do() 原样返回
    class _OffStep(_StubStep):
        name = "偏移步骤"

        def run(self) -> int:
            return 2

    o2 = _OffStep.create_default(tree, pkg)
    o2.io.change_value("input", 0, "1")
    o2.io.change_value("input", 1, "{{s1}}")
    o2.io.change_value("output", 0, "n1")
    assert o2.do() == 2

    class _ZeroStep(_StubStep):
        name = "零偏移步骤"

        def run(self) -> int:
            return 0

    o0 = _ZeroStep.create_default(tree, pkg)
    o0.io.change_value("input", 0, "1")
    o0.io.change_value("input", 1, "{{s1}}")
    o0.io.change_value("output", 0, "n1")
    assert o0.do() == 0

    # run() 返回非 int（None / bool）→ ERROR + ValueError 重抛；
    # 负偏移量合法（执行器 = 程序计数器 + 偏移：负值回跳，如汇编跳转）
    class _BadOffStep(_StubStep):
        name = "坏偏移步骤"

        def run(self) -> int:
            return None      # type: ignore

    b1 = _BadOffStep.create_default(tree, pkg)
    b1.io.change_value("input", 0, "5")
    b1.io.change_value("input", 1, "{{s1}}")
    b1.io.change_value("output", 0, "n1")
    LogModel.instance().clear()
    try:
        b1.do()
        raise AssertionError("非 int 偏移量应抛 ValueError")
    except ValueError:
        pass
    assert b1.status is StepStatus.ERROR

    class _NegOffStep(_StubStep):
        name = "负偏移步骤"

        def run(self) -> int:
            return -1

    n1 = _NegOffStep.create_default(tree, pkg)
    n1.io.change_value("input", 0, "5")
    n1.io.change_value("input", 1, "{{s1}}")
    n1.io.change_value("output", 0, "n1")
    assert n1.do() == -1                 # 负偏移原样返回（执行器回跳语义）
    assert n1.status is StepStatus.FINISHED

    class _BoolOffStep(_StubStep):
        name = "布尔偏移步骤"

        def run(self) -> int:
            return True      # type: ignore

    b2 = _BoolOffStep.create_default(tree, pkg)
    b2.io.change_value("input", 0, "5")
    b2.io.change_value("input", 1, "{{s1}}")
    b2.io.change_value("output", 0, "n1")
    try:
        b2.do()
        raise AssertionError("bool 偏移量应抛 ValueError")
    except ValueError:
        pass
    assert b2.status is StepStatus.ERROR

    # to/from_format_string 往返：值一致、规范化输出稳定
    fmt = s.to_format_string()
    assert "=" not in fmt and "+" not in fmt and "/" not in fmt
    s2 = _StubStep.from_format_string(fmt, tree, pkg)
    assert isinstance(s2, _StubStep)
    assert s2.io.to_format_string() == s.io.to_format_string()
    assert s2.do() == 1 and s2.status is StepStatus.FINISHED
    assert s2.inputs.a == 5 and s2.outputs.total == 10

    # enabled（是否运行）：默认运行；可经 __init__ 指定；参与格式化串往返
    assert s.enabled is True
    s_off = _StubStep(s.io, enabled=False)
    assert s_off.enabled is False
    fmt_off = s_off.to_format_string()
    back_off = _StubStep.from_format_string(fmt_off, tree, pkg)
    assert isinstance(back_off, _StubStep) and back_off.enabled is False
    # 旧格式串（无 run 键）→ 还原默认 True（向后兼容）
    legacy_fmt = _b64.urlsafe_b64encode(_json.dumps(
        {"name": "桩步骤",
         "in": [["a", "number"], ["b", "string"]],
         "out": [["total", "number"]],
         "io": s.io.to_format_string()}, ensure_ascii=False).encode()).decode().rstrip("=")
    back_legacy = _StubStep.from_format_string(legacy_fmt, tree, pkg)
    assert isinstance(back_legacy, _StubStep) and back_legacy.enabled is True
    # run 键非 bool → ValueError
    bad_run_fmt = _b64.urlsafe_b64encode(_json.dumps(
        {"name": "桩步骤",
         "in": [["a", "number"], ["b", "string"]],
         "out": [["total", "number"]],
         "io": s.io.to_format_string(),
         "run": "yes"}, ensure_ascii=False).encode()).decode().rstrip("=")
    try:
        _StubStep.from_format_string(bad_run_fmt, tree, pkg)
        raise AssertionError("run 键非 bool 应抛 ValueError")
    except ValueError:
        pass

    # tag（标签/签名）：默认 ''；可经 __init__ 指定；参与格式化串往返
    assert s.tag == ""
    s_tag = _StubStep(s.io, tag="主流程")
    assert s_tag.tag == "主流程"
    fmt_tag = s_tag.to_format_string()
    back_tag = _StubStep.from_format_string(fmt_tag, tree, pkg)
    assert isinstance(back_tag, _StubStep) and back_tag.tag == "主流程"
    # 旧格式串（无 tag 键）→ 还原默认 ''（向后兼容）
    back_legacy2 = _StubStep.from_format_string(legacy_fmt, tree, pkg)
    assert isinstance(back_legacy2, _StubStep) and back_legacy2.tag == ""
    # tag 非 str → ValueError
    bad_tag_fmt = _b64.urlsafe_b64encode(_json.dumps(
        {"name": "桩步骤",
         "in": [["a", "number"], ["b", "string"]],
         "out": [["total", "number"]],
         "io": s.io.to_format_string(),
         "tag": 123}, ensure_ascii=False).encode()).decode().rstrip("=")
    try:
        _StubStep.from_format_string(bad_tag_fmt, tree, pkg)
        raise AssertionError("tag 非 str 应抛 ValueError")
    except ValueError:
        pass

    # 名称不匹配 → None
    other_fmt = _json.dumps({"name": "别的步骤",
                             "in": [["a", "number"], ["b", "string"]],
                             "out": [["total", "number"]],
                             "io": s.io.to_format_string()}, ensure_ascii=False)
    other_fmt = _b64.urlsafe_b64encode(other_fmt.encode()).decode().rstrip("=")
    assert _StubStep.from_format_string(other_fmt, tree, pkg) is None
    # 基类自身（name=""）同样无法匹配
    assert Step.from_format_string(fmt, tree, pkg) is None

    # 签名不匹配（in 缺 b）→ None
    sig_fmt = _json.dumps({"name": "桩步骤",
                           "in": [["a", "number"]],
                           "out": [["total", "number"]],
                           "io": s.io.to_format_string()}, ensure_ascii=False)
    sig_fmt = _b64.urlsafe_b64encode(sig_fmt.encode()).decode().rstrip("=")
    assert _StubStep.from_format_string(sig_fmt, tree, pkg) is None

    # io 槽类型与签名推导不符 → None
    wrong_io = StepIOWidget(["number"], ["number"], tree, pkg)   # 输入槽少一个
    wrong_fmt = _json.dumps({"name": "桩步骤",
                             "in": [["a", "number"], ["b", "string"]],
                             "out": [["total", "number"]],
                             "io": wrong_io.to_format_string()}, ensure_ascii=False)
    wrong_fmt = _b64.urlsafe_b64encode(wrong_fmt.encode()).decode().rstrip("=")
    assert _StubStep.from_format_string(wrong_fmt, tree, pkg) is None

    # 非法编码 / 结构缺字段 → ValueError
    for bad in ("not*valid*", "###", ""):
        try:
            _StubStep.from_format_string(bad, tree, pkg)
            raise AssertionError("非法 base64 应抛 ValueError: %r" % bad)
        except ValueError:
            pass
    try:
        _StubStep.from_format_string(
            _b64.urlsafe_b64encode('{"name":"桩步骤"}'.encode("utf-8")).decode(), tree, pkg)
        raise AssertionError("缺字段应抛 ValueError")
    except ValueError:
        pass

    # 状态通知：每次状态变更通知监听者；重复赋值不通知；移除后不再通知
    events = []

    def _l(step, st):
        events.append((step.name, st))

    s.add_status_listener(_l)
    events.clear()
    assert s.do() == 1
    assert events == [("桩步骤", StepStatus.RUNNING),
                      ("桩步骤", StepStatus.FINISHED)], events
    # 重复置同一状态 → 不通知
    s.status = StepStatus.FINISHED
    assert events == [("桩步骤", StepStatus.RUNNING),
                      ("桩步骤", StepStatus.FINISHED)]
    s.status = StepStatus.ERROR
    assert events[-1] == ("桩步骤", StepStatus.ERROR)
    # 移除监听 → 不再通知
    s.remove_status_listener(_l)
    s.status = StepStatus.PENDING
    assert events[-1] == ("桩步骤", StepStatus.ERROR)
    # 异常路径也通知（PENDING → RUNNING → ERROR）
    e.add_status_listener(_l)
    events.clear()
    try:
        e.do()
        raise AssertionError("run 抛错应重抛")
    except ValueError:
        pass
    assert events == [("抛错步骤", StepStatus.RUNNING),
                      ("抛错步骤", StepStatus.ERROR)], events

    # 注解未注册（如 "audio"）→ create_default 立即报错，带类名/字段名/支持列表
    @dataclass
    class _BadInput:
        x: "audio" = ""  # type: ignore

    class _BadStep(Step):
        name = "坏步骤"
        description = "测试用坏步骤"
        input_class = _BadInput
        output_class = _StubOutput

    try:
        _BadStep.create_default(tree, pkg)
        raise AssertionError("未注册类型应抛 ValueError")
    except ValueError as exc:
        msg = str(exc)
        assert "坏步骤" in msg and "x" in msg and "audio" in msg

    print("Step smoke OK")
