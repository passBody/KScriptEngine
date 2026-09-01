# -*- coding: utf-8 -*-
"""
步骤输入/输出设置（数据 + GUI 生成器）
======================================

:class:`StepIOWidget` 是一个**轻量数据对象**（不继承 QWidget），用于标记步骤的
输入/输出变量或常量，可访问全局变量树 :class:`model.variable_tree.VariableTree`。
当需要 GUI 时调用 :meth:`gen_widget` 生成一个 QWidget，嵌入「步骤对象」卡片。
步骤执行函数借助本对象的获取输入 / 设置输出方法完成 输入→计算→输出
（无回调；编排由「步骤对象」内部负责）。

本模块属 model 层：**模块顶层不导入 PyQt5**，Qt 控件仅在生成 GUI 的方法内
延迟导入（:meth:`gen_widget` / :meth:`_default_picker` 等），因此导入本模块
不依赖 GUI 环境。

数据流（对象解析+写回；``run`` 由「步骤对象」内部编排，故此处不提供）::

    resolved = widget.resolve_inputs()        # 常量原值 / {{name}} -> tree.get(name).get_actual_data()
    ...                                      # run：纯逻辑计算（输入→输出）
    widget.write_outputs(outs)               # 对象：按输出槽类型写回变量树（检查变量合规）

基本用法
--------
::

    w = StepIOWidget(
        input_type=["number", "png", "string"],
        output_type=["number"],
        tree=variable_tree, package=kscp_pkg,
    )
    w.change_value("input", 0, "5")             # 常量
    w.change_value("input", 1, "{{img/pic}}")   # 变量引用（全局变量树中的变量名）
    w.change_value("output", 0, "结果")         # 输出到树中变量
    if w.is_valid:
        resolved = w.resolve_inputs()           # 按顺序取输入实际值
        w.write_outputs(calc(*resolved))        # 计算后写回（输出变量全是工程变量，检查合规）
    fmt = w.to_format_string()                  # 格式化自身（base64）
    w2 = StepIOWidget.from_format_string(fmt, tree, pkg)  # 静态方法还原
    card_layout.addWidget(w.gen_widget())       # 需要时才生成 QWidget
"""

from __future__ import annotations

import base64
import json
import re
import weakref
from typing import Any, Callable, Dict, List, Optional, Tuple, TYPE_CHECKING

from model.project_variable import ProjectVariable

# Qt.UserRole 在 PyQt5 运行期可用（Pyright 存根误报为未知，这里取其整数值规避）
_USER_ROLE = 0x0100  # Qt.UserRole

if TYPE_CHECKING:
    from PyQt5.QtWidgets import (
        QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QLineEdit, QPushButton,
        QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
    )
    from model.kscp_package import KscpPackage
    from model.variable_tree import VariableTree

__all__ = ["StepIOWidget"]

# 整串 {{变量名}} 才算变量引用（不支持串内插值/计算，留作后续）
_VAR_REF = re.compile(r"^\{\{(.+)\}\}$")

# 资源类槽可直接选择的图片扩展名（整合选择器：image 槽可选包内资源路径作常量）
_IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp")


def _parse_number(text: str) -> Any:
    """把文本解析为 int 或 float；失败抛 :class:`ValueError`。"""
    t = text.strip()
    try:
        return int(t)
    except ValueError:
        return float(t)  # 再失败则向上抛 ValueError


