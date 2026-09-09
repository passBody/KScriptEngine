# -*- coding: utf-8 -*-
"""
文字识别步骤（显示）
========================

:class:`TextRecognize`：识别输入图片中的文字，输出为 string 变量。

输入槽
------
* ``待识别图片``（image）：被识别的源图。

运行规则
--------
* 读源图字节 → :func:`libs.vision.ocr.read_text` → 识别文字（多块按识别顺序
  用换行拼接）→ 写回 string 输出变量。
* 引擎未安装 / 图片解码失败：抛 :class:`ValueError`（由 do() 置 ERROR 停步）。

自定义视图
----------
* 复用 :class:`MarkPreviewView` 仅展示源图（``show`` 模式语义——只看图不标注），
  故 ``read_points`` 恒返回 None（预览显示原图）、``write_points`` 为 no-op。
"""
from dataclasses import dataclass
from typing import List, Optional, Tuple

from PyQt5.QtWidgets import QVBoxLayout, QWidget

from model.执行.point_timeline import PointTimeline
from model.log_model import LogModel
from model.步骤.step import Step
from widgets.卡片.mark_preview_view import MarkPreviewView

__all__ = ["TextRecognize"]


@dataclass
class TextRecognizeInput:
    """输入：待识别图片（image）。"""
    待识别图片: "image" = ""  # type: ignore


@dataclass
class TextRecognizeOutput:
    """输出：识别文字（string）。"""
    识别文字: "string" = ""  # type: ignore


class TextRecognize(Step):
    """文字识别步骤：识别输入图片中的文字。"""

    name = "文字识别"
    description = "识别输入图片中的文字并输出为字符串变量"
    input_class = TextRecognizeInput
    output_class = TextRecognizeOutput

    # 待识别图片输入槽下标（自定义视图展示用）
    IMAGE_SLOT = 0

    def run(self) -> int:
        data = self.inputs.待识别图片
        if not data:
            raise ValueError("文字识别：待识别图片为空")
        try:
            from libs.vision.ocr import read_text
        except ImportError as e:
            raise ValueError(
                "文字识别：OCR 引擎未安装（缺少 rapidocr_onnxruntime）: %s" % e)
        try:
            text = read_text(_BytesIO(data))
        except FileNotFoundError as e:
            raise ValueError("文字识别：图片无法解码或识别失败: %s" % e)
        except (ImportError, OSError) as e:
            raise ValueError("文字识别：OCR 引擎运行失败: %s" % e)
        self.outputs.识别文字 = text or ""
        LogModel.instance().info("文字识别完成: %d 字" % len(text or ""))
        return 1

    def info_widget(self, parent: Optional[QWidget] = None) -> QWidget:
        """自定义视图：仅展示源图（不标注）。"""
        return _TextView(self, parent)


class _TextView(QWidget):
    """文字识别步骤的自定义卡片视图（仅展示，复用 :class:`MarkPreviewView`）。

    read_points 恒返回 None → 预览只显示原图、不加遮罩/标注；
    write_points 为 no-op → 「设置点位」按钮按下后不回写（展示语义）。
    """

    def __init__(self, step: "TextRecognize", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._step = step
        self._mark_view = MarkPreviewView(
            io=step.io, image_slot=TextRecognize.IMAGE_SLOT, mode="dot",
            hint_text=TextRecognize.description + "\n下方预览仅展示待识别图片（不标注）；点击缩略图查看大图",
            read_points=lambda: None,           # 仅展示：原图，不合成标注
            write_points=lambda pos_info: None,  # 展示语义：不回写坐标
            mark_button="查看原图",
            parent=self)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self._mark_view)


# BytesIO 在模块顶层导入一次，避免 run() 内重复 import 开销
import io as _io
_BytesIO = _io.BytesIO


