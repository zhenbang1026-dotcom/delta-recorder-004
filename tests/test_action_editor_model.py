from __future__ import annotations

import pytest

from 动作编辑器 import 动作列表窗口, 动作标签, 表单字段, 从表单创建动作
from 路线动作 import 路线动作


def test_copy_selected_action_inserts_independent_copy_after_source() -> None:
    source = 路线动作("key", {"keys": ["w", "f"], "mode": "hold", "duration_ms": 200})
    window = object.__new__(动作列表窗口)
    window.actions = [source, 路线动作("wait", {"milliseconds": 500})]
    window.listbox = type("Listbox", (), {"curselection": lambda self: (0,)})()
    selected = []
    window._刷新 = selected.append

    window._复制()

    assert window.actions == [source, source, 路线动作("wait", {"milliseconds": 500})]
    assert window.actions[1] is not source
    assert window.actions[1].参数 is not source.参数
    assert window.actions[1].参数["keys"] is not source.参数["keys"]
    assert selected == [1]


def test_copy_shortcut_runs_copy_and_stops_tk_default_handling() -> None:
    window = object.__new__(动作列表窗口)
    calls = []
    window._复制 = lambda: calls.append("copy")

    assert window._复制快捷键() == "break"
    assert calls == ["copy"]


def test_key_form_builds_ordered_combo() -> None:
    action = 从表单创建动作(
        "key",
        {"keys": "ctrl + shift + f", "mode": "长按", "duration_ms": "650"},
    )

    assert action.参数 == {
        "keys": ["ctrl", "shift", "f"],
        "mode": "hold",
        "duration_ms": 650,
        "repeat_count": 1,
        "repeat_interval_ms": 100,
        "duration_jitter_minus_ms": 5,
        "duration_jitter_plus_ms": 20,
    }


def test_key_form_builds_repeat_and_duration_jitter() -> None:
    action = 从表单创建动作(
        "key",
        {
            "keys": "w+f",
            "mode": "单击",
            "duration_ms": "100",
            "repeat_count": "3",
            "repeat_interval_ms": "100",
            "duration_jitter_minus_ms": "5",
            "duration_jitter_plus_ms": "20",
        },
    )

    assert action.参数["repeat_count"] == 3
    assert action.参数["repeat_interval_ms"] == 100
    assert action.参数["duration_jitter_minus_ms"] == 5
    assert action.参数["duration_jitter_plus_ms"] == 20


def test_key_form_defaults_repeat_and_duration_jitter() -> None:
    defaults = {key: default for key, _label, default, _options in 表单字段["key"]}

    assert defaults["repeat_count"] == "1"
    assert defaults["repeat_interval_ms"] == "100"
    assert defaults["duration_jitter_minus_ms"] == "5"
    assert defaults["duration_jitter_plus_ms"] == "20"


def test_chinese_comment_is_preserved() -> None:
    action = 从表单创建动作("comment", {"text": "开门后等待队友"})

    assert action.参数["text"] == "开门后等待队友"


@pytest.mark.parametrize(
    ("direction", "delta"),
    [("低头", "-300"), ("抬头", "300")],
)
def test_look_form_rejects_wrong_y_direction(direction: str, delta: str) -> None:
    with pytest.raises(ValueError, match="Y 位移"):
        从表单创建动作(
            "look",
            {
                "direction": direction,
                "y_delta": delta,
                "duration_ms": "300",
                "x_random": "4",
            },
        )


def test_yolo_form_requires_enough_w_time() -> None:
    with pytest.raises(ValueError, match="W 持续时间"):
        从表单创建动作(
            "yolo_interact",
            {
                "angle": "90",
                "confidence": "0.5",
                "timeout_ms": "5000",
                "tolerance_px": "12",
                "initial_f_ms": "500",
                "initial_wait_ms": "300",
                "repeat_f_ms": "50",
                "w_duration_ms": "500",
                "f_count": "5",
                "f_interval_ms": "500",
            },
        )


def test_yolo_form_builds_200ms_initial_f_and_vertical_offset() -> None:
    action = 从表单创建动作(
        "yolo_interact",
        {
            "angle": "90",
            "confidence": "0.5",
            "timeout_ms": "5000",
            "tolerance_px": "12",
            "target_y_offset_px": "20",
            "initial_f_ms": "200",
            "initial_wait_ms": "300",
            "repeat_f_ms": "50",
            "w_duration_ms": "500",
            "f_count": "1",
            "f_interval_ms": "500",
        },
    )

    assert action.参数["initial_f_ms"] == 200
    assert action.参数["target_y_offset_px"] == 20


def test_yolo_form_defaults_initial_f_to_200ms_and_offset_to_zero() -> None:
    defaults = {key: default for key, _label, default, _options in 表单字段["yolo_interact"]}

    assert defaults["initial_f_ms"] == "200"
    assert defaults["target_y_offset_px"] == "0"


def test_persistent_yolo_aim_on_and_off_forms_are_separate_actions() -> None:
    on = 从表单创建动作(
        "yolo_aim_on",
        {
            "angle": "248.2",
            "confidence": "0.5",
            "tolerance_px": "12",
            "target_y_offset_px": "20",
        },
    )
    off = 从表单创建动作("yolo_aim_off", {})

    assert 动作标签["yolo_interact"] == "YOLO 识别并交互"
    assert 动作标签["yolo_aim_on"] == "YOLO 识别并对准开"
    assert 动作标签["yolo_aim_off"] == "YOLO 识别并对准关"
    assert on.参数 == {
        "angle": 248.2,
        "confidence": 0.5,
        "tolerance_px": 12,
        "target_y_offset_px": 20,
    }
    assert off.参数 == {}
    assert [key for key, _label, _default, _options in 表单字段["yolo_aim_on"]] == [
        "angle", "confidence", "tolerance_px", "target_y_offset_px"
    ]
    assert 表单字段["yolo_aim_off"] == []
