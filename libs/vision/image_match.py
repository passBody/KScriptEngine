"""游戏自动化脚本：图像比对判断函数。

通过模板匹配判断目标元素在游戏画面中是否出现/消失，
找到时返回模板中心的屏幕绝对坐标，可直接传给鼠标点击函数。

用法示例：
    from vision import image_match

    image_match.set_default_screenshot_fn(capture_full_screen)  # 接入已有截图函数

    found, xy = image_match.find_template("button.png")
    if found:
        click(xy)  # 已有的鼠标点击函数
"""

import cv2
import numpy as np
from PIL import Image, ImageGrab

# 模板灰度图缓存：路径 -> numpy 数组（HxW, uint8）
_template_cache: dict = {}

# 默认截图函数（全屏）。用 set_default_screenshot_fn 接入已有截图实现。
_default_screenshot_fn = ImageGrab.grab


def set_default_screenshot_fn(fn):
    """替换默认截图函数（用于接入脚本中已有的全屏截图实现）。"""
    global _default_screenshot_fn
    _default_screenshot_fn = fn


def find_template(template_path, screenshot=None, threshold=0.8):
    """判断模板图是否出现在游戏画面中。

    Args:
        template_path: 预保存的元素图片路径（png/jpg 均可）。
        screenshot: 已截好的画面（PIL Image）；传 None 时调用默认截图函数。
        threshold: 相似度阈值（0~1），默认 0.8。

    Returns:
        (True, (x, y)): 找到元素，(x, y) 为模板中心的屏幕绝对坐标。
        (False, None): 未找到元素。

    Raises:
        ValueError: 模板尺寸大于截图尺寸。
        FileNotFoundError: 模板文件不存在或无法解析。
    """
    if screenshot is None:
        screenshot = _default_screenshot_fn()

    screen_gray = _to_gray(screenshot)
    template_gray = _load_template(template_path)

    if (template_gray.shape[0] > screen_gray.shape[0]
            or template_gray.shape[1] > screen_gray.shape[1]):
        raise ValueError(
            "模板尺寸 {}x{} 大于截图尺寸 {}x{}".format(
                template_gray.shape[1], template_gray.shape[0],
                screen_gray.shape[1], screen_gray.shape[0],
            )
        )

    result = cv2.matchTemplate(screen_gray, template_gray, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(result)

    # 纯色模板方差为 0，matchTemplate 结果无意义（旧版 OpenCV 为 NaN、5.x 为全 1.0），视为未找到
    if float(template_gray.std()) == 0 or not np.isfinite(max_val) or max_val < threshold:
        return False, None

    h, w = template_gray.shape
    center = (int(max_loc[0]) + w // 2, int(max_loc[1]) + h // 2)
    return True, center


def _to_gray(img):
    """PIL Image -> 灰度 numpy 数组（uint8, HxW）。"""
    return np.asarray(img.convert("L"), dtype=np.uint8)


def _load_template(template_path):
    """读取模板文件并转灰度，结果按路径缓存。

    文件不存在或无法解析时抛 FileNotFoundError（不静默返回，
    避免调用方把"文件有问题"误判为"元素没出现"）。
    """
    if template_path not in _template_cache:
        try:
            with Image.open(template_path) as img:
                _template_cache[template_path] = _to_gray(img)
        except FileNotFoundError:
            raise
        except OSError:
            raise FileNotFoundError("模板文件无法打开: {}".format(template_path))
    return _template_cache[template_path]
