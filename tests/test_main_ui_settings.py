from __future__ import annotations

import inspect
import json
import queue
import threading
from pathlib import Path
from typing import Any

import pytest

import 主界面 as main_ui


class _Var:
    def __init__(self, value: Any) -> None:
        self.value = value

    def get(self) -> Any:
        return self.value

    def set(self, value: Any) -> None:
        self.value = value


class _Button:
    def __init__(self) -> None:
        self.options: dict[str, Any] = {}

    def config(self, **kwargs: Any) -> None:
        self.options.update(kwargs)


class _Root:
    def __init__(self) -> None:
        self.calls: list[tuple[Any, ...]] = []

    def iconify(self) -> None:
        self.calls.append(("iconify",))

    def deiconify(self) -> None:
        self.calls.append(("deiconify",))

    def lift(self) -> None:
        self.calls.append(("lift",))

    def after(self, delay: int, callback: Any) -> str:
        self.calls.append(("after", delay, callback))
        return f"after-{len(self.calls)}"

    def after_cancel(self, after_id: str) -> None:
        self.calls.append(("after_cancel", after_id))

    def destroy(self) -> None:
        self.calls.append(("destroy",))


class _Thread:
    instances: list["_Thread"] = []

    def __init__(self, target: Any, daemon: bool) -> None:
        self.target = target
        self.daemon = daemon
        self.started = False
        self.instances.append(self)

    def start(self) -> None:
        self.started = True


def _settings_app() -> main_ui.合并主界面:
    app = object.__new__(main_ui.合并主界面)
    app.angle_mode_var = _Var("legacy")
    app.speed_var = _Var(1.5)
    app.speed_label_var = _Var("1.5x")
    app.arrival_var = _Var(3)
    app.precise_var = _Var(False)
    app.route_var = _Var("")
    return app


def _button_app() -> main_ui.合并主界面:
    app = _settings_app()
    app.root = _Root()
    app.detecting = False
    app.recording = False
    app.cruising = False
    app._detect_thread = None
    app._cruise_thread = None
    app.status_var = _Var("")
    app.btn_detect_start = _Button()
    app.btn_detect_stop = _Button()
    app.btn_rec_start = _Button()
    app.btn_rec_stop = _Button()
    app.btn_cruise_start = _Button()
    app.btn_cruise_stop = _Button()
    app._set_angle_radios = lambda _enabled: None
    return app


def test用户配置位于项目根目录() -> None:
    assert main_ui.USER_SETTINGS_PATH == main_ui.ROOT / "用户设置.json"


def test启动时先加载所选路线再用当前路线列表校验() -> None:
    init_source = inspect.getsource(main_ui.合并主界面.__init__)

    assert init_source.index("self._load_settings()") < init_source.index(
        "self._refresh_route_list()"
    )


def test没有可用路线时清空已失效的保存路径(monkeypatch: pytest.MonkeyPatch) -> None:
    app = _settings_app()
    app.route_combo = {}
    app.route_var.set(r"D:\deleted\missing.txt")
    monkeypatch.setattr(main_ui, "_list_route_files", lambda: [])

    app._refresh_route_list()

    assert app.route_var.get() == ""


