from __future__ import annotations

import ast
import hashlib
import inspect
from pathlib import Path

import pytest

import A测试角度识别 as 角度模式模块


LEGACY_SOURCE_SHA256 = "8bdc995bca7e39bc6726391e497593085e725463e46b4a87afd873a35f3808ca"
TEXT_RAW_SOURCE_SHA256 = "d671fc85b4ec3b7d308fc102741d836e9e848bd8a533791aa6326454072bfecf"
TEXT_STABLE_SOURCE_SHA256 = "b46e5fb23e0dcc499721d818c66041987a8858b8ebb38ecc181c3b5b423f4876"
TEXT_DEFAULT_SOURCE_SHA256 = "1d0061da8d94f833ee1aa27e585dc20a27aefdf9622e1a28350900e394dcb7c8"


def _get_function_source(source_path: Path, function_name: str) -> str:
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    node = next(
        item
        for item in tree.body
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
        and item.name == function_name
    )
    start_lineno = min([node.lineno, *(item.lineno for item in node.decorator_list)])
    return "\n".join(source.splitlines()[start_lineno - 1 : node.end_lineno]) + "\n"


def test函数源码哈希包含装饰器(tmp_path: Path) -> None:
    source = "@decorator\ndef target():\n    return 1\n"
    source_path = tmp_path / "decorated.py"
    source_path.write_text(source, encoding="utf-8")

    function_source = _get_function_source(source_path, "target")

    assert hashlib.sha256(function_source.encode("utf-8")).hexdigest() == hashlib.sha256(
        source.encode("utf-8")
    ).hexdigest()


def testlegacy函数源码和默认模式roi不变() -> None:
    source_path = Path(inspect.getsourcefile(角度模式模块))
    function_source = _get_function_source(source_path, "_analyze_image_legacy")

    assert hashlib.sha256(function_source.encode("utf-8")).hexdigest() == LEGACY_SOURCE_SHA256
    角度模式模块.set_angle_mode("legacy")
    assert 角度模式模块.get_angle_mode() == "legacy"
    assert 角度模式模块.get_angle_bbox() == (119, 161, 146, 188)


def testtext关键函数源码冻结() -> None:
    source_path = Path(inspect.getsourcefile(角度模式模块))

    raw_source = _get_function_source(source_path, "_analyze_image_text_raw")
    stable_source = _get_function_source(source_path, "_analyze_image_text")
    default_source = _get_function_source(source_path.with_name("识别角度.py"), "默认识别器")

    assert hashlib.sha256(raw_source.encode("utf-8")).hexdigest() == TEXT_RAW_SOURCE_SHA256
    assert hashlib.sha256(stable_source.encode("utf-8")).hexdigest() == TEXT_STABLE_SOURCE_SHA256
    assert hashlib.sha256(default_source.encode("utf-8")).hexdigest() == TEXT_DEFAULT_SOURCE_SHA256


def test后端只保留legacy和text两种角度模式() -> None:
    assert 角度模式模块.normalize_angle_mode("legacy") == "legacy"
    assert 角度模式模块.normalize_angle_mode("text") == "text"
    assert set(角度模式模块.ANGLE_MODE_LABELS) == {"legacy", "text"}

    for removed_mode in ("fusion", "overall", "融合", "融合算法"):
        with pytest.raises(ValueError, match="未知角度模式"):
            角度模式模块.normalize_angle_mode(removed_mode)


def test两种模式标签和roi保持独立() -> None:
    assert 角度模式模块.set_angle_mode("text") == "text"
    assert 角度模式模块.get_angle_mode_label() == "原版 TEXT"
    assert 角度模式模块.get_angle_bbox() == (34, 78, 227, 271)

    assert 角度模式模块.set_angle_mode("legacy") == "legacy"
    assert 角度模式模块.get_angle_mode_label() == "Legacy 丝滑版"
    assert 角度模式模块.get_angle_bbox() == (119, 161, 146, 188)


def testadaptive_text滤波只平滑小抖动正常转向直接跟随() -> None:
    stabilizer = 角度模式模块._AngleStabilizer(alpha=0.5, smooth_threshold=4.0)

    assert stabilizer.update(100.0) == 100.0
    assert stabilizer.update(102.0) == 101.0
    assert stabilizer.update(121.0) == 121.0
    assert stabilizer.update(359.0) == 359.0
    wrapped = stabilizer.update(1.0)
    assert abs(角度模式模块._AngleStabilizer._delta(wrapped, 0.0)) < 1e-9


def testlegacy和text按当前模式分发且不存在第三分支(monkeypatch) -> None:
    legacy_result = object()
    text_result = object()
    monkeypatch.setattr(
        角度模式模块, "_analyze_image_legacy", lambda *args, **kwargs: legacy_result
    )
    monkeypatch.setattr(
        角度模式模块, "_analyze_image_text", lambda *args, **kwargs: text_result
    )
    args = (object(), [], 45, 0, False, None, False)

    角度模式模块.set_angle_mode("legacy")
    assert 角度模式模块.analyze_image(*args) is legacy_result
    角度模式模块.set_angle_mode("text")
    assert 角度模式模块.analyze_image(*args) is text_result
    角度模式模块.set_angle_mode("legacy")
