from __future__ import annotations

import json
from pathlib import Path

import pytest

from 路线动作 import (
    路线动作,
    路线点,
    读取路线文件,
    写入路线文件,
)


def test_jsonl_roundtrip_preserves_order_and_chinese_comment(tmp_path: Path) -> None:
    path = tmp_path / "demo.jsonl"
    points = [
        路线点(10, 20, 30.5, False, ()),
        路线点(
            11,
            21,
            31.5,
            False,
            (
                路线动作("key", {"keys": ["ctrl", "f"], "mode": "hold", "duration_ms": 500}),
                路线动作("comment", {"text": "到门口后先观察，再继续前进"}),
                路线动作("wait", {"milliseconds": 750}),
            ),
        ),
    ]

    写入路线文件(path, points)
    restored = 读取路线文件(path)

    assert restored == points
    assert json.loads(path.read_text(encoding="utf-8").splitlines()[0])["version"] == 2


def test_old_txt_route_remains_readable(tmp_path: Path) -> None:
    path = tmp_path / "old.txt"
    path.write_text("1,2\n3,4\n", encoding="utf-8")

    points = 读取路线文件(path)

    assert [(p.x, p.y, p.angle, p.自动路线) for p in points] == [
        (1, 2, 0.0, True),
        (3, 4, 0.0, True),
    ]


def test_yolo_action_validates_w_duration_before_save() -> None:
    with pytest.raises(ValueError, match="W 持续时间"):
        路线动作(
            "yolo_interact",
            {
                "confidence": 0.5,
                "timeout_ms": 5000,
                "tolerance_px": 12,
                "initial_f_ms": 500,
                "initial_wait_ms": 300,
                "repeat_f_ms": 50,
                "w_duration_ms": 500,
                "f_count": 5,
                "f_interval_ms": 500,
            },
        ).校验()


def test_editing_actions_keeps_explicit_order() -> None:
    point = 路线点(
        1,
        2,
        3.0,
        False,
        (
            路线动作("wait", {"milliseconds": 1}),
            路线动作("comment", {"text": "第二步"}),
        ),
    )

    reordered = point.替换动作((point.actions[1], point.actions[0]))

    assert [item.类型 for item in reordered.actions] == ["comment", "wait"]
