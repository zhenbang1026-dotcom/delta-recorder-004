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
from YOLO连续对准 import YOLO连续对准控制器
from YOLO物资动作 import YOLO目标跟踪器, 生成扫描视角


class 路线动作执行器:
    def __init__(
        self,
        输入模块: Any,
        *,
        定位器: Any = None,
        yolo检测器: Any = None,
        获取检测区域: Callable[[], tuple[int, int, int, int, float, float]] | None = None,
        获取扩大检测区域: Callable[[], tuple[int, int, int, int, float, float]] | None = None,
        图像匹配器: Any = None,
        每度像素: float = 100 / 3,
        停止事件: Any = None,
        日志函数: Callable[..., Any] | None = None,
        状态函数: Callable[..., Any] | None = None,
        恢复焦点函数: Callable[[], None] | None = None,
        睡眠函数: Callable[[float], None] = time.sleep,
        时钟: Callable[[], float] = time.monotonic,
        随机数: random.Random | None = None,
        YOLO对准控制器工厂: Callable[..., Any] = YOLO连续对准控制器,
        持续YOLO服务: Any = None,
        最大视角恢复步长: int = 1200,
    ) -> None:
        self.输入模块 = 输入模块
        self.定位器 = 定位器
        self.yolo检测器 = yolo检测器
        self.获取检测区域 = 获取检测区域
        self.获取扩大检测区域 = 获取扩大检测区域
        self.图像匹配器 = 图像匹配器
        self.每度像素 = float(每度像素)
        self.停止事件 = 停止事件
        self.日志函数 = 日志函数
        self.状态函数 = 状态函数
        self.恢复焦点函数 = 恢复焦点函数
        self.睡眠函数 = 睡眠函数
        self.时钟 = 时钟
        self.随机数 = 随机数 or random.Random()
        self.YOLO对准控制器工厂 = YOLO对准控制器工厂
        self.持续YOLO服务 = 持续YOLO服务
        self.最大视角恢复步长 = int(最大视角恢复步长)

    def _YOLO检测间隔(self, 控制器: Any, 默认值: float = 0.02) -> float:
        更新看门狗 = getattr(控制器, "更新看门狗", None)
        推荐看门狗 = getattr(self.yolo检测器, "推荐看门狗秒数", None)
        if 推荐看门狗 is not None and callable(更新看门狗):
            更新看门狗(float(推荐看门狗))
        return max(
            float(默认值),
            float(getattr(self.yolo检测器, "推荐检测间隔秒数", 默认值)),
        )

    def _日志(self, 事件: str, **字段: Any) -> None:
        if self.日志函数 is None:
            return
        try:
            self.日志函数(事件, **字段)
        except TypeError:
            self.日志函数(f"{事件} | " + " | ".join(f"{k}={v}" for k, v in 字段.items()))

    def _状态(self, 事件: str, **字段: Any) -> None:
        if self.状态函数 is None:
            return
        try:
            self.状态函数(事件, **字段)
        except TypeError:
            try:
                self.状态函数({"event": 事件, **字段})
            except Exception:
                pass
        except Exception:
            pass

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
        duration_ms = int(p.get("duration_ms", 50))
        repeat_count = int(p.get("repeat_count", 1))
        interval = int(p.get("repeat_interval_ms", 100)) / 1000
        jitter_minus = int(p.get("duration_jitter_minus_ms", 0))
        jitter_plus = int(p.get("duration_jitter_plus_ms", 0))
        for index in range(repeat_count):
            jitter = (
                self.随机数.randint(-jitter_minus, jitter_plus)
                if jitter_minus or jitter_plus
                else 0
            )
            pressed: list[str] = []
            try:
                for key in keys:
                    self._检查停止()
                    self.输入模块.键盘按下(key)
                    pressed.append(str(key))
                self._等待((duration_ms + jitter) / 1000)
            finally:
                for key in reversed(pressed):
                    try:
                        self.输入模块.键盘弹起(key)
                    except Exception:
                        pass
            if index + 1 < repeat_count:
                self._等待(interval)
        return True

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
            pixels = max(-self.最大视角恢复步长, min(self.最大视角恢复步长, pixels))
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

    def _等待期间执行YOLO跟随(
        self,
        秒数: float,
        跟随回调: Callable[[], None] | None,
        *,
        检测间隔: float = 0.05,
    ) -> None:
        if 跟随回调 is None or 秒数 <= 0:
            self._等待(秒数)
            return
        结束时间 = self.时钟() + 秒数
        下次检测时间 = self.时钟()
        while True:
            self._检查停止()
            当前时间 = self.时钟()
            剩余时间 = 结束时间 - 当前时间
            if 剩余时间 <= 0:
                return
            if 当前时间 >= 下次检测时间:
                跟随回调()
                下次检测时间 = self.时钟() + 检测间隔
                continue
            self._等待(min(剩余时间, 下次检测时间 - 当前时间))

    def _YOLO持续跟随调整(
        self,
        p: dict[str, Any],
        roi: tuple[int, int, int, int],
        屏幕中心: tuple[float, float],
        控制器: Any,
        跟踪器: YOLO目标跟踪器,
    ) -> None:
        left, top, right, bottom = roi
        center_x, center_y = 屏幕中心
        tolerance = int(p.get("tolerance_px", 12))
        target_y_offset = int(p.get("target_y_offset_px", 0))
        confidence = float(p.get("confidence", 0.5))
        try:
            detections = self.yolo检测器.检测一次(left, top, right, bottom)
            target = 跟踪器.选择(
                detections,
                (center_x, center_y),
                confidence,
                当前时间=self.时钟(),
            )
            frame = getattr(self.yolo检测器, "最近截图", None)
            if frame is not None:
                try:
                    frame = frame.copy()
                except Exception:
                    frame = None
            self._状态(
                "inference",
                检测数=len(detections),
                检测结果=detections,
                目标=target,
                截图=frame,
                ROI=(left, top, right, bottom),
                中心=(center_x, center_y),
                剩余毫秒=0,
                执行器=getattr(self.yolo检测器, "执行器", "未知"),
                检测模式=getattr(self.yolo检测器, "最近检测模式", "正常"),
                持续跟随=True,
            )
            if target is None:
                控制器.更新误差(0.0, 0.0)
                return
            dx = float(target["中心X"]) - center_x
            dy = float(target["中心Y"]) + target_y_offset - center_y
            if abs(dx) <= tolerance and abs(dy) <= tolerance:
                目标速度X, 目标速度Y = 控制器.更新误差(0.0, 0.0)
            else:
                目标速度X, 目标速度Y = 控制器.更新误差(dx, dy)
            self._状态(
                "adjust",
                目标速度X=round(目标速度X, 2),
                目标速度Y=round(目标速度Y, 2),
                当前速度X=round(float(getattr(控制器, "当前速度X", 0.0)), 2),
                当前速度Y=round(float(getattr(控制器, "当前速度Y", 0.0)), 2),
                误差X=round(dx, 2),
                误差Y=round(dy, 2),
                持续跟随=True,
            )
            self._YOLO检测间隔(控制器)
        except Exception as exc:
            try:
                控制器.更新误差(0.0, 0.0)
            except Exception:
                pass
            self._日志("yolo_follow_failed", 错误=str(exc))
            self._状态("follow_failed", 错误=str(exc))

    def _执行首次按键和循环(
        self,
        p: dict[str, Any],
        *,
        持续YOLO调整: Callable[[], None] | None = None,
    ) -> bool:
        f_key = str(p.get("interaction_key", "f"))
        w_key = str(p.get("forward_key", "w"))
        pressed_w = False
        try:
            self._检查停止()
            if self.恢复焦点函数 is not None:
                self.恢复焦点函数()
            self._日志("yolo_key_down", 阶段="initial_f", 按键=f_key)
            self.输入模块.键盘按下(f_key)
            try:
                self._等待(int(p.get("initial_f_ms", 200)) / 1000)
            finally:
                self.输入模块.键盘弹起(f_key)
                self._日志("yolo_key_up", 阶段="initial_f", 按键=f_key)
            self._等待(int(p.get("initial_wait_ms", 300)) / 1000)

            self._日志("yolo_key_down", 阶段="w", 按键=w_key)
            self.输入模块.键盘按下(w_key)
            pressed_w = True
            w_start = self.时钟()
            repeat_ms = int(p.get("repeat_f_ms", 50))
            interval_ms = int(p["f_interval_ms"])
            for index in range(int(p["f_count"])):
                self._检查停止()
                cycle_start = self.时钟()
                self._日志("yolo_key_down", 阶段="repeat_f", 按键=f_key, 次数=index + 1)
                self.输入模块.键盘按下(f_key)
                try:
                    self._等待期间执行YOLO跟随(
                        repeat_ms / 1000,
                        持续YOLO调整,
                    )
                finally:
                    self.输入模块.键盘弹起(f_key)
                    self._日志("yolo_key_up", 阶段="repeat_f", 按键=f_key, 次数=index + 1)
                if index + 1 < int(p["f_count"]):
                    self._等待期间执行YOLO跟随(
                        max(0, interval_ms / 1000 - (self.时钟() - cycle_start)),
                        持续YOLO调整,
                    )
            self._等待期间执行YOLO跟随(
                max(0, int(p["w_duration_ms"]) / 1000 - (self.时钟() - w_start)),
                持续YOLO调整,
            )
            return True
        finally:
            if pressed_w:
                try:
                    self.输入模块.键盘弹起(w_key)
                    self._日志("yolo_key_up", 阶段="w", 按键=w_key)
                except Exception:
                    pass

    def _YOLO交互(self, action: 路线动作) -> bool:
        return self._YOLO对准(action, 执行交互=True)

    def _YOLO完全对准(self, action: 路线动作) -> bool:
        return self._YOLO对准(action, 执行交互=False)

    def _YOLO对准(self, action: 路线动作, *, 执行交互: bool) -> bool:
        p = action.参数
        timeout_ms = int(p.get("timeout_ms", 5000))
        对准控制器 = None
        持续恢复参数 = self.持续YOLO服务.暂停() if self.持续YOLO服务 is not None else None
        self._日志("yolo_interaction_start", 超时毫秒=timeout_ms, 仅对准=not 执行交互)
        self._状态(
            "start",
            目标角度=p.get("angle"),
            超时毫秒=timeout_ms,
            置信度阈值=float(p.get("confidence", 0.5)),
            仅对准=not 执行交互,
        )
        成功 = False
        扫描过 = False
        try:
            if "angle" in p and self.定位器 is not None:
                self._状态("view", 目标角度=p["angle"], 仅对准=not 执行交互)
                if not self.恢复视角(float(p["angle"])):
                    self._日志("yolo_view_failed", 目标角度=p["angle"])
                    self._状态("view_failed", 目标角度=p["angle"], 仅对准=not 执行交互)
                    return False
            if self.yolo检测器 is None or self.获取检测区域 is None:
                self._日志("yolo_unavailable")
                self._状态("unavailable", 仅对准=not 执行交互)
                return False

            deadline = self.时钟() + timeout_ms / 1000
            tolerance = int(p.get("tolerance_px", 12))
            target_y_offset = int(p.get("target_y_offset_px", 0))
            confidence = float(p.get("confidence", 0.5))
            required_stable_frames = int(p.get("stable_frame_count", 3))
            tracker = YOLO目标跟踪器(
                目标类别=str(p.get("target_class", "")),
                时钟=self.时钟,
            )
            scan_views = (
                生成扫描视角(
                    float(p.get("angle", 0)),
                    float(p.get("scan_step_degrees", 8)),
                    int(p.get("scan_attempts", 4)),
                )
                if not 执行交互 and bool(p.get("scan_enabled", True)) and self.定位器 is not None
                else []
            )
            scan_index = 0
            next_scan_time: float | None = None
            missing_since: float | None = None
            expanded_tracking = False
            stable_frames = 0
            对准控制器 = self.YOLO对准控制器工厂(
                self.输入模块,
                对准容差=tolerance,
                时钟=self.时钟,
            )

            while self.时钟() < deadline:
                self._检查停止()
                now = self.时钟()
                local_roi = self.获取检测区域()
                use_expanded = bool(
                    self.获取扩大检测区域 is not None
                    and (
                        expanded_tracking
                        or (missing_since is not None and now - missing_since >= 1.0)
                    )
                )
                if use_expanded:
                    left, top, right, bottom, center_x, center_y = self.获取扩大检测区域()
                else:
                    left, top, right, bottom, center_x, center_y = local_roi

                detections = self.yolo检测器.检测一次(left, top, right, bottom)
                target = tracker.选择(
                    detections,
                    (center_x, center_y),
                    confidence,
                    当前时间=self.时钟(),
                )
                剩余毫秒 = max(0, int(round((deadline - self.时钟()) * 1000)))
                frame = getattr(self.yolo检测器, "最近截图", None)
                if frame is not None:
                    try:
                        frame = frame.copy()
                    except Exception:
                        frame = None
                self._状态(
                    "inference",
                    检测数=len(detections),
                    检测结果=detections,
                    目标=target,
                    截图=frame,
                    ROI=(left, top, right, bottom),
                    中心=(center_x, center_y),
                    剩余毫秒=剩余毫秒,
                    执行器=getattr(self.yolo检测器, "执行器", "未知"),
                    检测模式=getattr(self.yolo检测器, "最近检测模式", "正常"),
                    搜索范围="扩大" if use_expanded else "局部",
                    仅对准=not 执行交互,
                )

                if target is None:
                    对准控制器.更新误差(0.0, 0.0)
                    stable_frames = 0
                    if missing_since is None:
                        missing_since = self.时钟()
                        next_scan_time = missing_since + 1.0
                    if (
                        scan_index < len(scan_views)
                        and next_scan_time is not None
                        and self.时钟() >= next_scan_time
                    ):
                        scan_angle = scan_views[scan_index]
                        scan_index += 1
                        扫描过 = True
                        self._状态(
                            "scan",
                            扫描视角=round(scan_angle, 2),
                            扫描次数=scan_index,
                            扫描总数=len(scan_views),
                            仅对准=True,
                        )
                        self.恢复视角(scan_angle)
                        tracker.重置()
                        missing_since = self.时钟()
                        next_scan_time = missing_since + 0.7
                    self._等待(self._YOLO检测间隔(对准控制器))
                    continue

                raw_x = float(target.get("原始中心X", target["中心X"]))
                raw_y = float(target.get("原始中心Y", target["中心Y"]))
                if use_expanded and not (
                    local_roi[0] <= raw_x <= local_roi[2]
                    and local_roi[1] <= raw_y <= local_roi[3]
                ):
                    expanded_tracking = True
                else:
                    expanded_tracking = False
                    missing_since = None
                    next_scan_time = None

                dx = float(target["中心X"]) - center_x
                dy = float(target["中心Y"]) + target_y_offset - center_y
                aligned = abs(dx) <= tolerance and abs(dy) <= tolerance
                if aligned:
                    目标速度X, 目标速度Y = 对准控制器.更新误差(0.0, 0.0)
                else:
                    目标速度X, 目标速度Y = 对准控制器.更新误差(dx, dy)
                current_speed_x = float(getattr(对准控制器, "当前速度X", 0.0))
                current_speed_y = float(getattr(对准控制器, "当前速度Y", 0.0))
                if aligned and abs(current_speed_x) <= 50 and abs(current_speed_y) <= 50:
                    stable_frames += 1
                else:
                    stable_frames = 0
                self._状态(
                    "adjust",
                    目标速度X=round(目标速度X, 2),
                    目标速度Y=round(目标速度Y, 2),
                    当前速度X=round(current_speed_x, 2),
                    当前速度Y=round(current_speed_y, 2),
                    误差X=round(dx, 2),
                    误差Y=round(dy, 2),
                    稳定帧=stable_frames,
                    需要稳定帧=required_stable_frames,
                    仅对准=not 执行交互,
                )
                self._YOLO检测间隔(对准控制器)

                if stable_frames >= required_stable_frames:
                    self._日志("yolo_aligned", 误差X=round(dx, 2), 误差Y=round(dy, 2))
                    self._状态(
                        "aligned",
                        误差X=round(dx, 2),
                        误差Y=round(dy, 2),
                        稳定帧=stable_frames,
                        仅对准=not 执行交互,
                    )
                    对准控制器.停止()
                    对准控制器 = None
                    if not 执行交互:
                        成功 = True
                        return True
                    跟随控制器 = self.YOLO对准控制器工厂(
                        self.输入模块,
                        对准容差=tolerance,
                        时钟=self.时钟,
                    )
                    follow_tracker = YOLO目标跟踪器(
                        目标类别=str(p.get("target_class", "")),
                        时钟=self.时钟,
                    )
                    try:
                        成功 = self._执行首次按键和循环(
                            p,
                            持续YOLO调整=lambda: self._YOLO持续跟随调整(
                                p,
                                (left, top, right, bottom),
                                (center_x, center_y),
                                跟随控制器,
                                follow_tracker,
                            ),
                        )
                    finally:
                        跟随控制器.停止()
                    return 成功
                if not aligned:
                    self._等待(self._YOLO检测间隔(对准控制器))

            if 扫描过 and "angle" in p and self.定位器 is not None:
                self.恢复视角(float(p["angle"]))
            self._日志("yolo_timeout", 超时毫秒=timeout_ms)
            self._状态("timeout", 超时毫秒=timeout_ms, 仅对准=not 执行交互)
            return False
        finally:
            if 对准控制器 is not None:
                对准控制器.停止()
            self._日志("yolo_interaction_finish", 成功=成功, 仅对准=not 执行交互)
            self._状态("finish", 成功=成功, 仅对准=not 执行交互)
            if 持续恢复参数 is not None:
                try:
                    self.持续YOLO服务.恢复(持续恢复参数)
                except Exception as exc:
                    self._日志("yolo_persistent_resume_failed", 错误=str(exc))

    def _持续YOLO开启(self, action: 路线动作) -> bool:
        if self.持续YOLO服务 is None:
            self._日志("yolo_persistent_unavailable")
            return False
        p = action.参数
        if self.定位器 is not None and not self.恢复视角(float(p["angle"])):
            self._日志("yolo_persistent_view_failed", 目标角度=p["angle"])
            return False
        return bool(self.持续YOLO服务.开启(p))

    def _持续YOLO关闭(self) -> bool:
        if self.持续YOLO服务 is not None:
            self.持续YOLO服务.关闭()
        return True

    def _识图动作(self, action: 路线动作) -> bool:
        if self.图像匹配器 is None:
            from 识图动作 import 模板匹配器

            self.图像匹配器 = 模板匹配器()
        p = action.参数
        timeout_ms = int(p.get("timeout_ms", 5000))
        interval = int(p.get("interval_ms", 100)) / 1000
        confidence = float(p.get("confidence", 0.85))
        template_path = str(p["template_path"])
        deadline = self.时钟() + timeout_ms / 1000
        self._状态("image_start", 类型=action.类型, 模板=template_path, 超时毫秒=timeout_ms)
        while True:
            self._检查停止()
            match = self.图像匹配器.匹配一次(template_path, confidence)
            found = match is not None
            success = found if action.类型 != "image_wait_disappear" else not found
            self._状态(
                "image_inference",
                类型=action.类型,
                模板=template_path,
                已找到=found,
                匹配结果=match,
                剩余毫秒=max(0, int(round((deadline - self.时钟()) * 1000))),
            )
            if success:
                if action.类型 == "image_click":
                    x = int(match["中心X"]) + int(p.get("click_offset_x", 0))
                    y = int(match["中心Y"]) + int(p.get("click_offset_y", 0))
                    self.输入模块.鼠标点击(x, y, 按键="左键")
                self._状态("image_finish", 类型=action.类型, 成功=True)
                return True
            if self.时钟() >= deadline:
                self._日志("image_timeout", 类型=action.类型, 模板=template_path)
                self._状态("image_finish", 类型=action.类型, 成功=False)
                return False
            self._等待(min(interval, max(0.0, deadline - self.时钟())))

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
        if action.类型 == "yolo_aim_once":
            return self._YOLO完全对准(action)
        if action.类型 == "yolo_aim_on":
            return self._持续YOLO开启(action)
        if action.类型 == "yolo_aim_off":
            return self._持续YOLO关闭()
        if action.类型 in {"image_wait_appear", "image_wait_disappear", "image_click"}:
            return self._识图动作(action)
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
