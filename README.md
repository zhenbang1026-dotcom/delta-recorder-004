# 三角洲录制器004

从 `changhe/services/navigation/legacy_delta` **完整复制** 后的独立优化版。

> **旧项目代码未修改。** 所有改动只在本目录。

## 相对旧版做了什么（仅 004）

| 优化 | 说明 |
|------|------|
| **稳定截图** | `截图模块.py`：默认 GDI → mss → PIL，不 sleep 重试 |
| **并集一截两裁** | 小地图+角度一次截图，内存裁切 |
| **寻路暂停 UI 识别** | 巡航中 UI 只显示缓存，不抢控制环 |
| **日志缓冲** | 普通 step 批量写盘，关键事件立即落盘 |
| **角度三模式** | **Legacy**（旧颜色轮廓）+ **TEXT**（MAP 校准箭头）+ **Fusion**（双算法交叉验证）；**截图方式不变** |
| **TEXT/Fusion 控制优化** | 连续限速、限加速度与近点保护，减少左右反复修正（见下） |
| **定位** | SIFT 与旧项目一致 |

### 角度三模式与默认值

程序每次启动都默认使用 **Legacy**，不会因为新增算法改变原有稳定模式：

- **Legacy**：保留旧颜色轮廓识别、ROI、路线与控制参数，作为默认模式。
- **TEXT**：使用雷达箭头识别，并通过 `校准截图/lv.txt` 中的 `MAP` 数据做圆周角校准。
- **Fusion**：以校准后的 TEXT 为主观测，用 Legacy 交叉验证；TEXT 异常或连续失败时降级到 Legacy，恢复稳定后再切回 TEXT。

### TEXT/Fusion 连续控制

水平滑动标定仍为 **33.3 像素 ≈ 1°**。TEXT/Fusion 使用连续控制：

- 固定标定尺 `33.3 px/°`，避免在线标定漂移。
- 对鼠标转向限速度、限加速度，抑制相邻控制周期反向振荡。
- 接近路线点时限制大角度转向，优先连续前进微调。
- Legacy 继续使用原有控制分支，不受 TEXT/Fusion 参数影响。

## 运行

```powershell
cd "D:\Azhuomian\GitHub\三角洲项目相关文件\三角洲录制器004"
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
# 推荐：合并主界面（录制 + 回放）
.\.venv\Scripts\python 主界面.py
# 或双击 start.bat
```

也可单独跑旧入口（未改逻辑）：

```powershell
.\.venv\Scripts\python 巡航脚本.py
.\.venv\Scripts\python 自动录制坐标工具.py
```

可选环境变量：`DELTA_CAPTURE_BACKEND=gdi|mss|pil`

## 合并主界面（主界面.py）

| 功能 | 说明 |
|------|------|
| 开始/停止识别 | 实时坐标+角度 |
| 开始/停止录制 | 防跳变抽稀，保存到 `录制结果/` 与 `routes/` |
| 路线列表 | 自动汇总 `routes/` + `录制结果/` |
| 开始/停止回放 | 调用旧 `巡航()`，Esc 紧急停止 |
| 角度模式 | legacy / text / fusion；默认 legacy（截图方式不变） |

`主界面.py` 统一编排三个模式；独立录制与巡航入口也提供相同选择，启动默认值均为 Legacy。

## 与 003 的区别

- **004**：Legacy 默认保留，并增加校准 TEXT、Fusion 与连续控制，方便三模式对比
- **003**：另有 text 角度模式切换等实验能力
