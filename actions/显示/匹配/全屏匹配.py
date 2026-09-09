# -*- coding: utf-8 -*-
"""
全屏匹配图片步骤（显示/匹配）
========================

:class:`FullScreenMatch`：在主屏全画面中匹配「匹配图片」，返回其中心在屏幕
上的绝对坐标与是否成功。

输入槽
------
* ``匹配图片``（image）：被查找的模板图。

运行规则
--------
* 用 :func:`libs.vision.image_match.find_template`（``screenshot=None`` →
  默认截图函数抓取主屏全画面）做模板匹配。
* 命中：输出 坐标x/坐标y = 模板中心屏幕坐标，是否成功 = 1。
* 未命中：坐标x/坐标y = 0，是否成功 = 0（**不报错**——匹配失败是正常分支，
  用是否成功=0 表达；调用方可据此分支）。
* 匹配图片为空 / 模板无法解码 / 模板大于屏幕：抛 :class:`ValueError`
  （由 do() 置「执行错误」停步）。

自定义视图
----------
* 复用 :class:`MarkPreviewView`（dot 模式）仅展示模板图（看「找什么」）。
"""
from dataclasses import dataclass
from typing import Optional

from PyQt5.QtWidgets import QVBoxLayout, QWidget

from model.log_model import LogModel
from model.步骤.step import Step
from widgets.卡片.mark_preview_view import MarkPreviewView

__all__ = ["FullScreenMatch"]


@dataclass
class FullScreenMatchInput:
    """输入：匹配图片（image）。"""
    匹配图片: "image" = ""  # type: ignore


@dataclass
class FullScreenMatchOutput:
    """输出：坐标x / 坐标y / 是否成功（number；1=成功 0=失败）。"""
    坐标x: "number" = 0  # type: ignore
    坐标y: "number" = 0  # type: ignore
    是否成功: "number" = 0  # type: ignore


class FullScreenMatch(Step):
    """全屏匹配图片步骤：在主屏全画面匹配模板，返回其中心的屏幕坐标。"""

    name = "全屏匹配图片"
    description = "在主屏全画面中匹配模板图片，返回其中心的屏幕坐标"
    input_class = FullScreenMatchInput
    output_class = FullScreenMatchOutput

    # 匹配图片输入槽下标（自定义视图展示用）
    IMAGE_SLOT = 0

    def run(self) -> int:
        tpl = self.inputs.匹配图片
        if not tpl:
            raise ValueError("全屏匹配图片：匹配图片为空")
        try:
            from libs.vision.image_match import find_template
        except ImportError as e:
            raise ValueError("全屏匹配图片：图像匹配引擎未安装: %s" % e)
        try:
            found, center = find_template(bytes(tpl))     # screenshot=None → 全屏
        except FileNotFoundError as e:
            raise ValueError("全屏匹配图片：匹配图片无法解码: %s" % e)
        except OSError as e:
            raise ValueError("全屏匹配图片：截图或匹配失败: %s" % e)
        except ValueError:
            raise                              # 模板大于屏幕 → 配置错误，置 ERROR
        if found and center is not None:
            self.outputs.坐标x = int(center[0])
            self.outputs.坐标y = int(center[1])
            self.outputs.是否成功 = 1
            LogModel.instance().info(
                "全屏匹配命中: (%d,%d)" % (center[0], center[1]))
        else:
            self.outputs.坐标x = 0
            self.outputs.坐标y = 0
            self.outputs.是否成功 = 0
            LogModel.instance().info("全屏匹配未命中")
        return 1

    def info_widget(self, parent: Optional[QWidget] = None) -> QWidget:
        """自定义视图：仅展示模板图（不标注）。"""
        return _MatchView(self, parent)


