# 普通路线点转弯疾跑与越过跳过 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为普通路线增加可选的中小角度转弯疾跑和越过普通点自动跳过，并保持所有关键点与旧路线默认跳点行为安全。

**Architecture:** 在现有 `巡航控制器` 内保存两个布尔策略，不改变动作指令和路线文件结构。转弯策略只影响近点微调动作是否保留疾跑类型；越过策略通过上一点、当前点、下一点的几何关系决定是否跳过当前普通点。主界面只负责创建、持久化并透传两个开关。

**Tech Stack:** Python 3.10+、Tkinter、pytest、现有 Win32 输入与巡航控制模块。

---

## 文件结构

- Modify: `巡航脚本.py` — 保存巡航策略、执行近点转弯策略、判断并跳过已越过普通点、记录诊断日志。
- Modify: `主界面.py` — 创建两个复选框、保存/恢复设置、启动回放时透传策略。
- Modify: `tests/test_cruise_advanced_policy.py` — 覆盖转弯速度、越过几何、关键点保护和巡航循环跳点行为。
- Modify: `tests/test_main_ui_settings.py` — 覆盖默认值、设置持久化和启动回放参数透传。

### Task 1: 可选的中小角度转弯疾跑

**Files:**
- Modify: `巡航脚本.py:1212-1273,1530-1542`
- Test: `tests/test_cruise_advanced_policy.py:268-292`

- [ ] **Step 1: 写入失败测试**

在 `tests/test_cruise_advanced_policy.py` 的近点微调测试后添加：

```python
@pytest.mark.parametrize(
    ("保持疾跑", "期望类型"),
    [(True, "疾跑前进并微调"), (False, "前进并微调")],
)
def test_near_point_turn_speed_respects_option(monkeypatch, 保持疾跑, 期望类型):
    设置模式(monkeypatch, "text")
    控制器 = cruise.巡航控制器(
        路径点列表=[cruise.路径点(8, 0, 0.0, True)],
        定位器=SimpleNamespace(),
        执行器=SimpleNamespace(),
        到点阈值=3,
        参数=cruise.普通模式参数(),
        普通点转弯保持疾跑=保持疾跑,
    )
    原动作 = cruise.选择动作(
        距离=8,
        角度差=20.0,
        到点阈值=3,
        参数=控制器.参数,
        自动路线=True,
    )

    动作 = 控制器._处理近点位转向(距离=8, 角度差=20.0, 动作=原动作)

    assert 原动作.类型 == "疾跑前进并微调"
    assert 动作.类型 == 期望类型
    assert 动作.鼠标像素 == 113


@pytest.mark.parametrize("保持疾跑", [True, False])
def test_large_angle_turn_still_stops_for_in_place_turn(monkeypatch, 保持疾跑):
    设置模式(monkeypatch, "text")
    控制器 = cruise.巡航控制器(
        路径点列表=[cruise.路径点(8, 0, 0.0, True)],
        定位器=SimpleNamespace(),
        执行器=SimpleNamespace(),
        到点阈值=3,
        参数=cruise.普通模式参数(),
        普通点转弯保持疾跑=保持疾跑,
    )
    原动作 = cruise.选择动作(
        距离=8,
        角度差=45.0,
        到点阈值=3,
        参数=控制器.参数,
        自动路线=True,
    )

    动作 = 控制器._处理近点位转向(距离=8, 角度差=45.0, 动作=原动作)

    assert 动作 == 原动作
    assert 动作.类型 == "转向"
```

- [ ] **Step 2: 运行测试并确认按预期失败**

Run:

```powershell
python -m pytest tests/test_cruise_advanced_policy.py::test_near_point_turn_speed_respects_option tests/test_cruise_advanced_policy.py::test_large_angle_turn_still_stops_for_in_place_turn -q
```

Expected: FAIL，错误为 `巡航控制器.__init__()` 不接受 `普通点转弯保持疾跑`。

- [ ] **Step 3: 写入最小实现**

在 `巡航控制器.__init__()` 的仅关键字参数中加入默认开启的参数并保存：

```python
        普通点转弯保持疾跑: bool = True,
```

```python
        self.普通点转弯保持疾跑 = bool(普通点转弯保持疾跑)
```

将 `_处理近点位转向()` 中生成近点微调动作的部分改为：

