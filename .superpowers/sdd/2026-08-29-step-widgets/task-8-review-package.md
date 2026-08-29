# Task 8 review package — 优化 1(自动显示第一个列表)+ 优化 2(右键新建空列表)

- 任务:用户新需求两条(裁定:①显示卡片 + 树中选中 ②与添加一致的 4 位置子菜单)
- 变更文件:`widgets/step_list_tree_widget.py`、`widgets/main_widget.py`(各含冒烟块)
- 非 git 适配:无 BASE/HEAD;下方磁盘现状为控制器已核对(行号与报告一致)。

## 实施者报告摘要

- 状态 **DONE**;两条优化各 TDD(RED:AttributeError first_list_path / _act_new_empty_list → GREEN);全量回归 17/17 全绿;T7 空 store 占位断言原样通过。
- 前提修正(重要):树上**无既有**「添加步骤列表」4 位置菜单(该模式在 step_list_view.py 是步骤级:头部=_add_step(0)/尾部=_add_step(-1)/前方/后方=卡片下标);实施者把视图菜单位置语义原样映射到树:位置 = 右键所在组 store 字典序(walk/执行序;树显示恒按名排序),前方/后方仅右键列表叶子可用。
- Concern:① `store._root` 直接访问(store 无插入 API 且 step_list_store.py 不可改,重建父字典定位插入,已加注释)② 位置语义 = store 序而非树显示位(树显示恒按名排序,既有裁定)③ 前方/后方仅列表可用(与视图形态一致)④ 懒构建接线(先 preview_widget 再 setCurrentItem)。

## 磁盘现状

### 优化 1 — `step_list_tree_widget.py` :136-155
```python
    def first_list_path(self) -> Optional[str]:
        """树显示顺序下深度优先先序遍历遇到的第一个列表路径；无列表 → None。

        复用 :meth:`_children_of` 的排序逻辑（组在上、列表在下、每层按名排序），
        与 :meth:`_fill` 构建顺序一致；store 的 ``walk()`` 是插入序，与显示序不同。
        """
        return self._first_list("")

    def _first_list(self, prefix: str) -> Optional[str]:
        """``prefix`` 子树内显示序第一个列表（组先递归、再列表，逐层按名排序）。"""
        dirs, leaves = self._children_of(prefix)
        for name, _is_group in dirs:
            sub = name if not prefix else prefix + "/" + name
            found = self._first_list(sub)
            if found is not None:
                return found
        if not leaves:
            return None
        name = leaves[0][0]
        return name if not prefix else prefix + "/" + name
```

### 优化 1 — `main_widget.py` :689-698(_open_package,`tree_changed.connect(refresh_cards)` 之后、`_manage_btn` 之前)
```python
        # 进入工程第一画面：store 非空 → 自动选中第一个步骤列表（显示序 DFS 首个列表）
        # 树/宿主均为懒构建 → 先构建再选中；宿主须在联动前构建，否则列表不显示
        sl_tree = sl_mgr.tree_widget()
        assert isinstance(sl_tree, StepListTreeWidget)
        sl_mgr.preview_widget()
        first_path = sl_tree.first_list_path()
        if first_path:
            item = sl_tree._find_item(first_path)
            if item is not None:
                sl_tree.setCurrentItem(item)   # 触发 list_selected → 宿主显示
```

### 优化 2 — 菜单 `step_list_tree_widget.py` :202-246(摘)
- 「添加组…」之后新增子菜单「新建空列表」= 头部/尾部 + 分隔 + 前方/后方;`anchor` = 右键项为列表叶子(非组)时非 None → 前方/后方 `setEnabled(anchor is not None)`;分发:`头部 → _act_new_empty_list(context_group, 0)`、`尾部 → (context_group, None)`、`前方 → (context_group, _sibling_index(anchor))`、`后方 → (context_group, _sibling_index(anchor) + 1)`。

