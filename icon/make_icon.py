# -*- coding: utf-8 -*-
"""
生成 KScript 图标两套（各含多尺寸 ``.ico`` + 256 ``.png`` + 矢量 ``.svg``）：

* ``kscript.*`` —— **程序图标**：蓝→紫渐变圆角底（呼应卡片选中蓝）+ 三张半透明白色
  层叠步骤卡片（呼应毛玻璃卡片）+ 柔和绿播放三角（自动化执行语义）。
* ``kscp.*`` —— **工程文件图标**（资源管理器里 ``.kscp`` 的显示图标，由
  ``tools/kscp_assoc.py`` 注册到注册表）：白纸 + 右上折角（一眼认出"这是文件"），
  纸面三条蓝→紫渐变步骤条 + 绿播放三角（与程序图标同一套视觉语言）。

两套共用 ``png_bytes`` / ``build_ico`` / ``SIZES``，改一处尺寸表两套同步。

运行：``python icon/make_icon.py``（重新生成；文件内容变化需同步重跑）。
"""

import os
import struct
import sys

from PyQt5.QtCore import QBuffer, QIODevice, QRectF, Qt
from PyQt5.QtGui import (QColor, QLinearGradient, QPainter, QPainterPath, QPen,
                         QPixmap)
from PyQt5.QtWidgets import QApplication

OUT = os.path.dirname(os.path.abspath(__file__))
SIZES = (16, 24, 32, 48, 64, 128, 256)

# ---------------------------------------------------------------- 程序图标

APP_SVG = """<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256" viewBox="0 0 256 256">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="256" y2="256" gradientUnits="userSpaceOnUse">
      <stop offset="0" stop-color="#4f8ce8"/>
      <stop offset="1" stop-color="#6a5acd"/>
    </linearGradient>
  </defs>
  <rect x="0" y="0" width="256" height="256" rx="56" fill="url(#bg)"/>
  <rect x="0" y="0" width="256" height="96" rx="56" fill="#ffffff" fill-opacity="0.10"/>
  <rect x="52" y="88" width="112" height="84" rx="14" fill="#ffffff" fill-opacity="0.74"/>
  <rect x="52" y="108" width="112" height="84" rx="14" fill="#ffffff" fill-opacity="0.86"/>
  <rect x="52" y="128" width="112" height="84" rx="14" fill="#ffffff" fill-opacity="0.98"/>
  <path d="M162 136 L162 184 L210 160 Z" fill="#3fb27a"/>
</svg>
"""

# ---------------------------------------------------------------- 文件图标

# 纸张：x 40..216、y 24..232，圆角 28；右上折角 F=56 → 斜边 (160,24)→(216,80)。
# 折角背面三角 = 该角沿斜边翻折后的落点，恰好是 (160,24)-(160,80)-(216,80)。
_PAPER_D = ("M68 24 H160 L216 80 V204 A28 28 0 0 1 188 232 "
            "H68 A28 28 0 0 1 40 204 V52 A28 28 0 0 1 68 24 Z")

FILE_SVG = """<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256" viewBox="0 0 256 256">
  <defs>
    <linearGradient id="paper" x1="40" y1="24" x2="216" y2="232" gradientUnits="userSpaceOnUse">
      <stop offset="0" stop-color="#ffffff"/>
      <stop offset="1" stop-color="#eef2f8"/>
    </linearGradient>
    <linearGradient id="bar" x1="72" y1="0" x2="176" y2="0" gradientUnits="userSpaceOnUse">
      <stop offset="0" stop-color="#4f8ce8"/>
      <stop offset="1" stop-color="#6a5acd"/>
    </linearGradient>
  </defs>
  <path d="%s" fill="url(#paper)"/>
  <path d="M160 24 V80 H216 Z" fill="#d7e0ef"/>
  <path d="%s" fill="none" stroke="#b9c6da" stroke-width="6" stroke-linejoin="round"/>
  <rect x="72" y="100" width="104" height="22" rx="11" fill="url(#bar)"/>
  <rect x="72" y="134" width="104" height="22" rx="11" fill="url(#bar)"/>
  <rect x="72" y="168" width="52" height="22" rx="11" fill="url(#bar)"/>
  <path d="M146 158 L146 188 L176 173 Z" fill="#3fb27a"/>
</svg>
""" % (_PAPER_D, _PAPER_D)


def draw_app_icon(size: int) -> QPixmap:
    """程序图标（256 基准等比例缩放）。"""
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    s = size / 256.0
    R = lambda v: v * s   # 坐标缩放

    # 底：圆角渐变方块（蓝 → 紫，柔和）
    grad = QLinearGradient(0, 0, R(256), R(256))
    grad.setColorAt(0.0, QColor("#4f8ce8"))
    grad.setColorAt(1.0, QColor("#6a5acd"))
    p.setBrush(grad)
    p.setPen(Qt.NoPen)
    p.drawRoundedRect(QRectF(0, 0, R(256), R(256)), R(56), R(56))
    # 顶部柔光（毛玻璃质感）
    p.setBrush(QColor(255, 255, 255, 26))
    p.drawRoundedRect(QRectF(0, 0, R(256), R(96)), R(56), R(56))
    # 三张层叠步骤卡片（白、半透明、圆角；从左下阶梯错开）
    for dy, alpha in ((88, 190), (108, 220), (128, 250)):
        p.setBrush(QColor(255, 255, 255, alpha))
        p.drawRoundedRect(QRectF(R(52), R(dy), R(112), R(84)), R(14), R(14))
    # 播放三角（柔和绿，卡片右侧；执行语义）
    tri = QPainterPath()
    tri.moveTo(R(162), R(136))
    tri.lineTo(R(162), R(184))
    tri.lineTo(R(210), R(160))
    tri.closeSubpath()
    p.setBrush(QColor("#3fb27a"))
    p.drawPath(tri)
    p.end()
    return pm


