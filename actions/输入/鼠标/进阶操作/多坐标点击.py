# -*- coding: utf-8 -*-
"""
多坐标点击步骤（输入模拟）
========================

:class:`MultiPosClick`：按坐标列表依次模拟鼠标指定按键点击（基于内嵌
:mod:`libs.key_control` 的 :class:`InputControl.mouse_click`）。

输入槽
------
* ``坐标x列表``（string）：鼠标点击的x列表
* ``坐标y列表``（string）：鼠标点击的y列表
* ``点击前等待时间列表``（string）：鼠标点击前等待的时间
* ``按下持续时间``（number）：鼠标每次按下的持续时间
* ``指定按键``（number，枚举）：1-LEFT 2-MIDDLE 3-RIGHT。
* ``素材图片``（image）：方便用户标注的图片

运行规则
--------
* 坐标列表为空/格式非法：状态「执行错误」+ 日志报错（抛异常）。
* 否则：逐点 ``click(x, y)``，点与点之间 sleep 间隔，返回 1。

> 模拟输入到游戏窗口需以管理员身份运行 KScript。
"""
import time
from dataclasses import dataclass
from typing import List, Optional, Tuple

from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import QVBoxLayout, QWidget

from model.执行.point_timeline import PointTimeline
from tools.mouse_controller import mouse_ctrl
from model.log_model import LogModel
from model.执行.run_interrupt import interruptible_sleep
from model.步骤.step import Step, StepStatus, optional
from widgets.卡片.mark_preview_view import MarkPreviewView


__all__ = ["MultiPosClick"]


@dataclass
class MultiPosClickInput:
    """输入：坐标列表（string）与点击间隔（number 秒）。"""
    坐标x列表: "string" = ""  # type: ignore
    坐标y列表: "string" = ""  # type: ignore
    点击前等待时间列表: "string" = ""  # type: ignore
    按下持续时间: "number" = 0.05  # type: ignore
    指定按键: "number" = 0  # type: ignore
    素材图片: "image" = optional("")  # type: ignore  # 非必须：编辑期辅助，可空


@dataclass
class MultiPosClickOutput:
    """无输出。"""
    pass


class MultiPosClick(Step):
    """多次点击步骤：按坐标列表依次指定按键点击。"""

    name = "多次点击"
    description = "按坐标列表依次模拟鼠标指定按键点击\n(数据之间使用英文`,`分割)\n(1:left,2:middle,3:right)"
    input_class = MultiPosClickInput
    output_class = MultiPosClickOutput

    def run(self) -> int:
        try:
            xs = [int(i.strip()) for i in self.inputs.坐标x列表.split(',')]
            ys = [int(i.strip()) for i in self.inputs.坐标y列表.split(',')]
            ts = [max(float(i.strip()),0.02) for i in self.inputs.点击前等待时间列表.split(',')]
        except Exception as e:
            raise ValueError("无法解析的数据：%s" % e)
        assert len(xs)==len(ys)==len(ts), 'x列表，y列表，时间列表 长度应该一致'
        down_time = max(float(self.inputs.按下持续时间), 0.02)
        mode = [None, 'left', 'middle', 'right'][int(self.inputs.指定按键)]
        for i in range(len(xs)):
            if interruptible_sleep(ts[i]): return 1
            mouse_ctrl.click(xs[i], ys[i], mode, down_time)
        return 1
    
    # 素材图片输入槽下标（自定义视图/点位标注用）
    IMAGE_SLOT = 5

    def info_widget(self, parent: Optional[QWidget] = None) -> QWidget:
        """自定义视图：提示 + 标注预览 + 设置点位按钮（见 _MouseInfoView）。"""
        return _MouseInfoView(self, parent)


class _MouseInfoView(QWidget):
    """鼠标点击步骤的自定义卡片视图（复用 :class:`MarkPreviewView`）。

    提示标签 + 缩略图（点击弹窗）+ 「设置点位」按钮均由共享控件提供，本类
    只接线：素材槽下标、dot 模式、x/y 槽的读点/回写。
    """

    def __init__(self, step: "MultiPosClick", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._step = step
        self._mark_view = MarkPreviewView(
            io=step.io, image_slot=MultiPosClick.IMAGE_SLOT, mode="dots",
            hint_text=MultiPosClick.description,
            read_points=self._read_xy,
            write_points=self._write_xyt,
            parent=self)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self._mark_view)

    def _read_xy(self) -> Optional[List[Tuple[int, int]]]:
        """从输入 GUI 的 x/y 槽读标注点；非数值 → None（预览显示原图）。"""
        try:
            x = [int(round(float(i.strip()))) for i in self._step.io.input_value(0).split(',')]
            y = [int(round(float(i.strip()))) for i in self._step.io.input_value(1).split(',')]
            if len(x) != len(y): raise ValueError("数据长度不一致")
            return list(zip(x,y))
        except (ValueError, TypeError):
            return None

    def _write_xyt(self, pos_info: Optional[PointTimeline]) -> None:
        """设置点位完成 → 坐标写回 x/y 输入槽（io 监听触发预览重合成）。"""
        pos_infos = pos_info.items()
        xs = [str(i[0][0]) for i in pos_infos]
        ys = [str(i[0][1]) for i in pos_infos]
        ts = [str(round(i[1],2)) for i in pos_infos]
        self._step.io.change_value("input", 0, ','.join(xs))
        self._step.io.change_value("input", 1, ','.join(ys))
        self._step.io.change_value("input", 2, ','.join(ts))

    def _preview_pixmap(self) -> QPixmap:
        """预览合成已由 MarkPreviewView 承担；本别名供冒烟兼容。"""
        return self._mark_view.preview_pixmap()