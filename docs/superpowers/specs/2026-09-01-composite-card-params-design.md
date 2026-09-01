# 合成卡片输入/输出参数 — 设计

> 日期：2026-09-01
> 状态：已实现（2026-09-01）；见 plans/2026-09-01-composite-card-params.md
> 关联：`2026-08-31` 合成卡片树 v1（参数 less，纯操作全局变量）；本设计为 v1 的增量扩展。

## 0. 背景与目标

v1 合成卡片是「无参的、纯操作全局变量」的可复用步骤集合：定义体是一个命名 `StepList`，
调用点以引用标记 `@合成卡片:<path>` 存放，运行时展开执行。痛点：同一逻辑要对不同变量
操作时，只能复制整张卡片或靠全局变量做隐式传参——复用性受限。

本设计给合成卡片加**输入/输出/局部参数**（函数语义）：调用点绑定入参（值或 `{{变量}}`）
与出参目标变量；运行期 body 在**纯局部作用域**内执行，看不到全局变量；出参值写回调用方
绑定的目标。三段（输入/输出/局部）互不兼任。

**核心决策（已与用户确认）**：

1. **作用域 = 纯局部**（无全局回退）：体内步骤只解析局部树；全局交互**只能**经参数
   （入参快照进、出参写回出）。v1 参数 less 合成卡片不受影响（body 仍走全局树）。
2. **局部机制 = 每个带参调用点实例配自己的 `VariableTree`**（运行期局部树），经
   `CompositeCard.run` 内临时换体内步骤的 `io._tree` 实现。**不**给全局 `VariableTree`
   加 `parent` 回退（把「局部」概念限定在合成卡片，不动核心）。
3. **声明 = 专用签名表**（purpose-built）：输入/输出/局部三段，每行 `名/类型`（局部多
   `默认值`）。调用点 io 直接复用 `StepIOWidget`，零新绑定 UI。
4. **body 选择器含「新建局部变量…」快捷入口**：绑定时就地新建局部 → 加进签名表局部段
   + 立刻绑定。

## 1. 模块布局（数据模型 ⇄ 窗口 解耦）

一切以易维护为主：数据模型层无 Qt 顶层依赖（仅 `info_widget` 内懒导入）；窗口层经**接口**
操作模型，不触 `StepIOWidget`/`StepCard` 内部。两层经 `io.picker` 钩子与 `CompositeCardStore`
解耦缝衔接。

```
model/（无 Qt 顶层依赖）
  composite_signature.py    [新]  Param/LocalVar/CompositeSignature — 纯数据 + to/from_json
  composite_definition.py   [新]  CompositeDefinition(body, signature) — 纯数据
  composite_local_tree.py   [新]  build_local_tree(sig, package) → VariableTree（运行期局部树工厂）
  composite_card_store.py   [改]  节点类型 StepList → CompositeDefinition；composites.json 扩 sig
  composite_card.py         [改]  带真实 io、marker 含 io、input/run/output 覆写、局部树换树

widgets/（依赖 model 接口）
  composite_signature_widget.py  [新]  3 段表编辑器，读写 CompositeSignature，发 signature_changed
  composite_local_picker.py       [新]  make_composite_local_picker(sig, on_new) → picker 闭包
  composite_tree_widget.py       [未改]   v2 不改——签名表不挂这里（见下方注）
  management_trees.py             [改]  CompositeManagementTree：装配签名表 + body 宿主 + 换 picker
  step_list_view.py               [未改] 调用点选合成卡片仍走 v1 的 TemplateChooser；body 选择器经 io.picker 钩子替换，v2 不触本文件
```

> 注（2026-09-01 实现核对）：`composite_tree_widget.py` 对 v2 **未改动**。真正的签名编辑器
> `CompositeSignatureWidget` 挂在 `CompositeManagementTree.preview_widget()` 返回的**容器**上
> （上 = 签名表、下 = `StepListHost`），而非树控件里——故原计划的「签名表挂载点」落到了
> `management_trees.py`，`composite_tree_widget.py` 维持 v1 不变。

**解耦缝**：

- `StepIOWidget.picker`（`picker(tree, vtype, parent) → 名|None`）—— `StepIOWidget` 只调钩子；
  `composite_local_picker` 闭包操作 `CompositeSignature`。`StepIOWidget` 完全不知「合成卡片」存在。
- `CompositeSignatureWidget` 只发 `signature_changed` 信号；`CompositeManagementTree` 负责落盘
  `composites.json` + 刷新 body 选择器 + 改指 body 内引用。widget 不触持久化。
