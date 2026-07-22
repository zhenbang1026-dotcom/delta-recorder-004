# -*- coding: utf-8 -*-
"""
legacy vs text 巡航日志对照分析（只读，不改寻路）。

用法:
  python 分析巡航对照.py
  python 分析巡航对照.py --legacy logs/a.log --text logs/b.log
  python 分析巡航对照.py --csv logs/对照结果.csv
  python 分析巡航对照.py logs/巡航工具_1.log logs/巡航工具_2.log
"""
from __future__ import annotations

import argparse
import csv
import math
import re
import statistics
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Sequence, Tuple


ROOT = Path(__file__).resolve().parent
LOG_DIR = ROOT / "logs"

RE_TS = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})")
RE_EVENT = re.compile(r"event=([^\s|]+)")
RE_KV = re.compile(r"\|\s*([^=|]+)=([^|]*)")


def _parse_ts(line: str) -> Optional[datetime]:
    m = RE_TS.match(line.strip())
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1).strip(), "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def _kv(line: str) -> dict:
    out = {}
    for k, v in RE_KV.findall(line):
        out[k.strip()] = v.strip()
    return out


def _f(s: Optional[str]) -> Optional[float]:
    if s is None or s in ("--", "", "None"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _ang_delta(a: float, b: float) -> float:
    d = abs(b - a) % 360.0
    return d if d <= 180.0 else 360.0 - d


@dataclass
class CruiseStats:
    path: Path
    label: str = ""
    lines: int = 0
    steps: int = 0
    turn_waits: int = 0
    duration_s: float = 0.0
    actions: Counter = field(default_factory=Counter)
    control_diag: Counter = field(default_factory=Counter)
    angle_abs: List[float] = field(default_factory=list)
    angle_seq: List[float] = field(default_factory=list)
    jump25: int = 0
    turn_reject: int = 0
    turn_not_converge: int = 0
    turn_not_accept: int = 0
    escape: int = 0  # 脱困 + 绕行脱困
    retry: int = 0
    coord_jump: int = 0
    state_reuse: int = 0
    identify_fail_hint: int = 0
    completed_hint: str = "未知"

    @property
    def steps_per_s(self) -> float:
        return self.steps / self.duration_s if self.duration_s > 0 else 0.0

    def action_ratio(self, name: str) -> float:
        return self.actions.get(name, 0) / self.steps if self.steps else 0.0

    def turn_ratio(self) -> float:
        return self.action_ratio("转向")

    def fine_ratio(self) -> float:
        n = self.actions.get("前进并微调", 0) + self.actions.get("疾跑前进并微调", 0)
        return n / self.steps if self.steps else 0.0

    def sprint_ratio(self) -> float:
        return self.action_ratio("疾跑前进")


def analyze_log(path: Path, label: str = "") -> CruiseStats:
    text = path.read_text(encoding="utf-8", errors="ignore")
    lines = text.splitlines()
    st = CruiseStats(path=path, label=label or path.name, lines=len(lines))
    times: List[datetime] = []

    for line in lines:
        ev_m = RE_EVENT.search(line)
        ev = ev_m.group(1) if ev_m else ""
        kv = _kv(line)
        ts = _parse_ts(line)

        if ev == "step":
            st.steps += 1
            if ts:
                times.append(ts)
            act = kv.get("动作", "")
            if act:
                st.actions[act] += 1
            cd = kv.get("控制诊断", "")
            if cd:
                st.control_diag[cd] += 1
            ad = _f(kv.get("角度差"))
            if ad is not None:
                st.angle_abs.append(abs(ad))
            ang = _f(kv.get("当前角度"))
            if ang is not None:
                st.angle_seq.append(ang)
            if "脱困" in act:
                st.escape += 1
            diag = kv.get("识别诊断", "")
            if "失败" in diag or "无法" in diag:
                st.identify_fail_hint += 1

        elif ev == "turn_wait":
            st.turn_waits += 1
            reason = kv.get("拒绝原因", "--")
            if reason and reason != "--":
                st.turn_reject += 1
            if kv.get("是否收敛") == "否":
                st.turn_not_converge += 1
            if kv.get("是否采信") == "否":
                st.turn_not_accept += 1

        elif ev == "retry":
            st.retry += 1
        elif ev == "coord_jump":
            st.coord_jump += 1
        elif ev == "state_reuse":
            st.state_reuse += 1

        # 控制诊断里的脱困
        if "脱困" in line and ev == "step":
            pass  # already counted via 动作

    if len(times) >= 2:
        st.duration_s = max(0.0, (times[-1] - times[0]).total_seconds())
    elif times:
        st.duration_s = 1.0

    for i in range(1, len(st.angle_seq)):
        if _ang_delta(st.angle_seq[i - 1], st.angle_seq[i]) >= 25.0:
            st.jump25 += 1

    # 完成启发式：最后 step 目标索引是否接近尾
    last_targets = []
    for line in reversed(lines):
        if "event=step" not in line:
            continue
        kv = _kv(line)
        t = kv.get("目标", "")
        m = re.search(r"(\d+)\s*/\s*(\d+)", t)
        if m:
            last_targets.append((int(m.group(1)), int(m.group(2))))
            break
    if last_targets:
        i, n = last_targets[0]
        if i >= n:
            st.completed_hint = "像是走完/到末点附近"
        elif i >= max(1, int(n * 0.85)):
            st.completed_hint = f"接近终点 ({i}/{n})"
        else:
            st.completed_hint = f"中途结束 ({i}/{n})"

    return st


def _pct(x: float) -> str:
    return f"{x * 100:.1f}%"


def _stat_list(xs: List[float]) -> str:
    if not xs:
        return "n/a"
    xs_sorted = sorted(xs)
    mean = statistics.mean(xs)
    med = statistics.median(xs)
    p90 = xs_sorted[int(0.9 * (len(xs_sorted) - 1))]
    return f"mean={mean:.1f} med={med:.1f} p90={p90:.1f}"


def print_report(stats: Sequence[CruiseStats]) -> None:
    print("=" * 72)
    print("  巡航对照分析（legacy vs text 请人工标注标签）")
    print("=" * 72)
    for st in stats:
        print(f"\n### {st.label}")
        print(f"  文件: {st.path}")
        print(f"  时长: {st.duration_s:.1f}s | steps: {st.steps} | step/s: {st.steps_per_s:.2f}")
        print(f"  完成启发: {st.completed_hint}")
        print(f"  转向占比: {_pct(st.turn_ratio())} ({st.actions.get('转向', 0)})")
        print(f"  微调占比: {_pct(st.fine_ratio())}")
        print(f"  疾跑占比: {_pct(st.sprint_ratio())}")
        print(f"  turn_wait: {st.turn_waits} | 拒绝: {st.turn_reject} | 不收敛: {st.turn_not_converge} | 不采信: {st.turn_not_accept}")
        print(f"  脱困类动作: {st.escape} | retry: {st.retry} | coord_jump: {st.coord_jump}")
        print(f"  角差|·|: {_stat_list(st.angle_abs)}")
        print(f"  帧间角度跳变≥25°: {st.jump25}")
        print(f"  动作 Top: {st.actions.most_common(6)}")
        print(f"  控制诊断 Top: {st.control_diag.most_common(5)}")

    if len(stats) >= 2:
        a, b = stats[0], stats[1]
        print("\n" + "=" * 72)
        print("  对比摘要 (A = 第1个, B = 第2个)")
        print("=" * 72)
        rows = [
            ("时长 s", a.duration_s, b.duration_s, "越短越好（同路线）"),
            ("step/s", a.steps_per_s, b.steps_per_s, "越高通常越流畅"),
            ("转向占比", a.turn_ratio(), b.turn_ratio(), "text 若显著更高→停车转向过多"),
            ("微调占比", a.fine_ratio(), b.fine_ratio(), "legacy 常更高→边跑边修"),
            ("turn_wait", a.turn_waits, b.turn_waits, "越多越停"),
            ("turn 拒绝", a.turn_reject, b.turn_reject, "高→确认环振荡/滤波滞后"),
            ("脱困", a.escape, b.escape, "高→位移不足卡死"),
            ("角差 mean", statistics.mean(a.angle_abs) if a.angle_abs else float("nan"),
             statistics.mean(b.angle_abs) if b.angle_abs else float("nan"),
             "text 更低仍卡 → 准≠好控"),
            ("跳变≥25°", a.jump25, b.jump25, "text 更低仍卡 → 主因非抖"),
        ]
        print(f"  {'指标':<12} {'A':>12} {'B':>12}  解读")
        for name, va, vb, tip in rows:
            def fmt(v):
                if isinstance(v, float):
                    if math.isnan(v):
                        return "n/a"
                    if 0 <= v <= 1 and name.endswith("占比"):
                        return _pct(v)
                    return f"{v:.2f}"
                return str(v)
            print(f"  {name:<12} {fmt(va):>12} {fmt(vb):>12}  {tip}")

        print("\n  【快速判定】")
        # heuristics
        if b.turn_ratio() > a.turn_ratio() + 0.05 and b.escape >= a.escape:
            print("  → 符合「text 更易阻塞转向 + 脱困」假设（若 B 为 text）")
        if b.turn_reject > a.turn_reject + 2:
            print("  → turn_wait 拒绝偏多：重点看滤波/确认环，而非换整套寻路")
        if (a.angle_abs and b.angle_abs
                and statistics.mean(b.angle_abs) < statistics.mean(a.angle_abs)
                and b.turn_ratio() > a.turn_ratio()):
            print("  → 角差更小但转向更多：精度↑ 触发停车阈值↑，控制未按 text 整形")
        if b.jump25 < a.jump25 and b.escape > a.escape:
            print("  → 跳变更少却更脱困：主因不是角度抖，是控制停步/确认")
        print("=" * 72)


def write_csv(stats: Sequence[CruiseStats], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "label", "file", "duration_s", "steps", "steps_per_s", "completed_hint",
        "turn_ratio", "fine_ratio", "sprint_ratio",
        "turn_waits", "turn_reject", "turn_not_converge", "escape",
        "angle_mean", "angle_med", "jump25", "retry",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for st in stats:
            w.writerow({
                "label": st.label,
                "file": str(st.path),
                "duration_s": f"{st.duration_s:.2f}",
                "steps": st.steps,
                "steps_per_s": f"{st.steps_per_s:.3f}",
                "completed_hint": st.completed_hint,
                "turn_ratio": f"{st.turn_ratio():.4f}",
                "fine_ratio": f"{st.fine_ratio():.4f}",
                "sprint_ratio": f"{st.sprint_ratio():.4f}",
                "turn_waits": st.turn_waits,
                "turn_reject": st.turn_reject,
                "turn_not_converge": st.turn_not_converge,
                "escape": st.escape,
                "angle_mean": f"{statistics.mean(st.angle_abs):.2f}" if st.angle_abs else "",
                "angle_med": f"{statistics.median(st.angle_abs):.2f}" if st.angle_abs else "",
                "jump25": st.jump25,
                "retry": st.retry,
            })
    print(f"\nCSV 已写: {path}")


def _latest_logs(n: int = 2) -> List[Path]:
    if not LOG_DIR.is_dir():
        return []
    files = sorted(LOG_DIR.glob("巡航*.log"), key=lambda p: p.stat().st_mtime)
    return files[-n:]


def main() -> None:
    ap = argparse.ArgumentParser(description="巡航日志对照分析")
    ap.add_argument("logs", nargs="*", help="日志路径（1～N 个）")
    ap.add_argument("--legacy", type=str, default=None, help="legacy 日志")
    ap.add_argument("--text", type=str, default=None, help="text 日志")
    ap.add_argument("--csv", type=str, default=None, help="导出 CSV 路径")
    args = ap.parse_args()

    pairs: List[Tuple[str, Path]] = []
    if args.legacy:
        pairs.append(("legacy", Path(args.legacy)))
    if args.text:
        pairs.append(("text", Path(args.text)))
    for p in args.logs:
        pairs.append((Path(p).name, Path(p)))

    if not pairs:
        latest = _latest_logs(2)
        if not latest:
            print("未找到 logs/巡航*.log，请先跑两轮巡航或指定日志路径。")
            print("示例: python 分析巡航对照.py --legacy logs\\a.log --text logs\\b.log")
            return
        if len(latest) == 1:
            pairs = [("log1", latest[0])]
            print("只找到 1 个日志，仅输出单份报告。建议跑完 legacy+text 再对比。")
        else:
            # 不擅自标注模式，按时间旧→新
            pairs = [("A(较早)", latest[0]), ("B(较晚)", latest[1])]
            print("自动选取最近 2 个巡航日志（请自行确认哪个是 legacy / text）：")
            for lab, p in pairs:
                print(f"  {lab}: {p.name}")

    stats = []
    for lab, p in pairs:
        path = p if p.is_absolute() else (ROOT / p)
        if not path.is_file():
            print(f"跳过不存在: {path}")
            continue
        stats.append(analyze_log(path, label=lab))

    if not stats:
        print("无有效日志")
        return

    print_report(stats)
    if args.csv:
        write_csv(stats, Path(args.csv) if Path(args.csv).is_absolute() else ROOT / args.csv)


if __name__ == "__main__":
    main()
