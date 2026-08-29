# Task 1 Brief: `StepManager` 骨架 + 加载 + 产出

> 摘录自实施计划 `docs/superpowers/plans/2026-08-28-step-manager.md`(权威文本)。完整 spec:`docs/superpowers/specs/2026-08-28-step-manager-design.md`。

## 本任务在工程中的位置

KScript 是 PyQt5 桌面自动化应用;`.kscp` 是工程包(ZIP 内存模型 `KscpPackage`)。`actions/base.py` 已交付 `Step` 基类(类属性 name/description、`create_default(tree, package)`、`from_format_string(fmt, tree, package)`、`_io_type_lists()` 类级注解预检)。本任务新增 `model/step_manager.py`:步骤模板工厂 `StepManager`,从 `.kscp` 包内 `actions/` 加载模板、按需产出步骤实例(不保存)。

## Global Constraints(全计划适用,本任务必须遵守)

- 非 git 仓库:不提交,「提交」步骤一律替换为「运行冒烟/自检验证」。
- **模板字节含中文/引号,写入 `.kscp` 一律 `str.encode("utf-8")`**——中文 bytes 字面量在 Python 3 是 SyntaxError。
- **模板文件内容必须绝对导入项目包**(`from actions.base import Step`),禁用相对导入。
- **模块名唯一前缀 + 加载后从 `sys.modules` 清理**——防同名模板文件跨工程串包。
- 冒烟测试用到 `QApplication` 时必须先创建(`QApplication.instance() or QApplication(sys.argv)`)。
- 路径中文合法(`actions/控制流程/延时.py` 等),勿改目录名。
- 错误一律 `LogModel.error()`;成功的加载摘要用 `LogModel.info()`。

**Files:**
- Create: `model/step_manager.py`

**Interfaces:**
- Consumes: `actions.base.Step`(类属性 name/description、`create_default(tree, package)`、`from_format_string(fmt, tree, package)`、`_io_type_lists()` 类级预检)、`model.kscp_package.KscpPackage`(`files` 是**属性**不是方法 / read_file / write_file / is_file / remove)、`model.variable_tree.VariableTree`、`model.log_model.LogModel`(单例,error/info;`entries` 条目有 `.message`,有 `clear()`)
- Produces: `StepManager(package, tree)`——`load()`(幂等)、`template_paths() -> List[str]`、`create_step(path) -> Step`、`from_format_string(fmt) -> Optional[Step]`;私有 `_load_file(rel) -> (bool, int)`、`_collect(module, folder, rel) -> int`

## Step 1: 写失败测试(先红)——建 `model/step_manager.py`(仅模块 docstring + 冒烟块,类定义留到 Step 3)

`model/step_manager.py`:

```python
# -*- coding: utf-8 -*-
"""
步骤管理模型（模板工厂）
========================

:class:`StepManager` 是步骤模板的工厂：从 ``.kscp`` 包内 ``actions/`` 目录
加载步骤模板并管理模板，按需**产出**步骤对象实例；模型不保存任何实例
（实例的保存与 ``step_list.json`` 归后续「步骤列表模型」）。

模板
----
* 模板 = ``.kscp/actions/`` 下的 ``.py`` 文件（惯例一文件一步骤类）。
* 注册表 = ``{路径: (步骤类, 文件相对路径)}``，路径 = ``文件夹名/类.name``
  （顶层文件只有 ``name``；如 ``"控制流程/延时"``）。

基本用法
--------
::

    mgr = StepManager(pkg, tree)
    mgr.load()                              # 从 .kscp/actions 加载模板
    paths = mgr.template_paths()            # ['控制流程/延时', ...]
    step = mgr.create_step("控制流程/延时")      # 产出新步骤实例（不保存）
    back = mgr.from_format_string(fmt)      # 由格式串还原（遍历注册表）
    mgr.add_template("my_step.py")          # 加入模板（无贡献自动回滚）
    mgr.paste_template()                    # 剪贴板模板粘入工程
"""
```

然后在文件末尾追加冒烟块(先只写冒烟块,类定义留到 Step 3):

