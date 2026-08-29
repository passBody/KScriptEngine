# -*- coding: utf-8 -*-
"""
步骤列表模型（纯数据模型）
========================

:class:`StepList` 是有序的 :class:`Step` 对象列表：提供增删插移、可运行 do
导出、base64 格式串导出/还原。列表的「名字」不在本对象内，而在
:class:`StepListStore` 的字典键上。

基本用法
--------
::

    from model.step_list import StepList

    sl = StepList.create_empty()        # 空列表
    sl.add(step_a)
    sl.insert(1, step_b)                # 插入到下标 1
    sl.move(2, 0)                       # 同列表内移动
    sl.remove(0)                        # 按下标删除
    runs = sl.do_methods()              # [启用步骤的 do, ...]（enabled 过滤）
    fmts = sl.to_format_strings()       # [base64 格式串, ...]
    sl2 = StepList.from_format_strings(fmts, mgr)   # 由格式串还原
"""

from typing import Callable, Iterator, List, TYPE_CHECKING

from model.step import Step

if TYPE_CHECKING:
    from model.step_manager import StepManager

__all__ = ["StepList"]


class StepList:
    """步骤列表：有序 ``Step`` 对象列表（纯数据模型）。"""

    def __init__(self) -> None:
        self._steps: List[Step] = []

    # ================================================================
    # 写（变更）
    # ================================================================
    def add(self, step: Step) -> None:
        """追加步骤到末尾。"""
        self._steps.append(step)

    def insert(self, index: int, step: Step) -> None:
        """在 ``index`` 处插入步骤（Python ``list.insert`` 语义：越界钳制，负数回绕）。"""
        self._steps.insert(index, step)

    def remove(self, index: int) -> None:
        """按下标删除步骤；越界抛 :class:`IndexError`。"""
        self._steps.pop(index)

    def move(self, src: int, dst: int) -> None:
        """同列表内移动：``pop(src)`` 后 ``insert(dst)``；``src == dst`` 空操作；越界抛 :class:`IndexError`。"""
        if src == dst:
            return
        step = self._steps.pop(src)
        self._steps.insert(dst, step)

    # ================================================================
    # 导出
    # ================================================================
    def do_methods(self) -> List[Callable[[], int]]:
        """导出可运行的 do：按序收集 ``enabled`` 为 True 的步骤的绑定 ``do``（导出时刻快照）。"""
        return [s.do for s in self._steps if s.enabled]

    def to_format_strings(self) -> List[str]:
        """导出为 base64 格式串列表（复用 ``Step.to_format_string``）。"""
        return [s.to_format_string() for s in self._steps]

    @classmethod
    def from_format_strings(cls, fmts: List[str],
                            manager: "StepManager") -> "StepList":
        """由格式串列表还原步骤列表；任一坏条目（非法编码或无匹配）→ ``ValueError``（带「第 N 条」下标）。"""
        sl = cls()
        for i, fmt in enumerate(fmts):
            try:
                step = manager.from_format_string(fmt)
            except ValueError as e:
                raise ValueError("步骤列表第 %d 条格式串无效: %s" % (i, e))
            if step is None:
                raise ValueError("步骤列表第 %d 条无法还原: 没有可匹配的模板" % i)
            sl._steps.append(step)
        return sl

    def insert_format_strings(self, index: int, fmts: List[str],
                              manager: "StepManager") -> None:
        """把格式串列表解码后插入到 ``index``（保持顺序）。

        事务性：先全部解码成功，再统一插入——任一条坏条目（非法编码或无匹配）
        → :class:`ValueError`（带「第 N 条」下标），且不产生任何部分插入。
        ``index`` 用 Python ``list.insert`` 语义（越界钳制，负数回绕）。
        """
        decoded: List[Step] = []
        for i, fmt in enumerate(fmts):
            try:
                step = manager.from_format_string(fmt)
            except ValueError as e:
                raise ValueError("步骤列表第 %d 条格式串无效: %s" % (i, e))
            if step is None:
                raise ValueError("步骤列表第 %d 条无法还原: 没有可匹配的模板" % i)
            decoded.append(step)
        for i, step in enumerate(decoded):
            self._steps.insert(index + i, step)

    @classmethod
    def create_empty(cls) -> "StepList":
        """生成空步骤列表。"""
        return cls()

    # ================================================================
    # 读取
    # ================================================================
    @property
    def steps(self) -> List[Step]:
        """全部步骤（拷贝）。"""
        return list(self._steps)

    # ================================================================
    # 双下方法
    # ================================================================
    def __len__(self) -> int:
        return len(self._steps)

    def __iter__(self) -> Iterator[Step]:
        return iter(self._steps)

    def __getitem__(self, i: int) -> Step:
        return self._steps[i]


