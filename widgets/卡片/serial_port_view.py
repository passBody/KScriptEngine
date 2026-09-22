# -*- coding: utf-8 -*-
"""
串口选择视图（可复用控件）
==============================

供 ``actions/输入/串口鼠标/`` 下各步骤的自定义卡片视图复用：提示标签 +
**可编辑下拉框**（列出当前可用串口）+「刷新」按钮。

槽位约定
--------
串口名固定填在各步骤输入类的**第 0 个字段**（:data:`PORT_SLOT`）。下拉框
选中/手输即经 ``io.change_value`` 写回该槽；反向地，槽值变化（含在卡片下方
标准输入 GUI 里手改）经**弱引用监听**同步回下拉框文本。

USB 转串口无需配置波特率，故本视图只有端口一项。

基本用法
--------
::

    view = SerialPortView(step, parent)   # step 输入类第 0 个字段恒为「串口」

端口列表在构造时枚举一次；插拔设备后点「刷新」重取。
"""
from typing import List, Optional

from PyQt5.QtWidgets import (
    QComboBox, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)

from tools.serial_controller import list_serial_ports

__all__ = ["PORT_SLOT", "SerialPortView"]

PORT_SLOT = 0    # 「串口」输入槽下标（各串口步骤输入类第 0 个字段）


class SerialPortView(QWidget):
    """串口步骤的自定义卡片视图：下拉框选串口 + 刷新重枚举。"""

    def __init__(self, step, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._step = step
        # 回写循环阻塞标志：必须在 change_value **之前**置位——change_value 同步
        # 通知监听器，监听器再回写下拉框会把光标弹到末尾、打断正在输入的用户。
        self._syncing = False
        self._weak_cb = None

        self._hint = QLabel()
        self._hint.setStyleSheet("color:#888;")
        self._hint.setWordWrap(True)

        self._combo = QComboBox()
        self._combo.setEditable(True)          # 允许手输未枚举到的端口名
        self._combo.setToolTip("选择串口鼠标所在端口，或直接输入端口名（如 COM3）")
        self._combo.currentTextChanged.connect(self._on_changed)

        self._btn_refresh = QPushButton("刷新")
        self._btn_refresh.setToolTip("重新枚举当前可用串口（插拔设备后用）")
        self._btn_refresh.clicked.connect(self._reload_ports)

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        row.addWidget(self._combo, 1)
        row.addWidget(self._btn_refresh)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        lay.addWidget(self._hint)
        lay.addLayout(row)

        self._reload_ports()
        self._attach_listener()

    # ==================== 数据 ====================
    def _value(self) -> str:
        """输入槽原文（常量或 ``{{变量}}`` 引用）；无该槽 → 空串。"""
        try:
            return self._step.io.input_value(PORT_SLOT) or ""
        except IndexError:
            return ""

    # ==================== 视图 ↔ 槽 ====================
    def _reload_ports(self) -> None:
        """重取可用端口并重建下拉项；文本始终回填当前槽值。"""
        ports: List[str] = []
        try:
            ports = list_serial_ports()
        except Exception:
            pass              # 枚举失败（驱动异常）→ 退化为纯手输，不拦用户
        self._syncing = True
        try:
            self._combo.blockSignals(True)
            self._combo.clear()
            self._combo.addItems(ports)
            self._combo.setEditText(self._value())
        finally:
            self._combo.blockSignals(False)
            self._syncing = False
        self._hint.setText(
            "已检测到 %d 个串口；选择后填入「串口」输入槽（USB 串口无需波特率）"
            % len(ports))

    def _sync_text(self) -> None:
        """槽值 → 下拉框文本（io 监听回调）。

        只改文本、**不重建下拉项**：重建会打断用户正在下拉框里敲字。
        """
        if self._syncing:
            return
        self._syncing = True
        try:
            self._combo.setEditText(self._value())
        finally:
            self._syncing = False

    def _on_changed(self, text: str) -> None:
        """下拉框文本 → 串口输入槽。"""
        if self._syncing:
            return
        self._syncing = True
        try:
            self._step.io.change_value("input", PORT_SLOT, text)
        finally:
            self._syncing = False

    def _attach_listener(self) -> None:
        """槽值变化 → 同步下拉框（弱引用：监听器不持视图强引用，防泄漏）。"""
        import weakref
        self_ref = weakref.ref(self)

        def cb():
            view = self_ref()
            if view is not None:
                view._sync_text()

        self._weak_cb = cb
        self._step.io.add_listener(cb)


# ================================================================
# 冒烟演示：直接 ``python -m widgets.卡片.serial_port_view`` 运行
# ================================================================
if __name__ == "__main__":
    import gc
    import sys
    import weakref

    from PyQt5.QtWidgets import QApplication

    from model.工程.kscp_package import KscpPackage
    from model.变量.variable_tree import VariableTree

    _mod = sys.modules[__name__]      # runpy 命名空间陷阱：桩挂当前命名空间

    app = QApplication.instance() or QApplication(sys.argv)

    # 桩替换端口枚举（冒烟不依赖本机真挂了什么设备）
    _fake = {"ports": ["COM3", "COM10"]}
    _orig_list = _mod.list_serial_ports
    _mod.list_serial_ports = lambda: list(_fake["ports"])

    pkg = KscpPackage.create_empty()
    tree = VariableTree.create_empty()

    from actions.输入.串口鼠标.基础操作.复位 import SerialReset
    step = SerialReset.create_default(tree, pkg)
    view = SerialPortView(step)

    # 下拉项 = 枚举结果，且为自然序（COM10 在 COM3 之后）
    assert [view._combo.itemText(i) for i in range(view._combo.count())] == \
        ["COM3", "COM10"], view._combo.count()
    assert view._combo.isEditable()
    assert "2 个串口" in view._hint.text(), view._hint.text()

    # 选下拉项 → 写回槽 0
    view._combo.setCurrentIndex(1)
    assert step.io.input_value(0) == "COM10", step.io.input_value(0)

    # 手输端口名 → 写回槽 0
    view._combo.setEditText("COM7")
    assert step.io.input_value(0) == "COM7", step.io.input_value(0)

    # 槽值外部变化（下方标准输入 GUI / 变量解析）→ 回填下拉框文本
    step.io.change_value("input", 0, "COM4")
    assert view._combo.currentText() == "COM4", view._combo.currentText()

    # 刷新：重枚举下拉项，且保留当前槽值不被清掉
    _fake["ports"] = ["COM1", "COM2", "COM3"]
    view._btn_refresh.click()
    assert [view._combo.itemText(i) for i in range(view._combo.count())] == \
        ["COM1", "COM2", "COM3"]
    assert view._combo.currentText() == "COM4", view._combo.currentText()
    assert step.io.input_value(0) == "COM4", step.io.input_value(0)
    assert "3 个串口" in view._hint.text(), view._hint.text()

    # 枚举抛异常 → 退化为纯手输，不崩、不丢槽值
    def _boom():
        raise OSError("桩：驱动异常")
    _mod.list_serial_ports = _boom
    view._btn_refresh.click()
    assert view._combo.count() == 0
    assert view._combo.currentText() == "COM4", view._combo.currentText()

    # 弱引用监听：视图销毁后可被 GC 回收，死回调路径不崩
    _mod.list_serial_ports = _orig_list
    vref = weakref.ref(view)
    del view
    gc.collect()
    assert vref() is None, "监听器须为弱引用：视图销毁后应可被 GC 回收"
    step.io.change_value("input", 0, "COM9")      # 触发死回调 → no-op

    print("SerialPortView smoke OK")
