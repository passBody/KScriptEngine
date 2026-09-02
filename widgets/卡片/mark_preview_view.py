# -*- coding: utf-8 -*-
"""
素材标注预览视图（可复用控件）
==============================

供鼠标类 action 的自定义卡片视图复用：缩略图（点击 → :class:`ImagePreviewDialog`
独立弹窗查看，查看器不嵌入卡片）+ 「设置点位」按钮（经 ``tools.image_marker``
标注后把坐标经 ``write_points`` 写回输入槽）。

预览画面**读输入 GUI 参数实时生成**（与卡片提示一致）：素材图 + 坐标 → 合成
「遮罩+标注+原图」（:func:`compose_mark`，与 image_marker 的合成一致）；
无素材 → 缩略图占位「无素材」。

基本用法
--------
::

    view = MarkPreviewView(
        io=step.io, image_slot=3, mode="dot",
        read_points=lambda: _read_xy(step),      # -> List[(x,y)] 或 None
        write_points=lambda pts: _write_xy(step, pts),
        hint_text="预览图按当前输入参数实时生成；点击缩略图查看大图")
"""
from typing import Callable, List, Optional, Tuple

from PyQt5.QtCore import QPoint, QRect, QSize, Qt, pyqtSignal
from PyQt5.QtGui import QColor, QPainter, QPen, QPixmap
from PyQt5.QtWidgets import (
    QDialog, QGraphicsPixmapItem, QGraphicsScene, QLabel, QMessageBox,
    QPushButton, QSizePolicy, QVBoxLayout, QWidget,
)

from model.步骤.step_io import StepIOWidget

__all__ = ["ClickPreviewLabel", "ImagePreviewDialog", "MarkPreviewView",
           "compose_mark"]

# 标注样式：与 tools.image_marker 的 _DIM_COLOR/_DOT_COLOR/_DOT_RADIUS 一致
_DIM_COLOR = QColor(128, 128, 128, 140)    # 灰色半透明遮罩（整图）
_DOT_COLOR = QColor(255, 0, 0)             # 标注点（红）
_DOT_RADIUS = 6
_BORDER_COLOR = QColor(0, 175, 255)        # rect 描边
_BORDER_WIDTH = 2
_NUM_COLOR = QColor(255, 255, 255)         # dots 序号颜色（白）

_PREVIEW_MAX_H = 88    # 缩略图最大高度（1k 显示器卡片空间有限）


def _match_var_ref(text: str) -> Optional[str]:
    """``{{变量名}}`` 整串引用 → 变量名；否则 None（与 StepIOWidget 语义一致）。"""
    if text.startswith("{{") and text.endswith("}}") and len(text) > 4:
        return text[2:-2]
    return None


def compose_mark(pixmap: QPixmap, points: List[Tuple[int, int]],
                 mode: str) -> QPixmap:
    """素材原图 → 标注合成图：遮罩 + 标注 + 原图（与 image_marker 各模式一致）。

    * ``dot``：单点红点。
    * ``rect``：两点矩形（框内还原原图 + 蓝色描边）。
    * ``dots``：多点红点 + 白色递增序号。
    """
    out = QPixmap(pixmap)
    p = QPainter(out)
    p.fillRect(QRect(0, 0, out.width(), out.height()), _DIM_COLOR)   # 遮罩
    if mode == "rect" and len(points) >= 2:
        (x1, y1), (x2, y2) = points[0], points[1]
        r = QRect(min(x1, x2), min(y1, y2), abs(x2 - x1) + 1, abs(y2 - y1) + 1)
        p.save()                                    # 框内还原原图（去遮罩）
        p.setClipRect(r)
        p.drawPixmap(0, 0, pixmap)
        p.restore()
        p.setPen(QPen(_BORDER_COLOR, _BORDER_WIDTH))
        p.setBrush(Qt.NoBrush)
        p.drawRect(r)
    else:
        numbered = mode == "dots"
        for i, (x, y) in enumerate(points):
            p.setPen(Qt.NoPen)
            p.setBrush(_DOT_COLOR)
            p.drawEllipse(QPoint(x, y), _DOT_RADIUS, _DOT_RADIUS)
            if numbered:
                p.setPen(_NUM_COLOR)
                p.drawText(x + _DOT_RADIUS + 2, y - _DOT_RADIUS, str(i + 1))
    p.end()
    return out


