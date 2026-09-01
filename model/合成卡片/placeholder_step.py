# -*- coding: utf-8 -*-
"""
无法还原的步骤占位（红色卡片）
================================

:class:`PlaceholderStep` 在工程加载时为「无法还原的步骤」兜底：当某条步骤格式串
的模板缺失、签名不匹配或编码损坏时，**不报错退出**，而是用本类占位：

* :meth:`to_format_string` **原样返回保存的格式串** → 槽位数据不丢失（内存序列
  不变）；模板修复后**重新加载工程**即可还原该条（见 :meth:`StepList._decode_one`）。
* :meth:`info_widget` 红色显示「无法还原」+ 原步骤名 + **失败原因**。
* :meth:`run` 跳过（记日志、置 ERROR、返回 1），不阻断整体执行。

本类继承 :class:`model.步骤.step.Step`，故可像普通步骤一样被卡片视图渲染、序列化、
由执行器调度；区别仅在 ``to_format_string`` 原样回吐（不经 StepManager 注册表匹配，
故永不为解码候选）。无输入/输出槽（空 ``_NoIO`` 签名）。

本模块属 model 层：**模块顶层不导入 PyQt5**（Qt 控件仅在 :meth:`info_widget`
内延迟导入），因此导入本模块不依赖 GUI 环境。
"""
import base64
import json
from dataclasses import dataclass
from typing import Optional, TYPE_CHECKING

from model.log_model import LogModel
from model.步骤.step import Step, StepStatus
from model.步骤.step_io import StepIOWidget

if TYPE_CHECKING:
    from PyQt5.QtWidgets import QWidget
    from model.工程.kscp_package import KscpPackage
    from model.变量.variable_tree import VariableTree

__all__ = ["PlaceholderStep"]

# 合成卡片引用标记前缀（与 model.合成卡片.composite_card 一致；用于 _extract_name 识别）
_MARKER_PREFIX = "@合成卡片:"


@dataclass
class _NoIO:
    """占位步骤无输入/输出槽的空 dataclass（使继承的 input()/output() 成为 no-op）。

    基类 :meth:`Step.input`/`output` 直接调 ``dataclasses.fields(input_class)``
    （非 ``_safe_fields``），故 ``object`` 哨兵会在 ``do()`` 时抛 TypeError；
    占位步骤需被 ``do()`` 调度（跳过），故用空 dataclass（``fields()`` 得 [] → no-op）。
    """
    pass


class PlaceholderStep(Step):
    """无法还原的步骤占位：红色卡片、保留原格式串、运行时跳过。

    由 :meth:`StepList._decode_one` 在解码失败时构造（``reason`` 描述失败原因，
    显示于卡片）。不在 :class:`StepManager` 注册表中登记，故永不为解码候选——
    其 ``to_format_string`` 原样回吐保存的格式串，下次加载仍走 :meth:`_decode_one`
    重试：模板已修复 → 还原为真实步骤；仍未修复 → 再次占位（稳定，不丢失数据）。
    """

    name = "（无法还原）"
    description = "步骤模板缺失或签名不匹配，无法还原"
    input_class = _NoIO        # 空签名：input()/output() 经 fields() 得 [] → no-op
    output_class = _NoIO

    def __init__(self, fmt: str, tree: "VariableTree",
                 package: "KscpPackage", reason: str = "",
                 enabled: bool = True, tag: str = "") -> None:
        io = StepIOWidget([], [], tree, package)   # 空签名 io（input/output 均 no-op）
        super().__init__(io, enabled, tag)
        self._broken_fmt = fmt            # 原始格式串（序列化时原样回吐 → 槽位不丢失）
        self._reason = reason or "未知原因"
        self._orig_name = self._extract_name(fmt)
        # 实例名 = 原步骤名（可识别）+ 占位标识；覆盖类级「（无法还原）」。
        # 不影响序列化：to_format_string 用 self._broken_fmt，不经 StepManager 名称匹配。
        self.name = ("（无法还原）%s" % self._orig_name) \
            if self._orig_name else "（无法还原）"
        # 占位即「执行错误」态：卡片 state=error → 红边框（见 view/cards.qss）
        self._status = StepStatus.ERROR

    # ================================================================
    # 信息显示（红色卡片，写明失败原因）
    # ================================================================
    def info_widget(self, parent: Optional["QWidget"] = None) -> "QWidget":
        from PyQt5.QtWidgets import QLabel

        text = "⚠ 无法还原的步骤\n原步骤：%s\n原因：%s" % (
            self._orig_name or "（未知）", self._reason)
        lbl = QLabel(text, parent)
        lbl.setWordWrap(True)
        lbl.setStyleSheet(
            "color: #b00; background: #fff0f0; border: 1px solid #e6b3b3;"
            " border-radius: 4px; padding: 6px;")
        return lbl

    # ================================================================
    # 序列化：原样回吐保存的格式串（槽位数据不丢失）
    # ================================================================
    def to_format_string(self) -> str:
        """原样返回加载时保存的格式串（非重编码）→ 槽位数据不丢失。

        故模板修复后**重新加载工程**即可还原该条（:meth:`StepList._decode_one`
        重试匹配）；编辑本占位卡片的标签等不改变此串（占位不可编辑复原，须删后重加）。
        """
        return self._broken_fmt

    @staticmethod
    def _extract_name(fmt: str) -> str:
        """从格式串解出原步骤名（仅卡片显示用；解析失败 → 空串）。

        合成卡片引用标记 → ``合成卡片→<ref>``；普通步骤 → base64 内 ``name`` 字段。
        """
        if isinstance(fmt, str) and fmt.startswith(_MARKER_PREFIX):
            ref = fmt[len(_MARKER_PREFIX):]
            return ("合成卡片→%s" % ref) if ref else "合成卡片（空引用）"
        if not isinstance(fmt, str) or not fmt:
            return ""
        try:
            pad = "=" * (-len(fmt) % 4)
            obj = json.loads(base64.urlsafe_b64decode(fmt + pad).decode("utf-8"))
            n = obj.get("name")
            return n if isinstance(n, str) and n else ""
        except Exception:
            return ""

    # ================================================================
    # 运行时：跳过（不阻断整体执行）
    # ================================================================
    def run(self) -> int:
        """跳过无法还原的步骤：记日志、置 ERROR、返回 1（外层前进到下一步）。

        手动置 ``ERROR``（同 :meth:`model.步骤.step.Step.do` 文档「run() 可手动置
        ERROR，do() 不覆盖」）——否则 do() 末尾会把 RUNNING 覆盖为 FINISHED，
        占位卡失去「执行错误」红态。不抛异常（占位无逻辑可执行），不阻断整体运行。
        """
        LogModel.instance().error(
            "跳过无法还原的步骤（%s）：%s" % (self._reason, self._orig_name or "未知"))
        self.status = StepStatus.ERROR
        return 1


