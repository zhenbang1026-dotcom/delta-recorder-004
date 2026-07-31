# Precise Waypoint Double-E Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 录制过程中双击 E 创建可编辑的精准路线点，回放必须在 1 像素坐标容差内恢复记录角度，否则安全停止路线。

**Architecture:** 在现有路线点末尾增加向后兼容的精准布尔标记，沿路线读写、自动抽稀和巡航内部模型传递。主界面旁路轮询 E 的独立按下沿并同步录制器状态；巡航复用动作点已有停稳、五次采样、三次低速补正和角度恢复，只对精准点增加严格失败判定。普通点和 Q 动作点的现有行为保持不变。

**Tech Stack:** Python 3.11、Tkinter、Win32 `GetAsyncKeyState`、JSONL、pytest

---

### Task 1: 精准点数据模型与自动路线保留

**Files:**
- Create: `tests/test_precise_waypoints.py`
- Modify: `路线动作.py:192-299`
- Modify: `巡航脚本.py:174-181,528-545,611-624`

- [ ] **Step 1: 写入路线模型失败测试**

在 `tests/test_precise_waypoints.py` 添加：

```python
import json
from pathlib import Path

import pytest

import 巡航脚本 as cruise
from 路线动作 import 路线动作, 路线点, 读取路线文件, 写入路线文件


def test_precise_point_roundtrip_and_normal_point_omits_false(tmp_path: Path) -> None:
    path = tmp_path / "route.jsonl"
    normal = 路线点(1, 2, 3.0, True)
    precise = 路线点(4, 5, 6.0, True, (), True)

    写入路线文件(path, [normal, precise])
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]

    assert "precise" not in records[1]
    assert records[2]["precise"] is True
    assert 读取路线文件(path) == [normal, precise]


def test_old_route_defaults_to_normal_and_rejects_non_boolean_precise(tmp_path: Path) -> None:
    old = tmp_path / "old.jsonl"
    old.write_text('{"version":2,"type":"route"}\n{"type":"point","x":1,"y":2,"auto":true,"actions":[]}\n', encoding="utf-8")
    assert 读取路线文件(old)[0].精准点 is False

    broken = tmp_path / "broken.jsonl"
    broken.write_text('{"version":2,"type":"route"}\n{"type":"point","x":1,"y":2,"precise":"yes","actions":[]}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="路线点格式错误"):
        读取路线文件(broken)


def test_replacing_actions_preserves_precise_flag() -> None:
    point = 路线点(1, 2, 3.0, True, (), True)
    changed = point.替换动作((路线动作("comment", {"text": "门口"}),))
    assert changed.精准点 is True
```

- [ ] **Step 2: 运行模型测试确认失败**

Run: `python -m pytest tests/test_precise_waypoints.py -q`

Expected: FAIL，`路线点` 还不接受第六个精准标记或没有 `精准点` 属性。

- [ ] **Step 3: 最小实现路线模型读写**

在 `路线动作.路线点` 的 `actions` 后增加：

```python
精准点: bool = False
```

在 `__post_init__` 中拒绝非布尔值；`替换动作()` 保留 `self.精准点`；新增：

```python
def 替换精准点(self, 精准点: bool) -> "路线点":
    return 路线点(self.x, self.y, self.angle, self.自动路线, self.actions, 精准点)
```

写入点记录时仅在 `point.精准点` 为真时增加 `record["precise"] = True`。读取时先取 `precise = data.get("precise", False)`，确认它是 `bool`，再作为第六个参数构造路线点。

- [ ] **Step 4: 写入抽稀保留失败测试**

继续添加：

```python
def test_cruise_keeps_precise_point_during_thinning(tmp_path: Path) -> None:
    path = tmp_path / "route.jsonl"
    points = [
        路线点(0, 0, 0.0, True),
        路线点(2, 0, 0.0, True, (), True),
        路线点(4, 0, 0.0, True),
        路线点(20, 0, 0.0, True),
    ]
    写入路线文件(path, points)

    loaded = cruise.读取路径(str(path), 自动路线点距=6)

    assert [(point.x, point.精准点) for point in loaded] == [
        (0, False), (2, True), (20, False)
    ]
```

Run: `python -m pytest tests/test_precise_waypoints.py::test_cruise_keeps_precise_point_during_thinning -q`

Expected: FAIL，巡航内部路径点没有精准标记或抽稀删除 x=2 的点。

- [ ] **Step 5: 传递精准标记并强制保留**

在 `巡航脚本.路径点` 的 `actions` 后增加 `精准点: bool = False`；JSONL 路线转换时传入 `点.精准点`；将抽稀保留条件改为：