if __name__ == "__main__":
    import sys

    from PyQt5.QtWidgets import QApplication

    from model.step import Step
    from model.kscp_package import KscpPackage
    from model.project_variable import ProjectVariable
    from model.step_list import StepList
    from model.step_manager import StepManager
    from model.variable_tree import VariableTree

    app = QApplication.instance() or QApplication(sys.argv)

    pkg = KscpPackage.create_empty()
    tree = VariableTree.create_empty()
    tree.add("n1", ProjectVariable.create("number", 100, pkg))

    # 模板字节（有效模板；中文/引号内容一律用 .encode("utf-8")，禁用中文 bytes 字面量）
    GOOD = '''# -*- coding: utf-8 -*-
from dataclasses import dataclass
from model.step import Step

@dataclass
class _DemoInput:
    count: "number" = 0

@dataclass
class _DemoOutput:
    total: "number" = 0

class DemoStep(Step):
    name = "示例"
    description = "测试模板"
    input_class = _DemoInput
    output_class = _DemoOutput

    def run(self) -> int:
        self.outputs.total = self.inputs.count * 2
        return 1
'''
    pkg.write_file("actions/示例.py", GOOD.encode("utf-8"))
    mgr = StepManager(pkg, tree)
    mgr.load()

    # 三个步骤实例：s2 禁用（enabled=False），其余默认启用
    s1 = mgr.create_step("示例")
    s1.io.change_value("input", 0, "5")
    s1.io.change_value("output", 0, "n1")
    s2 = mgr.create_step("示例")
    s2.enabled = False
    s3 = mgr.create_step("示例")
    s3.io.change_value("input", 0, "5")
    s3.io.change_value("output", 0, "n1")

    # 空列表
    sl = StepList.create_empty()
    assert len(sl) == 0 and sl.do_methods() == [] and sl.to_format_strings() == []
    assert sl.steps == []

    # 追加 / 插入 / 移动 / 删除
    sl.add(s1)
    sl.add(s2)
    sl.insert(1, s3)                  # [s1, s3, s2]
    assert sl[0] is s1 and sl[1] is s3 and sl[2] is s2
    sl.move(2, 0)                     # [s2, s1, s3]
    assert sl[0] is s2 and sl[1] is s1 and sl[2] is s3
    sl.move(0, 0)                     # src == dst 空操作
    assert len(sl) == 3
    sl.remove(0)                      # [s1, s3]
    assert sl[0] is s1 and sl[1] is s3
    try:
        sl.remove(99)
        raise AssertionError("越界删除应抛 IndexError")
    except IndexError:
        pass
    try:
        sl.move(99, 0)
        raise AssertionError("越界移动应抛 IndexError")
    except IndexError:
        pass

    # 可运行 do 导出：enabled 过滤 + 顺序保持 + 真实可调用
    assert len(sl.do_methods()) == 2
    assert [f() for f in sl.do_methods()] == [1, 1]

    # 格式串往返：规范化输出稳定；禁用状态参与往返
    fmts = sl.to_format_strings()
    assert len(fmts) == 2 and isinstance(fmts[0], str)
    sl2 = StepList.from_format_strings(fmts, mgr)
    assert isinstance(sl2, StepList)
    assert sl2.to_format_strings() == fmts
    sl3 = StepList.create_empty()
    sl3.add(s2)                       # s2 禁用
    sl3.add(s1)
    sl3b = StepList.from_format_strings(sl3.to_format_strings(), mgr)
    assert sl3b[0].enabled is False and sl3b[1].enabled is True

    # 坏条目（严格报错，带下标）：
    # ① 非法编码
    try:
        StepList.from_format_strings(["not*valid*"], mgr)
        raise AssertionError("非法编码应抛 ValueError")
    except ValueError as exc:
        assert "第 0 条" in str(exc)
    # ② 无匹配模板（伪造 name 的合法串）
    import base64 as _b64
    import json as _json
    fake = _b64.urlsafe_b64encode(_json.dumps(
        {"name": "别的步骤", "in": [], "out": [], "io": s1.io.to_format_string()},
        ensure_ascii=False).encode()).decode().rstrip("=")
    try:
        StepList.from_format_strings([fake], mgr)
        raise AssertionError("无匹配应抛 ValueError")
    except ValueError as exc:
        assert "第 0 条" in str(exc)

    # insert_format_strings：事务性解码后统一插入（保持顺序；list.insert 语义）
    sl4 = StepList.create_empty()
    sl4.insert_format_strings(0, fmts, mgr)          # 头部插入 → [f0, f1]
    assert sl4.to_format_strings() == fmts
    sl4.insert_format_strings(1, [fmts[0]], mgr)     # 中间插入 → [f0, f0, f1]
    assert sl4.to_format_strings() == [fmts[0], fmts[0], fmts[1]]
    sl4.insert_format_strings(99, [fmts[1]], mgr)    # 越界钳制 → 尾部追加
    assert sl4.to_format_strings() == [fmts[0], fmts[0], fmts[1], fmts[1]]
    sl4.insert_format_strings(-1, [fmts[0]], mgr)    # 负数回绕 → 倒数第 2
    assert sl4.to_format_strings() == [fmts[0], fmts[0], fmts[1], fmts[0], fmts[1]]
    # 事务性：坏条目出现在中间 → 一条都不插入
    sl5 = StepList.create_empty()
    sl5.add(s1)
    try:
        sl5.insert_format_strings(1, [fmts[0], "not*valid*", fmts[1]], mgr)
        raise AssertionError("坏条目应抛 ValueError")
    except ValueError as exc:
        assert "第 1 条" in str(exc)
    assert sl5.to_format_strings() == [s1.to_format_string()]   # 无部分插入
    try:
        sl5.insert_format_strings(0, [fake], mgr)    # 无匹配模板（复用上文 fake）
        raise AssertionError("无匹配应抛 ValueError")
    except ValueError as exc:
        assert "第 0 条" in str(exc)
    assert len(sl5) == 1

    print("StepList smoke OK")
