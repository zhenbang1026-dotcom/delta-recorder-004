from __future__ import annotations

import math
import threading
import time


class YOLO连续对准控制器:
    def __init__(
        self,
        输入模块,
        *,
        tick秒数: float = 0.008,
        比例增益: float = 40.0,
        最大速度: float = 9000.0,
        最大加速度: float = 54000.0,
        对准容差: float = 12.0,
        看门狗秒数: float = 0.12,
        自动启动: bool = True,
        时钟=time.monotonic,
    ) -> None:
        self.输入模块 = 输入模块
        self.tick秒数 = float(tick秒数)
        self.比例增益 = abs(float(比例增益))
        self.最大速度 = abs(float(最大速度))
        self.最大加速度 = abs(float(最大加速度))
        self.对准容差 = abs(float(对准容差))
        self.看门狗秒数 = max(0.0, float(看门狗秒数))
        self._时钟 = 时钟
        self._锁 = threading.Lock()
        self._停止事件 = threading.Event()
        self._线程: threading.Thread | None = None
        self._目标速度X = 0.0
        self._目标速度Y = 0.0
        self._当前速度X = 0.0
        self._当前速度Y = 0.0
        self._像素余数X = 0.0
        self._像素余数Y = 0.0
        self._最后更新时间 = float(self._时钟())
        if 自动启动:
            self._线程 = threading.Thread(target=self._运行, name="YOLO连续对准", daemon=True)
            self._线程.start()

    @property
    def 目标速度X(self) -> float:
        with self._锁:
            return self._目标速度X

    @property
    def 目标速度Y(self) -> float:
        with self._锁:
            return self._目标速度Y

    @property
    def 当前速度X(self) -> float:
        with self._锁:
            return self._当前速度X

    @property
    def 当前速度Y(self) -> float:
        with self._锁:
            return self._当前速度Y

    @property
    def 线程存活(self) -> bool:
        return self._线程 is not None and self._线程.is_alive()

    def _计算目标速度(self, 误差: float) -> float:
        if abs(误差) <= self.对准容差:
            return 0.0
        速度 = 误差 * self.比例增益
        return max(-self.最大速度, min(self.最大速度, 速度))

    def 更新误差(
        self, 误差X: float, 误差Y: float, *, 当前时间: float | None = None
    ) -> tuple[float, float]:
        当前时间 = float(self._时钟() if 当前时间 is None else 当前时间)
        with self._锁:
            self._目标速度X = self._计算目标速度(float(误差X))
            self._目标速度Y = self._计算目标速度(float(误差Y))
            self._最后更新时间 = 当前时间
            return self._目标速度X, self._目标速度Y

    @staticmethod
    def _趋近(当前值: float, 目标值: float, 最大变化: float) -> float:
        if 当前值 < 目标值:
            return min(目标值, 当前值 + 最大变化)
        if 当前值 > 目标值:
            return max(目标值, 当前值 - 最大变化)
        return 当前值

    @staticmethod
    def _取整像素(值: float) -> int:
        if 值 == 0:
            return 0
        return int(math.copysign(math.floor(abs(值) + 0.5), 值))

    def 推进一次(
        self, dt: float, *, 当前时间: float | None = None
    ) -> tuple[int, int]:
        dt = max(0.0, float(dt))
        当前时间 = float(self._时钟() if 当前时间 is None else 当前时间)
        with self._锁:
            if 当前时间 - self._最后更新时间 >= self.看门狗秒数:
                self._目标速度X = 0.0
                self._目标速度Y = 0.0

            目标速度X = self._目标速度X
            目标速度Y = self._目标速度Y
            if self._当前速度X * 目标速度X < 0:
                目标速度X = 0.0
            if self._当前速度Y * 目标速度Y < 0:
                目标速度Y = 0.0

            最大变化 = self.最大加速度 * dt
            self._当前速度X = self._趋近(self._当前速度X, 目标速度X, 最大变化)
            self._当前速度Y = self._趋近(self._当前速度Y, 目标速度Y, 最大变化)

            浮点像素X = self._当前速度X * dt + self._像素余数X
            浮点像素Y = self._当前速度Y * dt + self._像素余数Y
            整数像素X = self._取整像素(浮点像素X)
            整数像素Y = self._取整像素(浮点像素Y)
            self._像素余数X = 浮点像素X - 整数像素X
            self._像素余数Y = 浮点像素Y - 整数像素Y

        if 整数像素X or 整数像素Y:
            self.输入模块.鼠标相对移动(整数像素X, 整数像素Y)
        return 整数像素X, 整数像素Y

    def _运行(self) -> None:
        下次执行 = float(self._时钟()) + self.tick秒数
        while not self._停止事件.is_set():
            剩余 = 下次执行 - float(self._时钟())
            if 剩余 > 0 and self._停止事件.wait(剩余):
                break
            if self._停止事件.is_set():
                break
            当前时间 = float(self._时钟())
            self.推进一次(self.tick秒数, 当前时间=当前时间)
            下次执行 += self.tick秒数
            if 下次执行 < 当前时间:
                下次执行 = 当前时间 + self.tick秒数

    def 停止(self) -> None:
        with self._锁:
            self._目标速度X = 0.0
            self._目标速度Y = 0.0
        self._停止事件.set()
        if self._线程 is not None and self._线程 is not threading.current_thread():
            self._线程.join()
