# 普通自动中继点大角度转弯保持疾跑 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking.

**Goal:** 让“普通点转弯保持疾跑”覆盖普通自动中继点的大角度弯道，使人物保持 W+Shift 并通过现有连续视角控制器平滑转向。

**Architecture:** 保留 选择动作、近点保护和转向不收敛保护的原有职责，在巡航控制器中增加普通自动中继点资格判断，并在动作选择完成后把符合条件的 转向 或转向不收敛产生的 前进并微调 转换成 疾跑前进并微调。执行器不新增逻辑，继续使用现有疾跑分支和连续视角控制器，因此不会释放移动键。

**Tech Stack:** Python 3、pytest、现有 巡航脚本.py 巡航控制器、Win32执行器、连续视角控制器。

---

### Task 1: 为普通点大角度转弯添加失败测试

**Files:**

- Modify: tests/test_cruise_advanced_policy.py，在现有普通点转弯策略测试附近新增测试。
- Reference: 巡航脚本.py:1220-1277 的 巡航控制器 初始化，巡航脚本.py:1904-1927 的动作处理顺序。

- [ ] **Step 1: 添加普通自动中继点测试夹具**

在 tests/test_cruise_advanced_policy.py 增加以下辅助函数，确保被测索引既不是首点也不是最终点：

~~~python
def _普通点转弯控制器(*, enabled=True, points=None, segments=None):
    if points is None:
        points = [
            cruise.路径点(0, 0, 0.0, True),
            cruise.路径点(10, 0, 0.0, True),
            cruise.路径点(20, 0, 0.0, True),
        ]
    return cruise.巡航控制器(
        路径点列表=points,
        定位器=SimpleNamespace(),
        执行器=SimpleNamespace(),
        到点阈值=3,
        参数=cruise.普通模式参数(),
        普通点转弯保持疾跑=enabled,
        路线段列表=segments,
    )
~~~

- [ ] **Step 2: 添加大角度转换的失败测试**

添加以下测试。当前实现没有 _处理普通点转弯疾跑()，所以测试应先失败：

~~~python
@pytest.mark.parametrize("角度差", [45.0, 90.0, 120.0])
def test普通自动中继点大角度转向保持疾跑(角度差):
    控制器 = _普通点转弯控制器()
    原动作 = cruise.动作指令("转向", 鼠标像素=321)

    动作 = 控制器._处理普通点转弯疾跑(
        当前索引=1,
        动作=原动作,
    )

    assert 动作 == cruise.动作指令("疾跑前进并微调", 鼠标像素=321)


def test转向不收敛产生的普通微调也保持疾跑():
    控制器 = _普通点转弯控制器()
    控制器._转向不收敛触发 = True
    原动作 = cruise.动作指令("前进并微调", 鼠标像素=37)

    动作 = 控制器._处理普通点转弯疾跑(
        当前索引=1,
        动作=原动作,
    )

    assert 动作 == cruise.动作指令("疾跑前进并微调", 鼠标像素=37)
~~~

角度差参数用于覆盖 45°、90°、120° 三类急弯；动作转换本身保留原动作的鼠标像素，不重新计算或放大修正。

- [ ] **Step 3: 添加开关和保护边界的失败测试**

添加以下测试，固定关闭开关和受保护点不被转换：

~~~python
def test关闭普通点转弯疾跑时保持原地转向():
    控制器 = _普通点转弯控制器(enabled=False)
    原动作 = cruise.动作指令("转向", 鼠标像素=321)

    assert 控制器._处理普通点转弯疾跑(当前索引=1, 动作=原动作) == 原动作


@pytest.mark.parametrize("受保护点", [
    cruise.路径点(10, 0, 0.0, False),
    cruise.路径点(10, 0, 0.0, True, (路线动作("comment", {"text": "关键点"}),)),
    cruise.路径点(10, 0, 0.0, True, (), True),
])
def test非自动动作精准点不转换(受保护点):
    控制器 = _普通点转弯控制器(
        points=[cruise.路径点(0, 0, 0.0, True), 受保护点, cruise.路径点(20, 0, 0.0, True)],
    )
    原动作 = cruise.动作指令("转向", 鼠标像素=321)

    assert 控制器._处理普通点转弯疾跑(当前索引=1, 动作=原动作) == 原动作


def test路线段终点不转换():
    points = [
        cruise.路径点(0, 0, 0.0, True),
        cruise.路径点(10, 0, 0.0, True),
        cruise.路径点(20, 0, 0.0, True),
    ]
    segments = [
        cruise.路线段信息("one.jsonl", 0, 1),
        cruise.路线段信息("two.jsonl", 2, 2),
    ]
    控制器 = _普通点转弯控制器(points=points, segments=segments)
    原动作 = cruise.动作指令("转向", 鼠标像素=321)

    assert 控制器._处理普通点转弯疾跑(当前索引=1, 动作=原动作) == 原动作
~~~

- [ ] **Step 4: 添加执行器保持移动键的失败测试**

添加以下测试，证明转换动作走疾跑分支，不释放移动键：

~~~python
def test疾跑转弯动作保持移动键():
    输入 = 假输入模块()
    执行器 = cruise.Win32执行器(
        输入模块=输入,
        连续控制器工厂=lambda _input, **_kwargs: 假连续控制器(),
    )

    执行器.执行(cruise.动作指令("疾跑前进并微调", 鼠标像素=321))

    assert 输入.释放次数 == 0
    assert 执行器._正在前进 is True
    assert 执行器._本段已疾跑 is True
    执行器.停止()
