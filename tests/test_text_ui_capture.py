from __future__ import annotations

import inspect
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

import A测试角度识别 as 测试角度模块
import 识别角度 as text角度模块


class _变量:
    def __init__(self, value: str) -> None:
        self.value = value

    def get(self) -> str:
        return self.value

    def set(self, value: str) -> None:
        self.value = value


def _写校准(tmp_path: Path, crop: str) -> Path:
    calibration = tmp_path / "lv.txt"
    calibration.write_text(
        f"SRC_CROP:{crop}\nPRECISE_CENTER:10,10\n",
        encoding="utf-8",
    )
    return calibration


def test独立ui只有两种模式且默认legacy() -> None:
    init_source = inspect.getsource(测试角度模块.RealtimeAngleApp.__init__)
    ui_source = inspect.getsource(测试角度模块.RealtimeAngleApp._build_ui)

    assert "tk.StringVar(value=ANGLE_MODE_LEGACY)" in init_source
    assert "ANGLE_MODE_LABELS.items()" in ui_source
    assert "tk.Radiobutton" in ui_source
    assert 测试角度模块.ANGLE_MODE_LABELS == {
        "legacy": "Legacy 丝滑版",
        "text": "原版 TEXT",
    }


def test切模式立刻同步对应bbox() -> None:
    app = object.__new__(测试角度模块.RealtimeAngleApp)
    app.angle_mode_var = _变量("text")
    app.angle_bbox_var = _变量(测试角度模块.ANGLE_LEGACY_BBOX)

    app._on_angle_mode_changed()

    assert 测试角度模块.get_angle_mode() == "text"
    assert app.angle_bbox_var.get() == "34,78,227,271"

    app.angle_mode_var.set("legacy")
    app._on_angle_mode_changed()

    assert 测试角度模块.get_angle_mode() == "legacy"
    assert app.angle_bbox_var.get() == "119,161,146,188"


def test运行期间不能切换为与截图bbox不一致的模式() -> None:
    测试角度模块.set_angle_mode("legacy")
    app = object.__new__(测试角度模块.RealtimeAngleApp)
    app.worker = SimpleNamespace(is_alive=lambda: True)
    app.angle_mode_var = _变量("text")
    app.angle_bbox_var = _变量(测试角度模块.ANGLE_LEGACY_BBOX)

    app._on_angle_mode_changed()

    assert 测试角度模块.get_angle_mode() == "legacy"
    assert app.angle_mode_var.get() == "legacy"
    assert app.angle_bbox_var.get() == 测试角度模块.ANGLE_LEGACY_BBOX


def test默认text识别器自动加载三色校准() -> None:
    recognizer = text角度模块.默认识别器()

    assert isinstance(recognizer, text角度模块.多颜色角度识别器)
    configs = {
        name: (Path(item.lv_txt路径).parent.name, item.箭头HSV)
        for name, item in recognizer.颜色识别器列表
    }
    assert configs == {
        "蓝色": ("校准截图蓝色", ([100, 50, 50], [130, 255, 255])),
        "绿色": ("校准截图绿色", ([48, 66, 87], [78, 166, 255])),
        "黄色": ("校准截图黄色", ([18, 80, 80], [40, 255, 255])),
    }
    assert all(Path(item.lv_txt路径).is_file() for _, item in recognizer.颜色识别器列表)
    calibration = recognizer._读取校准数据()
    assert calibration["crop"] == (76, 70, 116, 110)
    assert calibration["center_x"] == pytest.approx(43.061184)
    assert calibration["center_y"] == pytest.approx(42.238440)


def test三色识别器选择圆心偏差最小的合法候选() -> None:
    class 假识别器:
        def __init__(self, angle, detail):
            self.angle = angle
            self.最近详情 = detail
            self.calls = 0

        def 识别角度(self, 图像数据=None, 显示=False):
            self.calls += 1
            return self.angle

    blue = 假识别器(10.0, {"disk_center_error": 2.0, "arrow_area": 100})
    green = 假识别器(20.0, {"disk_center_error": 0.2, "arrow_area": 50})
    yellow = 假识别器(None, {"error": "连通域不足: 1"})
    recognizer = text角度模块.多颜色角度识别器(
        [("蓝色", blue), ("绿色", green), ("黄色", yellow)]
    )

    angle = recognizer.识别角度(图像数据=np.zeros((10, 10, 3), dtype=np.uint8))

    assert angle == 20.0
    assert recognizer.最近详情["arrow_color"] == "绿色"
    assert [blue.calls, green.calls, yellow.calls] == [1, 1, 1]


