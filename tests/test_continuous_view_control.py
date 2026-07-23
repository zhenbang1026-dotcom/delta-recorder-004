import math
import threading
import time

from 连续视角控制 import 连续视角控制器


class 假输入模块:
    def __init__(self):
        self.移动记录 = []
        self.收到移动 = threading.Event()

    def 鼠标相对移动(self, dx, dy):
        self.移动记录.append((int(dx), int(dy)))
        self.收到移动.set()


def test_deadband_hysteresis_keeps_small_error_inactive():
    控制器 = 连续视角控制器(假输入模块(), 自动启动=False, 时钟=lambda: 0.0)

    控制器.更新角度差(1.49, 当前时间=0.0)
    assert 控制器.目标角速度 == 0.0
    assert not 控制器.正在修正

    控制器.更新角度差(1.51, 当前时间=0.01)
    assert 控制器.目标角速度 > 0.0
    assert 控制器.正在修正

    控制器.更新角度差(1.0, 当前时间=0.02)
    assert 控制器.目标角速度 > 0.0
    assert 控制器.正在修正

    控制器.更新角度差(0.74, 当前时间=0.03)
    assert 控制器.目标角速度 == 0.0
    assert not 控制器.正在修正

    控制器.更新角度差(1.49, 当前时间=0.04)
    assert 控制器.目标角速度 == 0.0


def test_speed_and_acceleration_are_limited_per_tick():
    控制器 = 连续视角控制器(假输入模块(), 自动启动=False, 时钟=lambda: 0.0)
    控制器.设置目标角速度(999.0, 当前时间=0.0)

    控制器.推进一次(0.008, 当前时间=0.008)

    assert 控制器.目标角速度 == 120.0
    assert math.isclose(控制器.当前角速度, 5.76, abs_tol=1e-9)
    assert abs(控制器.当前角速度) <= 120.0


def test_direction_reversal_must_pass_through_zero():
    控制器 = 连续视角控制器(假输入模块(), 自动启动=False, 时钟=lambda: 0.0)
    控制器.设置目标角速度(120.0, 当前时间=0.0)
    for i in range(10):
        控制器.推进一次(0.008, 当前时间=(i + 1) * 0.008)
    assert 控制器.当前角速度 > 0

    控制器.设置目标角速度(-120.0, 当前时间=0.08)
    速度序列 = []
    for i in range(20):
        控制器.推进一次(0.008, 当前时间=0.088 + i * 0.008)
        速度序列.append(控制器.当前角速度)
        if 控制器.当前角速度 < 0:
            break

    首个负值 = next(i for i, value in enumerate(速度序列) if value < 0)
    assert any(math.isclose(value, 0.0, abs_tol=1e-9) for value in 速度序列[:首个负值])
    assert all(
        abs(right - left) <= 720.0 * 0.008 + 1e-9
        for left, right in zip(速度序列, 速度序列[1:])
    )


def test_integer_residual_preserves_total_mouse_distance():
    输入 = 假输入模块()
    控制器 = 连续视角控制器(
        输入,
        自动启动=False,
        时钟=lambda: 0.0,
        最大角加速度=1e9,
        看门狗秒数=10.0,
    )
    控制器.设置目标角速度(1.0, 当前时间=0.0)

    for i in range(1000):
        控制器.推进一次(0.008, 当前时间=(i + 1) * 0.008)

    实际像素 = sum(dx for dx, _ in 输入.移动记录)
    理论像素 = 1.0 * 8.0 * (100.0 / 3.0)
    assert abs(实际像素 - 理论像素) <= 1.0


def test_emitted_pixels_can_be_drained_for_runtime_diagnostics():
    输入 = 假输入模块()
    控制器 = 连续视角控制器(
        输入,
        自动启动=False,
        时钟=lambda: 0.0,
        最大角加速度=1e9,
        看门狗秒数=10.0,
    )
    控制器.设置目标角速度(30.0, 当前时间=0.0)
    控制器.推进一次(0.008, 当前时间=0.008)
    控制器.推进一次(0.008, 当前时间=0.016)

    assert 控制器.取出输出像素() == sum(dx for dx, _ in 输入.移动记录)
    assert 控制器.取出输出像素() == 0


def test_watchdog_clears_stale_target_and_decelerates():
    控制器 = 连续视角控制器(假输入模块(), 自动启动=False, 时钟=lambda: 0.0)
    控制器.设置目标角速度(120.0, 当前时间=0.0)
    控制器.推进一次(0.008, 当前时间=0.008)
    原速度 = 控制器.当前角速度

    控制器.推进一次(0.008, 当前时间=0.121)

    assert 控制器.目标角速度 == 0.0
    assert abs(控制器.当前角速度) < abs(原速度)


def test_thread_ticks_and_stop_reclaims_it_immediately():
    输入 = 假输入模块()
    控制器 = 连续视角控制器(输入, tick秒数=0.004)
    控制器.更新角度差(60.0)
    assert 输入.收到移动.wait(0.2)

    开始 = time.monotonic()
    控制器.停止()
    停止耗时 = time.monotonic() - 开始
    停止时数量 = len(输入.移动记录)
    time.sleep(0.02)

    assert 停止耗时 < 0.1
    assert not 控制器.线程存活
    assert len(输入.移动记录) == 停止时数量


def test_stop_waits_until_inflight_mouse_call_finishes():
    class 阻塞输入:
        def __init__(self):
            self.已进入 = threading.Event()
            self.允许返回 = threading.Event()
            self.移动次数 = 0

        def 鼠标相对移动(self, _dx, _dy):
            self.已进入.set()
            self.允许返回.wait()
            self.移动次数 += 1

    输入 = 阻塞输入()
    控制器 = 连续视角控制器(输入, tick秒数=0.004)
    控制器.更新角度差(60.0)
    assert 输入.已进入.wait(0.2)

    停止完成 = threading.Event()
    停止线程 = threading.Thread(target=lambda: (控制器.停止(), 停止完成.set()))
    停止线程.start()

    assert not 停止完成.wait(0.08)
    输入.允许返回.set()
    assert 停止完成.wait(0.2)
    停止线程.join(timeout=0.2)
    停止后次数 = 输入.移动次数
    time.sleep(0.02)

    assert not 控制器.线程存活
    assert 输入.移动次数 == 停止后次数
