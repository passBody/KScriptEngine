# -*- coding: utf-8 -*-
"""
裁剪矩形步骤（显示/裁剪）
========================

:class:`CropRect`：按两点矩形坐标裁剪输入图片，输出为 image 变量。

输入槽
------
* ``待裁剪图片``（image）：被裁剪的源图。
* ``左上坐标``（string）：``(x1,y1)`` 形式的矩形左上角（相对源图）。
* ``右下坐标``（string）：``(x2,y2)`` 形式的矩形右下角（相对源图）。

运行规则
--------
* 读源图字节 → ``QImage`` → ``copy(x,y,w,h)`` → PNG 字节。
* **覆盖输出变量所在的图片**：读取输出槽绑定的 image 变量当前 ``data``
  （资源路径），把 PNG 字节写回该路径；输出槽设为同一资源路径。同一变量被
  反复裁剪时原地更新，而非新增固定资源。
* 坐标越界 / 格式非法 / 未指定输出 / 输出非 image / 编码失败：抛
  :class:`ValueError`（由 do() 置「执行错误」停步，且失败时不覆盖原图）。

自定义视图
----------
* 复用 :class:`MarkPreviewView`（rect 模式）：缩略图预览 +「设置点位」按钮，
  在源图上标两点矩形后自动回填到左上/右下输入槽。
"""
from dataclasses import dataclass
from typing import List, Optional, Tuple

from PyQt5.QtCore import QBuffer, QIODevice, QRect
from PyQt5.QtGui import QImage
from PyQt5.QtWidgets import QVBoxLayout, QWidget

from model.执行.point_timeline import PointTimeline
from model.log_model import LogModel
from model.步骤.step import Step
from widgets.卡片.mark_preview_view import MarkPreviewView

__all__ = ["CropRect"]


@dataclass
class CropRectInput:
    """输入：待裁剪图片（image）、左上/右下坐标（string）。"""
    待裁剪图片: "image" = ""  # type: ignore
    左上坐标: "string" = ""  # type: ignore
    右下坐标: "string" = ""  # type: ignore


@dataclass
class CropRectOutput:
    """输出：裁剪后图片（image）。"""
    裁剪后: "image" = ""  # type: ignore


class CropRect(Step):
    """裁剪矩形步骤：按两点矩形坐标裁剪输入图片，覆盖写入输出变量所指向的图片。"""

    name = "裁剪矩形"
    description = "按两点矩形坐标裁剪输入图片，覆盖写入输出变量所指向的图片"
    input_class = CropRectInput
    output_class = CropRectOutput

    # 待裁剪图片输入槽下标（自定义视图/点位标注用）
    IMAGE_SLOT = 0

    def run(self) -> int:
        data = self.inputs.待裁剪图片
        if not data:
            raise ValueError("裁剪矩形：待裁剪图片为空")
        x1, y1 = self._parse_point(self.inputs.左上坐标, "左上坐标")
        x2, y2 = self._parse_point(self.inputs.右下坐标, "右下坐标")
        x, y = min(x1, x2), min(y1, y2)
        w, h = abs(x2 - x1) + 1, abs(y2 - y1) + 1
        if w <= 0 or h <= 0:
            raise ValueError("裁剪矩形：矩形宽高必须大于 0")
        img = QImage()
        if not img.loadFromData(bytes(data)):
            raise ValueError("裁剪矩形：待裁剪图片解码失败")
        rect = QRect(x, y, w, h)
        if not QRect(0, 0, img.width(), img.height()).contains(rect):
            raise ValueError("裁剪矩形：矩形 %s 越出图片边界 %dx%d"
                             % (rect, img.width(), img.height()))
        # 输出槽绑定的 image 变量 → 其当前资源路径（裁剪结果覆盖目标）
        name = self.io.output_value(0)
        if not name:
            raise ValueError("裁剪矩形：未指定输出变量")
        bound = self.io.tree.get(name)
        if bound.type != "image":
            raise ValueError("裁剪矩形：输出变量「%s」不是 image 类型" % name)
        target = bound.data
        if not (isinstance(target, str) and target.startswith("assets/")
                and any(target.lower().endswith(s) for s in bound.suffixes)):
            raise ValueError("裁剪矩形：输出变量「%s」的图片路径非法: %r" % (name, target))
        cropped = img.copy(rect)
        buf = QBuffer()
        buf.open(QIODevice.ReadWrite)
        if not cropped.save(buf, "PNG"):
            raise ValueError("裁剪矩形：PNG 编码失败")
        png = bytes(buf.data())
        self.io.package.write_file(target, png)   # 原地覆盖输出变量所指向的图片
        self.outputs.裁剪后 = target
        LogModel.instance().info(
            "裁剪矩形完成: (%d,%d)-(%d,%d) of %dx%d → %s"
            % (x, y, x + w - 1, y + h - 1, img.width(), img.height(), target))
        return 1

    # ----------------------------------------------------------------
    # 坐标解析
    # ----------------------------------------------------------------
    @staticmethod
    def _parse_point(text: str, slot_name: str) -> Tuple[int, int]:
        """``"(x,y)"`` → (int, int)；非法 → ValueError。"""
        if not isinstance(text, str) or not text.strip():
            raise ValueError("裁剪矩形：%s 为空" % slot_name)
        s = text.strip()
        if s.startswith("(") and s.endswith(")"):
            s = s[1:-1]
        parts = [p.strip() for p in s.split(",")]
        if len(parts) != 2:
            raise ValueError("裁剪矩形：%s 格式非法，需 (x,y)" % slot_name)
        try:
            return int(float(parts[0])), int(float(parts[1]))
        except ValueError:
            raise ValueError("裁剪矩形：%s 含非数字" % slot_name)

    def info_widget(self, parent: Optional[QWidget] = None) -> QWidget:
        """自定义视图：提示 + 标注预览 + 设置点位按钮（rect 模式标矩形）。"""
        return _CropInfoView(self, parent)