```python
            self._近点位保护触发 = True
            微调角度 = max(-增强近点位最大微调角度, min(增强近点位最大微调角度, 角度差))
            动作类型 = (
                "疾跑前进并微调"
                if self.普通点转弯保持疾跑
                and 动作.类型 in {"疾跑前进", "疾跑前进并微调"}
                else "前进并微调"
            )
            return 动作指令(
                动作类型,
                鼠标像素=text微调鼠标像素(微调角度, self.参数.精准缩放),
            )
```

- [ ] **Step 4: 运行相关测试并确认通过**

Run:

```powershell
python -m pytest tests/test_cruise_advanced_policy.py -q
```

Expected: PASS，现有近点角度限幅测试和新增两组模式测试全部通过。

- [ ] **Step 5: 提交并推送本阶段修改**

```powershell
git add -- '巡航脚本.py' 'tests/test_cruise_advanced_policy.py'
git diff --cached --check
git commit -m '修复：支持普通点转弯保持疾跑'
git push origin feature/recorder-005
```

### Task 2: 可选的越过普通点自动跳过

**Files:**
- Modify: `巡航脚本.py:1212-1273,1725-1803,1922-1978`
- Test: `tests/test_cruise_advanced_policy.py`

- [ ] **Step 1: 写入越过几何和保护范围的失败测试**

在 `tests/test_cruise_advanced_policy.py` 添加：

```python
def _越过控制器(points, *, enabled=True, segments=None):
    return cruise.巡航控制器(
        路径点列表=points,
        定位器=SimpleNamespace(),
        执行器=SimpleNamespace(),
        到点阈值=3,
        参数=cruise.普通模式参数(),
        越过普通点自动跳过=enabled,
        路线段列表=segments,
    )


def test_passed_plain_waypoint_is_skipped_only_when_next_is_closer():
    points = [
        cruise.路径点(0, 0, 0.0, True),
        cruise.路径点(10, 0, 0.0, True),
        cruise.路径点(20, 0, 0.0, True),
    ]
    控制器 = _越过控制器(points)

    assert 控制器._应跳过已越过普通点(当前索引=1, x=16, y=0, 距离=6)
    assert not 控制器._应跳过已越过普通点(当前索引=1, x=14, y=0, 距离=4)


def test_passed_waypoint_option_defaults_to_disabled():
    points = [
        cruise.路径点(0, 0, 0.0, True),
        cruise.路径点(10, 0, 0.0, True),
        cruise.路径点(20, 0, 0.0, True),
    ]
    控制器 = _越过控制器(points, enabled=False)

    assert not 控制器._应跳过已越过普通点(当前索引=1, x=16, y=0, 距离=6)


@pytest.mark.parametrize(
    "受保护点",
    [
        cruise.路径点(10, 0, 0.0, False),
        cruise.路径点(10, 0, 0.0, True, (路线动作("comment", {"text": "关键点"}),)),
        cruise.路径点(10, 0, 0.0, True, (), True),
    ],
)
def test_manual_action_and_precise_waypoints_are_never_skipped(受保护点):
    控制器 = _越过控制器(
        [cruise.路径点(0, 0, 0.0, True), 受保护点, cruise.路径点(20, 0, 0.0, True)]
    )

    assert not 控制器._应跳过已越过普通点(当前索引=1, x=16, y=0, 距离=6)


def test_first_final_and_intermediate_segment_endpoints_are_never_skipped():
    points = [
        cruise.路径点(0, 0, 0.0, True),
        cruise.路径点(10, 0, 0.0, True),
        cruise.路径点(20, 0, 0.0, True),
    ]
    segments = [
        cruise.路线段信息("part1.jsonl", 0, 1),
        cruise.路线段信息("part2.jsonl", 2, 2),
    ]
    控制器 = _越过控制器(points, segments=segments)

    assert not 控制器._应跳过已越过普通点(当前索引=0, x=6, y=0, 距离=6)
    assert not 控制器._应跳过已越过普通点(当前索引=1, x=16, y=0, 距离=6)
    assert not 控制器._应跳过已越过普通点(当前索引=2, x=26, y=0, 距离=6)


def test_corner_overshoot_is_not_skipped_when_current_point_is_closer():
    points = [
        cruise.路径点(0, 0, 0.0, True),
        cruise.路径点(10, 0, 0.0, True),
        cruise.路径点(10, 10, 0.0, True),
    ]
    控制器 = _越过控制器(points)

    assert not 控制器._应跳过已越过普通点(当前索引=1, x=16, y=0, 距离=6)
```

