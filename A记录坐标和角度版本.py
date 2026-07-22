from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional
import importlib.util
import math
import queue
import sys
import threading
import time
import tkinter as tk
import unicodedata
from tkinter import ttk

import cv2
import numpy as np
from PIL import Image, ImageTk


def _按文件名加载模块(模块名):
    目录 = Path(__file__).resolve().parent
    目标 = unicodedata.normalize("NFC", 模块名)
    for 路径 in 目录.glob("*.py"):
        if unicodedata.normalize("NFC", 路径.stem) == 目标:
            spec = importlib.util.spec_from_file_location(模块名, 路径)
            模块 = importlib.util.module_from_spec(spec)
            sys.modules[模块名] = 模块
            spec.loader.exec_module(模块)
            return 模块
    raise ModuleNotFoundError("No module named {!r}".format(模块名))


try:
    import A测试模版匹配 as 地图模块
except ModuleNotFoundError:
    地图模块 = _按文件名加载模块("A测试模版匹配")
try:
    import A测试角度识别 as 角度模块
except ModuleNotFoundError:
    角度模块 = _按文件名加载模块("A测试角度识别")


小地图区域 = 地图模块.SMALL_MAP_BOX
角度区域 = 角度模块.parse_bbox(角度模块.ANGLE_DEFAULT_BBOX)
大地图路径 = 地图模块.BIG_MAP_PATH
小地图宽度 = 地图模块.SIZE1
小地图高度 = 地图模块.SIZE2
循环间隔 = 0.1
预览宽度 = 600

默认角度颜色 = 角度模块.parse_color_list(",".join(角度模块.ANGLE_DEFAULT_COLORS))
角度容差 = int(角度模块.ANGLE_DEFAULT_TOLERANCE)
角度最小面积 = float(角度模块.ANGLE_DEFAULT_MIN_AREA)
模板匹配缩放 = 2.0
模板匹配阈值 = 0.6
模板匹配边缘裁剪 = 6
匹配最小缩放 = 1.0
匹配最大缩放 = 3.2
匹配最大旋转角度 = 15.0


@dataclass
class 识别状态:
    x: int
    y: int
    angle: float
    color_hex: str
    map_method: str = "sift"


def 格式化记录行(x: int, y: int, angle: float) -> str:
    return f"{int(x)},{int(y)},{float(angle):.1f}"


def 写入定位文件(x: int, y: int, angle: float, 路径: Optional[Path] = None) -> None:
    (路径 or Path("location.txt")).write_text(
        f"x: {x}\ny: {y}\nangle: {angle:.2f}",
        encoding="utf-8",
    )


def 缩放为Tk图片(image_bgr: np.ndarray, max_width: int = 预览宽度) -> ImageTk.PhotoImage:
    image = Image.fromarray(cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB))
    if image.width > max_width:
        scale = max_width / image.width
        image = image.resize((max_width, int(image.height * scale)), Image.Resampling.LANCZOS)
    return ImageTk.PhotoImage(image=image)


