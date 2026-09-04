from .鼠标.基础操作.相对偏移 import MouseOffset
from .鼠标.基础操作.设置位置 import SetMousePosition
from .鼠标.基础操作.按下 import MousePress
from .鼠标.基础操作.松开 import MouseRelease
from .鼠标.基础操作.获取位置 import GetMousePosition
from .鼠标.进阶操作.鼠标点击 import MouseClick
from .鼠标.进阶操作.多坐标点击 import MultiPosClick
from .键盘.基础操作.按下 import KeyPress
from .键盘.基础操作.松开 import KeyRelease
from .键盘.进阶操作.点击 import KeyClick
from .键盘.进阶操作.粘贴 import KeyPaste


__all__ = [
    "MouseOffset", "SetMousePosition", "MousePress", 
    "MouseRelease", "GetMousePosition", "MouseClick", "MultiPosClick", 
    "KeyPress", "KeyRelease", "KeyClick","KeyPaste"
]
