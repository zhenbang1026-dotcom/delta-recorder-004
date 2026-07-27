# -*- coding: utf-8 -*-
from __future__ import annotations

from copy import deepcopy
import json
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import Callable, Iterable

from 路线动作 import (
    路线动作,
    路线点,
    获取动作层级,
    设置动作层级,
    读取路线文件,
    写入路线文件,
)
from 窗口定位 import 定位窗口到右下角


动作标签 = {
    "key": "键盘按键",
    "wait": "等待",
    "comment": "中文注释",
    "view": "恢复当前视角",
    "look": "低头 / 抬头",
    "yolo_interact": "YOLO 识别并交互",
    "yolo_aim_on": "YOLO 识别并对准开",
    "yolo_aim_off": "YOLO 识别并对准关",
    "yolo_aim_once": "YOLO 识别目标完全对准后退出",
    "image_wait_appear": "等待图片出现",
    "image_wait_disappear": "等待图片消失",
    "image_click": "识图点击",
}
标签动作 = {label: action_type for action_type, label in 动作标签.items()}
动作代码块文件 = Path(__file__).resolve().with_name("动作代码块.json")


def 动作块范围(actions: Iterable[路线动作], index: int) -> tuple[int, int]:
    """返回选中动作所在块的左闭右开范围；子项本身是单项块。"""
    items = list(actions)
    if not 0 <= index < len(items):
        raise IndexError("动作索引超出范围")
    if 获取动作层级(items[index]) == 1:
        return index, index + 1
    end = index + 1
    while end < len(items) and 获取动作层级(items[end]) == 1:
        end += 1
    return index, end


def 调整动作层级(
    actions: Iterable[路线动作], index: int, direction: int
) -> tuple[list[路线动作], int]:
    """将动作左移或右移一级，最多保留父子两层。"""
    items = list(actions)
    if direction not in {-1, 1}:
        raise ValueError("层级调整方向只能是 -1 或 1")
    if not 0 <= index < len(items):
        raise IndexError("动作索引超出范围")
    level = 获取动作层级(items[index])
    if direction == 1:
        if level == 1 or index == 0:
            return items, index
        items[index] = 设置动作层级(items[index], 1)
    elif level == 1:
        items[index] = 设置动作层级(items[index], 0)
    return items, index


def 移动动作组(
    actions: Iterable[路线动作], index: int, offset: int
) -> tuple[list[路线动作], int]:
    """移动父项及其子项；子项只能在同一父项内部排序。"""
    items = list(actions)
    if offset not in {-1, 1}:
        raise ValueError("移动方向只能是 -1 或 1")
    if not 0 <= index < len(items):
        raise IndexError("动作索引超出范围")

    if 获取动作层级(items[index]) == 1:
        target = index + offset
        if not 0 <= target < len(items) or 获取动作层级(items[target]) != 1:
            return items, index
        items[index], items[target] = items[target], items[index]
        return items, target

    start, end = 动作块范围(items, index)
    block = items[start:end]
    if offset == -1:
        if start == 0:
            return items, index
        previous_start = start - 1
        while previous_start > 0 and 获取动作层级(items[previous_start]) == 1:
            previous_start -= 1
        return items[:previous_start] + block + items[previous_start:start] + items[end:], previous_start

    if end >= len(items):
        return items, index
    _next_start, next_end = 动作块范围(items, end)
    next_block = items[end:next_end]
    moved = items[:start] + next_block + block + items[next_end:]
    return moved, start + len(next_block)


def 生成动作树编号(actions: Iterable[路线动作]) -> list[str]:
    numbers: list[str] = []
    parent_number = 0
    child_number = 0
    for action in actions:
        if 获取动作层级(action) == 0:
            parent_number += 1
            child_number = 0
            numbers.append(str(parent_number))
        else:
            child_number += 1
            numbers.append(f"{parent_number}.{child_number}")
    return numbers


def 读取动作代码块(path: str | Path = 动作代码块文件) -> dict[str, tuple[路线动作, ...]]:
    target = Path(path)
    if not target.exists():
        return {}
    try:
        data = json.loads(target.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise ValueError("动作代码块文件不是有效 JSON") from exc
    if not isinstance(data, dict):
        raise ValueError("动作代码块文件格式错误")
    raw_blocks = data.get("blocks", data)
    if not isinstance(raw_blocks, dict):
        raise ValueError("动作代码块列表格式错误")
    result: dict[str, tuple[路线动作, ...]] = {}
    for name, raw_actions in raw_blocks.items():
        if not isinstance(name, str) or not name.strip() or not isinstance(raw_actions, list):
            raise ValueError("动作代码块条目格式错误")
        actions = tuple(路线动作.from_dict(item) for item in raw_actions)
        if not actions:
            raise ValueError(f"动作代码块“{name}”不能为空")
        if 获取动作层级(actions[0]) == 1:
            actions = (设置动作层级(actions[0], 0), *actions[1:])
        result[name] = actions
    return result


def _写入动作代码块(
    blocks: dict[str, tuple[路线动作, ...]], path: str | Path
) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "version": 1,
        "blocks": {
            name: [action.to_dict() for action in actions]
            for name, actions in blocks.items()
        },
    }
    target.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def 保存动作代码块(
    name: str, actions: Iterable[路线动作], path: str | Path = 动作代码块文件
) -> None:
    normalized_name = str(name).strip()
    if not normalized_name:
        raise ValueError("代码块名称不能为空")
    block = tuple(deepcopy(list(actions)))
    if not block:
        raise ValueError("代码块至少需要一个动作")
    for action in block:
        action.校验()
    if 获取动作层级(block[0]) == 1:
        block = (设置动作层级(block[0], 0), *block[1:])
    blocks = 读取动作代码块(path)
    blocks[normalized_name] = block
    _写入动作代码块(blocks, path)


