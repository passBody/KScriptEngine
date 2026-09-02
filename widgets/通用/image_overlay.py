# -*- coding: utf-8 -*-
"""
图片遮罩预览（可复用控件）
========================

:class:`ImageOverlay` 在父窗口上盖一层半透明遮罩，居中显示一张可滚轮缩放、
拖拽平移、双击关闭的图片。资源树预览、image 变量预览共用本控件。
背景为应用背景色（浅色）而非黑色（用户反馈黑色突兀）。

:class:`ZoomGraphicsView` 为可单独复用的缩放/平移图片视图（背景同浅色），
供弹出式预览窗口（如「鼠标点击」素材预览）嵌入使用。

基本用法
--------
::

    from widgets import ImageOverlay
    ov = ImageOverlay(pixmap, parent_window)
    ov.show_overlay()      # 盖到 parent 上
    # 用户：滚轮缩放/拖拽/双击关闭；Esc 或点击空白处关闭
"""

from __future__ import annotations

from typing import Optional

from PyQt5.QtCore import QEvent, QSize, Qt, pyqtSignal
from PyQt5.QtGui import QColor, QPainter, QPixmap
from PyQt5.QtWidgets import (
    QGraphicsPixmapItem, QGraphicsScene, QGraphicsView, QHBoxLayout,
    QLabel, QVBoxLayout, QWidget,
)

__all__ = ["ImageOverlay", "ZoomGraphicsView"]

# 查看器背景：与应用浅色主题一致（黑色突兀，用户反馈）
_VIEW_BG = "#f4f7fc"


class ZoomGraphicsView(QGraphicsView):
    """滚轮缩放 + 拖拽平移的图片视图；双击发出 :data:`doubleClicked`。"""

    doubleClicked = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setDragMode(QGraphicsView.ScrollHandDrag)   # 鼠标拖拽平移
        self.setRenderHint(QPainter.Antialiasing)
        self.setResizeAnchor(QGraphicsView.AnchorUnderMouse)
        self.setBackgroundBrush(QColor(_VIEW_BG))
        self._zoom = 1.0
        self._last_size = QSize()   # 上次 widget 尺寸：区分窗口拉伸 vs 滚轮缩放致的滚动条变化

    def wheelEvent(self, event) -> None:  # noqa: N802 (Qt 命名)
        factor = 1.25 if event.angleDelta().y() > 0 else 1 / 1.25
        new = self._zoom * factor
        if 0.05 < new < 50:
            self._zoom = new
            self.scale(factor, factor)

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802 (Qt 命名)
        self.doubleClicked.emit()      # 双击 → 关闭遮罩（由 ImageOverlay 连接）

    def fit_view(self) -> None:
        self._zoom = 1.0
        self.resetTransform()
        if self.scene() is not None:
            self.fitInView(self.scene().sceneRect(), Qt.KeepAspectRatio)
        self._last_size = self.size()

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt 命名)
        super().resizeEvent(event)
        if self.scene() is None:
            return
        # 仅 widget 自身尺寸变化（窗口拉伸）时重新适配。滚轮放大→图片超出视口→
        # 滚动条出现也会触发 resizeEvent，但 widget 尺寸不变（== _last_size）→ 不重置，
        # 否则放大被立即还原（表现为「只能缩小不能放大」）。窗口拉伸 → 尺寸变化 → 适配。
        if self._last_size.isValid() and self.size() == self._last_size:
            return
        self._last_size = self.size()
        self.fit_view()


class ImageOverlay(QWidget):
    """半透明遮罩（浅色）+ 居中可缩放拖拽图片（可复用）。"""

    def __init__(self, pixmap: QPixmap, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._pixmap = pixmap
        self.setWindowFlags(Qt.SubWindow)        # 仍属父窗口，但能盖在兄弟控件之上
        self.setFocusPolicy(Qt.StrongFocus)

        self._view = ZoomGraphicsView(self)
        self._scene = QGraphicsScene(self)
        self._item = QGraphicsPixmapItem(pixmap)
        self._scene.addItem(self._item)
        self._view.setScene(self._scene)
        self._view.doubleClicked.connect(self.close_overlay)   # 双击图片 → 关闭遮罩

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        bar = QHBoxLayout()
        bar.setContentsMargins(6, 4, 6, 4)
        self._hint = QLabel("滚轮缩放 · 拖拽平移 · 双击关闭 · Esc/点击空白 关闭")
        self._hint.setAlignment(Qt.AlignCenter)
        self._hint.setStyleSheet("color:#666; background:#eef1f6; padding:3px;")
        bar.addWidget(self._hint)
        lay.addLayout(bar)
        lay.addWidget(self._view, 1)

    def show_overlay(self) -> None:
        """盖到父窗口全屏并显示、聚焦；父窗口 resize 时跟随（事件过滤器）。"""
        p = self.parentWidget()
        if p is not None:
            self.setGeometry(p.rect())
            p.installEventFilter(self)     # 宿主拖动窗口/面板 → 遮罩同步拉伸，避免割裂
        self.raise_()
        self.show()
        self.setFocus()
        self._view.fit_view()

    def close_overlay(self) -> None:
        p = self.parentWidget()
        if p is not None:
            p.removeEventFilter(self)
        self.hide()

    def eventFilter(self, obj, event) -> bool:  # noqa: N802 (Qt 命名)
        # 宿主 resize → 遮罩跟随；只响应父窗口自身，事件不吞掉
        if (obj is self.parentWidget() and event.type() == QEvent.Resize
                and not self.isHidden()):
            self.setGeometry(self.parentWidget().rect())
        return super().eventFilter(obj, event)

    def keyPressEvent(self, event) -> None:  # noqa: N802 (Qt 命名)
        if event.key() == Qt.Key_Escape:
            self.close_overlay()
        else:
            super().keyPressEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt 命名)
        # 半透明白色遮罩底色（浅色主题；_view 自有不透明背景盖住中心，四周呈遮罩色）
        from PyQt5.QtGui import QPainter
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(255, 255, 255, 170))

    def mousePressEvent(self, event) -> None:  # noqa: N802 (Qt 命名)
        # 点击遮罩空白（_view 之外）→ 关闭；_view 内部点击由其自行处理不冒泡
        if event.button() == Qt.LeftButton:
            self.close_overlay()
        super().mousePressEvent(event)


