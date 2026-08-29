# -*- coding: utf-8 -*-
"""
图片标注工具（PyQt5）
=====================

提供两个对外函数：

* :func:`mark_image` —— 全屏打开图片，按模式标注 / 展示，返回图片与坐标信息。
* :func:`save_png`    —— 把（标注后的）图片保存为 PNG 文件。

函数签名
--------
    mark_image(image_data, mode) -> (image, pos_info)
    save_png(image, path) -> path

参数（mark_image）
-----------------
    image_data : 多种类型（自动适配）
        * str              —— 图片文件路径
        * bytes / bytearray—— 图片二进制数据（自动识别 PNG/JPG 等格式）
        * QImage / QPixmap —— Qt 图像 / 位图
        * PIL.Image.Image  —— Pillow 图像（需安装 Pillow）
        * numpy.ndarray    —— HxWxC 的 uint8 数组，C 取 1/3/4（需安装 numpy）
    mode : {'dot', 'rect', 'dots', 'show'}
        'dot' / 'rect' / 'dots' 三种标注模式都会先给整图盖上灰色半透明遮罩：
        * 'dot'  —— 点标注：左键单击标记一个红色圆点，随即关闭。
        * 'rect' —— 矩形标注：第一次单击定起点，矩形对角点跟随鼠标、框内去除遮罩
          （透出原图并描边），第二次单击确认矩形区域并关闭。
        * 'dots' —— 多点标注：左键逐个标记红点（右上方带递增序号 1..n），Backspace
          撤销最近一个点，右键结束并返回所有点。
        * 'show' —— 仅展示：不加遮罩、不标注，纯全屏看图；任意点击 / Esc 退出。

返回（mark_image）
-----------------
    image : 标注后的图片
        默认与输入类型一致（round-trip）：QImage/QPixmap/PIL.Image/numpy.ndarray 进
        → 同类型出；str/bytes 进 → 优先 numpy.ndarray（不可用则 PIL.Image，再不行则
        QImage）。注：内部先「展平到白底 RGB888」再标注，带透明通道的图会合成到白底。
        'show' 与取消/失败时返回原输入 ``image_data``（未修改）。
    pos_info : :class:`model.point_timeline.PointTimeline` 或 None
        坐标点 + 每点点击前等待的秒数（首点恒为 0）。dot/rect/dots 标注完成时返回；
        'show' / 取消 / dots 空点 / 尺寸不符 时返回 None。遍历方式::

            for (x, y), wait in pos:        # wait = 点击该点前等待的秒数
                ...

尺寸校验
--------
    仅当 图片宽 <= 屏幕宽 且 图片高 <= 屏幕高 时才继续（保证 1:1 全屏，使点击坐标
    与像素坐标一致）；否则弹提示「该图片无法标注」并原样返回 (image_data, None)。
    若要「必须与屏幕尺寸完全相等」，把下文 <= 改成 == 即可。

交互
----
    dot   : 左键标记点 → 完成          右键 / Esc：取消
    rect  : 左键起点 → 移动 → 再单击确认 右键 / Esc：取消
    dots  : 左键加点（序号递增）→ Backspace 撤销 → 右键结束        Esc：取消
    show  : 任意点击 / Esc：退出

示例
----
    from tools.image_marker import mark_image, save_png

    img, pos = mark_image("a.png", "dot")     # pos -> PointTimeline([( ((x,y), 0.0) ]))
    img, pos = mark_image(np_arr, "rect")     # pos -> 2 项 PointTimeline
    img, pos = mark_image(np_arr, "dots")     # pos -> N 项 PointTimeline
    for (x, y), wait in pos:                  # 遍历坐标 + 点击前等待秒数
        print(x, y, wait)
    img, _ = mark_image("a.png", "show")      # 仅全屏展示
    save_png(img, "marked.png")              # 保存为 PNG

    # 直接运行本模块体验 demo：
    #   python tools/image_marker.py dot|rect|dots|show
"""

