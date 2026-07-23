from __future__ import annotations

import math
from bisect import bisect_right
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np
import pytest

from 三色精准角度 import (
    FUSION颜色配置,
    三色精准角度识别器,
    精准角度结果,
    读取并验证标定,
)


项目根目录 = Path(__file__).resolve().parents[1]


def _最短角差(起点: float, 终点: float) -> float:
    return (float(终点) - float(起点) + 180.0) % 360.0 - 180.0


def _圆形均值(角度列表: list[float]) -> float:
    x = sum(math.cos(math.radians(角度)) for 角度 in 角度列表)
    y = sum(math.sin(math.radians(角度)) for 角度 in 角度列表)
    return math.degrees(math.atan2(y, x)) % 360.0


def _独立MAP插值(
    原始角: float,
    映射: list[tuple[float, int]],
) -> float:
    分组: defaultdict[float, list[float]] = defaultdict(list)
    for 节点原始角, 游戏角 in 映射:
        节点原始角 %= 360.0
        分组[节点原始角].append(_最短角差(节点原始角, 游戏角))
    节点 = sorted((角, _圆形均值(残差)) for 角, 残差 in 分组.items())
    原始角 %= 360.0
    角列表 = [角 for 角, _ in 节点]
    右索引 = bisect_right(角列表, 原始角) % len(节点)
    左索引 = (右索引 - 1) % len(节点)
    左角, 左残差 = 节点[左索引]
    右角, 右残差 = 节点[右索引]
    if 左索引 >= 右索引:
        if 左角 > 原始角:
            左角 -= 360.0
        else:
            右角 += 360.0
    比例 = (原始角 - 左角) / (右角 - 左角)
    插值残差 = 左残差 + 比例 * _最短角差(左残差, 右残差)
    return (原始角 + 插值残差) % 360.0


def _十六进制转BGR(十六进制: str) -> tuple[int, int, int]:
    rgb = tuple(int(十六进制[i : i + 2], 16) for i in (0, 2, 4))
    return rgb[2], rgb[1], rgb[0]


def _中心原图坐标(配置, 根目录: Path) -> tuple[int, int, dict[str, object]]:
    标定 = 读取并验证标定(根目录 / 配置.校准相对路径)
    x1, y1, _x2, _y2 = 标定["crop"]
    x = round(x1 + float(标定["center_x"]) / 2.0)
    y = round(y1 + float(标定["center_y"]) / 2.0)
    return x, y, 标定


def _创建真实箭头图(
    配置,
    根目录: Path = 项目根目录,
    偏移: tuple[int, int] = (9, 0),
) -> tuple[np.ndarray, float]:
    中心_x, 中心_y, 标定 = _中心原图坐标(配置, 根目录)
    颜色 = _十六进制转BGR(配置.代表色)
    图像 = np.zeros((193, 193, 3), dtype=np.uint8)
    cv2.circle(图像, (中心_x, 中心_y), 5, 颜色, -1)
    目标 = (中心_x + 偏移[0], 中心_y + 偏移[1])
    cv2.circle(图像, 目标, 2, 颜色, -1)

    x1, y1, _x2, _y2 = 标定["crop"]
    dx = 2.0 * (目标[0] - x1) - float(标定["center_x"])
    dy = 2.0 * (目标[1] - y1) - float(标定["center_y"])
    原始角 = math.degrees(math.atan2(dy, dx)) % 360.0
    期望角 = _独立MAP插值(原始角, 标定["map_list"])
    return 图像, 期望角


def _写有效标定(根目录: Path, 配置) -> None:
    path = 根目录 / 配置.校准相对路径
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "SRC_CROP:0,0,193,193\n"
        "PRECISE_CENTER:193,193\n"
        + "".join(f"MAP:{角度},{角度}\n" for 角度 in range(360)),
        encoding="utf-8",
    )


def _候选(颜色: str, 质量: float, 角度: float = 10.0) -> 精准角度结果:
    return 精准角度结果(angle=角度, color=颜色, confidence=质量, details={})


