# -*- coding: utf-8 -*-
"""
三角洲录制器005 · 合并主界面

仅本文件为新增入口 UI，不修改旧模块源码。
通过 import 调用：
- A记录坐标和角度版本 / 自动录制坐标工具 → 识别 + 录制
- 巡航脚本 → 路线回放寻路

功能：
1. 实时识别（坐标/角度）
2. 录制路径点并保存
3. 选择路线 / 刷新列表
4. 开始/停止巡航回放
5. 角度模式切换（legacy / text）
"""
from __future__ import annotations

import json
import math
import os
import queue
import shutil
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import List, Optional, Tuple

# 保证以脚本方式运行时能找到同目录模块
_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import cv2
import numpy as np
import win32api
import win32con
import win32gui
from PIL import Image, ImageTk

import A记录坐标和角度版本 as 识别模块
import 自动录制坐标工具 as 录制模块
import 巡航脚本 as 巡航模块
from 动作编辑器 import 动作列表窗口, 路线编辑窗口
from 路线动作 import 路线动作, 路线点, 写入路线文件

# ---------------------------------------------------------------------------
# 路径
# ---------------------------------------------------------------------------
ROOT = _ROOT
MAP_PATH = ROOT / "maps" / "DB.png"
ROUTES_DIR = ROOT / "routes"
RECORD_DIR = ROOT / "录制结果"
LOGS_DIR = ROOT / "logs"
USER_SETTINGS_PATH = ROOT / "用户设置.json"
PREVIEW_W = 720
START_DELAY_MS = 3000


def _ensure_dirs() -> None:
    ROUTES_DIR.mkdir(parents=True, exist_ok=True)
    RECORD_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)


def _bgr_to_photo(image_bgr: np.ndarray, max_width: int = PREVIEW_W) -> ImageTk.PhotoImage:
    image = Image.fromarray(cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB))
    if image.width > max_width:
        scale = max_width / float(image.width)
        image = image.resize(
            (max_width, max(1, int(image.height * scale))),
            Image.Resampling.LANCZOS,
        )
    return ImageTk.PhotoImage(image=image)


def _list_route_files() -> List[Path]:
    files: List[Path] = []
    for folder in (ROUTES_DIR, RECORD_DIR):
        if not folder.is_dir():
            continue
        files.extend(sorted(folder.glob("*.txt")))
        files.extend(sorted(folder.glob("*.jsonl")))
    # 去重（按绝对路径）
    seen = set()
    out: List[Path] = []
    for p in files:
        key = str(p.resolve())
        if key not in seen:
            seen.add(key)
            out.append(p)
    return out


def 构建动作锚点(state, actions) -> 路线点:
    return 路线点(state.x, state.y, state.angle, True, tuple(actions))


def _生成录制路线路径(folder: Path) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    timestamp = 录制模块.生成时间戳()
    path = folder / f"自动录制路线_{timestamp}.jsonl"
    index = 1
    while path.exists():
        path = folder / f"自动录制路线_{timestamp}_{index}.jsonl"
        index += 1
    return path


