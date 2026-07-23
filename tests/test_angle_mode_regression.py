from __future__ import annotations

import ast
import hashlib
import inspect
from pathlib import Path

import numpy as np

import A测试角度识别 as 角度模式模块


LEGACY_SOURCE_SHA256 = "8bdc995bca7e39bc6726391e497593085e725463e46b4a87afd873a35f3808ca"
TEXT_RAW_SOURCE_SHA256 = "ad23f5fbd896429dc5fe7591601ef9d1e751bc1fa216e0dbeac41629d4c9ddff"
TEXT_STABLE_SOURCE_SHA256 = "89351d7c2befb1c1111d7ec57b67ad7b6d60e13b450b60bb50c3990eb9992d2b"
TEXT_DEFAULT_SOURCE_SHA256 = "56e3aac146039cbf3a1cf4069769613b24cdf9188819e13b2ce9b7c2fd49ee03"


def _get_function_source(source_path: Path, function_name: str) -> str:
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    node = next(
        item
        for item in tree.body
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
        and item.name == function_name
    )
    return "\n".join(source.splitlines()[node.lineno - 1 : node.end_lineno]) + "\n"


def testlegacy函数源码和默认模式roi不变() -> None:
    source_path = Path(inspect.getsourcefile(角度模式模块))
    function_source = _get_function_source(source_path, "_analyze_image_legacy")

    assert hashlib.sha256(function_source.encode("utf-8")).hexdigest() == LEGACY_SOURCE_SHA256
    角度模式模块.set_angle_mode("legacy")
    assert 角度模式模块.get_angle_mode() == "legacy"
    assert 角度模式模块.get_angle_bbox() == (119, 161, 146, 188)


def testtext关键函数源码冻结() -> None:
    source_path = Path(inspect.getsourcefile(角度模式模块))

    raw_source = _get_function_source(source_path, "_analyze_image_text_raw")
    stable_source = _get_function_source(source_path, "_analyze_image_text")
    default_source = _get_function_source(source_path.with_name("识别角度.py"), "默认识别器")

    assert hashlib.sha256(raw_source.encode("utf-8")).hexdigest() == TEXT_RAW_SOURCE_SHA256
    assert hashlib.sha256(stable_source.encode("utf-8")).hexdigest() == TEXT_STABLE_SOURCE_SHA256
    assert hashlib.sha256(default_source.encode("utf-8")).hexdigest() == TEXT_DEFAULT_SOURCE_SHA256


def testfusion别名标签和roi且切回legacy不变() -> None:
    assert 角度模式模块.normalize_angle_mode("融合") == "fusion"
    assert 角度模式模块.normalize_angle_mode("overall") == "fusion"
    assert 角度模式模块.set_angle_mode("fusion") == "fusion"
    assert 角度模式模块.get_angle_mode_label() == "融合算法（TEXT主观测+Legacy降级）"
    assert 角度模式模块.get_angle_bbox() == (34, 78, 227, 271)

    assert 角度模式模块.set_angle_mode("legacy") == "legacy"
    assert 角度模式模块.get_angle_bbox() == (119, 161, 146, 188)


def testadaptive_text滤波只平滑小抖动正常转向直接跟随() -> None:
    stabilizer = 角度模式模块._AngleStabilizer(alpha=0.5, smooth_threshold=4.0)

    assert stabilizer.update(100.0) == 100.0
    assert stabilizer.update(102.0) == 101.0
    assert stabilizer.update(121.0) == 121.0
    assert stabilizer.update(359.0) == 359.0
    wrapped = stabilizer.update(1.0)
    assert abs(角度模式模块._AngleStabilizer._delta(wrapped, 0.0)) < 1e-9


def testfusion在同一text大图裁出legacy相对roi(monkeypatch) -> None:
    calls = {"text_angle": 50.0, "legacy_angle": 51.0}

    def fake_text(image, colors, tolerance, min_area, clean_mask, region, hsv_mode=False):
        calls["text_shape"] = image.shape
        return 角度模式模块.AnalysisResult(
            calls["text_angle"], (100.0, 100.0), (110.0, 100.0), image.copy(),
            np.zeros(image.shape[:2], dtype=np.uint8), (0, 0), "TEXT"
        )

    def fake_legacy(image, colors, tolerance, min_area, clean_mask, region, hsv_mode=False):
        calls["legacy_region"] = region
        return 角度模式模块.AnalysisResult(
            calls["legacy_angle"], (13.0, 13.0), (14.0, 13.0), image.copy(),
            np.zeros(image.shape[:2], dtype=np.uint8), region[:2], "LEGACY"
        )

    monkeypatch.setattr(角度模式模块, "_analyze_image_text_raw", fake_text)
    monkeypatch.setattr(角度模式模块, "_analyze_image_legacy", fake_legacy)
    角度模式模块.reset_fusion_selector()
    image = np.zeros((240, 240, 3), dtype=np.uint8)
    outer_region = (10, 20, 203, 213)

    result = 角度模式模块._analyze_image_fusion(
        image, [("FFFFFF", (255, 255, 255))], 45, 0, False, outer_region, False
    )

    assert calls["text_shape"] == (193, 193, 3)
    assert calls["legacy_region"] == (85, 83, 112, 110)
    assert result.angle == 50.0
    assert result.observation_source == "text"
    assert result.offset == (10, 20)
    assert result.fusion_difference == 1.0
    assert result.text_error is None
    assert result.legacy_error is None

    calls["text_angle"] = 150.0
    角度模式模块.reset_fusion_selector()
    legacy_result = 角度模式模块._analyze_image_fusion(
        image, [("FFFFFF", (255, 255, 255))], 45, 0, False, outer_region, False
    )
    assert legacy_result.observation_source == "legacy"
    assert legacy_result.offset == (95, 103)
    assert legacy_result.fusion_difference == 99.0


def testfusion结果记录单路错误详情(monkeypatch) -> None:
    def failed_text(*args, **kwargs):
        raise ValueError("TEXT测试错误")

    def good_legacy(image, colors, tolerance, min_area, clean_mask, region, hsv_mode=False):
        return 角度模式模块.AnalysisResult(
            51.0, (13.0, 13.0), (14.0, 13.0), image.copy(),
            np.zeros(image.shape[:2], dtype=np.uint8), region[:2], "LEGACY"
        )

    monkeypatch.setattr(角度模式模块, "_analyze_image_text_raw", failed_text)
    monkeypatch.setattr(角度模式模块, "_analyze_image_legacy", good_legacy)
    角度模式模块.reset_fusion_selector()

    result = 角度模式模块._analyze_image_fusion(
        np.zeros((193, 193, 3), dtype=np.uint8),
        [("FFFFFF", (255, 255, 255))], 45, 0, False, None, False,
    )

    assert result.observation_source == "legacy"
    assert result.fusion_difference is None
    assert "TEXT测试错误" in result.text_error
    assert result.legacy_error is None