# ================================================================
# 冒烟演示：直接 ``python -m actions.显示.文字识别`` 运行
# ================================================================
if __name__ == "__main__":
    import sys

    from PyQt5.QtCore import QBuffer, QIODevice
    from PyQt5.QtGui import QImage
    from PyQt5.QtWidgets import QApplication

    from model.工程.kscp_package import KscpPackage
    from model.变量.project_variable import ProjectVariable
    from model.步骤.step import StepStatus
    from model.变量.variable_tree import VariableTree

    _mod = sys.modules[__name__]

    app = QApplication.instance() or QApplication(sys.argv)

    # 造一张占位 PNG 写入包内供识别（OCR 引擎桩替换，不真实识别）
    _src = QImage(4, 4, QImage.Format_RGB32)
    _src.fill(0xFFFFFFFF)
    _b = QBuffer()
    _b.open(QIODevice.ReadWrite)
    _src.save(_b, "PNG")
    _src_png = bytes(_b.data())

    pkg = KscpPackage.create_empty()
    pkg.write_file("assets/src.png", _src_png)
    tree = VariableTree.create_empty()
    tree.add("src", ProjectVariable.create("image", "assets/src.png", pkg))
    tree.add("txt", ProjectVariable.create("string", "", pkg))

    # create_default：槽类型推导
    t = TextRecognize.create_default(tree, pkg)
    assert t.io._input_type == ["image"]
    assert t.io._output_type == ["string"]
    assert t.name == "文字识别"

    # 输入绑定源图、输出绑定 txt
    t.io.change_value("input", 0, "{{src}}")
    t.io.change_value("output", 0, "txt")

    # run 用桩替换 OCR 引擎（冒烟不真实识别，保证可复现）
    import libs.vision.ocr as _ocr
    _orig_read = _ocr.read_text
    _ocr.read_text = lambda img: "识别结果\n第二行"
    try:
        assert t.do() == 1
        assert t.status is StepStatus.FINISHED
        assert tree.get("txt").data == "识别结果\n第二行"
    finally:
        _ocr.read_text = _orig_read

    # 空识别结果 → 输出空串（不报错）
    _ocr.read_text = lambda img: ""
    try:
        assert t.do() == 1
        assert tree.get("txt").data == ""
    finally:
        _ocr.read_text = _orig_read

    # 引擎未安装：read_text 抛 ImportError → do() 置 ERROR 停步
    LogModel.instance().clear()

    def _no_engine(img):
        raise ImportError("no rapidocr")

    _ocr.read_text = _no_engine
    try:
        t.do()
        raise AssertionError("引擎缺失应抛 ValueError 停步")
    except ValueError:
        pass
    finally:
        _ocr.read_text = _orig_read
    assert t.status is StepStatus.ERROR
    assert any("文字识别" in e.message for e in LogModel.instance().entries)

    # 待识别图片为空 → ERROR 停步
    LogModel.instance().clear()
    t2 = TextRecognize.create_default(tree, pkg)
    t2.io.change_value("output", 0, "txt")
    try:
        t2.do()
        raise AssertionError("空图片应抛 ValueError 停步")
    except ValueError:
        pass
    assert t2.status is StepStatus.ERROR

    # ---- info_widget：提示 + 预览（仅展示，不标注） ----
    t3 = TextRecognize.create_default(tree, pkg)
    t3.io.change_value("input", 0, "{{src}}")
    view = t3.info_widget()
    assert view is not None
    from PyQt5.QtWidgets import QLabel, QPushButton
    labels = view.findChildren(QLabel)
    btns = view.findChildren(QPushButton)
    assert any("查看原图" in b.text() for b in btns)
    assert any("查看大图" in l.text() for l in labels)
    assert not view._mark_view.preview_pixmap().isNull()   # 有素材 → 非占位

    # 往返
    fmt = t.to_format_string()
    assert "=" not in fmt and "+" not in fmt and "/" not in fmt
    t4 = TextRecognize.from_format_string(fmt, tree, pkg)
    assert isinstance(t4, TextRecognize)
    assert t4.io.to_format_string() == t.io.to_format_string()

    print("TextRecognize smoke OK")