class 合并主界面:
    def __init__(self) -> None:
        _ensure_dirs()
        self.root = tk.Tk()
        self.root.title("三角洲录制器005 · 录制 / 回放 / 路线动作")
        self.root.geometry("1100x820")
        self.root.minsize(920, 700)

        # 业务状态
        self.识别器: Optional[识别模块.实时坐标角度识别器] = None
        self.巡航定位器 = None
        self.录制器 = 录制模块.自动坐标录制器()
        self.current_state: Optional[识别模块.识别状态] = None
        self.preview_photo = None

        self.detecting = False
        self.recording = False
        self.recording_paused = False
        self.cruising = False
        self._recorded_route_points: list[路线点] = []
        self._q_down = False
        self._action_window = None
        self._previous_foreground_hwnd = 0
        self._yolo_window = None
        self._yolo_status_label = None
        self._yolo_info_label = None
        self._yolo_image_label = None
        self._yolo_photo = None
        self._yolo_last_update = 0.0
        self._yolo_previous_foreground_hwnd = 0
        self._yolo_close_after = None
        self._detect_stop = threading.Event()
        self._cruise_stop = threading.Event()
        self._detect_thread: Optional[threading.Thread] = None
        self._cruise_thread: Optional[threading.Thread] = None
        self._detect_start_after = None
        self._cruise_start_after = None
        self._queue: "queue.Queue[Tuple[str, object]]" = queue.Queue()
        self._log_path = None
        self._log_fn = None
        self._last_saved: Optional[Path] = None

        # UI 变量
        self.pose_var = tk.StringVar(value="坐标: -- | 角度: --")
        self.status_var = tk.StringVar(value="就绪。先选角度模式，再「开始识别」")
        self.angle_mode_var = tk.StringVar(value="legacy")
        self.angle_hint_var = tk.StringVar(value="")
        self.route_var = tk.StringVar(value="")
        self.arrival_var = tk.IntVar(value=3)
        self.precise_var = tk.BooleanVar(value=False)
        self.speed_var = tk.DoubleVar(value=1.5)
        self.speed_label_var = tk.StringVar(value="1.5x")
        self.record_count_var = tk.StringVar(value="录制点数: 0")

        self._init_backends()
        self._build_ui()
        self._load_settings()
        self._refresh_route_list()
        self._apply_angle_mode()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(80, self._drain_queue)
        self.root.after(100, self._esc_poll)
        self.root.after(50, self._q_poll)

    # ------------------------------------------------------------------ init
    def _map_path_for_cv2(self) -> str:
        """cv2.imread 不支持中文绝对路径，优先用相对路径 maps/DB.png。"""
        rel = Path("maps") / "DB.png"
        if rel.is_file():
            return str(rel).replace("\\", "/")
        if MAP_PATH.is_file():
            return str(MAP_PATH)
        return 巡航模块.地图文件路径

    def _init_backends(self) -> None:
        # 确保工作目录在项目根，相对 maps/ 可用
        try:
            os.chdir(str(ROOT))
        except Exception:
            pass

        try:
            识别模块.设置角度模式("legacy")
            map_path = self._map_path_for_cv2()
            self.识别器 = 识别模块.实时坐标角度识别器(
                地图匹配器=识别模块.单独坐标识别器(map_path),
                角度模式="legacy",
            )
        except Exception as exc:
            self.识别器 = None
            self.status_var.set(f"识别器初始化失败: {exc}")

        # 巡航定位器可延迟创建；启动时再试，避免中文路径导致整窗不可用
        self.巡航定位器 = None
        self._try_init_cruise_locator(silent=True)

    def _try_init_cruise_locator(self, silent: bool = False) -> bool:
        if self.巡航定位器 is not None:
            return True
        try:
            os.chdir(str(ROOT))
        except Exception:
            pass
        map_path = self._map_path_for_cv2()
        mode = self.angle_mode_var.get() if hasattr(self, "angle_mode_var") else "legacy"
        last_err = None
        for path_try in (map_path, "maps/DB.png", 巡航模块.地图文件路径):
            try:
                self.巡航定位器 = 巡航模块.实时定位器(
                    地图路径=path_try,
                    角度模式=mode,
                )
                return True
            except Exception as exc:
                last_err = exc
                self.巡航定位器 = None
        if not silent and last_err is not None:
            self.status_var.set(f"巡航定位器初始化失败: {last_err}")
        return False

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        top = ttk.Frame(self.root, padding=(12, 10, 12, 4))
        top.pack(fill="x")
        ttk.Label(
            top,
            text="三角洲录制器005",
            font=("Microsoft YaHei", 14, "bold"),
        ).pack(side="left")
        ttk.Label(
            top,
            text="  录制 · 回放 · Q 动作菜单 · YOLO 物资交互",
            foreground="#666666",
        ).pack(side="left")

        # 角度
        mode = ttk.LabelFrame(self.root, text="角度识别（截图方式不变）", padding=8)
        mode.pack(fill="x", padx=12, pady=(4, 4))
        row = ttk.Frame(mode)
        row.pack(fill="x")
        ttk.Radiobutton(
            row, text="Legacy 丝滑版", value="legacy",
            variable=self.angle_mode_var, command=self._apply_angle_mode,
        ).pack(side="left", padx=(0, 16))
        ttk.Radiobutton(
            row, text="原版 TEXT", value="text",
            variable=self.angle_mode_var, command=self._apply_angle_mode,
        ).pack(side="left")
        ttk.Label(mode, textvariable=self.angle_hint_var, foreground="#555555").pack(
            anchor="w", pady=(4, 0)
        )

        # 识别 / 录制
        rec = ttk.LabelFrame(self.root, text="识别与录制（录制中按 Q 暂停并添加动作）", padding=8)
        rec.pack(fill="x", padx=12, pady=4)
        btns = ttk.Frame(rec)
        btns.pack(fill="x")
        self.btn_detect_start = ttk.Button(btns, text="开始识别", command=self.start_detect, width=12)
        self.btn_detect_start.pack(side="left", padx=(0, 6))
        self.btn_detect_stop = ttk.Button(
            btns, text="停止识别", command=self.stop_detect, width=12, state="disabled"
        )
        self.btn_detect_stop.pack(side="left", padx=(0, 6))
        self.btn_rec_start = ttk.Button(
            btns, text="开始录制", command=self.start_record, width=12, state="disabled"
        )
        self.btn_rec_start.pack(side="left", padx=(0, 6))
        self.btn_rec_stop = ttk.Button(
            btns, text="停止录制并保存", command=self.stop_record, width=14, state="disabled"
        )
        self.btn_rec_stop.pack(side="left", padx=(0, 6))
        ttk.Button(btns, text="清空录制", command=self.clear_record, width=10).pack(
            side="left", padx=(0, 6)
        )
        ttk.Label(btns, textvariable=self.record_count_var).pack(side="left", padx=(12, 0))

        # 路线 / 回放
        cruise = ttk.LabelFrame(self.root, text="路线回放（巡航）", padding=8)
        cruise.pack(fill="x", padx=12, pady=4)
        r1 = ttk.Frame(cruise)
        r1.pack(fill="x")
        ttk.Label(r1, text="路线:").pack(side="left")
        self.route_combo = ttk.Combobox(
            r1, textvariable=self.route_var, state="readonly", width=56
        )
        self.route_combo.pack(side="left", padx=6, fill="x", expand=True)
        ttk.Button(r1, text="刷新", command=self._refresh_route_list, width=8).pack(
            side="left", padx=2
        )
        ttk.Button(r1, text="浏览…", command=self._browse_route, width=8).pack(
            side="left", padx=2
        )
        ttk.Button(r1, text="编辑动作", command=self._edit_selected_route, width=9).pack(
            side="left", padx=2
        )
        r2 = ttk.Frame(cruise)
        r2.pack(fill="x", pady=(6, 0))
        ttk.Label(r2, text="到点阈值:").pack(side="left")
        ttk.Spinbox(r2, from_=1, to=30, textvariable=self.arrival_var, width=5).pack(
            side="left", padx=(4, 12)
        )
        ttk.Checkbutton(r2, text="精准模式", variable=self.precise_var).pack(side="left")
        ttk.Label(r2, text="速度倍率:").pack(side="left", padx=(16, 0))
        tk.Scale(
            r2,
            from_=0.5,
            to=3.0,
            resolution=0.1,
            orient="horizontal",
            variable=self.speed_var,
            command=self._update_speed_label,
            showvalue=False,
            length=130,
        ).pack(side="left", padx=(4, 2))
        ttk.Label(r2, textvariable=self.speed_label_var, width=5).pack(side="left")
        self.btn_cruise_start = ttk.Button(
            r2, text="开始回放", command=self.start_cruise, width=12
        )
        self.btn_cruise_start.pack(side="left", padx=(10, 6))
        self.btn_cruise_stop = ttk.Button(
            r2, text="停止回放 (Esc)", command=self.stop_cruise, width=14, state="disabled"
        )
        self.btn_cruise_stop.pack(side="left")

        # 状态
        info = ttk.Frame(self.root, padding=(12, 4))
        info.pack(fill="x")
        ttk.Label(
            info, textvariable=self.pose_var, font=("Segoe UI", 13, "bold")
        ).pack(anchor="w")
        ttk.Label(info, textvariable=self.status_var, foreground="#333333").pack(
            anchor="w", pady=(2, 0)
        )

        # 预览 + 点列表
        body = ttk.Frame(self.root, padding=(12, 4, 12, 12))
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=3)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)

        self.preview_label = tk.Label(body, bg="#111111", relief="sunken")
        self.preview_label.grid(row=0, column=0, sticky="nsew", padx=(0, 8))

        right = ttk.Frame(body)
        right.grid(row=0, column=1, sticky="nsew")
        ttk.Label(right, text="本次录制点 (x,y)").pack(anchor="w")
        self.points_text = tk.Text(right, width=28, height=20)
        self.points_text.pack(fill="both", expand=True, pady=(4, 0))

        self._draw_preview(None)

    # ------------------------------------------------------------------ settings
    def _update_speed_label(self, value: Optional[str] = None) -> None:
        try:
            speed = float(self.speed_var.get() if value is None else value)
        except (TypeError, ValueError, tk.TclError):
            speed = 1.5
        self.speed_label_var.set(f"{speed:.1f}x")

    def _load_settings(self) -> None:
        try:
            data = json.loads(USER_SETTINGS_PATH.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            return
        if not isinstance(data, dict):
            return

        mode = data.get("角度模式")
        if mode in ("legacy", "text"):
            self.angle_mode_var.set(mode)

        speed = data.get("视角速度倍率")
        if isinstance(speed, (int, float)) and not isinstance(speed, bool):
            speed = float(speed)
            if math.isfinite(speed) and 0.5 <= speed <= 3.0:
                self.speed_var.set(round(speed, 1))

        arrival = data.get("到点阈值")
        if isinstance(arrival, int) and not isinstance(arrival, bool) and 1 <= arrival <= 30:
            self.arrival_var.set(arrival)

        precise = data.get("精准模式")
        if isinstance(precise, bool):
            self.precise_var.set(precise)

        route = data.get("所选路线")
        if isinstance(route, str):
            self.route_var.set(route)
        self._update_speed_label()

    def _save_settings(self) -> None:
        try:
            speed = float(self.speed_var.get())
            if not math.isfinite(speed) or not 0.5 <= speed <= 3.0:
                speed = 1.5
        except (TypeError, ValueError, tk.TclError):
            speed = 1.5
        try:
            arrival = int(self.arrival_var.get())
            if not 1 <= arrival <= 30:
                arrival = 3
        except (TypeError, ValueError, tk.TclError):
            arrival = 3
        mode = self.angle_mode_var.get()
        if mode not in ("legacy", "text"):
            mode = "legacy"
        data = {
            "角度模式": mode,
            "视角速度倍率": round(speed, 1),
            "到点阈值": arrival,
            "精准模式": bool(self.precise_var.get()),
            "所选路线": str(self.route_var.get()),
        }
        try:
            USER_SETTINGS_PATH.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError:
            pass

    def _restore_window(self) -> None:
        try:
            self.root.deiconify()
            self.root.lift()
        except tk.TclError:
            pass

    # ------------------------------------------------------------------ angle
    def _apply_angle_mode(self) -> None:
        if self.detecting or self.cruising:
            return
        mode = self.angle_mode_var.get()
        try:
            识别模块.设置角度模式(mode)
            label = 识别模块.当前角度模式标签()
            bbox = 识别模块.当前角度区域()
            self.angle_hint_var.set(
                f"{label} | ROI {bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]} | 截图 GDI/mss"
            )
            if self.巡航定位器 is not None and hasattr(self.巡航定位器, "设置角度模式"):
                self.巡航定位器.设置角度模式(mode)
            if not self.detecting and not self.cruising:
                self.status_var.set(f"角度模式: {label}")
        except Exception as exc:
            self.status_var.set(f"切换角度失败: {exc}")

    # ------------------------------------------------------------------ detect
    def start_detect(self) -> None:
        if self.detecting or self.cruising:
            return
        if self.识别器 is None:
            messagebox.showerror("错误", "识别器未初始化")
            return
        self._apply_angle_mode()
        self.detecting = True
        self._detect_stop.clear()
        self._log_path, self._log_fn = 录制模块.创建日志记录器("合并界面")
        录制模块.写日志(
            self._log_fn,
            "event=detect_start",
            角度模式=识别模块.当前角度模式(),
        )
        self.btn_detect_start.config(state="disabled")
        self.btn_detect_stop.config(state="normal")
        self.btn_rec_start.config(state="normal")
        self._set_angle_radios(False)
        self.status_var.set(f"窗口已最小化，3 秒后开始识别… | {识别模块.当前角度模式标签()}")
        self._detect_thread = None
        self.root.iconify()
        self._detect_start_after = self.root.after(START_DELAY_MS, self._start_detect_thread)

    def _start_detect_thread(self) -> None:
        self._detect_start_after = None
        if not self.detecting or self._detect_stop.is_set():
            return
        self.status_var.set(f"识别中… | {识别模块.当前角度模式标签()}")
        self._detect_thread = threading.Thread(target=self._detect_loop, daemon=True)
        self._detect_thread.start()

    def stop_detect(self) -> None:
        if self.recording:
            self.stop_record()
        self.detecting = False
        self._detect_stop.set()
        录制模块.写日志(self._log_fn, "event=detect_stop")
        self._restore_window()
        if self._detect_thread is None:
            after_id = getattr(self, "_detect_start_after", None)
            if after_id is not None:
                try:
                    self.root.after_cancel(after_id)
                except tk.TclError:
                    pass
            self._detect_start_after = None
            self.btn_detect_start.config(state="normal")
            self.btn_detect_stop.config(state="disabled")
            self.btn_rec_start.config(state="disabled")
            self.btn_rec_stop.config(state="disabled")
            if not self.cruising:
                self._set_angle_radios(True)
            self.status_var.set("已停止识别")

    def _detect_loop(self) -> None:
        assert self.识别器 is not None
        while not self._detect_stop.is_set():
            try:
                state = self.识别器.读取状态()
                self._queue.put(("state", state))
            except Exception as exc:
                录制模块.写日志(self._log_fn, "event=detect_error", 错误=str(exc))
                self._queue.put(("error", str(exc)))
            self._detect_stop.wait(识别模块.循环间隔)
        self._queue.put(("detect_stopped", None))

    # ------------------------------------------------------------------ record
    def start_record(self) -> None:
        if not self.detecting:
            self.status_var.set("请先开始识别")
            return
        if self.recording:
            return
        self.recording = True
        self.recording_paused = False
        self._last_saved = None
        self.录制器.清空()
        self._recorded_route_points.clear()
        self.录制器.日志函数 = self._log_fn
        self._refresh_points_text()
        self.btn_rec_start.config(state="disabled")
        self.btn_rec_stop.config(state="normal")
        self.record_count_var.set("录制点数: 0")
        self.status_var.set(
            f"录制中（最小距离 {self.录制器.最小记录距离}）…"
        )
        录制模块.写日志(self._log_fn, "event=record_start")

    def stop_record(self) -> None:
        if not self.recording:
            return
        self.recording = False
        self.recording_paused = False
        self.btn_rec_start.config(state="normal" if self.detecting else "disabled")
        self.btn_rec_stop.config(state="disabled")
        if not self._recorded_route_points:
            self._last_saved = None
            self.status_var.set("本次无记录，未保存")
            录制模块.写日志(self._log_fn, "event=record_stop", 结果="无记录")
            return
        try:
            path = _生成录制路线路径(RECORD_DIR)
            写入路线文件(path, self._recorded_route_points)
            ROUTES_DIR.mkdir(parents=True, exist_ok=True)
            dest = ROUTES_DIR / path.name
            if dest.resolve() != path.resolve():
                shutil.copy2(path, dest)
        except (OSError, ValueError) as exc:
            self._last_saved = None
            messagebox.showerror("保存失败", str(exc))
            self.status_var.set(f"保存失败: {exc}")
            录制模块.写日志(self._log_fn, "event=record_stop", 结果="保存失败", 错误=str(exc))
            return
        self._last_saved = dest
        self.route_var.set(str(dest))
        self._refresh_route_list(select=str(dest))
        self.status_var.set(f"已保存: {dest}")
        self.record_count_var.set(f"录制点数: {len(self._recorded_route_points)}")
        录制模块.写日志(
            self._log_fn,
            "event=record_stop",
            结果="已保存",
            文件=str(dest),
            点数=len(self._recorded_route_points),
        )

    def clear_record(self) -> None:
        if self.recording:
            self.status_var.set("请先停止录制")
            return
        self.录制器.清空()
        self._recorded_route_points.clear()
        self.recording_paused = False
        self._last_saved = None
        self._refresh_points_text()
        self.record_count_var.set("录制点数: 0")
        self.status_var.set("已清空本次录制")
        self._draw_preview(self.current_state)

    # ------------------------------------------------------------------ cruise
    def start_cruise(self) -> None:
        if self.cruising:
            return
        if self.detecting:
            messagebox.showinfo("提示", "请先停止识别，再开始回放，避免争抢截图。")
            return
        route = self.route_var.get().strip()
        if not route:
            messagebox.showerror("启动失败", "请先选择路线文件")
            return
        try:
            route = 巡航模块.校验路线文件(route)
        except ValueError as exc:
            messagebox.showerror("启动失败", str(exc))
            return
        if not self._try_init_cruise_locator(silent=False):
            messagebox.showerror(
                "启动失败",
                "巡航定位器未初始化。\n"
                "常见原因：地图路径含中文导致 OpenCV 读图失败。\n"
                "请确认 maps/DB.png 存在，并以项目目录为工作目录启动。",
            )
            return

        self._apply_angle_mode()
        try:
            到点 = int(self.arrival_var.get())
            巡航模块.校验到点阈值(到点)
        except Exception as exc:
            messagebox.showerror("启动失败", str(exc))
            return

        self.cruising = True
        self._cruise_stop.clear()
        self.btn_cruise_start.config(state="disabled")
        self.btn_cruise_stop.config(state="normal")
        self.btn_detect_start.config(state="disabled")
        self._set_angle_radios(False)
        delay = START_DELAY_MS // 1000
        label = 识别模块.当前角度模式标签()
        self.status_var.set(
            f"{巡航模块.构建开始状态文本(delay)} | 角度={label} | 到点={到点}"
        )
        定位器 = self.巡航定位器
        精准 = bool(self.precise_var.get())
        视角速度倍率 = float(self.speed_var.get())

        def worker() -> None:
            try:
                # 直接调 巡航，可传入到点阈值 / 精准模式
                _, log_fn = 巡航模块.创建日志记录器("巡航工具")
                巡航模块.巡航(
                    route,
                    到点阈值=到点,
                    精准模式=精准,
                    视角速度倍率=视角速度倍率,
                    定位器=定位器,
                    日志函数=log_fn,
                    停止事件=self._cruise_stop,
                    YOLO状态函数=self._queue_yolo_status,
                )
                self._queue.put(("cruise_done", "寻路已结束"))
            except 巡航模块.紧急停止异常:
                self._queue.put(("cruise_done", "已通过 Esc 停止"))
            except Exception as exc:
                self._queue.put(("cruise_error", str(exc)))
            finally:
                self._queue.put(("cruise_stopped", None))

        def start_worker() -> None:
            self._cruise_start_after = None
            if not self.cruising or self._cruise_stop.is_set():
                return
            self._cruise_thread = threading.Thread(target=worker, daemon=True)
            self._cruise_thread.start()

        self._cruise_thread = None
        self.root.iconify()
        self._cruise_start_after = self.root.after(START_DELAY_MS, start_worker)
        self.root.after(200, self._poll_cruise_preview)

    def stop_cruise(self) -> None:
        if not self.cruising:
            return
        self._cruise_stop.set()
        self._restore_window()
        if self._cruise_thread is None:
            after_id = getattr(self, "_cruise_start_after", None)
            if after_id is not None:
                try:
                    self.root.after_cancel(after_id)
                except tk.TclError:
                    pass
            self._cruise_start_after = None
            self.cruising = False
            self.btn_cruise_start.config(state="normal")
            self.btn_cruise_stop.config(state="disabled")
            self.btn_detect_start.config(state="normal")
            self._set_angle_radios(True)
            self.status_var.set("已停止巡航")
        else:
            self.status_var.set("正在停止巡航…")

    def _poll_cruise_preview(self) -> None:
        if not self.cruising:
            return
        loc = self.巡航定位器
        if loc is not None:
            st = getattr(loc, "最近状态", None)
            if st is not None:
                try:
                    x, y, ang = st
                    self.pose_var.set(f"坐标: ({x}, {y}) | 角度: {float(ang):.2f} | 巡航中")
                    img = loc.生成预览图(st)
                    self._set_preview(img)
                except Exception:
                    pass
        self.root.after(300, self._poll_cruise_preview)

    # ------------------------------------------------------------------ routes
    def _refresh_route_list(self, select: Optional[str] = None) -> None:
        paths = _list_route_files()
        labels = [str(p) for p in paths]
        self.route_combo["values"] = labels
        if select and select in labels:
            self.route_var.set(select)
        elif labels and not self.route_var.get():
            self.route_var.set(labels[0])
        elif self.route_var.get() and self.route_var.get() not in labels:
            self.route_var.set(labels[0] if labels else "")

    def _browse_route(self) -> None:
        path = filedialog.askopenfilename(
            title="选择路线文件",
            initialdir=str(ROUTES_DIR if ROUTES_DIR.is_dir() else ROOT),
            filetypes=[("路线文件", "*.jsonl *.txt"), ("005 JSONL 路线", "*.jsonl"), ("旧 TXT 路线", "*.txt")],
        )
        if path:
            self.route_var.set(path)
            self._refresh_route_list(select=path)

    def _edit_selected_route(self) -> None:
        if self.recording or self.cruising:
            messagebox.showinfo("提示", "请先停止录制或回放")
            return
        source = self.route_var.get().strip()
        if not source:
            messagebox.showerror("打开失败", "请先选择路线文件")
            return
        try:
            路线编辑窗口(self.root, source, 保存回调=self._on_route_edited)
        except (OSError, ValueError) as exc:
            messagebox.showerror("打开失败", str(exc))

    def _on_route_edited(self, path: Path) -> None:
        self.route_var.set(str(path))
        self._refresh_route_list(select=str(path))
        self.status_var.set(f"路线动作已保存: {path}")

    # ------------------------------------------------------------------ queue / preview
    def _drain_queue(self) -> None:
        while True:
            try:
                kind, payload = self._queue.get_nowait()
            except queue.Empty:
                break
            if kind == "state":
                self._on_state(payload)  # type: ignore[arg-type]
            elif kind == "error":
                self.status_var.set(f"识别失败: {payload}")
            elif kind == "detect_stopped":
                self.detecting = False
                self._detect_thread = None
                self.btn_detect_start.config(state="normal")
                self.btn_detect_stop.config(state="disabled")
                self.btn_rec_start.config(state="disabled")
                self.btn_rec_stop.config(state="disabled")
                if not self.cruising:
                    self._set_angle_radios(True)
                if self._last_saved is None:
                    self.status_var.set("已停止识别")
                else:
                    self.status_var.set(f"已停止识别 | 上次保存: {self._last_saved}")
                self._restore_window()
            elif kind == "cruise_done":
                self.status_var.set(str(payload))
            elif kind == "yolo_status":
                self._on_yolo_status(payload)  # type: ignore[arg-type]
            elif kind == "cruise_error":
                messagebox.showerror("寻路失败", str(payload))
                self.status_var.set(f"寻路失败: {payload}")
            elif kind == "cruise_stopped":
                self._关闭YOLO窗口()
                self.cruising = False
                self._cruise_thread = None
                self.btn_cruise_start.config(state="normal")
                self.btn_cruise_stop.config(state="disabled")
                self.btn_detect_start.config(state="normal")
                self._set_angle_radios(True)
                self._restore_window()
        self.root.after(80, self._drain_queue)

    def _queue_yolo_status(self, event: str, **fields) -> None:
        if event == "inference":
            now = time.monotonic()
            if now - self._yolo_last_update < 0.08:
                return
            self._yolo_last_update = now
        self._queue.put(("yolo_status", {"event": event, **fields}))

    def _创建YOLO窗口(self) -> None:
        if self._yolo_window is not None:
            try:
                if self._yolo_window.winfo_exists():
                    self._yolo_window.deiconify()
                    return
            except tk.TclError:
                pass
        try:
            self._yolo_previous_foreground_hwnd = int(win32gui.GetForegroundWindow() or 0)
        except Exception:
            self._yolo_previous_foreground_hwnd = 0
        window = tk.Toplevel(self.root)
        window.title("YOLO 物资识别状态（不抢游戏焦点）")
        window.geometry("560x430+20+80")
        window.resizable(False, False)
        window.protocol("WM_DELETE_WINDOW", self._关闭YOLO窗口)
        self._yolo_window = window
        self._yolo_status_label = ttk.Label(window, text="YOLO 准备中", font=("Microsoft YaHei", 12, "bold"))
        self._yolo_status_label.pack(anchor="w", padx=10, pady=(8, 2))
        self._yolo_info_label = ttk.Label(window, text="", justify="left")
        self._yolo_info_label.pack(anchor="w", padx=10, pady=(0, 6))
        self._yolo_image_label = tk.Label(window, bg="#111111", width=448, height=256)
        self._yolo_image_label.pack(padx=10, pady=(0, 10))
        try:
            window.update_idletasks()
            hwnd = int(window.winfo_id())
            exstyle = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
            no_activate = getattr(win32con, "WS_EX_NOACTIVATE", 0x08000000)
            tool_window = getattr(win32con, "WS_EX_TOOLWINDOW", 0x00000080)
            win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE, exstyle | no_activate | tool_window)
            flags = (
                win32con.SWP_NOMOVE
                | win32con.SWP_NOSIZE
                | win32con.SWP_NOACTIVATE
                | win32con.SWP_SHOWWINDOW
            )
            win32gui.SetWindowPos(hwnd, win32con.HWND_TOPMOST, 0, 0, 0, 0, flags)
            if self._yolo_previous_foreground_hwnd and win32gui.IsWindow(self._yolo_previous_foreground_hwnd):
                win32gui.SetForegroundWindow(self._yolo_previous_foreground_hwnd)
        except Exception:
            pass

    def _绘制YOLO预览(self, frame, detections, roi, target):
        if frame is None or self._yolo_image_label is None:
            return
        try:
            image = frame.copy()
            left, top, right, bottom = [int(value) for value in roi]
            target_center = None if target is None else (target.get("中心X"), target.get("中心Y"))
            for item in detections or []:
                x1 = int(item.get("x1", left) - left)
                y1 = int(item.get("y1", top) - top)
                x2 = int(item.get("x2", right) - left)
                y2 = int(item.get("y2", bottom) - top)
                center = (item.get("中心X"), item.get("中心Y"))
                color = (0, 255, 0) if center == target_center else (0, 140, 255)
                cv2.rectangle(image, (x1, y1), (x2, y2), color, 2)
                cv2.putText(
                    image,
                    f"{item.get('类别名称', '?')} {float(item.get('置信度', 0)):.2f}",
                    (max(0, x1), max(16, y1 - 5)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.45,
                    color,
                    1,
                    cv2.LINE_AA,
                )
            self._yolo_photo = _bgr_to_photo(image, max_width=540)
            self._yolo_image_label.configure(image=self._yolo_photo, width=0, height=0)
        except Exception:
            pass

    def _on_yolo_status(self, payload: dict) -> None:
        event = str(payload.get("event", ""))
        if event == "start":
            self._创建YOLO窗口()
            if self._yolo_status_label is not None:
                self._yolo_status_label.configure(text="YOLO：准备识别")
            if self._yolo_info_label is not None:
                self._yolo_info_label.configure(
                    text=f"目标视角：{payload.get('目标角度', '--')}°\n"
                    f"置信度阈值：{float(payload.get('置信度阈值', 0.5)):.2f}  |  超时：{payload.get('超时毫秒', '--')}ms"
                )
            return
        if self._yolo_window is None:
            self._创建YOLO窗口()
        if event == "view":
            status = f"YOLO：恢复视角到 {payload.get('目标角度', '--')}°"
        elif event == "view_failed":
            status = f"YOLO：视角恢复失败（{payload.get('目标角度', '--')}°），跳过识别"
        elif event == "inference":
            status = "YOLO：识别中"
            target = payload.get("目标") or {}
            info = (
                f"执行器：{payload.get('执行器', '未知')}  |  检测目标：{payload.get('检测数', 0)} 个\n"
                f"当前目标：{target.get('类别名称', '未找到')} 置信度：{float(target.get('置信度', 0)):.2f}\n"
                f"剩余时间：{payload.get('剩余毫秒', 0)}ms"
            )
            if self._yolo_info_label is not None:
                self._yolo_info_label.configure(text=info)
            self._绘制YOLO预览(
                payload.get("截图"), payload.get("检测结果", []), payload.get("ROI", (0, 0, 1, 1)), target
            )
        elif event == "adjust":
            status = "YOLO：对准调整中"
        elif event == "aligned":
            status = f"YOLO：已对准，误差 X={payload.get('误差X', '--')} Y={payload.get('误差Y', '--')}，执行 F/W"
        elif event == "timeout":
            status = "YOLO：识别/对准超时，跳过动作"
        elif event == "unavailable":
            status = "YOLO：检测器不可用，跳过动作"
        elif event == "finish":
            status = "YOLO：动作完成" if payload.get("成功") else "YOLO：动作失败，已继续路线"
            if self._yolo_window is not None:
                self._yolo_close_after = self.root.after(1200, self._关闭YOLO窗口)
        else:
            status = f"YOLO：{event}"
        if self._yolo_status_label is not None:
            self._yolo_status_label.configure(text=status)
        if event in {"view_failed", "timeout", "unavailable"} and self._yolo_info_label is not None:
            self._yolo_info_label.configure(text="本次动作将跳过，巡航会继续执行后续路线点。")

    def _关闭YOLO窗口(self) -> None:
        close_after = getattr(self, "_yolo_close_after", None)
        if close_after is not None:
            try:
                self.root.after_cancel(close_after)
            except Exception:
                pass
            self._yolo_close_after = None
        window = getattr(self, "_yolo_window", None)
        self._yolo_window = None
        self._yolo_photo = None
        self._yolo_status_label = None
        self._yolo_info_label = None
        self._yolo_image_label = None
        if window is not None:
            try:
                window.destroy()
            except tk.TclError:
                pass

    def _on_state(self, state: 识别模块.识别状态) -> None:
        if not self.detecting:
            return
        self.current_state = state
        try:
            识别模块.写入定位文件(state.x, state.y, state.angle)
        except Exception:
            pass
        self.pose_var.set(
            f"坐标: ({state.x}, {state.y}) | 角度: {state.angle:.2f} | "
            f"地图: {state.map_method}"
        )
        if self.recording and not self.recording_paused and self.录制器.尝试记录(state.x, state.y):
            self._recorded_route_points.append(路线点(state.x, state.y, state.angle, True))
            self.points_text.insert("end", 录制模块.格式化坐标行(state.x, state.y) + "\n")
            self.points_text.see("end")
            self.record_count_var.set(f"录制点数: {len(self._recorded_route_points)}")
        self._draw_preview(state)

    def _draw_preview(self, state: Optional[识别模块.识别状态]) -> None:
        if self.识别器 is None:
            return
        try:
            big = self.识别器.地图匹配器.big_map
            cur = None if state is None else (state.x, state.y)
            img = 录制模块.绘制轨迹预览(
                big,
                cur,
                self.录制器.记录列表,
                self.录制器.异常线列表,
            )
            self._set_preview(img)
        except Exception:
            pass

    def _set_preview(self, image_bgr: np.ndarray) -> None:
        self.preview_photo = _bgr_to_photo(image_bgr)
        self.preview_label.config(image=self.preview_photo)

    def _refresh_points_text(self) -> None:
        self.points_text.delete("1.0", "end")
        if self._recorded_route_points:
            self.points_text.insert(
                "1.0",
                "\n".join(
                    f"{点.x},{点.y}" + (f"  [动作 {len(点.actions)} 个]" if 点.actions else "")
                    for 点 in self._recorded_route_points
                )
                + "\n",
            )

    def _set_angle_radios(self, enabled: bool) -> None:
        # Radiobuttons 在 LabelFrame 里，用 state 控制
        state = "normal" if enabled else "disabled"
        for child in self.root.winfo_children():
            if isinstance(child, ttk.LabelFrame) and "角度" in str(child.cget("text")):
                for sub in child.winfo_children():
                    if isinstance(sub, ttk.Frame):
                        for rb in sub.winfo_children():
                            if isinstance(rb, ttk.Radiobutton):
                                rb.config(state=state)

    def _esc_poll(self) -> None:
        if self.cruising:
            try:
                if 巡航模块.处理esc紧急停止(self._cruise_stop):
                    self.stop_cruise()
            except Exception:
                pass
        self.root.after(50, self._esc_poll)

    def _q_poll(self) -> None:
        try:
            down = bool(win32api.GetAsyncKeyState(ord("Q")) & 0x8000)
        except Exception:
            down = False
        if down and not self._q_down and self.recording and not self.recording_paused:
            self._open_q_action_menu()
        self._q_down = down
        self.root.after(50, self._q_poll)

    def _open_q_action_menu(self) -> None:
        snapshot = self.current_state
        if snapshot is None:
            self.status_var.set("暂时没有可用坐标/视角，无法添加动作")
            return
        self.recording_paused = True
        try:
            self._previous_foreground_hwnd = int(win32gui.GetForegroundWindow() or 0)
        except Exception:
            self._previous_foreground_hwnd = 0
        self.root.deiconify()
        self.root.lift()
        try:
            self.root.attributes("-topmost", True)
            self.root.after(200, lambda: self.root.attributes("-topmost", False))
        except tk.TclError:
            pass
        self.status_var.set("录制已暂停：请添加动作，完成或取消后继续录制")
        self._action_window = 动作列表窗口(
            self.root,
            获取当前角度=lambda: float(getattr(self.current_state, "angle", snapshot.angle)),
            完成回调=lambda actions: self._save_q_actions(snapshot, actions),
            取消回调=self._close_q_action_menu,
            title=f"Q 动作菜单 · 锚点 ({snapshot.x}, {snapshot.y})",
        )

    def _save_q_actions(self, snapshot, actions: tuple[路线动作, ...]) -> None:
        if actions:
            self._recorded_route_points.append(构建动作锚点(snapshot, actions))
            self._refresh_points_text()
            self.record_count_var.set(f"录制点数: {len(self._recorded_route_points)}")
            录制模块.写日志(
                self._log_fn,
                "event=record_actions",
                坐标=f"{snapshot.x},{snapshot.y}",
                角度=f"{snapshot.angle:.2f}",
                动作数=len(actions),
            )
        self._close_q_action_menu()

    def _close_q_action_menu(self) -> None:
        self._action_window = None
        self.recording_paused = False
        if self.recording:
            self.status_var.set(f"录制继续（已记录 {len(self._recorded_route_points)} 个路线点）")
            self.root.iconify()
            self.root.after(80, self._restore_previous_foreground)

    def _restore_previous_foreground(self) -> None:
        hwnd = self._previous_foreground_hwnd
        self._previous_foreground_hwnd = 0
        if not hwnd:
            return
        try:
            if win32gui.IsWindow(hwnd):
                win32gui.SetForegroundWindow(hwnd)
        except Exception:
            pass

    def _on_close(self) -> None:
        try:
            if self.recording:
                self.stop_record()
            if self.detecting:
                self.stop_detect()
            if self.cruising:
                self.stop_cruise()
        except Exception:
            pass
        self._save_settings()
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


def main() -> None:
    # 工作目录切到项目根，保证 maps/ routes/ 相对路径可用
    # （cv2.imread 无法可靠读取含中文的绝对路径）
    os.chdir(str(ROOT))
    app = 合并主界面()
    app.run()


if __name__ == "__main__":
    main()
