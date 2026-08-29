# SDD ledger — plan: docs/superpowers/plans/2026-08-29-step-widgets.md

> 适配说明:本仓库**非 git 仓库**(既有裁定延续):task-brief / review-package 脚本依赖 git,不可用 → 简报用 awk 从计划文本手工摘录(已验证每简报含 header + Global Constraints + 任务节,边界正确);「提交」步骤 → 运行冒烟/自检验证;评审包 → 任务文件清单 + 直接 Read 文件内容;BASE/HEAD 无 git 概念 → 评审对照简报文本与实现文件;收尾 → 无分支可合,终审通过即完成;workspace 保留(无 git log 可恢复)。

## Preflight scan(对照计划文本)

| 任务对 | 共享文件 | 产出→消费 | 检查结果 |
|---|---|---|---|
| T1 → T4 | model/step_list.py(仅 T1 修改,T4 只读) | `insert_format_strings(index, fmts, manager)` → `StepListView._paste` | 一致:T1 实现与 T4 冒烟 `_paste(1)` 消费同签名 |
| T2 → T5 | model/step_list_store.py(仅 T2 修改) | `remove/rename/walk` → 管理树操作/数据源 | 一致:T5 消费 `remove(p)`/`rename(old, new_name)`/`walk()`;`get` 抛 FileNotFoundError 语义被 `_is_group`/`_on_current_changed` 依赖 |
| T3 → T4 | widgets/step_card.py(仅 T3 创建) | `StepCard`(menu_requested 信号/refresh/set_selected/step/固定尺寸) | 一致:T4 冒烟断言 `_cards`/`_proxies`/`_anims` 结构 |
| T4 → T5 | widgets/step_list_view.py(仅 T4 创建) | `StepClipboard.steps/items` | 一致 |
| T5 → T7 | widgets/step_list_tree_widget.py(仅 T5 创建) | `StepListTreeWidget(store, mgr, clipboard, on_changed)` + list_selected/store_changed | 一致 |
| T4 → T7 | widgets/step_list_view.py | `StepListView`/`StepClipboard` → `_StepListHost` | 一致 |
| T6 → T7 | widgets/variable_tree_widget.py(仅 T6 修改) | `tree` 可选参数 + `tree_changed` 信号 | 一致:T7 构造 `VariableTreeWidget(package, tree)` 并连接信号 |

| 任务 | 自洽检查 | 结果 |
|---|---|---|
| T1 | 冒烟断言(中/越界/负数插入、顺序保持、事务性、第 N 条包装)vs 实现代码一致;红 = AttributeError(方法缺失);仅修改 model/step_list.py | 一致 |
| T2 | 冒烟(walk 先序含空组、remove 三态、rename 保持插入位置/非法/不存在/冲突)vs 实现一致;红 = AttributeError;仅修改 model/step_list_store.py | 一致 |
| T3 | 冒烟(四态色/io 红优先/激活按钮 ✓✗ 文本/选中边框/信号/尺寸)vs 实现一致;红 = ImportError;仅创建 widgets/step_card.py | 一致 |
| T4 | 冒烟(空态/卡片数/滚轮/悬停缩放/添加复制粘贴剪切/对话框树结构/edited/refresh_validity)vs 实现一致;红 = ImportError;仅创建 widgets/step_list_view.py | 一致 |
| T5 | 冒烟(键值/组上列表下/添加组/复制粘贴去重/组子树/剪切保留/重命名/删除)vs 实现一致;红 = ImportError;仅创建 widgets/step_list_tree_widget.py | 一致 |
| T6 | 冒烟扩展(共享树构造/_save 发信号/缺省旧行为)vs 三处修改一致;红 = TypeError(新签名缺失);仅修改 variable_tree_widget.py | 一致 |
| T7 | 集成冒烟(managers 结构/共享树/step_list.json 镜像/选中→卡片/删列表→占位)vs 五处修改一致;红 = NameError;仅修改 main_widget.py(替换 __main__ 块) | 一致 |

## Rulings

- (preflight) **无 git 适配延续**(既有裁定):简报 awk 摘录、验证替代提交、评审包 = 文件清单 + 直接 Read。若适配出错,后果:简报与计划文本漂移,靠 awk 直接抽取 + 评审对照补救。
- (preflight) **计划自检已修缺陷,计划文本即最终权威**:T5 `_dedup_name` 逻辑错误(原 `_is_group` 对不存在路径也返回 True → 永远去重 + 可能死循环,改 walk() 存在性判断)、T5 `_act_paste` 双重组前缀、T5 冒烟锚点(重建后悬空引用/选中缺失/去重期望不符)、T3 激活按钮 ✓✗ 文本(spec §4)、T7 `exists`/`__main__` 块整体替换。简报从修正后文本摘录。
- (preflight) **模型分层**:T1-T6 纯转录(计划含完整代码)→ haiku;T7 集成(多文件接线)→ sonnet;任务评审 → sonnet;终审 → opus。
- (preflight) **提交替代**:每任务「提交」= 冒烟红→绿 + 依赖链回归绿,证据写入报告文件;无 commit 记录。

## Task 状态

### Task 1(完成,2026-08-29)

- 实施者状态:**DONE** — 红 `AttributeError: 'StepList' object has no attribute 'insert_format_strings'`(EXIT=1)→ 绿 `StepList smoke OK` EXIT=0;依赖链回归 3/3 绿(step_list_store / step_manager / actions.base)。
- 交付:修改 `model/step_list.py`(唯一变更文件):`insert_format_strings` 方法(:95-113)+ 冒烟断言(:258-282)。
- **任务评审(sonnet):✅ 通过** — 实现与冒烟断言对简报代码块**逐字一致**(行级核对);事务性(解码循环在插入前完整执行,坏条目居中用例 :272 能捕获"边解码边插入"缺陷)、`index + i` 顺序、`list.insert` 语义(越界 :264/负数 :266)、两条错误消息逐字且与既有 `from_format_strings` 同构、RED 错误类型符合简报预期;零 Critical/零 Important;1 条 Minor(报告行号与磁盘偏移 5 行,证据卫生)。
- Task 1: minor (deferred): ①报告行号引用与磁盘状态统一偏移 5 行(RED traceback 235 vs 实际 240)——证据卫生,不影响 TDD 结论;终审分诊。⚠️ RED 时刻文件内容无法从包内独立验证——已裁决:报告含简报预期错误类型 + EXIT=1 + 失败点为新断言首调用,与计划 Step 2 完全一致,采纳(与上一计划同一验证标准)。

### Task 2(完成,2026-08-29)

- 实施者状态:**DONE** — 红 `AttributeError: 'StepListStore' object has no attribute 'walk'`(EXIT=1)→ 绿 `StepListStore smoke OK` EXIT=0;回归 2/2 绿(step_list / step_manager)。疑虑 1 条:`step_list_store.py` 实际无 `from __future__ import annotations`(简报/派发误称已在)——按「不要重复加」未添加,运行正常,系上轮计划遗留状态。
- 交付:修改 `model/step_list_store.py`(唯一变更文件):typing 行加 `Tuple`(:39)、`remove`(:240-247)、`rename`(:249-269)、`walk` + `_collect_walk`(:271-289)、冒烟断言(:458-510)。
- **任务评审(sonnet):✅ 通过** — 实现与冒烟断言对简报逐字一致;remove 三态、rename 保持插入位置(重建父 dict 不 append)+ 三类异常 + 组子树对象同一性(`is sl_check`)、walk 先序含空组全部落实;冒烟钉住真实行为(键序/子树身份/walk 序列);手推冒烟全通过;零 Critical/零 Important;2 条 Minor(均为信息性)。
- Task 2: minor (deferred): ①`__future__` 行缺失系简报不实(上轮遗留,无运行时影响——所有注解运行时可求值),可选后续任务补;②`rename("x","x")` 同名改名 → FileExistsError(非 no-op),spec 未定义此情形,行为可辩护;T5 `_act_rename` 已用 `if new_path == old: return` 预先规避——下游无风险。

### Task 5(完成)

- 实施者状态:**DONE** — 冒烟绿 `StepListTreeWidget smoke OK` EXIT=0;回归 4/4 绿(step_list_view / step_list_store + 附加 step_card / step_list);实现块 320/320 行、冒烟块 128/128 行逐字一致,仅 2 处文档化偏差。
- **偏离简报两处(待评审独立判定)**:① QtCore import 行去掉 `QKeySequence`(PyQt5 中位于 QtGui,简报同块下一行已从 QtGui 导入;RED 第 2 次运行实证;三个既有 widget 文件同先例);② 冒烟顶层顺序断言 `["清理体力", "打开软件", "空组"]` → `["清理体力", "空组", "打开软件"]`(断言与实现「组在上、列表在下、每层各自按名排序」矛盾——组内排序恒在列表前,任何排序规则都无法把列表插到两组合之间;实现保持简报逐字,仅改期望)。
- **任务评审(sonnet):✅ 通过,1 条 Important(计划继承)进入修复轮** — 两处偏离独立验证确属正当(① QKeySequence 属 QtGui,PyQt5 5.15 实证 + 三个既有 widget 文件同先例,简报 QtCore 行死路;② 顶层顺序断言在简报自身「组在上、列表在下、每层各自排序」规则下不可能成立——任何排序规则都无法把列表插到两组合之间,断言与规范注释矛盾,改期望正确);约束全过(future import/中文注释/无 do()/无中文 bytes/encode("utf-8")/style() 守卫/QPainter 图标/剪贴板保留冒烟钉住);TDD 证据端到端自洽(RED 1 NameError → RED 2 QtCore ImportError → RED 3 顺序断言 → GREEN);零 Critical。
- **Ruling(修复轮 1,spec §2 剪贴板契约为绑定权威):多选复制/剪切不一致必须修,方案 = 限制复制/剪切为单选。** 评审 Important: `_act_copy`(:262-268)只复制 `tops[0]`,`_act_cut`(:290-296)却删除全部 tops——ExtendedSelection + 菜单对任意非空选中启用复制/剪切,多选剪切永久丢失未复制项,违反「剪切 = 复制 + 删除」;代码逐字来自简报 Step 3,系计划缺陷。spec §2 剪贴板 = 单条目 `(名, 三元组列表)`,多条目载荷需改 spec 契约(重);故修法 = 菜单 `a_copy`/`a_cut` 仅 `len(tops) == 1` 时启用(与既有「重命名仅单选」模式一致)+ `_act_copy`/`_act_cut` 入口守卫 + 覆盖冒烟(双选 → 复制/剪切 no-op,剪贴板与 store 均不变)。若照旧:用户多选两个列表按剪切,第二个永久丢失,数据损坏。
- Task 5: minor (deferred) 3 条——①`_act_paste` 全冲突时仍 `_changed`(空保存 step_list.json,可加 any-success 旗标);②`refresh()` 末行手动 `_on_current_changed` → 改名/粘贴后 `list_selected` 非纯点击语义(简报逐字,宿主重新显示变更列表属合理,T7 知悉即可);③冒烟未直接连接 `store_changed`(与 on_changed 同两行,风险可忽略)。— 终审分诊。
- 修复轮 1/5:**完成,re-review(sonnet)✅ 全部关闭** — 菜单 a_copy/a_cut 仅 `len(tops) == 1` 启用 + `_act_copy`/`_act_cut` 入口守卫 + 冒烟双选 no-op 断言;re-review 独立验证守卫使剪切在任意可达状态满足「复制 + 删除」、删除保持多选不误删、双选断言无条件执行于 print 前;报告 vs 磁盘逐行核对一致;零新 breakage。
- **Task 5: 完成。** 计划/简报已同步修复后最终实现(4 处:菜单 setEnabled ×2、_act_copy/_act_cut 守卫、冒烟双选 no-op 块)——计划文本即最终权威;T7 消费 `StepListTreeWidget(store, mgr, clipboard, on_changed)` + `list_selected`/`store_changed` 自动继承修复后行为。

