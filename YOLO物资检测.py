# -*- coding: utf-8 -*-
"""从 YOLO识别/yolov8检测模块.py 复制并适配的 best.onnx 检测器。"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable

import cv2
import numpy as np

import 截图模块
from YOLO物资动作 import letterbox_到模型输入, 物资检测区域客户区


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


class 物资检测器:
    def __init__(
        self,
        模型路径: str | Path = "best.onnx",
        *,
        设备ID: int = 0,
        日志函数: Callable[..., Any] | None = None,
        ort模块: Any = None,
    ) -> None:
        self.模型路径 = str(Path(模型路径).resolve())
        self.设备ID = int(设备ID)
        self.日志函数 = 日志函数
        self._ort = ort模块
        self.session = None
        self.执行器 = "未初始化"
        self._已运行时回退 = False
        self.最近截图 = None
        self.最近检测结果: list[dict[str, Any]] = []
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
        frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        tensor, meta = letterbox_到模型输入(frame_rgb, (self.输入高度, self.输入宽度))
        output = self._推理(tensor)
        result = self._后处理(
            output,
            meta,
            offset_x=int(left),
            offset_y=int(top),
            confidence_threshold=float(置信度阈值),
            iou_threshold=float(IOU阈值),
        )
        self.最近检测结果 = result
        self._日志(
            "yolo_inference",
            执行器=self.执行器,
            截图后端=backend,
            耗时毫秒=round((time.perf_counter() - started) * 1000, 2),
            目标数=len(result),
        )
        return result

    def 释放资源(self) -> None:
        self.session = None
