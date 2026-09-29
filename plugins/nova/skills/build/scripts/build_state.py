"""开发流水线的状态记录：每个 Story 的进度、下一个该做哪个、合并三路评审结果。

用法：
    python build_state.py init --stories stories.json --state state.json --feature-branch 分支 --base 基线分支 --test-cmd "命令" [--setup-cmd "命令"]
    python build_state.py next --state state.json
    python build_state.py set --state state.json S01 --status reviewing [--round 2] [--commit 提交] [--base 提交] [--reviewed 提交] [--note 说明]
    python build_state.py show --state state.json
    python build_state.py merge-reviews review-general-r1.json review-adversarial-r1.json … --out merged-r1.json

状态取值：pending → implementing → reviewing → verifying → merging → done；卡住时为 blocked。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "stories" / "scripts"))
from stories import topo_order  # noqa: E402

STATUSES = ("pending", "implementing", "reviewing", "verifying", "merging", "done", "blocked")
SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}
LENS_RE = re.compile(r"review-([a-z]+)-r\d+", re.I)


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def save(path: str, data: dict) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def init_state(stories: dict, feature_branch: str, base: str, test_cmd: str, setup_cmd: str = "") -> dict:
    items = stories["stories"]
    return {
        "feature": stories.get("feature", ""),
        "feature_branch": feature_branch,
        "base": base,
        "test_cmd": test_cmd,
        "setup_cmd": setup_cmd,
        "order": topo_order(items),
        "stories": {s["id"]: {"title": s["title"], "depends_on": s.get("depends_on", []), "status": "pending",
                              "round": 0, "base": "", "reviewed": "", "commit": "", "notes": [],
                              "updated_at": now()} for s in items},
    }


def next_story(state: dict) -> dict:
    stories = state["stories"]
    in_progress = [sid for sid in state["order"] if stories[sid]["status"] not in ("pending", "done", "blocked")]
    if in_progress:
        return {"story": in_progress[0], "resume": True}
    for sid in state["order"]:
        s = stories[sid]
        if s["status"] == "pending" and all(stories[d]["status"] == "done" for d in s["depends_on"]):
            return {"story": sid, "resume": False}
    if all(s["status"] == "done" for s in stories.values()):
        return {"story": None, "all_done": True}
    blocked = [sid for sid, s in stories.items() if s["status"] == "blocked"]
    waiting = [sid for sid, s in stories.items() if s["status"] == "pending"]
    return {"story": None, "all_done": False, "blocked": blocked, "waiting_on_blocked": waiting}


def set_status(state: dict, sid: str, status: str | None = None, round_: int | None = None,
               commit: str | None = None, note: str | None = None, base: str | None = None,
               reviewed: str | None = None) -> dict:
    if sid not in state["stories"]:
        raise KeyError(f"没有这个 Story：{sid}")
    s = state["stories"][sid]
    if status:
        if status not in STATUSES:
            raise ValueError(f"状态取值不对：{status}")
        s["status"] = status
    if round_ is not None:
        s["round"] = round_
    for key, value in (("commit", commit), ("base", base), ("reviewed", reviewed)):
        if value:
            s[key] = value
    if note:
        s["notes"].append({"at": now(), "text": note})
    s["updated_at"] = now()
    return state


def render(state: dict) -> str:
    lines = [f"功能 {state['feature']} · 分支 {state['feature_branch']}（基于 {state['base']}）· 测试命令：{state['test_cmd']}",
             "", "| 编号 | 标题 | 状态 | 轮次 | 提交 |", "|---|---|---|---|---|"]
    for sid in state["order"]:
        s = state["stories"][sid]
        lines.append(f"| {sid} | {s['title']} | {s['status']} | {s['round']} | {s['commit'][:10]} |")
    return "\n".join(lines)


def merge_reviews(paths: list[str]) -> dict:
    merged, verdicts, lenses = [], [], []
    for path in paths:
        data = load(path)
        m = LENS_RE.search(Path(path).stem)
        lens = data.get("lens") or (m.group(1) if m else Path(path).stem)
        lenses.append(lens)
        verdicts.append(data.get("verdict"))
        for f in data.get("findings", []):
            merged.append({**f, "id": f"{lens}-{f.get('id')}", "lens": lens})
    merged.sort(key=lambda f: SEVERITY_ORDER.get(f.get("severity"), 9))
    counts = {k: sum(f.get("severity") == k for f in merged) for k in SEVERITY_ORDER}
    blocking = counts["critical"] + counts["high"]
    return {
        "lenses": lenses,
        "verdict": "approved" if blocking == 0 and all(v == "approved" for v in verdicts) else "changes_requested",
        "counts": counts,
        "findings": merged,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("init")
    p.add_argument("--stories", required=True)
    p.add_argument("--state", required=True)
    p.add_argument("--feature-branch", required=True)
    p.add_argument("--base", required=True)
    p.add_argument("--test-cmd", required=True)
    p.add_argument("--setup-cmd", default="")
    p = sub.add_parser("next")
    p.add_argument("--state", required=True)
    p = sub.add_parser("set")
    p.add_argument("--state", required=True)
    p.add_argument("story")
    p.add_argument("--status")
    p.add_argument("--round", type=int)
    p.add_argument("--commit")
    p.add_argument("--base")
    p.add_argument("--reviewed")
    p.add_argument("--note")
    p = sub.add_parser("show")
    p.add_argument("--state", required=True)
    p = sub.add_parser("merge-reviews")
    p.add_argument("reviews", nargs="+")
    p.add_argument("--out", required=True)
    args = parser.parse_args(argv)

    try:
        if args.cmd == "init":
            if Path(args.state).exists():
                print(f"错误：{args.state} 已存在，要重来请先删除", file=sys.stderr)
                return 1
            state = init_state(load(args.stories), args.feature_branch, args.base, args.test_cmd, args.setup_cmd)
            save(args.state, state)
            print(f"已建立 {len(state['order'])} 个 Story 的状态，顺序：{' → '.join(state['order'])}")
        elif args.cmd == "next":
            print(json.dumps(next_story(load(args.state)), ensure_ascii=False))
        elif args.cmd == "set":
            state = set_status(load(args.state), args.story, args.status, args.round, args.commit, args.note,
                               args.base, args.reviewed)
            save(args.state, state)
            s = state["stories"][args.story]
            print(f"{args.story}：{s['status']} · 第 {s['round']} 轮")
        elif args.cmd == "show":
            print(render(load(args.state)))
        else:
            merged = merge_reviews(args.reviews)
            save(args.out, merged)
            c = merged["counts"]
            print(f"{merged['verdict']} · critical={c['critical']} high={c['high']} medium={c['medium']} "
                  f"low={c['low']} → {args.out}")
    except (KeyError, ValueError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
