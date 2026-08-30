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
import weakref
from dataclasses import dataclass
from typing import Any, Optional

from PyQt5.QtGui import QImage, QPixmap
from PyQt5.QtWidgets import (
    QDialog, QGraphicsPixmapItem, QGraphicsScene, QHBoxLayout, QLabel,
    QMessageBox, QPushButton, QVBoxLayout, QWidget,
)

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
        """自定义视图：提示 + 预览/设置点位按钮（见 _MouseInfoView）。"""
        return _MouseInfoView(self, parent)


_VAR_REF = re.compile(r"^\{\{(.+)\}\}$")


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


def _notify_preview_weak(view_ref) -> None:
    """弱引用回调：视图已销毁 → no-op（io 监听器不持视图强引用，避免泄漏）。"""
    view = view_ref()
    if view is not None:
        view._on_io_changed()


class _ImagePreviewDialog(QDialog):
    """素材预览弹出窗口：滚轮缩放 / 拖拽平移 / 双击关闭。

    **无父窗口**：卡片在 QGraphicsView 场景（QGraphicsProxyWidget）中，带父的
    QDialog 会被 proxy 内嵌渲染、嵌在卡片里（同 model.step_io 默认选择器的
    教训）——故构造不设父，exec_() 无父时应用模态、阻塞主窗口。背景为应用
    背景色（浅色）而非黑色。每次打开新建，画面取当前预览（标注图优先，否则素材原图）。
    """

    def __init__(self, pixmap: QPixmap) -> None:
        super().__init__()          # 无父窗口 → 独立顶层弹窗
        self.setWindowTitle("素材预览")
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

    布局（卡片内**不显示**任何预览画面——预览只存在于独立弹窗中）：
    * 提示标签：「自定义视图中的预览图的画面是通过读输入GUI的参数来生成」
    * 「预览」按钮 → _ImagePreviewDialog 独立弹窗查看（数据源 = 素材图片输入槽）
    * 「设置点位」按钮 → mark_image('dot') → 坐标回写 x/y 输入槽
    """

    def __init__(self, step: "MouseClick", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._step = step
        self._marked: Optional[QPixmap] = None   # 标注结果（内存，槽未变时保持）

        hint = QLabel("自定义视图中的预览图的画面是通过读输入GUI的参数来生成")
        hint.setStyleSheet("color:#888;")
        hint.setWordWrap(True)

        self._btn_preview = QPushButton("预览")
        self._btn_preview.setToolTip("弹出独立窗口查看素材预览")
        self._btn_preview.clicked.connect(self._open_preview)

        self._btn_mark = QPushButton("设置点位")
        self._btn_mark.clicked.connect(self._on_mark)

        row = QHBoxLayout()
        row.setSpacing(6)
        row.addWidget(self._btn_preview)
        row.addWidget(self._btn_mark)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        lay.addWidget(hint)
        lay.addLayout(row)

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
        """当前预览画面：标注图（素材槽未变时）优先，否则素材原图；无素材 → null。"""
        if self._marked is not None:
            return QPixmap(self._marked)
        data = self._image_bytes()
        if not data:
            return QPixmap()                      # null → 占位
        pix = QPixmap()
        pix.loadFromData(bytes(data))
        return pix

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
        # 素材槽变化 → 标注结果失效；预览按钮可用性随素材有无刷新
        self._marked = None
        self._btn_preview.setEnabled(not self._preview_pixmap().isNull())

    # ---- 设置点位 ----
    def _on_mark(self) -> None:
        data = self._image_bytes()
        if not data:
            QMessageBox.warning(None, "设置点位",
                                "请先在输入 GUI 中为「素材图片」选择图片变量")
            return
        from tools.image_marker import mark_image
        try:
            marked_img, pos = mark_image(data, "dot")
        except (ValueError, TypeError) as e:
            QMessageBox.warning(None, "设置点位", "标注失败：%s" % e)
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
        self._btn_preview.setEnabled(not self._preview_pixmap().isNull())


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
    # 三个要素：提示标签、预览按钮、设置点位按钮；卡片内**不显示**预览画面
    from PyQt5.QtWidgets import QLabel, QPushButton
    labels = view.findChildren(QLabel)
    btns = view.findChildren(QPushButton)
    assert any("预览图的画面是通过读输入GUI的参数来生成" in l.text() for l in labels)
    assert any(b.text() == "设置点位" for b in btns)
    assert any(b.text() == "预览" for b in btns)
    assert not hasattr(view, "_preview")             # 卡片内无嵌入的预览控件
    btn = [b for b in btns if b.text() == "设置点位"][0]
    pbtn = [b for b in btns if b.text() == "预览"][0]
    # 预览按钮可用性跟随素材槽（有素材可点、空槽禁用）
    assert not view._preview_pixmap().isNull()   # 已有 {{图}} → 非占位
    assert pbtn.isEnabled()
    m3.io.change_value("input", 3, "")
    assert view._preview_pixmap().isNull()       # 空槽 → 占位（null 图）
    assert not pbtn.isEnabled()                  # 无素材 → 预览不可点
    m3.io.change_value("input", 3, "{{图}}")
    assert not view._preview_pixmap().isNull()
    assert pbtn.isEnabled()

    # 点击预览按钮 → 独立弹窗：**无父窗口**（带父的 QDialog 在
    # QGraphicsProxyWidget 内会被内嵌渲染 —— 同 model.step_io 默认选择器教训）
    _captured = []
    from PyQt5.QtWidgets import QDialog
    _orig_exec = QDialog.exec_
    QDialog.exec_ = lambda self: (_captured.append(self), QDialog.Accepted)[1]
    try:
        pbtn.click()
    finally:
        QDialog.exec_ = _orig_exec
    assert len(_captured) == 1 and isinstance(_captured[0], _ImagePreviewDialog)
    assert _captured[0].parent() is None              # 独立顶层窗口，不嵌入卡片

    # 预览弹窗：背景 = 应用背景色（浅色，非黑）
    dlg = _ImagePreviewDialog(view._preview_pixmap())
    assert dlg._view.scene() is dlg._scene
    assert dlg._view.backgroundBrush().color().name() == "#f4f7fc"
    items = dlg._scene.items()
    assert len(items) == 1 and not items[0].pixmap().isNull()

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
