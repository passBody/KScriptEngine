# -*- coding: utf-8 -*-
"""``.kscp`` 文件关联的安装 / 卸载 / 查询（注册表写入全部集中在 **HKCU**）。

用法::

    python tools/kscp_assoc.py install   [--dry-run] [--python <pythonw.exe>]
    python tools/kscp_assoc.py uninstall [--dry-run]
    python tools/kscp_assoc.py status
    python tools/kscp_assoc.py selfcheck # 纯函数自检 + 沙箱键往返演练（不动真实关联）
    python -m tools.kscp_assoc           # 无参 = 仅纯函数自检（绝不碰注册表）

## 为什么注册表操作不写在 .bat 里

``安装-kscp文件关联.bat`` / ``卸载-kscp文件关联.bat`` 只负责定位解释器并调用
本模块，真正的注册表读写在 Python 里做，理由三条：

1. **编码**：``winreg`` 是 UTF-16 原生，``KScript 工程``「用 KScript 打开」这类
   中文值不会踩 cmd 按 GBK 解析 UTF-8 的坑；
2. **可审**：``--dry-run`` 能逐条打印将要写入的键/名/值/类型，一个字节都不写；
3. **可测**：纯逻辑（:func:`plan_install` / :func:`plan_uninstall`）与 IO
   （:func:`apply_set` / :func:`apply_delete`）分离，无参运行即可单测纯逻辑。

## 注册表布局（HKCU\\Software\\Classes 下）

ProgID = ``KScript.Project``，双击与右键「打开」都走 ``shell\\open``，
额外注册 ``shell\\runas`` 让右键出现「以管理员身份运行」（README：模拟输入到
游戏窗口需管理员运行，而资源管理器对非 exe 文件默认不提供该项）。

## 卸载的归属校验（安全阀）

``HKCU\\Software\\Classes\\.kscp`` **只在**其 (默认) 值为 ``KScript.Project``
或为空时才整棵删除；若已被别的程序占用，则只摘掉本模块写入的
``OpenWithProgids\\KScript.Project`` 一个值，绝不动别人的关联。
``FileExts\\.kscp\\UserChoice`` 同理，仅当 ProgId 是我们时才删。
"""

import os
import sys
from collections import namedtuple

# ---------------------------------------------------------------- 常量

PROG_ID = "KScript.Project"
EXT = ".kscp"

FRIENDLY_TYPE = "KScript 工程"        # 资源管理器「类型」列显示的名字
VERB_OPEN = "用 KScript 打开(&O)"
VERB_RUNAS = "以管理员身份运行(&A)"

# 以下均为 **HKCU 下的完整路径**（不含 HKEY_CURRENT_USER 根）。
# 注意：IO 层的 base 参数默认为空串（=路径已是完整的），**只在沙箱演练时**
# 才传非空值加前缀——曾因常量已含 CLASSES 而 base 又拼一次，把键写进了
# HKCU\Software\Classes\Software\Classes\...（双重前缀）。
CLASSES = r"Software\Classes"
FILE_EXTS = r"Software\Microsoft\Windows\CurrentVersion\Explorer\FileExts"

EXT_KEY = CLASSES + "\\" + EXT
PROG_KEY = CLASSES + "\\" + PROG_ID
OPENWITH_KEY = EXT_KEY + r"\OpenWithProgids"
USERCHOICE_KEY = FILE_EXTS + "\\" + EXT + r"\UserChoice"

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LAUNCHER = os.path.join(ROOT, "tools", "kscp_launch.pyw")
ICON = os.path.join(ROOT, "icon", "kscp.ico")
VENV_PYTHONW = os.path.join(ROOT, ".venv", "Scripts", "pythonw.exe")

# 注册表值类型（延迟 import winreg：本模块的纯逻辑部分不依赖 Windows）
REG_SZ, REG_NONE = 1, 0

# 一条待写条目：相对键路径 / 值名（"" = (默认)）/ 值 / 类型
Entry = namedtuple("Entry", "path name value type")
# 卸载计划：待删键（递归）/ 待删值（键, 名）
UninstallPlan = namedtuple("UninstallPlan", "keys values")


def _p(text: str = "") -> None:
    """中文路径/值在非 CJK 控制台下 print 会 UnicodeEncodeError → 安全降级。"""
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode("unicode_escape").decode("ascii"))


