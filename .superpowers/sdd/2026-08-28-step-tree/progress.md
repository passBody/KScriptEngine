# SDD ledger — plan: docs/superpowers/plans/2026-08-28-step-tree.md

> 适配说明:本仓库**非 git 仓库**(step-manager 计划同款适配延续):task-brief / review-package 脚本依赖 git,不可用 → 简报手工摘录自计划文本;「提交」步骤 → 运行冒烟/自检验证;评审包 → 任务文件清单 + 直接 Read 文件内容;BASE/HEAD 无 git 概念 → 评审对照计划文本与实现文件;收尾 → 无分支可合,终审通过即完成;workspace 保留(无 git log 可恢复)。

## Preflight scan(对照计划文本)

| 任务对 | 共享文件 | 产出→消费 | 检查结果 |
|---|---|---|---|
| T1 → T2 | `model/step_manager.py` | T1 追加 4 方法(move_template/rename_group/create_group/template_class)+ 冒烟断言 → T2 `StepTreeWidget` 消费 template_class/move_template/rename_group/create_group + 既有 load/template_paths/remove_template | 无冲突:插入点唯一(`print("StepManager smoke OK")` 为既有冒烟末行,T1 断言块在其前追加);T1 冒烟起始依赖既有冒烟末尾状态(注册表 控制流程/示例、示例、本地、本地2、子目录/深层;文件 本地步骤.py、本地2.py、子目录/深层.py),与 step-manager 台账 Task 2 收尾状态一致 |
| T2 → T3 | `widgets/step_tree_widget.py` | T2 定义 StepTreeWidget(package)/refresh(current_path=None)/step_selected/preview_widget()/StepInfoPanel/MoveStepDialog(groups, current_group="", parent) → T3 StepManagementTree 消费 StepTreeWidget(package) + preview_widget() | 无冲突:Task 3 经 main_widget.py 直接模块导入(不进 widgets/__init__,约束已写入计划 Global Constraints 与 spec §4.1) |

| 任务 | 自洽检查 | 结果 |
|---|---|---|
| T1 | 冒烟断言 vs 实现:move 3 情形(成功/已存在+日志/未知 ValueError)、rename 4 情形(成功含嵌套路径同步/已存在同名+日志/非法名/未知组)、create 4 情形(顶层/嵌套成功/重名+日志/非法名与父不存在)、template_class 2 情形;方法签名与 spec §3.1–3.4 逐条一致 | 一致;文件修改仅 `model/step_manager.py`;红预期 AttributeError(move_template 未实现) |
| T2 | 冒烟断言 vs 实现:树结构(组=包目录含空组、叶子文本 `名称 (in→out)`、组图标、坏语法不显示)、空包自建 actions、面板两页+列计数、step_selected 仅叶子、mgr+refresh 驱动(move/rename/remove 后路径与组存在性)、对话框 target 解析;「组内最后模板被删 → 组消失」断言依赖 is_dir 语义(只认显式目录+文件后代,remove 后无显式目录项 → False → 隐藏),正确;冒烟不 self-import(直接引用同模块名,规避 python -m 重入),红=NameError | 一致;文件创建仅 `widgets/step_tree_widget.py`;红预期 NameError(StepTreeWidget 未定义) |
| T3 | 集成性改动无测试载体(计划已注明红 N/A);验证 = heredoc 带包自检 + 空工程自检 + 全量回归(9 命令);managers 4 项 [资源, 变量, 步骤(占位), 步骤模板] 与 docstring 同步 | 一致;修改仅 `widgets/main_widget.py` |

## Rulings

