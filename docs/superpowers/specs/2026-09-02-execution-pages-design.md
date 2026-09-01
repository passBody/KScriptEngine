# 多执行列表页 + 每页独立热键（设计规格）

日期：2026-09-02

## 1. 目标

现状：KScript 只有一个全局触发热键（executor.json 的 `hotkey`），按一次
执行/停止当前范围（全部列表或仅当前列表）。用户场景受限：想按 `1` 跑
"记录坐标"、按 `2` 跑"点击记录坐标"、按 `3` 跑"截图"。

**目标**：步骤列表树顶部新增「执行列表」层（页），每页绑定自己的单字符
热键，按需触发；多页允许并发执行。用户确认的四项决策：并发多跑、设置
弹窗集中表格配置、每热键一个监听线程、热键常驻（工程打开即生效）。

## 2. 需求清单

| # | 需求 |
|---|---|
| R1 | step_list.json v2：顶层键 = 执行列表名，值 = 既有组/列表嵌套结构；旧格式自动迁移（顶层任一值为数组 → 包成单页「执行列表1」），**打开不改写旧文件** |
| R2 | 树面板换页 UI：顶部标题（右击重命名，值 = JSON 键）；标题右方下拉切换按钮（列出全部页，点击切换）；下方「添加页」按钮（命名弹窗 → 新建并跳转）与「删除该页」按钮（最后一页守卫）；**新建/重命名查重**——重名/非法名 → 日志报错并阻止命名行为 |
| R3 | 每页热键：executor.json `pages` 映射（页 → 单字符或空）；**每热键一个常驻 HotkeyListener**（工程打开即生效，取消"待命/停监听"武装流程） |
| R4 | 热键 toggle：该页 READY → 启动（错误/占位卡守卫）；RUNNING/STOPPING → request_stop；同一页单 runner 防双执行 |
| R5 | 并发：多页同时执行互不干扰（页间 store 独立 → 无交叉复位；immediate 停止线程本地隔离）；共享全局变量/日志为 last-writer-wins（用户已知并接受） |
| R6 | UI 锁定按活跃执行器集合重算（任一页非 READY → 锁）；每页独立代际过滤陈旧状态；step hooks 按页挂/摘 |
| R7 | 设置弹窗改集中表格：每页一行（页名 + 热键编辑框可空 + 清除按钮）；保存前页间热键查重（大小写不敏感），冲突弹窗阻止 |
| R8 | 执行按钮 = 当前页 toggle（点击直接执行/停止）；状态栏 = 当前页状态 + 「另 N 页执行中」 |
| R9 | 页增删改联动：页重命名 → 执行器/监听器字典重键；页删除 → 停监听 + 清理 + 悬空热键防御 |
| R10 | 兼容：executor.json 旧格式（无 pages）→ 顶层 hotkey 归第一页；缺失 → 第一页默认 `` ` ``；step_list.json v1 顶层全组文件与 v2 本质不可区分 → 按 v2 解读（文档明示） |

## 3. 关键设计决策

### 3.1 数据模型：StepPageStore（页 → 独立 StepListStore）

- 每页一个独立 `StepListStore`（复用全部现有模型 API，**零改动**）；
  `StepPageStore` 为薄容器（有序页名 → store，页序 = 插入序）。
- 页之间 store 独立 → 并发执行无交叉复位（StepRunner start 只复位本 store）。
- 跨页移动列表靠「复制/剪切 → 切页 → 粘贴」（剪贴板内容页根语义一致），
  不提供跨页拖拽（v1）。
- `sl_mgr.store` property 返回**当前页** store——既有调用方（main_widget/
  management_trees 冒烟）绝大多数不用改。

### 3.2 v1/v2 检测规则

顶层任一值不是对象（列表叶子）→ v1 → 整棵包成单页；顶层全为对象 → v2。
选 v2 优先的理由：v2 文件重读必须幂等往返（v2 单页全组文件若判 v1 会再包
一层损坏数据）；v1 全组文件罕见且歧义本质不可区分，docstring/文档明示。

### 3.3 run_interrupt 线程本地化（并发 immediate 正确性前提）

- 原模块级 `_active_stop` 全局单例在并发下会互相覆盖登记、任一停止打断
  所有页的可中断睡眠 → 改 `threading.local()`。
- **登记位置从 StepRunner.start()（GUI 线程）移入 `_run()` 工作线程内**
  （thread-local 要求登记者=睡觉者）；单 runner 行为等价（登记先于第一步 do）。
- 语义不变：未登记 → 普通 sleep；登记且事件置位 → ~20ms 内返回 True。

### 3.4 热键常驻 + 每页单 runner

- 打开工程 `_start_page_listeners()`：按 `_page_hotkeys()` 为每个非空热键建
  监听器（回调闭包携带页名 → 桥 `hotkey_toggle(page)`）。
- `_handle_hotkey_toggle(page)`：该页 runner 非 READY → request_stop（toggle）；
  否则错误兜底 → 建 runner（scope=current 且是当前页才传 only_path）→ 挂该页
  hooks → start。runner READY 后保留复用（同页防双执行）。

### 3.5 UI 锁定与状态

- `_set_exec_locked` 入口不变（全锁）；锁定量由状态事件**重算**：
  `active = any(runner 非 READY)`，不用加减计数（防漏算）。
- 状态栏 `_refresh_exec_status()`：当前页 RUNNING/STOPPING/待命 + 热键提示；
  后台页执行中追加「另 N 页执行中」。

### 3.6 executor.json v2

```json
{ "hotkey": "`", "stop_mode": "after_step",
  "pages": { "执行列表1": "f", "执行列表2": "" } }
