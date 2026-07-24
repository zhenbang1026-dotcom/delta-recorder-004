from __future__ import annotations

import sys
from types import SimpleNamespace

import numpy as np

import YOLO物资检测 as material_detection
from YOLO物资动作 import (
    物资检测区域客户区,
    letterbox_到模型输入,
    选择综合目标,
    还原检测框到原图,
)
from YOLO物资检测 import (
    创建近距离缩放画面,
    物资检测器,
    获取扩大物资检测区域屏幕坐标,
    还原近距离检测结果,
)


def test_close_range_frame_scales_to_55_percent_and_maps_boxes_back() -> None:
    frame = np.full((256, 448, 3), 255, dtype=np.uint8)

    scaled, transform = 创建近距离缩放画面(frame)

    scale_x, scale_y, pad_x, pad_y = transform
    assert scaled.shape == frame.shape
    assert scale_x == 246 / 448
    assert scale_y == 141 / 256
    assert (pad_x, pad_y) == (101, 57)
    assert np.all(scaled[0, 0] == 114)
    assert np.all(scaled[128, 224] == 255)

    detections = [
        {
            "类别ID": 1,
            "类别名称": "野外物资箱",
            "x1": pad_x + 40 * scale_x,
            "y1": pad_y + 20 * scale_y,
            "x2": pad_x + 200 * scale_x,
            "y2": pad_y + 100 * scale_y,
            "置信度": 0.88,
        }
    ]
    restored = 还原近距离检测结果(detections, transform, 500, 300, 448, 256)

    assert restored == [
        {
            "类别ID": 1,
            "类别名称": "野外物资箱",
            "x1": 540,
            "y1": 320,
            "x2": 700,
            "y2": 400,
            "宽度": 160,
            "高度": 80,
            "中心X": 620.0,
            "中心Y": 360.0,
            "置信度": 0.88,
        }
    ]


def test_detector_throttles_close_range_fallback_to_200ms(monkeypatch) -> None:
    now = [0.0]
    inference_calls = []
    post_results = iter(
        [
            [],
            [{"x1": 120, "y1": 70, "x2": 220, "y2": 150, "置信度": 0.9}],
            [],
            [],
            [{"x1": 120, "y1": 70, "x2": 220, "y2": 150, "置信度": 0.9}],
        ]
    )
    detector = object.__new__(物资检测器)
    detector.输入高度 = 256
    detector.输入宽度 = 448
    detector.执行器 = "CPU"
    detector.时钟 = lambda: now[0]
    detector.近距离检测间隔秒数 = 0.2
    detector._上次近距离检测时间 = -float("inf")
    detector._推理 = lambda tensor: inference_calls.append(tensor) or np.empty((1, 18, 2352))
    detector._后处理 = lambda *_args, **_kwargs: next(post_results)
    detector._日志 = lambda *_args, **_kwargs: None
    monkeypatch.setattr(
        material_detection.截图模块,
        "grab_bbox_bgr",
        lambda _bbox: (np.zeros((256, 448, 3), dtype=np.uint8), "test"),
    )

    assert detector.检测一次(500, 300, 948, 556)
    assert detector.最近检测模式 == "近距离"
    assert len(inference_calls) == 2

    now[0] = 0.1
    assert detector.检测一次(500, 300, 948, 556) == []
    assert detector.最近检测模式 == "正常"
    assert len(inference_calls) == 3

    now[0] = 0.2
    assert detector.检测一次(500, 300, 948, 556)
    assert detector.最近检测模式 == "近距离"
    assert len(inference_calls) == 5


def test_detector_skips_close_range_fallback_when_normal_detection_succeeds(monkeypatch) -> None:
    detector = object.__new__(物资检测器)
    detector.输入高度 = 256
    detector.输入宽度 = 448
    detector.执行器 = "CPU"
    detector.时钟 = lambda: 0.0
    detector.近距离检测间隔秒数 = 0.2
    detector._上次近距离检测时间 = -float("inf")
    inference_calls = []
    expected = [{"中心X": 724, "中心Y": 428, "置信度": 0.9}]
    detector._推理 = lambda tensor: inference_calls.append(tensor) or np.empty((1, 18, 2352))
    detector._后处理 = lambda *_args, **_kwargs: expected
    detector._日志 = lambda *_args, **_kwargs: None
    monkeypatch.setattr(
        material_detection.截图模块,
        "grab_bbox_bgr",
        lambda _bbox: (np.zeros((256, 448, 3), dtype=np.uint8), "test"),
    )

    assert detector.检测一次(500, 300, 948, 556) == expected
    assert detector.最近检测模式 == "正常"
    assert len(inference_calls) == 1


def test_material_roi_matches_tested_best_model_range() -> None:
    assert 物资检测区域客户区 == (504, 358, 952, 614)


def test_expanded_material_roi_is_center_80_percent_of_game_client(monkeypatch) -> None:
    fake_win32gui = SimpleNamespace(
        FindWindow=lambda *_args: 123,
        ClientToScreen=lambda _hwnd, _point: (100, 200),
        GetClientRect=lambda _hwnd: (0, 0, 1000, 800),
    )
    monkeypatch.setitem(sys.modules, "win32gui", fake_win32gui)

    assert 获取扩大物资检测区域屏幕坐标() == (200, 280, 1000, 920, 600.0, 600.0)


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
