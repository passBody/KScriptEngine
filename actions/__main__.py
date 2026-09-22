# -*- coding: utf-8 -*-
"""``python -m actions`` 冒烟：包级自检。

三件事：
1. __all__ 每个名字可解析；
2. 模板 name 全局唯一（防同名模板并存——曾出现两个「鼠标偏移」模板，
   模板树困惑且 `from actions import` 解析歧义）；
3. **每个模板都能走通 ``.kscp`` 的导入路径**（见下方 assert 段）。
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

    # ---- .kscp 导入路径复验（相对导入的照妖镜） ----
    # 工程不是 import 本包，而是把模板源码**拷进 .kscp**、再由 StepManager 写进
    # 临时目录、以**合成点分模块名**（如 ``_kscp<N>_actions_输入.鼠标.基础操作.按下``）
    # 加载——那些父包名在 sys.modules 里并不存在。于是模板里任何**多级相对导入**
    # 当场炸成「No module named '_kscp<N>_actions_输入'」，而上面两条 + 各模块直跑
    # 冒烟**全都发现不了**（2026-09-21 串口步骤就栽在这：直跑全绿、导进工程全红）。
    # 模板一律用绝对导入。这里跑真实路径：导入进空工程 → 每个文件都得注册成功、
    # 日志里不许有 ERROR。
    import os

    from model.log_model import LogModel
    from model.步骤.step_manager import StepManager
    from model.工程.kscp_package import KscpPackage
    from model.变量.variable_tree import VariableTree

    _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    _mgr = StepManager(KscpPackage.create_empty(), VariableTree.create_empty())
    LogModel.instance().clear()
    _added = _mgr.copy_source_templates(os.path.join(_root, "actions"))
    _errs = [e.message for e in LogModel.instance().entries if e.level.name == "ERROR"]
    assert not _errs, "模板经 .kscp 路径加载失败（相对导入？）:\n  " + "\n  ".join(_errs)

    # __all__ 里还有 Step/StepStatus/SkipToInput 这类非模板名（基类与枚举），
    # 它们本就不该被注册 —— 只核对真正的模板类。
    # 读 _registry 而非公开的 template_class()：后者**实例化**步骤
    # （entry[0].create_default(...)），42 个实例在无 QApplication 下没必要冒险。
    from model.步骤.step import Step as _Step

    _expected = {c.name for c in (getattr(_pkg, n, None) for n in __all__)
                 if isinstance(c, type) and c is not _Step and issubclass(c, _Step)}
    _loaded = {cls.name for cls, _rel in _mgr._registry.values()}
    _missing = sorted(_expected - _loaded)
    assert not _missing, "本包导出但 .kscp 路径载不进来: %s" % _missing
    assert _added == len(_mgr.template_paths()), \
        "导入 %d 个但注册 %d 个" % (_added, len(_mgr.template_paths()))
    print("actions package smoke OK（.kscp 路径 %d 个模板全通）" % _added)
