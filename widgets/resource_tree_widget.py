# -*- coding: utf-8 -*-
"""
全局资源管理树（GUI 控件）
========================

:class:`ResourceTreeWidget` 继承 :class:`QTreeWidget`，管理
:class:`model.kscp_package.KscpPackage` 中 ``assets/`` 目录的资源。支持
Ctrl/Shift 多选、右键上下文菜单（复制/粘贴/剪切/重命名/删除/添加），并可通过
:meth:`preview_widget` 显示预览面板（png 缩略图 / 只读文本 / 二进制占位）。

基本用法
--------
::

    from model import KscpPackage
    from widgets import ResourceTreeWidget
    from PyQt5.QtWidgets import QApplication, QMainWindow, QSplitter

    app = QApplication([])
    pkg = KscpPackage.create_empty()
    # ... 往 assets/ 里放些资源 ...
    tree = ResourceTreeWidget(pkg)
    win = QMainWindow()
    sp = QSplitter()
    sp.addWidget(tree)
    sp.addWidget(tree.preview_widget())
    win.setCentralWidget(sp)
    win.show(); app.exec_()
"""

from __future__ import annotations

import os
from typing import List, Optional, Tuple, TYPE_CHECKING

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QColor, QKeySequence, QPixmap
from PyQt5.QtWidgets import (
    QAbstractItemView, QDialog, QDialogButtonBox, QFileDialog, QInputDialog,
    QLabel, QMenu, QMessageBox, QShortcut, QStackedWidget, QStyle, QTextEdit,
    QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from model.kscp_package import KscpPackage
from widgets.image_overlay import ImageOverlay

if TYPE_CHECKING:
    ...

__all__ = ["ResourceTreeWidget"]

_PATH_ROLE = 0x0100  # Qt.UserRole（PyQt5 运行期可用，取整数值规避存根误报）
_IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp")


def _basename(path: str) -> str:
    return path.rsplit("/", 1)[-1]


def _parent(path: str) -> str:
    return path.rsplit("/", 1)[0] if "/" in path else ""


class _ClickableImageLabel(QLabel):
    """可点击的图片标签：左键点击发出 ``clicked``。"""

    clicked = pyqtSignal()

    def mousePressEvent(self, event) -> None:  # noqa: N802 (Qt 命名)
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class _PreviewPanel(QStackedWidget):
    """预览面板：占位 / 图片 / 只读文本 三页，resize 时重缩放图片。"""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._placeholder = QLabel("（无预览）")
        self._placeholder.setAlignment(Qt.AlignCenter)
        self._img_label = _ClickableImageLabel()
        self._img_label.setAlignment(Qt.AlignCenter)
        self._img_label.setMinimumSize(120, 120)
        self._img_label.setCursor(Qt.PointingHandCursor)
        self._img_label.setToolTip("点击查看大图（滚轮缩放 / 拖拽平移 / 双击或 Esc 关闭）")
        self._img_label.clicked.connect(self._open_image_dialog)
        self._text_edit = QTextEdit()
        self._text_edit.setReadOnly(True)
        self._raw_pixmap: Optional[QPixmap] = None
        self.addWidget(self._placeholder)   # 0
        self.addWidget(self._img_label)     # 1
        self.addWidget(self._text_edit)      # 2

    def _open_image_dialog(self) -> None:
        """点击图片 → 仅在预览视图上盖遮罩大图（滚轮缩放/拖拽平移/双击关闭）。

        parent 传 ``self``（预览面板）而非 ``self.window()``，遮罩只盖视图、不盖全窗口。
        """
        if self._raw_pixmap is None or self._raw_pixmap.isNull():
            return
        ImageOverlay(self._raw_pixmap, self).show_overlay()

    def show_placeholder(self, text: str) -> None:
        self._placeholder.setText(text)
        self.setCurrentIndex(0)

    def show_image(self, pix: QPixmap) -> None:
        self._raw_pixmap = pix
        self._rescale()
        self.setCurrentIndex(1)

    def show_text(self, text: str) -> None:
        self._raw_pixmap = None
        self._text_edit.setPlainText(text)
        self.setCurrentIndex(2)

    def _rescale(self) -> None:
        if self._raw_pixmap is None or self._raw_pixmap.isNull():
            return
        w = max(self._img_label.width() - 12, 64)
        h = max(self._img_label.height() - 12, 64)
        self._img_label.setPixmap(
            self._raw_pixmap.scaled(w, h, Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt 命名)
        super().resizeEvent(event)
        if self.currentIndex() == 1:
            self._rescale()


class ResourceTreeWidget(QTreeWidget):
    """管理 ``KscpPackage`` 的 ``assets/`` 子树的 QTreeWidget。"""

    path_selected = pyqtSignal(str)

    def __init__(self, package: KscpPackage,
                 select_mode: bool = False,
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._package = package
        self._select_mode = select_mode
        self._clipboard: Optional[Tuple[List[str], str]] = None  # (paths, "copy"|"cut")
        self._preview: Optional[_PreviewPanel] = None

        self.setHeaderHidden(True)
        self.setSelectionMode(
            QAbstractItemView.SingleSelection if select_mode
            else QAbstractItemView.ExtendedSelection)
        self.setUniformRowHeights(True)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._on_context_menu)
        self.currentItemChanged.connect(self._on_current_changed)

        if not select_mode:
            # 全局快捷键（编辑态；只读选模式禁用删除/重命名等）
            QShortcut(QKeySequence.Copy, self, self._act_copy)
            QShortcut(QKeySequence.Cut, self, self._act_cut)
            QShortcut(QKeySequence.Paste, self, self._act_paste)
            QShortcut(QKeySequence.Delete, self, self._act_delete)
            QShortcut("F2", self, self._act_rename)

        self.refresh()

    # ================================================================
    # 树构建 / 刷新
    # ================================================================
    def refresh(self, current_path: Optional[str] = None) -> None:
        """从 package 重建树，保留展开与选中状态。

        ``current_path`` 指定重建后应作为当前项的路径（如重命名后的新路径），
        使该项被选中、预览随之更新，避免预览消失。默认沿用重建前的当前路径。
        """
        expanded = set(self._expanded_paths())
        selected = set(self._selected_paths())
        cur = current_path if current_path is not None else self._current_path()
        self.blockSignals(True)
        self.clear()
        root = self.invisibleRootItem()
        if root is not None:
            self._fill(root, "assets")
        for item in self._walk_items():
            p = item.data(0, _PATH_ROLE)
            if p in expanded:
                item.setExpanded(True)
            if p in selected:
                item.setSelected(True)
        target = self._find_item(cur)
        if target is not None:
            self.setCurrentItem(target)
        self.blockSignals(False)
        self._update_preview(self._current_path())

    def _fill(self, parent_item: QTreeWidgetItem, dir_path: str) -> None:
        names = list(self._package.list_dir(dir_path))

        def child_of(n: str) -> str:
            return (dir_path + "/" + n) if dir_path else n

        # 文件夹在上、文件在下，各自按字符排序
        dirs = sorted(n for n in names if self._package.is_dir(child_of(n)))
        files = sorted(n for n in names if self._package.is_file(child_of(n)))
        for name in dirs + files:
            child = child_of(name)
            item = QTreeWidgetItem(parent_item)
            item.setText(0, name)
            item.setData(0, _PATH_ROLE, child)
            if self._package.is_file(child):
                item.setIcon(0, self.style().standardIcon(QStyle.SP_FileIcon))
            else:
                item.setIcon(0, self.style().standardIcon(QStyle.SP_DirIcon))
                self._fill(item, child)

    def _walk_items(self):
        def rec(item):
            for i in range(item.childCount()):
                ch = item.child(i)
                if ch is None:
                    continue
                yield ch
                yield from rec(ch)
        root = self.invisibleRootItem()
        if root is not None:
            yield from rec(root)

    def _find_item(self, path: Optional[str]) -> Optional[QTreeWidgetItem]:
        if not path:
            return None
        for item in self._walk_items():
            if item.data(0, _PATH_ROLE) == path:
                return item
        return None

    def _expanded_paths(self) -> List[str]:
        return [it.data(0, _PATH_ROLE) for it in self._walk_items() if it.isExpanded()]

    def _selected_paths(self) -> List[str]:
        return [it.data(0, _PATH_ROLE) for it in self.selectedItems()
                if it.data(0, _PATH_ROLE)]

    def _selected_paths_top(self) -> List[str]:
        """选中集「顶层化」：去掉被另一选中项包含的子项，避免重复删除/复制。"""
        paths = self._selected_paths()
        tops = []
        for p in paths:
            if not any(o != p and p.startswith(o + "/") for o in paths):
                tops.append(p)
        return sorted(set(tops))

    def _current_path(self) -> str:
        cur = self.currentItem()
        return cur.data(0, _PATH_ROLE) if cur is not None else ""

    # ================================================================
    # 上下文菜单
    # ================================================================
    def _context_dir(self, item: Optional[QTreeWidgetItem]) -> str:
        if item is None:
            return "assets"
        path = item.data(0, _PATH_ROLE)
        if self._package.is_file(path):
            return _parent(path) or "assets"
        return path  # 分组本身

    def _on_context_menu(self, pos) -> None:
        if self._select_mode:
            return
        item = self.itemAt(pos)
        # 右击项不在当前选中集中 → 仅选该项
        if item is not None and not item.isSelected():
            self.setCurrentItem(item)
        paths = self._selected_paths_top()
        context_dir = self._context_dir(item)

        menu = QMenu(self)
        a_copy = menu.addAction("复制\tCtrl+C")
        a_cut = menu.addAction("剪切\tCtrl+X")
        a_paste = menu.addAction("粘贴\tCtrl+V")
        menu.addSeparator()
        a_rename = menu.addAction("重命名\tF2")
        a_delete = menu.addAction("删除\tDel")
        menu.addSeparator()
        add_menu = menu.addMenu("添加")
        a_add_file = add_menu.addAction("添加文件…")
        a_add_group = add_menu.addAction("添加组…")

        has_sel = bool(paths)
        a_copy.setEnabled(has_sel)
        a_cut.setEnabled(has_sel)
        a_rename.setEnabled(len(paths) == 1)
        a_delete.setEnabled(has_sel)
        a_paste.setEnabled(self._clipboard is not None)

        action = menu.exec_(self.viewport().mapToGlobal(pos))
        if action is a_copy:
            self._act_copy()
        elif action is a_cut:
            self._act_cut()
        elif action is a_paste:
            self._act_paste(context_dir)
        elif action is a_rename:
            self._act_rename()
        elif action is a_delete:
            self._act_delete()
        elif action is a_add_file:
            self._act_add_file(context_dir)
        elif action is a_add_group:
            self._act_add_group(context_dir)

    # ================================================================
    # 操作
    # ================================================================
    def _act_copy(self) -> None:
        paths = self._selected_paths_top()
        if paths:
            self._clipboard = (paths, "copy")

    def _act_cut(self) -> None:
        paths = self._selected_paths_top()
        if paths:
            self._clipboard = (paths, "cut")

    def _act_paste(self, context_dir: Optional[str] = None) -> None:
        if self._clipboard is None:
            return
        if context_dir is None:
            context_dir = self._context_dir(self.currentItem())
        paths, mode = self._clipboard
        for src in paths:
            name = self._dedup_name(context_dir, _basename(src))
            dst = context_dir + "/" + name
            if mode == "copy":
                self._copy_resource(src, dst)
            else:  # cut
                self._package.move(src, dst)
        if mode == "cut":
            self._clipboard = None
        self.refresh()

    def _act_rename(self) -> None:
        paths = self._selected_paths_top()
        if len(paths) != 1:
            return
        old = paths[0]
        parent, name = _parent(old), _basename(old)
        new_name, ok = QInputDialog.getText(self, "重命名", "新名称：", text=name)
        if not ok:
            return
        new_name = new_name.strip()
        if not new_name or "/" in new_name or new_name in (".", ".."):
            QMessageBox.warning(self, "重命名", "名称非法")
            return
        new_path = (parent + "/" + new_name) if parent else new_name
        if new_path == old:
            return
        if self._package.exists(new_path):
            QMessageBox.warning(self, "重命名", "名称已存在：%s" % new_name)
            return
        self._package.move(old, new_path)
        self.refresh(new_path)   # 选中重命名后的资源，预览随之更新不消失

    def _act_delete(self) -> None:
        paths = self._selected_paths_top()
        if not paths:
            return
        if QMessageBox.question(
                self, "删除", "确定删除 %d 项？" % len(paths),
                QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes) != QMessageBox.Yes:
            return
        for p in paths:
            self._package.remove(p)
        self.refresh()

    def _act_add_file(self, context_dir: str) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, "添加文件", "", "所有文件 (*)")
        for lp in paths:
            name = self._dedup_name(context_dir, os.path.basename(lp))
            self._package.add_file_from_local(context_dir + "/" + name, lp)
        self.refresh()

    def _act_add_group(self, context_dir: str) -> None:
        name, ok = QInputDialog.getText(self, "添加组", "组名：")
        if not ok:
            return
        name = name.strip()
        if not name or "/" in name or name in (".", ".."):
            QMessageBox.warning(self, "添加组", "名称非法")
            return
        name = self._dedup_name(context_dir, name)
        self._package.make_dir(context_dir + "/" + name)
        self.refresh()

    # ---- 复制 / 去重 ----
    def _dedup_name(self, context_dir: str, name: str) -> str:
        """若 ``context_dir/name`` 已存在，追加 ``(k)`` 直到不重名。"""
        if not self._package.exists(context_dir + "/" + name):
            return name
        base, ext = os.path.splitext(name)
        k = 1
        while True:
            cand = "%s(%d)%s" % (base, k, ext)
            if not self._package.exists(context_dir + "/" + cand):
                return cand
            k += 1

    def _copy_resource(self, src: str, dst: str) -> None:
        """复制文件或整棵组（含空子目录）到 ``dst``。"""
        if self._package.is_file(src):
            self._package.add_file(dst, self._package.read_file(src))
        elif self._package.is_dir(src):
            self._package.make_dir(dst)
            for name in self._package.list_dir(src):
                self._copy_resource(src + "/" + name, dst + "/" + name)

    # ================================================================
    # 预览
    # ================================================================
    @staticmethod
    def pick_resource(package: KscpPackage, suffixes: tuple = (),
                      parent: Optional[QWidget] = None) -> Optional[str]:
        """弹对话框嵌入只读 ResourceTreeWidget，按后缀过滤；选中确认返回文件路径。

        不匹配后缀的文件、以及子树中无匹配文件的空目录均隐藏。双击文件项 = 确认返回。
        取消/无有效选中返回 ``None``。
        """
        dlg = QDialog(parent)
        dlg.setWindowTitle("选择资源")
        dlg.resize(600, 500)
        tree = ResourceTreeWidget(package, select_mode=True, parent=dlg)
        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(4)
        lay.addWidget(tree)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.button(QDialogButtonBox.Ok).setText("确认")
        btns.button(QDialogButtonBox.Cancel).setText("取消")
        lay.addWidget(btns)

        suffixes_l = tuple(s.lower() for s in suffixes)

        def _selected_file() -> Optional[str]:
            it = tree.currentItem()
            if it is None:
                return None
            p = it.data(0, _PATH_ROLE)
            if not p or not package.is_file(p):
                return None
            if suffixes_l and not p.lower().endswith(suffixes_l):
                return None
            return p

        tree.apply_suffix_filter(suffixes_l)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        tree.itemDoubleClicked.connect(
            lambda *_: dlg.accept() if _selected_file() is not None else None)

        if dlg.exec_() != QDialog.Accepted:
            return None
        return _selected_file()

    def preview_widget(self) -> _PreviewPanel:
        """返回预览面板（缓存）；选中项变化时自动更新。"""
        if self._preview is None:
            self._preview = _PreviewPanel()
            self._update_preview(self._current_path())
        return self._preview

    def _on_current_changed(self, cur, prev) -> None:
        path = cur.data(0, _PATH_ROLE) if cur is not None else ""
        self._update_preview(path)
        if path:
            self.path_selected.emit(path)

    def _update_preview(self, path: str) -> None:
        if self._preview is None:
            return
        if not path:
            self._preview.show_placeholder("（无预览）")
            return
        if self._package.is_dir(path):
            self._preview.show_placeholder("（目录）")
            return
        data = self._package.read_file(path)
        ext = os.path.splitext(path)[1].lower()
        if ext in _IMAGE_EXTS:
            pix = QPixmap()
            if pix.loadFromData(data):
                self._preview.show_image(pix)
                return
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            self._preview.show_placeholder("（二进制，无法预览）\n大小：%d 字节" % len(data))
            return
        self._preview.show_text(text)

    # ================================================================
    # 后缀过滤（选择资源对话框用）
    # ================================================================
    def apply_suffix_filter(self, suffixes: tuple = ()) -> None:
        """按后缀过滤：隐藏不匹配的文件，以及子树中无匹配文件的空目录。

        选择资源对话框用此过滤；普通树也可调用。空 ``suffixes`` 表示不限后缀
        （但仍隐藏子树中无任何文件的纯空目录）。
        """
        sl = tuple(s.lower() for s in suffixes)

        def _has_match(dir_path: str) -> bool:
            """该目录子树（含自身）内是否存在匹配后缀的文件。"""
            for nm in self._package.list_dir(dir_path):
                child = (dir_path + "/" + nm) if dir_path else nm
                if self._package.is_file(child):
                    if not sl or child.lower().endswith(sl):
                        return True
                elif self._package.is_dir(child) and _has_match(child):
                    return True
            return False

        for it in self._walk_items():
            p = it.data(0, _PATH_ROLE)
            if not p:
                continue
            if self._package.is_file(p):
                if sl and not p.lower().endswith(sl):
                    it.setHidden(True)
            elif self._package.is_dir(p) and not _has_match(p):
                it.setHidden(True)


# ================================================================
# 冒烟演示：直接 ``python -m widgets.resource_tree_widget`` 运行
# ================================================================
if __name__ == "__main__":
    import sys

    from PyQt5.QtWidgets import QApplication
    from PyQt5.QtGui import QColor, QImage
    from PyQt5.QtCore import QBuffer

    app = QApplication.instance() or QApplication(sys.argv)

    def _make_png(color):
        img = QImage(48, 32, QImage.Format_RGB32)
        img.fill(QColor(color))
        buf = QBuffer(); buf.open(QBuffer.ReadWrite)
        img.save(buf, "PNG")
        return bytes(buf.data())

    pkg = KscpPackage.create_empty()
    pkg.write_file("assets/1.png", b"\x89PNG-demo")           # 非法 PNG 占位
    pkg.write_file("assets/real.png", _make_png("#3a7bd5"))   # 合法 PNG
    pkg.write_file("assets/1.txt", "文本 A".encode("utf-8"))
    pkg.write_file("assets/data.bin", bytes(range(256)))
    pkg.make_dir("assets/音乐")
    pkg.write_file("assets/音乐/2.txt", "音乐文本".encode("utf-8"))
    pkg.make_dir("assets/音乐/子")

    tree = ResourceTreeWidget(pkg)
    # 顶层：文件夹在上、文件在下，各自按字符排序
    assert [it.text(0) for it in (tree.topLevelItem(i) for i in range(tree.topLevelItemCount()))] == \
           ["音乐", "1.png", "1.txt", "data.bin", "real.png"]
    assert tree._find_item("assets/音乐/2.txt") is not None
    assert tree._find_item("assets/音乐/子") is not None
    # 子级同样：目录在上、文件在下
    music = tree._find_item("assets/音乐")
    assert music is not None
    assert [music.child(i).text(0) for i in range(music.childCount())] == ["子", "2.txt"]

    # 选中 assets/1.txt，复制，粘入 assets 三次 → 1(1..3).txt
    tree._find_item("assets/1.txt").setSelected(True)
    tree.setCurrentItem(tree._find_item("assets/1.txt"))
    tree._act_copy()
    assert tree._clipboard == (["assets/1.txt"], "copy")
    for _ in range(3):
        tree._act_paste("assets")
    assert pkg.is_file("assets/1(1).txt")
    assert pkg.is_file("assets/1(2).txt")
    assert pkg.is_file("assets/1(3).txt")
    assert pkg.is_file("assets/1.txt")  # 原文件不动
    assert tree._clipboard == (["assets/1.txt"], "copy")  # 复制后保留

    # 剪切 1.txt 粘入 assets/音乐 → 移动且 clipboard 清除
    tree._act_cut()
    assert tree._clipboard == (["assets/1.txt"], "cut")
    tree._act_paste("assets/音乐")
    assert pkg.is_file("assets/音乐/1.txt")
    assert not pkg.is_file("assets/1.txt")
    assert tree._clipboard is None  # 剪切粘贴后清除

    # 复制组（含空子目录）
    tree.clearSelection()
    tree._copy_resource("assets/音乐", "assets/音乐副本")
    assert pkg.is_dir("assets/音乐副本")
    assert pkg.is_file("assets/音乐副本/1.txt")
    assert pkg.is_dir("assets/音乐副本/子")  # 空子目录也被复制

    # 重命名
    tree.setCurrentItem(tree._find_item("assets/data.bin"))
    # 直接调 package.move 模拟重命名结果（GUI 输入框不便于冒烟）
    pkg.move("assets/data.bin", "assets/data2.bin")
    tree.refresh()
    assert tree._find_item("assets/data2.bin") is not None
    assert tree._find_item("assets/data.bin") is None

    # 添加组（去重）
    pkg.make_dir("assets/新组")
    tree.refresh()
    assert pkg.is_dir("assets/新组")

    # 预览各态
    pv = tree.preview_widget()
    tree.setCurrentItem(tree._find_item("assets/real.png"))   # 合法图片
    assert pv.currentIndex() == 1 and not pv._raw_pixmap.isNull()
    ov = ImageOverlay(pv._raw_pixmap)                          # 构造遮罩预览（不 show_overlay）
    assert ov._item in ov._scene.items()
    assert not ov._item.pixmap().isNull()
    tree.setCurrentItem(tree._find_item("assets/1(1).txt"))  # 文本（1.txt 已移走，用副本）
    assert pv.currentIndex() == 2
    tree.setCurrentItem(tree._find_item("assets/data2.bin"))  # 二进制
    assert pv.currentIndex() == 0 and "二进制" in pv._placeholder.text()
    tree.setCurrentItem(tree._find_item("assets/音乐副本"))  # 目录
    assert pv.currentIndex() == 0 and "目录" in pv._placeholder.text()

    # 多选顶层化：选中组与其子项，操作集只保留组
    tree.clearSelection()
    tree._find_item("assets/音乐副本").setSelected(True)
    tree._find_item("assets/音乐副本/1.txt").setSelected(True)
    assert tree._selected_paths_top() == ["assets/音乐副本"]

    # 重命名后选中新路径、预览不消失
    tree.setCurrentItem(tree._find_item("assets/real.png"))   # 当前是合法图片
    assert pv.currentIndex() == 1
    pkg.move("assets/real.png", "assets/real2.png")
    tree.refresh("assets/real2.png")                          # 模拟重命名后的刷新
    assert tree._current_path() == "assets/real2.png"
    assert tree._find_item("assets/real2.png") is not None
    assert tree._find_item("assets/real.png") is None
    assert pv.currentIndex() == 1 and not pv._raw_pixmap.isNull()   # 预览仍在

    # 后缀过滤：隐藏不匹配文件 + 子树中无匹配文件的空目录
    ft = ResourceTreeWidget(pkg, select_mode=True)
    ft.apply_suffix_filter((".png",))

    def _hidden(path: str) -> Optional[bool]:
        it = ft._find_item(path)
        return None if it is None else it.isHidden()

    assert _hidden("assets/real2.png") is False      # png → 可见
    assert _hidden("assets/1.png") is False          # png（内容虽非法）→ 可见
    assert _hidden("assets/1(1).txt") is True        # txt → 隐藏
    assert _hidden("assets/data2.bin") is True       # bin → 隐藏
    assert _hidden("assets/音乐") is True            # 目录无 png → 隐藏
    assert _hidden("assets/音乐副本") is True         # 目录无 png → 隐藏
    assert _hidden("assets/新组") is True             # 空目录 → 隐藏
    assert _hidden("assets/音乐/子") is True          # 空子目录 → 隐藏

    print("ResourceTreeWidget smoke OK")
