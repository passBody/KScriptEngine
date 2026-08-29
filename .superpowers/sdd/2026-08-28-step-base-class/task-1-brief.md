# Task 1 Brief: 步骤基类 `actions/base.py`

(摘自 `docs/superpowers/plans/2026-08-28-step-base-class.md` Task 1,实施者以此为准,精确值照抄)

## Global Constraints(本项目全局约束,全部任务适用)

- 非 git 仓库:不提交,用运行冒烟验证替代。冒烟测试即各文件 `__main__` 中的 assert 块,`python -m <module>` 运行。
- 格式化串:UTF-8 JSON → urlsafe base64 去填充(与 `ProjectVariable`/`StepIOWidget` 一致)。
- 输入/输出 dataclass 字段必须带默认值(基类以无参方式实例化空容器)。
- 输入/输出类实例属性命名 `self.inputs` / `self.outputs`(方法 `input()`/`output()` 不能与实例属性同名——实例属性会遮蔽方法)。
- 冒烟测试用到 `QApplication` 时必须先创建(`QApplication.instance() or QApplication(sys.argv)`)。
- 路径中文包名合法(`actions.控制流程.time_delay`),勿改目录名。

**Files:**
- Create: `actions/__init__.py`
- Create: `actions/base.py`

**Interfaces:**
- Consumes: `widgets.step_io_widget.StepIOWidget`(resolve_inputs / write_outputs / change_value / to_format_string / from_format_string)、`model.log_model.LogModel`(单例,error())、`model.variable_tree.VariableTree`、`model.kscp_package.KscpPackage`
- Produces: `StepStatus`(Enum:PENDING/RUNNING/FINISHED/ERROR)、`Step`(name/description/input_class/output_class 类属性;io/status/inputs/outputs 实例属性;info_widget/input/run/output/do/to_format_string/from_format_string/create_default 方法;私有 `_io_type_lists`/`_signature`/`_decode`)

---

- [ ] **Step 1: 写失败测试(先红)——建 `actions/__init__.py` + `actions/base.py`(仅文档字符串 + `__main__` 冒烟块)**

`actions/__init__.py`:

```python
from .base import Step, StepStatus

__all__ = ["Step", "StepStatus"]
```

`actions/base.py`(此刻不含任何类定义,只有模块 docstring 与冒烟块;冒烟块引用的 `Step`/`StepStatus` 尚未定义,运行将 NameError):

```python
# -*- coding: utf-8 -*-
"""
步骤基类（数据结构 + 执行流程）
==============================

:class:`Step` 是所有「步骤」的基类：步骤是用来执行的，后续会创建步骤列表，
点击执行后每个步骤按顺序执行。子类在 ``actions/`` 下按目录分组
（如 ``actions/控制流程/time_delay.py``）。

基类职责
--------
* 持有「步骤输入/输出设置（数据 + GUI 生成器）」（:class:`StepIOWidget`）。
* 提供 :meth:`do` 整合执行流程：input → run → output → 返回偏移量。
* 提供 :meth:`to_format_string` / :meth:`from_format_string` 编码还原自身。

子类需覆盖
----------
* ``name`` / ``description``：步骤名称与描述。
* ``input_class`` / ``output_class``：dataclass，字段类型注解为变量类型名
  （如 ``"number"``），字段需带默认值（实例化空容器用）。
* :meth:`run`：执行逻辑，返回步骤偏移量（默认 1 = 运行下一个步骤、
  2 = 运行之后第二个、0 = 重新调用自身）。

基本用法
--------
::

    step = TimeDelay.create_default(tree, pkg)   # 由字段签名自动构建空 io
    step.io.change_value("input", 0, "5")        # 配置输入槽
    offset = step.do()                           # 执行：input→run→output
"""
```

然后在文件末尾追加(先只写冒烟块,类定义留到 Step 3):