- `CompositeCard` 经 `CompositeCardStore.get` 取 `CompositeDefinition`、经 `build_local_tree` 建局部树，
  不碰 widget。

## 2. 数据模型

### 2.1 类型

```python
@dataclass
class Param:
    name: str          # 参数名（合成卡片体内引用名）
    type: str          # 已注册变量类型名（"number"/"string"/"image"/...）

@dataclass
class LocalVar:
    name: str
    type: str
    default: Any       # 局部初始值（ProjectVariable.create(type, default, pkg)）

@dataclass
class CompositeSignature:
    inputs: List[Param]
    outputs: List[Param]
    locals: List[LocalVar]   # 三段互不兼任
    # 只读视图
    def input_types(self) -> List[str]:  ...
    def output_types(self) -> List[str]: ...
    def slot_names(self) -> List[str]:   ...   # inputs+outputs+locals 全名（供选择器列出）
    # 序列化
    def to_json(self) -> dict: ...
    @classmethod
    def from_json(cls, d) -> "CompositeSignature": ...
    # 校验：类型须已注册（type_of 不为 None）；名字段内唯一、跨段不重名；无 "/" 等非法字符

@dataclass
class CompositeDefinition:
    body: StepList                 # 体内步骤列表
    signature: CompositeSignature  # 参数签名
```

### 2.2 持久化（`composites.json`）

v1 的 `_walk` 据「**列表值=卡片叶子、字典值=组**」判别叶子/组（`composite_card_store.py`
的 `_walk`：`list→StepList`、`dict→组`）。若把签名塞进叶子（叶子变 dict），就与「组=dict」
判别**冲突**——含名为 `body` 子卡的组会被误读成带参叶子。故签名**不**入叶子节点，改用
**包装结构**：树体保持纯 v1 形态（叶子恒为 list），签名作为平铺 `path → sig` 表旁挂。

```json
{
  "tree": {
    "组/卡片A": ["<step fmt>", ...],
    "组": { "子卡片": ["<step fmt>", ...] }
  },
  "sigs": {
    "组/卡片A": {
      "in":  [{"name": "x", "type": "number"}, ...],
      "out": [{"name": "y", "type": "number"}, ...],
      "loc": [{"name": "t", "type": "number", "default": 0}, ...]
    }
  }
}
```

- **v1 向后兼容**：v1 文件顶层直接是树（无 `tree`/`sigs` 键）。`from_json` 检测：
  顶层含 `tree` 键 → 新格式（取 `tree` 走 v1 树 + 读 `sigs`，缺 `sigs` 视为空）；否则 → v1，
  整顶层作树、签名全空。一旦落盘即升级为新格式（前向迁移，单向）。
- 叶子仍是 `list`（v1 不变）；签名经 `sigs[path]` 旁挂查表。无 `sigs` 条目的叶子 → 空签名
  （v1 行为）。这把「树结构」与「参数签名」彻底解耦，`_walk` 树逻辑零改动。

### 2.3 `CompositeCardStore` 改动（最小）

- 内存：`root`（树，同 v1：`StepList` 叶子 / `dict` 组）+ `sigs: Dict[str, CompositeSignature]`
  （平铺 path→签名，与树并行）。
- `_to_node`：输出 `{"tree": <v1 树节点>, "sigs": {path: sig.to_json() ...}}`。
- `_walk`：检测包装（顶层含 `tree` → 取 `tree` 走 v1 树 + 读 `sigs`；否则整顶层作 v1 树、
  `sigs={}`）。**树体 `_walk` 逻辑不变**（`list→StepList` 叶、`dict→组`）——这是本方案的核心收益。
- `add_list(path, body, signature=CompositeSignature.empty())`：写树叶子 + `sigs[path]=signature`。
- `get(path) → CompositeDefinition(body=<树叶子>, signature=sigs.get(path, 空))`；
  便捷 `get_body(path) → StepList`（v1 调用方）、`get_signature(path) → CompositeSignature`。
- `rename`/`remove`：**除树操作外**，同步更新 `sigs`（rename 迁移 path 键、remove 删键）——
  签名随卡片走。`walk`/`paths` 不变（仍按树）。
- `get_or_none(ref)`（运行期解析器）返回 `CompositeDefinition`（调用方取 `.body`/`.signature`）。

## 3. CompositeCard（调用点步骤）

### 3.1 marker 格式

