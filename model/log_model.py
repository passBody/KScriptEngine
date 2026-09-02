# -*- coding: utf-8 -*-
"""
日志数据模型（单例）
==================

:class:`LogModel` 是 KScript 的全局日志模型（单例，经 :meth:`LogModel.instance` 取唯一
实例）。支持 5 个级别（DEBUG/INFO/WARNING/ERROR/CRITICAL）、追加日志、清空、按文本/JSON
导出，并通过监听器回调通知变更（保持 PyQt 无关）。

基本用法
--------
::

    from model import LogModel, LogLevel

    log = LogModel.instance()
    log.info("工程已打开")
    log.error("打开失败：%s" % path)
    log.add_listener(refresh_ui)        # 变更时回调
    data = log.export("text")           # -> bytes
"""

from __future__ import annotations

import json
import logging
import time
from enum import Enum
from typing import Callable, List, NamedTuple, Optional

_logger = logging.getLogger(__name__)


class LogLevel(Enum):
    """日志级别（数值与 Python ``logging`` 一致，便于按严重度比较）。"""
    DEBUG = 10
    INFO = 20
    WARNING = 30
    ERROR = 40
    CRITICAL = 50

    @staticmethod
    def levels() -> List["LogLevel"]:
        """按严重度升序返回全部级别。"""
        return sorted(LogLevel, key=lambda lv: lv.value)


class LogEntry(NamedTuple):
    """一条日志：时间戳（epoch 秒）、级别、消息。"""
    time: float
    level: LogLevel
    message: str