# 本文件大量使用 PyQt5 枚举（Qt.NoBrush / Qt.LeftButton / QIODevice.ReadWrite 等）
# 与 sip.voidptr 缓冲区；Pyright 在缺少 PyQt5 类型存根时会把这些合法访问误报为
# 「未知属性 / 可选成员 / 参数类型不匹配 / 重载参数名」。此处仅关闭相关噪声检查，
# 其余检查照常启用；安装 PyQt5 存根后可删除本行。
# pyright: reportAttributeAccessIssue=false, reportOptionalMemberAccess=false, reportArgumentType=false, reportIncompatibleMethodOverride=false

import io
import os
import sys
from typing import Any, Optional, Tuple

# 允许 `python tools/image_marker.py` 直接运行时能 import 同级的 model 包
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
from model.point_timeline import PointTimeline

from PyQt5.QtCore import Qt, QPoint, QRect, QByteArray, QBuffer, QIODevice, QEventLoop
from PyQt5.QtGui import QColor, QCursor, QFont, QImage, QPainter, QPen, QPixmap
from PyQt5.QtWidgets import QApplication, QDialog, QLabel, QMessageBox

# 可选依赖：缺失时对应输入类型不可用（其它类型照常工作）
try:
    import numpy as np
except Exception:  # pragma: no cover
    np = None

try:
    import PIL.Image as _PIL_Image
except Exception:  # pragma: no cover
    _PIL_Image = None

# 可调常量：标注样式
_DOT_COLOR = QColor(255, 0, 0)              # 点标注颜色（红）
_DOT_RADIUS = 6                             # 点标注半径（像素）
_NUM_COLOR = QColor(255, 255, 255)           # dots 序号颜色（白）
_DIM_COLOR = QColor(128, 128, 128, 140)      # 灰色半透明遮罩（整图）
_BORDER_COLOR = QColor(0, 175, 255)           # 矩形边框颜色
_BORDER_WIDTH = 2                           # 矩形边框宽度（像素）

_MODES = ("dot", "rect", "dots", "show")

__all__ = ["mark_image", "save_png"]


# ===========================================================================
# 类型转换：多种输入 ↔ QImage（RGB888，已展平到白底）
# ===========================================================================
def _flatten_to_rgb888(img: QImage) -> QImage:
    """任意格式 QImage → 不透明 RGB888（透明像素合成到白色背景）。"""
    if img.format() == QImage.Format_RGB888:
        return img.copy()
    out = QImage(img.size(), QImage.Format_RGB888)
    out.fill(QColor(255, 255, 255))
    p = QPainter(out)
    p.drawImage(0, 0, img)
    p.end()
    return out


# ---- 输入：多种类型 → RGB888 QImage ----------------------------------------
def _ndarray_to_qimage(arr: Any) -> QImage:
    """numpy.ndarray(HxWxC, uint8) → QImage（RGB888 / RGBA8888）。"""
    assert np is not None, "numpy 不可用"
    arr = np.ascontiguousarray(arr)
    if arr.dtype != np.uint8:
        arr = arr.astype(np.uint8)
    if arr.ndim != 3:
        raise ValueError("numpy 图像需为三维数组 HxWxC")
    h, w, c = arr.shape
    if c == 1:
        arr = np.repeat(arr, 3, axis=2)
        c = 3
    if c == 3:
        fmt = QImage.Format_RGB888
    elif c == 4:
        fmt = QImage.Format_RGBA8888
    else:
        raise ValueError("numpy 图像通道数需为 1 / 3 / 4")
    # copy：脱离 python 缓冲区，避免内存被回收
    return QImage(arr.tobytes(), w, h, w * c, fmt).copy()


