from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest

import 识别角度 as 角度模块


def _角差(a: float, b: float) -> float:
    return (float(b) - float(a) + 180.0) % 360.0 - 180.0


def _创建零度箭头图() -> np.ndarray:
    image = np.zeros((100, 100, 3), dtype=np.uint8)
    hsv_pixel = np.uint8([[[60, 120, 220]]])
    green = tuple(int(v) for v in cv2.cvtColor(hsv_pixel, cv2.COLOR_HSV2BGR)[0, 0])
    cv2.circle(image, (50, 50), 7, green, -1)
    cv2.circle(image, (75, 50), 4, green, -1)
    return image


@pytest.mark.parametrize(
    ("当前地图", "期望角度", "期望来源"),
    [
        ("零号大坝", 90.0, "fixed_offset_90"),
        ("其他地图", 0.0, "raw"),
    ],
)
def testtext识别最终角度严格使用atan2且忽略map(
    tmp_path: Path,
    当前地图: str,
    期望角度: float,
    期望来源: str,
) -> None:
    calibration = tmp_path / "lv.txt"
    calibration.write_text(
        "SRC_CROP:0,0,100,100\n"
        "PRECISE_CENTER:101,101\n"
        "MAP:0,61\n"
        "MAP:180,241\n",
        encoding="utf-8",
    )
    image = _创建零度箭头图()
    recognizer = 角度模块.角度识别器(str(calibration), 当前地图=当前地图)

    angle = recognizer.识别角度(图像数据=image)

    assert angle is not None
    assert abs(_角差(angle, 期望角度)) < 2.0
    assert abs(_角差(recognizer.最近详情["raw"], 0.0)) < 2.0
    assert recognizer.最近详情["angle"] == angle
    assert recognizer.最近详情["calibration_source"] == 期望来源


def test坏map行跳过且保留元数据和其它有效map(tmp_path: Path) -> None:
    calibration = tmp_path / "lv.txt"
    calibration.write_text(
        "SRC_CROP:0,0,100,100\n"
        "PRECISE_CENTER:101,101\n"
        "MAP:坏数据,20\n"
        "MAP:20\n"
        "MAP:0,61\n"
        "MAP:180,241\n",
        encoding="utf-8",
    )
    recognizer = 角度模块.角度识别器(str(calibration))

    data = recognizer._读取校准数据()

    assert data["crop"] == (0, 0, 100, 100)
    assert data["center_x"] == 101.0
    assert data["center_y"] == 101.0
    assert data["map_list"] == [(0.0, 61), (180.0, 241)]


@pytest.mark.parametrize("map_line", ["", "MAP:坏数据,仍然坏\n"])
def test仅坏map或无map时仍按旧90度公式回退(tmp_path: Path, map_line: str) -> None:
    calibration = tmp_path / "lv.txt"
    calibration.write_text(
        "SRC_CROP:0,0,100,100\n"
        "PRECISE_CENTER:101,101\n"
        + map_line,
        encoding="utf-8",
    )
    recognizer = 角度模块.角度识别器(str(calibration), 当前地图="零号大坝")

    angle = recognizer.识别角度(图像数据=_创建零度箭头图())

    assert angle is not None
    assert abs(_角差(angle, 90.0)) < 2.0
    assert recognizer.最近详情["calibration_source"] == "fixed_offset_90"
