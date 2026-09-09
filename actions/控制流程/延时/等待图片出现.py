# -*- coding: utf-8 -*-
"""
等待图片出现步骤（控制流程/延时）
================================

:class:`WaitForImage`：在超时时间内反复全屏匹配「指定图片」，命中即返回其
中心屏幕坐标；超时未命中则返回失败（是否成功=0）。

输入槽
------
* ``指定图片``（image）：等待其出现的模板图。
* ``超时时间``（number，单位 s）：最长等待时长。

运行规则
--------
* 轮询：每 ``POLL_INTERVAL``（0.2s）做一次 :func:`libs.vision.image_match.find_template`
  全屏匹配；命中 → 输出中心坐标 + 是否成功=1，立即返回。
* 超时未命中 → 坐标x/坐标y=0，是否成功=0（不报错）。
* 轮询间隔用 :func:`interruptible_sleep` 睡眠——执行器「立即停止」时
  ~20ms 内打断并返回失败。
* 指定图片为空 / 模板无法解码 / 模板大于屏幕 / 超时时间 ≤ 0：抛
  :class:`ValueError`（由 do() 置「执行错误」停步）。

自定义视图
----------
* 复用 :class:`MarkPreviewView`（dot 模式）仅展示指定图片（看「等什么」）。
"""
from dataclasses import dataclass
from typing import Optional

from PyQt5.QtWidgets import QVBoxLayout, QWidget

from model.log_model import LogModel
from model.步骤.step import Step
from widgets.卡片.mark_preview_view import MarkPreviewView

__all__ = ["WaitForImage"]

# 轮询间隔（s）：命中检查的频率与 CPU 占用的折中
POLL_INTERVAL = 0.2


@dataclass
class WaitForImageInput:
    """输入：指定图片（image）+ 超时时间（number，s）。"""
    指定图片: "image" = ""  # type: ignore
    超时时间: "number" = 5.0  # type: ignore  # 默认 5s，避免 0.0 恒为错误态


@dataclass
class WaitForImageOutput:
    """输出：坐标x / 坐标y / 是否成功（number；1=命中 0=超时/被打断）。"""
    坐标x: "number" = 0  # type: ignore
    坐标y: "number" = 0  # type: ignore
    是否成功: "number" = 0  # type: ignore


class WaitForImage(Step):
    """等待图片出现步骤：超时内反复全屏匹配，命中返回中心坐标。"""

    name = "等待图片出现"
    description = "在超时时间内等待指定图片出现，返回其中心的屏幕坐标"
    input_class = WaitForImageInput
    output_class = WaitForImageOutput

    # 指定图片输入槽下标（自定义视图展示用）
    IMAGE_SLOT = 0

    def run(self) -> int:
        tpl = self.inputs.指定图片
        if not tpl:
            raise ValueError("等待图片出现：指定图片为空")
        timeout = self.inputs.超时时间
        if timeout <= 0:
            raise ValueError("等待图片出现：超时时间必须大于 0: %r" % timeout)
        try:
            from libs.vision.image_match import find_template
        except ImportError as e:
            raise ValueError("等待图片出现：图像匹配引擎未安装: %s" % e)
        # interruptible_sleep / is_stop_requested 经模块引用，冒烟可桩替换
        from model.执行.run_interrupt import interruptible_sleep, is_stop_requested
        import time
        deadline = time.monotonic() + float(timeout)
        while True:
            if is_stop_requested():
                break                      # 立即停止：未命中，输出失败
            try:
                found, center = find_template(bytes(tpl))     # screenshot=None → 全屏
            except FileNotFoundError as e:
                raise ValueError("等待图片出现：指定图片无法解码: %s" % e)
            except OSError as e:
                raise ValueError("等待图片出现：截图或匹配失败: %s" % e)
            except ValueError:
                raise                      # 模板大于屏幕 → 配置错误，置 ERROR
            if found and center is not None:
                self.outputs.坐标x = int(center[0])
                self.outputs.坐标y = int(center[1])
                self.outputs.是否成功 = 1
                LogModel.instance().info(
                    "等待图片出现：命中 (%d,%d)" % (center[0], center[1]))
                return 1
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break                       # 超时未命中
            # 轮询间隔可中断：执行器「立即停止」时被打断返回 True
            if interruptible_sleep(min(POLL_INTERVAL, remaining)):
                break                       # 被打断：未命中，输出失败
        self.outputs.坐标x = 0
        self.outputs.坐标y = 0
        self.outputs.是否成功 = 0
        LogModel.instance().info("等待图片出现：超时或被打断，未命中")
        return 1

    def info_widget(self, parent: Optional[QWidget] = None) -> QWidget:
        """自定义视图：仅展示指定图片（不标注）。"""
        return _WaitView(self, parent)


