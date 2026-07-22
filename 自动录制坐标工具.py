from __future__ import annotations

from pathlib import Path
from typing import Callable, List, Optional, Tuple
import math
import queue
import threading
import time
import tkinter as tk
from tkinter import ttk

import cv2
import numpy as np

import A记录坐标和角度版本 as 基础模块


最小记录距离 = 3
最大单次跳变距离 = 10
异常确认次数 = 3
输出目录 = Path("录制结果")
日志目录 = Path("logs")
预览宽度 = 600


def 格式化坐标行(x: int, y: int) -> str:
    return f"{int(x)},{int(y)}"


def 计算距离(点1: Tuple[int, int], 点2: Tuple[int, int]) -> float:
    return math.hypot(点1[0] - 点2[0], 点1[1] - 点2[1])


def 生成时间戳() -> str:
    return time.strftime("%Y%m%d_%H%M%S")


def 生成输出路径(输出目录路径: Path, 时间戳: str) -> Path:
    输出目录路径.mkdir(parents=True, exist_ok=True)
    路径 = 输出目录路径 / f"自动录制坐标_{时间戳}.txt"
    序号 = 1
    while 路径.exists():
        路径 = 输出目录路径 / f"自动录制坐标_{时间戳}_{序号}.txt"
        序号 += 1
    return 路径


def 生成日志路径(日志名称: str, 输出目录路径: Path, 时间戳: str) -> Path:
    输出目录路径.mkdir(parents=True, exist_ok=True)
    路径 = 输出目录路径 / f"{日志名称}_{时间戳}.log"
    序号 = 1
    while 路径.exists():
        路径 = 输出目录路径 / f"{日志名称}_{时间戳}_{序号}.log"
        序号 += 1
    return 路径


def 格式化日志行(事件: str, **字段) -> str:
    字段文本 = " | ".join(f"{键}={值}" for 键, 值 in 字段.items())
    前缀 = f"{time.strftime('%Y-%m-%d %H:%M:%S')} | {事件}"
    return f"{前缀} | {字段文本}" if 字段文本 else 前缀


def 创建日志记录器(日志名称: str, 输出目录: Path = 日志目录, 时间戳: Optional[str] = None):
    路径 = 生成日志路径(日志名称, Path(输出目录), 时间戳 or 生成时间戳())

    def 记录日志(事件: str, **字段) -> None:
        with 路径.open("a", encoding="utf-8") as 文件:
            文件.write(格式化日志行(事件, **字段) + "\n")

    return 路径, 记录日志


def 写日志(日志函数, 事件: str, **字段) -> None:
    if 日志函数 is None:
        return
    try:
        日志函数(事件, **字段)
    except TypeError:
        日志函数(格式化日志行(事件, **字段))


def 写入录制文件(
    记录点列表: List[Tuple[int, int]],
    输出目录: Path = 输出目录,
    时间戳: Optional[str] = None,
) -> Path:
    路径 = 生成输出路径(Path(输出目录), 时间戳 or 生成时间戳())
    内容 = "\n".join(格式化坐标行(x, y) for x, y in 记录点列表)
    路径.write_text(内容, encoding="utf-8")
    return 路径


class 自动坐标录制器:
    def __init__(
        self,
        最小记录距离: int = 最小记录距离,
        最大单次跳变距离: int = 最大单次跳变距离,
        异常确认次数: int = 异常确认次数,
        日志函数=None,
    ) -> None:
        self.最小记录距离 = 最小记录距离
        self.最大单次跳变距离 = 最大单次跳变距离
        self.异常确认次数 = 异常确认次数
        self.日志函数 = 日志函数
        self.记录列表: List[Tuple[int, int]] = []
        self.异常线列表: List[Tuple[Tuple[int, int], Tuple[int, int]]] = []
        self.上一记录点: Optional[Tuple[int, int]] = None
        self._候选异常点: Optional[Tuple[int, int]] = None
        self._候选异常次数 = 0

    def 尝试记录(self, x: int, y: int) -> bool:
        点 = (int(x), int(y))
        if self.上一记录点 is None:
            写日志(self.日志函数, "event=record", 坐标=f"{点[0]},{点[1]}", 结果="首点记录")
            return self._接受记录点(点)

        距离 = 计算距离(self.上一记录点, 点)
        if 距离 < self.最小记录距离:
            写日志(
                self.日志函数,
                "event=record",
                坐标=f"{点[0]},{点[1]}",
                距离=f"{距离:.2f}",
                结果="忽略",
            )
            return False
        if 距离 <= self.最大单次跳变距离:
            self._候选异常点 = None
            self._候选异常次数 = 0
            写日志(
                self.日志函数,
                "event=record",
                坐标=f"{点[0]},{点[1]}",
                距离=f"{距离:.2f}",
                结果="记录",
            )
            return self._接受记录点(点)

        self.异常线列表.append((self.上一记录点, 点))
        if self._候选异常点 is not None and 计算距离(self._候选异常点, 点) <= self.最小记录距离:
            self._候选异常次数 += 1
        else:
            self._候选异常点 = 点
            self._候选异常次数 = 1
        写日志(
            self.日志函数,
            "event=record",
            坐标=f"{点[0]},{点[1]}",
            距离=f"{距离:.2f}",
            结果="异常候选",
            候选次数=self._候选异常次数,
        )
        if self._候选异常次数 >= self.异常确认次数:
            self._候选异常点 = None
            self._候选异常次数 = 0
            self._清理已转正异常线(点)
            写日志(
                self.日志函数,
                "event=record",
                坐标=f"{点[0]},{点[1]}",
                距离=f"{距离:.2f}",
                结果="异常转正",
            )
            return self._接受记录点(点)
        return False

    def _接受记录点(self, 点: Tuple[int, int]) -> bool:
        self.记录列表.append(点)
        self.上一记录点 = 点
        return True

    def _清理已转正异常线(self, 点: Tuple[int, int]) -> None:
        self.异常线列表 = [
            异常线 for 异常线 in self.异常线列表
            if 计算距离(异常线[1], 点) > self.最小记录距离
        ]

    def 清空(self) -> None:
        self.记录列表.clear()
        self.异常线列表.clear()
        self.上一记录点 = None
        self._候选异常点 = None
        self._候选异常次数 = 0


