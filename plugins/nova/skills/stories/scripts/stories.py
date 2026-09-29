"""Story 清单（stories.json）的校验、渲染和排序。

用法：
    python stories.py check stories.json [--root 代码根]    校验；给了代码根时还核对入口和改动文件
    python stories.py render stories.json --out stories.md  渲染成给人读的文档
    python stories.py order stories.json                    按依赖输出实现顺序

stories.json 结构：
{
  "feature": "功能名", "design": "docs/nova/功能名/design.md", "status": "draft | approved",
  "stories": [{
    "id": "S01", "title": "…", "goal": "交付后能做到什么", "design_refs": ["§4.2"],
    "depends_on": [], "scope": ["src/a/B.java", "新建 src/a/C.java"],
    "acceptance": [{"id": "S01-AC1", "given": "…", "when": "…", "then": "…",
                    "entry": "src/a/B.java::handle", "verify": "怎么验证"}],
    "notes": "实现提示（可空）"
  }]
}
entry 写生产代码里触发这条验收的入口：「路径::符号」，路径相对代码根，不能是测试文件。
入口或改动文件由本 Story 新建时，在 scope 里写「新建 路径」。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path, PurePosixPath

ID_RE = re.compile(r"^S\d{2,3}$")
TEST_DIRS = {"test", "tests", "__tests__", "spec", "fixtures", "testdata"}
NEW_PREFIX = "新建 "


class StoriesError(ValueError):
    pass


def load(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def new_files(story: dict) -> set[str]:
    return {s[len(NEW_PREFIX):].strip() for s in story.get("scope", []) if s.startswith(NEW_PREFIX)}


def topo_order(stories: list[dict]) -> list[str]:
    """按依赖排序；同层按编号。有环时抛 StoriesError。"""
    deps = {s["id"]: set(s.get("depends_on", [])) for s in stories}
    order, done = [], set()
    while len(order) < len(deps):
        ready = sorted(i for i, d in deps.items() if i not in done and d <= done)
        if not ready:
            raise StoriesError("依赖有环：" + "、".join(sorted(set(deps) - done)))
        order += ready
        done |= set(ready)
    return order


def check(data: dict, root: Path | None = None) -> list[str]:
    problems = []
    stories = data.get("stories")
    if not isinstance(stories, list) or not stories:
        return ["stories 必须是非空数组"]
    ids = [s.get("id") for s in stories]
    for sid in sorted({i for i in ids if ids.count(i) > 1 and i}):
        problems.append(f"编号重复：{sid}")
    known = set(ids)
    ac_ids: list[str] = []
    for s in stories:
        sid = s.get("id", "?")
        if not ID_RE.match(str(sid)):
            problems.append(f"编号不合规：{sid!r}（应为 S01 这种）")
        for field in ("title", "goal"):
            if not str(s.get(field, "")).strip():
                problems.append(f"{sid} 缺少 {field}")
        for dep in s.get("depends_on", []):
            if dep not in known:
                problems.append(f"{sid} 依赖了不存在的 {dep}")
            if dep == sid:
                problems.append(f"{sid} 依赖了自己")
        acs = s.get("acceptance") or []
        if not acs:
            problems.append(f"{sid} 没有验收标准")
        created = new_files(s)
        for ac in acs:
            aid = ac.get("id", "?")
            ac_ids.append(aid)
            if not str(aid).startswith(f"{sid}-AC"):
                problems.append(f"{sid} 的验收编号应以 {sid}-AC 开头：{aid!r}")
            for field in ("given", "when", "then", "entry", "verify"):
                if not str(ac.get(field, "")).strip():
                    problems.append(f"{aid} 缺少 {field}")
            entry = str(ac.get("entry", ""))
            if entry and "::" not in entry:
                problems.append(f"{aid} 的 entry 要写成「路径::符号」：{entry!r}")
                continue
            path, _, symbol = entry.partition("::")
            if path and set(PurePosixPath(path).parts[:-1]) & TEST_DIRS:
                problems.append(f"{aid} 的 entry 指向测试代码，应指向生产代码入口：{path}")
            if root and path and path not in created:
                target = root / path
                if not target.is_file():
                    problems.append(f"{aid} 的入口文件不存在（新建的要在 scope 里写「新建 {path}」）：{path}")
                elif symbol and symbol not in target.read_text(encoding="utf-8", errors="replace"):
                    problems.append(f"{aid} 的入口符号在文件里找不到：{symbol}（{path}）")
        if root:
            for item in s.get("scope", []):
                if not item.startswith(NEW_PREFIX) and not (root / item).exists():
                    problems.append(f"{sid} 的改动范围里有不存在的文件（新建的要加「新建 」前缀）：{item}")
    for aid in sorted({a for a in ac_ids if ac_ids.count(a) > 1}):
        problems.append(f"验收编号重复：{aid}")
    if not problems:
        try:
            topo_order(stories)
        except StoriesError as exc:
            problems.append(str(exc))
    return problems


def render(data: dict) -> str:
    stories = data["stories"]
    by_id = {s["id"]: s for s in stories}
    order = topo_order(stories)
    lines = [
        "---",
        f"feature: {data.get('feature', '')}",
        f"design: {data.get('design', '')}",
        f"status: {data.get('status', 'draft')}",
        "---",
        "",
        f"# Story 清单：{data.get('feature', '')}",
        "",
        "> 由 stories.json 生成，改内容请改 stories.json 后重新渲染。",
        "",
        "## 总览",
        "",
        "| 顺序 | 编号 | 标题 | 依赖 | 验收数 |",
        "|---|---|---|---|---|",
    ]
    for n, sid in enumerate(order, 1):
        s = by_id[sid]
        lines.append(f"| {n} | {sid} | {s['title']} | {'、'.join(s.get('depends_on', [])) or '—'} | "
                     f"{len(s.get('acceptance', []))} |")
    lines += ["", "## 依赖关系", "", "```mermaid", "flowchart LR"]
    lines += [f"  {sid}[\"{sid} {by_id[sid]['title']}\"]" for sid in order]
    lines += [f"  {dep} --> {sid}" for sid in order for dep in by_id[sid].get("depends_on", [])]
    lines += ["```", ""]
    for sid in order:
        s = by_id[sid]
        lines += [f"## {sid} {s['title']}", "", f"**目标**：{s['goal']}", ""]
        if s.get("design_refs"):
            lines.append(f"**对应方案**：{'、'.join(s['design_refs'])}")
        lines.append(f"**依赖**：{'、'.join(s.get('depends_on', [])) or '无'}")
        if s.get("scope"):
            lines += ["", "**改动范围**：", ""] + [f"- `{x}`" for x in s["scope"]]
        lines += ["", "**验收标准**：", "", "| 编号 | 前提 | 操作 | 结果 | 入口 | 验证方式 |", "|---|---|---|---|---|---|"]
        for ac in s.get("acceptance", []):
            cells = [ac["id"], ac["given"], ac["when"], ac["then"], f"`{ac['entry']}`", ac["verify"]]
            lines.append("| " + " | ".join(str(c).replace("|", "\\|") for c in cells) + " |")
        if s.get("notes"):
            lines += ["", f"**实现提示**：{s['notes']}"]
        lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check")
    c.add_argument("stories")
    c.add_argument("--root")
    r = sub.add_parser("render")
    r.add_argument("stories")
    r.add_argument("--out", required=True)
    o = sub.add_parser("order")
    o.add_argument("stories")
    args = parser.parse_args(argv)
    data = load(args.stories)
    if args.cmd == "check":
        problems = check(data, Path(args.root).resolve() if args.root else None)
        if problems:
            print("✗ stories.json 有问题：\n" + "\n".join(f"- {p}" for p in problems))
            return 1
        acs = sum(len(s["acceptance"]) for s in data["stories"])
        print(f"✓ {len(data['stories'])} 个 Story，{acs} 条验收标准，顺序：{' → '.join(topo_order(data['stories']))}")
        return 0
    try:
        if args.cmd == "render":
            Path(args.out).write_text(render(data), encoding="utf-8")
            print(f"→ {args.out}")
        else:
            print(" ".join(topo_order(data["stories"])))
    except (StoriesError, KeyError) as exc:
        print(f"错误：{exc}（先运行 check）", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
