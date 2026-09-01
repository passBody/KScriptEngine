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

    from model.步骤.step_list import StepList

    sl = StepList.create_empty()        # 空列表
    sl.add(step_a)
    sl.insert(1, step_b)                # 插入到下标 1
    sl.move(2, 0)                       # 同列表内移动
    sl.remove(0)                        # 按下标删除
    runs = sl.do_methods()              # [启用步骤的 do, ...]（enabled 过滤）
    fmts = sl.to_format_strings()       # [base64 格式串, ...]
    sl2 = StepList.from_format_strings(fmts, mgr)   # 由格式串还原
"""

from typing import Callable, Iterator, List, Optional, TYPE_CHECKING

from model.步骤.step import Step
from model.合成卡片.composite_card import CompositeCard
from model.log_model import LogModel
from model.合成卡片.placeholder_step import PlaceholderStep

if TYPE_CHECKING:
    from model.步骤.step_manager import StepManager

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
        """由格式串列表还原步骤列表；坏条目 → 红色占位卡片（**不报错退出**）。

        条目可为普通步骤格式串（base64，由 :meth:`StepManager.from_format_string`
        解码）或合成卡片引用标记（``@合成卡片:<路径>``，由
        :meth:`CompositeCard.from_marker` 解码）——二者混存，故步骤列表与合成卡片
        体内均可装合成卡片引用。

        任一条目无法还原（非法编码 / 无匹配模板 / 空引用标记）→ 经
        :meth:`_decode_one` 兜底为 :class:`PlaceholderStep`（红色占位卡片，保留
        原格式串、写明失败原因）；占位卡片的 ``to_format_string`` 原样回吐原串，
        故槽位数据不丢失——模板修复后**重新加载工程**即可还原该条。
        """
        sl = cls()
        for fmt in fmts:
            sl._steps.append(cls._decode_one(fmt, manager))
        return sl

    @staticmethod
    def _decode_one(fmt: str, manager: "StepManager") -> Step:
        """解码单条格式串 → :class:`Step`（**永不抛、永不返回 None**）。

        合成卡片标记 → :meth:`CompositeCard.from_marker`；否则 →
        :meth:`StepManager.from_format_string`。任一失败（非法编码 / 无匹配模板 /
        空引用标记）→ 返回 :class:`PlaceholderStep`（红色占位卡片，保留原格式串、
        写明失败原因），不报错退出。

        占位卡片的 ``to_format_string`` 原样回吐原 ``fmt`` → 下次加载仍走本方法
        重试：模板已修复 → 还原为真实步骤；仍未修复 → 再次占位（稳定，不丢失数据）。
        """
        if CompositeCard.is_marker(fmt):
            try:
                return CompositeCard.from_marker(fmt, manager)
            except ValueError as e:
                LogModel.instance().warning("合成卡片引用无效，已占位：%s" % e)
                return PlaceholderStep(fmt, manager.tree, manager.package,
                                       reason="合成卡片引用无效：%s" % e)
        try:
            step = manager.from_format_string(fmt)
        except ValueError as e:
            LogModel.instance().warning("步骤格式串无效，已占位：%s" % e)
            return PlaceholderStep(fmt, manager.tree, manager.package,
                                   reason="格式串无效：%s" % e)
        if step is None:
            nm = PlaceholderStep._extract_name(fmt) or (fmt[:40] if fmt else "")
            LogModel.instance().warning(
                "步骤无匹配模板，已占位：%s" % (nm or "（未知）"))
            return PlaceholderStep(
                fmt, manager.tree, manager.package,
                reason="没有可匹配的模板（名称/签名与注册表不符）")
        return step

    def insert_format_strings(self, index: int, fmts: List[str],
                              manager: "StepManager") -> None:
        """把格式串列表解码后插入到 ``index``（保持顺序）。

        坏条目 → 红色占位卡片（同 :meth:`from_format_strings`，不报错、不阻断
        其余条目插入）。``index`` 用 Python ``list.insert`` 语义（越界钳制，负数回绕）。
        """
        for i, fmt in enumerate(fmts):
            self._steps.insert(index + i, StepList._decode_one(fmt, manager))

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

    from model.步骤.step import Step
    from model.工程.kscp_package import KscpPackage
    from model.变量.project_variable import ProjectVariable
    from model.步骤.step_list import StepList
    from model.步骤.step_manager import StepManager
    from model.变量.variable_tree import VariableTree

    app = QApplication.instance() or QApplication(sys.argv)

    pkg = KscpPackage.create_empty()
    tree = VariableTree.create_empty()
    tree.add("n1", ProjectVariable.create("number", 100, pkg))

    # 模板字节（有效模板；中文/引号内容一律用 .encode("utf-8")，禁用中文 bytes 字面量）
    GOOD = '''# -*- coding: utf-8 -*-
from dataclasses import dataclass
from model.步骤.step import Step

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

    # 坏条目 → 红色占位卡片（不报错退出；原串保留、写明原因、可被 do 跳过）：
    import base64 as _b64
    import json as _json
    from model.log_model import LogModel
    from model.合成卡片.placeholder_step import PlaceholderStep
    from model.步骤.step import StepStatus
    LogModel.instance().clear()
    # ① 非法编码 → 占位（原因「格式串无效」），原串原样回吐
    bad_enc = StepList.from_format_strings(["not*valid*"], mgr)
    assert isinstance(bad_enc[0], PlaceholderStep)
    assert bad_enc[0].to_format_string() == "not*valid*"     # 原串保留 → 槽位不丢失
    assert "格式串无效" in bad_enc[0]._reason
    # ② 无匹配模板（伪造 name 的合法串）→ 占位（原因「没有可匹配的模板」）
    fake = _b64.urlsafe_b64encode(_json.dumps(
        {"name": "别的步骤", "in": [], "out": [], "io": s1.io.to_format_string()},
        ensure_ascii=False).encode()).decode().rstrip("=")
    bad_nomatch = StepList.from_format_strings([fake], mgr)
    assert isinstance(bad_nomatch[0], PlaceholderStep)
    assert bad_nomatch[0].to_format_string() == fake        # 原串保留
    assert "没有可匹配的模板" in bad_nomatch[0]._reason
    assert "别的步骤" in bad_nomatch[0].name                 # 实例名带原步骤名
    # 占位卡片可被 do() 调度（跳过、置 ERROR、返回 1，不阻断）
    assert bad_nomatch[0].do() == 1
    assert bad_nomatch[0].status is StepStatus.ERROR
    # 每个占位都打一条 warning（可定位失败原因）
    assert sum(1 for e in LogModel.instance().entries
               if e.level.name == "WARNING") >= 2
    # 占位串往返稳定：再加载仍占位（原串不变，模板修复后才还原）
    assert StepList.from_format_strings(
        bad_nomatch.to_format_strings(), mgr)[0].to_format_string() == fake

    # insert_format_strings：保持顺序；list.insert 语义（越界钳制、负数回绕）
    sl4 = StepList.create_empty()
    sl4.insert_format_strings(0, fmts, mgr)          # 头部插入 → [f0, f1]
    assert sl4.to_format_strings() == fmts
    sl4.insert_format_strings(1, [fmts[0]], mgr)     # 中间插入 → [f0, f0, f1]
    assert sl4.to_format_strings() == [fmts[0], fmts[0], fmts[1]]
    sl4.insert_format_strings(99, [fmts[1]], mgr)    # 越界钳制 → 尾部追加
    assert sl4.to_format_strings() == [fmts[0], fmts[0], fmts[1], fmts[1]]
    sl4.insert_format_strings(-1, [fmts[0]], mgr)    # 负数回绕 → 倒数第 2
    assert sl4.to_format_strings() == [fmts[0], fmts[0], fmts[1], fmts[0], fmts[1]]
    # 坏条目在中间 → 三条都插入（中间为占位），不阻断其余
    sl5 = StepList.create_empty()
    sl5.add(s1)
    sl5.insert_format_strings(1, [fmts[0], "not*valid*", fmts[1]], mgr)
    assert len(sl5) == 4                                   # s1 + 3 插入（含占位）
    assert isinstance(sl5[2], PlaceholderStep)            # 中间坏条目 → 占位
    assert sl5[2].to_format_string() == "not*valid*"
    assert sl5[1].to_format_string() == fmts[0] \
        and sl5[3].to_format_string() == fmts[1]
    # 无匹配模板也走占位（不阻断）
    sl5.insert_format_strings(0, [fake], mgr)
    assert isinstance(sl5[0], PlaceholderStep)
    assert len(sl5) == 5

    # ---- 合成卡片引用标记：与普通步骤混存，往返一致 ----
    from model.合成卡片.composite_card import CompositeCard
    cc = CompositeCard("组/卡片X", tree, pkg)
    sl_mix = StepList.create_empty()
    sl_mix.add(s1)                                    # 普通步骤（s1 来自上文）
    sl_mix.add(cc)                                    # 合成卡片引用
    fmts_mix = sl_mix.to_format_strings()
    assert fmts_mix[0] == s1.to_format_string()
    assert fmts_mix[1] == "@合成卡片:组/卡片X", fmts_mix[1]
    sl_back = StepList.from_format_strings(fmts_mix, mgr)
    assert sl_back.to_format_strings() == fmts_mix    # 往返稳定
    assert isinstance(sl_back[1], CompositeCard) and sl_back[1].ref == "组/卡片X"
    # 单条合成卡片标记的列表也能还原
    sl_cc = StepList.from_format_strings(["@合成卡片:列表/独"], mgr)
    assert isinstance(sl_cc[0], CompositeCard) and sl_cc[0].ref == "列表/独"
    # insert_format_strings 同样支持标记
    sl_mix.insert_format_strings(1, ["@合成卡片:组/卡片Y"], mgr)
    assert isinstance(sl_mix[1], CompositeCard) and sl_mix[1].ref == "组/卡片Y"
    # 空 ref 标记 → 占位（不报错；原因「合成卡片引用无效」，原串保留）
    bad_empty = StepList.from_format_strings(["@合成卡片:"], mgr)
    assert isinstance(bad_empty[0], PlaceholderStep)
    assert "合成卡片引用无效" in bad_empty[0]._reason
    assert bad_empty[0].to_format_string() == "@合成卡片:"

    print("StepList smoke OK")