class 单独坐标识别器:
    """使用 A测试模版匹配.py 单独窗口同款 SIFT 识别逻辑。"""

    def __init__(self, 地图路径: str = 大地图路径) -> None:
        self.big_map = cv2.imread(str(地图路径))
        if self.big_map is None:
            self.big_map = 地图模块.imread_unicode(地图路径)
        self.big_map_gray = cv2.cvtColor(self.big_map, cv2.COLOR_BGR2GRAY)
        self.sift = cv2.SIFT_create()
        self.bf = cv2.BFMatcher(cv2.NORM_L2)
        self.kp_big, self.des_big = self.sift.detectAndCompute(self.big_map_gray, None)
        if self.des_big is None or len(self.kp_big) < 10:
            raise RuntimeError(f"大地图特征不足: {地图路径}")
        self.last_xy: Optional[tuple[int, int]] = None
        self.prev_xy: Optional[tuple[int, int]] = None
        self.lost_count = 0

    def locate_minimap(self, small_map_bgr) -> dict:
        if small_map_bgr.shape[:2] != (小地图高度, 小地图宽度):
            small_map_bgr = cv2.resize(small_map_bgr, (小地图宽度, 小地图高度))
        gray = cv2.cvtColor(small_map_bgr, cv2.COLOR_BGR2GRAY)
        kp_query, des_query = self.sift.detectAndCompute(gray, None)
        if des_query is None or len(des_query) < 2:
            return self._predict()

        result = {"success": False, "x": None, "y": None, "method": None}
        if self.last_xy is not None:
            result = self._match_local(gray, kp_query, des_query)
        if not result["success"]:
            result = self._match_sift(kp_query, des_query, self.kp_big, self.des_big)
        if not result["success"]:
            result = self._match_template(gray)
        if not result["success"]:
            result = self._predict()
        if result["success"]:
            self._remember(result["x"], result["y"], result["method"] == "predict")
        return result

    def _match_sift(
        self,
        kp_query,
        des_query,
        kp_target,
        des_target,
        ratio: float = 0.75,
        min_good: int = 10,
        x_offset: int = 0,
        y_offset: int = 0,
        method: str = "sift",
    ) -> dict:
        matches = self.bf.knnMatch(des_query, des_target, k=2)
        good = []
        for mn in matches:
            if len(mn) >= 2 and mn[0].distance < ratio * mn[1].distance:
                good.append(mn[0])
        if len(good) < min_good:
            return {"success": False, "x": None, "y": None, "method": None}

        src = np.float32([kp_query[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
        dst = np.float32([kp_target[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)
        matrix, inlier_mask = cv2.estimateAffinePartial2D(
            src, dst, method=cv2.RANSAC, ransacReprojThreshold=5.0
        )
        if matrix is None:
            return {"success": False, "x": None, "y": None, "method": None}
        scale = float(np.hypot(matrix[0, 0], matrix[1, 0]))
        rotation = abs(math.degrees(math.atan2(matrix[1, 0], matrix[0, 0])))
        if not (匹配最小缩放 <= scale <= 匹配最大缩放) or rotation > 匹配最大旋转角度:
            return {"success": False, "x": None, "y": None, "method": None}

        center = np.float32([小地图宽度 // 2, 小地图高度 // 2, 1.0])
        x = float(matrix[0] @ center)
        y = float(matrix[1] @ center)
        inliers = int(inlier_mask.sum()) if inlier_mask is not None else len(good)
        return {
            "success": True,
            "x": int(x) + x_offset,
            "y": int(y) + y_offset,
            "method": method,
            "inliers": inliers,
        }

    def _match_local(self, gray, kp_query, des_query) -> dict:
        margin = 180
        last_x, last_y = self.last_xy
        left = max(0, last_x - margin)
        top = max(0, last_y - margin)
        right = min(self.big_map_gray.shape[1], last_x + margin)
        bottom = min(self.big_map_gray.shape[0], last_y + margin)
        region = self.big_map_gray[top:bottom, left:right]
        kp_target, des_target = self.sift.detectAndCompute(region, None)
        if des_target is None or len(kp_target) < 4:
            return {"success": False, "x": None, "y": None, "method": None}

        result = self._match_sift(
            kp_query, des_query, kp_target, des_target,
            ratio=0.9, min_good=4, x_offset=left, y_offset=top, method="local-sift"
        )
        if not result["success"]:
            return result
        if np.hypot(result["x"] - last_x, result["y"] - last_y) > margin:
            return {"success": False, "x": None, "y": None, "method": None}
        return result

    def _match_template(self, gray) -> dict:
        failed = {"success": False, "x": None, "y": None, "method": None}
        template = cv2.resize(
            gray,
            (int(小地图宽度 * 模板匹配缩放), int(小地图高度 * 模板匹配缩放)),
            interpolation=cv2.INTER_CUBIC,
        )
        margin = int(模板匹配边缘裁剪 * 模板匹配缩放)
        template = template[
            margin:template.shape[0] - margin, margin:template.shape[1] - margin
        ]
        if (
            template.shape[0] <= 0
            or template.shape[1] <= 0
            or template.shape[0] > self.big_map_gray.shape[0]
            or template.shape[1] > self.big_map_gray.shape[1]
        ):
            return failed
        scores = cv2.matchTemplate(self.big_map_gray, template, cv2.TM_CCOEFF_NORMED)
        _, score, _, loc = cv2.minMaxLoc(scores)
        if score < 模板匹配阈值:
            return failed
        return {
            "success": True,
            "x": int(loc[0] + template.shape[1] // 2),
            "y": int(loc[1] + template.shape[0] // 2),
            "method": "template",
        }

    def _predict(self) -> dict:
        if self.last_xy is None or self.lost_count >= 2:
            return {"success": False, "x": None, "y": None, "method": None}
        if self.prev_xy is None:
            x, y = self.last_xy
        else:
            x = self.last_xy[0] + (self.last_xy[0] - self.prev_xy[0])
            y = self.last_xy[1] + (self.last_xy[1] - self.prev_xy[1])
        return {"success": True, "x": int(x), "y": int(y), "method": "predict"}

    def _remember(self, x: int, y: int, predicted: bool = False) -> None:
        self.prev_xy = self.last_xy
        self.last_xy = (int(x), int(y))
        self.lost_count = self.lost_count + 1 if predicted else 0


def 绘制预览图(big_map: np.ndarray, x: int, y: int) -> np.ndarray:
    result = big_map.copy()
    left = max(0, x - 小地图宽度 // 2)
    top = max(0, y - 小地图高度 // 2)
    right = min(result.shape[1], x + 小地图宽度 // 2)
    bottom = min(result.shape[0], y + 小地图高度 // 2)
    cv2.rectangle(result, (left, top), (right, bottom), (0, 0, 255), 2)
    cv2.circle(result, (x, y), 5, (0, 0, 255), -1)
    cv2.putText(result, f"({x}, {y})", (left + 5, max(15, top - 5)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)
    return result


class 实时坐标角度识别器:
    def __init__(
        self,
        地图匹配器=None,
        角度分析器: Optional[Callable] = None,
        角度颜色=None,
    ) -> None:
        self.地图匹配器 = 地图匹配器 or 单独坐标识别器()
        self.角度分析器 = 角度分析器 or 角度模块.analyze_image
        self.角度颜色 = 角度颜色 or 默认角度颜色
        self.锁定角度颜色 = None

    def 从截图识别(self, small_map_bgr, angle_image_bgr) -> 识别状态:
        map_result = self.地图匹配器.locate_minimap(small_map_bgr)
        if not map_result["success"]:
            raise RuntimeError("无法识别当前位置")
        angle_result = self.角度分析器(
            angle_image_bgr,
            self.角度颜色,
            角度容差,
            角度最小面积,
            False,
            None,
            False,
        )
        self.锁定角度颜色 = None
        for 颜色 in self.角度颜色:
            if 颜色[0].upper() == str(angle_result.color_hex).upper():
                self.锁定角度颜色 = 颜色
                break
        return 识别状态(
            x=int(map_result["x"]),
            y=int(map_result["y"]),
            angle=float(angle_result.angle),
            color_hex=str(angle_result.color_hex),
            map_method=str(map_result.get("method") or "sift"),
        )

    def 读取状态(self) -> 识别状态:
        # 并集一次截图再裁（禁止对 ndarray 使用 `a or b`）
        small_map_bgr = None
        angle_image_bgr = None
        if hasattr(角度模块, "grab_regions_bgr"):
            key_map = tuple(int(v) for v in 小地图区域)
            key_ang = tuple(int(v) for v in 角度区域)
            crops = 角度模块.grab_regions_bgr(key_map, key_ang)
            small_map_bgr = crops.get(key_map)
            angle_image_bgr = crops.get(key_ang)
        if small_map_bgr is None:
            small_map_bgr, _ = 角度模块.grab_bbox_bgr(小地图区域)
        if angle_image_bgr is None:
            angle_image_bgr, _ = 角度模块.grab_bbox_bgr(角度区域)
        return self.从截图识别(small_map_bgr, angle_image_bgr)

    def 生成预览图(self, 状态: 识别状态) -> np.ndarray:
        return 绘制预览图(self.地图匹配器.big_map, 状态.x, 状态.y)


class 坐标角度记录应用:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("记录坐标和角度")
        self.root.geometry("860x740+220+20")
        self.root.minsize(760, 620)

        self.识别器 = 实时坐标角度识别器()
        self.running = False
        self.stop_event = threading.Event()
        self.worker: Optional[threading.Thread] = None
        self.queue: queue.Queue = queue.Queue()
        self.current_state: Optional[识别状态] = None
        self.preview_photo = None

        self.state_var = tk.StringVar(value="坐标: -- | 角度: --")
        self.status_var = tk.StringVar(value="未开始")
        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.after(100, self._drain_queue)

    def _build_ui(self) -> None:
        outer = ttk.Frame(self.root, padding=12)
        outer.pack(fill="both", expand=True)

        buttons = ttk.Frame(outer)
        buttons.pack(fill="x", pady=(0, 10))
        self.start_button = ttk.Button(buttons, text="开始检测", command=self.start)
        self.start_button.pack(side="left", padx=(0, 8))
        self.stop_button = ttk.Button(buttons, text="停止检测", command=self.stop, state="disabled")
        self.stop_button.pack(side="left", padx=(0, 8))
        ttk.Button(buttons, text="记录", command=self.record).pack(side="left")

        ttk.Label(outer, textvariable=self.state_var, font=("Segoe UI", 14, "bold")).pack(anchor="w")
        ttk.Label(outer, textvariable=self.status_var).pack(anchor="w", pady=(4, 10))
        self.preview_label = tk.Label(outer, bg="#111111", relief="sunken")
        self.preview_label.pack(fill="both", expand=True)
        self.record_text = tk.Text(outer, height=7)
        self.record_text.pack(fill="x", pady=(10, 0))

        self.preview_photo = 缩放为Tk图片(self.识别器.地图匹配器.big_map)
        self.preview_label.config(image=self.preview_photo)

    def start(self) -> None:
        if self.running:
            return
        self.running = True
        self.stop_event.clear()
        self.start_button.config(state="disabled")
        self.stop_button.config(state="normal")
        self.status_var.set("检测中...")
        self.worker = threading.Thread(target=self._worker_loop, daemon=True)
        self.worker.start()

    def stop(self) -> None:
        self.running = False
        self.stop_event.set()

    def record(self) -> None:
        if self.current_state is None:
            self.status_var.set("还没有可记录的识别结果")
            return
        line = 格式化记录行(self.current_state.x, self.current_state.y, self.current_state.angle)
        self.record_text.insert("end", line + "\n")
        self.record_text.see("end")
        self.status_var.set(f"已记录: {line}")

    def _worker_loop(self) -> None:
        while not self.stop_event.is_set():
            try:
                state = self.识别器.读取状态()
                preview = self.识别器.生成预览图(state)
                self.queue.put(("state", (state, preview)))
            except Exception as exc:
                self.queue.put(("error", str(exc)))
            self.stop_event.wait(循环间隔)
        self.queue.put(("stopped", None))

    def _drain_queue(self) -> None:
        while True:
            try:
                kind, payload = self.queue.get_nowait()
            except queue.Empty:
                break
            if kind == "state":
                state, preview = payload
                self._update_state(state, preview)
            elif kind == "error":
                self.status_var.set(f"识别失败: {payload}")
            elif kind == "stopped":
                self.start_button.config(state="normal")
                self.stop_button.config(state="disabled")
                self.status_var.set("已停止")
        self.root.after(100, self._drain_queue)

    def _update_state(self, state: 识别状态, preview_bgr: np.ndarray) -> None:
        if not self.running:
            return
        self.current_state = state
        self.state_var.set(
            f"坐标: ({state.x}, {state.y}) | 角度: {state.angle:.2f} | "
            f"颜色: #{state.color_hex} | 地图: {state.map_method}"
        )
        写入定位文件(state.x, state.y, state.angle)
        self.preview_photo = 缩放为Tk图片(preview_bgr)
        self.preview_label.config(image=self.preview_photo)

    def close(self) -> None:
        self.stop_event.set()
        self.running = False
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    坐标角度记录应用(root)
    root.mainloop()


if __name__ == "__main__":
    main()
