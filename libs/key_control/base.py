"""输入设备层：键鼠模拟 + 全局监听
# 内嵌自 ../MouseAndKeyboardMacros/key_control/base.py（2026-08-30 复制，未修改逻辑）

SwitchController / PipeController 共享的设备操作都在这里。
模拟输入到游戏窗口需要管理员权限运行 Python。
"""

import logging
import threading
import time

from pynput import mouse, keyboard

logger = logging.getLogger(__name__)

# key_click 支持的命名按键（多字符按键名）
NAMED_KEYS = {
    'space': keyboard.Key.space,
    'enter': keyboard.Key.enter,
    'tab': keyboard.Key.tab,
    'esc': keyboard.Key.esc,
    'backspace': keyboard.Key.backspace,
    'shift': keyboard.Key.shift,
    'ctrl': keyboard.Key.ctrl,
    'alt': keyboard.Key.alt,
    'up': keyboard.Key.up,
    'down': keyboard.Key.down,
    'left': keyboard.Key.left,
    'right': keyboard.Key.right,
    'home': keyboard.Key.home,
    'end': keyboard.Key.end,
    'pageup': keyboard.Key.page_up,
    'pagedown': keyboard.Key.page_down,
}


def validate_char_key(key, name):
    """校验单个字符按键（开关/退出键），返回小写形式，不合法抛异常。"""
    if not isinstance(key, str):
        raise TypeError(f'{name}类型应当为 str，实际是 {type(key).__name__}')
    if len(key) != 1:
        raise ValueError(f'{name}长度应当为 1')
    if '0' <= key <= '9':
        raise ValueError(f'{name}不应该是 0~9 的数字（数字用来选择参数）')
    return key.lower()


def key_char(key):
    """从 pynput 按键对象提取字符（纯函数，便于测试）。

    :return: 小写字符；功能键、无字符按键返回 None
    """
    if isinstance(key, keyboard.KeyCode) and key.char is not None:
        return key.char.lower()
    return None


class InputControl:
    """键鼠模拟与全局监听。"""

    def __init__(self):
        self.mouse_control = mouse.Controller()
        self.keyboard_control = keyboard.Controller()
        self.mouse_listener = None
        self.keyboard_listener = None
        self.is_listening = False

    # --- 模拟操作 ---

    def key_click(self, key, duration=None):
        """
            模拟键盘按 key。
            :param key: 按键文本（例如：'q'），也支持命名按键（如 'space'、'enter'）。
                        多字符按键（如 'ae'）为同时按下的和弦。
            :param duration: 按下后多久松开（单位s）。
        """
        if key in NAMED_KEYS:
            keys = [NAMED_KEYS[key]]
        else:
            keys = list(key)
        for k in keys:
            self.keyboard_control.press(k)
        if duration:
            time.sleep(duration)
        for k in keys:
            self.keyboard_control.release(k)

    def mouse_click(self, x, y, duration=None, restore_position=False):
        """
            在坐标（x, y）处模拟鼠标左键点击。
            :param x: 横坐标。
            :param y: 纵坐标。
            :param duration: 按下后多久松开（单位s）。
            :param restore_position: 点击后是否把鼠标移回原位。
        """
        old_position = self.mouse_control.position if restore_position else None
        self.mouse_control.position = (x, y)
        self.mouse_control.press(mouse.Button.left)
        if duration:
            time.sleep(duration)
        self.mouse_control.release(mouse.Button.left)
        if restore_position:
            self.mouse_control.position = old_position

    @property
    def mouse_position(self):
        """当前鼠标坐标 (x, y)。"""
        return self.mouse_control.position

    # --- 全局监听 ---

    def _create_keyboard_listener(self, on_press=None, on_release=None):
        """创建键盘设备监听器（阻塞，应放在独立线程）。"""
        try:
            with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
                self.keyboard_listener = listener
                listener.join()
        except Exception:
            logger.exception('键盘监听启动失败')

    def _create_mouse_listener(self, on_click=None):
        """创建鼠标设备监听器（阻塞，应放在独立线程）。"""
        try:
            with mouse.Listener(on_click=on_click) as listener:
                self.mouse_listener = listener
                listener.join()
        except Exception:
            logger.exception('鼠标监听启动失败')

    def start_key_listen(self, on_press=None, on_release=None):
        """在后台线程启动键盘监听。"""
        thread = threading.Thread(
            target=self._create_keyboard_listener,
            args=(on_press, on_release), daemon=True)
        thread.start()
        self.is_listening = True

    def start_mouse_listen(self, on_click=None):
        """在后台线程启动鼠标监听。"""
        thread = threading.Thread(
            target=self._create_mouse_listener,
            args=(on_click,), daemon=True)
        thread.start()
        self.is_listening = True

    def stop_listeners(self):
        """关闭全部设备监听。"""
        if self.mouse_listener is not None:
            self.mouse_listener.stop()
            self.mouse_listener = None
        if self.keyboard_listener is not None:
            self.keyboard_listener.stop()
            self.keyboard_listener = None
        self.is_listening = False


if __name__ == "__main__":
    from libs.key_control import InputControl
    from libs.key_control.base import NAMED_KEYS

    ctl = InputControl()
    assert hasattr(ctl, "key_click") and hasattr(ctl, "mouse_click")
    assert hasattr(ctl, "keyboard_control") and hasattr(ctl, "mouse_control")
    # NAMED_KEYS 覆盖 spec 需要的最小集合
    for k in ("space", "enter", "esc", "shift", "ctrl", "alt"):
        assert k in NAMED_KEYS
    print("key_control smoke OK")