def _to_qimage(image_data: Any) -> QImage:
    """多种类型 → RGB888 QImage。无法解析时抛 ValueError/TypeError。"""
    if isinstance(image_data, QImage):
        img = image_data
    elif isinstance(image_data, QPixmap):
        img = image_data.toImage()
    elif isinstance(image_data, (bytes, bytearray)):
        img = QImage.fromData(QByteArray(bytes(image_data)))
    elif isinstance(image_data, str):
        img = QImage(image_data)
    elif _PIL_Image is not None and isinstance(image_data, _PIL_Image.Image):
        buf = io.BytesIO()
        image_data.convert("RGBA").save(buf, format="PNG")
        img = QImage.fromData(QByteArray(buf.getvalue()))
    elif np is not None and isinstance(image_data, np.ndarray):
        img = _ndarray_to_qimage(image_data)
    else:
        raise TypeError(
            "不支持的 image_data 类型: %r（支持 str/bytes/QImage/QPixmap/PIL.Image/numpy.ndarray）"
            % type(image_data).__name__
        )
    if img is None or img.isNull():
        raise ValueError("无法解析图片数据，请检查路径或数据是否为有效图片。")
    return _flatten_to_rgb888(img)


# ---- 输出：RGB888 QImage → 与输入相同类型 ----------------------------------
def _qimage_to_ndarray(qimg: QImage) -> Any:
    """QImage → numpy.ndarray(HxWx3, uint8)，自动处理行对齐填充。"""
    assert np is not None, "numpy 不可用"
    qimg = qimg.convertToFormat(QImage.Format_RGB888)
    w, h = qimg.width(), qimg.height()
    bpl = qimg.bytesPerLine()
    ptr = qimg.constBits()
    ptr.setsize(bpl * h)
    arr = np.frombuffer(bytes(ptr), dtype=np.uint8)
    arr = arr.reshape(h, bpl)[:, : w * 3].copy()  # 去除行尾对齐填充
    return arr.reshape(h, w, 3)


def _qimage_to_pil(qimg: QImage):
    """QImage → PIL.Image（RGB，PNG 中转，不依赖 numpy）。"""
    buf = QBuffer()
    buf.open(QIODevice.ReadWrite)
    qimg.save(buf, "PNG")
    buf.close()
    pil = _PIL_Image.open(io.BytesIO(bytes(buf.data())))
    pil.load()
    return pil.convert("RGB")


def _from_qimage(qimg: QImage, like: Any) -> Any:
    """RGB888 QImage → 与输入 like 相同类型的结果（round-trip）。"""
    qimg = _flatten_to_rgb888(qimg)
    if isinstance(like, QImage):
        return qimg.copy()
    if isinstance(like, QPixmap):
        return QPixmap.fromImage(qimg)
    if _PIL_Image is not None and isinstance(like, _PIL_Image.Image):
        return _qimage_to_pil(qimg)
    if np is not None and isinstance(like, np.ndarray):
        return _qimage_to_ndarray(qimg)
    # str / bytes / 其它：优先 numpy，其次 PIL，最后 QImage
    if np is not None:
        return _qimage_to_ndarray(qimg)
    if _PIL_Image is not None:
        return _qimage_to_pil(qimg)
    return qimg.copy()


