import copy
import json

from conftest import load_script

wt = load_script("feishu-wiki", "wiki_tree")
wp = load_script("feishu-wiki", "wiki_plan")


def node(token, title, children=(), obj_type="docx"):
    return {"node_token": token, "obj_token": "", "obj_type": obj_type, "title": title,
            "parent_node_token": "", "has_child": bool(children), "children": list(children)}


def make_tree():
    root = node("R", "项目", [
        node("D", "设计", [node("D1", "旧方案 v1"), node("D2", "方案 v2")]),
        node("M", "会议纪要", [node("M1", "周会 0901")]),
        node("X", "杂项"),
    ])
    return {"space_id": "sp", "fetched_at": "2026-09-29T00:00:00+00:00", "count": 7,
            "truncated": False, "unreadable": [], "root": root}


ITEMS = [
    {"id": "W-001", "action": "create", "parent": "R", "new_title": "归档", "reason": "没有归档区"},
    {"id": "W-002", "action": "archive", "node": "D1", "target": "new:W-001", "reason": "已被 v2 取代"},
    {"id": "W-003", "action": "rename", "node": "X", "new_title": "参考资料", "reason": "名字太笼统"},
    {"id": "W-004", "action": "move", "node": "M1", "target": "D", "reason": "内容是设计评审"},
    {"id": "W-005", "action": "manual", "node": "D2", "reason": "正文过长，建议拆分"},
]


def test_valid_items_pass():
    assert wp.validate_items(ITEMS, make_tree()) == []


def test_validation_catches_bad_items():
    bad = [
        {"id": "W-1", "action": "move"},
        {"id": "W-002", "action": "fly", "node": "D1"},
        {"id": "W-003", "action": "move", "node": "nope", "target": "D"},
        {"id": "W-004", "action": "move", "node": "D1", "target": "new:W-999"},
        {"id": "W-005", "action": "rename", "node": "X", "new_title": " "},
        {"id": "W-005", "action": "create", "parent": "R", "new_title": "a"},
    ]
    problems = "\n".join(wp.validate_items(bad, make_tree()))
    for expected in ["W-1", "不认识", "不在树里", "W-004 缺少有效的 target", "W-005 缺少 new_title", "W-005 编号重复"]:
        assert expected in problems


def test_report_groups_items_with_checkboxes_and_preview():
    xml = wp.render_report(make_tree(), ITEMS)
    assert xml.startswith("<title>wiki 整理报告：项目</title>")
    assert f"<p>{wp.summary_line(4)}</p>" in xml
    assert '<checkbox done="false">[W-002] 「旧方案 v1」→ 移到「归档」下：已被 v2 取代</checkbox>' in xml
    assert '<checkbox done="false">[W-001] 在「项目」下新建「归档」：没有归档区</checkbox>' in xml
    assert "<li>[W-005] 「方案 v2」：正文过长，建议拆分</li>" in xml
    assert "归档〔新建〕" in xml and "参考资料〔改名〕" in xml
    assert xml.index("<h1>新建节点") < xml.index("<h1>改名") < xml.index("<h1>移动")


def test_report_escapes_xml_special_characters():
    tree = make_tree()
    tree["root"]["children"][2]["title"] = "A & B <草稿>"
    items = [{"id": "W-001", "action": "rename", "node": "X", "new_title": "C < D", "reason": "x"}]
    xml = wp.render_report(tree, items)
    assert "A &amp; B &lt;草稿&gt;" in xml and "C &lt; D" in xml
    assert "<草稿>" not in xml


def test_empty_report_says_nothing_to_do():
    xml = wp.render_report(make_tree(), [])
    assert wp.summary_line(0) in xml and "没有发现需要整理的地方" in xml


def test_preview_does_not_touch_original():
    tree = make_tree()
    before = copy.deepcopy(tree)
    after = wp.preview_tree(tree, ITEMS)
    assert tree == before
    titles = [n["title"] for n, _, _ in wt.iter_nodes(after)]
    assert "周会 0901  ← 移动" in titles


def test_parse_checked_reads_xml_checkboxes():
    xml = (
        '<checkbox done="true" id="b1">[W-001] 新建</checkbox>'
        '<checkbox done="false">[W-002] 归档</checkbox>'
        '<checkbox id="b3" done="true"><span>[W-003] 改名</span></checkbox>'
        "<li>[W-005] 手动</li>"
    )
    assert wp.parse_checked(xml) == {"checked": ["W-001", "W-003"], "unchecked": ["W-002"]}


