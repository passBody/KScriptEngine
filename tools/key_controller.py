import ctypes
import time
from typing import Optional, List, Union


# ==================== 常量定义 ====================
# KEYEVENTF 标志
KEYEVENTF_KEYDOWN = 0x0000
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_EXTENDEDKEY = 0x0001

# ==================== 虚拟键码映射表 ====================
VK_CODE = {
    # 字母
    'A': 0x41, 'B': 0x42, 'C': 0x43, 'D': 0x44, 'E': 0x45,
    'F': 0x46, 'G': 0x47, 'H': 0x48, 'I': 0x49, 'J': 0x4A,
    'K': 0x4B, 'L': 0x4C, 'M': 0x4D, 'N': 0x4E, 'O': 0x4F,
    'P': 0x50, 'Q': 0x51, 'R': 0x52, 'S': 0x53, 'T': 0x54,
    'U': 0x55, 'V': 0x56, 'W': 0x57, 'X': 0x58, 'Y': 0x59, 'Z': 0x5A,
    # 数字
    '0': 0x30, '1': 0x31, '2': 0x32, '3': 0x33, '4': 0x34,
    '5': 0x35, '6': 0x36, '7': 0x37, '8': 0x38, '9': 0x39,
    # 功能键
    'F1': 0x70, 'F2': 0x71, 'F3': 0x72, 'F4': 0x73,
    'F5': 0x74, 'F6': 0x75, 'F7': 0x76, 'F8': 0x77,
    'F9': 0x78, 'F10': 0x79, 'F11': 0x7A, 'F12': 0x7B,
    # 控制键
    'CTRL': 0x11, 'CONTROL': 0x11,
    'ALT': 0x12,
    'SHIFT': 0x10,
    'WIN': 0x5B, 'LWIN': 0x5B, 'RWIN': 0x5C,
    # 方向键
    'UP': 0x26, 'DOWN': 0x28, 'LEFT': 0x25, 'RIGHT': 0x27,
    # 编辑键
    'ENTER': 0x0D, 'RETURN': 0x0D,
    'SPACE': 0x20,
    'TAB': 0x09,
    'ESC': 0x1B, 'ESCAPE': 0x1B,
    'BACKSPACE': 0x08, 'DELETE': 0x2E,
    'HOME': 0x24, 'END': 0x23,
    'PAGEUP': 0x21, 'PAGEDOWN': 0x22,
    'INSERT': 0x2D,
    'CAPSLOCK': 0x14, 'NUMLOCK': 0x90, 'SCROLLLOCK': 0x91,
    # 小键盘
    'NUMPAD0': 0x60, 'NUMPAD1': 0x61, 'NUMPAD2': 0x62,
    'NUMPAD3': 0x63, 'NUMPAD4': 0x64, 'NUMPAD5': 0x65,
    'NUMPAD6': 0x66, 'NUMPAD7': 0x67, 'NUMPAD8': 0x68, 'NUMPAD9': 0x69,
    'NUMPAD_ADD': 0x6B, 'NUMPAD_SUB': 0x6D,
    'NUMPAD_MUL': 0x6A, 'NUMPAD_DIV': 0x6F,
    'NUMPAD_DOT': 0x6E,
    # 符号
    'MINUS': 0xBD, 'EQUALS': 0xBB,
    'LBRACKET': 0xDB, 'RBRACKET': 0xDD,
    'BACKSLASH': 0xDC, 'SLASH': 0xBF,
    'SEMICOLON': 0xBA, 'QUOTE': 0xDE,
    'COMMA': 0xBC, 'DOT': 0xBE, 'TILDE': 0xC0,
}


