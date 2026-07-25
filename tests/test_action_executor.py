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


class 假视角控制器:
    def __init__(self) -> None:
        self.角度差记录 = []
        self.当前角速度 = 0.0

    def 更新角度差(self, delta):
        self.角度差记录.append(float(delta))

    def 停止(self):
        raise AssertionError("共享视角控制器不应由单个路线动作停止")


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


@pytest.mark.parametrize("mode", ["click", "hold"])
def test_key_action_repeats_after_release_with_fresh_random_duration(mode) -> None:
    class 顺序随机数:
        def __init__(self):
            self.values = iter([-5, 20, 0])

        def randint(self, lower, upper):
            assert (lower, upper) == (-5, 20)
            return next(self.values)

    inp = 假输入()
    waits = []
    runner = 路线动作执行器(inp, 随机数=顺序随机数())
    runner._等待 = lambda seconds: waits.append(seconds)
    action = 路线动作(
        "key",
        {
            "keys": ["w", "f"],
            "mode": mode,
            "duration_ms": 100,
            "repeat_count": 3,
            "repeat_interval_ms": 100,
            "duration_jitter_minus_ms": 5,
            "duration_jitter_plus_ms": 20,
        },
    )

    assert runner.执行动作(action)
    assert inp.calls == [
        ("down", "w"), ("down", "f"), ("up", "f"), ("up", "w"),
        ("down", "w"), ("down", "f"), ("up", "f"), ("up", "w"),
        ("down", "w"), ("down", "f"), ("up", "f"), ("up", "w"),
    ]
    assert waits == pytest.approx([0.095, 0.1, 0.12, 0.1, 0.1])


def test_repeated_key_action_releases_current_combo_when_stopped() -> None:
    inp = 假输入()
    waits = [0]
    runner = 路线动作执行器(inp)

    def wait_or_stop(_seconds):
        waits[0] += 1
        if waits[0] == 3:
            raise InterruptedError("停止")

    runner._等待 = wait_or_stop
    action = 路线动作(
        "key",
        {
            "keys": ["ctrl", "f"],
            "mode": "hold",
            "duration_ms": 100,
            "repeat_count": 2,
            "repeat_interval_ms": 100,
        },
    )

    with pytest.raises(InterruptedError):
        runner.执行动作(action)
    assert inp.calls[-2:] == [("up", "f"), ("up", "ctrl")]


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
    controller = 假视角控制器()
    angles = iter([350.0, 358.0, 0.5])
    locator = SimpleNamespace(读取状态=lambda: (0, 0, next(angles)))
    now = [0.0]
    runner = 路线动作执行器(
        inp,
        定位器=locator,
        视角控制器=controller,
        时钟=lambda: now[0],
        睡眠函数=lambda seconds: now.__setitem__(0, now[0] + seconds),
    )

    assert runner.执行动作(路线动作("view", {"angle": 0.0}))
    assert controller.角度差记录 == pytest.approx([10.0, 0.0])
    assert not any(call[0] in {"smooth", "move"} for call in inp.calls)


def test_view_action_can_recover_a_large_angle_within_five_attempts() -> None:
    inp = 假输入()
    controller = 假视角控制器()
    angles = iter([204.0, 168.0, 132.0, 96.0, 93.0])
    locator = SimpleNamespace(读取状态=lambda: (0, 0, next(angles)))
    now = [0.0]
    runner = 路线动作执行器(
        inp,
        定位器=locator,
        视角控制器=controller,
        时钟=lambda: now[0],
        睡眠函数=lambda seconds: now.__setitem__(0, now[0] + seconds),
    )

    assert runner.执行动作(路线动作("view", {"angle": 93.0}))
    assert controller.角度差记录 == pytest.approx([-111.0, -75.0, -39.0, 0.0])
    assert not any(call[0] in {"smooth", "move"} for call in inp.calls)


def test_view_recovery_clears_continuous_target_when_locator_raises() -> None:
    controller = 假视角控制器()
    locator = SimpleNamespace(读取状态=lambda: (_ for _ in ()).throw(RuntimeError("识别失败")))
    runner = 路线动作执行器(假输入(), 定位器=locator, 视角控制器=controller)

    with pytest.raises(RuntimeError, match="识别失败"):
        runner.恢复视角(90.0)

    assert controller.角度差记录 == [0.0]


