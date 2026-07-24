# -*- coding: utf-8 -*-
"""从 YOLO识别/yolov8检测模块.py 复制并适配的 best.onnx 检测器。"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable

import cv2
import numpy as np

import 截图模块
from YOLO物资动作 import letterbox_到模型输入, 物资检测区域客户区, 计算自适应检测参数


模型类别 = [
    "井盖", "野外物资箱", "医疗物资堆", "航空箱", "鸟窝", "医疗包", "垃圾箱",
    "小保险", "收纳袋", "工具盒", "弹药箱", "衣服1", "高级旅行箱", "主机",
]
游戏窗口类名 = "UnrealWindow"
游戏窗口标题 = "三角洲行动"


def 查找游戏窗口() -> int:
    import win32gui

    for title in ("三角洲行动  ", "三角洲行动 ", "三角洲行动"):
        hwnd = int(win32gui.FindWindow(游戏窗口类名, title) or 0)
        if hwnd:
            return hwnd
    found: list[int] = []

    def callback(hwnd: int, _extra: Any) -> None:
        if win32gui.GetClassName(hwnd) != 游戏窗口类名:
            return
        if win32gui.GetWindowText(hwnd).strip().startswith(游戏窗口标题):
            found.append(int(hwnd))

    win32gui.EnumWindows(callback, None)
    if not found:
        raise RuntimeError("未找到三角洲行动游戏窗口")
    return found[0]


def 获取物资检测区域屏幕坐标() -> tuple[int, int, int, int, float, float]:
    import win32gui

    origin_x, origin_y = win32gui.ClientToScreen(查找游戏窗口(), (0, 0))
    left, top, right, bottom = 物资检测区域客户区
    screen_left = int(origin_x + left)
    screen_top = int(origin_y + top)
    screen_right = int(origin_x + right)
    screen_bottom = int(origin_y + bottom)
    return (
        screen_left,
        screen_top,
        screen_right,
        screen_bottom,
        (screen_left + screen_right) / 2,
        (screen_top + screen_bottom) / 2,
    )


def 获取扩大物资检测区域屏幕坐标() -> tuple[int, int, int, int, float, float]:
    """返回游戏客户区中央 80% 的屏幕坐标。"""
    import win32gui

    hwnd = 查找游戏窗口()
    origin_x, origin_y = win32gui.ClientToScreen(hwnd, (0, 0))
    client_left, client_top, client_right, client_bottom = win32gui.GetClientRect(hwnd)
    client_width = int(client_right - client_left)
    client_height = int(client_bottom - client_top)
    if client_width <= 0 or client_height <= 0:
        raise RuntimeError("游戏窗口客户区尺寸无效")
    margin_x = int(round(client_width * 0.1))
    margin_y = int(round(client_height * 0.1))
    screen_left = int(origin_x + client_left + margin_x)
    screen_top = int(origin_y + client_top + margin_y)
    screen_right = int(origin_x + client_right - margin_x)
    screen_bottom = int(origin_y + client_bottom - margin_y)
    return (
        screen_left,
        screen_top,
        screen_right,
        screen_bottom,
        (screen_left + screen_right) / 2,
        (screen_top + screen_bottom) / 2,
    )


def 创建近距离缩放画面(
    frame_bgr: np.ndarray,
    缩放比例: float = 0.55,
) -> tuple[np.ndarray, tuple[float, float, int, int]]:
    """缩小当前画面并居中补灰边，让近距离大目标回到模型熟悉的尺度。"""
    if frame_bgr.ndim != 3 or frame_bgr.shape[2] != 3:
        raise ValueError("近距离检测画面必须是 HWC 三通道")
    ratio = float(缩放比例)
    if not 0 < ratio < 1:
        raise ValueError("近距离缩放比例必须在 0 到 1 之间")
    height, width = frame_bgr.shape[:2]
    scaled_width = max(1, int(round(width * ratio)))
    scaled_height = max(1, int(round(height * ratio)))
    resized = cv2.resize(frame_bgr, (scaled_width, scaled_height), interpolation=cv2.INTER_AREA)
    canvas = np.full_like(frame_bgr, 114)
    pad_x = (width - scaled_width) // 2
    pad_y = (height - scaled_height) // 2
    canvas[pad_y : pad_y + scaled_height, pad_x : pad_x + scaled_width] = resized
    return canvas, (scaled_width / width, scaled_height / height, pad_x, pad_y)


def 还原近距离检测结果(
    detections: list[dict[str, Any]],
    transform: tuple[float, float, int, int],
    offset_x: int,
    offset_y: int,
    原宽: int,
    原高: int,
) -> list[dict[str, Any]]:
    scale_x, scale_y, pad_x, pad_y = transform
    result: list[dict[str, Any]] = []
    for detection in detections:
        x1 = max(0, min(int(round((float(detection["x1"]) - pad_x) / scale_x)), 原宽 - 1))
        y1 = max(0, min(int(round((float(detection["y1"]) - pad_y) / scale_y)), 原高 - 1))
        x2 = max(0, min(int(round((float(detection["x2"]) - pad_x) / scale_x)), 原宽 - 1))
        y2 = max(0, min(int(round((float(detection["y2"]) - pad_y) / scale_y)), 原高 - 1))
        if x2 <= x1 or y2 <= y1:
            continue
        restored = dict(detection)
        restored.update(
            {
                "x1": x1 + int(offset_x),
                "y1": y1 + int(offset_y),
                "x2": x2 + int(offset_x),
                "y2": y2 + int(offset_y),
                "宽度": x2 - x1,
                "高度": y2 - y1,
                "中心X": (x1 + x2) / 2 + int(offset_x),
                "中心Y": (y1 + y2) / 2 + int(offset_y),
            }
        )
        result.append(restored)
    return result


class 物资检测器:
    def __init__(
        self,
        模型路径: str | Path = "best.onnx",
        *,
        设备ID: int = 0,
        日志函数: Callable[..., Any] | None = None,
        ort模块: Any = None,
        时钟: Callable[[], float] = time.monotonic,
        近距离检测间隔秒数: float = 0.2,
    ) -> None:
        self.模型路径 = str(Path(模型路径).resolve())
        self.设备ID = int(设备ID)
        self.日志函数 = 日志函数
        self._ort = ort模块
        self.时钟 = 时钟
        self.近距离检测间隔秒数 = max(0.0, float(近距离检测间隔秒数))
        self._上次近距离检测时间 = -float("inf")
        self._近距离模式锁定 = False
        self._近距离未命中开始时间: float | None = None
        self.session = None
        self.执行器 = "未初始化"
        self._已运行时回退 = False
        self.最近截图 = None
        self.最近检测结果: list[dict[str, Any]] = []
        self.最近检测模式 = "正常"
        self.最近耗时毫秒 = 0.0
        self.推荐检测间隔秒数 = 0.02
        self.推荐看门狗秒数 = 0.2
        self._加载模型()

    def _日志(self, 事件: str, **字段: Any) -> None:
        if self.日志函数 is None:
            return
        try:
            self.日志函数(事件, **字段)
        except TypeError:
            self.日志函数(f"{事件} | " + " | ".join(f"{k}={v}" for k, v in 字段.items()))

    def _session_options(self):
        ort = self._ort
        options = ort.SessionOptions()
        options.log_severity_level = 3
        options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        options.enable_mem_pattern = False
        return options

    def _创建会话(self, providers):
        return self._ort.InferenceSession(
            self.模型路径,
            sess_options=self._session_options(),
            providers=providers,
        )

    def _加载模型(self) -> None:
        if self._ort is None:
            try:
                import onnxruntime as ort
            except ImportError as exc:
                raise RuntimeError("未安装 onnxruntime-directml/onnxruntime") from exc
            self._ort = ort
        if not Path(self.模型路径).is_file():
            raise FileNotFoundError(f"YOLO 模型不存在: {self.模型路径}")
        available = list(self._ort.get_available_providers())
        if "DmlExecutionProvider" in available:
            try:
                self.session = self._创建会话(
                    [("DmlExecutionProvider", {"device_id": self.设备ID}), "CPUExecutionProvider"]
                )
                self.执行器 = "DirectML"
            except Exception as exc:
                self._日志("yolo_provider_fallback", 原执行器="DirectML", 错误=str(exc))
                self.session = self._创建会话(["CPUExecutionProvider"])
                self.执行器 = "CPU"
        else:
            self.session = self._创建会话(["CPUExecutionProvider"])
            self.执行器 = "CPU"
        input_meta = self.session.get_inputs()[0]
        self.输入名称 = input_meta.name
        self.输入高度 = int(input_meta.shape[2])
        self.输入宽度 = int(input_meta.shape[3])
        self._日志("yolo_loaded", 执行器=self.执行器, 输入=f"{self.输入宽度}x{self.输入高度}")

    def _切换CPU(self, reason: Exception) -> None:
        if self.执行器 == "CPU" or self._已运行时回退:
            raise reason
        self._已运行时回退 = True
        self._日志("yolo_runtime_fallback", 原执行器=self.执行器, 错误=str(reason))
        self.session = self._创建会话(["CPUExecutionProvider"])
        self.执行器 = "CPU"

    def _推理(self, tensor: np.ndarray):
        try:
            return self.session.run(None, {self.输入名称: tensor})[0]
        except Exception as exc:
            self._切换CPU(exc)
            return self.session.run(None, {self.输入名称: tensor})[0]

    def _后处理(
        self,
        output: np.ndarray,
        meta,
        *,
        offset_x: int,
        offset_y: int,
        confidence_threshold: float,
        iou_threshold: float,
    ) -> list[dict[str, Any]]:
        rows = output[0].astype(np.float32).T
        boxes_xywh: list[list[int]] = []
        boxes_xyxy: list[tuple[int, int, int, int]] = []
        scores: list[float] = []
        class_ids: list[int] = []
        for row in rows:
            class_scores = row[4:]
            if class_scores.size == 0:
                continue
            class_id = int(np.argmax(class_scores))
            score = float(class_scores[class_id])
            if score < confidence_threshold:
                continue
            cx, cy, width, height = [float(value) for value in row[:4]]
            x1, y1, x2, y2 = meta.还原框(
                (cx - width / 2, cy - height / 2, cx + width / 2, cy + height / 2)
            )
            x1 = max(0, min(int(round(x1)), meta.原宽 - 1))
            y1 = max(0, min(int(round(y1)), meta.原高 - 1))
            x2 = max(0, min(int(round(x2)), meta.原宽 - 1))
            y2 = max(0, min(int(round(y2)), meta.原高 - 1))
            if x2 <= x1 or y2 <= y1:
                continue
            boxes_xyxy.append((x1, y1, x2, y2))
            boxes_xywh.append([x1, y1, x2 - x1, y2 - y1])
            scores.append(score)
            class_ids.append(class_id)
        indices = cv2.dnn.NMSBoxes(boxes_xywh, scores, confidence_threshold, iou_threshold)
        if len(indices) == 0:
            return []
        flat = np.asarray(indices).reshape(-1)
        result: list[dict[str, Any]] = []
        for raw_index in flat:
            index = int(raw_index)
            x1, y1, x2, y2 = boxes_xyxy[index]
            class_id = class_ids[index]
            result.append(
                {
                    "类别ID": class_id,
                    "类别名称": 模型类别[class_id] if class_id < len(模型类别) else str(class_id),
                    "x1": x1 + offset_x,
                    "y1": y1 + offset_y,
                    "x2": x2 + offset_x,
                    "y2": y2 + offset_y,
                    "宽度": x2 - x1,
                    "高度": y2 - y1,
                    "中心X": (x1 + x2) / 2 + offset_x,
                    "中心Y": (y1 + y2) / 2 + offset_y,
                    "置信度": scores[index],
                }
            )
        return result

    def _检测画面(
        self,
        frame_bgr: np.ndarray,
        *,
        offset_x: int,
        offset_y: int,
        confidence_threshold: float,
        iou_threshold: float,
    ) -> list[dict[str, Any]]:
        frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        tensor, meta = letterbox_到模型输入(frame_rgb, (self.输入高度, self.输入宽度))
        output = self._推理(tensor)
        return self._后处理(
            output,
            meta,
            offset_x=offset_x,
            offset_y=offset_y,
            confidence_threshold=confidence_threshold,
            iou_threshold=iou_threshold,
        )

    def 检测一次(
        self,
        left: int,
        top: int,
        right: int,
        bottom: int,
        *,
        置信度阈值: float = 0.5,
        IOU阈值: float = 0.5,
    ) -> list[dict[str, Any]]:
        started = time.perf_counter()
        frame_bgr, backend = 截图模块.grab_bbox_bgr((left, top, right, bottom))
        self.最近截图 = frame_bgr.copy()
        当前时间 = self.时钟()

        def 近距离检测() -> list[dict[str, Any]]:
            close_frame, transform = 创建近距离缩放画面(frame_bgr)
            close_detections = self._检测画面(
                close_frame,
                offset_x=0,
                offset_y=0,
                confidence_threshold=float(置信度阈值),
                iou_threshold=float(IOU阈值),
            )
            return 还原近距离检测结果(
                close_detections,
                transform,
                int(left),
                int(top),
                frame_bgr.shape[1],
                frame_bgr.shape[0],
            )

        if getattr(self, "_近距离模式锁定", False):
            self.最近检测模式 = "近距离"
            result = 近距离检测()
            if result:
                self._近距离未命中开始时间 = None
            elif getattr(self, "_近距离未命中开始时间", None) is None:
                self._近距离未命中开始时间 = 当前时间
            elif 当前时间 - self._近距离未命中开始时间 >= 1.0:
                self._近距离模式锁定 = False
                self._近距离未命中开始时间 = None
                self._上次近距离检测时间 = 当前时间
        else:
            self.最近检测模式 = "正常"
            result = self._检测画面(
                frame_bgr,
                offset_x=int(left),
                offset_y=int(top),
                confidence_threshold=float(置信度阈值),
                iou_threshold=float(IOU阈值),
            )
            if (
                not result
                and 当前时间 - self._上次近距离检测时间 >= self.近距离检测间隔秒数
            ):
                self._上次近距离检测时间 = 当前时间
                result = 近距离检测()
                self.最近检测模式 = "近距离"
                if result:
                    self._近距离模式锁定 = True
                    self._近距离未命中开始时间 = None
        self.最近检测结果 = result
        self.最近耗时毫秒 = (time.perf_counter() - started) * 1000
        self.推荐检测间隔秒数, self.推荐看门狗秒数 = 计算自适应检测参数(
            self.最近耗时毫秒 / 1000
        )
        self._日志(
            "yolo_inference",
            执行器=self.执行器,
            截图后端=backend,
            检测模式=self.最近检测模式,
            耗时毫秒=round(self.最近耗时毫秒, 2),
            目标数=len(result),
        )
        return result

    def 释放资源(self) -> None:
        self.session = None
