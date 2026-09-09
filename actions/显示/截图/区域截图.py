# -*- coding: utf-8 -*-
"""
区域截图步骤（显示/截图）
========================

:class:`RegionShot`：按两点矩形坐标截取主屏区域画面，覆盖写入**输出变量所指向的图片资源**。

输入槽
------
* ``左上坐标``（string）：``(x1,y1)`` 形式的矩形左上角。
* ``右下坐标``（string）：``(x2,y2)`` 形式的矩形右下角。
* ``素材图片``（image，**可选**）：**编辑期辅助**，仅用于自定义视图的点位标注
  与预览（模仿鼠标点击标记矩形）；可空（可选槽不校验、解析为 None），``run()`` 不读取它。

运行规则
--------
* 解析两点坐标 → ``screen.grabWindow(0, x, y, w, h)`` 抓区域 → PNG 字节。
* **覆盖输出变量所在的图片**：读取输出槽绑定的 image 变量当前 ``data``
  （资源路径），把 PNG 字节写回该路径；输出槽设为同一资源路径。同一变量被
  反复区域截图时原地更新，而非新增固定资源。
* 坐标格式非法 / 未指定输出 / 输出非 image / 抓屏失败：抛 :class:`ValueError`
  （由 do() 置「执行错误」停步，且失败时不覆盖原图）。
"""
from dataclasses import dataclass
from typing import List, Optional, Tuple, TYPE_CHECKING

from PyQt5.QtCore import QBuffer, QIODevice
from PyQt5.QtWidgets import QVBoxLayout, QWidget

from model.执行.point_timeline import PointTimeline
from model.log_model import LogModel
from model.步骤.step import Step, optional
from widgets.卡片.mark_preview_view import MarkPreviewView

if TYPE_CHECKING:
    pass

__all__ = ["RegionShot"]


@dataclass
class RegionShotInput:
    """输入：左上/右下坐标（string）与素材图片（image，仅编辑辅助）。"""
    左上坐标: "string" = ""  # type: ignore
    右下坐标: "string" = ""  # type: ignore
    素材图片: "image" = optional("")  # type: ignore  # 非必须：编辑期辅助，可空


@dataclass
class RegionShotOutput:
    """输出：区域截图（image）。"""
    区域截图: "image" = ""  # type: ignore


class RegionShot(Step):
    """区域截图步骤：按两点矩形坐标截取主屏区域，覆盖输出变量所指向的图片。"""

    name = "区域截图"
    description = "按两点矩形坐标截取主屏区域，覆盖写入输出变量所指向的图片"
    input_class = RegionShotInput
    output_class = RegionShotOutput

    # 素材图片输入槽下标（自定义视图/点位标注用）
    IMAGE_SLOT = 2

    def run(self) -> int:
        x1, y1 = self._parse_point(self.inputs.左上坐标, "左上坐标")
        x2, y2 = self._parse_point(self.inputs.右下坐标, "右下坐标")
        x, y = min(x1, x2), min(y1, y2)
        w, h = abs(x2 - x1) + 1, abs(y2 - y1) + 1
        if w <= 0 or h <= 0:
            raise ValueError("区域截图：矩形宽高必须大于 0")
        # 输出槽绑定的 image 变量 → 其当前资源路径（截图覆盖目标）
        name = self.io.output_value(0)
        if not name:
            raise ValueError("区域截图：未指定输出变量")
        bound = self.io.tree.get(name)
        if bound.type != "image":
            raise ValueError("区域截图：输出变量「%s」不是 image 类型" % name)
        target = bound.data
        if not (isinstance(target, str) and target.startswith("assets/")
                and any(target.lower().endswith(s) for s in bound.suffixes)):
            raise ValueError("区域截图：输出变量「%s」的图片路径非法: %r" % (name, target))
        png = self._capture_png(x, y, w, h)
        if not png:
            raise ValueError("区域截图：抓屏或编码失败（无屏幕环境）")
        self.io.package.write_file(target, png)
        self.outputs.区域截图 = target
        LogModel.instance().info(
            "区域截图完成: (%d,%d)-(%d,%d) → %s"
            % (x, y, x + w - 1, y + h - 1, target))
        return 1

    # ----------------------------------------------------------------
    # 坐标解析 / 抓屏
    # ----------------------------------------------------------------
    @staticmethod
    def _parse_point(text: str, slot_name: str) -> Tuple[int, int]:
        """``"(x,y)"`` → (int, int)；非法 → ValueError。"""
        if not isinstance(text, str) or not text.strip():
            raise ValueError("区域截图：%s 为空" % slot_name)
        s = text.strip()
        if s.startswith("(") and s.endswith(")"):
            s = s[1:-1]
        parts = [p.strip() for p in s.split(",")]
        if len(parts) != 2:
            raise ValueError("区域截图：%s 格式非法，需 (x,y)" % slot_name)
        try:
            return int(float(parts[0])), int(float(parts[1]))
        except ValueError:
            raise ValueError("区域截图：%s 含非数字" % slot_name)

    @staticmethod
    def _capture_png(x: int, y: int, w: int, h: int) -> Optional[bytes]:
        """主屏指定区域 → PNG 字节；无屏幕环境 / 编码失败 → None。"""
        from PyQt5.QtWidgets import QApplication

        app = QApplication.instance()
        if app is None:
            return None
        screen = app.primaryScreen()
        if screen is None:
            return None
        pix = screen.grabWindow(0, x, y, w, h)   # 0 = 整个屏幕，偏移取区域
        if pix.isNull():
            return None
        buf = QBuffer()
        buf.open(QIODevice.ReadWrite)
        ok = pix.toImage().save(buf, "PNG")
        return bytes(buf.data()) if ok else None

    def info_widget(self, parent: Optional[QWidget] = None) -> QWidget:
        """自定义视图：提示 + 标注预览 + 设置点位按钮（rect 模式标矩形）。"""
        return _RegionInfoView(self, parent)


