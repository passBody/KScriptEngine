# -*- coding: utf-8 -*-
"""
图片匹配步骤（显示/匹配）
========================

:class:`ImageMatch`：在「给定图片」中匹配「匹配图片」，返回其中心在给定图片
中的坐标与是否成功。

输入槽
------
* ``给定图片``（image）：被搜索的画面（haystack）。
* ``匹配图片``（image）：要查找的模板（needle）。

运行规则
--------
* 用 :func:`libs.vision.image_match.find_template`（``screenshot=给定图片``）做
  模板匹配——返回的坐标是**模板在给定图片中的中心位置**（非屏幕坐标）。
* 命中：输出 坐标x/坐标y = 模板中心在给定图片中的坐标，是否成功 = 1。
* 未命中：坐标x/坐标y = 0，是否成功 = 0（不报错，用是否成功=0 表达）。
* 任一图片为空 / 模板无法解码 / 模板大于给定图片：抛 :class:`ValueError`
  （由 do() 置「执行错误」停步）。

自定义视图
----------
* 复用 :class:`MarkPreviewView`（dot 模式）展示给定图片（看「在哪找」）。
"""
from dataclasses import dataclass
from typing import Optional

from PyQt5.QtWidgets import QVBoxLayout, QWidget

from model.log_model import LogModel
from model.步骤.step import Step
from widgets.卡片.mark_preview_view import MarkPreviewView

__all__ = ["ImageMatch"]


@dataclass
class ImageMatchInput:
    """输入：给定图片（haystack）+ 匹配图片（needle）。"""
    给定图片: "image" = ""  # type: ignore
    匹配图片: "image" = ""  # type: ignore


@dataclass
class ImageMatchOutput:
    """输出：坐标x / 坐标y / 是否成功（number；1=成功 0=失败）。"""
    坐标x: "number" = 0  # type: ignore
    坐标y: "number" = 0  # type: ignore
    是否成功: "number" = 0  # type: ignore


class ImageMatch(Step):
    """图片匹配步骤：在给定图片中匹配模板，返回其中心的图内坐标。"""

    name = "图片匹配"
    description = "在给定图片中匹配模板图片，返回其中心在该图中的坐标"
    input_class = ImageMatchInput
    output_class = ImageMatchOutput

    # 给定图片输入槽下标（自定义视图展示用——看「在哪找」）
    IMAGE_SLOT = 0

    def run(self) -> int:
        haystack = self.inputs.给定图片
        needle = self.inputs.匹配图片
        if not haystack:
            raise ValueError("图片匹配：给定图片为空")
        if not needle:
            raise ValueError("图片匹配：匹配图片为空")
        try:
            from libs.vision.image_match import find_template
        except ImportError as e:
            raise ValueError("图片匹配：图像匹配引擎未安装: %s" % e)
        try:
            found, center = find_template(bytes(needle),
                                          screenshot=bytes(haystack))
        except FileNotFoundError as e:
            raise ValueError("图片匹配：图片无法解码: %s" % e)
        except OSError as e:
            raise ValueError("图片匹配：匹配失败: %s" % e)
        except ValueError:
            raise                              # 模板大于给定图 → 配置错误，置 ERROR
        if found and center is not None:
            self.outputs.坐标x = int(center[0])
            self.outputs.坐标y = int(center[1])
            self.outputs.是否成功 = 1
            LogModel.instance().info(
                "图片匹配命中: (%d,%d)" % (center[0], center[1]))
        else:
            self.outputs.坐标x = 0
            self.outputs.坐标y = 0
            self.outputs.是否成功 = 0
            LogModel.instance().info("图片匹配未命中")
        return 1

    def info_widget(self, parent: Optional[QWidget] = None) -> QWidget:
        """自定义视图：仅展示给定图片（不标注）。"""
        return _MatchView(self, parent)


class _MatchView(QWidget):
    """图片匹配步骤的自定义卡片视图（复用 :class:`MarkPreviewView`，仅展示）。"""

    def __init__(self, step: "ImageMatch",
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._step = step
        self._mark_view = MarkPreviewView(
            io=step.io, image_slot=ImageMatch.IMAGE_SLOT, mode="dot",
            hint_text=ImageMatch.description
            + "\n下方预览仅展示给定图片（不标注）；点击缩略图查看大图",
            read_points=lambda: None,           # 仅展示：原图，不合成标注
            write_points=lambda pos_info: None,  # 展示语义：不回写坐标
            mark_button="查看原图",
            parent=self)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self._mark_view)