```
@合成卡片:<ref>            # v1 参数 less（无 :io，空 io，body 走全局树）
@合成卡片:<ref>:<io_b64>    # 带参：<io_b64> = StepIOWidget 格式串（base64，含 iv/ov 绑定值）
```

- `is_marker(fmt)`：`startswith("@合成卡片:")`（不变）。
- `marker_for(ref, io_fmt=None)`：`@合成卡片:<ref>` + (`:<io_fmt>` 若非空)。
- `from_marker(fmt, manager)`：
  1. 解 `ref` 与可选 `io_fmt`；
  2. 经解析器取 `CompositeDefinition` → `signature`；
  3. **以签名为准**建 `StepIOWidget(input_types=sig.input_types(), output_types=sig.output_types(), tree, package)`，
     再用 `io_fmt`（若存在）回填 `input_values`/`output_values`（类型以签名，值取自 marker；
     `io_fmt` 内 `it/ot` 与签名不符时按签名覆盖，`iv/ov` 保留——签名漂移容忍）；
  4. 返回 `CompositeCard(ref, sig, io, manager.tree, manager.package)`。
- `to_format_string()`：`marker_for(self.ref, self.io.to_format_string())`（空 io → 无 `:io`，v1）。

### 3.2 `CompositeCard.__init__`

```python
def __init__(self, ref, signature, io, tree, package, enabled=True, tag=""):
    super().__init__(io, enabled, tag)
    self.ref = ref
    self.signature = signature          # CompositeSignature（类型视图供运行期建树）
    self.name = ref.rsplit("/",1)[-1] if ref else "合成卡片"
    self._global_tree = tree           # 出参写回目标全局树
    self._package = package
    self._local_tree: Optional[VariableTree] = None   # 运行期局部树（input 建并填、output 读后清）
```

- 参数 less（空签名）：`input_class=output_class=_NoIO`（空 io），行为同 v1（`run` 不换树、body 走全局）。
- 带参：io 由 `from_marker` 按签名建（非空 input_type/output_type）。

> 注（2026-09-01 实现核对）：构造器**向后兼容** —— 实际签名为
> `__init__(self, ref, tree, package, signature=None, io=None, enabled=True, tag="")`。
> `tree` 在 `signature`/`io` 之前（非原计划的第 4 参）；`signature` 缺省 `CompositeSignature.empty()`、
> `io` 缺省为「空签名 io」（`StepIOWidget([], [], tree, package)`），故 v1 调用
> `CompositeCard(ref, tree, package)` 仍成立。

### 3.3 执行流程（覆写 input/run/output）

```
input():                            # ① 解析入参 → 建局部树 → 填入参
    if not self.signature: return                 # 空签名 → no-op（v1：body 走全局树）
    values = self.io.resolve_inputs()              # 解析调用点绑定的入参（值/变量引用）
    self._local_tree = build_local_tree(self.signature, self._package)
    # 局部树已含全部 inputs/outputs/locals（locals 填 default、outputs 填默认空）
    for p, val in zip(self.signature.inputs, values):
        self._local_tree.set(p.name, ProjectVariable.create(p.type, val, package))  # 入参快照
run():                              # ② 换树 → 跑 body → 恢复
    defn = CompositeCard.resolve_ref(self.ref)     # CompositeDefinition
    if defn is None: → 悬空（同 v1：记日志、ERROR、返回 1）
    深度守卫（threading.local，上限 32，同 v1）
    body = defn.body
    if not self.signature:                         # 空签名 → 不换树，body 走全局（同 v1）
        <mini pc+偏移循环：复位 PENDING、prog=body.do_methods()、_MAX_SUB_STEPS、_stop_event>
        return 1
    saved = [s.io._tree for s in body.steps]
    for s in body.steps: s.io._tree = self._local_tree   # 换树
    try:
        <mini pc+偏移循环：复位 PENDING、prog=body.do_methods()、_MAX_SUB_STEPS、_stop_event，同 v1>
    finally:
        for s, t in zip(body.steps, saved): s.io._tree = t   # 必恢复（即使 body 抛错）
    return 1
output():                           # ③ 读出参 → 写回调用方绑定目标
    if not self.signature: return                 # 空签名 → no-op（v1）
    outs = [self._local_tree.get(p.name) for p in self.signature.outputs]
    self.io.write_outputs([v.data for v in outs])   # write_outputs 写回 io._output_values 指定的全局目标（类型校验内置）
    self._local_tree = None
```

- 参数 less（空签名）：三阶段均 no-op（`_local_tree` 不建）；`run` 直接跑 body（body 步骤 `io._tree` 仍是全局树，不换）——**完全同 v1**。

