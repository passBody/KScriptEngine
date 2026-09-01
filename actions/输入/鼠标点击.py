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
import re
import weakref
from dataclasses import dataclass
from typing import Any, Optional, Tuple

from PyQt5.QtCore import QPoint, QRect, Qt, pyqtSignal
from PyQt5.QtGui import QColor, QPainter, QPixmap
from PyQt5.QtWidgets import (
    QDialog, QGraphicsPixmapItem, QGraphicsScene, QLabel,
    QMessageBox, QPushButton, QVBoxLayout, QWidget,
)

from libs.key_control import InputControl
from model.step import Step, optional

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


_VAR_REF = re.compile(r"^\{\{(.+)\}\}$")
_PREVIEW_H = 120   # 卡片内缩略图高度（点击 → 弹出窗口查看）


# 标注样式：与 tools.image_marker 的 _DIM_COLOR / _DOT_COLOR / _DOT_RADIUS 一致
_DIM_COLOR = QColor(128, 128, 128, 140)    # 灰色半透明遮罩（整图）
_DOT_COLOR = QColor(255, 0, 0)             # 标注点（红）
_DOT_RADIUS = 6


def _mark_composite_pixmap(src: QPixmap, x: int, y: int) -> QPixmap:
    """素材原图 → 标注合成图：**遮罩 + 红点 + 原图**（与 image_marker 'dot' 结果一致）。

    预览不直接用 mark_image 的返回图——mark_image 只提供坐标，预览由输入 GUI
    的参数（素材 + x/y）自行合成；x/y 变化时红点跟随移动。
    """
    out = QPixmap(src)
    p = QPainter(out)
    p.fillRect(QRect(0, 0, out.width(), out.height()), _DIM_COLOR)   # 遮罩
    p.setPen(Qt.NoPen)
    p.setBrush(_DOT_COLOR)
    p.drawEllipse(QPoint(x, y), _DOT_RADIUS, _DOT_RADIUS)            # 红点
    p.end()
    return out


def _notify_preview_weak(view_ref) -> None:
    """弱引用回调：视图已销毁 → no-op（io 监听器不持视图强引用，避免泄漏）。"""
    view = view_ref()
    if view is not None:
        view._on_io_changed()


class _ClickPreview(QLabel):
    """可点击预览缩略图：左键点击发出 :data:`clicked`（→ 弹出窗口查看）。"""

    clicked = pyqtSignal()

    def mousePressEvent(self, event) -> None:  # noqa: N802 (Qt 命名)
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class _ImagePreviewDialog(QDialog):
    """素材预览弹出窗口：滚轮缩放 / 拖拽平移 / 双击关闭。

    **无父窗口**：卡片在 QGraphicsView 场景（QGraphicsProxyWidget）中，带父的
    QDialog 会被 proxy 内嵌渲染、嵌在卡片里（同 model.step_io 默认选择器的
    教训）——故构造不设父，exec_() 无父时应用模态、阻塞主窗口。背景为应用
    背景色（浅色）而非黑色。初始尺寸 = 显示器可用区 2/3；窗口拉伸时图片
    跟随适配缩放（ZoomGraphicsView.resizeEvent）。每次打开新建，画面 = 当前
    预览（读输入 GUI 参数合成：遮罩+红点+原图；无标注坐标时为原图）。
    """

    def __init__(self, pixmap: QPixmap) -> None:
        super().__init__()          # 无父窗口 → 独立顶层弹窗
        self.setWindowTitle("素材预览")
        # 初始尺寸 = 显示器可用区 2/3（窗口拉伸时图片跟随适配，见 ZoomGraphicsView）
        from PyQt5.QtWidgets import QApplication
        _app = QApplication.instance()
        _screen = _app.primaryScreen() if _app is not None else None
        if _screen is not None:
            _g = _screen.availableGeometry()
            self.resize(_g.width() * 2 // 3, _g.height() * 2 // 3)
        else:
            self.resize(640, 480)
        from widgets.image_overlay import ZoomGraphicsView
        self._view = ZoomGraphicsView(self)
        self._scene = QGraphicsScene(self)
        self._scene.addItem(QGraphicsPixmapItem(pixmap))
        self._view.setScene(self._scene)
        self._view.doubleClicked.connect(self.accept)   # 双击图片 → 关闭
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self._view)

    def showEvent(self, event) -> None:  # noqa: N802 (Qt 命名)
        super().showEvent(event)
        self._view.fit_view()            # 显示后几何就绪 → 适配窗口


