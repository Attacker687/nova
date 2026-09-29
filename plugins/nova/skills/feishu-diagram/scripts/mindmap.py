"""把缩进树文本转成飞书画板的 mind_map 节点 JSON。

用法：
    python mindmap.py 树.txt --out nodes.json [--layout auto|up_down|left_right]

输入格式：每行一个节点，用 2 个空格（或 1 个 Tab）表示一层缩进，行首的 "- " 可有可无；
只能有一个根节点。节点文字里写字面的 \\n 表示换行。

输出 {"nodes": [...]}，直接作为
    lark-cli api POST board/v1/whiteboards/【画板】/nodes --as user --data @nodes.json
的请求体。坐标全给 0，由飞书自动排布；节点数超过阈值时自动改成左右布局。
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

LEFT_RIGHT_THRESHOLD = 50

# 按层级由深到浅的蓝色系（底色, 边框）；超出层数用最后一档。
DEPTH_COLORS = [
    ("#BAE0FF", "#1677FF"),
    ("#D6E4FF", "#2F54EB"),
    ("#E6F4FF", "#4096FF"),
    ("#F0F5FF", "#85A5FF"),
]


@dataclass
class Node:
    text: str
    children: list["Node"] = field(default_factory=list)


class TreeError(ValueError):
    pass


def parse_tree(text: str) -> Node:
    """解析缩进树，返回唯一的根节点。"""
    stack: list[tuple[int, Node]] = []
    root: Node | None = None
    for lineno, raw in enumerate(text.splitlines(), 1):
        if not raw.strip():
            continue
        expanded = raw.replace("\t", "  ")
        indent = len(expanded) - len(expanded.lstrip(" "))
        if indent % 2:
            raise TreeError(f"第 {lineno} 行缩进不是 2 的倍数")
        level = indent // 2
        label = expanded.strip()
        if label.startswith(("- ", "* ")):
            label = label[2:].strip()
        node = Node(label.replace("\\n", "\n"))
        if level == 0:
            if root is not None:
                raise TreeError(f"第 {lineno} 行：只能有一个根节点")
            root = node
            stack = [(0, node)]
            continue
        if root is None:
            raise TreeError(f"第 {lineno} 行：第一行必须是根节点（不缩进）")
        while stack and stack[-1][0] >= level:
            stack.pop()
        if not stack or stack[-1][0] != level - 1:
            raise TreeError(f"第 {lineno} 行缩进跳级")
        stack[-1][1].children.append(node)
        stack.append((level, node))
    if root is None:
        raise TreeError("没有任何节点")
    return root


def count_nodes(node: Node) -> int:
    return 1 + sum(count_nodes(c) for c in node.children)


def split_sides(children: list[Node]) -> list[str]:
    """一级节点按子树大小贪心分到左右两侧，返回与 children 对应的 "left"/"right"。"""
    order = sorted(range(len(children)), key=lambda i: -count_nodes(children[i]))
    load = {"right": 0, "left": 0}
    sides = [""] * len(children)
    for i in order:
        side = "right" if load["right"] <= load["left"] else "left"
        sides[i] = side
        load[side] += count_nodes(children[i])
    return sides


def _style(depth: int) -> dict:
    fill, border = DEPTH_COLORS[min(depth, len(DEPTH_COLORS) - 1)]
    return {
        "fill_color": fill,
        "fill_opacity": 100,
        "border_color": border,
        "border_style": "solid",
        "border_width": "extra_narrow",
    }


def build_nodes(root: Node, layout: str = "auto") -> list[dict]:
    if layout == "auto":
        layout = "left_right" if count_nodes(root) > LEFT_RIGHT_THRESHOLD else "up_down"
    if layout not in ("up_down", "left_right"):
        raise TreeError(f"未知布局：{layout}")

    nodes: list[dict] = []
    counter = iter(range(1_000_000))

    def emit(node: Node, parent_id: str, depth: int, side: str) -> str:
        node_id = f"n{next(counter)}"
        obj = {
            "id": node_id,
            "type": "mind_map",
            "x": 0,
            "y": 0,
            "mind_map": {"parent_id": parent_id},
            "text": {"text": node.text},
            "style": _style(depth),
        }
        nodes.append(obj)
        if depth == 0:
            obj["mind_map_root"] = {
                "layout": layout,
                "line_style": "round_angle",
                "type": "mind_map_round_rect",
                "left_children": [],
                "right_children": [],
            }
            for child, child_side in zip(node.children, split_sides(node.children)):
                if layout == "up_down":
                    child_side = "right"
                cid = emit(child, node_id, 1, child_side)
                obj["mind_map_root"][f"{child_side}_children"].append(cid)
        else:
            block = {
                "parent_id": parent_id,
                "type": "mind_map_round_rect",
                "children": [],
                "collapsed": False,
            }
            if depth == 1 and layout == "left_right":
                block["layout_position"] = side
            obj["mind_map_node"] = block
            for child in node.children:
                block["children"].append(emit(child, node_id, depth + 1, side))
        return node_id

    emit(root, "", 0, "right")
    return nodes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("tree", help="缩进树文本文件")
    parser.add_argument("--out", required=True, help="输出的 nodes.json")
    parser.add_argument("--layout", default="auto", choices=["auto", "up_down", "left_right"])
    args = parser.parse_args(argv)
    try:
        root = parse_tree(Path(args.tree).read_text(encoding="utf-8"))
        nodes = build_nodes(root, args.layout)
    except TreeError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1
    Path(args.out).write_text(json.dumps({"nodes": nodes}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"已生成 {len(nodes)} 个节点 → {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
