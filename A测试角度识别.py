"""
实时角度识别工具 - 从小地图标记计算朝向角度

该模块提供从游戏小地图中识别角色朝向角度的功能，支持：
- CLI命令行模式：处理单张图片并输出调试结果
- GUI交互模式：实时截图、连续识别、可视化展示
- 多颜色通道检测：支持多种颜色标记的识别
- HSV/BGR双模式颜色分割：提高识别精度
"""
from __future__ import annotations

import argparse
import math
import queue
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, scrolledtext

import cv2
import numpy as np
from PIL import Image, ImageGrab, ImageTk

from 角度融合 import 角度融合失败, 角度融合选择器, 角度观测

# ===========================================================================
# 常量配置
# ===========================================================================

DEFAULT_INTERVAL = 0.2
ANGLE_DEFAULT_COLORS = ["F0E791", "9AE77E", "95BBE8", "94BAE8", "94BAE7", "84A4CA", "8EB2DE"]
ANGLE_DEFAULT_IMAGE = "实时截图.png"
# 旧算法 ROI
ANGLE_LEGACY_BBOX = "119,161,146,188"
# text 雷达 ROI left,top,right,bottom
ANGLE_TEXT_BBOX = "34,78,227,271"
ANGLE_DEFAULT_BBOX = ANGLE_LEGACY_BBOX
ANGLE_DEFAULT_TOLERANCE = "45"
ANGLE_DEFAULT_MIN_AREA = "0"

# 角度模式：legacy=旧颜色轮廓 | text=text箭头（可加稳）
ANGLE_MODE_LEGACY = "legacy"
ANGLE_MODE_TEXT = "text"
ANGLE_MODE_FUSION = "fusion"
ANGLE_MODE_LABELS = {
    ANGLE_MODE_LEGACY: "旧算法（颜色轮廓）",
    ANGLE_MODE_TEXT: "text箭头算法",
    ANGLE_MODE_FUSION: "融合算法（三色精准主观测+Legacy降级）",
}
ANGLE_FUSION_LEGACY_REGION = (85, 83, 112, 110)
_angle_mode = ANGLE_MODE_LEGACY
_angle_mode_lock = threading.Lock()
_text_recognizer = None
_text_stabilizer = None
_fusion_selector = None
_fusion_precise_recognizer = None


class _AngleStabilizer:
    """TEXT 单层自适应滤波：只平滑小抖动，正常转向直接跟随。"""

    def __init__(
        self,
        alpha=0.65,
        smooth_threshold=4.0,
    ):
        self.alpha = float(alpha)
        self.smooth_threshold = float(smooth_threshold)
        self.last = None

    def reset(self):
        self.last = None

    def force(self, angle: float) -> float:
        """外部稳采样后强制对齐（转向后中位数）。"""
        angle = float(angle) % 360.0
        self.last = angle
        return angle

    @staticmethod
    def _delta(a, b):
        return (b - a + 180.0) % 360.0 - 180.0

    def update(self, angle: float) -> float:
        angle = float(angle) % 360.0
        if self.last is None:
            self.last = angle
            return angle
        d = self._delta(self.last, angle)
        if abs(d) <= self.smooth_threshold:
            self.last = (self.last + self.alpha * d) % 360.0
        else:
            self.last = angle
        return float(self.last)


def _get_text_recognizer():
    global _text_recognizer
    if _text_recognizer is not None:
        return _text_recognizer
    import importlib.util
    import unicodedata

    base = Path(__file__).resolve().parent
    target = unicodedata.normalize("NFC", "识别角度")
    for py in base.glob("*.py"):
        if unicodedata.normalize("NFC", py.stem) == target:
            name = "text_angle_mod_004"
            spec = importlib.util.spec_from_file_location(name, py)
            mod = importlib.util.module_from_spec(spec)
            sys.modules[name] = mod
            spec.loader.exec_module(mod)
            _text_recognizer = mod.默认识别器(静默=True)
            return _text_recognizer
    raise ModuleNotFoundError("未找到 识别角度.py")


def _get_text_stabilizer():
    global _text_stabilizer
    if _text_stabilizer is None:
        _text_stabilizer = _AngleStabilizer()
    return _text_stabilizer


def force_text_stabilizer_angle(angle: float) -> float:
    """转向后稳采样写回滤波器，避免下一帧又被旧 last 拖住。"""
    return _get_text_stabilizer().force(float(angle))


def _get_fusion_selector():
    global _fusion_selector
    if _fusion_selector is None:
        _fusion_selector = 角度融合选择器()
    return _fusion_selector


def _get_fusion_precise_recognizer():
    global _fusion_precise_recognizer
    if _fusion_precise_recognizer is None:
        from 三色精准角度 import 三色精准角度识别器

        _fusion_precise_recognizer = 三色精准角度识别器()
    return _fusion_precise_recognizer


def reset_fusion_selector() -> None:
    if _fusion_selector is not None:
        _fusion_selector.reset()
    if _fusion_precise_recognizer is not None:
        _fusion_precise_recognizer.reset()


def force_fusion_selector_angle(angle: float) -> float:
    return _get_fusion_selector().force(float(angle))


def normalize_angle_mode(mode: str | None) -> str:
    value = (mode or ANGLE_MODE_LEGACY).strip().lower()
    aliases = {
        "legacy": ANGLE_MODE_LEGACY,
        "old": ANGLE_MODE_LEGACY,
        "旧": ANGLE_MODE_LEGACY,
        "旧算法": ANGLE_MODE_LEGACY,
        "text": ANGLE_MODE_TEXT,
        "text_stable": ANGLE_MODE_TEXT,
        "new": ANGLE_MODE_TEXT,
        "新": ANGLE_MODE_TEXT,
        "箭头": ANGLE_MODE_TEXT,
        "fusion": ANGLE_MODE_FUSION,
        "overall": ANGLE_MODE_FUSION,
        "融合": ANGLE_MODE_FUSION,
        "融合算法": ANGLE_MODE_FUSION,
    }
    if value in aliases:
        return aliases[value]
    if value in (ANGLE_MODE_LEGACY, ANGLE_MODE_TEXT, ANGLE_MODE_FUSION):
        return value
    raise ValueError(f"未知角度模式: {mode}")


def set_angle_mode(mode: str) -> str:
    global _angle_mode
    mode = normalize_angle_mode(mode)
    with _angle_mode_lock:
        _angle_mode = mode
        if mode == ANGLE_MODE_TEXT:
            _get_text_stabilizer().reset()
        elif mode == ANGLE_MODE_FUSION:
            reset_fusion_selector()
    return mode


def get_angle_mode() -> str:
    with _angle_mode_lock:
        return _angle_mode


def get_angle_bbox_str(mode: str | None = None) -> str:
    mode = normalize_angle_mode(mode or get_angle_mode())
    return ANGLE_TEXT_BBOX if mode in (ANGLE_MODE_TEXT, ANGLE_MODE_FUSION) else ANGLE_LEGACY_BBOX


def get_angle_bbox(mode: str | None = None) -> tuple[int, int, int, int]:
    return parse_bbox(get_angle_bbox_str(mode))


