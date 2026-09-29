"""工作进度交接单：本地存档 + 通过项目 git 的 nova-handoff 分支跨机器传递。

交接单提交到独立分支 nova-handoff 的 handoff/ 目录下，用 git 底层命令完成，
不切分支、不碰工作区和暂存区，也不进当前分支的历史。

用法（在项目仓库内运行）：
    python handoff.py init "标题"                 生成交接单路径并采集 git 现状（JSON）
    python handoff.py publish 交接单.md [--no-push] 提交到 nova-handoff 分支并推送
    python handoff.py list [--limit 10] [--no-fetch] 列出本地和远端分支上的交接单（新的在前）
    python handoff.py show 文件名 [--out 路径]       取出分支上的某份交接单
"""
from __future__ import annotations

import argparse
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

BRANCH = "nova-handoff"
DIR_IN_BRANCH = "handoff"
LOCAL_DIR = Path(".nova") / "handoff"


class HandoffError(RuntimeError):
    pass


def git(*args: str, cwd: Path | None = None, env: dict | None = None, check: bool = True,
        strip: bool = True) -> str:
    proc = subprocess.run(
        ["git", *args], cwd=cwd, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    if check and proc.returncode != 0:
        raise HandoffError(f"git {' '.join(args)} 失败：{proc.stderr.strip() or proc.stdout.strip()}")
    return proc.stdout.strip() if strip else proc.stdout


def dirty_files(root: Path) -> list[str]:
    """未提交改动的文件（含未跟踪），路径相对仓库根。"""
    entries = git("status", "--porcelain", "-z", cwd=root, strip=False).split("\0")
    files, skip_next = [], False
    for entry in entries:
        if skip_next:  # 重命名条目后面跟着原路径
            skip_next = False
            continue
        if len(entry) > 3:
            files.append(entry[3:])
            skip_next = entry[0] in "RC"
    return files


def repo_root(cwd: Path | None = None) -> Path:
    out = git("rev-parse", "--show-toplevel", cwd=cwd, check=False)
    if not out:
        raise HandoffError("当前目录不在 git 仓库里")
    return Path(out)


def slugify(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:48].strip("-")
    return slug or "handoff"


def default_remote(root: Path) -> str | None:
    remotes = git("remote", cwd=root).split()
    if not remotes:
        return None
    return "origin" if "origin" in remotes else remotes[0]


def ref_sha(root: Path, ref: str) -> str | None:
    return git("rev-parse", "-q", "--verify", f"{ref}^{{commit}}", cwd=root, check=False) or None


def init_info(title: str, root: Path, now: datetime | None = None) -> dict:
    now = now or datetime.now()
    name = f"{now:%Y%m%d-%H%M%S}-{slugify(title)}.md"
    remote = default_remote(root)
    remote_branch = None
    if remote:
        heads = git("ls-remote", "--heads", remote, BRANCH, cwd=root, check=False)
        remote_branch = bool(heads)
    return {
        "path": str(root / LOCAL_DIR / name),
        "name": name,
        "title": title,
        "saved_at": now.isoformat(timespec="seconds"),
        "machine": socket.gethostname(),
        "branch": git("rev-parse", "--abbrev-ref", "HEAD", cwd=root, check=False) or "(无提交)",
        "commit": ref_sha(root, "HEAD") or "",
        "dirty_files": dirty_files(root),
        "remote": remote,
        "remote_branch_exists": remote_branch,
    }


def fetch(root: Path, remote: str) -> bool:
    """把远端 nova-handoff 取到 refs/remotes/【remote】/nova-handoff；远端没有该分支时返回 False。"""
    heads = git("ls-remote", "--heads", remote, BRANCH, cwd=root)
    if not heads:
        return False
    git("fetch", "-q", remote, f"+refs/heads/{BRANCH}:refs/remotes/{remote}/{BRANCH}", cwd=root)
    return True


def _is_ancestor(root: Path, a: str, b: str) -> bool:
    return subprocess.run(["git", "merge-base", "--is-ancestor", a, b], cwd=root, capture_output=True).returncode == 0


def publish(file: Path, root: Path, push: bool = True) -> dict:
    file = file.resolve()
    if not file.is_file():
        raise HandoffError(f"找不到交接单：{file}")
    remote = default_remote(root) if push else None
    remote_tip = None
    if remote and fetch(root, remote):
        remote_tip = ref_sha(root, f"refs/remotes/{remote}/{BRANCH}")
    local_tip = ref_sha(root, f"refs/heads/{BRANCH}")

    parents: list[str] = []
    base = remote_tip or local_tip
    if base:
        parents.append(base)
    if local_tip and remote_tip and local_tip != remote_tip and not _is_ancestor(root, local_tip, remote_tip):
        parents.append(local_tip)  # 本机还有没推上去的交接单，合并进来别丢

    git_dir = Path(git("rev-parse", "--absolute-git-dir", cwd=root))
    fd, index_path = tempfile.mkstemp(prefix="nova-handoff-", suffix=".index", dir=git_dir)
    os.close(fd)
    os.unlink(index_path)
    env = {**os.environ, "GIT_INDEX_FILE": index_path}
    try:
        if base:
            git("read-tree", base, cwd=root, env=env)
        if len(parents) == 2:
            for line in git("ls-tree", "-r", "-z", local_tip, cwd=root).split("\0"):
                if not line:
                    continue
                meta, path = line.split("\t", 1)
                mode, _, sha = meta.split()
                if not git("ls-files", "--", path, cwd=root, env=env):
                    git("update-index", "--add", "--cacheinfo", f"{mode},{sha},{path}", cwd=root, env=env)
        blob = git("hash-object", "-w", str(file), cwd=root)
        target = f"{DIR_IN_BRANCH}/{file.name}"
        git("update-index", "--add", "--cacheinfo", f"100644,{blob},{target}", cwd=root, env=env)
        tree = git("write-tree", cwd=root, env=env)
    finally:
        if os.path.exists(index_path):
            os.unlink(index_path)

    parent_args = [arg for p in parents for arg in ("-p", p)]
    commit = git("commit-tree", tree, *parent_args, "-m", f"handoff: {file.name}", cwd=root)
    git("update-ref", f"refs/heads/{BRANCH}", commit, cwd=root)
    pushed = False
    if remote:
        git("push", "-q", remote, f"refs/heads/{BRANCH}:refs/heads/{BRANCH}", cwd=root)
        git("update-ref", f"refs/remotes/{remote}/{BRANCH}", commit, cwd=root)
        pushed = True
    return {"branch": BRANCH, "commit": commit, "file": target, "remote": remote, "pushed": pushed,
            "created_remote_branch": pushed and remote_tip is None}


def parse_frontmatter(text: str) -> dict:
    if not text.startswith("---"):
        return {}
    meta = {}
    for line in text.splitlines()[1:]:
        if line.strip() == "---":
            break
        if ":" in line and not line.startswith((" ", "-")):
            key, value = line.split(":", 1)
            meta[key.strip()] = value.strip()
    return meta


def list_handoffs(root: Path, do_fetch: bool = True, limit: int = 10) -> list[dict]:
    remote = default_remote(root)
    refs = [f"refs/heads/{BRANCH}"]
    if remote:
        if do_fetch:
            fetch(root, remote)
        refs.append(f"refs/remotes/{remote}/{BRANCH}")
    found: dict[str, dict] = {}
    for ref in refs:
        if not ref_sha(root, ref):
            continue
        names = git("ls-tree", "-z", "--name-only", f"{ref}:{DIR_IN_BRANCH}", cwd=root, check=False)
        for name in filter(None, names.split("\0")):
            entry = found.setdefault(name, {"name": name, "refs": []})
            entry["refs"].append(ref)
    local_dir = root / LOCAL_DIR
    if local_dir.is_dir():
        for path in local_dir.glob("*.md"):
            found.setdefault(path.name, {"name": path.name, "refs": []})["local"] = str(path)
    result = []
    for name in sorted(found, reverse=True)[:limit]:
        entry = found[name]
        text = _read_entry(root, entry)
        meta = parse_frontmatter(text)
        entry.update({k: meta.get(k, "") for k in ("title", "saved_at", "machine", "branch", "commit")})
        entry["published"] = bool(entry["refs"])
        result.append(entry)
    return result


def _read_entry(root: Path, entry: dict) -> str:
    if entry.get("local"):
        return Path(entry["local"]).read_text(encoding="utf-8")
    return git("show", f"{entry['refs'][-1]}:{DIR_IN_BRANCH}/{entry['name']}", cwd=root)


def show(name: str, root: Path) -> str:
    remote = default_remote(root)
    refs = [f"refs/heads/{BRANCH}"] + ([f"refs/remotes/{remote}/{BRANCH}"] if remote else [])
    for ref in reversed(refs):
        if ref_sha(root, ref):
            text = git("show", f"{ref}:{DIR_IN_BRANCH}/{name}", cwd=root, check=False)
            if text:
                return text
    local = root / LOCAL_DIR / name
    if local.is_file():
        return local.read_text(encoding="utf-8")
    raise HandoffError(f"找不到交接单：{name}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_init = sub.add_parser("init")
    p_init.add_argument("title")
    p_pub = sub.add_parser("publish")
    p_pub.add_argument("file")
    p_pub.add_argument("--no-push", action="store_true")
    p_list = sub.add_parser("list")
    p_list.add_argument("--limit", type=int, default=10)
    p_list.add_argument("--no-fetch", action="store_true")
    p_show = sub.add_parser("show")
    p_show.add_argument("name")
    p_show.add_argument("--out")
    args = parser.parse_args(argv)
    try:
        root = repo_root()
        if args.cmd == "init":
            out = init_info(args.title, root)
        elif args.cmd == "publish":
            out = publish(Path(args.file), root, push=not args.no_push)
        elif args.cmd == "list":
            out = list_handoffs(root, do_fetch=not args.no_fetch, limit=args.limit)
        else:
            text = show(args.name, root)
            if args.out:
                Path(args.out).parent.mkdir(parents=True, exist_ok=True)
                Path(args.out).write_text(text, encoding="utf-8")
                out = {"saved": args.out}
            else:
                print(text)
                return 0
    except HandoffError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