# ===========================================================================
# 全屏标注对话框
# ===========================================================================
class _MarkerDialog(QDialog):
    """全屏对话框：按 mode 在 1:1 显示的图片上标注 / 展示。

    所有渲染走统一的 ``_render``（基于当前状态：mode + _timeline / _start / _current），
    实时预览与最终合成共用，避免逻辑重复。点击坐标与间隔时间记录在 ``_timeline``
    (:class:`PointTimeline`) 中，dot/rect/dots 完成时作为 pos_info 返回。
    """

    # 各模式底部提示文字
    _HINTS = {
        "dot":   "左键：标记点 → 完成      右键 / Esc：取消",
        "rect":  "左键：定起点 → 移动 → 再次单击确认矩形      右键 / Esc：取消",
        "dots":  "左键：加点(序号递增)   Backspace：撤销   右键：结束      Esc：取消",
        "show":  "点击 / Esc：退出",
    }

    def __init__(self, base: QImage, mode: str, screen_size) -> None:
        super().__init__()
        self._base = base                                  # QImage(RGB888)，只读
        self._mode = mode
        self._iw, self._ih = base.width(), base.height()
        self._img_rect = QRect(0, 0, self._iw, self._ih)    # 图片区域（图像坐标）
        self._sw, self._sh = screen_size.width(), screen_size.height()
        self._ox = (self._sw - self._iw) // 2               # 图片居中偏移
        self._oy = (self._sh - self._ih) // 2

        self._timeline = PointTimeline()    # 已标记的点 + 点击间隔（dot/dots/rect 共用）
        self._start = None                  # rect 起点（图像坐标，QPoint）
        self._current = None               # 鼠标当前位置（图像坐标，QPoint）
        self.result_image: Optional[QImage] = None
        self.result_pos: Optional[PointTimeline] = None

        # 序号字体（app 已由 mark_image 创建，可安全构造）
        self._num_font = QFont("Arial", 10)
        self._num_font.setBold(True)

        # 真正的全屏：无边框 + 置顶（覆盖任务栏与 IDLE 等其它窗口）
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setCursor(Qt.CrossCursor)
        self.setMouseTracking(True)                         # 无按键也接收 mouseMove
        self._build_labels()

    # ---- UI 辅助 ----
    def _build_labels(self) -> None:
        # show 模式不显示坐标标签（纯展示）
        if self._mode != "show":
            self._coord_label = QLabel("（x:0,y:0）", self)
            self._coord_label.setStyleSheet(
                "background-color: rgba(0,0,0,180); color: #7CFC00; "
                "padding: 2px 6px; border-radius: 3px; font-family: Consolas, monospace;"
            )
            self._coord_label.adjustSize()
        else:
            self._coord_label = None

        self._hint_label = QLabel(self._HINTS[self._mode], self)
        self._hint_label.setStyleSheet(
            "background-color: rgba(0,0,0,180); color: #dddddd; "
            "padding: 4px 10px; border-radius: 3px;"
        )
        self._hint_label.adjustSize()
        self._hint_label.move(
            (self._sw - self._hint_label.width()) // 2,
            self._sh - self._hint_label.height() - 10,
        )
        for lbl in (self._coord_label, self._hint_label):
            if lbl is None:
                continue
            lbl.setAttribute(Qt.WA_TransparentForMouseEvents, True)  # 鼠标穿透
            lbl.show()

    def _move_coord_label(self, pos) -> None:
        x, y = pos.x() + 14, pos.y() + 14
        w, h = self._coord_label.width(), self._coord_label.height()
        if x + w > self._sw:
            x = pos.x() - w - 14
        if y + h > self._sh:
            y = pos.y() - h - 14
        self._coord_label.move(x, y)

    def _to_image(self, pos) -> Tuple[int, int]:
        """控件坐标 → 图像像素坐标。"""
        return pos.x() - self._ox, pos.y() - self._oy

    @staticmethod
    def _norm_rect(a: QPoint, b: QPoint) -> QRect:
        """两点 → 正向 QRect（含两端像素）。"""
        x1, y1, x2, y2 = a.x(), a.y(), b.x(), b.y()
        return QRect(min(x1, x2), min(y1, y2), abs(x2 - x1) + 1, abs(y2 - y1) + 1)

    # ---- 场景绘制（实时预览与最终合成共用，基于当前状态）----
    def _render(self, p: QPainter) -> None:
        p.drawImage(0, 0, self._base)               # 原图
        if self._mode == "show":
            return                                 # 仅展示：无遮罩无标注
        p.fillRect(self._img_rect, _DIM_COLOR)     # 整图灰色遮罩（dot/rect/dots）
        if self._mode == "rect":
            if self._start is not None and self._current is not None:
                r = self._norm_rect(self._start, self._current)
                p.save()                           # 框内还原原图（去遮罩）
                p.setClipRect(r)
                p.drawImage(0, 0, self._base)
                p.restore()
                p.setPen(QPen(_BORDER_COLOR, _BORDER_WIDTH))
                p.setBrush(Qt.NoBrush)
                p.drawRect(r)
        else:  # dot / dots：画已标记的点（dots 带序号）
            numbered = self._mode == "dots"
            for i, (x, y) in enumerate(self._timeline.points):
                self._draw_dot(p, x, y, num=(i + 1) if numbered else None)

    def _draw_dot(self, p: QPainter, x: int, y: int, num: Optional[int] = None) -> None:
        """画一个红点；num 非 None 时在右上方写白色序号。"""
        p.setPen(Qt.NoPen)
        p.setBrush(_DOT_COLOR)
        p.drawEllipse(QPoint(x, y), _DOT_RADIUS, _DOT_RADIUS)
        if num is not None:
            p.setPen(_NUM_COLOR)
            p.setFont(self._num_font)
            # drawText(x, y, text)：基线在 (x, y) → 文字落在右上方
            p.drawText(x + _DOT_RADIUS + 2, y - _DOT_RADIUS, str(num))

    def _render_to_image(self) -> QImage:
        """把当前场景合成到一张新的 QImage（用于最终返回）。"""
        out = self._base.copy()
        p = QPainter(out)
        self._render(p)
        p.end()
        return out

    # ---- 结束 / 取消 ----
    def _finish_dot(self) -> None:
        self.result_image = self._render_to_image()
        self.result_pos = self._timeline
        self.accept()

    def _finish_dots(self) -> None:
        if not self._timeline:             # 一个点都没标 → 视为取消
            self.reject()
            return
        self.result_image = self._render_to_image()
        self.result_pos = self._timeline
        self.accept()

    def _finish_rect(self) -> None:
        self.result_image = self._render_to_image()
        self.result_pos = self._timeline
        self.accept()

    def _finish_show(self) -> None:
        self.result_image = None            # 不修改图
        self.result_pos = None
        self.accept()

    # ---- 事件 ----
    def showEvent(self, event) -> None:
        # 窗口刚显示即把坐标标签放到真实光标处（否则停在左上角直到鼠标移动）
        if self._mode != "show":
            self._sync_cursor(QCursor.pos())
        super().showEvent(event)

    def _sync_cursor(self, global_pos) -> None:
        """用全局光标位置同步坐标标签 / 预览，等价于一次 mouseMove。"""
        local = self.mapFromGlobal(global_pos)
        ix, iy = self._to_image(local)
        self._current = QPoint(ix, iy)
        if self._coord_label is not None:
            self._coord_label.setText("（x:%d,y:%d）" % (ix, iy))
            self._coord_label.adjustSize()
            self._move_coord_label(local)
        self.update()

    def paintEvent(self, _) -> None:
        p = QPainter(self)
        p.fillRect(self.rect(), Qt.black)           # 留白背景
        p.save()
        p.translate(self._ox, self._oy)
        self._render(p)                             # 统一按当前状态绘制
        p.restore()

    def mouseMoveEvent(self, event) -> None:
        if self._mode == "show":
            return                                  # 纯展示，无需跟随
        self._sync_cursor(event.globalPos())

    def mousePressEvent(self, event) -> None:
        btn = event.button()

        # show：任意点击即退出
        if self._mode == "show":
            if btn in (Qt.LeftButton, Qt.RightButton, Qt.MiddleButton):
                self._finish_show()
            return

        # 右键：dots=结束，dot/rect=取消
        if btn == Qt.RightButton:
            if self._mode == "dots":
                self._finish_dots()
            else:
                self.reject()
            return
        if btn != Qt.LeftButton:
            return

        ix, iy = self._to_image(event.pos())
        if not (0 <= ix < self._iw and 0 <= iy < self._ih):
            return                                  # 点击落在图片外，忽略

        if self._mode == "dot":
            self._timeline.add(ix, iy)
            self._finish_dot()
        elif self._mode == "dots":
            self._timeline.add(ix, iy)             # 记录点 + 间隔，继续
            self.update()
        else:  # rect
            if self._start is None:
                self._start = QPoint(ix, iy)
                self._current = QPoint(ix, iy)
                self._timeline.add(ix, iy)        # 起点（间隔 0）
            else:
                self._current = QPoint(ix, iy)
                self._timeline.add(ix, iy)        # 终点（间隔 = 距起点）
                self._finish_rect()

    def keyPressEvent(self, event) -> None:
        key = event.key()
        if key == Qt.Key_Escape:
            self.reject()
            return
        if key == Qt.Key_Backspace and self._mode == "dots":
            if self._timeline.undo():              # 撤销最近一个点（并重置计时）
                self.update()
            return
        super().keyPressEvent(event)