if __name__ == "__main__":
    import sys
    from PyQt5.QtWidgets import QApplication
    from PyQt5.QtGui import QColor, QImage
    from PyQt5.QtCore import QBuffer

    app = QApplication.instance() or QApplication(sys.argv)

    img = QImage(120, 80, QImage.Format_RGB32)
    img.fill(QColor("#3a7bd5"))
    buf = QBuffer(); buf.open(QBuffer.ReadWrite)
    img.save(buf, "PNG")
    pix = QPixmap()
    pix.loadFromData(bytes(buf.data()))

    host = QWidget()
    host.resize(400, 300)
    host.setStyleSheet("background:#fff;")
    host.show()                        # 遮罩跟随依赖宿主已显示（未显示 widget 不发 resize 事件）
    app.processEvents()
    ov = ImageOverlay(pix, host)
    assert ov._item in ov._scene.items()
    assert not ov._item.pixmap().isNull()
    # 查看器背景 = 应用背景色（浅色），非黑（用户反馈黑色突兀）
    assert isinstance(ov._view, ZoomGraphicsView)
    assert ov._view.backgroundBrush().color().name() == "#f4f7fc"
    ov.show_overlay()        # 不抛错（父窗口未 show，实际可见需运行时父窗口可见）
    assert not ov.isHidden()
    ov.close_overlay()
    assert ov.isHidden()     # close_overlay 后置隐藏
    # 双击图片 → doubleClicked 信号 → close_overlay（连线验证，绕过真实鼠标事件）
    ov.show_overlay()
    assert not ov.isHidden()
    got = []
    ov._view.doubleClicked.connect(lambda: got.append(1))
    ov._view.doubleClicked.emit()
    assert got == [1]
    assert ov.isHidden()     # doubleClicked → close_overlay → 隐藏

    # ---- 14e：宿主 resize → 遮罩跟随（修复「拉动窗口预览窗口不变、画面割裂」） ----
    ov.show_overlay()
    assert ov.geometry() == host.rect()
    m11_before = ov._view.transform().m11()      # 适配后初始缩放
    assert m11_before > 1.0
    host.resize(500, 400)
    app.processEvents()
    assert ov.geometry() == host.rect()          # 宿主变宽 → 遮罩同步拉伸
    assert ov._view.transform().m11() > m11_before * 1.2   # 图片随窗口拉伸跟随缩放
    ov.close_overlay()
    assert ov.isHidden()
    host.resize(600, 450)                        # 已关闭 → 不再跟随、无副作用
    app.processEvents()
    assert ov.isHidden()
    ov.show_overlay()                            # 再开后仍跟随
    host.resize(420, 330)
    app.processEvents()
    assert ov.geometry() == host.rect()
    ov.close_overlay()

    # ---- Fix：滚轮放大不被 resizeEvent→fit_view 重置（修「只能缩小不能放大」） ----
    _zv = ZoomGraphicsView()
    _zsc = QGraphicsScene()
    _zpix = QPixmap(400, 400); _zpix.fill(QColor("#3a7bd5"))
    _zsc.addItem(QGraphicsPixmapItem(_zpix))
    _zv.setScene(_zsc)
    _zv.resize(600, 400)
    _zv.show()
    app.processEvents()
    _zv.fit_view()
    app.processEvents()
    _m0 = _zv.transform().m11()
    _zv.scale(1.25, 1.25); _zv._zoom = 1.25      # 模拟滚轮向上（放大）
    app.processEvents()                           # 让滚动条/resize 事件处理
    assert _zv.transform().m11() > _m0 * 1.1, "滚轮放大应生效（不被 resizeEvent 重置）"
    # 模拟滚轮向下（缩小）：从适配态重新开始（放大再缩小 = 净 1.0 测不出缩小）
    _zv.fit_view(); app.processEvents()
    _zv.scale(1 / 1.25, 1 / 1.25); _zv._zoom = 0.8
    app.processEvents()
    assert _zv.transform().m11() < _m0 * 0.95, "滚轮缩小应生效"
    _zv.close()

    print("ImageOverlay smoke OK")
