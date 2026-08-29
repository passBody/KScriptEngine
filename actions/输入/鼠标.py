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
* ``素材图片``（image）：**编辑期辅助**，仅用于自定义视图的点位标注与预览；
  ``run()`` 不读取它。

> 模拟输入到游戏窗口需以管理员身份运行 KScript。
"""
import re
from dataclasses import dataclass
from typing import Any, Optional

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QImage, QPixmap
from PyQt5.QtWidgets import QLabel, QMessageBox, QPushButton, QVBoxLayout, QWidget

from libs.key_control import InputControl
from model.step import Step

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
    素材图片: "image" = ""  # type: ignore


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
_PREVIEW_H = 120


def _to_pixmap(image: Any) -> Optional[QPixmap]:
    """mark_image 返回的多种类型 → QPixmap；不可解析 → None。"""
    if isinstance(image, QPixmap):
        return image
    if isinstance(image, QImage):
        return QPixmap.fromImage(image)
    if isinstance(image, (bytes, bytearray)):
        pix = QPixmap()
        return pix if pix.loadFromData(bytes(image)) else None
    # numpy.ndarray(HxWx3, uint8)：bytes 输入时 mark_image 优先返回该类型
    if hasattr(image, "tobytes") and getattr(image, "ndim", 0) == 3:
        h, w = image.shape[0], image.shape[1]
        qimg = QImage(image.tobytes(), w, h, w * image.shape[2],
                      QImage.Format_RGB888)
        return QPixmap.fromImage(qimg.copy())
    return None


class _ClickPreview(QLabel):
    """可点击预览图：左键点击发出 :data:`clicked`。"""

    clicked = pyqtSignal()

    def mousePressEvent(self, event) -> None:  # noqa: N802 (Qt 命名)
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class _MouseInfoView(QWidget):
    """鼠标点击步骤的自定义卡片视图。

    布局：
    * 提示标签：「自定义视图中的预览图的画面是通过读输入GUI的参数来生成」
    * 预览图（点击 → ImageOverlay 大图）；数据源 = 素材图片输入槽
    * 「设置点位」按钮 → mark_image('dot') → 坐标回写 x/y 输入槽
    """

    def __init__(self, step: "MouseClick", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._step = step
        self._marked: Optional[QPixmap] = None   # 标注结果（内存，槽未变时保持）

        hint = QLabel("自定义视图中的预览图的画面是通过读输入GUI的参数来生成")
        hint.setStyleSheet("color:#888;")
        hint.setWordWrap(True)

        self._preview = _ClickPreview()
        self._preview.setAlignment(Qt.AlignCenter)
        self._preview.setMinimumHeight(_PREVIEW_H)
        self._preview.setStyleSheet("background:#1e1e1e; border:1px solid #444;")
        self._preview.clicked.connect(self._open_overlay)

        self._btn_mark = QPushButton("设置点位")
        self._btn_mark.clicked.connect(self._on_mark)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        lay.addWidget(hint)
        lay.addWidget(self._preview)
        lay.addWidget(self._btn_mark)

        step.io.add_listener(self._on_io_changed)   # 素材槽变化 → 刷新预览
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
        """当前预览画面：标注图（素材槽未变时）优先，否则素材原图；无素材 → null。"""
        if self._marked is not None:
            return QPixmap(self._marked)
        data = self._image_bytes()
        if not data:
            return QPixmap()                      # null → 占位
        pix = QPixmap()
        pix.loadFromData(bytes(data))
        return pix

    def _refresh_preview(self) -> None:
        pix = self._preview_pixmap()
        if pix.isNull():
            self._preview.setText("无素材")
        else:
            self._preview.setText("")
            self._preview.setPixmap(pix.scaledToHeight(
                _PREVIEW_H - 8, Qt.SmoothTransformation))

    def _open_overlay(self) -> None:
        pix = self._preview_pixmap()
        if pix.isNull():
            return
        from widgets.image_overlay import ImageOverlay
        host = self.window() or self
        ov = ImageOverlay(pix, host)
        ov.show_overlay()
        self._overlay = ov                      # 持有引用防回收（关闭后由用户行为自然释放）

    # ---- 槽变化 ----
    def _on_io_changed(self) -> None:
        # 素材槽变化 → 标注结果失效，回到原图预览
        self._marked = None
        self._refresh_preview()

    # ---- 设置点位 ----
    def _on_mark(self) -> None:
        data = self._image_bytes()
        if not data:
            QMessageBox.warning(self, "设置点位", "请先在输入 GUI 中为「素材图片」选择图片变量")
            return
        from tools.image_marker import mark_image
        try:
            marked_img, pos = mark_image(data, "dot")
        except (ValueError, TypeError) as e:
            QMessageBox.warning(self, "设置点位", "标注失败：%s" % e)
            return
        if pos is None or not pos.points:
            return                                   # 取消 / 尺寸超屏 → 数据不动
        x, y = pos.points[0]
        # change_value 触发 io 监听 → _on_io_changed 先把 _marked 置空刷新原图，
        # 随后用标注图覆盖（带红点回显）
        self._step.io.change_value("input", 0, str(int(x)))
        self._step.io.change_value("input", 1, str(int(y)))
        pix = _to_pixmap(marked_img)
        if pix is not None and not pix.isNull():
            self._marked = pix
        self._refresh_preview()


# ================================================================
# 冒烟演示：直接 ``python -m actions.输入.鼠标`` 运行
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

    # 素材图片槽是 image 资源：空值过不了 StepIOWidget 校验（input() 先于 run()
    # 抛 ValueError），必须引用工程资源变量（run() 不读取它，仅满足槽校验）
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

    # 往返
    fmt = m.to_format_string()
    assert "=" not in fmt and "+" not in fmt and "/" not in fmt
    m2 = MouseClick.from_format_string(fmt, tree, pkg)
    assert isinstance(m2, MouseClick)
    assert m2.io.to_format_string() == m.io.to_format_string()

    # ---- info_widget：提示标签 + 预览 + 设置点位 ----
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
    # 三个要素：提示标签文字、预览、设置点位按钮
    from PyQt5.QtWidgets import QLabel, QPushButton
    labels = view.findChildren(QLabel)
    btns = view.findChildren(QPushButton)
    assert any("预览图的画面是通过读输入GUI的参数来生成" in l.text() for l in labels)
    assert any(b.text() == "设置点位" for b in btns)
    btn = [b for b in btns if b.text() == "设置点位"][0]
    # 素材槽变化 → 预览刷新（占位 → 真图）
    assert not view._preview_pixmap().isNull()   # 已有 {{图}} → 非占位
    m3.io.change_value("input", 3, "")
    assert view._preview_pixmap().isNull()       # 空槽 → 占位（null 图）
    m3.io.change_value("input", 3, "{{图}}")
    assert not view._preview_pixmap().isNull()

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
    QMessageBox.warning = staticmethod(lambda *a, **k: warned.append(1) or QMessageBox.Ok)
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
    assert m3.io.input_value(0) == "1" and m3.io.input_value(1) == "2"   # 未改写

    print("MouseClick smoke OK")