def draw_file_icon(size: int) -> QPixmap:
    """工程文件（.kscp）图标（256 基准等比例缩放）。"""
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    s = size / 256.0
    R = lambda v: v * s

    # 纸张轮廓：左上圆角起步，顶边 → 折角斜边 → 右边 → 右下/左下圆角 → 左边
    paper_path = QPainterPath()
    paper_path.moveTo(R(68), R(24))
    paper_path.lineTo(R(160), R(24))
    paper_path.lineTo(R(216), R(80))                                  # 折角斜边
    paper_path.lineTo(R(216), R(204))
    paper_path.quadTo(R(216), R(232), R(188), R(232))                 # 右下圆角
    paper_path.lineTo(R(68), R(232))
    paper_path.quadTo(R(40), R(232), R(40), R(204))                   # 左下圆角
    paper_path.lineTo(R(40), R(52))
    paper_path.quadTo(R(40), R(24), R(68), R(24))                     # 左上圆角
    paper_path.closeSubpath()

    # 1) 纸面填充（先填充后描边：折角背面要压在填充上、压在描边下）
    paper_grad = QLinearGradient(R(40), R(24), R(216), R(232))
    paper_grad.setColorAt(0.0, QColor("#ffffff"))
    paper_grad.setColorAt(1.0, QColor("#eef2f8"))
    p.setPen(Qt.NoPen)
    p.setBrush(paper_grad)
    p.drawPath(paper_path)

    # 2) 折角背面：略深一档，读作"角被折下来了"
    fold = QPainterPath()
    fold.moveTo(R(160), R(24))
    fold.lineTo(R(160), R(80))
    fold.lineTo(R(216), R(80))
    fold.closeSubpath()
    p.setBrush(QColor("#d7e0ef"))
    p.drawPath(fold)

    # 3) 纸张描边（细线：16px 下仍留得住轮廓，但不糊成一块）
    p.setBrush(Qt.NoBrush)
    p.setPen(QPen(QColor("#b9c6da"), max(1.0, R(6))))
    p.drawPath(paper_path)

    # 4) 三条步骤条（蓝→紫渐变，与程序图标同色）；第三条缩短给播放三角让位
    bar_grad = QLinearGradient(R(72), 0, R(176), 0)
    bar_grad.setColorAt(0.0, QColor("#4f8ce8"))
    bar_grad.setColorAt(1.0, QColor("#6a5acd"))
    p.setPen(Qt.NoPen)
    p.setBrush(bar_grad)
    for y, w in ((100, 104), (134, 104), (168, 52)):
        p.drawRoundedRect(QRectF(R(72), R(y), R(w), R(22)), R(11), R(11))

    # 5) 播放三角（执行语义）
    tri = QPainterPath()
    tri.moveTo(R(146), R(158))
    tri.lineTo(R(146), R(188))
    tri.lineTo(R(176), R(173))
    tri.closeSubpath()
    p.setBrush(QColor("#3fb27a"))
    p.drawPath(tri)
    p.end()
    return pm


def png_bytes(pm: QPixmap) -> bytes:
    buf = QBuffer()
    buf.open(QIODevice.WriteOnly)
    pm.save(buf, "PNG")
    return bytes(buf.data())


def build_ico(pngs) -> bytes:
    """Vista+ PNG-in-ICO：ICONDIR + 条目表 + 各尺寸 PNG 数据。"""
    offset = 6 + 16 * len(pngs)
    entries = []
    body = []
    for size in SIZES:
        data = pngs[size]
        w = 0 if size == 256 else size
        entries.append(struct.pack(
            "<BBBBHHII", w, w, 0, 0, 1, 32, len(data), offset))
        offset += len(data)
        body.append(data)
    return struct.pack("<HHH", 0, 1, len(SIZES)) + b"".join(entries) + b"".join(body)


def write_set(stem: str, master: QPixmap, svg: str) -> None:
    """把一张 256 基准母图写成 ``<stem>.ico``（多尺寸）+ ``.png``（256）+ ``.svg``。"""
    pngs = {}
    for size in SIZES:
        pm = master if size == 256 else master.scaled(
            size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        pngs[size] = png_bytes(pm)
    with open(os.path.join(OUT, stem + ".ico"), "wb") as f:
        f.write(build_ico(pngs))
    with open(os.path.join(OUT, stem + ".png"), "wb") as f:
        f.write(pngs[256])
    with open(os.path.join(OUT, stem + ".svg"), "w", encoding="utf-8") as f:
        f.write(svg)


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)   # 必须持引用：无引用会被回收致崩溃
    write_set("kscript", draw_app_icon(256), APP_SVG)    # 程序图标
    write_set("kscp", draw_file_icon(256), FILE_SVG)     # .kscp 文件图标
    print("icons written to %s" % OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
