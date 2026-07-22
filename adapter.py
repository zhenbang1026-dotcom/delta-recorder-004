from __future__ import annotations

import hashlib
import importlib
import importlib.util
import math
import sys
import time
import unicodedata
from pathlib import Path


模块目录 = Path(__file__).resolve().parent
默认地图路径 = 模块目录 / "maps" / "DB.png"
默认特征路径 = 模块目录 / "maps" / "DB.sift.npz"


def _按文件名加载模块(模块名):
    目标 = unicodedata.normalize("NFC", 模块名)
    for 路径 in 模块目录.glob("*.py"):
        if unicodedata.normalize("NFC", 路径.stem) == 目标:
            spec = importlib.util.spec_from_file_location(模块名, 路径)
            模块 = importlib.util.module_from_spec(spec)
            sys.modules[模块名] = 模块
            spec.loader.exec_module(模块)
            return 模块
    raise ModuleNotFoundError("No module named {!r}".format(模块名))


def _加载旧模块():
    module_path = str(模块目录)
    if module_path not in sys.path:
        sys.path.insert(0, module_path)
    try:
        return importlib.import_module("巡航脚本")
    except ModuleNotFoundError:
        return _按文件名加载模块("巡航脚本")


def _标准化状态(state):
    if all(hasattr(state, name) for name in ("x", "y", "angle")):
        values = state.x, state.y, state.angle
    else:
        try:
            values = tuple(state)
        except TypeError as error:
            raise TypeError("定位状态必须包含 x、y、angle") from error
        if len(values) != 3:
            raise ValueError("定位状态必须包含三个值")
    try:
        x, y, angle = int(values[0]), int(values[1]), float(values[2])
    except (TypeError, ValueError) as error:
        raise ValueError("定位状态包含无效数值") from error
    if not all(math.isfinite(value) for value in (x, y, angle)):
        raise ValueError("定位状态包含非有限数值")
    return x, y, angle


def _加载地图匹配器(combined, map_path, feature_path=默认特征路径):
    map_path = Path(map_path)
    feature_path = Path(feature_path)
    if not feature_path.is_file():
        raise FileNotFoundError("未找到大地图特征缓存: {}".format(feature_path))
    with combined.np.load(str(feature_path), allow_pickle=False) as cache:
        if int(cache["format_version"].item()) != 1:
            raise ValueError("大地图特征缓存版本无效")
        if str(cache["map_sha256"].item()) != hashlib.sha256(
            map_path.read_bytes()
        ).hexdigest():
            raise ValueError("大地图与特征缓存不匹配")
        points = combined.np.asarray(cache["points"], dtype=combined.np.float32)
        descriptors = combined.np.ascontiguousarray(
            cache["descriptors"], dtype=combined.np.float32
        )
    if points.ndim != 2 or points.shape[1] != 2 or descriptors.shape != (
        len(points),
        128,
    ):
        raise ValueError("大地图特征缓存内容无效")

    matcher = combined.单独坐标识别器.__new__(combined.单独坐标识别器)
    matcher.big_map = combined.cv2.imread(str(map_path))
    if matcher.big_map is None:
        matcher.big_map = combined.地图模块.imread_unicode(map_path)
    matcher.big_map_gray = combined.cv2.cvtColor(
        matcher.big_map, combined.cv2.COLOR_BGR2GRAY
    )
    matcher.sift = combined.cv2.SIFT_create()
    matcher.bf = combined.cv2.BFMatcher(combined.cv2.NORM_L2)
    matcher.kp_big = [
        combined.cv2.KeyPoint(float(x), float(y), 1.0) for x, y in points
    ]
    matcher.des_big = descriptors
    matcher.last_xy = None
    matcher.prev_xy = None
    matcher.lost_count = 0
    return matcher


class 实时定位器:
    """保持新项目接口，内部完整委托旧项目的全屏定位器。"""

    def __init__(self, dx=None, map_path=None):
        del dx
        combined = _加载旧模块().合并识别模块
        self.backend = combined.实时坐标角度识别器(
            _加载地图匹配器(combined, map_path or 默认地图路径)
        )

    def 读取状态(self):
        return _标准化状态(self.backend.读取状态())


def 等待稳定坐标(
    locator,
    stop_event,
    timeout=120,
    max_distance=50,
    sleep=time.sleep,
    log_func=None,
):
    deadline = time.monotonic() + timeout
    previous = None
    attempts = 0
    while not stop_event.is_set() and time.monotonic() < deadline:
        attempts += 1
        try:
            current = _标准化状态(locator.读取状态())
        except Exception as error:
            previous = None
            if log_func is not None and (attempts == 1 or attempts % 5 == 0):
                log_func("联动坐标识别第 {} 次失败: {}".format(attempts, error))
        else:
            if previous is not None and math.hypot(
                current[0] - previous[0], current[1] - previous[1]
            ) <= max_distance:
                return current
            previous = current
        remaining = deadline - time.monotonic()
        if remaining > 0:
            sleep(min(0.2, remaining))
    return None


def 执行路线(路径文件, dx, input_device, stop_event, log_func=None):
    del dx, input_device
    locator = 实时定位器(map_path=默认地图路径)
    _加载旧模块().后台执行巡航(
        str(Path(路径文件)),
        延迟秒数=0,
        定位器=locator,
        日志函数=log_func,
        停止事件=stop_event,
    )