def 绘制轨迹预览(
    底图: np.ndarray,
    当前点: Optional[Tuple[int, int]],
    记录点列表: List[Tuple[int, int]],
    异常线列表: Optional[List[Tuple[Tuple[int, int], Tuple[int, int]]]] = None,
) -> np.ndarray:
    结果 = 底图.copy() if 当前点 is None else 基础模块.绘制预览图(底图, 当前点[0], 当前点[1])
    for 起点, 终点 in 异常线列表 or []:
        cv2.line(结果, 起点, 终点, (0, 255, 0), 1)
    if len(记录点列表) >= 2:
        cv2.polylines(结果, [np.array(记录点列表, dtype=np.int32)], False, (0, 255, 255), 2)
    for 点 in 记录点列表:
        cv2.circle(结果, 点, 4, (0, 255, 255), -1)
    return 结果


class 自动录制坐标应用:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("自动录制坐标工具")
        self.root.geometry("920x780+220+20")
        self.root.minsize(780, 640)

        self.识别器 = 基础模块.实时坐标角度识别器()
        self.录制器 = 自动坐标录制器()
        self.running = False
        self.recording = False
        self.stop_event = threading.Event()
        self.worker: Optional[threading.Thread] = None
        self.queue: "queue.Queue[Tuple[str, object]]" = queue.Queue()
        self.current_state: Optional[基础模块.识别状态] = None
        self.last_saved_path: Optional[Path] = None
        self.preview_photo = None
        self.log_path: Optional[Path] = None
        self._记录日志 = None

        self.state_var = tk.StringVar(value="坐标: -- | 角度: -- | 录制: 未开始 | 点数: 0")
        self.status_var = tk.StringVar(value="未开始")
        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.after(100, self._drain_queue)

    def _build_ui(self) -> None:
        outer = ttk.Frame(self.root, padding=12)
        outer.pack(fill="both", expand=True)

        buttons = ttk.Frame(outer)
        buttons.pack(fill="x", pady=(0, 10))
        self.start_button = ttk.Button(buttons, text="开始检测", command=self.start_detection)
        self.start_button.pack(side="left", padx=(0, 8))
        self.stop_button = ttk.Button(buttons, text="停止检测", command=self.stop_detection, state="disabled")
        self.stop_button.pack(side="left", padx=(0, 8))
        self.start_record_button = ttk.Button(buttons, text="开始录制", command=self.start_recording)
        self.start_record_button.pack(side="left", padx=(0, 8))
        self.stop_record_button = ttk.Button(buttons, text="停止录制", command=self.stop_recording, state="disabled")
        self.stop_record_button.pack(side="left", padx=(0, 8))
        ttk.Button(buttons, text="清空本次记录", command=self.clear_records).pack(side="left")

        ttk.Label(outer, textvariable=self.state_var, font=("Segoe UI", 14, "bold")).pack(anchor="w")
        ttk.Label(outer, textvariable=self.status_var).pack(anchor="w", pady=(4, 10))
        self.preview_label = tk.Label(outer, bg="#111111", relief="sunken")
        self.preview_label.pack(fill="both", expand=True)
        self.record_text = tk.Text(outer, height=8)
        self.record_text.pack(fill="x", pady=(10, 0))

        self._刷新预览()

    def start_detection(self) -> None:
        if self.running:
            return
        self.running = True
        self.stop_event.clear()
        self.log_path, self._记录日志 = 创建日志记录器("录制工具")
        self.录制器.日志函数 = self._记录日志
        写日志(self._记录日志, "event=detect_start")
        self.start_button.config(state="disabled")
        self.stop_button.config(state="normal")
        self.status_var.set("检测中...")
        self.worker = threading.Thread(target=self._worker_loop, daemon=True)
        self.worker.start()

    def stop_detection(self) -> None:
        if self.recording:
            self.stop_recording()
        self.running = False
        self.stop_event.set()
        写日志(self._记录日志, "event=detect_stop")

    def start_recording(self) -> None:
        if not self.running:
            self.status_var.set("请先开始检测")
            return
        if self.recording:
            return
        self.recording = True
        self.last_saved_path = None
        self.录制器.清空()
        self._刷新文本区()
        self.start_record_button.config(state="disabled")
        self.stop_record_button.config(state="normal")
        self.status_var.set(f"录制中，移动距离达到 {self.录制器.最小记录距离} 才会追加")
        写日志(
            self._记录日志,
            "event=record_start",
            最小记录距离=self.录制器.最小记录距离,
            最大单次跳变距离=self.录制器.最大单次跳变距离,
            异常确认次数=self.录制器.异常确认次数,
        )
        self._刷新状态栏()
        self._刷新预览()

    def stop_recording(self) -> None:
        if not self.recording:
            return
        self.recording = False
        self.start_record_button.config(state="normal")
        self.stop_record_button.config(state="disabled")
        if not self.录制器.记录列表:
            self.last_saved_path = None
            self.status_var.set("本次无记录，未保存文件")
            写日志(self._记录日志, "event=record_stop", 结果="无记录")
        else:
            self.last_saved_path = 写入录制文件(self.录制器.记录列表)
            self.status_var.set(f"已自动保存到: {self.last_saved_path}")
            写日志(
                self._记录日志,
                "event=record_stop",
                结果="已保存",
                文件=str(self.last_saved_path),
                点数=len(self.录制器.记录列表),
            )
        self._刷新状态栏()

    def clear_records(self) -> None:
        self.last_saved_path = None
        self.录制器.清空()
        self._刷新文本区()
        self.status_var.set("已清空本次记录")
        写日志(self._记录日志, "event=record_clear")
        self._刷新状态栏()
        self._刷新预览()

    def _worker_loop(self) -> None:
        while not self.stop_event.is_set():
            try:
                self.queue.put(("state", self.识别器.读取状态()))
            except Exception as exc:
                写日志(self._记录日志, "event=detect_error", 错误=str(exc))
                self.queue.put(("error", str(exc)))
            self.stop_event.wait(基础模块.循环间隔)
        self.queue.put(("stopped", None))

    def _drain_queue(self) -> None:
        while True:
            try:
                kind, payload = self.queue.get_nowait()
            except queue.Empty:
                break
            if kind == "state":
                self._update_state(payload)
            elif kind == "error":
                self.status_var.set(f"识别失败: {payload}")
            elif kind == "stopped":
                self.start_button.config(state="normal")
                self.stop_button.config(state="disabled")
                if self.last_saved_path is None:
                    self.status_var.set("已停止检测")
                else:
                    self.status_var.set(f"已停止检测 | 已自动保存到: {self.last_saved_path}")
        self.root.after(100, self._drain_queue)

    def _update_state(self, state: 基础模块.识别状态) -> None:
        if not self.running:
            return
        self.current_state = state
        基础模块.写入定位文件(state.x, state.y, state.angle)
        写日志(
            self._记录日志,
            "event=state",
            坐标=f"{state.x},{state.y}",
            角度=f"{state.angle:.2f}",
            地图=state.map_method,
            录制="是" if self.recording else "否",
        )
        if self.recording and self.录制器.尝试记录(state.x, state.y):
            self.record_text.insert("end", 格式化坐标行(state.x, state.y) + "\n")
            self.record_text.see("end")
        self._刷新状态栏()
        self._刷新预览()

    def _刷新状态栏(self) -> None:
        state = self.current_state
        if state is None:
            self.state_var.set(
                f"坐标: -- | 角度: -- | 录制: {'进行中' if self.recording else '未开始'} | 点数: {len(self.录制器.记录列表)}"
            )
            return
        self.state_var.set(
            f"坐标: ({state.x}, {state.y}) | 角度: {state.angle:.2f} | "
            f"地图: {state.map_method} | 录制: {'进行中' if self.recording else '未开始'} | "
            f"点数: {len(self.录制器.记录列表)}"
        )

    def _刷新文本区(self) -> None:
        self.record_text.delete("1.0", "end")
        if self.录制器.记录列表:
            self.record_text.insert(
                "1.0",
                "\n".join(格式化坐标行(x, y) for x, y in self.录制器.记录列表) + "\n",
            )

    def _刷新预览(self) -> None:
        当前点 = None if self.current_state is None else (self.current_state.x, self.current_state.y)
        预览图 = 绘制轨迹预览(
            self.识别器.地图匹配器.big_map,
            当前点,
            self.录制器.记录列表,
            self.录制器.异常线列表,
        )
        self.preview_photo = 基础模块.缩放为Tk图片(预览图, max_width=预览宽度)
        self.preview_label.config(image=self.preview_photo)

    def close(self) -> None:
        if self.recording:
            self.stop_recording()
        self.stop_event.set()
        self.running = False
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    自动录制坐标应用(root)
    root.mainloop()


if __name__ == "__main__":
    main()
