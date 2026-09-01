# -*- coding: utf-8 -*-
"""
兼容垫片：模块已移至 :mod:`model.变量.variable_tree`（重构 2026-09-02）
========================================================

旧 ``.kscp`` 工程包内的步骤模板与旧脚本仍从本路径导入，本模块仅
re-export 保持兼容。新代码请从 ``model.变量.variable_tree`` 导入。
"""
from model.变量.variable_tree import *  # noqa: F401,F403
from model.变量.variable_tree import __all__