def _设置受控底层详情(
    monkeypatch: pytest.MonkeyPatch,
    识别器: 三色精准角度识别器,
    配置,
    *,
    center_error: float = 0.0,
    arrow_radius: float = 15.75,
    mask_pixels: int = 400,
    mask: np.ndarray | None = None,
) -> None:
    单色识别器 = 识别器._识别器[配置.名称]
    x1, y1, x2, y2 = 单色识别器.角度映射数据缓存["crop"]
    mask_shape = (2 * (y2 - y1), 2 * (x2 - x1))
    if mask is None:
        mask = np.zeros(mask_shape, dtype=np.uint8)
        mask.flat[:mask_pixels] = 255
    origin = (
        float(单色识别器.角度映射数据缓存["center_x"]),
        float(单色识别器.角度映射数据缓存["center_y"]),
    )
    单色识别器.最近详情 = {
        "raw": 10.0,
        "confidence": 1.0,
        "origin": origin,
        "disk": (origin[0] + center_error, origin[1]),
        "target": (origin[0], origin[1] + arrow_radius),
        "mask": mask,
        "debug": np.zeros((*mask_shape, 3), dtype=np.uint8),
        "calibration_source": "map",
    }
    monkeypatch.setattr(单色识别器, "识别角度", lambda 图像数据: 10.0)


@pytest.mark.parametrize(
    ("名称", "偏移"),
    [("绿色", (9, 0)), ("蓝色", (0, 9)), ("黄色", (-7, -6))],
)
def test三色真实合成图使用各自标定返回正确角度(
    名称: str,
    偏移: tuple[int, int],
) -> None:
    配置 = next(配置 for 配置 in FUSION颜色配置 if 配置.名称 == 名称)
    图像, 期望角 = _创建真实箭头图(配置, 偏移=偏移)
    识别器 = 三色精准角度识别器(项目根目录)

    结果 = 识别器.识别(图像)

    assert 结果 is not None
    assert 结果.color == 名称
    assert abs(_最短角差(结果.angle, 期望角)) < 2.5
    assert 结果.confidence == pytest.approx(结果.details["quality"])


def test质量公式和详情字段精确匹配() -> None:
    配置 = FUSION颜色配置[0]
    图像, _期望角 = _创建真实箭头图(配置)
    结果 = 三色精准角度识别器(项目根目录).识别(图像)

    assert 结果 is not None
    assert set(结果.details) == {
        "center_error",
        "arrow_radius",
        "mask_pixels",
        "map_confidence",
        "quality",
        "origin",
        "disk",
        "target",
        "mask",
        "debug",
        "calibration_source",
        "color_hex",
    }
    center = max(0.0, min(1.0, 1.0 - 结果.details["center_error"] / 5.0))
    radius = max(
        0.0,
        min(1.0, 1.0 - abs(结果.details["arrow_radius"] - 15.75) / 6.25),
    )
    mask = max(
        0.0,
        min(1.0, 1.0 - abs(结果.details["mask_pixels"] - 配置.mask期望值) / 300.0),
    )
    期望质量 = (
        0.35 * center
        + 0.30 * radius
        + 0.20 * mask
        + 0.15 * 结果.details["map_confidence"]
    )
    assert 结果.details["quality"] == pytest.approx(期望质量)
    assert 结果.confidence == pytest.approx(期望质量)
    assert 结果.details["color_hex"] == 配置.代表色


def test真实单连通域图像返回None并记录原因() -> None:
    配置 = FUSION颜色配置[0]
    识别器 = 三色精准角度识别器(项目根目录)
    中心_x, 中心_y, _标定 = _中心原图坐标(配置, 项目根目录)
    图像 = np.zeros((193, 193, 3), dtype=np.uint8)
    cv2.circle(图像, (中心_x, 中心_y), 5, _十六进制转BGR(配置.代表色), -1)

    assert 识别器._识别单色(配置, 图像) is None
    assert "连通域" in str(识别器.最近错误)


