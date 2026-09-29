import pytest

from conftest import load_script

wt = load_script("feishu-wiki", "wiki_tree")


def raw(token, title, has_child=False, parent="", obj_type="docx"):
    return {
        "node_token": token,
        "obj_token": f"obj-{token}",
        "obj_type": obj_type,
        "title": title,
        "parent_node_token": parent,
        "has_child": has_child,
        "space_id": "sp",
    }


FAKE = {
    "": [raw("A", "手册", True), raw("B", "欢迎")],
    "A": [raw("A1", "安装", True, "A"), raw("A2", "表格", False, "A", "sheet")],
    "A1": [raw("A11", "Windows", False, "A1")],
}


def fake_list(space_id, parent):
    assert space_id == "sp"
    return FAKE[parent]


def space_root():
    return wt.resolve_root(None, "sp")[1]


def test_fetch_whole_space_builds_nested_tree():
    tree = wt.fetch_tree("sp", space_root(), fake_list)
    assert tree["count"] == 6
    assert not tree["truncated"] and tree["unreadable"] == []
    idx = wt.index_tree(tree)
    assert set(idx) == {"A", "B", "A1", "A2", "A11"}
    assert idx["A11"]["parent_token"] == "A1" and idx["A11"]["depth"] == 3
    assert idx["A"]["parent_token"] == ""


def test_fetch_from_node_root():
    space, root = wt.resolve_root("A", None, lambda t: raw("A", "手册", True))
    tree = wt.fetch_tree(space, root, fake_list)
    assert space == "sp"
    assert [n["node_token"] for n, _, _ in wt.iter_nodes(tree)] == ["A", "A1", "A11", "A2"]


def test_max_nodes_marks_unexpanded():
    tree = wt.fetch_tree("sp", space_root(), fake_list, max_nodes=3)
    assert tree["truncated"] and tree["count"] == 3
    assert any(n.get("unexpanded") for n, _, _ in wt.iter_nodes(tree))


def test_unreadable_subtree_is_recorded_not_fatal():
    def flaky(space_id, parent):
        if parent == "A1":
            raise wt.LarkError("permission denied")
        return fake_list(space_id, parent)

    tree = wt.fetch_tree("sp", space_root(), flaky)
    assert tree["unreadable"] == [{"node_token": "A1", "title": "安装", "error": "permission denied"}]
    assert tree["count"] == 5


def test_resolve_root_rejects_missing_space():
    with pytest.raises(wt.LarkError):
        wt.resolve_root("x", None, lambda t: {"title": "?"})


def test_render_text_draws_tree_and_types():
    tree = wt.fetch_tree("sp", space_root(), fake_list)
    text = wt.render_text(tree)
    assert text.splitlines() == [
        "空间 sp",
        "├─ 手册",
        "│  ├─ 安装",
        "│  │  └─ Windows",
        "│  └─ 表格 [sheet]",
        "└─ 欢迎",
    ]
    assert "<A11>" in wt.render_text(tree, tokens=True)
    assert "未展开" in wt.render_text(tree, max_depth=1)
