from __future__ import annotations

import pytest

from 动作编辑器 import 表单字段, 从表单创建动作


def test_key_form_builds_ordered_combo() -> None:
    action = 从表单创建动作(
        "key",
        {"keys": "ctrl + shift + f", "mode": "长按", "duration_ms": "650"},
    )

    assert action.参数 == {
        "keys": ["ctrl", "shift", "f"],
        "mode": "hold",
        "duration_ms": 650,
    }


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