- (preflight) **无 git 适配延续**(step-manager 计划既有裁定):简报手工摘录计划文本、验证替代提交、评审包 = 文件清单 + 直接 Read。若适配出错,后果:简报与计划文本漂移,靠逐字摘录 + 评审对照补救。
- (preflight) **计划自洽,无需修正即执行**:T1/T2/T3 无相互矛盾;冒烟状态依赖已与上一计划台账收尾状态核对一致。唯一注意点:T1 插入点措辞为「在 `print("StepManager smoke OK")` 之前」,实施者需保持既有断言块不动、仅在其与 print 之间插入(与 step-manager 计划 T2 同款做法)。
- (T1, 2026-08-29) **计划断言 1 字符缺陷,实施者最小修正,裁定照准**:计划断言 `not any(p.startswith("新组/深") for p in mgr.template_paths())` 永远无法通过——注册表必然含 `新组/深层`(子目录→新组 改名留下的兄弟文件,类名「深层」),`"新组/深层".startswith("新组/深")` 对任何实现恒为 True。修正:改为 `"新组/深/"`(尾斜杠,与同块 `子目录/` 断言及注释意图一致,正是要测的性质「新组/深/ 下无残留」)。RED 阶段(AttributeError,move_template 未实现)不受影响,先红后绿的 TDD 纪律保持。若照旧:Task 1 冒烟必失败且无自洽修法。**T1 评审将核对此偏离。**

## Task 状态

### Task 1(完成,2026-08-29)

- 实施者状态:**DONE_WITH_CONCERNS** — 红为预期 AttributeError(move_template 未实现);绿 `StepManager smoke OK`,EXIT=0;依赖链 4 命令全绿。4 方法逐字转录;1 处计划断言缺陷已最小修正(见 Rulings)。
- 交付:修改 `model/step_manager.py`(追加 4 方法 + 冒烟断言)。
- **任务评审(sonnet):✅ 通过** — spec §3.1–3.5 逐条验证(含 KscpPackage/LogModel 实读核对);零 Critical/Important;1 条 Minor(计划逐字代码,停车,不阻塞):`rename_group` 对带尾斜杠输入(`"新组/"`)会算出 `actions/新组/x` 自移入——父组从未去斜杠的 `group` 计算;§4.2 消费者只传树路径(无尾斜杠),冒烟未覆盖,仅信息性。
- ⚠️ 项(控制器裁决):冒烟无法在评审环境重跑 + 「无其他文件改动」无法 git 确认 → 控制器自跑 `python -m model.step_manager` = `StepManager smoke OK`,EXIT=0,两 ⚠️ 全部解决。
- Task 1: minor (deferred): rename_group 尾斜杠输入边界(消费者不可达,停车)。—— 终审裁定是否修。

- (T2, 2026-08-29) **计划冒烟 1 处 PyQt5 API 适配,实施者修正,裁定照准**:计划断言 `group.icon().isNull()` 在 PyQt5 5.15.11 抛 `TypeError: icon(self, column: int): not enough arguments`——`QTreeWidgetItem.icon(column)` 必填列参。修正:`group.icon(0).isNull()`(含注释说明)。RED 阶段(NameError,类未定义)不受影响。若照旧:冒烟在绿阶段必然崩溃。**T2 评审将核对此偏离。**

### Task 2(完成,2026-08-29)

- 实施者状态:**DONE_WITH_CONCERNS** — 红为预期 NameError(StepTreeWidget 未定义);绿 `StepTreeWidget smoke OK`,EXIT=0;依赖链 4 命令全绿。实现逐字转录;1 处 PyQt5 API 适配已修正(见 Rulings);`widgets/__init__.py` 未动。
- 交付:创建 `widgets/step_tree_widget.py`(唯一新增文件)。
- **任务评审(sonnet):✅ 通过** — spec §4–§5 逐条验证(含 actions/base._signature 同源核对、循环导入链实跑确认);评审者独立重跑冒烟 = `StepTreeWidget smoke OK`,EXIT=0;零 Critical/Important;3 条 Minor(计划级观察,停车,不阻塞,终审裁定):① `refresh()` 对仍选中的叶子无条件重发 `step_selected`(变量树同款继承设计,spec 字面满足);② 空白区右键且已有选中集时,菜单仍带移动/删除(点击落在空白但启用态看选中集;无害);③ 多选 {组, 组内叶子} 时删除为静默无操作(顶层化后过滤为空,提前返回)。
- ⚠️ 项(控制器裁决):RED 证据无法重跑 → 报告 traceback 与简报 Step 2 预期逐字吻合,内部一致,接受;GREEN 由评审者实跑确认。
- Task 2: minor (deferred): refresh 重发信号;空白区右键菜单启用态;组+叶子多选删除静默。—— 终审裁定是否修。

