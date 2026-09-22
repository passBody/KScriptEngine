# -*- coding: utf-8 -*-
"""Windows 上把系统自带的 MSVC 运行时「提前顶上去」的兼容性补丁。

**要解决的问题**

GUI 进程里跑 OCR／图片匹配时报::

    DLL load failed while importing onnxruntime_pybind11_state:
    动态链接库(DLL)初始化例程失败。

**根因**

PyQt5 的 ``find_qt()``（``PyQt5/__init__.py``，import PyQt5 就会执行）会做
``os.add_dll_directory(PyQt5\\Qt5\\bin)``。而那个目录里捆了一份**旧的** MSVC
运行时：``msvcp140.dll`` / ``vcruntime140.dll`` / ``vcruntime140_1.dll``。

``os.add_dll_directory`` 的优先级（``LOAD_LIBRARY_SEARCH_USER_DIRS``）高于
PATH 和 System32，所以 Qt5Core.dll 一加载就把这份旧运行时带进了进程。
等 onnxruntime 的 ``.pyd`` 再要 msvcp140 时，进程里已经有旧的了 —— 拿到手的是
它，``DllMain`` 初始化失败。

**判定证据**（同一次 ``add_dll_directory(Qt5/bin)`` 下，只换预载来源）：

* 预载 ``System32`` 的运行时 → onnxruntime 正常导入；
* 预载 Qt5/bin 里那份 → 照样失败。

两边只差 DLL 来源，足以锁定问题出在 Qt 捆的那份上。

**因此必须在 PyQt5 之前预载**：``QApplication`` 建好之后再预载已经晚了，
Qt 的运行时早就进了进程。实测在 PyQt5 之后、onnxruntime 之前补载无效，
所以调用点是进程入口最前面（``main.py`` 顶部），而不是等真要 OCR 的时候。

**降级策略**：非 Windows、DLL 不存在、加载失败 —— 一律跳过不抛异常。
这是补丁，不是依赖；它失效不该让程序起不来（真出问题会在 onnxruntime
那边以原本的错误暴露出来）。
"""

import ctypes
import os
import sys

# 要顶上去的三份。顺序无所谓，但都必须在 Qt5Core.dll 之前进进程。
# 不预载 vcruntime140 也行——python.exe 启动时就链了系统的那份；
# 一并列出是为了显式、不去赌解释器的链接方式。
_NEEDED = ("msvcp140.dll", "vcruntime140.dll", "vcruntime140_1.dll")


def preload_msvc_runtime():
    """把系统自带的 MSVC 运行时预载进当前进程。

    **必须在导入 PyQt5 之前调用**（原因见模块 docstring）。

    Returns:
        list[str]: 实际加载成功的 DLL 文件名。非 Windows 或系统里没有
        这些 DLL 时返回空列表——调用方不需要据此做任何事，
        返回值只为冒烟/诊断留个观察点。

    天然幂等：``ctypes.WinDLL`` 对已加载的 DLL 只返回现有句柄，重复调用无副作用。
    """
    if sys.platform != "win32":
        return []
    system32 = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32")
    loaded = []
    for name in _NEEDED:
        path = os.path.join(system32, name)
        if not os.path.isfile(path):
            continue
        try:
            ctypes.WinDLL(path)
        except OSError:
            # 单个 DLL 加载失败不连累其余，也不上抛。
            continue
        loaded.append(name)
    return loaded


if __name__ == "__main__":
    import subprocess

    done = preload_msvc_runtime()
    print("预载结果:", done or "(无——非 Windows 或系统缺 DLL)")
    assert preload_msvc_runtime() == done, "重复调用结果应一致（幂等）"

    # 真正的回归点：预载之后，PyQt5 与 onnxruntime 必须能共处一个进程。
    # 不加预载时这里会 DLL 初始化失败（这正是本次修复的 bug）。
    code = (
        "import sys\n"
        "sys.path.insert(0, %r)\n" % os.path.dirname(os.path.dirname(os.path.abspath(__file__))) +
        "from libs.win_dll import preload_msvc_runtime\n"
        "preload_msvc_runtime()\n"
        "import PyQt5\n"
        "import onnxruntime\n"
        "print('OK', onnxruntime.__version__)\n"
    )
    # encoding 写死 utf-8：子进程按 UTF-8 写 stdout，父进程若按本机 GBK 解码，
    # 中文会在管道上炸掉（见 libs/vision/__main__.py 里同类注释）。
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True,
                          text=True, encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        sys.stderr.write(proc.stderr)
        raise SystemExit("预载后 PyQt5 + onnxruntime 仍无法共存")
    print("PyQt5 + onnxruntime 共存:", proc.stdout.strip())
    print("win_dll 冒烟 OK")
