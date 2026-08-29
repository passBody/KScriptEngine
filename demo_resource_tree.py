# -*- coding: utf-8 -*-
"""
KScript 资源管理树 —— 演示脚本
==============================

运行::

    python demo_resource_tree.py            # 交互式打开窗口
    python demo_resource_tree.py --check    # 自检：构建、渲染、800ms 后自动退出（不交互）
    python demo_resource_tree.py --save sample.kscp   # 把示例包存成 .kscp 文件（供 main.py 打开）

窗口左侧是 ``ResourceTreeWidget``（管理 KscpPackage 的 assets/），右侧是预览面板。
可：
* Ctrl/Shift 多选；
* 右键空白或某项弹上下文菜单：复制 / 剪切 / 粘贴 / 重命名 / 删除 / 添加（文件/组）；
* 点选某项在右侧预览（png 缩略图 / 文本 / 二进制占位 / 目录占位）。

示例包内含：封面.png（生成）、说明.txt、data.bin、音乐/、音乐/封面2.png、脚本/run.py、空目录。
"""

import sys

from PyQt5.QtCore import QTimer
from PyQt5.QtGui import QColor, QImage
from PyQt5.QtWidgets import QApplication, QMainWindow, QSplitter

from model import KscpPackage
from widgets import ResourceTreeWidget


def _make_png(color: str) -> bytes:
    """用 QImage 生成一张 96x64 纯色 PNG 的字节。"""
    img = QImage(96, 64, QImage.Format_RGB32)
    img.fill(QColor(color))
    from PyQt5.QtCore import QBuffer
    buf = QBuffer()
    buf.open(QBuffer.ReadWrite)
    img.save(buf, "PNG")
    return bytes(buf.data())


def build_sample_package() -> KscpPackage:
    pkg = KscpPackage.create_empty()
    pkg.write_file("assets/封面.png", _make_png("#3a7bd5"))
    pkg.write_file("assets/说明.txt",
                   "KScript 资源管理树演示\n"
                   "本文件是 utf-8 文本预览示例。\n"
                   "右键可复制/剪切/粘贴/重命名/删除/添加。\n"
                   "粘贴重名会自动追加 (1)(2)…".encode("utf-8"))
    pkg.write_file("assets/data.bin", bytes(range(256)))
    pkg.write_file("assets/音乐/封面2.png", _make_png("#e15554"))
    pkg.write_file("assets/音乐/2.txt", "音乐目录下的文本。".encode("utf-8"))
    pkg.write_file("assets/脚本/run.py", b"print('hello from KScript')\n")
    pkg.make_dir("assets/空目录")
    return pkg


def make_window():
    pkg = build_sample_package()
    tree = ResourceTreeWidget(pkg)
    win = QMainWindow()
    win.setWindowTitle("KScript 资源管理树 演示")
    win.resize(900, 600)
    sp = QSplitter()
    sp.addWidget(tree)
    preview = tree.preview_widget()
    preview.setMinimumWidth(280)
    sp.addWidget(preview)
    sp.setStretchFactor(0, 2)
    sp.setStretchFactor(1, 3)
    win.setCentralWidget(sp)
    win.statusBar().showMessage(
        "右键：复制/剪切/粘贴/重命名/删除/添加；Ctrl/Shift 多选；点选预览；点击图片开大图（滚轮缩放/拖拽平移）")
    return win


def main() -> int:
    args = sys.argv[1:]
    app = QApplication.instance() or QApplication(sys.argv)  # QImage 需 app
    if "--save" in args:
        i = args.index("--save")
        path = args[i + 1] if i + 1 < len(args) else "sample.kscp"
        build_sample_package().save(path)
        print("saved:", path)
        return 0
    check = "--check" in args
    win = make_window()
    win.show()
    if check:
        QTimer.singleShot(800, app.quit)
    return app.exec_()


if __name__ == "__main__":
    sys.exit(main())
