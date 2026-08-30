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
sys.path.insert(0, str(ROOT))   # 便于 import 项目包（如 widgets.ui_common）

MODULES = [
    "actions.控制流程.time_delay", "actions.控制流程.输出日志",
    "actions.输入.按键", "actions.输入.鼠标", "actions.输入.鼠标移动",
    "actions.输入.鼠标滚轮", "actions.输入.鼠标拖动", "actions.输入.多次点击",
    "libs.key_control.base",
    "model.hotkey", "model.kscp_package", "model.log_model", "model.path_util",
    "model.project_variable", "model.settings", "model.step", "model.step_io",
    "model.step_list", "model.step_list_store", "model.step_manager",
    "model.step_runner", "model.variable_tree",
    "widgets.activity_bar", "widgets.image_overlay", "widgets.log_widget",
    "widgets.main_widget", "widgets.management_trees",
    "widgets.resource_tree_widget", "widgets.settings_dialog",
    "widgets.step_card", "widgets.step_list_tree_widget",
    "widgets.step_list_view", "widgets.step_tree_widget",
    "widgets.ui_common", "widgets.variable_tree_widget",
]
# 注：tools.image_marker 的 __main__ 是**交互式全屏标注 demo**（QEventLoop 阻塞
# 等待人工点击），无断言、无法无人值守运行——不纳入本清单，人工验证。

CHECKS = [
    ["main.py", "sample.kscp", "--check"],
    ["main.py", "qwer.kscp", "--check"],
    ["demo_resource_tree.py", "--check"],
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
    from widgets.ui_common import ensure_qt_plugin_path
    ensure_qt_plugin_path()

    failed = 0
    for mod in MODULES:
        failed += 1 if _run(["-m", mod], 120) != 0 else 0
    for args in CHECKS:
        failed += 1 if _run(args, 120) != 0 else 0
    if failed:
        _safe_print("\n%d FAILED" % failed)
        return 1
    _safe_print("ALL %d SMOKE + %d CHECKS OK" % (len(MODULES), len(CHECKS)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
