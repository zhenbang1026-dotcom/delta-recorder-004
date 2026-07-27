# -*- coding: utf-8 -*-
from __future__ import annotations

import win32api
import win32con
import win32gui


最近显示器 = getattr(win32con, "MONITOR_DEFAULTTONEAREST", 2)
最外层窗口 = getattr(win32con, "GA_ROOT", 2)
默认边距 = 20


def 计算右下角位置(
    工作区域: tuple[int, int, int, int],
    窗口宽度: int,
    窗口高度: int,
    边距: int = 默认边距,
) -> tuple[int, int]:
    left, top, right, bottom = (int(value) for value in 工作区域)
    width = int(窗口宽度)
    height = int(窗口高度)
    margin = max(0, int(边距))
    if right <= left or bottom <= top or width <= 0 or height <= 0:
        raise ValueError("窗口或显示器工作区域尺寸无效")
    return max(left, right - width - margin), max(top, bottom - height - margin)


def 计算右上角位置(
    工作区域: tuple[int, int, int, int],
    窗口宽度: int,
    窗口高度: int,
    边距: int = 默认边距,
) -> tuple[int, int]:
    left, top, right, bottom = (int(value) for value in 工作区域)
    width = int(窗口宽度)
    height = int(窗口高度)
    margin = max(0, int(边距))
    if right <= left or bottom <= top or width <= 0 or height <= 0:
        raise ValueError("窗口或显示器工作区域尺寸无效")
    return max(left, right - width - margin), min(top + margin, max(top, bottom - height))


def 获取外层窗口句柄(window) -> int:
    hwnd = int(window.winfo_id())
    try:
        outer_hwnd = int(win32gui.GetAncestor(hwnd, 最外层窗口) or 0)
        if outer_hwnd:
            return outer_hwnd
    except Exception:
        pass
    return hwnd


def _获取工作区域(window, 参照窗口=None) -> tuple[int, int, int, int]:
    try:
        if 参照窗口 is None:
            monitor = win32api.MonitorFromPoint(win32api.GetCursorPos(), 最近显示器)
        else:
            参照窗口.update_idletasks()
            monitor = win32api.MonitorFromWindow(获取外层窗口句柄(参照窗口), 最近显示器)
        info = win32api.GetMonitorInfo(monitor)
        return tuple(int(value) for value in info["Work"])
    except Exception:
        return 0, 0, int(window.winfo_screenwidth()), int(window.winfo_screenheight())


def _定位窗口(
    window,
    宽度: int,
    高度: int,
    *,
    参照窗口=None,
    边距: int = 默认边距,
    位置计算函数=计算右下角位置,
) -> tuple[int, int]:
    width = int(宽度)
    height = int(高度)
    window.geometry(f"{width}x{height}")
    window.update_idletasks()
    hwnd = 获取外层窗口句柄(window)
    work_area = _获取工作区域(window, 参照窗口)
    try:
        left, top, right, bottom = win32gui.GetWindowRect(hwnd)
        outer_width = max(1, int(right) - int(left))
        outer_height = max(1, int(bottom) - int(top))
    except Exception:
        outer_width, outer_height = width, height
    x, y = 位置计算函数(work_area, outer_width, outer_height, 边距)
    flags = win32con.SWP_NOSIZE | win32con.SWP_NOZORDER | win32con.SWP_NOACTIVATE
    try:
        win32gui.SetWindowPos(hwnd, 0, x, y, 0, 0, flags)
    except Exception:
        window.geometry(f"{width}x{height}+{max(0, x)}+{max(0, y)}")
    return x, y


def 定位窗口到右下角(
    window,
    宽度: int,
    高度: int,
    *,
    参照窗口=None,
    边距: int = 默认边距,
) -> tuple[int, int]:
    return _定位窗口(window, 宽度, 高度, 参照窗口=参照窗口, 边距=边距)


def 定位窗口到右上角(
    window,
    宽度: int,
    高度: int,
    *,
    参照窗口=None,
    边距: int = 默认边距,
) -> tuple[int, int]:
    return _定位窗口(
        window,
        宽度,
        高度,
        参照窗口=参照窗口,
        边距=边距,
        位置计算函数=计算右上角位置,
    )
