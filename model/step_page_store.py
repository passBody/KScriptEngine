# -*- coding: utf-8 -*-
"""
兼容垫片：模块已移至 :mod:`model.步骤.step_page_store`（重构 2026-09-02）
========================================================

旧 ``.kscp`` 工程包内的步骤模板与旧脚本仍从本路径导入，本模块仅
re-export 保持兼容。新代码请从 ``model.步骤.step_page_store`` 导入。
"""
from model.步骤.step_page_store import *  # noqa: F401,F403
from model.步骤.step_page_store import __all__
