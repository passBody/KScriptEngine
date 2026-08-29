# SDD ledger — plan: docs/superpowers/plans/2026-08-28-step-manager.md

> 适配说明:本仓库**非 git 仓库**(上轮同款适配):task-brief / review-package 脚本依赖 git,不可用 → 简报手工摘录自计划文本;「提交」步骤 → 运行冒烟/自检验证;评审包 → 任务文件清单 + 直接 Read 文件内容;收尾 → 无分支可合,终审通过即完成;workspace 保留(无 git log 可恢复)。

## Preflight scan(对照计划文本)

| 任务对 | 共享文件 | 产出→消费 | 检查结果 |
|---|---|---|---|
| T1 → T2 | `model/step_manager.py` | T1 定义 StepManager(load/template_paths/create_step/from_format_string + `_registry`/`_clipboard`/`_counter`)→ T2 追加 7 个模板操作方法 + 冒烟断言 | 无冲突:T2 冒烟插在 `print("StepManager smoke OK")` 之前(T1 冒烟末行)、实现追加在 `template_paths()` 之后(T1 末方法);T2 所需 `os`/`tempfile` import 已在 T1 冒烟块具备 |

| 任务 | 自洽检查 | 结果 |
|---|---|---|
| T1 | 冒烟断言 vs 实现:template_paths 排序注册表 / 错误日志关键词(坏语法、坏注解+audio、路径冲突)/ create_step 三情形(子目录、顶层、未知 ValueError)/ do() 写 n1=10 / from_format_string 三情形(还原、非法重抛、None+无法还原) | 一致;`files` 属性(非方法)已在计划内修正 `load()` 与 T2 冒烟两处调用;路径冲突断言已改不依赖排序胜者 |
| T1 | 文件创建:仅 `model/step_manager.py`(docstring+冒烟+类定义) | 一致;红预期 ImportError(类未定义,功能缺失红) |
| T2 | 冒烟断言 vs 实现:add 成功 True / 重名无贡献回滚 False+文件消失 / copy-cut-paste 恢复 / 已存在不覆盖+日志 / 粘贴子目录 / 空剪贴板 ValueError / remove+未知 ValueError / copy_source_templates==2 且无 __pycache__ | 一致;`pkg.files` 属性用法已修正;GOOD/LOCAL 链式 replace(示例→本地→本地2/深层)正确 |
| T2 | 文件修改:仅 `model/step_manager.py` | 一致;红预期 AttributeError(add_template 未实现) |

## Rulings

- (preflight) **无 git**:task-brief/review-package 脚本依赖 git 不可用 → 简报手工摘录计划文本、评审包 = 文件清单 + 直接 Read。若适配出错,后果:简报与计划文本漂移,靠逐字摘录 + 评审对照补救。
- (preflight) **计划自洽,无需修正即执行**:T1/T2 无相互矛盾;唯一风险点(`files` 属性、排序依赖断言)已在计划写作阶段修正。
- (T1, 2026-08-28) **计划冒烟 2 行路径断言错误,实施者最小修正,裁定照准**:计划冒烟断言 `template_paths() == ["控制流程/延时", "示例"]` 与 `create_step("控制流程/延时")` 把**文件名**「延时」混入**类名路径**;GOOD 模板类名实为「示例」,`_collect` 逐字实现与 spec §3.2(路径 = 文件夹名/类.name)均为类名语义,跨目录同名测试恰要求两文件类名相同 → 数学上不存在单一路径规则满足原断言。实施者保持实现逐字、修冒烟两行 + 注释为 `"控制流程/示例"`(docstring 示例与真实文件名 `延时.py` 不动,本就正确),与 spec/Task 2 冒烟/其余断言三方对齐。若照旧:Task 1 冒烟必失败且无自洽修法,或被迫篡改 spec 语义 — 不做。

## Task 状态

### Task 1(完成,2026-08-28)

- 实施者状态:**DONE_WITH_CONCERNS** — 冒烟绿(`StepManager smoke OK`,EXIT=0)+ 依赖链 4 命令全绿;红为预期 ImportError。实现逐字转录简报;1 处计划冒烟缺陷已最小修正(见 Rulings)。
- 交付:`model/step_manager.py`(唯一新增文件)。
- **任务评审(sonnet):✅ 通过** — spec 完全合规(类名路径注册、错误粒度、全局约束逐条验证);零 Critical/Important;4 条 Minor(均为简报/计划级措辞,停车,不阻塞):① docstring 用法示例 `"控制流程/延时"` 与修正后冒烟语义不一致(实为 TimeDelay 类名示例,与 spec §1 一致,阅读者可能混淆);② load 摘要无跳过计数(spec §3.3 措辞「成功 N 个 / 跳过 M 个」,简报原文所致);③ 冒烟块 `os`/`tempfile` import 暂未用(Task 2 追加冒烟将使用);④ `_collect` 仅捕获 ValueError 预检异常(spec §6「不抛未预期异常」非绝对,有意的)。评审全文:`task-1-review.md` 见评审者消息。
- Task 1: minor (deferred): docstring 示例路径措辞;load 摘要加跳过计数;冒烟未用 import;预检异常捕获范围。—— 终审裁定是否修。

