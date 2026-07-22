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
| **角度双模式** | **旧算法**（颜色轮廓）+ **text 箭头**（HSV+连通域+加稳）；**截图方式不变** |
| **定位** | SIFT 与旧项目一致 |

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
| 角度模式 | legacy / text（截图方式不变） |

**不修改** 旧 py 文件，仅新建 `主界面.py` 做 UI 编排。

## 与 003 的区别

- **004**：纯旧算法 + 控制环性能优化（推荐对比旧项目手感）
- **003**：另有 text 角度模式切换等实验能力