### Task 4(评审进行中)

- 实施者状态:**DONE** — 冒烟绿 `StepListView smoke OK` EXIT=0;回归 3/3 绿(step_card / step_list / step_list_store);实现块与简报逐字节一致(唯一差异 = docstring 后多一空行),冒烟块 3 处差异均系有意修正或非代码。
- **偏离简报两处(实施者报告,待评审独立判定)**:① `write_file(...GOOD.replace(...))` 补 `.encode("utf-8")`——简报转录笔误,与 Global Constraint「模板字节一律 .encode」冲突,不修则 RED 拦在类缺失之前且永远无法绿;② `QWheelEvent` 6 参构造在本机 PyQt5 5.15.11 不存在 → 8 参旧式(载荷与断言语义不变)。两处均已列入评审包的「已知偏离」段。
- 冒烟断言全过:空态提示/卡片数/滚轮水平移动/事件过滤转发/悬停动画参数(Enter 1.06 / Leave 1.0)/三处添加 + edited×3/复制粘贴往返/剪切保留+二次粘贴/refresh_validity 不重建/对话框分组与叶子 UserRole/选组 accept 被拒。
- **任务评审(sonnet):✅ 通过 — 零 Critical/零 Important。** 两处偏离独立验证确属必要:① `write_file` 走 `bytes(data)`(kscp_package.py:258,267),简报字面 str 必抛 TypeError、RED 不可达,补 encode 系唯一出路;② 6 参 QWheelEvent 本机实测失败,8 参旧式构造成功且 `angleDelta().y()==-240` 载荷不变。接口逐一对盘(insert_format_strings :90 事务性、template_paths :133 / create_step :160、StepCard :54/52/115/110);约束全过(future import、无 do() 调用、无 Ctrl+C/X/V、无中文 bytes、_PATH_ROLE 整数、style() 判 None、剪贴板保留语义冒烟钉住);TDD 证据与简报预期一致。
- Task 4: minor (deferred) 4 条——①`:246/:278` 坐标语义不一致(计划继承):卡片命中分支把 viewport 局部坐标直接喂 `menu.exec_`,与空白分支 mapToGlobal、卡片信号路径 globalPos 不一致;当前实际不可达(StepCard contextMenuEvent accept,信号仅空白区触发)→ 若 accept 改变则菜单弹错位。②`:108` `SP_DirIcon` 与「不依赖 QStyle 标准图标枚举」约束冲突(简报自带代码,style() 守卫已保运行安全)。③`:230` Leave 时 z 序立即降回 0 而动画仍在缩小,160ms 内邻卡可能压住缩回卡——外观问题,可在 finished 里还原 z。④`:332-334` `_paste` 的 QMessageBox.warning 路径冒烟未覆盖(坏剪贴板串)。— 终审分诊。
- **Task 4: 完成。**

### Task 3(完成)

- 实施者状态:**DONE** — 红 `ImportError: cannot import name 'StepCard'`(EXIT=1)→ 绿 `StepCard smoke OK` EXIT=0;依赖链回归绿。交付:创建 `widgets/step_card.py`(唯一新文件)。
- **任务评审(sonnet):✅ 通过,1 条 Important 进入修复轮** — 四态色 / io 红优先 / 激活按钮 ✓✗ / 选中边框 / menu_requested / 固定尺寸全部落实;桩注解去引号偏离经评审**独立验证**为「genuinely required, minimal, behavior-preserving. Not a defect」(Python 3.14 PEP 563 下 `a: "number"` 字符串化为 `"'number'"` → `ProjectVariable.type_of` 纯 dict 查找失败;actions/base.py 无 future import 故不受影响——T4/T5/T7 简报均无 dataclass 桩,不受牵连);零 Critical;2 条 Minor(冒烟未走 contextMenuEvent 真实路径——手动 emit;按钮绿/灰 hex 仅经 ✓✗ 文本间接断言)。
- **Ruling(修复轮 1,spec §4 ③ 为绑定权威):picker 刷新时机缺陷必须修。** 评审 Important #1(计划继承):step_card.py:96-103 picker 包装器在调用方应用选中值**之前**同步 `self.refresh()`(`_pick_input`/`_pick_output` 先 `picker(...)` 后 `_set_input(...)`,且 `_refresh_input_field`/`_refresh_output_field` blockSignals)→ 通过 picker 对话框选择变量后卡片颜色陈旧,直到无关刷新;钩子未达成 spec §4 ③「资源类按钮经 picker 选择后重检」的文档用途,T4 视图将继承此行为。裁定:修——包装器内改 `QTimer.singleShot(0, self.refresh)`(值落地后的事件循环迭代重检)+ 补覆盖性冒烟断言(fake picker 使 io 变非法 → 调用后同步仍旧色 → `app.processEvents()` 冲刷 zero-timer 后变红);修复验证通过后同步计划 T3 代码块与 task-3-brief.md(逐字同步纪律)。若照旧:用户经 picker 选变量后卡片颜色不更新,显示错误。
- 修复轮 1/5:**完成,re-review(sonnet)✅ 全部关闭** — 包装器改 `QTimer.singleShot(0, self.refresh)`(step_card.py:100),`QTimer` import(:29);覆盖冒烟(:247-260,构造前替换 fake picker → 调用后同步仍旧色 → `processEvents()` 后红);re-review 独立验证调用侧(仅 step_io_widget.py:418/:424 两处 picker 调用、值后落地;`_refresh_input_field` blockSignals)成立;报告 vs 磁盘逐行核对一致;零新 breakage(cancel 返回 None 时延迟刷新 = 无害 no-op;bound method 保活 self;wrapper 引用环系修复前既有,不变)。
- **Task 3: 完成。** 计划/简报已同步修复后最终实现(三处:桩注解去引号、QTimer import + 延迟重检、picker 覆盖冒烟 12 行)——re-review 出范围观察确认 T4 直接消费 StepCard,自动继承修复后行为;T4 冒烟不得假设 `step.io.picker` 在卡片构造后未被包装(已带入 T4 派发)。

### Task 6(完成,2026-08-29)

- 实施者状态:**DONE** — 冒烟红→绿(RED = `TypeError: QTreeWidget(...): argument 1 has unexpected type 'VariableTree'` EXIT=1 → GREEN `VariableTreeWidget smoke OK` EXIT=0)+ 回归 2/2 绿(resource_tree_widget OK / main.py --check EXIT=0)。
- 交付:修改 `widgets/variable_tree_widget.py`(唯一变更文件):① `tree_changed = pyqtSignal()`(:112)② `__init__` 加可选 `tree` 参数 + 加载分支(:114-141,缺省 None = 旧行为自加载;共享分支不读盘/不写空文件)③ `_save` 写盘后 `tree_changed.emit()`(:155-159)+ 冒烟断言(:1080-1094)。三处与简报逐字一致,中间行未动,无新 import。
- **任务评审(sonnet):✅ 通过 — 零 Critical/零 Important。** 三处修改与冒烟逐字核对;`tree_changed` 全文件仅 :112/:159;全库调用点均单参数,签名变更安全;旧 plan(2026-08-28-variable-tree.md:516-556)核实旧签名,2 位置参调用在 Python 层合法 → 评审独立重跑 3 条命令全部复现。
- **已知偏离判定(RED 错误类型):接受** — 属简报允许的「等价类缺失错误」且是唯一合理等价呈现:失败根因唯一 = 新 `tree` 参数缺失;RED 失败点 = 新断言首调用(:1085),EXIT=1,既有断言全过。
- Task 6: minor (deferred) 2 条——①简报 Step 2 预期 RED 消息不可达(plan defect:旧签名 `(package, parent=None)` 下 2 位置参合法,错误推迟到 Qt 构造器层;简报 TDD 框架以「失败原因 = 目标改动缺失」为判据,示例非穷举,不要求动作);②RED traceback 行号 :1079 vs 磁盘 :1085 差 7 行(实现新增行数恰好 +7,中间态痕迹,自洽)。— 终审分诊。
- **Task 6: 完成。** T7 消费 `VariableTreeWidget(package, tree)` + `tree_changed` 已就绪。

