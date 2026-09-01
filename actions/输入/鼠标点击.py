# -*- coding: utf-8 -*-
"""
鼠标点击步骤（输入模拟）
========================

:class:`MouseClick`：在坐标 (x, y) 模拟鼠标左键点击（基于内嵌
:mod:`libs.key_control` 的 :class:`InputControl`）。

输入槽
------
* ``x`` / ``y``（number）：点击坐标（可引用变量，接 image_marker 标注坐标流）。
* ``按住时长``（number，秒）：按下后多久松开。
* ``素材图片``（image，**可选**）：**编辑期辅助**，仅用于自定义视图的点位标注
  与预览；可空（可选槽不校验、解析为 None），``run()`` 不读取它。

> 模拟输入到游戏窗口需以管理员身份运行 KScript。
"""
from dataclasses import dataclass
from typing import List, Optional, Tuple

from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import QVBoxLayout, QWidget

from libs.key_control import InputControl
from model.步骤.step import Step, optional
from widgets.卡片.mark_preview_view import MarkPreviewView

__all__ = ["MouseClick"]


def _new_control() -> InputControl:
    """创建输入设备控制器（冒烟测试替换为桩，避免真实鼠标移动）。"""
    return InputControl()


@dataclass
class MouseClickInput:
    """输入：坐标 x/y、按住时长（number）、素材图片（image，仅编辑辅助）。"""
    x: "number" = 0        # type: ignore
    y: "number" = 0        # type: ignore
    按住时长: "number" = 0.05 # type: ignore
    素材图片: "image" = optional("")  # type: ignore  # 非必须：编辑期辅助，可空


@dataclass
class MouseClickOutput:
    """无输出。"""
    pass


class MouseClick(Step):
    """鼠标点击步骤：在坐标处模拟鼠标左键点击。"""

    name = "鼠标点击"
    description = "在坐标处模拟鼠标左键点击"
    input_class = MouseClickInput
    output_class = MouseClickOutput

    def run(self) -> int:
        duration = self.inputs.按住时长 if self.inputs.按住时长 > 0 else None
        _new_control().mouse_click(self.inputs.x, self.inputs.y, duration)
        return 1

    # 素材图片输入槽下标（自定义视图/点位标注用）
    IMAGE_SLOT = 3

    def info_widget(self, parent: Optional[QWidget] = None) -> QWidget:
        """自定义视图：提示 + 标注预览 + 设置点位按钮（见 _MouseInfoView）。"""
        return _MouseInfoView(self, parent)


class _MouseInfoView(QWidget):
    """鼠标点击步骤的自定义卡片视图（复用 :class:`MarkPreviewView`）。

    提示标签 + 缩略图（点击弹窗）+ 「设置点位」按钮均由共享控件提供，本类
    只接线：素材槽下标、dot 模式、x/y 槽的读点/回写。
    """

    def __init__(self, step: "MouseClick", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._step = step
        self._mark_view = MarkPreviewView(
            io=step.io, image_slot=MouseClick.IMAGE_SLOT, mode="dot",
            read_points=self._read_xy,
            write_points=self._write_xy,
            parent=self)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self._mark_view)

    def _read_xy(self) -> Optional[List[Tuple[int, int]]]:
        """从输入 GUI 的 x/y 槽读标注点；非数值 → None（预览显示原图）。"""
        try:
            x = int(round(float(self._step.io.input_value(0).strip())))
            y = int(round(float(self._step.io.input_value(1).strip())))
            return [(x, y)]
        except (ValueError, TypeError):
            return None

    def _write_xy(self, points: List[Tuple[int, int]]) -> None:
        """设置点位完成 → 坐标写回 x/y 输入槽（io 监听触发预览重合成）。"""
        x, y = points[0]
        self._step.io.change_value("input", 0, str(int(x)))
        self._step.io.change_value("input", 1, str(int(y)))

    def _preview_pixmap(self) -> QPixmap:
        """预览合成已由 MarkPreviewView 承担；本别名供冒烟兼容。"""
        return self._mark_view.preview_pixmap()


