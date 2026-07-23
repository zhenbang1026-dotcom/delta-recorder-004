from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np

import 识别角度 as 角度模块


@dataclass(frozen=True)
class 颜色配置:
    名称: str
    hsv下界: tuple[int, int, int]
    hsv上界: tuple[int, int, int]
    校准相对路径: Path
    代表色: str
    mask期望值: int


class 标定无效(ValueError):
    pass


@dataclass(frozen=True)
class 精准角度结果:
    angle: float
    color: str
    confidence: float
    details: dict[str, object]


FUSION颜色配置 = (
    颜色配置(
        名称="绿色",
        hsv下界=(48, 66, 87),
        hsv上界=(78, 166, 255),
        校准相对路径=Path("校准数据/Fusion/绿色/lv.txt"),
        代表色="9AE77E",
        mask期望值=438,
    ),
    颜色配置(
        名称="蓝色",
        hsv下界=(100, 50, 50),
        hsv上界=(130, 255, 255),
        校准相对路径=Path("校准数据/Fusion/蓝色/lv.txt"),
        代表色="95BBE8",
        mask期望值=425,
    ),
    颜色配置(
        名称="黄色",
        hsv下界=(18, 80, 80),
        hsv上界=(40, 255, 255),
        校准相对路径=Path("校准数据/Fusion/黄色/lv.txt"),
        代表色="F0E791",
        mask期望值=380,
    ),
)


def _抛出标定无效(path: Path, 原因: str) -> None:
    raise 标定无效(f"{path}: {原因}")


