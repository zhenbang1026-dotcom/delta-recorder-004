from __future__ import annotations

import pytest

from 角度融合 import 角度融合失败, 角度融合选择器, 角度观测


def _观测(angle: float, confidence: float = 0.9, source: str = "") -> 角度观测:
    return 角度观测(angle=angle, confidence=confidence, source=source)


def test一致时text为主观测且支持跨零角差() -> None:
    selector = 角度融合选择器()

    result = selector.update(_观测(359.0, source="text"), _观测(1.0, source="legacy"))

    assert result.source == "text"
    assert result.angle == 359.0


def test明显分歧时选择更接近预测角的观测() -> None:
    selector = 角度融合选择器()

    result = selector.update(
        _观测(120.0, source="text"),
        _观测(42.0, source="legacy"),
        predicted_angle=40.0,
    )

    assert result.source == "legacy"
    assert result.angle == 42.0


@pytest.mark.parametrize(
    ("text_angle", "legacy_angle", "predicted_angle"),
    [(120.0, 80.0, 100.0), (113.0, 99.0, 107.0)],
)
def testactive_text后分歧创新打平或优势不足必须选legacy(
    text_angle: float,
    legacy_angle: float,
    predicted_angle: float,
) -> None:
    selector = 角度融合选择器()
    assert selector.update(_观测(100.0), _观测(101.0)).source == "text"

    result = selector.update(
        _观测(text_angle),
        _观测(legacy_angle),
        predicted_angle=predicted_angle,
    )

    assert result.source == "legacy"


def testtext失败立即降级legacy但恢复需要连续三次确认() -> None:
    selector = 角度融合选择器(text_recovery_confirm=3)
    assert selector.update(_观测(100.0, source="text"), _观测(101.0, source="legacy")).source == "text"
    assert selector.update(None, _观测(105.0, source="legacy")).source == "legacy"

    assert selector.update(_观测(106.0, source="text"), _观测(106.5, source="legacy")).source == "legacy"
    assert selector.update(_观测(108.0, source="text"), _观测(108.5, source="legacy")).source == "legacy"
    assert selector.update(_观测(110.0, source="text"), _观测(110.5, source="legacy")).source == "text"


def test两路失败最多保持两次第三次抛错() -> None:
    selector = 角度融合选择器(hold_limit=2)
    selector.update(_观测(25.0, source="text"), None)

    first = selector.update(None, None)
    second = selector.update(None, None)

    assert (first.source, first.angle) == ("hold", 25.0)
    assert (second.source, second.angle) == ("hold", 25.0)
    with pytest.raises(角度融合失败):
        selector.update(None, None)


def test默认选择器两路失败立即抛错() -> None:
    selector = 角度融合选择器()
    selector.update(_观测(25.0, source="text"), None)

    with pytest.raises(角度融合失败):
        selector.update(None, None)


@pytest.mark.parametrize("hold_limit", [0, 2])
def test恢复计数遇双路失败必须清零并重新连续三帧(hold_limit: int) -> None:
    selector = 角度融合选择器(text_recovery_confirm=3, hold_limit=hold_limit)
    selector.update(_观测(100.0), _观测(101.0))
    selector.update(None, _观测(105.0))
    assert selector.update(_观测(106.0), _观测(106.5)).source == "legacy"
    assert selector.update(_观测(108.0), _观测(108.5)).source == "legacy"

    if hold_limit:
        assert selector.update(None, None).source == "hold"
    else:
        with pytest.raises(角度融合失败):
            selector.update(None, None)

    assert selector.update(_观测(110.0), _观测(110.5)).source == "legacy"
    assert selector.update(_观测(112.0), _观测(112.5)).source == "legacy"
    assert selector.update(_观测(114.0), _观测(114.5)).source == "text"


def test低置信观测视为失败且单路text仍可工作() -> None:
    selector = 角度融合选择器(min_confidence=0.5)

    result = selector.update(_观测(80.0, 0.9, "text"), _观测(82.0, 0.2, "legacy"))

    assert result.source == "text"
    assert result.angle == 80.0