### 3.4 `CompositeCard.set_resolver` / `resolve_ref`

- 解析器仍由主窗口打开工程时注入：`CompositeCard.set_resolver(cstore.get_or_none)`。
  返回值由 `StepList`（v1）改为 `CompositeDefinition`。`run` 取 `.body`、`from_marker` 取 `.signature`。
- 递归守卫、协作停止（`_stop_event`）、`_MAX_SUB_STEPS` 均同 v1，不变。

## 4. 运行期局部作用域（纯局部）

- `build_local_tree(sig, package)`：建一棵普通 `VariableTree`，按 sig.locals 填默认值、sig.outputs
  填类型默认空值（入参由 `input()` 后填，不预填）。返回局部树。
- **无 parent / 无 merged 适配器**：body 步骤 `resolve_inputs`/`write_outputs` 直走 `self._local_tree`。
  体内若引用了不在局部树的名字（如误填全局名）→ `resolve_inputs` 抛 `FileNotFoundError` → body 步骤
  `do()` 置 ERROR（同普通步骤解析失败）。
- **换树安全**：`StepRunner` 单线程 pc+偏移；`CompositeCard.run` 同步换-跑-恢复。递归（A→B→A）
  有深度上限 32，且各合成卡片 body 是不同 `StepList` 实例，不互踩 `_tree`。`try/finally` 保证恢复。
- **编辑期**：body 步骤 `io._tree` 仍是全局树（`from_format_strings` 建时设）；编辑期 body 选择器
  只列局部参数（见 §5），从源头杜绝引用全局。

## 5. 编辑器 UI

### 5.1 装配（`CompositeManagementTree`）

- `preview_widget()` = 容器（`QWidget` + `QVBoxLayout`）：上 `CompositeSignatureWidget`、下
  `StepListHost(body)`（复用现有 host）。
- 建 body 宿主时，把 body 视图步骤的 `io.picker` 设为
  `make_composite_local_picker(self._current_signature(), on_new=self._on_new_local)`。
- `CompositeSignatureWidget.signature_changed` → `CompositeManagementTree`：
  1. `self._cstore` 改指（签名是定义的一部分，落 `composites.json`）；
  2. 改名/删参数时，遍历 body 步骤 io 槽，改指/清空引用旧参数名的绑定（同 `repoint_refs` 套路）；
  3. 重建 body 选择器（picker 闭包捕获新签名）+ 刷新卡片。

### 5.2 签名表 `CompositeSignatureWidget`

- 3 段表（输入/输出/局部），每行：`名`(QLineEdit) / `类型`(下拉：`supported_types()`) /
  局部多 `默认值`(QLineEdit)。每段「+」增行、「-」删行。
- 改名：旧名 → 新名，发 `signature_changed`，宿主改指 body 内引用。
- 改类型：发 `signature_changed`，宿主重建 io 类型（调用点 marker 的 `iv/ov` 保留，类型按新签名）。
- 校验：类型须已注册；段内名唯一、跨段不重名；无 `/`（参数名不分组）。非法行红色提示，
  `signature_changed` 不发（不落盘非法态）。

### 5.3 局部选择器 `make_composite_local_picker`

```python
def make_composite_local_picker(signature: CompositeSignature,
                                 on_new: Callable[[str, str, Any], None]) -> Callable:
    """返回 picker 闭包，符合 io.picker 钩子签名 (tree, vtype, parent) → 名|None。

    弹菜单：列出 signature 中类型匹配 vtype 的 inputs/outputs/locals（标「入参/出参/局部」），
    + 末项「新建局部变量…」。选中 → 返回名；新建 → 弹 名/类型/默认值 → 调 on_new(name, type, default)
    （宿主加进 signature.locals 并发 signature_changed）→ 返回 name。
    tree 参数忽略（纯局部，不经全局树）。
    """
```

- 类型过滤：只列 `ProjectVariable.type_of(名).name == vtype` 的槽位。
- 「新建局部变量…」的默认类型预填为当前槽位 `vtype`，默认值按类型给空合理值。
- 新建后宿主加进 `sig.locals` → 签名表局部段也同步出现该行（`signature_changed` 刷新签名表）。

### 5.4 body 卡片视图

- body 步骤的 `StepCard` 与普通步骤完全一致（`info_widget` + `io.gen_widget`）。仅 `io.picker`
  被换为局部选择器——`StepCard`/`StepIOWidget` 不改。
