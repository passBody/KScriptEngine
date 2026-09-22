# -*- coding: utf-8 -*-
"""KScript 入口。

用法::

    python main.py                 # landing：新建 / 打开
    python main.py xxx.kscp        # 直接打开工程
    python main.py xxx.kscp --check  # 打开后自检并自动退出
    python main.py --help          # 用法
"""
import sys

from libs.win_dll import preload_msvc_runtime

# **必须早于任何 PyQt5 导入**：PyQt5 一加载 Qt5Core.dll，就会把 Qt5/bin 里捆的
# 那份旧 MSVC 运行时带进进程，之后再想顶掉它就晚了——OCR（onnxruntime）会以
# "动态链接库(DLL)初始化例程失败" 挂掉。所以放在这里，而不是等真用 OCR 的时候。
# 原因与验证见 libs/win_dll.py。
preload_msvc_runtime()

from widgets.main_widget import main  # noqa: E402  必须晚于上面那次预载


def _parse(argv):
    """解析命令行；非法用法打印提示并返回 None（评审#26：未知 flag 不再被当路径）。"""
    path, check = None, False
    for arg in argv[1:]:
        if arg == "--check":
            check = True
        elif arg in ("--help", "-h"):
            print("用法: python main.py [工程.kscp] [--check]\n"
                  "  --check  打开后自检并自动退出（渲染验证用）")
            sys.exit(0)
        elif arg.startswith("-"):
            print("未知参数: %s（可用 --help 查看用法）" % arg)
            return None
        elif path is None:
            path = arg
        else:
            print("多余参数: %s（只接受一个工程文件路径）" % arg)
            return None
    return path, check


if __name__ == "__main__":
    parsed = _parse(sys.argv)
    if parsed is None:
        sys.exit(2)
    path, check = parsed
    sys.exit(main(path, check))
