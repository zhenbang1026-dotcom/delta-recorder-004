from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path


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
