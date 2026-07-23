import inspect
from pathlib import Path
from types import SimpleNamespace

import pytest

import 巡航脚本 as cruise


class 假输入模块:
    def __init__(self):
        self.丝滑调用 = []
        self.释放次数 = 0

    def 丝滑相对移动(self, dx, dy):
        self.丝滑调用.append((dx, dy))

    def 释放移动键(self):
        self.释放次数 += 1

    def 键盘按下(self, _key):
        pass

    def 键盘单击(self, _key):
        pass

    def 点按shift(self):
        pass


class 假连续控制器:
    def __init__(self):
        self.角度差记录 = []
        self.已停止 = False

    def 更新角度差(self, value):
        self.角度差记录.append(value)

    def 停止(self):
        self.已停止 = True


def 设置模式(monkeypatch, mode):
    monkeypatch.setattr(cruise.合并识别模块, "当前角度模式", lambda: mode)


def test_mode_helpers_keep_text_exact(monkeypatch):
    设置模式(monkeypatch, "text")
    assert cruise.是否text角度模式()
    assert cruise.是否增强角度模式()

    设置模式(monkeypatch, "legacy")
    assert not cruise.是否text角度模式()
    assert not cruise.是否增强角度模式()


def test_legacy_action_and_executor_use_continuous_controller(monkeypatch):
    设置模式(monkeypatch, "legacy")
    参数 = cruise.普通模式参数()
    动作 = cruise.选择动作(距离=20, 角度差=20.0, 到点阈值=3, 参数=参数, 自动路线=True)
    assert 动作 == cruise.动作指令("转向", 鼠标像素=433)

    输入 = 假输入模块()
    连续 = 假连续控制器()
    执行器 = cruise.Win32执行器(
        输入模块=输入,
        连续控制器工厂=lambda _input, **_kwargs: 连续,
    )
    执行器.执行(动作)
    执行器.停止()

    assert 输入.丝滑调用 == []
    assert 连续.角度差记录 == [pytest.approx(433 / cruise.当前每度像素())]
    assert 连续.已停止


@pytest.mark.parametrize(
    ("mode", "输入倍率", "期望倍率"),
    [("legacy", "2.0", 2.0), ("text", 0.1, 0.5)],
)
def test_executor_passes_normalized_speed_multiplier_to_continuous_controller(
    monkeypatch, mode, 输入倍率, 期望倍率
):
    设置模式(monkeypatch, mode)
    收到参数 = {}

    def 创建连续控制器(_input, **kwargs):
        收到参数.update(kwargs)
        return 假连续控制器()

    执行器 = cruise.Win32执行器(
        输入模块=假输入模块(),
        视角速度倍率=输入倍率,
        连续控制器工厂=创建连续控制器,
    )
    执行器.停止()

    assert 收到参数 == {"视角速度倍率": 期望倍率}