class _RegionInfoView(QWidget):
    """区域截图步骤的自定义卡片视图（复用 :class:`MarkPreviewView`）。

    提示 + 缩略图（点击弹窗）+「设置点位」按钮均由共享控件提供，本类
    只接线：素材槽下标、rect 模式（两点矩形）、左上/右下槽的读点/回写。
    """

    def __init__(self, step: "RegionShot", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._step = step
        self._mark_view = MarkPreviewView(
            io=step.io, image_slot=RegionShot.IMAGE_SLOT, mode="rect",
            hint_text=RegionShot.description + "\n用「设置点位」标两点矩形；点击缩略图查看大图",
            read_points=self._read_rect,
            write_points=self._write_rect,
            parent=self)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self._mark_view)

    def _read_rect(self) -> Optional[List[Tuple[int, int]]]:
        """从输入 GUI 的左上/右下槽读两点；非数值 → None（预览显示原图）。"""
        try:
            x1, y1 = RegionShot._parse_point(self._step.io.input_value(0), "左上坐标")
            x2, y2 = RegionShot._parse_point(self._step.io.input_value(1), "右下坐标")
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
        self._step.io.change_value("input", 0, "(%d,%d)" % (x1, y1))
        self._step.io.change_value("input", 1, "(%d,%d)" % (x2, y2))