def test三色识别全部失败时保留每种颜色原因() -> None:
    class 假识别器:
        def __init__(self, reason):
            self.最近详情 = {"error": reason}

        def 识别角度(self, 图像数据=None, 显示=False):
            return None

    recognizer = text角度模块.多颜色角度识别器([
        ("蓝色", 假识别器("蓝失败")),
        ("绿色", 假识别器("绿失败")),
        ("黄色", 假识别器("黄失败")),
    ])

    angle = recognizer.识别角度(图像数据=np.zeros((10, 10, 3), dtype=np.uint8))

    assert angle is None
    assert recognizer.最近详情 == {
        "error": "三色识别失败：蓝色=蓝失败；绿色=绿失败；黄色=黄失败"
    }


@pytest.mark.parametrize(
    ("case", "reason"),
    [
        ("empty_capture", "截图空"),
        ("empty_crop", "裁剪为空"),
        ("insufficient_components", "连通域不足: 0"),
    ],
)
def testtext识别失败保留具体原因(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    case: str,
    reason: str,
) -> None:
    crop = "20,20,30,30" if case == "empty_crop" else "0,0,10,10"
    recognizer = text角度模块.角度识别器(str(_写校准(tmp_path, crop)))
    image = np.zeros((10, 10, 3), dtype=np.uint8)
    if case == "empty_capture":
        monkeypatch.setattr(recognizer, "截图", lambda: None)
        image = None

    assert recognizer.识别角度(图像数据=image) is None
    assert recognizer.最近详情 == {"error": reason}


def test缺少必需字段的校准返回明确失败而不抛keyerror(tmp_path: Path) -> None:
    calibration = tmp_path / "lv.txt"
    calibration.write_text("SRC_CROP:0,0,10,10\n", encoding="utf-8")
    recognizer = text角度模块.角度识别器(str(calibration))

    result = recognizer.识别角度(图像数据=np.zeros((10, 10, 3), dtype=np.uint8))

    assert result is None
    assert "校准缺少字段" in recognizer.最近详情["error"]


def testtext分析错误包含识别器具体原因(monkeypatch: pytest.MonkeyPatch) -> None:
    recognizer = SimpleNamespace(
        最近详情={"error": "连通域不足: 1"},
        识别角度=lambda **_kwargs: None,
    )
    monkeypatch.setattr(测试角度模块, "_text_recognizer", recognizer)

    with pytest.raises(RuntimeError, match="连通域不足: 1"):
        测试角度模块._analyze_image_text_raw(
            np.zeros((10, 10, 3), dtype=np.uint8),
            [],
            0,
            0,
            False,
            None,
        )


@pytest.mark.parametrize(
    ("arrow_color", "color_hex"),
    [("蓝色", "95BBE8"), ("绿色", "9AE77E"), ("黄色", "F0E791")],
)
def testtext分析结果传播实际箭头颜色(
    monkeypatch: pytest.MonkeyPatch,
    arrow_color: str,
    color_hex: str,
) -> None:
    recognizer = SimpleNamespace(
        最近详情={
            "origin": (1.0, 1.0),
            "target": (2.0, 2.0),
            "arrow_color": arrow_color,
        },
        识别角度=lambda **_kwargs: 123.0,
    )
    monkeypatch.setattr(测试角度模块, "_text_recognizer", recognizer)

    result = 测试角度模块._analyze_image_text_raw(
        np.zeros((10, 10, 3), dtype=np.uint8),
        [],
        0,
        0,
        False,
        None,
    )

    assert result.color_hex == color_hex
    assert result.arrow_color == arrow_color
