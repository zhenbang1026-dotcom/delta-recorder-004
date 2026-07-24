import math
import threading
import time

from YOLO连续对准 import YOLO连续对准控制器


class 假输入模块:
    def __init__(self):
        self.移动记录 = []
        self.收到移动 = threading.Event()

    def 鼠标相对移动(self, dx, dy):
        self.移动记录.append((int(dx), int(dy)))
        self.收到移动.set()


def test_large_error_is_emitted_as_multiple_small_steps():
    输入 = 假输入模块()
    控制器 = YOLO连续对准控制器(
        输入, 自动启动=False, 时钟=lambda: 0.0, 看门狗秒数=10.0
    )
    控制器.更新误差(1000, -1000, 当前时间=0.0)

    for index in range(5):
        控制器.推进一次(0.008, 当前时间=(index + 1) * 0.008)

    assert len(输入.移动记录) == 5
    assert all(0 < dx < 80 and -80 < dy < 0 for dx, dy in 输入.移动记录)
    assert len(set(输入.移动记录)) > 1


def test_speed_and_acceleration_are_limited_on_both_axes():
    控制器 = YOLO连续对准控制器(
        假输入模块(), 自动启动=False, 时钟=lambda: 0.0, 看门狗秒数=10.0
    )

    目标X, 目标Y = 控制器.更新误差(1000, -1000, 当前时间=0.0)
    控制器.推进一次(0.008, 当前时间=0.008)

    assert (目标X, 目标Y) == (9000.0, -9000.0)
    assert math.isclose(控制器.当前速度X, 432.0, abs_tol=1e-9)
    assert math.isclose(控制器.当前速度Y, -432.0, abs_tol=1e-9)


def test_each_axis_reverses_direction_through_zero():
    控制器 = YOLO连续对准控制器(
        假输入模块(), 自动启动=False, 时钟=lambda: 0.0, 看门狗秒数=10.0
    )
    控制器.更新误差(1000, -1000, 当前时间=0.0)
    for index in range(10):
        控制器.推进一次(0.008, 当前时间=(index + 1) * 0.008)
    assert 控制器.当前速度X > 0
    assert 控制器.当前速度Y < 0

    控制器.更新误差(-1000, 1000, 当前时间=0.08)
    X速度序列 = []
    Y速度序列 = []
    for index in range(30):
        控制器.推进一次(0.008, 当前时间=0.088 + index * 0.008)
        X速度序列.append(控制器.当前速度X)
        Y速度序列.append(控制器.当前速度Y)
        if 控制器.当前速度X < 0 and 控制器.当前速度Y > 0:
            break

    首个X负值 = next(index for index, value in enumerate(X速度序列) if value < 0)
    首个Y正值 = next(index for index, value in enumerate(Y速度序列) if value > 0)
    assert any(math.isclose(value, 0.0, abs_tol=1e-9) for value in X速度序列[:首个X负值])
    assert any(math.isclose(value, 0.0, abs_tol=1e-9) for value in Y速度序列[:首个Y正值])


def test_watchdog_clears_stale_error_and_decelerates():
    控制器 = YOLO连续对准控制器(假输入模块(), 自动启动=False, 时钟=lambda: 0.0)
    控制器.更新误差(1000, -1000, 当前时间=0.0)
    控制器.推进一次(0.008, 当前时间=0.008)
    原速度X = 控制器.当前速度X
    原速度Y = 控制器.当前速度Y

    控制器.推进一次(0.008, 当前时间=0.121)

    assert 控制器.目标速度X == 0.0
    assert 控制器.目标速度Y == 0.0
    assert abs(控制器.当前速度X) < abs(原速度X)
    assert abs(控制器.当前速度Y) < abs(原速度Y)


def test_stop_reclaims_background_thread_without_late_movement():
    输入 = 假输入模块()
    控制器 = YOLO连续对准控制器(输入, tick秒数=0.004)
    控制器.更新误差(1000, -1000)
    assert 输入.收到移动.wait(0.2)

    控制器.停止()
    停止时数量 = len(输入.移动记录)
    time.sleep(0.02)

    assert not 控制器.线程存活
    assert len(输入.移动记录) == 停止时数量
