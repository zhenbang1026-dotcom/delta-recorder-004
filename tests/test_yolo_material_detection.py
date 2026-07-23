from __future__ import annotations

import numpy as np

from YOLO物资动作 import (
    物资检测区域客户区,
    letterbox_到模型输入,
    选择综合目标,
    还原检测框到原图,
)


def test_material_roi_matches_tested_best_model_range() -> None:
    assert 物资检测区域客户区 == (504, 358, 952, 614)


def test_letterbox_keeps_aspect_ratio_and_restores_box() -> None:
    image = np.zeros((256, 448, 3), dtype=np.uint8)
    tensor, meta = letterbox_到模型输入(image, (256, 448))

    assert tensor.shape == (1, 3, 256, 448)
    assert tensor.dtype == np.float32

    box = (100.0, 40.0, 200.0, 140.0)
    transformed = meta.变换框(box)
    restored = meta.还原框(transformed)
    assert np.allclose(restored, box, atol=1e-5)


def test_target_selection_combines_confidence_and_center_distance() -> None:
    candidates = [
        {"中心X": 650, "中心Y": 480, "置信度": 0.88, "类别名称": "医疗包"},
        {"中心X": 730, "中心Y": 500, "置信度": 0.86, "类别名称": "航空箱"},
    ]

    target = 选择综合目标(candidates, center=(728, 486), confidence_threshold=0.5)

    assert target["类别名称"] == "航空箱"
