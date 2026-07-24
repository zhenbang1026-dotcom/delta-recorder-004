from __future__ import annotations

import threading
from types import SimpleNamespace

import pytest

from 路线动作 import 路线动作
from 路线动作执行 import 路线动作执行器


class 假输入:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def 键盘按下(self, key):
        self.calls.append(("down", key))

    def 键盘弹起(self, key):
        self.calls.append(("up", key))

    def 鼠标相对移动(self, dx, dy):
        self.calls.append(("move", dx, dy))

    def 丝滑相对移动(self, dx, dy, 步间隔=0.0):
        self.calls.append(("smooth", dx, dy))


def test_combo_key_releases_in_reverse_order() -> None:
    inp = 假输入()
    now = [0.0]
    runner = 路线动作执行器(
        inp,
        时钟=lambda: now[0],
        睡眠函数=lambda seconds: now.__setitem__(0, now[0] + seconds),
    )

    assert runner.执行动作(路线动作("key", {"keys": ["ctrl", "f"], "mode": "hold", "duration_ms": 1}))
    assert inp.calls == [("down", "ctrl"), ("down", "f"), ("up", "f"), ("up", "ctrl")]


def test_look_action_returns_x_to_origin_and_keeps_y_delta() -> None:
    inp = 假输入()
    now = [0.0]
    runner = 路线动作执行器(
        inp,
        随机数=__import__("random").Random(1),
        时钟=lambda: now[0],
        睡眠函数=lambda seconds: now.__setitem__(0, now[0] + seconds),
    )

    assert runner.执行动作(路线动作("look", {"direction": "down", "y_delta": 20, "duration_ms": 16, "x_random": 4}))
    moves = [call for call in inp.calls if call[0] == "smooth"]
    assert sum(call[1] for call in moves) == 0
    assert sum(call[2] for call in moves) == 20


def test_view_action_retries_until_angle_is_within_tolerance() -> None:
    inp = 假输入()
    angles = iter([350.0, 358.0, 0.5])
    locator = SimpleNamespace(读取状态=lambda: (0, 0, next(angles)))
    now = [0.0]
    runner = 路线动作执行器(
        inp,
        定位器=locator,
        时钟=lambda: now[0],
        睡眠函数=lambda seconds: now.__setitem__(0, now[0] + seconds),
    )

    assert runner.执行动作(路线动作("view", {"angle": 0.0}))
    assert any(call[0] in {"smooth", "move"} for call in inp.calls)


def test_view_action_can_recover_a_large_angle_within_five_attempts() -> None:
    inp = 假输入()
    angles = iter([204.0, 168.0, 132.0, 96.0, 93.0])
    locator = SimpleNamespace(读取状态=lambda: (0, 0, next(angles)))
    now = [0.0]
    runner = 路线动作执行器(
        inp,
        定位器=locator,
        时钟=lambda: now[0],
        睡眠函数=lambda seconds: now.__setitem__(0, now[0] + seconds),
    )

    assert runner.执行动作(路线动作("view", {"angle": 93.0}))
    assert max(abs(call[1]) for call in inp.calls if call[0] == "smooth") > 80


def test_yolo_action_always_releases_w_on_stop() -> None:
    inp = 假输入()
    stop = threading.Event()
    now = [0.0]

    def clock():
        return now[0]

    def sleep(seconds):
        now[0] += seconds
        if any(call == ("down", "w") for call in inp.calls):
            stop.set()

    detector = SimpleNamespace(
        检测一次=lambda *_args: [{"中心X": 100, "中心Y": 100, "置信度": 0.9, "类别名称": "医疗包"}]
    )
    runner = 路线动作执行器(
        inp,
        yolo检测器=detector,
        获取检测区域=lambda: (0, 0, 200, 200, 100, 100),
        停止事件=stop,
        时钟=clock,
        睡眠函数=sleep,
    )
    action = 路线动作(
        "yolo_interact",
        {
            "confidence": 0.5,
            "timeout_ms": 5000,
            "tolerance_px": 12,
            "initial_f_ms": 1,
            "initial_wait_ms": 0,
            "repeat_f_ms": 1,
            "w_duration_ms": 20,
            "f_count": 1,
            "f_interval_ms": 1,
        },
    )

    try:
        runner.执行动作(action)
    except InterruptedError:
        pass
    assert ("down", "w") in inp.calls
    assert ("up", "w") in inp.calls


def test_yolo_action_reports_visible_progress_events() -> None:
    inp = 假输入()
    events: list[str] = []
    now = [0.0]
    detector = SimpleNamespace(
        执行器="CPU",
        最近截图=None,
        检测一次=lambda *_args: [{"中心X": 100, "中心Y": 100, "置信度": 0.9, "类别名称": "医疗包"}],
    )
    runner = 路线动作执行器(
        inp,
        yolo检测器=detector,
        获取检测区域=lambda: (0, 0, 200, 200, 100, 100),
        状态函数=lambda event, **_fields: events.append(event),
        时钟=lambda: now[0],
        睡眠函数=lambda seconds: now.__setitem__(0, now[0] + seconds),
    )

    action = 路线动作(
        "yolo_interact",
        {
            "confidence": 0.5,
            "timeout_ms": 1,
            "tolerance_px": 12,
            "initial_f_ms": 1,
            "initial_wait_ms": 0,
            "repeat_f_ms": 1,
            "w_duration_ms": 1,
            "f_count": 1,
            "f_interval_ms": 1,
        },
    )

    assert runner.执行动作(action)
    assert events[0] == "start"
    assert "inference" in events
    assert "aligned" in events
    assert events[-1] == "finish"


