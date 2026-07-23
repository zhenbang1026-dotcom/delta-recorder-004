# -*- coding: utf-8 -*-
"""text 项目箭头角度识别（004 适配版）。

- 算法：HSV 绿箭头 + 连通域 + atan2 + 零号大坝 +90°
- 校准：校准截图/lv.txt
- 截图：统一走 截图模块（GDI→mss→pil），不使用 dxcam
"""
from __future__ import annotations

import math
import os
import sys
import importlib.util
import unicodedata
from bisect import bisect_right
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np

# 与 text 校准一致：left, top, right, bottom
DEFAULT_RADAR_LTRB = (34, 78, 227, 271)


def _最短角差(起点: float, 终点: float) -> float:
    return (float(终点) - float(起点) + 180.0) % 360.0 - 180.0


def _圆形均值(角度列表) -> float:
    x = sum(math.cos(math.radians(float(v))) for v in 角度列表)
    y = sum(math.sin(math.radians(float(v))) for v in 角度列表)
    if abs(x) < 1e-12 and abs(y) < 1e-12:
        return float(角度列表[0]) % 360.0
    return math.degrees(math.atan2(y, x)) % 360.0


def _构建圆形残差节点(映射数据):
    分组 = defaultdict(list)
    for 原始角, 游戏角 in 映射数据 or ():
        原始角 = float(原始角) % 360.0
        分组[原始角].append(_最短角差(原始角, float(游戏角)))
    return sorted(
        (原始角, _圆形均值(残差列表))
        for 原始角, 残差列表 in 分组.items()
    )


def _圆形残差插值详情(原始角度: float, 映射数据):
    """返回 ``(游戏角度, 置信度)``；没有 MAP 时返回 ``None``。"""
    原始角度 = float(原始角度) % 360.0
    节点 = _构建圆形残差节点(映射数据)
    if not 节点:
        return None
    if len(节点) == 1:
        return (原始角度 + 节点[0][1]) % 360.0, 0.25

    原始角列表 = [节点原始角 for 节点原始角, _ in 节点]
    右索引 = bisect_right(原始角列表, 原始角度)
    左索引 = (右索引 - 1) % len(节点)
    右索引 %= len(节点)
    左原始角, 左残差 = 节点[左索引]
    右原始角, 右残差 = 节点[右索引]
    if 左索引 >= 右索引:
        if 左原始角 > 原始角度:
            左原始角 -= 360.0
        else:
            右原始角 += 360.0
    区间 = 右原始角 - 左原始角
    比例 = (原始角度 - 左原始角) / 区间
    插值残差 = (左残差 + 比例 * _最短角差(左残差, 右残差)) % 360.0
    if 区间 <= 2.0:
        置信度 = 1.0
    elif 区间 <= 3.0:
        置信度 = 0.9
    elif 区间 <= 5.0:
        置信度 = 0.8
    elif 区间 <= 10.0:
        置信度 = 0.65
    else:
        置信度 = 0.5
    return (原始角度 + 插值残差) % 360.0, 置信度


def 圆形残差插值(原始角度: float, 映射数据):
    """把 MAP 的圆形残差分段插值为游戏角度。"""
    详情 = _圆形残差插值详情(原始角度, 映射数据)
    return None if 详情 is None else float(详情[0])


def _load_capture():
    base = Path(__file__).resolve().parent
    target = unicodedata.normalize("NFC", "截图模块")
    for py in base.glob("*.py"):
        if unicodedata.normalize("NFC", py.stem) == target:
            name = "text_angle_capture"
            if name in sys.modules:
                return sys.modules[name]
            spec = importlib.util.spec_from_file_location(name, py)
            mod = importlib.util.module_from_spec(spec)
            sys.modules[name] = mod
            assert spec.loader is not None
            spec.loader.exec_module(mod)
            return mod
    try:
        import 截图模块 as mod  # type: ignore
        return mod
    except ModuleNotFoundError:
        return None