### 优化 2 — `_act_new_empty_list` + `_sibling_index` :307-342
```python
    def _act_new_empty_list(self, context_group: str = "",
                            index: Optional[int] = None) -> None:
        """新建空列表：无步骤的 :class:`StepList`，插入到 ``context_group`` 内指定位置。

        位置语义与视图「添加步骤」一致：头部=0 / 尾部=None（追加）/
        前方=锚下标 / 后方=锚下标+1。位置 = store 字典序（树显示恒按名排序，
        位置体现在 walk/执行序）；store 无插入 API → 重建父字典定位插入。
        """
        full = self._dedup_name(context_group, "新列表")
        node = self._store._root
        if context_group:
            for seg in context_group.split("/"):
                node = node[seg]               # 右键组为真实组 → 节点必为 dict
        name = full.rsplit("/", 1)[-1]
        sl = StepList.create_empty()
        if index is None or index >= len(node):
            node[name] = sl                    # 尾部追加（与 add_list 同语义）
        else:
            items = list(node.items())
            items.insert(max(0, index), (name, sl))
            node.clear()
            node.update(items)
        self._changed(full)

    def _sibling_index(self, path: str) -> int:
        """path 在父层字典序中的下标（「前方/后方」锚点定位；walk 序 = 字典序）。"""
        parent = path.rsplit("/", 1)[0] if "/" in path else ""
        idx = 0
        for p, _is_group in self._store.walk():
            pp = p.rsplit("/", 1)[0] if "/" in p else ""
            if pp != parent:
                continue
            if p == path:
                return idx
            idx += 1
        return idx
```

### 冒烟 — `step_list_tree_widget.py` :631-668
- store4 = 组甲(中列表/后列表) + 顶列表;4 位置各创建:头部 → walk `[组甲, 组甲/新列表, 组甲/中列表, 组甲/后列表, 顶列表]` + 空内容 + `_current_path() == "组甲/新列表"`;尾部 → `新列表(1)` 组甲末位;前方(锚=中列表,`_sibling_index == 1`)→ `新列表(2)` 插锚前;后方(下标 3)→ `新列表(3)` 插中列表后;根层混合头部 → 「新列表」根首位且不去重;`changes4 == 5`。

### 冒烟 — `main_widget.py` :834-866
- 新工程 tmp2:store 插入序 = [乙(空), 组甲, 组甲/丙(含 1 步)](walk 首位「乙」)→ MainWindow(tmp2) 构造后断言:`tw2.first_list_path() == "组甲/丙"`(显示序 DFS ≠ walk 序首位)、`host2.currentIndex() == 1`、`len(host2._view._cards) == 1`、`sl_mgr2._current == "组甲/丙"`、`host2._view._step_list is sl_mgr2._store.get("组甲/丙")`。

## 评审焦点(控制器预判,独立验证)

1. `first_list_path` 与 `_fill` 显示序一致性(独立核对 `_fill` 只经 `_children_of` 构建;DFS 先组后列表 = 用户所见)
2. `_open_package` 接线:链路 setCurrentItem → currentItemChanged → `_on_current_changed`(store.get 成功才 emit)→ list_selected → `_on_list_selected` → 宿主 set_list;空 store no-op;宿主先构建(preview_widget)的正确性
3. 优化 2 前提修正:树上确无「添加步骤列表」菜单;位置语义映射到 store 字典序是否忠实于用户裁定意图(用户裁定「与添加一致:4 位置子菜单」系基于控制器错误的既有前提,实施者的映射为唯一合理路径?);前方/后方仅列表叶子是否合理
4. `_act_new_empty_list` 的 `store._root` 直访:组路径下行(node[seg] 必为 dict)、头部 0/尾部 None/前方/后方下标与 `_sibling_index`(walk 序)对齐(含子组混排场景的计数一致性——父层项含组时 walk 序与 dict 键序一致)、`_dedup_name` 同父去重、`_changed(full)` 收尾链路
5. 冒烟断言真实性(walk 序精确断言、去重、changes 计数、显示序≠walk 序)
6. 既有兼容:T7 空 store 占位断言原样、T5 全部断言未改

## 当前文件

- `widgets/step_list_tree_widget.py`(670 行):first_list_path :136-155、_on_context_menu :197-246、_act_new_empty_list :307-329、_sibling_index :331-342、冒烟 :631-668
- `widgets/main_widget.py`(868 行):_open_package :689-698、冒烟 :834-866
- 上下文:`_children_of` :124-134(sorted(dirs) + sorted(leaves))、`_fill`(树构建,读 :110-125 区域核对仅用 _children_of)、`_dedup_name`、`_group_of`、`_is_group`、`_changed`、`_on_current_changed` :186-194、`StepListManagementTree` :213-276
