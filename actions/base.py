# -*- coding: utf-8 -*-
"""
兼容垫片：步骤基类已迁至 :mod:`model.step`
==========================================

:class:`Step` / :class:`StepStatus` 的正式位置已迁移到 ``model/step.py``
（model 层不再经此依赖 GUI）。本模块仅 re-export，保证两个兼容路径可用：

* 已打包进旧 ``.kscp`` 工程包的步骤模板（``from actions.base import Step``
  随包分发）仍可正常动态导入；
* 旧代码引用路径不破坏。

新代码请直接从 ``model.step`` 导入。
"""
from model.step import Step, StepStatus

__all__ = ["Step", "StepStatus"]