# ---------------------------------------------------------------- 纯逻辑

def build_command(pythonw: str, launcher: str) -> str:
    """shell 命令串：``"<pythonw>" "<launcher>" "%1"``（%1 = 被双击的 .kscp）。"""
    return '"%s" "%s" "%%1"' % (pythonw, launcher)


def plan_install(pythonw: str, launcher: str, icon: str) -> list:
    """返回安装需写入的全部条目（无副作用，可打印审阅 / 单测）。"""
    cmd = build_command(pythonw, launcher)
    return [
        # —— 扩展名 → ProgID（双击的默认打开方式）——
        Entry(EXT_KEY, "", PROG_ID, REG_SZ),
        Entry(EXT_KEY, "PerceivedType", "document", REG_SZ),
        # 让 ProgID 出现在右键「打开方式」列表里（Windows 自身写的就是 REG_NONE 空值）
        Entry(OPENWITH_KEY, PROG_ID, b"", REG_NONE),
        # —— ProgID 本体 ——
        Entry(PROG_KEY, "", FRIENDLY_TYPE, REG_SZ),
        Entry(PROG_KEY + r"\DefaultIcon", "", '"%s",0' % icon, REG_SZ),
        Entry(PROG_KEY + r"\shell", "", "open", REG_SZ),          # 默认动词
        Entry(PROG_KEY + r"\shell\open", "", VERB_OPEN, REG_SZ),
        Entry(PROG_KEY + r"\shell\open\command", "", cmd, REG_SZ),
        # runas：资源管理器据此显示「以管理员身份运行」+ UAC 盾牌
        Entry(PROG_KEY + r"\shell\runas", "", VERB_RUNAS, REG_SZ),
        Entry(PROG_KEY + r"\shell\runas", "HasLUAShield", "", REG_SZ),
        Entry(PROG_KEY + r"\shell\runas\command", "", cmd, REG_SZ),
    ]


def plan_uninstall(ext_default, user_choice) -> UninstallPlan:
    """按当前注册表状态给出卸载计划（含归属校验，无副作用）。

    :param ext_default: ``Software\\Classes\\.kscp`` 的 (默认) 值；键不存在传 None
    :param user_choice: ``FileExts\\.kscp\\UserChoice`` 的 ProgId；键不存在传 None
    """
    keys = [PROG_KEY]                     # ProgID 整棵是我们的，无条件删
    values = []
    if ext_default in (None, PROG_ID):
        keys.append(EXT_KEY)              # 我们（或没人）占着 → 整棵删
    else:
        values.append((OPENWITH_KEY, PROG_ID))   # 别人占着 → 只摘自己那一个值
    if user_choice == PROG_ID:
        keys.append(USERCHOICE_KEY)
    return UninstallPlan(keys, values)


def describe_plan(entries) -> list:
    """把条目列表转成可读行（dry-run / 安装回显共用）。"""
    lines = []
    for e in entries:
        tname = {REG_SZ: "REG_SZ", REG_NONE: "REG_NONE"}.get(e.type, str(e.type))
        shown = e.value.decode("ascii", "replace") if isinstance(e.value, bytes) else e.value
        lines.append("HKCU\\%s\\%s = %r  [%s]" % (e.path, e.name or "(默认)", shown, tname))
    return lines


# ---------------------------------------------------------------- 注册表 IO

def _winreg():
    import winreg
    return winreg


def _full(path: str, base: str = "") -> str:
    """HKCU 下的真实键路径。

    ``base`` 为空（默认）→ path 本身已是完整路径（如 ``Software\\Classes\\.kscp``）；
    ``base`` 非空 → 仅供 :func:`_sandbox_roundtrip` 加沙箱前缀用。

    这里**硬性要求**完整路径：曾把裸扩展名（``".kscp"``）当路径传进来，读值永远
    返回 None 且不报错，直接导致卸载的归属校验把「被别的程序占用的 .kscp」误判成
    「没人占用」而整棵删除。宁可当场炸掉，也不要静默失效。
    """
    if base:
        return base + "\\" + path
    if not path.startswith("Software\\"):
        raise ValueError("键路径必须是 HKCU 下的完整路径（Software\\...），收到 %r" % path)
    return path


