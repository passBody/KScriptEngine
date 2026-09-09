# -*- coding: utf-8 -*-
"""
全屏截图步骤（显示/截图）
========================

:class:`FullScreenShot`：截取主屏全画面，覆盖写入**输出变量所指向的图片资源**。

输入槽
------
* 无。

运行规则
--------
* 用 :meth:`QScreen.grabWindow(0)` 抓主屏全画面 → PNG 字节。
* **覆盖输出变量所在的图片**：读取输出槽绑定的 image 变量当前 ``data``
  （资源路径，如 ``assets/某图.png``），把 PNG 字节写回该路径；再把输出槽
  设为同一资源路径。这样同一变量被反复截图时会原地更新，而非新增
  ``assets/fullscreen_shot.png`` 这类固定资源。
* 输出槽未绑定 image 变量 / 变量非法 / 抓屏失败：抛 :class:`ValueError`
  （由 do() 置「执行错误」停步）。
"""
from dataclasses import dataclass
from typing import Optional

from PyQt5.QtCore import QBuffer, QIODevice

from model.log_model import LogModel
from model.步骤.step import Step, StepStatus

__all__ = ["FullScreenShot"]


@dataclass
class FullScreenShotInput:
    """无输入。"""
    pass


@dataclass
class FullScreenShotOutput:
    """输出：全屏截图（image）。"""
    全屏截图: "image" = ""  # type: ignore


class FullScreenShot(Step):
    """全屏截图步骤：截取主屏全画面，覆盖输出变量所在的图片资源。"""

    name = "全屏截图"
    description = "截取主屏全画面，覆盖写入输出变量所指向的图片"
    input_class = FullScreenShotInput
    output_class = FullScreenShotOutput

    def run(self) -> int:
        # 输出槽绑定的 image 变量 → 其当前资源路径（截图覆盖目标）
        name = self.io.output_value(0)
        if not name:
            raise ValueError("全屏截图：未指定输出变量")
        bound = self.io.tree.get(name)
        if bound.type != "image":
            raise ValueError("全屏截图：输出变量「%s」不是 image 类型" % name)
        target = bound.data
        if not (isinstance(target, str) and target.startswith("assets/")
                and any(target.lower().endswith(s) for s in bound.suffixes)):
            raise ValueError("全屏截图：输出变量「%s」的图片路径非法: %r" % (name, target))
        png = self._capture_png()
        if not png:
            raise ValueError("全屏截图：抓屏或编码失败（无屏幕环境或编码失败）")
        self.io.package.write_file(target, png)
        self.outputs.全屏截图 = target
        LogModel.instance().info("全屏截图完成 → %s" % target)
        return 1

    # ----------------------------------------------------------------
    # 抓屏 → PNG 字节
    # ----------------------------------------------------------------
    @staticmethod
    def _capture_png() -> Optional[bytes]:
        """主屏全画面 → PNG 字节；无屏幕环境 / 编码失败 → None。"""
        from PyQt5.QtWidgets import QApplication

        app = QApplication.instance()
        if app is None:
            return None
        screen = app.primaryScreen()
        if screen is None:
            return None
        pix = screen.grabWindow(0)            # 0 = 整个屏幕
        if pix.isNull():
            return None
        buf = QBuffer()
        buf.open(QIODevice.ReadWrite)
        ok = pix.toImage().save(buf, "PNG")
        return bytes(buf.data()) if ok else None


