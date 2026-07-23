from __future__ import annotations

import hashlib
import math
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

import 识别角度 as 角度模块
from 三色精准角度 import FUSION颜色配置, 标定无效, 读取并验证标定


项目根目录 = Path(__file__).resolve().parents[1]


def _最短角差(实际值: float, 期望值: float) -> float:
    return (float(期望值) - float(实际值) + 180.0) % 360.0 - 180.0


def _均匀MAP(数量: int = 360) -> list[str]:
    return [f"MAP:{角度},{角度}" for 角度 in range(数量)]


def _标定文本(
    *,
    crop: str | None = "0,0,100,100",
    center: str | None = "100,100",
    map行: list[str] | None = None,
    注释: str = "# 标定",
) -> str:
    行: list[str] = []
    if crop is not None:
        行.append(f"SRC_CROP:{crop}")
    if center is not None:
        行.append(f"PRECISE_CENTER:{center}")
    行.append(注释)
    行.extend(_均匀MAP() if map行 is None else map行)
    return "\n".join(行) + "\n"


def _断言标定无效(
    tmp_path: Path,
    内容: str,
    原因片段: str,
) -> str:
    path = tmp_path / "无效标定.txt"
    path.write_text(内容, encoding="utf-8")

    with pytest.raises(标定无效) as 异常:
        读取并验证标定(path)

    消息 = str(异常.value)
    assert str(path) in 消息
    assert 原因片段 in 消息
    return 消息


@pytest.mark.parametrize(
    "损坏行",
    ["MAP 10,10", "SRC_CROP 0,0,1,1", "CORRUPTED RECORD"],
)
def test拒绝未知或疑似字段畸形行(tmp_path: Path, 损坏行: str) -> None:
    内容 = _标定文本() + 损坏行 + "\n"
    path = tmp_path / "末尾损坏的标定.txt"
    path.write_text(内容, encoding="utf-8")

    with pytest.raises(标定无效) as 异常:
        读取并验证标定(path)

    消息 = str(异常.value)
    assert str(path) in 消息
    assert "第 364 行" in 消息
    assert "未知或损坏的记录" in 消息
    assert 损坏行 in 消息