def read_value(path: str, name: str, base: str = ""):
    """读 HKCU 下某值 → ``(数据, 类型)``；键或值不存在 → None。

    刻意返回**元组**而不是裸数据：``OpenWithProgids`` 用的是 REG_NONE 空值，
    其数据本身读回就是 ``None``，裸返回会和"不存在"撞车（实测 QueryValueEx
    对 REG_NONE 返回 ``(None, 0)`` 而非抛错）。
    """
    winreg = _winreg()
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _full(path, base)) as k:
            return winreg.QueryValueEx(k, name)
    except OSError:
        return None


def read_text(path: str, name: str, base: str = ""):
    """REG_SZ 场景的便捷版：返回字符串；不存在或不是字符串 → None。"""
    got = read_value(path, name, base)
    if got is None or not isinstance(got[0], str):
        return None
    return got[0]


def apply_set(entries, base: str = "") -> None:
    """逐条写入（CreateKeyEx 自动补建中间层）。"""
    winreg = _winreg()
    for e in entries:
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, _full(e.path, base),
                                0, winreg.KEY_WRITE) as k:
            winreg.SetValueEx(k, e.name, 0, e.type, e.value)


def _delete_tree(base_path: str) -> list:
    """递归删除 HKCU\\<base_path>，返回实际删掉的键路径（深→浅）。"""
    winreg = _winreg()
    gone = []

    def walk(path):
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path, 0, winreg.KEY_ALL_ACCESS) as k:
                subs = []
                i = 0
                while True:
                    try:
                        subs.append(winreg.EnumKey(k, i))
                        i += 1
                    except OSError:
                        break
        except OSError:
            return
        for sub in subs:
            walk(path + "\\" + sub)
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, path)
            gone.append(path)
        except OSError:
            pass    # 已被别处删掉 / 权限不足：不阻断剩余清理

    walk(base_path)
    return gone


def _key_exists(path: str) -> bool:
    winreg = _winreg()
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path):
            return True
    except OSError:
        return False


def apply_delete(plan: UninstallPlan, base: str = "") -> list:
    """执行卸载计划，返回实际删除的键路径（值删除只回显不收集）。"""
    winreg = _winreg()
    for path, name in plan.values:
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _full(path, base),
                                0, winreg.KEY_SET_VALUE) as k:
                winreg.DeleteValue(k, name)
        except OSError:
            pass
    gone = []
    for path in plan.keys:
        gone += _delete_tree(_full(path, base))
    return gone


def notify_shell() -> bool:
    """SHChangeNotify(SHCNE_ASSOCCHANGED)：让资源管理器立刻刷新关联与图标。

    比 ``ie4uinit.exe -show`` 可靠（不必重启 explorer，也不挑系统版本）。
    """
    if os.name != "nt":
        return False
    try:
        import ctypes
        ctypes.windll.shell32.SHChangeNotify(0x08000000, 0x0000, None, None)
        return True
    except (AttributeError, OSError):
        return False


# ---------------------------------------------------------------- 解释器定位

def resolve_pythonw(override=None):
    """定位注册到 shell 命令里的 pythonw.exe；找不到返回 None。

    只认 ``<项目>\\.venv\\Scripts\\pythonw.exe``（或显式 ``--python``）——
    系统 Python 没装 PyQt5，注册上去双击必然打不开，宁可拒绝安装。
    """
    if override:
        return os.path.abspath(override)
    if os.path.isfile(VENV_PYTHONW):
        return VENV_PYTHONW
    return None


def _precheck(pythonw) -> list:
    """安装前置检查：返回问题列表（空 = 可安装）。"""
    problems = []
    if pythonw is None:
        problems.append("未找到 %s\n"
                        "    → 本机尚未建好运行环境，先在本目录执行：uv sync\n"
                        "    → 若 Python 装在别处，用 --python <pythonw.exe 绝对路径> 指定"
                        % VENV_PYTHONW)
    elif not os.path.isfile(pythonw):
        problems.append("指定的解释器不存在：%s" % pythonw)
    for label, path in (("启动器", LAUNCHER), ("图标", ICON)):
        if not os.path.isfile(path):
            problems.append("%s缺失：%s" % (label, path))
    return problems


# ---------------------------------------------------------------- 子命令

