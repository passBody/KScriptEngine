# 执行器与输入步骤设计规格

> 日期：2026-08-30
> 前置：2026-08-30 地基加固已落地（路径归一化统一、格式串校验、Step 状态通知、偏移量校验、LogWidget 增量刷新）。

---

## 1. 目标

1. **输入步骤**：新增三个步骤模板——「按键」「鼠标点击」（键盘/鼠标模拟，接入内嵌的 `key_control`）、「输出日志」。鼠标点击步骤提供图片标注辅助：以素材图片为底图标点位，坐标回写输入 GUI，自定义视图含标注预览图。
2. **执行器**：点击「执行」进入**待命**（监听用户自选热键）；按下热键 → 按插入序 DFS 执行**全部列表**（`all_do_methods`，程序计数器 + 偏移量推进）；再次按下热键 → **当前步骤完成后停止**；再按 → 从头执行。
3. **热键配置**：UI 输入框绑定任意单字符键，保存到 `setting.json`（不随 .kscp 分发）。

## 2. 已确认的设计决策（brainstorm 结论）

| 决策点 | 结论 |
|---|---|
| 启动语义 | 「执行」按钮 → 待命（监听热键，不执行）；热键按下才执行 |
| 执行范围 | 全部列表（插入序 DFS，`all_do_methods`，enabled 过滤） |
| 停止粒度 | 协作式：当前步骤完成后在下一步前停止，不打断动作 |
| 重触发 | 每次从头：触发前所有步骤状态复位 PENDING |
| 热键类型 | 任意单字符（含数字；KScript 无数字选参场景） |
| 注入键冲突 | 已实测：pynput 监听器会捕获 key_click 模拟的按键。采用**文档提醒**方案：热键不得与步骤模拟的按键冲突（UI tooltip + 文档） |
| 错误策略 | 任一步骤执行错误（do() 抛异常）→ 停止整个执行 |
| 执行中编辑 | RUNNING/STOPPING 期间锁定编辑（树/卡片/变量禁用） |
| 依赖接入 | `key_control` **最小内嵌副本**进 KScript（`libs/key_control/`） |

## 3. 组件与接口

### 组件 1：内嵌 key_control（libs/）

- 新建 `libs/key_control/`：从 `../MouseAndKeyboardMacros/key_control/` 复制 `base.py`（`InputControl`）+ 最小 `__init__.py`（仅导出 `InputControl`）。**不**内嵌 switch.py/pipe.py（子进程开关模式用不上）。
- `InputControl` 关键接口（已核实源项目实现）：
  - `key_click(key, duration=None)`：单字符 / 命名键（space/enter/f1 等，经 `NAMED_KEYS`）/ 多字符 = 同时按下的和弦；duration 为按住秒数。
  - `mouse_click(x, y, duration=None, restore_position=False)`：移动到 (x,y) 左键点击。
- KScript 新增 `requirements.txt`：`pynput>=1.7`。
- 文档注明：模拟输入到游戏窗口需**管理员身份运行**（沿用源项目经验）。

### 组件 2：StepIOWidget 槽值变更监听（model/step_io.py 扩展）

为自定义视图刷新预览提供通知机制（仿 LogModel/Step 状态监听的纯 Python 回调模式）：

```
add_listener(cb: Callable[[], None]) -> None     # 任何槽值变更后调用 cb()
remove_listener(cb) -> None                      # 移除；未注册静默
```

- 通知点在 `_set_input` / `_set_output` 出口（两条写路径——GUI 编辑与 `change_value` 程序化写入——都经过这里）。
- 监听者异常静默吞掉（与 LogModel 通知策略一致），不打断数据写入。
- 只通知「槽值已变」，不带参数；监听者自行决定刷新什么。

### 组件 3：输入步骤模板（actions/）

新增三个模板，全部输入槽可引用变量（`{{变量名}}`）。

#### 3.1 actions/输入/按键.py —— 按键

