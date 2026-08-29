# SDD ledger — plan: docs/superpowers/plans/2026-08-29-step-list.md

> 适配说明:本仓库**非 git 仓库**(既有裁定延续):task-brief / review-package 脚本依赖 git,不可用 → 简报用 awk 从计划文本手工摘录;「提交」步骤 → 运行冒烟/自检验证;评审包 → 任务文件清单 + 直接 Read 文件内容;BASE/HEAD 无 git 概念 → 评审对照计划文本与实现文件;收尾 → 无分支可合,终审通过即完成;workspace 保留(无 git log 可恢复)。

## Preflight scan(对照计划文本)

| 任务对 | 共享文件 | 产出→消费 | 检查结果 |
|---|---|---|---|
| T1 → T2 | 无共享文件(各自新建独立 .py) | T1 产出 `StepList`(add/insert/remove/move/do_methods/to_format_strings/from_format_strings/create_empty/steps/len/iter/getitem)→ T2 冒烟消费 create_empty/add/do_methods/to_format_strings/from_format_strings | 无冲突:T2 简报代码块已含完整消费签名;两文件均为新建,无插入点/共享修改问题 |

| 任务 | 自洽检查 | 结果 |
|---|---|---|
| T1 | 冒烟断言 vs 实现:空列表三断言 / 增删插移(含 remove(99)、move(99,0) 两种 IndexError)/ enabled 过滤 + 真实 do 调用 `[1,1]` / 格式串往返规范化稳定 + enabled 参与往返 / 坏条目两种(非法编码 + 无匹配伪造串,均断言「第 0 条」);红=NameError(StepList 未定义);文件仅创建 `model/step_list.py` | 一致 |
| T2 | 冒烟断言 vs 实现:空 store(`paths()==[]`、`b"{}"`)/ 结构四类(顶层列表+组+组内+嵌套组)/ paths 排序 / get 三态 / 冲突三类(同名列表、组撞列表、组幂等)/ 非法路径五种(空串、a//b、a/./b、a/..、父组不存在)+ 祖先为列表 + add_group("a//b")/ 归一化(前导 / 与反斜杠)/ 空组 / JSON 三态往返字节稳定 / all_do_methods 长度 4 + 全部返回 1 / 结构校验四种(顶层非对象、节点值 123、键含 /、坏格式串带「第 0 条」);红=NameError(StepListStore 未定义);文件仅创建 `model/step_list_store.py` | 一致;注意简报中 `"前导组\\临时"` 是 Python 转义反斜杠 → 运行时值为 `前导组\临时` → `_norm_path` 归一化得 `前导组/临时` |

## Rulings

- (preflight) **无 git 适配延续**(既有裁定):简报 awk 摘录、验证替代提交、评审包 = 文件清单 + 直接 Read。若适配出错,后果:简报与计划文本漂移,靠 awk 直接抽取 + 评审对照补救。
- (preflight) **计划自洽,无需修正即执行**:T1/T2 无相互矛盾;每任务红=NameError,冒烟即测试载体;Global Constraints 逐条写入简报。无计划缺陷需要实施期修正(计划已含 TDD 全码,实施 = 转录 + 运行验证)。

## Task 状态

### Task 1(完成,2026-08-29)

- 实施者状态:**DONE** — 红 `ImportError: cannot import name 'StepList'`(EXIT=1;runpy 语义:python -m 先按真名导入模块,冒烟内 self-import 落属性查找;与简报预判 NameError 同义,类缺失),绿 `StepList smoke OK` EXIT=0;依赖链 `StepManager smoke OK` / `Step smoke OK`。
- 交付:创建 `model/step_list.py`(唯一新文件)。
- **任务评审(sonnet):✅ 通过** — 程序化 diff 核对两代码块(冒烟 + 类)逐字包含;全部 API 在位(add/insert/remove/move/do_methods/to_format_strings/from_format_strings/create_empty/steps/双下);严格解码两分支均含「第 N 条」;依赖契约实读核对(Step.enabled 默认 True 且经 "run" 键往返、Step.do 绑定方法、StepManager.from_format_string 抛/None 契约);红 ImportError-vs-NameError 判定为正确 runpy 产物;零 Critical/Important;3 条 Minor(停车,不阻塞):① 计划 Interfaces 段写 staticmethod 而代码块是 classmethod——实现从代码块(正确,子类友好),Task 2 简报无继承矛盾;② 冒烟未直接覆盖 `__iter__`/insert 负索引钳制/`from_format_strings([])`(低风险,一行可补);③ 伪造串 `.encode()` 裸调用系简报逐字代码(非模板字节,无行动)。
- Task 1: minor (deferred): ①计划 Interfaces 段 staticmethod-vs-代码块 classmethod(实现从代码块,正确);②冒烟未直接覆盖 `__iter__`/insert 负索引钳制/`from_format_strings([])`;③伪造串 `.encode()` 裸调用系简报逐字代码。— 终审裁定是否修。
- Task 2: minor (deferred): ①`add_list` docstring「path 空 = 顶层」措辞误导(逐字来自简报,读者可能误用 `add_list("")`,行为已裁定 ValueError);②冒烟未断言 `add_group("")`/`add_group("/")` → ValueError(仅测 `a//b`);③`all_do_methods` 顺序断言 `[1,1,1,1]` 顺序不敏感(插入序 DFS 未被钉住,仅钉住 enabled 过滤计数);④`from_json` 非 JsonInput 类型漏 TypeError(注释已声明有意)。—— 终审裁定是否修。

### Task 2(完成,2026-08-29)

- 实施者状态:**DONE_WITH_CONCERNS** — 红 `ImportError: cannot import name 'StepListStore'`(EXIT=1)→ 绿 `StepListStore smoke OK` EXIT=0;依赖链 + 全量 12 命令回归全 EXIT=0;唯一 concern = 已裁定的 paths 排序偏离(见 Rulings),报告醒目标注。类 + 冒烟逐字转录(程序化核对)。
- 交付:创建 `model/step_list_store.py`(唯一新文件)。
- **任务评审(sonnet):✅ 通过** — 16 个类成员全在位、无多余;重点逐项核对(`_norm_path` 段规则、`_parent_of` 祖先为列表、add_group 幂等/撞列表、add_list 顶层/冲突/空串、from_json 三态 + 结构校验、all_do_methods 插入序 DFS、get/paths);paths 偏离独立判定正确(U+6253 < U+65E5 < U+68C0);严格解码链端到端核对(「第 N 条」);classmethod-vs-Interfaces-stalemethod 同 T1 先例;约束逐条核对(.encode("utf-8")、无中文 bytes、b"{}"/b'[1,2,3]' 系 ASCII);零 Critical/Important;4 条 Minor + 1 条 ⚠️(见 Rulings 第二条)。
- Task 2: minor (deferred): ①②③④。—— 终审裁定是否修。:冒烟期望 `["清理体力/日常/跑图", "清理体力/检查体力", "打开软件"]` 与实现 `paths()` 的 `sorted()`(spec §4 明文「排序」)矛盾——该期望是逆插入序,既非排序也非逆排序,系计划手误。修正:期望改为真实排序序 `["打开软件", "清理体力/日常/跑图", "清理体力/检查体力"]`(打 U+6253 < 日 U+65E5 < 检 U+68C0)。RED 阶段(ImportError,类未定义)不受影响;计划文本与简报已同步修正。若照旧:Task 2 冒烟在绿阶段必失败且无自洽修法。**T2 评审已核对此偏离并独立判定正确。**
- (T2 评审 ⚠️,2026-08-29) **`add_list("")` 语义澄清,裁定照准评审判断**:T2 评审指出派发约束措辞「空路径 = 顶层(仅 add_list 合法)」与实现/冒烟(`add_list("")` → ValueError)相矛盾。裁定:实现正确——空串列表无名字,若允许则键 `""` 违反 `_validate_name` 且破坏 JSON 往返;「顶层列表」= 无 `/` 的名单直接作路径(如 `打开软件`)。spec §4/§5 措辞已同步澄清(改「无 `/` 即顶层」,空串/纯 `/` 对两方法均 ValueError)。若照旧:读者会误用 `add_list("", sl)`。**终审将核对 spec 措辞一致性。**

### 终审(2026-08-29,完成)

- **终审(opus):✅ Ready to merge — 零 Critical、零 Important。** 程序化核对两文件类区域与计划代码块逐字一致;严格解码链(store._walk → from_format_strings → StepManager → Step._decode)单一包裹、下标语义正确;enabled 端到端贯通(do_methods / all_do_methods / 格式串往返,旧串缺 run 键 → True 向后兼容);错误分类与 spec §5 完全一致;无循环导入;无部分状态风险。6 条 Minor(含 deferred 分诊)。
- **Ruling(终审后修正 ①):`add_list` docstring 措辞修正。** 终审 Minor 1:docstring「path 空 = 顶层」描述不存在的行为,与 spec §4 冲突,是交付中唯一与 spec 矛盾的文本。裁定:修。已改实现 + 计划代码块(保持逐字同步)为「path 无 `/` 时即顶层列表;空串/纯 `/` → ValueError」。若照旧:后续 UI 任务读者误用 `add_list("")`。
- **Ruling(终审后修正 ②):spec §5 归一化句与错误表协调。** 终审 Minor 2:spec 第 72 行「折叠 `.` 段」与错误表(第 76 行 `.` → ValueError)自相矛盾,且与计划 Global Constraints(不折叠)和冒烟(`a/./b` → ValueError)不符;实现正确(从计划+错误表),但与 VariableTree 折叠语义刻意不同。裁定:修 spec——归一化句改为「含 `.` 或 `..` 段 → ValueError(不折叠,刻意严于 VariableTree)」。若照旧:UI 任务同时处理两棵树时会困惑。
- **Deferred minors 分诊(终审裁定全部照旧/停车,除上述 ① 已修):**
  - T1 ① Interfaces staticmethod-vs-classmethod → 停车:实现从代码块,classmethod 子类友好、行为等价。
  - T1 ② 冒烟未覆盖 `__iter__`/负索引 insert/`from_format_strings([])` → 停车:一行代理/空循环,读代码已证;有意义的变更与解码路径均已钉住。
  - T1 ③ 伪造串 `.encode()` 裸调用 → 停车:简报逐字代码,编码的是 JSON 载荷而非中文模板字节。
  - T2 ② 冒烟未断言 `add_group("")`/`add_group("/")` → 停车:与 `add_list("")` 共享 `_norm_path`,后者已钉住。
  - T2 ③ all_do_methods 顺序断言不敏感 → 停车:插入序 DFS 由构造保证(`_collect_do` 按 `node.values()` 字典序);UI 任务消费时补 `runs == sl_open.do_methods() + sl_check.do_methods() + sl_run.do_methods()` 钉住。
  - T2 ④ from_json 非 JsonInput 漏 TypeError → 停车:有意为之,注释声明,与 VariableTree 先例完全一致。
- 验证:修改后 `python -m model.step_list_store` → `StepListStore smoke OK` EXIT=0。
- **收尾:终审通过即完成**(非 git 适配延续裁定);workspace 保留(无 git log 可恢复)。