def 删除动作代码块(name: str, path: str | Path = 动作代码块文件) -> None:
    blocks = 读取动作代码块(path)
    blocks.pop(name, None)
    _写入动作代码块(blocks, path)


def _整数(value, name: str) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name}必须是整数") from exc


def _浮点数(value, name: str) -> float:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name}必须是数字") from exc


def _布尔值(value, name: str) -> bool:
    result = {"是": True, "否": False, "true": True, "false": False}.get(
        str(value).strip().lower()
    )
    if result is None:
        raise ValueError(f"{name}必须选择是或否")
    return result


def 从表单创建动作(action_type: str, values: dict[str, object]) -> 路线动作:
    if action_type == "key":
        keys = [part.strip().lower() for part in str(values.get("keys", "")).split("+") if part.strip()]
        mode = {"单击": "click", "长按": "hold", "click": "click", "hold": "hold"}.get(
            str(values.get("mode", "单击"))
        )
        action = 路线动作(
            "key",
            {
                "keys": keys,
                "mode": mode,
                "duration_ms": _整数(values.get("duration_ms"), "按键持续时间"),
                "repeat_count": _整数(values.get("repeat_count", 1), "执行次数"),
                "repeat_interval_ms": _整数(
                    values.get("repeat_interval_ms", 100), "每次弹起后间隔"
                ),
                "duration_jitter_minus_ms": _整数(
                    values.get("duration_jitter_minus_ms", 5), "按下时长随机减少"
                ),
                "duration_jitter_plus_ms": _整数(
                    values.get("duration_jitter_plus_ms", 20), "按下时长随机增加"
                ),
            },
        )
    elif action_type == "wait":
        action = 路线动作("wait", {"milliseconds": _整数(values.get("milliseconds"), "等待时间")})
    elif action_type == "comment":
        action = 路线动作("comment", {"text": str(values.get("text", "")).strip()})
    elif action_type == "view":
        action = 路线动作("view", {"angle": _浮点数(values.get("angle"), "视角角度")})
    elif action_type == "look":
        direction = {"低头": "down", "抬头": "up", "down": "down", "up": "up"}.get(
            str(values.get("direction", "低头"))
        )
        action = 路线动作(
            "look",
            {
                "direction": direction,
                "y_delta": _整数(values.get("y_delta"), "Y 位移"),
                "duration_ms": _整数(values.get("duration_ms"), "动作持续时间"),
                "x_random": _整数(values.get("x_random"), "X 随机范围"),
            },
        )
    elif action_type == "yolo_interact":
        action = 路线动作(
            "yolo_interact",
            {
                "angle": _浮点数(values.get("angle"), "视角角度"),
                "confidence": _浮点数(values.get("confidence"), "置信度"),
                "timeout_ms": _整数(values.get("timeout_ms"), "检测超时"),
                "tolerance_px": _整数(values.get("tolerance_px"), "对准容差"),
                "target_y_offset_px": _整数(
                    values.get("target_y_offset_px", 0), "容器垂直坐标偏差"
                ),
                "stable_frame_count": _整数(values.get("stable_frame_count", 3), "稳定帧数"),
                "target_class": str(values.get("target_class", "")).strip(),
                "initial_f_ms": _整数(values.get("initial_f_ms"), "首次 F 持续时间"),
                "initial_wait_ms": _整数(values.get("initial_wait_ms"), "首次 F 后等待"),
                "repeat_f_ms": _整数(values.get("repeat_f_ms"), "循环 F 持续时间"),
                "w_duration_ms": _整数(values.get("w_duration_ms"), "W 持续时间"),
                "f_count": _整数(values.get("f_count"), "循环 F 次数"),
                "f_interval_ms": _整数(values.get("f_interval_ms"), "循环 F 间隔"),
            },
        )
    elif action_type == "yolo_aim_on":
        action = 路线动作(
            "yolo_aim_on",
            {
                "angle": _浮点数(values.get("angle"), "视角角度"),
                "confidence": _浮点数(values.get("confidence"), "置信度"),
                "tolerance_px": _整数(values.get("tolerance_px"), "对准容差"),
                "target_y_offset_px": _整数(
                    values.get("target_y_offset_px", 0), "容器垂直坐标偏差"
                ),
                "target_class": str(values.get("target_class", "")).strip(),
            },
        )
    elif action_type == "yolo_aim_off":
        action = 路线动作("yolo_aim_off", {})
    elif action_type == "yolo_aim_once":
        action = 路线动作(
            "yolo_aim_once",
            {
                "angle": _浮点数(values.get("angle"), "视角角度"),
                "restore_view": _布尔值(values.get("restore_view", "是"), "恢复记录视角"),
                "confidence": _浮点数(values.get("confidence"), "置信度"),
                "timeout_ms": _整数(values.get("timeout_ms"), "检测超时"),
                "tolerance_px": _整数(values.get("tolerance_px"), "对准容差"),
                "target_y_offset_px": _整数(values.get("target_y_offset_px", 0), "目标 Y 偏移"),
                "stable_frame_count": _整数(values.get("stable_frame_count", 3), "稳定帧数"),
                "target_class": str(values.get("target_class", "")).strip(),
                "scan_enabled": _布尔值(values.get("scan_enabled", "是"), "多视角扫描"),
                "scan_step_degrees": _浮点数(values.get("scan_step_degrees", 8), "扫描视角步长"),
                "scan_attempts": _整数(values.get("scan_attempts", 4), "扫描次数"),
            },
        )
    elif action_type in {"image_wait_appear", "image_wait_disappear", "image_click"}:
        params = {
            "template_path": str(values.get("template_path", "")).strip(),
            "confidence": _浮点数(values.get("confidence", 0.85), "识图置信度"),
            "timeout_ms": _整数(values.get("timeout_ms", 5000), "识图超时"),
            "interval_ms": _整数(values.get("interval_ms", 100), "识图间隔"),
        }
        if action_type == "image_click":
            params.update(
                {
                    "click_offset_x": _整数(values.get("click_offset_x", 0), "点击 X 偏移"),
                    "click_offset_y": _整数(values.get("click_offset_y", 0), "点击 Y 偏移"),
                }
            )
        action = 路线动作(action_type, params)
    else:
        raise ValueError(f"不支持的动作类型: {action_type}")
    return action.校验()


