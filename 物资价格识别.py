# -*- coding: utf-8 -*-
"""物资价格识别：HSV 过滤稀有度底色 -> 按格子投票 -> 合并同一物资 -> 等级 x 格子数 = 价格。

思路
----
游戏里每件物资的底板是一块「稀有度颜色」的矩形，铺满它占据的所有格子。
1. 用 HSV 把 6 种稀有度底色分别过滤出来（底板偏暗，V 上限压到 75 可以把物资贴图本身滤掉）。
2. 逐格统计各颜色的像素占比，取最高者作为该格稀有度；占比过低判为空格。
3. 相邻同色格子之间如果没有「亮分隔线」，说明是同一件物资，用并查集合并。
4. 格子数 = 合并后的格子个数，价格 = 稀有度等级 x 格子数。

用法
----
    from 物资价格识别 import 识别区域, 抓屏识别, 容器区域, 背包区域

    物资表 = 抓屏识别(容器区域)
    for 物 in 物资表:
        print(物["色"], 物["价"], 物["双击点"])

直接运行本文件则跑 IMG_DIR 里的图片做离线验证，并输出标注图。
"""
from __future__ import annotations

import os
from typing import Dict, List, Optional, Sequence

import cv2
import numpy as np

# ---------------------------------------------------------------- 稀有度配置

#: 稀有度等级，数值越大越值钱。改这里就能改「单格价格」。
等级表: Dict[str, int] = {"白": 1, "绿": 2, "蓝": 3, "紫": 4, "金": 5, "红": 6}

#: 底板 V 上限。底板都比较暗，压住上限可以避开物资贴图的高亮像素。
_V上限 = 75

#: 稀有度底色的 HSV 区间（OpenCV 口径 H:0-179 S:0-255 V:0-255）。
#: 实测样本：红 H2-4 S110-120 V58-65 / 金 H14-20 S79-100 V50-58 /
#:          紫 H120-125 S47-62 V43-46 / 蓝 H101-104 S96-105 V52-57 /
#:          绿 H70-88 S49-96 V35-42 / 白 S18-32 V43-66 / 空格 H96-110 S26-44 V26-33
颜色区间: Dict[str, List[tuple]] = {
    "红": [((0, 80, 40), (9, 255, _V上限)), ((170, 80, 40), (179, 255, _V上限))],
    "金": [((10, 55, 38), (30, 255, _V上限))],
    "紫": [((113, 35, 36), (140, 255, _V上限))],
    "蓝": [((95, 60, 38), (112, 255, _V上限))],
    "绿": [((55, 45, 35), (92, 255, _V上限))],
    "白": [((0, 0, 37), (179, 35, _V上限))],
}

#: 一格里底色像素占比低于此值判为空格。实测有物资最低 12%，空格 0%。
空格阈值 = 0.08

#: 相邻同色格子之间亮分隔线的响应阈值。实测「分」最低 8.0，「合」最高 5.0。
分隔阈值 = 6.5

# ---------------------------------------------------------------- 区域配置

# 区域字段：
#   矩形     (左, 上, 宽, 高) 屏幕绝对坐标
#   格边长   一个格子的像素边长
#   原点     网格左上角相对「矩形」左上角的偏移 (dx, dy)
#   列数/行数
容器区域 = {
    "名称": "容器",
    "矩形": (962, 138, 201, 201),
    "格边长": 48,
    "原点": (5, 5),
    "列数": 4,
    "行数": 4,
}

# 背包是若干个子容器（胸挂/口袋/背包/安全箱）拼起来的，各自网格原点不同，
# 不能当成一整块网格来切。这里按「空位 558,287,58x58」推出格边长 58、原点 (6,197)，
# 只覆盖背包主格区；其余子容器请照这个格式各配一条。
背包区域 = {
    "名称": "背包",
    "矩形": (552, 90, 368, 753),
    "格边长": 58,
    "原点": (6, 197),
    "列数": 6,
    "行数": 9,
}


# ---------------------------------------------------------------- 内部工具


def _读图(路径: str) -> Optional[np.ndarray]:
    """cv2.imread 在中文路径下会失败，用 imdecode 绕开。"""
    数据 = np.fromfile(路径, dtype=np.uint8)
    return cv2.imdecode(数据, cv2.IMREAD_COLOR)


