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


def test_mode_helpers_keep_text_exact_and_include_fusion_as_advanced(monkeypatch):
    设置模式(monkeypatch, "text")
    assert cruise.是否text角度模式()
    assert cruise.是否增强角度模式()

    设置模式(monkeypatch, "fusion")
    assert not cruise.是否text角度模式()
    assert cruise.是否增强角度模式()

    设置模式(monkeypatch, "legacy")
    assert not cruise.是否text角度模式()
    assert not cruise.是否增强角度模式()


def test_legacy_action_and_executor_keep_original_behavior(monkeypatch):
    设置模式(monkeypatch, "legacy")
    参数 = cruise.普通模式参数()
    动作 = cruise.选择动作(距离=20, 角度差=20.0, 到点阈值=3, 参数=参数, 自动路线=True)
    assert 动作 == cruise.动作指令("转向", 鼠标像素=433)

    输入 = 假输入模块()
    是否创建连续控制器 = []
    执行器 = cruise.Win32执行器(
        输入模块=输入,
        增强视角=False,
        连续控制器工厂=lambda _input: 是否创建连续控制器.append(True),
    )
    执行器.执行(cruise.动作指令("转向", 鼠标像素=433))
    执行器.执行(cruise.动作指令("转向", 鼠标像素=0))
    assert 输入.丝滑调用 == [(433, 0), (0, 0)]
    assert 是否创建连续控制器 == []


def test_advanced_executor_uses_continuous_controller_without_legacy_smooth_move():
    输入 = 假输入模块()
    连续 = 假连续控制器()
    执行器 = cruise.Win32执行器(
        输入模块=输入,
        增强视角=True,
        连续控制器工厂=lambda _input: 连续,
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
        增强视角=True,
        连续控制器工厂=lambda _input: 连续,
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
        增强视角=True,
        连续控制器工厂=lambda _input: 连续,
    )
    控制器 = cruise.巡航控制器(
        路径点列表=[cruise.路径点(0, 0, 0.0, True)],
        定位器=SimpleNamespace(),
        执行器=执行器,
        到点阈值=3,
        参数=cruise.普通模式参数(),
    )
    原动作 = cruise.选择动作(
        距离=8, 角度差=45.0, 到点阈值=3, 参数=控制器.参数, 自动路线=True
    )
    近点动作 = 控制器._处理近点位转向(距离=8, 角度差=45.0, 动作=原动作)

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
    设置模式(monkeypatch, "fusion")
    assert cruise.当前模式自动路线点距() == 6


@pytest.mark.parametrize("mode", ["text", "fusion"])
def test_advanced_near_point_never_stops_for_large_turn(monkeypatch, mode):
    设置模式(monkeypatch, mode)
    控制器 = cruise.巡航控制器(
        路径点列表=[cruise.路径点(0, 0, 0.0, True)],
        定位器=SimpleNamespace(),
        执行器=SimpleNamespace(),
        到点阈值=3,
        参数=cruise.普通模式参数(),
    )
    原动作 = cruise.选择动作(
        距离=8,
        角度差=45.0,
        到点阈值=3,
        参数=控制器.参数,
        自动路线=True,
    )
    assert 原动作.类型 == "转向"

    动作 = 控制器._处理近点位转向(距离=8, 角度差=45.0, 动作=原动作)

    assert 动作.类型 == "前进并微调"
    assert abs(动作.鼠标像素) <= 114


@pytest.mark.parametrize("mode", ["text", "fusion"])
def test_advanced_turn_confirmation_is_non_blocking_and_does_not_read_again(monkeypatch, mode):
    设置模式(monkeypatch, mode)
    定位器 = SimpleNamespace(读取状态=lambda: (_ for _ in ()).throw(AssertionError("不应复读")))
    控制器 = cruise.巡航控制器(
        路径点列表=[cruise.路径点(10, 0, 0.0, True)],
        定位器=定位器,
        执行器=SimpleNamespace(),
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


def test_text_read_angle_no_longer_self_certifies_mouse_command(monkeypatch):
    设置模式(monkeypatch, "text")
    定位器 = object.__new__(cruise.实时定位器)
    定位器._text命令角 = 30.0

    assert 定位器._text融合读角(0.0) == 0.0
    assert 定位器._text命令角 == 30.0


def test_mode_log_fields_include_fusion_diagnostics(monkeypatch):
    设置模式(monkeypatch, "fusion")
    字段 = cruise.模式诊断日志字段(SimpleNamespace(Fusion诊断状态="双源一致"))
    assert 字段 == {"角度模式": "fusion", "Fusion诊断": "双源一致"}

    含控制输出 = cruise.模式诊断日志字段(
        SimpleNamespace(Fusion诊断状态="双源一致", 连续控制实际像素=-37)
    )
    assert 含控制输出["连续控制实际像素"] == "-37"


def test_locator_copies_fusion_result_into_runtime_diagnostics():
    定位器 = object.__new__(cruise.实时定位器)
    定位器._cv2 = SimpleNamespace(countNonZero=lambda _mask: 10)
    结果 = SimpleNamespace(
        color_hex="9AE77E",
        origin=(10.0, 10.0),
        target=(15.0, 10.0),
        mask=object(),
        observation_source="legacy",
        confidence=0.75,
        fusion_reason="TEXT 无效，降级 Legacy",
        fusion_difference=28.0,
    )

    定位器._记录角度诊断(结果)

    assert 定位器.Fusion诊断状态 == (
        "来源=legacy | 置信度=0.75 | 双源差=28.00° | TEXT 无效，降级 Legacy"
    )


def test_step_log_contains_mode_and_fusion_diagnostics(monkeypatch):
    设置模式(monkeypatch, "fusion")
    日志 = []

    class 记录器:
        def __init__(self):
            self.记录列表 = []

        def 记录(self, **fields):
            self.记录列表.append(fields)

        def 保存事件截图(self, _事件):
            pass

    class 定位器:
        Fusion诊断状态 = "主源可信"
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
    assert step["角度模式"] == "fusion"
    assert step["Fusion诊断"] == "主源可信"
    assert step["连续控制实际像素"] == "23"
    assert 寻路记录器.记录列表[-1]["角度模式"] == "fusion"
    assert 寻路记录器.记录列表[-1]["Fusion诊断"] == "主源可信"
    assert 寻路记录器.记录列表[-1]["连续控制实际像素"] == "23"


def test_standalone_ui_has_three_modes_and_legacy_default():
    source = inspect.getsource(cruise.启动巡航界面)
    assert 'tk.StringVar(value="legacy")' in source
    assert 'value="fusion"' in source
    assert "Fusion" in source
