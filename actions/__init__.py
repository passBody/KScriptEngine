# -*- coding: utf-8 -*-
"""步骤模板注册（动态发现，评审#29）。

遍历包内子模块，把各模块 ``__all__`` 导出的步骤类收集到本命名空间——
新增模板只需建文件并写 ``__all__``，无需修改本文件。
"""
import importlib
import pkgutil

from model.步骤.step import Step, StepStatus

__all__ = ["Step", "StepStatus"]

for _info in pkgutil.walk_packages(__path__, __name__ + "."):
    _mod = importlib.import_module(_info.name)
    for _name in getattr(_mod, "__all__", []):
        if _name in __all__:
            continue                       # 包 __init__ 与子模块重复导出 → 去重
        globals()[_name] = getattr(_mod, _name)
        __all__.append(_name)