class 角度识别器:
    """雷达角度识别器（text 算法）。"""

    def __init__(
        self,
        lv_txt路径: str,
        雷达范围=DEFAULT_RADAR_LTRB,  # left, top, right, bottom
        箭头绿色HSV=([48, 66, 87], [78, 166, 255]),
        当前地图="零号大坝",
        静默: bool = True,
    ):
        self.lv_txt路径 = lv_txt路径
        self.雷达范围 = tuple(int(v) for v in 雷达范围)
        self.箭头绿色HSV = 箭头绿色HSV
        self.当前地图 = 当前地图
        self.静默 = bool(静默)
        self.角度映射数据缓存 = None
        self.最近详情 = None

    def _log(self, msg: str) -> None:
        if not self.静默:
            print(msg)

    def _读取校准数据(self):
        if self.角度映射数据缓存 is not None:
            return self.角度映射数据缓存
        try:
            raw = None
            for enc in ("utf-8", "gbk", "utf-8-sig"):
                try:
                    with open(self.lv_txt路径, "r", encoding=enc) as f:
                        raw = f.readlines()
                    break
                except UnicodeDecodeError:
                    continue
            if raw is None:
                with open(self.lv_txt路径, "r", encoding="gbk", errors="ignore") as f:
                    raw = f.readlines()
            data = {}
            for line in raw:
                line = line.strip()
                if line.startswith("SRC_CROP:"):
                    parts = line.split(":")[1].split(",")
                    data["crop"] = tuple(map(int, parts))
                elif line.startswith("PRECISE_CENTER:"):
                    parts = line.split(":")[1].split(",")
                    data["center_x"] = float(parts[0])
                    data["center_y"] = float(parts[1])
                elif line.startswith("MAP:"):
                    try:
                        parts = line.split(":", 1)[1].split(",")
                        data.setdefault("map_list", []).append(
                            (float(parts[0]), int(parts[1]))
                        )
                    except (IndexError, ValueError):
                        self._log(f"[警告] 跳过无效 MAP 行: {line}")
            self.角度映射数据缓存 = data
            self._log(
                f"[校准] crop={data.get('crop')} center="
                f"({data.get('center_x')},{data.get('center_y')})"
            )
            return data
        except Exception as e:
            self._log(f"[错误] 读取校准失败: {e}")
            return None

    def 截图(self):
        """用 004 统一截图模块截雷达区。"""
        left, top, right, bottom = self.雷达范围
        # 兼容误传 left,top,w,h
        if right < 400 and bottom < 400 and right < left + 50:
            right = left + right
            bottom = top + bottom
        mod = _load_capture()
        if mod is None:
            return None
        return mod.grab_region(left, top, right, bottom)

    def 识别角度(self, 图像数据=None, 显示=False):
        """
        返回 [0,360) 游戏角度，失败 None。
        图像数据为雷达区 BGR；None 则自动截图。
        """
        self.最近详情 = None
        if 图像数据 is None:
            图像数据 = self.截图()
        if 图像数据 is None or getattr(图像数据, "size", 0) == 0:
            self._log("[错误] 截图失败")
            return None

        cache = self._读取校准数据()
        if cache is None:
            return None

        裁剪_x1, 裁剪_y1, 裁剪_x2, 裁剪_y2 = cache["crop"]
        精准中心_x = cache["center_x"]
        精准中心_y = cache["center_y"]

        裁剪图 = 图像数据[裁剪_y1:裁剪_y2, 裁剪_x1:裁剪_x2]
        if 裁剪图.size == 0:
            self._log("[错误] 裁剪为空")
            return None

        高, 宽 = 裁剪图.shape[:2]
        放大图 = cv2.resize(裁剪图, (宽 * 2, 高 * 2), interpolation=cv2.INTER_CUBIC)

        内核 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (1, 1))
        处理图 = cv2.morphologyEx(放大图, cv2.MORPH_OPEN, 内核, iterations=1)
        hsv = cv2.cvtColor(处理图, cv2.COLOR_BGR2HSV)
        lower = np.array(self.箭头绿色HSV[0], dtype=np.uint8)
        upper = np.array(self.箭头绿色HSV[1], dtype=np.uint8)
        掩码颜色 = cv2.inRange(hsv, lower, upper)
        掩码三通道 = cv2.cvtColor(掩码颜色, cv2.COLOR_GRAY2BGR)
        结果图 = cv2.bitwise_and(处理图, 掩码三通道)

        掩码_for_analysis = cv2.inRange(
            cv2.cvtColor(结果图, cv2.COLOR_BGR2HSV), lower, upper
        )
        标签数, _标签, 统计, 质心s = cv2.connectedComponentsWithStats(
            掩码_for_analysis, connectivity=8
        )
        if 标签数 < 3:
            self._log(f"[警告] 连通域不足: {标签数 - 1}")
            return None

        面积s = 统计[1:, cv2.CC_STAT_AREA]
        排序索引 = np.argsort(面积s)[::-1] + 1
        if len(排序索引) < 2:
            return None

        圆_label = int(排序索引[0])
        箭头_label = int(排序索引[1])
        箭头_x, 箭头_y = float(质心s[箭头_label][0]), float(质心s[箭头_label][1])
        圆心_x, 圆心_y = float(质心s[圆_label][0]), float(质心s[圆_label][1])

        dx = 箭头_x - 精准中心_x
        dy = 箭头_y - 精准中心_y
        原始实测角度 = math.degrees(math.atan2(dy, dx))
        if 原始实测角度 < 0:
            原始实测角度 += 360

        映射详情 = _圆形残差插值详情(
            原始实测角度,
            cache.get("map_list", ()),
        )
        if 映射详情 is not None:
            简单角度, 映射置信度 = 映射详情
            标定来源 = "map"
        elif self.当前地图 == "零号大坝":
            简单角度 = (原始实测角度 + 90) % 360
            映射置信度 = 0.25
            标定来源 = "fixed_offset_90"
        else:
            简单角度 = 原始实测角度
            映射置信度 = 0.25
            标定来源 = "raw"

        self.最近详情 = {
            "angle": float(简单角度),
            "raw": float(原始实测角度),
            "calibration_source": 标定来源,
            "confidence": float(映射置信度),
            "origin": (float(精准中心_x), float(精准中心_y)),
            "target": (箭头_x, 箭头_y),
            "disk": (圆心_x, 圆心_y),
            "mask": 掩码颜色,
            "debug": 放大图,
        }

        if not self.静默:
            print(f"[角度] 原始={原始实测角度:.2f} 最终={简单角度:.2f}")

        if 显示:
            标注 = 放大图.copy()
            cx, cy = int(精准中心_x), int(精准中心_y)
            ax, ay = int(箭头_x), int(箭头_y)
            cv2.circle(标注, (cx, cy), 2, (0, 0, 255), -1)
            cv2.circle(标注, (ax, ay), 2, (255, 0, 0), -1)
            cv2.line(标注, (cx, cy), (ax, ay), (0, 255, 0), 1)
            cv2.putText(
                标注, f"Angle: {简单角度:.1f}", (5, 18),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1,
            )
            cv2.imshow("text angle", 标注)
            cv2.waitKey(0)
            cv2.destroyAllWindows()

        return float(简单角度)


def 默认识别器(静默: bool = True) -> 角度识别器:
    base = Path(__file__).resolve().parent
    lv = base / "校准截图" / "lv.txt"
    if not lv.is_file():
        lv = base / "lv.txt"
    return 角度识别器(
        lv_txt路径=str(lv),
        雷达范围=DEFAULT_RADAR_LTRB,
        箭头绿色HSV=([48, 66, 87], [78, 166, 255]),
        当前地图="零号大坝",
        静默=静默,
    )


if __name__ == "__main__":
    r = 默认识别器(静默=False)
    print("雷达", r.雷达范围, "lv", r.lv_txt路径)
    print("单次", r.识别角度(显示=False))
