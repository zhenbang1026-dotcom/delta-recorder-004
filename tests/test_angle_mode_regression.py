from __future__ import annotations

import ast
import hashlib
import inspect
import math
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

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
    start_lineno = min([node.lineno, *(item.lineno for item in node.decorator_list)])
    return "\n".join(source.splitlines()[start_lineno - 1 : node.end_lineno]) + "\n"


def test函数源码哈希包含装饰器(tmp_path: Path) -> None:
    source = "@decorator\ndef target():\n    return 1\n"
    source_path = tmp_path / "decorated.py"
    source_path.write_text(source, encoding="utf-8")

    function_source = _get_function_source(source_path, "target")

    assert hashlib.sha256(function_source.encode("utf-8")).hexdigest() == hashlib.sha256(
        source.encode("utf-8")
    ).hexdigest()


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
    assert 角度模式模块.get_angle_mode_label() == "融合算法（三色精准主观测+Legacy降级）"
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


def testfusion在同一精准大图裁出legacy相对roi且对外映射精准来源(monkeypatch) -> None:
    calls = {"precise_angle": 50.0, "legacy_angle": 51.0}

    class FakePreciseRecognizer:
        最近错误 = None

        def reset(self):
            pass

        def 识别(self, image):
            calls["precise_shape"] = image.shape
            return SimpleNamespace(
                angle=calls["precise_angle"],
                color="绿色",
                confidence=0.9,
                details={
                    "origin": (100.0, 100.0),
                    "target": (110.0, 100.0),
                    "debug": image.copy(),
                    "mask": np.zeros(image.shape[:2], dtype=np.uint8),
                    "offset": (0, 0),
                    "color_hex": "9AE77E",
                },
            )

    def fake_legacy(image, colors, tolerance, min_area, clean_mask, region, hsv_mode=False):
        calls["legacy_region"] = region
        return 角度模式模块.AnalysisResult(
            calls["legacy_angle"], (13.0, 13.0), (14.0, 13.0), image.copy(),
            np.zeros(image.shape[:2], dtype=np.uint8), region[:2], "LEGACY"
        )

    monkeypatch.setattr(角度模式模块, "_fusion_precise_recognizer", FakePreciseRecognizer(), raising=False)
    monkeypatch.setattr(角度模式模块, "_analyze_image_legacy", fake_legacy)
    角度模式模块.reset_fusion_selector()
    image = np.zeros((240, 240, 3), dtype=np.uint8)
    outer_region = (10, 20, 203, 213)

    result = 角度模式模块._analyze_image_fusion(
        image, [("FFFFFF", (255, 255, 255))], 45, 0, False, outer_region, False
    )

    assert calls["precise_shape"] == (193, 193, 3)
    assert calls["legacy_region"] == (85, 83, 112, 110)
    assert result.angle == 50.0
    assert result.observation_source == "precise"
    assert result.offset == (10, 20)
    assert result.fusion_difference == 1.0
    assert result.precise_color == "绿色"
    assert result.precise_quality == 0.9
    assert result.precise_error is None
    assert result.text_error is None
    assert result.legacy_error is None
    assert "精准三色" in result.fusion_reason
    assert "TEXT" not in result.fusion_reason

    calls["precise_angle"] = 150.0
    角度模式模块.reset_fusion_selector()
    legacy_result = 角度模式模块._analyze_image_fusion(
        image, [("FFFFFF", (255, 255, 255))], 45, 0, False, outer_region, False
    )
    assert legacy_result.observation_source == "legacy"
    assert legacy_result.offset == (95, 103)
    assert legacy_result.fusion_difference == 99.0


def testfusion精准失败时降级legacy并记录兼容错误字段(monkeypatch) -> None:
    class FailedPreciseRecognizer:
        最近错误 = "精准三色测试错误"

        def reset(self):
            pass

        def 识别(self, image):
            return None

    def good_legacy(image, colors, tolerance, min_area, clean_mask, region, hsv_mode=False):
        return 角度模式模块.AnalysisResult(
            51.0, (13.0, 13.0), (14.0, 13.0), image.copy(),
            np.zeros(image.shape[:2], dtype=np.uint8), region[:2], "LEGACY"
        )

    monkeypatch.setattr(角度模式模块, "_fusion_precise_recognizer", FailedPreciseRecognizer(), raising=False)
    monkeypatch.setattr(角度模式模块, "_analyze_image_legacy", good_legacy)
    角度模式模块.reset_fusion_selector()

    result = 角度模式模块._analyze_image_fusion(
        np.zeros((193, 193, 3), dtype=np.uint8),
        [("FFFFFF", (255, 255, 255))], 45, 0, False, None, False,
    )

    assert result.observation_source == "legacy"
    assert result.fusion_difference is None
    assert result.precise_color is None
    assert result.precise_quality is None
    assert "精准三色测试错误" in result.precise_error
    assert result.text_error == result.precise_error
    assert result.legacy_error is None
    assert "精准三色 无效" in result.fusion_reason
    assert "TEXT" not in result.fusion_reason