def _写图(路径: str, 图: np.ndarray) -> None:
    ok, buf = cv2.imencode(os.path.splitext(路径)[1] or ".png", 图)
    if ok:
        buf.tofile(路径)


def _颜色掩码(hsv: np.ndarray) -> Dict[str, np.ndarray]:
    掩码 = {}
    for 名, 区间 in 颜色区间.items():
        m = np.zeros(hsv.shape[:2], np.uint8)
        for 低, 高 in 区间:
            m |= cv2.inRange(hsv, np.array(低, np.uint8), np.array(高, np.uint8))
        掩码[名] = m > 0
    return 掩码


def _边缘响应(灰: np.ndarray, 横向: bool) -> np.ndarray:
    """每个像素相对左右(或上下)邻居的亮度差，分隔线是一条亮线，会出现正峰。

    返回值第 0 维是被扫描的方向：横向时 shape 为 (高, 宽)，纵向时为 (宽, 高)。
    """
    g = 灰 if 横向 else 灰.T
    d = np.zeros(g.shape)
    d[:, 2:-2] = g[:, 2:-2] - (g[:, :-4] + g[:, 4:]) / 2.0
    return d


class _并查集:
    def __init__(self, 元素):
        self.父 = {k: k for k in 元素}

    def 找(self, a):
        while self.父[a] != a:
            self.父[a] = self.父[self.父[a]]
            a = self.父[a]
        return a

    def 并(self, a, b):
        ra, rb = self.找(a), self.找(b)
        if ra != rb:
            self.父[ra] = rb


# ---------------------------------------------------------------- 核心识别