class _CropInfoView(QWidget):
    """裁剪矩形步骤的自定义卡片视图（复用 :class:`MarkPreviewView`）。

    提示 + 缩略图（点击弹窗）+「设置点位」按钮均由共享控件提供，本类
    只接线：素材槽下标、rect 模式（两点矩形）、左上/右下槽的读点/回写。
    """

    def __init__(self, step: "CropRect", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._step = step
        self._mark_view = MarkPreviewView(
            io=step.io, image_slot=CropRect.IMAGE_SLOT, mode="rect",
            hint_text=CropRect.description + "\n用「设置点位」在图上标矩形；点击缩略图查看大图",
            read_points=self._read_rect,
            write_points=self._write_rect,
            parent=self)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self._mark_view)

    def _read_rect(self) -> Optional[List[Tuple[int, int]]]:
        """从输入 GUI 的左上/右下槽读两点；非数值 → None（预览显示原图）。"""
        try:
            x1, y1 = CropRect._parse_point(self._step.io.input_value(1), "左上坐标")
            x2, y2 = CropRect._parse_point(self._step.io.input_value(2), "右下坐标")
            return [(x1, y1), (x2, y2)]
        except (ValueError, TypeError):
            return None

    def _write_rect(self, pos_info: Optional[PointTimeline]) -> None:
        """设置点位完成 → 两点写回左上/右下槽（io 监听触发预览重合成）。"""
        if pos_info is None:
            return
        pts = pos_info.points
        if len(pts) < 2:
            return
        (x1, y1), (x2, y2) = pts[0], pts[1]
        self._step.io.change_value("input", 1, "(%d,%d)" % (x1, y1))
        self._step.io.change_value("input", 2, "(%d,%d)" % (x2, y2))


