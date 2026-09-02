# -*- coding: utf-8 -*-
"""``python -m actions`` 冒烟：包级自检。

__all__ 每个名字可解析、模板 name 全局唯一（防同名模板并存——
曾出现两个「鼠标偏移」模板，模板树困惑且 `from actions import` 解析歧义）。
"""
from actions import __all__

if __name__ == "__main__":
    import actions as _pkg

    for _name in __all__:
        assert hasattr(_pkg, _name), "actions.__all__ 含不可解析名字: %s" % _name
    _names = {}
    for _name in __all__:
        _cls = getattr(_pkg, _name)
        if isinstance(_cls, type):
            _shown = getattr(_cls, "name", None)
            if _shown is not None:
                assert _shown not in _names, \
                    "重复模板名「%s」: %s 与 %s" % (_shown, _names[_shown], _name)
                _names[_shown] = _name
    print("actions package smoke OK")
