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
程序已在启动时自动指路（`widgets/ui_common.ensure_qt_plugin_path`）；
如仍报错，可手工把 PyQt5 安装目录下的 `PyQt5/Qt5/plugins` 整个文件夹
复制到可执行程序同级目录（用户验证可行的兜底方案）。

## 工程文件（.kscp）

ZIP 归档，内含：

```
.kscp
│  step_list.json     步骤列表（组/列表/步骤，执行序）
│  variables.json     全局变量树
│  executor.json      执行热键配置（工程自带）
├─assets/             资源（图片等）
└─actions/            步骤模板（随工程分发，打开工程用包内版本）
```

## 测试

无测试框架，每模块自带 `__main__` 冒烟（`python -m <模块>` 运行）。
全量回归：所有模块冒烟 + `main.py sample.kscp --check` +
`main.py qwer.kscp --check` + `demo_resource_tree.py --check`。
