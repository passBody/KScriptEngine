# SDD ledger — plan: docs/superpowers/plans/2026-08-28-step-base-class.md

> 适配说明:本仓库**非 git 仓库**,skill 的 commit 基址 / review-package(依赖 git log/diff)机制全部不可用。替代方案:
> - 提交步骤 → 运行冒烟/自检验证(项目惯例)
> - 评审包 → 任务创建/修改的文件清单 + 直接 Read 文件内容
> - 任务基址 → 无 commit,用「任务 N 文件清单」界定评审范围
> - 收尾 → 无分支可合,最终全量评审通过即完成

## Preflight scan(对照计划文本)

| 任务对 | 共享文件 | 产出→消费 | 检查结果 |
|---|---|---|---|
| T1 → T2 | `actions/__init__.py` | T1 导出 Step/StepStatus → T2 追加 TimeDelay 导出 | 无冲突:T2 Step 5 覆盖整个文件,内容 = T1 内容 + TimeDelay 行 |
| T1 → T2 | `actions/base.py` | T1 定义 Step/StepStatus → T2 的 TimeDelay 继承 Step | 接口一致:类属性 name/description/input_class/output_class、方法 create_default/do/to_format_string/from_format_string |
| T1 → T2 | `model/log_model.LogModel` | 基类 do() 用 error() → T2 run() 也调用 | 无冲突(单例) |

| 任务 | 自洽检查 | 结果 |
|---|---|---|
| T1 | 冒烟断言 vs 实现代码:create_default 槽类型、do 全流程、异常置错、手动 ERROR、偏移量、往返、None 三情形、ValueError 两情形 | 一致;`offset` 在 run 抛错路径下未赋值但先重抛,安全 |
| T1 | 文件创建:`actions/__init__.py` + `actions/base.py` | 一致;`__init__.py` 仅导入 base(不导入尚不存在的 time_delay) |
| T2 | 冒烟断言 vs 实现:create_default 推导、0.05s 延时、≤0 报错、往返 | 一致 |
| T2 | 文件创建:`actions/控制流程/__init__.py` + `time_delay.py`,修改 `actions/__init__.py` | 一致;中文包名合法 |

## Rulings

- (preflight) **无 git**:SDD 的 commit/review-package/分支机制不可用 → 用「运行验证 + 文件清单」适配 — 项目本身即非 git 仓库,计划 Global Constraints 已规定此惯例。若适配出错,后果:评审范围界定不准,可读文件内容补救。
- (T1 fixes, 2026-08-28) **3 处计划文本硬伤,实施者最小修正,裁定全部正确**:① `b'{"name":"桩步骤"}'` 中文 bytes 字面量在 Python 3 是 SyntaxError(非 ASCII 须转义)→ 改 str `.encode("utf-8")`(等价,与冒烟块其余风格一致);② `from __future__ import annotations` 使引号注解以源码文本存为 `"'number'"`,`dataclasses.fields().type` 返回含引号串 → 槽类型推导出 `["'number'"]`,冒烟断言失败 → 删除该行(actions/ 内字段签名设计要求注解保持真实值);③ 冒烟桩 `_ManErrStep.run` 漏算 `outputs.total`(默认 0 会写回 0 而非断言预期的 10)→ 补一行赋值。三者均为「照抄即无法运行/无法通过简报自身断言」,修正后 `Step smoke OK`、全依赖链冒烟绿 — 若不做:Task 1 无法交付,Task 2 重演 ②。
- (T1→T2 forward, 2026-08-28) **Task 2 time_delay.py 同样禁用 `from __future__ import annotations`**:`TimeDelayInput.seconds: "number" = 0.0` 引号注解会存成 `"'number'"`,`create_default` 推导出 `["'number'"]`,冒烟断言 `t.io._input_type == ["number"]` 必挂 → 已直接修订 task-2-brief.md Step 3 代码(删该行)。红阶段预期由 NameError 修正为 ImportError(包加载时 `actions/控制流程/__init__.py` 第 1 行即抛,与 Task 1 同型「功能缺失」红)— 若不做,Task 2 必失败一轮。

## Task 状态

### Task 1(完成,2026-08-28)

- 实施者状态:**DONE_WITH_CONCERNS** — 全部冒烟绿(`Step smoke OK`、widgets OK、`import actions` OK、`main --check` EXIT=0);3 处计划文本硬伤已最小修正(见 Rulings,裁定正确)。
- 交付:`actions/__init__.py`(4 行)、`actions/base.py`(382 行)。
- 红确认:期望 NameError,实际 ImportError(`actions/__init__.py` 第 1 行),同型功能缺失红,无需再修。
- 观察项(不阻塞):`python -m actions.base` 的 runpy RuntimeWarning(包加载导入导致模块双执行,既有 `widgets.step_io_widget` 同款,非本次引入);`main.py --check` 无文本输出,以退出码判定。
- **任务评审(sonnet):✅ 通过** — spec 完全合规;无 Critical/Important;3 条 Minor(均为计划级观察,停车,不阻塞):① `input()` 的 zip 在 resolve_inputs 返回值少于字段数时静默截断(受控构造路径不可达,防御性建议);② RUNNING 状态无冒烟直测(仅 PENDING→FINISHED/ERROR 与 ERROR 保持,属简报覆盖缺口);③ runpy RuntimeWarning 待后续任务统一评估懒导入。评审全文:`task-1-review.md`。

