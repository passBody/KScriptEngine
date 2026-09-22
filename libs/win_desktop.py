# -*- coding: utf-8 -*-
"""当前输入桌面 / 安全桌面（UAC 提权确认、Ctrl+Alt+Del、登录锁屏）探测。

**什么是安全桌面**

Windows 在 UAC 提权确认、Ctrl+Alt+Del、登录/锁屏会把「输入桌面」切到
``Winlogon``；平时是 ``Default``。安全桌面上鼠标/键盘模拟注入到的是**另一套
桌面**，脚本要么等它消失再操作，要么先判定再走分支——所以这里把「现在在哪个
桌面」单独暴露出来，不掺任何输入模拟。

**三级判定**（逐级减弱，:attr:`InputDesktop.secure` 对应 True / None）

* 打开了当前输入桌面、且名字不是 ``Default`` → 在安全桌面上（**确定**）；
* 打开被拒（``ERROR_ACCESS_DENIED``）→ **疑似**在安全桌面上：普通进程在安全
  桌面出现时经常收到拒绝访问，但这只说明「拿不到」，**不能单独证明**就是 UAC
  （也可能只是这个进程的权限不够）；
* 其它错误 → **判不了**。别把它当「不在安全桌面」——方向反了最危险。

**为什么用 ``OpenInputDesktop`` 而不是 ``OpenDesktop("Winlogon")``**：后者是去
打开**指定**桌面，跟「现在输入在哪」是两回事；前者拿到的才是当前输入桌面。

**降级策略**：非 Windows 下 ``ctypes.WinDLL`` 都不存在，探测一律返回「判不了」
而不是导入失败（同 :mod:`libs.win_dll`：是探测不是依赖）。
"""
import ctypes
import sys
from typing import NamedTuple, Optional

__all__ = ["InputDesktop", "probe_input_desktop", "ERROR_ACCESS_DENIED"]

ERROR_ACCESS_DENIED = 5      # Win32 ERROR_ACCESS_DENIED：安全桌面下最常见的「拿不到」

_DESKTOP_READOBJECTS = 0x0001
_UOI_NAME = 2


if sys.platform == "win32":
    _user32 = ctypes.WinDLL("user32", use_last_error=True)

    _user32.OpenInputDesktop.argtypes = [
        ctypes.c_uint32,          # dwFlags
        ctypes.c_int,             # fInherit (BOOL)
        ctypes.c_uint32,          # dwDesiredAccess
    ]
    _user32.OpenInputDesktop.restype = ctypes.c_void_p      # HDESK；必须声明，
                                                            # 否则 64 位句柄被截成 int

    _user32.GetUserObjectInformationW.argtypes = [
        ctypes.c_void_p,          # hObj
        ctypes.c_int,             # nIndex
        ctypes.c_void_p,          # pvInfo（可为 NULL，先问长度）
        ctypes.c_uint32,          # nLength
        ctypes.POINTER(ctypes.c_uint32),   # lpnLengthNeeded
    ]
    _user32.GetUserObjectInformationW.restype = ctypes.c_int

    _user32.CloseDesktop.argtypes = [ctypes.c_void_p]
    _user32.CloseDesktop.restype = ctypes.c_int
else:
    _user32 = None


class InputDesktop(NamedTuple):
    """一次探测的结果（三个字段互相关联，见 :func:`probe_input_desktop`）。"""

    secure: Optional[bool]     # True=是 / False=否 / None=判不了
    name: Optional[str]        # 当前输入桌面名，通常 Default/Winlogon；取不到为 None
    error: int                 # Win32 错误码，0 = 没出错

    def describe(self) -> str:
        """一行中文依据（日志/卡片提示用）。"""
        if self.secure is True:
            if self.name is not None:
                return "是（当前输入桌面 %s）" % self.name
            return "疑似（打开输入桌面被拒，Win32 错误码 %d）" % self.error
        if self.secure is False:
            return "否（当前输入桌面 %s）" % self.name
        if self.error:
            return "无法判定（未取到输入桌面，Win32 错误码 %d）" % self.error
        return "无法判定（未取到输入桌面）"


def _input_desktop_name():
    """当前输入桌面的名字。

    Returns:
        (名字, 0) 成功；``(None, 错误码)`` 拿不到（含被拒）。
    """
    ctypes.set_last_error(0)
    desktop = _user32.OpenInputDesktop(0, False, _DESKTOP_READOBJECTS)
    if not desktop:
        return None, ctypes.get_last_error()

    try:
        needed = ctypes.c_uint32()
        # 第一次调用只为问缓冲区需要多少字节（pvInfo 传 NULL）
        _user32.GetUserObjectInformationW(
            desktop, _UOI_NAME, None, 0, ctypes.byref(needed))
        if not needed.value:
            return None, ctypes.get_last_error()

        # needed 的单位是**字节**，wintypes.WCHAR 是 2 字节 → 减去结尾 NUL
        buf = ctypes.create_unicode_buffer(needed.value // ctypes.sizeof(ctypes.c_wchar))
        if not _user32.GetUserObjectInformationW(
                desktop, _UOI_NAME, buf, needed.value, ctypes.byref(needed)):
            return None, ctypes.get_last_error()
        return buf.value, 0
    finally:
        _user32.CloseDesktop(desktop)


def probe_input_desktop() -> InputDesktop:
    """探测当前输入桌面。任何情况都**不抛异常**，判不了就用 ``secure=None``。"""
    if _user32 is None:            # 非 Windows：不编造错误码
        return InputDesktop(None, None, 0)

    name, error = _input_desktop_name()
    if name is not None:
        # 普通桌面叫 Default；Winlogon 即 UAC/登录界面
        return InputDesktop(name.lower() != "default", name, error)
    # 被拒只说明「疑似」——见模块 docstring 的三级判定
    return InputDesktop(True if error == ERROR_ACCESS_DENIED else None, None, error)


if __name__ == "__main__":
    # 只读探测（OpenInputDesktop + 问名字 + 关句柄），无副作用，可真跑。
    # 但**不断言本机实际在哪个桌面**——冒烟可能在锁屏/提权弹窗期间被跑到。
    first = probe_input_desktop()
    assert isinstance(first, InputDesktop)
    assert first.secure in (True, False, None), first.secure
    assert first.name is None or isinstance(first.name, str)
    assert isinstance(first.error, int)
    assert first.describe(), "describe() 不该为空"

    # 核心映射：拿到名字时 secure 必须等于「名字不是 default」
    if first.name is not None:
        assert first.secure is (first.name.lower() != "default"), first
    # 拿不到名字时只有 ERROR_ACCESS_DENIED 才敢说「疑似」
    else:
        assert first.secure is (True if first.error == ERROR_ACCESS_DENIED else None), first
        assert first.error != 0, "拿不到名字却没有错误码"

    assert probe_input_desktop() == first, "同一状态下两次探测应一致"
    print("win_desktop 冒烟 OK：%s" % first.describe())
