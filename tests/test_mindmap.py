import json

import pytest

from conftest import load_script

mm = load_script("feishu-diagram", "mindmap")


def test_parse_nested_tree_with_bullets_and_tabs():
    root = mm.parse_tree("公司\n  - 研发\n\t- 测试\n    前端\n")
    assert root.text == "公司"
    assert [c.text for c in root.children] == ["研发", "测试"]
    assert [c.text for c in root.children[1].children] == ["前端"]


def test_literal_backslash_n_becomes_newline():
    root = mm.parse_tree("根\\n副标题\n")
    assert root.text == "根\n副标题"


@pytest.mark.parametrize(
    "text, message",
    [
        ("", "没有任何节点"),
        ("a\nb\n", "只能有一个根节点"),
        ("  a\n", "第一行必须是根节点"),
        ("a\n    b\n", "跳级"),
        ("a\n   b\n", "2 的倍数"),
    ],
)
def test_parse_rejects_bad_input(text, message):
    with pytest.raises(mm.TreeError, match=message):
        mm.parse_tree(text)


def test_small_tree_uses_up_down_and_links_ids():
    root = mm.parse_tree("根\n  甲\n    甲1\n  乙\n")
    nodes = mm.build_nodes(root)
    by_id = {n["id"]: n for n in nodes}
    top = nodes[0]
    assert top["mind_map_root"]["layout"] == "up_down"
    assert top["mind_map_root"]["left_children"] == []
    first_level = top["mind_map_root"]["right_children"]
    assert [by_id[i]["text"]["text"] for i in first_level] == ["甲", "乙"]
    jia = by_id[first_level[0]]
    assert "layout_position" not in jia["mind_map_node"]
    assert [by_id[i]["text"]["text"] for i in jia["mind_map_node"]["children"]] == ["甲1"]
    assert all(n["x"] == 0 and n["y"] == 0 for n in nodes)
    for n in nodes[1:]:
        assert n["mind_map"]["parent_id"] == n["mind_map_node"]["parent_id"]


def test_large_tree_switches_to_left_right_and_balances_sides():
    lines = ["根"]
    for i in range(6):
        lines.append(f"  分支{i}")
        lines += [f"    叶{i}-{j}" for j in range(10)]
    nodes = mm.build_nodes(mm.parse_tree("\n".join(lines)))
    root = nodes[0]["mind_map_root"]
    assert root["layout"] == "left_right"
    assert len(root["left_children"]) == 3 and len(root["right_children"]) == 3
    by_id = {n["id"]: n for n in nodes}
    for side in ("left", "right"):
        for cid in root[f"{side}_children"]:
            assert by_id[cid]["mind_map_node"]["layout_position"] == side
            grandchild = by_id[by_id[cid]["mind_map_node"]["children"][0]]
            assert "layout_position" not in grandchild["mind_map_node"]


def test_cli_writes_nodes_file(tmp_path):
    src = tmp_path / "t.txt"
    src.write_text("根\n  子\n", encoding="utf-8")
    out = tmp_path / "nodes.json"
    assert mm.main([str(src), "--out", str(out)]) == 0
    assert len(json.loads(out.read_text(encoding="utf-8"))["nodes"]) == 2