def _cmd_install(argv) -> int:
    dry, override = False, None
    i = 0
    while i < len(argv):
        if argv[i] == "--dry-run":
            dry = True
        elif argv[i] == "--python" and i + 1 < len(argv):
            i += 1
            override = argv[i]
        else:
            _p("未知参数: %s" % argv[i])
            return 2
        i += 1

    pythonw = resolve_pythonw(override)
    problems = _precheck(pythonw)
    if problems:
        _p("安装中止，前置检查未通过：")
        for p in problems:
            _p("  · " + p)
        return 1

    entries = plan_install(pythonw, LAUNCHER, ICON)
    _p("工程目录：%s" % ROOT)
    _p("将写入以下 %d 条注册表项（HKCU，仅当前用户）：" % len(entries))
    for line in describe_plan(entries):
        _p("  " + line)

    # 提醒覆盖旧路径（换目录场景：应先在旧目录卸载）
    old = read_text(PROG_KEY + r"\shell\open\command", "")
    if old and old != build_command(pythonw, LAUNCHER):
        _p("")
        _p("注意：检测到已有旧关联，将被本次覆盖（不影响其它程序）：")
        _p("  旧命令：%s" % old)

    _p("")
    if dry:
        _p("[dry-run] 未写入任何内容。去掉 --dry-run 即真正安装。")
        return 0

    apply_set(entries)
    # 已经「始终用别的程序打开」过 .kscp 的话，UserChoice 会压过上面的 Classes 关联；
    # 程序化**写** UserChoice 被系统拒绝，但**删**允许 —— 删掉后回落本关联。
    uc = read_text(USERCHOICE_KEY, "ProgId")
    if uc and uc != PROG_ID:
        _p("检测到旧的「始终使用」选择（%s），已清除以便关联生效。" % uc)
        _delete_tree(USERCHOICE_KEY)

    _p("安装完成。" + ("已通知资源管理器刷新。" if notify_shell() else ""))
    _p("  · 双击 .kscp → 用 %s 打开" % os.path.basename(pythonw))
    _p("  · 右键 → 「%s」/「%s」" % (VERB_OPEN.replace("(&O)", ""),
                                     VERB_RUNAS.replace("(&A)", "")))
    return 0


def _cmd_uninstall(argv) -> int:
    dry = False
    for a in argv:
        if a == "--dry-run":
            dry = True
        else:
            _p("未知参数: %s" % a)
            return 2

    ext_default = read_text(EXT_KEY, "")
    user_choice = read_text(USERCHOICE_KEY, "ProgId")
    if ext_default is None and user_choice is None \
            and read_text(PROG_KEY, "") is None:
        _p("未检测到 KScript 文件关联，无需卸载。")
        return 0

    plan = plan_uninstall(ext_default, user_choice)
    _p("将删除：")
    for path in plan.keys:
        _p("  HKCU\\%s   （整棵，含子键）" % path)
    for path, name in plan.values:
        _p("  HKCU\\%s\\%s   （仅此值）" % (path, name))
    if ext_default not in (None, PROG_ID):
        _p("")
        _p("注：.kscp 已被其它程序占用（(默认)=%s），保留其关联，只摘掉本程序的值。"
           % ext_default)

    _p("")
    if dry:
        _p("[dry-run] 未删除任何内容。去掉 --dry-run 即真正卸载。")
        return 0

    gone = apply_delete(plan)
    for path in gone:
        _p("  已删除 HKCU\\%s" % path)
    _p("卸载完成。" + ("已通知资源管理器刷新。" if notify_shell() else ""))
    return 0


def _cmd_status(argv) -> int:
    if argv:
        _p("status 不接受参数：%s" % " ".join(argv))
        return 2
    cmd = read_text(PROG_KEY + r"\shell\open\command", "")
    if not cmd:
        _p("未安装：HKCU\\%s 下没有 shell\\open\\command。" % PROG_KEY)
        return 1
    _p("已安装。")
    _p("  ProgID    : %s" % PROG_ID)
    _p("  类型名    : %s" % read_text(PROG_KEY, ""))
    _p("  图标      : %s" % read_text(PROG_KEY + r"\DefaultIcon", ""))
    _p("  打开命令  : %s" % cmd)
    _p("  默认打开  : %s" % (read_text(EXT_KEY, "") or "(未设置)"))
    want = build_command(resolve_pythonw() or VENV_PYTHONW, LAUNCHER)
    if cmd != want:
        _p("  ⚠ 该关联指向的是**别的目录**（当前项目目录是 %s）。" % ROOT)
        _p("    换目录后请先在旧目录卸载，再在本目录安装。")
    return 0