~~~

- [ ] **Step 5: 运行新增定向测试确认先失败**

Run: pytest tests/test_cruise_advanced_policy.py -k "普通自动中继点大角度转向保持疾跑 or 转向不收敛产生的普通微调也保持疾跑 or 关闭普通点转弯疾跑 or 非自动动作精准点不转换 or 路线段终点不转换 or 疾跑转弯动作保持移动键" -q

Expected: 新增转换测试 FAIL，失败原因集中在巡航控制器尚未提供 _处理普通点转弯疾跑()；执行器保持移动键测试应通过。

### Task 2: 实现普通点大角度转弯疾跑转换

**Files:**

- Modify: 巡航脚本.py:1582-1637，在转向不收敛处理后增加普通点资格判断和动作转换。
- Modify: 巡航脚本.py:1904-1927，将转换函数接入现有动作流水线。
- Test: tests/test_cruise_advanced_policy.py 的 Task 1 测试。

- [ ] **Step 1: 增加普通自动中继点资格判断**

在 _处理转向不收敛() 后增加方法，使用控制器已有字段判断边界：

~~~python
def _是否普通自动中继点(self, 当前索引: int) -> bool:
    if not 0 < 当前索引 < len(self.路径点列表) - 1:
        return False
    if 当前索引 in self._中间段终点:
        return False
    当前点 = self.路径点列表[当前索引]
    return bool(
        当前点.自动路线
        and not 当前点.精准点
        and not 当前点.actions
    )
~~~

- [ ] **Step 2: 增加最小动作转换方法**

紧接资格判断方法增加：

~~~python
def _处理普通点转弯疾跑(self, *, 当前索引: int, 动作: 动作指令) -> 动作指令:
    if not self.普通点转弯保持疾跑 or not self._是否普通自动中继点(当前索引):
        return 动作
    if 动作.类型 == "转向" or (
        self._转向不收敛触发 and 动作.类型 == "前进并微调"
    ):
        return 动作指令(
            "疾跑前进并微调",
            鼠标像素=动作.鼠标像素,
            持续时间=动作.持续时间,
        )
    return 动作
~~~

该方法不重新计算转向像素，避免增加第二套角度控制；转向不收敛标志只在当前循环内有效，下一次非转向动作会由现有 _处理转向不收敛() 清理。

- [ ] **Step 3: 在运行循环中接入转换**

在 巡航控制器.运行() 中现有调用之后：

~~~python
动作 = self._处理转向不收敛(
    当前索引=当前索引,
    当前坐标=(x, y),
    距离=距离,
    角度差=角度差,
    动作=动作,
)
~~~

紧接增加：

~~~python
动作 = self._处理普通点转弯疾跑(
    当前索引=当前索引,
    动作=动作,
)
~~~

放置在诊断状态判断之前，确保日志记录最终执行动作；不调整动作选择、到点切换和越过点判定的顺序。

- [ ] **Step 4: 运行定向测试确认实现通过**

Run: pytest tests/test_cruise_advanced_policy.py -k "普通自动中继点大角度转向保持疾跑 or 转向不收敛产生的普通微调也保持疾跑 or 关闭普通点转弯疾跑 or 非自动动作精准点不转换 or 路线段终点不转换 or 疾跑转弯动作保持移动键" -q

Expected: PASS，新增加测试全部通过。

### Task 3: 完整回归与静态验证

**Files:**

- Verify: 巡航脚本.py
- Verify: tests/test_cruise_advanced_policy.py
- Do not stage: routes/、maps/、img/、logs/、实时截图.png

- [ ] **Step 1: 运行完整测试**

Run: pytest -q

Expected: 全部测试通过，原有测试不减少。

- [ ] **Step 2: 编译核心 Python 文件**

Run:

~~~powershell
python -m py_compile 巡航脚本.py 主界面.py 自动录制坐标工具.py 动作编辑器.py 路线动作.py 连续视角控制.py
~~~

Expected: 命令退出码为 0，无 traceback。

- [ ] **Step 3: 检查差异格式和变更范围**

Run:

~~~powershell
git diff --check
git status --short
git diff -- 巡航脚本.py tests/test_cruise_advanced_policy.py
~~~

Expected: git diff --check 无输出；差异只包含本功能代码和测试，用户路线、地图、截图、日志仍未被修改。

### Task 4: 提交并推送功能修改

**Files:**

- Stage only: 巡航脚本.py、tests/test_cruise_advanced_policy.py

- [ ] **Step 1: 只暂存本次相关文件**

Run: git add -- 巡航脚本.py tests/test_cruise_advanced_policy.py

Expected: git diff --cached --name-only 只显示上述两个文件。

- [ ] **Step 2: 创建中文提交**

Run: git commit -m "功能：普通点大角度转弯保持疾跑"

Expected: 新提交只包含巡航代码和相关测试。

- [ ] **Step 3: 推送当前分支**

Run: git push origin feature/recorder-005

Expected: 远端 origin/feature/recorder-005 更新成功。

- [ ] **Step 4: 记录交付信息**

记录提交哈希、提交消息、推送分支、测试结果，并说明实机复测需要观察：普通急弯是否仍出现 动作=转向、W/Shift 是否持续、精准点是否仍准确。