```python
# ================================================================
# 冒烟演示：直接 ``python -m model.step_manager`` 运行
# ================================================================
if __name__ == "__main__":
    import base64 as _b64
    import json as _json
    import os
    import sys
    import tempfile

    from PyQt5.QtWidgets import QApplication

    from actions.base import Step
    from model.kscp_package import KscpPackage
    from model.log_model import LogModel
    from model.project_variable import ProjectVariable
    from model.step_manager import StepManager
    from model.variable_tree import VariableTree

    app = QApplication.instance() or QApplication(sys.argv)

    pkg = KscpPackage.create_empty()
    tree = VariableTree.create_empty()
    tree.add("n1", ProjectVariable.create("number", 100, pkg))

    # 模板字节（有效模板；中文/引号内容一律用 .encode("utf-8")，禁用中文 bytes 字面量）
    GOOD = '''# -*- coding: utf-8 -*-
from dataclasses import dataclass
from actions.base import Step

@dataclass
class _DemoInput:
    count: "number" = 0

@dataclass
class _DemoOutput:
    total: "number" = 0

class DemoStep(Step):
    name = "示例"
    description = "测试模板"
    input_class = _DemoInput
    output_class = _DemoOutput

    def run(self) -> int:
        self.outputs.total = self.inputs.count * 2
        return 1
'''

    BAD_ANNO = '''from dataclasses import dataclass
from actions.base import Step

@dataclass
class _BadInput:
    x: "audio" = ""

@dataclass
class _BadOutput:
    pass

class BadStep(Step):
    name = "坏注解"
    description = "注解未注册"
    input_class = _BadInput
    output_class = _BadOutput
'''

    # 写入 .kscp/actions：有效（顶层+子目录）、坏语法、注解非法、同目录重名、非 .py
    pkg.write_file("actions/示例.py", GOOD.encode("utf-8"))
    pkg.write_file("actions/控制流程/延时.py", GOOD.encode("utf-8"))   # 跨目录同名，允许
    pkg.write_file("actions/坏语法.py", b"def broken(:\n")
    pkg.write_file("actions/坏注解.py", BAD_ANNO.encode("utf-8"))
    pkg.write_file("actions/重名.py", GOOD.encode("utf-8"))            # 与 示例.py 同目录重名
    pkg.write_file("actions/readme.txt", b"not a template")

    mgr = StepManager(pkg, tree)
    LogModel.instance().clear()
    mgr.load()

    # 注册表：顶层"示例" + 子目录"控制流程/示例"；坏语法/坏注解/重名被跳过，readme 不处理
    # （路径 = 文件夹名/类.name，类名为"示例"；"延时"是文件名，不参与路径——T1 裁定）
    assert mgr.template_paths() == ["控制流程/示例", "示例"]
    errs = [e.message for e in LogModel.instance().entries]
    assert any("坏语法" in m for m in errs)
    assert any("坏注解" in m and "audio" in m for m in errs)
    assert any("路径冲突" in m for m in errs)   # 同目录重名仅保留其一（谁被跳取决于排序，断言不依赖胜者）

    # create_step：子目录 / 顶层 / 未知路径
    s = mgr.create_step("控制流程/示例")
    assert isinstance(s, Step) and s.name == "示例" and s.description == "测试模板"
    s.io.change_value("input", 0, "5")
    s.io.change_value("output", 0, "n1")
    assert s.do() == 1
    assert tree.get("n1").data == 10            # 模板类真实可执行
    assert mgr.create_step("示例").name == "示例"
    try:
        mgr.create_step("不存在/路径")
        raise AssertionError("未知路径应抛 ValueError")
    except ValueError:
        pass

    # from_format_string：还原 / 非法编码重抛 / 无匹配 None+日志
    fmt = s.to_format_string()
    back = mgr.from_format_string(fmt)
    assert isinstance(back, Step)
    assert back.io.to_format_string() == s.io.to_format_string()
    try:
        mgr.from_format_string("not*valid*")
        raise AssertionError("非法编码应抛 ValueError")
    except ValueError:
        pass
    LogModel.instance().clear()
    fake = _b64.urlsafe_b64encode(_json.dumps(
        {"name": "别的步骤", "in": [], "out": [], "io": s.io.to_format_string()},
        ensure_ascii=False).encode()).decode().rstrip("=")
    assert mgr.from_format_string(fake) is None
    assert any("无法还原" in e.message for e in LogModel.instance().entries)

    print("StepManager smoke OK")
```

## Step 2: 运行确认失败(红)

Run: `python -m model.step_manager`
Expected: `ImportError: cannot import name 'StepManager' from 'model.step_manager'`(冒烟块 `from model.step_manager import StepManager` 处;类尚未定义,「功能缺失」红,无需再修;若报错内容不是「功能缺失」而是其它(如 QApplication 问题),先修复再重新确认。)

## Step 3: 实现最小代码 —— 在 docstring 之后、冒烟块之前插入类定义