class KeyController:
    """
    键盘控制器，基于 Windows keybd_event API 实现
    支持单键、组合键、文本输入、按键状态查询等
    """

    def __init__(self, delay: float = 0.05):
        """
        初始化键盘控制器
        :param delay: 按键按下和松开之间的默认延迟（秒）
        """
        self.delay = delay
        self.user32 = ctypes.windll.user32
        self._pressed_keys = set()  # 用于追踪当前按下的键

    # ==================== 核心底层方法 ====================

    def _get_vk_code(self, key: str) -> int:
        """获取虚拟键码，支持大小写不敏感"""
        code = VK_CODE.get(key.upper())
        if code is None:
            raise ValueError(f"未知按键: {key}")
        return code

    def _key_event(self, vk_code: int, flags: int, scan_code: int = 0):
        """
        发送键盘事件
        :param vk_code: 虚拟键码
        :param flags: 0=按下, 0x0002=松开
        :param scan_code: 硬件扫描码（通常为0）
        """
        self.user32.keybd_event(vk_code, scan_code, flags, 0)

    # ==================== 基础按键操作 ====================

    def press(self, key: str):
        """
        按下按键（不松开）
        :param key: 按键名称，如 'A', 'CTRL', 'ENTER'
        """
        vk = self._get_vk_code(key)
        self._key_event(vk, KEYEVENTF_KEYDOWN)
        self._pressed_keys.add(key.upper())

    def release(self, key: str):
        """
        松开按键
        :param key: 按键名称
        """
        vk = self._get_vk_code(key)
        self._key_event(vk, KEYEVENTF_KEYUP)
        self._pressed_keys.discard(key.upper())

    def tap(self, key: str, duration: Optional[float] = None):
        """
        敲击按键（按下 -> 等待 -> 松开）
        :param key: 按键名称
        :param duration: 按下持续时间，None 则使用默认 delay
        """
        if duration is None:
            duration = self.delay
        self.press(key)
        time.sleep(duration)
        self.release(key)

    def tap_multiple(self, *keys: str, duration: Optional[float] = None):
        """
        依次敲击多个按键
        :param keys: 按键名称列表
        :param duration: 每个按键的持续时间
        """
        for key in keys:
            self.tap(key, duration)

    # ==================== 组合键操作 ====================

    def combo(self, *keys: str, duration: Optional[float] = None):
        """
        模拟组合键：按下所有键 -> 等待 -> 按相反顺序松开
        例如: combo('CTRL', 'C')  -> Ctrl+C
              combo('ALT', 'TAB') -> Alt+Tab
        :param keys: 按键名称列表
        :param duration: 按下全部键后的等待时间
        """
        if duration is None:
            duration = self.delay
        # 按下所有键
        for key in keys:
            self.press(key)
        # 等待
        time.sleep(duration)
        # 反向松开
        for key in reversed(keys):
            self.release(key)

    # ==================== 文本输入 ====================

    def type_text(self, text: str, speed: float = 0.05):
        """
        输入文本（仅支持字母、数字和部分符号）
        :param text: 要输入的文本
        :param speed: 每个字符之间的间隔（秒）
        """
        # 需要处理 Shift 组合的特殊字符
        shift_chars = {
            '!': '1', '@': '2', '#': '3', '$': '4', '%': '5',
            '^': '6', '&': '7', '*': '8', '(': '9', ')': '0',
            '_': '-', '+': '=', '{': '[', '}': ']', '|': '\\',
            ':': ';', '"': "'", '<': ',', '>': '.', '?': '/',
            '~': '`',
        }

        for char in text:
            if char.isupper():
                # 大写字母：Shift + 字母
                self.combo('SHIFT', char, delay=0.01)
            elif char in shift_chars:
                # 需要 Shift 的符号
                base = shift_chars[char]
                self.combo('SHIFT', base, delay=0.01)
            else:
                # 普通字符（小写字母、数字、普通符号）
                self.tap(char, duration=0.01)
            time.sleep(speed)

    # ==================== 系统按键 ====================

    def show_desktop(self):
        """显示桌面 (Win + D)"""
        self.combo('WIN', 'D')

    def lock_screen(self):
        """锁屏 (Win + L)"""
        self.combo('WIN', 'L')

    def open_task_manager(self):
        """打开任务管理器 (Ctrl + Shift + Esc)"""
        self.combo('CTRL', 'SHIFT', 'ESC')

    def switch_window(self):
        """切换窗口 (Alt + Tab)"""
        self.combo('ALT', 'TAB')

    def copy(self):
        """复制 (Ctrl + C)"""
        self.combo('CTRL', 'C')

    def paste(self):
        """粘贴 (Ctrl + V)"""
        self.combo('CTRL', 'V')

    def cut(self):
        """剪切 (Ctrl + X)"""
        self.combo('CTRL', 'X')

    def select_all(self):
        """全选 (Ctrl + A)"""
        self.combo('CTRL', 'A')

    def undo(self):
        """撤销 (Ctrl + Z)"""
        self.combo('CTRL', 'Z')

    def redo(self):
        """重做 (Ctrl + Y)"""
        self.combo('CTRL', 'Y')

    def save(self):
        """保存 (Ctrl + S)"""
        self.combo('CTRL', 'S')

    def find(self):
        """查找 (Ctrl + F)"""
        self.combo('CTRL', 'F')

    # ==================== 辅助功能 ====================

    def is_pressed(self, key: str) -> bool:
        """
        检查某个键是否处于按下状态（由本控制器按下）
        :param key: 按键名称
        """
        return key.upper() in self._pressed_keys

    def reset(self):
        """松开所有被本控制器按下的键（紧急释放）"""
        for key in list(self._pressed_keys):
            try:
                self.release(key)
            except Exception:
                pass
        self._pressed_keys.clear()

    def wait(self, seconds: float):
        """等待指定时间"""
        time.sleep(seconds)

    # ==================== 特殊用法 ====================

    def hold_context(self, *keys: str):
        """
        上下文管理器：按住一组键，在代码块结束后自动松开
        用法:
            with key_ctrl.hold_context('SHIFT', 'CTRL'):
                key_ctrl.tap('A')
                key_ctrl.tap('B')
        """
        return _KeyHoldContext(self, keys)


class _KeyHoldContext:
    """用于 with 语句的上下文管理器"""

    def __init__(self, controller: KeyController, keys: tuple):
        self.controller = controller
        self.keys = keys

    def __enter__(self):
        for key in self.keys:
            self.controller.press(key)
        return self.controller

    def __exit__(self, exc_type, exc_val, exc_tb):
        for key in reversed(self.keys):
            self.controller.release(key)


# 创建控制器实例
key_ctrl = KeyController(delay=0.05)

# ==================== 使用示例 ====================
# if __name__ == "__main__":
    # 示例1: 单键敲击
    # print("敲击 A 键")
    # key_ctrl.tap('A')

    # 示例2: 组合键
    # print("执行 Ctrl+C")
    # key_ctrl.combo('CTRL', 'C')

    # 示例3: 输入文本
    # print("输入文本")
    # key_ctrl.type_text("Hello, World! 123", speed=0.05)

    # 示例4: 使用上下文管理器按住 Shift 输入大写
    # print("使用上下文管理器")
    # with key_ctrl.hold_context('SHIFT'):
    #     key_ctrl.tap('a')
    #     key_ctrl.tap('b')
    #     key_ctrl.tap('c')  # 输出 ABC
    
    # 示例5: 系统快捷键
    # print("显示桌面")
    # key_ctrl.show_desktop()
    # time.sleep(0.5)

    # print("切换窗口")
    # key_ctrl.switch_window()