# ===========================================================================
# 对外接口
# ===========================================================================
def mark_image(image_data: Any, mode: str) -> Tuple[Any, Optional[PointTimeline]]:
    """
    全屏打开图片并按模式标注 / 展示。

    :param image_data: 图片数据，支持 str(路径)/bytes/QImage/QPixmap/PIL.Image/numpy.ndarray。
    :param mode: 'dot' / 'rect' / 'dots' / 'show'。
    :return: ``(image, pos_info)``，pos_info 为 PointTimeline 或 None。详见模块文档。
    """
    if mode not in _MODES:
        raise ValueError("mode 必须为 %r 之一，当前为 %r" % (_MODES, mode))

    base = _to_qimage(image_data)  # 解析失败会抛错

    app = QApplication.instance() or QApplication(sys.argv)
    screen = app.primaryScreen()
    if screen is None:
        return image_data, None
    screen_size = screen.size()

    # 1) 尺寸校验：图片必须能 1:1 全屏显示
    if base.width() > screen_size.width() or base.height() > screen_size.height():
        QMessageBox.warning(None, "提示", "该图片无法标注（图片尺寸超出显示器）。")
        return image_data, None

    # 2) 全屏交互
    #    不用 QDialog.exec()：它内部会再 show() 一次，可能把 showFullScreen() 的全屏
    #    状态复位成普通窗口（任务栏 / 控制台仍可见）。改用 showFullScreen() + 本地
    #    QEventLoop 阻塞。
    dlg = _MarkerDialog(base, mode, screen_size)
    dlg.showFullScreen()
    dlg.raise_()
    dlg.activateWindow()
    loop = QEventLoop()
    dlg.finished.connect(loop.quit)
    loop.exec_()

    # 3) 返回：仅当「确认且有合成图」时返回标注结果；否则原样返回（取消/show/空点）
    if dlg.result() == QDialog.Accepted and dlg.result_image is not None:
        return _from_qimage(dlg.result_image, image_data), dlg.result_pos
    return image_data, None


