from __future__ import annotations

import threading
import time
from typing import Any, Callable

from YOLO物资动作 import 选择综合目标
from YOLO连续对准 import YOLO连续对准控制器


class YOLO持续对准服务:
    def __init__(
        self,
        输入模块: Any,
        yolo检测器: Any,
        获取检测区域: Callable[[], tuple[int, int, int, int, float, float]],
        *,
        停止事件: Any = None,
        日志函数: Callable[..., Any] | None = None,
        状态函数: Callable[..., Any] | None = None,
        YOLO对准控制器工厂: Callable[..., Any] = YOLO连续对准控制器,
        检测间隔秒数: float = 0.05,
        时钟: Callable[[], float] = time.monotonic,
    ) -> None:
        self.输入模块 = 输入模块
        self.yolo检测器 = yolo检测器
        self.获取检测区域 = 获取检测区域
        self.停止事件 = 停止事件
        self.日志函数 = 日志函数
        self.状态函数 = 状态函数
        self.YOLO对准控制器工厂 = YOLO对准控制器工厂
        self.检测间隔秒数 = max(0.0, float(检测间隔秒数))
        self.时钟 = 时钟
        self._线程: threading.Thread | None = None
        self._本次停止事件: threading.Event | None = None
        self._控制器: Any = None
        self._参数: dict[str, Any] | None = None

    @property
    def 是否开启(self) -> bool:
        return self._线程 is not None and self._线程.is_alive()

    def _全局已停止(self) -> bool:
        return bool(self.停止事件 is not None and self.停止事件.is_set())

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

    def 开启(self, 参数: dict[str, Any]) -> bool:
        self.关闭()
        if self._全局已停止():
            return False
        参数 = dict(参数)
        tolerance = int(参数.get("tolerance_px", 12))
        本次停止事件 = threading.Event()
        控制器 = self.YOLO对准控制器工厂(
            self.输入模块,
            对准容差=tolerance,
            时钟=self.时钟,
        )
        线程 = threading.Thread(
            target=lambda: self._运行(参数, 本次停止事件, 控制器),
            name="YOLO持续对准服务",
            daemon=True,
        )
        self._参数 = 参数
        self._本次停止事件 = 本次停止事件
        self._控制器 = 控制器
        self._线程 = 线程
        self._日志("yolo_persistent_start", 参数=参数)
        self._状态(
            "start",
            目标角度=参数.get("angle"),
            超时毫秒=0,
            置信度阈值=float(参数.get("confidence", 0.5)),
            持续跟随=True,
        )
        try:
            线程.start()
        except Exception:
            本次停止事件.set()
            控制器.停止()
            self._线程 = None
            self._本次停止事件 = None
            self._控制器 = None
            self._参数 = None
            raise
        return True

    def _运行(self, 参数: dict[str, Any], 本次停止事件: threading.Event, 控制器: Any) -> None:
        confidence = float(参数.get("confidence", 0.5))
        tolerance = int(参数.get("tolerance_px", 12))
        target_y_offset = int(参数.get("target_y_offset_px", 0))
        try:
            while not 本次停止事件.is_set() and not self._全局已停止():
                try:
                    left, top, right, bottom, center_x, center_y = self.获取检测区域()
                    detections = self.yolo检测器.检测一次(left, top, right, bottom)
                    if 本次停止事件.is_set() or self._全局已停止():
                        break
                    target = 选择综合目标(detections, (center_x, center_y), confidence)
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
                        持续跟随=True,
                    )
                    if target is None:
                        控制器.更新误差(0.0, 0.0)
                    else:
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
                            误差X=round(dx, 2),
                            误差Y=round(dy, 2),
                            持续跟随=True,
                        )
                except Exception as exc:
                    try:
                        控制器.更新误差(0.0, 0.0)
                    except Exception:
                        pass
                    self._日志("yolo_persistent_detection_failed", 错误=str(exc))
                    self._状态("follow_failed", 错误=str(exc), 持续跟随=True)
                if 本次停止事件.wait(self.检测间隔秒数):
                    break
        finally:
            控制器.停止()
            self._日志("yolo_persistent_stop")
            self._状态("finish", 成功=True, 持续跟随=True)

    def 关闭(self) -> None:
        本次停止事件 = self._本次停止事件
        线程 = self._线程
        if 本次停止事件 is not None:
            本次停止事件.set()
        if 线程 is not None and 线程 is not threading.current_thread():
            线程.join()
        self._线程 = None
        self._本次停止事件 = None
        self._控制器 = None
        self._参数 = None

    def 暂停(self) -> dict[str, Any] | None:
        参数 = dict(self._参数) if self.是否开启 and self._参数 is not None else None
        self.关闭()
        return 参数

    def 恢复(self, 参数: dict[str, Any] | None) -> bool:
        if 参数 is None or self._全局已停止():
            return False
        return self.开启(参数)