@pytest.mark.parametrize(
    ("mode", "输入倍率", "期望倍率"),
    [("legacy", 2.25, 2.25), ("text", "4.0", 3.0)],
)
def test_cruise_passes_speed_multiplier_to_win32_executor(
    monkeypatch, mode, 输入倍率, 期望倍率
):
    设置模式(monkeypatch, mode)
    收到参数 = {}
    已运行 = []

    def 创建执行器(**kwargs):
        收到参数.update(kwargs)
        return object()

    class 假巡航控制器:
        def __init__(self, **_kwargs):
            pass

        def 运行(self):
            已运行.append(True)

    monkeypatch.setattr(cruise, "读取路径", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(cruise, "重置每度像素校准", lambda *_args: None)
    monkeypatch.setattr(cruise, "寻路记录器", lambda: None)
    monkeypatch.setattr(cruise, "Win32执行器", 创建执行器)
    monkeypatch.setattr(cruise, "巡航控制器", 假巡航控制器)

    cruise.巡航("route.txt", 定位器=object(), 视角速度倍率=输入倍率)

    assert 收到参数 == {"视角速度倍率": 期望倍率}
    assert 已运行 == [True]


def test_advanced_executor_uses_continuous_controller_without_legacy_smooth_move():
    输入 = 假输入模块()
    连续 = 假连续控制器()
    执行器 = cruise.Win32执行器(
        输入模块=输入,
        连续控制器工厂=lambda _input, **_kwargs: 连续,
    )

    执行器.执行(cruise.动作指令("转向", 鼠标像素=400))
    执行器.停止()

    assert 输入.丝滑调用 == []
    assert 连续.角度差记录[-1] == pytest.approx(12.0)
    assert 连续.已停止


def test_advanced_waypoint_switch_clears_previous_turn_target():
    输入 = 假输入模块()
    连续 = 假连续控制器()
    执行器 = cruise.Win32执行器(
        输入模块=输入,
        连续控制器工厂=lambda _input, **_kwargs: 连续,
    )

    执行器.执行(cruise.动作指令("转向", 鼠标像素=400))
    执行器.执行(cruise.动作指令("自动路线切换下一个点"))
    执行器.执行(cruise.动作指令("转向", 鼠标像素=-400))
    执行器.执行(cruise.动作指令("切换下一个点"))

    assert 连续.角度差记录 == [12.0, 0.0, -12.0, 0.0]


def test_near_point_micro_adjustment_reaches_continuous_controller(monkeypatch):
    设置模式(monkeypatch, "text")
    输入 = 假输入模块()
    连续 = cruise.连续视角控制器(输入, 自动启动=False, 时钟=lambda: 0.0)
    执行器 = cruise.Win32执行器(
        输入模块=输入,
        连续控制器工厂=lambda _input, **_kwargs: 连续,
    )
    控制器 = cruise.巡航控制器(
        路径点列表=[cruise.路径点(0, 0, 0.0, True)],
        定位器=SimpleNamespace(),
        执行器=执行器,
        到点阈值=3,
        参数=cruise.普通模式参数(),
    )
    原动作 = cruise.选择动作(
        距离=8, 角度差=20.0, 到点阈值=3, 参数=控制器.参数, 自动路线=True
    )
    近点动作 = 控制器._处理近点位转向(距离=8, 角度差=20.0, 动作=原动作)

    执行器.执行(近点动作)

    assert 近点动作.鼠标像素 == 113
    assert 连续.目标角速度 > 0.0


def test_route_spacing_is_six_only_when_explicitly_selected(tmp_path):
    路径 = tmp_path / "route.txt"
    路径.write_text("\n".join(f"{x},0" for x in range(0, 31, 3)), encoding="utf-8")

    legacy = cruise.读取路径(str(路径))
    advanced = cruise.读取路径(str(路径), 自动路线点距=6)

    assert [(p.x, p.y) for p in legacy] == [(0, 0), (18, 0), (30, 0)]
    assert [(p.x, p.y) for p in advanced] == [
        (0, 0), (6, 0), (12, 0), (18, 0), (24, 0), (30, 0)
    ]


def test_current_mode_route_spacing_preserves_legacy_default(monkeypatch):
    设置模式(monkeypatch, "legacy")
    assert cruise.当前模式自动路线点距() == 18
    设置模式(monkeypatch, "text")
    assert cruise.当前模式自动路线点距() == 6


@pytest.mark.parametrize(("mode", "distance"), [("legacy", 4), ("text", 8)])
def test_near_point_large_angle_keeps_turning_in_place(monkeypatch, mode, distance):
    设置模式(monkeypatch, mode)
    控制器 = cruise.巡航控制器(
        路径点列表=[cruise.路径点(0, 0, 0.0, True)],
        定位器=SimpleNamespace(),
        执行器=SimpleNamespace(),
        到点阈值=3,
        参数=cruise.普通模式参数(),
    )
    原动作 = cruise.选择动作(
        距离=distance,
        角度差=45.0,
        到点阈值=3,
        参数=控制器.参数,
        自动路线=True,
    )
    assert 原动作.类型 == "转向"

    动作 = 控制器._处理近点位转向(距离=distance, 角度差=45.0, 动作=原动作)

    assert 动作 == 原动作
    for _ in range(cruise.转向不收敛判定次数):
        动作 = 控制器._处理转向不收敛(
            当前索引=0,
            当前坐标=(0, 0),
            距离=distance,
            角度差=45.0,
            动作=动作,
        )
        assert 动作 == 原动作


@pytest.mark.parametrize("mode", ["legacy", "text"])
def test_continuous_turn_confirmation_is_non_blocking_and_does_not_read_again(monkeypatch, mode):
    设置模式(monkeypatch, mode)
    定位器 = SimpleNamespace(读取状态=lambda: (_ for _ in ()).throw(AssertionError("不应复读")))
    控制器 = cruise.巡航控制器(
        路径点列表=[cruise.路径点(10, 0, 0.0, True)],
        定位器=定位器,
        执行器=SimpleNamespace(_连续视角控制器=object()),
        到点阈值=3,
        参数=cruise.普通模式参数(),
    )

    控制器._转向后确认状态(
        (0, 0, 0.0),
        cruise.路径点(10, 0, 0.0, True),
        45.0,
        cruise.动作指令("转向", 鼠标像素=400),
    )

    assert 控制器._待处理状态 is None


def test_text_mode_no_longer_exposes_removed_fusion_helper():
    assert not hasattr(cruise.实时定位器, "_text融合读角")


def test_text_angle_failure_reuses_recent_success_without_refresh(monkeypatch):
    class 定位器:
        识别诊断状态 = ""
        控制诊断状态 = ""

        def __init__(self):
            self.calls = 0

        def 读取状态(self):
            self.calls += 1
            if self.calls == 1:
                return 12, 34, 56.0
            raise RuntimeError("无法识别当前朝向（text箭头算法）：箭头面积过小: 12 < 20")

    执行动作 = []
    定位 = 定位器()
    控制器 = cruise.巡航控制器(
        路径点列表=[cruise.路径点(20, 30, 0.0, True)],
        定位器=定位,
        执行器=SimpleNamespace(执行=lambda action: 执行动作.append(action)),
        到点阈值=3,
        参数=cruise.普通模式参数(),
        循环间隔=0.0,
    )
    monkeypatch.setattr(cruise, "状态读取最大重试次数", 1)
    monkeypatch.setattr(cruise, "状态读取重试间隔", 0.0)

    assert 控制器._读取状态_带重试() == (12, 34, 56.0)
    assert 控制器._读取状态_带重试() == (12, 34, 56.0)
    assert 控制器._连续沿用次数 == 1
    assert 执行动作 == []


def test_text_locator_reuses_only_recent_angle_with_fresh_coordinates(monkeypatch):
    observations = iter([
        SimpleNamespace(angle=56.0),
        RuntimeError("无法识别当前朝向"),
        RuntimeError("无法识别当前朝向"),
        RuntimeError("无法识别当前朝向"),
        SimpleNamespace(angle=60.0),
        RuntimeError("无法识别当前朝向"),
    ])
    coordinates = iter([(12, 34), (13, 35), (14, 36), (15, 37), (16, 38), (17, 39)])
    times = iter([100.0, 100.03, 100.06, 100.09, 100.10, 100.13])

    def analyze(*_args, **_kwargs):
        observation = next(observations)
        if isinstance(observation, Exception):
            raise observation
        return observation

    locator = object.__new__(cruise.实时定位器)
    locator.角度模式 = "text"
    locator._合并识别器 = SimpleNamespace(角度分析器=analyze, 角度颜色=[])
    locator._截图小地图与角度 = lambda: (object(), object())
    locator._识别坐标 = lambda _image: next(coordinates)
    locator._确认角度跳变 = lambda _x, _y, angle, _retry: angle
    locator._记录角度诊断 = lambda _result: None
    locator.最近状态 = None
    monkeypatch.setattr(cruise.time, "monotonic", lambda: next(times))

    assert locator._读取状态_无锁() == (12, 34, 56.0)
    assert locator._读取状态_无锁() == (13, 35, 56.0)
    assert locator._读取状态_无锁() == (14, 36, 56.0)
    with pytest.raises(RuntimeError, match="无法识别当前朝向"):
        locator._读取状态_无锁()
    assert locator._读取状态_无锁() == (16, 38, 60.0)
    assert locator._读取状态_无锁() == (17, 39, 60.0)


@pytest.mark.parametrize(
    ("mode", "times"),
    [("text", iter([100.0, 100.11])), ("legacy", iter([100.0]))],
)
def test_text_angle_reuse_rejects_timeout_and_never_applies_to_legacy(monkeypatch, mode, times):
    observations = iter([SimpleNamespace(angle=56.0), RuntimeError("无法识别当前朝向")])

    def analyze(*_args, **_kwargs):
        observation = next(observations)
        if isinstance(observation, Exception):
            raise observation
        return observation

    locator = object.__new__(cruise.实时定位器)
    locator.角度模式 = mode
    locator._合并识别器 = SimpleNamespace(角度分析器=analyze, 角度颜色=[])
    locator._记录角度诊断 = lambda _result: None
    monkeypatch.setattr(cruise.time, "monotonic", lambda: next(times))

    assert locator._识别角度(object()) == 56.0
    with pytest.raises(RuntimeError, match="无法识别当前朝向"):
        locator._识别角度(object())


def test_mode_log_fields_include_continuous_output_without_fusion_diagnostics(monkeypatch):
    设置模式(monkeypatch, "legacy")
    字段 = cruise.模式诊断日志字段(SimpleNamespace(连续控制实际像素=-37))

    assert 字段 == {"角度模式": "legacy", "连续控制实际像素": "-37"}


def test_step_log_contains_mode_and_continuous_output(monkeypatch):
    设置模式(monkeypatch, "legacy")
    日志 = []

    class 记录器:
        def __init__(self):
            self.记录列表 = []

        def 记录(self, **fields):
            self.记录列表.append(fields)

        def 保存事件截图(self, _事件):
            pass

    class 定位器:
        识别诊断状态 = "识别完成"
        控制诊断状态 = "待机"

        def 读取状态(self):
            return 0, 0, 0.0

    class 执行器:
        def 执行(self, _动作):
            pass

        def 取出连续输出像素(self):
            return 23

        def 停止(self):
            pass

    寻路记录器 = 记录器()
    控制器 = cruise.巡航控制器(
        路径点列表=[cruise.路径点(0, -20, 0.0, True)],
        定位器=定位器(),
        执行器=执行器(),
        到点阈值=3,
        参数=cruise.普通模式参数(),
        循环间隔=0.0,
        日志函数=lambda event, **fields: 日志.append((event, fields)),
        记录器=寻路记录器,
    )

    with pytest.raises(RuntimeError, match="超过最大步数"):
        控制器.运行(最大步数=1)

    step = next(fields for event, fields in 日志 if event == "event=step")
    assert step["角度模式"] == "legacy"
    assert step["连续控制实际像素"] == "23"
    assert 寻路记录器.记录列表[-1]["角度模式"] == "legacy"
    assert 寻路记录器.记录列表[-1]["连续控制实际像素"] == "23"


def test_standalone_ui_has_only_legacy_and_text_modes_with_legacy_default():
    source = inspect.getsource(cruise.启动巡航界面)
    assert 'tk.StringVar(value="legacy")' in source
    assert 'value="legacy"' in source
    assert 'value="text"' in source
    assert 'text="Legacy 丝滑版"' in source
    assert 'text="原版 TEXT"' in source
    assert 'value="fusion"' not in source
    assert "Fusion" not in source
    assert source.count("ttk.Radiobutton") == 2
