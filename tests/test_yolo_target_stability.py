from __future__ import annotations

from YOLO物资动作 import YOLO目标跟踪器, 生成扫描视角, 计算自适应检测参数


def _target(name: str, x: float, y: float, confidence: float = 0.9) -> dict:
    return {"类别名称": name, "中心X": x, "中心Y": y, "置信度": confidence}


def test_target_tracker_uses_three_frame_median_and_keeps_locked_identity() -> None:
    tracker = YOLO目标跟踪器(滤波帧数=3, 锁定秒数=0.5)
    center = (100.0, 100.0)

    assert tracker.选择([_target("航空箱", 130, 100)], center, 0.5, 当前时间=0.0)["中心X"] == 130
    tracker.选择([_target("航空箱", 90, 100), _target("医疗包", 100, 100, 0.99)], center, 0.5, 当前时间=0.1)
    filtered = tracker.选择([_target("航空箱", 110, 100), _target("医疗包", 100, 100, 0.99)], center, 0.5, 当前时间=0.2)

    assert filtered["类别名称"] == "航空箱"
    assert filtered["中心X"] == 110


def test_target_tracker_can_filter_configured_class_and_unlock_after_timeout() -> None:
    tracker = YOLO目标跟踪器(目标类别="医疗包", 锁定秒数=0.5)
    center = (100.0, 100.0)

    assert tracker.选择([_target("航空箱", 100, 100)], center, 0.5, 当前时间=0.0) is None
    assert tracker.选择([_target("医疗包", 120, 100)], center, 0.5, 当前时间=0.1)
    assert tracker.选择([], center, 0.5, 当前时间=0.7) is None


def test_adaptive_timing_leaves_more_time_for_slow_hardware() -> None:
    fast_interval, fast_watchdog = 计算自适应检测参数(0.02)
    slow_interval, slow_watchdog = 计算自适应检测参数(0.25)

    assert slow_interval > fast_interval
    assert slow_watchdog > fast_watchdog
    assert slow_watchdog > 0.5


def test_scan_angles_alternate_around_recorded_view() -> None:
    assert 生成扫描视角(90.0, 8.0, 4) == [98.0, 82.0, 106.0, 74.0]