```python
if 点.actions or 点.精准点 or 计算距离(上次保留.x, 上次保留.y, 点.x, 点.y) >= 最小点距:
```

- [ ] **Step 6: 运行模型与现有路线测试**

Run: `python -m pytest tests/test_precise_waypoints.py tests/test_route_actions.py tests/test_cruise_advanced_policy.py -q`

Expected: 全部 PASS。

### Task 2: 双击 E 录制与录制器同步

**Files:**
- Modify: `tests/test_precise_waypoints.py`
- Modify: `自动录制坐标工具.py:94-181`
- Modify: `主界面.py:203-281,875-947,1870-1991`

- [ ] **Step 1: 写入双击检测和强制记录失败测试**

添加：

```python
import 主界面 as main_ui
import 自动录制坐标工具 as recorder_module
from types import SimpleNamespace


def test_record_double_click_requires_two_distinct_presses_within_500ms() -> None:
    detector = main_ui.录制双击检测器(0.5)
    assert not detector.更新(True, 0.0)
    assert not detector.更新(True, 0.1)
    assert not detector.更新(False, 0.2)
    assert detector.更新(True, 0.49)


def test_precise_record_replaces_near_plain_point_and_appends_after_action() -> None:
    recorder = recorder_module.自动坐标录制器(最小记录距离=3)
    recorder.强制记录(10, 20)
    points = [路线点(10, 20, 1.0, True)]

    result = main_ui.记录或更新精准点(points, recorder, SimpleNamespace(x=11, y=20, angle=45.0))
    assert result == "更新"
    assert points == [路线点(11, 20, 45.0, True, (), True)]
    assert recorder.记录列表 == [(11, 20)]
    assert recorder.上一记录点 == (11, 20)

    points[-1] = points[-1].替换动作((路线动作("comment", {"text": "动作"}),))
    result = main_ui.记录或更新精准点(points, recorder, SimpleNamespace(x=12, y=20, angle=50.0))
    assert result == "新增"
    assert len(points) == 2 and points[-1].精准点 is True
    assert recorder.记录列表[-1] == (12, 20)
```

- [ ] **Step 2: 运行录制测试确认失败**

Run: `python -m pytest tests/test_precise_waypoints.py -q`

Expected: FAIL，缺少 `录制双击检测器`、`强制记录` 或 `记录或更新精准点`。

- [ ] **Step 3: 实现最小录制状态接口**

在 `自动坐标录制器` 增加：

```python
def 强制记录(self, x: int, y: int, *, 替换最后: bool = False) -> None:
    点 = (int(x), int(y))
    if 替换最后 and self.记录列表:
        self.记录列表[-1] = 点
    else:
        self.记录列表.append(点)
    self.上一记录点 = 点
    self._候选异常点 = None
    self._候选异常次数 = 0
```

在 `主界面.py` 增加只依赖传入状态的 `录制双击检测器` 和 `记录或更新精准点()`。后者只在最后一点无动作且距离小于录制器最小距离时替换，否则新增，并调用 `强制记录()` 同步坐标录制器。

- [ ] **Step 4: 写入主界面状态门和反馈失败测试**

添加一个通过 `object.__new__(合并主界面)` 构造的最小应用，断言：

```python
def test_precise_record_is_ignored_outside_active_recording(monkeypatch) -> None:
    app = object.__new__(main_ui.合并主界面)
    app.recording = False
    app.recording_paused = False
    app.current_state = SimpleNamespace(x=10, y=20, angle=30.0)
    app._recorded_route_points = []
    app.录制器 = recorder_module.自动坐标录制器()
    assert app._记录精准点() is False
    assert app._recorded_route_points == []


class ValueVar:
    def __init__(self, value="") -> None:
        self.value = value

    def get(self):
        return self.value

    def set(self, value) -> None:
        self.value = value


def test_precise_record_updates_ui_without_popup_or_focus(monkeypatch) -> None:
    app = object.__new__(main_ui.合并主界面)
    app.recording = True
    app.recording_paused = False
    app.current_state = SimpleNamespace(x=10, y=20, angle=30.0)
    app._recorded_route_points = []
    app.录制器 = recorder_module.自动坐标录制器()
    app.status_var = ValueVar()
    app._log_fn = None
    refreshed = []
    previews = []
    beeps = []
    app._refresh_points_text = lambda: refreshed.append(True)
    app._draw_preview = previews.append
    monkeypatch.setattr(main_ui.录制模块, "写日志", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(main_ui.winsound, "MessageBeep", lambda *_args: beeps.append(True))
    monkeypatch.setattr(
        main_ui.messagebox,
        "showinfo",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("不得弹窗")),
    )

    assert app._记录精准点() is True
    assert app._recorded_route_points == [路线点(10, 20, 30.0, True, (), True)]
    assert "10,20" in app.status_var.get()
    assert refreshed == [True]
    assert previews == [app.current_state]
    assert beeps == [True]
```

