from __future__ import annotations

import math
from pathlib import Path

import cv2
import numpy as np
import pytest

import 识别角度 as 角度模块


def _角差(a: float, b: float) -> float:
    return (float(b) - float(a) + 180.0) % 360.0 - 180.0


def _读取真实标定() -> list[tuple[float, float]]:
    path = Path(__file__).resolve().parents[1] / "校准截图" / "lv.txt"
    text = None
    for encoding in ("utf-8", "gbk", "utf-8-sig"):
        try:
            text = path.read_text(encoding=encoding)
            break
        except UnicodeDecodeError:
            continue
    assert text is not None
    samples = []
    for line in text.splitlines():
        if line.startswith("MAP:"):
            raw, target = line[4:].split(",")
            samples.append((float(raw), float(target)))
    return samples


def _创建零度箭头图() -> np.ndarray:
    image = np.zeros((100, 100, 3), dtype=np.uint8)
    hsv_pixel = np.uint8([[[60, 120, 220]]])
    green = tuple(int(v) for v in cv2.cvtColor(hsv_pixel, cv2.COLOR_HSV2BGR)[0, 0])
    cv2.circle(image, (50, 50), 7, green, -1)
    cv2.circle(image, (75, 50), 4, green, -1)
    return image


def test圆形残差插值跨原始角和目标角零点() -> None:
    samples = [(359.0, 60.0), (1.0, 62.0)]

    assert 角度模块.圆形残差插值(359.5, samples) == 60.5
    assert 角度模块.圆形残差插值(0.0, samples) == 61.0
    assert 角度模块.圆形残差插值(0.5, samples) == 61.5

    target_wrap = [(298.0, 359.0), (300.0, 1.0)]
    assert abs(_角差(角度模块.圆形残差插值(299.0, target_wrap), 0.0)) < 1e-9


def test圆形残差插值处理重复原始角及空单点() -> None:
    assert 角度模块.圆形残差插值(10.0, []) is None
    assert 角度模块.圆形残差插值(350.0, [(10.0, 80.0)]) == 60.0

    result = 角度模块.圆形残差插值(
        10.0,
        [(10.0, 71.0), (10.0, 72.0)],
    )
    assert result is not None
    assert abs(_角差(result, 71.5)) < 1e-9


def test真实353样本留一预测p95小于1点5度() -> None:
    samples = _读取真实标定()
    assert len(samples) == 353
    errors = []
    for index, (raw, target) in enumerate(samples):
        predicted = 角度模块.圆形残差插值(raw, samples[:index] + samples[index + 1 :])
        assert predicted is not None
        errors.append(abs(_角差(predicted, target)))
    errors.sort()
    p95 = errors[math.ceil(len(errors) * 0.95) - 1]
    assert p95 < 1.5


def testtext识别输出使用map并记录来源和置信度(tmp_path: Path) -> None:
    calibration = tmp_path / "lv.txt"
    calibration.write_text(
        "SRC_CROP:0,0,100,100\n"
        "PRECISE_CENTER:101,101\n"
        "MAP:0,61\n"
        "MAP:180,241\n",
        encoding="utf-8",
    )
    image = _创建零度箭头图()
    recognizer = 角度模块.角度识别器(str(calibration), 当前地图="零号大坝")

    angle = recognizer.识别角度(图像数据=image)

    assert angle is not None
    assert abs(_角差(angle, 61.0)) < 2.0
    assert recognizer.最近详情["calibration_source"] == "map"
    assert 0.5 <= recognizer.最近详情["confidence"] <= 1.0


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
