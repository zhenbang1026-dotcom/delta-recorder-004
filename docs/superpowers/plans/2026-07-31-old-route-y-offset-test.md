# Old Route Y Offset Test Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不修改源路线的前提下生成一份所有路径点 Y 坐标减 11 的测试路线，并证明其他路线数据未变化。

**Architecture:** 把源 JSONL 逐行解析为对象，仅对 `type == "point"` 的顶层 `y` 字段执行减 11，再以紧凑 JSONL 写入全新的目标文件。生成前后分别使用 SHA256、逐字段比较和项目现有 `读取路线文件()` 完成验证；测试路线只供本地实机回放，不纳入 Git。

**Tech Stack:** Python 3、JSONL、`hashlib`、项目现有 `路线动作.读取路线文件`

---

### Task 1: 核对输入和输出边界

**Files:**
- Read: `routes/主变电站右1出生点到井盖.jsonl`
- Must not exist: `routes/主变电站右1出生点到井盖_旧路线Y减11测试.jsonl`

- [ ] **Step 1: 记录源文件 SHA256，并确认目标文件不存在**

Run:

```powershell
$sourceRoute = 'routes\主变电站右1出生点到井盖.jsonl'
$testRoute = 'routes\主变电站右1出生点到井盖_旧路线Y减11测试.jsonl'
Get-FileHash -Algorithm SHA256 -LiteralPath $sourceRoute
Test-Path -LiteralPath $testRoute
```

Expected: 源文件返回一个 SHA256；目标文件返回 `False`。如果目标已存在，立即停止，禁止覆盖。

### Task 2: 生成最小转换副本

**Files:**
- Read: `routes/主变电站右1出生点到井盖.jsonl`
- Create: `routes/主变电站右1出生点到井盖_旧路线Y减11测试.jsonl`

- [ ] **Step 1: 逐行转换并创建目标文件**

对每个非空 JSONL 行执行：

```python
record = json.loads(raw_line)
if record.get("type") == "point":
    record["y"] = record["y"] - 11
```

使用 `ensure_ascii=False` 和紧凑分隔符重新序列化。只允许创建目标文件；不得写入源文件。

- [ ] **Step 2: 确认源文件 SHA256 没有变化**

Run:

```powershell
Get-FileHash -Algorithm SHA256 -LiteralPath 'routes\主变电站右1出生点到井盖.jsonl'
```

Expected: SHA256 与 Task 1 完全相同。

### Task 3: 验证转换结果和读取兼容性

**Files:**
- Verify: `routes/主变电站右1出生点到井盖.jsonl`
- Verify: `routes/主变电站右1出生点到井盖_旧路线Y减11测试.jsonl`
- Reuse: `路线动作.py:269`

- [ ] **Step 1: 逐行比较新旧记录**

验证脚本必须断言：

```python
assert len(source_records) == len(test_records)
assert len(source_points) == len(test_points) == 84
assert new_point["x"] == old_point["x"]
assert new_point["y"] == old_point["y"] - 11
assert {k: v for k, v in new_point.items() if k != "y"} == {
    k: v for k, v in old_point.items() if k != "y"
}
```

非 `point` 记录解析后的对象必须完全一致；任何断言失败都视为生成失败。

- [ ] **Step 2: 使用项目现有读取器加载测试路线**

Run:

```powershell
python -c "from 路线动作 import 读取路线文件; p=读取路线文件(r'routes\主变电站右1出生点到井盖_旧路线Y减11测试.jsonl'); assert len(p)==84; print(len(p))"
```

Expected: 输出 `84`，退出码为 0。

- [ ] **Step 3: 确认没有改动 Git 已跟踪代码**

Run:

```powershell
git status --short
```

Expected: 除既有用户未跟踪文件和新测试路线外，没有已跟踪文件变化。测试路线不执行 `git add`、不提交。