- [ ] **Step 5: 接入 E 轮询和录制反馈**

- 初始化 `self._e_detector = 录制双击检测器(0.5)`，每 50ms 调度 `_e_poll`。
- `_e_poll` 使用 `GetAsyncKeyState(ord("E"))` 和 `time.monotonic()`；检测成功时只调用 `_记录精准点()`，不拦截按键。
- `_记录精准点()` 再次检查录制状态和定位状态，调用纯函数，刷新列表与预览，设置状态，记录日志并用 `winsound.MessageBeep` 提示；提示音异常被忽略。
- 开始、停止、清空录制时重置检测器。
- `_refresh_points_text()` 为精准点增加 `[精准]`。
- `_draw_preview()` 在基础预览上用 BGR 红色 `(0, 0, 255)` 绘制精准点。

- [ ] **Step 6: 运行录制与主界面回归测试**

Run: `python -m pytest tests/test_precise_waypoints.py tests/test_main_ui_settings.py tests/test_ui_mode_defaults.py -q`

Expected: 全部 PASS。

### Task 3: 精准点严格回放与失败停止

**Files:**
- Modify: `tests/test_precise_waypoints.py`
- Modify: `巡航脚本.py:1596-1755`

- [ ] **Step 1: 写入精准成功与带动作顺序失败测试**

添加使用假定位器和假执行器的测试：

```python
def test_precise_waypoint_aligns_before_actions_and_switches_once(monkeypatch) -> None:
    comment = 路线动作("comment", {"text": "开门"})
    events = []

    class Locator:
        def 读取状态(self):
            return 10, 20, 31.5

    class Executor:
        def 执行(self, action):
            events.append(("move", action.类型))

        def 执行路线动作(self, actions):
            events.append(("actions", tuple(actions)))

        def 停止(self):
            events.append("stop")

    monkeypatch.setattr(cruise, "处理esc紧急停止", lambda _event=None: False)
    monkeypatch.setattr(cruise, "动作终点停稳秒数", 0.0)
    monkeypatch.setattr(cruise, "动作终点采样间隔秒数", 0.0)
    controller = cruise.巡航控制器(
        路径点列表=[cruise.路径点(10, 20, 30.0, True, (comment,), True)],
        定位器=Locator(), 执行器=Executor(), 到点阈值=3,
        参数=cruise.普通模式参数(), 循环间隔=0.0,
    )
    controller.运行()
    assert events == [
        ("move", "切换下一个点"),
        ("actions", (comment,)),
        "stop",
    ]
```

定位器返回 31.5 度，与记录角度相差 1.5 度；测试同时证明 2 度角度容差内不会产生额外转向。

- [ ] **Step 2: 写入精准失败停止且不执行动作测试**

```python
def test_precise_waypoint_failure_stops_route_and_skips_actions(monkeypatch) -> None:
    comment = 路线动作("comment", {"text": "不应执行"})
    events = []

    class Locator:
        def 读取状态(self):
            return 12, 20, 0.0

    class Executor:
        def 执行(self, action):
            events.append(("move", action.类型))

        def 执行路线动作(self, actions):
            events.append(("actions", tuple(actions)))

        def 停止(self):
            events.append("stop")

    monkeypatch.setattr(cruise, "处理esc紧急停止", lambda _event=None: False)
    monkeypatch.setattr(cruise, "动作终点停稳秒数", 0.0)
    monkeypatch.setattr(cruise, "动作终点采样间隔秒数", 0.0)
    monkeypatch.setattr(cruise, "动作终点转向等待秒数", 0.0)
    controller = cruise.巡航控制器(
        路径点列表=[cruise.路径点(10, 20, 0.0, True, (comment,), True)],
        定位器=Locator(), 执行器=Executor(), 到点阈值=3,
        参数=cruise.普通模式参数(), 循环间隔=0.0,
    )

    with pytest.raises(cruise.精准点到达失败, match="目标.*10,20.*最终.*12,20"):
        controller.运行()

    assert events.count(("move", "终点低速补正")) == 3
    assert not any(event[0] == "actions" for event in events if isinstance(event, tuple))
    assert events[-1] == "stop"
```

- [ ] **Step 3: 运行严格回放测试确认失败**