class _MouseInfoView(QWidget):
    """鼠标点击步骤的自定义卡片视图。

    布局：
    * 提示标签：「自定义视图中的预览图的画面是通过读输入GUI的参数来生成」
    * 预览缩略图（点击 → _ImagePreviewDialog **弹出窗口**查看；查看器不嵌入卡片）
    * 「设置点位」按钮 → mark_image('dot') → 坐标回写 x/y 输入槽
    """

    def __init__(self, step: "MouseClick", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._step = step

        hint = QLabel("自定义视图中的预览图的画面是通过读输入GUI的参数来生成")
        hint.setStyleSheet("color:#888;")
        hint.setWordWrap(True)

        self._preview = _ClickPreview()
        self._preview.setAlignment(Qt.AlignCenter)
        self._preview.setMinimumHeight(_PREVIEW_H)
        self._preview.setStyleSheet("background:#f4f7fc; border:1px solid #d5dbe3;")
        self._preview.setToolTip("点击弹出窗口查看")
        self._preview.clicked.connect(self._open_preview)

        self._btn_mark = QPushButton("设置点位")
        self._btn_mark.clicked.connect(self._on_mark)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        lay.addWidget(hint)
        lay.addWidget(self._preview)
        lay.addWidget(self._btn_mark)

        self_ref = weakref.ref(self)                 # 弱引用：监听器不持视图强引用
        self._weak_cb = lambda r=self_ref: _notify_preview_weak(r)
        step.io.add_listener(self._weak_cb)          # 素材槽变化 → 刷新预览
        self._on_io_changed()

    # ---- 预览 ----
    def _slot_value(self) -> str:
        return self._step.io.input_value(MouseClick.IMAGE_SLOT)

    def _image_bytes(self) -> Optional[bytes]:
        """素材图片槽 → 实际图片字节；槽为空/非引用/变量缺失 → None。"""
        raw = self._slot_value()
        m = _VAR_REF.match(raw) if isinstance(raw, str) else None
        if not m:
            return None
        try:
            return self._step.io.tree.get(m.group(1)).get_actual_data()
        except (FileNotFoundError, ValueError):
            return None

    def _preview_pixmap(self) -> QPixmap:
        """当前预览画面：**读输入 GUI 参数实时生成**（与卡片提示一致）。

        素材图片槽 → 原图；x/y 槽为数值 → 合成 遮罩+红点+原图（红点跟随
        x/y 移动）；x/y 非数值（未标注/手误）→ 原图；无素材 → null。
        """
        data = self._image_bytes()
        if not data:
            return QPixmap()                      # null → 占位
        pix = QPixmap()
        if not pix.loadFromData(bytes(data)) or pix.isNull():
            return QPixmap()
        xy = self._dot_position()
        if xy is None:
            return pix
        return _mark_composite_pixmap(pix, xy[0], xy[1])

    def _dot_position(self) -> Optional[Tuple[int, int]]:
        """从输入 GUI 的 x/y 槽读标注点（四舍五入取整）；非数值 → None。"""
        try:
            x = int(round(float(self._step.io.input_value(0).strip())))
            y = int(round(float(self._step.io.input_value(1).strip())))
            return x, y
        except (ValueError, TypeError):
            return None

    def _refresh_preview(self) -> None:
        """缩略图随当前预览刷新：无素材 → 占位文字；有 → 等比缩放缩略图。"""
        pix = self._preview_pixmap()
        if pix.isNull():
            self._preview.setText("无素材")
        else:
            self._preview.setText("")
            self._preview.setPixmap(pix.scaledToHeight(
                _PREVIEW_H - 8, Qt.SmoothTransformation))

    def _open_preview(self) -> None:
        """独立弹窗查看当前预览（标注图优先，否则素材原图）；无素材不弹。

        不设父窗口（见 _ImagePreviewDialog）；exec_() 无父时应用模态 → 阻塞主窗口。
        """
        pix = self._preview_pixmap()
        if pix.isNull():
            return
        dlg = _ImagePreviewDialog(pix)     # 无父 → 独立顶层窗口
        dlg.exec_()                        # 应用模态：阻塞主窗口

    # ---- 槽变化 ----
    def _on_io_changed(self) -> None:
        # 素材 / x / y 槽变化 → 预览按输入 GUI 参数重新合成
        self._refresh_preview()

    # ---- 设置点位 ----
    def _on_mark(self) -> None:
        data = self._image_bytes()
        if not data:
            QMessageBox.warning(None, "设置点位",
                                "请先在输入 GUI 中为「素材图片」选择图片变量")
            return
        from tools.image_marker import mark_image
        try:
            _, pos = mark_image(data, "dot")   # 合成图（带灰色遮罩）弃用：预览自行画红点
        except (ValueError, TypeError) as e:
            QMessageBox.warning(None, "设置点位", "标注失败：%s" % e)
            return
        if pos is None or not pos.points:
            return                                   # 取消 / 尺寸超屏 → 数据不动
        x, y = pos.points[0]
        # 坐标写回 x/y 输入槽 → io 监听触发 _on_io_changed → 预览按输入 GUI
        # 参数重新合成（遮罩 + 红点 + 原图）；此处兜底再刷一次
        self._step.io.change_value("input", 0, str(int(x)))
        self._step.io.change_value("input", 1, str(int(y)))
        self._refresh_preview()


# ================================================================
# 冒烟演示：直接 ``python -m actions.输入.鼠标点击`` 运行
# ================================================================
if __name__ == "__main__":
    import sys
    import base64 as _b64

    from PyQt5.QtWidgets import QApplication

    from model.kscp_package import KscpPackage
    from model.project_variable import ProjectVariable
    from model.variable_tree import VariableTree

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
    from model.project_variable import ProjectVariable
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
    assert not view._preview_pixmap().isNull()   # 已有 {{图}} → 非占位
    assert view._preview.pixmap() is not None
    assert not view._preview.pixmap().isNull()
    assert view._preview.text() == ""
    m3.io.change_value("input", 3, "")
    assert view._preview_pixmap().isNull()       # 空槽 → 占位（null 图）
    assert view._preview.text() == "无素材"
    m3.io.change_value("input", 3, "{{图}}")
    assert not view._preview_pixmap().isNull()

    # 点击缩略图 → 独立弹窗：**无父窗口**（父窗口在 QGraphicsProxyWidget 内
    # 会被 proxy 内嵌渲染、嵌在卡片里 —— 同 model.step_io 默认选择器的教训）
    _captured = []
    from PyQt5.QtWidgets import QDialog
    _orig_exec = QDialog.exec_
    QDialog.exec_ = lambda self: (_captured.append(self), QDialog.Accepted)[1]
    try:
        view._preview.clicked.emit()
    finally:
        QDialog.exec_ = _orig_exec
    assert len(_captured) == 1 and isinstance(_captured[0], _ImagePreviewDialog)
    assert _captured[0].parent() is None              # 独立顶层窗口，不嵌入卡片

    # 预览弹窗：背景 = 应用背景色（浅色，非黑）；初始尺寸 = 显示器可用区 2/3
    dlg = _ImagePreviewDialog(view._preview_pixmap())
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
