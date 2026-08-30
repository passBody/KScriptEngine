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

MODULES = [
    "actions.控制流程.time_delay", "actions.控制流程.输出日志",
    "actions.输入.按键", "actions.输入.鼠标", "actions.输入.鼠标移动",
    "actions.输入.鼠标滚轮", "actions.输入.鼠标拖动", "actions.输入.多次点击",
    "libs.key_control.base",
    "model.hotkey", "model.kscp_package", "model.log_model", "model.path_util",
    "model.project_variable", "model.settings", "model.step", "model.step_io",
    "model.step_list", "model.step_list_store", "model.step_manager",
    "model.step_runner", "model.variable_tree",
    "tools.image_marker",
    "widgets.activity_bar", "widgets.image_overlay", "widgets.log_widget",
    "widgets.main_widget", "widgets.management_trees",
    "widgets.resource_tree_widget", "widgets.settings_dialog",
    "widgets.step_card", "widgets.step_list_tree_widget",
    "widgets.step_list_view", "widgets.step_tree_widget",
    "widgets.ui_common", "widgets.variable_tree_widget",
]

CHECKS = [
    ["main.py", "sample.kscp", "--check"],
    ["main.py", "qwer.kscp", "--check"],
    ["demo_resource_tree.py", "--check"],
]


def _run(args, timeout: int) -> int:
    r = subprocess.run([sys.executable] + args, cwd=str(ROOT),
                       timeout=timeout, capture_output=True)
    if r.returncode != 0:
        print("FAIL: %s" % " ".join(args))
        tail = r.stderr.decode("utf-8", "replace").strip().splitlines()
        for line in tail[-8:]:
            print("  " + line)
    return r.returncode


def main() -> int:
    failed = 0
    for mod in MODULES:
        failed += 1 if _run(["-m", mod], 120) != 0 else 0
    for args in CHECKS:
        failed += 1 if _run(args, 120) != 0 else 0
    if failed:
        print("\n%d FAILED" % failed)
        return 1
    print("ALL %d SMOKE + %d CHECKS OK" % (len(MODULES), len(CHECKS)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