# ================================================================
# 冒烟演示：直接 ``python -m model.合成卡片.placeholder_step`` 运行
# ================================================================
if __name__ == "__main__":
    import sys

    from PyQt5.QtWidgets import QApplication, QLabel

    from model.工程.kscp_package import KscpPackage
    from model.log_model import LogModel
    from model.变量.variable_tree import VariableTree

    app = QApplication.instance() or QApplication(sys.argv)

    pkg = KscpPackage.create_empty()
    tree = VariableTree.create_empty()

    # ---- 构造：坏格式串 + 失败原因 ----
    import base64 as _b64
    import json as _json
    good_fmt = _b64.urlsafe_b64encode(_json.dumps({
        "name": "设置数字变量", "in": [["数字", "string"]],
        "out": [["数字变量", "string"]], "io": "e30", "run": False, "tag": "",
    }, ensure_ascii=False).encode()).decode().rstrip("=")
    p = PlaceholderStep(good_fmt, tree, pkg, reason="没有可匹配的模板（签名不匹配）")
    # 实例名带原步骤名；to_format_string 原样回吐；空签名 io
    assert "设置数字变量" in p.name and "无法还原" in p.name, p.name
    assert p.to_format_string() == good_fmt            # 原样回吐 → 槽位不丢失
    assert p.io.input_types == [] and p.io.output_types == []
    assert p.io.is_valid                               # 空 io 恒合规
    assert p.status is StepStatus.ERROR                # 占位即 ERROR 态
    assert p._orig_name == "设置数字变量"              # 从格式串解出原名
    assert p._reason == "没有可匹配的模板（签名不匹配）"

    # ---- info_widget：红色 QLabel，含原步骤名 + 失败原因 ----
    w = p.info_widget()
    assert isinstance(w, QLabel)
    txt = w.text()
    assert "无法还原" in txt and "设置数字变量" in txt \
        and "没有可匹配的模板" in txt, txt
    assert "red" in w.styleSheet() or "#b00" in w.styleSheet()  # 红色

    # ---- run：跳过、记 ERROR 日志、返回 1、状态保持 ERROR ----
    LogModel.instance().clear()
    assert p.do() == 1
    assert p.status is StepStatus.ERROR
    assert any("跳过无法还原的步骤" in e.message and "设置数字变量" in e.message
               for e in LogModel.instance().entries)

    # ---- _extract_name：合成卡片标记 / 非法串 / 空 ----
    assert PlaceholderStep._extract_name("@合成卡片:组/卡片A") == "合成卡片→组/卡片A"
    assert PlaceholderStep._extract_name("@合成卡片:") == "合成卡片（空引用）"
    assert PlaceholderStep._extract_name("not*valid*") == ""   # 非法 base64 → 空
    assert PlaceholderStep._extract_name("") == ""

    # ---- 往返稳定：占位序列化 → 再加载仍占位（原串不变）----
    assert PlaceholderStep(good_fmt, tree, pkg, "x").to_format_string() == good_fmt

    print("PlaceholderStep smoke OK")
