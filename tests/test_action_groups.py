from __future__ import annotations

import 动作编辑器 as editor
import 路线动作 as route_model


def _wait(milliseconds: int, level: int = 0):
    action = route_model.路线动作("wait", {"milliseconds": milliseconds})
    return route_model.设置动作层级(action, level)


def test_动作层级写入字典并可完整恢复() -> None:
    child = _wait(500, 1)

    restored = route_model.路线动作.from_dict(child.to_dict())

    assert route_model.获取动作层级(restored) == 1
    assert restored.to_dict()["editor_level"] == 1


def test_右移成为上一动作子项且左移恢复顶层() -> None:
    actions = [_wait(100), _wait(200), _wait(300)]

    indented, selected = editor.调整动作层级(actions, 1, 1)

    assert selected == 1
    assert [route_model.获取动作层级(action) for action in indented] == [0, 1, 0]
    outdented, selected = editor.调整动作层级(indented, 1, -1)
    assert selected == 1
    assert [route_model.获取动作层级(action) for action in outdented] == [0, 0, 0]


def test_父项上下移动会携带全部子项() -> None:
    first = _wait(100)
    child = _wait(200, 1)
    second = _wait(300)

    moved, selected = editor.移动动作组([first, child, second], 0, 1)

    assert moved == [second, first, child]
    assert selected == 1


def test_子项只能在同一个父项内部上下移动() -> None:
    parent = _wait(100)
    child1 = _wait(200, 1)
    child2 = _wait(300, 1)
    other = _wait(400)

    moved, selected = editor.移动动作组([parent, child1, child2, other], 1, 1)
    assert moved == [parent, child2, child1, other]
    assert selected == 2
    unchanged, selected = editor.移动动作组(moved, 2, 1)
    assert unchanged == moved
    assert selected == 2


def test_动作块范围包含父项及连续子项() -> None:
    actions = [_wait(100), _wait(200, 1), _wait(300, 1), _wait(400)]

    assert editor.动作块范围(actions, 0) == (0, 3)
    assert editor.动作块范围(actions, 1) == (1, 2)
    assert editor.动作块范围(actions, 3) == (3, 4)


def test_命名代码块保存读取和删除(tmp_path) -> None:
    path = tmp_path / "动作代码块.json"
    actions = [_wait(100), _wait(200, 1)]

    editor.保存动作代码块("井盖交互", actions, path=path)
    blocks = editor.读取动作代码块(path=path)

    assert list(blocks) == ["井盖交互"]
    assert blocks["井盖交互"] == tuple(actions)
    editor.删除动作代码块("井盖交互", path=path)
    assert editor.读取动作代码块(path=path) == {}


def test_树形编号显示父项和子项() -> None:
    actions = [_wait(100), _wait(200, 1), _wait(300, 1), _wait(400)]

    assert editor.生成动作树编号(actions) == ["1", "1.1", "1.2", "2"]
