# Task 1 Brief: `StepManager` 模型扩展(移动 / 分组 / 类访问)

> 摘录自实施计划 `docs/superpowers/plans/2026-08-28-step-tree.md`(权威文本)。完整 spec:`docs/superpowers/specs/2026-08-28-step-tree-design.md` §3。

## 本任务在工程中的位置

KScript 是 PyQt5 桌面自动化应用;`.kscp` 是工程包(ZIP 内存模型 `KscpPackage`)。`model/step_manager.py` 已交付 `StepManager` 模板工厂(加载/产出/模板操作,含冒烟块,末行 `print("StepManager smoke OK")`)。本任务追加 4 个方法,支撑步骤管理树:模板类只读访问、模板文件移动、分组重命名、分组创建。**只展示模板不创建对象**:任何路径不得调用 `create_step`。

## Global Constraints(全计划适用,本任务必须遵守)

- 非 git 仓库:不提交,「提交」步骤一律替换为「运行冒烟/自检验证」。
- 模板字节含中文/引号,写入 `.kscp` 一律 `str.encode("utf-8")`——中文 bytes 字面量在 Python 3 是 SyntaxError。
- 模板文件内容必须绝对导入项目包(`from actions.base import Step`),禁用相对导入。
- 冒烟测试用到 `QApplication` 时必须先创建(`QApplication.instance() or QApplication(sys.argv)`)。
- 路径中文合法(`actions/控制流程/延时.py` 等),勿改目录名。
- 错误一律 `LogModel.error()`;成功的操作摘要用 `LogModel.info()`。
- `KscpPackage.make_dir` 幂等但不建中间目录;目标冲突预检用 `exists()`(文件或目录都算)。
- 冒烟驱动 = 直接调 `mgr` 方法(不弹真实对话框,与既有冒烟同思路)。

**Files:**
- Modify: `model/step_manager.py`(冒烟块追加断言 + `copy_source_templates` 方法之后、类体结束之前追加 4 方法)

**Interfaces:**
- Consumes: 既有 `StepManager`(`_registry`/`_actions_rel`/`load()`/`_package.move`/`is_dir`/`exists`/`make_dir`)、`KscpPackage.files`(属性)、`LogModel`
- Produces: `template_class(path) -> type`、`move_template(path, target_dir="") -> None`、`rename_group(group, new_name) -> None`、`create_group(name) -> None`(Task 2/3 消费)

## Step 1: 追加失败测试(先红)——在冒烟块 `print("StepManager smoke OK")` 之前插入以下断言

**注意:既有断言块(上一计划的)保持不动,新断言块插在既有断言之后、print 之前。** 起始状态为既有冒烟末尾:注册表含 控制流程/示例、示例、本地、本地2、子目录/深层;文件含 actions/本地步骤.py、本地2.py、子目录/深层.py。

```python
    # ---- 移动 / 分组操作 / 模板类访问（步骤管理树支持） ----
    # move_template：顶层 → 子目录成功
    mgr.move_template("本地", "子目录")
    assert "子目录/本地" in mgr.template_paths()
    assert "本地" not in mgr.template_paths()
    assert pkg.is_file("actions/子目录/本地步骤.py")
    assert not pkg.is_file("actions/本地步骤.py")
    # move_template：目标已存在 → 不覆盖 + 日志
    LogModel.instance().clear()
    mgr.move_template("子目录/本地", "子目录")   # 目标 = actions/子目录/本地步骤.py 已存在
    assert any("已存在" in e.message for e in LogModel.instance().entries)
    assert pkg.is_file("actions/子目录/本地步骤.py")
    assert mgr.create_step("子目录/本地").name == "本地"
    # move_template：未知路径 → ValueError
    try:
        mgr.move_template("不存在/路径", "")
        raise AssertionError("未知路径应抛 ValueError")
    except ValueError:
        pass
    # rename_group：成功（整组移动，路径同步）
    mgr.rename_group("子目录", "新组")
    assert "新组/本地" in mgr.template_paths()
    assert "新组/深层" in mgr.template_paths()
    assert not any(p.startswith("子目录/") for p in mgr.template_paths())
    assert pkg.is_file("actions/新组/深层.py")
    # rename_group：目标已存在（同名）→ 日志报错、原组不变
    LogModel.instance().clear()
    mgr.rename_group("新组", "新组")
    assert any("已存在" in e.message for e in LogModel.instance().entries)
    assert "新组/本地" in mgr.template_paths()
    # rename_group：非法新名 / 未知组 → ValueError
    for bad in ("", "a/b", ".."):
        try:
            mgr.rename_group("新组", bad)
            raise AssertionError("非法新组名应抛 ValueError: %r" % bad)
        except ValueError:
            pass
    try:
        mgr.rename_group("不存在组", "x")
        raise AssertionError("未知组应抛 ValueError")
    except ValueError:
        pass
    # 嵌套组：移动建组 → 重命名保留父组
    mgr.move_template("本地2", "新组/深")
    assert "新组/深/本地2" in mgr.template_paths()
    mgr.rename_group("新组/深", "更深")
    assert "新组/更深/本地2" in mgr.template_paths()
    assert not any(p.startswith("新组/深") for p in mgr.template_paths())
    # create_group：顶层成功 / 嵌套成功（父组存在）
    mgr.create_group("空组")
    assert pkg.is_dir("actions/空组")
    mgr.create_group("新组/嵌套")
    assert pkg.is_dir("actions/新组/嵌套")
    # create_group：重名 → 日志报错返回
    LogModel.instance().clear()
    mgr.create_group("空组")
    assert any("已存在" in e.message for e in LogModel.instance().entries)
    # create_group：非法名 / 父组不存在 → ValueError
    for bad in ("", ".", "..", "a//b", "/a", "a/"):
        try:
            mgr.create_group(bad)
            raise AssertionError("非法组名应抛 ValueError: %r" % bad)
        except ValueError:
            pass
    try:
        mgr.create_group("不存在父/子")
        raise AssertionError("父组不存在应抛 ValueError")
    except ValueError:
        pass
    # template_class：返回类 / 未知路径 ValueError
    cls = mgr.template_class("控制流程/示例")
    assert isinstance(cls, type) and cls.name == "示例"
    try:
        mgr.template_class("不存在/路径")
        raise AssertionError("未知路径应抛 ValueError")
    except ValueError:
        pass
```

