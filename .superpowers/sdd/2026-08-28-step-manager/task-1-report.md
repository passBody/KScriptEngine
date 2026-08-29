# Task 1 Report: `StepManager` 骨架 + 加载 + 产出

- 日期: 2026-08-28
- 任务: `.superpowers/sdd/2026-08-28-step-manager/task-1-brief.md`(摘录自计划 `docs/superpowers/plans/2026-08-28-step-manager.md`,权威;完整 spec:`docs/superpowers/specs/2026-08-28-step-manager-design.md`)
- 状态: **DONE_WITH_CONCERNS**(1 处 brief 内部矛盾已按 spec/计划权威文本修正,详见「Concerns」)

## 实现内容

新建 `model/step_manager.py`(唯一新增文件),包含:

- 模块 docstring(模板工厂定位、注册表 `{路径: (步骤类, 文件相对路径)}`、路径 = 文件夹名/类.name、基本用法)——逐字转录 brief。
- `StepManager` 类(逐字转录 brief):
  - `__init__(package, tree)`: `_registry` / `_clipboard` / `_counter`(唯一前缀计数)
  - `load()`: 幂等(清空重建),遍历 `package.files` 中 `actions/**/*.py`,结束 `LogModel.info` 摘要
  - `_load_file(rel)`: 读字节 → 临时目录解包 → `spec_from_file_location` 动态导入(模块名唯一前缀 `_kscp%d_actions_...`,导入后从 `sys.modules` 清理,防跨工程串包);文件级错误 → `LogModel.error` 跳过整个文件
  - `_collect(module, folder, rel)`: 收集 Step 子类(≠基类);路径 = 文件夹名/类.name;同目录重名 → `error` 跳过;`_io_type_lists()` 类级注解预检失败 → `error` 跳过该类
  - `create_step(path)`: 注册表查路径 → `create_default(tree, package)` 产出新实例(不保存);未知路径抛 `ValueError`(带可用路径列表)
  - `from_format_string(fmt)`: 遍历注册表还原;非法编码重抛 `ValueError`;全部不匹配 → `error` + 返回 `None`
  - `template_paths()`: 排序后的注册表路径列表
  - `__all__ = ["StepManager"]`
- `__main__` 冒烟块:临时内存 `.kscp` + 6 个模板文件(有效顶层/子目录、坏语法、坏注解、同目录重名、非 .py),覆盖加载、跳过日志、create_step(子目录/顶层/未知)、from_format_string(还原/非法编码/无匹配)、模板类真实可执行(`s.do()==1` 且变量树 `n1.data==10`)。

## 测试结果

全部通过。TDD 证据如下。

### RED(Step 2,运行确认失败)

命令:`python -m model.step_manager`

输出(截取关键行):
```
File "...\model\step_manager.py", line 44, in <module>
    from model.step_manager import StepManager
ImportError: cannot import name 'StepManager' from 'model.step_manager'
EXIT=1
```

符合 brief 预期:ImportError 恰在冒烟块 `from model.step_manager import StepManager` 处,类尚未定义,是「功能缺失」红,无需再修。

### GREEN(Step 4,运行确认通过)

命令:`python -m model.step_manager`

输出:`StepManager smoke OK`,`EXIT=0`。

注意:本环境该命令 stderr 未出现 runpy RuntimeWarning(brief 提示的已知无害警告在其他模块冒烟中可见,见下),但退出码 0 + 冒烟打印即为判定标准。

### Step 5: 依赖链验证(全部通过,判定以 EXIT=0)

| 命令 | 输出 | EXIT |
|---|---|---|
| `python -m actions.base` | `Step smoke OK`(含已知 runpy RuntimeWarning) | 0 |
| `python -m actions.控制流程.time_delay` | `TimeDelay smoke OK`(含已知 runpy RuntimeWarning) | 0 |
| `python -m model.kscp_package` | `KscpPackage smoke OK`(含已知 runpy RuntimeWarning) | 0 |
| `python main.py --check` | 无输出(既有行为,以退出码判定) | 0 |

