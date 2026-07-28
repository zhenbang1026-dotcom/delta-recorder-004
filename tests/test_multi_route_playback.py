from __future__ import annotations

from pathlib import Path

import pytest

import 主界面 as main_ui
import 巡航脚本 as cruise
from 路线动作 import 路线动作, 路线点, 写入路线文件


def test_连续路线按文件顺序拼接并保留动作和分段信息(tmp_path: Path) -> None:
    first = tmp_path / "第一段.jsonl"
    second = tmp_path / "第二段.jsonl"
    comment = 路线动作("comment", {"text": "第一段终点"})
    写入路线文件(
        first,
        [
            路线点(0, 0, 10.0, False),
            路线点(10, 0, 20.0, False, (comment,)),
        ],
    )
    写入路线文件(
        second,
        [路线点(13, 0, 30.0, False), 路线点(20, 0, 40.0, False)],
    )

    points, segments = cruise.读取连续路径([str(first), str(second)])

    assert [(point.x, point.y) for point in points] == [(0, 0), (10, 0), (13, 0), (20, 0)]
    assert points[1].actions == (comment,)
    assert [
        (segment.路径, segment.起点索引, segment.终点索引)
        for segment in segments
    ] == [(str(first), 0, 1), (str(second), 2, 3)]
    connections = cruise.计算路线衔接距离(points, segments)
    assert [(item[0].路径, item[1].路径, item[2]) for item in connections] == [
        (str(first), str(second), 3)
    ]


def test_连续路线明确报告出错段和文件名(tmp_path: Path) -> None:
    valid = tmp_path / "正常.jsonl"
    broken = tmp_path / "损坏.jsonl"
    写入路线文件(valid, [路线点(0, 0, 0.0, False)])
    broken.write_text("{broken json\n", encoding="utf-8")

    with pytest.raises(ValueError, match=r"第 2/2 段.*损坏\.jsonl"):
        cruise.读取连续路径([str(valid), str(broken)])


def test_控制器通知当前段并在中间段终点执行对正(monkeypatch) -> None:
    progress = []
    aligned = []
    angles = iter([10.0, 42.0, 180.0])
    comment = 路线动作("comment", {"text": "动作后角度变化"})

    class Locator:
        def 读取状态(self):
            return 0, 0, next(angles)

    class Executor:
        def 执行(self, _action):
            pass

        def 执行路线动作(self, _actions):
            pass

        def 停止(self):
            pass

    segments = [
        cruise.路线段信息("第一段.jsonl", 0, 0),
        cruise.路线段信息("第二段.jsonl", 1, 1),
    ]
    monkeypatch.setattr(cruise, "处理esc紧急停止", lambda _event=None: False)
    controller = cruise.巡航控制器(
        路径点列表=[
            cruise.路径点(0, 0, 90.0, False, (comment,)),
            cruise.路径点(0, 0, 180.0, False),
        ],
        定位器=Locator(),
        执行器=Executor(),
        到点阈值=3,
        参数=cruise.普通模式参数(),
        循环间隔=0.0,
        路线段列表=segments,
        路线段回调=lambda index, total, path: progress.append((index, total, path)),
        中间段终点对正=True,
    )
    controller._执行动作终点对准 = lambda _point: (0, 0, 10.0)
    controller._执行终点对正 = lambda point, angle: aligned.append((point.angle, angle))

    controller.运行()

    assert progress == [(1, 2, "第一段.jsonl"), (2, 2, "第二段.jsonl")]
    assert aligned == [(90.0, 42.0)]


def test_路线队列保持顺序阻止重复并可上下移动() -> None:
    queue = main_ui.添加路线到队列([], ["A.jsonl", "B.jsonl", "A.jsonl"])

    assert queue == ["A.jsonl", "B.jsonl"]
    moved, selected = main_ui.移动路线队列项(queue, 1, -1)
    assert moved == ["B.jsonl", "A.jsonl"]
    assert selected == 0
    unchanged, selected = main_ui.移动路线队列项(moved, 0, -1)
    assert unchanged == moved
    assert selected == 0