```python
import importlib.util
import os
import sys
import tempfile
from typing import Dict, List, Optional, Tuple

from actions.base import Step
from model.kscp_package import KscpPackage
from model.log_model import LogModel
from model.variable_tree import VariableTree

__all__ = ["StepManager"]


class StepManager:
    """步骤模板工厂：加载/管理 ``.kscp/actions`` 下的步骤模板，按需产出步骤实例。"""

    _PREFIX = "_kscp%d_actions_"

    def __init__(self, package: KscpPackage, tree: VariableTree) -> None:
        self._package = package
        self._tree = tree
        self._registry: Dict[str, Tuple[type, str]] = {}   # 路径 -> (步骤类, 文件相对路径)
        self._clipboard: Optional[Tuple[str, bytes]] = None  # (文件名, 内容)，单槽
        self._counter = 0                                   # 唯一前缀计数

    # ================================================================
    # 加载
    # ================================================================
    def load(self) -> None:
        """从 ``.kscp/actions`` 加载模板（幂等：每次清空注册表重建）。"""
        self._registry = {}
        files = sorted(f for f in self._package.files      # files 是属性不是方法
                       if f.startswith("actions/") and f.endswith(".py"))
        loaded = 0
        for rel in files:
            ok, count = self._load_file(rel)
            if ok:
                loaded += count
        LogModel.instance().info("步骤模板加载完成: 模板 %d 个, 文件 %d 个"
                                 % (loaded, len(files)))

    def _load_file(self, rel: str) -> Tuple[bool, int]:
        """加载单个模板文件；返回 (文件是否成功, 注册成功的模板数)。"""
        folder = os.path.dirname(rel[len("actions/"):])
        try:
            code = self._package.read_file(rel)
        except Exception as e:
            LogModel.instance().error("读取模板文件失败: %s（%s）" % (rel, e))
            return False, 0
        tmp_dir = tempfile.mkdtemp(prefix="kscp_actions_")
        try:
            tmp_path = os.path.join(tmp_dir, os.path.basename(rel))
            with open(tmp_path, "wb") as fh:
                fh.write(code)
            self._counter += 1
            # 唯一前缀模块名：防同名模板文件跨工程串包（sys.modules 缓存旧类）
            mod_name = (self._PREFIX % self._counter) + \
                rel[len("actions/"):].replace("/", ".")[:-3]
            spec = importlib.util.spec_from_file_location(mod_name, tmp_path)
            if spec is None or spec.loader is None:
                LogModel.instance().error("无法为模板创建导入规范: %s" % rel)
                return False, 0
            module = importlib.util.module_from_spec(spec)
            sys.modules[mod_name] = module
            try:
                spec.loader.exec_module(module)
            except Exception as e:
                LogModel.instance().error("模板文件加载失败: %s（%s）" % (rel, e))
                return False, 0
            finally:
                sys.modules.pop(mod_name, None)
            return True, self._collect(module, folder, rel)
        finally:
            try:
                os.remove(tmp_path)
                os.rmdir(tmp_dir)
            except OSError:
                pass

    def _collect(self, module: object, folder: str, rel: str) -> int:
        """从模块收集 Step 子类并注册（类级预检：注解非法/路径冲突 → 日志跳过）；返回注册数。"""
        count = 0
        for obj in vars(module).values():
            if not isinstance(obj, type) or not issubclass(obj, Step) or obj is Step:
                continue
            path = ("%s/%s" % (folder, obj.name)) if folder else obj.name
            if path in self._registry:
                LogModel.instance().error(
                    "步骤模板路径冲突, 跳过: %s（%s 与 %s 同名）"
                    % (path, rel, self._registry[path][1]))
                continue
            try:
                obj._io_type_lists()      # 类级预检：注解必须为已注册变量类型
            except ValueError as e:
                LogModel.instance().error(
                    "步骤模板注解非法, 跳过: %s（%s）" % (path, e))
                continue
            self._registry[path] = (obj, rel)
            count += 1
        return count

    # ================================================================
    # 产出（不保存）
    # ================================================================
    def create_step(self, path: str) -> Step:
        """按路径生成步骤实例（如 "控制流程/延时"）；未知路径抛 ValueError。"""
        entry = self._registry.get(path)
        if entry is None:
            raise ValueError("未找到步骤模板: %r（可用: %s）"
                             % (path, self.template_paths()))
        return entry[0].create_default(self._tree, self._package)

    def from_format_string(self, fmt: str) -> Optional[Step]:
        """遍历注册表由格式串还原步骤实例。

        非法编码 → 重抛 ValueError；全部不匹配 → 日志报错返回 None。
        """
        for cls, _rel in self._registry.values():
            try:
                step = cls.from_format_string(fmt, self._tree, self._package)
            except ValueError:
                raise
            if step is not None:
                return step
        LogModel.instance().error(
            "无法还原步骤格式化字符串: 没有可匹配的模板(名称/签名与注册表不符)")
        return None

    # ================================================================
    # 模板路径
    # ================================================================
    def template_paths(self) -> List[str]:
        """排序后的注册表路径列表（树 UI 数据源）。"""
        return sorted(self._registry)
```

## Step 4: 运行确认通过(绿)

Run: `python -m model.step_manager`
Expected: `StepManager smoke OK`,EXIT=0(stderr 有已知的 runpy RuntimeWarning——包 `__init__.py` 加载即导入所致,既有模式,无害)

## Step 5: 依赖链验证

Run:
```bash
python -m actions.base
python -m actions.控制流程.time_delay
python -m model.kscp_package
python main.py --check
```
Expected: 全部冒烟 OK、`main --check` 无输出但 EXIT=0(既有行为,以退出码判定)。