def _读取标定文本(path: Path) -> str:
    for encoding in ("utf-8-sig", "utf-8", "gbk", "gb18030"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
        except OSError as exc:
            _抛出标定无效(path, f"无法读取文件：{exc}")
    _抛出标定无效(path, "无法使用 utf-8-sig、utf-8、gbk 或 gb18030 解码")


def 读取并验证标定(path: Path) -> dict[str, object]:
    path = Path(path)
    文本 = _读取标定文本(path)
    crop: tuple[int, int, int, int] | None = None
    crop行号: int | None = None
    center_x: float | None = None
    center_y: float | None = None
    center行号: int | None = None
    map_list: list[tuple[float, int]] = []
    map行号列表: list[int] = []

    for 行号, 原始行 in enumerate(文本.splitlines(), start=1):
        行 = 原始行.strip()
        if not 行 or 行.startswith("#"):
            continue
        if 行.startswith("SRC_CROP:"):
            if crop is not None:
                _抛出标定无效(path, f"第 {行号} 行重复 SRC_CROP")
            try:
                值 = tuple(int(部分.strip()) for 部分 in 行.split(":", 1)[1].split(","))
            except ValueError:
                _抛出标定无效(path, f"第 {行号} 行 SRC_CROP 必须是四个整数")
            if len(值) != 4:
                _抛出标定无效(path, f"第 {行号} 行 SRC_CROP 必须是四个整数")
            crop = 值
            crop行号 = 行号
        elif 行.startswith("PRECISE_CENTER:"):
            if center_x is not None or center_y is not None:
                _抛出标定无效(path, f"第 {行号} 行重复 PRECISE_CENTER")
            部分 = 行.split(":", 1)[1].split(",")
            if len(部分) != 2:
                _抛出标定无效(path, f"第 {行号} 行 PRECISE_CENTER 必须是两个数")
            try:
                center_x, center_y = (float(值.strip()) for 值 in 部分)
            except ValueError:
                _抛出标定无效(path, f"第 {行号} 行 PRECISE_CENTER 必须是两个数")
            if not math.isfinite(center_x) or not math.isfinite(center_y):
                _抛出标定无效(path, f"第 {行号} 行 PRECISE_CENTER 包含非有限数")
            center行号 = 行号
        elif 行.startswith("MAP:"):
            部分 = 行.split(":", 1)[1].split(",")
            if len(部分) != 2:
                _抛出标定无效(path, f"第 {行号} 行 MAP 必须是两个数")
            try:
                原始角 = float(部分[0].strip())
                游戏角数值 = float(部分[1].strip())
            except ValueError:
                _抛出标定无效(path, f"第 {行号} 行 MAP 必须是两个数")
            if not math.isfinite(原始角) or not math.isfinite(游戏角数值):
                _抛出标定无效(path, f"第 {行号} 行 MAP 包含非有限数")
            if not 游戏角数值.is_integer():
                _抛出标定无效(path, f"第 {行号} 行 MAP 游戏角必须是整数")
            map_list.append((原始角, int(游戏角数值)))
            map行号列表.append(行号)
        else:
            摘要 = 行 if len(行) <= 80 else 行[:77] + "..."
            _抛出标定无效(path, f"第 {行号} 行未知或损坏的记录：{摘要}")

    if crop is None:
        _抛出标定无效(path, "缺少 SRC_CROP")
    if center_x is None or center_y is None:
        _抛出标定无效(path, "缺少 PRECISE_CENTER")
    if not map_list:
        _抛出标定无效(path, "缺少 MAP")

    x1, y1, x2, y2 = crop
    if not (0 <= x1 < x2 <= 193 and 0 <= y1 < y2 <= 193):
        _抛出标定无效(
            path,
            f"第 {crop行号} 行 SRC_CROP 必须为正且不得越出 193x193 画布",
        )

    两倍宽 = 2 * (x2 - x1)
    两倍高 = 2 * (y2 - y1)
    if not (0 <= center_x < 两倍宽 and 0 <= center_y < 两倍高):
        _抛出标定无效(
            path,
            f"第 {center行号} 行 PRECISE_CENTER 不得越出 2×crop",
        )

    if len(map_list) < 300:
        _抛出标定无效(path, "MAP 数量少于 300")
    for 索引, (原始角, 游戏角) in enumerate(map_list):
        if not 0 <= 原始角 < 360:
            _抛出标定无效(
                path,
                f"第 {map行号列表[索引]} 行 MAP 原始角必须在 [0, 360)",
            )
        if not 0 <= 游戏角 <= 360:
            _抛出标定无效(
                path,
                f"第 {map行号列表[索引]} 行 MAP 游戏角必须在 [0, 360]",
            )
        if 游戏角 == 360:
            map_list[索引] = (原始角, 0)

    排序原始角 = sorted(原始角 for 原始角, _ in map_list)
    圆周间隙 = [
        后一个 - 前一个
        for 前一个, 后一个 in zip(排序原始角, 排序原始角[1:])
    ]
    圆周间隙.append(排序原始角[0] + 360 - 排序原始角[-1])
    最大间隙 = max(圆周间隙)
    if 最大间隙 > 10:
        _抛出标定无效(path, f"原始角最大圆周间隙 {最大间隙:.6f}° 超过 10°")

    return {
        "crop": crop,
        "center_x": center_x,
        "center_y": center_y,
        "map_list": map_list,
    }


def _限制到单位区间(数值: float) -> float:
    return max(0.0, min(1.0, 数值))


class 三色精准角度识别器:
    def __init__(self, 根目录: Path | None = None):
        self._根目录 = (
            Path(__file__).resolve().parent if 根目录 is None else Path(根目录).resolve()
        )
        self._可用配置: list[颜色配置] = []
        self._识别器: dict[str, 角度模块.角度识别器] = {}
        self._加载错误: list[str] = []
        self._当前颜色: str | None = None
        self._待切换颜色: str | None = None
        self._待切换计数 = 0
        self._最近错误: str | None = None

        for 配置 in FUSION颜色配置:
            path = (self._根目录 / 配置.校准相对路径).resolve()
            try:
                标定 = 读取并验证标定(path)
                识别器 = 角度模块.角度识别器(
                    lv_txt路径=str(path),
                    箭头绿色HSV=(list(配置.hsv下界), list(配置.hsv上界)),
                    静默=True,
                )
                识别器.角度映射数据缓存 = {
                    "crop": 标定["crop"],
                    "center_x": 标定["center_x"],
                    "center_y": 标定["center_y"],
                    "map_list": list(标定["map_list"]),
                }
            except Exception as exc:
                错误 = f"{配置.名称}标定不可用：{path}：{exc}"
                self._加载错误.append(错误)
                self._最近错误 = 错误
                continue
            self._可用配置.append(配置)
            self._识别器[配置.名称] = 识别器

    @property
    def 当前颜色(self) -> str | None:
        return self._当前颜色

    @property
    def 待切换颜色(self) -> str | None:
        return self._待切换颜色

    @property
    def 待切换计数(self) -> int:
        return self._待切换计数

    @property
    def 加载错误(self) -> tuple[str, ...]:
        return tuple(self._加载错误)

    @property
    def 最近错误(self) -> str | None:
        return self._最近错误

    def reset(self) -> None:
        self._当前颜色 = None
        self._清除待切换()
        self._最近错误 = None

    def _清除待切换(self) -> None:
        self._待切换颜色 = None
        self._待切换计数 = 0

    def _记录失败(self, 配置: 颜色配置, 原因: str) -> None:
        self._最近错误 = f"{配置.名称}识别失败：{原因}"

    def _识别单色(
        self,
        配置: 颜色配置,
        图像: np.ndarray,
    ) -> 精准角度结果 | None:
        识别器 = self._识别器[配置.名称]
        try:
            angle = 识别器.识别角度(图像数据=图像)
            详情 = 识别器.最近详情
            if angle is None or not isinstance(详情, dict):
                self._记录失败(配置, "未识别到有效的两个连通域")
                return None

            angle = float(angle)
            raw = float(详情["raw"])
            map_confidence = float(详情["confidence"])
            origin = tuple(float(值) for 值 in 详情["origin"])
            disk = tuple(float(值) for 值 in 详情["disk"])
            target = tuple(float(值) for 值 in 详情["target"])
            mask = 详情["mask"]
            debug = 详情["debug"]
            calibration_source = 详情["calibration_source"]
            if (
                len(origin) != 2
                or len(disk) != 2
                or len(target) != 2
                or not isinstance(mask, np.ndarray)
            ):
                raise ValueError("识别详情结构无效")
            数值 = (angle, raw, map_confidence, *origin, *disk, *target)
            if not all(math.isfinite(值) for 值 in 数值):
                raise ValueError("识别详情包含非有限数")
            if not 0.0 <= angle < 360.0:
                raise ValueError("angle不在[0, 360)内")
            if mask.ndim != 2:
                raise ValueError("mask必须是二维数组")
            if mask.dtype != np.uint8:
                raise ValueError("mask dtype必须是uint8")
            x1, y1, x2, y2 = 识别器.角度映射数据缓存["crop"]
            mask_shape = (2 * (y2 - y1), 2 * (x2 - x1))
            if mask.shape != mask_shape:
                raise ValueError(f"mask尺寸{mask.shape}必须为{mask_shape}")
            mask_pixels = int(np.count_nonzero(mask))
        except Exception as exc:
            self._记录失败(配置, str(exc))
            return None

        center_error = math.hypot(disk[0] - origin[0], disk[1] - origin[1])
        arrow_radius = math.hypot(target[0] - origin[0], target[1] - origin[1])
        if center_error > 5.0:
            self._记录失败(配置, f"圆盘中心偏差{center_error:.3f}px超过5px")
            return None
        if not 10.0 <= arrow_radius <= 22.0:
            self._记录失败(配置, f"箭头半径{arrow_radius:.3f}px不在[10, 22]内")
            return None
        if not 200 <= mask_pixels <= 800:
            self._记录失败(配置, f"mask像素{mask_pixels}不在[200, 800]内")
            return None

        center_score = _限制到单位区间(1.0 - center_error / 5.0)
        radius_score = _限制到单位区间(
            1.0 - abs(arrow_radius - 15.75) / 6.25
        )
        mask_score = _限制到单位区间(
            1.0 - abs(mask_pixels - 配置.mask期望值) / 300.0
        )
        quality = (
            0.35 * center_score
            + 0.30 * radius_score
            + 0.20 * mask_score
            + 0.15 * map_confidence
        )
        结果详情: dict[str, object] = {
            "center_error": center_error,
            "arrow_radius": arrow_radius,
            "mask_pixels": mask_pixels,
            "map_confidence": map_confidence,
            "quality": quality,
            "origin": origin,
            "disk": disk,
            "target": target,
            "mask": mask,
            "debug": debug,
            "calibration_source": calibration_source,
            "color_hex": 配置.代表色,
        }
        return 精准角度结果(
            angle=angle,
            color=配置.名称,
            confidence=quality,
            details=结果详情,
        )

    def _最佳候选(
        self,
        配置列表: list[颜色配置],
        图像: np.ndarray,
    ) -> 精准角度结果 | None:
        候选列表: list[精准角度结果] = []
        for 配置 in 配置列表:
            候选 = self._识别单色(配置, 图像)
            if 候选 is not None:
                候选列表.append(候选)
        if not 候选列表:
            return None
        最高质量 = max(候选.confidence for 候选 in 候选列表)
        return next(
            候选 for 候选 in 候选列表 if 最高质量 - 候选.confidence < 1e-9
        )

    def 识别(self, 图像) -> 精准角度结果 | None:
        if (
            not isinstance(图像, np.ndarray)
            or 图像.size == 0
            or 图像.ndim != 3
            or 图像.shape[2] != 3
        ):
            self._最近错误 = "图像无效：需要非空BGR三通道数组"
            self._清除待切换()
            return None
        if not self._可用配置:
            self._最近错误 = "无可用颜色标定：" + "；".join(self._加载错误)
            return None

        if self._当前颜色 is None:
            候选 = self._最佳候选(self._可用配置, 图像)
            if 候选 is None:
                self._清除待切换()
                self._最近错误 = "三色均未识别到有效候选"
                return None
            self._当前颜色 = 候选.color
            self._清除待切换()
            self._最近错误 = None
            return 候选

        当前配置 = next(
            配置 for 配置 in self._可用配置 if 配置.名称 == self._当前颜色
        )
        当前候选 = self._识别单色(当前配置, 图像)
        if 当前候选 is not None:
            self._清除待切换()
            self._最近错误 = None
            return 当前候选
        当前失败 = self._最近错误 or f"{当前配置.名称}识别失败"

        其它配置 = [配置 for 配置 in self._可用配置 if 配置 is not 当前配置]
        切换候选 = self._最佳候选(其它配置, 图像)
        if 切换候选 is None:
            self._清除待切换()
            self._最近错误 = 当前失败
            return None
        if self._待切换颜色 == 切换候选.color:
            self._待切换计数 += 1
        else:
            self._待切换颜色 = 切换候选.color
            self._待切换计数 = 1
        if self._待切换计数 < 2:
            self._最近错误 = (
                f"{当前失败}；等待{切换候选.color} {self._待切换计数}/2"
            )
            return None

        self._当前颜色 = 切换候选.color
        self._清除待切换()
        self._最近错误 = None
        return 切换候选
