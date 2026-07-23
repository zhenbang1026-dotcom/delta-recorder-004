from __future__ import annotations

import importlib.util
import json
import math
import random
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path
import threading
import time

from 连续视角控制 import 默认视角速度倍率, 规范化视角速度倍率, 连续视角控制器


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
    import Win32键鼠模块 as win32_input
except ModuleNotFoundError:
    win32_input = _按文件名加载模块("Win32键鼠模块")
try:
    import A记录坐标和角度版本 as 合并识别模块
except ModuleNotFoundError:
    合并识别模块 = _按文件名加载模块("A记录坐标和角度版本")


# 用户标定：水平滑动 33.3 像素 ≈ 游戏内 1°（= 100/3）
每度像素 = 100 / 3
# text 模式锁定该值（标定尺：33.3px=1°）
TEXT_每度像素 = 100 / 3
# 增益折中：0.45 太肉、1.0+大 cap 太猛 → 微调约 0.85×、单帧≤12°
TEXT_微调像素增益 = 0.85
TEXT_微调最大角度 = 12.0
# 停车转向：约 0.85×、单次≤38°（≈ 33.3*38*0.85 ≈ 1070px 上限）
TEXT_转向像素增益 = 0.85
TEXT_单次最大转向角度 = 38.0
小地图区域 = (57, 116, 200, 235)
# 默认旧算法 ROI；text 模式切换为 (34,78,227,271)
角度区域 = (119, 161, 146, 188)
角度区域_旧 = (119, 161, 146, 188)
角度区域_text = (34, 78, 227, 271)
地图文件路径 = "maps/DB.png"
小地图宽度 = 143
小地图高度 = 119
角度颜色 = ("F0E791", "9AE77E", "95BBE8")
角度容差 = 90
角度最小面积 = 1.0
角度清理掩码 = False
角度使用HSV = False
大地图最小特征数 = 10
终点对正角度阈值 = 3.0
终点对正最大尝试次数 = 5
局部匹配搜索边距 = 220
模板匹配缩放 = 2.0
模板匹配阈值 = 0.6
模板匹配边缘裁剪 = 6
匹配最小缩放 = 1.0
匹配最大缩放 = 3.2
匹配最大旋转角度 = 15.0
小地图特征掩码缩进 = 6
默认到点阈值 = 3
默认精准模式 = False
默认终点对正 = False
默认启动延迟秒数 = 2
自动路线最小点距 = 18
增强自动路线最小点距 = 6
首次状态读取最大重试次数 = 30
状态读取最大重试次数 = 10
状态读取重试间隔 = 0.1
刷新视角后等待秒数 = 0.2
转向后确认超时秒数 = 0.6
转向后确认轮询间隔 = 0.05
转向后最小角度变化 = 4.0
转向后最小收敛角差 = 6.0
最近状态最大沿用次数 = 5
TEXT角度最大沿用帧数 = 2
TEXT角度最大沿用秒数 = 0.10
角度颜色识别错误 = ("没有匹配到主颜色", "只找到 0 个颜色像素", "颜色像素未覆盖截图中心", "未找到可用的朝向目标点")
可重试识别错误 = ("无法识别当前位置", "无法识别当前朝向", *角度颜色识别错误)
预览宽度 = 600
角度识别刷新最大次数 = 3
角度刷新最小角度 = 8.0
角度刷新最大角度 = 15.0
卡住检测秒数 = 5.0
卡住判定距离 = 1
脱困冷却秒数 = 3.0
脱困转向角度 = 25.0
脱困前进秒数 = 0.4
脱困转向序列 = (-30.0, 30.0, -60.0, 60.0)
最大单帧角度跳变 = 90.0
角度跳变复查阈值 = 45.0
角度跳变复查一致阈值 = 8.0
角度跳变小位移距离 = 4
转向后异常变差角度 = 8.0
日志目录 = Path("logs")
定位诊断目录 = 日志目录 / "定位诊断"
定位诊断上限 = 200
定位诊断最小间隔 = 2.0
转向不收敛判定次数 = 4
转向收敛最小改善角度 = 8.0
转向不收敛微调角度 = 12.0
转向不收敛原地距离 = 4
近点位转向保护增量 = 2
增强近点位保护距离 = 10
增强近点位最大微调角度 = 4.0
自适应转向比例 = 0.65
自适应转向最大角度 = 30.0
振荡转向抑制比例 = 0.5
转向类动作 = ("转向", "终点对正", "刷新视角")
寻路诊断目录 = 日志目录 / "寻路诊断"
寻路诊断截图上限 = 300
标定最小角度变化 = 5.0
标定平滑比例 = 0.25
每度像素下限 = 每度像素 * 0.7
每度像素上限 = 每度像素 * 1.5
标定样本最小比例 = 0.5
标定样本最大比例 = 1.5
坐标跳变判定距离 = 80
坐标跳变判定秒数 = 1.0

_每度像素校准 = {"值": 每度像素}


def 是否text角度模式() -> bool:
    try:
        return 合并识别模块.当前角度模式() == "text"
    except Exception:
        return False


def 是否增强角度模式() -> bool:
    return 是否text角度模式()


def 当前模式自动路线点距() -> int:
    return 增强自动路线最小点距 if 是否增强角度模式() else 自动路线最小点距


def 重置每度像素校准(值: float | None = None) -> float:
    _每度像素校准["值"] = float(值 if 值 is not None else 每度像素)
    return _每度像素校准["值"]


@dataclass(frozen=True)
class 路径点:
    x: int
    y: int
    angle: float
    自动路线: bool = False


@dataclass(frozen=True)
class 模式参数:
    大角度阈值: float
    小角度阈值: float
    允许疾跑: bool
    精准缩放: float


@dataclass(frozen=True)
class 动作指令:
    类型: str
    鼠标像素: int = 0
    持续时间: float = 0.0


class 紧急停止异常(RuntimeError):
    pass


def 计算目标角度(x1: float, y1: float, x2: float, y2: float) -> float:
    dx = x2 - x1
    dy = y2 - y1
    return math.degrees(math.atan2(dx, -dy)) % 360


def 计算距离(x1: float, y1: float, x2: float, y2: float) -> int:
    return int(round(math.hypot(x2 - x1, y2 - y1)))


def 计算最短角度差(当前角度: float, 目标角度: float) -> float:
    角度差 = (目标角度 - 当前角度 + 540) % 360 - 180
    if 角度差 == -180:
        return 180.0 if 目标角度 > 当前角度 else -180.0
    return 角度差


def 当前每度像素() -> float:
    # text：固定 33.3 px/°，与用户标定一致
    if 是否增强角度模式():
        return float(TEXT_每度像素)
    return _每度像素校准["值"]


def 更新每度像素校准(鼠标像素: int, 实际角度变化: float) -> float:
    # text 不参与在线标定，避免漂到 40+ 导致过冲
    if 是否增强角度模式():
        return float(TEXT_每度像素)
    if not 鼠标像素 or abs(实际角度变化) < 标定最小角度变化:
        return _每度像素校准["值"]
    if (鼠标像素 > 0) != (实际角度变化 > 0):
        return _每度像素校准["值"]
    实测每度像素 = abs(鼠标像素) / abs(实际角度变化)
    新值 = _每度像素校准["值"] * (1 - 标定平滑比例) + 实测每度像素 * 标定平滑比例
    _每度像素校准["值"] = min(每度像素上限, max(每度像素下限, 新值))
    return _每度像素校准["值"]


def 角度差转鼠标像素(角度差: float, 像素增益: float = 1.0) -> int:
    像素差 = 角度差 * 当前每度像素() * float(像素增益)
    return int(math.copysign(math.floor(abs(像素差) + 0.5), 像素差))


def 计算自适应转向角度(角度差: float) -> float:
    if 是否增强角度模式():
        幅度 = min(abs(角度差) * 0.88, TEXT_单次最大转向角度)
        return math.copysign(幅度, 角度差)
    幅度 = min(abs(角度差), abs(角度差) * 自适应转向比例, 自适应转向最大角度)
    return math.copysign(幅度, 角度差)


def 校验到点阈值(到点阈值: int) -> None:
    if 到点阈值 < 1:
        raise ValueError("到点阈值必须大于等于 1")


def 巡航默认参数() -> dict[str, object]:
    return {
        "到点阈值": 默认到点阈值,
        "精准模式": 默认精准模式,
        "终点对正": 默认终点对正,
    }


def 校验路线文件(路径文件: str) -> str:
    路径文件 = 路径文件.strip()
    if not 路径文件:
        raise ValueError("请先选择路线文件")
    return 路径文件


