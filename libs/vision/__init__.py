# -*- coding: utf-8 -*-
"""内嵌游戏自动化视觉工具包：图像比对判断与 OCR 文字识别。

**休眠模块（2026-09-02 标注）**：当前无任何主流程/步骤模板导入本包，
依赖 ``rapidocr_onnxruntime`` 亦未列入 pyproject 依赖（离线部署拉不动）。
代码与接口保留，未来接入视觉步骤时再激活（届时补依赖 + 冒烟 + 注册）。
"""
from .ocr import read_text
from .image_match import find_template

__all__ = ["read_text", "find_template"]
