# -*- coding: utf-8 -*-
"""005 路线动作与路线文件格式。

旧项目路线仍是纯文本坐标；005 新路线使用一行一个 JSON 对象，便于动作
参数和中文注释安全保存，也便于以后增加 image_match 等动作类型。
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable


支持动作类型 = {"key", "wait", "comment", "view", "look", "yolo_interact"}


def _整数(值: Any, 名称: str, *, 最小值: int | None = None) -> int:
    if isinstance(值, bool):
        raise ValueError(f"{名称}必须是整数")
    try:
        结果 = int(值)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{名称}必须是整数") from exc
    if 最小值 is not None and 结果 < 最小值:
        raise ValueError(f"{名称}不能小于{最小值}")
    return 结果


@dataclass(frozen=True)
class 路线动作:
    类型: str
    参数: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "参数", dict(self.参数))

    def 校验(self) -> "路线动作":
        if self.类型 not in 支持动作类型:
            raise ValueError(f"不支持的路线动作类型: {self.类型}")
        p = self.参数
        if self.类型 == "key":
            keys = p.get("keys")
            if isinstance(keys, str):
                keys = [item.strip() for item in keys.split("+") if item.strip()]
            if not isinstance(keys, (list, tuple)) or not keys or not all(str(item).strip() for item in keys):
                raise ValueError("按键动作至少需要一个按键")
            if p.get("mode", "click") not in {"click", "hold"}:
                raise ValueError("按键动作模式必须是 click 或 hold")
            _整数(p.get("duration_ms", 50), "按键持续时间", 最小值=1)
        elif self.类型 == "wait":
            _整数(p.get("milliseconds", 0), "等待时间", 最小值=0)
        elif self.类型 == "comment":
            if not isinstance(p.get("text"), str) or not p["text"].strip():
                raise ValueError("注释内容不能为空")
        elif self.类型 == "view":
            angle = float(p.get("angle"))
            if not math.isfinite(angle) or not 0 <= angle < 360:
                raise ValueError("视角角度必须在 0 到 360 度之间")
        elif self.类型 == "look":
            if p.get("direction") not in {"down", "up"}:
                raise ValueError("低头/抬头方向无效")
            y_delta = _整数(p.get("y_delta"), "Y 位移")
            if p.get("direction") == "down" and y_delta <= 0:
                raise ValueError("低头的 Y 位移必须大于 0")
            if p.get("direction") == "up" and y_delta >= 0:
                raise ValueError("抬头的 Y 位移必须小于 0")
            _整数(p.get("duration_ms", 100), "低头/抬头持续时间", 最小值=1)
            _整数(p.get("x_random", 0), "X 随机范围", 最小值=0)
        elif self.类型 == "yolo_interact":
            confidence = float(p.get("confidence", 0.5))
            if not math.isfinite(confidence) or not 0 <= confidence <= 1:
                raise ValueError("置信度必须在 0 到 1 之间")
            _整数(p.get("timeout_ms", 5000), "YOLO 超时时间", 最小值=1)
            _整数(p.get("tolerance_px", 12), "对准容差", 最小值=1)
            _整数(p.get("initial_f_ms", 500), "首次 F 持续时间", 最小值=1)
            _整数(p.get("initial_wait_ms", 300), "首次 F 后等待时间", 最小值=0)
            repeat_ms = _整数(p.get("repeat_f_ms", 50), "循环 F 持续时间", 最小值=1)
            w_ms = _整数(p.get("w_duration_ms"), "W 持续时间", 最小值=1)
            count = _整数(p.get("f_count"), "循环 F 次数", 最小值=1)
            interval = _整数(p.get("f_interval_ms"), "循环 F 间隔", 最小值=repeat_ms)
            required = (count - 1) * interval + repeat_ms
            if w_ms < required:
                raise ValueError(f"W 持续时间不足，至少需要 {required}ms")
        return self

    def to_dict(self) -> dict[str, Any]:
        self.校验()
        return {"type": self.类型, **self.参数}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "路线动作":
        if not isinstance(data, dict):
            raise ValueError("动作必须是 JSON 对象")
        类型 = data.get("type") or data.get("类型")
        if not isinstance(类型, str):
            raise ValueError("动作缺少 type")
        参数 = {key: value for key, value in data.items() if key not in {"type", "类型"}}
        action = cls(类型, 参数)
        return action.校验()


@dataclass(frozen=True)
class 路线点:
    x: int
    y: int
    angle: float = 0.0
    自动路线: bool = False
    actions: tuple[路线动作, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "x", int(self.x))
        object.__setattr__(self, "y", int(self.y))
        object.__setattr__(self, "angle", float(self.angle))
        actions = tuple(self.actions)
        for action in actions:
            if not isinstance(action, 路线动作):
                raise ValueError("路线点 actions 必须全部是路线动作")
            action.校验()
        object.__setattr__(self, "actions", actions)

    def 替换动作(self, actions: Iterable[路线动作]) -> "路线点":
        return 路线点(self.x, self.y, self.angle, self.自动路线, tuple(actions))


def 写入路线文件(路径: str | Path, 路线点列表: Iterable[路线点]) -> Path:
    path = Path(路径)
    if path.suffix.lower() not in {".jsonl", ".json"}:
        raise ValueError("005 动作路线必须保存为 .jsonl")
    points = list(路线点列表)
    for point in points:
        if not isinstance(point, 路线点):
            raise ValueError("路线点列表包含无效对象")
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps({"version": 2, "type": "route"}, ensure_ascii=False, separators=(",", ":"))]
    for point in points:
        lines.append(
            json.dumps(
                {
                    "type": "point",
                    "x": point.x,
                    "y": point.y,
                    "angle": point.angle,
                    "auto": point.自动路线,
                    "actions": [action.to_dict() for action in point.actions],
                },
                ensure_ascii=False,
                separators=(",", ":"),
            )
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _读取旧文本(路径: Path) -> list[路线点]:
    内容 = 路径.read_text(encoding="utf-8-sig").splitlines()
    if not 内容 or all(not 行.strip() for 行 in 内容):
        raise ValueError("路径文件为空")
    结果: list[路线点] = []
    自动路线: bool | None = None
    for 行号, 行 in enumerate(内容, start=1):
        if not 行.strip():
            continue
        部分 = [项目.strip() for 项目 in 行.split(",")]
        if len(部分) not in (2, 3):
            raise ValueError(f"第{行号}行格式错误: {行}")
        当前自动 = len(部分) == 2
        if 自动路线 is None:
            自动路线 = 当前自动
        elif 自动路线 != 当前自动:
            raise ValueError(f"第{行号}行不能混用 x,y 和 x,y,角度 格式")
        try:
            x, y = int(部分[0]), int(部分[1])
            angle = 0.0 if 当前自动 else float(部分[2])
        except ValueError as exc:
            raise ValueError(f"第{行号}行格式错误: {行}") from exc
        结果.append(路线点(x, y, angle, 当前自动))
    return 结果


def 读取路线文件(路径: str | Path) -> list[路线点]:
    path = Path(路径)
    if path.suffix.lower() not in {".jsonl", ".json"}:
        return _读取旧文本(path)
    result: list[路线点] = []
    for line_no, raw in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), start=1):
        if not raw.strip():
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"第{line_no}行不是有效 JSON") from exc
        if data.get("type") in {"route", "meta"}:
            continue
        if data.get("type") != "point":
            raise ValueError(f"第{line_no}行不是 point")
        try:
            actions = tuple(路线动作.from_dict(item) for item in data.get("actions", []))
            result.append(
                路线点(
                    int(data["x"]),
                    int(data["y"]),
                    float(data.get("angle", 0.0)),
                    bool(data.get("auto", False)),
                    actions,
                )
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"第{line_no}行路线点格式错误") from exc
    if not result:
        raise ValueError("路径文件为空")
    return result