class LogModel:
    """全局日志模型（单例）。请用 :meth:`instance` 取唯一实例。"""

    _instance: Optional["LogModel"] = None

    def __init__(self) -> None:
        # 评审#25：直接 LogModel() 绕过单例 → 拒绝（唯一入口 = instance()）
        if LogModel._instance is not None:
            raise RuntimeError("LogModel 是单例：请使用 LogModel.instance()")
        self._entries: List[LogEntry] = []
        self._listeners: List[Callable[[], None]] = []
        self.error_count = 0      # 增量维护的错误/警告计数（状态栏 O(1) 读取）
        self.warning_count = 0

    # ---- 单例 ----
    @classmethod
    def instance(cls) -> "LogModel":
        """返回全局唯一实例（首次调用时构造）。"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def _reset_instance(cls) -> None:
        """清空单例（仅供测试）。"""
        cls._instance = None

    # ---- 写入 ----
    def log(self, level: LogLevel, message: str) -> None:
        """追加一条日志，时间戳取当前 epoch 秒。"""
        self._entries.append(LogEntry(time.time(), level, message))
        if level is LogLevel.ERROR:
            self.error_count += 1
        elif level is LogLevel.WARNING:
            self.warning_count += 1
        self._notify()

    def debug(self, message: str) -> None:
        self.log(LogLevel.DEBUG, message)

    def info(self, message: str) -> None:
        self.log(LogLevel.INFO, message)

    def warning(self, message: str) -> None:
        self.log(LogLevel.WARNING, message)

    def error(self, message: str) -> None:
        self.log(LogLevel.ERROR, message)

    def critical(self, message: str) -> None:
        self.log(LogLevel.CRITICAL, message)

    def clear(self) -> None:
        """清空当前日志。"""
        self._entries.clear()
        self.error_count = 0
        self.warning_count = 0
        self._notify()

    def export(self, fmt: str = "text") -> bytes:
        """导出为 ``bytes``：``"text"`` 每行一条可读日志；``"json"`` 结构化列表。"""
        if fmt == "json":
            data = [{"time": self.format_time(e.time),
                     "level": e.level.name, "message": e.message}
                    for e in self._entries]
            return json.dumps(data, ensure_ascii=False).encode("utf-8")
        lines = ["%s %-8s %s" % (self.format_time(e.time),
                                 e.level.name, e.message) for e in self._entries]
        return "\n".join(lines).encode("utf-8")

    # ---- 读取 ----
    @property
    def entries(self) -> List[LogEntry]:
        """所有日志条目（拷贝，按记录顺序）。"""
        return list(self._entries)

    def __len__(self) -> int:
        return len(self._entries)

    def __iter__(self):
        return iter(self._entries)

    def __bool__(self) -> bool:
        return bool(self._entries)

    # ---- 监听 ----
    def add_listener(self, cb: Callable[[], None]) -> None:
        """注册变更监听器；log/clear 末尾回调（无参）。"""
        self._listeners.append(cb)

    def remove_listener(self, cb: Callable[[], None]) -> None:
        """移除监听器。"""
        if cb in self._listeners:
            self._listeners.remove(cb)

    def _notify(self) -> None:
        for cb in list(self._listeners):
            try:
                cb()
            except Exception:
                # 评审#15：不再静默吞异常——UI 刷新崩溃应可见（其余监听者照常收到通知）
                _logger.exception("日志监听器回调异常（该监听器已跳过）")

    # ---- 静态 ----
    @staticmethod
    def format_time(ts: float) -> str:
        """``epoch 秒 -> "YYYY-MM-DD HH:MM:SS.fff"``。"""
        t = time.localtime(ts)
        return "%s.%03d" % (time.strftime("%Y-%m-%d %H:%M:%S", t),
                            int((ts - int(ts)) * 1000))


if __name__ == "__main__":
    import json as _j

    LogModel._reset_instance()
    a = LogModel.instance()
    b = LogModel.instance()
    assert a is b                                  # 单例唯一
    a.debug("d"); a.info("i"); a.warning("w"); a.error("e"); a.critical("c")
    assert len(a) == 5
    assert [e.level for e in a.entries] == [
        LogLevel.DEBUG, LogLevel.INFO, LogLevel.WARNING, LogLevel.ERROR, LogLevel.CRITICAL]
    assert a.entries[0].message == "d"
    assert LogModel.format_time(0).startswith("1970") and \
        LogModel.format_time(0).endswith(".000")
    txt = a.export("text")
    assert b"DEBUG" in txt and b"CRITICAL" in txt
    obj = _j.loads(a.export("json"))
    assert len(obj) == 5
    assert obj[1]["level"] == "INFO" and obj[1]["message"] == "i"
    assert obj[4]["level"] == "CRITICAL"
    fired = []

    def cb() -> None:
        fired.append("x")

    a.add_listener(cb)
    a.info("again")
    assert len(a) == 6 and fired == ["x"]           # log 触发一次
    a.clear()
    assert len(a) == 0 and fired == ["x", "x"]       # clear 触发一次
    a.remove_listener(cb)
    a.info("no notify")
    assert len(a) == 1 and fired == ["x", "x"]       # 移除后不再触发

    # 评审#25：直接构造绕过单例 → RuntimeError
    try:
        LogModel()
        raise AssertionError("直接 LogModel() 应抛 RuntimeError")
    except RuntimeError:
        pass

    # 评审#15：监听器异常可见（logging 记录），其余监听者照常收到通知
    import logging as _lg
    import sys as _sys
    _records = []
    _h = _lg.Handler()
    _h.emit = lambda r: _records.append(r.getMessage())
    # runpy 下本模块以 __main__ 执行，模块级 _logger 绑定的是 "__main__"——
    # 必须挂到运行命名空间的 logger 上（而非按包名 getLogger）
    _running_logger = _sys.modules[__name__]._logger
    _running_logger.addHandler(_h)
    try:
        a.add_listener(lambda: (_ for _ in ()).throw(RuntimeError("boom")))
        fired2 = []
        a.add_listener(lambda: fired2.append(1))
        a.info("after-bad")
        assert fired2 == [1]                          # 异常监听者不阻断后续通知
        assert any("监听器回调异常" in m for m in _records)   # 异常不再静默
    finally:
        _running_logger.removeHandler(_h)
    print("LogModel smoke OK")
