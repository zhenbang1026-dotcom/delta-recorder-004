from __future__ import annotations

"""
小地图定位器 - 基于SIFT特征匹配的实时位置识别系统

该模块通过截取游戏小地图区域，使用SIFT特征匹配算法在大地图上定位当前位置。
主要功能包括：
- 实时截取小地图区域
- SIFT特征点检测与匹配
- RANSAC单应性变换计算精确坐标
- 可视化显示当前在大地图上的位置
- 支持多线程异步处理避免UI卡顿
"""
import cv2
import numpy as np
from PIL import ImageGrab, Image, ImageTk
import time
import threading
import tkinter as tk
from tkinter import ttk
from pathlib import Path

# ================== 配置常量 ==================
SMALL_MAP_BOX = (57, 116, 200, 235)
BIG_MAP_PATH = "maps/DB.png"
SIZE1 = 143  # 小地图宽
SIZE2 = 119  # 小地图高

MAX_DISPLAY_WIDTH = 600  # 显示窗口的最大宽度（等比缩放）
LOOP_INTERVAL = 0.1     # 检测循环间隔（秒）
DEFAULT_SEARCH_MARGIN = 220
DEFAULT_TEMPLATE_THRESHOLD = 0.35
DEFAULT_MASK_INSET = 6
DEFAULT_TEMPLATE_PEAK_DELTA = 0.03
DEFAULT_TEMPLATE_DISTANCE_PENALTY = 0.1


def imread_unicode(path: str | Path) -> np.ndarray:
    """
    读取支持中文路径的图片
    """
    data = np.fromfile(str(path), dtype=np.uint8)
    image = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if image is None:
        raise FileNotFoundError(f"无法读取图片：{path}")
    return image