class _MatchView(QWidget):
    """全屏匹配步骤的自定义卡片视图（复用 :class:`MarkPreviewView`，仅展示模板）。"""

    def __init__(self, step: "FullScreenMatch",
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._step = step
        self._mark_view = MarkPreviewView(
            io=step.io, image_slot=FullScreenMatch.IMAGE_SLOT, mode="dot",
            hint_text=FullScreenMatch.description
            + "\n下方预览仅展示待匹配图片（不标注）；点击缩略图查看大图",
            read_points=lambda: None,           # 仅展示：原图，不合成标注
            write_points=lambda pos_info: None,  # 展示语义：不回写坐标
            mark_button="查看原图",
            parent=self)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self._mark_view)


# ================================================================
# 冒烟演示：直接 ``python -m actions.显示.匹配.全屏匹配`` 运行
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

    # 造一张「屏幕」图：白底 + 左上有图案的小图标（非纯色，灰度有方差）
    _screen = _PILImage.new("RGB", (40, 30), "white")
    _d = _IDraw.Draw(_screen)
    _d.rectangle([10, 8, 16, 14], outline="black")
    _d.point((12, 11), fill="red")
    _d.point((14, 13), fill="blue")
    _buf = _io.BytesIO()
    _screen.save(_buf, "PNG")
    _screen_png = _buf.getvalue()
    # 模板 = 该图标的 7×7 裁剪
    _tpl = _screen.crop((10, 8, 17, 15))
    _buf2 = _io.BytesIO()
    _tpl.save(_buf2, "PNG")
    _tpl_png = _buf2.getvalue()

    pkg = KscpPackage.create_empty()
    pkg.write_file("assets/tpl.png", _tpl_png)
    tree = VariableTree.create_empty()
    tree.add("tpl", ProjectVariable.create("image", "assets/tpl.png", pkg))
    tree.add("ox", ProjectVariable.create("number", 0, pkg))
    tree.add("oy", ProjectVariable.create("number", 0, pkg))
    tree.add("ok", ProjectVariable.create("number", 0, pkg))

    # create_default：槽类型推导
    m = FullScreenMatch.create_default(tree, pkg)
    assert m.io._input_type == ["image"]
    assert m.io._output_type == ["number", "number", "number"]
    assert m.name == "全屏匹配图片"

    # 输入绑定模板、输出绑定 ox/oy/ok
    m.io.change_value("input", 0, "{{tpl}}")
    m.io.change_value("output", 0, "ox")
    m.io.change_value("output", 1, "oy")
    m.io.change_value("output", 2, "ok")

    # 桩替换 find_template（冒烟不真实截屏/匹配，保证可复现）
    import libs.vision.image_match as _im
    _orig = _im.find_template

    # 命中：返回中心 (13, 11)
    _im.find_template = lambda tpl, screenshot=None, threshold=0.8: (True, (13, 11))
    try:
        assert m.do() == 1
        assert m.status is StepStatus.FINISHED
        assert tree.get("ox").get_actual_data() == 13
        assert tree.get("oy").get_actual_data() == 11
        assert tree.get("ok").get_actual_data() == 1
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

    # 模板大于屏幕（ValueError）→ ERROR 停步
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
    assert any("全屏匹配" in e.message for e in LogModel.instance().entries)

    # 匹配图片为空（未绑定必填槽）→ resolve_inputs 校验拦截 → ERROR 停步
    LogModel.instance().clear()
    m_empty = FullScreenMatch.create_default(tree, pkg)
    m_empty.io.change_value("output", 0, "ox")
    m_empty.io.change_value("output", 1, "oy")
    m_empty.io.change_value("output", 2, "ok")
    try:
        m_empty.do()
        raise AssertionError("空模板应停步")
    except ValueError:
        pass
    assert m_empty.status is StepStatus.ERROR
    assert any("全屏匹配" in e.message for e in LogModel.instance().entries)

    # ---- info_widget：提示 + 预览（仅展示模板） ----
    m2 = FullScreenMatch.create_default(tree, pkg)
    m2.io.change_value("input", 0, "{{tpl}}")
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
    m3 = FullScreenMatch.from_format_string(fmt, tree, pkg)
    assert isinstance(m3, FullScreenMatch)
    assert m3.io.to_format_string() == m.io.to_format_string()

    print("FullScreenMatch smoke OK")
