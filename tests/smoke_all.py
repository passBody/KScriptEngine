# -*- coding: utf-8 -*-
"""全量回归入口：逐模块运行 __main__ 冒烟 + 工程加载自检。

用法::

    python tests/smoke_all.py

说明:
* 每个冒烟以**独立子进程**运行、输出经 capture_output 收集（绝不经过 shell
  管道——管道曾导致 Qt 冒烟 EXIT=139 段错误）。
* 任一失败打印模块名与 stderr 尾部，最后以非零码退出（CI 友好）。
* 冒烟仍内嵌于各生产模块（评审#24：tests/ 目录当前承载回归编排，
  逐步将内嵌冒烟迁入本目录）。
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))   # 便于 import 项目包（如 widgets.通用.ui_common）

MODULES = [
    # actions 包不逐个写死子模块路径：``python -m actions`` 走包级自检
    # （actions/__main__.py：遍历包 + __all__ 每个名字可解析 + 模板 name 全局唯一），
    # 动态覆盖全部 action 模块——重组织/增删 action 时本清单无需改、不失效。
    "actions",
    "libs.key_control.base",
    "model.执行.hotkey", "model.工程.kscp_package", "model.log_model", "model.工程.path_util",
    "model.变量.project_variable", "model.执行.point_timeline", "model.执行.run_interrupt",
    "model.步骤.step", "model.步骤.step_io",
    "model.步骤.step_list", "model.步骤.step_list_store", "model.步骤.step_manager",
    "model.步骤.step_page_store", "model.执行.step_runner", "model.变量.variable_tree",
    "model.合成卡片.composite_card", "model.合成卡片.composite_card_store",
    "model.合成卡片.composite_definition", "model.合成卡片.composite_local_tree",
    "model.合成卡片.composite_signature", "model.合成卡片.placeholder_step",
    "widgets.通用.activity_bar", "widgets.通用.image_overlay", "widgets.通用.log_widget",
    "widgets.main_widget", "widgets.树.management_trees",
    "widgets.卡片.mark_preview_view",
    "widgets.合成卡片.composite_local_picker", "widgets.合成卡片.composite_signature_widget",
    "widgets.树.composite_tree_widget",
    "widgets.树.resource_tree_widget", "widgets.通用.settings_dialog",
    "widgets.卡片.step_card", "widgets.树.step_list_tree_widget",
    "widgets.卡片.step_list_view", "widgets.树.step_tree_widget",
    "widgets.通用.ui_common", "widgets.树.variable_tree_widget",
    "widgets.通用.data_view_dialog",
]
# 注：tools.image_marker 的 __main__ 是**交互式全屏标注 demo**（QEventLoop 阻塞
# 等待人工点击），无断言、无法无人值守运行——不纳入本清单，人工验证。

CHECKS = [
    ["main.py", "sample.kscp", "--check"],
]


def _safe_print(text: str) -> None:
    """中文路径在 GBK 控制台下 print 会 UnicodeEncodeError → 安全降级打印。"""
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode("unicode_escape").decode("ascii"))


def _run(args, timeout: int) -> int:
    try:
        r = subprocess.run([sys.executable] + args, cwd=str(ROOT),
                           timeout=timeout, capture_output=True)
    except subprocess.TimeoutExpired:
        _safe_print("TIMEOUT(%ds): %s" % (timeout, " ".join(args)))
        return 1
    if r.returncode != 0:
        _safe_print("FAIL: %s" % " ".join(args))
        tail = r.stderr.decode("utf-8", "replace").strip().splitlines()
        for line in tail[-8:]:
            _safe_print("  " + line)
    return r.returncode


def main() -> int:
    # venv 等独立部署：先指路 Qt 插件（子进程继承环境变量，避免 Qt 冒烟挂起）
    from widgets.通用.ui_common import ensure_qt_plugin_path
    ensure_qt_plugin_path()

    failed = 0
    for mod in MODULES:
        failed += 1 if _run(["-m", mod], 120) != 0 else 0
    for args in CHECKS:
        failed += 1 if _run(args, 120) != 0 else 0
    n_checks = len(CHECKS)
    if failed:
        _safe_print("\n%d FAILED" % failed)
        return 1
    _safe_print("ALL %d SMOKE + %d CHECKS OK" % (len(MODULES), n_checks))
    return 0


if __name__ == "__main__":
    sys.exit(main())
