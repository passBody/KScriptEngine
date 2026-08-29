# Task 2 Brief: 模板操作 + 拷贝入口

> 摘录自实施计划 `docs/superpowers/plans/2026-08-28-step-manager.md`(权威文本)。完整 spec:`docs/superpowers/specs/2026-08-28-step-manager-design.md`。

## 本任务在工程中的位置

Task 1 已交付 `model/step_manager.py`:`StepManager(package, tree)` 含 `load()`(幂等,从 `.kscp/actions` 动态导入模板,注册表 `_registry: Dict[str, Tuple[type, str]]` = 路径 → (步骤类, 文件相对路径))、`template_paths()`、`create_step()`、`from_format_string()`,以及 `_clipboard: Optional[Tuple[str, bytes]]` 单槽剪贴板(文件名, 字节)与 `_counter` 唯一前缀计数。本任务在**同一文件**追加模板操作:add/remove/copy/cut/paste + `copy_source_templates` 拷贝入口。

## Global Constraints(全计划适用,本任务必须遵守)

- 非 git 仓库:不提交,「提交」步骤一律替换为「运行冒烟/自检验证」。
- **模板字节含中文/引号,写入 `.kscp` 一律 `str.encode("utf-8")`**——中文 bytes 字面量在 Python 3 是 SyntaxError。
- **模板文件内容必须绝对导入项目包**(`from actions.base import Step`),禁用相对导入。
- **模块名唯一前缀 + 加载后从 `sys.modules` 清理**——防同名模板文件跨工程串包。
- 冒烟测试用到 `QApplication` 时必须先创建(`QApplication.instance() or QApplication(sys.argv)`)。
- 路径中文合法(`actions/控制流程/延时.py` 等),勿改目录名。
- `add_template` 返回 `bool`(成功 True / 无贡献回滚 False),`copy_source_templates` 据此统计成功数。
- 错误一律 `LogModel.error()`;成功的加载/操作摘要用 `LogModel.info()`。

**Files:**
- Modify: `model/step_manager.py`(冒烟块追加断言 + 追加 7 个方法)

**Interfaces:**
- Consumes: Task 1 产出的 `StepManager`(`_registry`/`_clipboard`/`load()`/`template_paths()`/`_package.write_file`/`is_file`/`remove`/`read_file`)、`model.kscp_package.KscpPackage`(`files` 是**属性**不是方法)
- Produces: `add_template(src_py, dest_dir="") -> bool`、`remove_template(path)`、`copy_template(path)`、`cut_template(path)`、`paste_template(target_dir="")`、`copy_source_templates(source_dir) -> int`;私有 `_actions_rel(dest_dir, base) -> str`、`_write_template(target, data, what) -> bool`

## Step 1: 追加失败测试(先红)——在冒烟块 `print("StepManager smoke OK")` 之前插入以下断言

```python
    # ---- 模板操作（增删复制粘贴剪切 / 拷贝入口） ----
    with tempfile.TemporaryDirectory() as td:
        LOCAL = GOOD.replace('name = "示例"', 'name = "本地"')
        # add_template：成功
        local_py = os.path.join(td, "本地步骤.py")
        with open(local_py, "w", encoding="utf-8") as fh:
            fh.write(LOCAL)
        assert mgr.add_template(local_py) is True
        assert "本地" in mgr.template_paths()
        assert pkg.is_file("actions/本地步骤.py")
        # add_template：重名无贡献 → 自动回滚
        dup_py = os.path.join(td, "重复.py")
        with open(dup_py, "w", encoding="utf-8") as fh:
            fh.write(GOOD)                       # name "示例" 顶层已有
        assert mgr.add_template(dup_py) is False
        assert not pkg.is_file("actions/重复.py")
        # copy → cut → paste 恢复
        mgr.copy_template("本地")
        assert mgr._clipboard[0] == "本地步骤.py"
        mgr.cut_template("本地")
        assert "本地" not in mgr.template_paths()
        assert not pkg.is_file("actions/本地步骤.py")
        LogModel.instance().clear()
        mgr.paste_template()
        assert "本地" in mgr.template_paths()
        assert pkg.is_file("actions/本地步骤.py")
        # 重名粘贴：不覆盖 + 日志
        LogModel.instance().clear()
        mgr.copy_template("示例")
        mgr.paste_template()
        assert any("已存在" in e.message for e in LogModel.instance().entries)
        # 粘贴到子目录
        mgr.copy_template("本地")
        mgr.paste_template("子目录")
        assert "子目录/本地" in mgr.template_paths()
        # 空剪贴板 → ValueError
        mgr._clipboard = None
        try:
            mgr.paste_template()
            raise AssertionError("空剪贴板应抛 ValueError")
        except ValueError:
            pass
        # remove_template + 未知路径
        mgr.remove_template("子目录/本地")
        assert "子目录/本地" not in mgr.template_paths()
        try:
            mgr.remove_template("不存在")
            raise AssertionError("未知路径应抛 ValueError")
        except ValueError:
            pass
        # copy_source_templates：跳过 base/__init__/__pycache__，保目录结构
        src = os.path.join(td, "src_actions")
        os.makedirs(os.path.join(src, "子目录", "__pycache__"))
        for name, content in (
                ("base.py", "pass\n"),
                ("__init__.py", "pass\n"),
                ("本地2.py", LOCAL.replace('name = "本地"', 'name = "本地2"')),
                ("子目录/深层.py", LOCAL.replace('name = "本地"', 'name = "深层"')),
                ("子目录/__pycache__/缓存.py", LOCAL)):
            with open(os.path.join(src, name), "w", encoding="utf-8") as fh:
                fh.write(content)
        assert mgr.copy_source_templates(src) == 2
        assert "本地2" in mgr.template_paths()
        assert "子目录/深层" in mgr.template_paths()
        assert not any("__pycache__" in f for f in pkg.files)
```

