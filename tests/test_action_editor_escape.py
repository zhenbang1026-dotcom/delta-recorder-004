from __future__ import annotations

import inspect
from pathlib import Path

import 动作编辑器 as editor
from 路线动作 import 路线点


class FakeWindow:
    def __init__(self) -> None:
        self.bindings = {}

    def bind(self, sequence, callback):
        self.bindings[sequence] = callback


def test_escape_binding_runs_callback_and_stops_event_propagation() -> None:
    window = FakeWindow()
    calls = []

    editor.绑定Esc自动保存(window, lambda: calls.append("saved"))

    assert window.bindings["<Escape>"](object()) == "break"
    assert calls == ["saved"]


def test_all_action_editor_windows_bind_escape_to_their_existing_commit_callbacks() -> None:
    parameter_source = inspect.getsource(editor.动作参数窗口.__init__)
    action_list_source = inspect.getsource(editor.动作列表窗口.__init__)
    route_source = inspect.getsource(editor.路线编辑窗口.__init__)
    code_block_source = inspect.getsource(editor.动作列表窗口._打开代码块窗口)

    assert '绑定Esc自动保存(self.window, self._保存)' in parameter_source
    assert '绑定Esc自动保存(self.window, self._完成)' in action_list_source
    assert '绑定Esc自动保存(self.window, lambda: self._保存(确认覆盖=False))' in route_source
    assert '绑定Esc自动保存(dialog, insert)' in code_block_source
    assert '绑定Esc自动保存(dialog, close)' in code_block_source


def test_escape_route_editor_saves_txt_as_jsonl_without_confirmation(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "旧路线.txt"
    source.write_text("0,0\n", encoding="utf-8")
    saved = []
    closed = []
    writes = []
    editor_instance = object.__new__(editor.路线编辑窗口)
    editor_instance.source = source
    editor_instance.points = [路线点(1, 2, 3.0)]
    editor_instance.window = object()
    editor_instance._关闭 = lambda: closed.append(True)
    editor_instance.保存回调 = lambda path: saved.append(path)
    monkeypatch.setattr(editor, "写入路线文件", lambda path, points: writes.append((path, points)))
    monkeypatch.setattr(
        editor.messagebox,
        "askyesno",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("Esc 自动保存不应询问确认")),
    )

    editor_instance._保存(确认覆盖=False)

    target = source.with_suffix(".jsonl")
    assert writes == [(target, editor_instance.points)]
    assert saved == [target]
    assert closed == [True]