def 动作摘要(action: 路线动作) -> str:
    p = action.参数
    if action.类型 == "key":
        mode = "长按" if p.get("mode") == "hold" else "单击"
        return (
            f"按键 {'+'.join(p.get('keys', []))}，{mode} {p.get('duration_ms', 50)}ms，"
            f"执行 {p.get('repeat_count', 1)} 次，间隔 {p.get('repeat_interval_ms', 100)}ms，"
            f"随机 -{p.get('duration_jitter_minus_ms', 0)}/+{p.get('duration_jitter_plus_ms', 0)}ms"
        )
    if action.类型 == "wait":
        return f"等待 {p.get('milliseconds', 0)}ms"
    if action.类型 == "comment":
        return f"注释：{p.get('text', '')}"
    if action.类型 == "view":
        return f"恢复水平视角 {float(p.get('angle', 0)):.2f}°"
    if action.类型 == "look":
        direction = "低头" if p.get("direction") == "down" else "抬头"
        return f"{direction} Y={p.get('y_delta')}px，X±{p.get('x_random', 0)}px，{p.get('duration_ms')}ms"
    if action.类型 == "yolo_aim_on":
        return (
            f"YOLO 持续对准开（视角 {float(p.get('angle', 0)):.2f}°，"
            f"容器Y偏差 {p.get('target_y_offset_px', 0)}px）"
        )
    if action.类型 == "yolo_aim_off":
        return "YOLO 持续对准关"
    if action.类型 == "yolo_aim_once":
        target_class = p.get("target_class") or "任意类别"
        view_summary = (
            f"恢复视角 {float(p.get('angle', 0)):.2f}°"
            if bool(p.get("restore_view", True))
            else "使用执行时当前视角"
        )
        return (
            f"YOLO 完全对准后退出（{target_class}，{view_summary}，"
            f"Y偏移 {p.get('target_y_offset_px', 0)}px，稳定 {p.get('stable_frame_count', 3)} 帧）"
        )
    if action.类型 in {"image_wait_appear", "image_wait_disappear", "image_click"}:
        label = 动作标签[action.类型]
        return f"{label}：{p.get('template_path', '')}，阈值 {float(p.get('confidence', 0.85)):.2f}"
    return (
        f"YOLO 对准（视角 {float(p.get('angle', 0)):.2f}°），W {p.get('w_duration_ms')}ms，"
        f"循环 F {p.get('f_count')} 次，容器Y偏差 {p.get('target_y_offset_px', 0)}px"
    )


