# -*- coding: utf-8 -*-
"""005 路线动作执行器。

所有输入都通过注入的输入模块发送，测试可以使用假输入；真实执行时由
Win32键鼠模块提供实现。每个动作都有停止检查，且按键在 finally 中释放。
"""
from __future__ import annotations

import math
import random
import time
from typing import Any, Callable, Iterable

from 路线动作 import 路线动作
from YOLO物资动作 import 选择综合目标


class 路线动作执行器:
    def __init__(
        self,
        输入模块: Any,
        *,
        定位器: Any = None,
        yolo检测器: Any = None,
        获取检测区域: Callable[[], tuple[int, int, int, int, float, float]] | None = None,
        每度像素: float = 100 / 3,
        停止事件: Any = None,
        日志函数: Callable[..., Any] | None = None,
        睡眠函数: Callable[[float], None] = time.sleep,
        时钟: Callable[[], float] = time.monotonic,
        随机数: random.Random | None = None,
        对准增益: float = 0.65,
        最大对准步长: int = 80,
    ) -> None:
        self.输入模块 = 输入模块
        self.定位器 = 定位器
        self.yolo检测器 = yolo检测器
        self.获取检测区域 = 获取检测区域
        self.每度像素 = float(每度像素)
        self.停止事件 = 停止事件
        self.日志函数 = 日志函数
        self.睡眠函数 = 睡眠函数
        self.时钟 = 时钟
        self.随机数 = 随机数 or random.Random()
        self.对准增益 = float(对准增益)
        self.最大对准步长 = int(最大对准步长)

    def _日志(self, 事件: str, **字段: Any) -> None:
        if self.日志函数 is None:
            return
        try:
            self.日志函数(事件, **字段)
        except TypeError:
            self.日志函数(f"{事件} | " + " | ".join(f"{k}={v}" for k, v in 字段.items()))

    def _停止_requested(self) -> bool:
        return bool(self.停止事件 is not None and self.停止事件.is_set())

    def _检查停止(self) -> None:
        if self._停止_requested():
            raise InterruptedError("路线动作已停止")

    def _等待(self, 秒数: float) -> None:
        if 秒数 <= 0:
            self._检查停止()
            return
        结束 = self.时钟() + 秒数
        while True:
            self._检查停止()
            剩余 = 结束 - self.时钟()
            if 剩余 <= 0:
                return
            self.睡眠函数(min(0.05, 剩余))

    def _按键动作(self, action: 路线动作) -> bool:
        p = action.参数
        keys = p.get("keys", [])
        if isinstance(keys, str):
            keys = [item.strip() for item in keys.split("+") if item.strip()]
        mode = p.get("mode", "click")
        duration = int(p.get("duration_ms", 50)) / 1000
        pressed: list[str] = []
        try:
            for key in keys:
                self._检查停止()
                self.输入模块.键盘按下(key)
                pressed.append(str(key))
            self._等待(duration)
            return True
        finally:
            for key in reversed(pressed):
                try:
                    self.输入模块.键盘弹起(key)
                except Exception:
                    pass

    def _鼠标平滑移动(self, dx: int, dy: int, 间隔: float = 0.0) -> None:
        if not dx and not dy:
            return
        smooth = getattr(self.输入模块, "丝滑相对移动", None)
        if callable(smooth):
            smooth(dx, dy, 步间隔=间隔)
        else:
            self.输入模块.鼠标相对移动(dx, dy)

    def _读取角度(self) -> float:
        state = self.定位器.读取状态()
        if hasattr(state, "angle"):
            return float(state.angle)
        return float(state[2])

    @staticmethod
    def _角度差(current: float, target: float) -> float:
        return (target - current + 540) % 360 - 180

    def 恢复视角(self, target_angle: float, tolerance: float = 3.0, max_attempts: int = 5) -> bool:
        if self.定位器 is None:
            return False
        target_angle = float(target_angle) % 360
        for _ in range(max_attempts):
            self._检查停止()
            current = self._读取角度()
            delta = self._角度差(current, target_angle)
            if abs(delta) <= tolerance:
                return True
            pixels = int(round(delta * self.每度像素))
            pixels = max(-self.最大对准步长, min(self.最大对准步长, pixels))
            self._鼠标平滑移动(pixels, 0)
            self._等待(0.05)
        return False

    def _低头抬头(self, action: 路线动作) -> bool:
        p = action.参数
        total_y = int(p["y_delta"])
        duration_ms = int(p.get("duration_ms", 100))
        x_random = int(p.get("x_random", 0))
        steps = max(1, int(math.ceil(duration_ms / 8)))
        moved_x = 0
        moved_y = 0
        for index in range(1, steps + 1):
            self._检查停止()
            target_y = round(total_y * index / steps)
            step_y = target_y - moved_y
            step_x = self.随机数.randint(-x_random, x_random) if x_random else 0
            self._鼠标平滑移动(step_x, step_y, 间隔=0.0)
            moved_x += step_x
            moved_y += step_y
            self._等待(duration_ms / 1000 / steps)
        if moved_x:
            self._鼠标平滑移动(-moved_x, 0, 间隔=0.0)
            moved_x = 0
        return moved_y == total_y and moved_x == 0

    def _执行首次按键和循环(self, p: dict[str, Any]) -> bool:
        f_key = str(p.get("interaction_key", "f"))
        w_key = str(p.get("forward_key", "w"))
        pressed_w = False
        try:
            self._检查停止()
            self.输入模块.键盘按下(f_key)
            try:
                self._等待(int(p.get("initial_f_ms", 500)) / 1000)
            finally:
                self.输入模块.键盘弹起(f_key)
            self._等待(int(p.get("initial_wait_ms", 300)) / 1000)

            self.输入模块.键盘按下(w_key)
            pressed_w = True
            w_start = self.时钟()
            repeat_ms = int(p.get("repeat_f_ms", 50))
            interval_ms = int(p["f_interval_ms"])
            for index in range(int(p["f_count"])):
                self._检查停止()
                cycle_start = self.时钟()
                self.输入模块.键盘按下(f_key)
                try:
                    self._等待(repeat_ms / 1000)
                finally:
                    self.输入模块.键盘弹起(f_key)
                if index + 1 < int(p["f_count"]):
                    self._等待(max(0, interval_ms / 1000 - (self.时钟() - cycle_start)))
            self._等待(max(0, int(p["w_duration_ms"]) / 1000 - (self.时钟() - w_start)))
            return True
        finally:
            if pressed_w:
                try:
                    self.输入模块.键盘弹起(w_key)
                except Exception:
                    pass

    def _YOLO交互(self, action: 路线动作) -> bool:
        p = action.参数
        if "angle" in p and self.定位器 is not None:
            if not self.恢复视角(float(p["angle"])):
                self._日志("yolo_view_failed", 目标角度=p["angle"])
                return False
        if self.yolo检测器 is None or self.获取检测区域 is None:
            self._日志("yolo_unavailable")
            return False
        left, top, right, bottom, center_x, center_y = self.获取检测区域()
        deadline = self.时钟() + int(p.get("timeout_ms", 5000)) / 1000
        tolerance = int(p.get("tolerance_px", 12))
        confidence = float(p.get("confidence", 0.5))
        while self.时钟() < deadline:
            self._检查停止()
            detections = self.yolo检测器.检测一次(left, top, right, bottom)
            target = 选择综合目标(detections, (center_x, center_y), confidence)
            if target is None:
                self._等待(0.05)
                continue
            dx = float(target["中心X"]) - center_x
            dy = float(target["中心Y"]) - center_y
            if abs(dx) <= tolerance and abs(dy) <= tolerance:
                self._日志("yolo_aligned", 误差X=round(dx, 2), 误差Y=round(dy, 2))
                return self._执行首次按键和循环(p)
            move_x = int(round(max(-self.最大对准步长, min(self.最大对准步长, dx * self.对准增益))))
            move_y = int(round(max(-self.最大对准步长, min(self.最大对准步长, dy * self.对准增益))))
            self.输入模块.鼠标相对移动(move_x, move_y)
            self._等待(0.02)
        self._日志("yolo_timeout", 超时毫秒=p.get("timeout_ms", 5000))
        return False

    def 执行动作(self, action: 路线动作) -> bool:
        action.校验()
        self._检查停止()
        if action.类型 == "key":
            return self._按键动作(action)
        if action.类型 == "wait":
            self._等待(int(action.参数.get("milliseconds", 0)) / 1000)
            return True
        if action.类型 == "comment":
            self._日志("comment", 内容=action.参数["text"])
            return True
        if action.类型 == "view":
            return self.恢复视角(float(action.参数["angle"]))
        if action.类型 == "look":
            return self._低头抬头(action)
        if action.类型 == "yolo_interact":
            return self._YOLO交互(action)
        raise ValueError(f"不支持的路线动作: {action.类型}")

    def 执行动作列表(self, actions: Iterable[路线动作]) -> list[bool]:
        results: list[bool] = []
        for action in actions:
            try:
                results.append(self.执行动作(action))
            except InterruptedError:
                raise
            except Exception as exc:
                self._日志("action_failed", 类型=action.类型, 错误=str(exc))
                results.append(False)
        return results
