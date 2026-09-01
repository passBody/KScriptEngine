"""游戏自动化脚本：OCR 文字识别函数。

用本地 RapidOCR 引擎识别图片中的文字，支持中英混合。
给定图片文件路径或 PIL Image 对象，返回识别出的文字字符串。

用法示例：
    from vision.ocr import read_text

    text = read_text("crop.png")                 # 文件路径
    text = read_text(screenshot.crop(region))    # PIL Image
"""

import os
import threading

import numpy as np
from PIL import Image
from rapidocr_onnxruntime import RapidOCR

# 懒加载单例：首次调用时初始化引擎（约 0.2~1s），之后复用
_engine = None
_engine_lock = threading.Lock()


def read_text(image):
    """识别图片中的文字。

    Args:
        image: 图片文件路径（str/os.PathLike）或 PIL Image 对象。

    Returns:
        识别出的文字，多块按识别顺序用换行拼接；
        图中没有文字时返回空字符串 ""。

    Raises:
        FileNotFoundError: 图片文件不存在或无法解析。
    """
    try:
        img = _open_image(image)
        bgr = _to_bgr(img)
    except FileNotFoundError:
        raise
    except OSError:
        # 损坏/无法解析的文件转为 FileNotFoundError：不静默返回空串，
        # 避免调用方把"文件有问题"误判成"图里没字"
        raise FileNotFoundError("图片文件无法打开或解析: {}".format(image))

    result, _ = _get_engine()(bgr)
    if not result:
        return ""
    return "\n".join(item[1] for item in result)


def _open_image(image):
    """str/os.PathLike 打开为 PIL Image；PIL Image 原样返回。"""
    if isinstance(image, (str, os.PathLike)):
        return Image.open(image)
    return image


def _to_bgr(img):
    """PIL Image -> 连续 BGR numpy 数组（uint8, HxWx3）。

    RapidOCR 的 numpy 输入约定为 BGR（OpenCV 惯例）；
    转连续数组避免负步长视图导致引擎内部出错。
    """
    rgb = np.asarray(img.convert("RGB"), dtype=np.uint8)
    return np.ascontiguousarray(rgb[:, :, ::-1])


def _get_engine():
    """返回引擎单例，首次调用时初始化（加锁避免并发重复初始化）。"""
    global _engine
    if _engine is None:
        with _engine_lock:
            if _engine is None:
                _engine = RapidOCR()
    return _engine
