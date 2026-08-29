# Task 5 fix round 1 — scoped re-review package

- 任务:widgets/step_list_tree_widget.py(StepListTreeWidget,新建于 T5)
- 修复轮次:1/5(恢复原实施者)
- 变更文件(唯一):`widgets/step_list_tree_widget.py`
- 非 git 适配:无 BASE/HEAD 可 diff;下方「变更区域 before/after」为修复前后对照(旧文 = T5 评审所见简报逐字代码;新文 = 磁盘现状,已核实)。

## Findings under verification(上一评审的 Important #1,逐字核心句)

> Multi-select copy/cut mismatch causes data loss — plan-mandated — widgets/step_list_tree_widget.py:262-268, 290-296. `_act_copy` copies only `tops[0]` into the clipboard while `_act_cut` then removes **all** `tops`. With `ExtendedSelection` (line 77) and the context menu enabling 复制/剪切 for any non-empty selection (lines 203-204), a user who selects two lists and hits 剪切 loses the second item permanently — the clipboard holds only the first, violating the global "剪切 = 复制 + 删除" constraint for multi-selection. Verbatim from the brief's Step 3 block — plan defect, not implementer error. Resolution belongs to the plan author: either copy all tops (multi-item clipboard payload) or restrict copy/cut to single selection.

控制器裁定(ledger 已记):spec §2 剪贴板契约 = 单条目 `(名, 三元组列表)` → 多条目载荷需改 spec 契约(重);修法 = 限制复制/剪切为单选(与「重命名仅单选」UI 模式一致)+ 入口守卫 + 覆盖冒烟。

## 变更区域 before/after

### 菜单启用(旧)
```python
        a_copy.setEnabled(bool(tops))
        a_cut.setEnabled(bool(tops))
        a_paste.setEnabled(self._clipboard.items is not None)
        a_rename.setEnabled(len(tops) == 1)
        a_delete.setEnabled(bool(tops))
```
### 菜单启用(新,step_list_tree_widget.py:193-197)
```python
        a_copy.setEnabled(len(tops) == 1)
        a_cut.setEnabled(len(tops) == 1)
        a_paste.setEnabled(self._clipboard.items is not None)
        a_rename.setEnabled(len(tops) == 1)
        a_delete.setEnabled(bool(tops))
```

### _act_copy 守卫(旧)
```python
    def _act_copy(self) -> None:
        tops = self._selected_paths_top()
        if not tops:
            return
        path = tops[0]
```
### _act_copy 守卫(新,:262-266)
```python
    def _act_copy(self) -> None:
        tops = self._selected_paths_top()
        if len(tops) != 1:
            return                       # 剪贴板单条目契约 → 复制限单选
        path = tops[0]
```

### _act_cut 守卫(旧)
```python
    def _act_cut(self) -> None:
        tops = self._selected_paths_top()
        if not tops:
            return
        self._act_copy()
```
### _act_cut 守卫(新,:290-294)
```python
    def _act_cut(self) -> None:
        tops = self._selected_paths_top()
        if len(tops) != 1:
            return                       # 剪切 = 复制 + 删除 → 与复制同限单选
        self._act_copy()
```

### 冒烟新增断言(step_list_tree_widget.py:534-547,位于 `print("StepListTreeWidget smoke OK")` 之前)
```python
    # 多选复制/剪切 = no-op（剪贴板单条目契约 → 复制/剪切限单选，防数据丢失）
    a = tw._find_item("打开软件")
    b = tw._find_item("清理体力/检查体力")
    assert a is not None and b is not None
    tw.setCurrentItem(a)
    a.setSelected(True)
    b.setSelected(True)
    assert len(tw._selected_paths()) == 2            # 选中集确含两项
    old_items = clipboard.items
    tw._act_copy()                                   # 多选复制 → no-op
    assert clipboard.items is old_items              # 剪贴板未被覆盖
    paths_before = sorted(store.paths())
    tw._act_cut()                                    # 多选剪切 → no-op
    assert sorted(store.paths()) == paths_before     # 未删除任何项
```

## 当前文件相关区域

- 全文件: `widgets/step_list_tree_widget.py`(550 行)——修复区域 :193-197、:262-266、:290-294、:534-547;其余区域与 T5 评审所见一致(评审已过),只关注 fix diff 波及处。