# ================================================================
# 冒烟演示：直接 ``python -m actions.显示.截图.区域截图`` 运行
# ================================================================
if __name__ == "__main__":
    import sys

    from PyQt5.QtWidgets import QApplication

    from model.工程.kscp_package import KscpPackage
    from model.变量.project_variable import ProjectVariable
    from model.步骤.step import StepStatus
    from model.变量.variable_tree import VariableTree

    _mod = sys.modules[__name__]

    app = QApplication.instance() or QApplication(sys.argv)

    pkg = KscpPackage.create_empty()
    tree = VariableTree.create_empty()
    # 输出变量指向一张已有图片 assets/shot.png（截图将原地覆盖它）
    pkg.write_file("assets/shot.png", b"\x89PNG\r\n\x1a\nOLD")
    tree.add("shot", ProjectVariable.create("image", "assets/shot.png", pkg))

    # create_default：槽类型推导（含素材图片可选）
    r = RegionShot.create_default(tree, pkg)
    assert r.io._input_type == ["string", "string", "image"]
    assert r.io._input_optional == [False, False, True]
    assert r.io._output_type == ["image"]
    assert r.name == "区域截图"

    # 输出绑定 image 变量
    r.io.change_value("output", 0, "shot")

    # run 用桩替换抓屏（冒烟不真实截屏）
    captured = []

    def _fake_capture(x, y, w, h):
        captured.append((x, y, w, h))
        buf = QBuffer()
        buf.open(QIODevice.ReadWrite)
        from PyQt5.QtGui import QImage
        QImage(2, 2, QImage.Format_RGB32).save(buf, "PNG")
        return bytes(buf.data())

    _orig = RegionShot._capture_png
    RegionShot._capture_png = staticmethod(_fake_capture)
    try:
        # 正常：两点矩形（顺序无关，内部 min/abs 归一）
        r.io.change_value("input", 0, "(100,200)")
        r.io.change_value("input", 1, "(150,250)")
        assert r.do() == 1
        assert r.status is StepStatus.FINISHED
        assert captured == [(100, 200, 51, 51)], captured
        # 截图覆盖了输出变量指向的同一资源路径 assets/shot.png（原地更新，非新增固定资源）
        png = pkg.read_file("assets/shot.png")
        assert png[:8] == b"\x89PNG\r\n\x1a\n"
        assert png != b"\x89PNG\r\n\x1a\nOLD"   # 旧内容已被新截图覆盖
        assert tree.get("shot").data == "assets/shot.png"
        # 反向两点同样归一
        captured.clear()
        r.io.change_value("input", 0, "(150,250)")
        r.io.change_value("input", 1, "(100,200)")
        assert r.do() == 1
        assert captured == [(100, 200, 51, 51)], captured
        # 无括号写法
        captured.clear()
        r.io.change_value("input", 0, "10,20")
        r.io.change_value("input", 1, "30,40")
        assert r.do() == 1
        assert captured == [(10, 20, 21, 21)], captured
    finally:
        RegionShot._capture_png = _orig

    # 解析失败：抛 ValueError → do() 置 ERROR 停步（原图不被改写）
    LogModel.instance().clear()
    pkg.write_file("assets/shot.png", b"\x89PNG\r\n\x1a\nOLD")   # 复位
    r2 = RegionShot.create_default(tree, pkg)
    r2.io.change_value("output", 0, "shot")
    r2.io.change_value("input", 0, "abc")
    r2.io.change_value("input", 1, "(1,2)")
    try:
        r2.do()
        raise AssertionError("坐标非法应抛 ValueError 停步")
    except ValueError:
        pass
    assert r2.status is StepStatus.ERROR
    assert any("区域截图" in e.message for e in LogModel.instance().entries)
    assert pkg.read_file("assets/shot.png") == b"\x89PNG\r\n\x1a\nOLD"  # 失败不覆盖

    # 未指定输出 → ERROR 停步
    LogModel.instance().clear()
    r_noout = RegionShot.create_default(tree, pkg)
    r_noout.io.change_value("input", 0, "(0,0)")
    r_noout.io.change_value("input", 1, "(5,5)")
    try:
        r_noout.do()
        raise AssertionError("未指定输出应抛 ValueError 停步")
    except ValueError:
        pass
    assert r_noout.status is StepStatus.ERROR
    assert any("未指定输出" in e.message for e in LogModel.instance().entries)

    # 输出非 image → ERROR 停步
    LogModel.instance().clear()
    tree.add("txt", ProjectVariable.create("string", "hi", pkg))
    r_badtype = RegionShot.create_default(tree, pkg)
    r_badtype.io.change_value("output", 0, "txt")
    r_badtype.io.change_value("input", 0, "(0,0)")
    r_badtype.io.change_value("input", 1, "(5,5)")
    try:
        r_badtype.do()
        raise AssertionError("非 image 输出应抛 ValueError 停步")
    except ValueError:
        pass
    assert r_badtype.status is StepStatus.ERROR
    assert any("不是 image 类型" in e.message for e in LogModel.instance().entries)

    # 素材图片为可选输入（optional("") 标记）：空值合法、解析为 None，run 不依赖
    r.io.change_value("input", 2, "")
    assert r.io.is_valid
    captured.clear()
    RegionShot._capture_png = staticmethod(_fake_capture)
    r.io.change_value("input", 0, "(0,0)")
    r.io.change_value("input", 1, "(5,5)")
    try:
        assert r.do() == 1
        assert captured == [(0, 0, 6, 6)]
    finally:
        RegionShot._capture_png = _orig
    assert r.inputs.素材图片 is None

    # ---- info_widget：提示 + 预览 + 设置点位（rect 模式） ----
    import base64 as _b64
    pkg.write_file("assets/底图.png", _b64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGNgYGBgAAAABQAB"
        "pfZFQAAAAABJRU5ErkJggg=="))   # 1x1 PNG
    tree.add("底图", ProjectVariable.create("image", "assets/底图.png", pkg))
    r3 = RegionShot.create_default(tree, pkg)
    r3.io.change_value("input", 2, "{{底图}}")
    r3.io.change_value("input", 0, "(20,20)")
    r3.io.change_value("input", 1, "(80,80)")
    view = r3.info_widget()
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
        points = [(123, 456), (789, 12)]
    _im.mark_image = lambda data, mode: (data, _FakeRect())
    try:
        [b for b in btns if b.text() == "设置点位"][0].click()
    finally:
        _im.mark_image = _orig_mark
    assert r3.io.input_value(0) == "(123,456)", r3.io.input_value(0)
    assert r3.io.input_value(1) == "(789,12)", r3.io.input_value(1)

    # 往返
    fmt = r.to_format_string()
    assert "=" not in fmt and "+" not in fmt and "/" not in fmt
    r4 = RegionShot.from_format_string(fmt, tree, pkg)
    assert isinstance(r4, RegionShot)
    assert r4.io.to_format_string() == r.io.to_format_string()

    print("RegionShot smoke OK")
