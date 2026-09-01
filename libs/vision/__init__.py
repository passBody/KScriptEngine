# -*- coding: utf-8 -*-
"""内嵌游戏自动化视觉工具包：图像比对判断与 OCR 文字识别。"""
from .ocr import read_text
from .image_match import find_template

__all__ = ["read_text", "find_template"]