@pytest.mark.parametrize(
    ("字段", "数值", "原因"),
    [
        ("center_error", 5.01, "圆盘中心偏差"),
        ("arrow_radius", 9.99, "箭头半径"),
        ("arrow_radius", 22.01, "箭头半径"),
        ("mask_pixels", 199, "mask像素"),
        ("mask_pixels", 801, "mask像素"),
    ],
)
def test受控详情只命中目标几何门禁(
    monkeypatch: pytest.MonkeyPatch,
    字段: str,
    数值: float,
    原因: str,
) -> None:
    配置 = FUSION颜色配置[0]
    识别器 = 三色精准角度识别器(项目根目录)
    _设置受控底层详情(monkeypatch, 识别器, 配置, **{字段: 数值})

    assert 识别器._识别单色(配置, np.zeros((1, 1, 3), dtype=np.uint8)) is None
    assert 原因 in str(识别器.最近错误)


@pytest.mark.parametrize(
    ("字段", "数值"),
    [
        ("center_error", 5.0),
        ("arrow_radius", 10.0),
        ("arrow_radius", 22.0),
        ("mask_pixels", 200),
        ("mask_pixels", 800),
    ],
)
def test几何门禁闭区间端点通过(
    monkeypatch: pytest.MonkeyPatch,
    字段: str,
    数值: float,
) -> None:
    配置 = FUSION颜色配置[0]
    识别器 = 三色精准角度识别器(项目根目录)
    _设置受控底层详情(monkeypatch, 识别器, 配置, **{字段: 数值})

    结果 = 识别器._识别单色(配置, np.zeros((1, 1, 3), dtype=np.uint8))

    assert 结果 is not None
    assert 结果.details[字段] == pytest.approx(数值)


@pytest.mark.parametrize(
    ("错误类型", "原因"),
    [("dtype", "uint8"), ("ndim", "二维"), ("shape", "尺寸")],
)
def test非法mask结构返回None并记录可读原因(
    monkeypatch: pytest.MonkeyPatch,
    错误类型: str,
    原因: str,
) -> None:
    配置 = FUSION颜色配置[0]
    识别器 = 三色精准角度识别器(项目根目录)
    单色识别器 = 识别器._识别器[配置.名称]
    x1, y1, x2, y2 = 单色识别器.角度映射数据缓存["crop"]
    正确shape = (2 * (y2 - y1), 2 * (x2 - x1))
    if 错误类型 == "dtype":
        class 布尔求值异常:
            def __bool__(self) -> bool:
                raise RuntimeError("object mask不应进入像素计数")

        mask = np.zeros(正确shape, dtype=object)
        mask.flat[0] = 布尔求值异常()
    elif 错误类型 == "ndim":
        mask = np.zeros((*正确shape, 1), dtype=np.uint8)
        mask.flat[:400] = 255
    else:
        mask = np.zeros((正确shape[0] - 1, 正确shape[1]), dtype=np.uint8)
        mask.flat[:400] = 255
    _设置受控底层详情(monkeypatch, 识别器, 配置, mask=mask)

    结果 = 识别器._识别单色(配置, np.zeros((1, 1, 3), dtype=np.uint8))

    assert 结果 is None
    assert 原因 in str(识别器.最近错误)


@pytest.mark.parametrize(
    "非法图像",
    [
        None,
        np.empty((0, 0, 3), dtype=np.uint8),
        np.zeros((193, 193), dtype=np.uint8),
        np.zeros((193, 193, 4), dtype=np.uint8),
        object(),
    ],
)
def test空或非法图像返回None且不抛异常(非法图像: object) -> None:
    识别器 = 三色精准角度识别器(项目根目录)

    assert 识别器.识别(非法图像) is None