def save_png(image: Any, path: str) -> str:
    """
    把图片（多种类型）保存为 PNG 文件。

    :param image: 图片数据，支持 str/bytes/QImage/QPixmap/PIL.Image/numpy.ndarray。
    :param path:  保存路径（建议以 .png 结尾）。
    :return: 保存路径。
    :raises IOError: 写盘失败时抛出。

    注：内部先展平到白底 RGB888，带透明通道的图会合成到白底。
    """
    qimg = _to_qimage(image)
    if not qimg.save(path, "PNG"):
        raise IOError("保存 PNG 失败：%r" % path)
    return path


# ===========================================================================
# demo
# ===========================================================================
def _demo_image(app: QApplication) -> QImage:
    sz = app.primaryScreen().size()
    w = max(320, min(640, sz.width() - 40))
    h = max(240, min(480, sz.height() - 80))
    img = QImage(w, h, QImage.Format_RGB888)
    img.fill(QColor(30, 30, 46))
    p = QPainter(img)
    step = 40
    for j in range(0, h, step):
        for i in range(0, w, step):
            p.fillRect(
                QRect(i, j, step - 2, step - 2),
                QColor((i * 5) % 256, (j * 7) % 256, ((i + j) * 3) % 256),
            )
    p.setPen(QPen(QColor(255, 255, 255), 1))
    p.drawLine(0, h // 2, w, h // 2)
    p.drawLine(w // 2, 0, w // 2, h)
    p.end()
    return img


if __name__ == "__main__":
    _mode = sys.argv[1] if len(sys.argv) > 1 else "dot"
    _app = QApplication.instance() or QApplication(sys.argv)
    _img = _demo_image(_app)
    _out, _pos = mark_image(_img, _mode)
    print("mode =", _mode, "| pos =", _pos, "| 返回类型:", type(_out).__name__)
    if _pos is not None:
        _p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "image_marker_demo.png")
        save_png(_out, _p)
        print("已保存 demo PNG:", _p)
