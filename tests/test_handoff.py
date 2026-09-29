import subprocess
from datetime import datetime

import pytest

from conftest import load_script

ho = load_script("save", "handoff")


def run(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def make_repo(path, remote=None):
    path.mkdir()
    run(path, "init", "-q", "-b", "main")
    run(path, "config", "user.name", "t")
    run(path, "config", "user.email", "t@example.com")
    run(path, "config", "core.autocrlf", "false")
    (path / "a.txt").write_text("a\n")
    run(path, "add", "a.txt")
    run(path, "commit", "-q", "-m", "init")
    if remote:
        run(path, "remote", "add", "origin", str(remote))
    return path


@pytest.fixture
def remote(tmp_path):
    bare = tmp_path / "remote.git"
    run(tmp_path, "init", "-q", "--bare", str(bare))
    return bare


def write_handoff(repo, title, when):
    info = ho.init_info(title, repo, now=when)
    path = repo / ".nova" / "handoff" / info["name"]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\ntitle: {title}\nbranch: {info['branch']}\ncommit: {info['commit']}\n---\n\n正文 {title}\n",
                    encoding="utf-8")
    return path, info


def test_slugify_keeps_ascii_and_falls_back():
    assert ho.slugify("Fix Login Bug!") == "fix-login-bug"
    assert ho.slugify("修登录问题") == "handoff"


def test_init_reports_git_state(tmp_path):
    repo = make_repo(tmp_path / "r")
    (repo / "a.txt").write_text("changed\n")
    info = ho.init_info("Login 修复", repo, now=datetime(2026, 9, 29, 17, 30, 5))
    assert info["name"] == "20260929-173005-login.md"
    assert info["branch"] == "main" and len(info["commit"]) == 40
    assert info["dirty_files"] == ["a.txt"]
    assert info["remote"] is None


def test_dirty_files_handles_renames_and_untracked(tmp_path):
    repo = make_repo(tmp_path / "r")
    run(repo, "mv", "a.txt", "b.txt")
    (repo / "new file.txt").write_text("x\n")
    assert sorted(ho.dirty_files(repo)) == ["b.txt", "new file.txt"]


def test_publish_without_remote_commits_locally_and_leaves_worktree_alone(tmp_path):
    repo = make_repo(tmp_path / "r")
    path, _ = write_handoff(repo, "one", datetime(2026, 9, 29, 10, 0, 0))
    head_before = run(repo, "rev-parse", "HEAD")
    result = ho.publish(path, repo)
    assert result["pushed"] is False and result["remote"] is None
    assert run(repo, "rev-parse", "HEAD") == head_before
    assert run(repo, "rev-parse", "--abbrev-ref", "HEAD") == "main"
    assert run(repo, "status", "--porcelain") == "?? .nova/"
    assert "正文 one" in run(repo, "show", f"nova-handoff:handoff/{path.name}")


def test_publish_pushes_and_second_machine_can_list_and_show(tmp_path, remote):
    a = make_repo(tmp_path / "a", remote)
    run(a, "push", "-q", "origin", "main")
    first, info = write_handoff(a, "first", datetime(2026, 9, 29, 10, 0, 0))
    assert info["remote"] == "origin" and info["remote_branch_exists"] is False
    res = ho.publish(first, a)
    assert ho.init_info("x", a)["remote_branch_exists"] is True
    assert res["pushed"] and res["created_remote_branch"]
    second, _ = write_handoff(a, "second", datetime(2026, 9, 29, 11, 0, 0))
    res2 = ho.publish(second, a)
    assert res2["pushed"] and not res2["created_remote_branch"]

    b = tmp_path / "b"
    run(tmp_path, "clone", "-q", str(remote), str(b))
    listed = ho.list_handoffs(b)
    assert [e["title"] for e in listed] == ["second", "first"]
    assert all(e["published"] for e in listed)
    assert "正文 first" in ho.show(first.name, b)


def test_publish_merges_diverged_local_and_remote_branches(tmp_path, remote):
    a = make_repo(tmp_path / "a", remote)
    run(a, "push", "-q", "origin", "main")
    b = tmp_path / "b"
    run(tmp_path, "clone", "-q", str(remote), str(b))
    run(b, "config", "user.name", "t")
    run(b, "config", "user.email", "t@example.com")

    pa, _ = write_handoff(a, "from-a", datetime(2026, 9, 29, 10, 0, 0))
    ho.publish(pa, a)
    pb_local, _ = write_handoff(b, "b-offline", datetime(2026, 9, 29, 10, 30, 0))
    ho.publish(pb_local, b, push=False)
    pb, _ = write_handoff(b, "from-b", datetime(2026, 9, 29, 11, 0, 0))
    ho.publish(pb, b)

    files = run(b, "ls-tree", "--name-only", "origin/nova-handoff:handoff").split()
    assert sorted(files) == sorted([pa.name, pb_local.name, pb.name])


def test_list_includes_unpublished_local_files(tmp_path):
    repo = make_repo(tmp_path / "r")
    path, _ = write_handoff(repo, "draft", datetime(2026, 9, 29, 9, 0, 0))
    listed = ho.list_handoffs(repo)
    assert listed[0]["name"] == path.name and listed[0]["published"] is False


def test_show_missing_raises(tmp_path):
    repo = make_repo(tmp_path / "r")
    with pytest.raises(ho.HandoffError):
        ho.show("nope.md", repo)


def test_parse_frontmatter_ignores_lists():
    text = "---\ntitle: x\ndirty_files:\n  - a.txt\nbranch: main\n---\nbody"
    assert ho.parse_frontmatter(text) == {"title": "x", "dirty_files": "", "branch": "main"}