- 输入槽绑定 = 局部选择器选参数名；输出槽绑定 = 同（写出参/局部）。值显示为参数名（如 `x`），
  非 `{{x}}`（参数名直接是局部树路径）。

## 6. 向后兼容 + 错误处理

- **v1 参数 less 合成卡片**：无 `sig`（或空签名）→ 空 io → marker `@合成卡片:<path>` →
  `run` 不换树、body 走全局树（同今天）。`from_marker` 见空签名走 v1 路径。
- **类型校验**：调用点 `io` 用签名 `input_type`/`output_type`；`write_outputs` 内置类型校验
  （调用方绑错类型目标 → ERROR，同普通步骤）。
- **签名漂移**：定义签名改了，旧 marker 的 `iv/ov` 与签名类型不符 → `from_marker` 按签名重建 io
  （`iv/ov` 尽量保留；类型不符的 `ov` 目标置空 → 调用点卡片红色「输出槽未指定变量名」，可定位、
  不崩）。见 §3.1 step 3。
- **悬空引用 / 递归**：同 v1（解析失败记日志、置 ERROR、软跳过；深度上限 32）。
- **换树异常**：`run` 内 `try/finally` 保证 `io._tree` 必恢复（即使 body 抛错、stop_event 置位）。
- **编辑期改名/删参数**：宿主经 `repoint_refs` 套路改指 body 内引用；若删的参数仍被某 body 步骤引用
  → 该引用悬空（`resolve_inputs` 抛 `FileNotFoundError` → 该步骤 ERROR）——签名表删行时弹确认。

## 7. 测试

新增/扩展 `__main__` 冒烟：

- `model.composite_signature`：`to/from_json` 往返；三段独立性；类型/名字校验（非法类型、重名、`/`）。
- `model.composite_card`（扩展）：带参 marker 往返（`@合成卡片:p:<io>`）；`do()` 端到端
  （入参→body 体内步骤用入参→出参写回调用方绑定目标）；纯局部（body 内步骤引用全局 → ERROR）；
  换树 `try/finally` 恢复（body 抛错后 `io._tree` 复位）；签名漂移重载（旧 marker + 新签名 → 不崩）；
  v1 参数 less 回归（空签名 → 行为同今天）。
- `model.composite_card_store`（扩展）：存 `CompositeDefinition` 往返；v1 无 `sig` 兼容回读。
- `model.composite_local_tree`：建树含 locals 默认值、outputs 默认空；入参后填。
- `widgets.composite_signature_widget`：3 段增删改名改类型 → `signature_changed`；非法行不发信号。
- `widgets.composite_local_picker`：类型过滤列表正确；「新建局部变量」→ `on_new` 回调 + 返回名。
- `widgets.management_trees`（扩展）：带参合成卡片装配（签名表 + body 宿主 + picker 换成局部选择器）；
  改名参数 → body 内引用改指。
- `widgets.main_widget`（扩展）：带参合成卡片端到端（建卡 → 声明签名 → body 用参 → 步骤列表引用 →
  执行 → 出参写回）。
- `tests/smoke_all.py`：登记 `model.composite_signature`、`model.composite_definition`、
  `model.composite_local_tree`、`widgets.composite_signature_widget`、`widgets.composite_local_picker`。

## 8. 文档更新（要求 2）

实现完成后更新：

- `docs/工程分析.md`：合成卡片章节补「输入/输出/局部参数（纯局部作用域）」。
- `docs/superpowers/specs/2026-09-01-composite-card-params-design.md`：本 spec。
- 旧合成卡片 spec（若有「v1 无参」措辞）：补「v2 带参」指向本 spec。
- `README`（若有合成卡片章节）：同步。
- `.claude/skills/adding-an-action`（若提及合成卡片）：补带参合成卡片声明流程（签名表 + 局部选择器）。
- 顶层 `actions/__init__.py` 相关注释（若涉及）：无改动（合成卡片非 action 模板）。

## 9. 风险与回退

- **换树侵入性**：`io._tree` 是 `StepIOWidget` 私有属性，运行期临时换——`try/finally` 严格保护恢复。
  替代方案（给 `VariableTree` 加 `parent`）作 core 变更，本设计**不采**（局部概念限合成卡片）。
- **签名漂移**：旧工程带参合成卡片若签名被改，调用点 io 类型重建——极端情况下值丢失（置空），
  红色卡片可定位、不崩。
- **body 引用悬空**：删参数后 body 引用悬空 → ERROR（同普通步骤解析失败）——签名表删行确认提示。
