# -*- coding: utf-8 -*-
"""
步骤列表视图（GUI 控件）
======================

:class:`StepListView` 是「步骤列表」（:class:`model.step_list.StepList`）的
可视化视图（QGraphicsView）：横向排布 :class:`StepCard` 卡片
（QGraphicsProxyWidget），滚轮横向滚动，悬停卡片平滑放大（1.06 倍），
右键菜单支持 添加（头部/尾部/前方/后方，经 :class:`TemplateChooserDialog`
模板树选择）/ 复制 / 剪切 / 粘贴 / 删除。

**步骤剪贴板**（:class:`StepClipboard`）：步骤格式串列表，跨列表切换存活，
由宿主（管理树）持有并注入；剪切后剪贴板保留（剪切 = 复制 + 删除，
允许多次粘贴）。

基本用法
--------
::

    view = StepListView(mgr, clipboard)
    view.set_list(step_list, mgr)   # 绑定列表并重建卡片
    view.refresh()                  # 重建（顺序/内容变化后）
    view.refresh_validity()         # 仅重检颜色（变量树变化后）
"""

from __future__ import annotations

from typing import Dict, List, Optional

from PyQt5.QtCore import (
    QEasingCurve, QEvent, QPointF, QRectF, Qt, QVariantAnimation, pyqtSignal,
)
from PyQt5.QtGui import QColor, QFont, QFontMetrics, QPainter
from PyQt5.QtWidgets import (
    QAbstractItemView, QDialog, QDialogButtonBox, QGraphicsItem,
    QGraphicsProxyWidget, QGraphicsScene, QGraphicsSimpleTextItem,
    QGraphicsView, QMenu, QMessageBox, QStyle, QTreeWidget, QTreeWidgetItem,
    QVBoxLayout, QWidget,
)

from model.step_list import StepList
from model.step_manager import StepManager
from widgets.step_card import StepCard, card_size_for_screen

__all__ = ["StepClipboard", "StepListView", "TemplateChooserDialog"]

_PATH_ROLE = 0x0100   # Qt.UserRole
_CARD_GAP = 16        # 卡片间距
_SCALE_MAX = 1.06     # 悬停放大倍数
_SCALE_GROW = (_SCALE_MAX - 1) / 2.0   # 中心放大：上下/左右各扩出比例（3% 卡高）
_EDGE = 8.0           # 场景边缘安全边距（标签不得裁出场景）
_SHADOW_COLOR = (40, 60, 90)   # 投影基色（RGB；各层叠加透明度）


def _label_slot() -> float:
    """卡片外标签槽高 = SimSun 12 真实渲染行高 + 4 间距。

    探针文本必须与真实错误标签同内容（含 ⚠，SimSun 无此字形 → 自动回退
    字体、行高被撑高：本机纯汉字 24 vs 含 ⚠ 32）；只量纯汉字或
    QFontMetrics.height() 会低估，错误标签顶到场景底、最小尺寸下被视口切掉。
    """
    probe = QGraphicsSimpleTextItem("⚠: 样例文本")
    probe.setFont(QFont("SimSun", 12))
    return probe.boundingRect().height() + 4.0


class _CardShadowItem(QGraphicsItem):
    """卡片场景阴影：多层半透明圆角矩形近似模糊投影（不依赖 QGraphicsEffect）。

    实测 QGraphicsDropShadowEffect 挂在 QGraphicsProxyWidget（或其内嵌 widget）
    上时卡片整体渲染白屏（Qt 5.15 Windows 纹理化 bug，离屏与真实窗口皆然），
    阴影改由普通场景绘制实现：卡片下方偏移的多层圆角矩形，由内到外逐层减淡
    近似模糊。随卡片由视图创建 / 重建 / 删除统一管理（见 :meth:`StepListView.refresh`）。
    """

    def __init__(self, w: int, h: int, radius: float = 14.0) -> None:
        super().__init__()
        self._w, self._h, self._radius = w, h, radius
        self.setZValue(-1)   # 垫在所有卡片之下（悬停放大后 z=1 亦在阴影上）

    def boundingRect(self) -> QRectF:  # noqa: N802 (Qt 命名)
        # 阴影最外圈扩展：左右各 3px、下方 7px（偏移 4 + 外扩 3）
        return QRectF(-4.0, 0.0, self._w + 8.0, self._h + 8.0)

    def paint(self, painter, option, widget=None) -> None:  # noqa: N802
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        for i, alpha in enumerate((26, 18, 12, 7)):   # 由内到外逐层减淡 → 模糊近似
            r = QRectF(-i, 4 - i, self._w + 2.0 * i, self._h + 2.0 * i)
            painter.setBrush(QColor(*_SHADOW_COLOR, alpha))
            painter.drawRoundedRect(r, self._radius, self._radius)
        painter.restore()


class StepClipboard:
    """步骤 / 列表剪贴板（纯数据；跨视图与列表存活）。"""

    def __init__(self) -> None:
        self.steps: Optional[List[str]] = None          # 步骤格式串
        self.items: Optional[tuple] = None              # (名, 三元组列表)；列表/组剪贴板


class TemplateChooserDialog(QDialog):
    """添加步骤：模板树选择。按文件夹分组展示全部已注册模板，叶子才可确定。"""

    def __init__(self, mgr: StepManager,
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("选择步骤模板")
        self.resize(360, 420)
        self._path: Optional[str] = None
        self._mgr = mgr
        lay = QVBoxLayout(self)
        self._tw = QTreeWidget()
        self._tw.setHeaderHidden(True)
        self._tw.setSelectionMode(QAbstractItemView.SingleSelection)
        self._tw.itemDoubleClicked.connect(lambda *_: self.accept())
        self._tw.currentItemChanged.connect(lambda *_: self._update_ok())
        lay.addWidget(self._tw)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self._ok = btns.button(QDialogButtonBox.Ok)
        self._ok.setText("添加")
        self._ok.setEnabled(False)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)
        self._build_tree()

    def selected_path(self) -> Optional[str]:
        """返回选中的模板路径；未选（或选的是组）→ None。"""
        return self._path

    def _build_tree(self) -> None:
        style = self.style()
        root = self._tw.invisibleRootItem()
        if root is None:
            return
        for path in self._mgr.template_paths():
            item = root
            segs = path.split("/")
            for i, seg in enumerate(segs):
                found = None
                for c in range(item.childCount()):
                    ch = item.child(c)
                    if ch is not None and ch.text(0) == seg:
                        found = ch
                        break
                if found is None:
                    found = QTreeWidgetItem(item)
                    found.setText(0, seg)
                    if i < len(segs) - 1 and style is not None:
                        found.setIcon(0, style.standardIcon(QStyle.SP_DirIcon))
                item = found
            item.setData(0, _PATH_ROLE, path)

    def _update_ok(self) -> None:
        it = self._tw.currentItem()
        path = it.data(0, _PATH_ROLE) if it is not None else None
        self._path = path
        self._ok.setEnabled(path is not None)

    def accept(self) -> None:  # noqa: N802 (Qt 命名)
        if self._path is None:
            return                     # 未选叶子 → 不关闭
        super().accept()


