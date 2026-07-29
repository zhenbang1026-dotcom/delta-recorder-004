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


def test_realtime_detector_captures_the_configured_ranges(monkeypatch) -> None:
    small_box = (60, 120, 203, 239)
    angle_box = (120, 162, 147, 189)
    captures = []
    small_image = np.zeros((119, 143, 3), dtype=np.uint8)
    angle_image = np.zeros((27, 27, 3), dtype=np.uint8)

    def grab_regions(*boxes):
        captures.append(boxes)
        return {small_box: small_image, angle_box: angle_image}

    monkeypatch.setattr(main_ui.识别模块.角度模块, "grab_regions_bgr", grab_regions)
    detector = main_ui.识别模块.实时坐标角度识别器(
        地图匹配器=SimpleNamespace(
            locate_minimap=lambda image: {
                "success": image is small_image,
                "x": 10,
                "y": 20,
                "method": "sift",
            }
        ),
        角度分析器=lambda image, *_args: SimpleNamespace(
            angle=30.0,
            color_hex="#FFFFFF" if image is angle_image else "#000000",
        ),
        角度颜色=[("#FFFFFF", (255, 255, 255))],
        小地图截图区域=small_box,
        角度截图区域=angle_box,
    )

    state = detector.读取状态()

    assert captures == [(small_box, angle_box)]
    assert (state.x, state.y, state.angle) == (10, 20, 30.0)


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
    app.small_map_box = (60, 120, 203, 239)
    app.angle_boxes = {"text": (35, 79, 228, 272)}
    app.识别器 = object()
    app.巡航定位器 = object()

    old_size, new_size = app._应用大地图(new_path)

    assert (old_size, new_size) == ((100, 100), (100, 100))
    assert app.map_path_var.get() == str(new_path.resolve())
    assert ("map", str(new_path.resolve())) in created
    assert any(
        kind == "detect"
        and value["小地图截图区域"] == (60, 120, 203, 239)
        and value["角度截图区域"] == (35, 79, 228, 272)
        for kind, value in created
    )
    assert any(kind == "cruise" and value["地图路径"] == str(new_path.resolve()) for kind, value in created)
    assert any(
        kind == "cruise"
        and value["小地图截图区域"] == (60, 120, 203, 239)
        and value["角度截图区域"] == (35, 79, 228, 272)
        for kind, value in created
    )


def _range_app(tmp_path: Path) -> main_ui.合并主界面:
    map_path = tmp_path / "map.png"
    map_path.touch()
    app = object.__new__(main_ui.合并主界面)
    app.detecting = False
    app.recording = False
    app.cruising = False
    app.map_path_var = Var(str(map_path))
    app.angle_mode_var = Var("legacy")
    app.small_map_box = (57, 116, 200, 235)
    app.angle_boxes = {
        "legacy": (119, 161, 146, 188),
        "text": (34, 78, 227, 271),
    }
    app.small_map_box_var = Var("60,120,203,239")
    app.angle_box_var = Var("120,162,147,189")
    app.status_var = Var("")
    app.识别器 = object()
    app.巡航定位器 = object()
    app.map_monitor_var = Var(False)
    app.angle_monitor_var = Var(False)
    app._map_monitor_window = None
    app._map_monitor_app = None
    app._angle_monitor_window = None
    app._angle_monitor_app = None
    app._save_settings = lambda: None
    return app