# ================================================================
# 冒烟演示：直接 ``python -m actions.显示.匹配.图片匹配`` 运行
# ================================================================
if __name__ == "__main__":
    import io as _io
    import sys

    from PIL import Image as _PILImage, ImageDraw as _IDraw
    from PyQt5.QtWidgets import QApplication

    from model.工程.kscp_package import KscpPackage
    from model.变量.project_variable import ProjectVariable
    from model.步骤.step import StepStatus
    from model.变量.variable_tree import VariableTree

    _mod = sys.modules[__name__]

    app = QApplication.instance() or QApplication(sys.argv)

    # 造一张「给定图片」：白底 + 左上有图案的小图标（非纯色，灰度有方差）
    _given = _PILImage.new("RGB", (40, 30), "white")
    _d = _IDraw.Draw(_given)
    _d.rectangle([10, 8, 16, 14], outline="black")
    _d.point((12, 11), fill="red")
    _d.point((14, 13), fill="blue")
    _buf = _io.BytesIO()
    _given.save(_buf, "PNG")
    _given_png = _buf.getvalue()
    # 模板 = 该图标的 7×7 裁剪
    _tpl = _given.crop((10, 8, 17, 15))
    _buf2 = _io.BytesIO()
    _tpl.save(_buf2, "PNG")
    _tpl_png = _buf2.getvalue()

    pkg = KscpPackage.create_empty()
    pkg.write_file("assets/given.png", _given_png)
    pkg.write_file("assets/tpl.png", _tpl_png)
    tree = VariableTree.create_empty()
    tree.add("given", ProjectVariable.create("image", "assets/given.png", pkg))
    tree.add("tpl", ProjectVariable.create("image", "assets/tpl.png", pkg))
    tree.add("ox", ProjectVariable.create("number", 0, pkg))
    tree.add("oy", ProjectVariable.create("number", 0, pkg))
    tree.add("ok", ProjectVariable.create("number", 0, pkg))

    # create_default：槽类型推导
    m = ImageMatch.create_default(tree, pkg)
    assert m.io._input_type == ["image", "image"]
    assert m.io._output_type == ["number", "number", "number"]
    assert m.name == "图片匹配"

    # 输入绑定 given/tpl、输出绑定 ox/oy/ok
    m.io.change_value("input", 0, "{{given}}")
    m.io.change_value("input", 1, "{{tpl}}")
    m.io.change_value("output", 0, "ox")
    m.io.change_value("output", 1, "oy")
    m.io.change_value("output", 2, "ok")

    # 桩替换 find_template（冒烟不真实匹配，保证可复现）
    import libs.vision.image_match as _im
    _orig = _im.find_template
    _calls = []
    _im.find_template = lambda tpl, screenshot=None, threshold=0.8: (
        _calls.append((bytes(tpl)[:8], bytes(screenshot)[:8])) or (True, (13, 11)))
    try:
        assert m.do() == 1
        assert m.status is StepStatus.FINISHED
        assert tree.get("ox").get_actual_data() == 13
        assert tree.get("oy").get_actual_data() == 11
        assert tree.get("ok").get_actual_data() == 1
        # 模板与给定图都按字节传入（PNG 头一致）
        assert _calls[0][0] == _tpl_png[:8] and _calls[0][1] == _given_png[:8]
    finally:
        _im.find_template = _orig

    # 未命中：是否成功=0，坐标 0，不报错
    _im.find_template = lambda tpl, screenshot=None, threshold=0.8: (False, None)
    try:
        assert m.do() == 1
        assert m.status is StepStatus.FINISHED
        assert tree.get("ox").get_actual_data() == 0
        assert tree.get("oy").get_actual_data() == 0
        assert tree.get("ok").get_actual_data() == 0
    finally:
        _im.find_template = _orig

    # 模板大于给定图（ValueError）→ ERROR 停步
    LogModel.instance().clear()

    def _raise_too_big(tpl, screenshot=None, threshold=0.8):
        raise ValueError("模板尺寸 100x100 大于截图尺寸 40x30")

    _im.find_template = _raise_too_big
    try:
        m.do()
        raise AssertionError("模板过大应抛 ValueError 停步")
    except ValueError:
        pass
    finally:
        _im.find_template = _orig
    assert m.status is StepStatus.ERROR
    assert any("图片匹配" in e.message for e in LogModel.instance().entries)

    # 给定图片为空（未绑定必填槽）→ resolve_inputs 校验拦截 → ERROR 停步
    LogModel.instance().clear()
    m_no_given = ImageMatch.create_default(tree, pkg)
    m_no_given.io.change_value("input", 1, "{{tpl}}")   # 给定图片槽留空
    m_no_given.io.change_value("output", 0, "ox")
    m_no_given.io.change_value("output", 1, "oy")
    m_no_given.io.change_value("output", 2, "ok")
    try:
        m_no_given.do()
        raise AssertionError("给定图片为空应停步")
    except ValueError:
        pass
    assert m_no_given.status is StepStatus.ERROR
    assert any("图片匹配" in e.message for e in LogModel.instance().entries)

    # 匹配图片为空（未绑定必填槽）→ 同上 ERROR 停步
    LogModel.instance().clear()
    m_no_needle = ImageMatch.create_default(tree, pkg)
    m_no_needle.io.change_value("input", 0, "{{given}}")  # 匹配图片槽留空
    m_no_needle.io.change_value("output", 0, "ox")
    m_no_needle.io.change_value("output", 1, "oy")
    m_no_needle.io.change_value("output", 2, "ok")
    try:
        m_no_needle.do()
        raise AssertionError("匹配图片为空应停步")
    except ValueError:
        pass
    assert m_no_needle.status is StepStatus.ERROR
    assert any("图片匹配" in e.message for e in LogModel.instance().entries)

    # ---- info_widget：提示 + 预览（仅展示给定图片） ----
    m2 = ImageMatch.create_default(tree, pkg)
    m2.io.change_value("input", 0, "{{given}}")
    view = m2.info_widget()
    assert view is not None
    from PyQt5.QtWidgets import QLabel, QPushButton
    labels = view.findChildren(QLabel)
    btns = view.findChildren(QPushButton)
    assert any("查看原图" in b.text() for b in btns)
    assert any("查看大图" in l.text() for l in labels)
    assert not view._mark_view.preview_pixmap().isNull()   # 有素材 → 非占位

    # 往返
    fmt = m.to_format_string()
    assert "=" not in fmt and "+" not in fmt and "/" not in fmt
    m3 = ImageMatch.from_format_string(fmt, tree, pkg)
    assert isinstance(m3, ImageMatch)
    assert m3.io.to_format_string() == m.io.to_format_string()

    print("ImageMatch smoke OK")
