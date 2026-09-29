"""wiki 整理的确定性部分：校验整理项、渲染报告、读回勾选、生成执行计划。

用法：
    python wiki_plan.py report --tree tree.json --items items.json --out report.xml [--rules "规则来源说明"]
    python wiki_plan.py checked 报告读回.xml
    python wiki_plan.py plan --before tree.json --now tree_now.json --items items.json --checked W-001,W-003 --out plan.json

items.json 形如 {"items": [整理项, ...]}，每项：
    id        W-001 起三位编号
    action    move | archive | rename | create | trash | manual
    node      被操作节点的 node_token（create 不需要）
    target    move/archive/trash 的新父节点 token；也可写 "new:W-00x" 指向同批 create 出来的节点
    parent    create 的父节点 token（同样可写 "new:W-00x"）
    new_title rename/create 的新标题
    reason    一句话理由（报告里给人看）
"""
from __future__ import annotations

import argparse
import copy
import json
import re
import sys
from html import escape as _html_escape
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wiki_tree import index_tree, iter_nodes, render_text  # noqa: E402

ACTIONS = {
    "create": "新建节点",
    "rename": "改名",
    "move": "移动",
    "archive": "归档",
    "trash": "移入「待删除」",
    "manual": "需要你手动处理（不会自动执行）",
}
MOVE_LIKE = {"move", "archive", "trash"}
ID_RE = re.compile(r"^W-\d{3}$")
CHECK_RE = re.compile(r"^\s*(?:[-*+]\s*)?\[(?P<mark>[ xX✓✔])\]\s*\\?\[(?P<id>W-\d{3})\\?\]")
XML_CHECK_RE = re.compile(
    r'<checkbox\b[^>]*?\bdone="(?P<done>true|false)"[^>]*>\s*(?:<[^>]+>\s*)*\\?\[(?P<id>W-\d{3})\\?\]'
)
SUMMARY_PREFIX = "📊 待处理"


def escape(text: str) -> str:
    return _html_escape(text, quote=False)


