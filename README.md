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
| **算法** | 与旧项目一致（legacy 颜色角度 + SIFT 定位） |

## 运行

```powershell
cd "D:\Azhuomian\GitHub\三角洲项目相关文件\三角洲录制器004"
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
.\.venv\Scripts\python 巡航脚本.py
.\.venv\Scripts\python 自动录制坐标工具.py
```

可选环境变量：`DELTA_CAPTURE_BACKEND=gdi|mss|pil`

## 与 003 的区别

- **004**：纯旧算法 + 控制环性能优化（推荐对比旧项目手感）
- **003**：另有 text 角度模式切换等实验能力