def test_standalone_view_recovery_creates_and_reclaims_pathfinding_controller() -> None:
    controller = 假视角控制器()
    stopped = []
    controller.停止 = lambda: stopped.append(True)
    angles = iter([350.0, 0.0])
    locator = SimpleNamespace(读取状态=lambda: (0, 0, next(angles)))
    now = [0.0]
    runner = 路线动作执行器(
        假输入(),
        定位器=locator,
        视角控制器工厂=lambda *_args, **_kwargs: controller,
        时钟=lambda: now[0],
        睡眠函数=lambda seconds: now.__setitem__(0, now[0] + seconds),
    )

    assert runner.恢复视角(0.0)
    assert controller.角度差记录 == [10.0, 0.0]
    assert stopped == [True]


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
            [{"中心X": 100, "中心Y": 100, "置信度": 0.9, "类别名称": "医疗包"}],
            [{"中心X": 100, "中心Y": 100, "置信度": 0.9, "类别名称": "医疗包"}],
            [{"中心X": 100, "中心Y": 100, "置信度": 0.9, "类别名称": "医疗包"}],
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


def test_yolo_keeps_adjusting_while_w_is_held() -> None:
    记录 = []
    控制器列表 = []

    class 跟随输入(假输入):
        def 键盘按下(self, key):
            记录.append(("down", key))
            super().键盘按下(key)

    class 跟随控制器(假YOLO对准控制器):
        pass

    def 创建控制器(input_module, **kwargs):
        控制器 = 跟随控制器(input_module, 记录, **kwargs)
        控制器列表.append(控制器)
        return 控制器

    targets = iter(
        [
            [{"中心X": 100, "中心Y": 100, "置信度": 0.9, "类别名称": "医疗包"}],
            [{"中心X": 100, "中心Y": 100, "置信度": 0.9, "类别名称": "医疗包"}],
            [{"中心X": 100, "中心Y": 100, "置信度": 0.9, "类别名称": "医疗包"}],
            [{"中心X": 130, "中心Y": 90, "置信度": 0.9, "类别名称": "医疗包"}],
        ]
    )
    now = [0.0]
    输入 = 跟随输入()
    runner = 路线动作执行器(
        输入,
        yolo检测器=SimpleNamespace(检测一次=lambda *_args: next(targets)),
        获取检测区域=lambda: (0, 0, 200, 200, 100, 100),
        YOLO对准控制器工厂=创建控制器,
        时钟=lambda: now[0],
        睡眠函数=lambda seconds: now.__setitem__(0, now[0] + seconds),
    )
    action = 路线动作(
        "yolo_interact",
        {
            "timeout_ms": 100,
            "tolerance_px": 12,
            "initial_f_ms": 1,
            "initial_wait_ms": 0,
            "repeat_f_ms": 1,
            "w_duration_ms": 80,
            "f_count": 1,
            "f_interval_ms": 1,
        },
    )

    assert runner.执行动作(action)
    assert len(控制器列表) == 2
    assert ("aim", 30.0, -10.0) in 记录
    assert 记录.index(("down", "w")) < 记录.index(("aim", 30.0, -10.0))
    assert 记录[-1] == ("aim_stop",)


def test_yolo_follow_detection_failure_does_not_abort_w_action() -> None:
    记录 = []
    检测次数 = [0]
    now = [0.0]

    def 检测一次(*_args):
        检测次数[0] += 1
        if 检测次数[0] <= 3:
            return [{"中心X": 100, "中心Y": 100, "置信度": 0.9, "类别名称": "医疗包"}]
        raise RuntimeError("跟随检测失败")

    日志 = []
    runner = 路线动作执行器(
        假输入(),
        yolo检测器=SimpleNamespace(检测一次=检测一次),
        获取检测区域=lambda: (0, 0, 200, 200, 100, 100),
        YOLO对准控制器工厂=lambda input_module, **kwargs: 假YOLO对准控制器(
            input_module, 记录, **kwargs
        ),
        日志函数=lambda event, **fields: 日志.append((event, fields)),
        时钟=lambda: now[0],
        睡眠函数=lambda seconds: now.__setitem__(0, now[0] + seconds),
    )
    action = 路线动作(
        "yolo_interact",
        {
            "timeout_ms": 100,
            "tolerance_px": 12,
            "initial_f_ms": 1,
            "initial_wait_ms": 0,
            "repeat_f_ms": 1,
            "w_duration_ms": 80,
            "f_count": 1,
            "f_interval_ms": 1,
        },
    )

    assert runner.执行动作(action)
    assert any(event == "yolo_follow_failed" for event, _fields in 日志)
    assert ("down", "w") in runner.输入模块.calls
    assert ("up", "w") in runner.输入模块.calls


