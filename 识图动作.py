# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path
from typing import Callable

import cv2
import numpy as np

import 截图模块


def 获取游戏客户区屏幕坐标() -> tuple[int, int, int, int]:
    import win32gui

    from YOLO物资检测 import 查找游戏窗口

    hwnd = 查找游戏窗口()
    left, top = win32gui.ClientToScreen(hwnd, (0, 0))
    _, _, right, bottom = win32gui.GetClientRect(hwnd)
    return int(left), int(top), int(left + right), int(top + bottom)


class 模板匹配器:
    def __init__(
        self,
        *,
        区域函数: Callable[[], tuple[int, int, int, int]] = 获取游戏客户区屏幕坐标,
        截图函数=截图模块.grab_bbox_bgr,
    ) -> None:
        self.区域函数 = 区域函数
        self.截图函数 = 截图函数
        self._模板缓存: dict[str, np.ndarray] = {}

    def _读取模板(self, template_path: str) -> np.ndarray:
        path = Path(template_path).expanduser()
        if not path.is_absolute():
            path = Path(__file__).resolve().parent / path
        key = str(path.resolve())
        if key not in self._模板缓存:
            if not path.is_file():
                raise FileNotFoundError(f"模板图片不存在: {path}")
            data = np.fromfile(path, dtype=np.uint8)
            template = cv2.imdecode(data, cv2.IMREAD_GRAYSCALE)
            if template is None or template.size == 0:
                raise ValueError(f"无法读取模板图片: {path}")
            self._模板缓存[key] = template
        return self._模板缓存[key]

    def 匹配一次(self, template_path: str, confidence: float = 0.85) -> dict | None:
        left, top, right, bottom = self.区域函数()
        frame, _backend = self.截图函数((left, top, right, bottom))
        template = self._读取模板(template_path)
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        template_height, template_width = template.shape[:2]
        if template_height > gray.shape[0] or template_width > gray.shape[1]:
            raise ValueError("模板图片尺寸不能大于游戏客户区")
        result = cv2.matchTemplate(gray, template, cv2.TM_CCOEFF_NORMED)
        _min_score, max_score, _min_location, max_location = cv2.minMaxLoc(result)
        if float(max_score) < float(confidence):
            return None
        x, y = max_location
        return {
            "x1": int(left + x),
            "y1": int(top + y),
            "x2": int(left + x + template_width),
            "y2": int(top + y + template_height),
            "中心X": int(left + x + template_width // 2),
            "中心Y": int(top + y + template_height // 2),
            "置信度": float(max_score),
        }