| 项 | 内容 |
|---|---|
| name / description | `按键` / 模拟键盘按键 |
| 输入类 | `键名: "string" = ""`、`按住时长: "number" = 0.05` |
| 输出类 | 空 |
| run() | 键名为空 → 置 ERROR + 日志报错（不抛异常，与 TimeDelay 同风格）；否则 `InputControl().key_click(键名, 时长 if 时长 > 0 else None)`，返回 1 |
| 键名语义 | 沿用 InputControl：单字符 / NAMED_KEYS 命名键 / 多字符和弦 |

#### 3.2 actions/输入/鼠标.py —— 鼠标点击

| 项 | 内容 |
|---|---|
| name / description | `鼠标点击` / 在坐标处模拟鼠标左键点击 |
| 输入类 | `x: "number" = 0`、`y: "number" = 0`、`按住时长: "number" = 0.05`、`素材图片: "image" = ""` |
| 输出类 | 空 |
| run() | `InputControl().mouse_click(x, y, 时长 if 时长 > 0 else None)`，返回 1。**素材图片不参与执行**（纯编辑期辅助） |

**自定义视图（重写 `info_widget`）**，自上而下：

1. **提示标签**（固定文字）：「自定义视图中的预览图的画面是通过读输入GUI的参数来生成」——告知用户预览图由输入 GUI 参数（素材图片槽）驱动。
2. **标注预览图**（QLabel 缩略图）：
   - 数据源 = 读取本步骤 io 的「素材图片」输入槽（`{{变量}}` → 变量树取实际字节 → QPixmap 缩放）。
   - 槽为空/未引用/资源缺失 → 占位图（灰底「无素材」）。
   - 标注完成后显示**带红点的标注图**（内存中 QImage，不回写 assets；仅当素材槽未变时保持）。
   - **点击预览图** → 用现有 `ImageOverlay` 打开大图查看（点击时的当前画面）。
   - **刷新时机**：订阅 `step.io.add_listener`（组件 2）——素材图片槽变化即重建预览。
3. **「设置点位」按钮**：
   - 解析素材图片槽 → 实际字节；槽为空/非法/变量缺失 → `QMessageBox.warning` 提示，数据不动。
   - 调 `tools.image_marker.mark_image(图片字节, "dot")` → 返回 `(标注图, PointTimeline | None)`；None（取消/尺寸超屏）→ 不改数据。
   - 成功：取第一个点 `(x, y)`，经 `step.io.change_value("input", 0, str(x))` 与 `("input", 1, str(y))` 写回 x/y 输入槽——输入 GUI 自动同步（现有 `_live_widgets` 机制），标注图更新到预览。

#### 3.3 actions/控制流程/输出日志.py —— 输出日志

| 项 | 内容 |
|---|---|
| name / description | `输出日志` / 向日志面板输出一条信息 |
| 输入类 | `消息: "string" = ""` |
| 输出类 | 空 |
| run() | `LogModel.instance().info(消息)`，返回 1 |

#### 3.4 模板注册

- `actions/__init__.py` 静态 import 登记三个新步骤（沿用现有模式）。
- 三个模板文件 import `libs.key_control`（鼠标/按键）与 `model` 包——与应用内其它模板同假设：KScript 应用环境可解析（sys.path 含项目根）。

### 组件 4：执行器（model/step_runner.py + model/hotkey.py）

#### 4.1 StepRunner（纯 Python，无 Qt / 无 pynput）

```
StepRunnerState = Enum: READY / RUNNING / STOPPING
```

```
class StepRunner:
    def __init__(self, store: StepListStore)
    def start(self) -> None                 # 仅 READY 可调用；否则 RuntimeError
    def request_stop(self) -> None          # RUNNING/STOPPING 置停止事件；其余静默
    def add_state_listener(cb: Callable[[StepRunnerState], None])
    @property state
```