def test应用识别范围同时替换两个后端(monkeypatch, tmp_path: Path) -> None:
    app = _range_app(tmp_path)
    created = []
    monkeypatch.setattr(main_ui.messagebox, "askyesno", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(main_ui.识别模块, "单独坐标识别器", lambda path: ("map", path))
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

    app._应用识别范围()

    assert app.small_map_box == (60, 120, 203, 239)
    assert app.angle_boxes["legacy"] == (120, 162, 147, 189)
    assert created[0][1]["小地图截图区域"] == (60, 120, 203, 239)
    assert created[0][1]["角度截图区域"] == (120, 162, 147, 189)
    assert created[1][1]["小地图截图区域"] == (60, 120, 203, 239)
    assert created[1][1]["角度截图区域"] == (120, 162, 147, 189)


def test应用识别范围后端失败保持旧状态(monkeypatch, tmp_path: Path) -> None:
    app = _range_app(tmp_path)
    old_detector = app.识别器
    old_locator = app.巡航定位器
    errors = []
    monkeypatch.setattr(main_ui.messagebox, "askyesno", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(main_ui.messagebox, "showerror", lambda *args: errors.append(args))
    monkeypatch.setattr(main_ui.识别模块, "单独坐标识别器", lambda path: ("map", path))
    monkeypatch.setattr(main_ui.识别模块, "实时坐标角度识别器", lambda **_kwargs: object())
    monkeypatch.setattr(
        main_ui.巡航模块,
        "实时定位器",
        lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    app._应用识别范围()

    assert app.small_map_box == (57, 116, 200, 235)
    assert app.angle_boxes["legacy"] == (119, 161, 146, 188)
    assert app.识别器 is old_detector
    assert app.巡航定位器 is old_locator
    assert errors


def test取消小地图范围风险提示不会应用(monkeypatch, tmp_path: Path) -> None:
    app = _range_app(tmp_path)
    calls = []
    monkeypatch.setattr(main_ui.messagebox, "askyesno", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(
        main_ui.识别模块,
        "实时坐标角度识别器",
        lambda **_kwargs: calls.append("detect"),
    )

    app._应用识别范围()

    assert calls == []
    assert app.small_map_box == (57, 116, 200, 235)


def test识别录制或回放时禁止应用识别范围(monkeypatch, tmp_path: Path) -> None:
    warnings = []
    monkeypatch.setattr(main_ui.messagebox, "showwarning", lambda *args: warnings.append(args))
    for state in ("detecting", "recording", "cruising"):
        app = _range_app(tmp_path)
        setattr(app, state, True)
        app._应用识别范围()
    assert len(warnings) == 3


def test_monitor_checkboxes_are_default_off_and_visible_in_ui() -> None:
    init_source = inspect.getsource(main_ui.合并主界面.__init__)
    ui_source = inspect.getsource(main_ui.合并主界面._build_ui)

    assert "self.map_monitor_var = tk.BooleanVar(value=False)" in init_source
    assert "self.angle_monitor_var = tk.BooleanVar(value=False)" in init_source
    assert "小地图匹配大地图" in ui_source
    assert "角度识别监视" in ui_source
    assert "选择大地图" in ui_source
    assert "小地图范围:" in ui_source
    assert "当前角度范围:" in ui_source
    assert "应用识别范围" in ui_source
    assert "恢复默认范围" in ui_source


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
        lambda _window, big_map_path, small_map_box: calls.append(
            ("path", big_map_path, small_map_box)
        ) or monitor,
    )
    app = object.__new__(main_ui.合并主界面)
    app.root = object()
    map_path = tmp_path / "1.bmp"
    map_path.touch()
    app.map_path_var = Var(str(map_path))
    app.map_monitor_var = Var(True)
    app.small_map_box = (60, 120, 203, 239)
    app._map_monitor_window = None
    app._map_monitor_app = None
    app._显示监视窗口 = lambda *_args, **_kwargs: None

    app._切换小地图监视()
    app.map_monitor_var.set(False)
    app._切换小地图监视()

    assert ("path", str(map_path.resolve()), (60, 120, 203, 239)) in calls
    assert calls.count("start") == 1
    assert calls.count("stop") == 1
    assert calls.count("hide") == 1


def test_angle_monitor_receives_the_current_mode_range(monkeypatch) -> None:
    calls = []
    window = SimpleNamespace(
        deiconify=lambda: calls.append("show"),
        winfo_exists=lambda: True,
        protocol=lambda *_args: None,
    )
    monitor = SimpleNamespace(
        angle_mode_var=Var("legacy"),
        angle_bbox_var=Var(""),
        _on_angle_mode_changed=lambda: calls.append("mode"),
        start=lambda: calls.append("start"),
    )
    monkeypatch.setattr(main_ui.tk, "Toplevel", lambda _root: window)
    monkeypatch.setattr(
        main_ui.角度监视模块,
        "RealtimeAngleApp",
        lambda _window: monitor,
    )
    app = object.__new__(main_ui.合并主界面)
    app.root = object()
    app.angle_mode_var = Var("text")
    app.angle_boxes = {"text": (35, 79, 228, 272)}
    app.angle_monitor_var = Var(True)
    app._angle_monitor_window = None
    app._angle_monitor_app = None
    app._显示监视窗口 = lambda *_args, **_kwargs: None

    app._切换角度监视()

    assert monitor.angle_mode_var.get() == "text"
    assert monitor.angle_bbox_var.get() == "35,79,228,272"
    assert calls == ["mode", "show", "start"]


def test_cruise_mode_switch_keeps_the_supplied_custom_range(monkeypatch) -> None:
    locator = object.__new__(cruise.实时定位器)
    monkeypatch.setattr(cruise.合并识别模块, "设置角度模式", lambda mode: mode)

    locator.设置角度模式("text", (35, 79, 228, 272))

    assert locator.角度模式 == "text"
    assert locator.角度截图区域 == (35, 79, 228, 272)


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