USAGE = """用法: python tools/kscp_assoc.py <子命令> [选项]

  install   [--dry-run] [--python <pythonw.exe>]   注册 .kscp 关联（HKCU）
  uninstall [--dry-run]                            移除本程序注册的全部键值
  status                                           查看当前关联状态
  selfcheck                                        纯函数自检 + 沙箱键往返演练

  --dry-run   只打印将要做的事，不写注册表
  --python    指定 pythonw.exe（默认 <项目>\\.venv\\Scripts\\pythonw.exe）

无参数运行 = 仅纯函数自检（绝不接触注册表）。
"""

# 沙箱演练用的临时键：与真实关联同一套条目与代码路径，但键名独立、用后即删
SMOKE_BASE = r"Software\KScriptAssocSelfCheck"


def _selftest() -> int:
    """纯函数自检：不接触真实注册表（IO 层不参与）。"""
    pw = r"C:\demo\.venv\Scripts\pythonw.exe"
    lc = r"C:\demo\tools\kscp_launch.pyw"
    ic = r"C:\demo\icon\kscp.ico"

    # build_command：两处引号 + %1 原样保留（不被 % 格式化吃掉）
    cmd = build_command(pw, lc)
    assert cmd == '"%s" "%s" "%%1"' % (pw, lc), cmd
    # 引号结构：恰好三个被引号包住的字段，顺序为 pythonw / launcher / %1
    # （路径含空格时缺引号会被 shell 拆断，故此断言必须先过）
    assert [s for s in cmd.split('"') if s.strip()] == [pw, lc, "%1"], cmd
    spaced = build_command(r"C:\a b\pythonw.exe", r"C:\c d\launch.pyw")
    assert [s for s in spaced.split('"') if s.strip()] == \
        [r"C:\a b\pythonw.exe", r"C:\c d\launch.pyw", "%1"], spaced

    # plan_install：条目集合与关键键值
    entries = plan_install(pw, lc, ic)
    assert len(entries) == 11, len(entries)
    by = {(e.path, e.name): e for e in entries}
    assert by[(EXT_KEY, "")].value == PROG_ID
    assert by[(EXT_KEY, "")].type == REG_SZ
    assert by[(EXT_KEY, "PerceivedType")].value == "document"
    # OpenWithProgids 用 REG_NONE 空值（Windows 自身写法）
    assert by[(OPENWITH_KEY, PROG_ID)].value == b"" and by[(OPENWITH_KEY, PROG_ID)].type == REG_NONE
    assert by[(PROG_KEY, "")].value == FRIENDLY_TYPE
    assert by[(PROG_KEY + r"\DefaultIcon", "")].value == '"%s",0' % ic
    assert by[(PROG_KEY + r"\shell", "")].value == "open"
    # open 与 runas 必须同一条命令
    assert by[(PROG_KEY + r"\shell\open\command", "")].value == cmd
    assert by[(PROG_KEY + r"\shell\runas\command", "")].value == cmd
    assert by[(PROG_KEY + r"\shell\runas", "HasLUAShield")].value == ""
    # 所有条目都落在 HKCU\Software\Classes 下（本模块绝不写其它地方）
    assert all(e.path.startswith(CLASSES + "\\") for e in entries), "越界写入"

    # plan_uninstall 归属校验三分支
    p = plan_uninstall(PROG_ID, PROG_ID)
    assert p.keys == [PROG_KEY, EXT_KEY, USERCHOICE_KEY] and p.values == [], p
    p = plan_uninstall(None, None)                       # 没人占用 → 整棵删
    assert p.keys == [PROG_KEY, EXT_KEY] and p.values == [], p
    p = plan_uninstall("Other.App", None)                # 被别人占用 → 保留其关联
    assert p.keys == [PROG_KEY] and p.values == [(OPENWITH_KEY, PROG_ID)], p
    p = plan_uninstall("Other.App", "Other.App")         # UserChoice 不是我们的 → 不删
    assert p.keys == [PROG_KEY] and p.values == [(OPENWITH_KEY, PROG_ID)], p

    # describe_plan：REG_NONE 的 bytes 值不炸
    assert any("REG_NONE" in ln for ln in describe_plan(entries))

    # —— 路径前缀回归（曾真实踩坑）——
    # 常量已是 HKCU 下的**完整**路径，默认 base 必须原样使用；若 IO 层再拼一次
    # 就会写进 HKCU\Software\Classes\Software\Classes\... 这种无意义位置，
    # 关联看着"装成功了"（自家 status 自洽）却对资源管理器完全无效。
    assert _full(EXT_KEY) == EXT_KEY == r"Software\Classes\.kscp"
    assert _full(PROG_KEY) == r"Software\Classes\KScript.Project"
    assert _full(USERCHOICE_KEY) == r"Software\Microsoft\Windows\CurrentVersion" \
                                    r"\Explorer\FileExts\.kscp\UserChoice"
    for e in entries:
        assert "Classes\\Software\\Classes" not in _full(e.path), "双重前缀回归"
    # 沙箱前缀只在显式传入时生效
    assert _full(EXT_KEY, SMOKE_BASE) == SMOKE_BASE + "\\" + EXT_KEY
    # 裸扩展名（".kscp"）不是键路径：曾经误传导致读值恒为 None，
    # 卸载的归属校验因此把"别人占用的 .kscp"误判为"没人占用"而整棵删除。
    try:
        _full(EXT)
    except ValueError:
        pass
    else:
        raise AssertionError("_full 接受了裸扩展名 %r（应拒绝）" % EXT)
    return 0