def testfusion精准成功legacy失败时复用精准详情(monkeypatch) -> None:
    debug = np.full((5, 7, 3), 23, dtype=np.uint8)
    mask = np.full((5, 7), 255, dtype=np.uint8)

    class GoodPreciseRecognizer:
        最近错误 = None

        def reset(self):
            pass

        def 识别(self, image):
            return SimpleNamespace(
                angle=72.5,
                color="蓝色",
                confidence=0.91,
                details={
                    "origin": (4.0, 5.0),
                    "target": (6.0, 7.0),
                    "debug": debug,
                    "mask": mask,
                    "offset": (3, 4),
                    "color_hex": "95BBE8",
                },
            )

    def failed_legacy(*args, **kwargs):
        raise ValueError("Legacy测试错误")

    monkeypatch.setattr(角度模式模块, "_fusion_precise_recognizer", GoodPreciseRecognizer(), raising=False)
    monkeypatch.setattr(角度模式模块, "_analyze_image_legacy", failed_legacy)
    角度模式模块.reset_fusion_selector()

    result = 角度模式模块._analyze_image_fusion(
        np.zeros((240, 240, 3), dtype=np.uint8),
        [("FFFFFF", (255, 255, 255))], 45, 0, False, (10, 20, 203, 213), False,
    )

    assert result.angle == 72.5
    assert result.origin == (4.0, 5.0)
    assert result.target == (6.0, 7.0)
    assert result.debug is debug
    assert result.mask is mask
    assert result.offset == (13, 24)
    assert result.color_hex == "95BBE8"
    assert result.observation_source == "precise"
    assert result.precise_color == "蓝色"
    assert result.precise_quality == 0.91
    assert result.precise_error is None
    assert result.text_error is None
    assert "Legacy测试错误" in result.legacy_error
    assert result.fusion_difference is None
    assert result.fusion_reason == "Legacy 无效，采用 精准三色"


def testfusion两路均失败时错误明确使用精准三色名称(monkeypatch) -> None:
    class FailedPreciseRecognizer:
        最近错误 = "没有精准候选"

        def reset(self):
            pass

        def 识别(self, image):
            return None

    def failed_legacy(*args, **kwargs):
        raise ValueError("没有Legacy候选")

    monkeypatch.setattr(角度模式模块, "_fusion_precise_recognizer", FailedPreciseRecognizer(), raising=False)
    monkeypatch.setattr(角度模式模块, "_analyze_image_legacy", failed_legacy)
    角度模式模块.reset_fusion_selector()

    with pytest.raises(RuntimeError) as exc_info:
        角度模式模块._analyze_image_fusion(
            np.zeros((193, 193, 3), dtype=np.uint8),
            [("FFFFFF", (255, 255, 255))], 45, 0, False, None, False,
        )

    message = str(exc_info.value)
    assert "精准三色=没有精准候选" in message
    assert "Legacy=没有Legacy候选" in message
    assert "TEXT" not in message


def testfusion精准识别器惰性构造且复用实例(monkeypatch) -> None:
    getter = getattr(角度模式模块, "_get_fusion_precise_recognizer", None)
    assert callable(getter)

    import 三色精准角度

    created = []

    class FakePreciseRecognizer:
        pass

    def fake_factory():
        instance = FakePreciseRecognizer()
        created.append(instance)
        return instance

    monkeypatch.setattr(三色精准角度, "三色精准角度识别器", fake_factory)
    monkeypatch.setattr(角度模式模块, "_fusion_precise_recognizer", None)

    first = getter()
    second = getter()

    assert first is second
    assert created == [first]


def testlegacy和text模式分析不创建三色精准识别器(monkeypatch) -> None:
    def forbidden_getter():
        raise AssertionError("Legacy/TEXT模式不得创建三色精准识别器")

    legacy_result = object()
    text_result = object()
    monkeypatch.setattr(角度模式模块, "_get_fusion_precise_recognizer", forbidden_getter, raising=False)
    monkeypatch.setattr(角度模式模块, "_analyze_image_legacy", lambda *args, **kwargs: legacy_result)
    monkeypatch.setattr(角度模式模块, "_analyze_image_text", lambda *args, **kwargs: text_result)
    args = (np.zeros((10, 10, 3), dtype=np.uint8), [], 45, 0, False, None, False)

    角度模式模块.set_angle_mode("legacy")
    assert 角度模式模块.analyze_image(*args) is legacy_result
    角度模式模块.set_angle_mode("text")
    assert 角度模式模块.analyze_image(*args) is text_result
    角度模式模块.set_angle_mode("legacy")