Run: `python -m pytest tests/test_precise_waypoints.py -q`

Expected: FAIL，精准点仍按普通点切换，或没有严格失败异常。

- [ ] **Step 4: 复用动作终点补正并增加严格验证**

新增：

```python
class 精准点到达失败(RuntimeError):
    pass
```

在控制器增加 `_执行精准点对准(点, 索引)`：调用现有 `_执行动作终点对准()`，计算最终坐标距离；超过 `动作终点坐标容差` 时写 `event=precise_waypoint_failed` 并抛出包含序号、目标、最终坐标和误差的异常，否则写成功日志并返回状态。

到点分支按以下顺序处理：

1. `当前点.精准点` 时执行严格精准对准，异常不吞掉。
2. 有动作且不是精准点时沿用当前 try/except 的宽松动作点对准。
3. 有动作时执行动作；精准失败时不会到达此步骤。
4. 末点和切点逻辑保持原样。

控制器现有 `finally: self.执行器.停止()` 负责释放全部输入。

- [ ] **Step 5: 运行精准、动作点和多路线回归**

Run: `python -m pytest tests/test_precise_waypoints.py tests/test_cruise_route_actions.py tests/test_multi_route_playback.py -q`

Expected: 全部 PASS；原动作点补正失败后仍执行动作。

### Task 4: 已保存路线的精准状态编辑

**Files:**
- Modify: `tests/test_precise_waypoints.py`
- Modify: `动作编辑器.py:948-1045`

- [ ] **Step 1: 写入路线编辑器切换失败测试**

添加不创建真实 Tk 的测试：

```python
import 动作编辑器 as editor


class SelectedList:
    def curselection(self):
        return (0,)


def test_route_editor_toggles_precise_without_changing_actions() -> None:
    comment = 路线动作("comment", {"text": "门口"})
    window = object.__new__(editor.路线编辑窗口)
    window.points = [路线点(1, 2, 3.0, True, (comment,))]
    window.listbox = SelectedList()
    refreshed = []
    window._刷新 = refreshed.append

    window._切换精准状态()

    assert window.points[0] == 路线点(1, 2, 3.0, True, (comment,), True)
    assert refreshed == [0]
```

- [ ] **Step 2: 运行编辑器测试确认失败**

Run: `python -m pytest tests/test_precise_waypoints.py::test_route_editor_toggles_precise_without_changing_actions -q`

Expected: FAIL，缺少 `_切换精准状态`。

- [ ] **Step 3: 增加列表标记和切换按钮**

- 路线列表每行在序号后显示 `[精准]` 或 `[普通]`。
- 按钮区增加“切换精准/普通”，调用 `_切换精准状态()`。
- 方法校验已选择点，调用 `point.替换精准点(not point.精准点)` 并刷新原索引。
- 保持坐标角度只读、动作编辑、保存和 Esc 自动保存流程不变。

- [ ] **Step 4: 运行编辑器与保存回归测试**

Run: `python -m pytest tests/test_precise_waypoints.py tests/test_action_editor_escape.py tests/test_route_actions.py -q`

Expected: 全部 PASS。

### Task 5: 全量验证与交付

**Files:**
- Verify: `路线动作.py`
- Verify: `自动录制坐标工具.py`
- Verify: `主界面.py`
- Verify: `巡航脚本.py`
- Verify: `动作编辑器.py`
- Verify: `tests/test_precise_waypoints.py`

- [ ] **Step 1: 运行精准点专项测试**

Run: `python -m pytest tests/test_precise_waypoints.py -q`

Expected: 全部 PASS。

- [ ] **Step 2: 运行全量测试**

Run: `python -m pytest -q`

Expected: 全部 PASS，0 failed。

- [ ] **Step 3: 检查语法、格式和提交范围**

Run:

```powershell
python -m py_compile 路线动作.py 自动录制坐标工具.py 主界面.py 巡航脚本.py 动作编辑器.py
git diff --check
git status --short
```

Expected: Python 编译退出码 0；`git diff --check` 无输出；只暂存上述五个实现文件、新测试文件和本计划/设计相关文档，不暂存 routes、img、maps、logs、截图或用户设置。

- [ ] **Step 4: 提交并推送实现**

```powershell
git add -- 路线动作.py 自动录制坐标工具.py 主界面.py 巡航脚本.py 动作编辑器.py tests/test_precise_waypoints.py
git commit -m "功能：支持双击E录制精准路线点"
git push origin feature/recorder-005
```

Expected: 提交成功；本地 HEAD 与 `origin/feature/recorder-005` 一致。