- [ ] **Step 2: 运行测试并确认按预期失败**

Run:

```powershell
python -m pytest tests/test_cruise_advanced_policy.py -k 'passed or skipped or overshoot or endpoints' -q
```

Expected: FAIL，原因是构造函数没有 `越过普通点自动跳过` 参数且 `_应跳过已越过普通点` 尚不存在。

- [ ] **Step 3: 实现最小越过判断**

在 `巡航控制器.__init__()` 加入并保存：

```python
        越过普通点自动跳过: bool = False,
```

```python
        self.越过普通点自动跳过 = bool(越过普通点自动跳过)
```

在 `巡航控制器` 中添加：

```python
    def _应跳过已越过普通点(
        self,
        *,
        当前索引: int,
        x: int,
        y: int,
        距离: int,
    ) -> bool:
        if (
            not self.越过普通点自动跳过
            or 当前索引 <= 0
            or 当前索引 >= len(self.路径点列表) - 1
            or 当前索引 in self._中间段终点
            or 距离 <= self.到点阈值
        ):
            return False
        上一点 = self.路径点列表[当前索引 - 1]
        当前点 = self.路径点列表[当前索引]
        下一点 = self.路径点列表[当前索引 + 1]
        if not 当前点.自动路线 or 当前点.精准点 or 当前点.actions:
            return False
        入向量_x = 当前点.x - 上一点.x
        入向量_y = 当前点.y - 上一点.y
        if 入向量_x == 0 and 入向量_y == 0:
            return False
        已越过 = (x - 当前点.x) * 入向量_x + (y - 当前点.y) * 入向量_y > 0
        下一点距离 = 计算距离(x, y, 下一点.x, 下一点.y)
        return 已越过 and 下一点距离 < 距离
```

- [ ] **Step 4: 写入巡航循环跳点的失败测试**

在同一测试文件添加：

```python
def test_run_skips_passed_plain_waypoint_without_stopping(monkeypatch):
    monkeypatch.setattr(cruise, "处理esc紧急停止", lambda _event=None: False)
    states = iter([(0, 0, 0.0), (16, 0, 0.0), (20, 0, 0.0)])
    events = []
    logs = []

    class 定位器:
        def 读取状态(self):
            return next(states)

    class 执行器:
        def 执行(self, 动作):
            events.append(动作.类型)

        def 停止(self):
            events.append("停止")

    控制器 = cruise.巡航控制器(
        路径点列表=[
            cruise.路径点(0, 0, 0.0, True),
            cruise.路径点(10, 0, 0.0, True),
            cruise.路径点(20, 0, 0.0, True),
        ],
        定位器=定位器(),
        执行器=执行器(),
        到点阈值=3,
        参数=cruise.普通模式参数(),
        越过普通点自动跳过=True,
        循环间隔=0.0,
        日志函数=lambda event, **fields: logs.append((event, fields)),
    )

    控制器.运行()

    assert events == ["自动路线切换下一个点", "自动路线切换下一个点", "停止"]
    skipped = next(fields for event, fields in logs if event == "event=waypoint_skipped")
    assert skipped["目标"] == "10,0"
    assert skipped["下一目标"] == "20,0"
```

- [ ] **Step 5: 运行巡航循环测试并确认按预期失败**

Run:

```powershell
python -m pytest tests/test_cruise_advanced_policy.py::test_run_skips_passed_plain_waypoint_without_stopping -q
```

Expected: FAIL，因为巡航循环尚未调用越过判断，人物会对已越过目标执行转向。

- [ ] **Step 6: 在巡航循环中执行一次安全跳点**

在 `距离 = 计算距离(...)` 和原有 `if 距离 <= self.到点阈值:` 之间加入：

