"""核对文档里的代码出处（`路径:行号` 或 `路径:起-止`）是否真实存在。

用法：
    python refcheck.py 【文档文件或目录…】 --root 【代码根目录】 [--json]

路径先按代码根拼接；找不到时按「以该路径结尾」在代码根下查找，唯一命中即算有效，
多处命中报「有歧义」。行号超出文件行数报「行号越界」。有问题时退出码为 1。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from inventory import CONFIG_EXT, DOC_EXT, LANGUAGES, list_files  # noqa: E402

KNOWN_EXT = set(LANGUAGES) | CONFIG_EXT | DOC_EXT
REF_RE = re.compile(r"(?<![\w/.:-])((?:[\w.@-]+/)*[\w@-][\w.@-]*\.([A-Za-z0-9]{1,6})):(\d+)(?:-(\d+))?(?!\d)")


def find_refs(text: str) -> list[dict]:
    refs = []
    for lineno, line in enumerate(text.splitlines(), 1):
        for m in REF_RE.finditer(line):
            if f".{m.group(2).lower()}" not in KNOWN_EXT:
                continue
            start = int(m.group(3))
            end = int(m.group(4)) if m.group(4) else start
            refs.append({"doc_line": lineno, "ref": m.group(0), "path": m.group(1), "start": start, "end": end})
    return refs


class Resolver:
    def __init__(self, root: Path):
        self.root = root
        self.files = list_files(root)
        self._lines: dict[str, int] = {}

    def resolve(self, path: str) -> tuple[str | None, str | None]:
        """返回 (相对路径, 问题)。"""
        if (self.root / path).is_file():
            return path, None
        hits = [f for f in self.files if f.endswith("/" + path)]
        if len(hits) == 1:
            return hits[0], None
        if len(hits) > 1:
            return None, f"有歧义（{len(hits)} 处同名）"
        return None, "文件不存在"

    def line_count(self, rel: str) -> int:
        if rel not in self._lines:
            data = (self.root / rel).read_bytes()
            self._lines[rel] = data.count(b"\n") + (0 if data.endswith(b"\n") or not data else 1)
        return self._lines[rel]


def check(docs: list[Path], root: Path) -> dict:
    resolver = Resolver(root)
    problems, total = [], 0
    for doc in docs:
        for ref in find_refs(doc.read_text(encoding="utf-8", errors="replace")):
            total += 1
            rel, problem = resolver.resolve(ref["path"])
            if rel and not problem:
                count = resolver.line_count(rel)
                if ref["start"] < 1 or ref["end"] > count or ref["end"] < ref["start"]:
                    problem = f"行号越界（文件共 {count} 行）"
            if problem:
                problems.append({"doc": doc.as_posix(), "doc_line": ref["doc_line"], "ref": ref["ref"],
                                 "problem": problem})
    return {"refs": total, "problems": problems}


def collect_docs(targets: list[str]) -> list[Path]:
    docs = []
    for target in targets:
        p = Path(target)
        docs += sorted(p.rglob("*.md")) if p.is_dir() else [p]
    return docs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("docs", nargs="+")
    parser.add_argument("--root", required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    result = check(collect_docs(args.docs), Path(args.root).resolve())
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"共 {result['refs']} 处代码出处，问题 {len(result['problems'])} 处")
        for p in result["problems"]:
            print(f"- {p['doc']}:{p['doc_line']}  {p['ref']}  {p['problem']}")
    return 1 if result["problems"] else 0


if __name__ == "__main__":
    sys.exit(main())
