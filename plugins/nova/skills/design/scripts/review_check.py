"""校验评审结果 JSON（格式见 references/review-format.md），并输出统计。

用法：
    python review_check.py 评审结果.json [更多文件…]

格式有问题时逐条列出、退出码 1；都合格时打印每个文件的结论和按严重程度的计数。
多个文件一起给时（如三路代码评审），另外打印合计。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

VERDICTS = {"approved", "changes_requested"}
SEVERITIES = ("critical", "high", "medium", "low")
AXES = {"goal", "complete", "clear", "consistent", "grounded", "decision", "testable", "correct", "robust",
        "maintainable"}
KINDS = {"fix", "decide"}
REQUIRED = ("id", "severity", "axis", "kind", "where", "problem", "suggestion")


def validate(data: object) -> list[str]:
    if not isinstance(data, dict):
        return ["顶层必须是 JSON 对象"]
    problems = []
    if data.get("verdict") not in VERDICTS:
        problems.append(f"verdict 取值不对：{data.get('verdict')!r}")
    findings = data.get("findings")
    if not isinstance(findings, list):
        return problems + ["findings 必须是数组（没有问题写 []）"]
    ids = []
    for i, f in enumerate(findings, 1):
        label = f.get("id", f"第 {i} 条") if isinstance(f, dict) else f"第 {i} 条"
        if not isinstance(f, dict):
            problems.append(f"{label} 不是对象")
            continue
        ids.append(f.get("id"))
        missing = [k for k in REQUIRED if not str(f.get(k, "")).strip()]
        if missing:
            problems.append(f"{label} 缺少字段：{', '.join(missing)}")
        if f.get("severity") not in SEVERITIES:
            problems.append(f"{label} 的 severity 取值不对：{f.get('severity')!r}")
        if f.get("axis") not in AXES:
            problems.append(f"{label} 的 axis 取值不对：{f.get('axis')!r}")
        if f.get("kind") not in KINDS:
            problems.append(f"{label} 的 kind 取值不对：{f.get('kind')!r}")
    dupes = sorted({i for i in ids if ids.count(i) > 1 and i})
    if dupes:
        problems.append(f"编号重复：{', '.join(dupes)}")
    blocking = [f for f in findings if isinstance(f, dict) and f.get("severity") in ("critical", "high")]
    if blocking and data.get("verdict") == "approved":
        problems.append("有 critical/high 问题时 verdict 必须是 changes_requested")
    for g in data.get("goal_check") or []:
        if not isinstance(g, dict) or not g.get("goal") or not isinstance(g.get("supported"), bool):
            problems.append(f"goal_check 条目不完整：{g!r}")
    return problems


def summarize(data: dict) -> dict:
    findings = data.get("findings") or []
    counts = {s: sum(f.get("severity") == s for f in findings) for s in SEVERITIES}
    return {
        "verdict": data.get("verdict"),
        "counts": counts,
        "blocking": counts["critical"] + counts["high"],
        "decide": [f["id"] for f in findings if f.get("kind") == "decide"],
        "unsupported_goals": [g["goal"] for g in data.get("goal_check") or [] if g.get("supported") is False],
    }


def main(argv: list[str] | None = None) -> int:
    paths = argv if argv is not None else sys.argv[1:]
    if not paths:
        print(__doc__)
        return 2
    bad = False
    total = {s: 0 for s in SEVERITIES}
    for path in paths:
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"✗ {path}：读不了或不是合法 JSON（{exc}）")
            bad = True
            continue
        problems = validate(data)
        if problems:
            bad = True
            print(f"✗ {path}")
            for p in problems:
                print(f"  - {p}")
            continue
        s = summarize(data)
        for k in SEVERITIES:
            total[k] += s["counts"][k]
        extra = []
        if s["decide"]:
            extra.append(f"待拍板 {', '.join(s['decide'])}")
        if s["unsupported_goals"]:
            extra.append(f"未支撑目标 {', '.join(s['unsupported_goals'])}")
        counts = " ".join(f"{k}={v}" for k, v in s["counts"].items())
        print(f"✓ {path}：{s['verdict']} · {counts}" + (f" · {'；'.join(extra)}" if extra else ""))
    if len(paths) > 1 and not bad:
        print("合计：" + " ".join(f"{k}={v}" for k, v in total.items()))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
