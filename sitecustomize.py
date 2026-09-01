# -*- coding: utf-8 -*-
"""sitecustomize：自动 Qt 插件指路（venv 部署必需）。

由 ``tools/fix_qt_plugins.py`` 复制到当前虚拟环境的 site-packages 中安装；
Python 3.14 起不再从当前目录/脚本目录加载 sitecustomize（安全加固），
故须放在 site-packages 才能在解释器初始化阶段自动执行。

作用：任何用本 venv 启动的进程（应用、模块冒烟 ``python -m xxx``、IDE、
双击脚本）都会把 ``QT_PLUGIN_PATH`` / ``QT_QPA_PLATFORM_PLUGIN_PATH``
指向当前环境 PyQt5 附带的 plugins 目录。

根因：venv 中 PyQt5 把插件目录解析到**基础 Python 安装目录**（如
``C:/0_self/bin/Python314/platforms``），导致「no Qt platform plugin
could be initialized」弹窗、进程以 127 退出。程序主入口 main() 会调用
:func:`widgets.通用.ui_common.ensure_qt_plugin_path`（同逻辑），但模块冒烟与
任意脚本调不到——由本文件兜底。

setdefault 语义：用户手工设置的环境变量优先，不会被覆盖。
"""
import importlib.util
import os

_spec = importlib.util.find_spec("PyQt5")
if _spec is not None and _spec.submodule_search_locations:
    _plugins = os.path.join(_spec.submodule_search_locations[0], "Qt5", "plugins")
    os.environ.setdefault("QT_QPA_PLATFORM_PLUGIN_PATH",
                          os.path.join(_plugins, "platforms"))
    os.environ.setdefault("QT_PLUGIN_PATH", _plugins)
