# Task 4 报告:StepListView + TemplateChooserDialog + StepClipboard

日期:2026-08-29
状态:**DONE**
文件:`C:\Users\feelnn\Desktop\项目\KScript\widgets\step_list_view.py`(新建)

## 一、实现了什么

新文件 `widgets/step_list_view.py`,包含三个导出(`__all__ = ["StepClipboard", "StepListView", "TemplateChooserDialog"]`):

1. **`StepClipboard`**(纯数据):`steps: Optional[List[str]]`(步骤格式串)+ `items: Optional[tuple]`(T5 列表/组剪贴板预留)。跨列表存活,由宿主(管理树)持有注入。
2. **`TemplateChooserDialog(mgr, parent)`**:QTreeWidget 模板树按文件夹分组,叶子 `UserRole(0x0100)` = 模板路径;未选叶子(选组)→ `accept()` 被拒、确定按钮禁用;`selected_path()` 返回路径或 None;`exec_()` 正常可用。组图标 `QStyle.SP_DirIcon` 仅在 `self.style() is not None` 时设置(存根规避)。
3. **`StepListView(mgr, clipboard, parent)`**:QGraphicsView + QGraphicsScene,QGraphicsProxyWidget 横排 StepCard(间距 16,起点 (16,12),场景高 400);`set_list(step_list, mgr=None)` / `refresh()`(重建)/ `refresh_validity()`(仅逐卡 `card.refresh()` 重检颜色,不重建);滚轮垂直增量 → 水平滚动条(`wheelEvent`);卡片事件过滤(滚轮转发 + Enter/Leave 悬停缩放至 1.06/1.0 的 QVariantAnimation(160ms, OutCubic)+ 点击选中);右键菜单:空白处 = 头部/尾部添加 + 粘贴,卡片上 = 前方/后方添加 + 复制/剪切/粘贴 + 删除;`_add_step`(经 TemplateChooserDialog)/ `_copy` / `_cut`(= 复制 + 删除,剪贴板保留)/ `_paste`(经 `StepList.insert_format_strings` 事务性插入,ValueError → QMessageBox.warning)/ `_delete_step`(QMessageBox.question 确认);每次变更发 `edited` 信号;空列表显示提示文本 `_hint`(QGraphicsSimpleTextItem)。

冒烟块位于文件末尾 `if __name__ == "__main__":`,逐字来自简报(两处必要修正见下)。

## 二、TDD 证据

### RED(确认失败)

**第 1 次运行**(简报逐字转录原样):
```
Traceback (most recent call last):
  ...
  File ".../model/kscp_package.py", line 267, in write_file
    self._files[n] = bytes(data)
TypeError: string argument without an encoding
EXIT=1
```
失败原因 = 简报冒烟块 `pkg.write_file("actions/控制流程/延时.py", GOOD.replace(...))` 传的是 **str**,而 `write_file` 要求 bytes —— 与绑定约束「模板字节:一律 `.encode("utf-8")` 写入包」直接冲突,且拦在类缺失 RED 之前。按约束修正为 `.encode("utf-8")`(见第四节偏离清单)。

**第 2 次运行**(修正后,规范 RED):
```
Traceback (most recent call last):
  File "<frozen runpy>", line 203, in _run_module_as_main
  File "<frozen runpy>", line 88, in _run_code
  File ".../widgets/step_list_view.py", line 91, in <module>
    clipboard = StepClipboard()
                ^^^^^^^^^^^^^
NameError: name 'StepClipboard' is not defined
EXIT=1
```
符合简报 Step 2 预期(简报明确:「RED 阶段 ImportError 与 NameError 等价 = 类缺失」)。

### GREEN(实现后)

```
StepListView smoke OK
EXIT=0
```

### 简报代码块逐字核对(机械 diff)

- **实现代码块**(简报 Step 3,行 240–564 vs 文件行 26–349):`diff` 结果**逐字节一致**,唯一差异 = 文件在 docstring 后多一个空行(排版需要),简报行 564 的收尾 ``` 定界符不属于代码。
- **冒烟代码块**(简报 Step 1,行 42–230 vs 文件行 352–522):`diff` 结果仅 3 处差异,均为**有意修正**或非代码内容:
  1. 简报行 1–25 为模块 docstring(已在文件头部,不重复);
  2. `GOOD.replace(...)` 加 `.encode("utf-8")`(绑定约束要求,见下);
  3. `QWheelEvent(...)` 6 参 → 8 参旧式构造(见下);
  4. 收尾 ``` 定界符。
  其余断言、数值、补丁点、调用顺序全部逐字一致。
- 冒烟全部断言通过:`_cards/_hint`(空列表提示、绑定重建)、`_proxies[0].scale()==1.0`、滚轮 `hsb.value() != old`、`eventFilter(card, wheel) is True`、`_anims[0].endValue()` Enter=1.06 / Leave=1.0、三处 `_add_step`(0/-1/2)后 `len(sl)==5` 且 `edited==[1,1,1]`、复制/粘贴格式串往返、剪切(=复制+删除)后剪贴板保留并二次粘贴、`refresh_validity` 卡片数不变、对话框分组 top==["控制流程","示例"]、叶子 UserRole 路径、`_ok` 启用逻辑、选组 `accept()` 被拒 `result()==0`。