### Task 7(完成,2026-08-29)

- 实施者状态:**DONE** — RED `NameError: name 'StepListManagementTree' is not defined`(EXIT=1,失败点 = 冒烟首条新特性断言)→ GREEN `MainWindow smoke OK` EXIT=0 → **全量回归 17/17 全绿**(逐命令,不经管道);另附 py_compile OK。
- 交付:修改 `widgets/main_widget.py`(唯一变更文件):① imports(:25 Callable + :40-45 六个新 import)② `VariableManagementTree` 加可选 tree 参数 + 两处透传(:160-183)③ 新类 `StepListManagementTree`(:213-276)+ `_StepListHost`(:279-301)④ `_open_package` 头部(:668-686,第 3 位替换占位 + 共享树 + `vtw.tree_changed.connect(sl_mgr.refresh_cards)`;:687 起原样保留)⑤ `_load_shared_tree`(:706-714);__main__ 块整体替换为集成冒烟(:729-822)。五处与简报逐字节一致。
- **任务评审(sonnet):✅ 通过 — 零 Critical/零 Important/零 Minor。** 程序化逐字节比对 7 个代码围栏全部通过;冒烟实测(独立重跑 + 5 条依赖链抽测全绿);约束全过(无中文 bytes/无 do()/唯一变更文件 mtime 佐证/__all__ 与 main() 未动);报告行号引用与磁盘精确一致;RED 失败点/根因/类型与简报一致。
- **已知偏离判定**:① RED 编排偏差 = **plan defect,合理**——简报 Step 1 冒烟块本身依赖 ① imports 才可运行到预期失败点(不导入 VariableTree 则 RED 先行落在导入缺失),Step 1/2/3 排序自相矛盾;实施者将 imports(测试载体)与块替换同一步应用,使 RED 精确呈现简报文档化失败根因,红绿纪律完整成立,无需修改。② docstring 过时 + `PlaceholderManagementTree` 未引用保留 = 可接受(简报五处未含,按不顺手重构约束保留正确;装饰性,终审可收尾)。
- Task 7: minor (deferred) 0 条新;实施者观察项 2 条(模块 docstring 仍描述占位时代状态;PlaceholderManagementTree 类保留未引用)——终审分诊。
- **Task 7: 完成。** 全部 7 个任务实施 + 评审闭环;进入终审(opus 全分支评审 + deferred minors 分诊 + Rulings 汇总)。

## 终审(opus,2026-08-29)

- **验证**:通读 7 文件全文 + 计划/spec/ledger/评审包;独立重跑 8 条冒烟全绿(集成冒烟 + 6 模块 + main --check);grep 验证(无 do() 调用/无 Ctrl 快捷键/Placeholder 无引用)。
- **Assessment: With fixes** — 零 Critical;**2 条 Important(全分支新发现)** + 1 条 Minor(接受即可):
  - **I-1(plan defect)卡片 io 编辑不触发保存** — step_card.py:90-104 / step_list_view.py:127,318,336,349 / main_widget.py:290-292。textChanged 钩子与 picker 包装只调 refresh() 改色,不发出「内容已改」;edited 仅在 添加/粘贴/删除 三处发出 → 用户在卡片改 io 后关闭应用(无 closeEvent 自动保存)或 Ctrl+O 切换工程时改动静默丢失,与变量管理树「确认即写盘」不一致。spec §5 edited 契约与实现不符(plan defect)。修法(终审建议):StepCard 加 `io_changed = pyqtSignal()`,textChanged 钩子与 picker 包装值落地后发出;StepListView.refresh 建卡时 `card.io_changed.connect(self.edited)` 复用 _save_store 链路;成本低无接口破坏。
  - **I-2 picker 包装器链式累积(内存缓慢泄漏)** — step_card.py:96-103。每次建卡包一层,`io.picker → wrapperN → … → wrapper1 → card1` 链;视图重建(`set_list`/添加/删除/粘贴都 refresh)每步加环,旧卡唯一存活引用就是这条链 → 卡片控件树永久滞留,且每次 picker 点击触发链上所有旧卡延迟 refresh()(无害空耗)。修法(终审建议):扁平化——`orig = getattr(step.io.picker, "_kscript_orig", step.io.picker)`,包装器挂 `_kscript_orig`;旧包装器替换后即无引用。与 T3 冒烟「构造前替换 fake_picker」兼容(getattr 天然兼容)。
  - M-1:refresh() 只 `_anims.clear()` 不 stop() 运行中动画 — 接受即可。
- **Deferred 分诊表**(ledger 实记 16 条):【修】1 条 = T7-① 模块 docstring 过时(main_widget.py:10-12,3 行文档改写零成本);【接受】13 条(T1-①、T2-②、T3-①②、T4-①②③④、T5-①②、T6-①②、T7-②);【已过时】2 条(T2-① PEP 649 使 future import 冗余;T5-③ 已被 T7 集成冒烟覆盖)。
- **Rulings 汇总**(面向用户):①T5 多选剪切数据丢失修复(复制/剪切限单选 + 守卫 + 冒烟);②T3 picker 延迟重检;③T4 两处实施偏离必要(encode/QWheelEvent 8 参);④T5 两处偏离必要(QtGui QKeySequence/顶层顺序期望);⑤T6/T7 RED 编排偏离均属计划缺陷可接受。
- **行动**:一次修复派发(I-1 + I-2 + docstring)→ scoped re-review(sonnet)。

## 终审修复 fix-1(完成,2026-08-29)

- 实施者状态:**DONE_WITH_CONCERNS** — 三条修复各经 RED→GREEN(AttributeError io_changed / AssertionError 链计数 0);全量回归 17/17 全绿;T3 picker 冒烟原样通过。
- 交付(4 文件):step_card.py(`io_changed` L66 + 弱引用钩子 L50-59/104-110 + 扁平化 L111-122 + `_io_edited` L142-149 + 冒烟 L290-307);step_list_view.py(L180 建卡连接 + 冒烟 L516-527);**越界** step_io_widget.py(L279-300 `_live_widgets` C++ 存活过滤);main_widget.py(docstring L9-14)。
- **阻塞性既有潜伏缺陷(实施中 TDD 发现并修)**:视图重建后对卡片输入 → `RuntimeError: wrapped C/C++ object has been deleted`(shiboken 包装器滞留,`_live_widgets` 弱引用照常解析无法过滤)+ `io._widgets` 无限累积;修复 = `_live_widgets` objectName() 探活过滤 + 清理登记表(step_io_widget.py,越界最小外科修改,无签名变化)+ textChanged 钩子弱引用化(切断字段→槽→卡片自引用环)。
- **re-review(sonnet):✅ All findings addressed** — I-1 信号时机(仅真实 textChanged + picker 延迟;change_value input blockSignals 不误发)、保存链路闭环(io_changed → edited → _save_store)核实;I-2 扁平化 + T3 fake_picker 兼容成立;越界 `_live_widgets` **独立实验证实为硬前提**(monkeypatch 旧语义 → 真实重建场景必崩 RuntimeError,新语义干净);弱引用钩子无自引用环;docstring 与实际装配一致;concern ① 双发(output 异值 = 同步 2 + 延迟 1,保存幂等)与 ② 极端时序(实测不崩)均接受。
- 新 Minor(非代码缺陷,接受):报告 §7 「change_value 不误发」仅对 input 成立——output `_refresh_output_field`(L374-375)不 blockSignals → `change_value("output", 异值)` 发 1 次 io_changed;应用运行期 main_widget 不调 change_value、保存幂等 → 无功能影响;可选收紧(加 blockSignals)非必需,不动(避免影响既有 step_io_widget 行为)。
- **fix-1: 完成。** 终审 2 条 Important + docstring 全部关闭;计划全部任务闭环。

## 用户新需求(2026-08-29,裁定已录)

- **优化 1**:进入工程第一画面时自动显示步骤列表树中第一个步骤列表(卡片 + 树中选中;空 store 保持占位页)。
- **优化 2**:右键步骤列表树可创建空步骤列表(与「添加步骤列表」一致的 4 位置子菜单:头部/尾部/前方/后方;命名复用 `_dedup_name` 去重)。
- 任务 #41/#42 已建;待 fix-1 re-review 关闭后派发(sonnet)。

## Task 8(完成,2026-08-29)—— 用户优化 1 + 2

- 实施者状态:**DONE** — 两条优化各 TDD(RED AttributeError first_list_path / _act_new_empty_list → GREEN);全量回归 17/17 全绿;T7 空 store 占位断言与 T5 全部断言原样通过。
- 交付:
  - **优化 1**(进入工程自动显示第一个列表):`StepListTreeWidget.first_list_path()`(:136-155,复用 `_children_of` 排序逻辑 DFS 先组后叶 = 树显示序;`walk()` 插入序 ≠ 显示序)+ `_open_package` 接线(:689-698,先构建树+宿主再 setCurrentItem → 既有 currentItemChanged → list_selected → 宿主链路;空 store → None → no-op 占位不变)。冒烟(main_widget :834-866):tmp2 含列表工程,「组甲/丙」显示序首个(≠ walk 首位「乙」)、宿主 currentIndex()==1、卡片 1 张、`_current`/`_step_list` 同一性。
  - **优化 2**(右键新建空列表):菜单子菜单「新建空列表」= 头部/尾部 + 分隔 + 前方/后方(:210-246,前方/后方仅右键列表叶子可用);`_act_new_empty_list`(:307-329,`_dedup_name` 同父去重 + `StepList.create_empty()` + 重建父 dict 定位插入 + `_changed(full)` 收尾)+ `_sibling_index`(:331-342)。冒烟(:631-668)4 位置 walk 序精确断言 + 去重(1)(2)(3)/根层不去重 + changes4==5。