def test_yolo_applies_vertical_target_offset_to_initial_and_follow_aim() -> None:
    记录 = []
    targets = iter(
        [
            [{"中心X": 100, "中心Y": 80, "置信度": 0.9, "类别名称": "医疗包"}],
            [{"中心X": 100, "中心Y": 80, "置信度": 0.9, "类别名称": "医疗包"}],
            [{"中心X": 100, "中心Y": 80, "置信度": 0.9, "类别名称": "医疗包"}],
            [{"中心X": 100, "中心Y": 100, "置信度": 0.9, "类别名称": "医疗包"}],
        ]
    )
    now = [0.0]
    runner = 路线动作执行器(
        假输入(),
        yolo检测器=SimpleNamespace(检测一次=lambda *_args: next(targets)),
        获取检测区域=lambda: (0, 0, 200, 200, 100, 100),
        YOLO对准控制器工厂=lambda input_module, **kwargs: 假YOLO对准控制器(
            input_module, 记录, **kwargs
        ),
        时钟=lambda: now[0],
        睡眠函数=lambda seconds: now.__setitem__(0, now[0] + seconds),
    )
    action = 路线动作(
        "yolo_interact",
        {
            "timeout_ms": 100,
            "tolerance_px": 12,
            "target_y_offset_px": 20,
            "initial_f_ms": 1,
            "initial_wait_ms": 0,
            "repeat_f_ms": 1,
            "w_duration_ms": 1,
            "f_count": 1,
            "f_interval_ms": 1,
        },
    )

    assert runner.执行动作(action)
    assert ("aim", 0.0, 20.0) in 记录


class 假持续YOLO服务:
    def __init__(self):
        self.calls = []

    def 开启(self, params):
        self.calls.append(("on", dict(params)))
        return True

    def 关闭(self):
        self.calls.append(("off",))

    def 暂停(self):
        self.calls.append(("pause",))
        return {"confidence": 0.6}

    def 恢复(self, params):
        self.calls.append(("resume", dict(params)))
        return True


def test_persistent_yolo_aim_on_restores_view_and_off_stops_service() -> None:
    service = 假持续YOLO服务()
    locator = SimpleNamespace(读取状态=lambda: (0, 0, 90.0))
    runner = 路线动作执行器(假输入(), 定位器=locator, 持续YOLO服务=service)
    on = 路线动作(
        "yolo_aim_on",
        {"angle": 90.0, "confidence": 0.5, "tolerance_px": 12, "target_y_offset_px": 20},
    )

    assert runner.执行动作(on)
    assert runner.执行动作(路线动作("yolo_aim_off", {}))
    assert service.calls == [
        ("on", {"angle": 90.0, "confidence": 0.5, "tolerance_px": 12, "target_y_offset_px": 20}),
        ("off",),
    ]


def test_old_yolo_interaction_pauses_and_resumes_persistent_aim() -> None:
    service = 假持续YOLO服务()
    now = [0.0]
    detector = SimpleNamespace(
        检测一次=lambda *_args: [
            {"中心X": 100, "中心Y": 100, "置信度": 0.9, "类别名称": "医疗包"}
        ]
    )
    runner = 路线动作执行器(
        假输入(),
        yolo检测器=detector,
        获取检测区域=lambda: (0, 0, 200, 200, 100, 100),
        持续YOLO服务=service,
        时钟=lambda: now[0],
        睡眠函数=lambda seconds: now.__setitem__(0, now[0] + seconds),
    )

    assert runner.执行动作(_YOLO动作())
    assert service.calls[0] == ("pause",)
    assert service.calls[-1] == ("resume", {"confidence": 0.6})


def test_yolo_aim_once_requires_stable_frames_then_exits_without_f_or_w() -> None:
    service = 假持续YOLO服务()
    now = [0.0]
    statuses = []
    detector = SimpleNamespace(
        执行器="CPU",
        最近截图=None,
        检测一次=lambda *_args: [
            {"中心X": 100, "中心Y": 80, "置信度": 0.9, "类别名称": "航空箱"}
        ],
    )
    runner = 路线动作执行器(
        假输入(),
        yolo检测器=detector,
        获取检测区域=lambda: (0, 0, 200, 200, 100, 100),
        持续YOLO服务=service,
        状态函数=lambda event, **fields: statuses.append((event, fields)),
        时钟=lambda: now[0],
        睡眠函数=lambda seconds: now.__setitem__(0, now[0] + seconds),
    )
    action = 路线动作(
        "yolo_aim_once",
        {
            "angle": 90.0,
            "confidence": 0.5,
            "timeout_ms": 1000,
            "tolerance_px": 12,
            "target_y_offset_px": 20,
            "stable_frame_count": 3,
            "target_class": "航空箱",
            "scan_enabled": False,
            "scan_step_degrees": 8.0,
            "scan_attempts": 4,
        },
    )

    assert runner.执行动作(action)
    assert not any(call in {("down", "f"), ("down", "w")} for call in runner.输入模块.calls)
    assert service.calls == [("pause",), ("resume", {"confidence": 0.6})]
    assert [fields["稳定帧"] for event, fields in statuses if event == "adjust"][-3:] == [1, 2, 3]


