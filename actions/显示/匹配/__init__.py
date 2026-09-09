# -*- coding: utf-8 -*-
"""匹配类别（显示/匹配）：在截图中定位模板图片的中心坐标。

当前类别下步骤：
* :class:`FullScreenMatch` — 全屏匹配图片，返回模板在屏幕上的中心坐标。
* :class:`ImageMatch` — 给定图片内匹配模板，返回模板在该图内的中心坐标。
"""
from .全屏匹配 import FullScreenMatch
from .图片匹配 import ImageMatch

__all__ = ["FullScreenMatch", "ImageMatch"]