### Task 3(完成,2026-08-29)

- 实施者状态:**DONE** — 5 处逐字编辑;空工程自检 EXIT=0、带包自检(临时 .kscp 构建+检查+清理)EXIT=0、9 模块全量回归全绿。
- 交付:修改 `widgets/main_widget.py`(`_make_icon` kind "template"、import、StepManagementTree、managers 4 项、docstring)。
- **任务评审(sonnet):✅ 通过** — spec §6 五步逐字核对(含占位「步骤」保留为第 3 个、第 4 个为步骤模板);循环导入防线静态确认(widgets/__init__ 未导出);零 Critical/Important;2 条 Minor(停车,不阻塞,终审裁定):① `_make_icon` 自身 docstring 仍只枚举 resource/variable/step/default,漏记新 kind "template"(仅注释陈旧,非 spec 违规——简报 Step 1 代码块不含该改动);② 实施者报告 Step 7 在简报复合命令尾加了 `ls` 确认清理,复合命令整体 EXIT=2,但三个真实验证命令(构建/检查/rm)各自 EXIT=0,证据完整。
- ⚠️ 项(控制器裁决):EXIT 码证据无法重跑 → 报告逐命令含退出码,完整充分,接受;「无其他文件改动」无 git 基线 → 三任务均为单文件范围,实施者各自报告文件清单一致,静态关键约束(widgets/__init__)已确认。
- Task 3: minor (deferred): _make_icon docstring 未列 template kind;报告 Step 7 复合命令尾 ls 致 EXIT=2(证据不受影响)。—— 终审裁定是否修。

### 终审(opus,2026-08-29):✅ Ready to merge(非 git:即完成)

- 三文件全分支评审:零 Critical/Important;跨任务接缝全部实读验证(widget→model 方法签名、`_signature` 语义、`create_empty` 纯内存、KscpPackage move/exists/_dirs 语义、main_widget 与 VariableManagementTree 模式逐点对照、循环导入防线);终审器独立重跑 `model.step_manager` / `widgets.step_tree_widget` / `main.py --check` 全绿。5 条 Minor(M1 rename_group 尾斜杠、M2 仅组选中删除静默、M3 _make_icon docstring、M4 移动对话框预选当前组致 OK 后「目标已存在」日志、M5 自由输入目标遇文件祖先时 ValueError 优雅弹窗)——全部无行为危害,不修。
- **Deferred minors 分诊:全部停车,无必修**。要点:T1 尾斜杠消费者不可达(widget 传归一化路径、target() 剥斜杠);T2-① 变量树同款继承模式、spec 字面满足;T2-② 资源/变量树同款行为、创建上下文仍守 spec;T2-③ 机制纠正(见下);T3-① 仅注释;T3-② 信息性。两处计划缺陷裁定(新组/深/、icon(0))再次复核照准。
- **台账纠正(终审器实测)**:T2-③ 原记录「组+叶子多选 → 顶层化过滤为空 → 删除静默」机制错误——组路径带 `actions/` 前缀而叶子不带,前缀过滤不会滤掉叶子;实测行为 = 对话框计数 1、叶子被删、组被静默忽略。静默无操作仅发生于纯组选中(M2),而组删除是非目标(spec §9.3)。分类(minor,停车)不变。
- 计划文本与实现一致(除两处已裁定偏离外逐字);复选框全部勾选;实现即交付(无分支可合)。

## 计划完成(2026-08-29)

`model/step_manager.py` 4 方法 + `widgets/step_tree_widget.py`(新文件)+ `widgets/main_widget.py` 第 4 图标全部交付完毕。三任务实施 + 三任务评审 + 终审全过;全量回归(9 模块冒烟 + `main --check` + 带包自检)持续全绿。台账即收尾记录(无分支可合,非 git 适配);**workspace 保留**(上轮裁定延续:无 git log 可恢复,删除即永久丢失)。
