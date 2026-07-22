# -*- coding: utf-8 -*-
"""稳定桌面截图（仅 004 使用，不改旧项目）。

控制环默认 **gdi → mss → pil**：
- 几乎不返回空帧
- 不 sleep 重试（避免控制周期抖动）
- 支持并集一次截图再裁多区域

环境变量 DELTA_CAPTURE_BACKEND=gdi|mss|pil 可覆盖。
"""
from __future__ import annotations

import os
import threading
from typing import Dict, Optional, Sequence, Tuple

import numpy as np

BBox = Tuple[int, int, int, int]

_lock = threading.Lock()
_backend = (os.environ.get("DELTA_CAPTURE_BACKEND") or "gdi").strip().lower()
_last = "none"
_mss = None


def set_backend(name: str) -> str:
    global _backend
    name = (name or "gdi").strip().lower()
    if name not in {"gdi", "mss", "pil", "auto"}:
        raise ValueError(name)
    _backend = name
    return _backend


def get_backend() -> str:
    return _backend


def get_last_backend() -> str:
    return _last


def grab_region(left: int, top: int, right: int, bottom: int) -> Optional[np.ndarray]:
    global _last
    left, top, right, bottom = int(left), int(top), int(right), int(bottom)
    if right <= left or bottom <= top:
        return None
    bbox = (left, top, right, bottom)
    for name in _order(_backend):
        frame = _by(name, bbox)
        if frame is not None and getattr(frame, "size", 0):
            _last = name
            return frame
    _last = "fail"
    return None


def grab_bbox_bgr(bbox: BBox) -> Tuple[np.ndarray, str]:
    x1, y1, x2, y2 = [int(v) for v in bbox]
    if x2 <= x1 or y2 <= y1:
        raise ValueError(f"bbox 无效: {bbox}")
    frame = grab_region(x1, y1, x2, y2)
    if frame is None:
        raise RuntimeError(f"截图失败: {bbox}")
    return frame, _last


def grab_union_crop(regions: Sequence[BBox]) -> Dict[BBox, np.ndarray]:
    cleaned: list[BBox] = []
    for r in regions:
        x1, y1, x2, y2 = [int(v) for v in r]
        if x2 > x1 and y2 > y1:
            cleaned.append((x1, y1, x2, y2))
    if not cleaned:
        return {}
    if len(cleaned) == 1:
        img = grab_region(*cleaned[0])
        return {cleaned[0]: img} if img is not None else {}

    ul = min(r[0] for r in cleaned)
    ut = min(r[1] for r in cleaned)
    ur = max(r[2] for r in cleaned)
    ub = max(r[3] for r in cleaned)
    full = grab_region(ul, ut, ur, ub)
    if full is None:
        out: Dict[BBox, np.ndarray] = {}
        for r in cleaned:
            img = grab_region(*r)
            if img is not None:
                out[r] = img
        return out

    result: Dict[BBox, np.ndarray] = {}
    for x1, y1, x2, y2 in cleaned:
        crop = full[y1 - ut : y2 - ut, x1 - ul : x2 - ul]
        if crop.size:
            result[(x1, y1, x2, y2)] = crop.copy()
    return result


def grab_fullscreen() -> Optional[np.ndarray]:
    try:
        import win32api

        w = int(win32api.GetSystemMetrics(0))
        h = int(win32api.GetSystemMetrics(1))
        if w > 0 and h > 0:
            return grab_region(0, 0, w, h)
    except Exception:
        pass
    try:
        from PIL import ImageGrab
        import cv2

        rgb = ImageGrab.grab().convert("RGB")
        return cv2.cvtColor(np.array(rgb), cv2.COLOR_RGB2BGR)
    except Exception:
        return None


def release() -> None:
    global _mss
    with _lock:
        _mss = None


def _order(pref: str) -> list[str]:
    pref = (pref or "gdi").lower()
    if pref == "mss":
        return ["mss", "gdi", "pil"]
    if pref == "pil":
        return ["pil", "gdi"]
    if pref == "auto":
        return ["gdi", "mss", "pil"]
    return ["gdi", "mss", "pil"]


def _by(name: str, bbox: BBox) -> Optional[np.ndarray]:
    if name == "gdi":
        return _gdi(bbox)
    if name == "mss":
        return _mss_grab(bbox)
    if name == "pil":
        return _pil(bbox)
    return None


def _gdi(bbox: BBox) -> Optional[np.ndarray]:
    x1, y1, x2, y2 = bbox
    w, h = x2 - x1, y2 - y1
    try:
        import cv2
        import win32con
        import win32gui
        import win32ui

        hwnd = win32gui.GetDesktopWindow()
        hdc = win32gui.GetWindowDC(hwnd)
        mfc = win32ui.CreateDCFromHandle(hdc)
        save = mfc.CreateCompatibleDC()
        bmp = win32ui.CreateBitmap()
        bmp.CreateCompatibleBitmap(mfc, w, h)
        save.SelectObject(bmp)
        save.BitBlt((0, 0), (w, h), mfc, (x1, y1), win32con.SRCCOPY)
        bits = bmp.GetBitmapBits(True)
        img = np.frombuffer(bits, dtype=np.uint8).reshape(h, w, 4)
        win32gui.DeleteObject(bmp.GetHandle())
        save.DeleteDC()
        mfc.DeleteDC()
        win32gui.ReleaseDC(hwnd, hdc)
        return cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
    except Exception:
        return None


def _mss_grab(bbox: BBox) -> Optional[np.ndarray]:
    global _mss
    x1, y1, x2, y2 = bbox
    w, h = x2 - x1, y2 - y1
    try:
        import mss

        with _lock:
            if _mss is None:
                _mss = mss.mss()
            shot = _mss.grab({"left": x1, "top": y1, "width": w, "height": h})
        raw = np.frombuffer(shot.raw, dtype=np.uint8).reshape(shot.height, shot.width, 4)
        return raw[:, :, :3].copy()
    except Exception:
        return None


def _pil(bbox: BBox) -> Optional[np.ndarray]:
    x1, y1, x2, y2 = bbox
    try:
        from PIL import ImageGrab
        import cv2

        rgb = ImageGrab.grab(bbox=(x1, y1, x2, y2)).convert("RGB")
        return cv2.cvtColor(np.array(rgb), cv2.COLOR_RGB2BGR)
    except Exception:
        return None