表单字段 = {
    "key": [
        ("keys", "按键/组合键（用 + 分隔）", "f", None),
        ("mode", "方式", "单击", ("单击", "长按")),
        ("duration_ms", "按下时长（毫秒）", "50", None),
        ("repeat_count", "执行次数", "1", None),
        ("repeat_interval_ms", "每次弹起后间隔（毫秒）", "100", None),
        ("duration_jitter_minus_ms", "按下时长随机减少（毫秒）", "5", None),
        ("duration_jitter_plus_ms", "按下时长随机增加（毫秒）", "20", None),
    ],
    "wait": [("milliseconds", "等待时间（毫秒）", "500", None)],
    "comment": [("text", "中文注释", "", None)],
    "view": [("angle", "水平视角（度）", "0", None)],
    "look": [
        ("direction", "动作", "低头", ("低头", "抬头")),
        ("y_delta", "Y 位移（低头正、抬头负）", "300", None),
        ("duration_ms", "平滑移动时长（毫秒）", "300", None),
        ("x_random", "每步 X 随机范围（±像素）", "4", None),
    ],
    "yolo_interact": [
        ("angle", "先恢复水平视角（度）", "0", None),
        ("confidence", "置信度阈值", "0.50", None),
        ("timeout_ms", "识别/对准超时（毫秒）", "5000", None),
        ("tolerance_px", "X/Y 对准容差（像素）", "12", None),
        ("target_y_offset_px", "容器垂直坐标偏差（像素）", "0", None),
        ("stable_frame_count", "连续稳定帧数", "3", None),
        ("target_class", "目标类别（留空为任意）", "", None),
        ("initial_f_ms", "首次 F 持续时间（毫秒）", "200", None),
        ("initial_wait_ms", "首次 F 后等待（毫秒）", "300", None),
        ("w_duration_ms", "W 持续时间（毫秒）", "5000", None),
        ("f_count", "W 期间循环 F 次数", "5", None),
        ("f_interval_ms", "循环 F 启动间隔（毫秒）", "500", None),
        ("repeat_f_ms", "每次循环 F 持续（毫秒）", "50", None),
    ],
    "yolo_aim_on": [
        ("angle", "先恢复水平视角（度）", "0", None),
        ("confidence", "置信度阈值", "0.50", None),
        ("tolerance_px", "X/Y 对准容差（像素）", "12", None),
        ("target_y_offset_px", "容器垂直坐标偏差（像素）", "0", None),
        ("target_class", "目标类别（留空为任意）", "", None),
    ],
    "yolo_aim_off": [],
    "yolo_aim_once": [
        ("angle", "先恢复水平视角（度）", "0", None),
        ("restore_view", "恢复记录视角", "是", ("是", "否")),
        ("confidence", "置信度阈值", "0.50", None),
        ("timeout_ms", "识别/对准超时（毫秒）", "5000", None),
        ("tolerance_px", "完全对准容差（像素）", "12", None),
        ("target_y_offset_px", "目标垂直坐标偏差（像素）", "0", None),
        ("stable_frame_count", "连续稳定帧数", "3", None),
        ("target_class", "目标类别（留空为任意）", "", None),
        ("scan_enabled", "丢失时多视角扫描", "是", ("是", "否")),
        ("scan_step_degrees", "每次扫描角度（度）", "8", None),
        ("scan_attempts", "最多扫描次数", "4", None),
    ],
    "image_wait_appear": [
        ("template_path", "模板图片", "", None),
        ("confidence", "匹配阈值", "0.85", None),
        ("timeout_ms", "等待超时（毫秒）", "5000", None),
        ("interval_ms", "检测间隔（毫秒）", "100", None),
    ],
    "image_wait_disappear": [
        ("template_path", "模板图片", "", None),
        ("confidence", "匹配阈值", "0.85", None),
        ("timeout_ms", "等待超时（毫秒）", "5000", None),
        ("interval_ms", "检测间隔（毫秒）", "100", None),
    ],
    "image_click": [
        ("template_path", "模板图片", "", None),
        ("confidence", "匹配阈值", "0.85", None),
        ("timeout_ms", "识别超时（毫秒）", "5000", None),
        ("interval_ms", "检测间隔（毫秒）", "100", None),
        ("click_offset_x", "点击 X 偏移（像素）", "0", None),
        ("click_offset_y", "点击 Y 偏移（像素）", "0", None),
    ],
}


