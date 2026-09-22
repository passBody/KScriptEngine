# -*- coding: utf-8 -*-
"""
串口设备步骤基类（串口鼠标/串口键盘共用，**非模板**）
==================================================

``actions/输入/串口鼠标/`` 与 ``actions/输入/串口键盘/`` 下各步骤共用同一套
「选串口 → 下发一行命令 → 把失败收敛成执行错误」的流程，本模块把它收在一处。

**为什么在 tools/ 而不在 actions/ 里**（两条都是实测踩出来的）
--------------------------------------------------------------
1. ``StepManager`` 加载 ``.kscp`` 内嵌模板时，把每个文件写进临时目录、以
   **合成点分模块名**（``_kscp<N>_actions_输入.串口键盘.基础操作.键盘按下``）从
   文件位置导入——那些父包名在 ``sys.modules`` 里根本不存在。于是**任何多级
   相对导入**（``from ..._串口步骤 import ...``）都会炸在
   ``No module named '_kscp<N>_actions_输入'``；只有绝对导入能活。
   全 ``actions/`` 树里其余模板一律绝对导入（``from tools.mouse_controller …``），
   本模块与之对齐。
2. ``_iter_source_templates`` 会把 ``actions/`` 下**除 base/__init__/__main__ 外
   的所有 .py** 当模板候选拷进工程。基类若留在 ``actions/``，它自己会被搬运并
   尝试注册成一个模板（``SerialStep`` 也是 ``Step`` 子类，却无 ``name``）。
   ``tools/`` 不在扫描范围内，天然免疫。

约定
----
* 各步骤输入类的**第 0 个字段恒为** ``串口: "string"``（自定义视图按
  :data:`widgets.卡片.serial_port_view.PORT_SLOT` = 0 号槽读写它）。
* 命令随 ``.kscp`` 存进步骤槽，行结束符/波特率见 :mod:`tools.serial_controller`。
* ``run()`` 一律**不抛异常**：校验失败与串口失败都经 :meth:`SerialStep._fail`
  置 :class:`StepStatus.ERROR` + 记错误日志，返回值仍是 1。
"""
from typing import Optional

from model.log_model import LogModel
from model.步骤.step import Step, StepStatus
from tools.serial_controller import SerialError, serial_ctrl

__all__ = []      # 本模块不导出模板（基类不是可添加的步骤）


