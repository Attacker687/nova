"""测试结果（results.json）：从 JUnit XML 导入、手工登记、汇总。

用法：
    python results.py import 报告.xml [更多…] --plan testplan.json --out results.json
    python results.py set results.json TC-003 --result blocked --message "环境缺支付沙箱" [--kind env] [--defect BUG-001]
    python results.py summary results.json --plan testplan.json

测试名（或类名）里含用例编号（TC-001、TC_001、TC001 都认）才能归到用例上；
同一用例被多个测试覆盖时，任一失败即失败。import 会覆盖同一用例之前的结果、保留其他用例的结果。
result 取值：pass | fail | blocked | skipped。kind（失败原因）：product 产品缺陷 | test 测试代码问题 | env 环境问题。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

CASE_RE = re.compile(r"TC[-_]?(\d{3})", re.I)
RESULTS = ("pass", "fail", "blocked", "skipped")
KINDS = ("product", "test", "env")
RANK = {"fail": 3, "blocked": 2, "pass": 1, "skipped": 0}


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load(path: str, default: dict | None = None) -> dict:
    p = Path(path)
    if not p.exists() and default is not None:
        return default
    return json.loads(p.read_text(encoding="utf-8"))


def parse_junit(path: str) -> tuple[dict, list[str]]:
    """返回 ({用例编号: 结果}, 没法归到用例的测试名)。"""
    root = ET.parse(path).getroot()
    found: dict[str, dict] = {}
    unmapped = []
    for tc in root.iter("testcase"):
        name = f"{tc.get('classname', '')}.{tc.get('name', '')}".strip(".")
        m = CASE_RE.search(tc.get("name", "")) or CASE_RE.search(tc.get("classname", ""))
        if not m:
            unmapped.append(name)
            continue
        cid = f"TC-{m.group(1)}"
        failure = tc.find("failure")
        if failure is None:
            failure = tc.find("error")
        if failure is not None:
            result = "fail"
            text = (failure.get("message") or failure.text or "").strip()
            message = text.splitlines()[0][:300] if text else ""
        elif tc.find("skipped") is not None:
            result, message = "skipped", (tc.find("skipped").get("message") or "")[:300]
        else:
            result, message = "pass", ""
        entry = {"result": result, "message": message, "tests": [name], "time": float(tc.get("time") or 0),
                 "source": Path(path).name}
        prev = found.get(cid)
        if prev:
            if RANK[result] > RANK[prev["result"]]:
                prev.update(result=result, message=message)
            prev["tests"].append(name)
            prev["time"] += entry["time"]
        else:
            found[cid] = entry
    return found, unmapped


def import_junit(paths: list[str], results: dict, plan: dict) -> dict:
    planned = {c["id"] for c in plan.get("cases", [])}
    results.setdefault("cases", {})
    results.setdefault("runs", [])
    report = {"imported": 0, "unmapped": [], "unknown_cases": []}
    for path in paths:
        found, unmapped = parse_junit(path)
        report["unmapped"] += unmapped
        for cid, entry in found.items():
            if cid not in planned:
                report["unknown_cases"].append(cid)
            old = results["cases"].get(cid, {})
            entry["kind"] = old.get("kind", "") if entry["result"] == "fail" else ""
            entry["defect"] = old.get("defect", "") if entry["result"] == "fail" else ""
            results["cases"][cid] = entry
            report["imported"] += 1
        results["runs"].append({"at": now(), "source": Path(path).name, "cases": len(found)})
    return report


def set_result(results: dict, cid: str, result: str, message: str = "", kind: str = "", defect: str = "") -> None:
    if result not in RESULTS:
        raise ValueError(f"result 取值不对：{result}")
    if kind and kind not in KINDS:
        raise ValueError(f"kind 取值不对：{kind}")
    results.setdefault("cases", {})
    entry = results["cases"].setdefault(cid, {"tests": [], "time": 0, "source": "手工登记"})
    entry.update(result=result, message=message or entry.get("message", ""), kind=kind or entry.get("kind", ""),
                 defect=defect or entry.get("defect", ""))


def summarize(results: dict, plan: dict) -> dict:
    cases = plan.get("cases", [])
    got = results.get("cases", {})
    counts = {r: 0 for r in RESULTS}
    not_run = []
    for c in cases:
        r = got.get(c["id"], {}).get("result")
        if r in counts:
            counts[r] += 1
        else:
            not_run.append(c["id"])
    unexplained = [cid for cid, e in got.items() if e.get("result") == "fail" and not e.get("kind")]
    return {"planned": len(cases), **counts, "not_run": not_run, "fail_without_kind": sorted(unexplained)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("import")
    p.add_argument("junit", nargs="+")
    p.add_argument("--plan", required=True)
    p.add_argument("--out", required=True)
    p = sub.add_parser("set")
    p.add_argument("results")
    p.add_argument("case")
    p.add_argument("--result", required=True)
    p.add_argument("--message", default="")
    p.add_argument("--kind", default="")
    p.add_argument("--defect", default="")
    p = sub.add_parser("summary")
    p.add_argument("results")
    p.add_argument("--plan", required=True)
    args = parser.parse_args(argv)
    try:
        if args.cmd == "import":
            results = load(args.out, {"cases": {}, "runs": []})
            report = import_junit(args.junit, results, load(args.plan))
            Path(args.out).write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"导入 {report['imported']} 条用例结果 → {args.out}")
            if report["unmapped"]:
                print(f"提醒：{len(report['unmapped'])} 个测试名里没有用例编号，未归入：{'、'.join(report['unmapped'][:5])}")
            if report["unknown_cases"]:
                print(f"提醒：这些编号不在测试方案里：{'、'.join(sorted(set(report['unknown_cases'])))}")
        elif args.cmd == "set":
            results = load(args.results, {"cases": {}, "runs": []})
            set_result(results, args.case, args.result, args.message, args.kind, args.defect)
            Path(args.results).write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"{args.case}：{args.result}")
        else:
            s = summarize(load(args.results), load(args.plan))
            print(json.dumps(s, ensure_ascii=False))
    except (ValueError, ET.ParseError, OSError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
