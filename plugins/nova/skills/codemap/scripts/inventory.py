"""代码地图的盘点：列出程序里的文件、按语言和用途分类、识别模块和入口线索，并切成扫描批次。

用法：
    python inventory.py 【程序根目录】 --out inventory.json [--batch-files 40] [--batch-lines 6000]
    python inventory.py 【程序根目录】 --since 【提交】 --out changed.json

在 git 仓库里只看 git 跟踪的和未被忽略的新文件；不在 git 里时跳过常见的依赖和构建目录。
--since 用于增量更新：列出该提交之后（含未提交的改动）变过的文件及其所属模块。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

LANGUAGES = {
    ".java": "Java", ".kt": "Kotlin", ".kts": "Kotlin", ".scala": "Scala", ".groovy": "Groovy",
    ".py": "Python", ".go": "Go", ".rs": "Rust", ".rb": "Ruby", ".php": "PHP", ".cs": "C#",
    ".js": "JavaScript", ".jsx": "JavaScript", ".mjs": "JavaScript", ".cjs": "JavaScript",
    ".ts": "TypeScript", ".tsx": "TypeScript", ".vue": "Vue", ".svelte": "Svelte",
    ".c": "C", ".h": "C", ".cpp": "C++", ".cc": "C++", ".hpp": "C++", ".swift": "Swift", ".m": "Objective-C",
    ".dart": "Dart", ".lua": "Lua", ".sh": "Shell", ".ps1": "PowerShell", ".sql": "SQL",
    ".html": "HTML", ".css": "CSS", ".scss": "SCSS", ".less": "Less",
}
CONFIG_EXT = {".json", ".yaml", ".yml", ".toml", ".xml", ".properties", ".ini", ".cfg", ".conf", ".env", ".gradle"}
DOC_EXT = {".md", ".rst", ".txt", ".adoc"}
MODULE_MARKERS = ("pom.xml", "build.gradle", "build.gradle.kts", "package.json", "go.mod", "pyproject.toml",
                  "setup.py", "Cargo.toml", "composer.json", "Gemfile")
SKIP_DIRS = {".git", "node_modules", "dist", "build", "target", "out", ".venv", "venv", "__pycache__", ".idea",
             ".vscode", "vendor", ".next", ".nuxt", "coverage", ".gradle", ".mvn", ".nova", ".pytest_cache"}
TEST_NAME_RE = re.compile(
    r"(^test_.*\.py$|.*_test\.(py|go|rb)$|.*Tests?\.(java|kt|cs)$|.*\.(spec|test)\.(js|jsx|ts|tsx|mjs)$)"
)
TEST_DIR_PARTS = {"test", "tests", "__tests__", "spec", "specs", "androidTest", "e2e"}
ENTRY_PATTERNS = [
    ("http", re.compile(r"@(RestController|Controller|RequestMapping|GetMapping|PostMapping|PutMapping|DeleteMapping|PatchMapping)\b")),
    ("http", re.compile(r"@(app|router|bp|blueprint|api)\.(route|get|post|put|delete|patch)\(")),
    ("http", re.compile(r"\b(app|router)\.(get|post|put|delete|patch|use)\(\s*['\"`]/")),
    ("http", re.compile(r"\.(GET|POST|PUT|DELETE|PATCH|HandleFunc|Handle)\(\s*\"/")),
    ("http", re.compile(r"\[(ApiController|Http(Get|Post|Put|Delete|Patch))\b")),
    ("route", re.compile(r"\b(createRouter|createBrowserRouter|RouterModule\.forRoot)\("
                         r"|\broutes\s*(?::\s*[\w<>\[\]]+\s*)?=\s*\[|^\s*routes\s*:\s*\[")),
    ("job", re.compile(r"@(Scheduled|KafkaListener|RabbitListener|JmsListener|EventListener|XxlJob)\b|@celery\.task|@shared_task|cron\.schedule\(")),
    ("main", re.compile(r"public\s+static\s+void\s+main\s*\(|^if\s+__name__\s*==\s*['\"]__main__['\"]|^func\s+main\s*\(|^fn\s+main\s*\(")),
    ("cli", re.compile(r"@click\.(command|group)\b|argparse\.ArgumentParser\(|\bcommander\b|yargs\(")),
    ("api-call", re.compile(r"\b(axios|request|http|api|\$http)\.(get|post|put|delete|patch)\(|\bfetch\(\s*['\"`]")),
]
MAX_HINTS_PER_FILE = 5
MAX_FILE_BYTES = 1_000_000


def git(root: Path, *args: str) -> str | None:
    proc = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, encoding="utf-8",
                          errors="replace")
    return proc.stdout if proc.returncode == 0 else None


def list_files(root: Path) -> list[str]:
    """相对 root 的 POSIX 路径。git 仓库里用 git 的视角（尊重 .gitignore）。"""
    tracked = git(root, "ls-files", "-z", "--cached", "--others", "--exclude-standard", "--", ".")
    if tracked is not None:
        files = [p for p in tracked.split("\0") if p]
        return sorted(p for p in files if not (set(PurePosixPath(p).parts[:-1]) & SKIP_DIRS)
                      and (root / p).is_file())
    result = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        rel_dir = Path(dirpath).relative_to(root)
        result += [(rel_dir / f).as_posix() for f in filenames]
    return sorted(result)


def classify(path: str) -> tuple[str, str]:
    """返回 (用途, 语言)。用途：source | test | config | doc | other。"""
    p = PurePosixPath(path)
    ext = p.suffix.lower()
    lang = LANGUAGES.get(ext, "")
    if lang:
        if TEST_NAME_RE.match(p.name) or set(p.parts[:-1]) & TEST_DIR_PARTS:
            return "test", lang
        return "source", lang
    if ext in CONFIG_EXT or p.name in MODULE_MARKERS or p.name in ("Dockerfile", "Makefile"):
        return "config", ""
    if ext in DOC_EXT:
        return "doc", ""
    return "other", ""


def read_text(path: Path) -> str | None:
    try:
        if path.stat().st_size > MAX_FILE_BYTES:
            return None
        data = path.read_bytes()
    except OSError:
        return None
    if b"\0" in data[:4096]:
        return None
    return data.decode("utf-8", errors="replace")


def entry_hints(text: str) -> list[dict]:
    hints = []
    for lineno, line in enumerate(text.splitlines(), 1):
        for kind, pattern in ENTRY_PATTERNS:
            if pattern.search(line):
                hints.append({"line": lineno, "kind": kind, "text": line.strip()[:120]})
                break
        if len(hints) >= MAX_HINTS_PER_FILE:
            break
    return hints


def module_of(path: str, module_roots: list[str]) -> str:
    """文件所属模块 = 离它最近的、含构建标记文件的祖先目录；都没有就用第一级目录。"""
    parts = PurePosixPath(path).parts[:-1]
    for i in range(len(parts), -1, -1):
        candidate = "/".join(parts[:i]) or "."
        if candidate in module_roots:
            return candidate
    return parts[0] if parts else "."


def make_batches(files: list[dict], max_files: int, max_lines: int) -> list[dict]:
    """同模块、同目录的源码尽量放同一批；超过上限就切开。"""
    batches: list[dict] = []
    ordered = sorted((f for f in files if f["kind"] == "source"), key=lambda f: (f["module"], f["path"]))
    current: dict | None = None
    for f in ordered:
        full = current and (len(current["files"]) >= max_files or current["lines"] + f["lines"] > max_lines)
        if current is None or current["module"] != f["module"] or (full and current["files"]):
            current = {"id": f"B{len(batches) + 1:02d}", "module": f["module"], "files": [], "lines": 0}
            batches.append(current)
        current["files"].append(f["path"])
        current["lines"] += f["lines"]
    return batches


def inventory(root: Path, max_files: int = 40, max_lines: int = 6000) -> dict:
    root = root.resolve()
    paths = list_files(root)
    module_roots = sorted({(PurePosixPath(p).parent.as_posix() or ".") for p in paths
                           if PurePosixPath(p).name in MODULE_MARKERS})
    files, hints = [], []
    for path in paths:
        kind, lang = classify(path)
        text = read_text(root / path) if kind in ("source", "test", "config") else None
        lines = text.count("\n") + (1 if text and not text.endswith("\n") else 0) if text else 0
        entry = {"path": path, "kind": kind, "language": lang, "lines": lines,
                 "module": module_of(path, module_roots)}
        files.append(entry)
        if kind == "source" and text:
            hints += [{"path": path, **h} for h in entry_hints(text)]

    def tally(key: str, where=lambda f: True) -> dict:
        out: dict[str, int] = {}
        for f in files:
            if f[key] and where(f):
                out[f[key]] = out.get(f[key], 0) + 1
        return dict(sorted(out.items(), key=lambda kv: -kv[1]))

    modules = []
    for name in sorted({f["module"] for f in files}):
        members = [f for f in files if f["module"] == name]
        marker = next((PurePosixPath(f["path"]).name for f in members
                       if PurePosixPath(f["path"]).name in MODULE_MARKERS
                       and (PurePosixPath(f["path"]).parent.as_posix() or ".") == name), None)
        modules.append({
            "path": name, "marker": marker,
            "source_files": sum(f["kind"] == "source" for f in members),
            "test_files": sum(f["kind"] == "test" for f in members),
            "lines": sum(f["lines"] for f in members if f["kind"] == "source"),
        })
    head = git(root, "rev-parse", "HEAD")
    return {
        "root": root.as_posix(),
        "commit": head.strip() if head else None,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "totals": {
            "files": len(files),
            "source_files": sum(f["kind"] == "source" for f in files),
            "test_files": sum(f["kind"] == "test" for f in files),
            "source_lines": sum(f["lines"] for f in files if f["kind"] == "source"),
            "by_language": tally("language", lambda f: f["kind"] == "source"),
            "by_kind": tally("kind"),
        },
        "modules": modules,
        "entry_hints": hints,
        "batches": make_batches(files, max_files, max_lines),
        "files": files,
    }


def changed_since(root: Path, commit: str) -> dict:
    root = root.resolve()
    if git(root, "cat-file", "-e", f"{commit}^{{commit}}") is None:
        raise SystemExit(f"错误：找不到提交 {commit}")
    diff = git(root, "diff", "--name-status", "-z", commit, "--", ".") or ""
    untracked = git(root, "ls-files", "-z", "--others", "--exclude-standard", "--", ".") or ""
    prefix = (git(root, "rev-parse", "--show-prefix") or "").strip()
    changes: dict[str, str] = {}
    tokens = [t for t in diff.split("\0") if t]
    i = 0
    while i < len(tokens):
        status = tokens[i][0]
        if status in "RC":
            old, new = tokens[i + 1], tokens[i + 2]
            changes[old] = "deleted"
            changes[new] = "added"
            i += 3
            continue
        changes[tokens[i + 1]] = {"A": "added", "D": "deleted"}.get(status, "modified")
        i += 2
    for p in untracked.split("\0"):
        if p:
            changes[prefix + p] = "added"
    all_paths = list_files(root)
    module_roots = sorted({(PurePosixPath(p).parent.as_posix() or ".") for p in all_paths
                           if PurePosixPath(p).name in MODULE_MARKERS})
    result = []
    for repo_path, change in sorted(changes.items()):
        if prefix and not repo_path.startswith(prefix):
            continue
        path = repo_path[len(prefix):]
        kind, lang = classify(path)
        if kind in ("source", "test", "config"):
            result.append({"path": path, "change": change, "kind": kind, "language": lang,
                           "module": module_of(path, module_roots)})
    head = git(root, "rev-parse", "HEAD")
    return {"root": root.as_posix(), "since": commit, "commit": head.strip() if head else None,
            "changed": result, "modules": sorted({c["module"] for c in result})}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("root")
    parser.add_argument("--out", required=True)
    parser.add_argument("--since", help="增量模式：只列这个提交之后变过的文件")
    parser.add_argument("--batch-files", type=int, default=40)
    parser.add_argument("--batch-lines", type=int, default=6000)
    args = parser.parse_args(argv)
    root = Path(args.root)
    if not root.is_dir():
        print(f"错误：不是目录：{root}", file=sys.stderr)
        return 1
    result = changed_since(root, args.since) if args.since else inventory(root, args.batch_files, args.batch_lines)
    Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.since:
        print(f"自 {args.since[:10]} 以来变过 {len(result['changed'])} 个文件，涉及模块：{', '.join(result['modules']) or '无'}")
    else:
        t = result["totals"]
        print(f"源码 {t['source_files']} 个文件 / {t['source_lines']} 行，测试 {t['test_files']} 个，"
              f"模块 {len(result['modules'])} 个，入口线索 {len(result['entry_hints'])} 条，"
              f"切成 {len(result['batches'])} 批 → {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