def test读取遇到OSError立即失败且不继续尝试编码(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "无权读取.txt"
    尝试编码: list[str] = []

    def 假读取(_self: Path, *, encoding: str) -> str:
        尝试编码.append(encoding)
        raise OSError("拒绝访问")

    monkeypatch.setattr(Path, "read_text", 假读取)

    with pytest.raises(标定无效) as 异常:
        读取并验证标定(path)

    消息 = str(异常.value)
    assert 尝试编码 == ["utf-8-sig"]
    assert str(path) in 消息
    assert "无法读取文件" in 消息
    assert "拒绝访问" in 消息


def test所有编码UnicodeDecodeError耗尽后报告失败(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "无法解码.txt"
    尝试编码: list[str] = []

    def 假读取(_self: Path, *, encoding: str) -> str:
        尝试编码.append(encoding)
        raise UnicodeDecodeError(encoding, b"\xff", 0, 1, "非法字节")

    monkeypatch.setattr(Path, "read_text", 假读取)

    with pytest.raises(标定无效) as 异常:
        读取并验证标定(path)

    消息 = str(异常.value)
    assert 尝试编码 == ["utf-8-sig", "utf-8", "gbk", "gb18030"]
    assert str(path) in 消息
    assert "无法使用 utf-8-sig、utf-8、gbk 或 gb18030 解码" in 消息


@pytest.mark.parametrize(
    ("内容", "行号", "原因片段"),
    [
        (
            _标定文本().replace(
                "SRC_CROP:0,0,100,100\n",
                "SRC_CROP:0,0,100,100\nSRC_CROP:0,0,100,100\n",
            ),
            2,
            "重复 SRC_CROP",
        ),
        (
            _标定文本().replace(
                "PRECISE_CENTER:100,100\n",
                "PRECISE_CENTER:100,100\nPRECISE_CENTER:100,100\n",
            ),
            3,
            "重复 PRECISE_CENTER",
        ),
    ],
)
def test拒绝重复单值字段(
    tmp_path: Path,
    内容: str,
    行号: int,
    原因片段: str,
) -> None:
    消息 = _断言标定无效(tmp_path, 内容, 原因片段)
    assert f"第 {行号} 行" in 消息


@pytest.mark.parametrize(
    ("内容", "行号", "原因片段"),
    [
        (_标定文本(crop="0,0,100"), 1, "SRC_CROP 必须是四个整数"),
        (_标定文本(center="100"), 2, "PRECISE_CENTER 必须是两个数"),
        (
            _标定文本(map行=["MAP:0"] + _均匀MAP()[1:]),
            4,
            "MAP 必须是两个数",
        ),
    ],
)
def test拒绝字段数量错误且报告行号(
    tmp_path: Path,
    内容: str,
    行号: int,
    原因片段: str,
) -> None:
    消息 = _断言标定无效(tmp_path, 内容, 原因片段)
    assert f"第 {行号} 行" in 消息


@pytest.mark.parametrize(
    ("内容", "行号", "原因片段"),
    [
        (_标定文本(crop="0,坏,100,100"), 1, "SRC_CROP 必须是四个整数"),
        (_标定文本(center="100,坏"), 2, "PRECISE_CENTER 必须是两个数"),
        (
            _标定文本(map行=["MAP:坏,0"] + _均匀MAP()[1:]),
            4,
            "MAP 必须是两个数",
        ),
    ],
)
def test拒绝普通非法数值且报告行号(
    tmp_path: Path,
    内容: str,
    行号: int,
    原因片段: str,
) -> None:
    消息 = _断言标定无效(tmp_path, 内容, 原因片段)
    assert f"第 {行号} 行" in 消息


def test拒绝有限但非整数的游戏角且报告行号(tmp_path: Path) -> None:
    内容 = _标定文本(map行=["MAP:0,1.5"] + _均匀MAP()[1:])

    消息 = _断言标定无效(tmp_path, 内容, "MAP 游戏角必须是整数")

    assert "第 4 行" in 消息


def testFusion三色配置使用精确参数且冻结() -> None:
    assert isinstance(FUSION颜色配置, tuple)
    assert [配置.名称 for 配置 in FUSION颜色配置] == ["绿色", "蓝色", "黄色"]

    assert FUSION颜色配置[0].hsv下界 == (48, 66, 87)
    assert FUSION颜色配置[0].hsv上界 == (78, 166, 255)
    assert FUSION颜色配置[0].校准相对路径 == Path("校准数据/Fusion/绿色/lv.txt")
    assert FUSION颜色配置[0].代表色 == "9AE77E"
    assert FUSION颜色配置[0].mask期望值 == 438

    assert FUSION颜色配置[1].hsv下界 == (100, 50, 50)
    assert FUSION颜色配置[1].hsv上界 == (130, 255, 255)
    assert FUSION颜色配置[1].校准相对路径 == Path("校准数据/Fusion/蓝色/lv.txt")
    assert FUSION颜色配置[1].代表色 == "95BBE8"
    assert FUSION颜色配置[1].mask期望值 == 425

    assert FUSION颜色配置[2].hsv下界 == (18, 80, 80)
    assert FUSION颜色配置[2].hsv上界 == (40, 255, 255)
    assert FUSION颜色配置[2].校准相对路径 == Path("校准数据/Fusion/黄色/lv.txt")
    assert FUSION颜色配置[2].代表色 == "F0E791"
    assert FUSION颜色配置[2].mask期望值 == 380

    with pytest.raises(FrozenInstanceError):
        setattr(FUSION颜色配置[0], "名称", "另一种绿色")


@pytest.mark.parametrize(
    ("名称", "sha256", "crop", "center", "map数量", "归零原始角"),
    [
        (
            "绿色",
            "C5851E480890B391D7BC08F80F589383D065635F2041A7E893005CC7D81398E2",
            (46, 50, 146, 150),
            (102.968905, 92.205255),
            353,
            298.819047,
        ),
        (
            "蓝色",
            "18E39D7763CA51CE759E23DA773CC0A64B15CCC2921EA6DF5D0B483CE89E624D",
            (76, 70, 116, 110),
            (43.061184, 42.238440),
            359,
            296.059175,
        ),
        (
            "黄色",
            "409B09E134D9586CF9FC26B382FB84C9D2530ECCD25B953100D3019E40712F87",
            (62, 56, 130, 124),
            (70.820383, 70.104956),
            360,
            298.590937,
        ),
    ],
)
def test三份独立标定文件原样复制且元数据正确(
    名称: str,
    sha256: str,
    crop: tuple[int, int, int, int],
    center: tuple[float, float],
    map数量: int,
    归零原始角: float,
) -> None:
    配置 = next(配置 for 配置 in FUSION颜色配置 if 配置.名称 == 名称)
    path = 项目根目录 / 配置.校准相对路径

    assert hashlib.sha256(path.read_bytes()).hexdigest().upper() == sha256
    数据 = 读取并验证标定(path)
    assert 数据["crop"] == crop
    assert 数据["center_x"] == pytest.approx(center[0])
    assert 数据["center_y"] == pytest.approx(center[1])
    assert len(数据["map_list"]) == map数量
    assert all(isinstance(原始角, float) for 原始角, _ in 数据["map_list"])
    assert all(isinstance(游戏角, int) for _, 游戏角 in 数据["map_list"])
    assert (归零原始角, 0) in 数据["map_list"]
    assert all(游戏角 != 360 for _, 游戏角 in 数据["map_list"])


@pytest.mark.parametrize("名称", ["绿色", "蓝色", "黄色"])
def test三色真实标定留一预测满足误差阈值(名称: str) -> None:
    配置 = next(配置 for 配置 in FUSION颜色配置 if 配置.名称 == 名称)
    样本 = 读取并验证标定(项目根目录 / 配置.校准相对路径)["map_list"]
    误差: list[float] = []

    for 索引, (原始角, 游戏角) in enumerate(样本):
        留一数据 = 样本[:索引] + 样本[索引 + 1 :]
        预测角 = 角度模块.圆形残差插值(原始角, 留一数据)
        assert 预测角 is not None
        误差.append(abs(_最短角差(预测角, 游戏角)))

    误差.sort()
    p95 = 误差[math.ceil(len(误差) * 0.95) - 1]
    assert p95 < 1.5, f"{名称} P95={p95:.6f}°"
    assert max(误差) < 2.5, f"{名称} max={max(误差):.6f}°"


@pytest.mark.parametrize(
    ("encoding", "注释"),
    [
        ("utf-8-sig", "# UTF-8 BOM 标定"),
        ("utf-8", "# UTF-8 标定"),
        ("gbk", "# GBK 标定"),
        ("gb18030", "# GB18030 专用字符：𠀀"),
    ],
)
def test读取兼容四种文本编码(tmp_path: Path, encoding: str, 注释: str) -> None:
    path = tmp_path / f"{encoding}.txt"
    path.write_text(_标定文本(注释=注释), encoding=encoding)

    数据 = 读取并验证标定(path)

    assert 数据["crop"] == (0, 0, 100, 100)
    assert 数据["center_x"] == 100.0
    assert 数据["center_y"] == 100.0
    assert len(数据["map_list"]) == 360


@pytest.mark.parametrize(
    ("内容", "原因片段"),
    [
        (_标定文本(crop=None), "缺少 SRC_CROP"),
        (_标定文本(center=None), "缺少 PRECISE_CENTER"),
        (_标定文本(map行=[]), "缺少 MAP"),
    ],
)
def test拒绝缺少必需字段(tmp_path: Path, 内容: str, 原因片段: str) -> None:
    _断言标定无效(tmp_path, 内容, 原因片段)


@pytest.mark.parametrize(
    ("内容", "行号"),
    [
        (_标定文本(center="nan,100"), 2),
        (_标定文本(map行=["MAP:inf,0"] + _均匀MAP()[1:]), 4),
        (_标定文本(map行=["MAP:0,nan"] + _均匀MAP()[1:]), 4),
    ],
)
def test拒绝非有限数(tmp_path: Path, 内容: str, 行号: int) -> None:
    消息 = _断言标定无效(tmp_path, 内容, "非有限")
    assert f"第 {行号} 行" in 消息


@pytest.mark.parametrize(
    "crop",
    [
        "46,50,46,150",
        "46,50,146,50",
        "-1,0,100,100",
        "0,0,194,193",
        "0,0,193,194",
    ],
)
def test拒绝非正或越出193画布的crop(tmp_path: Path, crop: str) -> None:
    消息 = _断言标定无效(tmp_path, _标定文本(crop=crop), "SRC_CROP")
    assert "第 1 行" in 消息


@pytest.mark.parametrize("center", ["-0.1,10", "10,-0.1", "20,10", "10,20"])
def test拒绝越出两倍crop的精准中心(tmp_path: Path, center: str) -> None:
    内容 = _标定文本(crop="10,20,20,30", center=center)
    消息 = _断言标定无效(tmp_path, 内容, "PRECISE_CENTER")
    assert "第 2 行" in 消息


def test拒绝少于300条map(tmp_path: Path) -> None:
    _断言标定无效(tmp_path, _标定文本(map行=_均匀MAP(299)), "MAP 数量少于 300")


@pytest.mark.parametrize(
    ("无效行", "原因片段"),
    [
        ("MAP:-0.1,0", "原始角必须在 [0, 360)"),
        ("MAP:360,0", "原始角必须在 [0, 360)"),
        ("MAP:0,-1", "游戏角必须在 [0, 360]"),
        ("MAP:0,361", "游戏角必须在 [0, 360]"),
    ],
)
def test拒绝越出角度范围的map(
    tmp_path: Path,
    无效行: str,
    原因片段: str,
) -> None:
    消息 = _断言标定无效(
        tmp_path,
        _标定文本(map行=[无效行] + _均匀MAP()[1:]),
        原因片段,
    )
    assert "第 4 行" in 消息


def test游戏角360规范化为0(tmp_path: Path) -> None:
    path = tmp_path / "游戏角360.txt"
    path.write_text(
        _标定文本(map行=["MAP:0,360"] + _均匀MAP()[1:]),
        encoding="utf-8",
    )

    数据 = 读取并验证标定(path)

    assert 数据["map_list"][0] == (0.0, 0)


def test拒绝原始角最大圆周间隙超过10度(tmp_path: Path) -> None:
    _断言标定无效(
        tmp_path,
        _标定文本(map行=_均匀MAP(300)),
        "原始角最大圆周间隙",
    )