class 动作参数窗口:
    def __init__(
        self,
        parent,
        *,
        action: 路线动作 | None,
        获取当前角度: Callable[[], float],
        完成回调: Callable[[路线动作], None],
    ) -> None:
        self.parent = parent
        self.action = action
        self.获取当前角度 = 获取当前角度
        self.完成回调 = 完成回调
        self.window = tk.Toplevel(parent)
        self.window.title("编辑动作" if action else "添加动作")
        self.window.transient(parent)
        定位窗口到右下角(self.window, 620, 700, 参照窗口=parent)
        self.window.protocol("WM_DELETE_WINDOW", self._关闭)
        self.window.grab_set()

        outer = ttk.Frame(self.window, padding=12)
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text="动作类型").grid(row=0, column=0, sticky="w", pady=4)
        initial_type = action.类型 if action else "key"
        self.类型变量 = tk.StringVar(value=动作标签[initial_type])
        combo = ttk.Combobox(
            outer, textvariable=self.类型变量, values=list(标签动作), state="readonly", width=28
        )
        combo.grid(row=0, column=1, sticky="ew", pady=4)
        combo.bind("<<ComboboxSelected>>", self._重建表单)
        outer.columnconfigure(1, weight=1)
        self.form = ttk.Frame(outer)
        self.form.grid(row=1, column=0, columnspan=2, sticky="nsew", pady=(8, 0))
        self.字段变量: dict[str, tk.StringVar] = {}
        self._重建表单()

        buttons = ttk.Frame(outer)
        buttons.grid(row=2, column=0, columnspan=2, sticky="e", pady=(18, 0))
        ttk.Button(buttons, text="保存", command=self._保存, width=10).pack(side="left", padx=4)
        ttk.Button(buttons, text="取消", command=self._关闭, width=10).pack(side="left")

    def _现有值(self, action_type: str, key: str, default: str) -> str:
        if self.action is None or self.action.类型 != action_type:
            return f"{self.获取当前角度():.2f}" if key == "angle" else default
        value = self.action.参数.get(key, default)
        if key == "mode":
            return "长按" if value == "hold" else "单击"
        if key == "direction":
            return "低头" if value == "down" else "抬头"
        if key in {"restore_view", "scan_enabled"}:
            return "是" if bool(value) else "否"
        if key == "keys" and isinstance(value, (list, tuple)):
            return "+".join(str(item) for item in value)
        return str(value)

    def _重建表单(self, _event=None) -> None:
        for child in self.form.winfo_children():
            child.destroy()
        self.字段变量.clear()
        action_type = 标签动作[self.类型变量.get()]
        for row, (key, label, default, options) in enumerate(表单字段[action_type]):
            ttk.Label(self.form, text=label).grid(row=row, column=0, sticky="w", padx=(0, 12), pady=5)
            variable = tk.StringVar(value=self._现有值(action_type, key, default))
            self.字段变量[key] = variable
            if options:
                widget = ttk.Combobox(self.form, textvariable=variable, values=options, state="readonly")
            else:
                widget = ttk.Entry(self.form, textvariable=variable)
            widget.grid(row=row, column=1, sticky="ew", pady=5)
            if key == "angle":
                ttk.Button(self.form, text="记录当前视角", command=self._记录当前视角).grid(
                    row=row, column=2, padx=(6, 0), pady=5
                )
            elif key == "template_path":
                ttk.Button(self.form, text="选择图片", command=self._选择模板图片).grid(
                    row=row, column=2, padx=(6, 0), pady=5
                )
        self.form.columnconfigure(1, weight=1)
        self.action = None

    def _记录当前视角(self) -> None:
        self.字段变量["angle"].set(f"{self.获取当前角度():.2f}")

    def _选择模板图片(self) -> None:
        selected = filedialog.askopenfilename(
            parent=self.window,
            title="选择识图模板",
            filetypes=[("图片", "*.png *.jpg *.jpeg *.bmp"), ("所有文件", "*.*")],
        )
        if selected:
            self.字段变量["template_path"].set(selected)

    def _保存(self) -> None:
        try:
            action = 从表单创建动作(
                标签动作[self.类型变量.get()],
                {key: variable.get() for key, variable in self.字段变量.items()},
            )
        except ValueError as exc:
            messagebox.showerror("参数错误", str(exc), parent=self.window)
            return
        self._关闭()
        self.完成回调(action)

    def _关闭(self) -> None:
        try:
            self.window.grab_release()
        except tk.TclError:
            pass
        self.window.destroy()
        try:
            self.parent.grab_set()
        except tk.TclError:
            pass


