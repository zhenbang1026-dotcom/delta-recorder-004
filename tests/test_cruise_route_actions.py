from __future__ import annotations

import threading
from pathlib import Path

import 巡航脚本 as cruise
from 路线动作 import 路线动作, 路线点, 写入路线文件


def test_escape_requires_two_distinct_presses_within_500ms() -> None:
    detector = cruise.Esc双击检测器(0.5)

    assert not detector.更新(True, 0.0)
    assert not detector.更新(True, 0.1)
    assert not detector.更新(False, 0.2)
    assert detector.更新(True, 0.49)


def test_escape_single_press_expires_and_starts_a_new_pair() -> None:
    detector = cruise.Esc双击检测器(0.5)

    assert not detector.更新(True, 0.0)
    assert not detector.更新(False, 0.1)
    assert not detector.更新(False, 0.51)
    assert not detector.更新(True, 0.6)
    assert not detector.更新(False, 0.7)
    assert detector.更新(True, 1.0)


def test_escape_stop_event_is_set_only_after_double_press(monkeypatch) -> None:
    pressed = [True]
    now = [0.0]
    stop_event = threading.Event()
    monkeypatch.setattr(cruise, "_esc双击检测器", cruise.Esc双击检测器(0.5))
    monkeypatch.setattr(cruise.win32_input, "按键是否按下", lambda _key: pressed[0])
    monkeypatch.setattr(cruise.time, "monotonic", lambda: now[0])

    assert not cruise.处理esc紧急停止(stop_event)
    assert not stop_event.is_set()
    pressed[0] = False
    now[0] = 0.1
    assert not cruise.处理esc紧急停止(stop_event)
    pressed[0] = True
    now[0] = 0.4
    assert cruise.处理esc紧急停止(stop_event)
    assert stop_event.is_set()


def test_jsonl_route_keeps_actions_for_cruise(tmp_path: Path) -> None:
    path = tmp_path / "route.jsonl"
    comment = 路线动作("comment", {"text": "到达终点"})
    写入路线文件(path, [路线点(10, 20, 30.0, False, (comment,))])

    points = cruise.读取路径(str(path))

    assert len(points) == 1
    assert points[0].actions == (comment,)


def test_final_waypoint_actions_run_before_executor_stops(monkeypatch) -> None:
    comment = 路线动作("comment", {"text": "终点动作"})
    events: list[object] = []

    class Locator:
        def 读取状态(self):
            return 10, 20, 30.0

    class Executor:
        def 执行(self, action):
            events.append(("move", action.类型))

        def 执行路线动作(self, actions):
            events.append(("actions", tuple(actions)))

        def 停止(self):
            events.append("stop")

    monkeypatch.setattr(cruise, "处理esc紧急停止", lambda _event=None: False)
    monkeypatch.setattr(cruise, "动作终点停稳秒数", 0.0)
    monkeypatch.setattr(cruise, "动作终点采样间隔秒数", 0.0)
    controller = cruise.巡航控制器(
        路径点列表=[cruise.路径点(10, 20, 30.0, False, (comment,))],
        定位器=Locator(),
        执行器=Executor(),
        到点阈值=3,
        参数=cruise.普通模式参数(),
        循环间隔=0.0,
    )

    controller.运行()

    assert events == [
        ("move", "切换下一个点"),
        ("actions", (comment,)),
        "stop",
    ]


def test_action_waypoint_uses_five_sample_median_before_actions(monkeypatch) -> None:
    comment = 路线动作("comment", {"text": "测试中位数"})
    states = iter(
        [
            (10, 20, 30.0),
            (9, 21, 30.0),
            (10, 20, 30.0),
            (100, 200, 30.0),
            (11, 19, 30.0),
            (10, 20, 30.0),
            (10, 20, 30.0),
        ]
    )
    events: list[object] = []

    class Locator:
        def 读取状态(self):
            return next(states)

    class Executor:
        def 执行(self, action):
            events.append(("move", action.类型))

        def 执行路线动作(self, actions):
            events.append(("actions", tuple(actions)))

        def 停止(self):
            events.append("stop")

    monkeypatch.setattr(cruise, "处理esc紧急停止", lambda _event=None: False)
    monkeypatch.setattr(cruise, "动作终点停稳秒数", 0.0)
    monkeypatch.setattr(cruise, "动作终点采样间隔秒数", 0.0)
    controller = cruise.巡航控制器(
        路径点列表=[cruise.路径点(10, 20, 30.0, False, (comment,))],
        定位器=Locator(),
        执行器=Executor(),
        到点阈值=3,
        参数=cruise.普通模式参数(),
        循环间隔=0.0,
    )

    controller.运行()

    assert controller._最近动作终点坐标 == (10, 20)
    assert events[-2:] == [("actions", (comment,)), "stop"]


def test_action_waypoint_limits_low_speed_corrections_and_still_runs_actions(
    monkeypatch,
) -> None:
    comment = 路线动作("comment", {"text": "补正失败仍继续"})
    events: list[object] = []

    class Locator:
        def 读取状态(self):
            return 12, 20, 0.0

    class Executor:
        def 执行(self, action):
            events.append(("move", action.类型))

        def 执行路线动作(self, actions):
            events.append(("actions", tuple(actions)))

        def 停止(self):
            events.append("stop")

    monkeypatch.setattr(cruise, "处理esc紧急停止", lambda _event=None: False)
    monkeypatch.setattr(cruise, "动作终点停稳秒数", 0.0)
    monkeypatch.setattr(cruise, "动作终点采样间隔秒数", 0.0)
    monkeypatch.setattr(cruise, "动作终点转向等待秒数", 0.0)
    controller = cruise.巡航控制器(
        路径点列表=[cruise.路径点(10, 20, 0.0, False, (comment,))],
        定位器=Locator(),
        执行器=Executor(),
        到点阈值=3,
        参数=cruise.普通模式参数(),
        循环间隔=0.0,
    )

    controller.运行()

    correction_count = events.count(("move", "终点低速补正"))
    assert correction_count == 3
    assert ("actions", (comment,)) in events
