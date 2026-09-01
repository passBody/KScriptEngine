# -*- coding: utf-8 -*-
"""
执行列表页容器（多页步骤列表）
==============================

:class:`StepPageStore`：「执行列表」页的有序集合——每页是一个**独立的**
:class:`StepListStore`（组/列表树）。页之间互不共享步骤状态，可被独立
执行器并发运行（如按 ``1`` 跑记录坐标页、按 ``2`` 跑点击坐标页）。

序列化（step_list.json v2）
---------------------------
顶层键 = 页名，值 = 页内树（沿用 StepListStore 的嵌套 dict/数组格式）::

    {
      "执行列表1": {"打开软件": ["…格式串…"], "清理体力": {"检查体力": ["…"]}},
      "执行列表2": {…}
    }

v1 兼容：旧格式顶层 = 组/列表树（顶层任一值为数组）。载入检测：
顶层任一值不是对象 → v1，整棵包成单页「执行列表1」；顶层全为对象 →
按 v2 解读。注意本质歧义：v1 顶层**全是组**（无顶层列表）的文件与 v2
形态相同、无法区分，会按 v2 解读（每个顶层键成为一页）——如需包进
单页请手动包一层。
"""
import json
from typing import Any, Dict, List

from model.工程.path_util import validate_name
from model.步骤.step_list_store import StepListStore

__all__ = ["StepPageStore"]

DEFAULT_PAGE = "执行列表1"


class StepPageStore:
    """执行列表页集合：有序页名 → StepListStore。"""

    def __init__(self) -> None:
        self._pages: Dict[str, StepListStore] = {}   # 插入序 = 页序

    @classmethod
    def create_empty(cls) -> "StepPageStore":
        """空页集合（无页；打开工程路径按需 :meth:`ensure_default_page`）。"""
        return cls()

    # ================================================================
    # 查询
    # ================================================================
    def page_names(self) -> List[str]:
        """有序页名列表。"""
        return list(self._pages)

    def pages(self) -> Dict[str, StepListStore]:
        """有序页名 → 页内树（拷贝引用）。"""
        return dict(self._pages)

    def get_page(self, name: str) -> StepListStore:
        """按页名取页内树；不存在 → :class:`FileNotFoundError`。"""
        try:
            return self._pages[name]
        except KeyError:
            raise FileNotFoundError("执行列表不存在: %r" % name) from None

    # ================================================================
    # 修改
    # ================================================================
    def add_page(self, name: str) -> None:
        """新建空页；非法名 ValueError；重名 FileExistsError（UI 层日志并阻止）。"""
        validate_name(name)
        if name in self._pages:
            raise FileExistsError("执行列表已存在: %r" % name)
        self._pages[name] = StepListStore.create_empty()

    def rename_page(self, old: str, new: str) -> None:
        """重命名页（保持插入位置，同 StepListStore.rename 模式）。

        非法新名 ValueError；不存在 FileNotFoundError；重名 FileExistsError；
        ``old == new`` 幂等。
        """
        validate_name(new)
        if old not in self._pages:
            raise FileNotFoundError("执行列表不存在: %r" % old)
        if old == new:
            return
        if new in self._pages:
            raise FileExistsError("执行列表已存在: %r" % new)
        ordered = list(self._pages.items())
        idx = next(i for i, (n, _) in enumerate(ordered) if n == old)
        ordered[idx] = (new, ordered[idx][1])
        self._pages = dict(ordered)

    def remove_page(self, name: str) -> None:
        """删除页；不存在 FileNotFoundError；删最后一页 ValueError。"""
        if name not in self._pages:
            raise FileNotFoundError("执行列表不存在: %r" % name)
        if len(self._pages) == 1:
            raise ValueError("至少保留一个执行列表")
        del self._pages[name]

    def ensure_default_page(self) -> str:
        """无页时建「执行列表1」，返回（当前）首页名。"""
        if not self._pages:
            self._pages[DEFAULT_PAGE] = StepListStore.create_empty()
        return next(iter(self._pages))

    # ================================================================
    # JSON 导出 / 还原
    # ================================================================
    def to_json_bytes(self) -> bytes:
        """生成 ``step_list.json`` 的 JSON 字节串（可直接 ``package.write_file``）。"""
        node = {name: StepListStore._to_node(store.root)
                for name, store in self._pages.items()}
        return json.dumps(node, ensure_ascii=False).encode("utf-8")

    @classmethod
    def from_json(cls, data: Any, manager) -> "StepPageStore":
        """由 ``step_list.json`` 生成页集合（v1 兼容，见模块 docstring）。

        ``data`` 可为 JSON 字符串、已解析 dict、或字节串（同
        :meth:`StepListStore.from_json`）。``manager`` 用于解码步骤格式串。
        """
        if isinstance(data, dict):
            root = data
        else:
            try:
                root = json.loads(data)
            except (json.JSONDecodeError, UnicodeDecodeError, RecursionError) as e:
                raise ValueError("无效的 step_list.json: %s" % e)
        if not isinstance(root, dict):
            raise ValueError(
                "step_list.json 顶层必须是对象，而非 %s" % type(root).__name__)
        # v1 检测：顶层任一值不是对象（列表叶子）→ 旧格式 → 整棵包成单页
        if any(not isinstance(v, dict) for v in root.values()):
            root = {DEFAULT_PAGE: root}
        store = cls()
        for name, subtree in root.items():
            validate_name(name)                     # 页名同列表/组名规则
            if not isinstance(subtree, dict):
                raise ValueError(
                    "执行列表 %r 的值必须是对象" % name)
            store._pages[name] = StepListStore.from_json(subtree, manager)
        return store