class 动作列表窗口:
    动作剪贴板: list[路线动作] = []

    def __init__(
        self,
        parent,
        *,
        actions: Iterable[路线动作] = (),
        获取当前角度: Callable[[], float],
        完成回调: Callable[[tuple[路线动作, ...]], None],
        取消回调: Callable[[], None] | None = None,
        测试回调: Callable[[路线动作 | tuple[路线动作, ...]], None] | None = None,
        title: str = "路线动作",
    ) -> None:
        self.parent = parent
        self.actions = list(actions)
        self.获取当前角度 = 获取当前角度
        self.完成回调 = 完成回调
        self.取消回调 = 取消回调
        self.测试回调 = 测试回调
        self.window = tk.Toplevel(parent)
        self.window.title(title)
        self.window.transient(parent)
        定位窗口到右下角(self.window, 980, 560, 参照窗口=parent)
        self.window.protocol("WM_DELETE_WINDOW", self._取消)
        self.window.grab_set()

        outer = ttk.Frame(self.window, padding=12)
        outer.pack(fill="both", expand=True)
        ttk.Label(
            outer,
            text="动作按树形列表从上到下执行；父项可折叠，移动、复制、删除和测试会包含其子项。",
        ).pack(anchor="w")
        tree_frame = ttk.Frame(outer)
        tree_frame.pack(fill="both", expand=True, pady=8)
        self.listbox = ttk.Treeview(tree_frame, show="tree", selectmode="browse", height=15)
        scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=self.listbox.yview)
        self.listbox.configure(yscrollcommand=scrollbar.set)
        self.listbox.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self._tree_index_by_item: dict[str, int] = {}
        self.window.bind("<Control-c>", self._复制快捷键)
        self.window.bind("<Control-v>", self._粘贴快捷键)

        buttons = ttk.Frame(outer)
        buttons.pack(fill="x")
        for text, command in (
            ("添加", self._添加),
            ("编辑", self._编辑),
            ("复制", self._复制),
            ("粘贴", self._粘贴),
            ("删除", self._删除),
            ("上移", lambda: self._移动(-1)),
            ("下移", lambda: self._移动(1)),
            ("左移", lambda: self._调整层级(-1)),
            ("右移", lambda: self._调整层级(1)),
        ):
            ttk.Button(buttons, text=text, command=command, width=9).pack(side="left", padx=(0, 5))

        block_buttons = ttk.Frame(outer)
        block_buttons.pack(fill="x", pady=(8, 0))
        ttk.Button(block_buttons, text="保存代码块", command=self._保存代码块, width=12).pack(
            side="left", padx=(0, 5)
        )
        ttk.Button(block_buttons, text="插入代码块", command=self._插入代码块, width=12).pack(
            side="left", padx=(0, 5)
        )
        ttk.Button(block_buttons, text="管理代码块", command=self._管理代码块, width=12).pack(
            side="left", padx=(0, 5)
        )
        if self.测试回调 is not None:
            ttk.Button(block_buttons, text="测试选中动作/组", command=self._测试, width=16).pack(
                side="left", padx=(4, 0)
            )
        ttk.Button(block_buttons, text="完成", command=self._完成, width=10).pack(side="right")
        ttk.Button(block_buttons, text="取消", command=self._取消, width=10).pack(
            side="right", padx=5
        )
        self._刷新()

    def _选中索引(self) -> int | None:
        if hasattr(self.listbox, "selection"):
            selected = self.listbox.selection()
            if not selected:
                return None
            item = str(selected[0])
            index_by_item = getattr(self, "_tree_index_by_item", {})
            if item in index_by_item:
                return index_by_item[item]
            if item.startswith("action-"):
                return int(item.removeprefix("action-"))
            return None
        selected = self.listbox.curselection()
        return int(selected[0]) if selected else None

    def _刷新(self, select: int | None = None) -> None:
        children = self.listbox.get_children()
        if children:
            self.listbox.delete(*children)
        self._tree_index_by_item.clear()
        numbers = 生成动作树编号(self.actions)
        parent_item = ""
        item_by_index: dict[int, str] = {}
        for index, (action, number) in enumerate(zip(self.actions, numbers)):
            level = 获取动作层级(action)
            if level == 0 or not parent_item:
                item = self.listbox.insert(
                    "", "end", iid=f"action-{index}", text=f"{number}. {动作摘要(action)}", open=True
                )
                parent_item = item
            else:
                item = self.listbox.insert(
                    parent_item,
                    "end",
                    iid=f"action-{index}",
                    text=f"{number}. {动作摘要(action)}",
                )
            self._tree_index_by_item[item] = index
            item_by_index[index] = item
        if select is not None and self.actions:
            select = max(0, min(select, len(self.actions) - 1))
            item = item_by_index[select]
            self.listbox.selection_set(item)
            self.listbox.focus(item)
            self.listbox.see(item)

    def _添加(self) -> None:
        动作参数窗口(
            self.window,
            action=None,
            获取当前角度=self.获取当前角度,
            完成回调=lambda action: self._追加(action),
        )

    def _追加(self, action: 路线动作) -> None:
        self.actions.append(action)
        self._刷新(len(self.actions) - 1)

    def _编辑(self) -> None:
        index = self._选中索引()
        if index is None:
            messagebox.showinfo("提示", "请先选择一个动作", parent=self.window)
            return
        动作参数窗口(
            self.window,
            action=self.actions[index],
            获取当前角度=self.获取当前角度,
            完成回调=lambda action, i=index: self._替换(i, action),
        )

    def _替换(self, index: int, action: 路线动作) -> None:
        self.actions[index] = 设置动作层级(action, 获取动作层级(self.actions[index]))
        self._刷新(index)

    def _复制(self) -> None:
        index = self._选中索引()
        if index is None:
            messagebox.showinfo("提示", "请先选择一个动作", parent=self.window)
            return
        start, end = 动作块范围(self.actions, index)
        type(self).动作剪贴板 = deepcopy(self.actions[start:end])

    def _插入动作序列(self, actions: Iterable[路线动作]) -> None:
        copied = deepcopy(list(actions))
        if not copied:
            return
        index = self._选中索引()
        if index is None:
            insert_at = len(self.actions)
        else:
            _start, insert_at = 动作块范围(self.actions, index)
            if 获取动作层级(copied[0]) == 0 and 获取动作层级(self.actions[index]) == 1:
                parent_index = index - 1
                while parent_index > 0 and 获取动作层级(self.actions[parent_index]) == 1:
                    parent_index -= 1
                _parent_start, insert_at = 动作块范围(self.actions, parent_index)
        if (insert_at == 0 or not self.actions) and 获取动作层级(copied[0]) == 1:
            copied[0] = 设置动作层级(copied[0], 0)
        self.actions[insert_at:insert_at] = copied
        self._刷新(insert_at)

    def _粘贴(self) -> None:
        if not type(self).动作剪贴板:
            messagebox.showinfo("提示", "动作剪贴板为空，请先复制动作", parent=self.window)
            return
        self._插入动作序列(type(self).动作剪贴板)

    def _复制快捷键(self, _event=None) -> str:
        self._复制()
        return "break"

    def _粘贴快捷键(self, _event=None) -> str:
        self._粘贴()
        return "break"

    def _测试(self) -> None:
        index = self._选中索引()
        if index is None:
            messagebox.showinfo("提示", "请先选择一个动作", parent=self.window)
            return
        if self.测试回调 is not None:
            start, end = 动作块范围(self.actions, index)
            block = tuple(self.actions[start:end])
            self.测试回调(block if len(block) > 1 else block[0])

    def _删除(self) -> None:
        index = self._选中索引()
        if index is None:
            return
        start, end = 动作块范围(self.actions, index)
        if end - start > 1 and not messagebox.askyesno(
            "删除动作组",
            f"该父项包含 {end - start - 1} 个子项，确定删除整个动作组吗？",
            parent=self.window,
        ):
            return
        del self.actions[start:end]
        self._刷新(start)

    def _移动(self, offset: int) -> None:
        index = self._选中索引()
        if index is None:
            return
        self.actions, selected = 移动动作组(self.actions, index, offset)
        self._刷新(selected)

    def _调整层级(self, direction: int) -> None:
        index = self._选中索引()
        if index is None:
            return
        self.actions, selected = 调整动作层级(self.actions, index, direction)
        self._刷新(selected)

    def _保存代码块(self) -> None:
        index = self._选中索引()
        if index is None:
            messagebox.showinfo("提示", "请先选择要保存的动作或动作组", parent=self.window)
            return
        name = simpledialog.askstring("保存代码块", "请输入代码块名称：", parent=self.window)
        if name is None or not name.strip():
            return
        try:
            blocks = 读取动作代码块()
            normalized_name = name.strip()
            if normalized_name in blocks and not messagebox.askyesno(
                "覆盖代码块",
                f"代码块“{normalized_name}”已存在，确定覆盖吗？",
                parent=self.window,
            ):
                return
            start, end = 动作块范围(self.actions, index)
            保存动作代码块(normalized_name, self.actions[start:end])
        except (OSError, ValueError) as exc:
            messagebox.showerror("保存失败", str(exc), parent=self.window)
            return
        messagebox.showinfo("保存成功", f"已保存代码块“{normalized_name}”", parent=self.window)

    def _插入代码块(self) -> None:
        self._打开代码块窗口(允许删除=False)

    def _管理代码块(self) -> None:
        self._打开代码块窗口(允许删除=True)

    def _打开代码块窗口(self, *, 允许删除: bool) -> None:
        try:
            blocks = 读取动作代码块()
        except (OSError, ValueError) as exc:
            messagebox.showerror("读取失败", str(exc), parent=self.window)
            return
        if not blocks:
            messagebox.showinfo("代码块", "还没有保存的动作代码块", parent=self.window)
            return

        dialog = tk.Toplevel(self.window)
        dialog.title("管理动作代码块" if 允许删除 else "插入动作代码块")
        dialog.transient(self.window)
        定位窗口到右下角(dialog, 480, 360, 参照窗口=self.window)
        dialog.grab_set()
        outer = ttk.Frame(dialog, padding=12)
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text="双击名称或选中后点击插入。代码块会插入到当前选中动作块之后。").pack(
            anchor="w"
        )
        names = tk.Listbox(outer)
        names.pack(fill="both", expand=True, pady=8)

        def refresh() -> None:
            names.delete(0, "end")
            for block_name in blocks:
                names.insert("end", block_name)

        def selected_name() -> str | None:
            selected = names.curselection()
            return str(names.get(selected[0])) if selected else None

        def close() -> None:
            try:
                dialog.grab_release()
            except tk.TclError:
                pass
            dialog.destroy()
            try:
                self.window.grab_set()
            except tk.TclError:
                pass

        def insert(_event=None) -> None:
            name = selected_name()
            if name is None:
                messagebox.showinfo("提示", "请先选择代码块", parent=dialog)
                return
            self._插入动作序列(blocks[name])
            close()

        def delete() -> None:
            name = selected_name()
            if name is None:
                messagebox.showinfo("提示", "请先选择代码块", parent=dialog)
                return
            if not messagebox.askyesno("删除代码块", f"确定删除“{name}”吗？", parent=dialog):
                return
            try:
                删除动作代码块(name)
            except (OSError, ValueError) as exc:
                messagebox.showerror("删除失败", str(exc), parent=dialog)
                return
            blocks.pop(name, None)
            if not blocks:
                close()
                return
            refresh()

        names.bind("<Double-Button-1>", insert)
        controls = ttk.Frame(outer)
        controls.pack(fill="x")
        ttk.Button(controls, text="插入", command=insert, width=10).pack(side="left")
        if 允许删除:
            ttk.Button(controls, text="删除", command=delete, width=10).pack(
                side="left", padx=(6, 0)
            )
        ttk.Button(controls, text="关闭", command=close, width=10).pack(side="right")
        dialog.protocol("WM_DELETE_WINDOW", close)
        refresh()
        names.selection_set(0)

    def _关闭(self) -> None:
        try:
            self.window.grab_release()
        except tk.TclError:
            pass
        self.window.destroy()
        if isinstance(self.parent, tk.Toplevel):
            try:
                self.parent.grab_set()
            except tk.TclError:
                pass

    def _完成(self) -> None:
        result = tuple(self.actions)
        self._关闭()
        self.完成回调(result)

    def _取消(self) -> None:
        self._关闭()
        if self.取消回调 is not None:
            self.取消回调()