def 绘制定位预览图(大地图, 状态: tuple[int, int, float] | None = None):
    import cv2

    预览图 = 大地图.copy()
    if 状态 is None:
        return 预览图
    x, y, angle = 状态
    左 = max(0, int(x) - 小地图宽度 // 2)
    上 = max(0, int(y) - 小地图高度 // 2)
    右 = min(预览图.shape[1], int(x) + 小地图宽度 // 2)
    下 = min(预览图.shape[0], int(y) + 小地图高度 // 2)
    cv2.rectangle(预览图, (左, 上), (右, 下), (0, 0, 255), 2)
    cv2.circle(预览图, (int(x), int(y)), 5, (0, 0, 255), -1)
    cv2.putText(
        预览图,
        f"({int(x)}, {int(y)}) {float(angle):.1f}",
        (左 + 5, max(15, 上 - 5)),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.5,
        (0, 0, 255),
        1,
    )
    return 预览图


def 缩放为Tk图片(图像bgr, 最大宽度: int = 预览宽度):
    import cv2
    from PIL import Image, ImageTk

    image = Image.fromarray(cv2.cvtColor(图像bgr, cv2.COLOR_BGR2RGB))
    if image.width > 最大宽度:
        scale = 最大宽度 / image.width
        resampling = getattr(getattr(Image, "Resampling", Image), "LANCZOS")
        image = image.resize((最大宽度, int(image.height * scale)), resampling)
    return ImageTk.PhotoImage(image=image)


def 构建开始状态文本(延迟秒数: int) -> str:
    return f"已开始，{延迟秒数} 秒后执行寻路"


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


def 处理esc紧急停止(停止事件: threading.Event | None = None, 根窗口=None) -> bool:
    已触发 = 停止事件.is_set() if 停止事件 is not None else False
    if not 已触发 and not win32_input.按键是否按下("esc"):
        return False
    if 停止事件 is not None:
        停止事件.set()
    if 根窗口 is not None:
        try:
            根窗口.after(0, 根窗口.destroy)
        except Exception:
            pass
    return True


def 创建日志记录器(日志名称: str, 输出目录: Path = 日志目录, 时间戳: str | None = None):
    路径 = 生成日志路径(日志名称, Path(输出目录), 时间戳 or time.strftime("%Y%m%d_%H%M%S"))
    # 缓冲写盘：降低每步 open/flush 对控制环的抖动
    _缓冲: list[str] = []
    _缓冲上限 = 12
    _锁 = threading.Lock()

    def _刷盘(强制: bool = False) -> None:
        if not _缓冲:
            return
        if not 强制 and len(_缓冲) < _缓冲上限:
            return
        文本 = "".join(_缓冲)
        _缓冲.clear()
        with 路径.open("a", encoding="utf-8") as 文件:
            文件.write(文本)

    def 记录日志(事件: str, **字段) -> None:
        行 = 格式化日志行(事件, **字段) + "\n"
        with _锁:
            _缓冲.append(行)
            # 关键事件立即落盘，普通 step 批量写
            强制 = 事件 not in {"event=step", "step"}
            try:
                _刷盘(强制=强制)
            except Exception:
                pass

    def 关闭日志() -> None:
        with _锁:
            try:
                _刷盘(强制=True)
            except Exception:
                pass

    记录日志.关闭 = 关闭日志  # type: ignore[attr-defined]
    return 路径, 记录日志


def 写日志(日志函数, 事件: str, **字段) -> None:
    if 日志函数 is None:
        return
    try:
        日志函数(事件, **字段)
    except TypeError:
        日志函数(格式化日志行(事件, **字段))


def 设置识别诊断状态(对象, 文本: str) -> None:
    try:
        setattr(对象, "识别诊断状态", 文本)
    except Exception:
        pass


def 设置控制诊断状态(对象, 文本: str) -> None:
    try:
        setattr(对象, "控制诊断状态", 文本)
    except Exception:
        pass


def 格式化诊断状态文本(定位器=None) -> str:
    控制状态 = getattr(定位器, "控制诊断状态", "待机")
    识别状态 = getattr(定位器, "识别诊断状态", "未开始")
    return f"诊断: 控制={控制状态} | 识别={识别状态}"


def 格式化控制详情文本(定位器=None) -> str:
    目标详情 = getattr(定位器, "当前目标点详情", "--")
    目标角度 = getattr(定位器, "当前目标角度", None)
    当前角度差 = getattr(定位器, "当前角度差", None)
    最近动作 = getattr(定位器, "最近动作类型", "--")
    目标角度文本 = "--" if 目标角度 is None else f"{float(目标角度):.2f}"
    角度差文本 = "--" if 当前角度差 is None else f"{float(当前角度差):.2f}"
    return f"控制详情: 目标={目标详情} | 目标角度={目标角度文本} | 角度差={角度差文本} | 动作={最近动作}"


def _格式化角度点(点) -> str:
    if 点 is None:
        return "--"
    try:
        return f"{float(点[0]):.1f},{float(点[1]):.1f}"
    except Exception:
        return str(点)


def 角度诊断日志字段(定位器=None) -> dict[str, str]:
    return {
        "角度颜色": str(getattr(定位器, "角度诊断颜色", "--")),
        "角度origin": _格式化角度点(getattr(定位器, "角度诊断origin", None)),
        "角度target": _格式化角度点(getattr(定位器, "角度诊断target", None)),
        "角度mask像素": str(getattr(定位器, "角度诊断mask像素", "--")),
    }


def 模式诊断日志字段(定位器=None) -> dict[str, str]:
    try:
        模式 = str(合并识别模块.当前角度模式())
    except Exception:
        模式 = "legacy"
    字段 = {"角度模式": 模式}
    实际像素 = getattr(定位器, "连续控制实际像素", None)
    if 实际像素 is not None:
        字段["连续控制实际像素"] = str(实际像素)
    return 字段


def 普通模式参数() -> 模式参数:
    if 是否增强角度模式():
        # 中等门槛：太高会长期欠纠（角差 mean 35°）；太低又狂停车
        return 模式参数(大角度阈值=32, 小角度阈值=8, 允许疾跑=True, 精准缩放=1.0)
    return 模式参数(大角度阈值=18, 小角度阈值=6, 允许疾跑=True, 精准缩放=1.0)


def 精准模式参数() -> 模式参数:
    if 是否增强角度模式():
        return 模式参数(大角度阈值=22, 小角度阈值=5, 允许疾跑=False, 精准缩放=0.55)
    return 模式参数(大角度阈值=10, 小角度阈值=3, 允许疾跑=False, 精准缩放=0.35)


def text微调鼠标像素(角度差: float, 精准缩放: float = 1.0) -> int:
    """text 边跑边修：≤12°×0.85 增益 ≈ 约 340 像素/帧（折中）。"""
    限幅 = max(-TEXT_微调最大角度, min(TEXT_微调最大角度, 角度差)) * 精准缩放
    return 角度差转鼠标像素(限幅, TEXT_微调像素增益)


def 读取路径(路径文件: str, 自动路线点距: int | None = None) -> list[路径点]:
    内容 = Path(路径文件).read_text(encoding="utf-8-sig").splitlines()
    if not 内容 or all(not 行.strip() for 行 in 内容):
        raise ValueError("路径文件为空")

    结果: list[路径点] = []
    自动路线: bool | None = None
    for 行号, 行 in enumerate(内容, start=1):
        if not 行.strip():
            continue
        部分 = [项目.strip() for 项目 in 行.split(",")]
        if len(部分) not in (2, 3):
            raise ValueError(f"第{行号}行格式错误: {行}")
        当前自动路线 = len(部分) == 2
        if 自动路线 is None:
            自动路线 = 当前自动路线
        elif 自动路线 != 当前自动路线:
            raise ValueError(f"第{行号}行不能混用 x,y 和 x,y,角度 格式")
        try:
            x = int(部分[0])
            y = int(部分[1])
            angle = 0.0 if 当前自动路线 else float(部分[2])
        except ValueError as exc:
            raise ValueError(f"第{行号}行格式错误: {行}") from exc
        结果.append(路径点(x=x, y=y, angle=angle, 自动路线=当前自动路线))
    点距 = 自动路线最小点距 if 自动路线点距 is None else int(自动路线点距)
    return 抽稀自动路线(结果, 点距) if 自动路线 else 结果


def 抽稀自动路线(路径点列表: list[路径点], 最小点距: int = 自动路线最小点距) -> list[路径点]:
    if len(路径点列表) <= 2:
        return 路径点列表
    结果 = [路径点列表[0]]
    上次保留 = 路径点列表[0]
    for 点 in 路径点列表[1:-1]:
        if 计算距离(上次保留.x, 上次保留.y, 点.x, 点.y) >= 最小点距:
            结果.append(点)
            上次保留 = 点
    if 结果[-1] != 路径点列表[-1]:
        结果.append(路径点列表[-1])
    return 结果


def 选择动作(*, 距离: int, 角度差: float, 到点阈值: int, 参数: 模式参数, 自动路线: bool = False) -> 动作指令:
    if 距离 <= 到点阈值:
        return 动作指令("自动路线切换下一个点" if 自动路线 else "切换下一个点")
    # text：≥32° 且够远才停车；中等角差边跑边修（增益已折中）
    if 是否增强角度模式():
        if abs(角度差) >= 参数.大角度阈值 and 距离 >= 到点阈值 * 2:
            转角 = 计算自适应转向角度(角度差) * 参数.精准缩放
            return 动作指令(
                "转向",
                鼠标像素=角度差转鼠标像素(转角, TEXT_转向像素增益),
            )
        if 参数.允许疾跑 and 距离 >= 到点阈值 * 2:
            if abs(角度差) <= 参数.小角度阈值:
                return 动作指令("疾跑前进")
            return 动作指令(
                "疾跑前进并微调",
                鼠标像素=text微调鼠标像素(角度差, 参数.精准缩放),
            )
        if abs(角度差) <= 参数.小角度阈值:
            return 动作指令("前进")
        return 动作指令(
            "前进并微调",
            鼠标像素=text微调鼠标像素(角度差, 参数.精准缩放),
        )
    if abs(角度差) >= 参数.大角度阈值:
        return 动作指令("转向", 鼠标像素=角度差转鼠标像素(计算自适应转向角度(角度差) * 参数.精准缩放))
    if 自动路线 and 参数.允许疾跑 and 距离 >= 到点阈值 * 2:
        if abs(角度差) <= 参数.小角度阈值:
            return 动作指令("疾跑前进")
        return 动作指令("疾跑前进并微调", 鼠标像素=角度差转鼠标像素(角度差 * 参数.精准缩放))
    if 参数.允许疾跑 and abs(角度差) <= 参数.小角度阈值 and 距离 >= 到点阈值 * 5:
        return 动作指令("疾跑前进")
    if abs(角度差) <= 参数.小角度阈值:
        return 动作指令("前进")
    return 动作指令("前进并微调", 鼠标像素=角度差转鼠标像素(角度差 * 参数.精准缩放))


class 实时定位器:
    def __init__(
        self,
        *,
        地图路径: str = 地图文件路径,
        小地图截图区域: tuple[int, int, int, int] = 小地图区域,
        角度截图区域: tuple[int, int, int, int] | None = None,
        角度模式: str | None = None,
    ):
        self._加载依赖()
        self.小地图截图区域 = 小地图截图区域
        if 角度模式 is not None:
            合并识别模块.设置角度模式(角度模式)
        self.角度模式 = 合并识别模块.当前角度模式()
        if 角度截图区域 is None:
            try:
                角度截图区域 = 合并识别模块.当前角度区域()
            except Exception:
                角度截图区域 = 角度区域
        self.角度截图区域 = 角度截图区域
        self.大地图 = self._cv2.imread(str(Path(地图路径)))
        if self.大地图 is None:
            raise FileNotFoundError(f"未找到地图文件: {地图路径}")
        self.大地图灰度 = self._cv2.cvtColor(self.大地图, self._cv2.COLOR_BGR2GRAY)
        self._sift = self._cv2.SIFT_create()
        self._bf = self._cv2.BFMatcher(self._cv2.NORM_L2)
        self._大地图匹配灰度 = self._预处理匹配图像(self.大地图)
        self._大图关键点, self._大图描述符 = self._sift.detectAndCompute(self._大地图匹配灰度, None)
        if (
            self._大图描述符 is None
            or len(self._大图关键点) < 大地图最小特征数
            or len(self._大图描述符) < 大地图最小特征数
        ):
            raise RuntimeError(f"大地图特征不足，无法初始化实时定位器: {地图路径}")
        self._角度颜色列表 = [(颜色, self._解析十六进制颜色(颜色)) for 颜色 in 角度颜色]
        self._最近匹配坐标: tuple[int, int] | None = None
        self.最近状态: tuple[int, int, float] | None = None
        self._text最近有效角度: float | None = None
        self._text最近有效角度时间: float | None = None
        self._text角度连续沿用次数 = 0
        self.识别诊断状态 = "未开始"
        self.控制诊断状态 = "待机"
        self.角度诊断颜色 = "--"
        self.角度诊断origin = None
        self.角度诊断target = None
        self.角度诊断mask像素 = "--"
        self.当前目标点详情 = "--"
        self.当前目标角度: float | None = None
        self.当前角度差: float | None = None
        self.最近动作类型 = "--"
        self._读取锁 = threading.Lock()
        self._合并识别器 = 合并识别模块.实时坐标角度识别器(
            地图匹配器=合并识别模块.单独坐标识别器(地图路径)
        )

    def 设置角度模式(self, 模式: str) -> str:
        """切换角度算法并同步 ROI；截图后端不变。"""
        mode = 合并识别模块.设置角度模式(模式)
        self.角度模式 = mode
        try:
            self.角度截图区域 = 合并识别模块.当前角度区域()
        except Exception:
            self.角度截图区域 = 角度区域_text if mode == "text" else 角度区域_旧
        self.最近状态 = None
        self._text最近有效角度 = None
        self._text最近有效角度时间 = None
        self._text角度连续沿用次数 = 0
        # text：锁定 33.3 px/°；legacy：恢复默认可在线标定
        if mode == "text":
            重置每度像素校准(TEXT_每度像素)
        else:
            重置每度像素校准(每度像素)
        return mode

    def _加载依赖(self) -> None:
        try:
            import cv2
            import numpy as np
            from PIL import ImageGrab
        except ImportError as exc:
            缺少模块 = exc.name or str(exc)
            raise RuntimeError(f"实时定位器缺少识别依赖: {缺少模块}") from exc
        self._cv2 = cv2
        self._np = np
        self._ImageGrab = ImageGrab

    def _解析十六进制颜色(self, 值: str) -> tuple[int, int, int]:
        值 = 值.strip().lstrip("#")
        return int(值[0:2], 16), int(值[2:4], 16), int(值[4:6], 16)

    def _rgb转hsv颜色(self, rgb: tuple[int, int, int]) -> tuple[int, int, int]:
        arr = self._np.uint8([[list(rgb)]])
        hsv = self._cv2.cvtColor(arr, self._cv2.COLOR_RGB2HSV)[0, 0]
        return int(hsv[0]), int(hsv[1]), int(hsv[2])

    def _颜色阈值(self, 图像bgr, 颜色rgb: tuple[int, int, int]):
        if not 角度使用HSV:
            c = self._np.array([颜色rgb[2], 颜色rgb[1], 颜色rgb[0]], dtype=self._np.int16)
            lo = self._np.clip(c - 角度容差, 0, 255).astype(self._np.uint8)
            hi = self._np.clip(c + 角度容差, 0, 255).astype(self._np.uint8)
            mask = self._cv2.inRange(图像bgr, lo, hi)
        else:
            h, s, v = self._rgb转hsv颜色(颜色rgb)
            hsv = self._cv2.cvtColor(图像bgr, self._cv2.COLOR_BGR2HSV)
            h_tol = max(5, min(角度容差 // 3, 20))
            s_tol = max(20, min(角度容差, 80))
            v_tol = max(20, min(角度容差, 80))
            hl = (h - h_tol) % 180
            hh = (h + h_tol) % 180
            if hl <= hh:
                h_mask = self._cv2.inRange(hsv[:, :, 0], hl, hh)
            else:
                h_mask = self._cv2.bitwise_or(
                    self._cv2.inRange(hsv[:, :, 0], 0, hh),
                    self._cv2.inRange(hsv[:, :, 0], hl, 179),
                )
            s_mask = self._cv2.inRange(hsv[:, :, 1], max(0, s - s_tol), min(255, s + s_tol))
            v_mask = self._cv2.inRange(hsv[:, :, 2], max(0, v - v_tol), min(255, v + v_tol))
            mask = self._cv2.bitwise_and(self._cv2.bitwise_and(h_mask, s_mask), v_mask)
        if 角度清理掩码:
            k = self._np.ones((3, 3), self._np.uint8)
            mask = self._cv2.morphologyEx(mask, self._cv2.MORPH_OPEN, k)
            mask = self._cv2.morphologyEx(mask, self._cv2.MORPH_CLOSE, k)
        return mask

    def _轮廓中心(self, 轮廓) -> tuple[float, float] | None:
        m = self._cv2.moments(轮廓)
        if m["m00"] == 0:
            点集 = 轮廓.reshape(-1, 2)
            if len(点集) == 0:
                return None
            return float(点集[:, 0].mean()), float(点集[:, 1].mean())
        return m["m10"] / m["m00"], m["m01"] / m["m00"]

    def _优化中心(self, 轮廓) -> tuple[float, float] | None:
        点集 = 轮廓.reshape(-1, 2).astype(self._np.float32)
        if len(点集) < 5:
            return self._轮廓中心(轮廓)
        cx, cy = self._轮廓中心(轮廓) or (float(点集[:, 0].mean()), float(点集[:, 1].mean()))
        try:
            (ec_x, ec_y), _ = self._cv2.minEnclosingCircle(点集)
        except self._cv2.error:
            return cx, cy
        if abs(ec_x - cx) < 6 and abs(ec_y - cy) < 6:
            return float(ec_x), float(ec_y)
        return cx, cy

    def _识别角度(self, 图像bgr) -> float:
        if hasattr(self, "_合并识别器"):
            try:
                result = self._合并识别器.角度分析器(
                    图像bgr,
                    self._合并识别器.角度颜色,
                    合并识别模块.角度容差,
                    合并识别模块.角度最小面积,
                    False,
                    None,
                    False,
                )
            except RuntimeError:
                if getattr(self, "角度模式", None) != "text":
                    raise
                当前时间 = time.monotonic()
                最近角度 = getattr(self, "_text最近有效角度", None)
                最近时间 = getattr(self, "_text最近有效角度时间", None)
                沿用次数 = getattr(self, "_text角度连续沿用次数", 0)
                if (
                    最近角度 is not None
                    and 最近时间 is not None
                    and 沿用次数 < TEXT角度最大沿用帧数
                    and 当前时间 - 最近时间 <= TEXT角度最大沿用秒数
                ):
                    self._text角度连续沿用次数 = 沿用次数 + 1
                    self._角度复查诊断 = (
                        f"TEXT角度短暂沿用 {self._text角度连续沿用次数}/"
                        f"{TEXT角度最大沿用帧数}"
                    )
                    return float(最近角度)
                raise
            self._记录角度诊断(result)
            angle = float(result.angle)
            if getattr(self, "角度模式", None) == "text":
                self._text最近有效角度 = angle
                self._text最近有效角度时间 = time.monotonic()
                self._text角度连续沿用次数 = 0
            return angle
        for 颜色文本, 颜色rgb in self._角度颜色列表:
            mask = self._颜色阈值(图像bgr, 颜色rgb)
            contours, _ = self._cv2.findContours(mask, self._cv2.RETR_EXTERNAL, self._cv2.CHAIN_APPROX_SIMPLE)
            候选 = []
            for contour in contours:
                area = self._cv2.contourArea(contour)
                if area < 角度最小面积:
                    continue
                center = self._优化中心(contour)
                if center is not None:
                    候选.append((area, center))
            if len(候选) < 2:
                continue
            候选.sort(key=lambda item: item[0], reverse=True)
            self.角度诊断颜色 = f"#{颜色文本.strip().lstrip('#').upper()}"
            self.角度诊断origin = 候选[0][1]
            self.角度诊断target = 候选[1][1]
            self.角度诊断mask像素 = int(self._cv2.countNonZero(mask))
            return 计算目标角度(
                候选[0][1][0],
                候选[0][1][1],
                候选[1][1][0],
                候选[1][1][1],
            )
        raise RuntimeError("无法识别当前朝向")

    def _记录角度诊断(self, result) -> None:
        self.角度诊断颜色 = f"#{str(getattr(result, 'color_hex', '--')).strip().lstrip('#').upper()}"
        self.角度诊断origin = getattr(result, "origin", None)
        self.角度诊断target = getattr(result, "target", None)
        mask = getattr(result, "mask", None)
        if mask is None:
            self.角度诊断mask像素 = "--"
            return
        self.角度诊断mask像素 = int(self._cv2.countNonZero(mask))

    def _稳定角度(self, angle: float) -> float:
        最近状态 = getattr(self, "最近状态", None)
        if 最近状态 is None:
            return float(angle)
        上次角度 = float(最近状态[2])
        # text：单帧跳变上限更严，抑制转向中野值
        上限 = 55.0 if 是否增强角度模式() else 最大单帧角度跳变
        if abs(计算最短角度差(上次角度, angle)) > 上限:
            return 上次角度
        return float(angle)

    def _确认角度跳变(self, x: int, y: int, angle: float, 复查函数) -> float:
        self._角度复查诊断 = ""
        最近状态 = getattr(self, "最近状态", None)
        if 最近状态 is None:
            return float(angle)
        上次角度 = float(最近状态[2])
        位移 = 计算距离(int(最近状态[0]), int(最近状态[1]), x, y)
        跳变 = abs(计算最短角度差(上次角度, angle))
        复查阈 = 32.0 if 是否增强角度模式() else 角度跳变复查阈值
        if 位移 > 角度跳变小位移距离 or 跳变 < 复查阈:
            return self._稳定角度(angle)
        复查角度 = float(复查函数())
        复查跳变 = abs(计算最短角度差(上次角度, 复查角度))
        一致阈 = 12.0 if 是否增强角度模式() else 角度跳变复查一致阈值
        if abs(计算最短角度差(angle, 复查角度)) <= 一致阈:
            self._角度复查诊断 = f"角度跳变复查通过 {float(angle):.2f}->{复查角度:.2f}"
            return 复查角度
        if 复查跳变 < 复查阈:
            self._角度复查诊断 = f"角度跳变复查通过 {float(angle):.2f}->{复查角度:.2f}"
            return 复查角度
        self._角度复查诊断 = f"角度跳变复查拒绝 {float(angle):.2f}/{复查角度:.2f}，沿用 {上次角度:.2f}"
        return 上次角度

    def _预处理匹配图像(self, 图像bgr):
        灰度图 = self._cv2.cvtColor(图像bgr, self._cv2.COLOR_BGR2GRAY)
        if hasattr(self._cv2, "createCLAHE"):
            clahe = self._cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            灰度图 = clahe.apply(灰度图)
        return 灰度图

    def _创建小地图特征掩码(self):
        掩码 = self._np.zeros((小地图高度, 小地图宽度), dtype=self._np.uint8)
        圆心 = (小地图宽度 // 2, 小地图高度 // 2)
        半径 = max(10, min(小地图宽度, 小地图高度) // 2 - 小地图特征掩码缩进)
        self._cv2.circle(掩码, 圆心, 半径, 255, -1)
        return 掩码

    def _匹配坐标(
        self,
        查询灰度图,
        目标灰度图,
        *,
        特征掩码=None,
        目标关键点=None,
        目标描述符=None,
        x偏移: int = 0,
        y偏移: int = 0,
    ) -> tuple[int, int] | None:
        查询关键点, 查询描述符 = self._sift.detectAndCompute(查询灰度图, 特征掩码)
        if 查询描述符 is None or len(查询描述符) < 2:
            return None
        if 目标关键点 is None or 目标描述符 is None:
            目标关键点, 目标描述符 = self._sift.detectAndCompute(目标灰度图, None)
        if (
            目标描述符 is None
            or 目标关键点 is None
            or len(目标关键点) < 大地图最小特征数
            or len(目标描述符) < 大地图最小特征数
        ):
            return None
        matches = self._bf.knnMatch(查询描述符, 目标描述符, k=2)
        good = [m[0] for m in matches if len(m) >= 2 and m[0].distance < 0.75 * m[1].distance]
        if len(good) < 10:
            return None
        src = self._np.float32([查询关键点[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
        dst = self._np.float32([目标关键点[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)
        变换矩阵, _ = self._cv2.estimateAffinePartial2D(
            src, dst, method=self._cv2.RANSAC, ransacReprojThreshold=5.0
        )
        if 变换矩阵 is None:
            return None
        缩放 = float(self._np.hypot(变换矩阵[0, 0], 变换矩阵[1, 0]))
        旋转 = abs(math.degrees(math.atan2(变换矩阵[1, 0], 变换矩阵[0, 0])))
        if not (匹配最小缩放 <= 缩放 <= 匹配最大缩放) or 旋转 > 匹配最大旋转角度:
            return None
        中心 = self._np.float32([小地图宽度 // 2, 小地图高度 // 2, 1.0])
        cx = float(变换矩阵[0] @ 中心)
        cy = float(变换矩阵[1] @ 中心)
        return int(cx) + x偏移, int(cy) + y偏移

    def _整图匹配坐标(self, 查询灰度图, 特征掩码) -> tuple[int, int] | None:
        return self._匹配坐标(
            查询灰度图,
            self._大地图匹配灰度,
            特征掩码=特征掩码,
            目标关键点=self._大图关键点,
            目标描述符=self._大图描述符,
        )

    def _局部匹配坐标(self, 查询灰度图, 特征掩码) -> tuple[int, int] | None:
        if self._最近匹配坐标 is None:
            return None
        中心x, 中心y = self._最近匹配坐标
        左 = max(0, 中心x - 局部匹配搜索边距)
        上 = max(0, 中心y - 局部匹配搜索边距)
        右 = min(self._大地图匹配灰度.shape[1], 中心x + 局部匹配搜索边距)
        下 = min(self._大地图匹配灰度.shape[0], 中心y + 局部匹配搜索边距)
        局部地图灰度 = self._大地图匹配灰度[上:下, 左:右]
        if 局部地图灰度.shape[0] < 小地图高度 or 局部地图灰度.shape[1] < 小地图宽度:
            return None
        return self._匹配坐标(
            查询灰度图,
            局部地图灰度,
            特征掩码=特征掩码,
            x偏移=左,
            y偏移=上,
        )

    def _模板匹配坐标(self, 查询灰度图) -> tuple[int, int] | None:
        模板 = self._cv2.resize(
            查询灰度图,
            (int(小地图宽度 * 模板匹配缩放), int(小地图高度 * 模板匹配缩放)),
            interpolation=self._cv2.INTER_CUBIC,
        )
        边距 = int(模板匹配边缘裁剪 * 模板匹配缩放)
        模板 = 模板[边距:模板.shape[0] - 边距, 边距:模板.shape[1] - 边距]
        if (
            模板.shape[0] <= 0
            or 模板.shape[1] <= 0
            or 模板.shape[0] > self._大地图匹配灰度.shape[0]
            or 模板.shape[1] > self._大地图匹配灰度.shape[1]
        ):
            return None
        结果 = self._cv2.matchTemplate(
            self._大地图匹配灰度, 模板, self._cv2.TM_CCOEFF_NORMED
        )
        _, 分数, _, 位置 = self._cv2.minMaxLoc(结果)
        if 分数 < 模板匹配阈值:
            return None
        return (
            int(位置[0] + 模板.shape[1] // 2),
            int(位置[1] + 模板.shape[0] // 2),
        )

    def _识别坐标(self, 小地图图像) -> tuple[int, int]:
        if 小地图图像.shape[:2] != (小地图高度, 小地图宽度):
            小地图图像 = self._cv2.resize(小地图图像, (小地图宽度, 小地图高度))
        if hasattr(self, "_合并识别器"):
            结果 = self._合并识别器.地图匹配器.locate_minimap(小地图图像)
            if not 结果["success"]:
                self._保存定位诊断(小地图图像)
                raise RuntimeError("无法识别当前位置")
            匹配坐标 = (int(结果["x"]), int(结果["y"]))
            self._最近匹配坐标 = 匹配坐标
            return 匹配坐标
        查询灰度图 = self._预处理匹配图像(小地图图像)
        特征掩码 = self._创建小地图特征掩码()
        匹配坐标 = None
        if self._最近匹配坐标 is not None:
            匹配坐标 = self._局部匹配坐标(查询灰度图, 特征掩码)
        if 匹配坐标 is None:
            匹配坐标 = self._整图匹配坐标(查询灰度图, 特征掩码)
        if 匹配坐标 is None:
            匹配坐标 = self._模板匹配坐标(查询灰度图)
        if 匹配坐标 is None:
            self._保存定位诊断(小地图图像)
            raise RuntimeError("无法识别当前位置")
        self._最近匹配坐标 = 匹配坐标
        return 匹配坐标

    def _保存定位诊断(self, 小地图图像):
        now = time.time()
        if now - getattr(self, "_定位诊断时间", 0.0) < 定位诊断最小间隔:
            return
        try:
            定位诊断目录.mkdir(parents=True, exist_ok=True)
            if len(list(定位诊断目录.glob("*.png"))) >= 定位诊断上限:
                return
            success, encoded = self._cv2.imencode(".png", 小地图图像)
            if not success:
                return
            名称 = "{}_{:03d}_小地图.png".format(
                time.strftime("%Y%m%d_%H%M%S", time.localtime(now)),
                int(now * 1000) % 1000,
            )
            encoded.tofile(str(定位诊断目录 / 名称))
            self._定位诊断时间 = now
        except Exception:
            pass

    def 读取状态(self) -> tuple[int, int, float]:
        with self._读取锁:
            return self._读取状态_无锁()

    def _读取状态_无锁(self) -> tuple[int, int, float]:
        self._角度复查诊断 = ""
        设置识别诊断状态(self, "识别坐标中")
        小地图图像, 角度图像 = self._截图小地图与角度()
        x, y = self._识别坐标(小地图图像)
        设置识别诊断状态(self, "识别角度中")
        angle = self._确认角度跳变(
            x,
            y,
            self._识别角度(角度图像),
            lambda: self._识别角度(self._截图区域(self.角度截图区域)),
        )
        self.最近状态 = (x, y, angle)
        设置识别诊断状态(self, self._角度复查诊断 or "识别完成")
        return self.最近状态

    def _截图小地图与角度(self):
        地图区 = tuple(int(v) for v in self.小地图截图区域)
        角度区 = tuple(int(v) for v in self.角度截图区域)
        角度模块 = getattr(合并识别模块, "角度模块", None)
        if 角度模块 is not None and hasattr(角度模块, "grab_regions_bgr"):
            crops = 角度模块.grab_regions_bgr(地图区, 角度区)
            小地图 = crops.get(地图区)
            角度图 = crops.get(角度区)
            if 小地图 is not None and 角度图 is not None:
                return 小地图, 角度图
        return self._截图区域(地图区), self._截图区域(角度区)

    def _截图区域(self, 区域: tuple[int, int, int, int]):
        角度模块 = getattr(合并识别模块, "角度模块", None)
        if 角度模块 is not None and hasattr(角度模块, "grab_bbox_bgr"):
            图像, _ = 角度模块.grab_bbox_bgr(区域)
            return 图像
        try:
            import 截图模块 as _cap
            图像 = _cap.grab_region(区域[0], 区域[1], 区域[2], 区域[3])
            if 图像 is not None:
                return 图像
        except Exception:
            pass
        截图 = self._ImageGrab.grab(bbox=区域)
        return self._cv2.cvtColor(self._np.array(截图), self._cv2.COLOR_RGB2BGR)

    def 从全屏图像读取状态(self, 全屏图像) -> tuple[int, int, float]:
        self._角度复查诊断 = ""
        x1, y1, x2, y2 = getattr(self, "小地图截图区域", 小地图区域)
        a1, b1, a2, b2 = getattr(self, "角度截图区域", 角度区域)
        设置识别诊断状态(self, "识别坐标中")
        x, y = self._识别坐标(全屏图像[y1:y2, x1:x2])
        设置识别诊断状态(self, "识别角度中")
        角度图像 = 全屏图像[b1:b2, a1:a2]
        angle = self._确认角度跳变(x, y, self._识别角度(角度图像), lambda: self._识别角度(角度图像))
        self.最近状态 = (x, y, angle)
        设置识别诊断状态(self, self._角度复查诊断 or "识别完成")
        return self.最近状态

    def 生成预览图(self, 状态: tuple[int, int, float] | None = None):
        return 绘制定位预览图(self.大地图, 状态 or self.最近状态)


class 寻路记录器:
    def __init__(self, 输出目录: Path = 寻路诊断目录, 时间戳: str | None = None):
        时间戳 = 时间戳 or time.strftime("%Y%m%d_%H%M%S")
        self.目录 = Path(输出目录) / 时间戳
        序号 = 1
        while self.目录.exists():
            self.目录 = Path(输出目录) / f"{时间戳}_{序号}"
            序号 += 1
        self._记录路径 = self.目录 / "steps.jsonl"
        self._截图数量 = 0
        self._已就绪 = False

    def _确保目录(self) -> None:
        if not self._已就绪:
            self.目录.mkdir(parents=True, exist_ok=True)
            self._已就绪 = True

    def 记录(self, **字段) -> None:
        try:
            self._确保目录()
            字段.setdefault("时间", time.strftime("%Y-%m-%d %H:%M:%S"))
            with self._记录路径.open("a", encoding="utf-8") as 文件:
                文件.write(json.dumps(字段, ensure_ascii=False, default=str) + "\n")
        except Exception:
            pass

    def 保存事件截图(self, 事件: str) -> None:
        if self._截图数量 >= 寻路诊断截图上限:
            return
        try:
            import cv2

            self._确保目录()
            图像 = None
            try:
                import 截图模块 as _cap
                图像 = _cap.grab_fullscreen()
            except Exception:
                图像 = None
            if 图像 is None:
                from PIL import ImageGrab
                import numpy as np

                图像 = cv2.cvtColor(np.array(ImageGrab.grab()), cv2.COLOR_RGB2BGR)
            名称 = "{}_{:03d}_{}.png".format(
                time.strftime("%Y%m%d_%H%M%S"),
                int(time.time() * 1000) % 1000,
                事件,
            )
            success, encoded = cv2.imencode(".png", 图像)
            if success:
                encoded.tofile(str(self.目录 / 名称))
                self._截图数量 += 1
        except Exception:
            pass


class 巡航控制器:
    def __init__(
        self,
        *,
        路径点列表: list[路径点],
        定位器,
        执行器,
        到点阈值: int,
        参数: 模式参数,
        终点对正: bool = False,
        循环间隔: float = 0.05,
        日志函数=None,
        停止事件: threading.Event | None = None,
        记录器: 寻路记录器 | None = None,
    ):
        if not 路径点列表:
            raise ValueError("路径点列表不能为空")
        校验到点阈值(到点阈值)
        self.路径点列表 = 路径点列表
        self.定位器 = 定位器
        self.执行器 = 执行器
        self.到点阈值 = 到点阈值
        self.参数 = 参数
        self.终点对正 = 终点对正
        self.循环间隔 = 循环间隔
        self.日志函数 = 日志函数
        self.停止事件 = 停止事件
        self.记录器 = 记录器
        self._最近成功状态: tuple[int, int, float] | None = None
        self._待处理状态: tuple[int, int, float] | None = None
        self._连续沿用次数 = 0
        self._上次移动参考坐标: tuple[int, int] | None = None
        self._上次移动时间: float | None = None
        self._上次推进参考距离: int | None = None
        self._上次推进时间: float | None = None
        self._上次推进路径索引: int | None = None
        self._上次脱困时间: float | None = None
        self._脱困次数 = 0
        self._上次状态时间: float | None = None
        self._坐标跳变已拒绝 = False
        self._连续转向次数 = 0
        self._上次转向角差: float | None = None
        self._上次转向路径索引: int | None = None
        self._上次转向坐标: tuple[int, int] | None = None
        self._转向不收敛触发 = False
        self._近点位保护触发 = False
        设置控制诊断状态(self.定位器, "待机")

    def _检查紧急停止(self) -> None:
        if 处理esc紧急停止(getattr(self, "停止事件", None)):
            raise 紧急停止异常("检测到 ESC，已停止巡航")

    def _等待并检查停止(self, 秒数: float) -> None:
        if 秒数 <= 0:
            self._检查紧急停止()
            return
        if getattr(self, "停止事件", None) is None:
            self._检查紧急停止()
            time.sleep(秒数)
            self._检查紧急停止()
            return
        结束时间 = time.monotonic() + 秒数
        while True:
            self._检查紧急停止()
            剩余秒数 = 结束时间 - time.monotonic()
            if 剩余秒数 <= 0:
                return
            time.sleep(min(0.05, 剩余秒数))

    def _读取状态_带重试(self) -> tuple[int, int, float]:
        if self._待处理状态 is not None:
            状态 = self._待处理状态
            self._待处理状态 = None
            self._最近成功状态 = 状态
            self._连续沿用次数 = 0
            return 状态
        最大重试次数 = 首次状态读取最大重试次数 if self._最近成功状态 is None else 状态读取最大重试次数
        最后异常: RuntimeError | None = None
        刷新次数 = 0
        for 尝试次数 in range(最大重试次数):
            self._检查紧急停止()
            try:
                状态 = self.定位器.读取状态()
                当前时间 = time.monotonic()
                if (
                    not self._坐标跳变已拒绝
                    and self._最近成功状态 is not None
                    and self._上次状态时间 is not None
                    and 当前时间 - self._上次状态时间 <= 坐标跳变判定秒数
                    and 计算距离(
                        self._最近成功状态[0], self._最近成功状态[1], 状态[0], 状态[1]
                    ) > 坐标跳变判定距离
                ):
                    self._坐标跳变已拒绝 = True
                    设置识别诊断状态(self.定位器, "坐标跳变，复查中")
                    写日志(
                        self.日志函数,
                        "event=coord_jump",
                        原坐标=f"{self._最近成功状态[0]},{self._最近成功状态[1]}",
                        新坐标=f"{状态[0]},{状态[1]}",
                    )
                    if 状态读取重试间隔 > 0:
                        self._等待并检查停止(状态读取重试间隔)
                    continue
                self._坐标跳变已拒绝 = False
                self._上次状态时间 = 当前时间
                self._最近成功状态 = 状态
                self._连续沿用次数 = 0
                return 状态
            except RuntimeError as exc:
                if not any(错误 in str(exc) for 错误 in 可重试识别错误):
                    raise
                最后异常 = exc
                if self._需要刷新视角(exc) and 刷新次数 < 角度识别刷新最大次数:
                    self.执行器.执行(self._生成刷新视角动作())
                    刷新次数 += 1
                    设置控制诊断状态(
                        self.定位器,
                        f"角度识别失败，刷新视角重试 {刷新次数}/{角度识别刷新最大次数}",
                    )
                    写日志(
                        self.日志函数,
                        "event=retry",
                        刷新次数=f"{刷新次数}/{角度识别刷新最大次数}",
                        控制诊断=getattr(self.定位器, "控制诊断状态", ""),
                        识别异常=str(exc),
                    )
                    if 刷新视角后等待秒数 > 0:
                        self._等待并检查停止(刷新视角后等待秒数)
                if 尝试次数 >= 最大重试次数 - 1:
                    break
                if 状态读取重试间隔 > 0:
                    self._等待并检查停止(状态读取重试间隔)
        if self._最近成功状态 is not None and self._连续沿用次数 < 最近状态最大沿用次数:
            self._连续沿用次数 += 1
            设置识别诊断状态(self.定位器, f"沿用最近成功状态 {self._连续沿用次数}/{最近状态最大沿用次数}")
            写日志(
                self.日志函数,
                "event=state_reuse",
                次数=f"{self._连续沿用次数}/{最近状态最大沿用次数}",
                坐标=f"{self._最近成功状态[0]},{self._最近成功状态[1]}",
                角度=f"{self._最近成功状态[2]:.2f}",
            )
            return self._最近成功状态
        if 最后异常 is not None:
            raise 最后异常
        raise RuntimeError("无法读取当前状态")

    def _终点对正动作(self, 当前角度: float, 终点: 路径点) -> 动作指令:
        角度差 = 计算最短角度差(当前角度, 终点.angle)
        return 动作指令("终点对正", 鼠标像素=角度差转鼠标像素(计算自适应转向角度(角度差)))

    def _检测卡住(self, x: int, y: int, 距离: int, 路径索引: int) -> tuple[bool, float]:
        当前时间 = time.monotonic()
        当前坐标 = (x, y)
        if (
            self._上次移动参考坐标 is None
            or self._上次移动时间 is None
            or self._上次推进参考距离 is None
            or self._上次推进时间 is None
            or self._上次推进路径索引 != 路径索引
        ):
            self._上次移动参考坐标 = 当前坐标
            self._上次移动时间 = 当前时间
            self._上次推进参考距离 = 距离
            self._上次推进时间 = 当前时间
            self._上次推进路径索引 = 路径索引
            return False, 当前时间
        if 计算距离(*self._上次移动参考坐标, x, y) > 卡住判定距离:
            self._上次移动参考坐标 = 当前坐标
            self._上次移动时间 = 当前时间
            self._脱困次数 = 0
        if 距离 < self._上次推进参考距离 - 卡住判定距离:
            self._上次推进参考距离 = 距离
            self._上次推进时间 = 当前时间
        if (
            当前时间 - self._上次移动时间 < 卡住检测秒数
            and 当前时间 - self._上次推进时间 < 卡住检测秒数
        ):
            return False, 当前时间
        if self._上次脱困时间 is not None and 当前时间 - self._上次脱困时间 < 脱困冷却秒数:
            return False, 当前时间
        return True, 当前时间

    def _重置卡住计时(self) -> None:
        当前时间 = time.monotonic()
        if self._上次移动时间 is not None:
            self._上次移动时间 = 当前时间
        if self._上次推进时间 is not None:
            self._上次推进时间 = 当前时间

    def _生成脱困动作(self) -> 动作指令:
        序号 = self._脱困次数
        self._脱困次数 += 1
        角度 = 脱困转向序列[序号 % len(脱困转向序列)]
        类型 = "脱困" if (序号 + 1) % len(脱困转向序列) == 0 else "绕行脱困"
        return 动作指令(类型, 鼠标像素=角度差转鼠标像素(角度), 持续时间=脱困前进秒数)

    def _需要刷新视角(self, exc: RuntimeError) -> bool:
        return any(错误 in str(exc) for 错误 in 角度颜色识别错误)

    def _生成刷新视角动作(self) -> 动作指令:
        角度差 = random.choice((-1.0, 1.0)) * random.uniform(角度刷新最小角度, 角度刷新最大角度)
        return 动作指令("刷新视角", 鼠标像素=角度差转鼠标像素(角度差))

    def _转向后确认状态(
        self,
        当前状态: tuple[int, int, float],
        当前点: 路径点,
        原角度差: float,
        动作: 动作指令,
    ) -> None:
        if 是否增强角度模式() or getattr(self.执行器, "_连续视角控制器", None) is not None:
            return
        if 动作.类型 not in {"转向", "终点对正"}:
            return
        起始角度 = float(当前状态[2])
        最新状态 = 当前状态
        最新可信状态 = None
        最新角度差 = 原角度差
        最新可信角度差 = 原角度差
        收敛阈值 = max(0.0, abs(原角度差) - 转向后最小收敛角差)
        是否收敛 = False
        拒绝原因 = ""

        超时 = 转向后确认超时秒数
        最小变化 = 转向后最小角度变化
        变差阈值 = 转向后异常变差角度
        截止时间 = time.monotonic() + 超时
        while True:
            if 转向后确认轮询间隔 > 0:
                self._等待并检查停止(转向后确认轮询间隔)
            最新状态 = self._读取状态_带重试()
            最新目标角度 = 计算目标角度(最新状态[0], 最新状态[1], 当前点.x, 当前点.y)
            最新角度差 = 计算最短角度差(最新状态[2], 最新目标角度)
            角度变化 = abs(计算最短角度差(起始角度, 最新状态[2]))
            if abs(最新角度差) > abs(原角度差) + 变差阈值:
                拒绝原因 = f"转向后角差变大 {原角度差:.2f}->{最新角度差:.2f}"
            else:
                最新可信状态 = 最新状态
                最新可信角度差 = 最新角度差
                拒绝原因 = ""
            if abs(最新角度差) <= 收敛阈值 and 角度变化 >= 最小变化:
                是否收敛 = True
                break
            if time.monotonic() >= 截止时间:
                break

        if 最新可信状态 is not None:
            self._待处理状态 = 最新可信状态
        回写状态 = 最新可信状态 or 当前状态
        if 最新可信状态 is not None:
            实际角度变化 = 计算最短角度差(起始角度, 最新可信状态[2])
            预期角度变化 = (动作.鼠标像素 or 0) / 当前每度像素()
            if (
                abs(预期角度变化) >= 标定最小角度变化
                and 标定样本最小比例 * abs(预期角度变化)
                <= abs(实际角度变化)
                <= 标定样本最大比例 * abs(预期角度变化)
            ):
                更新每度像素校准(动作.鼠标像素 or 0, 实际角度变化)
        self._最近成功状态 = 回写状态
        try:
            self.定位器.最近状态 = 回写状态
        except Exception:
            pass
        写日志(
            self.日志函数,
            "event=turn_wait",
            起始角度=f"{起始角度:.2f}",
            最新角度=f"{最新状态[2]:.2f}",
            角度变化=f"{计算最短角度差(起始角度, 最新状态[2]):.2f}",
            起始角度差=f"{原角度差:.2f}",
            最新角度差=f"{最新角度差:.2f}",
            缓存角度差=f"{最新可信角度差:.2f}" if 最新可信状态 is not None else "--",
            是否收敛="是" if 是否收敛 else "否",
            是否采信="是" if 最新可信状态 is not None else "否",
            校准每度像素=f"{当前每度像素():.2f}",
            拒绝原因=拒绝原因 or "--",
            动作=动作.类型,
            **角度诊断日志字段(self.定位器),
            **模式诊断日志字段(self.定位器),
        )

    def _处理近点位转向(self, *, 距离: int, 角度差: float, 动作: 动作指令) -> 动作指令:
        self._近点位保护触发 = False
        if 动作.类型 == "转向":
            近点位距离 = 增强近点位保护距离 if 是否增强角度模式() else self.到点阈值 + 近点位转向保护增量
            self._近点位保护触发 = 距离 <= 近点位距离
            return 动作
        if 是否增强角度模式() and 距离 <= 增强近点位保护距离:
            if not 动作.鼠标像素 and abs(角度差) <= self.参数.小角度阈值:
                return 动作
            self._近点位保护触发 = True
            微调角度 = max(-增强近点位最大微调角度, min(增强近点位最大微调角度, 角度差))
            return 动作指令("前进并微调", 鼠标像素=text微调鼠标像素(微调角度, self.参数.精准缩放))
        return 动作

    def _处理转向不收敛(
        self,
        *,
        当前索引: int,
        当前坐标: tuple[int, int],
        距离: int,
        角度差: float,
        动作: 动作指令,
    ) -> 动作指令:
        if 动作.类型 != "转向":
            self._连续转向次数 = 0
            self._上次转向角差 = None
            self._上次转向路径索引 = None
            self._上次转向坐标 = None
            self._转向不收敛触发 = False
            return 动作
        if self._近点位保护触发:
            self._连续转向次数 = 0
            self._上次转向角差 = None
            self._上次转向路径索引 = None
            self._上次转向坐标 = None
            self._转向不收敛触发 = False
            return 动作
        同一路径 = self._上次转向路径索引 == 当前索引
        原地转向 = self._上次转向坐标 is not None and 计算距离(*self._上次转向坐标, *当前坐标) <= 转向不收敛原地距离
        方向翻转 = (
            同一路径
            and 原地转向
            and self._上次转向角差 is not None
            and 角度差 * self._上次转向角差 < 0
            and abs(角度差) >= self.参数.大角度阈值
        )
        未明显改善 = 方向翻转 or (
            self._上次转向角差 is not None and abs(self._上次转向角差) - abs(角度差) < 转向收敛最小改善角度
        )
        self._连续转向次数 = self._连续转向次数 + 1 if 同一路径 and 原地转向 and 未明显改善 and 距离 > self.到点阈值 else 1
        self._上次转向角差 = 角度差
        self._上次转向路径索引 = 当前索引
        self._上次转向坐标 = 当前坐标
        self._转向不收敛触发 = False
        if self._连续转向次数 < 转向不收敛判定次数:
            if 方向翻转:
                return 动作指令(
                    "转向",
                    鼠标像素=角度差转鼠标像素(
                        计算自适应转向角度(角度差) * 振荡转向抑制比例 * self.参数.精准缩放
                    ),
                )
            return 动作
        self._连续转向次数 = 0
        self._上次转向角差 = None
        self._上次转向路径索引 = None
        self._上次转向坐标 = None
        self._转向不收敛触发 = True
        微调角度 = max(-转向不收敛微调角度, min(转向不收敛微调角度, 角度差))
        return 动作指令("前进并微调", 鼠标像素=角度差转鼠标像素(微调角度 * self.参数.精准缩放))

    def _执行终点对正(self, 终点: 路径点, 当前角度: float) -> None:
        已尝试次数 = 0
        while 已尝试次数 < 终点对正最大尝试次数:
            设置控制诊断状态(self.定位器, "终点对正中")
            setattr(self.定位器, "最近动作类型", "终点对正")
            角度差 = 计算最短角度差(当前角度, 终点.angle)
            if abs(角度差) <= 终点对正角度阈值:
                return
            self.执行器.执行(self._终点对正动作(当前角度, 终点))
            写日志(
                self.日志函数,
                "event=align",
                目标=f"({终点.x}, {终点.y})",
                目标角度=f"{终点.angle:.2f}",
                当前角度=f"{当前角度:.2f}",
                角度差=f"{角度差:.2f}",
                动作="终点对正",
            )
            已尝试次数 += 1
            if self.循环间隔 > 0:
                self._等待并检查停止(self.循环间隔)
            _, _, 当前角度 = self._读取状态_带重试()

    def 运行(self, 最大步数: int | None = None) -> None:
        当前索引 = 0
        步数 = 0
        try:
            while 当前索引 < len(self.路径点列表):
                self._检查紧急停止()
                if 最大步数 is not None and 步数 >= 最大步数:
                    raise RuntimeError("巡航超过最大步数，疑似未收敛")
                步数 += 1
                当前点 = self.路径点列表[当前索引]
                x, y, 当前角度 = self._读取状态_带重试()
                取出连续输出 = getattr(self.执行器, "取出连续输出像素", None)
                if callable(取出连续输出):
                    实际像素 = 取出连续输出()
                    if 实际像素 is not None:
                        setattr(self.定位器, "连续控制实际像素", int(实际像素))
                距离 = 计算距离(x, y, 当前点.x, 当前点.y)
                是否卡住, 当前时间 = self._检测卡住(x, y, 距离, 当前索引)
                setattr(self.定位器, "当前目标点详情", f"{当前索引 + 1}/{len(self.路径点列表)} -> ({当前点.x}, {当前点.y})")
                if 距离 <= self.到点阈值:
                    if 当前索引 == len(self.路径点列表) - 1:
                        if self.终点对正:
                            self._执行终点对正(当前点, 当前角度)
                        break
                    自动路线 = getattr(当前点, "自动路线", False)
                    切点动作 = "自动路线切换下一个点" if 自动路线 else "切换下一个点"
                    设置控制诊断状态(self.定位器, "已到点，切换下一个点")
                    setattr(self.定位器, "最近动作类型", 切点动作)
                    写日志(
                        self.日志函数,
                        "event=step",
                        坐标=f"{x},{y}",
                        当前角度=f"{当前角度:.2f}",
                        目标=getattr(self.定位器, "当前目标点详情", "--"),
                        目标角度="--",
                        角度差="--",
                        动作=切点动作,
                        控制诊断=getattr(self.定位器, "控制诊断状态", ""),
                        识别诊断=getattr(self.定位器, "识别诊断状态", ""),
                        **角度诊断日志字段(self.定位器),
                        **模式诊断日志字段(self.定位器),
                    )
                    if self.记录器 is not None:
                        self.记录器.记录(
                            坐标=f"{x},{y}", 角度=round(当前角度, 2), 索引=当前索引,
                            目标=f"{当前点.x},{当前点.y}", 距离=距离, 动作=切点动作,
                            **模式诊断日志字段(self.定位器),
                        )
                    self.执行器.执行(动作指令(切点动作))
                    当前索引 += 1
                    continue
                if 是否卡住:
                    脱困动作 = self._生成脱困动作()
                    设置控制诊断状态(self.定位器, "脱困中")
                    setattr(self.定位器, "最近动作类型", 脱困动作.类型)
                    写日志(
                        self.日志函数,
                        "event=step",
                        坐标=f"{x},{y}",
                        当前角度=f"{当前角度:.2f}",
                        目标=getattr(self.定位器, "当前目标点详情", "--"),
                        目标角度=getattr(self.定位器, "当前目标角度", "--"),
                        角度差=getattr(self.定位器, "当前角度差", "--"),
                        动作=脱困动作.类型,
                        控制诊断=getattr(self.定位器, "控制诊断状态", ""),
                        识别诊断=getattr(self.定位器, "识别诊断状态", ""),
                        **角度诊断日志字段(self.定位器),
                        **模式诊断日志字段(self.定位器),
                    )
                    if self.记录器 is not None:
                        self.记录器.记录(
                            坐标=f"{x},{y}", 角度=round(当前角度, 2), 索引=当前索引,
                            目标=f"{当前点.x},{当前点.y}", 距离=距离, 动作=脱困动作.类型,
                            鼠标像素=脱困动作.鼠标像素,
                            识别诊断=getattr(self.定位器, "识别诊断状态", ""),
                            **模式诊断日志字段(self.定位器),
                        )
                        self.记录器.保存事件截图("脱困")
                    self.执行器.执行(脱困动作)
                    self._上次脱困时间 = 当前时间
                    continue
                目标角度 = 计算目标角度(x, y, 当前点.x, 当前点.y)
                角度差 = 计算最短角度差(当前角度, 目标角度)
                setattr(self.定位器, "当前目标角度", 目标角度)
                setattr(self.定位器, "当前角度差", 角度差)
                自动路线 = getattr(当前点, "自动路线", False)
                动作 = 选择动作(
                    距离=距离,
                    角度差=角度差,
                    到点阈值=self.到点阈值,
                    参数=self.参数,
                    自动路线=自动路线,
                )
                动作 = self._处理近点位转向(
                    距离=距离,
                    角度差=角度差,
                    动作=动作,
                )
                动作 = self._处理转向不收敛(
                    当前索引=当前索引,
                    当前坐标=(x, y),
                    距离=距离,
                    角度差=角度差,
                    动作=动作,
                )
                if 动作.类型 == "转向":
                    设置控制诊断状态(self.定位器, "大角差转向中")
                elif 动作.类型 == "终点对正":
                    设置控制诊断状态(self.定位器, "终点对正中")
                elif 动作.类型 == "刷新视角":
                    设置控制诊断状态(self.定位器, "角度识别失败，刷新视角中")
                elif 动作.类型 == "脱困":
                    设置控制诊断状态(self.定位器, "脱困中")
                elif 动作.类型 in {"疾跑前进", "前进"}:
                    设置控制诊断状态(self.定位器, "前进中")
                elif 动作.类型 in {"疾跑前进并微调", "前进并微调"}:
                    if self._近点位保护触发:
                        设置控制诊断状态(self.定位器, "近点位，尝试前进微调")
                    else:
                        设置控制诊断状态(self.定位器, "转向不收敛，尝试前进微调" if self._转向不收敛触发 else "前进中，角度微调")
                setattr(self.定位器, "最近动作类型", 动作.类型)
                写日志(
                    self.日志函数,
                    "event=step",
                    坐标=f"{x},{y}",
                    当前角度=f"{当前角度:.2f}",
                    目标=getattr(self.定位器, "当前目标点详情", "--"),
                    目标角度=f"{目标角度:.2f}",
                    角度差=f"{角度差:.2f}",
                    动作=动作.类型,
                    控制诊断=getattr(self.定位器, "控制诊断状态", ""),
                    识别诊断=getattr(self.定位器, "识别诊断状态", ""),
                    **角度诊断日志字段(self.定位器),
                    **模式诊断日志字段(self.定位器),
                )
                if self.记录器 is not None:
                    self.记录器.记录(
                        坐标=f"{x},{y}",
                        角度=round(当前角度, 2),
                        索引=当前索引,
                        目标=f"{当前点.x},{当前点.y}",
                        距离=距离,
                        目标角度=round(目标角度, 2),
                        角度差=round(角度差, 2),
                        动作=动作.类型,
                        鼠标像素=动作.鼠标像素,
                        连续转向=self._连续转向次数,
                        控制诊断=getattr(self.定位器, "控制诊断状态", ""),
                        识别诊断=getattr(self.定位器, "识别诊断状态", ""),
                        **模式诊断日志字段(self.定位器),
                    )
                    if self._转向不收敛触发:
                        self.记录器.保存事件截图("转向不收敛")
                    elif 动作.类型 == "转向" and self._连续转向次数 >= 3:
                        self.记录器.保存事件截图("连续转向")
                self.执行器.执行(动作)
                self._转向后确认状态((x, y, 当前角度), 当前点, 角度差, 动作)
                if 动作.类型 in 转向类动作:
                    self._重置卡住计时()
                if self._转向不收敛触发:
                    self._转向不收敛触发 = False
                if self._近点位保护触发:
                    self._近点位保护触发 = False
                if self.循环间隔 > 0:
                    self._等待并检查停止(self.循环间隔)
        finally:
            self.执行器.停止()


def 巡航(
    路径文件: str,
    到点阈值: int = 默认到点阈值,
    精准模式: bool = 默认精准模式,
    终点对正: bool = 默认终点对正,
    定位器=None,
    日志函数=None,
    停止事件: threading.Event | None = None,
    视角速度倍率=默认视角速度倍率,
) -> None:
    校验到点阈值(到点阈值)
    视角速度倍率 = 规范化视角速度倍率(视角速度倍率)
    路径点列表 = 读取路径(路径文件, 自动路线点距=当前模式自动路线点距())
    # 按当前角度模式取参（text 已提高大角差阈值）
    if 是否增强角度模式():
        重置每度像素校准(TEXT_每度像素)
    参数 = 精准模式参数() if 精准模式 else 普通模式参数()
    try:
        记录器 = 寻路记录器()
    except Exception:
        记录器 = None
    执行器参数 = {"视角速度倍率": 视角速度倍率}
    if 停止事件 is not None:
        执行器参数["停止事件"] = 停止事件
    控制器 = 巡航控制器(
        路径点列表=路径点列表,
        定位器=定位器 or 实时定位器(),
        执行器=Win32执行器(**执行器参数),
        到点阈值=到点阈值,
        参数=参数,
        终点对正=终点对正,
        日志函数=日志函数,
        停止事件=停止事件,
        记录器=记录器,
    )
    控制器.运行()


def 后台执行巡航(
    路径文件: str,
    *,
    巡航函数=巡航,
    延迟秒数: int = 默认启动延迟秒数,
    定位器=None,
    日志函数=None,
    停止事件: threading.Event | None = None,
) -> None:
    路径文件 = 校验路线文件(路径文件)
    if 延迟秒数 > 0:
        结束时间 = time.monotonic() + 延迟秒数
        while time.monotonic() < 结束时间:
            if 处理esc紧急停止(停止事件):
                raise 紧急停止异常("检测到 ESC，已停止巡航")
            time.sleep(min(0.05, max(0.0, 结束时间 - time.monotonic())))
    参数 = 巡航默认参数()
    巡航参数 = {
        "到点阈值": 参数["到点阈值"],
        "精准模式": 参数["精准模式"],
        "终点对正": 参数["终点对正"],
    }
    if 定位器 is not None:
        巡航参数["定位器"] = 定位器
    if 停止事件 is not None:
        巡航参数["停止事件"] = 停止事件
    if 巡航函数 is 巡航:
        _, 默认日志函数 = 创建日志记录器("巡航工具")
        巡航参数["日志函数"] = 日志函数 or 默认日志函数
    巡航函数(路径文件, **巡航参数)


class Win32执行器:
    def __init__(
        self,
        输入模块=win32_input,
        停止事件: threading.Event | None = None,
        *,
        视角速度倍率=默认视角速度倍率,
        连续控制器工厂=连续视角控制器,
    ):
        self.输入模块 = 输入模块
        self.停止事件 = 停止事件
        self.视角速度倍率 = 规范化视角速度倍率(视角速度倍率)
        self._连续视角控制器 = 连续控制器工厂(
            输入模块, 视角速度倍率=self.视角速度倍率
        )
        self._正在前进 = False
        self._本段已疾跑 = False

    def _更新视角(self, 鼠标像素: int | None) -> None:
        角度差 = float(鼠标像素 or 0) / 当前每度像素()
        self._连续视角控制器.更新角度差(角度差)

    def _停止前进(self) -> None:
        if self._正在前进 or self._本段已疾跑:
            self.输入模块.释放移动键()
        self._正在前进 = False
        self._本段已疾跑 = False

    def 取出连续输出像素(self) -> int | None:
        取出输出 = getattr(self._连续视角控制器, "取出输出像素", None)
        return int(取出输出()) if callable(取出输出) else None

    def _检查紧急停止(self) -> None:
        if 处理esc紧急停止(getattr(self, "停止事件", None)):
            raise 紧急停止异常("检测到 ESC，已停止巡航")

    def _等待并检查停止(self, 秒数: float) -> None:
        if 秒数 <= 0:
            self._检查紧急停止()
            return
        if getattr(self, "停止事件", None) is None:
            self._检查紧急停止()
            time.sleep(秒数)
            self._检查紧急停止()
            return
        结束时间 = time.monotonic() + 秒数
        while True:
            self._检查紧急停止()
            剩余秒数 = 结束时间 - time.monotonic()
            if 剩余秒数 <= 0:
                return
            time.sleep(min(0.05, 剩余秒数))

    def 执行(self, 动作: 动作指令) -> None:
        self._检查紧急停止()
        if 动作.类型 in {"转向", "终点对正", "刷新视角"}:
            self._停止前进()
            self._更新视角(动作.鼠标像素)
            return
        if 动作.类型 in {"脱困", "绕行脱困"}:
            self._停止前进()
            self._更新视角(动作.鼠标像素)
            self.输入模块.键盘按下("w")
            self._正在前进 = True
            if 动作.类型 == "脱困":
                self.输入模块.键盘单击("space")
            if 动作.持续时间 > 0:
                self._等待并检查停止(动作.持续时间)
            self._停止前进()
            return
        if 动作.类型 in {"疾跑前进", "疾跑前进并微调"}:
            if not self._正在前进:
                self.输入模块.键盘按下("w")
                self._正在前进 = True
            if not self._本段已疾跑:
                self.输入模块.点按shift()
                self._本段已疾跑 = True
            self._更新视角(动作.鼠标像素)
            return
        if 动作.类型 in {"前进", "前进并微调"}:
            if not self._正在前进:
                self.输入模块.键盘按下("w")
                self._正在前进 = True
            self._更新视角(动作.鼠标像素)
            return
        if 动作.类型 == "切换下一个点":
            self._更新视角(0)
            self._停止前进()
            return
        if 动作.类型 == "自动路线切换下一个点":
            self._更新视角(0)
            return
        raise ValueError(f"不支持的动作: {动作.类型}")

    def 停止(self) -> None:
        self._连续视角控制器.停止()
        self._停止前进()


def 格式化识别状态文本(
    状态: tuple[int, int, float] | None = None,
    错误: str | None = None,
    最近状态: tuple[int, int, float] | None = None,
) -> str:
    if 错误:
        if 最近状态 is not None:
            x, y, angle = 最近状态
            return f"坐标: ({x}, {y}) | 角度: {angle:.2f} | 识别失败: {错误}"
        return f"坐标: -- | 角度: -- | 识别失败: {错误}"
    if 状态 is None:
        return "坐标: -- | 角度: --"
    x, y, angle = 状态
    return f"坐标: ({x}, {y}) | 角度: {angle:.2f}"


def 刷新识别状态(
    *,
    根窗口,
    识别状态变量,
    诊断状态变量=None,
    控制详情变量=None,
    定位器,
    预览更新函数=None,
    刷新间隔毫秒: int = 500,
    暂停判定=None,
) -> None:
    """定时刷新。暂停判定为 True 时只显示缓存，不抢控制环截图。"""
    暂停 = False
    try:
        if 暂停判定 is not None:
            暂停 = bool(暂停判定())
    except Exception:
        暂停 = False

    if not 暂停:
        try:
            状态 = 定位器.读取状态()
            识别状态变量.set(格式化识别状态文本(状态))
            if 诊断状态变量 is not None:
                诊断状态变量.set(格式化诊断状态文本(定位器))
            if 控制详情变量 is not None:
                控制详情变量.set(格式化控制详情文本(定位器))
            if 预览更新函数 is not None:
                预览更新函数(定位器.生成预览图(状态))
        except Exception as exc:
            识别状态变量.set(
                格式化识别状态文本(错误=str(exc), 最近状态=getattr(定位器, "最近状态", None))
            )
            if 诊断状态变量 is not None:
                诊断状态变量.set(格式化诊断状态文本(定位器))
            if 控制详情变量 is not None:
                控制详情变量.set(格式化控制详情文本(定位器))
    else:
        最近 = getattr(定位器, "最近状态", None)
        if 最近 is not None:
            识别状态变量.set(格式化识别状态文本(最近) + " | 寻路中(缓存)")
            if 诊断状态变量 is not None:
                诊断状态变量.set(格式化诊断状态文本(定位器))
            if 控制详情变量 is not None:
                控制详情变量.set(格式化控制详情文本(定位器))
            if 预览更新函数 is not None:
                try:
                    预览更新函数(定位器.生成预览图(最近))
                except Exception:
                    pass

    根窗口.after(
        刷新间隔毫秒,
        lambda: 刷新识别状态(
            根窗口=根窗口,
            识别状态变量=识别状态变量,
            诊断状态变量=诊断状态变量,
            控制详情变量=控制详情变量,
            定位器=定位器,
            预览更新函数=预览更新函数,
            刷新间隔毫秒=刷新间隔毫秒,
            暂停判定=暂停判定,
        ),
    )


def 启动巡航界面() -> None:
    import threading
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk

    root = tk.Tk()
    root.title("巡航启动器 · 004（角度可选）")
    root.geometry("900x800")
    root.minsize(780, 680)

    路径变量 = tk.StringVar()
    状态变量 = tk.StringVar(value="请选择路线文件")
    识别状态变量 = tk.StringVar(value=格式化识别状态文本())
    诊断状态变量 = tk.StringVar(value=格式化诊断状态文本())
    控制详情变量 = tk.StringVar(value=格式化控制详情文本())
    角度模式变量 = tk.StringVar(value="legacy")
    角度模式说明 = tk.StringVar(value="")
    预览照片 = {"image": None}
    停止事件 = threading.Event()
    巡航中 = {"value": False}

    try:
        监视定位器 = 实时定位器(角度模式="legacy")
    except Exception as exc:
        监视定位器 = None
        识别状态变量.set(格式化识别状态文本(错误=str(exc)))
        诊断状态变量.set(f"诊断: 控制=初始化失败 | 识别={str(exc)}")

    def 同步角度模式说明() -> None:
        mode = 角度模式变量.get()
        if mode == "text":
            角度模式说明.set(
                "text 箭头：HSV+连通域+加稳 | 雷达 34,78,227,271 | 截图仍用 GDI/mss"
            )
        else:
            角度模式说明.set(
                "旧算法：颜色轮廓 | 角度区 119,161,146,188 | 截图仍用 GDI/mss"
            )
        if 监视定位器 is not None and not 巡航中["value"]:
            try:
                监视定位器.设置角度模式(mode)
            except Exception as exc:
                状态变量.set(f"切换角度模式失败: {exc}")

    def 更新预览图(图像bgr) -> None:
        预览照片["image"] = 缩放为Tk图片(图像bgr)
        预览标签.config(image=预览照片["image"])

    def 选择文件() -> None:
        路径 = filedialog.askopenfilename(
            title="选择路线文件",
            filetypes=[("文本文件", "*.txt"), ("所有文件", "*.*")],
        )
        if 路径:
            路径变量.set(路径)
            状态变量.set("路线文件已选择")

    def 恢复按钮状态() -> None:
        巡航中["value"] = False
        开始按钮.config(state="normal")
        选择按钮.config(state="normal")
        for w in 角度单选:
            w.config(state="normal")

    def 安全派发(callback) -> None:
        try:
            root.after(0, callback)
        except Exception:
            pass

    def 轮询esc关闭() -> None:
        if 处理esc紧急停止(停止事件, root):
            return
        try:
            root.after(50, 轮询esc关闭)
        except Exception:
            pass

    def 开始寻路() -> None:
        try:
            路径文件 = 校验路线文件(路径变量.get())
        except ValueError as exc:
            messagebox.showerror("启动失败", str(exc))
            return
        if 监视定位器 is None:
            messagebox.showerror("启动失败", "定位器未初始化")
            return
        try:
            监视定位器.设置角度模式(角度模式变量.get())
        except Exception as exc:
            messagebox.showerror("启动失败", f"角度模式无效: {exc}")
            return

        开始按钮.config(state="disabled")
        选择按钮.config(state="disabled")
        for w in 角度单选:
            w.config(state="disabled")
        巡航中["value"] = True
        标签 = 合并识别模块.当前角度模式标签()
        状态变量.set(f"{构建开始状态文本(默认启动延迟秒数)} | 角度={标签}")

        def worker() -> None:
            try:
                后台执行巡航(路径文件, 定位器=监视定位器, 停止事件=停止事件)
                安全派发(lambda: 状态变量.set("寻路已结束"))
            except 紧急停止异常:
                安全派发(lambda: 状态变量.set("已通过 Esc 停止"))
            except Exception as exc:
                安全派发(lambda err=str(exc): messagebox.showerror("寻路失败", err))
                安全派发(lambda err=str(exc): 状态变量.set(f"寻路失败: {err}"))
            finally:
                安全派发(恢复按钮状态)

        threading.Thread(target=worker, daemon=True).start()

    tk.Label(root, text="路线文件").pack(anchor="w", padx=20, pady=(18, 6))
    tk.Entry(root, textvariable=路径变量, state="readonly", width=62).pack(padx=20, fill="x")

    模式框 = tk.LabelFrame(root, text="角度识别（截图方式不变）", padx=10, pady=8)
    模式框.pack(anchor="w", padx=20, pady=(12, 0), fill="x")
    角度单选 = []
    r1 = ttk.Radiobutton(
        模式框, text="Legacy 丝滑版", value="legacy",
        variable=角度模式变量, command=同步角度模式说明,
    )
    r1.pack(anchor="w")
    角度单选.append(r1)
    r2 = ttk.Radiobutton(
        模式框, text="原版 TEXT", value="text",
        variable=角度模式变量, command=同步角度模式说明,
    )
    r2.pack(anchor="w")
    角度单选.append(r2)
    tk.Label(模式框, textvariable=角度模式说明, fg="#555555", anchor="w", justify="left").pack(
        anchor="w", pady=(4, 0)
    )
    同步角度模式说明()

    tk.Label(
        root,
        text="截图：GDI→mss→PIL 并集一截两裁；寻路中暂停 UI 识别",
        fg="#555555",
        anchor="w",
    ).pack(anchor="w", padx=20, pady=(6, 0))

    按钮框 = tk.Frame(root)
    按钮框.pack(anchor="w", padx=20, pady=12)

    选择按钮 = tk.Button(按钮框, text="选择路线文件", command=选择文件, width=16)
    选择按钮.pack(side="left")

    开始按钮 = tk.Button(按钮框, text="开始寻路", command=开始寻路, width=16)
    开始按钮.pack(side="left", padx=(10, 0))

    tk.Label(root, textvariable=状态变量, anchor="w").pack(anchor="w", padx=20)
    tk.Label(root, text="实时识别状态").pack(anchor="w", padx=20, pady=(10, 4))
    tk.Label(root, textvariable=识别状态变量, anchor="w", justify="left").pack(anchor="w", padx=20)
    tk.Label(root, textvariable=诊断状态变量, anchor="w", justify="left").pack(anchor="w", padx=20, pady=(4, 0))
    tk.Label(root, textvariable=控制详情变量, anchor="w", justify="left").pack(anchor="w", padx=20, pady=(4, 0))
    预览标签 = tk.Label(root, bg="#111111", relief="sunken")
    预览标签.pack(fill="both", expand=True, padx=20, pady=(10, 20))
    if 监视定位器 is not None:
        更新预览图(监视定位器.生成预览图())
        root.after(
            0,
            lambda: 刷新识别状态(
                根窗口=root,
                识别状态变量=识别状态变量,
                诊断状态变量=诊断状态变量,
                控制详情变量=控制详情变量,
                定位器=监视定位器,
                预览更新函数=更新预览图,
                暂停判定=lambda: 巡航中["value"],
            ),
        )
    root.after(50, 轮询esc关闭)
    root.mainloop()


if __name__ == "__main__":
    启动巡航界面()