def test_parse_checked_handles_markdown_and_escapes():
    md = "\n".join([
        "- [x] [W-001] 新建",
        "- [ ] \\[W-002\\] 归档",
        "* [X] [W-003] 改名",
        "[✓] [W-004] 移动",
        "- [W-005] 手动",
        "正文里提到 [W-006] 不算",
    ])
    assert wp.parse_checked(md) == {"checked": ["W-001", "W-003", "W-004"], "unchecked": ["W-002"]}


def test_plan_orders_steps_and_reports_unchecked():
    tree = make_tree()
    plan = wp.build_plan(tree, copy.deepcopy(tree), ITEMS, ["W-004", "W-002", "W-001", "W-005"])
    assert [s["id"] for s in plan["steps"]] == ["W-001", "W-002", "W-004"]
    assert plan["steps"][1] == {"id": "W-002", "action": "archive", "node": "D1", "target": "new:W-001",
                                "space_id": "sp"}
    assert plan["ignored"][0]["id"] == "W-005"
    assert plan["unchecked"] == ["W-003"]
    assert plan["conflicts"] == []


def test_plan_flags_nodes_changed_since_report():
    before = make_tree()
    now = copy.deepcopy(before)
    m1 = now["root"]["children"][1]["children"].pop()
    now["root"]["children"][2]["children"].append(m1)
    now["root"]["children"][2]["title"] = "杂项（已改）"
    plan = wp.build_plan(before, now, ITEMS, ["W-003", "W-004"])
    reasons = {c["id"]: c["reason"] for c in plan["conflicts"]}
    assert "移动过" in reasons["W-004"] and "改过名" in reasons["W-003"]
    assert plan["steps"] == []


def test_plan_drops_steps_whose_created_parent_is_not_checked():
    tree = make_tree()
    plan = wp.build_plan(tree, copy.deepcopy(tree), ITEMS, ["W-002"])
    assert plan["steps"] == []
    assert "没有执行" in plan["conflicts"][0]["reason"]


def test_plan_drops_chains_of_nested_creates():
    items = [
        {"id": "W-001", "action": "create", "parent": "R", "new_title": "归档"},
        {"id": "W-002", "action": "create", "parent": "new:W-001", "new_title": "2025"},
        {"id": "W-003", "action": "archive", "node": "D1", "target": "new:W-002"},
    ]
    tree = make_tree()
    plan = wp.build_plan(tree, copy.deepcopy(tree), items, ["W-002", "W-003"])
    assert plan["steps"] == []
    assert sorted(c["id"] for c in plan["conflicts"]) == ["W-002", "W-003"]


def test_plan_flags_deleted_target():
    before = make_tree()
    now = copy.deepcopy(before)
    now["root"]["children"] = [c for c in now["root"]["children"] if c["node_token"] != "D"]
    plan = wp.build_plan(before, now, ITEMS, ["W-004"])
    assert "不在树里" in plan["conflicts"][0]["reason"]


def test_cli_report_and_plan_roundtrip(tmp_path):
    tree_path, items_path = tmp_path / "tree.json", tmp_path / "items.json"
    tree_path.write_text(json.dumps(make_tree(), ensure_ascii=False), encoding="utf-8")
    items_path.write_text(json.dumps({"items": ITEMS}, ensure_ascii=False), encoding="utf-8")
    report = tmp_path / "report.md"
    assert wp.main(["report", "--tree", str(tree_path), "--items", str(items_path), "--out", str(report)]) == 0
    ticked = report.read_text(encoding="utf-8").replace('<checkbox done="false">[W-003]',
                                                        '<checkbox done="true">[W-003]')
    assert wp.parse_checked(ticked)["checked"] == ["W-003"]
    out = tmp_path / "plan.json"
    assert wp.main(["plan", "--before", str(tree_path), "--now", str(tree_path), "--items", str(items_path),
                    "--checked", "W-003", "--out", str(out)]) == 0
    assert json.loads(out.read_text(encoding="utf-8"))["steps"][0]["new_title"] == "参考资料"


def test_cli_report_rejects_invalid_items(tmp_path, capsys):
    tree_path, items_path = tmp_path / "tree.json", tmp_path / "items.json"
    tree_path.write_text(json.dumps(make_tree(), ensure_ascii=False), encoding="utf-8")
    items_path.write_text(json.dumps({"items": [{"id": "W-001", "action": "move", "node": "D1"}]}),
                          encoding="utf-8")
    assert wp.main(["report", "--tree", str(tree_path), "--items", str(items_path),
                    "--out", str(tmp_path / "r.md")]) == 1
    assert "target" in capsys.readouterr().err
