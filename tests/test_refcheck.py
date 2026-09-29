from conftest import load_script

rc = load_script("codemap", "refcheck")


def write(root, rel, text):
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_find_refs_skips_urls_and_unknown_extensions():
    text = "\n".join([
        "见 `src/app/Order.java:12` 和 src/app/util.py:3-5",
        "服务在 http://localhost:8080/api 和 example.com:443",
        "时间 12:30，版本 v1.2:3",
        "配置 application.yml:7",
    ])
    refs = [(r["path"], r["start"], r["end"]) for r in rc.find_refs(text)]
    assert refs == [("src/app/Order.java", 12, 12), ("src/app/util.py", 3, 5), ("application.yml", 7, 7)]


def test_check_reports_missing_ambiguous_and_out_of_range(tmp_path):
    code = tmp_path / "code"
    write(code, "svc/src/Order.java", "a\nb\nc\n")
    write(code, "a/Util.py", "x\n")
    write(code, "b/Util.py", "y\n")
    write(code, "svc/src/Only.kt", "1\n2")
    doc = write(tmp_path / "docs", "map.md", "\n".join([
        "- svc/src/Order.java:3 有效",
        "- Order.java:2 按后缀唯一命中",
        "- src/Only.kt:2 无换行结尾的最后一行",
        "- Util.py:1 两处同名",
        "- svc/src/Order.java:4 越界",
        "- svc/src/Order.java:2-9 区间越界",
        "- gone/Missing.java:1 不存在",
    ]))
    result = rc.check([doc], code)
    assert result["refs"] == 7
    got = {(p["doc_line"], p["problem"].split("（")[0]) for p in result["problems"]}
    assert got == {(4, "有歧义"), (5, "行号越界"), (6, "行号越界"), (7, "文件不存在")}


def test_cli_exit_code(tmp_path, capsys):
    code = tmp_path / "code"
    write(code, "x.py", "1\n")
    docs = tmp_path / "docs"
    write(docs, "ok.md", "x.py:1")
    assert rc.main([str(docs), "--root", str(code)]) == 0
    write(docs, "bad.md", "y.py:1")
    assert rc.main([str(docs), "--root", str(code)]) == 1
    assert "文件不存在" in capsys.readouterr().out
