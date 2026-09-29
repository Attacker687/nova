"""测试方案（testplan.json）的校验和渲染。

用法：
    python testplan.py check testplan.json [--stories stories.json] [--need-cases]
    python testplan.py render testplan.json --out test-plan.md

testplan.json 结构（字段含义见 references/method.md）：
{
  "feature": "功能名", "status": "draft | approved",
  "sources": ["参考了哪些文件"],
  "strategy": {"scope": "", "out_of_scope": "", "environment": "", "data": "", "risks": ""},
  "requirements": [{"id": "REQ-01", "text": "判据项", "source": "出处"}],
  "gaps": [{"id": "GAP-01", "text": "需求没说清的", "affects": ["TP-003"]}],
  "points": [{"id": "TP-001", "title": "验证什么", "type": "unit|api|e2e|manual",
              "condition": "input|rule|state", "technique": "ep-bva|decision-table|state-transition|pairwise|error-guessing",
              "covers": ["REQ-01"], "story": "S01", "rules": ["R-003"], "priority": "P0|P1|P2",
              "quote": "需求原文（≤120 字）", "inferred": "推断依据（没有原文时必填）", "expected": "可证伪的预期"}],
  "cases": [{"id": "TC-001", "point": "TP-001", "title": "…", "preconditions": ["…"], "steps": ["…"],
             "data": {"字段": "值"}, "expected": ["…"], "automatable": true}]
}
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

TYPES = {"unit": "单元", "api": "接口", "e2e": "端到端", "manual": "人工"}
CONDITIONS = {"input": "输入取值", "rule": "业务规则", "state": "状态流程"}
TECHNIQUES = {"ep-bva": "等价类+边界值", "decision-table": "决策表", "state-transition": "状态迁移",
              "pairwise": "组合", "error-guessing": "错误推测"}
PRIORITIES = ("P0", "P1", "P2")
VAGUE = re.compile(r"^(操作|请求|处理|执行|调用)?(成功|正常|正确|无异常|没有报错|符合预期|通过)[。！!]?$")
MAX_QUOTE = 120


def load(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _dupes(ids: list) -> list:
    return sorted({i for i in ids if i and ids.count(i) > 1})


def check(data: dict, story_ids: set[str] | None = None, need_cases: bool = False) -> tuple[list[str], list[str]]:
    """返回 (问题, 提醒)。问题会让 check 失败，提醒只打印。"""
    problems, warnings = [], []
    reqs = data.get("requirements") or []
    points = data.get("points") or []
    cases = data.get("cases") or []
    if not reqs:
        problems.append("requirements 为空：先列出要覆盖的判据项")
    if not points:
        problems.append("points 为空")
    req_ids = [r.get("id") for r in reqs]
    point_ids = [p.get("id") for p in points]
    for label, ids in (("判据项", req_ids), ("测试点", point_ids), ("用例", [c.get("id") for c in cases])):
        for d in _dupes(ids):
            problems.append(f"{label}编号重复：{d}")
    known_reqs = set(req_ids)
    covered = set()
    for p in points:
        pid = p.get("id", "?")
        if not re.match(r"^TP-\d{3}$", str(pid)):
            problems.append(f"测试点编号不合规：{pid!r}（应为 TP-001）")
        for field in ("title", "expected"):
            if not str(p.get(field, "")).strip():
                problems.append(f"{pid} 缺少 {field}")
        for field, allowed in (("type", TYPES), ("condition", CONDITIONS), ("technique", TECHNIQUES)):
            if p.get(field) not in allowed:
                problems.append(f"{pid} 的 {field} 取值不对：{p.get(field)!r}")
        if p.get("priority") not in PRIORITIES:
            problems.append(f"{pid} 的 priority 取值不对：{p.get('priority')!r}")
        quote, inferred = str(p.get("quote") or "").strip(), str(p.get("inferred") or "").strip()
        if not quote and not inferred:
            problems.append(f"{pid} 既没有需求原文 quote，也没有推断依据 inferred")
        if len(quote) > MAX_QUOTE:
            problems.append(f"{pid} 的 quote 超过 {MAX_QUOTE} 字，只截取相关的那句")
        if VAGUE.match(str(p.get("expected", "")).strip()):
            problems.append(f"{pid} 的 expected 太笼统，要写成可以判断对错的具体结果")
        cov = p.get("covers") or []
        if not cov:
            problems.append(f"{pid} 没有对应任何判据项（covers 为空）")
        for r in cov:
            if r not in known_reqs:
                problems.append(f"{pid} 对应了不存在的判据项 {r}")
            covered.add(r)
        if story_ids is not None and p.get("story") and p["story"] not in story_ids:
            problems.append(f"{pid} 的 story 不在 stories.json 里：{p['story']}")
    for r in req_ids:
        if r and r not in covered:
            problems.append(f"判据项 {r} 没有被任何测试点覆盖")
    present = {p.get("condition") for p in points}
    for cond, name in CONDITIONS.items():
        if points and cond not in present:
            warnings.append(f"没有「{name}」类测试点；确实不涉及的话在 strategy.scope 里说明")
    known_points = set(point_ids)
    with_cases = set()
    for c in cases:
        cid = c.get("id", "?")
        if not re.match(r"^TC-\d{3}$", str(cid)):
            problems.append(f"用例编号不合规：{cid!r}（应为 TC-001）")
        if c.get("point") not in known_points:
            problems.append(f"{cid} 对应的测试点不存在：{c.get('point')!r}")
        with_cases.add(c.get("point"))
        for field in ("title", "steps", "expected"):
            if not c.get(field):
                problems.append(f"{cid} 缺少 {field}")
        for e in c.get("expected") or []:
            if VAGUE.match(str(e).strip()):
                problems.append(f"{cid} 的预期「{e}」太笼统")
    if need_cases:
        for pid in point_ids:
            if pid and pid not in with_cases:
                problems.append(f"测试点 {pid} 还没有用例")
    for g in data.get("gaps") or []:
        for tp in g.get("affects", []):
            if tp not in known_points:
                warnings.append(f"{g.get('id')} 影响的测试点不存在：{tp}")
    return problems, warnings


def _cell(value) -> str:
    if isinstance(value, list):
        value = "<br>".join(str(v) for v in value)
    elif isinstance(value, dict):
        value = "<br>".join(f"{k}：{v}" for k, v in value.items())
    return str(value or "").replace("|", "\\|").replace("\n", "<br>")


def render(data: dict) -> str:
    points, reqs, cases = data.get("points", []), data.get("requirements", []), data.get("cases", [])
    s = data.get("strategy", {})
    by_type = {t: sum(p.get("type") == t for p in points) for t in TYPES}
    by_pri = {p_: sum(p.get("priority") == p_ for p in points) for p_ in PRIORITIES}
    lines = [
        "---", f"feature: {data.get('feature', '')}", f"status: {data.get('status', 'draft')}", "---", "",
        f"# 测试方案：{data.get('feature', '')}", "",
        "> 由 testplan.json 生成，改内容请改 testplan.json 后重新渲染。", "",
        "## 1. 概述", "",
        f"判据项 {len(reqs)} 条，测试点 {len(points)} 个，用例 {len(cases)} 条。",
        "测试点按类型：" + "、".join(f"{TYPES[t]} {n}" for t, n in by_type.items() if n) +
        "；按优先级：" + "、".join(f"{k} {v}" for k, v in by_pri.items() if v) + "。", "",
        f"- **范围**：{s.get('scope', '')}", f"- **不测**：{s.get('out_of_scope', '')}",
        f"- **环境**：{s.get('environment', '')}", f"- **数据**：{s.get('data', '')}", "",
        "## 2. 判据项与覆盖", "",
        "| 判据项 | 内容 | 出处 | 覆盖的测试点 |", "|---|---|---|---|",
    ]
    for r in reqs:
        tps = [p["id"] for p in points if r["id"] in (p.get("covers") or [])]
        lines.append(f"| {r['id']} | {_cell(r.get('text'))} | {_cell(r.get('source'))} | {'、'.join(tps) or '**未覆盖**'} |")
    lines += ["", "## 3. 测试点", "",
              "| 编号 | 验证什么 | 类型 | 条件 | 技法 | 优先级 | Story | 依据 | 预期 |",
              "|---|---|---|---|---|---|---|---|---|"]
    for p in points:
        basis = f"原文：{p['quote']}" if p.get("quote") else f"推断：{p.get('inferred', '')}"
        if p.get("rules"):
            basis += f"（规则 {'、'.join(p['rules'])}）"
        lines.append(f"| {p['id']} | {_cell(p.get('title'))} | {TYPES.get(p.get('type'), p.get('type'))} | "
                     f"{CONDITIONS.get(p.get('condition'), '')} | {TECHNIQUES.get(p.get('technique'), '')} | "
                     f"{p.get('priority', '')} | {p.get('story', '')} | {_cell(basis)} | {_cell(p.get('expected'))} |")
    if cases:
        lines += ["", "## 4. 用例", "",
                  "| 编号 | 测试点 | 标题 | 前置条件 | 步骤 | 数据 | 预期 | 可自动化 |", "|---|---|---|---|---|---|---|---|"]
        for c in cases:
            lines.append(f"| {c['id']} | {c.get('point', '')} | {_cell(c.get('title'))} | {_cell(c.get('preconditions'))} | "
                         f"{_cell(c.get('steps'))} | {_cell(c.get('data'))} | {_cell(c.get('expected'))} | "
                         f"{'是' if c.get('automatable', True) else '否'} |")
    lines += ["", f"## {5 if cases else 4}. 风险与需求缺口", "", f"**风险**：{s.get('risks', '')}", ""]
    gaps = data.get("gaps") or []
    if gaps:
        lines += ["| 编号 | 缺口 | 影响的测试点 |", "|---|---|---|"]
        lines += [f"| {g.get('id')} | {_cell(g.get('text'))} | {'、'.join(g.get('affects', []))} |" for g in gaps]
    else:
        lines.append("没有登记需求缺口。")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check")
    c.add_argument("testplan")
    c.add_argument("--stories")
    c.add_argument("--need-cases", action="store_true", help="要求每个测试点都有用例")
    r = sub.add_parser("render")
    r.add_argument("testplan")
    r.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    data = load(args.testplan)
    if args.cmd == "render":
        Path(args.out).write_text(render(data), encoding="utf-8")
        print(f"→ {args.out}")
        return 0
    story_ids = {s["id"] for s in load(args.stories)["stories"]} if args.stories else None
    problems, warnings = check(data, story_ids, args.need_cases)
    for w in warnings:
        print(f"提醒：{w}")
    if problems:
        print("✗ testplan.json 有问题：\n" + "\n".join(f"- {p}" for p in problems))
        return 1
    print(f"✓ 判据项 {len(data['requirements'])} 条全部覆盖，测试点 {len(data['points'])} 个，"
          f"用例 {len(data.get('cases') or [])} 条")
    return 0


if __name__ == "__main__":
    sys.exit(main())