## Step 2: 运行确认失败(红)

Run: `python -m model.step_manager`
Expected: `AttributeError: 'StepManager' object has no attribute 'move_template'`(追加断言首个调用处;模板操作方法尚未实现,「功能缺失」红,无需再修;若报错内容不是「功能缺失」,先修复再重新确认)

## Step 3: 实现 —— 在 `copy_source_templates` 方法之后、类体结束之前插入以下 4 方法

```python
    # ================================================================
    # 模板类访问（只读；信息面板数据源）
    # ================================================================
    def template_class(self, path: str) -> type:
        """只读返回路径对应的模板类；未知路径抛 ValueError。"""
        entry = self._registry.get(path)
        if entry is None:
            raise ValueError("未找到步骤模板: %r" % path)
        return entry[0]

    # ================================================================
    # 移动 / 分组操作（步骤管理树支持）
    # ================================================================
    def move_template(self, path: str, target_dir: str = "") -> None:
        """把模板文件移动到 ``actions/<target_dir>/``；目标已存在不覆盖。"""
        entry = self._registry.get(path)
        if entry is None:
            raise ValueError("未找到步骤模板: %r" % path)
        old_rel = entry[1]
        target = self._actions_rel(target_dir, os.path.basename(old_rel))
        if self._package.exists(target):
            LogModel.instance().error(
                "移动模板失败: 目标已存在 %s（不覆盖）" % target)
            return
        self._package.move(old_rel, target)
        self.load()
        LogModel.instance().info("移动模板: %s → %s" % (old_rel, target))

    def rename_group(self, group: str, new_name: str) -> None:
        """把分组 ``actions/<group>/`` 重命名为 ``actions/<父组>/<new_name>/``；目标已存在不合并。"""
        if not group:
            raise ValueError("分组为空")
        if not new_name or "/" in new_name or new_name in (".", ".."):
            raise ValueError("非法新组名: %r" % new_name)
        old_dir = "actions/" + group.strip("/")
        if not self._package.is_dir(old_dir):
            raise ValueError("分组不存在: %r" % group)
        parent = group.rsplit("/", 1)[0] if "/" in group else ""
        new_dir = ("actions/%s/%s" % (parent, new_name)) if parent \
            else ("actions/" + new_name)
        if self._package.exists(new_dir):
            LogModel.instance().error(
                "重命名分组失败: 目标已存在 %s（不合并）" % new_dir)
            return
        self._package.move(old_dir, new_dir)
        self.load()
        LogModel.instance().info("重命名分组: %s → %s" % (old_dir, new_dir))

    def create_group(self, name: str) -> None:
        """创建分组 ``actions/<name>/``（name 可多层）；已存在不覆盖。"""
        if not name or any(seg in (".", "..") or not seg
                           for seg in name.split("/")):
            raise ValueError("非法分组名: %r" % name)
        parent = name.rsplit("/", 1)[0] if "/" in name else ""
        target = "actions/" + name
        if parent and not self._package.is_dir("actions/" + parent):
            raise ValueError("父分组不存在: %r" % parent)
        if self._package.exists(target):
            LogModel.instance().error("创建分组失败: 已存在 %s" % target)
            return
        self._package.make_dir(target)
        LogModel.instance().info("创建分组: %s" % target)
```

## Step 4: 运行确认通过(绿)

Run: `python -m model.step_manager`
Expected: `StepManager smoke OK`,EXIT=0(stderr 有已知 runpy RuntimeWarning——包 `__init__.py` 加载即导入所致,既有模式,无害)

## Step 5: 依赖链验证(替代提交)

Run:
```bash
python -m model.step_manager
python -m actions.base
python -m actions.控制流程.time_delay
python -m model.kscp_package
```
Expected: 全部冒烟 OK,EXIT=0