class StepIOWidget:
    """步骤输入/输出设置对象（轻量，不继承 QWidget）。

    输入槽存字符串（常量或 ``{{变量名}}`` 引用），输出槽存变量名。
    对象负责解析输入与写回输出（无回调，编排由「步骤对象」内部负责），并可
    经 :meth:`to_format_string` / :meth:`from_format_string` 编码还原自身；
    需要 GUI 时调 :meth:`gen_widget` 生成 QWidget。一个对象可多次
    ``gen_widget``，各控件经弱引用登记，互相保持同步。
    """

    # 可编辑类型的常量解析器（资源类不可编辑常量、自动走选择器）
    _CONSTANT_PARSERS: Dict[str, Callable[[str], Any]] = {
        "string": lambda t: t,
        "number": _parse_number,
    }

    def __init__(self, input_type: List[str], output_type: List[str],
                 tree: "VariableTree", package: "KscpPackage") -> None:
        self._input_type: List[str] = list(input_type)
        self._output_type: List[str] = list(output_type)
        self._tree = tree
        self._package = package
        self._input_values: List[str] = [""] * len(self._input_type)
        self._output_values: List[str] = [""] * len(self._output_type)
        self._input_names: Optional[List[str]] = None    # 参数名（Step 签名注入；None=无名字）
        self._output_names: Optional[List[str]] = None
        self._input_optional: List[bool] = [False] * len(self._input_type)
        # 可选输入标记（Step 签名注入）：可选槽空值不校验、解析为 None
        self._picker: Optional[Callable[..., Optional[str]]] = None  # None -> 内置默认
        self._widgets: List["weakref.ref[QWidget]"] = []  # 已生成控件弱引用
        self._listeners: List[Callable[[], None]] = []  # 槽值变更监听（任意写入路径均通知）

    # ================================================================
    # 类型扩展接口（预留）
    # ================================================================
    @classmethod
    def register_constant_parser(cls, type_name: str,
                                 parser: Callable[[str], Any]) -> None:
        """注册可编辑类型的常量解析器（预留接口）。资源类无需注册。"""
        cls._CONSTANT_PARSERS[type_name] = parser

    @staticmethod
    def _type_is_resource(vtype: str) -> bool:
        """该类型是否为资源类（决定编辑器样式：资源类只能选择）。"""
        h = ProjectVariable.type_of(vtype)
        return h.is_resource if h is not None else False

    @staticmethod
    def _accepted_types(vtype: str) -> Tuple[str, ...]:
        """槽位接受的变量类型集合：string 槽兼容 number（隐式转字符串）。"""
        return ("string", "number") if vtype == "string" else (vtype,)

    # ================================================================
    # 槽值变更监听（自定义视图刷新预览等用；纯 Python 回调，无 Qt）
    # ================================================================
    def add_listener(self, cb: Callable[[], None]) -> None:
        """注册槽值变更监听：任何输入/输出槽值写入后调用 ``cb()``。"""
        self._listeners.append(cb)

    def remove_listener(self, cb: Callable[[], None]) -> None:
        """移除监听者；未注册静默忽略。"""
        try:
            self._listeners.remove(cb)
        except ValueError:
            pass

    def _notify_listeners(self) -> None:
        for cb in list(self._listeners):   # 拷贝遍历：回调可增删监听者
            try:
                cb()
            except Exception:
                pass                       # 监听者异常不打断数据写入

    def input_value(self, i: int) -> str:
        """读取输入槽原始串（常量或 ``{{变量名}}``）；越界抛 :class:`IndexError`。"""
        if not 0 <= i < len(self._input_values):
            raise IndexError("输入索引越界: %d" % i)
        return self._input_values[i]

    def output_value(self, i: int) -> str:
        """读取输出槽原始串（变量名）；越界抛 :class:`IndexError`。"""
        if not 0 <= i < len(self._output_values):
            raise IndexError("输出索引越界: %d" % i)
        return self._output_values[i]

    @property
    def input_types(self) -> List[str]:
        """输入槽类型列表（只读副本；跨类签名比对用，避免访问私有 _input_type——评审#11）。"""
        return list(self._input_type)

    @property
    def output_types(self) -> List[str]:
        """输出槽类型列表（只读副本）。"""
        return list(self._output_type)

    @property
    def tree(self) -> "VariableTree":
        """关联的变量树（自定义视图解析 ``{{变量}}`` 引用用）。"""
        return self._tree

    @property
    def package(self) -> "KscpPackage":
        """关联的工程包（资源类常量读写/校验用，如素材预览读取资源路径）。"""
        return self._package

    def set_optional_inputs(self, flags: List[bool]) -> None:
        """设置输入槽可选标记（Step 签名注入；不足补 False、多余忽略）。

        可选槽语义：空值合规（校验/错误原因跳过）、解析为 None；一旦填值
        仍按类型正常校验。输出槽恒为必须。
        """
        self._input_optional = list(flags[:len(self._input_type)])
        if len(self._input_optional) < len(self._input_type):
            self._input_optional += [False] * (
                len(self._input_type) - len(self._input_optional))

    def set_slot_names(self, input_names: Optional[List[str]],
                       output_names: Optional[List[str]]) -> None:
        """设置槽标签用的参数名（来自 Step 的输入/输出 dataclass 字段名）。

        ``None`` = 无名字 → 标签回退「类型+序号」。名字数量与槽数不符时
        只取前 N 个，多余忽略（防调用方数据错误）。
        """
        self._input_names = list(input_names) if input_names else None
        self._output_names = list(output_names) if output_names else None

    # ================================================================
    # 合规性 / 解析 / 写回
    # ================================================================
    @property
    def is_valid(self) -> bool:
        """是否合规：输入与输出全部合规。"""
        return self._validate_inputs() and self._validate_outputs()

    def _validate_inputs(self) -> bool:
        return all(self._is_input_valid(i, t)
                   for i, t in enumerate(self._input_type))

    def _is_input_valid(self, i: int, vtype: str) -> bool:
        text = self._input_values[i]
        if self._input_optional[i] and (
                not isinstance(text, str) or not text.strip()):
            return True   # 可选槽为空 → 合规（跳过类型/引用校验）
        if not isinstance(text, str):
            return False  # 槽值非 str（程序性注入）：视为不合规，不崩溃
        m = _VAR_REF.match(text)
        if m:  # 变量引用
            name = m.group(1)
            try:
                # 用 is_variable 而非 ``in``：``in`` 对分组名也为 True，
                # 随后 get() 抛 FileNotFoundError（用户输入 {{组名}} 崩溃）
                if not self._tree.is_variable(name):
                    return False
                return self._tree.get(name).type in self._accepted_types(vtype)
            except (ValueError, FileNotFoundError):
                return False   # 根路径等非法引用：非法而非崩溃
        # 常量
        if self._type_is_resource(vtype):
            # 资源类常量 = 包内图片资源路径（整合选择器：image 槽可直接选资源）
            return (bool(text.strip())
                    and text.lower().endswith(_IMAGE_EXTS)
                    and self._package.exists(text))
        if not text.strip():
            return False  # 为空
        parser = self._CONSTANT_PARSERS.get(vtype, lambda t: t)
        try:
            parser(text)
        except (ValueError, TypeError):
            return False
        return True

    def _validate_outputs(self) -> bool:
        for i in range(len(self._output_type)):
            name = self._output_values[i]
            try:
                # is_variable 而非 ``in``：输出槽指向分组名应判非法，
                # 否则 write_outputs 的 tree.set() 会因「目标已是分组」抛 ValueError
                if not name or not self._tree.is_variable(name):
                    return False
            except ValueError:
                return False
        return True

    def error_reasons(self) -> List[str]:
        """不合规的具体原因列表（输入槽 → 输出槽顺序）；空列表 = 全合规。

        每条一条短语（「输入参数为空」「变量不存在: n1」「n1 类型不符」、
        「无法解析为 number」「输出变量未指定」），供卡片在正下方提示
        （宿主以「⚠: 」前缀拼接展示，见 :class:`widgets.step_list_view.StepListView`）。
        """
        out: List[str] = []
        for i, vtype in enumerate(self._input_type):
            text = self._input_values[i]
            if self._input_optional[i] and (
                    not isinstance(text, str) or not text.strip()):
                continue                       # 可选槽为空 → 无错误
            if not isinstance(text, str):
                out.append("输入参数为空")      # 槽值非 str：按空处理，不崩溃
                continue
            m = _VAR_REF.match(text)
            if m:  # 变量引用
                name = m.group(1)
                try:
                    if not self._tree.is_variable(name):
                        out.append("变量不存在: %s" % name)
                    elif self._tree.get(name).type not in self._accepted_types(vtype):
                        out.append("%s 类型不符" % name)
                except (ValueError, FileNotFoundError):
                    out.append("变量不存在: %s" % name)
                continue
            if self._type_is_resource(vtype):
                if not text.strip():
                    out.append("输入参数为空")
                elif (not text.lower().endswith(_IMAGE_EXTS)
                      or not self._package.exists(text)):
                    out.append("资源不存在: %s" % text)  # 或非图片扩展名
            elif not text.strip():
                out.append("输入参数为空")
            else:
                parser = self._CONSTANT_PARSERS.get(vtype, lambda t: t)
                try:
                    parser(text)
                except (ValueError, TypeError):
                    out.append("无法解析为 %s" % vtype)
        for i in range(len(self._output_type)):
            name = self._output_values[i]
            if not name:
                out.append("输出变量未指定")
            else:
                try:
                    ok = self._tree.is_variable(name)
                except ValueError:
                    ok = False
                if not ok:
                    out.append("变量不存在: %s" % name)
        return out

    def resolve_inputs(self) -> List[Any]:
        """解析所有输入为实际数据（引用→``get_actual_data()``，常量→解析值）。

        不合规抛 :class:`ValueError`。
        """
        if not self._validate_inputs():
            raise ValueError("输入不合规，无法解析")
        out: List[Any] = []
        for i, vtype in enumerate(self._input_type):
            text = self._input_values[i]
            if self._input_optional[i] and (
                    not isinstance(text, str) or not text.strip()):
                out.append(None)          # 可选槽为空 → 解析为 None
                continue
            m = _VAR_REF.match(text)
            if m:
                var = self._tree.get(m.group(1))
                data = var.get_actual_data()
                if vtype == "string" and var.type == "number":
                    data = str(data)          # 数字变量 → 字符串（隐式转换）
                out.append(data)
            elif self._type_is_resource(vtype):
                out.append(self._package.read_file(text))   # 资源常量 → 文件字节
            else:
                parser = self._CONSTANT_PARSERS.get(vtype, lambda t: t)
                out.append(parser(text))
        return out

    def write_outputs(self, outs: List[Any]) -> None:
        """按输出槽类型把 ``outs`` 写回变量树（输出变量全是工程变量）。

        每个 ``outs[i]`` 经 ``ProjectVariable.create(output_type[i], value, package)``
        创建变量；创建的变量不合规（如 number 槽写字符串）抛 :class:`ValueError`，
        变量名不在树中抛 :class:`FileNotFoundError`。合规后 ``tree.set(name, var)``
        替换同名变量。
        """
        if len(outs) != len(self._output_type):
            raise ValueError("输出值数量与输出槽数不符: %d vs %d" % (
                len(outs), len(self._output_type)))
        for i, vtype in enumerate(self._output_type):
            name = self._output_values[i]
            if not name:
                raise ValueError("输出槽 %d 未指定变量名" % i)
            if name not in self._tree:
                raise FileNotFoundError("输出变量不在树中: %r" % name)
            var = ProjectVariable.create(vtype, outs[i], self._package)
            if not var.valid:
                raise ValueError(
                    "输出槽 %d 的值不合规（%s 类型）: %r" % (i, vtype, outs[i]))
            self._tree.set(name, var)

    # ================================================================
    # 格式化字符串
    # ================================================================
    def to_format_string(self) -> str:
        """提取槽类型与槽值（非实际值）生成 base64 格式化字符串。

        格式：``json({"it": 输入类型列表, "iv": 输入值列表, "ot": 输出类型列表,
        "ov": 输出值列表})`` 经 UTF-8、urlsafe base64 去填充。
        """
        raw = json.dumps({
            "it": self._input_type,
            "iv": self._input_values,
            "ot": self._output_type,
            "ov": self._output_values,
        }, ensure_ascii=False)
        return base64.urlsafe_b64encode(
            raw.encode("utf-8")).decode("ascii").rstrip("=")

    @classmethod
    def from_format_string(cls, fmt: str, tree: "VariableTree",
                           package: "KscpPackage") -> "StepIOWidget":
        """由格式化字符串（base64）反解槽类型与槽值，还原自身对象。

        ``tree`` / ``package`` 用于还原后的解析与校验。非法 base64 或结构
        缺字段/数量不符抛 :class:`ValueError`；槽值语义（如引用不存在的
        变量）不抛错，经 :meth:`is_valid` 反映当前树状态。
        """
        obj = cls._decode(fmt)
        w = cls(obj["it"], obj["ot"], tree, package)
        w._input_values = list(obj["iv"])
        w._output_values = list(obj["ov"])
        return w

    @staticmethod
    def _decode(fmt: str) -> Dict[str, Any]:
        """反解格式化字符串为 ``{"it": ..., "iv": ..., "ot": ..., "ov": ...}``。"""
        if not isinstance(fmt, str) or not fmt:
            raise ValueError("无效的步骤输入/输出格式化字符串: %r" % (fmt,))
        pad = "=" * (-len(fmt) % 4)
        try:
            raw = base64.urlsafe_b64decode((fmt + pad).encode("ascii"))
            obj = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as e:
            raise ValueError("无效的步骤输入/输出格式化字符串: %r（%s）" % (fmt, e))
        if not isinstance(obj, dict) or not {"it", "iv", "ot", "ov"} <= set(obj):
            raise ValueError("无效的步骤输入/输出格式化字符串: %r" % (fmt,))
        for k in ("it", "iv", "ot", "ov"):
            if not isinstance(obj[k], list):
                raise ValueError("无效的步骤输入/输出格式化字符串: %r" % (fmt,))
        if len(obj["it"]) != len(obj["iv"]) or len(obj["ot"]) != len(obj["ov"]):
            raise ValueError("无效的步骤输入/输出格式化字符串: %r" % (fmt,))
        # 元素类型校验：类型名与槽值必须全是 str（手工编辑的 .kscp 含数字等
        # 会在后续 _VAR_REF.match 上 TypeError，这里提前拒绝）
        for k in ("it", "ot", "iv", "ov"):
            for i, v in enumerate(obj[k]):
                if not isinstance(v, str):
                    raise ValueError(
                        "无效的步骤输入/输出格式化字符串: %r（%s[%d] 非字符串）"
                        % (fmt, k, i))
        return obj

    # ================================================================
    # GUI 生成
    # ================================================================
    def gen_widget(self, parent: Optional[QWidget] = None) -> QWidget:
        """按槽类型动态生成一个 QWidget（输入区 + 输出区），返回供卡片嵌入。

        控件内的编辑会写回本对象数据；本对象的 :meth:`change_value` 也会刷新
        所有已生成控件。可多次调用，各控件互相同步。
        """
        from PyQt5.QtWidgets import QVBoxLayout, QWidget

        widget = QWidget(parent)
        widget.input_fields = []   # List[QWidget]：各输入槽的控件
        widget.output_fields = []  # List[QWidget]：各输出槽的控件
        widget.input_labels = []   # List[QLabel]：各输入槽的标签（变量名/常量值）
        widget.output_labels = []  # List[QLabel]：各输出槽的标签

        root = QVBoxLayout(widget)
        root.setContentsMargins(16, 6, 16, 16)   # 左右/底部明显留白：控件不贴卡片边（参数多时可滚动）
        root.setSpacing(6)

        root.addWidget(self._section_label("输入"))
        for i, vtype in enumerate(self._input_type):
            root.addLayout(self._make_input_row(widget, i, vtype))

        root.addWidget(self._section_label("输出"))
        for i, vtype in enumerate(self._output_type):
            root.addLayout(self._make_output_row(widget, i, vtype))
        root.addStretch()

        self._widgets.append(weakref.ref(widget))
        return widget

    def _live_widgets(self) -> List[QWidget]:
        """返回仍存活的已生成控件，并顺手清理失效弱引用。

        同一步骤被视图重建多次时，本对象持有多个已生成控件；旧控件随卡片
        销毁，但其 Python 包装器可能仍被注册表持有（C++ 对象已删除）。
        这里按 C++ 存活与否过滤，否则对旧控件刷新字段会抛 RuntimeError
        （wrapped C/C++ object has been deleted），且弱引用列表会无限累积。
        """
        live: List[QWidget] = []
        refs: List["weakref.ref[QWidget]"] = []
        for ref in self._widgets:
            w = ref()
            if w is None:
                continue
            try:
                w.objectName()      # C++ 对象是否已删除
            except RuntimeError:
                continue
            live.append(w)
            refs.append(ref)
        self._widgets = refs
        return live

    @staticmethod
    def _section_label(text: str) -> QLabel:
        from PyQt5.QtWidgets import QLabel

        lbl = QLabel(text)
        lbl.setStyleSheet("font-weight:bold; color:#555; padding-top:2px;")
        return lbl

    def _make_input_row(self, widget: QWidget, i: int, vtype: str) -> QHBoxLayout:
        from PyQt5.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QPushButton

        row = QHBoxLayout()
        row.setSpacing(4)
        lbl = QLabel()
        lbl.setMinimumWidth(40)
        self._apply_row_label(lbl, "input", i)
        row.addWidget(lbl)
        widget.input_labels.append(lbl)
        if self._type_is_resource(vtype):
            # 资源类：仅一个按钮（只能选择变量）
            fallback = ("（可选）选择变量…" if self._input_optional[i]
                        else "选择变量…")
            btn = QPushButton(self._display_name(self._input_values[i])
                              or fallback)
            btn.clicked.connect(lambda _=False, wd=widget, i=i: self._pick_input(wd, i))
            row.addWidget(btn, 1)
            widget.input_fields.append(btn)
            return row
        # 可编辑类型：QLineEdit + 选择按钮
        edit = QLineEdit()
        edit.setPlaceholderText(
            ("（可选）" if self._input_optional[i] else "") + "常量 或 {{变量名}}")
        edit.blockSignals(True)
        edit.setText(self._input_values[i])  # 初始值不触发同步
        edit.blockSignals(False)
        edit.textChanged.connect(
            lambda text, wd=widget, i=i: self._set_input(i, text, skip=wd))
        btn = QPushButton("…")
        btn.setFixedWidth(28)
        btn.setToolTip("选择变量")
        btn.clicked.connect(lambda _=False, wd=widget, i=i: self._pick_input(wd, i))
        row.addWidget(edit, 1)
        row.addWidget(btn)
        widget.input_fields.append(edit)
        return row

    def _make_output_row(self, widget: QWidget, i: int, vtype: str) -> QHBoxLayout:
        from PyQt5.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QPushButton

        row = QHBoxLayout()
        row.setSpacing(4)
        lbl = QLabel()
        lbl.setMinimumWidth(40)
        self._apply_row_label(lbl, "output", i)
        row.addWidget(lbl)
        widget.output_labels.append(lbl)
        edit = QLineEdit(self._output_values[i])
        edit.setReadOnly(True)
        edit.setPlaceholderText("未指定")
        btn = QPushButton("…")
        btn.setFixedWidth(28)
        btn.setToolTip("选择变量")
        btn.clicked.connect(
            lambda _=False, wd=widget, i=i, vt=vtype: self._pick_output(wd, i, vt))
        row.addWidget(edit, 1)
        row.addWidget(btn)
        widget.output_fields.append(edit)
        return row

    @staticmethod
    def _display_name(value: str) -> str:
        """从输入字段串中取出变量名（剥 ``{{}}``）；常量返回原串。非 str 返回空串。"""
        if not isinstance(value, str):
            return ""
        m = _VAR_REF.match(value)
        return m.group(1) if m else value

    def _row_label(self, kind: str, i: int) -> Tuple[str, str]:
        """槽标签 (显示文本, tooltip)：**参数名**（Step 签名注入，如 ``x``/``y``），
        无名字回退「类型+序号」；tooltip 含类型与当前值（变量名/常量）。

        显示文本不在此截断——截断在控件层按标签宽度做（见 _apply_row_label）。
        """
        if kind == "input":
            vtype = self._input_type[i]
            value = self._input_values[i]
            names = self._input_names
        else:
            vtype = self._output_type[i]
            value = self._output_values[i]
            names = self._output_names
        if names is not None and i < len(names) and names[i]:
            shown = names[i]
        elif kind == "input":
            shown = "%s%d" % (vtype, i)
        else:
            shown = value if value else "未指定"
        current = self._display_name(value) if value else "（空）"
        opt = " | 可选" if (kind == "input" and self._input_optional[i]) else ""
        return shown, "类型: %s | 当前: %s%s" % (vtype, current, opt)

    def _apply_row_label(self, lbl: QLabel, kind: str, i: int) -> None:
        """把槽标签写到 QLabel：超宽省略（80px），tooltip 放完整信息。"""
        from PyQt5.QtCore import Qt
        from PyQt5.QtGui import QFontMetrics

        shown, tooltip = self._row_label(kind, i)
        fm = QFontMetrics(lbl.font())
        lbl.setText(fm.elidedText(shown, Qt.ElideRight, 80))
        lbl.setToolTip(tooltip)

    def _refresh_input_field(self, widget: QWidget, i: int) -> None:
        from PyQt5.QtWidgets import QLineEdit, QPushButton

        field = widget.input_fields[i]
        value = self._input_values[i]
        if isinstance(field, QLineEdit):
            field.blockSignals(True)
            field.setText(value)
            field.blockSignals(False)
        elif isinstance(field, QPushButton):
            fallback = ("（可选）选择变量…" if self._input_optional[i]
                        else "选择变量…")
            field.setText(self._display_name(value) or fallback)
        if len(widget.input_labels) > i:      # 标签随值变化同步（变量名/常量值）
            self._apply_row_label(widget.input_labels[i], "input", i)

    def _refresh_output_field(self, widget: QWidget, i: int) -> None:
        widget.output_fields[i].setText(self._output_values[i])
        if len(widget.output_labels) > i:
            self._apply_row_label(widget.output_labels[i], "output", i)

    # ================================================================
    # 槽位写入（统一入口：更新数据 + 同步已生成控件）
    # ================================================================
    def _set_input(self, i: int, value: str,
                   skip: Optional[QWidget] = None) -> None:
        self._input_values[i] = value
        for wd in self._live_widgets():
            if wd is skip:
                continue
            self._refresh_input_field(wd, i)
        self._notify_listeners()

    def _set_output(self, i: int, value: str,
                    skip: Optional[QWidget] = None) -> None:
        self._output_values[i] = value
        for wd in self._live_widgets():
            if wd is skip:
                continue
            self._refresh_output_field(wd, i)
        self._notify_listeners()

    def change_value(self, kind: str, index: int, value: str) -> None:
        """手动修改输入/输出槽位（程序化设置，同步刷新所有已生成控件）。

        ``kind`` 为 ``"input"`` 时 ``value`` 为字段串（常量或 ``{{变量名}}``）；
        ``kind`` 为 ``"output"`` 时 ``value`` 为变量名。
        """
        if kind == "input":
            if not 0 <= index < len(self._input_values):
                raise IndexError("输入索引越界: %d" % index)
            self._set_input(index, value)
        elif kind == "output":
            if not 0 <= index < len(self._output_values):
                raise IndexError("输出索引越界: %d" % index)
            self._set_output(index, value)
        else:
            raise ValueError("kind 必须是 'input' 或 'output'，而非 %r" % kind)

    # ================================================================
    # 变量选择器（内置极简 + 钩子）
    # ================================================================
    @property
    def picker(self) -> Callable[..., Optional[str]]:
        """变量选择器。默认内置极简选择器；可赋值替换为「树资源管理器」。

        签名：``picker(tree, vtype, parent) -> str|None``。
        """
        return self._picker or self._default_picker

    @picker.setter
    def picker(self, fn: Optional[Callable[..., Optional[str]]]) -> None:
        self._picker = fn

    def _pick_input(self, widget: QWidget, i: int) -> None:
        name = self.picker(self._tree, self._input_type[i], widget)
        if name is None:
            return
        # 整合选择器：资源类槽选中「包内图片路径」→ 常量直写；否则视为变量引用
        if self._type_is_resource(self._input_type[i]) \
                and self._package.exists(name):
            self._set_input(i, name)
        else:
            self._set_input(i, "{{%s}}" % name)  # 刷新所有控件（含触发的）

    def _pick_output(self, widget: QWidget, i: int, vtype: str) -> None:
        name = self.picker(self._tree, vtype, widget)
        if name is None:
            return
        self._set_output(i, name)

    @staticmethod
    def _picker_tree(tree: "VariableTree", vtype: str) -> "VariableTree":
        """选择器展示树：string 槽兼容 number（合并两类）；其余按类型筛选。"""
        if vtype == "string":
            return tree.filter_by_types("string", "number")
        return tree.filter_by_type(vtype)

    def _default_picker(self, tree: "VariableTree", vtype: str,
                        parent: QWidget) -> Optional[str]:
        """变量选择器：弹窗树形列表，按类型筛选，单选返回路径。

        * string 槽同时列出 string 与 number 变量（数字可作字符串用）。
        * 资源类槽（image）双页：变量页 + 资源页（包内图片，返回资源路径
          作常量，与「整合选择器」需求一致）。
        """
        from PyQt5.QtWidgets import (
            QDialog, QDialogButtonBox, QTabWidget, QTreeWidget, QVBoxLayout,
        )

        # 顶层窗口而非 parent：卡片在 QGraphicsView 场景（QGraphicsProxyWidget）中时，
        # 带 parent 的 QDialog 会被 proxy 内嵌渲染、被相邻卡片遮挡 → 弹到外面
        is_resource = self._type_is_resource(vtype)
        dlg = QDialog(None)
        dlg.setWindowTitle(("选择变量 / 资源（%s）" % vtype)
                           if is_resource else "选择变量（%s）" % (
                               "string / number" if vtype == "string" else vtype))
        dlg.resize(320, 400)
        lay = QVBoxLayout(dlg)

        var_tw = QTreeWidget()
        var_tw.setHeaderLabels(["变量", "类型"])   # 双列：名称 + 类型（picker 升级）
        var_tw.setColumnWidth(0, 180)
        sub = self._picker_tree(tree, vtype) if vtype else tree
        root_item = var_tw.invisibleRootItem()
        if root_item is not None:
            self._fill_tree(root_item, sub, "")
        var_tw.expandAll()                         # 分组默认展开，变量一目了然

        tabs = None
        res_tw = None                              # 资源页（挂对话框上供断言）
        if is_resource:
            tabs = QTabWidget()
            tabs.addTab(var_tw, "变量")
            res_tw = QTreeWidget()
            res_tw.setHeaderLabel("资源")
            res_root = res_tw.invisibleRootItem()
            if res_root is not None and self._package.is_dir("assets"):
                self._fill_resources(res_root, "assets")
            res_tw.expandAll()
            tabs.addTab(res_tw, "资源")
            dlg._res_tw = res_tw                   # 供冒烟断言
            lay.addWidget(tabs)
        else:
            lay.addWidget(var_tw)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        lay.addWidget(btns)
        chosen = {"path": None}

        def _active_tree():
            return (tabs.currentWidget() if tabs is not None else var_tw)

        def on_ok() -> None:
            item = _active_tree().currentItem()
            if item is not None:
                chosen["path"] = item.data(0, _USER_ROLE)  # 叶子存路径，分组为 None

        def on_double(item, _col) -> None:
            # 双击叶子 = 选中并确定（分组双击仅选中，不关闭）
            if item is not None and item.data(0, _USER_ROLE):
                chosen["path"] = item.data(0, _USER_ROLE)
                dlg.accept()

        for _tw in ((var_tw, res_tw) if res_tw is not None else (var_tw,)):
            _tw.itemDoubleClicked.connect(on_double)
        btns.accepted.connect(on_ok)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        dlg.exec_()
        return chosen["path"]

    def _fill_resources(self, parent_item: QTreeWidgetItem,
                        dir_path: str) -> None:
        """资源页树：目录递归，图片文件为叶子（UserRole=包内路径），其余文件不显示。"""
        from PyQt5.QtWidgets import QTreeWidgetItem

        for name in sorted(self._package.list_dir(dir_path)):
            path = dir_path + "/" + name
            if self._package.is_dir(path):
                item = QTreeWidgetItem(parent_item)
                item.setText(0, name)
                self._fill_resources(item, path)
            elif path.lower().endswith(_IMAGE_EXTS):
                item = QTreeWidgetItem(parent_item)
                item.setText(0, name)
                item.setData(0, _USER_ROLE, path)

    @staticmethod
    def _fill_tree(parent_item: QTreeWidgetItem, var_tree: "VariableTree",
                   prefix: str) -> None:
        """把变量树填进 QTreeWidget；叶子节点 data(0,UserRole)=路径。"""
        from PyQt5.QtWidgets import QTreeWidgetItem

        for name in var_tree.list_dir(prefix):
            path = name if not prefix else prefix + "/" + name
            item = QTreeWidgetItem(parent_item)
            item.setText(0, name)
            if var_tree.is_variable(path):
                item.setData(0, _USER_ROLE, path)
                item.setText(1, var_tree.get(path).type)   # 第二列 = 类型
            else:
                StepIOWidget._fill_tree(item, var_tree, path)  # 分组递归

    # ================================================================
    # 双下方法
    # ================================================================
    def __repr__(self) -> str:
        return "StepIOWidget(inputs=%d, outputs=%d, valid=%r)" % (
            len(self._input_type), len(self._output_type), self.is_valid)