### Task 2(完成,2026-08-28)

- 实施者状态:**DONE** — 红为预期 AttributeError(`add_template` 未实现);绿 `StepManager smoke OK`;9 命令全量回归全绿(8 模块冒烟 + `main --check` EXIT=0)。逐字转录简报,无担忧。
- 交付:修改 `model/step_manager.py`(追加 8 方法 + 冒烟断言)。
- **任务评审(sonnet):✅ 通过** — spec §5 模板操作表逐条验证;接口聚焦检查(`files` 属性、`remove` 文件/子树语义)确认;零 Critical/Important;3 条 Minor(均为简报原文所致/非缺陷,停车,不阻塞):① `add_template` 对本地源路径非法(FileNotFoundError/PermissionError)直接抛出,spec §6「不抛未预期异常」的边界解读(调用方错误 vs 模型状态错误,有争议,终审裁定);② 回滚路径两次 `load()` 产生两条 info 日志(仅噪音);③ `_actions_rel` 不净化 `dest_dir` 的 `..`/`\`(KscpPackage 归一化已拒绝 `..` 并折叠反斜杠,当前无缺陷,UI 层直接传入用户路径时留意)。
- Task 2: minor (deferred): add 本地路径异常传播;回滚双 load 日志噪音;_actions_rel 输入净化。—— 终审裁定是否修。

### 终审(opus,2026-08-28):Ready to merge: With fixes

- 与 spec/计划逐条一致(实现逐字 = 计划两个代码块,T1 裁定自洽,docstring `"控制流程/延时"` 经核为 TimeDelay 真实类名示例);9 命令全量回归评审者自跑全绿。
- **1 条 Important(已复现,合前必修)**:`_collect` 仅捕 `ValueError`——模板子类漏写 dataclass 输入/输出类(如 `input_class = object`)时 `dataclasses.fields(object)` 抛 `TypeError`,逃逸 `load()` 崩溃整个模型,违反 spec §6「全部错误均不抛未预期异常」与 §3.3 类级跳过契约;且 `load()` 内嵌于每个模板操作,一个坏文件连坐后续 add/paste/remove(paste 在 write 后崩溃还会留孤儿文件)。修复:`except (ValueError, TypeError) as e:` + 冒烟守卫(缺容器模板断言跳过、load 完成)。
- **Deferred minors 裁定**:① docstring 示例 — **可停车**(TimeDelay 类名确为「延时」,示例无错);② load 摘要跳过计数 — **可停车**(仅日志措辞,可选加);③ 冒烟未用 import — **可停车**(Task 2 已用);④ 预检异常捕获范围 — **合前必修**(即上方 Important #1);⑤ add 本地路径异常传播 — **可停车**(与 KscpPackage 本地文件操作约定一致,open 先于写盘无状态残留);⑥ 回滚双 load 日志 — **可停车**(仅冗余 info);⑦ _actions_rel 输入净化 — **可停车**(KscpPackage 归一化拒绝 `..`、折叠反斜杠,当前调用方均为 API 内部)。
- 2 条 spec 级备注(非实现偏离,留 spec 修订):§4.2 重抛范围按字面执行(结构性非法载荷也重抛,非仅编码);§5 覆盖旧模板后无贡献回滚会删旧文件(spec 字面行为,便宜加固 = 回滚前读旧字节)。

### 终审修复 + 限定复审(2026-08-28):✅ 全部解决

- 修复子代理(haiku):**DONE** — 红(TypeError 逃逸 `mgr.load()`,EXIT=1,与预测路径一致)→ 一行修复(`except (ValueError, TypeError) as e:`,step_manager.py:122)→ 绿 `StepManager smoke OK`;9 命令全量回归全绿。报告:`final-fix-report.md`。
- 限定复审(haiku):**All findings addressed** — except 子句精确生效且范围仅限类级预检调用;冒烟守卫(缺容器模板 `input_class = object`)真实复现修复前 TypeError 崩溃;`template_paths()` 断言双保险(缺容器若误注册也会失败);无新破坏。唯一观察:跳过日志措辞「注解非法」对非 dataclass 容器略不精确(合同只要求报错+跳过,不修)。
- 计划文本已同步(except 子句、NO_DATACLASS 守卫冒烟)。

## 计划完成(2026-08-28)

`model/step_manager.py` 交付完毕:StepManager 模板工厂(加载/产出/模板操作/拷贝入口)。双任务实施 + 双任务评审 + 终审(1 Important 已修 + 限定复审视通过)全过;全量回归(8 模块冒烟 + `main --check`)持续全绿。台账即收尾记录(无分支可合,非 git 适配);**workspace 保留**(上轮裁定延续:无 git log 可恢复,删除即永久丢失)。计划复选框已全部勾选,文本已与裁定/终审修复同步。
