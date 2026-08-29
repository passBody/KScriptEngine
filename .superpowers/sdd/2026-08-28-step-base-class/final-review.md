# 终审：步骤基类（Step + TimeDelay）— 全量评审

- 评审日期：2026-08-28
- 评审范围：`actions/__init__.py`、`actions/base.py`、`actions/控制流程/__init__.py`、`actions/控制流程/time_delay.py`
- 评审方式：逐文件通读 + 依赖组件对照（`widgets/step_io_widget.py`、`model/log_model.py`、`model/variable_tree.py`、`model/project_variable.py`、`model/kscp_package.py`、`main.py`）+ 全量运行验证
- 运行验证（2026-08-28 重跑）：`python -m actions.base` → `Step smoke OK`；`python -m actions.控制流程.time_delay` → `TimeDelay smoke OK`；`python -m widgets.step_io_widget`、`python -m model.kscp_package`、`python -m model.project_variable`、`python -m model.variable_tree`、`python -m model.log_model` 全部 OK；`python main.py --check` → EXIT=0。

---

### Strengths

- **Spec 完全对齐，零未裁定偏差。** 状态枚举四态值、do() 流程（RUNNING → input/run/output → 异常置 ERROR + 日志 + 重抛、run 手动 ERROR 不覆盖、output 不执行于异常路径）、偏移量透传、格式串结构 `{"name","in","out","io"}`、`from_format_string` 的 None-on-名称/签名/槽类型不匹配与 ValueError-on-非法编码的**判定顺序**、`create_default` 的签名驱动槽推导、TimeDelay 的 run 规则（≤0 → ERROR+日志、不抛异常、返回 1）——逐条核对一致。
- **与既有组件惯例无缝一致。** base64 编解码（UTF-8 JSON → urlsafe base64 去填充、`"=" * (-len % 4)` 补丁、`(ValueError, UnicodeDecodeError)` 捕获）与 `ProjectVariable` / `StepIOWidget` 逐字同款；私有辅助命名（`_decode` / `_io_type_lists` / `_signature`）跨模块一致；`StepIOWidget` 的 resolve_inputs / write_outputs / change_value / to/from_format_string 契约全部按既有语义使用。
- **do() 异常路径无未绑定变量问题**：`offset` 在 input()/run() 抛错时未赋值但先 `raise`，安全（`_UnboundLocalError` 不可达）。
- **格式串自描述**（name+in+out+io）：名称不匹配返回 None 的设计天然支持未来步骤注册表逐个尝试解码的调度方式；io 槽类型与签名二次比对堵住了篡改 io 子串的路径。
- **冒烟测试验证真实行为而非同义反复**：断言树值写回（`tree.get("n1").data == 10`）、日志内容、耗时下限、异常重抛、`is` 身份比较；`_ManErrStep` 补写的 `outputs.total` 赋值（修订③）使「手动 ERROR 后 output 仍执行」这一断言真实成立。
- **已裁决的 3 处计划文本修正全部正确落地**，最终文件与修订后的计划文本逐行一致；全量回归（7 模块冒烟 + main --check）重新跑通。

---

### Issues

#### Critical (Must Fix)

无。

#### Important (Should Fix)

1. **类型注解契约无运行时校验，是唯一值得加固的扩展面**
   - 位置：`C:\Users\feelnn\Desktop\项目\KScript\actions\base.py:76-84`（`_io_type_lists` / `_signature`）、`base.py:89-94`（`create_default`）
   - 问题：槽类型完全依赖 dataclass 字段注解字符串（如 `"number"`），没有任何地方校验注解是否为已注册变量类型（`ProjectVariable.type_of`）。子类作者写错时失败既晚又费解：
     - 写真实类型（`seconds: float`）：`to_format_string` 在保存时抛 `TypeError: Object of type type is not JSON serializable`（base.py:151-156），错误信息与根因无关；
     - 写未注册类型名（`"Number"` / `"audio"`）：**静默**——StepIOWidget 把未知类型当非资源类处理（`_type_is_resource` 返回 False），编辑器样式与解析器全部悄悄偏离。
   - 为什么重要：这是后续「步骤列表/步骤管理」任务新增子类的**唯一扩展入口**，且与已裁决的「禁用 `from __future__ import annotations`」裁定互为表里——该裁定防的是注解被加引号（`"'number'"`），但没有任何机制强制执行它（项目其余模块全部使用 future annotations，新模块极易抄错）。TDD 冒烟能兜底但只在作者写了 create_default 断言时。
   - 修复：在 `_io_type_lists` 中对每个注解做 `ProjectVariable.type_of(t)` 校验，未注册即抛 `ValueError("步骤类 %s 字段 %s 的注解 %r 不是已注册变量类型" ...)`；顺带可防御性 `strip("'\"")` 使 future-annotations 误用时也能正确还原。约 5 行，不改变当前两个子类的任何行为。

