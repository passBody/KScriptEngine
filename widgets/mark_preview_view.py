# -*- coding: utf-8 -*-
"""
兼容垫片：素材标注预览视图已移至 :mod:`widgets.卡片.mark_preview_view`
======================================================================

旧 ``.kscp`` 工程包内的「鼠标点击」模板（``from widgets.mark_preview_view
import MarkPreviewView``）仍从本路径导入，本模块仅 re-export 保持兼容。
新代码请从 ``widgets.卡片.mark_preview_view`` 导入。
"""
from widgets.卡片.mark_preview_view import *  # noqa: F401,F403
from widgets.卡片.mark_preview_view import __all__