class ClickPreviewLabel(QLabel):
    """可点击预览缩略图：存原图、**随自身尺寸缩放显示**；左键点击发出 :data:`clicked`。

    随尺寸缩放（resizeEvent 重缩放）是防重叠的关键：卡片空间不足时本标签被
    压缩，若固定高度缩放图会超出标签边界、视觉上压住下方按钮（用户报告）。
    """

    clicked = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._raw: Optional[QPixmap] = None
        self.setAlignment(Qt.AlignCenter)
        # 高度策略（两次踩坑的收敛结论）：
        # * **不能设 minimum**：布局按更小的分配值排布后续控件（按钮），标签却
        #   被 minimum 钳制回原值 → 按钮与标签错位重叠（用户报告「按钮压住
        #   缩略图下半部分」）。
        # * **不能用 Ignored**：Ignored 让布局完全忽略 sizeHint（贡献 0）→
        #   标签被分配 0 高，预览不可见。
        # * 正确 = Expanding + min 0 + max 88：sizeHint（见 sizeHint 覆盖，
        #   与 pixmap 解耦）参与分配、剩余空间吸收、空间不足时压缩——
        #   重叠与 0 高在几何上都不可能。
        self.setMaximumHeight(_PREVIEW_MAX_H)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        self.setStyleSheet("background:#f4f7fc; border:1px solid #d5dbe3;")
        self.setToolTip("点击弹出窗口查看")

    def mousePressEvent(self, event) -> None:  # noqa: N802 (Qt 命名)
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

    def sizeHint(self) -> QSize:  # noqa: N802 (Qt 命名)
        """高度与 pixmap 解耦（固定为最大预览高）。

        QLabel 默认 sizeHint = pixmap 尺寸——若随 pixmap 变化，setPixmap →
        sizeHint 变 → 布局再分配 → resizeEvent 再缩放，负反馈环会把标签
        收敛到 0 高。固定高度后布局按需分配、pixmap 只随分配结果缩放。
        """
        return QSize(super().sizeHint().width(), _PREVIEW_MAX_H)

    def set_raw(self, pix: QPixmap) -> None:
        """存原图并按当前尺寸缩放显示。"""
        self._raw = pix
        self._rescale()

    def clear_image(self, text: str = "无素材") -> None:
        self._raw = None
        self.setPixmap(QPixmap())          # 清掉旧 pixmap，避免文字与图重叠
        self.setText(text)

    def _rescale(self) -> None:
        if self._raw is None or self._raw.isNull():
            return
        size = self.size()
        if size.width() <= 0 or size.height() <= 0:
            size = QSize(_PREVIEW_MAX_H * 2, _PREVIEW_MAX_H)   # 未布局兜底
        self.setText("")
        self.setPixmap(self._raw.scaled(
            size, Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt 命名)
        super().resizeEvent(event)
        self._rescale()


class ImagePreviewDialog(QDialog):
    """素材预览弹出窗口：滚轮缩放 / 拖拽平移 / 双击关闭。

    **无父窗口**：卡片在 QGraphicsView 场景（QGraphicsProxyWidget）中，带父的
    QDialog 会被 proxy 内嵌渲染、嵌在卡片里（同 model.步骤.step_io 默认选择器的
    教训）——故构造不设父，exec_() 无父时应用模态、阻塞主窗口。背景为应用
    背景色（浅色）而非黑色。初始尺寸 = 显示器可用区 2/3；窗口拉伸时图片
    跟随适配缩放（ZoomGraphicsView.resizeEvent）。
    """

    def __init__(self, pixmap: QPixmap) -> None:
        super().__init__()          # 无父窗口 → 独立顶层弹窗
        self.setWindowTitle("素材预览")
        from PyQt5.QtWidgets import QApplication
        _app = QApplication.instance()
        _screen = _app.primaryScreen() if _app is not None else None
        if _screen is not None:
            _g = _screen.availableGeometry()
            self.resize(_g.width() * 2 // 3, _g.height() * 2 // 3)
        else:
            self.resize(640, 480)
        from widgets.通用.image_overlay import ZoomGraphicsView
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


class MarkPreviewView(QWidget):
    """素材标注预览视图：提示 + 缩略图（点击弹窗）+「设置点位」按钮。

    构造参数
    --------
    * ``io``：步骤的 :class:`StepIOWidget`（读素材槽/监听变更）。
    * ``image_slot``：素材图片输入槽下标。
    * ``mode``：``'dot'`` / ``'rect'`` / ``'dots'``（决定 mark_image 模式与合成样式）。
    * ``read_points``：``() -> List[(x,y)] 或 None``——从输入槽读标注点（预览合成用）。
    * ``write_points``：``(List[(x,y)]) -> None``——标注完成后把坐标写回输入槽。
    """

    def __init__(self, io: StepIOWidget, image_slot: int, mode: str,
                 read_points: Callable[[], Optional[List[Tuple[int, int]]]],
                 write_points: Callable[[List[Tuple[int, int]]], None],
                 hint_text: str = "预览图按当前输入参数实时生成；点击缩略图查看大图",
                 mark_button: str = "设置点位",
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._io = io
        self._image_slot = image_slot
        self._mode = mode
        self._read_points = read_points
        self._write_points = write_points

        hint = QLabel(hint_text)
        hint.setStyleSheet("color:#888;")
        hint.setWordWrap(True)

        self.preview_label = ClickPreviewLabel()
        self.preview_label.clicked.connect(self._open_preview)

        self.btn_mark = QPushButton(mark_button)
        self.btn_mark.clicked.connect(self._on_mark)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)                      # 预览与按钮间留足间距（防贴压）
        lay.addWidget(hint)
        lay.addWidget(self.preview_label)      # Expanding 策略负责吸收剩余空间
        lay.addWidget(self.btn_mark)

        self._weak_cb = None            # io 监听弱引用（见 _attach_listener）
        self._attach_listener()
        self._refresh_preview()

    def _attach_listener(self) -> None:
        """素材槽变化 → 刷新预览（弱引用：监听器不持视图强引用，防泄漏）。"""
        import weakref
        self_ref = weakref.ref(self)

        def cb():
            view = self_ref()
            if view is not None:
                view._refresh_preview()

        self._weak_cb = cb
        self._io.add_listener(cb)

    # ---- 预览数据 ----
    def _image_bytes(self) -> Optional[bytes]:
        """素材槽 → 图片字节：``{{变量}}`` 引用 / 包内资源路径常量 / 空 → None。"""
        raw = self._io.input_value(self._image_slot)
        name = _match_var_ref(raw) if isinstance(raw, str) else None
        if name is not None:
            try:
                return self._io.tree.get(name).get_actual_data()
            except (FileNotFoundError, ValueError):
                return None
        if isinstance(raw, str) and raw.strip():
            try:
                return self._io.package.read_file(raw)   # 整合选择器：资源常量
            except (FileNotFoundError, KeyError):
                return None
        return None

    def preview_pixmap(self) -> QPixmap:
        """当前预览画面：**读输入 GUI 参数实时生成**（与卡片提示一致）。

        素材 → 原图；坐标合法 → 合成 遮罩+标注+原图；无素材 → null。
        """
        data = self._image_bytes()
        if not data:
            return QPixmap()                      # null → 占位
        pix = QPixmap()
        if not pix.loadFromData(bytes(data)) or pix.isNull():
            return QPixmap()
        pts = self._read_points()
        if not pts:
            return pix
        return compose_mark(pix, pts, self._mode)

    def _refresh_preview(self) -> None:
        pix = self.preview_pixmap()
        if pix.isNull():
            self.preview_label.clear_image()
        else:
            self.preview_label.set_raw(pix)   # 随标签尺寸缩放（见 ClickPreviewLabel）

    # ---- 弹窗 / 标注 ----
    def _open_preview(self) -> None:
        pix = self.preview_pixmap()
        if pix.isNull():
            return
        dlg = ImagePreviewDialog(pix)     # 无父 → 独立顶层窗口
        dlg.exec_()                        # 应用模态：阻塞主窗口

    def _on_mark(self) -> None:
        data = self._image_bytes()
        if not data:
            QMessageBox.warning(None, self.btn_mark.text(),
                                "请先在输入 GUI 中为「素材图片」选择图片变量")
            return
        from tools.image_marker import mark_image
        try:
            _, pos = mark_image(data, self._mode)   # 合成图弃用：预览自行合成
        except (ValueError, TypeError) as e:
            QMessageBox.warning(None, self.btn_mark.text(), "标注失败：%s" % e)
            return
        if pos is None or not pos.points:
            return                                   # 取消 / 尺寸超屏 → 数据不动
        self._write_points([(int(round(x)), int(round(y)))
                            for x, y in pos.points])
        self._refresh_preview()


# ================================================================
# 冒烟演示：直接 ``python -m widgets.卡片.mark_preview_view`` 运行
# ================================================================
if __name__ == "__main__":
    import sys

    from PyQt5.QtWidgets import QApplication

    from model.工程.kscp_package import KscpPackage
    from model.变量.project_variable import ProjectVariable
    from model.步骤.step_io import StepIOWidget
    from model.变量.variable_tree import VariableTree

    app = QApplication.instance() or QApplication(sys.argv)

    # compose_mark：dot 红点 / rect 框内还原+描边 / dots 序号（像素级断言）
    src = QPixmap(200, 200)
    src.fill(QColor(255, 255, 255))
    img = compose_mark(src, [(50, 50)], "dot").toImage()
    assert img.pixelColor(50, 50).red() > 200 and img.pixelColor(50, 50).green() < 100
    assert 100 < img.pixelColor(10, 10).red() < 220      # 遮罩压暗
    img_r = compose_mark(src, [(20, 20), (80, 80)], "rect").toImage()
    assert img_r.pixelColor(40, 40).red() > 240          # 框内还原原图
    assert img_r.pixelColor(10, 10).red() < 220          # 框外遮罩
    img_d = compose_mark(src, [(30, 30), (90, 90)], "dots").toImage()
    assert img_d.pixelColor(30, 30).red() > 200 and img_d.pixelColor(90, 90).red() > 200

    # MarkPreviewView：占位/刷新/弹窗无父/标注回写（桩替换 mark_image）
    import base64 as _b64
    pkg = KscpPackage.create_empty()
    pkg.write_file("assets/图.png", _b64.b64decode(     # 1×1 RGBA 透明 PNG（真实可解码）
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGNgYGBgAAAABQAB"
        "pfZFQAAAAABJRU5ErkJggg=="))
    tree = VariableTree.create_empty()
    tree.add("图", ProjectVariable.create("image", "assets/图.png", pkg))
    io = StepIOWidget(["number", "number", "image"], [], tree, pkg)
    io.change_value("input", 2, "{{图}}")
    got_points = []
    view = MarkPreviewView(
        io, image_slot=2, mode="dot",
        read_points=lambda: [(100, 100)],
        write_points=lambda pts: got_points.extend(pts))
    assert not view.preview_pixmap().isNull()
    assert view.preview_label.pixmap() is not None
    # 默认提示（用户化文案）：不再用难懂的「通过读输入GUI的参数来生成」
    _hints = [l.text() for l in view.findChildren(QLabel)]
    assert any("点击缩略图查看大图" in t for t in _hints), _hints
    # 弹窗：无父 + 背景浅色（exec 桩替换）
    _dlgs = []
    from PyQt5.QtWidgets import QDialog
    _orig_exec = QDialog.exec_
    QDialog.exec_ = lambda self: (_dlgs.append(self), QDialog.Accepted)[1]
    try:
        view.preview_label.clicked.emit()
    finally:
        QDialog.exec_ = _orig_exec
    assert len(_dlgs) == 1 and isinstance(_dlgs[0], ImagePreviewDialog)
    assert _dlgs[0].parent() is None
    assert _dlgs[0]._view.backgroundBrush().color().name() == "#f4f7fc"
    # 标注回写：桩 mark_image → write_points 收到坐标、预览刷新
    import tools.image_marker as _im
    _orig_mark = _im.mark_image

    class _FakePos:
        points = [(123, 456)]
    _im.mark_image = lambda data, mode: (data, _FakePos())
    try:
        view.btn_mark.click()
    finally:
        _im.mark_image = _orig_mark
    assert got_points == [(123, 456)]
    # 素材槽变化 → 预览刷新（空 → 占位）
    io.change_value("input", 2, "")
    assert view.preview_pixmap().isNull()
    assert view.preview_label.text() == "无素材"

    # 防重叠：纵向压缩 → 标签变小、pixmap 随尺寸缩放不超出标签边界，
    # 按钮顶边始终位于标签底边之下（用户报告：按钮压住预览图下半部分）
    io.change_value("input", 2, "{{图}}")
    view.resize(200, 120)
    view.show()
    app.processEvents()
    _pm = view.preview_label.pixmap()
    assert _pm is not None and not _pm.isNull()
    assert _pm.width() <= view.preview_label.width() + 1, (_pm.width(),
                                                          view.preview_label.width())
    assert _pm.height() <= view.preview_label.height() + 1
    assert view.btn_mark.y() >= view.preview_label.y() + view.preview_label.height()

    # ---- 真实卡片几何（经 StepListView/QGraphicsProxyWidget）：按钮不得压住缩略图 ----
    from model.步骤.step import Step
    from model.步骤.step_list import StepList
    from model.步骤.step_manager import StepManager
    from widgets.卡片.step_list_view import StepClipboard, StepListView

    _pkg2 = KscpPackage.create_empty()
    _pkg2.write_file("actions/示例.py", '''# -*- coding: utf-8 -*-
from dataclasses import dataclass
from model.步骤.step import Step
from model.步骤.step import optional

@dataclass
class _In:
    x: "number" = 0
    y: "number" = 0
    素材: "image" = optional("")

@dataclass
class _Out:
    pass

class DemoStep(Step):
    name = "示例"
    description = "几何探针"
    input_class = _In
    output_class = _Out

    def info_widget(self, parent=None):
        from widgets.卡片.mark_preview_view import MarkPreviewView
        return MarkPreviewView(
            io=self.io, image_slot=2, mode="dot",
            read_points=lambda: [(1, 1)],
            write_points=lambda pts: None, parent=parent)

    def run(self) -> int:
        return 1
'''.encode("utf-8"))
    _tree2 = VariableTree.create_empty()
    _mgr2 = StepManager(_pkg2, _tree2)
    _mgr2.load()
    _s2 = _mgr2.create_step("示例")
    _sl2 = StepList.create_empty()
    _sl2.add(_s2)
    _view2 = StepListView(_mgr2, StepClipboard())
    _view2.set_list(_sl2, _mgr2)
    _view2.resize(760, 400)
    _view2.show()
    app.processEvents()
    _card2 = _view2.cards[0]
    _labels = [l for l in _card2.findChildren(QLabel)
               if l.toolTip() == "点击弹出窗口查看"]
    _buttons = [b for b in _card2.findChildren(QPushButton)
                if b.text() == "设置点位"]
    assert len(_labels) == 1 and len(_buttons) == 1
    _lb, _bt = _labels[0], _buttons[0]
    assert _bt.y() >= _lb.y() + _lb.height(), \
        (_bt.y(), _lb.y(), _lb.height())          # 修复前：按钮压住缩略图
    assert _lb.height() > 0, _lb.height()         # 修复前（Ignored）：0 高不可见

    print("MarkPreviewView smoke OK")