```python
# ================================================================
# 冒烟演示：直接 ``python -m actions.base`` 运行
# ================================================================
if __name__ == "__main__":
    import base64 as _b64
    import json as _json
    import sys

    from PyQt5.QtWidgets import QApplication, QLabel

    from model.kscp_package import KscpPackage
    from model.log_model import LogModel
    from model.project_variable import ProjectVariable
    from model.variable_tree import VariableTree
    from widgets.step_io_widget import StepIOWidget

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
        a: "number" = 0
        b: "string" = ""

    @dataclass
    class _StubOutput:
        total: "number" = 0

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
    assert s.io._input_type == ["number", "string"]
    assert s.io._output_type == ["number"]
    assert s.status is StepStatus.PENDING
    assert s.inputs.a == 0 and s.inputs.b == "" and s.outputs.total == 0
    card = s.info_widget()
    assert isinstance(card, QLabel)
    assert card.text() == "测试用桩步骤"

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

    # to/from_format_string 往返：值一致、规范化输出稳定
    fmt = s.to_format_string()
    assert "=" not in fmt and "+" not in fmt and "/" not in fmt
    s2 = _StubStep.from_format_string(fmt, tree, pkg)
    assert isinstance(s2, _StubStep)
    assert s2.io.to_format_string() == s.io.to_format_string()
    assert s2.do() == 1 and s2.status is StepStatus.FINISHED
    assert s2.inputs.a == 5 and s2.outputs.total == 10

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
            _b64.urlsafe_b64encode(b'{"name":"桩步骤"}').decode(), tree, pkg)
        raise AssertionError("缺字段应抛 ValueError")
    except ValueError:
        pass

    print("Step smoke OK")
```

- [ ] **Step 2: 运行确认失败(红)**

Run: `python -m actions.base`
Expected: `NameError: name 'Step' is not defined`(冒烟块里 `_StubStep(Step)` 处)。若报错内容不是「功能缺失」而是其它(如 import 错误、QApplication 问题),先修复再重新确认。

- [ ] **Step 3: 实现最小代码 —— 在 `actions/base.py` 的 docstring 之后、冒烟块之前插入类定义**

```python
from __future__ import annotations

import base64
import json
from dataclasses import fields
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING

from PyQt5.QtWidgets import QLabel, QWidget

from model.log_model import LogModel
from widgets.step_io_widget import StepIOWidget

if TYPE_CHECKING:
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

    def __init__(self, io: StepIOWidget) -> None:
        self.io = io                     # 步骤输入/输出设置（数据 + GUI 生成器）
        self.status: StepStatus = StepStatus.PENDING
        self.inputs = self.input_class()     # 输入类实例（运行时值容器）
        self.outputs = self.output_class()   # 输出类实例（运行时值容器）

    # ================================================================
    # 槽类型推导 / 签名
    # ================================================================
    @classmethod
    def _io_type_lists(cls) -> Tuple[List[str], List[str]]:
        """由输入/输出 dataclass 字段的类型注解推导 io 槽类型列表（顺序一致）。"""
        return ([f.type for f in fields(cls.input_class)],
                [f.type for f in fields(cls.output_class)])

    @classmethod
    def _signature(cls, klass: type) -> List[List[str]]:
        """dataclass 签名：[(字段名, 类型注解), ...]。"""
        return [[f.name, f.type] for f in fields(klass)]

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
    def info_widget(self, parent: Optional[QWidget] = None) -> QWidget:
        """信息显示窗口：可在步骤列表视图的卡片里生成自定义窗口；默认显示描述。"""
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

        默认 1：运行下一个步骤；返回 2：运行之后第二个；返回 0：重新调用自身。
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
        """
        self.status = StepStatus.RUNNING
        try:
            self.input()
            offset = self.run()
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
        """生成格式化数据：base64 编码【名称，输入类签名，输出类签名，io 格式串】。"""
        raw = json.dumps({
            "name": self.name,
            "in": self._signature(self.input_class),
            "out": self._signature(self.output_class),
            "io": self.io.to_format_string(),
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
        if io._input_type != cls._io_type_lists()[0] \
                or io._output_type != cls._io_type_lists()[1]:
            return None
        return cls(io)

    @staticmethod
    def _decode(fmt: str) -> Dict[str, Any]:
        """反解格式化字符串为 ``{"name","in","out","io"}``。"""
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
        return obj
```

- [ ] **Step 4: 运行确认通过(绿)**

Run: `python -m actions.base`
Expected: `Step smoke OK`(若无输出或报错,检查 Step 3 代码与冒烟断言是否一致)

- [ ] **Step 5: 验证(替代提交)——确认依赖链未破坏**

Run:
```bash
python -m widgets.step_io_widget   # StepIOWidget 冒烟（base 依赖它）
python -c "import actions; print(actions.Step, actions.StepStatus)"
python main.py --check             # 主窗口自检
```
Expected: `StepIOWidget smoke OK`、`<class 'actions.base.Step'> ...`、`main --check OK`

## 实施者报告契约

完成全部步骤后,把完整报告写入 `.superpowers/sdd/2026-08-28-step-base-class/task-1-report.md`,包含:
- 各步骤执行情况(红/绿输出摘要)
- 冒烟运行命令与结果
- 自检发现与处理
- 疑问/顾虑

向控制器返回:状态(DONE / DONE_WITH_CONCERNS / NEEDS_CONTEXT / BLOCKED)+ 一行测试摘要 + 关注点。**不得派生子代理。**
