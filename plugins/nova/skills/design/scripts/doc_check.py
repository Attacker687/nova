"""对照模板检查一份文档：章节齐不齐、有没有没填的占位、还有多少待确认和待定。

用法：
    python doc_check.py 文档.md --template 模板.md [--json]
    python doc_check.py 文档.md --export 输出.md       去掉文件头（--- 之间的元数据）和第一个一级标题，
                                                       用于发布到飞书；一级标题作为文档标题打印出来

章节按模板里的 `## ` 二级标题核对（忽略编号）。缺章节时退出码 1；
没填的【】占位、「待确认」、状态为「待定」的决策只报数量和位置，不算失败。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HEADING_RE = re.compile(r"^##\s+(?:\d+(?:\.\d+)*[.、]?\s*)?(.+?)\s*$")
PLACEHOLDER_RE = re.compile(r"【[^】\n]{1,60}】")
FENCE_RE = re.compile(r"^\s*(```|~~~)")


def split_frontmatter(text: str) -> tuple[dict, str]:
    if not text.startswith("---"):
        return {}, text
    lines = text.splitlines(keepends=True)
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            meta = {}
            for line in lines[1:i]:
                if ":" in line:
                    k, v = line.split(":", 1)
                    meta[k.strip()] = v.strip()
            return meta, "".join(lines[i + 1:]).lstrip("\n")
    return {}, text


def export_body(text: str) -> tuple[str, str]:
    """返回 (标题, 正文)：去掉文件头，第一个一级标题拿出来当标题。"""
    _, body = split_frontmatter(text)
    lines = body.splitlines(keepends=True)
    for i, line in enumerate(lines):
        if line.startswith("# "):
            return line[2:].strip(), "".join(lines[:i] + lines[i + 1:]).lstrip("\n")
    return "", body


def headings(body: str) -> list[str]:
    result, in_code = [], False
    for line in body.splitlines():
        if FENCE_RE.match(line):
            in_code = not in_code
            continue
        if not in_code:
            m = HEADING_RE.match(line)
            if m:
                result.append(m.group(1))
    return result


def check(doc_text: str, template_text: str) -> dict:
    meta, body = split_frontmatter(doc_text)
    _, tpl_body = split_frontmatter(template_text)
    have = headings(body)
    missing = [h for h in headings(tpl_body) if h not in have]
    placeholders, pending_confirm, mermaid, undecided, defaults = [], [], 0, [], []
    in_code = False
    for lineno, line in enumerate(body.splitlines(), 1):
        if FENCE_RE.match(line):
            if not in_code and "mermaid" in line:
                mermaid += 1
            in_code = not in_code
            continue
        if in_code:
            continue
        placeholders += [{"line": lineno, "text": m.group(0)} for m in PLACEHOLDER_RE.finditer(line)]
        if "待确认" in line:
            pending_confirm.append(lineno)
        cells = [c.strip() for c in line.strip().strip("|").split("|")] if line.lstrip().startswith("|") else []
        if len(cells) >= 5 and re.match(r"^D-\d+", cells[0]):
            if cells[4].startswith("待定"):
                undecided.append(cells[0])
            elif cells[4].startswith("默认"):
                defaults.append(cells[0])
    return {
        "status": meta.get("status", ""),
        "missing_sections": missing,
        "placeholders": placeholders,
        "pending_confirm_lines": pending_confirm,
        "mermaid_blocks": mermaid,
        "undecided": undecided,
        "defaults": defaults,
        "ok": not missing,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("doc")
    parser.add_argument("--template")
    parser.add_argument("--export", help="把去掉文件头的正文写到这个文件")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    text = Path(args.doc).read_text(encoding="utf-8")
    if args.export:
        title, body = export_body(text)
        Path(args.export).write_text(body, encoding="utf-8")
        print(f"标题：{title}\n正文 → {args.export}")
        if not args.template:
            return 0
    if not args.template:
        parser.error("需要 --template 或 --export")
    result = check(text, Path(args.template).read_text(encoding="utf-8"))
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"{'✓' if result['ok'] else '✗'} {args.doc}（status={result['status'] or '无'}）")
        if result["missing_sections"]:
            print(f"  缺章节：{'、'.join(result['missing_sections'])}")
        if result["placeholders"]:
            shown = "、".join(f"第{p['line']}行{p['text']}" for p in result["placeholders"][:8])
            print(f"  未填占位 {len(result['placeholders'])} 处：{shown}")
        print(f"  待确认 {len(result['pending_confirm_lines'])} 处 · 待定决策 {len(result['undecided'])} 项"
              f" · 默认决定 {len(result['defaults'])} 项 · mermaid 图 {result['mermaid_blocks']} 张")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