def test有效配置可保存并完整恢复(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    settings_path = tmp_path / "用户设置.json"
    monkeypatch.setattr(main_ui, "USER_SETTINGS_PATH", settings_path)
    app = _settings_app()
    app.angle_mode_var.set("text")
    app.speed_var.set(2.4)
    app.arrival_var.set(7)
    app.precise_var.set(True)
    app.route_var.set(r"D:\routes\demo.txt")

    app._save_settings()

    assert json.loads(settings_path.read_text(encoding="utf-8")) == {
        "角度模式": "text",
        "视角速度倍率": 2.4,
        "到点阈值": 7,
        "精准模式": True,
        "所选路线": r"D:\routes\demo.txt",
    }

    restored = _settings_app()
    restored._load_settings()
    assert restored.angle_mode_var.get() == "text"
    assert restored.speed_var.get() == 2.4
    assert restored.speed_label_var.get() == "2.4x"
    assert restored.arrival_var.get() == 7
    assert restored.precise_var.get() is True
    assert restored.route_var.get() == r"D:\routes\demo.txt"


@pytest.mark.parametrize(
    "content",
    [
        "{broken json",
        json.dumps(
            {
                "角度模式": "fusion",
                "视角速度倍率": 3.1,
                "到点阈值": 0,
                "精准模式": "yes",
                "所选路线": 123,
            },
            ensure_ascii=False,
        ),
    ],
)
def test坏json或越界值安全回退默认值(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    content: str,
) -> None:
    settings_path = tmp_path / "用户设置.json"
    settings_path.write_text(content, encoding="utf-8")
    monkeypatch.setattr(main_ui, "USER_SETTINGS_PATH", settings_path)
    app = _settings_app()

    app._load_settings()

    assert app.angle_mode_var.get() == "legacy"
    assert app.speed_var.get() == 1.5
    assert app.speed_label_var.get() == "1.5x"
    assert app.arrival_var.get() == 3
    assert app.precise_var.get() is False
    assert app.route_var.get() == ""


def test关闭时先保存配置再销毁窗口() -> None:
    app = _button_app()
    app.recording = False
    app.detecting = False
    app.cruising = False
    events: list[str] = []
    app._save_settings = lambda: events.append("save")
    app.root.destroy = lambda: events.append("destroy")

    app._on_close()

    assert events == ["save", "destroy"]


def test回放区倍率控件范围步长默认值并显示当前值() -> None:
    init_source = inspect.getsource(main_ui.合并主界面.__init__)
    ui_source = inspect.getsource(main_ui.合并主界面._build_ui)
    assert "tk.DoubleVar(value=1.5)" in init_source
    assert 'text="速度倍率:"' in ui_source
    assert "from_=0.5" in ui_source
    assert "to=3.0" in ui_source
    assert "resolution=0.1" in ui_source
    assert "textvariable=self.speed_label_var" in ui_source

    app = _settings_app()
    app._update_speed_label("2.36")
    assert app.speed_label_var.get() == "2.4x"


def test开始识别先最小化且三秒后才启动读取线程(monkeypatch: pytest.MonkeyPatch) -> None:
    _Thread.instances.clear()
    monkeypatch.setattr(main_ui.threading, "Thread", _Thread)
    monkeypatch.setattr(main_ui.录制模块, "创建日志记录器", lambda _name: (None, None))
    monkeypatch.setattr(main_ui.录制模块, "写日志", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(main_ui.识别模块, "当前角度模式", lambda: "legacy")
    monkeypatch.setattr(main_ui.识别模块, "当前角度模式标签", lambda: "Legacy")
    app = _button_app()
    app.detecting = False
    app.cruising = False
    app.识别器 = object()
    app._detect_stop = threading.Event()
    app._apply_angle_mode = lambda: None
    app._detect_loop = lambda: None

    app.start_detect()

    delayed = [call for call in app.root.calls if call[:2] == ("after", 3000)]
    assert app.root.calls[0] == ("iconify",)
    assert len(delayed) == 1
    assert _Thread.instances == []

    delayed[0][2]()
    assert len(_Thread.instances) == 1
    assert _Thread.instances[0].started is True


def test开始回放先最小化且延迟透传倍率(monkeypatch: pytest.MonkeyPatch) -> None:
    _Thread.instances.clear()
    monkeypatch.setattr(main_ui.threading, "Thread", _Thread)
    monkeypatch.setattr(main_ui.巡航模块, "校验路线文件", lambda route: route)
    monkeypatch.setattr(main_ui.巡航模块, "校验到点阈值", lambda _value: None)
    monkeypatch.setattr(main_ui.巡航模块, "构建开始状态文本", lambda delay: f"delay={delay}")
    monkeypatch.setattr(main_ui.巡航模块, "创建日志记录器", lambda _name: (None, None))
    monkeypatch.setattr(main_ui.识别模块, "当前角度模式标签", lambda: "Legacy")
    cruise_calls: list[dict[str, Any]] = []
    monkeypatch.setattr(
        main_ui.巡航模块,
        "巡航",
        lambda _route, **kwargs: cruise_calls.append(kwargs),
    )
    app = _button_app()
    app.detecting = False
    app.cruising = False
    app.route_var.set("route.txt")
    app.speed_var.set(2.4)
    app.巡航定位器 = object()
    app._cruise_stop = threading.Event()
    app._queue = queue.Queue()
    app._apply_angle_mode = lambda: None
    app._try_init_cruise_locator = lambda silent=False: True
    app._poll_cruise_preview = lambda: None

    app.start_cruise()

    delayed = [call for call in app.root.calls if call[:2] == ("after", 3000)]
    assert app.root.calls[0] == ("iconify",)
    assert len(delayed) == 1
    assert _Thread.instances == []

    delayed[0][2]()
    assert len(_Thread.instances) == 1
    assert _Thread.instances[0].started is True
    _Thread.instances[0].target()
    assert cruise_calls[0]["视角速度倍率"] == 2.4


def test停止识别或回放会立即恢复主窗口(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(main_ui.录制模块, "写日志", lambda *_args, **_kwargs: None)
    detect_app = _button_app()
    detect_app.recording = False
    detect_app.detecting = True
    detect_app._detect_stop = threading.Event()
    detect_app._detect_thread = None
    detect_app._log_fn = None
    detect_app.stop_detect()
    assert ("deiconify",) in detect_app.root.calls

    cruise_app = _button_app()
    cruise_app.cruising = True
    cruise_app._cruise_stop = threading.Event()
    cruise_app.stop_cruise()
    assert ("deiconify",) in cruise_app.root.calls


def test三秒等待期间停止会取消待启动回调(monkeypatch: pytest.MonkeyPatch) -> None:
    _Thread.instances.clear()
    monkeypatch.setattr(main_ui.threading, "Thread", _Thread)
    monkeypatch.setattr(main_ui.录制模块, "创建日志记录器", lambda _name: (None, None))
    monkeypatch.setattr(main_ui.录制模块, "写日志", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(main_ui.识别模块, "当前角度模式", lambda: "legacy")
    monkeypatch.setattr(main_ui.识别模块, "当前角度模式标签", lambda: "Legacy")
    app = _button_app()
    app.识别器 = object()
    app._detect_stop = threading.Event()
    app._apply_angle_mode = lambda: None
    app._detect_loop = lambda: None

    app.start_detect()
    delayed = next(call for call in app.root.calls if call[:2] == ("after", 3000))
    after_id = app._detect_start_after
    app.stop_detect()

    assert ("after_cancel", after_id) in app.root.calls
    delayed[2]()
    assert _Thread.instances == []


@pytest.mark.parametrize("kind", ["detect_stopped", "cruise_stopped"])
def test任务结束消息会恢复主窗口(kind: str) -> None:
    app = _button_app()
    app._queue = queue.Queue()
    app._queue.put((kind, None))
    app.detecting = kind == "detect_stopped"
    app.cruising = kind == "cruise_stopped"
    app._last_saved = None

    app._drain_queue()

    assert ("deiconify",) in app.root.calls


def testesc轮询仍可停止回放(monkeypatch: pytest.MonkeyPatch) -> None:
    app = _button_app()
    app.cruising = True
    app._cruise_stop = threading.Event()
    monkeypatch.setattr(
        main_ui.巡航模块,
        "处理esc紧急停止",
        lambda event: event.set() or True,
    )

    app._esc_poll()

    assert app._cruise_stop.is_set()
    assert any(call[:2] == ("after", 50) for call in app.root.calls)
