from __future__ import annotations

import inspect
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

import 主界面 as main_ui
import 动作编辑器 as editor
import 自动录制坐标工具 as recorder_module
import 巡航脚本 as cruise
from 路线动作 import 路线动作, 路线点, 读取路线文件, 写入路线文件


def test_precise_point_roundtrip_and_normal_point_omits_false(tmp_path: Path) -> None:
    path = tmp_path / "route.jsonl"
    normal = 路线点(1, 2, 3.0, True)
    precise = 路线点(4, 5, 6.0, True, (), True)

    写入路线文件(path, [normal, precise])
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]

    assert "precise" not in records[1]
    assert records[2]["precise"] is True
    assert 读取路线文件(path) == [normal, precise]


def test_old_route_defaults_to_normal_and_rejects_non_boolean_precise(tmp_path: Path) -> None:
    old = tmp_path / "old.jsonl"
    old.write_text(
        '{"version":2,"type":"route"}\n'
        '{"type":"point","x":1,"y":2,"auto":true,"actions":[]}\n',
        encoding="utf-8",
    )

    assert 读取路线文件(old)[0].精准点 is False

    broken = tmp_path / "broken.jsonl"
    broken.write_text(
        '{"version":2,"type":"route"}\n'
        '{"type":"point","x":1,"y":2,"precise":"yes","actions":[]}\n',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="路线点格式错误"):
        读取路线文件(broken)


def test_replacing_actions_preserves_precise_flag() -> None:
    point = 路线点(1, 2, 3.0, True, (), True)

    changed = point.替换动作((路线动作("comment", {"text": "门口"}),))

    assert changed.精准点 is True


def test_cruise_keeps_precise_point_during_thinning(tmp_path: Path) -> None:
    path = tmp_path / "route.jsonl"
    points = [
        路线点(0, 0, 0.0, True),
        路线点(2, 0, 0.0, True, (), True),
        路线点(4, 0, 0.0, True),
        路线点(20, 0, 0.0, True),
    ]
    写入路线文件(path, points)

    loaded = cruise.读取路径(str(path), 自动路线点距=6)

    assert [(point.x, point.精准点) for point in loaded] == [
        (0, False),
        (2, True),
        (20, False),
    ]


def test_record_double_click_requires_two_distinct_presses_within_500ms() -> None:
    detector = main_ui.录制双击检测器(0.5)

    assert not detector.更新(True, 0.0)
    assert not detector.更新(True, 0.1)
    assert not detector.更新(False, 0.2)
    assert detector.更新(True, 0.49)


def test_record_double_click_timeout_starts_a_new_pair() -> None:
    detector = main_ui.录制双击检测器(0.5)

    assert not detector.更新(True, 0.0)
    assert not detector.更新(False, 0.1)
    assert not detector.更新(False, 0.51)
    assert not detector.更新(True, 0.6)
    assert not detector.更新(False, 0.7)
    assert detector.更新(True, 1.0)


def test_recorder_force_record_can_replace_last_coordinate() -> None:
    recorder = recorder_module.自动坐标录制器(最小记录距离=3)

    recorder.强制记录(10, 20)
    recorder.强制记录(11, 21, 替换最后=True)

    assert recorder.记录列表 == [(11, 21)]
    assert recorder.上一记录点 == (11, 21)


def test_precise_record_replaces_near_plain_point_and_appends_after_action() -> None:
    recorder = recorder_module.自动坐标录制器(最小记录距离=3)
    recorder.强制记录(10, 20)
    points = [路线点(10, 20, 1.0, True)]

    result = main_ui.记录或更新精准点(
        points,
        recorder,
        SimpleNamespace(x=11, y=20, angle=45.0),
    )

    assert result == "更新"
    assert points == [路线点(11, 20, 45.0, True, (), True)]
    assert recorder.记录列表 == [(11, 20)]
    assert recorder.上一记录点 == (11, 20)

    points[-1] = points[-1].替换动作((路线动作("comment", {"text": "动作"}),))
    result = main_ui.记录或更新精准点(
        points,
        recorder,
        SimpleNamespace(x=12, y=20, angle=50.0),
    )

    assert result == "新增"
    assert len(points) == 2
    assert points[-1].精准点 is True
    assert recorder.记录列表[-1] == (12, 20)


def test_precise_record_appends_after_distant_plain_point() -> None:
    recorder = recorder_module.自动坐标录制器(最小记录距离=3)
    recorder.强制记录(10, 20)
    points = [路线点(10, 20, 1.0, True)]

    result = main_ui.记录或更新精准点(
        points,
        recorder,
        SimpleNamespace(x=14, y=20, angle=45.0),
    )

    assert result == "新增"
    assert points == [
        路线点(10, 20, 1.0, True),
        路线点(14, 20, 45.0, True, (), True),
    ]


class ValueVar:
    def __init__(self, value="") -> None:
        self.value = value

    def get(self):
        return self.value

    def set(self, value) -> None:
        self.value = value


@pytest.mark.parametrize(
    ("recording", "paused"),
    [(False, False), (True, True)],
)
def test_precise_record_is_ignored_outside_active_recording(recording, paused) -> None:
    app = object.__new__(main_ui.合并主界面)
    app.recording = recording
    app.recording_paused = paused
    app.current_state = SimpleNamespace(x=10, y=20, angle=30.0)
    app._recorded_route_points = []
    app.录制器 = recorder_module.自动坐标录制器()

    assert app._记录精准点() is False
    assert app._recorded_route_points == []


