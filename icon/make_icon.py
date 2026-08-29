# -*- coding: utf-8 -*-
"""
生成 KScript 程序图标：``icon/kscript.ico``（多尺寸）+ ``kscript.png``（256）+ ``kscript.svg``（矢量源）。

设计：蓝→紫渐变圆角底（呼应卡片选中蓝）+ 三张半透明白色层叠步骤卡片
（呼应毛玻璃卡片）+ 柔和绿播放三角（自动化执行语义）。

运行：``python icon/make_icon.py``（重新生成；文件内容变化需同步重跑）。
"""

import os
import struct
import sys

from PyQt5.QtCore import QBuffer, QIODevice, QRectF, Qt
from PyQt5.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPixmap
from PyQt5.QtWidgets import QApplication

OUT = os.path.dirname(os.path.abspath(__file__))
SIZES = (16, 24, 32, 48, 64, 128, 256)

SVG = """<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256" viewBox="0 0 256 256">
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


def draw_icon(size: int) -> QPixmap:
    """按尺寸绘制图标（256 基准等比例缩放）。"""
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


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    master = draw_icon(256)
    pngs = {}
    for size in SIZES:
        pm = master if size == 256 else master.scaled(
            size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        pngs[size] = png_bytes(pm)
    with open(os.path.join(OUT, "kscript.ico"), "wb") as f:
        f.write(build_ico(pngs))
    with open(os.path.join(OUT, "kscript.png"), "wb") as f:
        f.write(pngs[256])
    with open(os.path.join(OUT, "kscript.svg"), "w", encoding="utf-8") as f:
        f.write(SVG)
    print("icons written to %s" % OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
