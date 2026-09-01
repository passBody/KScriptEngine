---
name: adding-an-action
description: Use when adding a new step template (action) to the KScript project's actions/ directory — a new Step subclass with input/output dataclasses and a smoke test — or when a smoke test would touch real key/mouse/global-listener simulation.
---

# 添加 action（步骤模板）

## Overview

KScript 的 action = `Step` 子类模板（`actions/<类别>/<名字>.py`），随 `.kscp` 工程分发。
新增 = 建文件 + 类别 `__init__` 导出 + 内嵌冒烟，三件缺一不可。

## Checklist

**1. 文件骨架**（仿照 `actions/输入/多次点击.py` 与 `actions/输入/按键.py`）：
- 模块 docstring 分「输入槽 / 运行规则」两段；类 `name`/`description`/`input_class`/`output_class`
- 输入/输出 dataclass 的字段**注解必须是已注册的变量类型名**（`"number"`/`"string"`/`"image"` 等，未知类型在加载时被 StepManager 跳过并记日志）
- **非必须参数**用 `optional(default)` 标记（`from model.步骤.step import Step, optional`）：
  `素材图片: "image" = optional("")` —— 可选槽**空值不校验**（卡片不报错）、
  **解析为 None** 传入 run()、一旦填值仍按类型校验；仅输入槽支持、输出槽恒必须；
  **run() 必须容忍可选槽的 None**（典型：编辑期辅助参数，如鼠标点击的素材图片）
- 输入模拟类模板必须提供 `_new_control()` 桩工厂（冒烟替换用，仿 `按键.py`）
- 鼠标类自定义视图的**素材预览/设置点位复用** `widgets.卡片.mark_preview_view.MarkPreviewView`
  （io/素材槽/mode/read_points/write_points 参数化，合成样式 dot/rect/dots 齐备）——
  不要在新 action 里再复制一份缩略图/弹窗代码
- `__all__ = ["类名"]`
- `run()` 错误路径：置 `StepStatus.ERROR` + `LogModel.instance().error(...)`，**不抛异常**，返回 1；
  错误消息与守卫风格与同类模板保持一致（分开守卫或合并守卫，仿照按键.py）
- 中文内容一律 `.encode("utf-8")` 或普通字符串；**禁止中文 bytes 字面量**
- 默认值不能是「恒错误态」（教训：延时曾默认 0.0）

**2. 注册**：`actions/__init__.py` 是 pkgutil 动态发现（收集各模块 `__all__`），但类别包
`actions/<类别>/__init__.py` 仍是显式导出 —— **必须把新类加进对应 `__init__.py` 的 import 与 `__all__`**。

**3. 冒烟测试**（内嵌 `if __name__ == "__main__"`）：
- **runpy 命名空间陷阱**：桩必须挂到当前执行命名空间 `_mod = sys.modules[__name__]`，
  `_mod._new_control = lambda: 桩()`。**绝不用 `import 模块 as _mod`** —— 包导入缓存
  使桩挂到旧模块对象上，冒烟会触发真实按键/鼠标（按键.py 顶部有完整注释）
- `time.sleep` 同样经 `_mod.time.sleep` 桩替换（冒烟不等真实延时）
- **步骤内长等待用 `from model.执行.run_interrupt import interruptible_sleep`**（立即停止 ~20ms
  内中断；未登记事件时即普通 sleep）——延时、连点间隔、拖拽插值均已接入；
  冒烟对应经 `_mod.interruptible_sleep` 桩替换
- 冒烟**零真实输入**：桩记录调用并断言参数（如 `called == [(key, duration)]`）
- 空常量陷阱：空字符串过不了 StepIOWidget 校验，触达 `run()` 的空值守卫要经
  「string 变量引用 → 空串」（仿按键.py 的 `{{empty_key}}` 用例）
- 断言 `create_default` 的槽类型列表、错误路径日志、格式串往返（`to/from_format_string`）
- 运行：`python -m 模块` **直跑，禁止管道**（管道曾导致 EXIT=139 段错误），
  再 `python tests/smoke_all.py` 全量
- 直跑时先打印的 `runpy RuntimeWarning: found in sys.modules after import of package`
  是桩机制的正常外在表现，**可忽略、非错误**
- **更新 `tests/smoke_all.py` 的 MODULES 列表**；README 与 docs/工程分析.md 中的
  「模块冒烟」计数以 **MODULES 实际条目数为准**核对（grep "模块冒烟"，勿简单 +1——
  历史数字可能已有漂移）

**4. 分发提醒**：`.kscp` 内嵌 action 源码，改完代码后**打开工程需重新导入该步骤**
（删除旧步骤重新添加）才生效。

## Common Mistakes

| 坑 | 后果 | 对策 |
|---|---|---|
| `import 模块 as _mod` 做桩 | 冒烟真实按键 | `sys.modules[__name__]` |
| 漏加类别 `__init__` 导出 | 模板发现不到 | 双处：import + `__all__` |
| 冒烟输出走管道 | EXIT=139 段错误 | 直跑 |
| 忘更新 smoke_all 的 MODULES | 回归漏测 | 顺手加 |
| 次数/数值直接传入 | 小数未定义语义 | `int()` 并注明向下取整 |
| 可选槽的 run() 未处理 None | 空值执行即崩溃 | 判断 None 或只读不依赖 |
| 间隔语义不清 | 末次多等待 | 与多次点击一致：两次之间等待、末次后不等待 |
| `tools/image_marker` 冒烟挂起 | smoke_all 超时 | 该模块是交互 demo，不在回归清单内，勿改动它 |