class StepListView(QGraphicsView):
    """水平步骤列表视图：卡片横排、滚轮横向滚动、悬停放大、右键菜单。"""

    edited = pyqtSignal()
    errors_changed = pyqtSignal(int)   # 错误卡片数量变化（工具条统计）

    def __init__(self, mgr: StepManager, clipboard: StepClipboard,
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._mgr = mgr
        self._clipboard = clipboard
        self._step_list: Optional[StepList] = None
        self._cards: List[StepCard] = []
        self._proxies: List[QGraphicsProxyWidget] = []
        self._shadows: List[QGraphicsItem] = []
        self._anims: Dict[int, QVariantAnimation] = {}
        self._selected: Optional[StepCard] = None
        # 多选集（Ctrl/Shift+点击；按点击序，恒含主选中）→ 多选复制批次
        self._multi: List[StepCard] = []
        # Shift 范围选择锚点（最近一次普通/Ctrl 点击的卡；Shift 不更新锚点）
        self._anchor: Optional[StepCard] = None
        self._hint: Optional[QGraphicsSimpleTextItem] = None
        # 卡片错误标签（io 不合规时显示在卡片正下方；无错误不建）
        self._error_labels: Dict[StepCard, QGraphicsSimpleTextItem] = {}
        # 序号标签（每卡一个，显示在卡片正上方：(n/总数)）
        self._index_labels: Dict[StepCard, QGraphicsSimpleTextItem] = {}

        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._on_context_menu)
        self.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)  # 内容不足视口时靠左显示
        self.setRenderHint(QPainter.Antialiasing)
        self.refresh()

    # ---- 绑定 / 刷新 ----
    def set_list(self, step_list: Optional[StepList],
                 mgr: Optional[StepManager] = None) -> None:
        """绑定列表并重建卡片；``mgr`` 可选更新（同一实例常可省略）。"""
        self._step_list = step_list
        if mgr is not None:
            self._mgr = mgr
        self.refresh()

    def refresh(self) -> None:
        """按当前列表重建卡片（顺序/内容变化后调用）。"""
        for anim in self._anims.values():
            anim.stop()     # 播放中的动画不得触碰已移除的代理（C++ 已删 → RuntimeError）
        self._anims.clear()
        # 旧卡片/阴影必须真正移出场景：只清 Python 列表会让 proxy 永久残留叠加
        # （幽灵卡片：右键 _cards.index(card) 抛 ValueError）
        for sh in self._shadows:
            self._scene.removeItem(sh)
        self._shadows = []
        for proxy in self._proxies:
            self._scene.removeItem(proxy)
        self._proxies = []
        for label in self._error_labels.values():
            self._scene.removeItem(label)
        self._error_labels = {}
        for label in self._index_labels.values():
            self._scene.removeItem(label)
        self._index_labels = {}
        self._cards = []
        self._selected = None
        self._multi = []
        self._anchor = None
        if self._hint is not None:
            self._scene.removeItem(self._hint)
            self._hint = None
        sl = self._step_list
        if sl is None or len(sl) == 0:
            self._hint = self._scene.addSimpleText(
                "右键添加步骤（或在左侧管理树选择列表）")
            if self._hint is not None:
                self._hint.setFont(QFont("SimSun", 22))   # 22 号宋体
                self._center_hint()
            self.setMinimumHeight(0)   # 无卡片 → 无放大保护（防旧值残留）
            self.errors_changed.emit(0)
            return
        x = 16.0
        # 卡顶留白 = 放大余量(pad) + 标签槽(行高+间距) + 场景边距：
        # 序号标签固定在「放大后的卡顶」之外（中心放大上下各扩 pad，标签不移位
        # 就不会被盖）；卡片 y 随之抬高，保证标签不裁出场景顶部。
        slot = _label_slot()
        pad = card_size_for_screen()[1] * _SCALE_GROW
        y = round(pad + slot + _EDGE)
        for n, step in enumerate(sl, 1):
            card = StepCard(step)
            card.io_changed.connect(self.edited)   # 卡片内 io 编辑 → 内容已改（宿主保存）
            # io 编辑同步该卡错误标签（不重建；卡销毁后信号不会再来）
            card.io_changed.connect(
                lambda c=card: self._update_error_label(c))
            card.menu_requested.connect(self._on_card_menu)
            card.installEventFilter(self)   # 滚轮转发 / 悬停缩放 / 点击选中
            proxy = self._scene.addWidget(card)
            proxy.setPos(QPointF(x, y))
            proxy.setTransformOriginPoint(
                QPointF(card.width() / 2.0, card.height() / 2.0))
            shadow = _CardShadowItem(card.width(), card.height())
            shadow.setPos(x, y)      # 阴影相对偏移 (0, 4) 在 paint 内
            self._scene.addItem(shadow)
            self._cards.append(card)
            self._proxies.append(proxy)
            self._shadows.append(shadow)
            self._set_error_label(card)   # 初始错误标签（无错误不建）
            self._set_index_label(card, n, len(sl))   # 序号标签 (n/总数)
            x += card.width() + _CARD_GAP
        # 场景高度随卡片尺寸动态，容纳：卡顶留白(y) + 卡片 + 放大余量(pad) +
        # 错误标签槽 + 底部边距（错误标签固定在「放大后的卡底」之外）；
        # 视图最小高度同步（窗口/布局压缩时标签与放大卡片都不裁剪）。
        # 注意 minimumHeight 必须补足「视口外占用」(frame×2 + 水平滚动条)：
        # 否则视口比场景矮、AlignVCenter 居中显示时卡片与错误标签被上下切。
        h = self._cards[0].height()
        scene_h = y + h + pad + slot + _EDGE
        self._scene.setSceneRect(0, 0, x + 16.0, scene_h)
        self.setMinimumHeight(round(scene_h) + self._viewport_overhead())
        self._fit_scene_width()
        self.errors_changed.emit(self._count_errors())

    def refresh_validity(self) -> None:
        """仅重检各卡片颜色与错误标签（io 校验可能随变量树变化），不重建。"""
        for card in self._cards:
            card.refresh()
            self._set_error_label(card)
        self.errors_changed.emit(self._count_errors())

    def _set_error_label(self, card: StepCard) -> None:
        """按卡片当前 io 校验同步其下方错误标签（合规 → 移除）。

        文本格式「⚠: 原因1, 原因2」；标签在卡片外正下方居中（y = 卡底 + 4）。
        """
        label = self._error_labels.get(card)
        reasons = card.step.io.error_reasons()
        if not reasons:
            if label is not None:
                self._scene.removeItem(label)
                del self._error_labels[card]
            return
        text = "⚠: " + ", ".join(reasons)
        if label is None:
            label = self._scene.addSimpleText(text)
            label.setFont(QFont("SimSun", 12))
            label.setBrush(QColor(200, 50, 40))   # 错误红
            self._error_labels[card] = label
        else:
            label.setText(text)
        p = self._proxies[self._cards.index(card)].pos()
        r = label.boundingRect()
        # 错误标签在「放大后的卡底」之外（中心放大向下扩出 3% 卡高）→ 不被盖
        pad = card.height() * _SCALE_GROW
        label.setPos(p.x() + (card.width() - r.width()) / 2.0,
                     p.y() + card.height() + pad + 4.0)
        self._fit_scene_width()   # 多原因文本可宽于卡片 → 场景宽同步扩展

    def _viewport_overhead(self) -> int:
        """视口外占用：上下 frame 边框 + 水平滚动条高度。

        minimumHeight 只覆盖场景高，视口实际高度还差这部分；不补足时
        AlignVCenter 居中显示（垂直滚动条关闭），卡片与错误标签被上下切。
        """
        return self.frameWidth() * 2 + self.horizontalScrollBar().height()

    def _fit_scene_width(self) -> None:
        """场景横向至少容纳全部卡片外标签。

        错误标签文本可宽于卡片且居中 → 左右都可能溢出：场景左端与右端
        都按标签外扩 8px（右端不足时右端切、左端不足时标签贴场景左）。
        """
        r = self._scene.sceneRect()
        left = r.x()
        right = r.x() + r.width()
        for label in (list(self._index_labels.values())
                      + list(self._error_labels.values())):
            br = label.sceneBoundingRect()
            left = min(left, br.x() - 8.0)
            right = max(right, br.x() + br.width() + 8.0)
        if left != r.x() or right != r.x() + r.width():
            self._scene.setSceneRect(left, r.y(), right - left, r.height())

    def _update_error_label(self, card: StepCard) -> None:
        """单卡 io 编辑 → 同步其错误标签（卡片已重建销毁则忽略）。"""
        if card not in self._cards:
            return
        self._set_error_label(card)
        self.errors_changed.emit(self._count_errors())

    def _set_index_label(self, card: StepCard, n: int, total: int) -> None:
        """序号标签：卡片正上方居中，文本 ``(n/total)``。

        位置 = 卡顶 − 放大余量(pad) − 标签高 − 4：悬停放大（中心缩放，卡顶
        向上扩出 pad）时标签仍在放大后的卡顶之外，不被盖住。
        """
        label = self._index_labels.get(card)
        if label is None:
            label = self._scene.addSimpleText("")
            label.setFont(QFont("SimSun", 12))
            label.setBrush(QColor(110, 110, 135))   # 灰蓝小字
            self._index_labels[card] = label
        label.setText("(%d/%d)" % (n, total))
        p = self._proxies[self._cards.index(card)].pos()
        r = label.boundingRect()
        pad = card.height() * _SCALE_GROW
        label.setPos(p.x() + (card.width() - r.width()) / 2.0,
                     p.y() - pad - r.height() - 4.0)

    # ---- 工具条动作（宿主工具栏调用） ----
    def jump_to_index(self, n: int) -> bool:
        """跳转定位到第 ``n`` 张卡（1 起）：滚动使卡片可见 + 选中；越界 → False。"""
        if n < 1 or n > len(self._cards):
            return False
        self.ensureVisible(self._proxies[n - 1], 24, 24)
        self._select(self._cards[n - 1])
        return True

    def locate_by_tag(self, text: str) -> bool:
        """搜索标签并定位：从当前选中卡之后找第一张 ``tag`` 含 ``text`` 的卡
        （循环到开头再找一遍）；找到 → 滚动 + 选中；未找到 → False。"""
        text = text.strip()
        if not text or not self._cards:
            return False
        n = len(self._cards)
        start = 0
        if self._selected in self._cards:
            start = self._cards.index(self._selected) + 1
        for i in list(range(start, n)) + list(range(0, start)):
            if text in self._cards[i].step.tag:
                return self.jump_to_index(i + 1)
        return False

    def error_card_indices(self) -> List[int]:
        """错误卡片序号（1 起，与序号标签一致）：io 校验失败（= 错误标签显示的卡）。"""
        return [i + 1 for i, c in enumerate(self._cards)
                if not c.step.io.is_valid]

    def _count_errors(self) -> int:
        return len(self.error_card_indices())

    def jump_to_error(self) -> bool:
        """跳转下一张错误卡片：从当前选中卡之后循环找（同标签搜索）；
        无错误卡 → False。"""
        n = len(self._cards)
        if n == 0:
            return False
        bad = set(self.error_card_indices())
        start = 0
        if self._selected in self._cards:
            start = self._cards.index(self._selected) + 1
        for i in list(range(start, n)) + list(range(0, start)):
            if i + 1 in bad:
                return self.jump_to_index(i + 1)
        return False

    def _center_hint(self) -> None:
        """把空列表提示放到视口中心（窗口尺寸变化时同步）。"""
        if self._hint is None:
            return
        center = self.mapToScene(self.viewport().rect().center())
        r = self._hint.boundingRect()
        self._hint.setPos(center.x() - r.width() / 2.0,
                          center.y() - r.height() / 2.0)

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt 命名)
        super().resizeEvent(event)
        self._center_hint()

    # ---- 滚轮（横向）----
    def wheelEvent(self, event) -> None:  # noqa: N802 (Qt 命名)
        delta = event.angleDelta().y()
        sb = self.horizontalScrollBar()
        sb.setValue(sb.value() - delta)
        event.accept()

    def eventFilter(self, obj, event) -> bool:
        """卡片事件过滤：滚轮转发 / 悬停缩放 / 点击选中。"""
        if event.type() == QEvent.Wheel:
            self.wheelEvent(event)  # type: ignore[arg-type]
            return True
        if obj in self._cards:
            idx = self._cards.index(obj)
            if event.type() == QEvent.Enter:
                self._animate_scale(idx, _SCALE_MAX)
            elif event.type() == QEvent.Leave:
                self._animate_scale(idx, 1.0)
            elif (event.type() == QEvent.MouseButtonPress
                    and event.button() == Qt.LeftButton):
                # 右键交给 contextMenuEvent（_card_menu 内保持多选）；左键：
                # Ctrl+点击 = 加选/减选，Shift+点击 = 锚点范围选择，
                # 普通点击 = 单选（同时更新范围锚点）
                mod = event.modifiers()
                if mod & Qt.ControlModifier:
                    self._select_toggle(obj)
                elif mod & Qt.ShiftModifier:
                    self._select_shift(obj)
                else:
                    self._select(obj)
        return super().eventFilter(obj, event)

    def _animate_scale(self, idx: int, target: float) -> None:
        proxy = self._proxies[idx]
        old = self._anims.pop(idx, None)
        if old is not None:
            old.stop()
        anim = QVariantAnimation(self)
        anim.setDuration(160)
        anim.setStartValue(proxy.scale())
        anim.setEndValue(target)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.valueChanged.connect(lambda v, p=proxy: p.setScale(float(v)))
        # finished 即从字典清理：动画对象随后被 deleteLater 销毁，
        # 残留的 Python 包装器会在下次 Enter/Leave 的 pop+stop 上抛
        # RuntimeError（wrapped C/C++ object has been deleted）——结束不留尸。
        anim.finished.connect(lambda a=anim, i=idx: self._anims.pop(i, None))
        anim.finished.connect(anim.deleteLater)
        proxy.setZValue(1 if target > 1.0 else 0)
        self._anims[idx] = anim
        anim.start()

    def _select(self, card: StepCard) -> None:
        """单选（清空多选）：普通点击 / 右键未选中卡 / 定位；更新范围锚点。"""
        if self._selected is card and len(self._multi) == 1:
            return
        for c in list(self._multi):
            c.set_selected(False)
        self._multi = [card]
        self._selected = card
        self._anchor = card
        card.set_selected(True)

    def _select_toggle(self, card: StepCard) -> None:
        """Ctrl+点击：切换该卡加入/移出多选（主选中随之更新）；更新范围锚点。"""
        self._anchor = card
        if card in self._multi:
            self._multi.remove(card)
            card.set_selected(False)
            if self._selected is card:
                self._selected = self._multi[-1] if self._multi else None
        else:
            self._multi.append(card)
            self._selected = card
            card.set_selected(True)

    def _select_shift(self, card: StepCard) -> None:
        """Shift+点击：从锚点到该卡的范围选择（替换当前多选；锚点不动）。

        锚点 = 最近一次普通/Ctrl 点击的卡；连续 Shift 从同一锚点重选范围。
        无锚点（首操作）→ 等同单选并成为新锚点。
        """
        anchor = self._anchor
        if anchor not in self._cards:
            anchor = self._cards[0] if self._cards else None
        if anchor is None:
            self._select(card)
            return
        i0, i1 = self._cards.index(anchor), self._cards.index(card)
        if i0 > i1:
            i0, i1 = i1, i0
        sel = self._cards[i0:i1 + 1]
        for c in list(self._multi):
            c.set_selected(False)
        self._multi = list(sel)
        self._selected = card
        for c in sel:
            c.set_selected(True)

    def _selected_cards(self) -> List[StepCard]:
        """选中卡（含多选），按卡片显示顺序（= 复制批次序）。"""
        sel = set(self._multi)
        return [c for c in self._cards if c in sel]

    # ---- 右键菜单 ----
    def _on_context_menu(self, pos) -> None:
        card = self._card_at(pos)
        if card is not None:
            # 菜单 exec_ 需要全局坐标；viewport 局部坐标直接用会在视图左上角弹出
            self._card_menu(card, self.viewport().mapToGlobal(pos))
            return
        menu = QMenu(self)
        a_head = menu.addAction("头部添加…")
        a_tail = menu.addAction("尾部添加…")
        menu.addSeparator()
        a_paste = menu.addAction("粘贴")
        a_paste.setEnabled(bool(self._clipboard.steps))
        action = menu.exec_(self.viewport().mapToGlobal(pos))
        if action is a_head:
            self._add_step(0)
        elif action is a_tail:
            self._add_step(-1)   # 尾部哨兵
        elif action is a_paste:
            self._paste(len(self._step_list) if self._step_list is not None else 0)

    def _on_card_menu(self, card: StepCard, pos) -> None:
        self._card_menu(card, pos)   # StepCard.contextMenuEvent 已传全局坐标

    def _card_menu(self, card: StepCard, global_pos) -> None:
        """卡片右键菜单；``global_pos`` 为全局坐标（exec_ 弹出位置 = 鼠标处）。

        多选（>1 张）时只留「复制」：添加/剪切/粘贴/删除都依赖单卡锚点，
        多选无锚点语义 → 全部禁用，仅批量复制。
        """
        if card not in self._multi:      # 右键未选中卡 → 单选它（保持多选时不动选择）
            self._select(card)
        multi = len(self._multi) > 1
        idx = self._cards.index(card)
        menu = QMenu(self)
        a_before = menu.addAction("添加到此步骤前方…")
        a_after = menu.addAction("添加到此步骤后方…")
        menu.addSeparator()
        a_copy = menu.addAction("复制")
        a_cut = menu.addAction("剪切")
        a_paste = menu.addAction("粘贴")
        menu.addSeparator()
        a_del = menu.addAction("删除")
        a_paste.setEnabled(bool(self._clipboard.steps))
        if multi:                        # 禁用项在设置默认可用性之后覆盖
            for a in (a_before, a_after, a_cut, a_paste, a_del):
                a.setEnabled(False)
        action = menu.exec_(global_pos)
        if action is a_before:
            self._add_step(idx)
        elif action is a_after:
            self._add_step(idx + 1)
        elif action is a_copy:
            self._copy_selected()
        elif action is a_cut:
            self._copy(idx)
            self._delete_step(idx)
        elif action is a_paste:
            self._paste(idx + 1)
        elif action is a_del:
            self._delete_step(idx)

    def _card_at(self, pos) -> Optional[StepCard]:
        item = self.itemAt(pos)
        if isinstance(item, QGraphicsProxyWidget):
            w = item.widget()
            if isinstance(w, StepCard):
                return w
        return None

    # ---- 操作 ----
    def _add_step(self, index: int) -> None:
        dlg = TemplateChooserDialog(self._mgr, self)
        if dlg.exec_() != QDialog.Accepted:
            return
        path = dlg.selected_path()
        if not path:
            return
        step = self._mgr.create_step(path)
        sl = self._step_list
        if sl is None:
            return
        if index == -1 or index >= len(sl):
            sl.add(step)
        else:
            sl.insert(index, step)
        self.refresh()
        self.edited.emit()

    def _copy(self, index: int) -> None:
        sl = self._step_list
        if sl is None:
            return
        self._clipboard.steps = [sl[index].to_format_string()]

    def _copy_selected(self) -> None:
        """复制全部选中卡（多选按卡片显示序）→ 剪贴板（可多次粘贴/跨列表粘贴）。"""
        cards = self._selected_cards()
        if not cards:
            return
        self._clipboard.steps = [c.step.to_format_string() for c in cards]

    def _paste(self, index: int) -> None:
        if not self._clipboard.steps or self._step_list is None:
            return
        try:
            self._step_list.insert_format_strings(
                index, self._clipboard.steps, self._mgr)
        except ValueError as e:
            QMessageBox.warning(self, "粘贴", "无法粘贴：%s" % e)
            return
        self.refresh()
        self.edited.emit()

    def _delete_step(self, index: int) -> None:
        sl = self._step_list
        if sl is None:
            return
        if QMessageBox.question(
                self, "删除", "确定删除该步骤？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes) != QMessageBox.Yes:
            return
        sl.remove(index)
        self.refresh()
        self.edited.emit()


if __name__ == "__main__":
    import sys

    from PyQt5.QtCore import QEvent, QPoint, QPointF, Qt
    from PyQt5.QtGui import QWheelEvent
    from PyQt5.QtWidgets import QApplication, QDialog, QMessageBox

    from model.step import Step
    from model.kscp_package import KscpPackage
    from model.project_variable import ProjectVariable
    from model.step_list import StepList
    from model.step_list_store import StepListStore
    from model.step_manager import StepManager
    from model.variable_tree import VariableTree

    app = QApplication.instance() or QApplication(sys.argv)

    pkg = KscpPackage.create_empty()
    tree = VariableTree.create_empty()
    tree.add("n1", ProjectVariable.create("number", 100, pkg))

    # 模板字节（有效模板；中文/引号内容一律用 .encode("utf-8")，禁用中文 bytes 字面量）
    GOOD = '''# -*- coding: utf-8 -*-
from dataclasses import dataclass
from actions.base import Step

@dataclass
class _DemoInput:
    count: "number" = 0

@dataclass
class _DemoOutput:
    total: "number" = 0

class DemoStep(Step):
    name = "示例"
    description = "测试模板"
    input_class = _DemoInput
    output_class = _DemoOutput

    def run(self) -> int:
        self.outputs.total = self.inputs.count * 2
        return 1
'''
    pkg.write_file("actions/示例.py", GOOD.encode("utf-8"))
    pkg.write_file("actions/控制流程/延时.py",
                   GOOD.replace('name = "示例"', 'name = "延时"').encode("utf-8"))
    mgr = StepManager(pkg, tree)
    mgr.load()

    def make_step() -> Step:
        s = mgr.create_step("示例")
        s.io.change_value("input", 0, "5")
        s.io.change_value("output", 0, "n1")
        return s

    # 装配 store + 列表
    store = StepListStore.create_empty()
    sl = StepList.create_empty()
    sl.add(make_step())
    sl.add(make_step())
    store.add_list("主列表", sl)
    sl2 = StepList.create_empty()
    store.add_list("空列表", sl2)

    clipboard = StepClipboard()
    view = StepListView(mgr, clipboard)
    view.resize(400, 360)
    edited = []
    view.edited.connect(lambda: edited.append(1))

    # 空列表 → 提示项存在、无卡片
    view.set_list(sl2, mgr)
    assert view._cards == [] and view._hint is not None

    # 绑定列表 → 卡片数 = 步骤数
    view.set_list(sl, mgr)
    assert len(view._cards) == 2 and view._hint is None
    assert view._proxies[0].scale() == 1.0

    # 滚轮（垂直增量）→ 水平滚动条移动
    hsb = view.horizontalScrollBar()
    old = hsb.value()
    ev = QWheelEvent(QPointF(10, 10), QPointF(10, 10), QPoint(0, 0),
                     QPoint(0, -240), 0, Qt.Horizontal,
                     Qt.NoButton, Qt.NoModifier)
    view.wheelEvent(ev)
    assert hsb.value() != old
    # 事件过滤器：卡片滚轮转发（同一处理路径）
    assert view.eventFilter(view._cards[0], ev) is True

    # 悬停缩放：Enter → 目标放大；Leave → 还原（不启动事件循环，验证动画参数）
    enter = QEvent(QEvent.Enter)
    leave = QEvent(QEvent.Leave)
    view.eventFilter(view._cards[0], enter)
    assert view._anims[0].endValue() == 1.06
    view.eventFilter(view._cards[0], leave)
    assert view._anims[0].endValue() == 1.0

    # 添加（类级补丁模板对话框；头部/尾部/中间）
    orig_exec = TemplateChooserDialog.exec_
    orig_path = TemplateChooserDialog.selected_path
    TemplateChooserDialog.exec_ = lambda self: QDialog.Accepted
    TemplateChooserDialog.selected_path = lambda self: "示例"
    try:
        view._add_step(0)                      # 头部
        assert len(sl) == 3 and sl[0].name == "示例"
        view._add_step(-1)                     # 尾部
        assert len(sl) == 4
        view._add_step(2)                      # 中间（前方/后方同路径）
        assert len(sl) == 5
    finally:
        TemplateChooserDialog.exec_ = orig_exec
        TemplateChooserDialog.selected_path = orig_path
    assert edited == [1, 1, 1]                 # 每次添加发 edited

    # 复制 → 剪贴板；粘贴 → 插入指定位置（后方）
    view._copy(0)
    assert clipboard.steps == [sl[0].to_format_string()]
    before = len(sl)
    view._paste(1)
    assert len(sl) == before + 1
    assert sl[1].to_format_string() == clipboard.steps[0]

    # 剪切 = 复制 + 删除（补丁确认框；剪贴板保留）
    orig_q = QMessageBox.question
    QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)
    try:
        n = len(sl)
        view._copy(2)
        view._delete_step(2)
        assert len(sl) == n - 1
        assert clipboard.steps is not None          # 剪贴板保留（可再次粘贴）
        view._paste(2)
        assert len(sl) == n
    finally:
        QMessageBox.question = orig_q

    # refresh_validity：不重建（卡片数不变）
    ncards = len(view._cards)
    view.refresh_validity()
    assert len(view._cards) == ncards

    # TemplateChooserDialog：分组 + 叶子 UserRole = 路径（不 exec）
    dlg = TemplateChooserDialog(mgr, None)
    top = [dlg._tw.topLevelItem(i).text(0)
           for i in range(dlg._tw.topLevelItemCount())]
    assert top == ["控制流程", "示例"], top
    delay = dlg._tw.topLevelItem(0)
    assert delay is not None and delay.childCount() == 1
    leaf = delay.child(0)
    assert leaf is not None and leaf.data(0, _PATH_ROLE) == "控制流程/延时"
    assert dlg._tw.topLevelItem(1).data(0, _PATH_ROLE) == "示例"
    # 未选叶子 → 添加禁用；选叶子 → 可选
    assert dlg._ok.isEnabled() is False
    dlg._tw.setCurrentItem(leaf)
    assert dlg.selected_path() == "控制流程/延时"
    assert dlg._ok.isEnabled() is True
    # 选组 → accept 被拒（未选叶子）
    dlg._tw.setCurrentItem(delay)
    dlg.accept()
    assert dlg.result() == 0

    # ---- I-1：卡片内 io 编辑 → edited（宿主保存链路；经真实 textChanged 路径） ----
    # 重建后的卡片仍可编辑不崩：同一 step 曾多次建卡（io 多个已生成控件，旧控件已销毁）
    probe_view = StepListView(mgr, StepClipboard())
    p2 = StepList.create_empty()
    p2.add(make_step())
    probe_view.set_list(p2, mgr)
    probe_view.refresh()          # 同 step 重建（io 再次 gen_widget）
    probe_view.refresh()
    probe_view._cards[0]._io_widget.input_fields[0].setText("42")
    n_before = len(edited)
    view._cards[0]._io_widget.input_fields[0].setText("42")   # 模拟卡片内用户输入
    assert len(edited) == n_before + 1, edited                # io 编辑 → edited +1

    # ---- I-2：悬停动画结束后再次悬停（事件循环已销毁动画对象）→ 不崩、正常缩放 ----
    # 修复前：finished 后动画残留 _anims；deleteLater 销毁 C++ 对象后再次 Enter/Leave
    # → pop 出死动画 → old.stop() → RuntimeError: wrapped C/C++ object has been deleted
    import time as _t
    aview = StepListView(mgr, StepClipboard())
    alist3 = StepList.create_empty()
    alist3.add(make_step())
    aview.set_list(alist3, mgr)
    aview.eventFilter(aview._cards[0], QEvent(QEvent.Enter))   # 放大动画开始
    a1 = aview._anims[0]
    _dl = _t.time() + 2.0
    while a1.state() != QVariantAnimation.Stopped and _t.time() < _dl:
        app.processEvents()                    # 驱动动画定时器
        _t.sleep(0.005)
    app.processEvents()                        # 处理 DeferredDelete → 动画 C++ 对象已销毁
    assert 0 not in aview._anims               # 修复：字典不残留已销毁的动画
    aview.eventFilter(aview._cards[0], QEvent(QEvent.Leave))   # 修复前：此处 RuntimeError
    aview.eventFilter(aview._cards[0], QEvent(QEvent.Enter))   # 再次放大（不触碰死对象）
    assert aview._anims[0].endValue() == 1.06

    # ---- I-3：内容不足视口时默认居左（不居中） ----
    # QGraphicsView 默认 AlignCenter：卡片少于铺满视口时整排居中 → 靠左
    assert view.alignment() == (Qt.AlignLeft | Qt.AlignVCenter)
    # 场景高度随卡片尺寸动态：卡顶留白 + 卡片 + 放大余量 + 错误标签槽 + 边距
    _pad0 = view._cards[0].height() * _SCALE_GROW
    _slot0 = _label_slot()
    assert view.scene().sceneRect().height() \
        == round(_pad0 + _slot0 + _EDGE) + view._cards[0].height() \
        + _pad0 + _slot0 + _EDGE

    # ---- J-1：refresh 重建后场景无幽灵 proxy ----
    # 修复前：refresh 只清 Python 列表、从不 removeItem，旧 proxy 永久残留叠加；
    # 右键点到幽灵卡片 → _cards.index(card) 抛 ValueError。
    n_cards = len(view._cards)
    proxies = [i for i in view.scene().items()
               if isinstance(i, QGraphicsProxyWidget)]
    assert len(proxies) == n_cards, (len(proxies), n_cards)
    view.refresh()                                 # 重建（移除旧 proxy 并重加）
    proxies2 = [i for i in view.scene().items()
                if isinstance(i, QGraphicsProxyWidget)]
    assert len(proxies2) == len(view._cards) == n_cards, \
        (len(proxies2), len(view._cards))
    # 场景中的每张卡片都在 _cards 里（右键菜单索引不崩）
    ws = [p.widget() for p in proxies2 if isinstance(p.widget(), StepCard)]
    assert all(w in view._cards for w in ws)

    # ---- J-2：卡片在 proxy 中离屏渲染非白（白屏回归防线） ----
    # 修复前：StepCard 上挂 QGraphicsDropShadowEffect → QGraphicsProxyWidget
    # 整体渲染白屏（离屏 render 与真实窗口均白，非白采样 ≈ 0）。
    from PyQt5.QtGui import QPainter, QPixmap
    pm = QPixmap(900, 420)
    pm.fill(Qt.white)
    p = QPainter(pm)
    view.render(p)
    p.end()
    img = pm.toImage()
    non_white = 0
    for x in range(0, img.width(), 4):
        for y in range(0, img.height(), 4):
            c = img.pixelColor(x, y)
            if c.alpha() > 0 and (c.red() < 245 or c.green() < 245
                                  or c.blue() < 245):
                non_white += 1
    assert non_white > 3000, non_white

    # ---- J-3：卡片右键菜单弹在鼠标处（exec_ 收到全局坐标） ----
    # python -m 冒烟注意：运行中的 __main__ 是 runpy 的临时模块，import 自身
    # 拿不到它（_t_probe 探针证实 globals 不同一），故必须用 globals() 替换
    # 本模块的 QMenu 才能让运行中的 _on_context_menu 命中打桩类。
    import PyQt5.QtWidgets as _W

    class _MenuRec2(_W.QMenu):
        """记录 exec_ 收到的坐标（不真弹窗）。"""
        got_pos = None

        def exec_(self, *args):
            _MenuRec2.got_pos = args[0] if args else None
            return None

    _orig_qmenu = QMenu
    globals()["QMenu"] = _MenuRec2           # 替换运行中模块的 QMenu（C++ 方法不可直接 patch）
    try:
        vp = view.viewport()
        pos = QPoint(vp.width() // 2, 100)   # viewport 局部坐标（命中卡片中部）
        view._on_context_menu(pos)           # 修复前：菜单 exec_ 收到局部坐标 → 视图左上角弹出
        assert _MenuRec2.got_pos == vp.mapToGlobal(pos), _MenuRec2.got_pos
        # 卡片右键信号路径（StepCard.contextMenuEvent 已传全局坐标 → 原样透传）
        view._on_card_menu(view._cards[0], QPoint(123, 456))
        assert _MenuRec2.got_pos == QPoint(123, 456)
    finally:
        globals()["QMenu"] = _orig_qmenu

    # ---- J-4：空列表提示居中 + 22 号宋体 ----
    view.set_list(StepList.create_empty(), mgr)   # 空列表 → hint 提示
    view.show()                                  # 未显示时 viewport 布局事件不派发，
    app.processEvents()                          # resize 后视口几何不更新 → 居中断言不稳定
    view._center_hint()                          # 视口几何就绪后提示重新居中
    h = view._hint
    assert h is not None
    assert h.font().family() == "SimSun" and h.font().pointSize() == 22
    center = view.mapToScene(view.viewport().rect().center())
    r = h.boundingRect()
    hp = h.pos()
    assert abs(hp.x() - (center.x() - r.width() / 2.0)) < 2.0 \
        and abs(hp.y() - (center.y() - r.height() / 2.0)) < 2.0, hp
    # 窗口尺寸变化 → 提示重新居中
    view.resize(500, 300)
    app.processEvents()
    app.processEvents()
    center2 = view.mapToScene(view.viewport().rect().center())
    r2 = h.boundingRect()
    hp2 = h.pos()
    assert abs(hp2.x() - (center2.x() - r2.width() / 2.0)) < 2.0 \
        and abs(hp2.y() - (center2.y() - r2.height() / 2.0)) < 2.0, hp2

    # ---- J-5：卡片错误 → 卡片外正下方错误标签；编辑实时同步 / 修复移除 ----
    view.set_list(sl, mgr)
    # 补全全部卡片 io（菜单添加/粘贴的步骤 io 为空）→ 无标签
    for c in view._cards:
        c.step.io.change_value("input", 0, "5")
        c.step.io.change_value("output", 0, "n1")
    view.refresh()
    assert view._error_labels == {}
    bad = view._cards[0]
    bad._io_widget.input_fields[0].setText("")    # 真实 textChanged 路径 → io_changed
    lbl = view._error_labels.get(bad)
    assert lbl is not None, view._error_labels
    assert lbl.text() == "⚠: 输入参数为空", lbl.text()
    proxy = view._proxies[0]
    r = lbl.boundingRect()
    p = proxy.pos()
    assert abs(lbl.pos().x() - (p.x() + (bad.width() - r.width()) / 2.0)) < 2.0
    # 错误标签在放大余量之外（中心放大向下扩 pad）→ 不被放大卡片遮挡
    assert abs(lbl.pos().y()
               - (p.y() + bad.height() + bad.height() * _SCALE_GROW + 4.0)) < 2.0
    # 第二张卡输出未指定 → 多卡并存（输出字段只读，走数据层 + 重检路径：
    # 真实场景 = picker 选择变化（触发 io_changed）或变量树变化（refresh_validity））
    bad2 = view._cards[1]
    bad2.step.io.change_value("output", 0, "")
    view.refresh_validity()
    lbl2 = view._error_labels.get(bad2)
    assert lbl2 is not None and lbl2.text() == "⚠: 输出变量未指定", lbl2.text()
    # refresh_validity（变量树变化路径）：不重建、标签仍在
    view.refresh_validity()
    assert view._error_labels.get(bad) is not None
    # 修好第一张卡 → 标签移除；第二张仍坏
    bad._io_widget.input_fields[0].setText("5")
    assert view._error_labels.get(bad) is None
    assert view._error_labels.get(bad2) is not None
    # refresh 重建 → 场景无幽灵标签（错误 + 序号标签与字典一致）
    view.refresh()
    labels = [i for i in view.scene().items()
              if isinstance(i, QGraphicsSimpleTextItem)]
    assert len(labels) == len(view._error_labels) + len(view._index_labels) \
        and len(view._error_labels) == 1, \
        (len(labels), len(view._error_labels), len(view._index_labels))

    # ---- J-6：视图最小高度 ≥ 卡片放大后高度 + 标签槽 + 视口外占用（压缩不裁剪） ----
    view.set_list(sl, mgr)
    h = view._cards[0].height()
    pad6 = h * _SCALE_GROW
    slot6 = _label_slot()
    y6 = round(pad6 + slot6 + _EDGE)
    scene6 = y6 + h + pad6 + slot6 + _EDGE
    assert view.minimumHeight() == round(scene6) + view._viewport_overhead()
    assert view.scene().sceneRect().height() == scene6
    # 空列表 → 无卡片 → 最小高度归零（无放大保护）
    view.set_list(StepList.create_empty(), mgr)
    assert view.minimumHeight() == 0

    # ---- J-6b：压缩到最小尺寸时卡片外标签完整可见（不被视口/场景切） ----
    # 单卡坏列表：卡片/标签都在视口宽度内 → 滚动位置 0 时即全部可见
    one = StepList.create_empty()
    one.add(make_step())
    one[0].io.change_value("output", 0, "")
    view.set_list(one, mgr)
    view.resize(600, view.minimumHeight())   # 最小高 + 正常宽 → 底部不切
    app.processEvents()
    vp = view.viewport().rect()
    for lbl in (list(view._error_labels.values())
                + list(view._index_labels.values())):
        r = view.mapFromScene(lbl.sceneBoundingRect()).boundingRect()
        assert vp.contains(r), (vp, r, lbl.text())
    # 宽错误标签（多原因，文本宽于卡片）→ 场景宽扩展、标签完整在场景内
    for c in view._cards:
        c.step.io.change_value("input", 0, "")
        c.step.io.change_value("output", 0, "")
    view.refresh_validity()
    assert len(view._error_labels) == len(view._cards)
    sc_r = view.scene().sceneRect()
    for lbl in view._error_labels.values():
        br = lbl.sceneBoundingRect()
        assert br.x() >= sc_r.x() and br.right() <= sc_r.right(), \
            (lbl.text(), br, sc_r)

    # ---- J-7：序号标签 (n/总数) 在卡片正上方 ----
    view.set_list(sl, mgr)
    n7 = len(view._cards)
    assert len(view._index_labels) == n7
    for i, c in enumerate(view._cards, 1):
        lbl = view._index_labels[c]
        assert lbl.text() == "(%d/%d)" % (i, n7), lbl.text()
        px = view._proxies[i - 1].pos()
        r = lbl.boundingRect()
        assert abs(lbl.pos().x() - (px.x() + (c.width() - r.width()) / 2.0)) < 2.0
        assert lbl.pos().y() <= px.y() - 2.0         # 卡片外正上方
    assert min(l.pos().y() for l in view._index_labels.values()) >= 0.0, \
        "序号标签不得裁出场景顶部"

    # ---- J-8：跳转序号 / 搜索标签定位 ----
    assert view.jump_to_index(0) is False
    assert view.jump_to_index(n7 + 1) is False
    for c in view._cards:
        c.step.tag = ""
    view._cards[2].step.tag = "关键步骤"
    assert view.locate_by_tag("关键") is True
    assert view._selected is view._cards[2]          # 定位并选中
    assert view.locate_by_tag("不存在") is False
    # 从当前选中卡之后继续找下一张匹配
    view._cards[4].step.tag = "关键步骤2"
    assert view.locate_by_tag("关键") is True
    assert view._selected is view._cards[4]
    # 循环到开头：选中最后一张后，仍能找到后续匹配
    view._select(view._cards[n7 - 1])
    assert view.locate_by_tag("关键") is True
    assert view._selected is view._cards[2]

    # ---- J-9：错误卡片统计 + 跳转错误（计数随重建/编辑/重检路径同步） ----
    counts = []
    view.errors_changed.connect(lambda n: counts.append(n))
    view.set_list(sl, mgr)                     # 重建 → 发计数
    assert counts[-1] == 1, counts             # J-5 遗留：cards[1] 输出未指定
    assert view.error_card_indices() == [2]
    assert view.jump_to_error() is True
    assert view._selected is view._cards[1]    # 定位到唯一坏卡
    assert view.jump_to_error() is True        # 仅一张坏卡 → 绕回同一张
    assert view._selected is view._cards[1]
    # 弄坏 cards[0] → 两张坏卡 [1,2]（输入字段 blockSignals，change_value 不发射
    # → 显式重检路径 refresh_validity 才发计数）
    view._cards[0].step.io.change_value("input", 0, "")
    view.refresh_validity()
    assert counts[-1] == 2, counts
    assert view.error_card_indices() == [1, 2]
    view._select(view._cards[1])
    assert view.jump_to_error() is True
    assert view._selected is view._cards[0]    # 从选中之后循环到开头
    assert view.jump_to_error() is True
    assert view._selected is view._cards[1]    # 下一张
    view.refresh_validity()                    # 再重检 → 计数仍 2
    assert counts[-1] == 2, counts
    # 全部修好 → 计数 0、无卡可跳（输出字段 setText 无 blockSignals → 编辑路径先发）
    view._cards[0].step.io.change_value("input", 0, "5")
    view._cards[1].step.io.change_value("output", 0, "n1")
    assert counts[-1] == 0, counts            # 输出框 textChanged → 单卡路径即时同步
    assert view.error_card_indices() == []
    assert view.jump_to_error() is False

    # ---- J-10：放大后卡片不遮挡序号/错误标签（中心放大上下各扩 pad） ----
    for i, c in enumerate(view._cards):
        pr = view._proxies[i]
        pr.setScale(_SCALE_MAX)                # 直接置最终缩放（不动画）
        rb = pr.sceneBoundingRect()            # 放大后卡片几何（含变换）
        lr = view._index_labels[c].boundingRect()
        lp = view._index_labels[c].pos()
        assert lp.y() + lr.height() <= rb.top() - 2.0, \
            (i, lp.y(), lr.height(), rb.top())       # 序号标签在放大卡顶之外
        el = view._error_labels.get(c)
        if el is not None:
            er = el.boundingRect()
            ep = el.pos()
            assert ep.y() >= rb.bottom() + 2.0, \
                (i, ep.y(), rb.bottom())             # 错误标签在放大卡底之外
        pr.setScale(1.0)
    # 标签完整落在场景内（顶部/底部不被裁剪）
    assert min(l.pos().y() for l in view._index_labels.values()) >= 0.0
    for el in view._error_labels.values():
        assert el.pos().y() + el.boundingRect().height() \
            <= view.scene().sceneRect().height()

    # ---- 多选复制：Ctrl+点击加选/减选、单选清空、复制按卡片序、粘贴多条/跨列表 ----
    slx = StepList.create_empty()
    for v in ("7", "8", "9"):
        sx = mgr.create_step("示例")
        sx.io.change_value("input", 0, v)
        sx.io.change_value("output", 0, "n1")
        slx.add(sx)
    view.set_list(slx, mgr)
    c0, c1, c2 = view._cards

    view._select(c0)                            # 普通点击 = 单选（清多选）
    assert view._selected is c0 and view._multi == [c0]
    view._select_toggle(c1)                     # Ctrl+点击加选
    assert view._multi == [c0, c1]
    assert c0.property("selected") and c1.property("selected")
    view._select_toggle(c1)                     # 再点 → 减选
    assert view._multi == [c0] and not c1.property("selected")
    view._select_toggle(c2)
    assert view._multi == [c0, c2] and view._selected is c2

    # 事件过滤器路径：左键 MouseButtonPress + Ctrl → toggle；普通左键 → 单选；
    # 右键按下不改变选择（交给 contextMenuEvent）
    from PyQt5.QtGui import QMouseEvent
    me = QMouseEvent(QEvent.MouseButtonPress, QPointF(5, 5), Qt.LeftButton,
                     Qt.LeftButton, Qt.ControlModifier)
    view.eventFilter(c1, me)
    assert view._multi == [c0, c2, c1]
    me2 = QMouseEvent(QEvent.MouseButtonPress, QPointF(5, 5), Qt.LeftButton,
                      Qt.LeftButton, Qt.NoModifier)
    view.eventFilter(c1, me2)
    assert view._multi == [c1] and view._selected is c1
    me3 = QMouseEvent(QEvent.MouseButtonPress, QPointF(5, 5), Qt.RightButton,
                      Qt.RightButton, Qt.NoModifier)
    view.eventFilter(c2, me3)                   # 右键按下 → 不动选择
    assert view._multi == [c1]

    # ---- Shift+点击：锚点范围选择（锚点 = 最近普通/Ctrl 点击的卡） ----
    view._select(c0)                            # 普通点击 → 锚点 = c0
    assert view._anchor is c0
    me_s = QMouseEvent(QEvent.MouseButtonPress, QPointF(5, 5), Qt.LeftButton,
                       Qt.LeftButton, Qt.ShiftModifier)
    view.eventFilter(c2, me_s)                  # Shift 点 c2 → c0..c2 全选
    assert view._multi == [c0, c1, c2]
    assert view._selected is c2 and view._anchor is c0   # 锚点不动
    assert all(c.property("selected") for c in (c0, c1, c2))
    view.eventFilter(c1, me_s)                  # 连续 Shift 点 c1 → 重选 c0..c1
    assert view._multi == [c0, c1]
    view._select_toggle(c2)                     # Ctrl 点击 → 锚点更新为 c2
    assert view._anchor is c2
    view.eventFilter(c0, me_s)                  # Shift 点 c0 → c0..c2（反向范围）
    assert view._multi == [c0, c1, c2]
    # 无锚点（失效/首操作）→ 本次回退第一张卡：Shift 点 c1 → c0..c1；
    # 锚点保持失效（不写回，下次 Shift 仍从第一张起）
    view._multi = []
    view._selected = None
    view._anchor = None
    view.eventFilter(c1, me_s)
    assert view._multi == [c0, c1] and view._selected is c1 and view._anchor is None

    # 菜单多选态：只留「复制」，添加/剪切/粘贴/删除禁用；右键已选卡保持多选
    view._select(c0)
    view._select_toggle(c1)
    assert view._multi == [c0, c1]

    class _MenuRec3(_W.QMenu):
        last = None

        def exec_(self, *args):
            _MenuRec3.last = [(a.text(), a.isEnabled()) for a in self.actions()
                              if not a.isSeparator()]
            return None

    _orig_qmenu3 = QMenu
    globals()["QMenu"] = _MenuRec3
    try:
        view._card_menu(c0, QPoint(1, 1))
        texts = dict(_MenuRec3.last)
        assert texts["复制"] is True
        for t in ("添加到此步骤前方…", "添加到此步骤后方…",
                  "剪切", "粘贴", "删除"):
            assert texts[t] is False, texts
        assert view._multi == [c0, c1]           # 右键已选卡 → 选择不动
        # 单卡菜单回归：全部可用（粘贴随剪贴板非空）
        view._select(c2)
        view._card_menu(c2, QPoint(1, 1))
        texts = dict(_MenuRec3.last)
        assert all(texts[t] for t in (
            "添加到此步骤前方…", "添加到此步骤后方…", "复制", "剪切", "粘贴", "删除")), texts
    finally:
        globals()["QMenu"] = _orig_qmenu3

    # 多选复制：按卡片显示序多条 → 剪贴板；粘贴 → 多条一起插入
    view._select(c0)
    view._select_toggle(c1)
    view._copy_selected()
    assert clipboard.steps == [c0.step.to_format_string(),
                               c1.step.to_format_string()]
    n = len(slx)
    view._paste(1)
    assert len(slx) == n + 2
    assert slx[1].to_format_string() == clipboard.steps[0]
    assert slx[2].to_format_string() == clipboard.steps[1]
    # 跨列表粘贴：切到另一列表（剪贴板保留）→ 尾部插入
    view.set_list(sl2, mgr)
    assert view._cards == []
    view._paste(0)
    assert len(sl2) == 2
    assert sl2[0].to_format_string() == clipboard.steps[0]
    assert sl2[1].to_format_string() == clipboard.steps[1]

    print("StepListView smoke OK")
