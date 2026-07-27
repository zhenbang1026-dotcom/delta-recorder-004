from __future__ import annotations

import inspect

import pytest

import 主界面 as main_ui
import 动作编辑器 as action_editor
import 窗口定位 as window_position


class _Window:
    def __init__(self, hwnd: int) -> None:
        self.hwnd = hwnd
        self.geometry_calls: list[str] = []
        self.update_count = 0

    def geometry(self, value: str) -> None:
        self.geometry_calls.append(value)

    def update_idletasks(self) -> None:
        self.update_count += 1

    def winfo_id(self) -> int:
        return self.hwnd


def test右下角位置使用工作区并保留20像素边距() -> None:
    assert window_position.计算右下角位置((1920, 0, 3840, 1040), 620, 700) == (3200, 320)
    assert window_position.计算右上角位置((1920, 0, 3840, 1040), 560, 430) == (3260, 20)


def test子窗口跟随父窗口显示器并使用绝对坐标(monkeypatch: pytest.MonkeyPatch) -> None:
    parent = _Window(101)
    window = _Window(202)
    monitor_calls = []
    position_calls = []
    monkeypatch.setattr(
        window_position.win32api,
        "MonitorFromWindow",
        lambda hwnd, flag: monitor_calls.append((hwnd, flag)) or "monitor-2",
    )
    monkeypatch.setattr(
        window_position.win32api,
        "GetMonitorInfo",
        lambda monitor: {"Work": (1920, 0, 3840, 1040)},
    )
    monkeypatch.setattr(
        window_position.win32gui,
        "GetAncestor",
        lambda hwnd, flag: {101: 901, 202: 902}[hwnd],
    )
    monkeypatch.setattr(
        window_position.win32gui,
        "GetWindowRect",
        lambda hwnd: (0, 0, 640, 740) if hwnd == 902 else pytest.fail("必须读取外层窗口"),
    )
    monkeypatch.setattr(
        window_position.win32gui,
        "SetWindowPos",
        lambda *args: position_calls.append(args),
    )

    result = window_position.定位窗口到右下角(window, 620, 700, 参照窗口=parent)

    assert window.geometry_calls == ["620x700"]
    assert parent.update_count == 1
    assert monitor_calls == [(901, window_position.最近显示器)]
    assert result == (3180, 280)
    assert position_calls[0][0:5] == (902, 0, 3180, 280, 0)
    assert position_calls[0][5] == 0


def test主窗口跟随鼠标所在显示器(monkeypatch: pytest.MonkeyPatch) -> None:
    window = _Window(303)
    monitor_calls = []
    monkeypatch.setattr(window_position.win32api, "GetCursorPos", lambda: (2500, 300))
    monkeypatch.setattr(
        window_position.win32api,
        "MonitorFromPoint",
        lambda point, flag: monitor_calls.append((point, flag)) or "monitor-2",
    )
    monkeypatch.setattr(
        window_position.win32api,
        "GetMonitorInfo",
        lambda monitor: {"Work": (1920, 0, 3840, 1040)},
    )
    monkeypatch.setattr(
        window_position.win32gui,
        "GetAncestor",
        lambda hwnd, flag: 903,
    )
    monkeypatch.setattr(
        window_position.win32gui,
        "GetWindowRect",
        lambda hwnd: (0, 0, 1120, 860),
    )
    monkeypatch.setattr(window_position.win32gui, "SetWindowPos", lambda *_args: None)

    result = window_position.定位窗口到右下角(window, 1100, 820)

    assert monitor_calls == [((2500, 300), window_position.最近显示器)]
    assert result == (2700, 160)


def test005所有自建窗口都调用统一右下角定位() -> None:
    bottom_right_sources = (
        inspect.getsource(main_ui.合并主界面.__init__),
        inspect.getsource(action_editor.动作参数窗口.__init__),
        inspect.getsource(action_editor.动作列表窗口.__init__),
        inspect.getsource(action_editor.动作列表窗口._打开代码块窗口),
        inspect.getsource(action_editor.路线编辑窗口.__init__),
    )

    assert all("定位窗口到右下角" in source for source in bottom_right_sources)
    assert "定位窗口到右上角" in inspect.getsource(main_ui.合并主界面._显示YOLO窗口)


def test所有窗口完成控件构建后才定位避免白屏() -> None:
    sources_and_markers = (
        (inspect.getsource(main_ui.合并主界面.__init__), "self._build_ui()"),
        (inspect.getsource(action_editor.动作参数窗口.__init__), 'text="取消"'),
        (inspect.getsource(action_editor.动作列表窗口.__init__), "self._刷新()"),
        (inspect.getsource(action_editor.动作列表窗口._打开代码块窗口), "names.selection_set(0)"),
        (inspect.getsource(action_editor.路线编辑窗口.__init__), "self._刷新(0)"),
    )

    for source, marker in sources_and_markers:
        assert source.index(marker) < source.rindex("定位窗口到右下角")
