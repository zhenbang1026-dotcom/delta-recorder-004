# -*- coding: utf-8 -*-
from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Callable, Iterable

from 路线动作 import 路线动作, 路线点, 读取路线文件, 写入路线文件


动作标签 = {
    "key": "键盘按键",
    "wait": "等待",
    "comment": "中文注释",
    "view": "恢复当前视角",
    "look": "低头 / 抬头",
    "yolo_interact": "YOLO 识别并交互",
}
标签动作 = {label: action_type for action_type, label in 动作标签.items()}


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


def 从表单创建动作(action_type: str, values: dict[str, object]) -> 路线动作:
    if action_type == "key":
        keys = [part.strip().lower() for part in str(values.get("keys", "")).split("+") if part.strip()]
        mode = {"单击": "click", "长按": "hold", "click": "click", "hold": "hold"}.get(
            str(values.get("mode", "单击"))
        )
        action = 路线动作(
            "key",
            {"keys": keys, "mode": mode, "duration_ms": _整数(values.get("duration_ms"), "按键持续时间")},
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
                "initial_f_ms": _整数(values.get("initial_f_ms"), "首次 F 持续时间"),
                "initial_wait_ms": _整数(values.get("initial_wait_ms"), "首次 F 后等待"),
                "repeat_f_ms": _整数(values.get("repeat_f_ms"), "循环 F 持续时间"),
                "w_duration_ms": _整数(values.get("w_duration_ms"), "W 持续时间"),
                "f_count": _整数(values.get("f_count"), "循环 F 次数"),
                "f_interval_ms": _整数(values.get("f_interval_ms"), "循环 F 间隔"),
            },
        )
    else:
        raise ValueError(f"不支持的动作类型: {action_type}")
    return action.校验()


def 动作摘要(action: 路线动作) -> str:
    p = action.参数
    if action.类型 == "key":
        mode = "长按" if p.get("mode") == "hold" else "单击"
        return f"按键 {'+'.join(p.get('keys', []))}，{mode} {p.get('duration_ms', 50)}ms"
    if action.类型 == "wait":
        return f"等待 {p.get('milliseconds', 0)}ms"
    if action.类型 == "comment":
        return f"注释：{p.get('text', '')}"
    if action.类型 == "view":
        return f"恢复水平视角 {float(p.get('angle', 0)):.2f}°"
    if action.类型 == "look":
        direction = "低头" if p.get("direction") == "down" else "抬头"
        return f"{direction} Y={p.get('y_delta')}px，X±{p.get('x_random', 0)}px，{p.get('duration_ms')}ms"
    return (
        f"YOLO 对准（视角 {float(p.get('angle', 0)):.2f}°），W {p.get('w_duration_ms')}ms，"
        f"循环 F {p.get('f_count')} 次"
    )


表单字段 = {
    "key": [
        ("keys", "按键/组合键（用 + 分隔）", "f", None),
        ("mode", "方式", "单击", ("单击", "长按")),
        ("duration_ms", "按下时长（毫秒）", "50", None),
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
        ("initial_f_ms", "首次 F 持续时间（毫秒）", "500", None),
        ("initial_wait_ms", "首次 F 后等待（毫秒）", "300", None),
        ("w_duration_ms", "W 持续时间（毫秒）", "5000", None),
        ("f_count", "W 期间循环 F 次数", "5", None),
        ("f_interval_ms", "循环 F 启动间隔（毫秒）", "500", None),
        ("repeat_f_ms", "每次循环 F 持续（毫秒）", "50", None),
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
        self.window.geometry("600x560")
        self.window.transient(parent)
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
        self.form.columnconfigure(1, weight=1)
        self.action = None

    def _记录当前视角(self) -> None:
        self.字段变量["angle"].set(f"{self.获取当前角度():.2f}")

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
    def __init__(
        self,
        parent,
        *,
        actions: Iterable[路线动作] = (),
        获取当前角度: Callable[[], float],
        完成回调: Callable[[tuple[路线动作, ...]], None],
        取消回调: Callable[[], None] | None = None,
        title: str = "路线动作",
    ) -> None:
        self.parent = parent
        self.actions = list(actions)
        self.获取当前角度 = 获取当前角度
        self.完成回调 = 完成回调
        self.取消回调 = 取消回调
        self.window = tk.Toplevel(parent)
        self.window.title(title)
        self.window.geometry("760x460")
        self.window.transient(parent)
        self.window.protocol("WM_DELETE_WINDOW", self._取消)
        self.window.grab_set()

        outer = ttk.Frame(self.window, padding=12)
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text="动作按列表从上到下执行，可连续添加多个。").pack(anchor="w")
        self.listbox = tk.Listbox(outer, height=15)
        self.listbox.pack(fill="both", expand=True, pady=8)
        buttons = ttk.Frame(outer)
        buttons.pack(fill="x")
        for text, command in (
            ("添加", self._添加), ("编辑", self._编辑), ("删除", self._删除),
            ("上移", lambda: self._移动(-1)), ("下移", lambda: self._移动(1)),
        ):
            ttk.Button(buttons, text=text, command=command, width=9).pack(side="left", padx=(0, 5))
        ttk.Button(buttons, text="完成", command=self._完成, width=10).pack(side="right")
        ttk.Button(buttons, text="取消", command=self._取消, width=10).pack(side="right", padx=5)
        self._刷新()

    def _选中索引(self) -> int | None:
        selected = self.listbox.curselection()
        return int(selected[0]) if selected else None

    def _刷新(self, select: int | None = None) -> None:
        self.listbox.delete(0, "end")
        for index, action in enumerate(self.actions, start=1):
            self.listbox.insert("end", f"{index}. {动作摘要(action)}")
        if select is not None and self.actions:
            select = max(0, min(select, len(self.actions) - 1))
            self.listbox.selection_set(select)
            self.listbox.see(select)

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
        self.actions[index] = action
        self._刷新(index)

    def _删除(self) -> None:
        index = self._选中索引()
        if index is not None:
            del self.actions[index]
            self._刷新(index)

    def _移动(self, offset: int) -> None:
        index = self._选中索引()
        target = None if index is None else index + offset
        if index is None or target is None or not 0 <= target < len(self.actions):
            return
        self.actions[index], self.actions[target] = self.actions[target], self.actions[index]
        self._刷新(target)

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
    def __init__(self, parent, source: str | Path, *, 保存回调: Callable[[Path], None]) -> None:
        self.parent = parent
        self.source = Path(source)
        self.points = 读取路线文件(self.source)
        self.保存回调 = 保存回调
        self.window = tk.Toplevel(parent)
        self.window.title("编辑已保存路线动作（坐标只读）")
        self.window.geometry("820x540")
        self.window.transient(parent)
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