def create_minimap_feature_mask(width: int = SIZE1, height: int = SIZE2, inset: int = DEFAULT_MASK_INSET) -> np.ndarray:
    """
    创建小地图圆形特征掩码，尽量屏蔽半透明边缘和圆外背景。
    """
    mask = np.zeros((height, width), dtype=np.uint8)
    center = (width // 2, height // 2)
    radius = max(10, min(width, height) // 2 - inset)
    cv2.circle(mask, center, radius, 255, -1)
    return mask


def preprocess_match_image(image_bgr: np.ndarray) -> np.ndarray:
    """
    统一匹配预处理：灰度化 + 局部对比度增强。
    """
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    if hasattr(cv2, "createCLAHE"):
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        gray = clahe.apply(gray)
    return gray


def extract_minimap_from_fullscreen(fullscreen_bgr: np.ndarray, box: tuple[int, int, int, int] = SMALL_MAP_BOX) -> np.ndarray:
    """
    从全屏图中裁出小地图。
    """
    x1, y1, x2, y2 = box
    cropped = fullscreen_bgr[y1:y2, x1:x2].copy()
    if cropped.shape[:2] != (SIZE2, SIZE1):
        cropped = cv2.resize(cropped, (SIZE1, SIZE2))
    return cropped


class MapMatcher:
    """
    离线/实时通用的小地图匹配器。
    """

    def __init__(
        self,
        big_map_path: str = BIG_MAP_PATH,
        small_map_box: tuple[int, int, int, int] = SMALL_MAP_BOX,
        search_margin: int = DEFAULT_SEARCH_MARGIN,
        template_threshold: float = DEFAULT_TEMPLATE_THRESHOLD,
    ) -> None:
        self.small_map_box = small_map_box
        self.search_margin = search_margin
        self.template_threshold = template_threshold
        self.template_peak_delta = DEFAULT_TEMPLATE_PEAK_DELTA
        self.template_distance_penalty = DEFAULT_TEMPLATE_DISTANCE_PENALTY
        self.big_map = imread_unicode(big_map_path)
        self.big_map_preprocessed = preprocess_match_image(self.big_map)
        self.feature_mask = create_minimap_feature_mask()
        self.sift = cv2.SIFT_create()
        self.bf = cv2.BFMatcher(cv2.NORM_L2)
        self.kp_big, self.des_big = self.sift.detectAndCompute(self.big_map_preprocessed, None)
        self.last_xy: tuple[int, int] | None = None

    def _preprocess_minimap(self, image_bgr: np.ndarray) -> np.ndarray:
        if image_bgr.shape[:2] != (SIZE2, SIZE1):
            image_bgr = cv2.resize(image_bgr, (SIZE1, SIZE2))
        return preprocess_match_image(image_bgr)

    def _create_feature_mask(self) -> np.ndarray:
        return self.feature_mask

    def _select_template_peak(
        self,
        result: np.ndarray,
        expected_center: tuple[int, int] | None = None,
    ) -> tuple[int, int, float] | None:
        _, max_val, _, max_loc = cv2.minMaxLoc(result)
        if max_val < self.template_threshold:
            return None
        if expected_center is None:
            return max_loc[0] + SIZE1 // 2, max_loc[1] + SIZE2 // 2, float(max_val)
        cutoff = max(self.template_threshold, max_val - self.template_peak_delta)
        ys, xs = np.where(result >= cutoff)
        if len(xs) == 0:
            return max_loc[0] + SIZE1 // 2, max_loc[1] + SIZE2 // 2, float(max_val)
        centers_x = xs + SIZE1 // 2
        centers_y = ys + SIZE2 // 2
        distances = np.hypot(centers_x - expected_center[0], centers_y - expected_center[1])
        scores = result[ys, xs]
        normalized = np.minimum(distances / max(float(self.search_margin), 1.0), 1.0)
        adjusted = scores - normalized * self.template_distance_penalty
        best_index = int(np.argmax(adjusted))
        return int(centers_x[best_index]), int(centers_y[best_index]), float(scores[best_index])

    def _match_template(
        self,
        query_gray: np.ndarray,
        target_gray: np.ndarray,
        expected_center: tuple[int, int] | None = None,
    ) -> tuple[int, int, float] | None:
        try:
            result = cv2.matchTemplate(target_gray, query_gray, cv2.TM_CCORR_NORMED, mask=self.feature_mask)
        except cv2.error:
            masked_query = cv2.bitwise_and(query_gray, query_gray, mask=self.feature_mask)
            result = cv2.matchTemplate(target_gray, masked_query, cv2.TM_CCOEFF_NORMED)
        return self._select_template_peak(result, expected_center=expected_center)

    def _sift_match(self, query_gray: np.ndarray, target_gray: np.ndarray, x_offset: int = 0, y_offset: int = 0) -> tuple[int, int, float] | None:
        kp_query, des_query = self.sift.detectAndCompute(query_gray, self.feature_mask)
        if des_query is None or len(des_query) < 2:
            return None
        kp_target, des_target = self.sift.detectAndCompute(target_gray, None)
        if des_target is None or len(des_target) < 10:
            return None
        matches = self.bf.knnMatch(des_query, des_target, k=2)
        good_matches = []
        for mn in matches:
            if len(mn) < 2:
                continue
            m, n = mn
            if m.distance < 0.75 * n.distance:
                good_matches.append(m)
        if len(good_matches) < 10:
            return None
        src_pts = np.float32([kp_query[m.queryIdx].pt for m in good_matches]).reshape(-1, 1, 2)
        dst_pts = np.float32([kp_target[m.trainIdx].pt for m in good_matches]).reshape(-1, 1, 2)
        matrix, _ = cv2.findHomography(src_pts, dst_pts, cv2.RANSAC, 5.0)
        if matrix is None:
            return None
        center_query = np.float32([[[SIZE1 // 2, SIZE2 // 2]]])
        center_target = cv2.perspectiveTransform(center_query, matrix)[0][0]
        return int(center_target[0]) + x_offset, int(center_target[1]) + y_offset, float(len(good_matches))

    def _match_in_region(
        self,
        query_gray: np.ndarray,
        target_gray: np.ndarray,
        x_offset: int = 0,
        y_offset: int = 0,
        expected_center: tuple[int, int] | None = None,
    ) -> tuple[int, int, str] | None:
        template_result = self._match_template(query_gray, target_gray, expected_center=expected_center)
        if template_result is not None:
            x, y, _score = template_result
            return x + x_offset, y + y_offset, "template"
        sift_result = self._sift_match(query_gray, target_gray, x_offset=x_offset, y_offset=y_offset)
        if sift_result is not None:
            x, y, _score = sift_result
            return x, y, "sift"
        return None

    def _try_local_match(self, query_gray: np.ndarray, feature_mask: np.ndarray) -> tuple[int, int, str] | None:
        if self.last_xy is None:
            return None
        x, y = self.last_xy
        left = max(0, x - self.search_margin)
        top = max(0, y - self.search_margin)
        right = min(self.big_map_preprocessed.shape[1], x + self.search_margin)
        bottom = min(self.big_map_preprocessed.shape[0], y + self.search_margin)
        region = self.big_map_preprocessed[top:bottom, left:right]
        if region.shape[0] < SIZE2 or region.shape[1] < SIZE1:
            return None
        expected_center = (x - left, y - top)
        return self._match_in_region(
            query_gray,
            region,
            x_offset=left,
            y_offset=top,
            expected_center=expected_center,
        )

    def _try_global_match(self, query_gray: np.ndarray, feature_mask: np.ndarray) -> tuple[int, int, str] | None:
        return self._match_in_region(
            query_gray,
            self.big_map_preprocessed,
            expected_center=self.last_xy,
        )

    def locate_minimap(self, small_map_bgr: np.ndarray) -> dict:
        query_gray = self._preprocess_minimap(small_map_bgr)
        feature_mask = self._create_feature_mask()
        result = None
        if self.last_xy is not None:
            result = self._try_local_match(query_gray, feature_mask)
        if result is None:
            result = self._try_global_match(query_gray, feature_mask)
        if result is None:
            return {"success": False, "x": None, "y": None, "method": None}
        x, y, method = result
        self.last_xy = (x, y)
        return {"success": True, "x": x, "y": y, "method": method}

    def locate_from_fullscreen(self, fullscreen_bgr: np.ndarray) -> dict:
        return self.locate_minimap(extract_minimap_from_fullscreen(fullscreen_bgr, self.small_map_box))


class MapLocatorApp:
    """
    小地图定位图形界面应用
    
    使用SIFT特征匹配算法实时识别游戏小地图在大地图中的位置。
    
    Attributes:
        root (tk.Tk): Tkinter根窗口
        big_map (numpy.ndarray): 大地图BGR图像
        big_map_gray (numpy.ndarray): 大地图灰度图
        sift: SIFT特征检测器对象
        bf: BFMatcher暴力匹配器对象
        kp_big (list): 大地图关键点列表
        des_big (numpy.ndarray): 大地图描述符矩阵
        running (bool): 检测运行状态标志
        thread (threading.Thread): 后台检测线程
        scale (float): 显示缩放比例
        display_w (int): 缩放后显示宽度
        display_h (int): 缩放后显示高度
    """
    def __init__(self, root):
        """
        初始化定位器应用
        
        加载大地图、初始化SIFT检测器、预计算大地图特征、构建UI。
        
        Args:
            root (tk.Tk): Tkinter根窗口对象
            
        Raises:
            FileNotFoundError: 大地图文件不存在时抛出
        """
        self.root = root
        self.root.title("小地图定位器")

        # 读取大地图并转换为灰度图
        self.big_map = cv2.imread(BIG_MAP_PATH)
        if self.big_map is None:
            raise FileNotFoundError(f"未找到大地图文件: {BIG_MAP_PATH}")
        self.big_map_gray = cv2.cvtColor(self.big_map, cv2.COLOR_BGR2GRAY)

        # 仅初始化一次 SIFT 与匹配器，并预计算大地图特征
        self.sift = cv2.SIFT_create()
        self.bf = cv2.BFMatcher(cv2.NORM_L2)
        self.kp_big, self.des_big = self.sift.detectAndCompute(self.big_map_gray, None)

        # 线程控制
        self.running = False
        self.thread = None

        # 等比缩放比例
        self.scale = MAX_DISPLAY_WIDTH / self.big_map.shape[1]
        self.display_w = int(self.big_map.shape[1] * self.scale)
        self.display_h = int(self.big_map.shape[0] * self.scale)

        self._build_ui()
        self._show_image(self.big_map)

    # ---------- UI构建 ----------
    def _build_ui(self):
        """
        构建用户界面布局
        
        界面结构：
        - 顶部：开始/停止按钮
        - 中部：坐标显示标签
        - 中部：状态显示标签
        - 底部：画布显示大地图和标记
        """
        main = ttk.Frame(self.root, padding="10")
        main.grid(row=0, column=0, sticky="nsew")

        # 按钮区
        btn_frame = ttk.Frame(main)
        btn_frame.grid(row=0, column=0, columnspan=2, pady=(0, 8))

        self.start_btn = ttk.Button(btn_frame, text="开始检测", command=self.start_detection)
        self.start_btn.grid(row=0, column=0, padx=5)

        self.stop_btn = ttk.Button(btn_frame, text="停止检测",
                                   command=self.stop_detection, state=tk.DISABLED)
        self.stop_btn.grid(row=0, column=1, padx=5)

        # 坐标显示
        self.coord_label = ttk.Label(main, text="坐标: --",
                                     font=("Arial", 11, "bold"))
        self.coord_label.grid(row=1, column=0, columnspan=2, pady=(0, 4))

        # 状态显示
        self.status_label = ttk.Label(main, text="状态: 已停止", foreground="gray")
        self.status_label.grid(row=2, column=0, columnspan=2, pady=(0, 8))

        # 画布（等比缩放后的大小）
        self.canvas = tk.Canvas(main, width=self.display_w,
                                height=self.display_h, bg="black")
        self.canvas.grid(row=3, column=0, columnspan=2)

        self._tk_img = None  # 防止被 GC 回收

    def _show_image(self, cv_img):
        """
        在画布上等比缩放显示图像
        
        将OpenCV图像转换为Tkinter兼容格式并按比例缩放显示。
        
        Args:
            cv_img (numpy.ndarray): BGR格式输入图像
        """
        scaled = cv2.resize(cv_img, (self.display_w, self.display_h),
                            interpolation=cv2.INTER_AREA)
        rgb = cv2.cvtColor(scaled, cv2.COLOR_BGR2RGB)
        pil_img = Image.fromarray(rgb)
        self._tk_img = ImageTk.PhotoImage(image=pil_img)
        self.canvas.delete("all")
        self.canvas.create_image(self.display_w // 2, self.display_h // 2,
                                 image=self._tk_img)

    # ---------- 控制逻辑 ----------
    def start_detection(self):
        """
        启动检测循环
        
        创建后台线程开始周期性执行截图和特征匹配。
        """
        if self.running:
            return
        self.running = True
        self.start_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        self._set_status("检测中...", "green")
        self.thread = threading.Thread(target=self._detection_loop, daemon=True)
        self.thread.start()

    def stop_detection(self):
        """
        停止检测循环
        
        设置停止标志并等待后台线程退出。
        """
        if not self.running:
            return
        self.running = False
        self.start_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)
        self._set_status("已停止", "gray")

    def _set_status(self, text, color):
        """
        更新状态显示文本
        
        Args:
            text (str): 状态描述文本
            color (str): 文本颜色
        """
        self.status_label.config(text=f"状态: {text}", foreground=color)

    def _set_coord(self, x, y):
        """
        更新坐标显示
        
        Args:
            x (int): 大地图X坐标
            y (int): 大地图Y坐标
        """
        self.coord_label.config(text=f"坐标: ({x}, {y})")

    # ---------- 检测线程 ----------
    def _detection_loop(self):
        """
        后台检测主循环
        
        周期性执行单次检测并通过线程安全方式更新UI。
        异常会被捕获并通过after方法传递到主线程显示。
        """
        while self.running:
            try:
                res = self._detect_once()
                if res is not None:
                    img, x, y = res
                    # 通过 after 在主线程更新 UI
                    self.root.after(0, self._on_frame_ok, img, x, y)
                else:
                    self.root.after(0, self._set_status, "匹配点不足", "orange")
            except Exception as e:
                self.root.after(0, self._set_status, f"错误: {e}", "red")
            time.sleep(LOOP_INTERVAL)

    def _on_frame_ok(self, img, x, y):
        """
        处理成功的检测结果（在主线程中执行）
        
        Args:
            img (numpy.ndarray): 标注后的结果图像
            x (int): 检测到的X坐标
            y (int): 检测到的Y坐标
        """
        if not self.running:
            return
        self._set_coord(x, y)
        self._show_image(img)
        self._set_status("检测中...", "green")

    # ---------- 单次检测核心算法 ----------
    def _detect_once(self):
        """
        执行单次小地图截图和特征匹配检测
        
        算法流程：
        1. 截取屏幕指定区域获取小地图
        2. 调整尺寸到标准大小
        3. 提取SIFT特征点和描述符
        4. 使用BFMatcher进行KNN匹配（k=2）
        5. Lowe's ratio test筛选优质匹配点
        6. RANSAC计算单应性矩阵
        7. 透视变换得到中心点在大地图的坐标
        8. 绘制标记框和坐标文本
        
        Returns:
            tuple[numpy.ndarray, int, int] or None: 
                成功时返回(标注图像, X坐标, Y坐标)，失败返回None
        """
        try:
            import 截图模块 as _cap
            small_map = _cap.grab_region(*SMALL_MAP_BOX)
        except Exception:
            small_map = None
        if small_map is None:
            screenshot = ImageGrab.grab(bbox=SMALL_MAP_BOX)
            small_map = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)

        if small_map.shape[:2] != (SIZE2, SIZE1):
            small_map = cv2.resize(small_map, (SIZE1, SIZE2))

        gray = cv2.cvtColor(small_map, cv2.COLOR_BGR2GRAY)

        kp_query, des_query = self.sift.detectAndCompute(gray, None)
        if des_query is None or len(des_query) < 2:
            return None

        matches = self.bf.knnMatch(des_query, self.des_big, k=2)

        good_matches = []
        for mn in matches:
            if len(mn) < 2:
                continue
            m, n = mn
            if m.distance < 0.75 * n.distance:
                good_matches.append(m)

        if len(good_matches) < 10:
            return None

        src_pts = np.float32([kp_query[m.queryIdx].pt for m in good_matches]).reshape(-1, 1, 2)
        dst_pts = np.float32([self.kp_big[m.trainIdx].pt for m in good_matches]).reshape(-1, 1, 2)

        M, mask = cv2.findHomography(src_pts, dst_pts, cv2.RANSAC, 5.0)
        if M is None:
            return None

        center_query = np.float32([[[SIZE1 // 2, SIZE2 // 2]]])
        center_big = cv2.perspectiveTransform(center_query, M)
        x, y = map(int, center_big[0][0])

        # 保存坐标到文件
        with open("location.txt", "w") as f:
            f.write(f"x: {x}\ny: {y}")

        # 在大地图上绘制标记
        result = self.big_map.copy()
        left = max(0, x - SIZE1 // 2)
        top = max(0, y - SIZE2 // 2)
        right = min(result.shape[1], x + SIZE1 // 2)
        bottom = min(result.shape[0], y + SIZE2 // 2)

        cv2.rectangle(result, (left, top), (right, bottom), (0, 0, 255), 2)
        cv2.circle(result, (x, y), 5, (0, 0, 255), -1)
        cv2.putText(result, f"({x}, {y})", (left + 5, max(15, top - 5)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)

        return result, x, y

    # ---------- 关闭清理 ----------
    def on_closing(self):
        """
        窗口关闭时的清理操作
        
        停止检测线程并销毁窗口，确保资源正确释放。
        """
        self.running = False
        if self.thread is not None and self.thread.is_alive():
            self.thread.join(timeout=1.0)
        self.root.destroy()


def main():
    """
    程序入口函数
    
    创建Tkinter窗口并启动MapLocatorApp应用。
    """
    root = tk.Tk()
    app = MapLocatorApp(root)
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    root.mainloop()


if __name__ == "__main__":
    main()
