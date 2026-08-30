---
name: adding-a-variable-type
description: Use when adding a new variable type to the KScript project — a new VariableType handler registered with ProjectVariable, plus its GUI editor — or when a type name needs project-wide support in validation, pickers, and the variable creation dialog.
---

# 添加变量类型

## Overview

KScript 变量类型 = `VariableType` 子类（模型注册）+ `register_editor`（GUI 编辑器），
**两个注册点缺一不可**；另有若干冒烟把某个名字当「未注册类型」示例，需联动改掉。

## Checklist

**1. 模型注册**（`model/project_variable.py`）：
- 子类化 `VariableType`，设置 `name` / `is_resource` / `suffixes` / `description`：
  - 资源类：`is_resource=True`、`suffixes=(...)`（小写含点）；`normalize` 委托
    `model.path_util.norm_maybe_root`；`is_valid` 检查 `data.startswith("assets/")`
    + 后缀 + `package.is_file(data)`；`to_actual` 返回 `package.read_file(data)`
    （仿 `_ImageType`）
  - 字面值类：`is_valid` 只查数据类型（`_StringType`/`_NumberType` 可作蓝本）
- 多个资源类时可抽公共 `_ResourceType` 基类（image/audio 共用 normalize/is_valid/to_actual），
  新类型只剩三行声明
- 末尾 `ProjectVariable.register_type(实例)` 注册

**2. GUI 编辑器注册**（`widgets/variable_tree_widget.py`）：
- `register_editor("类型名", fn)`，`fn(var, package, on_changed) -> QWidget`；
  资源类仿 `_image_editor`（信息区 + `ResourceTreeWidget.pick_resource(pkg, tuple(var.suffixes), w)`
  选择按钮，按后缀过滤）；字面值类用 QLineEdit 实时校验
- `_make_var_icon` 加该类型的图标分支（树节点与创建对话框共用）
- 创建对话框的**类型卡片按钮组**经 `supported_types()` 自动包含新类型，无需改对话框本身

**3. 联动坑（先 grep 全库，含各模块 `__main__` 冒烟）**：把某名字当「未注册类型」
示例的用例，注册新类型后必须换成别的占位名：
- `model/step.py`：注解未注册用例
- `model/step_manager.py`：坏注解模板
- `model/variable_tree.py`：`filter_by_type("未知")` 用例
- `model/project_variable.py` 自身冒烟：`create("未知")` 抛 ValueError 用例 +
  「自定义类型演示」——**演示类若与新类型同名，会在运行期覆盖内置注册**
  （测试恰好仍过、极难察觉）
（基线教训：注册 audio 时靠全库 grep 才找全，漏一处必红）

**4. 可选联动（注意副作用）**：
- `model/step_io.py`：资源类槽经 `_type_is_resource` 自动获得选择按钮；但
  `_IMAGE_EXTS` **同时**用于整合选择器「资源」页过滤**和资源类常量的合法性校验**
  ——直接往里塞新后缀会让 image 槽误接受新类型常量；如需资源页直选新类型，
  应按槽类型拆分过滤列表（否则只能经变量引用选择）
- `ProjectVariable.supported_types()` 相关冒烟断言更新

**5. 冒烟**：`project_variable.py` 与 `variable_tree_widget.py` 各补正例/反例
（缺失文件、后缀不符、路径归一化、格式串往返、编辑器控件存在与校验）；
跑 `python tests/smoke_all.py` 全量；README/docs 的类型列表同步。

## Common Mistakes

| 坑 | 后果 | 对策 |
|---|---|---|
| 只注册模型、漏 `register_editor` | 创建对话框选了类型无编辑器 | 两个注册点都做 |
| 漏改「未知类型示例」（含冒烟内的演示类） | 冒烟全红 / 内置注册被覆盖 | 先 grep 类型名（含 `__main__`） |
| 资源类不查 `package.is_file` | 悬空路径被判合法 | 仿 `_ImageType.is_valid` |
| 后缀与选择器过滤不一致 | 编辑器能选、校验不过 | 选择器用 `var.suffixes` |
| 往 `_IMAGE_EXTS` 里加新后缀 | image 槽误接受新类型常量 | 按槽类型拆分过滤 |
| 冒烟输出走管道 | EXIT=139 段错误 | 直跑 |
| venv 部署下 Qt 冒烟 QApplication 挂起 | 插件路径解析到基础 Python 目录 | 冒烟前置 `ensure_qt_plugin_path()` 同款 env（ui_common） |
