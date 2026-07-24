# -*- coding: utf-8 -*-
"""best.onnx 的无设备依赖算法工具。"""
from __future__ import annotations

import math
import statistics
import time
from collections import deque
from dataclasses import dataclass
from typing import Callable, Iterable

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


def 计算自适应检测参数(
    推理耗时秒数: float,
    基础检测间隔秒数: float = 0.02,
) -> tuple[float, float]:
    """按推理耗时放宽检测间隔和看门狗，兼容较慢显卡与 CPU。"""
    inference = max(0.0, float(推理耗时秒数))
    interval = max(float(基础检测间隔秒数), min(0.12, inference * 0.25))
    watchdog = max(0.2, min(1.5, inference * 2.5 + interval))
    return interval, watchdog


def 生成扫描视角(记录视角: float, 步长度数: float, 尝试次数: int) -> list[float]:
    base = float(记录视角) % 360
    step = abs(float(步长度数))
    result: list[float] = []
    for index in range(max(0, int(尝试次数))):
        multiplier = index // 2 + 1
        direction = 1 if index % 2 == 0 else -1
        result.append((base + direction * multiplier * step) % 360)
    return result


class YOLO目标跟踪器:
    """锁定同一类别目标，并对最近几帧中心点做中位数滤波。"""

    def __init__(
        self,
        *,
        目标类别: str = "",
        滤波帧数: int = 3,
        锁定秒数: float = 0.5,
        时钟: Callable[[], float] = time.monotonic,
    ) -> None:
        self.目标类别 = str(目标类别).strip()
        self.滤波帧数 = max(1, int(滤波帧数))
        self.锁定秒数 = max(0.0, float(锁定秒数))
        self.时钟 = 时钟
        self._锁定类别: str | None = None
        self._最后中心: tuple[float, float] | None = None
        self._最后命中时间: float | None = None
        self._中心历史: deque[tuple[float, float]] = deque(maxlen=self.滤波帧数)

    def 重置(self) -> None:
        self._锁定类别 = None
        self._最后中心 = None
        self._最后命中时间 = None
        self._中心历史.clear()

    def _锁定仍有效(self, 当前时间: float) -> bool:
        return bool(
            self._锁定类别 is not None
            and self._最后命中时间 is not None
            and 当前时间 - self._最后命中时间 <= self.锁定秒数
        )

    def 选择(
        self,
        candidates: Iterable[dict],
        center: tuple[float, float],
        confidence_threshold: float = 0.5,
        *,
        当前时间: float | None = None,
    ) -> dict | None:
        now = float(self.时钟() if 当前时间 is None else 当前时间)
        available = [
            item
            for item in candidates
            if float(item.get("置信度", 0.0)) >= confidence_threshold
            and (not self.目标类别 or str(item.get("类别名称", "")) == self.目标类别)
        ]
        locked = self._锁定仍有效(now)
        if not locked and self._锁定类别 is not None:
            self.重置()

        target = None
        if locked:
            same_class = [
                item for item in available if str(item.get("类别名称", "")) == self._锁定类别
            ]
            if same_class:
                reference = self._最后中心 or center
                target = min(
                    same_class,
                    key=lambda item: math.hypot(
                        float(item["中心X"]) - reference[0],
                        float(item["中心Y"]) - reference[1],
                    ),
                )
        else:
            target = 选择综合目标(available, center, confidence_threshold)

        if target is None:
            return None

        target = dict(target)
        raw_center = (float(target["中心X"]), float(target["中心Y"]))
        target_class = str(target.get("类别名称", ""))
        if self._锁定类别 is not None and target_class != self._锁定类别:
            self._中心历史.clear()
        self._锁定类别 = target_class
        self._最后中心 = raw_center
        self._最后命中时间 = now
        self._中心历史.append(raw_center)
        target["原始中心X"] = raw_center[0]
        target["原始中心Y"] = raw_center[1]
        target["中心X"] = float(statistics.median(item[0] for item in self._中心历史))
        target["中心Y"] = float(statistics.median(item[1] for item in self._中心历史))
        return target
