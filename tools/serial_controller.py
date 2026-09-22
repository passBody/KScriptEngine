# -*- coding: utf-8 -*-
"""
串口控制器（pyserial 薄封装）
============================

:class:`SerialController`：按端口名收发**单行命令**，供 ``actions/输入/串口鼠标/``
下的各步骤共用。

协议约定
--------
* 命令与响应均为 UTF-8 文本、**一行一条**，行结束符固定 ``\\n``
  （:data:`LINE_ENDING`，SCPI 标准）。
* 波特率是唯一的硬件旋钮（:data:`BAUDRATE`）：原生 USB 的单片机（USB CDC）
  忽略它，USB 转串口桥（CH340/CP2102 等）必须与固件一致 —— 换设备后整条链路
  无响应时，先改这一处。

连接管理
--------
按端口名缓存句柄：同一端口反复下发复用同一条连接，省去每步开关口的开销，
也避免反复开合时 DTR 电平抖动复位设备。**写失败即丢弃句柄重连一次**
（拔线重插、设备复位后旧句柄失效是常态），仍失败则抛 :class:`SerialError`，
由步骤置「执行错误」。

.. note::
   导入本模块即导入 pyserial（执行期硬依赖，见 pyproject 注释）。
"""
import threading

import serial
from serial.tools import list_ports

__all__ = ["SerialController", "SerialError", "list_serial_ports", "serial_ctrl"]

LINE_ENDING = "\n"      # 行结束符（SCPI 标准 LF）
BAUDRATE = 115200       # 唯一硬件旋钮：USB CDC 忽略，USB 转串口桥须与固件一致
OPEN_TIMEOUT = 1.0      # 打开端口超时（秒）
READ_TIMEOUT = 1.0      # 查询等待响应超时（秒）


class SerialError(Exception):
    """串口收发失败（打不开 / 写失败 / 查询无响应）—— 步骤据此置执行错误。"""


def _natural_key(name: str):
    """端口名自然序键：``COM10`` 须排在 ``COM3`` 之后（纯字典序会反过来）。"""
    head = name.rstrip("0123456789")
    tail = name[len(head):]
    return (head, int(tail) if tail else 0)


def list_serial_ports() -> list:
    """当前可用串口名列表（如 ``["COM1", "COM3"]``，自然序）。"""
    return sorted((p.device for p in list_ports.comports()), key=_natural_key)


class SerialController:
    """按端口名缓存连接的单行命令收发器（线程安全）。"""

    def __init__(self) -> None:
        # ponytail: 一把全局锁串行化所有端口的收发。当前规模（每个执行器一个
        # 工作线程 + 编辑器单跑）绰绰有余；真出现多页高频并发打同一批端口，
        # 再改成按端口名分锁。
        self._lock = threading.RLock()
        self._conns = {}

    # ==================== 连接管理 ====================
    def _conn(self, port: str):
        """取（或建立）端口句柄；失败抛 :class:`SerialError`。"""
        conn = self._conns.get(port)
        if conn is not None:
            return conn
        try:
            conn = serial.Serial(port, BAUDRATE, timeout=READ_TIMEOUT,
                                 write_timeout=OPEN_TIMEOUT)
        except (serial.SerialException, OSError, ValueError) as e:
            raise SerialError("打开串口 %s 失败: %s" % (port, e))
        self._conns[port] = conn
        return conn

    def close(self, port: str = None) -> None:
        """关闭连接（``port=None`` 关闭全部）；没打开过的端口静默忽略。"""
        with self._lock:
            for name in ([port] if port is not None else list(self._conns)):
                conn = self._conns.pop(name, None)
                if conn is not None:
                    try:
                        conn.close()
                    except Exception:
                        pass        # 句柄已失效（拔线）→ 关不掉也不影响后续重连

    # ==================== 收发 ====================
    def _transact(self, port: str, line: str, expect: bool):
        """下发一行；``expect=True`` 时再读回一行响应（已 strip）。

        写失败视为句柄失效：丢弃后重连一次再试，二次仍失败才抛。
        """
        payload = (line + LINE_ENDING).encode("utf-8")
        with self._lock:
            raw = b""
            for attempt in (1, 2):
                try:
                    conn = self._conn(port)
                    conn.reset_input_buffer()   # 丢弃上一条命令的残留响应
                    conn.write(payload)
                    conn.flush()
                    if not expect:
                        return None
                    raw = conn.readline()       # 超时返回 b""（pyserial 不抛）
                    break
                except (serial.SerialException, OSError) as e:
                    self.close(port)            # 句柄失效 → 丢弃，下次循环重连
                    if attempt == 2:
                        raise SerialError("串口 %s 下发失败: %s" % (port, e))
            text = raw.decode("utf-8", "replace").strip()
            if not text:
                raise SerialError("串口 %s 无响应（超时 %.1fs）: %s"
                                  % (port, READ_TIMEOUT, line))
            return text

    def send(self, port: str, line: str) -> None:
        """下发一行为命令（自动补 :data:`LINE_ENDING`），不读响应。"""
        self._transact(port, line, expect=False)

    def query(self, port: str, line: str) -> str:
        """下发查询命令并读回一行响应（已 strip）；无响应抛 :class:`SerialError`。"""
        return self._transact(port, line, expect=True)


