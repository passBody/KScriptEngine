from .按键 import KeyClick
from .鼠标点击 import MouseClick
from .鼠标移动 import MouseMove
from .鼠标滚轮 import MouseScroll
from .鼠标拖动 import MouseDrag
from .多次点击 import MultiClick

from .鼠标.基础操作.相对偏移 import MouseOffset
from .鼠标.基础操作.设置位置 import SetMousePosition
from .鼠标.基础操作.按下 import MousePress
from .鼠标.基础操作.松开 import MouseRelease
from .鼠标.基础操作.获取位置 import GetMousePosition

__all__ = ["KeyClick", "MouseClick", "MouseMove", "MouseScroll",
           "MouseDrag", "MultiClick", "MouseOffset", "SetMousePosition",
           "MousePress", "MouseRelease", "GetMousePosition"]