- **start()**：
  1. 复位：遍历 store 全部列表的全部步骤（含 enabled=False 的），`status = PENDING`（触发各自的 Step 状态监听 → UI 变回待机色）。
  2. `prog = store.all_do_methods()`（插入序 DFS，enabled 过滤——已由模型层实现）。
  3. 状态 → RUNNING，通知状态监听者。
  4. 工作线程（daemon）执行循环（见下）；循环结束 → 状态回 READY，通知。
- **执行循环**（PC = 程序计数器）：
  ```
  pc, steps_done = 0, 0
  while pc < len(prog) and not stop_event.is_set():
      steps_done += 1
      if steps_done > MAX_STEPS:           # 死循环保护（偏移 0/负值）
          LogModel.error("执行步数超过上限…"); break
      try:
          offset = prog[pc]()              # do() 内部：input → run → output；异常已置 ERROR + 日志 + 重抛
      except Exception:
          break                            # 遇错停止整个执行（错误日志由 do() 记录）
      pc += offset
      if pc < 0: pc = 0                    # 负偏移回跳，最前钳到 0
  ```
- **request_stop()**：置 `threading.Event`，状态 → STOPPING，通知。协作式：当前 `do()` 结束后，循环条件在下一次检查时退出（**当前步骤完成后停止**）。
- **步数上限**：类属性 `max_steps = 10000`（冒烟测试可建小上限子类覆盖）。
- **线程安全**：状态读写经 `threading.Lock`；`start`/`request_stop`/监听者回调可在任意线程调用。
- 执行结束时（正常走完 / 停止 / 错误 / 超限）状态统一回 READY；步骤状态保持现场（FINISHED/ERROR 的颜色留作结果展示），下次 start() 再复位。

#### 4.2 HotkeyListener（model/hotkey.py，唯一 import pynput 的模块）

```
class HotkeyListener:
    def __init__(self, hotkey: str, on_toggle: Callable[[], None])
    def start(self) -> None                 # 启动 pynput keyboard.Listener（后台线程）
    def stop(self) -> None                  # 停止监听
```

- `on_press` 回调：`getattr(key, 'char', None) == hotkey` → `on_toggle()`。
- 回调发生在监听线程——UI 侧必须经 Qt 信号跨线程桥接（见组件 6）。
- **已知限制（文档 + tooltip 提醒）**：pynput 监听器会捕获 key_click 模拟的按键（实测确认）；热键与步骤模拟的按键字符冲突时会误触发停止。用户自选热键时提示避开步骤用键。

### 组件 5：热键配置（model/settings.py + setting.json）

```
class Settings:
    @classmethod load(cls, path=None) -> Settings   # 默认 <应用目录>/setting.json；不存在 → 默认值
    def save(self, path=None) -> None               # 原子写（mkstemp + os.replace）
    @property hotkey: str                           # 默认 "`"
    def set_hotkey(self, key: str) -> None          # 校验：单字符 str（含数字），否则 ValueError
