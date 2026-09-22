# -*- coding: utf-8 -*-
"""系统类别包：跟 Windows 本身打交道（桌面/会话状态），不模拟输入。

各步骤由 ``actions/__init__.py`` 经 pkgutil 动态发现（收集模块 ``__all__``）。
"""
from .是否进入安全桌面 import IsSecureDesktop
from .打印当前桌面模式 import PrintDesktopMode

__all__ = ["IsSecureDesktop", "PrintDesktopMode"]
