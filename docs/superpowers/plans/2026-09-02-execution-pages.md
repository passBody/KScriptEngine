# 多执行列表页 + 每页独立热键（实施计划与记录）

日期：2026-09-02 ｜ 对应 spec：2026-09-02-execution-pages-design.md

## Global Constraints（沿用项目约定）

- 模块冒烟 `python -m <mod>` 直跑，禁管道（EXIT=139）；runpy 桩挂
  `sys.modules[__name__]`；中文一律 `.encode("utf-8")`（禁中文 bytes 字面量）；
  新模块进 tests/smoke_all.py MODULES；每步全量冒烟绿再提交。
- sample.kscp 保持 v1 不动（打开不改写旧文件），CHECKS 天然回归迁移路径。

## 实施顺序（四个提交，均 51 SMOKE + 1 CHECKS 全绿后提交）

### 提交 ① 模型层：run_interrupt thread-local + StepPageStore + JSON v2

- model/run_interrupt.py：模块级 `_active_stop`/`_lock` → `threading.local()`；
  冒烟新增双线程隔离（A 的事件不打断 B；主线程无登记不受影响）。
- model/step_runner.py：`set_stop_event` 从 start() 锁内移入 `_run()` 工作线程
  开头；冒烟新增并发 immediate 用例（两个 runner 各含 `interruptible_sleep(1.0)`
  慢步骤：停 r2 → r2 快速结束 count==101、r1 count 仍 1 且 status 未被交叉
  复位；再停 r1 同样快速结束）。
- model/step_page_store.py（新建，334 行）：页容器全 API + 冒烟
  （增删改查/保序重命名/最后一页守卫/v1 检测含全组歧义/v2 幂等往返/
  坏数据/ensure_default_page）。
- tests/smoke_all.py MODULES 加 model.step_page_store。

### 提交 ② 换页 UI + 页管理

- widgets/management_trees.py：
  - `ManagementTree` 基类改 `QObject`（承载页信号）。
  - StepListManagementTree 改页容器：`_build_page_container` = 标题行
    （QLabel 标题右击 CustomContextMenu「重命名」+ QToolButton InstantPopup
    下拉切换，全部页勾选当前）+「添加页/删除该页」按钮行 + QStackedWidget
    （每页一棵缓存 StepListTreeWidget）。
  - 查重：add_page/rename_page 抛 FileExistsError → LogModel.error 并阻止。
  - 页信号 page_changed/page_added/page_renamed/page_removed + list_selected
    跨页出口；`store` property = 当前页 store；current_tree()/trees()；
    `_activate_page` 恢复该页选中（首次进入自动选首个列表，空页回占位）；
    执行期只读：全部页树锁、添加/删除按钮禁用、标题重命名守卫、下拉切换可用。
  - repoint_composite_refs / resync_composite_steps 扩展到全部页。
- widgets/main_widget.py：`_open_package` 用 current_tree() 接线（执行器仍
  单例，行为与单页等价）；_clear_running_highlight/_on_step_status 走
  trees()/current_tree()。
- 冒烟：页容器结构/添加页跳转/重命名缓存重键+落盘/查重日志阻止/删除守卫/
  切页宿主重绑/只读矩阵（QInputDialog 顺序桩）。

### 提交 ③ 多执行器 + 设置表格 + 热键分发

- widgets/main_widget.py：
  - 删除 `_runner/_runner_gen/_hotkey_listener/_exec_locked/_step_hooks/
    _step_paths` 单例 → 按页字典 + `_current_page`。
  - `_ExecBridge` 信号携带页：runner_state=(page,gen,st)、hotkey_toggle=page、
    step_status=(page,step)、progress=(page,i,n)。
  - `_start_page_listeners`（开包常驻）+ `_handle_hotkey_toggle(page)` 分发 +
    `_exec_has_errors(page)` + `_attach/_detach_step_hooks(page)` +
    `_recompute_lock` 活跃重算 + `_refresh_exec_status` 组合文案 +
    执行按钮=当前页 toggle + `_rebuild_runner(page)` +
    `_set_exec_scope` 重建全部 READY 页 + `_on_exec_list_changed` +
    页联动四信号处理（重键/停监听/悬空防御）。
  - `_page_hotkeys()` / `_apply_settings(hotkeys, stop_mode)`：executor.json v2。
- widgets/settings_dialog.py：集中表格 + `_validate` 查重 + `_on_save_clicked`
  校验阻止 + HotkeyEdit 可空/清除。
- 冒烟重写：双页双监听、热键分发 toggle（同页防双执行）、并发锁定计数、
  后台页提示、页删除/重命名联动、每页代际、`_page_hotkeys` 读回
  （v2/旧格式/缺失/非法）、`_apply_settings` 落盘结构、设置表格查重。

### 提交 ④ 文档与回归

- README.md：工程文件表（v2 页格式/executor pages）+「多执行列表与热键」
  使用说明 + 冒烟计数 51。
- docs/工程分析.md：架构树、数据流、序列化协议栈、模块表（新增
  step_page_store、更新 step_runner/run_interrupt/main_widget/settings_dialog/
  management_trees 行数与职责）、7.1 执行器、5.2 实现状态、8 行数清单、
  10 总体评价。
- docs/README.md 索引（specs 15 / plans 10）+ 本 spec/plan 两份存档。
- 全量 `python tests/smoke_all.py`（51 SMOKE + 1 CHECKS）。

## 风险与对策（实施中已闭环）

1. **thread-local 登记时机**：必须移入工作线程——并发 immediate 冒烟覆盖 ✓。
2. **单例残留**：`_runner` 等五符号 grep 全库逐一改点（含冒烟大段重写）✓。
3. **v1/v2 全组歧义**：本质不可区分，按 v2 解读，docstring + 文档明示 ✓。
4. **页名/映射一致性**：rename 重键五字典；remove 停监听 + 悬空防御 ✓。
5. **锁定漏算**：状态事件重算替代加减计数 ✓。
6. **HotkeyEdit 可空化**：set_hotkey("") + 清除按钮；旧冒烟断言随表格化更新 ✓。
7. **状态文案依赖 runner 实际状态**：STOPPING 文案测试移到假 runner 段
   （真实 runner 状态由 emit 不可伪造）✓。

## 验证结果

- 51 SMOKE + 1 CHECKS 全绿（2026-09-02）。
- 提交链：`02b65e9`（模型层）→ `7630acb`（换页 UI）→ `93f5e51`（多执行器
  核心）→ 本文档提交。