# ================================================================
# 冒烟演示：直接 ``python -m actions.输入.鼠标点击`` 运行
# ================================================================
if __name__ == "__main__":
    import sys
    import base64 as _b64

    from PyQt5.QtWidgets import QApplication

    from model.工程.kscp_package import KscpPackage
    from model.变量.project_variable import ProjectVariable
    from model.变量.variable_tree import VariableTree

    # actions/__init__.py 已登记本模块：runpy 执行前会先被包导入（sys.modules 里
    # 是旧命名空间）。桩必须挂在当前执行命名空间（run 的闭包指向它），否则冒烟会
    # 调用真实 InputControl——故不用 ``import ... as _mod``。
    _mod = sys.modules[__name__]

    app = QApplication.instance() or QApplication(sys.argv)

    pkg = KscpPackage.create_empty()
    tree = VariableTree.create_empty()

    # create_default：槽类型推导（含素材图片）
    m = MouseClick.create_default(tree, pkg)
    assert m.io._input_type == ["number", "number", "number", "image"]
    assert m.io._output_type == []
    assert m.name == "鼠标点击" and m.status is not None

    # 素材图片为可选输入槽（optional("")）：空值即可执行；此处先设引用供后续
    # 冒烟（预览/设置点位）使用
    pkg.write_file("assets/1.png", b"\x89PNG\r\n\x1a\n")
    tree.add("img", ProjectVariable.create("image", "assets/1.png", pkg))
    m.io.change_value("input", 3, "{{img}}")

    # run 用桩替换（冒烟不得真实鼠标操作）
    called = []

    class _StubCtl:
        def mouse_click(self, x, y, duration=None):
            called.append((x, y, duration))

    _mod._new_control = lambda: _StubCtl()

    # 正常：坐标 + 时长
    m.io.change_value("input", 0, "100")
    m.io.change_value("input", 1, "200")
    m.io.change_value("input", 2, "0.1")
    assert m.do() == 1
    assert called == [(100.0, 200.0, 0.1)], called
    # 时长 <= 0 → None
    called.clear()
    m.io.change_value("input", 2, "0")
    assert m.do() == 1
    assert called == [(100.0, 200.0, None)], called

    # 素材图片为可选输入（optional("") 标记）：空值合法、解析为 None，run 不依赖
    m.io.change_value("input", 3, "")
    assert m.io.is_valid
    called.clear()
    m.io.change_value("input", 2, "0.1")
    assert m.do() == 1
    assert called == [(100.0, 200.0, 0.1)], called      # run 只消费 x/y/时长
    assert m.inputs.素材图片 is None
    m.io.change_value("input", 3, "{{img}}")            # 复位（后续预览用例需要）

    # 往返
    fmt = m.to_format_string()
    assert "=" not in fmt and "+" not in fmt and "/" not in fmt
    m2 = MouseClick.from_format_string(fmt, tree, pkg)
    assert isinstance(m2, MouseClick)
    assert m2.io.to_format_string() == m.io.to_format_string()

    # ---- info_widget：提示标签 + 预览按钮 + 设置点位 ----
    pkg.write_file("assets/底图.png", _b64.b64decode(
        # 注：简报原 base64（...FQABh6FO1A...）IDAT CRC 损坏且 zlib 校验失败，
        # 无法被 libpng 解码；此处为等价有效 1x1 RGBA 透明 PNG（同尺寸同格式）。
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGNgYGBgAAAABQAB"
        "pfZFQAAAAABJRU5ErkJggg=="))     # 1x1 PNG
    from model.变量.project_variable import ProjectVariable
    tree.add("图", ProjectVariable.create("image", "assets/底图.png", pkg))
    m3 = MouseClick.create_default(tree, pkg)
    m3.io.change_value("input", 3, "{{图}}")
    view = m3.info_widget()
    assert view is not None
    # 三个要素：提示标签文字、预览缩略图、设置点位按钮（查看器不嵌入卡片）
    from PyQt5.QtWidgets import QLabel, QPushButton
    labels = view.findChildren(QLabel)
    btns = view.findChildren(QPushButton)
    assert any("预览图的画面是通过读输入GUI的参数来生成" in l.text() for l in labels)
    assert any(b.text() == "设置点位" for b in btns)
    assert not any(b.text() == "预览" for b in btns)   # 按钮已由缩略图取代
    btn = [b for b in btns if b.text() == "设置点位"][0]
    # 缩略图随素材槽变化（有素材 → 图，空槽 → 占位文字）
    _pv = view._mark_view.preview_label
    assert not view._preview_pixmap().isNull()   # 已有 {{图}} → 非占位
    assert _pv.pixmap() is not None
    assert not _pv.pixmap().isNull()
    assert _pv.text() == ""
    m3.io.change_value("input", 3, "")
    assert view._preview_pixmap().isNull()       # 空槽 → 占位（null 图）
    assert _pv.text() == "无素材"
    m3.io.change_value("input", 3, "{{图}}")
    assert not view._preview_pixmap().isNull()

    # 点击缩略图 → 独立弹窗：**无父窗口**（父窗口在 QGraphicsProxyWidget 内
    # 会被 proxy 内嵌渲染、嵌在卡片里 —— 同 model.步骤.step_io 默认选择器的教训）
    from widgets.卡片.mark_preview_view import ImagePreviewDialog
    _captured = []
    from PyQt5.QtWidgets import QDialog
    _orig_exec = QDialog.exec_
    QDialog.exec_ = lambda self: (_captured.append(self), QDialog.Accepted)[1]
    try:
        _pv.clicked.emit()
    finally:
        QDialog.exec_ = _orig_exec
    assert len(_captured) == 1 and isinstance(_captured[0], ImagePreviewDialog)
    assert _captured[0].parent() is None              # 独立顶层窗口，不嵌入卡片

    # 预览弹窗：背景 = 应用背景色（浅色，非黑）；初始尺寸 = 显示器可用区 2/3
    dlg = ImagePreviewDialog(view._preview_pixmap())
    assert dlg._view.scene() is dlg._scene
    assert dlg._view.backgroundBrush().color().name() == "#f4f7fc"
    items = dlg._scene.items()
    assert len(items) == 1 and not items[0].pixmap().isNull()
    from PyQt5.QtWidgets import QApplication
    _scr = QApplication.instance().primaryScreen()
    if _scr is not None:
        _g = _scr.availableGeometry()
        assert dlg.width() == _g.width() * 2 // 3, (dlg.width(), _g.width())
        assert dlg.height() == _g.height() * 2 // 3

    # 设置点位：桩替换 mark_image，坐标回写 x/y 槽
    import tools.image_marker as _im
    _orig_mark = _im.mark_image

    class _FakePos:
        points = [(123, 456)]
    _im.mark_image = lambda data, mode: (data, _FakePos())
    try:
        btn.click()
    finally:
        _im.mark_image = _orig_mark
    assert m3.io.input_value(0) == "123" and m3.io.input_value(1) == "456"

    # 素材槽非法（空）→ 点按钮 → 数据不动（无弹窗：冒烟用桩替换 QMessageBox）
    from PyQt5.QtWidgets import QMessageBox
    _warn = QMessageBox.warning
    warned = []
    warned_parents = []
    QMessageBox.warning = staticmethod(
        lambda parent, *a, **k: (warned.append(1), warned_parents.append(parent),
                                 QMessageBox.Ok)[2])
    try:
        m3.io.change_value("input", 3, "")
        m3.io.change_value("input", 0, "1")
        m3.io.change_value("input", 1, "2")
        _im.mark_image = lambda data, mode: (data, _FakePos())
        btn.click()
    finally:
        _im.mark_image = _orig_mark
        QMessageBox.warning = _warn
    assert warned == [1]
    assert warned_parents == [None]     # 无父：警告框不在卡片 proxy 内嵌
    assert m3.io.input_value(0) == "1" and m3.io.input_value(1) == "2"   # 未改写

    # ---- 标注预览：原图+红点、无灰色遮罩（用户反馈：预览图是加遮罩的版本） ----
    from PyQt5.QtCore import QBuffer, QRect
    from PyQt5.QtGui import QColor, QImage as _QImage, QPainter as _QPainter
    _big = _QImage(200, 200, _QImage.Format_RGB32)
    _big.fill(QColor(255, 255, 255))
    _buf = QBuffer()
    _buf.open(QBuffer.ReadWrite)
    _big.save(_buf, "PNG")
    pkg.write_file("assets/大图.png", bytes(_buf.data()))
    tree.add("大图", ProjectVariable.create("image", "assets/大图.png", pkg))
    m4 = MouseClick.create_default(tree, pkg)
    m4.io.change_value("input", 3, "{{大图}}")
    view4 = m4.info_widget()

    class _FakePos50:
        points = [(50, 50)]

    def _fake_mark_masked(data, mode):
        """模拟真实 mark_image('dot')：返回整图灰色遮罩合成图 + 坐标。"""
        _masked = _big.copy()
        _pm = _QPainter(_masked)
        _pm.fillRect(QRect(0, 0, 200, 200), QColor(128, 128, 128, 140))
        _pm.end()
        return _masked, _FakePos50()

    _im.mark_image = _fake_mark_masked
    try:
        _btn4 = [b for b in view4.findChildren(QPushButton)
                 if b.text() == "设置点位"][0]
        _btn4.click()
    finally:
        _im.mark_image = _orig_mark
    assert m4.io.input_value(0) == "50" and m4.io.input_value(1) == "50"
    _img4 = view4._preview_pixmap().toImage()
    _c_dot = _img4.pixelColor(50, 50)
    assert _c_dot.red() > 200 and _c_dot.green() < 100, _c_dot.getRgb()   # 红点
    _c_bg = _img4.pixelColor(10, 10)
    assert 100 < _c_bg.red() < 220, _c_bg.getRgb()         # 灰色遮罩压暗（有意保留）
    # 预览由输入 GUI 参数生成：改 x/y → 红点跟随移动
    m4.io.change_value("input", 0, "120")
    m4.io.change_value("input", 1, "80")
    _img5 = view4._preview_pixmap().toImage()
    assert _img5.pixelColor(120, 80).red() > 200          # 新位置红点
    assert _img5.pixelColor(50, 50).red() < 220           # 旧位置只剩遮罩
    # 素材槽清空 → 占位（null）
    m4.io.change_value("input", 3, "")
    assert view4._preview_pixmap().isNull()

    # ---- I4: 视图销毁后监听器不泄漏（弱引用回调；触发 io 变更不崩） ----
    import weakref as _wr
    import gc as _gc
    _v = m3.info_widget()
    _vref = _wr.ref(_v)
    del _v
    _gc.collect()
    assert _vref() is None, "监听器须为弱引用：视图销毁后应可被 GC 回收"
    m3.io.change_value("input", 3, "")          # 死回调路径 → no-op 不崩
    m3.io.change_value("input", 3, "{{图}}")

    print("MouseClick smoke OK")