```python
                if self._应跳过已越过普通点(
                    当前索引=当前索引,
                    x=x,
                    y=y,
                    距离=距离,
                ):
                    下一点 = self.路径点列表[当前索引 + 1]
                    下一点距离 = 计算距离(x, y, 下一点.x, 下一点.y)
                    设置控制诊断状态(self.定位器, "已越过普通点，切换下一点")
                    写日志(
                        self.日志函数,
                        "event=waypoint_skipped",
                        索引=当前索引,
                        坐标=f"{x},{y}",
                        目标=f"{当前点.x},{当前点.y}",
                        下一目标=f"{下一点.x},{下一点.y}",
                        当前点距离=距离,
                        下一点距离=下一点距离,
                    )
                    if self.记录器 is not None:
                        self.记录器.记录(
                            事件="waypoint_skipped",
                            索引=当前索引,
                            坐标=f"{x},{y}",
                            目标=f"{当前点.x},{当前点.y}",
                            下一目标=f"{下一点.x},{下一点.y}",
                            当前点距离=距离,
                            下一点距离=下一点距离,
                        )
                    self.执行器.执行(动作指令("自动路线切换下一个点"))
                    当前索引 += 1
                    continue
```

- [ ] **Step 7: 运行高级巡航策略测试并确认通过**

Run:

```powershell
python -m pytest tests/test_cruise_advanced_policy.py -q
```

Expected: PASS，越过判断、关键点保护、日志和原有巡航策略测试全部通过。

- [ ] **Step 8: 提交并推送本阶段修改**

```powershell
git add -- '巡航脚本.py' 'tests/test_cruise_advanced_policy.py'
git diff --cached --check
git commit -m '功能：支持跳过已越过的普通路线点'
git push origin feature/recorder-005
```

### Task 3: 主界面开关、设置持久化与参数透传

**Files:**
- Modify: `主界面.py:308-330,588-615,684-778,1061-1111`
- Modify: `巡航脚本.py:1922-1978`
- Test: `tests/test_main_ui_settings.py:72-89,171-225,260-315,360-430`
- Test: `tests/test_cruise_advanced_policy.py:202-233`

- [ ] **Step 1: 写入 UI 默认值、设置持久化和参数透传的失败测试**

在 `_settings_app()` 中添加与真实 UI 相同的默认变量：

```python
    app.turn_sprint_var = _Var(True)
    app.skip_passed_waypoint_var = _Var(False)
```

在 `test有效配置可保存并完整恢复` 中保存非默认组合：

```python
    app.turn_sprint_var.set(False)
    app.skip_passed_waypoint_var.set(True)
```

并在期望 JSON 字典和恢复断言中加入：

```python
        "普通点转弯保持疾跑": False,
        "越过普通点自动跳过": True,
```

```python
    assert restored.turn_sprint_var.get() is False
    assert restored.skip_passed_waypoint_var.get() is True
```

在非法配置参数中加入非布尔值，并断言保持默认值：

```python
                "普通点转弯保持疾跑": "yes",
                "越过普通点自动跳过": 1,
```

```python
    assert app.turn_sprint_var.get() is True
    assert app.skip_passed_waypoint_var.get() is False
```

在 `test开始回放自动停止识别并延迟透传倍率` 执行前设置：

```python
    app.turn_sprint_var.set(False)
    app.skip_passed_waypoint_var.set(True)
```

并在调用断言中加入：

```python
    assert cruise_calls[0][1]["普通点转弯保持疾跑"] is False
    assert cruise_calls[0][1]["越过普通点自动跳过"] is True
```

在 `test_cruise_advanced_policy.py` 的 `test_cruise_passes_speed_multiplier_to_win32_executor` 附近新增巡航参数透传测试：

```python
def test_cruise_passes_normal_waypoint_options_to_controller(monkeypatch):
    received = {}

    class 假巡航控制器:
        def __init__(self, **kwargs):
            received.update(kwargs)

        def 运行(self):
            pass

    monkeypatch.setattr(cruise, "读取路径", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(cruise, "重置每度像素校准", lambda *_args: None)
    monkeypatch.setattr(cruise, "寻路记录器", lambda: None)
    monkeypatch.setattr(cruise, "Win32执行器", lambda **_kwargs: object())
    monkeypatch.setattr(cruise, "巡航控制器", 假巡航控制器)

    cruise.巡航(
        "route.txt",
        定位器=object(),
        普通点转弯保持疾跑=False,
        越过普通点自动跳过=True,
    )

    assert received["普通点转弯保持疾跑"] is False
    assert received["越过普通点自动跳过"] is True
```

- [ ] **Step 2: 运行测试并确认按预期失败**

Run:

```powershell
python -m pytest tests/test_main_ui_settings.py tests/test_cruise_advanced_policy.py::test_cruise_passes_normal_waypoint_options_to_controller -q
```

Expected: FAIL，保存字典缺少两个字段，`巡航()` 也不接受两个新参数。