def test_precise_record_updates_ui_without_popup_or_focus(monkeypatch) -> None:
    app = object.__new__(main_ui.合并主界面)
    app.recording = True
    app.recording_paused = False
    app.current_state = SimpleNamespace(x=10, y=20, angle=30.0)
    app._recorded_route_points = []
    app.录制器 = recorder_module.自动坐标录制器()
    app.status_var = ValueVar()
    app.record_count_var = ValueVar()
    app._log_fn = None
    refreshed = []
    previews = []
    beeps = []
    app._refresh_points_text = lambda: refreshed.append(True)
    app._draw_preview = previews.append
    monkeypatch.setattr(main_ui.录制模块, "写日志", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(main_ui.winsound, "MessageBeep", lambda *_args: beeps.append(True))
    monkeypatch.setattr(
        main_ui.messagebox,
        "showinfo",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("不得弹窗")),
    )

    assert app._记录精准点() is True
    assert app._recorded_route_points == [路线点(10, 20, 30.0, True, (), True)]
    assert "10,20" in app.status_var.get()
    assert refreshed == [True]
    assert previews == [app.current_state]
    assert beeps == [True]


def test_precise_waypoint_without_actions_still_aligns_before_finish(monkeypatch) -> None:
    events = []

    class Locator:
        def 读取状态(self):
            return 10, 20, 31.5

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
        路径点列表=[cruise.路径点(10, 20, 30.0, True, (), True)],
        定位器=Locator(),
        执行器=Executor(),
        到点阈值=3,
        参数=cruise.普通模式参数(),
        循环间隔=0.0,
    )

    controller.运行()

    assert events == [
        ("move", "切换下一个点"),
        "stop",
    ]


def test_precise_waypoint_runs_actions_after_successful_alignment(monkeypatch) -> None:
    comment = 路线动作("comment", {"text": "开门"})
    events = []

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
        路径点列表=[cruise.路径点(10, 20, 30.0, True, (comment,), True)],
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


def test_precise_waypoint_failure_stops_route_and_skips_actions(monkeypatch) -> None:
    comment = 路线动作("comment", {"text": "不应执行"})
    events = []

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
        路径点列表=[cruise.路径点(10, 20, 0.0, True, (comment,), True)],
        定位器=Locator(),
        执行器=Executor(),
        到点阈值=3,
        参数=cruise.普通模式参数(),
        循环间隔=0.0,
    )

    with pytest.raises(cruise.精准点到达失败, match="目标.*10,20.*最终.*12,20"):
        controller.运行()

    assert events.count(("move", "终点低速补正")) == 3
    assert not any(event[0] == "actions" for event in events if isinstance(event, tuple))
    assert events[-1] == "stop"


class SelectedList:
    def curselection(self):
        return (0,)


def test_route_editor_toggles_precise_without_changing_actions() -> None:
    comment = 路线动作("comment", {"text": "门口"})
    window = object.__new__(editor.路线编辑窗口)
    window.points = [路线点(1, 2, 3.0, True, (comment,))]
    window.listbox = SelectedList()
    refreshed = []
    window._刷新 = refreshed.append

    window._切换精准状态()

    assert window.points[0] == 路线点(1, 2, 3.0, True, (comment,), True)
    assert refreshed == [0]


class CapturingList:
    def __init__(self) -> None:
        self.rows = []

    def delete(self, *_args) -> None:
        self.rows.clear()

    def insert(self, _position, value) -> None:
        self.rows.append(value)

    def selection_set(self, _index) -> None:
        pass

    def see(self, _index) -> None:
        pass


def test_route_editor_labels_normal_and_precise_points() -> None:
    window = object.__new__(editor.路线编辑窗口)
    window.points = [
        路线点(1, 2, 3.0, True),
        路线点(4, 5, 6.0, True, (), True),
    ]
    window.listbox = CapturingList()

    window._刷新()

    assert "[普通]" in window.listbox.rows[0]
    assert "[精准]" in window.listbox.rows[1]


class CapturingText:
    def __init__(self) -> None:
        self.content = ""

    def delete(self, *_args) -> None:
        self.content = ""

    def insert(self, _position, value) -> None:
        self.content = value


def test_recorded_point_list_labels_precise_points() -> None:
    app = object.__new__(main_ui.合并主界面)
    app._recorded_route_points = [
        路线点(1, 2, 3.0, True),
        路线点(4, 5, 6.0, True, (), True),
    ]
    app.points_text = CapturingText()

    app._refresh_points_text()

    assert "4,5  [精准]" in app.points_text.content


def test_precise_points_are_red_in_recording_preview() -> None:
    app = object.__new__(main_ui.合并主界面)
    app.识别器 = SimpleNamespace(
        地图匹配器=SimpleNamespace(big_map=np.zeros((30, 30, 3), dtype=np.uint8))
    )
    app.录制器 = recorder_module.自动坐标录制器()
    app.录制器.强制记录(10, 10)
    app._recorded_route_points = [路线点(10, 10, 0.0, True, (), True)]
    previews = []
    app._set_preview = previews.append

    app._draw_preview(None)

    assert tuple(previews[0][10, 10]) == (0, 0, 255)


def test_recording_ui_explains_double_e_precise_point_shortcut() -> None:
    source = inspect.getsource(main_ui.合并主界面._build_ui)

    assert "双击 E 添加精准点" in source