## Step 2: 运行确认失败(红)

Run: `python -m model.step_manager`
Expected: `AttributeError: 'StepManager' object has no attribute 'add_template'`(追加断言首个调用处;模板操作方法尚未实现,「功能缺失」红,无需再修)

## Step 3: 实现 —— 在 `template_paths()` 方法之后插入以下方法

```python
    # ================================================================
    # 模板操作（对 .py 文件；操作后自动 load() 刷新）
    # ================================================================
    def add_template(self, src_py: str, dest_dir: str = "") -> bool:
        """把本地 .py 加入工程 ``actions/<dest_dir>/``；成功 True，无贡献回滚 False。"""
        base = os.path.basename(src_py)
        if not base.endswith(".py"):
            base += ".py"
        target = self._actions_rel(dest_dir, base)
        with open(src_py, "rb") as fh:
            data = fh.read()
        return self._write_template(target, data, "添加模板")

    def _actions_rel(self, dest_dir: str, base: str) -> str:
        d = dest_dir.strip("/")
        return ("actions/%s/%s" % (d, base)) if d else ("actions/" + base)

    def _write_template(self, target: str, data: bytes, what: str) -> bool:
        """写盘 → load → 无贡献（非模板/重名被跳/注解非法）回滚删除；成功 info。"""
        self._package.write_file(target, data)
        self.load()
        if any(rel == target for _cls, rel in self._registry.values()):
            LogModel.instance().info("%s成功: %s" % (what, target))
            return True
        try:
            self._package.remove(target)
        except Exception:
            pass
        self.load()
        LogModel.instance().error(
            "%s失败, 已回滚: %s(文件中没有可注册的步骤模板)" % (what, target))
        return False

    def remove_template(self, path: str) -> None:
        """删除路径对应的模板文件；未知路径抛 ValueError。"""
        entry = self._registry.get(path)
        if entry is None:
            raise ValueError("未找到步骤模板: %r" % path)
        rel = entry[1]
        self._package.remove(rel)
        self.load()
        LogModel.instance().info("删除模板: %s" % path)

    def copy_template(self, path: str) -> None:
        """把模板文件拷入剪贴板（单槽：文件名 + 字节）；未知路径抛 ValueError。"""
        entry = self._registry.get(path)
        if entry is None:
            raise ValueError("未找到步骤模板: %r" % path)
        rel = entry[1]
        self._clipboard = (os.path.basename(rel), self._package.read_file(rel))

    def cut_template(self, path: str) -> None:
        """剪切模板 = 复制 + 删除。"""
        self.copy_template(path)
        self.remove_template(path)

    def paste_template(self, target_dir: str = "") -> None:
        """把剪贴板模板写入 ``actions/<target_dir>/``；剪贴板空抛 ValueError；
        目标已存在 → 日志报错不覆盖。"""
        if self._clipboard is None:
            raise ValueError("剪贴板为空")
        name, data = self._clipboard
        target = self._actions_rel(target_dir, name)
        if self._package.is_file(target):
            LogModel.instance().error("粘贴失败: 目标已存在 %s(不覆盖)" % target)
            return
        self._write_template(target, data, "粘贴模板")

    def copy_source_templates(self, source_dir: str) -> int:
        """把源码 ``actions/`` 下 .py 模板按相对目录全部加入工程；返回成功数。

        跳过 ``base.py`` / ``__init__.py`` / ``__pycache__``。
        """
        added = 0
        for root, dirs, files in os.walk(source_dir):
            dirs[:] = [d for d in dirs if d != "__pycache__"]
            for name in sorted(files):
                if not name.endswith(".py") or name in ("base.py", "__init__.py"):
                    continue
                src = os.path.join(root, name)
                rel_dir = os.path.relpath(root, source_dir)
                rel_dir = "" if rel_dir == "." else rel_dir.replace("\\", "/")
                if self.add_template(src, rel_dir):
                    added += 1
        return added
```

## Step 4: 运行确认通过(绿)

Run: `python -m model.step_manager`
Expected: `StepManager smoke OK`,EXIT=0

## Step 5: 全量回归验证(替代提交)

Run:
```bash
python -m model.step_manager
python -m actions.base
python -m actions.控制流程.time_delay
python -m widgets.step_io_widget
python -m model.kscp_package
python -m model.project_variable
python -m model.variable_tree
python -m model.log_model
python main.py --check
```
Expected: 全部冒烟 OK、`main --check` 无输出但 EXIT=0(以退出码判定)。
