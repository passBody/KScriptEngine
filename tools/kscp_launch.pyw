# -*- coding: utf-8 -*-
"""``.kscp`` 双击启动器（注册表 shell 命令调用：``pythonw.exe 本文件 "<工程.kscp>"``）。

**为什么要多这一层**：注册表若直接写 ``pythonw.exe main.py "%1"``，
main.py 一旦抛异常（依赖缺失、Qt 插件没指路、工程损坏），pythonw 没有控制台，
双击后**毫无反应**，只能靠猜。本启动器兜住全部异常并弹 MessageBox。

异常同时落盘到 ``<项目>\\kscp_launch_error.log``（已在 .gitignore），便于附带排查。

`.pyw` 后缀是刻意的：即使被误双击，也走 pythonw 而不是弹一个黑窗。
"""

import os
import sys
import traceback

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG = os.path.join(ROOT, "kscp_launch_error.log")


class _NullStream:
    """pythonw 下 sys.stdout/stderr 是 None；补一个黑洞，免得库代码 print 时炸掉。"""

    encoding = "utf-8"
    errors = "replace"

    def write(self, *args):
        return 0

    def flush(self):
        pass

    def isatty(self):
        return False


def _alert(text: str) -> None:
    """无控制台环境下的错误提示。"""
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, text, "KScript 启动失败", 0x10)
    except Exception:
        pass    # 弹窗都失败就只能靠日志文件了


def main() -> int:
    if sys.stdout is None:
        sys.stdout = _NullStream()
    if sys.stderr is None:
        sys.stderr = _NullStream()

    sys.path.insert(0, ROOT)        # 脚本在 tools/ 下，项目根需自己补进搜索路径
    # 注册表只传 "%1"；额外参数（如 --check）留给手工调试直接跑本文件用
    args = sys.argv[1:]
    path = args[0] if args and not args[0].startswith("-") else None
    check = "--check" in args

    try:
        from widgets.main_widget import main as app_main
        return app_main(path, check)
    except Exception:
        tb = traceback.format_exc()
        try:
            with open(LOG, "w", encoding="utf-8") as f:
                f.write("argv=%r\n\n%s" % (sys.argv, tb))
            tail = "\n\n详细日志：%s" % LOG
        except OSError:
            tail = ""
        _alert("打开 %s 时出错：\n\n%s%s"
               % (path or "(未指定工程)", tb.strip().splitlines()[-1], tail))
        return 1


if __name__ == "__main__":
    sys.exit(main())
