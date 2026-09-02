import ctypes
from ctypes import wintypes
import time

# 加载 Windows 用户32库
user32 = ctypes.windll.user32

# 定义 Windows API 所需的常量
MOUSEEVENTF_MOVE = 0x0001          # 移动鼠标
MOUSEEVENTF_ABSOLUTE = 0x8000      # 绝对坐标标志（配合 MOVE 使用）
MOUSEEVENTF_LEFTDOWN = 0x0002      # 左键按下
MOUSEEVENTF_LEFTUP = 0x0004        # 左键松开
MOUSEEVENTF_RIGHTDOWN = 0x0008     # 右键按下
MOUSEEVENTF_RIGHTUP = 0x0010       # 右键松开
MOUSEEVENTF_MIDDLEDOWN = 0x0020    # 中键按下
MOUSEEVENTF_MIDDLEUP = 0x0040      # 中键松开
MOUSEEVENTF_WHEEL = 0x0800         # 滚轮滚动

# 滚轮滚动量：通常 120 为一个"刻度"
# 正数 = 向上滚动，负数 = 向下滚动
WHEEL_DELTA = 120

# 定义 C 结构体（用于 SendInput）
class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

class MouseInput(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))
    ]

class Input_I(ctypes.Union):
    _fields_ = [("mi", MouseInput)]

class Input(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("ii", Input_I)]