def load_json(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def validate_items(items: list[dict], tree: dict) -> list[str]:
    """返回问题清单；空列表表示通过。"""
    problems = []
    idx = index_tree(tree)
    ids = [it.get("id") for it in items]
    created = {it["id"] for it in items if it.get("action") == "create" and it.get("id")}

    def ref_ok(token: str | None) -> bool:
        if not token:
            return False
        if token.startswith("new:"):
            return token[4:] in created
        return token in idx

    for it in items:
        iid = it.get("id")
        if not iid or not ID_RE.match(iid):
            problems.append(f"编号不合规：{iid!r}（应为 W-001 这种三位编号）")
            continue
        if ids.count(iid) > 1:
            problems.append(f"{iid} 编号重复")
        action = it.get("action")
        if action not in ACTIONS:
            problems.append(f"{iid} 的 action 不认识：{action!r}")
            continue
        if action != "create" and it.get("node") not in idx:
            problems.append(f"{iid} 的 node 不在树里：{it.get('node')!r}")
        if action in MOVE_LIKE and not ref_ok(it.get("target")):
            problems.append(f"{iid} 缺少有效的 target")
        if action == "create" and not ref_ok(it.get("parent")):
            problems.append(f"{iid} 缺少有效的 parent")
        if action in ("rename", "create") and not (it.get("new_title") or "").strip():
            problems.append(f"{iid} 缺少 new_title")
    return problems


def _title_of(token: str | None, idx: dict, items_by_id: dict) -> str:
    if not token:
        return "?"
    if token.startswith("new:"):
        return items_by_id.get(token[4:], {}).get("new_title", token)
    entry = idx.get(token)
    return entry["node"]["title"] if entry else token


def describe(item: dict, idx: dict, items_by_id: dict) -> str:
    action = item["action"]
    title = _title_of(item.get("node"), idx, items_by_id) if action != "create" else ""
    if action in MOVE_LIKE:
        text = f"「{title}」→ 移到「{_title_of(item['target'], idx, items_by_id)}」下"
    elif action == "rename":
        text = f"「{title}」→ 改名为「{item['new_title']}」"
    elif action == "create":
        text = f"在「{_title_of(item['parent'], idx, items_by_id)}」下新建「{item['new_title']}」"
    else:
        text = f"「{title}」"
    reason = (item.get("reason") or "").strip()
    return f"{text}：{reason}" if reason else text


def preview_tree(tree: dict, items: list[dict]) -> dict:
    """把全部整理项（manual 除外）应用到树的副本上，给报告做「整理后」预览。"""
    after = copy.deepcopy(tree)
    root = after["root"]
    nodes = {n["node_token"]: n for n, _, _ in iter_nodes(after) if n["node_token"]}
    parents = {n["node_token"]: p for n, _, p in iter_nodes(after) if n["node_token"] and p}

    def resolve(token: str):
        if token and token.startswith("new:"):
            return nodes.get(token)
        return nodes.get(token) if token else root

    for it in sorted(items, key=lambda x: 0 if x["action"] == "create" else 1):
        action = it["action"]
        if action == "create":
            parent = resolve(it["parent"])
            new = {"node_token": f"new:{it['id']}", "title": f"{it['new_title']}〔新建〕", "obj_type": "docx",
                   "children": []}
            parent["children"].append(new)
            nodes[new["node_token"]] = new
            parents[new["node_token"]] = parent
        elif action == "rename":
            nodes[it["node"]]["title"] = f"{it['new_title']}〔改名〕"
        elif action in MOVE_LIKE:
            node, target = nodes[it["node"]], resolve(it["target"])
            old_parent = parents.get(it["node"], root)
            old_parent["children"] = [c for c in old_parent["children"] if c is not node]
            target["children"].append(node)
            parents[it["node"]] = target
            node["title"] = f"{node['title']}  ← {ACTIONS[action]}"
    return after


def summary_line(count: int) -> str:
    """报告顶部的摘要行；执行后用 str_replace 按原文替换它，所以措辞要稳定。"""
    return f"{SUMMARY_PREFIX} {count} 项 · 勾选要执行的项，然后回到对话说「按勾选整理」"


def _code(text: str) -> str:
    return f'<pre lang="plaintext"><code>{escape(text)}</code></pre>'


def render_report(tree: dict, items: list[dict], rules: str = "通用结构规则") -> str:
    """渲染成飞书文档 XML（勾选框只有 XML 能表达）。"""
    idx = index_tree(tree)
    items_by_id = {it["id"]: it for it in items}
    actionable = [it for it in items if it["action"] != "manual"]
    title = f"wiki 整理报告：{tree['root'].get('title', '')}"
    meta = f"规则来源：{rules} · 结构拉取时间：{tree.get('fetched_at', '?')} · 共 {tree.get('count', '?')} 个节点"
    parts = [
        f"<title>{escape(title)}</title>",
        f"<p>{escape(summary_line(len(actionable)))}</p>",
        f"<p>{escape(meta)}</p>",
        "<p>只有打了勾的项会执行。「待删除」只是移动到一个容器节点里，真正删除由你自己在飞书里做。</p>",
    ]
    if not items:
        parts.append("<p>✅ 没有发现需要整理的地方。</p>")
    for action, label in ACTIONS.items():
        group = [it for it in items if it["action"] == action]
        if not group:
            continue
        parts.append(f"<h1>{escape(label)}（{len(group)}）</h1>")
        lines = [f"[{it['id']}] {describe(it, idx, items_by_id)}" for it in group]
        if action == "manual":
            parts.append("<ul>" + "".join(f"<li>{escape(line)}</li>" for line in lines) + "</ul>")
        else:
            parts += [f'<checkbox done="false">{escape(line)}</checkbox>' for line in lines]
    if actionable:
        parts += ["<h1>整理后的结构（全部勾选时）</h1>", _code(render_text(preview_tree(tree, items)))]
    parts += ["<h1>当前结构</h1>", _code(render_text(tree))]
    unreadable = tree.get("unreadable") or []
    if unreadable or tree.get("truncated"):
        notes = [f"「{u['title']}」的子节点读取失败：{u['error']}" for u in unreadable]
        if tree.get("truncated"):
            notes.append("节点数超过上限，部分子树未展开，报告只覆盖已展开部分")
        parts += ["<h1>没读全的部分</h1>", "<ul>" + "".join(f"<li>{escape(n)}</li>" for n in notes) + "</ul>"]
    return "\n".join(parts) + "\n"


def parse_checked(text: str) -> dict:
    """从读回的报告里找勾选框。认 XML 的 <checkbox done=…>，也认 Markdown 的 - [x]。"""
    checked, unchecked = [], []
    for m in XML_CHECK_RE.finditer(text):
        (checked if m.group("done") == "true" else unchecked).append(m.group("id"))
    if not checked and not unchecked:
        for line in text.splitlines():
            m = CHECK_RE.match(line)
            if m:
                (unchecked if m.group("mark") == " " else checked).append(m.group("id"))
    return {"checked": checked, "unchecked": unchecked}


def build_plan(before: dict, now: dict, items: list[dict], checked: list[str]) -> dict:
    """按勾选生成执行步骤；和拉报告时相比已经变了的节点列为冲突，不执行。"""
    idx_before, idx_now = index_tree(before), index_tree(now)
    by_id = {it["id"]: it for it in items}
    steps, conflicts, ignored = [], [], []
    for iid in checked:
        it = by_id.get(iid)
        if it is None:
            conflicts.append({"id": iid, "reason": "报告里有这个编号，但整理项清单里没有"})
            continue
        if it["action"] == "manual":
            ignored.append({"id": iid, "reason": "人工处理项，不自动执行"})
            continue
        reason = _conflict(it, idx_before, idx_now)
        if reason:
            conflicts.append({"id": iid, "reason": reason})
        else:
            steps.append(it)
    # 依赖的新建项不执行时，挂在它下面的步骤也不能执行；反复剔除直到稳定（新建项可以嵌套）。
    changed = True
    while changed:
        changed = False
        kept = {s["id"] for s in steps}
        blocked = {c["id"] for c in conflicts}
        for it in list(steps):
            refs = [it.get("target"), it.get("parent")]
            dep = next((r[4:] for r in refs if r and r.startswith("new:") and r[4:] not in kept), None)
            if dep:
                steps.remove(it)
                why = "依赖的新建项被判为冲突" if dep in blocked else "依赖的新建项没有执行"
                conflicts.append({"id": it["id"], "reason": f"{why}（{dep}）"})
                changed = True
    order = {"create": 0, "rename": 1, "move": 2, "archive": 2, "trash": 2}
    steps.sort(key=lambda it: (order[it["action"]], it["id"]))
    return {
        "space_id": now.get("space_id"),
        "steps": [_step(it, now.get("space_id")) for it in steps],
        "conflicts": conflicts,
        "ignored": ignored,
        "unchecked": [it["id"] for it in items if it["id"] not in checked and it["action"] != "manual"],
    }


def _conflict(it: dict, before: dict, now: dict) -> str | None:
    tokens = [it.get("node")] if it["action"] != "create" else []
    tokens += [t for t in (it.get("target"), it.get("parent")) if t and not t.startswith("new:")]
    for token in tokens:
        if token not in now:
            return f"节点 {token} 已经不在树里了"
    node = it.get("node")
    if node and node in before and node in now:
        if now[node]["parent_token"] != before[node]["parent_token"]:
            return "这个节点在出报告之后被移动过"
        if now[node]["node"]["title"] != before[node]["node"]["title"]:
            return "这个节点在出报告之后被改过名"
    return None


def _step(it: dict, space_id: str | None) -> dict:
    step = {k: it[k] for k in ("id", "action", "node", "target", "parent", "new_title") if it.get(k)}
    step["space_id"] = space_id
    return step


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    rp = sub.add_parser("report")
    rp.add_argument("--tree", required=True)
    rp.add_argument("--items", required=True)
    rp.add_argument("--out", required=True)
    rp.add_argument("--rules", default="通用结构规则")
    ck = sub.add_parser("checked")
    ck.add_argument("markdown")
    pl = sub.add_parser("plan")
    pl.add_argument("--before", required=True)
    pl.add_argument("--now", required=True)
    pl.add_argument("--items", required=True)
    pl.add_argument("--checked", required=True, help="逗号分隔的编号")
    pl.add_argument("--out", required=True)
    args = parser.parse_args(argv)

    if args.cmd == "checked":
        print(json.dumps(parse_checked(Path(args.markdown).read_text(encoding="utf-8")), ensure_ascii=False))
        return 0

    items = load_json(args.items)["items"]
    if args.cmd == "report":
        tree = load_json(args.tree)
        problems = validate_items(items, tree)
        if problems:
            print("整理项有问题，先修正：\n" + "\n".join(f"- {p}" for p in problems), file=sys.stderr)
            return 1
        Path(args.out).write_text(render_report(tree, items, args.rules), encoding="utf-8")
        print(f"报告 → {args.out}（{len(items)} 项）")
        return 0

    checked = [c.strip() for c in args.checked.split(",") if c.strip()]
    plan = build_plan(load_json(args.before), load_json(args.now), items, checked)
    Path(args.out).write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"可执行 {len(plan['steps'])} 步 · 冲突 {len(plan['conflicts'])} 项 · 未勾选 {len(plan['unchecked'])} 项 → {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