- [ ] **Step 3: 创建 UI 变量和复选框**

在 `合并主界面.__init__()` 的 `precise_var` 后添加：

```python
        self.turn_sprint_var = tk.BooleanVar(value=True)
        self.skip_passed_waypoint_var = tk.BooleanVar(value=False)
```

在回放按钮行 `r2` 后新增单独策略行，避免挤压已有控件：

```python
        route_options = ttk.Frame(cruise)
        route_options.pack(fill="x", pady=(6, 0))
        ttk.Label(route_options, text="普通点策略:").pack(side="left")
        ttk.Checkbutton(
            route_options,
            text="转弯保持疾跑",
            variable=self.turn_sprint_var,
        ).pack(side="left", padx=(6, 14))
        ttk.Checkbutton(
            route_options,
            text="越过普通点自动跳过",
            variable=self.skip_passed_waypoint_var,
        ).pack(side="left")
```

- [ ] **Step 4: 保存和恢复两个布尔设置**

在 `_load_settings()` 的精准模式读取后添加：

```python
        turn_sprint = data.get("普通点转弯保持疾跑")
        if isinstance(turn_sprint, bool):
            self.turn_sprint_var.set(turn_sprint)

        skip_passed = data.get("越过普通点自动跳过")
        if isinstance(skip_passed, bool):
            self.skip_passed_waypoint_var.set(skip_passed)
```

在 `_save_settings()` 的 `data` 字典中添加：

```python
            "普通点转弯保持疾跑": bool(self.turn_sprint_var.get()),
            "越过普通点自动跳过": bool(self.skip_passed_waypoint_var.get()),
```

- [ ] **Step 5: 从主界面透传到巡航控制器**

在 `start_cruise()` 创建工作线程前读取：

```python
        普通点转弯保持疾跑 = bool(self.turn_sprint_var.get())
        越过普通点自动跳过 = bool(self.skip_passed_waypoint_var.get())
```

在 `巡航模块.巡航()` 调用中加入：

```python
                    普通点转弯保持疾跑=普通点转弯保持疾跑,
                    越过普通点自动跳过=越过普通点自动跳过,
```

在 `巡航()` 签名中加入默认值：

```python
    普通点转弯保持疾跑: bool = True,
    越过普通点自动跳过: bool = False,
```

在 `巡航控制器(...)` 构造调用中加入：

```python
        普通点转弯保持疾跑=普通点转弯保持疾跑,
        越过普通点自动跳过=越过普通点自动跳过,
```

- [ ] **Step 6: 运行相关测试并确认通过**

Run:

```powershell
python -m pytest tests/test_main_ui_settings.py tests/test_cruise_advanced_policy.py -q
```

Expected: PASS，两个设置的默认值、持久化、独立透传与巡航策略测试全部通过。

- [ ] **Step 7: 执行完整自动验证**

Run:

```powershell
python -m pytest -q
python -m py_compile '巡航脚本.py' '主界面.py'
git diff --check
```

Expected: 全部测试通过，两个 Python 文件编译成功，`git diff --check` 无输出。

- [ ] **Step 8: 检查改动范围并提交推送**

Run:

```powershell
git status --short
git diff -- '巡航脚本.py' '主界面.py' 'tests/test_cruise_advanced_policy.py' 'tests/test_main_ui_settings.py'
git add -- '巡航脚本.py' '主界面.py' 'tests/test_cruise_advanced_policy.py' 'tests/test_main_ui_settings.py'
git diff --cached --check
git commit -m '功能：增加普通点转弯与越过策略开关'
git push origin feature/recorder-005
```

Expected: 提交仅包含上述 4 个任务文件；用户路线、地图、截图、日志和运行产物均不暂存。

## 实机验收

使用 `routes/主变电站右1出生点到井盖.jsonl` 依次测试：

1. 转弯疾跑开、越过跳过关：中小角度转弯保持疾跑，越过点仍返回。
2. 转弯疾跑关、越过跳过关：保持原有慢走转弯与返回行为。
3. 转弯疾跑开、越过跳过开：中小角度保持疾跑，明确越过普通点后继续前往下一点。
4. 转弯疾跑关、越过跳过开：慢走转弯，但明确越过普通点后不回头。
5. 四种组合下，大角度转弯都停车调整，精准点、动作点、任一路线段终点和最终终点都不跳过。