class MouseController:
    """基于 ctypes 的鼠标控制器"""
    
    def __init__(self):
        # 获取屏幕尺寸（用于绝对坐标转换）
        self.screen_width = user32.GetSystemMetrics(0)
        self.screen_height = user32.GetSystemMetrics(1)
    
    # ==================== 1. 获取鼠标位置 ====================
    def get_position(self) -> tuple:
        """
        获取当前鼠标在屏幕上的绝对坐标
        返回: (x, y)
        """
        point = POINT()
        user32.GetCursorPos(ctypes.byref(point))
        return (point.x, point.y)
    
    # ==================== 2. 绝对定位移动 ====================
    def set_position(self, x: int, y: int):
        """
        将鼠标移动到屏幕上的绝对坐标 (x, y)
        等效于 pyautogui.moveTo()
        """
        # Windows API 的绝对坐标范围是 0~65535
        # 需要将屏幕坐标映射到此范围
        abs_x = int(x * 65535 / self.screen_width)
        abs_y = int(y * 65535 / self.screen_height)
        
        # 构造输入事件：移动 + 绝对坐标模式
        extra = ctypes.c_ulong(0)
        mi = MouseInput(
            abs_x, abs_y, 0,
            MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE,
            0, ctypes.pointer(extra)
        )
        ii = Input_I()
        ii.mi = mi
        cmd = Input(0, ii)  # 0 代表 INPUT_MOUSE
        
        user32.SendInput(1, ctypes.byref(cmd), ctypes.sizeof(cmd))
    
    # ==================== 3. 相对位移移动（3D游戏镜头） ====================
    def move_relative(self, dx: int, dy: int):
        """
        发送相对移动信号（不改变屏幕光标位置）
        适用于3D游戏视角控制
        """
        extra = ctypes.c_ulong(0)
        mi = MouseInput(
            dx, dy, 0,
            MOUSEEVENTF_MOVE,  # 不加 ABSOLUTE 标志，即为相对移动
            0, ctypes.pointer(extra)
        )
        ii = Input_I()
        ii.mi = mi
        cmd = Input(0, ii)
        
        user32.SendInput(1, ctypes.byref(cmd), ctypes.sizeof(cmd))
    
    # ==================== 4. 按下鼠标左键 ====================
    def left_down(self):
        """按下左键（不松开）"""
        extra = ctypes.c_ulong(0)
        mi = MouseInput(0, 0, 0, MOUSEEVENTF_LEFTDOWN, 0, ctypes.pointer(extra))
        ii = Input_I()
        ii.mi = mi
        cmd = Input(0, ii)
        user32.SendInput(1, ctypes.byref(cmd), ctypes.sizeof(cmd))
    
    # ==================== 5. 松开鼠标左键 ====================
    def left_up(self):
        """松开左键"""
        extra = ctypes.c_ulong(0)
        mi = MouseInput(0, 0, 0, MOUSEEVENTF_LEFTUP, 0, ctypes.pointer(extra))
        ii = Input_I()
        ii.mi = mi
        cmd = Input(0, ii)
        user32.SendInput(1, ctypes.byref(cmd), ctypes.sizeof(cmd))
    
    # ==================== 6. 右键支持 ====================
    def right_down(self):
        extra = ctypes.c_ulong(0)
        mi = MouseInput(0, 0, 0, MOUSEEVENTF_RIGHTDOWN, 0, ctypes.pointer(extra))
        ii = Input_I()
        ii.mi = mi
        cmd = Input(0, ii)
        user32.SendInput(1, ctypes.byref(cmd), ctypes.sizeof(cmd))
    
    def right_up(self):
        extra = ctypes.c_ulong(0)
        mi = MouseInput(0, 0, 0, MOUSEEVENTF_RIGHTUP, 0, ctypes.pointer(extra))
        ii = Input_I()
        ii.mi = mi
        cmd = Input(0, ii)
        user32.SendInput(1, ctypes.byref(cmd), ctypes.sizeof(cmd))

    # ==================== 7. 中键  ====================
    
    def middle_down(self):
        """按下鼠标中键"""
        extra = ctypes.c_ulong(0)
        mi = MouseInput(0, 0, 0, MOUSEEVENTF_MIDDLEDOWN, 0, ctypes.pointer(extra))
        ii = Input_I()
        ii.mi = mi
        cmd = Input(0, ii)
        user32.SendInput(1, ctypes.byref(cmd), ctypes.sizeof(cmd))
    
    def middle_up(self):
        """松开鼠标中键"""
        extra = ctypes.c_ulong(0)
        mi = MouseInput(0, 0, 0, MOUSEEVENTF_MIDDLEUP, 0, ctypes.pointer(extra))
        ii = Input_I()
        ii.mi = mi
        cmd = Input(0, ii)
        user32.SendInput(1, ctypes.byref(cmd), ctypes.sizeof(cmd))
    
    # ==================== 8. 滚轮  ====================
    def scroll_up(self, amount: int = 1):
        """
        向上滚动滚轮
        :param amount: 滚动刻度数，1 = 一个标准刻度
        """
        extra = ctypes.c_ulong(0)
        # mouseData 为正数表示向上滚动
        scroll_amount = amount * WHEEL_DELTA
        mi = MouseInput(0, 0, scroll_amount, MOUSEEVENTF_WHEEL, 0, ctypes.pointer(extra))
        ii = Input_I()
        ii.mi = mi
        cmd = Input(0, ii)
        user32.SendInput(1, ctypes.byref(cmd), ctypes.sizeof(cmd))
    
    def scroll_down(self, amount: int = 1):
        """
        向下滚动滚轮
        :param amount: 滚动刻度数，1 = 一个标准刻度
        """
        extra = ctypes.c_ulong(0)
        # mouseData 为负数表示向下滚动
        scroll_amount = -amount * WHEEL_DELTA
        mi = MouseInput(0, 0, scroll_amount, MOUSEEVENTF_WHEEL, 0, ctypes.pointer(extra))
        ii = Input_I()
        ii.mi = mi
        cmd = Input(0, ii)
        user32.SendInput(1, ctypes.byref(cmd), ctypes.sizeof(cmd))
    
    # ==================== 9.通用方法 ====================
    def scroll(self, amount: int):
        """
        更灵活的滚动接口
        :param amount: 正数向上，负数向下
        """
        if amount > 0:
            self.scroll_up(amount)
        elif amount < 0:
            self.scroll_down(-amount)
        # amount == 0 则什么都不做
    
    def press(self, button: str = "left"):
        """
        按下指定的鼠标键（不松开）
        :param button: "left" / "right" / "middle"
        """
        if button == "left":
            self.left_down()
        elif button == "right":
            self.right_down()
        elif button == "middle":
            self.middle_down()
        else:
            raise ValueError("button 必须是 'left', 'right' 或 'middle'")

    def release(self, button: str = "left"):
        """
        松开指定的鼠标键
        :param button: "left" / "right" / "middle"
        """
        if button == "left":
            self.left_up()
        elif button == "right":
            self.right_up()
        elif button == "middle":
            self.middle_up()
        else:
            raise ValueError("button 必须是 'left', 'right' 或 'middle'")

    def click(self, x: int = None, y: int = None, button: str = "left", delay: float = 0.05):
        """
        完整的点击
        :param button: "left" / "right" / "middle"
        """
        if x is not None and y is not None:
            self.set_position(x, y)
            time.sleep(0.02)
        
        if button == "left":
            self.left_down()
            time.sleep(delay)
            self.left_up()
        elif button == "right":
            self.right_down()
            time.sleep(delay)
            self.right_up()
        elif button == "middle":
            self.middle_down()
            time.sleep(delay)
            self.middle_up()
        else:
            raise ValueError("button 必须是 'left', 'right' 或 'middle'")

mouse_ctrl = MouseController()