```

- `setting.json` 形态：`{"hotkey": "`"}`。
- 热键**不**存进 .kscp（本地配置，各机器各自绑定）。

### 组件 6：执行 UI 接线（widgets/main_widget.py）

- **工具栏「执行」按钮**：
  - 未监听：点击 → `HotkeyListener.start()` + 状态栏「待命：按 X 执行/停止」；按钮文本变「停止监听」。
  - 已监听：点击 → 停监听（若 RUNNING 先 `request_stop()` 等其自然结束），按钮复原。
- **热键 toggle 事件** → 若 runner READY → `start()`；若 RUNNING/STOPPING → `request_stop()`。
- **状态栏执行器指示**：待命（热键提示）/ 运行中 / 停止中 / 已停止。
- **跨线程桥接**：main_widget 建 QObject 桥（`pyqtSignal` 转发 runner 状态、步骤状态、热键事件），回调线程 emit → Qt 自动 queued 到 GUI 线程刷新。
- **卡片颜色实时刷新**：执行前 main_widget 给每个步骤 `add_status_listener` → 桥 → 对应卡片/视图重检颜色（现有 StepCard.refresh 体系）。执行结束移除监听。
- **执行期间锁定编辑**：RUNNING/STOPPING 时禁用步骤列表树、变量树、卡片视图（`setEnabled(False)`）；回到 READY 恢复。
- **热键设置 UI**：工具栏输入框（点击后按任意键绑定）→ `Settings.set_hotkey` + `save`；tooltip 注明「热键勿与步骤按键冲突（模拟按键也会被监听）」与「模拟输入到游戏窗口需管理员运行」。

## 4. 校验与错误表

| 场景 | 行为 |
|---|---|
| 热键非法（非 str / 长度≠1） | `Settings.set_hotkey` ValueError；UI 提示 |
| READY 外调用 `start()` | RuntimeError |
| 非运行态 `request_stop()` | 静默忽略 |
| 执行步数 > MAX_STEPS | LogModel.error + 停止执行 |
| 步骤 do() 抛异常 | 状态 ERROR + 日志（do() 内部）+ 停止整个执行 |
| 按键步骤键名为空 | ERROR + 日志，返回 1（不抛异常） |
| 鼠标点击「设置点位」时素材槽空/非法/缺失 | QMessageBox 提示，数据不动 |
| mark_image 返回 None（取消/尺寸超屏） | 数据不动 |
| 执行器执行时热键冲突（步骤模拟了热键字符） | 误触发停止——文档/tooltip 提醒，用户规避（已实测 pynput 行为，采用提醒方案） |
| setting.json 损坏 | load 捕获 → 回退默认值 + 日志警告 |

## 5. 测试（TDD 冒烟清单）

每个模块 `python -m xxx` 冒烟，先 RED 后 GREEN：

1. **model/settings**：默认值、读写往返、非法热键拒绝、损坏文件回退默认。
2. **model/step_io**（扩展）：`add_listener` 收到 change_value 与 GUI 编辑两路变更；移除后不通知；监听者异常不中断写入。
3. **model/step_runner**：假步骤列表（do 返回 1/2/0/-1/抛异常）验证——
   - 顺序执行与偏移跳转（2 跳一步）；
   - 负偏移回跳与 pc<0 钳制；
   - 偏移 0 死循环 → MAX_STEPS 上限停止（用小上限子类或注参）；
   - request_stop 协作式停止（长步骤中途请求 → 当前步骤完成后退出）；
   - 遇错停止；状态流转 READY→RUNNING→(STOPPING)→READY 与监听者通知；
   - start() 复位全部步骤 PENDING；READY 外 start() → RuntimeError。
4. **actions/输入/按键**：槽类型推导 `["string","number"]`/`[]`；run 用**桩替换 InputControl**（冒烟不得真实按键——模板文件提供模块级 `_new_control()` 工厂供替换）验证 key_click 参数、空键名报错、格式化串往返。
5. **actions/输入/鼠标**：槽推导 `["number","number","number","image"]`/`[]`；run 桩验证 mouse_click 参数；`info_widget` 构造断言（提示标签文字、预览控件、设置点位按钮存在）；预览随素材槽变化刷新（改 `change_value` → 断言预览更新）。
6. **actions/控制流程/输出日志**：run 后 LogModel 出现对应 info 条目；格式化串往返。
7. **model/hotkey**：构造与非法热键校验冒烟（真实键盘监听不自动化）。
8. **widgets/main_widget**：执行按钮状态流转（直接调 runner API 驱动，不依赖真实热键）、执行期间锁定编辑生效与恢复、状态栏文本。
9. 全量回归：全部既有冒烟 + `main.py sample.kscp --check`。

## 6. 非目标（明确不做）

- 日志级别参数（输出日志固定 info）。
- 组合键热键（Ctrl+X 等）。
- 注入键过滤（底层钩子方案，用户已选「文档提醒」）。
- 暂停/恢复、执行进度条。
- 鼠标滚轮/拖动/长按步骤（后续按需）。
- PipeController 指令模式内嵌。
- 素材图片参与 run()（纯编辑辅助）。
