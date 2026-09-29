"""拉取飞书 wiki 子树的结构（只拉标题和层级，不拉正文），输出 JSON，或把 JSON 渲染成文字树。

用法：
    python wiki_tree.py fetch --root 【wiki 链接或节点 token】 --out tree.json [--max-nodes 3000]
    python wiki_tree.py fetch --space 【空间 ID 或 my_library】 --out tree.json
    python wiki_tree.py render tree.json [--tokens] [--max-depth N]

fetch 通过 lark-cli（--as user）逐层列子节点。读不到的子树不会中断整体，
会在该节点上记 error，并计入 JSON 顶层的 unreadable 列表。
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

NODE_FIELDS = ("node_token", "obj_token", "obj_type", "title", "parent_node_token", "has_child")


class LarkError(RuntimeError):
    pass


def run_lark(args: list[str]) -> dict:
    """以用户身份调用 lark-cli，返回解析后的 JSON；失败时抛 LarkError。"""
    exe = shutil.which("lark-cli")
    if not exe:
        raise LarkError("找不到 lark-cli，请先安装：npm install -g @larksuite/cli")
    proc = subprocess.run(
        [exe, *args, "--as", "user"], capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        raise LarkError(f"lark-cli 输出无法解析：{(proc.stdout or proc.stderr)[:500]}") from None
    if not data.get("ok"):
        raise LarkError(json.dumps(data.get("error", data), ensure_ascii=False)[:500])
    return data


Lister = Callable[[str, str], list]
Getter = Callable[[str], dict]


def lark_list_children(space_id: str, parent_token: str) -> list:
    args = ["wiki", "+node-list", "--space-id", space_id, "--page-all", "--page-limit", "0"]
    if parent_token:
        args += ["--parent-node-token", parent_token]
    return run_lark(args)["data"].get("nodes", [])


def lark_get_node(token: str) -> dict:
    data = run_lark(["wiki", "+node-get", "--node-token", token])["data"]
    return data.get("node", data)


def _pick(raw: dict) -> dict:
    node = {k: raw.get(k) for k in NODE_FIELDS}
    node["has_child"] = bool(node["has_child"])
    node["children"] = []
    return node


def fetch_tree(
    space_id: str,
    root: dict,
    list_children: Lister = lark_list_children,
    max_nodes: int = 3000,
) -> dict:
    """从 root 开始广度优先拉整棵子树。root 的 node_token 为空串表示空间根。"""
    count = 1
    truncated = False
    unreadable: list[dict] = []
    queue = deque([root])
    while queue:
        node = queue.popleft()
        if node["node_token"] and not node["has_child"]:
            continue
        if count >= max_nodes:
            node["unexpanded"] = True
            truncated = True
            continue
        try:
            children = list_children(space_id, node["node_token"])
        except LarkError as exc:
            node["error"] = str(exc)
            unreadable.append({"node_token": node["node_token"], "title": node["title"], "error": str(exc)})
            continue
        for raw in children:
            if count >= max_nodes:
                node["unexpanded"] = True
                truncated = True
                break
            child = _pick(raw)
            node["children"].append(child)
            count += 1
            queue.append(child)
    return {
        "space_id": space_id,
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "count": count,
        "truncated": truncated,
        "unreadable": unreadable,
        "root": root,
    }


def resolve_root(root_ref: str | None, space: str | None, get_node: Getter = lark_get_node) -> tuple[str, dict]:
    """返回 (space_id, root 节点)。给 space 时 root 是虚拟的空间根。"""
    if space:
        return space, {
            "node_token": "",
            "obj_token": "",
            "obj_type": "space",
            "title": f"空间 {space}",
            "parent_node_token": "",
            "has_child": True,
            "children": [],
        }
    raw = get_node(root_ref)
    if not raw.get("space_id") or not raw.get("node_token"):
        raise LarkError(f"读不到节点信息：{root_ref}")
    return raw["space_id"], _pick(raw)


def iter_nodes(tree_or_node: dict, depth: int = 0, parent: dict | None = None):
    """深度优先遍历，产出 (节点, 深度, 父节点)。接受整棵树 JSON 或单个节点。"""
    node = tree_or_node.get("root", tree_or_node)
    yield node, depth, parent
    for child in node.get("children", []):
        yield from iter_nodes(child, depth + 1, node)


def index_tree(tree: dict) -> dict[str, dict]:
    """node_token → {node, parent_token, depth}，不含空间根这种没有 token 的虚拟节点。"""
    result = {}
    for node, depth, parent in iter_nodes(tree):
        if node["node_token"]:
            result[node["node_token"]] = {
                "node": node,
                "parent_token": parent["node_token"] if parent else node.get("parent_node_token", ""),
                "depth": depth,
            }
    return result


def render_text(tree: dict, tokens: bool = False, max_depth: int | None = None) -> str:
    root = tree.get("root", tree)
    lines = [_label(root, tokens)]

    def walk(node: dict, prefix: str, depth: int) -> None:
        children = node.get("children", [])
        if max_depth is not None and depth >= max_depth:
            if children:
                lines.append(f"{prefix}└─ …（{len(children)} 个子节点未展开）")
            return
        for i, child in enumerate(children):
            last = i == len(children) - 1
            lines.append(f"{prefix}{'└─' if last else '├─'} {_label(child, tokens)}")
            walk(child, prefix + ("   " if last else "│  "), depth + 1)

    walk(root, "", 0)
    return "\n".join(lines)


def _label(node: dict, tokens: bool) -> str:
    parts = [node.get("title") or "（无标题）"]
    obj_type = node.get("obj_type")
    if obj_type and obj_type not in ("docx", "space"):
        parts.append(f"[{obj_type}]")
    if node.get("unexpanded"):
        parts.append("（未展开）")
    if node.get("error"):
        parts.append("（读取失败）")
    if tokens and node.get("node_token"):
        parts.append(f"<{node['node_token']}>")
    return " ".join(parts)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fetch", help="拉取子树结构")
    target = f.add_mutually_exclusive_group(required=True)
    target.add_argument("--root", help="wiki 链接或节点 token")
    target.add_argument("--space", help="空间 ID，个人文档库写 my_library")
    f.add_argument("--out", required=True)
    f.add_argument("--max-nodes", type=int, default=3000)
    r = sub.add_parser("render", help="把 tree.json 渲染成文字树")
    r.add_argument("tree")
    r.add_argument("--tokens", action="store_true", help="在每个节点后附 node_token")
    r.add_argument("--max-depth", type=int)
    args = parser.parse_args(argv)

    if args.cmd == "render":
        tree = json.loads(Path(args.tree).read_text(encoding="utf-8"))
        print(render_text(tree, tokens=args.tokens, max_depth=args.max_depth))
        return 0

    try:
        space_id, root = resolve_root(args.root, args.space)
        tree = fetch_tree(space_id, root, max_nodes=args.max_nodes)
    except LarkError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1
    Path(args.out).write_text(json.dumps(tree, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"共 {tree['count']} 个节点 → {args.out}")
    if tree["truncated"]:
        print(f"⚠️ 超过 {args.max_nodes} 个节点，部分子树未展开")
    if tree["unreadable"]:
        print(f"⚠️ {len(tree['unreadable'])} 个节点的子节点读取失败，见 JSON 的 unreadable")
    return 0


if __name__ == "__main__":
    sys.exit(main())
