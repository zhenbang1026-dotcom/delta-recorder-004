from __future__ import annotations

import inspect
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np

import 主界面 as main_ui
import A测试模版匹配 as map_monitor
import 巡航脚本 as cruise


class Var:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


def test_minimap_capture_range_remains_compatible_with_existing_routes() -> None:
    assert map_monitor.SMALL_MAP_BOX == (57, 116, 200, 235)
    assert (map_monitor.SIZE1, map_monitor.SIZE2) == (143, 119)
    assert cruise.小地图区域 == (57, 116, 200, 235)


def test_map_reader_accepts_bmp_and_reports_dimensions(tmp_path: Path) -> None:
    path = tmp_path / "1.bmp"
    ok, encoded = cv2.imencode(".bmp", np.zeros((37, 53, 3), dtype=np.uint8))
    assert ok
    encoded.tofile(path)

    assert main_ui.读取大地图尺寸(path) == (53, 37)


def test_selected_map_is_used_to_rebuild_both_locators(monkeypatch, tmp_path: Path) -> None:
    old_path = tmp_path / "old.png"
    new_path = tmp_path / "1.bmp"
    old_path.touch()
    new_path.touch()
    created = []

    monkeypatch.setattr(main_ui, "读取大地图尺寸", lambda path: (100, 100))
    monkeypatch.setattr(
        main_ui.识别模块,
        "单独坐标识别器",
        lambda path: created.append(("map", str(path))) or ("map", str(path)),
    )
    monkeypatch.setattr(
        main_ui.识别模块,
        "实时坐标角度识别器",
        lambda **kwargs: created.append(("detect", kwargs)) or ("detect", kwargs),
    )
    monkeypatch.setattr(
        main_ui.巡航模块,
        "实时定位器",
        lambda **kwargs: created.append(("cruise", kwargs)) or ("cruise", kwargs),
    )
    app = object.__new__(main_ui.合并主界面)
    app.map_path_var = Var(str(old_path))
    app.angle_mode_var = Var("text")
    app.识别器 = object()
    app.巡航定位器 = object()

    old_size, new_size = app._应用大地图(new_path)

    assert (old_size, new_size) == ((100, 100), (100, 100))
    assert app.map_path_var.get() == str(new_path.resolve())
    assert ("map", str(new_path.resolve())) in created
    assert any(kind == "cruise" and value["地图路径"] == str(new_path.resolve()) for kind, value in created)


def test_monitor_checkboxes_are_default_off_and_visible_in_ui() -> None:
    init_source = inspect.getsource(main_ui.合并主界面.__init__)
    ui_source = inspect.getsource(main_ui.合并主界面._build_ui)

    assert "self.map_monitor_var = tk.BooleanVar(value=False)" in init_source
    assert "self.angle_monitor_var = tk.BooleanVar(value=False)" in init_source
    assert "小地图匹配大地图" in ui_source
    assert "角度识别监视" in ui_source
    assert "选择大地图" in ui_source


def test_map_monitor_stops_and_hides_when_unchecked(monkeypatch, tmp_path: Path) -> None:
    calls = []
    window = SimpleNamespace(
        deiconify=lambda: calls.append("show"),
        withdraw=lambda: calls.append("hide"),
        winfo_exists=lambda: True,
        protocol=lambda *_args: None,
    )
    monitor = SimpleNamespace(
        start_detection=lambda: calls.append("start"),
        stop_detection=lambda: calls.append("stop"),
    )
    monkeypatch.setattr(main_ui.tk, "Toplevel", lambda _root: window)
    monkeypatch.setattr(
        main_ui.地图监视模块,
        "MapLocatorApp",
        lambda _window, big_map_path: calls.append(("path", big_map_path)) or monitor,
    )
    app = object.__new__(main_ui.合并主界面)
    app.root = object()
    map_path = tmp_path / "1.bmp"
    map_path.touch()
    app.map_path_var = Var(str(map_path))
    app.map_monitor_var = Var(True)
    app._map_monitor_window = None
    app._map_monitor_app = None
    app._显示监视窗口 = lambda *_args, **_kwargs: None

    app._切换小地图监视()
    app.map_monitor_var.set(False)
    app._切换小地图监视()

    assert ("path", str(map_path.resolve())) in calls
    assert calls.count("start") == 1
    assert calls.count("stop") == 1
    assert calls.count("hide") == 1


def test_switching_map_recreates_an_open_map_monitor(monkeypatch, tmp_path: Path) -> None:
    old_path = tmp_path / "old.png"
    new_path = tmp_path / "1.bmp"
    old_path.touch()
    new_path.touch()
    calls = []
    monkeypatch.setattr(main_ui.filedialog, "askopenfilename", lambda **_kwargs: str(new_path))
    monkeypatch.setattr(main_ui, "读取大地图尺寸", lambda _path: (100, 100))
    app = object.__new__(main_ui.合并主界面)
    app.detecting = False
    app.cruising = False
    app.map_path_var = Var(str(old_path))
    app.map_monitor_var = Var(True)
    app.status_var = Var("")
    app._map_monitor_window = object()
    app._map_monitor_app = SimpleNamespace(on_closing=lambda: calls.append("close-old"))
    app._应用大地图 = lambda path: calls.append(("apply", str(path)))
    app._切换小地图监视 = lambda: calls.append("open-new")

    app._选择大地图()

    assert calls == [("apply", str(new_path)), "close-old", "open-new"]
    assert app._map_monitor_window is None
    assert app._map_monitor_app is None
