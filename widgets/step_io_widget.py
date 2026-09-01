# -*- coding: utf-8 -*-
"""
兼容垫片：步骤输入/输出设置已迁至 :mod:`model.步骤.step_io`
======================================================

:class:`StepIOWidget` 是轻量数据对象（不继承 QWidget），正式位置已迁移到
``model/步骤.step_io.py``（model 层顶层不导入 PyQt5）。本模块仅 re-export，
保证旧引用路径不破坏。

新代码请直接从 ``model.步骤.step_io`` 导入。
"""
from model.步骤.step_io import StepIOWidget

__all__ = ["StepIOWidget"]