def get_angle_mode_label(mode: str | None = None) -> str:
    mode = normalize_angle_mode(mode or get_angle_mode())
    return ANGLE_MODE_LABELS.get(mode, mode)


# ===========================================================================
# 通用工具函数
# ===========================================================================

def app_dir() -> Path:
    """
    获取应用程序所在目录
    
    自动判断是打包后的exe环境还是开发环境。
    
    Returns:
        Path: 应用程序目录路径
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def parse_bbox(value: str) -> tuple[int, int, int, int]:
    """
    解析边界框字符串为坐标元组
    
    Args:
        value (str): 格式为"x1,y1,x2,y2"的字符串
        
    Returns:
        tuple[int, int, int, int]: (x1, y1, x2, y2) 左上角和右下角坐标
        
    Raises:
        ValueError: 格式错误或坐标无效时抛出
    """
    parts = [int(item.strip()) for item in value.split(",")]
    if len(parts) != 4:
        raise ValueError("bbox 格式必须是 x1,y1,x2,y2")
    x1, y1, x2, y2 = parts
    if x2 <= x1 or y2 <= y1:
        raise ValueError("bbox 必须满足 x2 > x1 且 y2 > y1")
    return x1, y1, x2, y2


def parse_hex_color(value: str) -> tuple[int, int, int]:
    """
    解析十六进制颜色字符串为RGB元组
    
    Args:
        value (str): 6位十六进制颜色字符串（可带#前缀）
        
    Returns:
        tuple[int, int, int]: (R, G, B) 颜色值
        
    Raises:
        ValueError: 格式错误时抛出
    """
    value = value.strip().lstrip("#")
    if len(value) != 6:
        raise ValueError("颜色必须是 6 位 RGB 十六进制，例如 9AE77E。")
    return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)


def parse_color_list(value: str) -> list[tuple[str, tuple[int, int, int]]]:
    """
    解析逗号分隔的颜色列表字符串
    
    Args:
        value (str): 多个十六进制颜色用逗号分隔的字符串
        
    Returns:
        list[tuple[str, tuple[int, int, int]]]: [(hex_str, (R,G,B)), ...] 列表
        
    Raises:
        ValueError: 没有有效颜色时抛出
    """
    color_hexes = [c.strip().lstrip("#").upper() for c in value.split(",") if c.strip()]
    if not color_hexes:
        raise ValueError("至少需要输入一个颜色。")
    return [(h, parse_hex_color(h)) for h in color_hexes]


def parse_region(value: str | None) -> tuple[int, int, int, int] | None:
    """
    解析识别区域字符串，支持空值
    
    Args:
        value (str or None): 格式为"x1,y1,x2,y2"的字符串或None
        
    Returns:
        tuple[int, int, int, int] or None: 解析后的区域坐标或None
        
    Raises:
        ValueError: 格式错误或坐标无效时抛出
    """
    if not value:
        return None
    parts = [int(p.strip()) for p in value.split(",")]
    if len(parts) != 4:
        raise ValueError("识别区域格式必须是 x1,y1,x2,y2。")
    x1, y1, x2, y2 = parts
    if x2 <= x1 or y2 <= y1:
        raise ValueError("识别区域必须满足 x2 > x1 且 y2 > y1。")
    return x1, y1, x2, y2


def imread_unicode(path: Path) -> np.ndarray:
    """
    读取支持Unicode路径的图片文件
    
    使用numpy+OpenCV组合方案解决中文路径问题。
    
    Args:
        path (Path): 图片文件路径
        
    Returns:
        numpy.ndarray: BGR格式图像数组
        
    Raises:
        FileNotFoundError: 文件无法读取时抛出
    """
    data = np.fromfile(str(path), dtype=np.uint8)
    image = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if image is None:
        raise FileNotFoundError(f"无法读取图片：{path}")
    return image


def imwrite_unicode(path: Path, image: np.ndarray) -> None:
    """
    保存支持Unicode路径的图片文件
    
    Args:
        path (Path): 输出文件路径
        image (numpy.ndarray): BGR格式图像数组
        
    Raises:
        ValueError: 编码失败时抛出
    """
    ok, encoded = cv2.imencode(path.suffix or ".png", image)
    if not ok:
        raise ValueError(f"无法保存图片：{path}")
    encoded.tofile(str(path))


def pil_to_bgr(image: Image.Image) -> np.ndarray:
    """
    将PIL图像转换为OpenCV BGR格式
    
    Args:
        image (Image.Image): PIL RGB图像对象
        
    Returns:
        numpy.ndarray: BGR格式图像数组
    """
    return cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)


def resize_bgr_for_tk(image_bgr: np.ndarray, max_size: tuple[int, int]) -> ImageTk.PhotoImage:
    """
    调整BGR图像尺寸以适配Tkinter显示
    
    保持宽高比缩放到最大尺寸内。
    
    Args:
        image_bgr (numpy.ndarray): BGR格式图像
        max_size (tuple[int, int]): (width, height) 最大显示尺寸
        
    Returns:
        ImageTk.PhotoImage: Tkinter兼容的图片对象
    """
    image = Image.fromarray(cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB))
    image.thumbnail(max_size, Image.Resampling.NEAREST)
    return ImageTk.PhotoImage(image)

# ===========================================================================
# 图像处理核心算法
# ===========================================================================

def create_demo_image(color_rgb: tuple[int, int, int]) -> np.ndarray:
    """
    创建演示用的小地图测试图像
    
    绘制模拟的角色图标和目标点，用于离线测试。
    
    Args:
        color_rgb (tuple[int, int, int]): 角色图标的RGB颜色
        
    Returns:
        numpy.ndarray: 240x240的BGR演示图像
    """
    image = np.full((240, 240, 3), 245, dtype=np.uint8)
    center, target = (120, 120), (168, 72)
    color_bgr = (color_rgb[2], color_rgb[1], color_rgb[0])
    cv2.line(image, center, target, (180, 180, 180), 2)
    cv2.circle(image, center, 18, color_bgr, -1)
    cv2.circle(image, target, 10, color_bgr, -1)
    cv2.circle(image, center, 82, (210, 210, 210), 2)
    cv2.putText(image, "demo minimap marker", (25, 225),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (70, 70, 70), 1, cv2.LINE_AA)
    return image


def crop_region(image: np.ndarray, region: tuple[int, int, int, int] | None) -> tuple[np.ndarray, tuple[int, int]]:
    """
    裁剪图像的指定区域
    
    自动处理边界溢出情况。
    
    Args:
        image (numpy.ndarray): BGR格式源图像
        region (tuple or None): 裁剪区域(x1,y1,x2,y2)，None则返回完整图像
        
    Returns:
        tuple[numpy.ndarray, tuple[int, int]]: (裁剪后的图像, 裁剪偏移量(x1,y1))
    """
    if region is None:
        return image.copy(), (0, 0)
    x1, y1, x2, y2 = region
    h, w = image.shape[:2]
    x1, x2 = max(0, min(x1, w)), max(0, min(x2, w))
    y1, y2 = max(0, min(y1, h)), max(0, min(y2, h))
    return image[y1:y2, x1:x2].copy(), (x1, y1)


def rgb_to_hsv_color(color_rgb: tuple[int, int, int]) -> tuple[int, int, int]:
    """
    将RGB颜色转换为HSV颜色空间
    
    Args:
        color_rgb (tuple[int, int, int]): RGB颜色值
        
    Returns:
        tuple[int, int, int]: (H, S, V) HSV颜色值，H范围0-179，S/V范围0-255
    """
    arr = np.uint8([[list(color_rgb)]])
    hsv = cv2.cvtColor(arr, cv2.COLOR_RGB2HSV)[0, 0]
    return int(hsv[0]), int(hsv[1]), int(hsv[2])


def color_threshold(image_bgr, color_rgb, tolerance, clean_mask, hsv_mode=False):
    """
    根据颜色阈值生成二值化掩码
    
    支持BGR直接阈值和HSV空间阈值两种模式：
    - BGR模式：在RGB空间对每个通道应用容差范围
    - HSV模式：分别对色相/饱和度/明度应用不同容差策略
    
    Args:
        image_bgr (numpy.ndarray): BGR格式输入图像
        color_rgb (tuple[int, int, int]): 目标RGB颜色
        tolerance (int): 颜色容差值
        clean_mask (bool): 是否执行形态学去噪
        hsv_mode (bool): 是否使用HSV空间分割
        
    Returns:
        numpy.ndarray: 单通道二值化掩码图像
    """
    if not hsv_mode:
        color_bgr = np.array([color_rgb[2], color_rgb[1], color_rgb[0]], dtype=np.int16)
        lower = np.clip(color_bgr - tolerance, 0, 255).astype(np.uint8)
        upper = np.clip(color_bgr + tolerance, 0, 255).astype(np.uint8)
        mask = cv2.inRange(image_bgr, lower, upper)
    else:
        h, s, v = rgb_to_hsv_color(color_rgb)
        hsv = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2HSV)
        h_tol = max(5, min(tolerance // 3, 20))
        s_tol = max(20, min(tolerance, 80))
        v_tol = max(20, min(tolerance, 80))
        h_low, h_high = (h - h_tol) % 180, (h + h_tol) % 180
        if h_low <= h_high:
            h_mask = cv2.inRange(hsv[:, :, 0], h_low, h_high)
        else:
            h_mask = cv2.bitwise_or(cv2.inRange(hsv[:, :, 0], 0, h_high),
                                    cv2.inRange(hsv[:, :, 0], h_low, 179))
        s_mask = cv2.inRange(hsv[:, :, 1], max(0, s - s_tol), min(255, s + s_tol))
        v_mask = cv2.inRange(hsv[:, :, 2], max(0, v - v_tol), min(255, v + v_tol))
        mask = cv2.bitwise_and(cv2.bitwise_and(h_mask, s_mask), v_mask)
    if clean_mask:
        kernel = np.ones((3, 3), np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    return mask


def contour_center(contour: np.ndarray) -> tuple[float, float] | None:
    """
    计算轮廓的质心坐标
    
    使用图像矩方法计算，退化情况下使用顶点平均。
    
    Args:
        contour (numpy.ndarray): OpenCV轮廓数据
        
    Returns:
        tuple[float, float] or None: (cx, cy) 质心坐标，无有效点时返回None
    """
    m = cv2.moments(contour)
    if m["m00"] == 0:
        pts = contour.reshape(-1, 2)
        if len(pts) == 0:
            return None
        return float(pts[:, 0].mean()), float(pts[:, 1].mean())
    return m["m10"] / m["m00"], m["m01"] / m["m00"]


def refine_center(mask: np.ndarray, contour: np.ndarray) -> tuple[float, float] | None:
    """
    亚像素级质心精修
    
    结合图像矩和最小外接圆进行二次校正，提高定位精度。
    
    Args:
        mask (numpy.ndarray): 二值化掩码图像
        contour (numpy.ndarray): OpenCV轮廓数据
        
    Returns:
        tuple[float, float] or None: 精修后的质心坐标
    """
    pts = contour.reshape(-1, 2).astype(np.float32)
    if len(pts) < 5:
        return contour_center(contour)
    cx, cy = contour_center(contour) or (float(pts[:, 0].mean()), float(pts[:, 1].mean()))
    try:
        (enc_cx, enc_cy), _ = cv2.minEnclosingCircle(pts)
        if abs(enc_cx - cx) < 6 and abs(enc_cy - cy) < 6:
            return float(enc_cx), float(enc_cy)
    except cv2.error:
        pass
    return cx, cy


def mask_peak_center(mask: np.ndarray) -> tuple[float, float, float] | None:
    """
    用距离变换估计单个连通色块的主圆中心和半径。
    """
    if cv2.countNonZero(mask) == 0:
        return None
    distance = cv2.distanceTransform(mask, cv2.DIST_L2, 3)
    _, max_value, _, max_loc = cv2.minMaxLoc(distance)
    if max_value <= 0:
        return None
    return float(max_loc[0]), float(max_loc[1]), float(max_value)


def estimate_single_contour_target(mask: np.ndarray, contour: np.ndarray) -> tuple[tuple[float, float], tuple[float, float]] | None:
    """
    当角色主体与朝向小尾巴连成一个轮廓时，基于主圆外残留区域估计朝向。
    """
    peak = mask_peak_center(mask)
    if peak is None:
        return None
    center_x, center_y, radius = peak
    pts = contour.reshape(-1, 2).astype(np.float32)
    deltas = pts - np.array([[center_x, center_y]], dtype=np.float32)
    norms = np.linalg.norm(deltas, axis=1)
    if len(norms) == 0:
        return None
    percentile_threshold = float(np.percentile(norms, 88))
    min_threshold = max(radius + 0.8, percentile_threshold)
    focus = norms >= min_threshold
    if not np.any(focus):
        focus = norms >= float(norms.max()) - 0.5
    if not np.any(focus):
        return None
    focus_deltas = deltas[focus]
    focus_norms = norms[focus]
    direction = focus_deltas.mean(axis=0)
    length = float(np.linalg.norm(direction))
    if length < 1e-6:
        return None
    reach = max(radius + 1.5, float(focus_norms.mean()))
    target_x = center_x + direction[0] / length * reach
    target_y = center_y + direction[1] / length * reach
    return (center_x, center_y), (float(target_x), float(target_y))


def estimate_far_color_target(mask: np.ndarray, origin: tuple[float, float]) -> tuple[float, float] | None:
    points_yx = np.column_stack(np.where(mask > 0))
    if len(points_yx) == 0:
        return None
    h, w = mask.shape[:2]
    points_xy = points_yx[:, ::-1].astype(np.float32)
    deltas = points_xy - np.array([[origin[0], origin[1]]], dtype=np.float32)
    distances = np.linalg.norm(deltas, axis=1)
    center_radius = max(2.5, min(3.5, min(w, h) * 0.14))
    far_mask = distances >= center_radius + 1.0
    if not np.any(far_mask):
        far_mask = distances >= max(1.0, float(np.percentile(distances, 90)))
    if not np.any(far_mask):
        return None
    far_points = points_xy[far_mask]
    far_distances = distances[far_mask]
    max_distance = float(far_distances.max())
    if max_distance <= center_radius + 0.5:
        return None
    tip_points = far_points[far_distances >= max_distance - 1.5]
    if len(tip_points) < 2:
        return None
    return float(tip_points[:, 0].mean()), float(tip_points[:, 1].mean())


def calculate_angle(origin: tuple[float, float], target: tuple[float, float]) -> float:
    """
    计算两点连线相对于垂直方向的角度
    
    角度定义：从正北方向顺时针旋转的角度（0-360度）。
    
    Args:
        origin (tuple[float, float]): 起点坐标(x, y)
        target (tuple[float, float]): 终点坐标(x, y)
        
    Returns:
        float: 角度值（0-360度）
    """
    return math.degrees(math.atan2(target[0] - origin[0], origin[1] - target[1])) % 360


def detect_angle(image_bgr, color_rgb, tolerance, min_area, clean_mask, hsv_mode=False):
    """
    从图像中检测指定颜色的两个标记点并计算角度
    
    算法流程：
    1. 颜色阈值分割生成掩码
    2. 轮廓提取和面积过滤
    3. 质心定位和精修
    4. 按面积排序选择最大的两个轮廓
    5. 计算角度
    
    Args:
        image_bgr (numpy.ndarray): BGR格式输入图像
        color_rgb (tuple[int, int, int]): 目标RGB颜色
        tolerance (int): 颜色容差
        min_area (float): 最小轮廓面积阈值
        clean_mask (bool): 是否清理噪声
        hsv_mode (bool): 是否使用HSV模式
        
    Returns:
        tuple[float, tuple, tuple, ndarray, list]: 
            - angle: 计算的角度值
            - origin: 较大轮廓的质心（作为原点）
            - target: 较小轮廓的质心（作为目标点）
            - mask: 二值化掩码
            - contours: 所有符合条件的轮廓列表
            
    Raises:
        RuntimeError: 找到的有效轮廓少于2个时抛出
    """
    mask = color_threshold(image_bgr, color_rgb, tolerance, clean_mask, hsv_mode)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    infos = []
    for c in contours:
        area = cv2.contourArea(c)
        if area < min_area:
            continue
        center = refine_center(mask, c)
        if center is not None:
            infos.append((area, center, c))
    if len(infos) < 2:
        raise RuntimeError(f"只找到 {len(infos)} 个颜色轮廓。")
    infos.sort(key=lambda x: x[0], reverse=True)
    origin, target = infos[0][1], infos[1][1]
    return calculate_angle(origin, target), origin, target, mask, [x[2] for x in infos]


def detect_angle_with_fallback(image_bgr, color_rgb, tolerance, min_area, clean_mask, hsv_mode=False):
    """
    使用截图中心点作为角色原点，优先从绿色外凸方向点估计朝向。
    """
    mask = color_threshold(image_bgr, color_rgb, tolerance, clean_mask, hsv_mode)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    h, w = mask.shape[:2]
    origin = ((w - 1) / 2.0, (h - 1) / 2.0)
    points_yx = np.column_stack(np.where(mask > 0))
    if len(points_yx) == 0:
        raise RuntimeError("只找到 0 个颜色像素。")

    points_xy = points_yx[:, ::-1].astype(np.float32)
    deltas = points_xy - np.array([[origin[0], origin[1]]], dtype=np.float32)
    distances = np.linalg.norm(deltas, axis=1)
    center_radius = max(2.5, min(3.5, min(w, h) * 0.14))
    if not np.any(distances <= center_radius):
        raise RuntimeError("颜色像素未覆盖截图中心，跳过该颜色。")

    infos = []
    for contour in contours:
        area = cv2.contourArea(contour)
        if area < min_area:
            continue
        center = refine_center(mask, contour)
        if center is not None:
            infos.append((area, center, contour))
    valid_contours = [x[2] for x in infos]
    if len(infos) >= 2:
        infos.sort(key=lambda x: x[0], reverse=True)
        origin_from_contour, target_from_contour = infos[0][1], infos[1][1]
        return calculate_angle(origin_from_contour, target_from_contour), origin_from_contour, target_from_contour, mask, valid_contours
    target = estimate_far_color_target(mask, origin)
    if target is None and infos:
        infos.sort(key=lambda x: x[0], reverse=True)
        fallback = estimate_single_contour_target(mask, infos[0][2])
        if fallback is not None:
            target = fallback[1]
    if target is None:
        raise RuntimeError("未找到可用的朝向目标点。")
    return calculate_angle(origin, target), origin, target, mask, valid_contours


def draw_angle_debug(image_bgr, angle, origin, target, contours):
    """
    绘制角度调试可视化图像
    
    在图像上标注：
    - 前8个轮廓（紫色）
    - 原点和目标点（绿色/橙色圆点）
    - 连接线（红色箭头）
    - 角度数值文本
    
    Args:
        image_bgr (numpy.ndarray): BGR格式源图像
        angle (float): 计算的角度值
        origin (tuple[float, float]): 原点坐标
        target (tuple[float, float]): 目标点坐标
        contours (list): 轮廓列表
        
    Returns:
        numpy.ndarray: 标注后的BGR图像副本
    """
    debug = image_bgr.copy()
    cv2.drawContours(debug, contours[:8], -1, (255, 0, 255), 2)
    p1 = (round(origin[0]), round(origin[1]))
    p2 = (round(target[0]), round(target[1]))
    cv2.circle(debug, p1, 5, (0, 255, 0), -1)
    cv2.circle(debug, p2, 5, (0, 200, 255), -1)
    cv2.arrowedLine(debug, p1, p2, (0, 0, 255), 3, tipLength=0.25)
    cv2.putText(debug, f"angle: {angle:.1f} deg", (10, 28),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2, cv2.LINE_AA)
    return debug


class AnalysisResult:
    """
    图像分析结果封装类
    
    存储角度识别的所有关键信息，包括可视化图像和中间数据。
    
    Attributes:
        angle (float): 计算的角度值
        origin (tuple[float, float]): 原点坐标
        target (tuple[float, float]): 目标点坐标
        debug (numpy.ndarray): 调试可视化图像
        mask (numpy.ndarray): 颜色掩码图像
        offset (tuple[int, int]): 裁剪偏移量
        color_hex (str): 匹配的颜色十六进制字符串
    """
    def __init__(self, angle, origin, target, debug, mask, offset, color_hex):
        self.angle = angle
        self.origin = origin
        self.target = target
        self.debug = debug
        self.mask = mask
        self.offset = offset
        self.color_hex = color_hex


def _analyze_image_legacy(image_bgr, colors, tolerance, min_area, clean_mask, region, hsv_mode=False):
    """旧算法：多颜色轮廓 + 北向 atan2。"""
    cropped, offset = crop_region(image_bgr, region)
    errors = []
    for color_hex, color_rgb in colors:
        modes = [hsv_mode]
        if not hsv_mode:
            modes.append(True)
        last_error = None
        for current_hsv_mode in modes:
            try:
                angle, origin, target, mask, contours = detect_angle_with_fallback(
                    cropped, color_rgb, tolerance, min_area, clean_mask, current_hsv_mode)
                debug = draw_angle_debug(cropped, angle, origin, target, contours)
                return AnalysisResult(angle, origin, target, debug, mask, offset, color_hex)
            except RuntimeError as exc:
                last_error = exc
        errors.append(f"#{color_hex}: {last_error}")
    raise RuntimeError("没有匹配到配置颜色。" + " | ".join(errors))


def _analyze_image_text_raw(image_bgr, colors, tolerance, min_area, clean_mask, region, hsv_mode=False):
    """返回经过 MAP 校准但尚未做时序滤波的 TEXT 观测。"""
    del colors, tolerance, min_area, clean_mask, hsv_mode
    cropped, offset = crop_region(image_bgr, region)
    recognizer = _get_text_recognizer()
    raw = recognizer.识别角度(图像数据=cropped, 显示=False)
    if raw is None:
        raise RuntimeError("无法识别当前朝向（text箭头算法）")
    detail = recognizer.最近详情 or {}
    origin = detail.get("origin") or (0.0, 0.0)
    target = detail.get("target") or origin
    mask = detail.get("mask")
    debug_src = detail.get("debug")
    if debug_src is not None:
        debug = draw_angle_debug(debug_src, float(raw), origin, target, [])
    else:
        debug = draw_angle_debug(cropped, float(raw), origin, target, [])
    if mask is None:
        mask = np.zeros(cropped.shape[:2], dtype=np.uint8)
    result = AnalysisResult(float(raw), origin, target, debug, mask, offset, "9AE77E")
    result.confidence = float(detail.get("confidence", 0.5))
    result.calibration_source = str(detail.get("calibration_source", "unknown"))
    result.observation_source = "text"
    return result


def _analyze_image_text(image_bgr, colors, tolerance, min_area, clean_mask, region, hsv_mode=False):
    """MAP 校准后的 TEXT 观测，仅做一层自适应小抖动滤波。"""
    result = _analyze_image_text_raw(
        image_bgr, colors, tolerance, min_area, clean_mask, region, hsv_mode
    )
    result.angle = _get_text_stabilizer().update(float(result.angle))
    return result


def _analyze_image_fusion(image_bgr, colors, tolerance, min_area, clean_mask, region, hsv_mode=False):
    """同一大图内并行取三色精准与 Legacy 观测并选择可信来源。"""
    cropped, offset = crop_region(image_bgr, region)
    precise_result = None
    legacy_result = None
    precise_color = None
    precise_quality = None
    precise_error = None
    legacy_error = None
    try:
        recognizer = _get_fusion_precise_recognizer()
        precise = recognizer.识别(cropped)
        if precise is None:
            precise_error = getattr(recognizer, "最近错误", None) or "未识别到三色精准角度"
        else:
            details = precise.details if isinstance(precise.details, dict) else {}
            origin = details.get("origin") or (0.0, 0.0)
            target = details.get("target") or origin
            debug = details.get("debug")
            if debug is None:
                debug = cropped.copy()
            mask = details.get("mask")
            if mask is None:
                mask = np.zeros(cropped.shape[:2], dtype=np.uint8)
            precise_color = str(precise.color)
            precise_quality = float(precise.confidence)
            precise_result = AnalysisResult(
                float(precise.angle),
                origin,
                target,
                debug,
                mask,
                details.get("offset") or (0, 0),
                str(details.get("color_hex") or "PRECISE"),
            )
            precise_result.confidence = precise_quality
    except Exception as exc:
        precise_error = str(exc)
    try:
        legacy_result = _analyze_image_legacy(
            cropped,
            colors,
            tolerance,
            min_area,
            clean_mask,
            ANGLE_FUSION_LEGACY_REGION,
            hsv_mode,
        )
    except Exception as exc:
        legacy_error = exc

    selector = _get_fusion_selector()
    precise_observation = None
    if precise_result is not None:
        precise_angle = float(precise_result.angle)
        precise_confidence = float(getattr(precise_result, "confidence", 0.8))
        if not math.isfinite(precise_angle):
            precise_error = f"精准三色角度非有限：{precise_angle}"
        elif not math.isfinite(precise_confidence):
            precise_error = f"精准三色质量非有限：{precise_confidence}"
        elif precise_confidence < selector.min_confidence:
            precise_error = (
                f"精准三色质量{precise_confidence:g}低于融合门槛"
                f"{selector.min_confidence:g}"
            )
        precise_observation = 角度观测(
            precise_angle,
            precise_confidence,
            "text",
        )
    legacy_observation = None
    if legacy_result is not None:
        legacy_observation = 角度观测(legacy_result.angle, 0.75, "legacy")
    try:
        fused = selector.update(precise_observation, legacy_observation)
    except 角度融合失败 as exc:
        details = f"精准三色={precise_error}; Legacy={legacy_error}"
        raise RuntimeError(f"无法识别当前朝向（融合算法）：{details}") from exc

    fusion_difference = None
    if precise_result is not None and legacy_result is not None:
        fusion_difference = abs(
            (float(legacy_result.angle) - float(precise_result.angle) + 180.0)
            % 360.0
            - 180.0
        )

    if fused.source == "text":
        result = precise_result
    elif fused.source == "legacy":
        result = legacy_result
    else:
        result = AnalysisResult(
            fused.angle,
            (0.0, 0.0),
            (0.0, 0.0),
            cropped.copy(),
            np.zeros(cropped.shape[:2], dtype=np.uint8),
            offset,
            "HOLD",
        )
    if fused.source != "hold":
        local_x, local_y = getattr(result, "offset", (0, 0))
        result.offset = (offset[0] + local_x, offset[1] + local_y)
    result.angle = float(fused.angle)
    result.observation_source = "precise" if fused.source == "text" else fused.source
    result.confidence = float(fused.confidence)
    result.fusion_reason = fused.reason.replace("TEXT", "精准三色")
    result.fusion_difference = fusion_difference
    result.precise_color = precise_color
    result.precise_quality = precise_quality
    result.precise_error = precise_error
    result.text_error = precise_error
    result.legacy_error = None if legacy_error is None else str(legacy_error)
    return result


def analyze_image(image_bgr, colors, tolerance, min_area, clean_mask, region, hsv_mode=False):
    """
    角度分析入口（按全局模式分发）。
    - legacy: 旧颜色轮廓
    - text: text 箭头 + 加稳
    截图仍走 grab_bbox_bgr / 截图模块，不在此改截图。
    """
    mode = get_angle_mode()
    if mode == ANGLE_MODE_TEXT:
        return _analyze_image_text(
            image_bgr, colors, tolerance, min_area, clean_mask, region, hsv_mode
        )
    if mode == ANGLE_MODE_FUSION:
        return _analyze_image_fusion(
            image_bgr, colors, tolerance, min_area, clean_mask, region, hsv_mode
        )
    return _analyze_image_legacy(
        image_bgr, colors, tolerance, min_area, clean_mask, region, hsv_mode
    )


def analyze_fullscreen_angle(
    image_bgr,
    colors,
    tolerance,
    min_area,
    clean_mask,
    bbox,
    hsv_mode=False,
):
    """
    从全屏图中裁出角度区域并执行角度分析。
    """
    cropped, _ = crop_region(image_bgr, bbox)
    return analyze_image(cropped, colors, tolerance, min_area, clean_mask, None, hsv_mode)

# ===========================================================================
# 截屏 & 诊断工具
# ===========================================================================

def _load_capture():
    import importlib.util
    import unicodedata

    base = Path(__file__).resolve().parent
    target = unicodedata.normalize("NFC", "截图模块")
    for py in base.glob("*.py"):
        if unicodedata.normalize("NFC", py.stem) == target:
            name = "capture_mod_004"
            if name in sys.modules:
                return sys.modules[name]
            spec = importlib.util.spec_from_file_location(name, py)
            mod = importlib.util.module_from_spec(spec)
            sys.modules[name] = mod
            spec.loader.exec_module(mod)
            return mod
    try:
        import 截图模块 as mod  # type: ignore
        return mod
    except ModuleNotFoundError:
        return None


def grab_bbox_bgr(bbox: tuple[int, int, int, int]) -> tuple[np.ndarray, str]:
    """
    按指定边界框截取屏幕区域。

    004：优先稳定 GDI（BitBlt），再 mss / PIL。
    """
    mod = _load_capture()
    if mod is not None:
        return mod.grab_bbox_bgr(bbox)
    x1, y1, x2, y2 = bbox
    w, h = x2 - x1, y2 - y1
    if w <= 0 or h <= 0:
        raise ValueError(f"bbox 区域无效: {bbox}")
    try:
        import mss
        with mss.mss() as sct:
            shot = sct.grab({"left": x1, "top": y1, "width": w, "height": h})
            raw = np.frombuffer(shot.raw, dtype=np.uint8).reshape(shot.height, shot.width, 4)
            return raw[:, :, :3].copy(), "mss"
    except (ImportError, Exception):
        pass
    return pil_to_bgr(ImageGrab.grab(bbox=bbox)), "PIL"


def grab_regions_bgr(
    *regions: tuple[int, int, int, int],
) -> dict[tuple[int, int, int, int], np.ndarray]:
    """一次截并集再裁多区域。"""
    mod = _load_capture()
    if mod is not None and hasattr(mod, "grab_union_crop"):
        return mod.grab_union_crop(regions)
    out = {}
    for r in regions:
        img, _ = grab_bbox_bgr(r)
        out[tuple(int(v) for v in r)] = img
    return out


def diagnose_capture(image_bgr, colors, tolerance, hsv_mode):
    """
    诊断截图质量和颜色匹配情况
    
    统计图像基本信息和各颜色的像素命中数。
    
    Args:
        image_bgr (numpy.ndarray): BGR格式截图
        colors (list): 颜色列表
        tolerance (int): 颜色容差
        hsv_mode (bool): 是否使用HSV模式
        
    Returns:
        dict: 诊断信息字典，包含：
            - shape: 图像尺寸
            - tl_pixel: 左上角像素值
            - mean_bgr: 平均BGR值
            - color_hits: 各颜色的像素命中数
    """
    h, w = image_bgr.shape[:2]
    tl = image_bgr[0, 0].tolist() if h and w else []
    mean = image_bgr.reshape(-1, 3).mean(axis=0).tolist() if h and w else [0, 0, 0]
    hits = {}
    for color_hex, color_rgb in colors:
        entry = {"bgr": int(cv2.countNonZero(
            color_threshold(image_bgr, color_rgb, tolerance, False, hsv_mode=False)))}
        if hsv_mode:
            entry["hsv"] = int(cv2.countNonZero(
                color_threshold(image_bgr, color_rgb, tolerance, False, hsv_mode=True)))
        hits[color_hex] = entry
    return {"shape": [h, w], "tl_pixel": tl,
            "mean_bgr": [round(m, 1) for m in mean], "color_hits": hits}


def format_diag(diag):
    """
    格式化诊断信息为可读字符串
    
    Args:
        diag (dict): diagnose_capture返回的诊断字典
        
    Returns:
        str: 格式化的诊断日志字符串
    """
    if not diag:
        return ""
    hits = diag.get("color_hits", {})
    parts = []
    for ch, e in hits.items():
        parts.append(f"{ch}:bgr={e.get('bgr', 0)}" +
                     (f"/hsv={e['hsv']}" if e.get("hsv") is not None else ""))
    return (f" [diag] backend={diag.get('backend', '?')} shape={diag.get('shape', [])} "
            f"mean_bgr={diag.get('mean_bgr', [])} hits=[{', '.join(parts)}]")

# ===========================================================================
# CLI 命令行模式
# ===========================================================================

def run_angle_cli(args: argparse.Namespace) -> None:
    """
    执行命令行角度识别模式
    
    处理单张图片（或演示图像），输出角度结果和调试图像。
    
    Args:
        args (argparse.Namespace): 命令行参数对象，包含：
            - color: 颜色列表
            - tolerance: 容差
            - min_area: 最小面积
            - clean: 是否清理mask
            - hsv: 是否使用HSV
            - region: 识别区域
            - image: 输入图片路径（可选）
            - out: 输出文件名
    """
    colors = []
    for color in args.color or ANGLE_DEFAULT_COLORS:
        h = color.strip().lstrip("#").upper()
        colors.append((h, parse_hex_color(h)))
    region = parse_region(args.region)
    if args.image:
        image_path = Path(args.image)
        if not image_path.is_absolute():
            image_path = app_dir() / image_path
        image_bgr = imread_unicode(image_path)
    else:
        image_bgr = create_demo_image(colors[0][1])
        imwrite_unicode(app_dir() / "angle_demo_input.png", image_bgr)
        print("No --image provided, generated angle_demo_input.png")
    result = analyze_image(image_bgr, colors, args.tolerance, args.min_area, args.clean, region, args.hsv)
    out_path = app_dir() / args.out
    mask_path = out_path.with_name(out_path.stem + "_mask.png")
    imwrite_unicode(out_path, result.debug)
    imwrite_unicode(mask_path, result.mask)
    print(f"angle: {result.angle:.2f} degrees")
    print(f"matched color: #{result.color_hex}")
    print(f"debug image: {out_path}")
    print(f"mask image: {mask_path}")

# ===========================================================================
# 实时截图 GUI 应用
# ===========================================================================

class RealtimeAngleApp:
    """
    实时角度识别图形界面应用
    
    提供完整的GUI交互功能：
    - 参数配置（截图区域、颜色、容差等）
    - 实时截图和角度识别
    - 可视化展示（角度预览、截图预览）
    - 日志记录
    - 多线程异步处理
    
    Attributes:
        root (tk.Tk): Tkinter根窗口
        stop_event (threading.Event): 线程停止信号
        worker (threading.Thread): 后台工作线程
        queue (queue.Queue): 线程间通信队列
        angle_var (tk.StringVar): 角度显示变量
        status_var (tk.StringVar): 状态显示变量
        latest_angle (float or None): 最新识别角度
        latest_color (str or None): 最新匹配颜色
    """
    def __init__(self, root: tk.Tk) -> None:
        """
        初始化GUI应用
        
        Args:
            root (tk.Tk): Tkinter根窗口对象
        """
        self.root = root
        self.root.title("实时截图角度识别")
        self.root.geometry("960x720+220+20")
        self.root.minsize(820, 620)
        self.stop_event = threading.Event()
        self.worker: threading.Thread | None = None
        self.queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self.angle_photo = None
        self.capture_photo = None
        self.latest_angle = None
        self.latest_color = None
        self.latest_origin = None
        self.latest_target = None

        self.angle_bbox_var = tk.StringVar(value=ANGLE_DEFAULT_BBOX)
        self.interval_var = tk.StringVar(value=str(DEFAULT_INTERVAL))
        self.angle_colors_var = tk.StringVar(value=",".join(ANGLE_DEFAULT_COLORS))
        self.angle_tolerance_var = tk.StringVar(value=ANGLE_DEFAULT_TOLERANCE)
        self.angle_min_area_var = tk.StringVar(value=ANGLE_DEFAULT_MIN_AREA)
        self.angle_region_var = tk.StringVar(value="")
        self.angle_clean_var = tk.BooleanVar(value=False)
        self.angle_hsv_var = tk.BooleanVar(value=False)
        self.angle_var = tk.StringVar(value="Angle: --")
        self.status_var = tk.StringVar(value="未开始")

        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.after(100, self.drain_queue)

    def _build_ui(self) -> None:
        """
        构建用户界面布局
        
        界面结构：
        - 左侧：参数配置面板
        - 右上：角度显示和状态栏
        - 右中：角度预览和截图预览
        - 右下：日志输出区
        """
        outer = tk.Frame(self.root, padx=12, pady=12)
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(1, weight=1)
        outer.rowconfigure(1, weight=1)

        controls = tk.LabelFrame(outer, text="参数", padx=10, pady=10)
        controls.grid(row=0, column=0, rowspan=2, sticky="ns", padx=(0, 12))

        fields = [
            ("角度截图 bbox", self.angle_bbox_var),
            ("循环间隔 秒", self.interval_var),
            ("角度颜色 RGB", self.angle_colors_var),
            ("角度容差", self.angle_tolerance_var),
            ("角度最小面积", self.angle_min_area_var),
            ("角度识别区域 可空", self.angle_region_var),
        ]
        for row, (label, var) in enumerate(fields):
            tk.Label(controls, text=label).grid(row=row, column=0, sticky="w",
                                                pady=(0 if row == 0 else 7, 0))
            tk.Entry(controls, textvariable=var, width=26).grid(
                row=row, column=1, sticky="ew", padx=(8, 0),
                pady=(0 if row == 0 else 7, 0))

        tk.Checkbutton(controls, text="清理角度 mask", variable=self.angle_clean_var).grid(
            row=len(fields), column=0, columnspan=2, sticky="w", pady=(8, 0))
        tk.Checkbutton(controls, text="HSV 颜色分割（精度优先）", variable=self.angle_hsv_var).grid(
            row=len(fields) + 1, column=0, columnspan=2, sticky="w", pady=(4, 0))

        buttons = tk.Frame(controls)
        buttons.grid(row=len(fields) + 2, column=0, columnspan=2, pady=(14, 0), sticky="ew")
        self.start_button = tk.Button(buttons, text="开始", width=10, command=self.start)
        self.start_button.pack(side="left", padx=(0, 8))
        self.stop_button = tk.Button(buttons, text="停止", width=10, command=self.stop, state="disabled")
        self.stop_button.pack(side="left", padx=(0, 8))
        tk.Button(buttons, text="单次截图识别", width=12, command=self.run_once).pack(side="left")

        summary = tk.Frame(outer)
        summary.grid(row=0, column=1, sticky="ew")
        tk.Label(summary, textvariable=self.angle_var, font=("Segoe UI", 24, "bold"),
                 fg="#0969da").grid(row=0, column=0, sticky="w")
        tk.Label(summary, textvariable=self.status_var, fg="#333333",
                 wraplength=760, justify="left").grid(row=1, column=0, sticky="w", pady=(4, 8))

        content = tk.Frame(outer)
        content.grid(row=1, column=1, sticky="nsew")
        content.columnconfigure(0, weight=1)
        content.columnconfigure(1, weight=1)
        content.rowconfigure(0, weight=1)
        content.rowconfigure(2, weight=1)

        self.angle_label = tk.Label(content, text="角度识别预览", bg="#eeeeee", relief="sunken")
        self.angle_label.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        self.capture_label = tk.Label(content, text="截图预览", bg="#222222", fg="#ffffff", relief="sunken")
        self.capture_label.grid(row=0, column=1, sticky="nsew", padx=(6, 0))

        self.log_box = scrolledtext.ScrolledText(content, height=8)
        self.log_box.grid(row=2, column=0, columnspan=2, sticky="nsew", pady=(8, 0))

    def parse_settings(self) -> dict:
        """
        解析并验证当前界面设置
        
        Returns:
            dict: 完整的配置字典，包含：
                - bbox: 截图区域
                - colors: 颜色列表
                - tolerance: 容差
                - min_area: 最小面积
                - region: 识别区域
                - clean: 是否清理mask
                - hsv_mode: 是否使用HSV
                - interval: 循环间隔
                
        Raises:
            ValueError: 参数验证失败时抛出
        """
        interval = float(self.interval_var.get().strip())
        if interval <= 0:
            raise ValueError("循环间隔必须大于 0")
        return {
            "bbox": parse_bbox(self.angle_bbox_var.get().strip()),
            "colors": parse_color_list(self.angle_colors_var.get().strip()),
            "tolerance": int(self.angle_tolerance_var.get().strip()),
            "min_area": float(self.angle_min_area_var.get().strip()),
            "region": parse_region(self.angle_region_var.get().strip() or None),
            "clean": self.angle_clean_var.get(),
            "hsv_mode": self.angle_hsv_var.get(),
            "interval": interval,
        }

    def start(self) -> None:
        """
        启动实时识别循环
        
        验证参数后创建后台线程开始周期性截图识别。
        """
        if self.worker and self.worker.is_alive():
            return
        try:
            settings = self.parse_settings()
        except Exception as e:
            messagebox.showerror("输入错误", str(e))
            return
        self.stop_event.clear()
        self.start_button.config(state="disabled")
        self.stop_button.config(state="normal")
        self.status_var.set("识别中")
        self.append_log(f"[{time.strftime('%H:%M:%S')}] 开始：角度 bbox={settings['bbox']}")
        self.worker = threading.Thread(target=self.run_worker, args=(settings,), daemon=True)
        self.worker.start()

    def stop(self) -> None:
        """
        停止实时识别循环
        
        设置停止信号，等待工作线程自然退出。
        """
        self.stop_event.set()

    def run_once(self) -> None:
        """
        执行单次截图识别
        
        不进行循环，立即识别并更新结果。
        """
        if self.worker and self.worker.is_alive():
            messagebox.showinfo("正在识别", "请先停止循环识别再执行单次截图。")
            return
        try:
            settings = self.parse_settings()
        except Exception as e:
            messagebox.showerror("输入错误", str(e))
            return
        self.update_angle(self.angle_step(settings))
        self.append_log(f"[{time.strftime('%H:%M:%S')}] 单次截图识别完成")

    def run_worker(self, settings: dict) -> None:
        """
        后台工作线程主循环
        
        周期性执行截图识别并通过队列传递结果到UI线程。
        
        Args:
            settings (dict): 识别配置参数
        """
        while not self.stop_event.is_set():
            self.queue.put(("angle", self.angle_step(settings)))
            self.stop_event.wait(settings["interval"])
        self.queue.put(("stopped", ""))

    def angle_step(self, settings: dict) -> dict:
        """
        执行单步角度识别
        
        包含截图、保存、诊断、分析完整流程。
        
        Args:
            settings (dict): 识别配置参数
            
        Returns:
            dict: 识别结果字典，包含：
                - ok: 是否成功
                - angle: 角度值（成功时）
                - color: 匹配颜色
                - origin/target: 原点/目标坐标
                - debug/capture_bgr: 调试/截图图像
                - error/traceback: 错误信息（失败时）
        """
        try:
            image_bgr, backend = grab_bbox_bgr(settings["bbox"])
            Image.fromarray(cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)).save(
                app_dir() / ANGLE_DEFAULT_IMAGE)
            diag = diagnose_capture(image_bgr, settings["colors"], settings["tolerance"],
                                    settings.get("hsv_mode", False))
            diag["backend"] = backend
            result = analyze_image(image_bgr, settings["colors"], settings["tolerance"],
                                   settings["min_area"], settings["clean"],
                                   settings["region"], settings.get("hsv_mode", False))
            return {"ok": True, "angle": result.angle, "color": result.color_hex,
                    "origin": result.origin, "target": result.target,
                    "offset": result.offset, "debug": result.debug,
                    "capture_bgr": image_bgr, "backend": backend, "diag": diag}
        except Exception as e:
            import traceback
            return {"ok": False, "error": str(e), "traceback": traceback.format_exc(limit=4)}

    def drain_queue(self) -> None:
        """
        处理线程间通信队列
        
        定期从队列取出后台线程的结果并更新UI。
        """
        while True:
            try:
                kind, value = self.queue.get_nowait()
            except queue.Empty:
                break
            if kind == "stopped":
                self.start_button.config(state="normal")
                self.stop_button.config(state="disabled")
                self.status_var.set("已停止")
                self.append_log(f"[{time.strftime('%H:%M:%S')}] 已停止")
            elif kind == "angle":
                self.update_angle(value)
            else:
                self.append_log(str(value))
        self.root.after(100, self.drain_queue)

    def update_angle(self, payload: dict) -> None:
        """
        根据识别结果更新UI显示
        
        成功时更新角度、预览图和状态；失败时显示错误信息。
        
        Args:
            payload (dict): angle_step返回的结果字典
        """
        if payload.get("ok"):
            ang = float(payload["angle"])
            self.latest_angle = ang
            self.latest_color = payload.get("color")
            self.latest_origin = payload.get("origin")
            self.latest_target = payload.get("target")
            self.angle_var.set(f"Angle: {ang:.2f} deg")
            self.angle_photo = resize_bgr_for_tk(payload["debug"], (420, 260))
            self.angle_label.config(image=self.angle_photo, text="")
            self.capture_photo = self._capture_photo(payload.get("capture_bgr"))
            if self.capture_photo is not None:
                self.capture_label.config(image=self.capture_photo, text="")
            self.status_var.set(
                f"角度={ang:.2f} color=#{payload.get('color')} "
                f"origin={payload.get('origin')} target={payload.get('target')}")
            self.append_log(f"[{time.strftime('%H:%M:%S')}] 角度={ang:.2f} color=#{payload.get('color')}")
            self.append_log(format_diag(payload.get("diag")))
        else:
            self.latest_angle = None
            self.angle_var.set("Angle: --")
            error = payload.get("error", "未知错误")
            self.status_var.set(f"识别失败：{error}")
            self.append_log(f"[{time.strftime('%H:%M:%S')}] 识别失败：{error}")
            if payload.get("traceback"):
                self.append_log(payload["traceback"])

    def _capture_photo(self, capture_bgr):
        """
        生成截图预览的PhotoImage对象
        
        Args:
            capture_bgr (numpy.ndarray or None): BGR格式截图
            
        Returns:
            ImageTk.PhotoImage or None: Tkinter图片对象
        """
        if capture_bgr is None:
            return None
        return resize_bgr_for_tk(capture_bgr, (420, 260))

    def append_log(self, line: str) -> None:
        """
        追加日志行到滚动文本框
        
        Args:
            line (str): 日志文本行
        """
        self.log_box.insert("end", line + "\n")
        self.log_box.see("end")

    def close(self) -> None:
        """
        关闭应用时的清理操作
        
        停止工作线程并销毁窗口。
        """
        self.stop_event.set()
        self.root.destroy()

# ===========================================================================
# 程序入口
# ===========================================================================

def create_parser() -> argparse.ArgumentParser:
    """
    创建命令行参数解析器
    
    定义CLI和GUI共用的参数选项。
    
    Returns:
        argparse.ArgumentParser: 配置好的参数解析器对象
    """
    p = argparse.ArgumentParser(description="角度识别工具（从小地图标记计算朝向角度）")
    p.add_argument("--cli", action="store_true", help="使用 CLI 命令行模式（默认启动 GUI）")
    # 通用参数
    p.add_argument("--color", action="append", help="RGB hex 颜色，可多次指定")
    p.add_argument("--tolerance", type=int, default=45, help="颜色容差")
    p.add_argument("--min-area", type=float, default=0.0, help="最小轮廓面积")
    p.add_argument("--clean", action="store_true", help="清理颜色 mask 噪点")
    p.add_argument("--hsv", action="store_true", help="启用 HSV 颜色分割（精度优先）")
    p.add_argument("--region", help="识别区域 x1,y1,x2,y2，可空")
    # CLI 专用
    p.add_argument("--image", help="输入图片路径（CLI 模式）")
    p.add_argument("--out", default="angle_debug.png", help="调试图输出文件名（CLI 模式）")
    # GUI 专用
    p.add_argument("--bbox", default=ANGLE_DEFAULT_BBOX, help="屏幕截图区域 x1,y1,x2,y2（GUI 模式）")
    p.add_argument("--interval", type=float, default=DEFAULT_INTERVAL, help="循环间隔秒（GUI 模式）")
    return p


def main() -> None:
    """
    程序主入口函数
    
    根据参数决定启动CLI模式还是GUI模式。
    """
    args = create_parser().parse_args()
    if args.cli:
        run_angle_cli(args)
        return
    root = tk.Tk()
    app = RealtimeAngleApp(root)
    if args.bbox:
        app.angle_bbox_var.set(args.bbox)
    if args.interval:
        app.interval_var.set(str(args.interval))
    if args.color:
        app.angle_colors_var.set(",".join(c.strip().lstrip("#").upper() for c in args.color))
    app.angle_tolerance_var.set(str(args.tolerance))
    app.angle_min_area_var.set(str(args.min_area))
    if args.clean:
        app.angle_clean_var.set(True)
    if args.hsv:
        app.angle_hsv_var.set(True)
    if args.region:
        app.angle_region_var.set(args.region)
    root.mainloop()


if __name__ == "__main__":
    main()