```

- 读 `_page_hotkeys()`：v2 pages 逐页取（未知页忽略、非法值空）；旧格式无
  pages → 顶层 hotkey 归第一页；文件缺失/损坏 → 第一页默认 `` ` ``。
- 写 `_apply_settings(hotkeys, stop_mode)`：全量映射落盘 → 重建全部监听 →
  READY runner 按新停止方式重建。
- 页增删改不写 executor.json（映射跟随页名，改名不丢热键）。

## 4. 文件与接口

| 文件 | 变更 |
|---|---|
| model/step_page_store.py | 新建：StepPageStore（page_names/pages/get_page/add_page/rename_page/remove_page/ensure_default_page/to_json_bytes/from_json；DEFAULT_PAGE="执行列表1"） |
| model/run_interrupt.py | thread-local 登记（set/clear/interruptible_sleep 导出名不变） |
| model/step_runner.py | 登记移入 `_run()` 工作线程（start 锁内两行删除） |
| widgets/management_trees.py | ManagementTree 基类改 QObject；StepListManagementTree 页容器（标题右击重命名/下拉切换/添加页/删除该页/查重日志阻止/每页缓存树/共享宿主/页信号 + list_selected 跨页出口/store property=当前页）；合成卡片引用改指与签名重同步扩展到全部页 |
| widgets/main_widget.py | 按页字典 runners/gens/listeners/hooks/paths；桥信号携带页；`_handle_hotkey_toggle(page)` 分发；`_start_page_listeners` 常驻；执行按钮=当前页 toggle；活跃重算锁定；`_page_hotkeys`/`_apply_settings` v2；页联动四个信号处理 |
| widgets/settings_dialog.py | 集中表格（页名+HotkeyEdit 可空+清除按钮）+ `_validate` 页间查重 + `hotkeys()` |
| tests/smoke_all.py | MODULES + model.step_page_store |

## 5. 验证

- 单元：run_interrupt 双线程隔离；step_runner 并发 immediate（停一页不误停
  另一页、start 不交叉复位）；step_page_store 全 API + v1/v2 检测 + 幂等往返。
- UI：双页工程双监听、热键分发 toggle、并发锁定计数、后台页提示、页删除/
  重命名联动、每页代际、`_page_hotkeys`/`_apply_settings` 往返、查重冲突。
- 全量：`python tests/smoke_all.py`（51 SMOKE + 1 CHECKS，CHECKS 覆盖
  sample.kscp v1 迁移路径）。
- 手工：sample.kscp 打开自动迁移单页；新建页绑热键 g；两页各放延时步骤，
  按 f/g 并发跑 → 各自独立执行/停止、状态栏「另 1 页执行中」、卡片颜色
  各自刷新、immediate 停止只停对应页。
