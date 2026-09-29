"""根据测试方案、执行结果和缺陷清单生成测试报告，并按固定规则给出结论。

用法：
    python report.py testplan.json --results results.json [--defects defects.json] --out report.md [--env "测试环境说明"] [--json]

结论规则（算出即定，不人为调整）：
    通过        全部用例已执行，没有失败，没有未关闭的缺陷
    有条件通过  全部用例已执行，每个失败用例都关联了缺陷，未关闭缺陷全是 low，且 low 缺陷数 < 用例总数的 10%
    不通过      其余情况
「已执行」指结果为 pass 或 fail；blocked、skipped、没跑的都算未执行。
缺陷状态：open（未修）| fixed（已修待复测）| closed（已关闭）| wontfix（不修）；open 和 fixed 都算未关闭。

defects.json 形如 {"defects": [{"id": "BUG-001", "title": "", "severity": "critical|high|medium|low",
"status": "open", "cases": ["TC-001"], "steps": "", "expected": "", "actual": "", "evidence": ""}]}
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

SEVERITIES = ("critical", "high", "medium", "low")
OPEN = {"open", "fixed"}
TYPES = {"unit": "单元", "api": "接口", "e2e": "端到端", "manual": "人工"}
RESULT_TEXT = {"pass": "通过", "fail": "失败", "blocked": "阻塞", "skipped": "跳过", None: "未执行"}


def load(path: str | None, default: dict) -> dict:
    if not path or not Path(path).exists():
        return default
    return json.loads(Path(path).read_text(encoding="utf-8"))


def compute(plan: dict, results: dict, defects: dict) -> dict:
    cases = plan.get("cases", [])
    got = results.get("cases", {})
    res = {c["id"]: got.get(c["id"], {}).get("result") for c in cases}
    planned = len(cases)
    passed = sum(r == "pass" for r in res.values())
    failed = [cid for cid, r in res.items() if r == "fail"]
    executed = passed + len(failed)
    open_defects = [d for d in defects.get("defects", []) if d.get("status") in OPEN]
    open_by_sev = {s: sum(d.get("severity") == s for d in open_defects) for s in SEVERITIES}
    defect_cases = {c for d in open_defects for c in d.get("cases", [])}
    failed_without_defect = [cid for cid in failed if cid not in defect_cases and not got.get(cid, {}).get("defect")]
    exec_rate = executed / planned if planned else 0.0
    reasons = [f"执行率 {exec_rate:.0%}（{executed}/{planned}）", f"失败 {len(failed)} 条",
               "未关闭缺陷 " + " ".join(f"{s}={n}" for s, n in open_by_sev.items())]
    serious = open_by_sev["critical"] + open_by_sev["high"] + open_by_sev["medium"]
    if planned and executed == planned and not failed and not open_defects:
        verdict = "通过"
    elif (planned and executed == planned and not failed_without_defect and serious == 0
          and open_by_sev["low"] > 0 and open_by_sev["low"] / planned < 0.10):
        verdict = "有条件通过"
    else:
        verdict = "不通过"
        if failed_without_defect:
            reasons.append(f"{len(failed_without_defect)} 条失败用例没有关联缺陷：{'、'.join(failed_without_defect)}")
        if not planned:
            reasons.append("测试方案里没有用例")
    point_of = {c["id"]: c.get("point") for c in cases}
    cases_of_point: dict[str, list[str]] = {}
    for cid, pid in point_of.items():
        cases_of_point.setdefault(pid, []).append(cid)
    req_status = []
    for r in plan.get("requirements", []):
        pts = [p["id"] for p in plan.get("points", []) if r["id"] in (p.get("covers") or [])]
        rcases = [cid for pid in pts for cid in cases_of_point.get(pid, [])]
        states = [res.get(cid) for cid in rcases]
        if rcases and all(s == "pass" for s in states):
            status = "已验证"
        elif any(s == "fail" for s in states):
            status = "有问题"
        else:
            status = "未验证"
        req_status.append({"id": r["id"], "text": r.get("text", ""), "cases": rcases, "status": status})
    by_type: dict[str, dict] = {}
    types = {p["id"]: p.get("type") for p in plan.get("points", [])}
    for c in cases:
        t = types.get(c.get("point"), "?")
        row = by_type.setdefault(t, {"planned": 0, "pass": 0, "fail": 0, "other": 0})
        row["planned"] += 1
        key = res[c["id"]] if res[c["id"]] in ("pass", "fail") else "other"
        row[key] += 1
    return {
        "verdict": verdict, "reasons": reasons, "planned": planned, "executed": executed, "passed": passed,
        "failed": failed, "exec_rate": exec_rate, "pass_rate": passed / executed if executed else 0.0,
        "open_defects": open_by_sev, "results": res, "requirements": req_status, "by_type": by_type,
    }


def _cell(v) -> str:
    return str(v or "").replace("|", "\\|").replace("\n", "<br>")


def render(plan: dict, results: dict, defects: dict, stats: dict, env: str = "") -> str:
    s = plan.get("strategy", {})
    got = results.get("cases", {})
    titles = {c["id"]: c.get("title", "") for c in plan.get("cases", [])}
    risky = [d for d in defects.get("defects", []) if d.get("status") in OPEN]
    risky.sort(key=lambda d: SEVERITIES.index(d.get("severity")) if d.get("severity") in SEVERITIES else 9)
    unverified = [r for r in stats["requirements"] if r["status"] != "已验证"]
    lines = [
        f"# 测试报告：{plan.get('feature', '')}（结论：{stats['verdict']}）", "",
        f"> 生成时间 {datetime.now():%Y-%m-%d %H:%M} · 本报告只覆盖功能测试，性能、安全等专项不在其内。", "",
        "## 1. 结论与风险", "",
        f"**结论：{stats['verdict']}**。依据：{'；'.join(stats['reasons'])}。", "",
    ]
    if risky:
        lines += ["未关闭的缺陷：", ""] + [f"- {d['id']}（{d.get('severity')}，{d.get('status')}）{d.get('title', '')}"
                                          for d in risky] + [""]
    if unverified:
        lines += ["未验证或有问题的判据项：", ""] + [f"- {r['id']} {r['text']}：{r['status']}" for r in unverified] + [""]
    if not risky and not unverified:
        lines += ["没有未关闭的缺陷，全部判据项已验证。", ""]
    lines += [
        "## 2. 概述", "",
        f"- **范围**：{s.get('scope', '')}", f"- **不测**：{s.get('out_of_scope', '')}",
        f"- **环境**：{env or s.get('environment', '')}",
        f"- **执行记录**：" + "；".join(f"{r.get('at', '')} {r.get('source', '')}" for r in results.get("runs", [])), "",
        "## 3. 执行情况", "",
        "| 计划 | 已执行 | 通过 | 失败 | 执行率 | 通过率 |", "|---|---|---|---|---|---|",
        f"| {stats['planned']} | {stats['executed']} | {stats['passed']} | {len(stats['failed'])} | "
        f"{stats['exec_rate']:.0%} | {stats['pass_rate']:.0%} |", "",
        "| 类型 | 计划 | 通过 | 失败 | 未执行/阻塞/跳过 |", "|---|---|---|---|---|",
    ]
    lines += [f"| {TYPES.get(t, t)} | {r['planned']} | {r['pass']} | {r['fail']} | {r['other']} |"
              for t, r in stats["by_type"].items()]
    lines += ["", "## 4. 判据项验证情况", "", "| 判据项 | 内容 | 用例 | 状态 |", "|---|---|---|---|"]
    lines += [f"| {r['id']} | {_cell(r['text'])} | {'、'.join(r['cases']) or '—'} | {r['status']} |"
              for r in stats["requirements"]]
    lines += ["", "## 5. 缺陷", ""]
    if defects.get("defects"):
        lines += ["| 编号 | 标题 | 严重程度 | 状态 | 相关用例 |", "|---|---|---|---|---|"]
        lines += [f"| {d['id']} | {_cell(d.get('title'))} | {d.get('severity', '')} | {d.get('status', '')} | "
                  f"{'、'.join(d.get('cases', []))} |" for d in defects["defects"]]
    else:
        lines.append("没有登记缺陷。")
    bad = [cid for cid, r in stats["results"].items() if r != "pass"]
    lines += ["", "## 6. 未通过的用例", ""]
    if bad:
        lines += ["| 用例 | 标题 | 结果 | 原因 | 说明 | 缺陷 |", "|---|---|---|---|---|---|"]
        for cid in bad:
            e = got.get(cid, {})
            lines.append(f"| {cid} | {_cell(titles.get(cid))} | {RESULT_TEXT.get(stats['results'][cid])} | "
                         f"{e.get('kind', '')} | {_cell(e.get('message'))} | {e.get('defect', '')} |")
    else:
        lines.append("全部通过。")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("testplan")
    parser.add_argument("--results", required=True)
    parser.add_argument("--defects")
    parser.add_argument("--out", required=True)
    parser.add_argument("--env", default="")
    parser.add_argument("--json", action="store_true", help="同时把统计打印成 JSON")
    args = parser.parse_args(argv)
    plan = load(args.testplan, {})
    results = load(args.results, {"cases": {}, "runs": []})
    defects = load(args.defects, {"defects": []})
    stats = compute(plan, results, defects)
    Path(args.out).write_text(render(plan, results, defects, stats, args.env), encoding="utf-8")
    print(f"结论：{stats['verdict']}（{'；'.join(stats['reasons'])}）→ {args.out}")
    if args.json:
        print(json.dumps({k: v for k, v in stats.items() if k != "results"}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