# ================================================================
# 冒烟演示：直接 ``python -m model.step_io`` 运行
# ================================================================
if __name__ == "__main__":
    import base64 as _b64
    import json as _json
    import sys

    from PyQt5.QtWidgets import QApplication, QDialog, QWidget

    from model.kscp_package import KscpPackage
    from model.variable_tree import VariableTree

    app = QApplication.instance() or QApplication(sys.argv)

    # 工程资源 + 变量树
    pkg = KscpPackage.create_empty()
    pkg.write_file("assets/1.png", b"\x89PNG-demo")
    tree = VariableTree.create_empty()
    tree.add("n1", ProjectVariable.create("number", 100, pkg))
    tree.add("s1", ProjectVariable.create("string", "hello", pkg))
    tree.add("img/pic", ProjectVariable.create("image", "assets/1.png", pkg))

    # 无回调构造（回调已移除；输入→计算→输出由「步骤对象」内部编排）
    w = StepIOWidget(["number", "image", "string"], ["number"], tree, pkg)
    # 不继承 QWidget：是普通对象，未生成控件前即可设置/校验/解析
    assert not isinstance(w, QWidget)
    w.change_value("input", 0, "5")            # number 常量
    w.change_value("input", 1, "{{img/pic}}")  # image 引用
    w.change_value("input", 2, "{{s1}}")       # string 引用
    w.change_value("output", 0, "n1")          # 输出到 n1
    assert w.is_valid

    # 获取输入参数：按顺序返回输入变量的实际值
    resolved = w.resolve_inputs()
    assert resolved[0] == 5
    assert resolved[1] == b"\x89PNG-demo"
    assert resolved[2] == "hello"

    # 设置输出参数：输出变量全是工程变量，写回变量树
    w.write_outputs([6])
    assert tree.get("n1").data == 6            # 5+1 写回 n1
    assert tree.get("n1").valid

    # 输出变量不在树中 → FileNotFoundError
    w.change_value("output", 0, "nope")
    try:
        w.write_outputs([1])
        raise AssertionError("输出变量不在树中应抛 FileNotFoundError")
    except FileNotFoundError:
        pass
    w.change_value("output", 0, "n1")

    # 输出值不合规（number 槽写字符串）→ ValueError
    try:
        w.write_outputs(["abc"])
        raise AssertionError("输出值不合规应抛 ValueError")
    except ValueError:
        pass

    # 格式化自身：to_format_string 编码 base64（含槽类型与槽值）
    fmt = w.to_format_string()
    assert "=" not in fmt and "+" not in fmt and "/" not in fmt  # 去填充、urlsafe
    # 静态方法还原：from_format_string 返回自身
    w2 = StepIOWidget.from_format_string(fmt, tree, pkg)
    assert isinstance(w2, StepIOWidget)
    assert w2.is_valid == w.is_valid
    assert w2.resolve_inputs() == resolved
    assert w2.to_format_string() == fmt        # 规范化输出稳定
    # 还原后可继续使用（输出写回）
    w2.change_value("output", 0, "n1")
    w2.write_outputs([7])
    assert tree.get("n1").data == 7

    # 非法格式化串 → ValueError
    for bad in ("not*valid*", "###", ""):
        try:
            StepIOWidget.from_format_string(bad, tree, pkg)
            raise AssertionError("非法 base64 应抛 ValueError: %r" % bad)
        except ValueError:
            pass
    try:  # 合法 base64 但 JSON 结构缺字段
        StepIOWidget.from_format_string(
            _b64.urlsafe_b64encode(b'{"it":[],"iv":[]}').decode(), tree, pkg)
        raise AssertionError("结构缺字段应抛 ValueError")
    except ValueError:
        pass
    try:  # 槽类型与槽值数量不符
        StepIOWidget.from_format_string(
            _b64.urlsafe_b64encode(b'{"it":["number"],"iv":[],"ot":[],"ov":[]}')
            .decode(), tree, pkg)
        raise AssertionError("数量不符应抛 ValueError")
    except ValueError:
        pass
    # 槽值/槽类型元素非 str（手工编辑的 .kscp 含数字等）→ ValueError 而非崩溃
    for bad_obj in (
        {"it": ["number"], "iv": [5], "ot": [], "ov": []},          # iv 元素是数字
        {"it": [7], "iv": ["1"], "ot": [], "ov": []},               # it 元素是数字
        {"it": ["number"], "iv": ["1"], "ot": [], "ov": [None]},    # ov 元素是 null
    ):
        try:
            StepIOWidget.from_format_string(
                _b64.urlsafe_b64encode(
                    _json.dumps(bad_obj, ensure_ascii=False).encode("utf-8")
                ).decode(), tree, pkg)
            raise AssertionError("槽值/类型非 str 应抛 ValueError: %r" % bad_obj)
        except ValueError:
            pass

    # 还原出的对象引用不存在的变量 → 不抛错，is_valid 为 False
    tree2 = VariableTree.create_empty()
    w3 = StepIOWidget.from_format_string(fmt, tree2, pkg)
    assert not w3.is_valid

    # gen_widget：生成 QWidget，change_value 同步刷新字段
    card = w.gen_widget()
    assert isinstance(card, QWidget)
    # io 边距：左右 16 / 底部 16（控件不贴卡片边，参数多时滚动区观感）
    _m = card.layout().contentsMargins()
    assert (_m.left(), _m.top(), _m.right(), _m.bottom()) == (16, 6, 16, 16), \
        (_m.left(), _m.top(), _m.right(), _m.bottom())
    assert w.change_value("input", 0, "9") is None
    assert card.input_fields[0].text() == "9"   # number 槽是 QLineEdit
    # 多控件同步
    card2 = w.gen_widget()
    assert card2.input_fields[0].text() == "9"  # 新控件读取当前数据
    w.change_value("input", 0, "7")
    assert card.input_fields[0].text() == "7"
    assert card2.input_fields[0].text() == "7"

    # ---- IO 槽标签：参数名优先（Step 签名注入）；无名字回退 类型+序号 ----
    wl2 = StepIOWidget(["number", "string"], ["number"], tree, pkg)
    cl = wl2.gen_widget()
    assert cl.input_labels[0].text() == "number0"     # 无名字回退
    assert cl.input_labels[1].text() == "string1"
    assert cl.output_labels[0].text() == "未指定"
    assert "number" in cl.input_labels[0].toolTip()   # tooltip 恒含类型
    # 注入参数名 → 标签显示参数名；tooltip 含类型与当前值
    wl2.set_slot_names(["x", "y"], ["结果"])
    wl2.change_value("input", 0, "{{n1}}")
    assert cl.input_labels[0].text() == "x"
    assert "n1" in cl.input_labels[0].toolTip()       # 当前值进 tooltip
    wl2.change_value("input", 1, "hello")
    assert cl.input_labels[1].text() == "y"
    assert "hello" in cl.input_labels[1].toolTip()
    wl2.change_value("output", 0, "n1")
    assert cl.output_labels[0].text() == "结果"
    assert "n1" in cl.output_labels[0].toolTip()
    # 同步刷新：新控件标签读取参数名
    cl3 = wl2.gen_widget()
    assert cl3.input_labels[0].text() == "x"
    assert cl3.output_labels[0].text() == "结果"

    # 不合规：number 输入空
    w4 = StepIOWidget(["number"], [], tree, pkg)
    assert not w4.is_valid
    try:
        w4.resolve_inputs()
        raise AssertionError("不合规应抛错")
    except ValueError:
        pass

    # 不合规：引用不存在的变量；string 槽兼容 number（隐式转字符串）
    w5 = StepIOWidget(["string"], [], tree, pkg)
    w5.change_value("input", 0, "{{nope}}")
    assert not w5.is_valid
    w5.change_value("input", 0, "{{n1}}")     # n1 是 number，string 槽兼容 → 合法
    assert w5.is_valid
    assert w5.resolve_inputs()[0] == str(tree.get("n1").data)  # 隐式转字符串

    # 资源类常量 = 包内图片路径（整合选择器）；不存在/非图片扩展名 → 不合规
    w6 = StepIOWidget(["image"], [], tree, pkg)
    w6.change_value("input", 0, "assets/不存在.png")
    assert not w6.is_valid
    w6.change_value("input", 0, "assets/1.png")   # 包内图片常量 → 合规
    assert w6.is_valid
    assert w6.resolve_inputs()[0] == b"\x89PNG-demo"
    w6.change_value("input", 0, "assets/readme.txt")  # 非图片扩展名 → 不合规
    assert not w6.is_valid
    w6.change_value("input", 0, "{{img/pic}}")   # 引用 → 合规
    assert w6.is_valid

    # number 常量解析：int 与 float
    w7 = StepIOWidget(["number"], [], tree, pkg)
    w7.change_value("input", 0, "3.14")
    assert w7.is_valid and w7.resolve_inputs()[0] == 3.14
    w7.change_value("input", 0, "abc")        # 非数字 → 不合规
    assert not w7.is_valid

    # picker 钩子替换（不弹真实对话框）；经控件按钮触发
    picked = []

    def my_picker(t, vt, parent):
        picked.append(vt)
        return "n1"

    w8 = StepIOWidget(["number"], [], tree, pkg)
    w8.picker = my_picker
    c8 = w8.gen_widget()
    w8._pick_input(c8, 0)                     # 模拟点击「…」按钮
    assert picked == ["number"]
    assert w8._input_values[0] == "{{n1}}"
    assert c8.input_fields[0].text() == "{{n1}}"  # 控件字段已同步
    assert w8.is_valid  # n1 是 number，槽是 number

    # 输出值数量不符
    try:
        w.write_outputs([1, 2])  # w 只有 1 个输出槽
        raise AssertionError("输出数量不符应抛错")
    except ValueError:
        pass

    # ---- I-3：变量选择弹窗必须是顶层窗口（不被 QGraphicsProxyWidget 内嵌遮挡） ----
    # 卡片在 QGraphicsView 场景中时，QDialog(parent=卡片内控件) 会被 proxy 内嵌
    # 渲染、被相邻卡片遮挡 → 默认选择器必须用顶层窗口（无 parent），弹到外面
    _captured = []
    _orig_exec = QDialog.exec_
    QDialog.exec_ = lambda self: (_captured.append(self), QDialog.Accepted)[1]
    try:
        w9 = StepIOWidget(["number"], [], tree, pkg)
        c9 = w9.gen_widget()
        w9._default_picker(tree, "number", c9)
        assert len(_captured) == 1
        assert _captured[0].parent() is None   # 修复：顶层窗口，不被卡片遮挡
        # picker 升级：双列（名称/类型）+ 叶子第二列为变量类型
        from PyQt5.QtWidgets import QTreeWidget as _QTW
        _tw = _captured[0].findChild(_QTW)
        assert _tw is not None and _tw.columnCount() == 2
        assert _tw.topLevelItemCount() >= 1
        assert _tw.topLevelItem(0).text(1) == "number"
    finally:
        QDialog.exec_ = _orig_exec

    # ---- I-3b：整合选择器——image 槽弹窗含 变量/资源 双页；资源叶子=包内路径 ----
    from PyQt5.QtWidgets import QTabWidget as _QTB
    _cap2 = []
    QDialog.exec_ = lambda self: (_cap2.append(self), QDialog.Accepted)[1]
    try:
        w_img = StepIOWidget(["image"], [], tree, pkg)
        w_img._default_picker(tree, "image", None)
        assert len(_cap2) == 1
        _tabs = _cap2[0].findChild(_QTB)
        assert _tabs is not None and _tabs.count() == 2
        _res_tw = _cap2[0]._res_tw
        assert _res_tw is not None and _res_tw.topLevelItemCount() >= 1
        assert _res_tw.topLevelItem(0).data(0, _USER_ROLE) == "assets/1.png"
    finally:
        QDialog.exec_ = _orig_exec
    # _pick_input：资源类槽选中包内路径 → 常量直写；变量引用 → 加 {{}}
    w_img.picker = lambda t, vt, p: "assets/1.png"
    c_img = w_img.gen_widget()
    w_img._pick_input(c_img, 0)
    assert w_img.input_value(0) == "assets/1.png"
    w_img.picker = lambda t, vt, p: "img/pic"
    w_img._pick_input(c_img, 0)
    assert w_img.input_value(0) == "{{img/pic}}"

    # ---- K-1：error_reasons —— 卡片错误原因（卡片正下方提示用） ----
    # 全合规 → 空列表
    w10 = StepIOWidget(["number"], ["number"], tree, pkg)
    w10.change_value("input", 0, "5")
    w10.change_value("output", 0, "n1")
    assert w10.error_reasons() == []
    # 输入为空 + 输出未指定 → 两项依次列出
    w11 = StepIOWidget(["number"], ["number"], tree, pkg)
    assert w11.error_reasons() == ["输入参数为空", "输出变量未指定"]
    # 引用不存在的变量
    w12 = StepIOWidget(["number"], [], tree, pkg)
    w12.change_value("input", 0, "{{不存在}}")
    assert w12.error_reasons() == ["变量不存在: 不存在"]
    # 引用类型不符（s1 是 string，槽是 number）
    w13 = StepIOWidget(["number"], [], tree, pkg)
    w13.change_value("input", 0, "{{s1}}")
    assert w13.error_reasons() == ["s1 类型不符"]
    # string 槽兼容 number（隐式转字符串）→ 无错误
    w13b = StepIOWidget(["string"], [], tree, pkg)
    w13b.change_value("input", 0, "{{n1}}")
    assert w13b.error_reasons() == []
    # 常量无法解析（number 槽 "abc"）
    w14 = StepIOWidget(["number"], [], tree, pkg)
    w14.change_value("input", 0, "abc")
    assert w14.error_reasons() == ["无法解析为 number"]
    # 资源类常量：空 → 空提示；包内不存在 → 资源不存在
    w15 = StepIOWidget(["image"], [], tree, pkg)
    w15.change_value("input", 0, "")
    assert w15.error_reasons() == ["输入参数为空"]
    w15.change_value("input", 0, "assets/不存在.png")
    assert w15.error_reasons() == ["资源不存在: assets/不存在.png"]
    w15.change_value("input", 0, "assets/1.png")
    assert w15.error_reasons() == []
    # 输出变量不存在
    w16 = StepIOWidget([], ["number"], tree, pkg)
    w16.change_value("output", 0, "不存在")
    assert w16.error_reasons() == ["变量不存在: 不存在"]
    # 多原因顺序：输入在前、输出在后
    w17 = StepIOWidget(["number"], ["number"], tree, pkg)
    w17.change_value("input", 0, "{{不存在}}")
    assert w17.error_reasons() == ["变量不存在: 不存在", "输出变量未指定"]

    # ---- 可选输入槽：空值合法、解析 None、error_reasons 跳过（非必须参数机制） ----
    w21 = StepIOWidget(["number", "string"], [], tree, pkg)
    w21.set_optional_inputs([False, True])
    w21.change_value("input", 0, "5")
    assert w21.is_valid                  # 第二个槽可选且为空 → 合法
    assert w21.resolve_inputs() == [5, None]
    assert w21.error_reasons() == []
    w21.change_value("input", 1, "{{不存在}}")
    assert not w21.is_valid              # 可选槽一旦填了值仍须合规
    assert w21.error_reasons() == ["变量不存在: 不存在"]
    w21.change_value("input", 1, "")
    assert w21.is_valid

    # ---- 槽值变更监听 + 读取接口 ----
    # add_listener：change_value 与 GUI 编辑两路写入都通知；remove 后不通知
    events = []
    wl = StepIOWidget(["number"], ["number"], tree, pkg)
    wl.add_listener(lambda: events.append(1))
    wl.change_value("input", 0, "5")
    assert events == [1], events                 # change_value 路径
    cw = wl.gen_widget()
    cw.input_fields[0].setText("7")              # GUI 编辑路径（模拟用户输入）
    assert events == [1, 1], events
    cb2 = lambda: events.append(2)
    wl.add_listener(cb2)
    wl.change_value("input", 0, "3")
    assert events == [1, 1, 1, 2], events        # 多监听者依次通知
    wl.remove_listener(cb2)
    wl.change_value("input", 0, "4")
    assert events == [1, 1, 1, 2, 1], events
    # 监听者异常不中断写入
    def bad_cb():
        raise RuntimeError("boom")
    wl.add_listener(bad_cb)
    wl.change_value("input", 0, "6")             # 不抛
    assert wl.input_value(0) == "6"
    # 读取接口
    assert wl.input_value(0) == "6"
    assert wl.output_value(0) == ""
    for bad_i, fn in ((-1, lambda i: wl.input_value(i)),
                      (1, lambda i: wl.input_value(i))):
        try:
            fn(bad_i)
            raise AssertionError("越界应抛 IndexError")
        except IndexError:
            pass

    # ---- N-1：引用分组名/根路径：非法而非崩溃（{{组名}} 不得抛 FileNotFoundError） ----
    tree.add_group("组")
    w18 = StepIOWidget(["string"], [], tree, pkg)
    for ref in ("{{组}}", "{{组/}}", "{{/}}"):
        w18.change_value("input", 0, ref)
        assert not w18.is_valid, ref        # 修复前：is_valid 抛 FileNotFoundError/ValueError
        assert w18.error_reasons() == ["变量不存在: %s" % ref[2:-2]], ref
    # 输出槽指向分组名 → 非法（在 write_outputs 前拦截，防 set() 抛 ValueError）
    w19 = StepIOWidget([], ["number"], tree, pkg)
    w19.change_value("output", 0, "组")
    assert not w19.is_valid
    assert w19.error_reasons() == ["变量不存在: 组"]

    # ---- N-2：string 槽兼容 number 变量（隐式转字符串；选择器合并两类） ----
    tree.add("f1", ProjectVariable.create("number", 3.14, pkg))
    w20 = StepIOWidget(["string"], [], tree, pkg)
    w20.change_value("input", 0, "{{n1}}")
    assert w20.is_valid
    assert w20.resolve_inputs()[0] == str(tree.get("n1").data)  # int → str
    w20.change_value("input", 0, "{{f1}}")
    assert w20.resolve_inputs()[0] == "3.14"     # float → "3.14"
    w20.change_value("input", 0, "直接文本")
    assert w20.is_valid and w20.resolve_inputs()[0] == "直接文本"
    # 选择器树：string 槽合并 string+number；number 槽仍只列 number
    sub = StepIOWidget._picker_tree(tree, "string")
    assert sorted(sub.variables) == ["f1", "n1", "s1"], sub.variables
    sub_num = StepIOWidget._picker_tree(tree, "number")
    assert sorted(sub_num.variables) == ["f1", "n1"]

    print("StepIOWidget smoke OK")
