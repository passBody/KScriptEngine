# -*- coding: utf-8 -*-
"""内嵌游戏自动化视觉工具包：图像比对判断与 OCR 文字识别。

两个子模块**互不依赖**，所以这里只做惰性导出（PEP 562）：取用哪个才导入哪个。

**别改回 ``from .ocr import read_text`` 这种包级急切导入**。那样写的话，
``import libs.vision.image_match`` 会先跑完本文件、把 ``ocr`` 一并拉起来，
于是只用到 cv2/numpy 的图像匹配被邻居连累，连带拖进
``rapidocr`` → ``onnxruntime``。代价不只是慢：
onnxruntime 与 PyQt5 在 MSVC 运行时上有冲突（根因见 :mod:`libs.win_dll`），
GUI 进程里被拖进来就是 ``DLL load failed ... 初始化例程失败``，
而报错话术是「图像匹配引擎未安装」——引擎其实压根没被用到，
照着这句话去查会一路查错方向。

回归用例：``python -m libs.vision``。
"""
__all__ = ["read_text", "find_template"]

# 名字 -> 它所在的子模块（相对本包）。__getattr__ 按需导入。
_LAZY = {
    "read_text": ".ocr",
    "find_template": ".image_match",
}


def __getattr__(name):
    """PEP 562 惰性导出：``libs.vision.read_text`` 首次取用时才导入子模块。

    导入后写回 ``globals()``，后续取用不再走这里（也让 ``dir()`` 自然可见）。
    """
    submodule = _LAZY.get(name)
    if submodule is None:
        raise AttributeError("module %r has no attribute %r" % (__name__, name))
    import importlib

    value = getattr(importlib.import_module(submodule, __name__), name)
    globals()[name] = value
    return value


def __dir__():
    return sorted(set(globals()) | set(__all__))