#### Minor (Nice to Have)

2. `actions/base.py:163` — `from_format_string` 文档字符串写「静态方法」，实际是 `@classmethod`（spec §4.3 同样用词）。中文语境下「静态方法」口语上可泛指类方法，但改措辞（如「类方法」）避免误导。1 字之改。
3. `actions/base.py:175` — `StepIOWidget.from_format_string(obj["io"], ...)` 抛出的 `ValueError` 未经包装直接透出，报错文本是「无效的步骤输入/输出格式化字符串」，而调用方是 Step 层。语义正确（spec 步骤 1 要求 ValueError），只是消息指向了内层组件；可包一层「步骤格式化串中的 io 无效」再抛，纯体验优化。
4. `actions/base.py:61-64` — `input_class: type = object` 默认值：直接对基类调用 `Step.create_default()` / `Step.do()` 会在 `dataclasses.fields(object)` 处抛出不带指引的 `TypeError`。基类本就不该被直接实例化（冒烟已测 `Step.from_format_string` 返回 None），可改为在这些入口对「未被子类覆盖」抛带说明的 `NotImplementedError`，防御性提升。
5. `actions/base.py:108-112` — `zip(fields, values)` 在 `resolve_inputs` 返回值少于字段数时静默截断（停车观察①）。经 `create_default` / `from_format_string` 的受控构造路径不可达，纯防御性，维持不修。
6. `actions/base.py` 冒烟 — RUNNING 状态无直测（停车观察②）：do() 置 RUNNING 后立即被 FINISHED/ERROR 覆盖，唯一未被直接断言的转移。低成本补法：桩子类 `run()` 内 `assert self.status is StepStatus.RUNNING`（约 4 行），把规范 §4.4 的 RUNNING 转移也锁进冒烟。
7. runpy RuntimeWarning（停车观察③）— `python -m` 下包 `__init__.py` 导入导致模块双执行警告；**既有项目通病**（widgets/model 全模块同样输出，已复现确认非本次引入），建议后续单独立项统一处理（懒导入），不在本次范围。
8. `actions/控制流程/time_delay.py:21,64` — 模块级与 `__main__` 内重复 `import time`（停车观察④），计划原文照抄所致，无害，不修。

---

### Recommendations

- **优先做 Important #1**（注解校验）：在「步骤列表/步骤管理」任务开始新增子类前落地，成本最低、收益最大——把扩展面上的两类失败（晚而费解、静默偏离）变成类定义处的即时清晰报错。
- 未来步骤列表引擎的消费方式已由本次 API 完整支撑，建议按此接线：`create_default(tree, pkg)` 新增步骤 → `io.change_value` 配置 → `do()` 返回偏移量（1/2/0 语义由引擎定义）→ `do()` 后检查 `status is ERROR`（异常路径靠重抛捕获）→ `to/from_format_string` 持久化，注册表遍历各步骤类、None 即换下一个类。
- `create_default` 目前不接 `picker`；StepIOWidget 已预留 `picker` 属性钩子（step_io_widget.py:405-415），步骤管理接入树资源管理器时直接赋值即可，无需改基类。
- spec §5 步骤 1 的「数量不符 → ValueError」在实际实现中表现为「in/out 数量与签名不符 → None」（签名比对覆盖数量差）。与计划冒烟一致且对注册表调度更友好，不构成缺陷；如需严格化可在 spec 补一句「步骤层 in/out 数量不符归入签名不匹配（None）」以免后续任务误解。
- 无 git 仓库的运行验证替代方案运转良好（本次全部重跑确认），可沿用。

---

### Assessment

**Ready to merge?** Yes

**Reasoning:** 实现与 spec/计划逐条一致，四个交付文件与修订后计划文本逐字吻合，全量回归（7 模块冒烟 + `main --check` EXIT=0）重跑通过，四条停车观察无一需要升级。唯一 Important 项是扩展面加固（类型注解校验），不阻塞本次交付，但建议在下一步「步骤列表/步骤管理」任务消费该 API 之前落地。