- **前提修正(评审判定忠实且合理)**:树上原无「添加步骤列表」4 位置菜单(该模式在 step_list_view.py 为步骤级:头部=_add_step(0)/尾部=哨兵 -1/前方/后方=卡片下标);实施者映射 头部=0 / 尾部=None(追加,同 add_list)/ 前方=锚下标 / 后方=锚+1,语义完全同构,子菜单分隔线镜像视图两段形态。用户裁定「与添加一致」基于控制器错误前提,修正系任务约束下唯一合理路径。
- **任务评审(sonnet):✅ 通过 — 零 Critical/零 Important;3 条 Informational。** 位置语义 = store 字典序(树显示恒按名排序下唯一自洽解读——按显示行定位则 refresh 排序后位置即消失;walk/执行序与 all_do_methods/JSON 序一致才有持久语义,plan defect 已合理消解);`store._root` 直访可接受(既有私有属性、model 文件零改动、dict 原地变更引用一致);懒构建接线正确且必要(`_on_list_selected` 仅当 `_host is not None` 才显示——不先 preview_widget 则只记 _current 不切页);`_sibling_index` 父层计数与 dict 重建下标对齐(含子组混排)经手工推演 5 次创建全部吻合;约束全过(model/step_list_store.py 零改动、无 do()、中文注释、无重构);独立重跑两冒烟全绿。
- Task 8: minor (deferred) 0 条;informational 3 条(报告行号漂移 :835-871 vs 实际 :834-866;位置语义解读已文档化;前方/后方仅叶子可扩展)。
- **Task 8: 完成。** 全部工作闭环:7 任务 + 终审修复 fix-1 + 用户优化 1/2;终审(opus)2 条 Important 已关闭;workspace 保留(非 git 裁定);计划关闭。

## 用户需求 3(完成,2026-08-29)—— 默认管理树 = 步骤列表树

- 改动:main_widget.py `_open_package` 末尾 `set_current_row(0)`(资源树)→ `set_current_row(2)`(步骤列表管理树,`_managers` 第 3 位)+ 注释;冒烟断言追加(win 构造后 `_switcher._buttons[2].isChecked()`,RED AssertionError → GREEN)。
- 验证:inline TDD(先加断言 RED → 改一行 → GREEN);全量 17/17 回归全绿。
- 说明:切换仅影响左侧管理树默认显示;进入工程自动选中第一个列表的接线(优化 1)与之正交,顺序无依赖(自动选中在 set_current_row 之前执行,宿主已就绪)。

## 用户需求 4(完成,2026-08-29)—— 左侧管理树排序:步骤列表 / 全局变量 / 步骤模板 / 资源

- 改动(main_widget.py):`_managers` 顺序 `[Resource, Variable, StepList, Step]` → `[StepList, Variable, Step, Resource]`(注释「左侧管理树排序(从上到下)」);接线索引 `sl_mgr = _managers[2]` → `[0]`(`var_mgr = [1]` 不变);默认行 `set_current_row(2)` → `set_current_row(0)`;冒烟断言三处索引同步(第 1 位 StepListManagementTree / 切换栏第 1 位高亮 / tmp2 同)。
- 验证:inline TDD(RED AssertionError isinstance → GREEN `MainWindow smoke OK`);全量 17/17 回归全绿。
- 说明:顺序只影响左侧切换栏显示与默认位;自动选中第一个列表、共享树接线均按新索引重绑,断言钉住。

## 用户 Bug 修复(完成,2026-08-29)—— 悬停放大动画结束后再次悬停崩溃

- 现象:创建步骤后鼠标移到步骤上,卡片放大(1.06 倍动画),随后动鼠标即报 `RuntimeError: wrapped C/C++ object has been deleted`(用户贴出 traceback,崩点 `_animate_scale` 的 `old.stop()`)。
- 根因(step_list_view.py `_animate_scale`):动画 `finished → deleteLater` 销毁 C++ 对象,但 `self._anims[idx]` 残留 Python 包装器;下次 Enter/Leave → `pop` 出死动画 → `old.stop()` → RuntimeError。同类隐患:`refresh()` 只 `clear()` 字典不 stop 动画,播放中重建时动画会 setScale 已删除的旧 proxy。
- 修复:① `finished` 连接在 `deleteLater` 前同步 `self._anims.pop(i, None)`(结束不留尸)② `refresh()` 开头先 `anim.stop()` 再 `clear()`。
- 验证:TDD(RED:冒烟断言 `0 not in aview._anims` AssertionError → GREEN `StepListView smoke OK`);全量 17/17 回归全绿。

## 用户优化 5+6(完成,2026-08-29)—— 卡片圆角/居左 + 变量弹窗不被遮挡

- 优化 5:① 圆角样式已有(step_card `border-radius:10px`),冒烟补断言钉住;② 卡片排列默认不居中 → `StepListView.__init__` 加 `setAlignment(Qt.AlignLeft | Qt.AlignVCenter)`(QGraphicsView 默认 AlignCenter,内容不足时整排居中)。
- 优化 6:变量选择弹窗被其他卡片遮挡 → 根因:卡片在 QGraphicsView 场景(QGraphicsProxyWidget)中,`QDialog(parent=卡片内控件)` 被 proxy 内嵌渲染 → `_default_picker` 改 `QDialog(None)` 顶层窗口(唯一弹窗入口,grep 确认)。应用模态 exec_ 行为不变。
- 验证:两项各 inline TDD(RED AssertionError → GREEN);全量 17/17 回归全绿。

## 用户优化 7(完成,2026-08-29)—— 5 项:命名窗/毛玻璃卡片/动态尺寸/图标/隐藏?

1. **新建空列表先弹命名窗**:`_act_new_empty_list` 弹 QInputDialog(默认建议名「新列表」),确认后创建;取消/空名(警告)不创建;重名沿用同父去重。冒烟:patch getText 自定义名/取消/空名三场景 + 既有 4 位置断言包 patch。
2. **卡片毛玻璃 + 圆角 + 阴影 + 柔和色,样式入 view\**:新建 `view/cards.qss`(静态规则 + 属性选择器 valid/state/enabled/selected,io 非法红优先、选中蓝、未激活虚线均在文件内级联);`step_card._update_style` 改为 setProperty + unpolish/polish;阴影 = QGraphicsDropShadowEffect(blur 28,offset(0,4),Qt QSS 不支持 box-shadow);删除硬编码颜色常量。冒烟改为属性断言 + QSS 文件断言 + 阴影断言。
3. **窗口 2/3 屏 + 卡片随屏幕动态**:`main_widget._window_size()`(光标所在屏 availableGeometry 2/3;landing 与工程视图统一);`step_card.card_size_for_screen()`(1080p 基准 240×340,宽=屏宽×0.125/高=屏高×0.315,clamp 180/260);sceneRect 高度 = 卡片高 + 60。
4. **图标**:设计 = 蓝紫渐变圆角底 + 三张半透明白层叠卡(呼应毛玻璃卡片)+ 柔和绿播放三角(执行语义);`icon/make_icon.py` 生成 `icon/kscript.ico`(16-256 七尺寸 PNG-in-ICO)+ `kscript.png` + `kscript.svg`;main() 里 `app.setWindowIcon` 全局应用(所有弹窗继承)。冒烟:文件存在 + QIcon 非空。
5. **弹窗右上角无 ? 按钮**:main() 里 `app.setAttribute(Qt.AA_DisableWindowContextHelpButton, True)` 全局禁用(一处生效所有弹窗)。冒烟:属性枚举存在断言。

- 验证:各项 inline TDD(属性断言/文件存在断言 RED→GREEN);全量 17/17 回归全绿。

## Bug 修复(完成,2026-08-29)—— 卡片白屏 + 右键删除 ValueError

- 现象(用户报告):创建步骤后看不到任何卡片(一片白,鼠标点击有反应);右击删除步骤报 `ValueError: list.index(x): x not in list`(崩点 `_card_menu: idx = self._cards.index(card)`)。
- 根因①(白屏):`StepCard.__init__` 挂 `QGraphicsDropShadowEffect` → QGraphicsProxyWidget(或其内嵌 widget)带 QGraphicsEffect 时整体渲染白屏(Qt 5.15 Windows 纹理化 bug,离屏 render 与真实窗口皆然;实验:带 effect 非白采样 0,去掉后 6752)。
- 根因②(幽灵 proxy):`refresh()` 只清 Python 列表 `_proxies=[]`/`_cards=[]`,**从不 `scene.removeItem`** —— 旧 proxy 的 C++ 对象永久残留场景,每次 refresh 叠加一层(复现:冒烟流程累积 31 个 proxy vs 6 张卡)。旧卡被新卡同位置完全盖住,以前视觉/命中都不暴露;白屏后旧卡反而成为唯一可点目标 → 右键命中幽灵卡 → `_cards.index` ValueError。
- 修复:① `step_card` 删除 QGraphicsDropShadowEffect(含导入);② `step_list_view.refresh()` 重建前 `removeItem` 全部旧阴影与旧 proxy;③ 阴影改场景层 `_CardShadowItem`(QGraphicsItem,paint 多层半透明圆角矩形由内到外 26/18/12/7 alpha 近似模糊,偏移 (0,4),z=-1 垫底,随卡片生命周期统一管理)。
- 验证:TDD RED(GREEN 前断言失败:step_card `graphicsEffect() is None` AssertionError;step_list_view 幽灵计数 `(31, 6)` AssertionError)→ GREEN;用户场景脚本:`[添加1]` 非白 0→6322、`[添加2]` proxies=2=_cards=2 一致=True、右键 `_cards.index` 不再抛 ValueError;全量 17/17 回归全绿。

## 用户优化 8(完成,2026-08-29)—— 4 项:删除后显示下一个 / 卡片菜单在鼠标处 / 空列表提示 / 树菜单重设计