def test底层详情缺少字段时记录原因并返回None(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    配置 = FUSION颜色配置[0]
    识别器 = 三色精准角度识别器(项目根目录)
    单色识别器 = 识别器._识别器[配置.名称]
    单色识别器.最近详情 = {
        "raw": 10.0,
        "confidence": 1.0,
        "origin": (20.0, 20.0),
        "disk": (20.0, 20.0),
        "target": (35.0, 20.0),
        "mask": np.ones((20, 15), dtype=np.uint8),
        "calibration_source": "map",
    }
    monkeypatch.setattr(单色识别器, "识别角度", lambda 图像数据: 10.0)

    结果 = 识别器._识别单色(
        配置,
        np.zeros((193, 193, 3), dtype=np.uint8),
    )

    assert 结果 is None
    assert "绿色" in str(识别器.最近错误)
    assert "debug" in str(识别器.最近错误)


def test未锁定扫描三色并按质量和固定顺序锁定(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    识别器 = 三色精准角度识别器(项目根目录)
    调用: list[str] = []
    输出 = {
        "绿色": _候选("绿色", 0.5),
        "蓝色": _候选("蓝色", 0.9),
        "黄色": _候选("黄色", 0.7),
    }

    def 假识别(配置, _图像):
        调用.append(配置.名称)
        return 输出[配置.名称]

    monkeypatch.setattr(识别器, "_识别单色", 假识别)

    assert 识别器.识别(np.zeros((1, 1, 3), dtype=np.uint8)).color == "蓝色"
    assert 调用 == ["绿色", "蓝色", "黄色"]
    assert 识别器.当前颜色 == "蓝色"

    识别器.reset()
    调用.clear()
    输出.update({名称: _候选(名称, 0.8) for 名称 in 输出})
    assert 识别器.识别(np.zeros((1, 1, 3), dtype=np.uint8)).color == "绿色"
    assert 调用 == ["绿色", "蓝色", "黄色"]
    assert 识别器.当前颜色 == "绿色"

    识别器.reset()
    调用.clear()
    输出.update(
        {
            "绿色": _候选("绿色", 0.0),
            "蓝色": _候选("蓝色", 1e-9),
            "黄色": _候选("黄色", 0.0),
        }
    )
    assert 识别器.识别(np.zeros((1, 1, 3), dtype=np.uint8)).color == "蓝色"
    assert 调用 == ["绿色", "蓝色", "黄色"]
    assert 识别器.当前颜色 == "蓝色"

    识别器.reset()
    调用.clear()
    输出.update(
        {
            "绿色": _候选("绿色", 0.5),
            "蓝色": _候选("蓝色", 0.5000000005),
            "黄色": _候选("黄色", 0.4),
        }
    )
    assert 识别器.识别(np.zeros((1, 1, 3), dtype=np.uint8)).color == "绿色"
    assert 调用 == ["绿色", "蓝色", "黄色"]
    assert 识别器.当前颜色 == "绿色"


def test近似同分链以全体最高质量为基准(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    识别器 = 三色精准角度识别器(项目根目录)
    输出 = {
        "绿色": _候选("绿色", 0.0),
        "蓝色": _候选("蓝色", 0.9e-9),
        "黄色": _候选("黄色", 1.8e-9),
    }
    monkeypatch.setattr(识别器, "_识别单色", lambda 配置, _图像: 输出[配置.名称])

    结果 = 识别器.识别(np.zeros((1, 1, 3), dtype=np.uint8))

    assert 结果 is 输出["蓝色"]
    assert 识别器.当前颜色 == "蓝色"


def test锁定有效时只调用当前色一次并清除pending(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    识别器 = 三色精准角度识别器(项目根目录)
    输出 = {"绿色": _候选("绿色", 0.8), "蓝色": None, "黄色": None}
    调用: list[str] = []

    def 假识别(配置, _图像):
        调用.append(配置.名称)
        return 输出[配置.名称]

    monkeypatch.setattr(识别器, "_识别单色", 假识别)
    assert 识别器.识别(np.zeros((1, 1, 3), dtype=np.uint8)).color == "绿色"
    输出.update({"绿色": None, "蓝色": _候选("蓝色", 0.9)})
    assert 识别器.识别(np.zeros((1, 1, 3), dtype=np.uint8)) is None
    assert 识别器.待切换颜色 == "蓝色"
    输出["绿色"] = _候选("绿色", 0.7)
    调用.clear()

    assert 识别器.识别(np.zeros((1, 1, 3), dtype=np.uint8)).color == "绿色"
    assert 调用 == ["绿色"]
    assert 识别器.待切换颜色 is None
    assert 识别器.待切换计数 == 0


def test连续两帧候选才从绿色切换到蓝色(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    识别器 = 三色精准角度识别器(项目根目录)
    输出 = {"绿色": _候选("绿色", 0.8), "蓝色": None, "黄色": None}
    调用: list[str] = []

    def 假识别(配置, _图像):
        调用.append(配置.名称)
        return 输出[配置.名称]

    monkeypatch.setattr(识别器, "_识别单色", 假识别)
    assert 识别器.识别(np.zeros((1, 1, 3), dtype=np.uint8)).color == "绿色"
    输出.update({"绿色": None, "蓝色": _候选("蓝色", 0.9)})
    调用.clear()

    assert 识别器.识别(np.zeros((1, 1, 3), dtype=np.uint8)) is None
    assert 调用 == ["绿色", "蓝色", "黄色"]
    assert 识别器.待切换颜色 == "蓝色"
    assert 识别器.待切换计数 == 1
    调用.clear()
    第二帧结果 = 识别器.识别(np.zeros((1, 1, 3), dtype=np.uint8))
    assert 第二帧结果 is 输出["蓝色"]
    assert 调用 == ["绿色", "蓝色", "黄色"]
    assert 识别器.当前颜色 == "蓝色"
    assert 识别器.待切换颜色 is None
    assert 识别器.待切换计数 == 0


def test待切换时最终诊断明确等待颜色而非扫描中间错误(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    识别器 = 三色精准角度识别器(项目根目录)
    输出 = {"绿色": _候选("绿色", 0.8), "蓝色": None, "黄色": None}

    def 假识别(配置, _图像):
        候选 = 输出[配置.名称]
        if 候选 is None:
            识别器._最近错误 = f"{配置.名称}识别失败：受控失败"
        return 候选

    monkeypatch.setattr(识别器, "_识别单色", 假识别)
    识别器.识别(np.zeros((1, 1, 3), dtype=np.uint8))
    输出.update({"绿色": None, "蓝色": _候选("蓝色", 0.9)})

    assert 识别器.识别(np.zeros((1, 1, 3), dtype=np.uint8)) is None
    assert 识别器.待切换颜色 == "蓝色"
    assert "绿色识别失败" in str(识别器.最近错误)
    assert "等待蓝色 1/2" in str(识别器.最近错误)
    assert "黄色识别失败" not in str(识别器.最近错误)


def test当前色失败且无替代候选时保留当前色诊断(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    识别器 = 三色精准角度识别器(项目根目录)
    输出 = {"绿色": _候选("绿色", 0.8), "蓝色": None, "黄色": None}

    def 假识别(配置, _图像):
        候选 = 输出[配置.名称]
        if 候选 is None:
            识别器._最近错误 = f"{配置.名称}识别失败：受控失败"
        return 候选

    monkeypatch.setattr(识别器, "_识别单色", 假识别)
    识别器.识别(np.zeros((1, 1, 3), dtype=np.uint8))
    输出["绿色"] = None

    assert 识别器.识别(np.zeros((1, 1, 3), dtype=np.uint8)) is None
    assert "绿色识别失败" in str(识别器.最近错误)
    assert "黄色识别失败" not in str(识别器.最近错误)


def test待切蓝色时旧绿色恢复会保留绿色并清pending(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    识别器 = 三色精准角度识别器(项目根目录)
    输出 = {"绿色": _候选("绿色", 0.8), "蓝色": None, "黄色": None}
    monkeypatch.setattr(识别器, "_识别单色", lambda 配置, _图像: 输出[配置.名称])
    识别器.识别(np.zeros((1, 1, 3), dtype=np.uint8))
    输出.update({"绿色": None, "蓝色": _候选("蓝色", 0.9)})
    assert 识别器.识别(np.zeros((1, 1, 3), dtype=np.uint8)) is None
    输出["绿色"] = _候选("绿色", 0.7)

    恢复结果 = 识别器.识别(np.zeros((1, 1, 3), dtype=np.uint8))

    assert 恢复结果 is 输出["绿色"]
    assert 识别器.当前颜色 == "绿色"
    assert 识别器.待切换颜色 is None
    assert 识别器.待切换计数 == 0


def test空帧中断待切换且下一蓝帧重新计数并且不返回旧角(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    识别器 = 三色精准角度识别器(项目根目录)
    旧结果 = _候选("绿色", 0.8, 角度=20.0)
    输出 = {"绿色": 旧结果, "蓝色": None, "黄色": None}
    monkeypatch.setattr(识别器, "_识别单色", lambda 配置, _图像: 输出[配置.名称])
    assert 识别器.识别(np.zeros((1, 1, 3), dtype=np.uint8)) is 旧结果
    输出.update({"绿色": None, "蓝色": _候选("蓝色", 0.9, 角度=80.0)})
    assert 识别器.识别(np.zeros((1, 1, 3), dtype=np.uint8)) is None
    输出["蓝色"] = None

    assert 识别器.识别(np.zeros((1, 1, 3), dtype=np.uint8)) is None
    assert 识别器.待切换颜色 is None
    assert 识别器.待切换计数 == 0
    输出["蓝色"] = _候选("蓝色", 0.9, 角度=80.0)
    assert 识别器.识别(np.zeros((1, 1, 3), dtype=np.uint8)) is None
    assert 识别器.待切换颜色 == "蓝色"
    assert 识别器.待切换计数 == 1


def test_reset只清状态且不重新读取标定(monkeypatch: pytest.MonkeyPatch) -> None:
    识别器 = 三色精准角度识别器(项目根目录)
    输出 = {"绿色": _候选("绿色", 0.8), "蓝色": None, "黄色": None}
    monkeypatch.setattr(识别器, "_识别单色", lambda 配置, _图像: 输出[配置.名称])
    识别器.识别(np.zeros((1, 1, 3), dtype=np.uint8))
    输出.update({"绿色": None, "蓝色": _候选("蓝色", 0.9)})
    识别器.识别(np.zeros((1, 1, 3), dtype=np.uint8))
    monkeypatch.setattr(
        "三色精准角度.读取并验证标定",
        lambda _path: (_ for _ in ()).throw(AssertionError("reset不得重新读标定")),
    )

    识别器.reset()

    assert 识别器.当前颜色 is None
    assert 识别器.待切换颜色 is None
    assert 识别器.待切换计数 == 0
    assert 识别器.最近错误 is None


@pytest.mark.parametrize("损坏方式", ["缺失", "坏记录"])
def test单色资产缺失或损坏时禁用该色且其它色仍可识别(
    tmp_path: Path,
    损坏方式: str,
) -> None:
    绿色, 蓝色, 黄色 = FUSION颜色配置
    _写有效标定(tmp_path, 绿色)
    _写有效标定(tmp_path, 黄色)
    蓝色路径 = (tmp_path / 蓝色.校准相对路径).resolve()
    if 损坏方式 == "坏记录":
        蓝色路径.parent.mkdir(parents=True, exist_ok=True)
        蓝色路径.write_text("CORRUPTED RECORD\n", encoding="utf-8")
    (tmp_path / "lv.txt").write_text(
        "SRC_CROP:0,0,193,193\nPRECISE_CENTER:193,193\n"
        + "".join(f"MAP:{角度},{角度}\n" for 角度 in range(360)),
        encoding="utf-8",
    )

    识别器 = 三色精准角度识别器(tmp_path)

    错误文本 = "\n".join(识别器.加载错误) + "\n" + str(识别器.最近错误)
    assert "蓝色" in 错误文本
    assert str(蓝色路径) in 错误文本
    assert ("无法读取文件" if 损坏方式 == "缺失" else "未知或损坏") in 错误文本
    图像, _期望 = _创建真实箭头图(绿色, tmp_path)
    结果 = 识别器.识别(图像)
    assert 结果 is not None
    assert 结果.color == "绿色"


def test三色资产全不可用时构造和识别均不崩溃(tmp_path: Path) -> None:
    识别器 = 三色精准角度识别器(tmp_path)

    assert len(识别器.加载错误) == 3
    识别器.reset()
    assert 识别器.最近错误 is None
    assert 识别器.识别(np.zeros((193, 193, 3), dtype=np.uint8)) is None
    assert "无可用颜色标定" in str(识别器.最近错误)
    for 配置 in FUSION颜色配置:
        assert 配置.名称 in "\n".join(识别器.加载错误)
        assert str((tmp_path / 配置.校准相对路径).resolve()) in "\n".join(识别器.加载错误)
        assert 配置.名称 in str(识别器.最近错误)
