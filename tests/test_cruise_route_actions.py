from __future__ import annotations

from pathlib import Path

import 巡航脚本 as cruise
from 路线动作 import 路线动作, 路线点, 写入路线文件


def test_jsonl_route_keeps_actions_for_cruise(tmp_path: Path) -> None:
    path = tmp_path / "route.jsonl"
    comment = 路线动作("comment", {"text": "到达终点"})
    写入路线文件(path, [路线点(10, 20, 30.0, False, (comment,))])

    points = cruise.读取路径(str(path))

    assert len(points) == 1
    assert points[0].actions == (comment,)


def test_final_waypoint_actions_run_before_executor_stops(monkeypatch) -> None:
    comment = 路线动作("comment", {"text": "终点动作"})
    events: list[object] = []

    class Locator:
        def 读取状态(self):
            return 10, 20, 30.0

    class Executor:
        def 执行路线动作(self, actions):
            events.append(("actions", tuple(actions)))

        def 停止(self):
            events.append("stop")

    monkeypatch.setattr(cruise, "处理esc紧急停止", lambda _event=None: False)
    controller = cruise.巡航控制器(
        路径点列表=[cruise.路径点(10, 20, 30.0, False, (comment,))],
        定位器=Locator(),
        执行器=Executor(),
        到点阈值=3,
        参数=cruise.普通模式参数(),
        循环间隔=0.0,
    )

    controller.运行()

    assert events == [("actions", (comment,)), "stop"]