def 识别区域(图: np.ndarray, 区域: dict) -> List[dict]:
    """在一张已裁好的区域图上识别所有物资。

    :param 图: 区域的 BGR 图，尺寸应与 区域["矩形"] 的宽高一致
    :param 区域: 见 容器区域 / 背包区域
    :return: 物资列表，每项含 色/等级/行/列/格宽/格高/格数/价/矩形/双击点
    """
    左, 上, _, _ = 区域["矩形"]
    边 = 区域["格边长"]
    ox, oy = 区域["原点"]
    列数, 行数 = 区域["列数"], 区域["行数"]

    hsv = cv2.cvtColor(图, cv2.COLOR_BGR2HSV)
    灰 = cv2.cvtColor(图, cv2.COLOR_BGR2GRAY).astype(float)
    掩码 = _颜色掩码(hsv)
    dx = _边缘响应(灰, True)
    dy = _边缘响应(灰, False)

    # 1) 逐格投票定稀有度
    格色: Dict[tuple, Optional[str]] = {}
    for r in range(行数):
        for c in range(列数):
            y0, x0 = oy + r * 边 + 4, ox + c * 边 + 4
            y1, x1 = oy + (r + 1) * 边 - 4, ox + (c + 1) * 边 - 4
            if y1 > 图.shape[0] or x1 > 图.shape[1] or y0 < 0 or x0 < 0:
                格色[(r, c)] = None
                continue
            总数 = (y1 - y0) * (x1 - x0)
            计数 = {名: int(m[y0:y1, x0:x1].sum()) for 名, m in 掩码.items()}
            最多 = max(计数, key=计数.get)
            格色[(r, c)] = 最多 if 计数[最多] > 空格阈值 * 总数 else None

    # 2) 相邻同色格子若无分隔线则合并
    def _相连(d: np.ndarray, 线: int, 起: int, 止: int) -> bool:
        带 = d[起 + 8:止 - 4, 线 - 1:线 + 2]
        if 带.size == 0:
            return False
        return float(np.median(带, axis=0).max()) < 分隔阈值

    集 = _并查集([k for k, v in 格色.items() if v])
    for r in range(行数):
        for c in range(列数):
            当前 = 格色.get((r, c))
            if not 当前:
                continue
            if c + 1 < 列数 and 格色.get((r, c + 1)) == 当前:
                if _相连(dx, ox + (c + 1) * 边, oy + r * 边, oy + (r + 1) * 边):
                    集.并((r, c), (r, c + 1))
            if r + 1 < 行数 and 格色.get((r + 1, c)) == 当前:
                if _相连(dy, oy + (r + 1) * 边, ox + c * 边, ox + (c + 1) * 边):
                    集.并((r, c), (r + 1, c))

    分组: Dict[tuple, List[tuple]] = {}
    for k in 集.父:
        分组.setdefault(集.找(k), []).append(k)

    # 3) 算格子数和价格
    物资表 = []
    for 格们 in 分组.values():
        行们 = [a for a, _ in 格们]
        列们 = [b for _, b in 格们]
        r0, c0 = min(行们), min(列们)
        格宽 = max(列们) - c0 + 1
        格高 = max(行们) - r0 + 1
        色 = 格色[格们[0]]
        等级 = 等级表[色]
        x = 左 + ox + c0 * 边
        y = 上 + oy + r0 * 边
        w, h = 格宽 * 边, 格高 * 边
        物资表.append({
            "区域": 区域["名称"],
            "色": 色,
            "等级": 等级,
            "行": r0,
            "列": c0,
            "格宽": 格宽,
            "格高": 格高,
            "格数": len(格们),
            "价": 等级 * len(格们),
            "矩形": (x, y, w, h),
            "双击点": (x + w // 2, y + h // 2),
        })
    return sorted(物资表, key=lambda z: (z["行"], z["列"]))


def 抓屏识别(区域: dict) -> List[dict]:
    """实时截屏并识别指定区域。"""
    import 截图模块

    左, 上, 宽, 高 = 区域["矩形"]
    图, _ = 截图模块.grab_bbox_bgr((左, 上, 左 + 宽, 上 + 高))
    return 识别区域(图, 区域)


def 总价(物资表: Sequence[dict]) -> int:
    return sum(物["价"] for 物 in 物资表)


def 空格数(图: np.ndarray, 区域: dict) -> int:
    """区域内还剩多少空格子。"""
    已占 = sum(物["格数"] for 物 in 识别区域(图, 区域))
    return 区域["列数"] * 区域["行数"] - 已占


# ---------------------------------------------------------------- 标注输出

_标注色 = {
    "红": (60, 60, 220), "金": (40, 170, 230), "紫": (200, 80, 200),
    "蓝": (230, 160, 60), "绿": (80, 200, 80), "白": (230, 230, 230),
}


def 画标注(图: np.ndarray, 区域: dict, 物资表: Sequence[dict]) -> np.ndarray:
    """在区域图上画出每件物资的框和「色 等级x格数=价」。"""
    左, 上, _, _ = 区域["矩形"]
    出 = 图.copy()
    for 物 in 物资表:
        x, y, w, h = 物["矩形"]
        x, y = x - 左, y - 上
        色 = _标注色[物["色"]]
        cv2.rectangle(出, (x, y), (x + w, y + h), 色, 2)
        cv2.putText(出, "%dx%d=%d" % (物["等级"], 物["格数"], 物["价"]),
                    (x + 3, y + h - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.4, 色, 1, cv2.LINE_AA)
    return 出


# ---------------------------------------------------------------- 离线验证

IMG_DIR = r"D:\Azhuomian\GitHub\Python工具\images"
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "识别结果")


def _离线验证(目录: str = IMG_DIR, 区域: dict = 容器区域) -> None:
    if not os.path.isdir(目录):
        print("图片目录不存在:", 目录)
        return
    os.makedirs(OUT_DIR, exist_ok=True)
    左, 上, 宽, 高 = 区域["矩形"]
    文件 = sorted(f for f in os.listdir(目录) if f.lower().endswith((".jpg", ".jpeg", ".png", ".bmp")))
    for 名 in 文件:
        全 = _读图(os.path.join(目录, 名))
        if 全 is None:
            print("读取失败:", 名)
            continue
        图 = 全[上:上 + 高, 左:左 + 宽]
        物资表 = 识别区域(图, 区域)
        print("=== %s  （%s %d,%d,%dx%d）" % (名, 区域["名称"], 左, 上, 宽, 高))
        for 物 in 物资表:
            print("   %s 等级%d 位置(行%d,列%d) 尺寸%dx%d 格数%d 价%d 双击点%s"
                  % (物["色"], 物["等级"], 物["行"], 物["列"], 物["格宽"], 物["格高"],
                     物["格数"], 物["价"], 物["双击点"]))
        print("   物资数 %d，总价 %d" % (len(物资表), 总价(物资表)))
        路径 = os.path.join(OUT_DIR, os.path.splitext(名)[0] + "_标注.png")
        _写图(路径, 画标注(图, 区域, 物资表))
        print("   标注图:", 路径)


if __name__ == "__main__":
    _离线验证()