# ================================================================
# 冒烟演示：直接 ``python -m actions.显示.截图.全屏截图`` 运行
# ================================================================
if __name__ == "__main__":
    import sys

    from PyQt5.QtWidgets import QApplication

    from model.工程.kscp_package import KscpPackage
    from model.变量.project_variable import ProjectVariable
    from model.步骤.step import StepStatus
    from model.变量.variable_tree import VariableTree

    _mod = sys.modules[__name__]

    app = QApplication.instance() or QApplication(sys.argv)

    pkg = KscpPackage.create_empty()
    tree = VariableTree.create_empty()
    # 输出变量指向一张已有图片 assets/shot.png（截图将原地覆盖它）
    pkg.write_file("assets/shot.png", b"\x89PNG\r\n\x1a\nOLD")
    tree.add("shot", ProjectVariable.create("image", "assets/shot.png", pkg))

    # create_default：无输入、一输出 image
    s = FullScreenShot.create_default(tree, pkg)
    assert s.io._input_type == []
    assert s.io._output_type == ["image"]
    assert s.name == "全屏截图"

    # 输出绑定 image 变量；run 经桩替换抓屏（冒烟不真实截屏，保证可复现）
    s.io.change_value("output", 0, "shot")

    captured = {}

    class _FakePix:
        def isNull(self):
            return False

        def toImage(self):
            from PyQt5.QtGui import QImage
            img = QImage(2, 2, QImage.Format_RGB32)
            img.fill(0)
            return img

    def _fake_capture():
        captured["yes"] = True
        buf = QBuffer()
        buf.open(QIODevice.ReadWrite)
        _FakePix().toImage().save(buf, "PNG")
        return bytes(buf.data())

    _orig = FullScreenShot._capture_png
    FullScreenShot._capture_png = staticmethod(_fake_capture)
    try:
        assert s.do() == 1
    finally:
        FullScreenShot._capture_png = _orig
    assert s.status is StepStatus.FINISHED
    assert captured.get("yes")
    # 截图覆盖了输出变量指向的同一资源路径 assets/shot.png（原地更新，非新增固定资源）
    png = pkg.read_file("assets/shot.png")
    assert png[:8] == b"\x89PNG\r\n\x1a\n", png[:16]
    assert png != b"\x89PNG\r\n\x1a\nOLD"   # 旧内容已被新截图覆盖
    assert tree.get("shot").data == "assets/shot.png"

    # 未指定输出变量 → ValueError 停步
    LogModel.instance().clear()
    s_none = FullScreenShot.create_default(tree, pkg)
    try:
        s_none.do()
        raise AssertionError("未指定输出应抛 ValueError 停步")
    except ValueError:
        pass
    assert s_none.status is StepStatus.ERROR
    assert any("未指定输出" in e.message for e in LogModel.instance().entries)

    # 输出变量非 image → ValueError 停步
    LogModel.instance().clear()
    tree.add("txt", ProjectVariable.create("string", "hi", pkg))
    s_badtype = FullScreenShot.create_default(tree, pkg)
    s_badtype.io.change_value("output", 0, "txt")
    try:
        s_badtype.do()
        raise AssertionError("非 image 输出应抛 ValueError 停步")
    except ValueError:
        pass
    assert s_badtype.status is StepStatus.ERROR
    assert any("不是 image 类型" in e.message for e in LogModel.instance().entries)

    # 抓屏失败 → ERROR + 日志，资源不被改写
    LogModel.instance().clear()
    pkg.write_file("assets/shot.png", b"\x89PNG\r\n\x1a\nOLD")   # 复位旧内容
    FullScreenShot._capture_png = staticmethod(lambda: None)
    try:
        s.do()
        raise AssertionError("抓屏失败应抛 ValueError 停步")
    except ValueError:
        pass
    finally:
        FullScreenShot._capture_png = _orig
    assert s.status is StepStatus.ERROR
    assert any("全屏截图" in e.message for e in LogModel.instance().entries)
    assert pkg.read_file("assets/shot.png") == b"\x89PNG\r\n\x1a\nOLD"  # 失败不覆盖

    # 往返
    fmt = s.to_format_string()
    assert "=" not in fmt and "+" not in fmt and "/" not in fmt
    s3 = FullScreenShot.from_format_string(fmt, tree, pkg)
    assert isinstance(s3, FullScreenShot)
    assert s3.io.to_format_string() == s.io.to_format_string()

    print("FullScreenShot smoke OK")
