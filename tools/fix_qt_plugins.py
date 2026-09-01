# -*- coding: utf-8 -*-
"""安装 Qt 插件指路：把根目录 sitecustomize.py 复制到当前环境的 site-packages。

背景：venv 中 PyQt5 把插件目录解析到基础 Python 安装目录，导致
「no Qt platform plugin could be initialized」弹窗（exit 127）。主入口
main() 有 ensure_qt_plugin_path() 兜底，但模块冒烟（python -m xxx）与
任意脚本需要 sitecustomize 兜底——而 Python 3.14 起不再从当前目录加载
sitecustomize，必须放进 site-packages。

用法（uv sync 重建 venv 后需重跑一次；幂等）::

    .venv/Scripts/python.exe tools/fix_qt_plugins.py
"""
import os
import shutil
import sys
import sysconfig

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "sitecustomize.py")


def main() -> int:
    dst = os.path.join(sysconfig.get_paths()["purelib"], "sitecustomize.py")
    try:
        with open(SRC, encoding="utf-8") as f:
            content = f.read()
    except OSError as e:
        print("读取 %s 失败: %s" % (SRC, e))
        return 1
    if os.path.exists(dst):
        with open(dst, encoding="utf-8") as f:
            old = f.read()
        if old == content:
            print("sitecustomize 已是最新（%s）" % dst)
            return 0
    shutil.copyfile(SRC, dst)
    print("已安装 sitecustomize -> %s" % dst)
    return 0


if __name__ == "__main__":
    sys.exit(main())