class _WaitView(QWidget):
    """等待图片出现步骤的自定义卡片视图（复用 :class:`MarkPreviewView`）。"""

    def __init__(self, step: "WaitForImage",
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._step = step
        self._mark_view = MarkPreviewView(
            io=step.io, image_slot=WaitForImage.IMAGE_SLOT, mode="dot",
            hint_text=WaitForImage.description
            + "\n下方预览仅展示等待出现的图片（不标注）；点击缩略图查看大图",
            read_points=lambda: None,           # 仅展示：原图，不合成标注
            write_points=lambda pos_info: None,  # 展示语义：不回写坐标
            mark_button="查看原图",
            parent=self)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self._mark_view)


# ================================================================
# 冒烟演示：直接 ``python -m actions.控制流程.延时.等待图片出现`` 运行
# ================================================================
if __name__ == "__main__":
    import sys
    import time

    from PIL import Image as _PILImage, ImageDraw as _IDraw
    from PyQt5.QtWidgets import QApplication

    from model.工程.kscp_package import KscpPackage
    from model.变量.project_variable import ProjectVariable
    from model.步骤.step import StepStatus
    from model.变量.variable_tree import VariableTree

    _mod = sys.modules[__name__]

    app = QApplication.instance() or QApplication(sys.argv)

    # 造一张非纯色模板（7×7，有图案，灰度有方差）
    _tpl = _PILImage.new("RGB", (7, 7), "white")
    _d = _IDraw.Draw(_tpl)
    _d.rectangle([0, 0, 6, 6], outline="black")
    _d.point((3, 3), fill="red")
    import io as _io
    _buf = _io.BytesIO()
    _tpl.save(_buf, "PNG")
    _tpl_png = _buf.getvalue()

    pkg = KscpPackage.create_empty()
    pkg.write_file("assets/tpl.png", _tpl_png)
    tree = VariableTree.create_empty()
    tree.add("tpl", ProjectVariable.create("image", "assets/tpl.png", pkg))
    tree.add("ox", ProjectVariable.create("number", 0, pkg))
    tree.add("oy", ProjectVariable.create("number", 0, pkg))
    tree.add("ok", ProjectVariable.create("number", 0, pkg))

    # create_default：槽类型推导
    w = WaitForImage.create_default(tree, pkg)
    assert w.io._input_type == ["image", "number"]
    assert w.io._output_type == ["number", "number", "number"]
    assert w.name == "等待图片出现"

    # 输入绑定 tpl + 超时、输出绑定 ox/oy/ok
    w.io.change_value("input", 0, "{{tpl}}")
    w.io.change_value("input", 1, "5")
    w.io.change_value("output", 0, "ox")
    w.io.change_value("output", 1, "oy")
    w.io.change_value("output", 2, "ok")

    # 桩替换 find_template（冒烟不真实截屏/匹配）+ interruptible_sleep（不等真实时间）
    import libs.vision.image_match as _im
    import model.执行.run_interrupt as _ri
    _orig_find = _im.find_template
    _orig_sleep = _ri.interruptible_sleep     # run 内 from ... import 取本模块属性
    _sleep_calls = []

    def _fake_sleep(seconds, poll=0.02):
        _sleep_calls.append(seconds)
        return False                        # 未被打断

    _ri.interruptible_sleep = _fake_sleep

    # 立即命中：find_template 首次返回 True
    _im.find_template = lambda tpl, screenshot=None, threshold=0.8: (True, (30, 40))
    _sleep_calls.clear()
    try:
        assert w.do() == 1
        assert w.status is StepStatus.FINISHED
        assert tree.get("ox").get_actual_data() == 30
        assert tree.get("oy").get_actual_data() == 40
        assert tree.get("ok").get_actual_data() == 1
        assert _sleep_calls == []          # 命中即返回，未睡眠
    finally:
        _im.find_template = _orig_find
    _ri.interruptible_sleep = _orig_sleep

    # 二次轮询后命中：首次 False、第二次 True → 中间睡眠一次
    _calls = {"n": 0}

    def _find_late(tpl, screenshot=None, threshold=0.8):
        _calls["n"] += 1
        return (True, (5, 6)) if _calls["n"] >= 2 else (False, None)

    _im.find_template = _find_late
    _ri.interruptible_sleep = _fake_sleep
    _sleep_calls.clear()
    try:
        assert w.do() == 1
        assert w.status is StepStatus.FINISHED
        assert tree.get("ox").get_actual_data() == 5
        assert tree.get("oy").get_actual_data() == 6
        assert tree.get("ok").get_actual_data() == 1
        assert len(_sleep_calls) >= 1       # 首次未命中 → 睡过一轮询间隔
    finally:
        _im.find_template = _orig_find
        _ri.interruptible_sleep = _orig_sleep

    # 超时未命中：find_template 恒 False；超时 0.1s → 轮询后超时退出
    _im.find_template = lambda tpl, screenshot=None, threshold=0.8: (False, None)
    _ri.interruptible_sleep = _fake_sleep
    w.io.change_value("input", 1, "0.1")
    _t0 = time.monotonic()
    try:
        assert w.do() == 1
        assert w.status is StepStatus.FINISHED
        assert tree.get("ok").get_actual_data() == 0    # 超时失败
        assert tree.get("ox").get_actual_data() == 0
        assert tree.get("oy").get_actual_data() == 0
        assert time.monotonic() - _t0 < 2.0             # 远小于 5s（超时控制）
    finally:
        _im.find_template = _orig_find
        _ri.interruptible_sleep = _orig_sleep
    w.io.change_value("input", 1, "5")    # 复位

    # 被立即停止打断：interruptible_sleep 返回 True → 失败退出
    _im.find_template = lambda tpl, screenshot=None, threshold=0.8: (False, None)
    _ri.interruptible_sleep = lambda seconds, poll=0.02: True   # 模拟被立即停止打断
    try:
        assert w.do() == 1
        assert w.status is StepStatus.FINISHED
        assert tree.get("ok").get_actual_data() == 0    # 被打断 → 失败
    finally:
        _im.find_template = _orig_find
        _ri.interruptible_sleep = _orig_sleep

    # 超时时间 ≤ 0 → ERROR 停步
    LogModel.instance().clear()
    w.io.change_value("input", 1, "0")
    try:
        w.do()
        raise AssertionError("超时≤0 应抛 ValueError 停步")
    except ValueError:
        pass
    assert w.status is StepStatus.ERROR
    assert any("超时时间必须大于 0" in e.message for e in LogModel.instance().entries)
    w.io.change_value("input", 1, "5")    # 复位

    # 模板大于屏幕（ValueError）→ ERROR 停步
    LogModel.instance().clear()

    def _raise_too_big(tpl, screenshot=None, threshold=0.8):
        raise ValueError("模板尺寸 100x100 大于截图尺寸 40x30")

    _im.find_template = _raise_too_big
    try:
        w.do()
        raise AssertionError("模板过大应抛 ValueError 停步")
    except ValueError:
        pass
    finally:
        _im.find_template = _orig_find
    assert w.status is StepStatus.ERROR
    assert any("等待图片出现" in e.message for e in LogModel.instance().entries)

    # ---- info_widget：提示 + 预览（仅展示指定图片） ----
    w2 = WaitForImage.create_default(tree, pkg)
    w2.io.change_value("input", 0, "{{tpl}}")
    view = w2.info_widget()
    assert view is not None
    from PyQt5.QtWidgets import QLabel, QPushButton
    labels = view.findChildren(QLabel)
    btns = view.findChildren(QPushButton)
    assert any("查看原图" in b.text() for b in btns)
    assert any("查看大图" in l.text() for l in labels)
    assert not view._mark_view.preview_pixmap().isNull()   # 有素材 → 非占位

    # 往返
    fmt = w.to_format_string()
    assert "=" not in fmt and "+" not in fmt and "/" not in fmt
    w3 = WaitForImage.from_format_string(fmt, tree, pkg)
    assert isinstance(w3, WaitForImage)
    assert w3.io.to_format_string() == w.io.to_format_string()

    print("WaitForImage smoke OK")
