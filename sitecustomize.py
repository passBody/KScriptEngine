# -*- coding: utf-8 -*-
"""sitecustomize：进程启动阶段的 venv 环境修补（venv 部署必需）。

由 ``tools/fix_qt_plugins.py`` 复制到当前虚拟环境的 site-packages 中安装；
Python 3.14 起不再从当前目录/脚本目录加载 sitecustomize（安全加固），
故须放在 site-packages 才能在解释器初始化阶段自动执行。

两件事，都是「必须早于用户代码」的：

1. **Qt 插件指路**：把 ``QT_PLUGIN_PATH`` / ``QT_QPA_PLATFORM_PLUGIN_PATH``
   指向当前环境 PyQt5 附带的 plugins 目录。

   根因：venv 中 PyQt5 把插件目录解析到**基础 Python 安装目录**（如
   ``C:/0_self/bin/Python314/platforms``），导致「no Qt platform plugin
   could be initialized」弹窗、进程以 127 退出。程序主入口 main() 会调用
   :func:`widgets.通用.ui_common.ensure_qt_plugin_path`（同逻辑），但模块冒烟与
   任意脚本调不到——由本文件兜底。

2. **预载系统 MSVC 运行时**：见 :mod:`libs.win_dll` 的完整根因说明。

   必须早于 **PyQt5** 而非早于 onnxruntime：PyQt5 一加载 Qt5Core.dll，就会把
   Qt5/bin 里捆的那份旧 MSVC 运行时带进进程，之后再顶就晚了。而 ``python -m
   actions`` 这类模块冒烟是**一个进程跑完整个包**——前面某个 action 导 PyQt5，
   后面「文字识别」的冒烟再 ``import libs.vision.ocr``，就正好踩中。
   main.py 顶部也有一次显式调用（同逻辑，应用不依赖本文件是否装对）。

setdefault 语义：用户手工设置的环境变量优先，不会被覆盖。
"""
import importlib.util
import os
import sys

_spec = importlib.util.find_spec("PyQt5")
if _spec is not None and _spec.submodule_search_locations:
    _plugins = os.path.join(_spec.submodule_search_locations[0], "Qt5", "plugins")
    os.environ.setdefault("QT_QPA_PLATFORM_PLUGIN_PATH",
                          os.path.join(_plugins, "platforms"))
    os.environ.setdefault("QT_PLUGIN_PATH", _plugins)

# 与 libs.win_dll.preload_msvc_runtime 同逻辑。这里不能 import 项目模块
# （解释器初始化阶段项目根未必在 sys.path 上），故内联。
# 整个块务必不抛：本文件在解释器初始化阶段执行，异常会让**每一次** python
# 调用都起不来。真出问题也应由 onnxruntime 那边以原本的错误暴露。
if sys.platform == "win32":
    try:
        import ctypes

        _sys32 = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32")
        for _dll in ("msvcp140.dll", "vcruntime140.dll", "vcruntime140_1.dll"):
            _path = os.path.join(_sys32, _dll)
            if os.path.isfile(_path):
                try:
                    ctypes.WinDLL(_path)
                except OSError:
                    pass
    except Exception:
        pass