def test进入fusion和重置只重置已存在精准实例且不触发加载(monkeypatch) -> None:
    monkeypatch.setattr(角度模式模块, "_fusion_selector", None)
    monkeypatch.setattr(角度模式模块, "_fusion_precise_recognizer", None, raising=False)

    角度模式模块.reset_fusion_selector()
    assert 角度模式模块._fusion_selector is None
    assert 角度模式模块._fusion_precise_recognizer is None
    assert 角度模式模块.set_angle_mode("fusion") == "fusion"
    assert 角度模式模块._fusion_selector is None
    assert 角度模式模块._fusion_precise_recognizer is None

    class ExistingResettable:
        def __init__(self):
            self.reset_count = 0

        def reset(self):
            self.reset_count += 1

    existing_selector = ExistingResettable()
    existing_precise = ExistingResettable()
    monkeypatch.setattr(角度模式模块, "_fusion_selector", existing_selector)
    monkeypatch.setattr(角度模式模块, "_fusion_precise_recognizer", existing_precise)

    角度模式模块.reset_fusion_selector()
    assert existing_selector.reset_count == 1
    assert existing_precise.reset_count == 1
    assert 角度模式模块.set_angle_mode("fusion") == "fusion"
    assert existing_selector.reset_count == 2
    assert existing_precise.reset_count == 2
    角度模式模块.set_angle_mode("legacy")


def testfusion低质量精准观测降级legacy并保留可读诊断(monkeypatch) -> None:
    class LowQualityPreciseRecognizer:
        最近错误 = None

        def reset(self):
            pass

        def 识别(self, image):
            return SimpleNamespace(
                angle=50.0,
                color="黄色",
                confidence=0.0975,
                details={"color_hex": "F0E791"},
            )

    def good_legacy(image, colors, tolerance, min_area, clean_mask, region, hsv_mode=False):
        return 角度模式模块.AnalysisResult(
            51.0, (13.0, 13.0), (14.0, 13.0), image.copy(),
            np.zeros(image.shape[:2], dtype=np.uint8), region[:2], "LEGACY"
        )

    monkeypatch.setattr(
        角度模式模块, "_fusion_precise_recognizer", LowQualityPreciseRecognizer()
    )
    monkeypatch.setattr(角度模式模块, "_analyze_image_legacy", good_legacy)
    monkeypatch.setattr(角度模式模块, "_fusion_selector", None)

    result = 角度模式模块._analyze_image_fusion(
        np.zeros((193, 193, 3), dtype=np.uint8),
        [("FFFFFF", (255, 255, 255))], 45, 0, False, None, False,
    )

    assert result.observation_source == "legacy"
    assert result.fusion_reason == "精准三色 无效，降级 Legacy"
    assert result.precise_color == "黄色"
    assert result.precise_quality == 0.0975
    assert "质量" in result.precise_error
    assert "0.0975" in result.precise_error
    assert "0.5" in result.precise_error
    assert result.text_error == result.precise_error
    assert result.fusion_difference == 1.0


@pytest.mark.parametrize(
    ("angle", "confidence", "error_fragment"),
    [
        (math.nan, 0.9, "角度非有限"),
        (50.0, math.inf, "质量非有限"),
    ],
)
def testfusion非有限精准观测降级legacy且不崩溃(
    monkeypatch, angle: float, confidence: float, error_fragment: str
) -> None:
    class NonFinitePreciseRecognizer:
        最近错误 = None

        def reset(self):
            pass

        def 识别(self, image):
            return SimpleNamespace(
                angle=angle,
                color="绿色",
                confidence=confidence,
                details={"color_hex": "9AE77E"},
            )

    def good_legacy(image, colors, tolerance, min_area, clean_mask, region, hsv_mode=False):
        return 角度模式模块.AnalysisResult(
            52.0, (13.0, 13.0), (14.0, 13.0), image.copy(),
            np.zeros(image.shape[:2], dtype=np.uint8), region[:2], "LEGACY"
        )

    monkeypatch.setattr(
        角度模式模块, "_fusion_precise_recognizer", NonFinitePreciseRecognizer()
    )
    monkeypatch.setattr(角度模式模块, "_analyze_image_legacy", good_legacy)
    monkeypatch.setattr(角度模式模块, "_fusion_selector", None)

    result = 角度模式模块._analyze_image_fusion(
        np.zeros((193, 193, 3), dtype=np.uint8),
        [("FFFFFF", (255, 255, 255))], 45, 0, False, None, False,
    )

    assert result.observation_source == "legacy"
    assert result.fusion_reason == "精准三色 无效，降级 Legacy"
    assert error_fragment in result.precise_error
    assert result.text_error == result.precise_error
