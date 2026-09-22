# KScriptEngine

python 脚本驱动引擎，将脚本独立化，积木式组装。

## 运行

```bash
python main.py                  # landing：新建 / 打开工程
python main.py xxx.kscp         # 直接打开工程
python main.py --check          # 自检（渲染后自动退出）
```

> 模拟输入到游戏窗口需以**管理员身份**运行。

## 部署到其他电脑（uv 方案）

环境由 `pyproject.toml` + `uv.lock` 锁定（Python ≥3.14、PyQt5、pynput）。
**venv 目录不能直接拷贝**（Python 路径硬编码），两条正路：

**① 目标机有网（推荐）**：装 [uv](https://docs.astral.sh/uv/) 后：

```bash
uv sync                                   # 自动装 Python + 全部依赖到 .venv
.venv\Scripts\python.exe tools/fix_qt_plugins.py   # 安装 Qt 插件指路（uv sync 重建 venv 后需重跑）
.venv\Scripts\python.exe main.py          # 运行
```

**② 目标机无网**：本机预下载 wheel + 拷贝同版本 Python 安装目录，目标机离线安装：

```bash
# 本机
uv pip download -p 3.14 --no-deps -r <(uv export --format requirements-txt) -d wheels/
# 目标机（已装 uv 与同版本 Python）
uv venv
uv pip install --no-index --find-links wheels/ -e .   # 或按 export 清单安装
```

**关于 Qt 插件弹窗**（"no Qt platform plugin could be initialized"）：
venv 等独立部署下 PyQt5 可能把插件目录解析到基础 Python 安装目录。
程序主入口已自动指路（`widgets/通用/ui_common.ensure_qt_plugin_path`）；
模块冒烟等任意脚本由 `tools/fix_qt_plugins.py` 安装的 sitecustomize 兜底
（Python 3.14 起不再从当前目录加载 sitecustomize，故须装入 site-packages）。
如仍报错，可手工把 PyQt5 安装目录下的 `PyQt5/Qt5/plugins` 整个文件夹
复制到可执行程序同级目录（用户验证可行的兜底方案）。

## 工程文件（.kscp）

ZIP 归档，内含：

```
.kscp
│  step_list.json     执行列表页 → 组/列表/步骤（v2；旧格式自动迁移为单页）
│  variables.json     全局变量树
│  composites.json    合成卡片定义（tree + 三段签名 sigs）
│  executor.json      各页热键映射（pages）+ 停止方式配置（工程自带）
├─assets/             资源（图片等）
└─actions/            步骤模板（随工程分发，打开工程用包内版本）
```

## 文件关联（双击 / 右键打开 .kscp）

双击 `.kscp` 或右键「用 KScript 打开」即启动本程序——**关联里写死的是当前这份
代码的绝对路径**，所以换目录后旧关联会指向已经不存在的文件，必须重挂：

| 想做什么 | 双击 |
|---|---|
| 关联到**当前目录** | `安装-kscp文件关联.bat` |
| 从当前目录摘掉关联 | `卸载-kscp文件关联.bat` |

**换目录**：先在旧目录双击卸载，再到新目录双击安装。

两个 bat 都调 `tools/kscp_assoc.py`（可单独用命令行跑，支持 `--dry-run` 先看
再写）：

```bash
python tools/kscp_assoc.py install --dry-run   # 只打印将要写入的 11 条，不动注册表
python tools/kscp_assoc.py install             # 真装
python tools/kscp_assoc.py status              # 当前装没装、指向哪个目录
python tools/kscp_assoc.py uninstall           # 卸载
python tools/kscp_assoc.py selfcheck           # 纯函数自检 + 沙箱键往返演练
```

写入位置与行为：

- **只动 `HKCU`（当前用户）**，不需要管理员权限，卸载干净不留残渣。
- 注册 ProgID `KScript.Project` + `.kscp` 扩展名 + 图标 `icon/kscp.ico`。
- 右键菜单两项：**用 KScript 打开**（`shell\open`）与**以管理员身份运行**
  （`shell\runas`，带 UAC 盾牌图标）——模拟输入到游戏窗口需要后者。
- 卸载**不会**盲删 `.kscp`：若该扩展名已被别的程序占用，只摘掉本程序登记的
  值，保留对方的关联（归属校验，见 `tools/kscp_assoc.py: plan_uninstall`）。
- 启动走 `tools/kscp_launch.pyw`（pythonw，无黑窗）。启动失败会弹 MessageBox
  并写堆栈到项目根目录 `kscp_launch_error.log`（已在 `.gitignore`）。
- 图标由 `icon/make_icon.py` 生成（同时产出 `kscript.*` 程序图标与
  `kscp.*` 文件图标），改图标后重跑该脚本即可。

## 多执行列表与热键

步骤列表树按「执行列表页」组织：树顶标题（右击重命名）+ 右侧下拉切换 +
「添加页/删除该页」按钮。**每页可在设置弹窗（活动栏齿轮）绑定热键**
（表格逐页配置，留空 = 不绑定），工程打开后热键常驻监听：

- 按页热键 → 执行该页全部列表；执行中再按 → 停止（停止方式见设置弹窗）
- **热键支持**：单键（如 `、f）、功能键（F1…F12）、组合（Ctrl+Alt+I）、
  单独修饰键（Ctrl）——设置弹窗点击热键栏后直接按下目标按键即可捕获，
  退格清空 = 不绑定；「Ctrl」与「Ctrl+Alt+I」并存时组合优先
  （单独按 Ctrl 松开才触发）
- **多页可同时执行**（各页独立线程，共享全局变量为 last-writer-wins）
- 活动栏「执行」按钮 = **全部页待命开关**：点击变绿后所有页开始监听各自
  热键（不执行步骤），按某页热键触发该页执行/停止；再点关闭待命
  （执行中的页会同时停止）
- 活动栏「最小化」按钮 = **最小化至系统托盘**（托盘图标单击/双击恢复，
  右键菜单「显示主窗口/退出」）；**最小化热键**（设置弹窗配置，全局生效）
  随时最小化至托盘/还原程序
- 热键勿与步骤按键冲突（模拟按键也会被监听）

## 测试

无测试框架，每模块自带 `__main__` 冒烟（`python -m <模块>` 运行）。
全量回归一条命令：

```bash
python tests/smoke_all.py   # 48 模块冒烟 + 1 个自检（工程加载 + sample.kscp 渲染），失败非零退出
```

## 文档

- **docs/工程分析.md** —— 工程全景分析（架构/模块表/评审债单/实现状态，随代码维护）
- **docs/README.md** —— 文档导航索引
- **docs/superpowers/specs & plans/** —— 设计文档存档（15 spec + 10 plan，历史时点）
- **.claude/skills/** —— 项目技能：添加 action / 添加变量类型