serial_ctrl = SerialController()


# ================================================================
# 冒烟演示：直接 ``python -m tools.serial_controller`` 运行
# ================================================================
if __name__ == "__main__":
    import sys

    # runpy 命名空间陷阱（见 actions/输入/键盘/基础操作/按下.py 顶部注释）：
    # 桩须挂在当前执行命名空间，否则冒烟会去开真实串口。
    _mod = sys.modules[__name__]
    _real_serial = _mod.serial

    # ---- 端口枚举 / 自然序 ----
    assert isinstance(list_serial_ports(), list)
    assert _natural_key("COM10") > _natural_key("COM3"), _natural_key("COM10")
    _seen = ["COM10", "COM3", "COM1"]
    assert sorted(_seen, key=_natural_key) == ["COM1", "COM3", "COM10"]

    # ---- 打开不存在的端口 → SerialError，且不缓存失败句柄 ----
    _ctrl = SerialController()
    try:
        _ctrl.send("COM_NOT_EXIST", "*IDN?")
        raise AssertionError("不存在的端口应抛 SerialError")
    except SerialError:
        pass
    assert _ctrl._conns == {}, _ctrl._conns

    # ---- 桩替换 serial.Serial：后续断言不碰真实硬件 ----
    class _FakePort:
        instances = []
        fail_all_write = False      # 置位 → 连重连出来的新句柄也写失败

        def __init__(self, port, baudrate, timeout=None, write_timeout=None):
            self.port = port
            self.written = b""
            self.to_read = b""
            self.purges = 0
            self.closed = False
            self.fail_write = False
            _FakePort.instances.append(self)

        def reset_input_buffer(self):
            self.purges += 1

        def write(self, data):
            if self.fail_write or _FakePort.fail_all_write:
                raise OSError("桩：写失败")
            self.written += data

        def flush(self):
            pass

        def readline(self):
            return self.to_read

        def close(self):
            self.closed = True

    class _FakeSerialModule:
        SerialException = _real_serial.SerialException

        def __init__(self):
            self.Serial = _FakePort

    _mod.serial = _FakeSerialModule()

    # 发送：自动补 LF；同一端口二次下发复用同一句柄（只开一次口）
    _ctrl = SerialController()
    _ctrl.send("COM9", "*RST")
    assert len(_FakePort.instances) == 1, _FakePort.instances
    assert _FakePort.instances[0].written == b"*RST\n", _FakePort.instances[0].written
    _ctrl.send("COM9", "Mouse:Press 1")
    assert len(_FakePort.instances) == 1, "同一端口应复用句柄"
    assert _FakePort.instances[0].written == b"*RST\nMouse:Press 1\n"
    assert _FakePort.instances[0].purges == 2, "每次下发前清残留响应"

    # 查询：读回一行并 strip（含 CRLF 与首尾空白）
    _FakePort.instances[0].to_read = b"  1920,1024 \r\n"
    assert _ctrl.query("COM9", "DISPlay:GETsize?") == "1920,1024"
    assert _FakePort.instances[0].written.endswith(b"DISPlay:GETsize?\n")

    # 查询超时（readline 返回空）→ SerialError
    _FakePort.instances[0].to_read = b""
    try:
        _ctrl.query("COM9", "*IDN?")
        raise AssertionError("无响应应抛 SerialError")
    except SerialError as e:
        assert "无响应" in str(e), e

    # 写失败 → 丢弃句柄重连一次（新句柄接着写成功）
    _FakePort.instances[0].fail_write = True
    _ctrl.send("COM9", "Key:Press a")
    assert len(_FakePort.instances) == 2, "写失败应重连一次"
    assert _FakePort.instances[0].closed, "旧句柄应被关闭"
    assert _FakePort.instances[1].written == b"Key:Press a\n"
    assert _ctrl._conns["COM9"] is _FakePort.instances[1], "应缓存新句柄"

    # 连续两次写失败 → SerialError，且不留下坏句柄
    _FakePort.fail_all_write = True
    try:
        _ctrl.send("COM9", "Key:Press b")
        raise AssertionError("二次写失败应抛 SerialError")
    except SerialError as e:
        assert "下发失败" in str(e), e
    assert "COM9" not in _ctrl._conns, _ctrl._conns
    assert _FakePort.instances[-1].closed, "重连出的坏句柄也应被关闭"
    _FakePort.fail_all_write = False

    # close：关掉并从缓存移除；重复 close 与关闭空缓存均静默
    _ctrl.send("COM9", "*RST")
    _live = _ctrl._conns["COM9"]
    _ctrl.close("COM9")
    assert _live.closed and _ctrl._conns == {}
    _ctrl.close("COM9")             # 已关闭 → no-op
    _ctrl.close()                   # 关闭全部（空）→ no-op

    _mod.serial = _real_serial
    print("serial_controller smoke OK")
