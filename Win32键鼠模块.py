import math
import random
import time

import win32api
import win32con


鼠标按键映射 = {
    "left": (win32con.MOUSEEVENTF_LEFTDOWN, win32con.MOUSEEVENTF_LEFTUP),
    "左键": (win32con.MOUSEEVENTF_LEFTDOWN, win32con.MOUSEEVENTF_LEFTUP),
    "right": (win32con.MOUSEEVENTF_RIGHTDOWN, win32con.MOUSEEVENTF_RIGHTUP),
    "右键": (win32con.MOUSEEVENTF_RIGHTDOWN, win32con.MOUSEEVENTF_RIGHTUP),
    "middle": (win32con.MOUSEEVENTF_MIDDLEDOWN, win32con.MOUSEEVENTF_MIDDLEUP),
    "中键": (win32con.MOUSEEVENTF_MIDDLEDOWN, win32con.MOUSEEVENTF_MIDDLEUP),
}


按键映射 = {
    "backspace": win32con.VK_BACK,
    "tab": win32con.VK_TAB,
    "enter": win32con.VK_RETURN,
    "return": win32con.VK_RETURN,
    "shift": win32con.VK_SHIFT,
    "ctrl": win32con.VK_CONTROL,
    "control": win32con.VK_CONTROL,
    "alt": win32con.VK_MENU,
    "esc": win32con.VK_ESCAPE,
    "escape": win32con.VK_ESCAPE,
    "space": win32con.VK_SPACE,
    "空格": win32con.VK_SPACE,
    "left": win32con.VK_LEFT,
    "right": win32con.VK_RIGHT,
    "up": win32con.VK_UP,
    "down": win32con.VK_DOWN,
    "delete": win32con.VK_DELETE,
    "del": win32con.VK_DELETE,
    "home": win32con.VK_HOME,
    "end": win32con.VK_END,
    "pageup": win32con.VK_PRIOR,
    "pagedown": win32con.VK_NEXT,
    "insert": win32con.VK_INSERT,
    "capslock": win32con.VK_CAPITAL,
}

for i in range(1, 13):
    按键映射[f"f{i}"] = getattr(win32con, f"VK_F{i}")


def _解析鼠标按键(按键):
    if isinstance(按键, str):
        key = 按键.lower()
    else:
        key = 按键
    if key not in 鼠标按键映射:
        raise ValueError(f"不支持的鼠标按键: {按键}")
    return 鼠标按键映射[key]


def _解析按键(按键):
    if isinstance(按键, int):
        return 按键

    key = str(按键)
    lower_key = key.lower()
    if lower_key in 按键映射:
        return 按键映射[lower_key]

    if len(key) == 1:
        vk = win32api.VkKeyScan(key)
        if vk == -1:
            raise ValueError(f"无法解析按键: {按键}")
        return vk & 0xFF

    if lower_key.startswith("0x"):
        return int(lower_key, 16)

    raise ValueError(f"不支持的键盘按键: {按键}")


def 鼠标绝对移动(x, y):
    """移动鼠标到屏幕绝对坐标。"""
    win32api.SetCursorPos((int(round(x)), int(round(y))))


def 鼠标相对移动(dx, dy):
    """按相对偏移移动鼠标。"""
    win32api.mouse_event(win32con.MOUSEEVENTF_MOVE, int(round(dx)), int(round(dy)), 0, 0)


def 生成丝滑相对移动(dx, dy, 随机种子=None):
    """生成前快后慢的相对移动序列，所有分段相加严格等于目标偏移。"""
    dx = int(round(dx))
    dy = int(round(dy))
    if dx == 0 and dy == 0:
        return []

    距离 = math.hypot(dx, dy)
    if 距离 < 4:
        return [(dx, dy)]

    if 距离 < 20:
        分段数 = 3
    elif 距离 < 80:
        分段数 = 5
    else:
        分段数 = min(12, max(6, int(距离 / 22)))

    rng = random.Random(随机种子) if 随机种子 is not None else random
    控制1 = (dx * rng.uniform(0.45, 0.65), dy * rng.uniform(0.45, 0.65))
    控制2 = (dx * rng.uniform(0.82, 0.95), dy * rng.uniform(0.82, 0.95))
    累计x = 0
    累计y = 0
    上个x = 0.0
    上个y = 0.0
    结果 = []

    for i in range(1, 分段数 + 1):
        t = i / 分段数
        缓动t = 1 - (1 - t) ** 2
        inv = 1 - 缓动t
        x = 3 * inv * inv * 缓动t * 控制1[0] + 3 * inv * 缓动t * 缓动t * 控制2[0] + 缓动t ** 3 * dx
        y = 3 * inv * inv * 缓动t * 控制1[1] + 3 * inv * 缓动t * 缓动t * 控制2[1] + 缓动t ** 3 * dy
        if i == 分段数:
            step_x = dx - 累计x
            step_y = dy - 累计y
        else:
            step_x = int(round(x - 上个x))
            step_y = int(round(y - 上个y))
        if step_x or step_y:
            结果.append((step_x, step_y))
            累计x += step_x
            累计y += step_y
        上个x = x
        上个y = y

    return 结果


def 丝滑相对移动(dx, dy, 步间隔=0.006):
    """按贝塞尔缓动分段移动鼠标，速度前快后慢。"""
    for step_x, step_y in 生成丝滑相对移动(dx, dy):
        鼠标相对移动(step_x, step_y)
        if 步间隔 > 0:
            time.sleep(步间隔)


def 鼠标点击(x=None, y=None, 按键="左键", 间隔=0.02):
    """鼠标点击；传入 x/y 时会先移动到指定位置。"""
    if x is not None and y is not None:
        鼠标绝对移动(x, y)

    down_flag, up_flag = _解析鼠标按键(按键)
    win32api.mouse_event(down_flag, 0, 0, 0, 0)
    time.sleep(间隔)
    win32api.mouse_event(up_flag, 0, 0, 0, 0)


def 键盘按下(按键):
    """按下键盘按键。按键可以是 VK 数字、单字符或常见名字。"""
    vk = _解析按键(按键)
    scan = win32api.MapVirtualKey(vk, 0)
    win32api.keybd_event(vk, scan, 0, 0)


def 键盘弹起(按键):
    """弹起键盘按键。"""
    vk = _解析按键(按键)
    scan = win32api.MapVirtualKey(vk, 0)
    win32api.keybd_event(vk, scan, win32con.KEYEVENTF_KEYUP, 0)


def 键盘单击(按键, 间隔=0.02):
    """键盘单击。"""
    键盘按下(按键)
    time.sleep(间隔)
    键盘弹起(按键)


def 释放按键列表(*按键):
    for 按键 in 按键:
        try:
            键盘弹起(按键)
        except Exception:
            pass


def 释放移动键():
    释放按键列表("w", "a", "s", "d", "shift")


def 点按shift(间隔=0.02):
    键盘单击("shift", 间隔=间隔)


def 按键是否按下(按键):
    vk = _解析按键(按键)
    return bool(win32api.GetAsyncKeyState(vk) & 0x8000)


def 获取鼠标位置():
    """返回当前鼠标位置: (x, y)。"""
    return win32api.GetCursorPos()


if __name__ == "__main__":
    print("Win32键鼠模块已加载")
    print("当前鼠标位置:", 获取鼠标位置())
