from __future__ import annotations

import math
import threading
import time


class 连续视角控制器:
    def __init__(
        self,
        输入模块,
        *,
        tick秒数: float = 0.008,
        每度像素: float = 100.0 / 3.0,
        比例增益: float = 3.0,
        最大角速度: float = 120.0,
        最大角加速度: float = 720.0,
        激活角度: float = 1.5,
        退出角度: float = 0.75,
        看门狗秒数: float = 0.12,
        自动启动: bool = True,
        时钟=time.monotonic,
    ) -> None:
        self.输入模块 = 输入模块
        self.tick秒数 = float(tick秒数)
        self.每度像素 = float(每度像素)
        self.比例增益 = float(比例增益)
        self.最大角速度 = abs(float(最大角速度))
        self.最大角加速度 = abs(float(最大角加速度))
        self.激活角度 = abs(float(激活角度))
        self.退出角度 = abs(float(退出角度))
        self.看门狗秒数 = max(0.0, float(看门狗秒数))
        self._时钟 = 时钟
        self._锁 = threading.Lock()
        self._停止事件 = threading.Event()
        self._线程: threading.Thread | None = None
        self._目标角速度 = 0.0
        self._当前角速度 = 0.0
        self._像素余数 = 0.0
        self._待读取像素 = 0
        self._正在修正 = False
        self._最后更新时间 = float(self._时钟())
        if 自动启动:
            self._线程 = threading.Thread(target=self._运行, name="连续视角控制", daemon=True)
            self._线程.start()

    @property
    def 目标角速度(self) -> float:
        with self._锁:
            return self._目标角速度

    @property
    def 当前角速度(self) -> float:
        with self._锁:
            return self._当前角速度

    @property
    def 正在修正(self) -> bool:
        with self._锁:
            return self._正在修正

    @property
    def 线程存活(self) -> bool:
        return self._线程 is not None and self._线程.is_alive()

    def 更新角度差(self, 角度差: float, *, 当前时间: float | None = None) -> float:
        当前时间 = float(self._时钟() if 当前时间 is None else 当前时间)
        角度差 = float(角度差)
        with self._锁:
            幅度 = abs(角度差)
            if self._正在修正:
                if 幅度 <= self.退出角度:
                    self._正在修正 = False
            elif 幅度 >= self.激活角度:
                self._正在修正 = True
            目标 = self.比例增益 * 角度差 if self._正在修正 else 0.0
            self._目标角速度 = self._限速(目标)
            self._最后更新时间 = 当前时间
            return self._目标角速度

    def 设置目标角速度(self, 目标角速度: float, *, 当前时间: float | None = None) -> float:
        当前时间 = float(self._时钟() if 当前时间 is None else 当前时间)
        with self._锁:
            self._目标角速度 = self._限速(float(目标角速度))
            self._最后更新时间 = 当前时间
            return self._目标角速度

    def _限速(self, 角速度: float) -> float:
        return max(-self.最大角速度, min(self.最大角速度, 角速度))

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

    def 推进一次(self, dt: float, *, 当前时间: float | None = None) -> int:
        dt = max(0.0, float(dt))
        当前时间 = float(self._时钟() if 当前时间 is None else 当前时间)
        with self._锁:
            if 当前时间 - self._最后更新时间 >= self.看门狗秒数:
                self._目标角速度 = 0.0
                self._正在修正 = False
            目标 = self._目标角速度
            if self._当前角速度 * 目标 < 0:
                目标 = 0.0
            最大变化 = self.最大角加速度 * dt
            self._当前角速度 = self._趋近(self._当前角速度, 目标, 最大变化)
            浮点像素 = self._当前角速度 * dt * self.每度像素 + self._像素余数
            整数像素 = self._取整像素(浮点像素)
            self._像素余数 = 浮点像素 - 整数像素
        if 整数像素:
            self.输入模块.鼠标相对移动(整数像素, 0)
            with self._锁:
                self._待读取像素 += 整数像素
        return 整数像素

    def 取出输出像素(self) -> int:
        with self._锁:
            输出像素 = self._待读取像素
            self._待读取像素 = 0
            return 输出像素

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
            self._目标角速度 = 0.0
            self._正在修正 = False
        self._停止事件.set()
        if self._线程 is not None and self._线程 is not threading.current_thread():
            self._线程.join()