class SerialStep(Step):
    """串口鼠标步骤基类：串口槽守卫 + 下发/查询 + 输入值守卫。"""

    # ==================== 自定义视图 ====================
    def info_widget(self, parent=None):
        """自定义视图：串口下拉框（选端口即回填 0 号「串口」槽）。"""
        from widgets.卡片.serial_port_view import SerialPortView
        return SerialPortView(self, parent)

    # ==================== 错误出口 ====================
    def _fail(self, msg: str) -> None:
        """统一的执行错误出口：置「执行错误」+ 记错误日志（run 不抛异常）。"""
        self.status = StepStatus.ERROR
        LogModel.instance().error("%s：%s" % (self.name, msg))

    # ==================== 串口 ====================
    def _port(self) -> Optional[str]:
        """「串口」输入槽 → 端口名；空则置执行错误并返回 None。"""
        port = getattr(self.inputs, "串口", None)
        port = "" if port is None else str(port).strip()
        if not port:
            self._fail("未选择串口")
            return None
        return port

    def _send(self, line: str) -> bool:
        """下发一行命令；串口未选 / 收发失败 → 置执行错误并返回 False。"""
        port = self._port()
        if port is None:
            return False
        try:
            serial_ctrl.send(port, line)
        except SerialError as e:
            self._fail(str(e))
            return False
        LogModel.instance().info("%s：%s" % (self.name, line))
        return True

    def _query(self, line: str) -> Optional[str]:
        """下发查询命令并取回一行响应；失败（含无响应）置执行错误并返回 None。"""
        port = self._port()
        if port is None:
            return None
        try:
            resp = serial_ctrl.query(port, line)
        except SerialError as e:
            self._fail(str(e))
            return None
        LogModel.instance().info("%s：%s -> %s" % (self.name, line, resp))
        return resp

    # ==================== 输入值守卫 ====================
    def _int(self, value, what: str) -> Optional[int]:
        """槽值 → int（浮点**向下取整**）；非法值置执行错误并返回 None。

        取整语义与同类模板一致（次数/坐标不接受小数）。
        """
        try:
            return int(float(value))
        except (TypeError, ValueError):
            self._fail("%s 非数值: %r" % (what, value))
            return None

    def _str(self, value, what: str) -> Optional[str]:
        """文本槽 → 去首尾空白的非空串；空则置执行错误并返回 None。"""
        text = "" if value is None else str(value).strip()
        if not text:
            self._fail("%s 为空" % what)
            return None
        return text

    def _button(self, value) -> Optional[int]:
        """鼠标键槽 → 1/2/3；其它值置执行错误并返回 None。"""
        btn = self._int(value, "指定按键")
        if btn is None:
            return None
        if btn not in (1, 2, 3):
            self._fail("指定按键须为 1(左)/2(中)/3(右)，得到 %r" % (value,))
            return None
        return btn

    def _duration_ms(self, value) -> Optional[int]:
        """按住时长槽（毫秒）→ 正整数；``t <= 0`` 置执行错误并返回 None。"""
        ms = self._int(value, "按住时长")
        if ms is None:
            return None
        if ms <= 0:
            self._fail("按住时长须大于 0 毫秒，得到 %r" % (value,))
            return None
        return ms


# ================================================================
# 冒烟辅助：桩替换串口收发（供各 action 冒烟复用）
# ================================================================
class _StubSerial:
    """记录桩：``calls`` 收 ``(port, line)``；``fail`` 置位后每次收发都抛它。"""

    def __init__(self, respond=None):
        self.calls = []
        self.fail = None          # 置 SerialError → 走错误路径
        self.respond = respond    # str / dict{line: resp} / callable(line) -> str

    def _record(self, port, line):
        self.calls.append((port, line))
        if self.fail is not None:
            raise self.fail

    def send(self, port, line):
        self._record(port, line)

    def query(self, port, line):
        self._record(port, line)
        if callable(self.respond):
            return self.respond(line)
        if isinstance(self.respond, dict):
            return self.respond.get(line, "")
        return self.respond if self.respond is not None else ""


def install_stub_serial(respond=None) -> _StubSerial:
    """冒烟辅助：拦截**本类别全部**串口步骤的收发，返回记录桩。

    patch 的是**本模块全局** ``serial_ctrl`` —— :meth:`SerialStep._send` /
    :meth:`SerialStep._query` 读的正是它，故各 action 冒烟不必各自打桩，
    也不受 runpy「包导入缓存了旧模块对象」陷阱影响。
    """
    global serial_ctrl
    stub = _StubSerial(respond)
    serial_ctrl = stub
    return stub