def test_yolo_aim_once_without_restore_uses_runtime_view_for_scan_and_reset() -> None:
    now = [0.0]
    restore_calls = []
    aim_records = []
    detector = SimpleNamespace(
        执行器="CPU",
        最近截图=None,
        检测一次=lambda *_args: [],
    )
    runner = 路线动作执行器(
        假输入(),
        定位器=SimpleNamespace(读取状态=lambda: (0, 0, 120.0)),
        yolo检测器=detector,
        获取检测区域=lambda: (0, 0, 200, 200, 100, 100),
        YOLO对准控制器工厂=lambda input_module, **kwargs: 假YOLO对准控制器(
            input_module, aim_records, **kwargs
        ),
        时钟=lambda: now[0],
        睡眠函数=lambda seconds: now.__setitem__(0, now[0] + seconds),
    )
    runner.恢复视角 = lambda angle: restore_calls.append(angle) or True
    action = 路线动作(
        "yolo_aim_once",
        {
            "angle": 90.0,
            "restore_view": False,
            "timeout_ms": 1200,
            "scan_enabled": True,
            "scan_step_degrees": 8.0,
            "scan_attempts": 1,
        },
    )

    assert not runner.执行动作(action)
    assert restore_calls == pytest.approx([128.0, 120.0])


def test_old_yolo_aim_once_defaults_to_restoring_recorded_view() -> None:
    now = [0.0]
    restore_calls = []
    aim_records = []
    detector = SimpleNamespace(
        执行器="CPU",
        最近截图=None,
        检测一次=lambda *_args: [
            {"中心X": 100, "中心Y": 100, "置信度": 0.9, "类别名称": "航空箱"}
        ],
    )
    runner = 路线动作执行器(
        假输入(),
        定位器=SimpleNamespace(读取状态=lambda: (0, 0, 120.0)),
        yolo检测器=detector,
        获取检测区域=lambda: (0, 0, 200, 200, 100, 100),
        YOLO对准控制器工厂=lambda input_module, **kwargs: 假YOLO对准控制器(
            input_module, aim_records, **kwargs
        ),
        时钟=lambda: now[0],
        睡眠函数=lambda seconds: now.__setitem__(0, now[0] + seconds),
    )
    runner.恢复视角 = lambda angle: restore_calls.append(angle) or True
    action = 路线动作(
        "yolo_aim_once",
        {"angle": 90.0, "timeout_ms": 1000, "stable_frame_count": 1, "scan_enabled": False},
    )

    assert runner.执行动作(action)
    assert restore_calls == [90.0]


def test_image_wait_and_click_actions_use_match_center_and_offsets() -> None:
    class 可点击输入(假输入):
        def 鼠标点击(self, x, y, 按键="左键"):
            self.calls.append(("click", x, y, 按键))

    class 假匹配器:
        def __init__(self):
            self.results = iter([None, {"中心X": 100, "中心Y": 200, "置信度": 0.9}])

        def 匹配一次(self, _path, _confidence):
            return next(self.results)

    now = [0.0]
    inp = 可点击输入()
    runner = 路线动作执行器(
        inp,
        图像匹配器=假匹配器(),
        时钟=lambda: now[0],
        睡眠函数=lambda seconds: now.__setitem__(0, now[0] + seconds),
    )
    action = 路线动作(
        "image_click",
        {
            "template_path": "images/箱子.png",
            "confidence": 0.85,
            "timeout_ms": 1000,
            "interval_ms": 100,
            "click_offset_x": 5,
            "click_offset_y": -3,
        },
    )

    assert runner.执行动作(action)
    assert inp.calls == [("click", 105, 197, "左键")]


def test_wait_for_image_disappear_succeeds_only_after_match_is_gone() -> None:
    class 假匹配器:
        def __init__(self):
            self.results = iter([{"中心X": 1, "中心Y": 1}, None])

        def 匹配一次(self, _path, _confidence):
            return next(self.results)

    now = [0.0]
    runner = 路线动作执行器(
        假输入(),
        图像匹配器=假匹配器(),
        时钟=lambda: now[0],
        睡眠函数=lambda seconds: now.__setitem__(0, now[0] + seconds),
    )
    action = 路线动作(
        "image_wait_disappear",
        {
            "template_path": "images/箱子.png",
            "confidence": 0.85,
            "timeout_ms": 1000,
            "interval_ms": 100,
        },
    )

    assert runner.执行动作(action)
    assert now[0] == pytest.approx(0.1)
