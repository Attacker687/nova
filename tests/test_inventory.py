import json
import subprocess

import pytest

from conftest import load_script

inv = load_script("codemap", "inventory")


def write(root, rel, text=""):
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def git(root, *args):
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


@pytest.fixture
def project(tmp_path):
    root = tmp_path / "shop"
    write(root, "order-service/pom.xml", "<project/>")
    write(root, "order-service/src/main/java/shop/OrderController.java",
          "package shop;\n@RestController\npublic class OrderController {\n  @GetMapping(\"/orders\")\n  List<Order> list() { return null; }\n}\n")
    write(root, "order-service/src/main/java/shop/Order.java", "package shop;\nclass Order {}\n")
    write(root, "order-service/src/test/java/shop/OrderControllerTest.java", "class OrderControllerTest {}\n")
    write(root, "web/package.json", "{}")
    write(root, "web/src/router.ts", "export const routes = [\n  { path: '/' },\n];\n")
    write(root, "web/src/App.spec.ts", "test('x', () => {});\n")
    write(root, "tools/run.py", "import argparse\nif __name__ == '__main__':\n    argparse.ArgumentParser()\n")
    write(root, "README.md", "# shop\n")
    write(root, "web/node_modules/lib/index.js", "ignored\n")
    (root / "logo.png").write_bytes(b"\x89PNG\0\0binary")
    return root


def test_classify():
    assert inv.classify("a/b/Foo.java") == ("source", "Java")
    assert inv.classify("src/test/java/FooTest.java") == ("test", "Java")
    assert inv.classify("pkg/test_util.py") == ("test", "Python")
    assert inv.classify("x/y.spec.ts") == ("test", "TypeScript")
    assert inv.classify("pom.xml") == ("config", "")
    assert inv.classify("docs/a.md") == ("doc", "")
    assert inv.classify("logo.png") == ("other", "")


def test_inventory_without_git(project):
    result = inv.inventory(project)
    paths = [f["path"] for f in result["files"]]
    assert not any("node_modules" in p for p in paths)
    assert result["commit"] is None
    totals = result["totals"]
    assert totals["source_files"] == 4 and totals["test_files"] == 2
    assert totals["by_language"] == {"Java": 2, "TypeScript": 1, "Python": 1}
    modules = {m["path"]: m for m in result["modules"]}
    assert modules["order-service"]["marker"] == "pom.xml"
    assert modules["order-service"]["source_files"] == 2 and modules["order-service"]["test_files"] == 1
    assert modules["web"]["marker"] == "package.json"
    assert modules["tools"]["marker"] is None
    kinds = {(h["path"].rsplit("/", 1)[-1], h["kind"]) for h in result["entry_hints"]}
    assert ("OrderController.java", "http") in kinds
    assert ("router.ts", "route") in kinds
    assert ("run.py", "main") in kinds


@pytest.mark.parametrize("line", [
    "export const routes = [",
    "const routes: Routes = [",
    "  routes: [",
    "const router = createRouter({",
])
def test_route_hints(line):
    assert [h["kind"] for h in inv.entry_hints(line)] == ["route"]


@pytest.mark.parametrize("line", ["axios.get('/api/orders')", "  return request.post(url, data)", "fetch(`/api/x`)"])
def test_api_call_hints(line):
    assert [h["kind"] for h in inv.entry_hints(line)] == ["api-call"]


def test_plain_code_has_no_hints():
    assert inv.entry_hints("const reroutes = compute();\nfunction mainly() {}\n") == []


def test_batches_respect_modules_and_limits(project):
    for i in range(5):
        write(project, f"order-service/src/main/java/shop/Svc{i}.java", "class S {}\n" * 10)
    result = inv.inventory(project, max_files=3, max_lines=1000)
    batches = result["batches"]
    assert all(len(b["files"]) <= 3 for b in batches)
    assert all(len({f.split("/")[0] for f in b["files"]}) == 1 for b in batches)
    covered = [f for b in batches for f in b["files"]]
    sources = [f["path"] for f in result["files"] if f["kind"] == "source"]
    assert sorted(covered) == sorted(sources)
    assert [b["id"] for b in batches] == [f"B{i:02d}" for i in range(1, len(batches) + 1)]


def test_single_huge_file_gets_its_own_batch():
    files = [
        {"path": "m/a.py", "kind": "source", "lines": 10, "module": "m"},
        {"path": "m/b.py", "kind": "source", "lines": 9000, "module": "m"},
        {"path": "m/c.py", "kind": "source", "lines": 10, "module": "m"},
    ]
    batches = inv.make_batches(files, max_files=40, max_lines=6000)
    assert [b["files"] for b in batches] == [["m/a.py"], ["m/b.py"], ["m/c.py"]]


def test_git_mode_respects_gitignore_and_tracks_changes(project):
    write(project, ".gitignore", "tools/\n")
    git(project, "init", "-q", "-b", "main")
    git(project, "config", "user.email", "t@example.com")
    git(project, "config", "user.name", "t")
    git(project, "add", "-A")
    git(project, "commit", "-q", "-m", "init")
    result = inv.inventory(project)
    assert len(result["commit"]) == 40
    assert not any(f["path"].startswith("tools/") for f in result["files"])

    base = result["commit"]
    write(project, "order-service/src/main/java/shop/Order.java", "package shop;\nclass Order { int id; }\n")
    write(project, "web/src/NewPage.tsx", "export default 1\n")
    (project / "web/src/router.ts").unlink()
    changed = inv.changed_since(project, base)
    by_path = {c["path"]: c["change"] for c in changed["changed"]}
    assert by_path == {
        "order-service/src/main/java/shop/Order.java": "modified",
        "web/src/NewPage.tsx": "added",
        "web/src/router.ts": "deleted",
    }
    assert changed["modules"] == ["order-service", "web"]


def test_changed_since_in_subdirectory_reports_relative_paths(project):
    git(project, "init", "-q", "-b", "main")
    git(project, "config", "user.email", "t@example.com")
    git(project, "config", "user.name", "t")
    git(project, "add", "-A")
    git(project, "commit", "-q", "-m", "init")
    base = inv.git(project, "rev-parse", "HEAD").strip()
    write(project, "web/src/router.ts", "export const routes = [];\n")
    write(project, "order-service/src/main/java/shop/Order.java", "changed\n")
    changed = inv.changed_since(project / "web", base)
    assert [c["path"] for c in changed["changed"]] == ["src/router.ts"]


def test_cli_writes_json(project, tmp_path, capsys):
    out = tmp_path / "inv.json"
    assert inv.main([str(project), "--out", str(out)]) == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["totals"]["source_files"] == 4
    assert "切成" in capsys.readouterr().out
