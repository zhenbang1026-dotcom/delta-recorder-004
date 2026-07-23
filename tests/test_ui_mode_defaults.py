from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _source(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8-sig")


def _radio_options(name: str) -> dict[str, str]:
    tree = ast.parse(_source(name), filename=name)
    options: dict[str, str] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Attribute) or node.func.attr != "Radiobutton":
            continue
        keywords = {item.arg: item.value for item in node.keywords if item.arg}
        value = keywords.get("value")
        text = keywords.get("text")
        if (
            isinstance(value, ast.Constant)
            and isinstance(value.value, str)
            and isinstance(text, ast.Constant)
            and isinstance(text.value, str)
        ):
            options[value.value] = text.value
    return options


def _assigned_stringvar_default(name: str, attribute: str) -> str | None:
    tree = ast.parse(_source(name), filename=name)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Attribute) or target.attr != attribute:
            continue
        call = node.value
        if not isinstance(call, ast.Call):
            continue
        for keyword in call.keywords:
            if keyword.arg == "value" and isinstance(keyword.value, ast.Constant):
                return keyword.value.value
    return None


def test_both_ui_entries_offer_fusion_as_third_angle_mode() -> None:
    for name in ("主界面.py", "自动录制坐标工具.py"):
        options = _radio_options(name)
        assert set(options) == {"legacy", "text", "fusion"}, (name, options)
        assert "Fusion" in options["fusion"]


def test_both_ui_entries_keep_legacy_as_default() -> None:
    for name in ("主界面.py", "自动录制坐标工具.py"):
        assert _assigned_stringvar_default(name, "angle_mode_var") == "legacy"


def test_backend_initialization_remains_forced_to_legacy() -> None:
    main_source = _source("主界面.py")
    recorder_source = _source("自动录制坐标工具.py")

    assert '识别模块.设置角度模式("legacy")' in main_source
    assert '角度模式="legacy"' in main_source
    assert '实时坐标角度识别器(角度模式="legacy")' in recorder_source


def test_readme_documents_three_modes_and_keeps_legacy_default() -> None:
    readme = _source("README.md")

    assert "三模式" in readme
    assert "legacy / text / fusion" in readme.lower()
    assert "默认" in readme and "Legacy" in readme


def test_readme_documents_text_calibration_and_fusion_control() -> None:
    readme = _source("README.md")

    assert "MAP" in readme and "校准" in readme
    assert "Fusion" in readme and "降级" in readme and "Legacy" in readme
    assert "TEXT/Fusion" in readme and "连续控制" in readme