class 路线编辑窗口:
    def __init__(
        self,
        parent,
        source: str | Path,
        *,
        保存回调: Callable[[Path], None],
        测试回调: Callable[[路线动作], None] | None = None,
    ) -> None:
        self.parent = parent
        self.source = Path(source)
        self.points = 读取路线文件(self.source)
        self.保存回调 = 保存回调
        self.测试回调 = 测试回调
        self.window = tk.Toplevel(parent)
        self.window.title("编辑已保存路线动作（坐标只读）")
        self.window.transient(parent)
        定位窗口到右下角(self.window, 820, 540, 参照窗口=parent)
        self.window.protocol("WM_DELETE_WINDOW", self._关闭)
        self.window.grab_set()

        outer = ttk.Frame(self.window, padding=12)
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text=f"文件：{self.source}").pack(anchor="w")
        ttk.Label(outer, text="坐标点只读；选择路线点后可编辑该点的动作。", foreground="#555555").pack(anchor="w")
        self.listbox = tk.Listbox(outer)
        self.listbox.pack(fill="both", expand=True, pady=8)
        buttons = ttk.Frame(outer)
        buttons.pack(fill="x")
        ttk.Button(buttons, text="编辑选中点动作", command=self._编辑动作, width=18).pack(side="left")
        ttk.Button(buttons, text="保存路线", command=self._保存, width=12).pack(side="right")
        ttk.Button(buttons, text="取消", command=self._关闭, width=10).pack(side="right", padx=6)
        self._刷新(0)

    def _刷新(self, select: int | None = None) -> None:
        self.listbox.delete(0, "end")
        for index, point in enumerate(self.points, start=1):
            self.listbox.insert(
                "end",
                f"{index:04d}  x={point.x}, y={point.y}, angle={point.angle:.2f}°  |  动作 {len(point.actions)} 个",
            )
        if select is not None and self.points:
            self.listbox.selection_set(select)
            self.listbox.see(select)

    def _编辑动作(self) -> None:
        selected = self.listbox.curselection()
        if not selected:
            messagebox.showinfo("提示", "请先选择一个路线点", parent=self.window)
            return
        index = int(selected[0])
        point = self.points[index]
        动作列表窗口(
            self.window,
            actions=point.actions,
            获取当前角度=lambda p=point: p.angle,
            完成回调=lambda actions, i=index: self._替换动作(i, actions),
            测试回调=self.测试回调,
            title=f"编辑第 {index + 1} 个路线点动作",
        )

    def _替换动作(self, index: int, actions: tuple[路线动作, ...]) -> None:
        self.points[index] = self.points[index].替换动作(actions)
        self._刷新(index)

    def _保存(self) -> None:
        target = self.source
        if self.source.suffix.lower() not in {".jsonl", ".json"}:
            selected = filedialog.asksaveasfilename(
                parent=self.window,
                title="旧 TXT 另存为 005 JSONL 路线",
                initialdir=str(self.source.parent),
                initialfile=self.source.with_suffix(".jsonl").name,
                defaultextension=".jsonl",
                filetypes=[("005 JSONL 路线", "*.jsonl")],
            )
            if not selected:
                return
            target = Path(selected)
            if target.exists() and not messagebox.askyesno(
                "确认覆盖", f"目标 JSONL 已存在，确定覆盖？\n{target}", parent=self.window
            ):
                return
        elif not messagebox.askyesno("确认覆盖", f"确定覆盖保存？\n{target}", parent=self.window):
            return
        try:
            写入路线文件(target, self.points)
        except (OSError, ValueError) as exc:
            messagebox.showerror("保存失败", str(exc), parent=self.window)
            return
        self._关闭()
        self.保存回调(target)

    def _关闭(self) -> None:
        try:
            self.window.grab_release()
        except tk.TclError:
            pass
        self.window.destroy()