### Task 2(完成,2026-08-28)

- 实施者状态:**DONE** — 8 项全量回归全绿(7 模块冒烟 OK + `main --check` exit 0),红为预期 ImportError(`控制流程/__init__.py` 第 1 行),Step 5 导出断言 `('延时','执行中')` 通过;逐行照抄简报,只动 3 个 Files 列出的文件,未碰 `actions/base.py`;无担忧。
- **任务评审(sonnet):✅ 通过** — 三文件逐字核对一致、基类契约对照验证(槽类型推导 `["number"]`、ERROR 不覆盖规则、`self.inputs` 命名);零 Critical/Important;1 条 Minor:time_delay.py 模块级与 `__main__` 内重复 `import time`(简报原文所致,无害,不修)。评审全文:`task-2-review.md`。
- 停车观察汇总(Task 1 3 条 + Task 2 1 条):均不阻塞,交给终审与收尾消息。

### 终审(opus,2026-08-28):✅ Ready to merge

- 与 spec/计划逐条一致,四交付文件与修订后计划文本逐字吻合;评审者重跑全量回归(7 模块冒烟 + `main --check` EXIT=0)全过。
- 零 Critical;1 条 Important(评审明示不阻塞本次交付):`_io_type_lists`/`_signature` 无注解注册校验——子类作者写错注解类型时失败晚且费解(真实类型名 → 保存期 TypeError;未注册类型名 → StepIOWidget 静默偏离)。**裁定:停车,留待下一步「步骤列表/步骤管理」开始前落地**(评审原话建议;当前仅 spec 内两个子类且均正确,提前加固属 YAGNI;若不做,后果:下一步新增子类时踩一次晚而费解的错,成本低)。
- 7 条 Minor 停车(2 新措辞/消息优化 + 3 新防御项 + 2 复认):「静态方法」→「类方法」措辞;io ValueError 透出消息优化;基类直接实例化建议改 NotImplementedError;zip 静默截断;RUNNING 无直测;重复 import time(计划原文);runpy RuntimeWarning 建议后续单独立项懒导入。
- **收尾裁定:保留 workspace**(`.superpowers/sdd/2026-08-28-step-base-class/` 含台账/简报/报告/评审——非 git 仓库下唯一的裁定与审计记录;skill 的「删除 workspace」依赖 git log 可恢复,此处删除即永久丢失)。计划文档复选框已全部勾选。

## 计划完成(2026-08-28)

`actions/` 包交付完毕:StepStatus + Step 基类 + TimeDelay 示例子类;双任务实施 + 双任务评审 + 终审全过;台账即收尾记录(无分支可合,非 git 适配)。

## 后续落地(2026-08-28,用户指示:落地终审 Important #1 注解校验)

- **变更**:`actions/base.py` — ① `_io_type_lists` 对输入/输出 dataclass 每个字段注解做 `ProjectVariable.type_of()` 注册校验,未注册 → `ValueError`(带步骤名/角色/字段名/支持列表);② 新增 import `ProjectVariable`;③ 模块 docstring「子类需覆盖」补注册要求;④ 冒烟新增 `_BadStep`(`x: "audio"`):`create_default` 抛 ValueError 且消息含 `坏步骤`/`x`/`audio`。
- **TDD**:红 — `AssertionError: 未注册类型应抛 ValueError`(base.py:394,create_default 对坏注解静默成功);绿 — `Step smoke OK`;全量回归 7 模块冒烟 + `main --check` EXIT=0 全过。`TimeDelay`(seconds: "number")不受影响。
- **裁定(偏离评审建议的 parenthetical)**:**不做** `strip("'\"")` — 引号剥离会让误带 future-annotations 的文件(`"'number'"`)被静默归一到 `"number"` 而通过校验,恰好掩盖「禁用 future annotations」裁定要抓住的失败模式;严格校验下该错误会在 `create_default` 处响亮失败(消息含 `"'number'"`),定位即修复。若做:此错误类别静默,与裁定意图相悖。
- 效果:子类作者写错注解(真实类型 `float` / 未注册名 `"audio"` / future 引号串)均在类使用处即时报错,不再「保存期 TypeError」或「静默偏离」。spec §4.5/§7 已同步。

## Task 状态

(空 — 从 Task 1 开始)
