from __future__ import annotations

import inspect
import queue
import threading

import pytest

import 主界面 as main_ui


class _变量:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class _按钮:
    def __init__(self):
        self.state = "normal"

    def config(self, **kwargs):
        self.state = kwargs.get("state", self.state)


class _窗口:
    def __init__(self):
        self.calls = []

    def iconify(self):
        self.calls.append(("iconify",))

    def deiconify(self):
        self.calls.append(("deiconify",))

    def lift(self):
        self.calls.append(("lift",))

    def after(self, delay, callback):
        self.calls.append(("after", delay, callback))
        return "after-1"


class _线程:
    instances = []

    def __init__(self, target, daemon):
        self.target = target
        self.daemon = daemon
        self.started = False
        self.instances.append(self)

    def start(self):
        self.started = True

    def is_alive(self):
        return self.started


def test_debug_look_action_uses_fixed_down_and_custom_up_values() -> None:
    down = main_ui.构建低头抬头测试动作("down", -3000, 450, 7)
    up = main_ui.构建低头抬头测试动作("up", -3200, 450, 7)

    assert down.参数 == {
        "direction": "down",
        "y_delta": 8000,
        "duration_ms": 450,
        "x_random": 7,
    }
    assert up.参数 == {
        "direction": "up",
        "y_delta": -3200,
        "duration_ms": 450,
        "x_random": 7,
    }


@pytest.mark.parametrize(
    ("direction", "up_y", "duration", "x_random"),
    [("up", 3000, 300, 4), ("up", -3000, 0, 4), ("down", -3000, 300, -1)],
)
def test_debug_look_action_rejects_invalid_values(direction, up_y, duration, x_random) -> None:
    with pytest.raises(ValueError):
        main_ui.构建低头抬头测试动作(direction, up_y, duration, x_random)


def test_main_ui_contains_standalone_look_debug_controls() -> None:
    init_source = inspect.getsource(main_ui.合并主界面.__init__)
    ui_source = inspect.getsource(main_ui.合并主界面._build_ui)

    assert 'tk.StringVar(value="-3000")' in init_source
    assert 'tk.StringVar(value="300")' in init_source
    assert 'tk.StringVar(value="4")' in init_source
    assert 'text="低头 / 抬头独立测试"' in ui_source
    assert 'text="测试低头 (+8000)"' in ui_source
    assert 'text="测试抬头"' in ui_source


def test_debug_look_minimizes_then_executes_in_background(monkeypatch) -> None:
    _线程.instances.clear()
    monkeypatch.setattr(main_ui.threading, "Thread", _线程)
    executed = []

    class 假执行器:
        def __init__(self, input_module, **kwargs):
            self.input_module = input_module
            self.kwargs = kwargs

        def 执行动作(self, action):
            executed.append(action)
            return True

    monkeypatch.setattr(main_ui, "路线动作执行器", 假执行器)
    app = object.__new__(main_ui.合并主界面)
    app.root = _窗口()
    app.recording = False
    app.cruising = False
    app.look_up_y_var = _变量("-3000")
    app.look_duration_var = _变量("300")
    app.look_x_random_var = _变量("4")
    app.btn_look_down_test = _按钮()
    app.btn_look_up_test = _按钮()
    app.status_var = _变量("")
    app._look_test_thread = None
    app._look_test_start_after = None
    app._look_test_stop = threading.Event()
    app._queue = queue.Queue()

    app._start_look_test("up")

    assert app.root.calls[0] == ("iconify",)
    delayed = next(call for call in app.root.calls if call[:2] == ("after", 1000))
    assert executed == []
    delayed[2]()
    assert len(_线程.instances) == 1
    assert _线程.instances[0].started is True
    _线程.instances[0].target()
    assert executed[0].参数["y_delta"] == -3000
    assert app._queue.get_nowait()[0] == "look_test_done"


def test_debug_look_completion_restores_buttons_and_window() -> None:
    app = object.__new__(main_ui.合并主界面)
    app.root = _窗口()
    app._queue = queue.Queue()
    app._queue.put(("look_test_done", "抬头测试完成"))
    app._look_test_thread = object()
    app.btn_look_down_test = _按钮()
    app.btn_look_up_test = _按钮()
    app.btn_look_down_test.state = "disabled"
    app.btn_look_up_test.state = "disabled"
    app.status_var = _变量("")

    app._drain_queue()

    assert app._look_test_thread is None
    assert app.btn_look_down_test.state == "normal"
    assert app.btn_look_up_test.state == "normal"
    assert app.status_var.get() == "抬头测试完成"
    assert ("deiconify",) in app.root.calls
    assert ("lift",) in app.root.calls
