# -*- coding: utf-8 -*-
"""
带点击间隔时间的坐标点序列（数据结构）
=====================================

:class:`PointTimeline` 记录一组坐标点，以及「点击该点之前等待的时间」，
作为 :func:`tools.image_marker.mark_image` 的 dot / rect / dots 模式返回的坐标信息。

规则
----
* 第一个点间隔固定为 ``0``（没有前序事件）。
* 每次 :meth:`add` 记录当前点，及其相对上一个事件（上一次 add / undo）的间隔秒数。
* :meth:`undo` 移除最后一个点，并把计时归零 —— 下一个点的间隔从撤销时刻起算。

快速遍历
--------
::

    for (x, y), wait in timeline:      # wait = 点击该点前等待的秒数
        ...

也可用 ``timeline.points`` / ``timeline.waits`` / ``timeline.items()``。
"""

import time
from typing import Iterator, List, Optional, Tuple

Point = Tuple[int, int]


class PointTimeline:
    """坐标点 + 每点等待时间的有序序列。"""

    def __init__(self) -> None:
        self._points: List[Point] = []
        self._waits: List[float] = []
        self._t0: Optional[float] = None  # 上一次事件(add/undo)的单调时间；None=尚未开始

    # ---- 写入 ----
    def add(self, x: int, y: int) -> None:
        """记录一个点；间隔 = 距上一次事件的时间，首个点恒为 0。"""
        now = time.monotonic()
        wait = 0.0 if self._t0 is None else now - self._t0
        self._points.append((int(x), int(y)))
        self._waits.append(wait)
        self._t0 = now

    def undo(self) -> Optional[Point]:
        """移除最后一个点并重置计时（从 0 重新计时）；空则返回 None。"""
        if not self._points:
            return None
        p = self._points.pop()
        self._waits.pop()
        self._t0 = time.monotonic()  # 撤销即归零：下一个点从现在起算
        return p

    def clear(self) -> None:
        """清空所有点并重置计时。"""
        self._points.clear()
        self._waits.clear()
        self._t0 = None

    # ---- 读取 ----
    @property
    def points(self) -> List[Point]:
        """所有坐标点（按记录顺序）。"""
        return list(self._points)

    @property
    def waits(self) -> List[float]:
        """每个点点击前等待的秒数（首点恒为 0）。"""
        return list(self._waits)

    def items(self) -> List[Tuple[Point, float]]:
        """``[(点, 等待秒数), ...]``。"""
        return list(zip(self._points, self._waits))

    # ---- 遍历协议 ----
    def __iter__(self) -> Iterator[Tuple[Point, float]]:
        return iter(zip(self._points, self._waits))

    def __len__(self) -> int:
        return len(self._points)

    def __getitem__(self, i: int) -> Tuple[Point, float]:
        return self._points[i], self._waits[i]

    def __bool__(self) -> bool:
        return bool(self._points)

    def __repr__(self) -> str:
        return "PointTimeline(%r)" % (self.items(),)


# ================================================================
# 冒烟演示：直接 ``python -m model.执行.point_timeline`` 运行
# ================================================================
if __name__ == "__main__":
    import time as _t

    tl = PointTimeline()
    assert not tl and len(tl) == 0
    tl.add(1, 2)                       # 首点间隔恒 0
    assert tl.points == [(1, 2)] and tl.waits == [0.0]
    _t.sleep(0.01)
    tl.add(3, 4)                       # 第二点间隔 ≥ 睡眠时长
    assert tl.waits[1] >= 0.01
    assert tl.items() == [((1, 2), tl.waits[0]), ((3, 4), tl.waits[1])]
    assert [p for p, w in tl] == [(1, 2), (3, 4)]
    assert tl[0] == ((1, 2), 0.0) and tl[1][0] == (3, 4)
    # undo：移除末点 + 计时归零（下一个点间隔从撤销起算）
    assert tl.undo() == (3, 4)
    assert len(tl) == 1
    _t.sleep(0.01)
    tl.add(5, 6)
    assert tl.waits[1] >= 0.01        # 从 undo 时刻起算（非从第二个点起算）
    # undo 空 → None；clear 清空并重置计时
    tl.clear()
    assert not tl and tl.undo() is None
    tl.add(7, 8)
    assert repr(tl) == "PointTimeline([((7, 8), 0.0)])"
    # 负索引与 bool
    assert tl[-1] == ((7, 8), 0.0) and bool(tl)

    print("PointTimeline smoke OK")
