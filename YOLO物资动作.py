# -*- coding: utf-8 -*-
"""best.onnx 的无设备依赖算法工具。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import cv2
import numpy as np


# 来自 YOLO 旧项目中已验证的 best.onnx 客户区范围（不是整屏坐标）。
物资检测区域客户区 = (504, 358, 952, 614)


@dataclass(frozen=True)
class Letterbox信息:
    原宽: int
    原高: int
    目标宽: int
    目标高: int
    缩放: float
    左边距: int
    上边距: int

    def 变换框(self, box: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
        x1, y1, x2, y2 = box
        return (
            x1 * self.缩放 + self.左边距,
            y1 * self.缩放 + self.上边距,
            x2 * self.缩放 + self.左边距,
            y2 * self.缩放 + self.上边距,
        )

    def 还原框(self, box: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
        x1, y1, x2, y2 = box
        return (
            (x1 - self.左边距) / self.缩放,
            (y1 - self.上边距) / self.缩放,
            (x2 - self.左边距) / self.缩放,
            (y2 - self.上边距) / self.缩放,
        )


def letterbox_到模型输入(
    image: np.ndarray,
    input_size: tuple[int, int] = (256, 448),
) -> tuple[np.ndarray, Letterbox信息]:
    """保持比例缩放到 (高,宽)，返回 NCHW float32 张量。"""
    if image.ndim != 3 or image.shape[2] != 3:
        raise ValueError("输入图片必须是 HWC 三通道")
    target_h, target_w = (int(input_size[0]), int(input_size[1]))
    if target_h <= 0 or target_w <= 0:
        raise ValueError("模型输入尺寸必须为正数")
    原高, 原宽 = image.shape[:2]
    缩放 = min(target_w / 原宽, target_h / 原高)
    new_w = max(1, int(round(原宽 * 缩放)))
    new_h = max(1, int(round(原高 * 缩放)))
    resized = cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
    canvas = np.full((target_h, target_w, 3), 114, dtype=np.uint8)
    left = (target_w - new_w) // 2
    top = (target_h - new_h) // 2
    canvas[top : top + new_h, left : left + new_w] = resized
    tensor = canvas.astype(np.float32) / 255.0
    tensor = np.transpose(tensor, (2, 0, 1))[None, ...]
    return tensor, Letterbox信息(原宽, 原高, target_w, target_h, new_w / 原宽, left, top)


def 还原检测框到原图(
    box: tuple[float, float, float, float],
    meta: Letterbox信息,
) -> tuple[float, float, float, float]:
    return meta.还原框(box)


def 选择综合目标(
    candidates: Iterable[dict],
    center: tuple[float, float],
    confidence_threshold: float = 0.5,
) -> dict | None:
    """置信度 60% + 接近检测区域中心 40%，结果可重复。"""
    cx, cy = center
    diagonal = max(1.0, float(np.hypot(cx, cy)))
    best = None
    best_score = -float("inf")
    for candidate in candidates:
        confidence = float(candidate.get("置信度", 0.0))
        if confidence < confidence_threshold:
            continue
        distance = float(np.hypot(float(candidate["中心X"]) - cx, float(candidate["中心Y"]) - cy))
        proximity = 1.0 - min(1.0, distance / diagonal)
        score = confidence * 0.6 + proximity * 0.4
        if score > best_score:
            best_score = score
            best = candidate
    return best
