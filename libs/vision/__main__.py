# -*- coding: utf-8 -*-
"""``python -m libs.vision`` 冒烟。

盯的是两个**跨模块**的失败模式——都不是「函数算错了」，而是
「谁被顺带导入了」「谁先谁后」，所以只能在这里测：

1. **图像匹配不许被 OCR 连累**（本次 bug）：``__init__.py`` 若改回急切导入
   ``from .ocr import read_text``，导入 ``image_match`` 就会拖进
   rapidocr → onnxruntime。
2. **OCR 与 PyQt5 共存**：依赖 ``libs.win_dll.preload_msvc_runtime`` 在 PyQt5
   之前跑过（``main.py`` 里就是这么调的），否则 onnxruntime 加载失败。
"""

import os
import subprocess
import sys

# 与 main.py 一致的顺序：预载必须在导入 PyQt5 之前。
# 详见 libs/win_dll.py——晚了就没用了。
from libs.win_dll import preload_msvc_runtime

_preloaded = preload_msvc_runtime()

# 模拟 GUI：PyQt5 一进来，Qt5/bin 就被加进 DLL 搜索目录。
import PyQt5  # noqa: F401,E402

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 只该由「用 OCR」带进来的名字。图像匹配碰它们任何一个都算被连累。
_OCR_ONLY = ("onnxruntime", "rapidocr_onnxruntime", "libs.vision.ocr")


def _check_image_match_not_dragged_in():
    """图像匹配能导入，且没把 OCR 那条链子拖进来。

    **必须在干净子进程里做**。本进程是 ``python -m libs.vision`` 起来的，
    runpy 会**先**导入 ``libs.vision`` 包再执行 ``__main__``：等跑到这里，
    包级急切导入早就发生过了，再快照 ``sys.modules`` 只会看到「已经是脏的」，
    判断恒为「没拖进来」——测试看着是绿的，其实什么都没验。这正是本 bug
    当初能潜伏下去的那类假绿。
    """
    code = (
        "import sys\n"
        "from libs.win_dll import preload_msvc_runtime\n"
        "preload_msvc_runtime()\n"
        "import PyQt5\n"
        "assert 'onnxruntime' not in sys.modules, '基线就不干净'\n"
        "from libs.vision.image_match import find_template\n"
        "bad = [n for n in %r if n in sys.modules]\n"
        # 管道上只走 ASCII：子进程按 UTF-8 写，父进程按本机 GBK 读，
        # 中文会在解码时炸掉（而不是报错内容本身）。模块名恰好是 ASCII，
        # 于是这个坑只在「无事发生」那一支才暴露——最难查的那种。
        "print('DRAGGED=' + ','.join(bad))\n" % (_OCR_ONLY,)
    )
    env = dict(os.environ, PYTHONPATH=_ROOT, PYTHONUTF8="1")
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True,
                          text=True, encoding="utf-8", errors="replace",
                          cwd=_ROOT, env=env, timeout=300)
    if proc.returncode != 0:
        sys.stderr.write(proc.stderr)
        raise AssertionError("干净进程里导入 image_match 失败（用户报的就是这个）")
    assert proc.stdout.strip() == "DRAGGED=", (
        "导入 libs.vision.image_match 顺带拖进了 OCR 依赖（%s）——"
        "libs/vision/__init__.py 的惰性导出（PEP 562）被改回急切导入了？"
        % proc.stdout.strip()
    )


def _check_lazy_exports():
    """包级惰性导出：取哪个导入哪个，取不到的报 AttributeError。"""
    import libs.vision as vision

    # 顺序要紧：取用本身就会触发导入，所以「还没导入」必须先断言，
    # 不能先取完再回头查——那等于用被自己破坏掉的前置条件做验证。
    assert "libs.vision.ocr" not in sys.modules, (
        "还没取用 read_text，ocr 就先被导入了——包级急切导入又回来了？"
    )

    assert callable(vision.find_template), "包级 find_template 应可取用"
    assert "libs.vision.ocr" not in sys.modules, (
        "取 find_template 不该顺带导入 ocr"
    )

    assert callable(vision.read_text), "包级 read_text 应可取用"
    assert "libs.vision.ocr" in sys.modules, "取过 read_text 后 ocr 应在 sys.modules"
    # 惰性导出会写回 globals()，所以取过之后 dir() 里就该有
    assert "read_text" in dir(vision), "取用过的名字应出现在 dir() 里"

    try:
        vision.不存在的名字
    except AttributeError:
        pass
    else:
        raise AssertionError("未知属性应抛 AttributeError，而不是静默返回 None")


def _check_find_template_works():
    """真跑一次匹配，确认不是「导入没报错但功能废了」。"""
    import numpy as np
    from PIL import Image

    from libs.vision.image_match import find_template

    canvas = np.random.RandomState(0).randint(0, 255, (200, 300, 3), dtype=np.uint8)
    tpl = np.zeros((40, 50, 3), dtype=np.uint8)
    tpl[:, :25] = 255                       # 左白右黑，保证方差非 0
    canvas[80:120, 120:170] = tpl           # 贴到第 80~119 行、120~169 列

    found, center = find_template(Image.fromarray(tpl), Image.fromarray(canvas),
                                  threshold=0.95)
    assert found, "嵌入的模板应被找到"
    # 契约：center 是模板**中心**的 (x, y) = (列+w//2, 行+h//2)
    assert center == (145, 100), "中心坐标应为 (145, 100)，实际 %r" % (center,)

    miss, none_center = find_template(Image.fromarray(tpl[0:8, 0:8]),
                                      Image.fromarray(canvas), threshold=0.999)
    assert not miss and none_center is None, "阈值高到不匹配时应返回 (False, None)"


def _check_ocr_works_with_qt():
    """Fix B 的回归点：预载之后，PyQt5 已在进程里，OCR 仍要能跑。"""
    from PIL import Image, ImageDraw

    from libs.vision.ocr import read_text

    img = Image.new("RGB", (420, 120), (255, 255, 255))
    ImageDraw.Draw(img).text((20, 40), "HELLO KSCRIPT", fill=(0, 0, 0))
    text = read_text(img)
    assert "HELLO KSCRIPT" in text.upper(), "OCR 应识别出 HELLO KSCRIPT，实际 %r" % text


if __name__ == "__main__":
    print("MSVC 运行时预载:", _preloaded or "(无)")
    _check_image_match_not_dragged_in()
    print("图像匹配独立导入 OK（未拖入 OCR）")
    _check_lazy_exports()
    print("包级惰性导出 OK")
    _check_find_template_works()
    print("find_template 功能 OK")
    _check_ocr_works_with_qt()
    print("OCR 与 PyQt5 共存 OK")
    print("libs.vision 冒烟 OK")