def test_yolo_interaction_restores_game_focus_before_f() -> None:
    inp = 假输入()
    focus_calls: list[str] = []
    now = [0.0]
    detector = SimpleNamespace(
        执行器="CPU",
        检测一次=lambda *_args: [{"中心X": 100, "中心Y": 100, "置信度": 0.9, "类别名称": "医疗包"}],
    )
    runner = 路线动作执行器(
        inp,
        yolo检测器=detector,
        获取检测区域=lambda: (0, 0, 200, 200, 100, 100),
        恢复焦点函数=lambda: focus_calls.append("game"),
        时钟=lambda: now[0],
        睡眠函数=lambda seconds: now.__setitem__(0, now[0] + seconds),
    )

    action = 路线动作(
        "yolo_interact",
        {
            "timeout_ms": 1,
            "tolerance_px": 12,
            "initial_f_ms": 1,
            "initial_wait_ms": 0,
            "repeat_f_ms": 1,
            "w_duration_ms": 1,
            "f_count": 1,
            "f_interval_ms": 1,
        },
    )

    assert runner.执行动作(action)
    assert focus_calls == ["game"]
    assert ("down", "f") in inp.calls
    assert ("down", "w") in inp.calls


class 假YOLO对准控制器:
    def __init__(self, _输入模块, 记录, **_kwargs):
        self.记录 = 记录

    def 更新误差(self, dx, dy):
        self.记录.append(("aim", dx, dy))
        return dx, dy

    def 停止(self):
        self.记录.append(("aim_stop",))


def _YOLO动作():
    return 路线动作(
        "yolo_interact",
        {
            "timeout_ms": 100,
            "tolerance_px": 12,
            "initial_f_ms": 1,
            "initial_wait_ms": 0,
            "repeat_f_ms": 1,
            "w_duration_ms": 1,
            "f_count": 1,
            "f_interval_ms": 1,
        },
    )


def test_yolo_uses_smooth_controller_and_stops_it_before_keyboard_actions() -> None:
    记录 = []

    class 带记录输入(假输入):
        def 键盘按下(self, key):
            记录.append(("down", key))
            super().键盘按下(key)

    targets = iter(
        [
            [{"中心X": 150, "中心Y": 80, "置信度": 0.9, "类别名称": "医疗包"}],
            [{"中心X": 100, "中心Y": 100, "置信度": 0.9, "类别名称": "医疗包"}],
        ]
    )
    now = [0.0]
    输入 = 带记录输入()
    runner = 路线动作执行器(
        输入,
        yolo检测器=SimpleNamespace(检测一次=lambda *_args: next(targets)),
        获取检测区域=lambda: (0, 0, 200, 200, 100, 100),
        YOLO对准控制器工厂=lambda input_module, **kwargs: 假YOLO对准控制器(
            input_module, 记录, **kwargs
        ),
        时钟=lambda: now[0],
        睡眠函数=lambda seconds: now.__setitem__(0, now[0] + seconds),
    )

    assert runner.执行动作(_YOLO动作())
    assert ("aim", 50.0, -20.0) in 记录
    assert 记录.index(("aim_stop",)) < 记录.index(("down", "f"))
    assert not any(call[0] == "move" for call in 输入.calls)


def test_yolo_stops_smooth_controller_on_timeout() -> None:
    记录 = []
    now = [0.0]
    runner = 路线动作执行器(
        假输入(),
        yolo检测器=SimpleNamespace(
            检测一次=lambda *_args: [
                {"中心X": 150, "中心Y": 80, "置信度": 0.9, "类别名称": "医疗包"}
            ]
        ),
        获取检测区域=lambda: (0, 0, 200, 200, 100, 100),
        YOLO对准控制器工厂=lambda input_module, **kwargs: 假YOLO对准控制器(
            input_module, 记录, **kwargs
        ),
        时钟=lambda: now[0],
        睡眠函数=lambda seconds: now.__setitem__(0, now[0] + seconds),
    )

    assert not runner.执行动作(_YOLO动作())
    assert 记录[-1] == ("aim_stop",)


def test_yolo_stops_smooth_controller_when_detection_raises() -> None:
    记录 = []

    def 检测失败(*_args):
        raise RuntimeError("检测失败")

    runner = 路线动作执行器(
        假输入(),
        yolo检测器=SimpleNamespace(检测一次=检测失败),
        获取检测区域=lambda: (0, 0, 200, 200, 100, 100),
        YOLO对准控制器工厂=lambda input_module, **kwargs: 假YOLO对准控制器(
            input_module, 记录, **kwargs
        ),
    )

    with pytest.raises(RuntimeError, match="检测失败"):
        runner.执行动作(_YOLO动作())
    assert 记录[-1] == ("aim_stop",)