## 三、依赖链回归输出

```
python -m widgets.step_card      → StepCard smoke OK      EXIT=0
python -m model.step_list        → StepList smoke OK      EXIT=0
python -m model.step_list_store  → StepListStore smoke OK EXIT=0
```
全部 GREEN,T1/T2/T3 接口(`StepList.insert_format_strings`、`StepCard.menu_requested/set_selected/refresh`、`StepManager.template_paths/create_step`、`StepListStore.create_empty/add_list`)按简报消费,无回归。

## 四、文件变更清单

| 文件 | 动作 |
|---|---|
| `C:\Users\feelnn\Desktop\项目\KScript\widgets\step_list_view.py` | 新建(唯一变更) |

无其他文件改动。非 git 仓库,「提交」= 冒烟绿 + 依赖链回归(均完成)。

## 五、自审发现

1. **简报冒烟块与绑定 Global Constraint 冲突**:`pkg.write_file("actions/控制流程/延时.py", GOOD.replace(...))` 未 `.encode("utf-8")`,而 `KscpPackage.write_file` 走 `bytes(data)`(str 必抛 TypeError)。已按约束改为 `.encode("utf-8")`。若逐字保留,任务将永远无法绿(T1/T2/T3 的同类调用均有 encode,简报此处是转录笔误)。
2. **QWheelEvent 构造在 PyQt5 5.15.11 无 6 参重载**:本机 Qt 5.15.2 / PyQt5 5.15.11,可用重载 = 8 参旧式(pos, globalPos, pixelDelta, angleDelta, qt4Delta, qt4Orientation, buttons, modifiers)与 9 参新式;7 参(带 phase)也不存在。已用 8 参旧式:`(QPointF(10,10), QPointF(10,10), QPoint(0,0), QPoint(0,-240), 0, Qt.Horizontal, Qt.NoButton, Qt.NoModifier)`,保持 pixelDelta/angleDelta 载荷不变(垂直 -240 → 水平滚动),断言语义与简报完全一致。
3. **RED 失败形态为 NameError 而非 ImportError**:简报 Step 2 预期字面是 `ImportError: cannot import name 'StepClipboard'`;实际因冒烟块以模块全局名直接引用类,报 `NameError: name 'StepClipboard' is not defined`。简报 Global Constraints 已声明两者等价(类缺失),判定 RED 通过。
4. **不触碰 picker**:模块内无任何 `picker` 引用;`StepCard(step)` 构造时按 T3 设计内部包装 picker(QTimer.singleShot 延迟重检),冒烟未重置、未假设构造后 picker 原样 —— 符合先决信息 1。
5. **Python 3.14 注解安全**:`_DemoInput/_DemoOutput` dataclass 仅存在于模板字符串内(写入包后由 StepManager 编译,无 future import,引号注解安全);模块级无任何 dataclass;本文件已 `from __future__ import annotations`。
6. **Qt 存根规避**:枚举用整数值(`_PATH_ROLE = 0x0100`);`self.style()` 判 None 后再 `standardIcon`;无 QStyle 标准图标枚举裸用。`python -m py_compile` 通过。
7. **不调 `step.do()`**:模块内 grep `do(` 无命中;状态纯显示,变更后走 `refresh()`。
8. **无中文 bytes 字面量**:grep 非 ASCII bytes 字面量无命中;模板全部 `.encode("utf-8")`。
9. **无 `<frozen runpy> RuntimeWarning` 出现**(若出现亦无害,已按约定忽略)。

## 六、疑虑

1. **简报转录笔误两处**(见自审 1、2):均已按「Global Constraints 逐条绑定 + 必须可绿」修正,修正点已在第四节列明并可审。若评审方要求严格逐字,可回退但任务将无法通过验证。
2. **`StepClipboard.items` 在本任务未使用**(T5 消费),已按简报原样实现为空壳字段。
3. **`_card_menu` 与 `_on_context_menu` 的坐标语义**:卡片菜单收到的是 StepCard `contextMenuEvent` 的全局坐标,视图空白菜单收到 viewport 局部坐标再 `mapToGlobal` —— 均按简报原样,未经真实 UI 交互验证(冒烟不启事件循环,菜单分支经类级补丁或直接调私有方法覆盖)。
4. **QVariantAnimation 动画实际播放未经事件循环验证**:冒烟仅断言 `endValue()` 与参数,符合简报「不启动事件循环」的约定。
5. 执行环境为 Windows 控制台,终端输出中文路径显示为乱码(如 `��Ŀ`),不影响结果;冒烟判据一律以英文 `smoke OK` 行 + EXIT code 为准。