1. **删除列表后显示下一个**:`step_list_tree_widget._act_delete` 删除后调 `_pick_next(before, tops)` —— 被删项之后第一个仍存在的列表,无则之前最后一个,再无则第一个;`before` = 删除前 walk 序(显示序 = 执行序)。删组视其子树全删。冒烟:删中间→丙、删末尾→甲、删唯一→""。
2. **卡片右键菜单弹在鼠标处**:`step_list_view._on_context_menu` 传 `viewport().mapToGlobal(pos)` 给 `_card_menu`(QMenu.exec_ 要全局坐标;原直接 exec_ 局部坐标 → 视图左上角弹出)。StepCard.contextMenuEvent 已传全局坐标,信号路径原样透传。冒烟 J-3(见下方打桩谜)。
3. **空列表提示居中 + 22 号宋体**:`set_list` 空列表 → scene 加 `addSimpleText("右键添加步骤…")`,`setFont(QFont("SimSun", 22))`,`_center_hint()` 按 viewport 中心 mapToScene 定位;`resizeEvent` 同步重居中。冒烟 J-4:字体/坐标断言 + resize 后二次断言。
4. **树右键菜单重设计 + 修复插入位置**:
   - 根因:树显示按名排序(`_children_of` 排序),而插入/执行按 walk 序(字典插入序)→ 用户「第一下正确、第二下跑偏」(内容增多后排序序 ≠ 插入序);「后方创建却生成在第一个位置」同根因。
   - 修复:`_children_of` 改 walk 序(不排序、不组前列表后)→ 树显示序 = 创建序 = 执行序(`all_do_methods`)。
   - 菜单:空白右击 =「头部添加步骤…|尾部添加步骤…」(所在层首/末位);列表右击额外「在此列表前添加…|在此列表后添加…」(锚的兄弟序下标前/后);原「新建空列表」子菜单(头部/尾部/前方/后方)删除。冒烟:空白/列表菜单文本断言 + 点击「在此列表前添加…」→ walk == ["甲","新列表","乙"];用户 bug 场景(头部两次创建、尾部创建)断言 walk 序与 topLevelItem 显示序一致。

### 调试记录:python -m 冒烟中 QMenu 打桩失效之谜(已解)

- 现象:冒烟 `_vmod.QMenu = _MenuRec2`(子类记录 exec_ 坐标)替换后仍弹真 QMenu 挂起;独立脚本 `_t_menu4.py` 同样替换却生效。
- 根因(探针 `_t_probe.py` 证实):`python -m pkg.mod` 时 runpy 先用模块名 import 一次(sys.modules 条目 = 模块对象 A),再以 `__main__` 名把同一段代码 exec 进**临时模块对象 B**;`import pkg.mod as _vmod` 返回 A,而运行中的函数 `__globals__` 是 B.__dict__ → 替换 A 不生效。探针输出:`me is sys.modules['__main__']: False`、`globals dict same: False`、替换后调用仍返回 "real"。
- 修复:冒烟内直接 `globals()["QMenu"] = _MenuRec2`(运行中模块的 dict 就是 B.__dict__),finally 恢复 `_orig_qmenu`。step_list_view J-3 与 step_list_tree_widget 菜单结构测试同法。用户此前看到的「上下文窗口一直显示,点复制报错」即真菜单阻塞所致,属调试打桩失效,非产品缺陷。
- 验证:全量 19/19 回归全绿。

## 用户优化 9(完成,2026-08-29)—— 2 项:卡片错误原因 / 视图最小高度

1. **卡片错误 → 卡片外正下方错误原因**:`StepIOWidget.error_reasons()` 新增 —— 按输入槽→输出槽顺序收集不合规短语:输入空/资源类未选 →「输入参数为空」;引用变量不存在 →「变量不存在: 名」;类型不符 →「名 类型不符」;常量解析失败 →「无法解析为 number」;输出空 →「输出变量未指定」;输出变量不存在 →「变量不存在: 名」。视图 `StepListView` 每卡一个 `QGraphicsSimpleTextItem` 标签(字典 `_error_labels`,键=卡):文本「⚠: 原因1, 原因2」,SimSun 12 错误红,卡片正下方居中(y = 卡底 + 4)。刷新点三处:refresh 重建(初始)、io 编辑(输入字段真实 textChanged → 单卡同步,lambda 持卡防旧卡)、refresh_validity(变量树变化)。输出字段只读(只能 picker 选),输出变化走数据层 + 重检路径。
2. **视图最小高度 ≥ 卡片放大后高度**:场景高 = 卡高 × 1.06(悬停中心放大,上下各 3%)+ 60;`setMinimumHeight(round(卡高 × 1.06 + 60))` 随 refresh 动态(窗口/布局压缩不裁剪放大卡片,4K 680 高卡也完整);空列表 → 最小高度归零。

- TDD:error_reasons K-1(9 场景 RED AttributeError → GREEN);视图 J-5(标签文本/位置/实时同步/修复移除/无幽灵)、J-6(最小高度/场景高/空列表归零);I-3 场景高断言改 ×1.06。
- 坑①:J-5 首版断言失败 —— 冒烟菜单添加/粘贴的步骤 io 本就为空(标签确实该有),需先补全 io;坑②:输出字段 QLineEdit 只读,setText 不写回数据 → 测试改走 change_value + refresh_validity。
- 验证:全量 19/19 回归全绿。

## 用户优化 10(完成,2026-08-29)—— 4 项:卡片序号 / tag 属性 / 签名编辑+工具条 / 组创建位置(+JSON 顺序)

1. **卡片正上方序号 (n/总数)**:视图每卡一个 `QGraphicsSimpleTextItem` 索引标签(字典 `_index_labels`,与 `_error_labels` 同模式,refresh 全清重建):文本 `"(n/total)"`,SimSun 12、色 (110,110,135),卡片正上方居中(y = 卡顶 - 标签高 - 4)。卡片布局 y=30 常量:顶部为序号标签留空、并给悬停放大留顶部余量。
2. **Step 基类 tag 属性**:`actions/base.py` —— `__init__(io, enabled=True, tag="")` 存 `self.tag`;`to_format_string` 加 `"tag"`,`from_format_string` 读 `obj.get("tag", "")`(旧格式兼容 → "")`;`_decode` 校验非 str → ValueError。冒烟:默认空串/构造指定/往返/legacy/非 str 拒绝。
3. **卡片签名编辑 + 视图工具条**:
   - 卡片顶行 = 激活按钮 + 步骤名 + `QLineEdit#cardTag`(placeholder「签名…」,textChanged → 写回 `step.tag` + `io_changed` 保存链路;refresh 用 blockSignals 同步控件不重复保存)。QSS `#cardTag`:12px、未聚焦半透明融入卡片,`:focus` 白底蓝边。
   - 视图栏下方工具条 `#viewToolbar`(浅底 + 下边框):序号框 +「定位」按钮(returnPressed 同款)→ `jump_to_index(n)`(越界/非数 → 状态提示「序号需为数字」「序号越界(1-total)」;`ensureVisible` + 选中 + 「已定位 n/total」);关键词框 +「搜索」按钮 → `locate_by_tag(text)`(当前选中卡之后循环搜「text in tag」,命中 jump_to_index;无命中 →「未找到匹配标签」)。状态文本在 `_toolbar_status`。
