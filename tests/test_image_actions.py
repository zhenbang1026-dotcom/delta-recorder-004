from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from 识图动作 import 模板匹配器


def test_template_matcher_reads_chinese_path_and_returns_screen_center(tmp_path: Path) -> None:
    rng = np.random.default_rng(7)
    template = rng.integers(0, 256, (12, 16), dtype=np.uint8)
    frame = np.zeros((80, 100, 3), dtype=np.uint8)
    frame[20:32, 30:46] = cv2.cvtColor(template, cv2.COLOR_GRAY2BGR)
    template_path = tmp_path / "航空箱模板.png"
    ok, encoded = cv2.imencode(".png", template)
    assert ok
    encoded.tofile(template_path)
    matcher = 模板匹配器(
        区域函数=lambda: (100, 200, 200, 280),
        截图函数=lambda _bbox: (frame, "test"),
    )

    result = matcher.匹配一次(str(template_path), 0.95)

    assert result is not None
    assert result["中心X"] == 138
    assert result["中心Y"] == 226
    assert result["置信度"] >= 0.95
