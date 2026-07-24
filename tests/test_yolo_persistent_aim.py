from __future__ import annotations

import threading
from types import SimpleNamespace

from YOLO持续对准 import YOLO持续对准服务


class 假控制器:
    def __init__(self, _input, records, received, **_kwargs):
        self.records = records
        self.received = received
        self.stopped = False

    def 更新误差(self, dx, dy):
        self.records.append((dx, dy))
        self.received.set()
        return dx, dy

    def 停止(self):
        self.stopped = True


def test_persistent_service_detects_until_closed_and_can_pause_resume() -> None:
    records = []
    controllers = []
    received = threading.Event()

    def create_controller(input_module, **kwargs):
        controller = 假控制器(input_module, records, received, **kwargs)
        controllers.append(controller)
        return controller

    detector = SimpleNamespace(
        执行器="CPU",
        最近截图=None,
        检测一次=lambda *_args: [
            {"中心X": 130, "中心Y": 90, "置信度": 0.9, "类别名称": "医疗包"}
        ],
    )
    service = YOLO持续对准服务(
        object(),
        detector,
        lambda: (0, 0, 200, 200, 100, 100),
        YOLO对准控制器工厂=create_controller,
        检测间隔秒数=0.001,
    )
    params = {"confidence": 0.5, "tolerance_px": 12, "target_y_offset_px": 20}

    assert service.开启(params)
    assert received.wait(0.2)
    token = service.暂停()
    assert token == params
    assert not service.是否开启
    assert controllers[0].stopped
    assert (30.0, 10.0) in records

    received.clear()
    assert service.恢复(token)
    assert received.wait(0.2)
    service.关闭()
    assert not service.是否开启
    assert controllers[-1].stopped


def test_persistent_service_expands_search_after_one_second_and_restores_local_roi() -> None:
    records = []
    controllers = []
    finished = threading.Event()
    now = [0.0]
    calls = []
    local_roi = (0, 0, 200, 200, 100, 100)
    expanded_roi = (-300, -200, 500, 400, 100, 100)
    expanded_hits = [0]
    brought_into_local_roi = [False]

    def create_controller(input_module, **kwargs):
        controller = 假控制器(input_module, records, threading.Event(), **kwargs)
        controllers.append(controller)
        return controller

    def detect(left, top, right, bottom):
        roi = (left, top, right, bottom)
        calls.append((now[0], roi))
        now[0] += 0.25
        if roi == expanded_roi[:4]:
            expanded_hits[0] += 1
            if expanded_hits[0] == 2:
                return [{"中心X": 350, "中心Y": 90, "置信度": 0.9, "类别名称": "医疗包"}]
            if expanded_hits[0] == 3:
                brought_into_local_roi[0] = True
                return [{"中心X": 130, "中心Y": 90, "置信度": 0.9, "类别名称": "医疗包"}]
        elif brought_into_local_roi[0]:
            finished.set()
        return []

    detector = SimpleNamespace(执行器="CPU", 最近截图=None, 检测一次=detect)
    service = YOLO持续对准服务(
        object(),
        detector,
        lambda: local_roi,
        获取扩大检测区域=lambda: expanded_roi,
        YOLO对准控制器工厂=create_controller,
        检测间隔秒数=0.001,
        时钟=lambda: now[0],
    )

    assert service.开启({"confidence": 0.5, "tolerance_px": 12})
    assert finished.wait(0.2)
    service.关闭()

    expanded_calls = [(timestamp, roi) for timestamp, roi in calls if roi == expanded_roi[:4]]
    assert expanded_calls[0][0] >= 1.0
    assert expanded_calls[1][0] - expanded_calls[0][0] >= 0.5
    assert expanded_calls[2][0] - expanded_calls[1][0] < 0.5
    assert calls[calls.index(expanded_calls[2]) + 1][1] == local_roi[:4]
    assert (250.0, -10.0) in records
    assert (30.0, -10.0) in records