4. **组创建支持头尾/前后位置**:
   - `_insert_node(node, name, value, index)` 静态方法:walk 序(= 显示序 = 执行序)下标 index 处插入(None/越界 → 尾部;store 无插入 API → items 重建定位);`_act_new_empty_list` 一并复用。
   - `_act_add_group(context_group="", index=None)`:组名校验(空/'/'.'/'..' → 警告)+ 已存在(`store.get` 成功)→ 警告「无法添加:已存在」;位置:菜单「头部添加组…」(index 0)/「尾部添加组…」(None),右击组时额外「在此组前/后添加…」(锚的父组 + sibling_index 前/后)。
   - 分发顺序关键:先 `a_group_head/tail`(action None 时与它们比,None is None 陷阱由「先验锚非 None」兜底,组分支按 `a_group_before is not None and action is a_group_before` 书写)。
   - 坑①:嵌套树下 `visualItemRect` 对未展开子项返回 (0,0,0,0) → 冒烟先 `expandAll()`。
   - 坑②(真产品 bug):右击组时 `context_group = _group_of(item)` 返回组自身 →「在此组前添加…」把新组建进锚组**内部**;修复:before/after 分支显式取 `p.rsplit("/",1)[0]`(锚的父组)作 context_group。列表版无此问题(anchor 恒为叶子)。
5. **JSON 顺序保留(用户提问)**:保留。`to_json_bytes`/`from_json` 均按 dict items 插入顺序遍历,`json.dumps` 不 sort_keys → JSON 键顺序即顺序载体;往返冒烟断言 `to_json_bytes() == 原始字节` 已证明保序;树显示序 = 创建序 = 执行序 = JSON 键序(四者同源)。

- TDD:tag K-1(默认/往返/legacy/非法);卡片 K-2(编辑写回+保存信号、外部变更同步不重复触发);视图 J-7(索引标签文本/位置、y≥0)、J-8(jump 边界、locate 命中+循环);工具条(状态文本);树菜单结构断言(空白/列表/组三种)+ 点击「在此组前添加…」→ walk == [组甲, 组甲/列表1, 组甲/新组1, 组甲/组乙] + 头部两次/尾部/组内头部/重名拒绝 + 列表回归。
- 验证:全量 19/19 回归全绿(actions.base + 7 model + 11 widgets 冒烟;main/demo_resource_tree 为真实 GUI 入口非冒烟模块)。

## 用户优化 11(完成,2026-08-29)—— 2 项:卡片标签移出放大遮挡区 / 工具条错误卡片统计+跳转

1. **卡片外上下提示不被放大卡片遮挡**:
   - 根因:悬停放大是中心缩放(1.06 倍),上下各扩出 pad = 3% 卡高;而序号/错误标签只离卡边 4px → 放大后卡片直接盖住标签。
   - 修复(step_list_view):标签固定在「放大后的卡边」之外 —— 序号标签 y = 卡顶 − pad − 标签高 − 4,错误标签 y = 卡底 + pad + 4(不随缩放移动,放大卡边永远够不到);卡片 y 抬高 = pad + 标签槽 + 场景边距(round),场景高 = 卡顶留白 + 卡片 + pad + 标签槽 + 边距,视图最小高度同步 —— 标签完整落于场景内、不裁出顶部/底部。
   - 坑:`_LABEL_SLOT` 常量 20 低估实际行高 —— SimSun 12pt 在 Windows 下 QGraphicsSimpleTextItem 实测行高 32、宽 225;改用 `_label_slot() = QFontMetrics(QFont("SimSun", 12)).height() + 4` 动态计算(与场景文本同度量),顶底同槽。
   - 坑:`refresh` 中 pad 不能用 `_cards[0]`(循环前为空)→ 用 `card_size_for_screen()[1]`。
2. **工具条第二行:错误卡片信息 + 跳转**:
   - `StepListView` 新增 `errors_changed(int)` 信号(计数 = io 校验失败的卡数,与错误标签同判据),三处刷新路径全部发射:refresh(重建)/refresh_validity(重检)/单卡编辑(_update_error_label);新增 `error_card_indices()`(1 起序号)与 `jump_to_error()`(从当前选中之后循环定位下一张坏卡,仿 locate_by_tag)。
   - 宿主 `_build_toolbar` 改两行 QVBoxLayout:第二行 = 「错误卡片: N」(红色,经 errors_changed 同步)+「跳转错误」按钮(`_on_jump_error` → 状态「已定位错误卡片」/「无错误卡片」)。
   - 探针结论(发射语义):`change_value("input")` 不发射(输入字段 blockSignals 包裹);`change_value("output")` 经只读输出框 setText(无 blockSignals)触发单卡编辑路径发计数 → 冒烟统一在显式 refresh_validity 后断言 counts[-1],不依赖隐式路径。
- TDD:J-9(计数随重建/编辑/重检同步、indices、单卡循环跳转、修好归零)、J-10(置 _SCALE_MAX 后序号标签底 ≤ 放大卡顶 − 2、错误标签顶 ≥ 放大卡底 + 2、标签完整在场景内);I-3/J-6 场景高/最小高公式更新(round(pad+slot+8) + h + pad + slot + 8);宿主冒烟(初始 0 → 弄坏 → 1 + 跳转定位 → 修好 → 0 + 无卡可跳)。
- 验证:全量 19/19 回归全绿。

## 优化 12:列表右击补「在此前/后添加组」(用户 bug 修复)

- **症状**:右击步骤列表,上下文中没有「在此前添加组|在此后添加组」——优化 10 只给了组自身的前/后,列表只给空列表前/后,组新建缺少列表锚定。
- **修复**(step_list_tree_widget._on_context_menu):组选项改三态——右击组 →「在此组前/后添加…」;右击列表 →「在此前/后添加组…」(锚定列表的兄弟位置,分发复用 a_group_before/after,锚 = 列表路径的父组 + `_sibling_index(锚)`);空白 → 只有头/尾。
- **TDD**:冒烟补菜单文本断言(列表右击含两个新选项)+ 点击测试:在「乙」前插「新列表」→ 再点「在此前添加组…」→ 断言 [甲, 新列表, 前组, 乙]。
- **坑(冒烟复现暴露,产品逻辑本身正确)**:第二次右击必须**重新** `_find_item("乙")` 取新 visualItemRect 中心——第一次插入后 QTreeWidget 即使 refresh 回调为空也重算布局,旧 pos 的 itemAt 命中「新列表」行,`_sibling_index` 算到 1、组被插到错误位置。探针:walk2 = [甲, 前组, 新列表, 乙] + itemAt(旧pos)='前组' 确认。
- 验证:树冒烟全绿 + 全量 19/19 回归全绿。

## 优化 13:签名 14 号宋体 + 共享模板工厂 + 树错误红加粗 + 最小尺寸标签遮挡修复

1. **卡片签名放大**:view/cards.qss `#cardTag` 加 `font-family: "SimSun"; font-size: 14px`(原 12px 无字体族);冒烟正则断言规则内含 SimSun + 14px。
2. **「步骤模板加载完成」双日志(用户问是否正常)**:非正常——MainWindow._open_package 自建 mgr,StepTreeWidget/StepListManagementTree 各自再自建 mgr,每份各自 load 打一条。修复:open_package 建一份 `shared_mgr` 加载一次,两棵管理树构造签名加 `mgr=None` 参数(传入即复用、不重复 load/日志;None 时自建 + load 保持独立可用)。冒烟:共享后 LogModel 清空再建树 → 无新日志。
3. **树错误标记**:StepListTreeWidget.refresh_error_marks()——walk 找 io 非法的列表(`any(not s.io.is_valid)`),其路径与各级祖先组红加粗(QColor(200,50,40) + bold),合规恢复 palette().text();refresh() 末尾自动调用;宿主链路:StepListView.errors_changed → _StepListHost.errors_changed(新转发信号)→ StepListManagementTree._refresh_tree_marks(判空)→ refresh_error_marks。
   - 坑:冒烟断言把「组A/好组」(坏列表的兄弟)误当祖先链——祖先链 = 沿 rsplit 向上,兄弟不在内;实现正确,修断言。
   - 坑:main_widget 冒烟树在 937 行构建时 store 为空,950 行 add_list 走 API 直改不触发树重建 → `_find_item("主列表")` 为 None;补 `tw.refresh()`。
4. **最小尺寸下错误标签被遮挡**(step_list_view):
   - 根因①:setMinimumHeight 只按 scene 高,缺视口外占用(frame 边框×2 + 水平滚动条高)→ 最小时视口比场景矮,底部标签被切。新增 `_viewport_overhead()` 补齐。
   - 根因②(字形 fallback 撑行高):_label_slot 用 QFontMetrics(QFont("SimSun",12)).height()=24,但含「⚠」(U+26A0,SimSun 无此字形 → 自动字体回退)的真实行高 32 → 标签底超场景 1px。探针文本必须与真实错误标签同内容「⚠: 样例文本」→ 32+4。
   - 根因③:错误标签文本可宽于卡片且居中 → 左右都可能溢出场景;`_fit_scene_width` 同时跟踪左/右端(label 左 −8 / 右 +8),_set_error_label 后调用。
   - 坑:冒烟未显示 widget 的 viewport 几何不随 resize 更新(QAbstractScrollArea 布局需事件循环)→ show + processEvents + 显式 _center_hint;多卡水平滚动残留(value=12)致第二卡标签不在视口 → J-6b 用单卡坏列表。
- TDD:step_list_tree_widget 冒烟(坏列表 + 祖先组红加粗、兄弟/合规不标、修复恢复默认)、main_widget 冒烟(弄坏卡片 → 树条目红加粗 → 修好恢复)、step_card 冒烟(QSS 正则)、step_list_view 冒烟(J-6b 视口内断言 + 最小高公式)、step_tree_widget 冒烟(共享无重复日志)。
- 验证:全量 19/19 回归全绿。

## 优化 14:卡片多选复制 + 工具栏合并文件菜单(含另存为)

1. **卡片多选复制**(step_list_view):
   - 交互:普通左键点击 = 单选(清多选);Ctrl+左键点击 = 加选/减选(点击序列表 `_multi`,恒含主选中 `_selected`);右键按下不改变选择(交给 contextMenuEvent)——右键处理在 `_card_menu`:右键卡已在多选集 → 保持多选,否则单选。
   - 菜单多选态(>1 张):只留「复制」,添加前/后、剪切、粘贴、删除全部禁用——多选无单卡锚点,位置/整批操作语义不明;禁用覆盖在设置默认可用性之后(粘贴默认可用性 = 剪贴板非空)。
   - `_copy_selected()`:按卡片显示序收集选中卡 `to_format_string` → 剪贴板(多张);粘贴复用 `insert_format_strings`(天然支持多条)。**跨列表粘贴零改动**:剪贴板全局存活 + 当前列表可插任意格式串 → 切到目标列表视图右键粘贴即跨列表(与树无关,按用户要求不加树入口)。
   - 坑:eventFilter 原把所有 MouseButtonPress(含右键)都走 `_select` → Ctrl 加选后右键会清空多选;加 `event.button() == Qt.LeftButton` 分流。
   - TDD:冒烟加选/减选/单选/事件过滤器三种按钮路径、菜单多选态禁用断言(类级 QMenu 替换 _MenuRec3)、多选复制序、粘贴多条、跨列表粘贴。
2. **工具栏文件菜单**(main_widget):
   - 新建/打开/保存三个平铺 QAction 合并到「文件」QToolButton 下拉(QMenu,仿「管理/窗口」InstantPopup 先例),新增「另存为…」;快捷键挂菜单项:新建 Ctrl+N / 打开 Ctrl+O / 保存 Ctrl+S / 另存为 Ctrl+Shift+S。
   - `_on_save` 重构:有路径直接写,无路径(新建工程)→ 同另存为弹窗;`_on_save_as` 总弹窗;共用 `_save_to(path)`(写盘 + `_kscp_path`/标题更新)。
   - TDD:冒烟断言菜单项序与四快捷键、「文件」按钮唯一、另存为弹窗路径 → 新文件写出 + 路径/标题切换 + 原文件不动、另存为后保存不再弹窗。
- 验证:全量 19/19 回归全绿。

## 优化 14b:签名 14 号宋体未生效的真相——单位语义 px vs pt

- **症状**:用户再次提出「签名字体 14 号宋体」(优化 13 已做 14px)——不是没做,是没看到变化。
- **根因(双坑)**:
  1. **QSS 单位语义**:用户「14号」= 14pt(中文字号惯例);优化 13 做成 `font-size: 14px` ≈ 10.5pt,比原 12px 视觉仅大 2px(行高 14 vs 12),几乎无感 → 用户以为没生效。
  2. **未显示控件样式假象**:探针在未显示卡片上读 `_tag_edit.font()` 返回 9pt/SimSun——初判「QSS 未应用」;二分实验(K:构造→读(-1)→processEvents→读(14))证明 QSS 一直生效,只是样式应用延迟到 ensurePolished/显示时机(未显示 + 未访问属性时返回默认字体;card.show() + processEvents 后 font 即为 QSS 值)。**教训:探 QSS 必须 show + processEvents**。
- **修复**:cards.qss `#cardTag font-size: 14px` → `14pt`(≈19px,行高 28,视觉增幅明显);注释记录单位坑;step_card 冒烟断言同步 14px→14pt(先红后绿)。
- 验证:渲染探针 SimSun 14pt ✓ + 全量 19/19 回归全绿。

## 优化 14c:卡片 Shift+点击 范围多选

- 交互(step_list_view):Shift+点击 = 从**锚点卡**(最近一次普通/Ctrl 点击)到当前卡的范围选择,替换当前多选;连续 Shift 从同一锚点重选范围(锚点不动);Ctrl/普通点击更新锚点;右键单选也更新锚点。无锚点(失效/首操作)→ 本次回退第一张卡为锚点,**不写回**(下次 Shift 仍从第一张起)。
- `_select_shift(card)`:范围 = `_cards[锚点..当前]`(支持反向);复用多选高亮/复制链路(菜单多选态、`_copy_selected` 自动覆盖)。
- 坑:无锚点时 `_select_shift` 走回退分支而非 `_select`——锚点不更新(调试探针证实 anchor 保持 None);冒烟断言先错后正(期待 c0 写回 → 实际不写回,按实现语义修正注释与断言)。
- TDD:冒烟覆盖 锚点更新(Ctrl/普通点击)、范围正反向、连续 Shift 重选、无锚点回退、事件过滤器 Shift 路径。
- 验证:全量 19/19 回归全绿。

## 优化 14d:image 变量缩略图放大(预览与编辑)

- **症状**:图片变量在变量编辑卡的缩略图太小(252×200 恒 200 下限),用户要求放大预览与编辑。
- **根因**:VariableEditPanel 主布局 `host_lay` 上下各一个 `addStretch(1)` 把 `_editor_slot` 夹在中间——编辑区只按 sizeHint(~238)分配,面板余量被两个 stretch 平分;image 编辑器缩略图 stretch 1 吸不了编辑区外的余量 → 恒卡 `setMinimumHeight(200)`。
- **坑(探针路径陷阱)**:「先 load 后 resize/显示」时 thumb=480(假阳性,布局重算正常);「先显示后 load」(真实用户路径:窗口开着选中变量)thumb=200(真 bug)——首版冒烟断言测前者,布局未改就全绿;必须按真实路径写断言(ep.show() + resize 后 setCurrentItem 重建编辑器再量)。
- **修复**:`host_lay.addWidget(self._editor_slot, 1)` 去掉上下两个 stretch——编辑区吸收全部余量(header/状态/按钮固定),所有类型编辑器可用高度随面板缩放。
- 验证:真实路径缩略图 252×200 → 554×636(pixmap 546×409 保持宽高比),冒烟(真实路径断言)>300 + 随面板收缩同步,全量 19/19 回归全绿。

## 优化 14e:image 预览宽度跟随 + 大图遮罩随窗口 resize

- **症状**(用户三条反馈):(1) 预览窗口高度变了但宽度没变;(2) 创建 image 变量对话框里点开预览图后拉动窗口,预览窗口大小不变、画面割裂;(3) 编辑栏里拉动窗口预览尺寸不变,不合理。
- **根因(两个)**:
  1. **宽度卡 560 限宽**:`VariableEditPanel._rebuild_editor` 统一 `editor.setMaximumWidth(560)`(防输入框过宽)且 `addWidget(editor)` 无横向 stretch → image 编辑器宽度 = min(sizeHint, 560) 恒 552;14d 修复后高度随面板、宽度不动,正是「高度变了宽度没变」。创建对话框无此限宽(缩略图本就随对话框)。
  2. **遮罩一次性定位**:`ImageOverlay.show_overlay` 只在打开时 `setGeometry(p.rect())`,无任何 resize 钩子 → 宿主(编辑面板/创建对话框)被拉动后遮罩保持旧几何,盖不全、图不动,画面割裂。
- **修复**:
  1. `_rebuild_editor` 按类型分流:image → 不限宽 + `addWidget(editor, 1)`(横向同垂直一样吸收余量,缩略图随面板/窗口变化);string/number 保持 560 限宽 + 居中(原注释语义)。
  2. `ImageOverlay`:show_overlay 时 `parent.installEventFilter(self)`,`eventFilter` 响应父窗口自身 `QEvent.Resize`(且未隐藏)→ `setGeometry(parent.rect())`;close_overlay 时 `removeEventFilter`(幂等,再开重挂)。父窗口缩放/拖拽 → 遮罩同步拉伸,滚轮缩放与拖拽平移状态保留(resize 不改 view 变换)。
- **坑**:未显示宿主 `resize()` 不发 Resize 事件(冒烟首版断言直接失败)→ 冒烟必须先 `host.show()`;真实路径宿主必已显示,行为正确。
- TDD:image_overlay 冒烟追加 宿主 resize → 遮罩几何=新 rect、关闭后 resize 无副作用、再开仍跟随;variable_tree_widget 冒烟追加 宽面板缩略图 >700(修复前恒 552)、image 编辑器 maximumWidth 不限、变窄同步收缩、对话框拉宽缩略图 >w0+80。
- 验证:全量 19/19 回归全绿。

## 优化 14f:变量描述与编辑框间距过大(14d 副作用)

- **症状**:string/number 变量预览图中,「描述(字符串值：/数值：)」与输入框之间距离太远。
- **根因**:14d 让编辑区(`_editor_slot`)吸满面板余量后,编辑器(QWidget,sizePolicy Preferred)也被布局拉满(474px);其内部 QVBoxLayout 中 QLabel 垂直 Preferred → 吸收全部余量被拉成 437px(文本卡顶、下半空白),QLineEdit(Fixed)沉底 → 视觉上描述与输入框隔数百 px。
- **修复**:`_rebuild_editor` 非 image 分支对齐改 `AlignHCenter | AlignTop`——编辑器按 sizeHint 紧凑排布(474→55px),余量留在编辑区底部;image 分支(stretch 1 吸满)不受影响,14d/14e 断言原样通过。
- TDD:探针实测 修复前 label 437px/gap 视觉数百 px → 修复后 label 18px/editor 55px/gap 10px;冒烟断言 string+number 的 gap ∈ [0,20] 且 editor 高 <150,image 仍吸满(>400)防回归。
- 验证:全量 19/19 回归全绿。

## 优化 15(完成,2026-08-29)—— 列表勾选框 + 添加/粘贴子菜单重组 + 拖拽排序移动

1. **列表勾选框**(step_list_tree_widget):
   - 列表 item 图标左侧勾选框:全激活 = 勾选、全停用 = 未勾、混合 = 半选;点击切换列表内全部步骤 enabled 并保存;组无勾选框(QTreeWidgetItem 默认 flags 含 ItemIsUserCheckable,组显式 `& ~` 移除,否则显示空框)。
   - `_on_item_changed` 只改 store + `store_changed.emit()` + 回调,**不 refresh**——勾选框状态 Qt 已更新、store 已改,重建树反而有害(见调试记录)。
2. **添加/粘贴子菜单重组**:主菜单只留 复制/剪切/重命名/删除;「添加的子项」= 头部/尾部添加步骤 + (右击列表)在此列表前/后 + 头部/尾部添加组 + (右击条目)在此组前/后或在此前/后添加组;「粘贴的子项」= 粘贴到列表头/列表尾 + (右击列表)粘贴到此列表前/后。`_act_paste(context_group, index)` 支持四向:0=头、None=尾、sibling 下标=锚前、sibling+1=锚后(组粘贴 = 组节点插下标 + 子树按序进组)。
3. **拖拽排序/移动**:`InternalMove` + `dropEvent`(source is self + itemAt + dropIndicatorPosition)→ `_move_paths(paths, target_path, position)`:OnItem(组)= 组内尾,Above/Below = 同层前/后;多选拖拽 = 批量移动(保持选中序);防御:target 在移动集内 / target 是被移动项子树 / OnItem 目标是列表 → 拒绝;跨父重名 `_dedup_name` 去重。
- TDD 与调试记录(本优化的主要成本,根因三条):
  - **崩溃①(构造期 RuntimeError deleted)**:`_fill` 的 `setCheckState(PartiallyChecked)` 在非 tristate item 上被 Qt 强转为 Checked → 半选消失;且 `refresh_error_marks` 的 `setFont`/`setForeground` 走 model setData,同样发射 itemChanged——`blockSignals(False)` 在 refresh_error_marks 之前就解除 → `_on_item_changed` 读到「Checked + 混合步骤」误判状态不等 → 改 store + `_changed` → 递归 refresh → clear() 删除外层正在遍历的 item → RuntimeError。修复:列表 item 加 `Qt.ItemIsTristate`;refresh_error_marks 移入 blockSignals 范围(重建全程屏蔽,程序置入不泄漏信号)。
  - **崩溃②(点击勾选框 segfault)**:`_on_item_changed` 同步 `_changed` → refresh → clear() 在 itemChanged 分发栈上删除 item,Qt 侧 setCheckState 返回前仍引用它 → use-after-free。修复:点击处理不再 refresh(见上)。**教训:itemChanged/任何 model 信号分发栈内禁止 clear()/重建树。**
  - **断言坑×3(期望错误非实现错误)**:第二次保存回调是 append(1) → 期望 `[1,1]` 非 `[2]`(三态 item Unchecked→Checked 发两次 itemChanged,第一次状态未变被 early-return 拦截,恰好保存一次);OnItem 组 = 组内尾 → 甲拖入组后 [丙,乙,组,组/甲] 与 [组2,组2/M,组2/组1,组2/组1/L],组不提前。
- 验证:树冒烟 `StepListTreeWidget smoke OK` EXIT=0(勾选三态/点击切换/嵌套菜单结构/粘贴四向/拖拽全场景/错误标记回归)+ 全量 19/19 回归全绿。

## 用户 Bug 修复(完成,2026-08-29)—— 非激活卡片被整体禁用

- **症状**:卡片点「✗」停用后,整个卡片无法控制——hover 放大动画消失、激活按钮点击无效、无法切回激活。用户期望:非激活 = `Step.enabled=False` + 背景变灰,控件本身保持可交互。
- **根因(Qt 陷阱)**:`StepCard._update_style` 用 `setProperty("enabled", ...)` 设「动态属性」供 QSS 属性选择器匹配,但 **"enabled" 是 QWidget 的 Q_PROPERTY——QObject::setProperty 命中内置属性会调用其 setter**,等价 `setEnabled(False)`!三处调用把整卡(StepCard)、名称(QLabel)、激活按钮(QToolButton)全部真正禁用 → 不接收鼠标(点击无效/hover 动画消失),且禁用后无法再点回激活。探针确认:`w.setProperty("enabled", False)` → `w.isEnabled() == False`。
- **修复**:动态属性改名 `active`(避开内置属性;`state/valid/selected` 无同名 Q_PROPERTY,不受影响)——step_card.py `_update_style` 三处 + view/cards.qss 属性选择器四处(`StepCard[active="false"]` 虚线灰底 / `#cardName` / `#cardTag` / `#btnActive`)+ 注释记录陷阱;冒烟断言改 `property("active")` 并新增 `isEnabled()` 链断言(切换前后卡片与按钮均保持启用、按钮仍 checkable)——RED(属性为 None)→ GREEN。
- 验证:全量 19/19 回归全绿(step_list_view 动画冒烟原样通过 → hover 放大不受影响)。

## 需求三合一(完成,2026-08-29)—— 激活双向刷新 / 拖拽亮线 / 多选拖拽修复

### 优化 A:激活切换双向立刻刷新(任务 #71,完成)
- **需求**:「步骤栏左边的激活按钮切换是 视图中的步骤没有立刻刷新,请实现立刻刷新」——树勾选框停用列表后,右侧卡片画面必须立即变灰。
- **根因(单向缺失)**:树勾选 → `_on_item_changed` → `store_changed` → 宿主 `_on_store_changed` **只检查当前列表存在性(FileNotFoundError → 占位页),不重建卡片**——list_selected 只在点击树条目时触发,勾选框切换不发 → 视图永不刷新。反向(卡片激活按钮 → 树勾选框)完全没接线。
- **修复**:
  - `main_widget._on_store_changed`:else 分支 `set_list(lst, self._mgr)` 重建卡片(删除分支保留占位页);勾选/添加/粘贴/删除全部经此刷新画面。
  - `step_card._on_active_toggled`:写回 enabled 后 `refresh()` + `io_changed.emit()`(保存链路)。
  - `main_widget._on_edited`(新,包装 `_save_store`):保存 + `tree.refresh_active_marks()` 同步树勾选框;`preview_widget` 的 view 编辑回调换用它。
  - `step_list_tree_widget.refresh_active_marks`(新):遍历 items 重设勾选框聚合(与 `_fill` 一致:全激活 Checked / 全停 Unchecked / 混合 PartiallyChecked / 空 all([])→Checked);**blockSignals 包裹**——setCheckState 走 model setData 发 itemChanged,泄漏会误触 `_on_item_changed` 全量启停(与 refresh_error_marks 同坑)。
- **断言坑**:`host2._view._cards[0] is s2` 失败——`MainWindow(tmp2)` 内部从 pkg2 **重新反序列化**出新 store/步骤对象,测试侧 `slm2` 的 `s2` 是旧对象 → 断言改 `sl_mgr2._store.get(...).steps[0]`;且重建后旧卡 C++ 对象已删 → RuntimeError,断言须重建后重新取卡。
- **验证**:main_widget 冒烟新增「树勾选 → 新卡 active=False」+「卡片按钮 → 树勾选框 Checked」+「卡片切换 → view.edited 保存链路」;step_card / step_list_tree_widget 冒烟原样全绿。

### 优化 B:多选拖拽顺序错乱 + 拖后画面不显示(任务 #73,完成)
- **需求**:「bug 目前多个选中拖拽移动后,导致部分步骤列表画面不显示」——拖拽后列表消失了(实际是画面没刷新)。
- **根因①(顺序错乱)**:`_selected_paths_top` 返回 `sorted(set(tops))`——按名称排(Unicode 码点,「乙」0x4E59 <「甲」0x7532),与树显示序(= walk 序 = 执行序)相反 → 多选拖拽批量插入顺序错乱。修复:按 walk 序排序(`order = {p: i for i,(p,_g) in enumerate(store.walk())}`)。
- **根因②(画面不显示)**:`_move_paths` 结尾 `_changed(snap[0][0])`——`snap[0][0]` 只是**名称**,而 `refresh(current_path)` 的 `_find_item` 按完整路径匹配;组内移动后 root 层无该名称 → `_find_item` 失败 → `setCurrentItem(None)` → `list_selected` 不触发 → 宿主不重建画面。修复:跟踪 `first_new`(第一个插入项的完整新路径 `parent + "/" + top_name`)传给 `_changed`。
- **断言坑**:中文 Unicode 排序「乙<甲」恰与 walk 序相同 → 用创建序「甲→乙」使名称序 ≠ walk 序才测出排序 bug;首版期望把「组内项拖到 root 尾前」写成组内(实际 parent 取目标同层 → root)→ 期望修正为 `["组X","子乙","子甲","尾"]`。
- **验证**:树冒烟新增「选中集 walk 序」(root + 组内两组)、「组内移动 → list_selected 收到完整路径 组X/子甲」、「拖到 root → root 路径」;RED(名称序 [乙,甲] / got=[]) → GREEN。

### 优化 C:拖拽亮线 + 位置语义(任务 #72,完成)
- **需求**:① 拖到两条目中间 → 中间亮线;② 拖到空白 → 末尾亮线;③ 拖到某条目 → 该条目尾部亮线(意味着插入到该条目的**下一条**)。
- **语义变更**:OnItem 从「目标为组 → 组内尾部」改为「目标之后」(列表/组统一 = 下一条);空白(无目标)→ root 尾部;Above/Below 不变。
- **实现**:
  - `setDropIndicatorShown(False)` + 自绘:`_drop_rect` 状态 + `paintEvent` 在 viewport 画 3px 蓝线(`_LINE_H=3`);`dropMoveEvent` 更新线(`_update_drop_line`),`dragLeaveEvent`/`dropEvent` 清除。
  - `_update_drop_line(pos, position=None)`:AboveItem → 目标顶部;Below/OnItem → 目标底部(OnItem = 下一条语义);空白 → `_last_visible_item`(itemBelow 链尾)底部;`position=None` 时取 `dropIndicatorPosition()`(冒烟可显式传——非拖拽态恒 NoPosition)。
  - `dropEvent`:target None → `target_path=""` 不再 ignore;`_move_paths` 接受空 target = root 尾部,OnItem 检查(`_is_group`)删除,OnItem/Below 统一 `sibling+1`。
- **重构 bug 教训**:把 `_sibling_index` 从 remove 循环之后挪到之前(注释「删除后重新定位」是代码事实),多选拖拽时目标下标用删除前的 walk 算 → 探针 D `[组,甲,丙,乙]` 错序。修复:index 计算移回删除后。
- **断言坑**:期望按「组在 walk 中位置固定」推算(甲插组后 = [丙,乙,组,甲],非 [丙,乙,甲,组]);QDragMoveEvent 首参 QPoint 非 QPointF。
- **验证**:树冒烟 OnItem 组/列表/多选/空白/防御 + 亮线位置/清除 + dropMoveEvent,全绿;19/19 全量回归全绿。

## 用户 Bug 修复(完成,2026-08-29)—— 拖拽丢列表 + 删空组崩溃

### Bug A:拖拽后列表丢失(任务 #74,完成)
- **症状**:「拖拽哪个,哪个就消失」——列表 [a1,a2,a3] 拖 a3 到 a2,树变 [a1,a2]。
- **根因(非事务性移动)**:`_move_paths` 先删源后解码插入,且无 try——`StepList.from_format_strings` 抛 ValueError(模板缺失/未加载 → 无匹配)时:**删除已完成、插入未发生 → 列表真丢**,异常穿透 `dropEvent` 被 Qt 事件循环吞掉(traceback 不可见)→ 用户只见列表消失。探针复现:stub 步骤 + 未 load 的 manager → `ValueError: 第 0 条无法还原` → walk [a1,a2](a3 丢)。`_act_paste` 有 try/except+弹窗,`_move_paths` 没有——粘贴不丢、拖拽丢。
- **修复(三层)**:
  - `_move_paths` **事务性预检**:删除源前先对全部格式串试解码(组跳过),失败 → 弹窗「移动失败」+ return False,**任何数据不动**。
  - `dropEvent` 包 try/except:意外异常不再静默(弹窗 + 拒绝),不破坏拖拽状态。
  - `refresh` 的 `blockSignals` 改 try/finally:中途异常(数据损坏等)也不残留信号屏蔽(残留 → 树全部信号静默 → list_selected 不发 → 视图永不刷新,「拖拽后失去显示」的另一个可能来源)。
- **验证**:冒烟新增「不可还原 → 拒绝 + walk 不变」(mgr_t 未 load + 来自已 load mgr 的步骤格式串;QMessageBox.warning patch 成 no-op 防阻塞)+ 探针确认 a3 保留;19/19 回归全绿。

### Bug B:删除空步骤对象组 ValueError(任务 #75,完成)
- **症状**:删空组崩溃:`_pick_next` 里 `max(i for i, p in enumerate(before) if p in dead)` ValueError。
- **根因**:`before`(删除前列表序)只收集**列表**路径,`dead` 是其子集;删空组(无任何列表)时 `dead` 为空 → `max()` 空生成器 → ValueError。
- **修复**:`_pick_next` 开头 `if not dead:` → 返回删除后首个列表(或 None)。语义:删空组不影响列表序,显示删除后第一个列表即可。
- **验证**:冒烟新增 `_pick_next(before, ["空组"]) == "甲"`(旧实现 ValueError);19/19 回归全绿。
