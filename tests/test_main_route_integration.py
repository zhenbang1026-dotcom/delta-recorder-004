from __future__ import annotations

import inspect
from types import SimpleNamespace

import 主界面 as main_ui
from 路线动作 import 路线动作


def test_route_list_includes_txt_and_jsonl(tmp_path, monkeypatch) -> None:
    routes = tmp_path / "routes"
    records = tmp_path / "records"
    routes.mkdir()
    records.mkdir()
    txt = routes / "old.txt"
    jsonl = records / "new.jsonl"
    txt.write_text("1,2\n", encoding="utf-8")
    jsonl.write_text("{}\n", encoding="utf-8")
    monkeypatch.setattr(main_ui, "ROUTES_DIR", routes)
    monkeypatch.setattr(main_ui, "RECORD_DIR", records)

    assert main_ui._list_route_files() == [txt, jsonl]


def test_q_anchor_keeps_snapshot_pose_and_action_order() -> None:
    actions = (
        路线动作("comment", {"text": "先开门"}),
        路线动作("wait", {"milliseconds": 500}),
    )
    state = SimpleNamespace(x=10, y=20, angle=123.5)

    point = main_ui.构建动作锚点(state, actions)

    assert (point.x, point.y, point.angle, point.自动路线) == (10, 20, 123.5, True)
    assert point.actions == actions


def test_回放区域提供可见路线队列和完整管理按钮() -> None:
    source = inspect.getsource(main_ui.合并主界面._build_ui)

    for text in (
        "路线播放队列",
        "加入队列",
        "批量浏览",
        "上移",
        "下移",
        "移除",
        "清空",
        "编辑选中",
    ):
        assert text in source