# ================================================================
# 冒烟演示：直接 ``python -m actions.显示.裁剪.裁剪矩形`` 运行
# ================================================================
if __name__ == "__main__":
    import sys

    from PyQt5.QtCore import QBuffer as _QBuf
    from PyQt5.QtGui import QImage as _QImg
    from PyQt5.QtWidgets import QApplication

    from model.工程.kscp_package import KscpPackage
    from model.变量.project_variable import ProjectVariable
    from model.步骤.step import StepStatus
    from model.变量.variable_tree import VariableTree

    _mod = sys.modules[__name__]

    app = QApplication.instance() or QApplication(sys.argv)

    # 造一张 100×100 白底 PNG 写入包内供裁剪
    _src = _QImg(100, 100, _QImg.Format_RGB32)
    _src.fill(0xFFFFFFFF)
    _b = _QBuf()
    _b.open(QIODevice.ReadWrite)
    _src.save(_b, "PNG")
    _src_png = bytes(_b.data())

    pkg = KscpPackage.create_empty()
    pkg.write_file("assets/src.png", _src_png)
    tree = VariableTree.create_empty()
    tree.add("src", ProjectVariable.create("image", "assets/src.png", pkg))
    # 输出变量指向一张已有图片 assets/out.png（裁剪结果将原地覆盖它）
    pkg.write_file("assets/out.png", b"\x89PNG\r\n\x1a\nOLD")
    tree.add("out", ProjectVariable.create("image", "assets/out.png", pkg))

    # create_default：槽类型推导
    c = CropRect.create_default(tree, pkg)
    assert c.io._input_type == ["image", "string", "string"]
    assert c.io._output_type == ["image"]
    assert c.name == "裁剪矩形"

    # 输入绑定源图、输出绑定 out
    c.io.change_value("input", 0, "{{src}}")
    c.io.change_value("output", 0, "out")

    # 正常：裁剪 (10,10)-(50,50)
    c.io.change_value("input", 1, "(10,10)")
    c.io.change_value("input", 2, "(50,50)")
    assert c.do() == 1
    assert c.status is StepStatus.FINISHED
    # 裁剪结果覆盖了输出变量指向的同一资源路径 assets/out.png（原地更新，非新增固定资源）
    out_png = pkg.read_file("assets/out.png")
    assert out_png[:8] == b"\x89PNG\r\n\x1a\n"
    assert out_png != b"\x89PNG\r\n\x1a\nOLD"   # 旧内容已被裁剪结果覆盖
    out_img = _QImg()
    assert out_img.loadFromData(out_png)
    assert out_img.width() == 41 and out_img.height() == 41, (out_img.width(), out_img.height())
    assert tree.get("out").data == "assets/out.png"

    # 反向两点同样归一为 (10,10)-(50,50)
    c.io.change_value("input", 1, "(50,50)")
    c.io.change_value("input", 2, "(10,10)")
    assert c.do() == 1
    out_img = _QImg()
    out_img.loadFromData(pkg.read_file("assets/out.png"))
    assert out_img.width() == 41 and out_img.height() == 41

    # 越界：抛 ValueError → ERROR 停步（原图不被改写）
    LogModel.instance().clear()
    pkg.write_file("assets/out.png", b"\x89PNG\r\n\x1a\nOLD")   # 复位
    c2 = CropRect.create_default(tree, pkg)
    c2.io.change_value("input", 0, "{{src}}")
    c2.io.change_value("output", 0, "out")
    c2.io.change_value("input", 1, "(80,80)")
    c2.io.change_value("input", 2, "(120,120)")
    try:
        c2.do()
        raise AssertionError("矩形越界应抛 ValueError 停步")
    except ValueError:
        pass
    assert c2.status is StepStatus.ERROR
    assert any("裁剪矩形" in e.message for e in LogModel.instance().entries)
    assert pkg.read_file("assets/out.png") == b"\x89PNG\r\n\x1a\nOLD"  # 失败不覆盖

    # 坐标格式非法 → ERROR
    LogModel.instance().clear()
    c3 = CropRect.create_default(tree, pkg)
    c3.io.change_value("input", 0, "{{src}}")
    c3.io.change_value("output", 0, "out")
    c3.io.change_value("input", 1, "abc")
    c3.io.change_value("input", 2, "(1,2)")
    try:
        c3.do()
        raise AssertionError("坐标非法应抛 ValueError 停步")
    except ValueError:
        pass
    assert c3.status is StepStatus.ERROR

    # 未指定输出 → ERROR 停步
    LogModel.instance().clear()
    c_noout = CropRect.create_default(tree, pkg)
    c_noout.io.change_value("input", 0, "{{src}}")
    c_noout.io.change_value("input", 1, "(0,0)")
    c_noout.io.change_value("input", 2, "(10,10)")
    try:
        c_noout.do()
        raise AssertionError("未指定输出应抛 ValueError 停步")
    except ValueError:
        pass
    assert c_noout.status is StepStatus.ERROR
    assert any("未指定输出" in e.message for e in LogModel.instance().entries)

    # 输出非 image → ERROR 停步
    LogModel.instance().clear()
    tree.add("txt", ProjectVariable.create("string", "hi", pkg))
    c_badtype = CropRect.create_default(tree, pkg)
    c_badtype.io.change_value("input", 0, "{{src}}")
    c_badtype.io.change_value("output", 0, "txt")
    c_badtype.io.change_value("input", 1, "(0,0)")
    c_badtype.io.change_value("input", 2, "(10,10)")
    try:
        c_badtype.do()
        raise AssertionError("非 image 输出应抛 ValueError 停步")
    except ValueError:
        pass
    assert c_badtype.status is StepStatus.ERROR
    assert any("不是 image 类型" in e.message for e in LogModel.instance().entries)

    # ---- info_widget：提示 + 预览 + 设置点位（rect 模式） ----
    c4 = CropRect.create_default(tree, pkg)
    c4.io.change_value("input", 0, "{{src}}")
    c4.io.change_value("input", 1, "(20,20)")
    c4.io.change_value("input", 2, "(80,80)")
    view = c4.info_widget()
    assert view is not None
    from PyQt5.QtWidgets import QLabel, QPushButton
    labels = view.findChildren(QLabel)
    btns = view.findChildren(QPushButton)
    assert any("设置点位" in b.text() for b in btns)
    assert any("查看大图" in l.text() for l in labels)
    assert not view._mark_view.preview_pixmap().isNull()   # 有素材 → 非占位
    # 设置点位：桩替换 mark_image → 两点写回左上/右下槽
    import tools.image_marker as _im
    _orig_mark = _im.mark_image

    class _FakeRect:
        points = [(12, 34), (56, 78)]
    _im.mark_image = lambda data, mode: (data, _FakeRect())
    try:
        [b for b in btns if b.text() == "设置点位"][0].click()
    finally:
        _im.mark_image = _orig_mark
    assert c4.io.input_value(1) == "(12,34)", c4.io.input_value(1)
    assert c4.io.input_value(2) == "(56,78)", c4.io.input_value(2)

    # 往返
    fmt = c.to_format_string()
    assert "=" not in fmt and "+" not in fmt and "/" not in fmt
    c5 = CropRect.from_format_string(fmt, tree, pkg)
    assert isinstance(c5, CropRect)
    assert c5.io.to_format_string() == c.io.to_format_string()

    print("CropRect smoke OK")