def _sandbox_roundtrip() -> None:
    """在临时键下演练 IO 层：写入 → 逐条读回比对 → 递归删除 → 确认清空。

    条目与代码路径和真实安装**完全一致**，只是键名前缀换成
    ``HKCU\\Software\\KScriptAssocSelfCheck``，绝不触碰真实关联。
    这一步是专门用来兜住 winreg 的类型坑（如 REG_NONE 空值读回是 ``None``）。
    """
    entries = plan_install(r"C:\selfcheck\pythonw.exe",
                           r"C:\selfcheck\tools\kscp_launch.pyw",
                           r"C:\selfcheck\icon\kscp.ico")
    _delete_tree(SMOKE_BASE)                      # 清掉上次可能的残留
    try:
        apply_set(entries, base=SMOKE_BASE)
        for e in entries:
            got = read_value(e.path, e.name, base=SMOKE_BASE)
            assert got is not None, "写入后读不到：%s\\%s" % (e.path, e.name)
            data, typ = got
            if e.type == REG_NONE:
                # 实测：REG_NONE 写入 b""，QueryValueEx 读回的是 None（不是 b""）——
                # 两侧都归一成 None 再比，否则这条永远"不符"。
                data, want = None, None
            else:
                want = e.value.decode("ascii") if isinstance(e.value, bytes) else e.value
            assert data == want, "%s\\%s 数据不符：%r != %r" % (e.path, e.name, data, want)
            assert typ == e.type, "%s\\%s 类型不符：%r != %r" % (e.path, e.name, typ, e.type)
    finally:
        _delete_tree(SMOKE_BASE)
    assert not _key_exists(SMOKE_BASE), "沙箱键未清干净：%s" % SMOKE_BASE


def _cmd_selfcheck(argv) -> int:
    if argv:
        _p("selfcheck 不接受参数：%s" % " ".join(argv))
        return 2
    before = read_text(EXT_KEY, "")
    _p("1/2 纯函数自检 ...")
    _selftest()
    _p("    OK")
    _p("2/2 沙箱键往返演练（HKCU\\%s，用后即删）..." % SMOKE_BASE)
    _sandbox_roundtrip()
    _p("    OK")
    assert read_text(EXT_KEY, "") == before, "演练意外改动了真实关联！"
    _p("")
    _p("全部通过。真实关联（HKCU\\%s）未被触碰。" % CLASSES)
    return 0


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        _selftest()
        _p("自检通过（纯逻辑，未接触注册表）。")
        _p("")
        _p(USAGE)
        return 0
    if argv[0] in ("-h", "--help"):
        _p(USAGE)
        return 0
    cmd, rest = argv[0], argv[1:]
    if cmd == "install":
        return _cmd_install(rest)
    if cmd == "uninstall":
        return _cmd_uninstall(rest)
    if cmd == "status":
        return _cmd_status(rest)
    if cmd == "selfcheck":
        return _cmd_selfcheck(rest)
    _p("未知子命令: %s" % cmd)
    _p("")
    _p(USAGE)
    return 2


if __name__ == "__main__":
    sys.exit(main())
