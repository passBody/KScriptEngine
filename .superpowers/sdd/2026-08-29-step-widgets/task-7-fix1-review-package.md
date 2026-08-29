# 终审修复(fix-1)review package — I-1 保存链路 + I-2 泄漏 + docstring + 阻塞性潜伏缺陷

- 来源:终审(opus)2 条 Important(I-1/I-2)+ 分诊表唯一【修】项(docstring);实施中发现并修复 1 条阻塞性既有潜伏缺陷(越界文件)。
- 修复派发范围:step_card.py / step_list_view.py / main_widget.py(docstring);**越界变更**:step_io_widget.py `_live_widgets`。
- 非 git 适配:无 BASE/HEAD;下方为磁盘现状(控制器已核对)与修复点。

## 变更清单(磁盘已核实)

1. `widgets/step_card.py`:
   - L27 `import weakref`;L50-59 `_notify_io_edited(self_ref)` 模块级弱引用取卡槽;L66 `io_changed = pyqtSignal()`;L104-110 textChanged 钩子改弱引用(只对 QLineEdit 字段);L111-122 picker 包装扁平化(`orig = getattr(step.io.picker, "_kscript_orig", step.io.picker)` + `_picker._kscript_orig = orig` + `QTimer.singleShot(0, self._io_edited)`);L142-149 `_io_edited()`(refresh + emit);冒烟 L290-307(I-1 真实 textChanged 路径 `input_fields[0].setText("9")` → fired==[1];I-2 两次建卡后 `_kscript_orig` 回溯计数 ==1)
2. `widgets/step_list_view.py`:L180 `card.io_changed.connect(self.edited)`;冒烟 L516-527(同 step 多次重建后对卡片 QLineEdit setText 不崩 + `edited` +1)
3. `widgets/step_io_widget.py`(越界):L279-300 `_live_widgets` 按 C++ 存活过滤(shiboken 探活 `w.objectName()`,RuntimeError → 丢弃)+ 清理登记表 `self._widgets = refs`
4. `widgets/main_widget.py`:L9-14 模块 docstring 重写为实际架构(四棵管理树/共享变量树/无占位)

## 修复点核对要点

- **I-1 时机**:io_changed 仅在两处发出——真实 textChanged(用户输入)与 picker 值落地后(延迟队列);`change_value` 程序化改值走 blockSignals 不误发;视图建卡时连接一次(L180);宿主保存链路复用既有 edited → _save_store(main_widget.py:290-291 未动)。
- **I-2 扁平化**:getattr 取最原始 picker(无 `_kscript_orig` 时取自身 → 与 T3 fake_picker 冒烟兼容,构造前替换场景 orig = fake);旧包装器被替换后无引用可回收。
- **越界修改(评审重点)**:`_live_widgets` 原实现(无 BASE 可 diff,评审对照 step_io_widget.py 既有调用语义 :383/:391 `for wd in self._live_widgets()` 与 `gen_widget` :276 的登记)仅过滤 `ref() is None`,无法滤掉「Python 包装器存活但 C++ 已删」的控件 → 视图重建后对旧卡片刷新抛 RuntimeError。新实现 objectName() 探活 + 清理。无接口/签名变化,其余行未动。
- **实施者自述 concern**:① io_changed 输出 picker 取值可能双发(既有 `_refresh_output_field` setText 不 blockSignals;保存幂等,无害,未扩大范围);② 极端时序(卡片销毁后 picker 延迟定时器触发 → RuntimeError 被 PyQt 槽机制捕获打印,现实不可达)。

## 实施者报告摘要

- 三条修复各经 RED(AttributeError io_changed / AssertionError 链计数 0)→ GREEN;阻塞性缺陷 RED = 重建后 setText → EXIT=127(静默)/RuntimeError。
- 全量回归 17/17 全绿(step_io_widget 含在内);T3 picker 覆盖冒烟原样通过(兼容性已确认);`_probe_stale.py` 等临时文件已删。

## 当前文件

- `widgets/step_card.py`(310 行)全文;`widgets/step_list_view.py`(527 行)L175-186 + L510-527;`widgets/step_io_widget.py`(约 400 行)L270-300 + :383/:391 消费点;`widgets/main_widget.py` L9-14。