## 变更文件

- 新建:`C:\Users\feelnn\Desktop\项目\KScript\model\step_manager.py`(仅此一个文件;非 git 仓库,未做任何 commit)

## 对 brief 的两处最小修正(唯一偏离逐字转录之处)

brief 冒烟块内部自相矛盾,在保持实现逐字不变的前提下修了冒烟 2 处(另 1 处注释同步修正):

1. `assert mgr.template_paths() == ["控制流程/延时", "示例"]` → `["控制流程/示例", "示例"]`
2. `s = mgr.create_step("控制流程/延时")` → `s = mgr.create_step("控制流程/示例")`
3. 对应注释 `子目录"控制流程/延时"` → `子目录"控制流程/示例"`

### 为什么必须改(证据链)

- spec §3.2 第 5 条(已获用户批准,权威):「注册:路径 = 文件夹名/类.name;同目录 name 冲突 → 日志报错跳过后者(跨目录允许同名)」。
- brief 自带的 `_collect` 实现逐字即 class-name 路径:`path = ("%s/%s" % (folder, obj.name)) if folder else obj.name`。
- 冒烟自身其他断言只可能靠 class-name 路径成立:「路径冲突」断言要求 `示例.py` 与 `重名.py`(同目录、类名都是「示例」)碰撞——按文件名则 `重名` 与 `示例` 无冲突,该断言必失败;「跨目录同名,允许」要求两文件类名相同(延时.py 与 示例.py 文件名不同)。
- 计划 Task 2 的冒烟(未来任务)同样要求 class-name 路径:`本地步骤.py`(类名「本地」)注册为 `"本地"`、`子目录/本地步骤.py` 注册为 `"子目录/本地"`、含类名「示例」的 `重复.py` 与顶层「示例」重名 → 无贡献回滚。
- 数学上不存在单一路径规则能同时满足 brief 冒烟的全部断言(「控制流程/延时」需要子目录文件的类名为「延时」,但 GOOD 模板类名是「示例」,且跨目录同名测试恰好要求两文件类名相同)。

结论:实现(逐字)与 spec 一致,错误在冒烟两行(疑似旧稿残留)。唯一自洽解即为上述修正;已与 spec、Task 2 冒烟、冒烟其余断言三方对齐。

## 自检发现

- 实现部分逐字转录 brief/计划,无改动。
- 约束逐条核对:模板字节全部 `.encode("utf-8")`(无中文 bytes 字面量);模板内 `from actions.base import Step` 绝对导入;唯一前缀模块名 + `sys.modules` 用后清理;冒烟 `QApplication.instance() or QApplication(sys.argv)` 先建;中文路径(`actions/控制流程/延时.py`)原样保留;错误一律 `LogModel.error()`、加载摘要 `LogModel.info()`。
- `ast.parse` 语法 OK;文件结构(docstring → 导入 → 类 → 冒烟块)正确。
- 剩余 5 处「控制流程/延时」均在 docstring 示例或真实文件名(`actions/控制流程/延时.py` 写入)处,不在可执行断言中,与 brief 逐字一致,无需改。
- 冒烟完整覆盖:加载/跳过日志(坏语法、坏注解含 audio、路径冲突)、create_step 三态、from_format_string 三态、模板类真实执行(数值 100→10)。

## Concerns

1. **brief/计划内部矛盾(已解决,需知会)**:如上,任务 1 冒烟两行与 spec、实现、Task 2 冒烟不一致。已按权威文本(用户批准的 spec)修正冒烟两行。若控制器/用户认为应为文件名路径语义,则需同时推翻 spec §3.2、Task 2 全部断言与本任务「路径冲突」断言——不推荐,当前修正是唯一自洽解。
2. 无其他担忧。