# ================================================================
# 冒烟演示：直接 ``python -m tools.serial_step`` 运行
# ================================================================
if __name__ == "__main__":
    from dataclasses import dataclass

    from model.工程.kscp_package import KscpPackage
    from model.变量.project_variable import ProjectVariable
    from model.变量.variable_tree import VariableTree

    @dataclass
    class _In:
        """最小输入类：只为驱动基类（真实步骤的输入类见各 action 模块）。"""
        串口: "string" = ""  # type: ignore
        x: "number" = 0      # type: ignore

    @dataclass
    class _Out:
        pass

    class _Demo(SerialStep):
        name = "串口基类自检"
        description = "非模板"
        input_class = _In
        output_class = _Out

        def run(self) -> int:
            x = self._int(self.inputs.x, "x")
            if x is None:
                return 1
            self._send("TEST:%d" % x)
            return 1

    pkg = KscpPackage.create_empty()
    tree = VariableTree.create_empty()

    d = _Demo.create_default(tree, pkg)
    assert d.io._input_type == ["string", "number"]
    assert d.io._output_type == []

    stub = install_stub_serial()
    d.io.change_value("input", 1, "5")

    # ---- 空串常量进不了 run：io 校验先拦下（do 重抛） ----
    try:
        d.do()
        raise AssertionError("空串常量应被 io 校验拦下")
    except ValueError:
        pass
    assert stub.calls == [], stub.calls

    # ---- 未选串口 → 执行错误、不下发（空值守卫须经变量引用才触达） ----
    tree.add("空串", ProjectVariable.create("string", "", pkg))
    d.io.change_value("input", 0, "{{空串}}")
    LogModel.instance().clear()
    assert d.do() == 1
    assert d.status is StepStatus.ERROR
    assert stub.calls == [], stub.calls
    assert any("未选择串口" in e.message for e in LogModel.instance().entries), \
        [e.message for e in LogModel.instance().entries]

    # ---- 正常下发：槽值参与命令、状态完成、日志有命令原文 ----
    d.io.change_value("input", 0, "COM9")
    LogModel.instance().clear()
    assert d.do() == 1
    assert d.status is StepStatus.FINISHED, d.status
    assert stub.calls == [("COM9", "TEST:5")], stub.calls
    assert any("TEST:5" in e.message for e in LogModel.instance().entries), \
        [e.message for e in LogModel.instance().entries]

    # 注：非数值常量（"abc" 填进 number 槽）到不了 run —— io 校验先拦下，
    # 故 _int 守卫按下方「输入守卫」直接单测，不绕 do()。

    # ---- 串口失败 → 执行错误 + 错误日志（run 不抛） ----
    stub.calls.clear()
    d.io.change_value("input", 1, "7")
    stub.fail = SerialError("打开串口 COM9 失败: 桩")
    LogModel.instance().clear()
    assert d.do() == 1
    assert d.status is StepStatus.ERROR
    assert stub.calls == [("COM9", "TEST:7")], stub.calls
    assert any(e.level.name == "ERROR" and "COM9" in e.message
               for e in LogModel.instance().entries), \
        [(e.level.name, e.message) for e in LogModel.instance().entries]
    stub.fail = None

    # ---- 查询：取回响应；无响应（桩抛）→ 执行错误 ----
    stub.respond = "resp-v1"
    assert d._query("IDN?") == "resp-v1"
    assert stub.calls[-1] == ("COM9", "IDN?"), stub.calls[-1]
    stub.respond = None
    stub.fail = SerialError("串口 COM9 无响应（超时 1.0s）: IDN?")
    assert d._query("IDN?") is None
    assert d.status is StepStatus.ERROR
    stub.fail = None

    # ---- 输入守卫：_int 向下取整 / _button 枚举 / _duration_ms 正数 / _str 非空 ----
    assert d._int("100.9", "x") == 100 and d._int(-3.7, "x") == -3
    assert d._int("", "x") is None and d.status is StepStatus.ERROR
    assert d._button("2") == 2
    assert d._button("9") is None and d.status is StepStatus.ERROR
    assert d._int("0", "x") == 0                      # 0 合法（非 None）
    assert d._duration_ms("50") == 50
    assert d._duration_ms("0") is None and d.status is StepStatus.ERROR
    assert d._str("  ctrl  ", "按键") == "ctrl"
    assert d._str("   ", "按键") is None and d.status is StepStatus.ERROR

    # ---- 往返 ----
    fmt = d.to_format_string()
    d2 = _Demo.from_format_string(fmt, tree, pkg)
    assert isinstance(d2, _Demo)
    assert d2.io.to_format_string() == d.io.to_format_string()

    print("SerialStep smoke OK")