# ================================================================
# 冒烟演示：直接 ``python -m model.步骤.step_page_store`` 运行
# ================================================================
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

    def make_step() -> Step:
        s = mgr.create_step("示例")
        s.io.change_value("input", 0, "5")
        s.io.change_value("output", 0, "n1")
        return s

    # ---- 空容器 / ensure_default_page ----
    store = StepPageStore.create_empty()
    assert store.page_names() == []
    assert store.ensure_default_page() == "执行列表1"
    assert store.page_names() == ["执行列表1"]
    assert isinstance(store.get_page("执行列表1"), StepListStore)
    store.ensure_default_page()                      # 已有页 → 幂等
    assert store.page_names() == ["执行列表1"]

    # ---- 页增删改查：序 / 唯一性 / 非法名 / 守卫 ----
    store.add_page("执行列表2")
    assert store.page_names() == ["执行列表1", "执行列表2"]
    try:
        store.add_page("执行列表1")
        raise AssertionError("重名页应抛 FileExistsError")
    except FileExistsError:
        pass
    try:
        store.add_page("a/b")
        raise AssertionError("页名含 / 应抛 ValueError")
    except ValueError:
        pass
    try:
        store.get_page("不存在")
        raise AssertionError("取不存在页应抛 FileNotFoundError")
    except FileNotFoundError:
        pass
    # rename：保插入位置
    store.add_page("执行列表3")
    store.rename_page("执行列表2", "坐标页")
    assert store.page_names() == ["执行列表1", "坐标页", "执行列表3"]
    store.rename_page("坐标页", "坐标页")           # old == new → 幂等
    assert store.page_names() == ["执行列表1", "坐标页", "执行列表3"]
    try:
        store.rename_page("坐标页", "执行列表1")
        raise AssertionError("重命名撞名应抛 FileExistsError")
    except FileExistsError:
        pass
    try:
        store.rename_page("不存在", "x")
        raise AssertionError("重命名不存在页应抛 FileNotFoundError")
    except FileNotFoundError:
        pass
    # remove：删不存在 FileNotFoundError；删到剩一页合法（最后一页守卫见文末）
    store.remove_page("执行列表3")
    assert store.page_names() == ["执行列表1", "坐标页"]
    try:
        store.remove_page("不存在")
        raise AssertionError("删除不存在页应抛 FileNotFoundError")
    except FileNotFoundError:
        pass

    # ---- 页内树完全复用 StepListStore ----
    p1 = store.get_page("执行列表1")
    sl_open = StepList.create_empty()
    sl_open.add(make_step())
    p1.add_list("打开软件", sl_open)
    p1.add_group("清理体力")
    sl_check = StepList.create_empty()
    sl_check.add(make_step())
    p1.add_list("清理体力/检查体力", sl_check)
    assert p1.paths() == ["打开软件", "清理体力/检查体力"]
    assert p1.get("打开软件") is sl_open

    # ---- JSON v2 往返 ----
    raw = store.to_json_bytes()
    assert isinstance(raw, bytes) and raw.decode("utf-8").startswith('{"执行列表1"')
    store2 = StepPageStore.from_json(raw, mgr)
    assert store2.page_names() == ["执行列表1", "坐标页"]
    p1b = store2.get_page("执行列表1")
    assert p1b.paths() == ["打开软件", "清理体力/检查体力"]
    assert p1b.get("打开软件").steps[0].io.to_format_string() == \
        sl_open.steps[0].io.to_format_string()       # 步骤内容往返一致
    assert store2.to_json_bytes() == raw             # 幂等往返

    # ---- v1 检测：顶层含列表叶子 → 包成单页 ----
    pkg_v1 = KscpPackage.create_empty()
    pkg_v1.write_file("actions/示例.py", GOOD.encode("utf-8"))
    mgr_v1 = StepManager(pkg_v1, tree)
    mgr_v1.load()
    v1_store = StepListStore.create_empty()
    sl_v1 = StepList.create_empty()
    s_v1 = mgr_v1.create_step("示例")
    s_v1.io.change_value("input", 0, "5")
    s_v1.io.change_value("output", 0, "n1")
    sl_v1.add(s_v1)
    v1_store.add_list("主列表", sl_v1)
    v1_raw = v1_store.to_json_bytes()
    migrated = StepPageStore.from_json(v1_raw, mgr_v1)
    assert migrated.page_names() == ["执行列表1"]
    assert migrated.get_page("执行列表1").paths() == ["主列表"]
    # 再写回 → v2 形态（此后按 v2 读取，不重复包层）
    assert StepPageStore.from_json(migrated.to_json_bytes(), mgr_v1) \
        .page_names() == ["执行列表1"]

    # ---- v1 全组歧义（文档明示）：顶层全对象 → 按 v2 解读（各组变各页） ----
    groups_only = StepListStore.create_empty()
    groups_only.add_group("组A")
    groups_only.add_list("组A/列表X", sl_v1)
    amb = StepPageStore.from_json(groups_only.to_json_bytes(), mgr_v1)
    assert amb.page_names() == ["组A"]              # 按 v2：组A 成为一页
    assert amb.get_page("组A").paths() == ["列表X"]

    # ---- 坏数据 ----
    try:
        StepPageStore.from_json(b"[1,2]", mgr)
        raise AssertionError("顶层非对象应抛 ValueError")
    except ValueError:
        pass
    try:
        StepPageStore.from_json('{"页1": 3}', mgr)
        raise AssertionError("页值非对象应抛 ValueError")
    except ValueError:
        pass
    try:
        StepPageStore.from_json('{"a/b": {}}', mgr)
        raise AssertionError("页名非法应抛 ValueError")
    except ValueError:
        pass
    # 空对象 → 无页（打开工程路径经 ensure_default_page 兜底）
    assert StepPageStore.from_json(b"{}", mgr).page_names() == []

    # ---- 删除守卫：从 2 页删到 1 页合法；删最后一页 ValueError ----
    store_del = StepPageStore.create_empty()
    store_del.add_page("甲")
    store_del.add_page("乙")
    store_del.remove_page("甲")                    # 2 → 1 合法
    assert store_del.page_names() == ["乙"]
    try:
        store_del.remove_page("乙")
        raise AssertionError("删最后一页应抛 ValueError")
    except ValueError:
        pass

    print("StepPageStore smoke OK")
