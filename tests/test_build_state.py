import json

import pytest

from conftest import load_script

bs = load_script("build", "build_state")

STORIES = {"feature": "f", "stories": [
    {"id": "S01", "title": "a", "depends_on": []},
    {"id": "S02", "title": "b", "depends_on": ["S01"]},
    {"id": "S03", "title": "c", "depends_on": []},
    {"id": "S04", "title": "d", "depends_on": ["S02", "S03"]},
]}


def state():
    return bs.init_state(STORIES, "nova/f", "main", "pytest -q")


def test_next_follows_dependencies_and_resumes():
    s = state()
    assert s["order"] == ["S01", "S03", "S02", "S04"]
    assert bs.next_story(s) == {"story": "S01", "resume": False}
    bs.set_status(s, "S01", "reviewing", 1)
    assert bs.next_story(s) == {"story": "S01", "resume": True}
    bs.set_status(s, "S01", "done", commit="abc")
    assert bs.next_story(s)["story"] == "S03"
    bs.set_status(s, "S03", "done")
    assert bs.next_story(s)["story"] == "S02"
    bs.set_status(s, "S02", "done")
    bs.set_status(s, "S04", "done")
    assert bs.next_story(s) == {"story": None, "all_done": True}


def test_blocked_story_holds_dependents():
    s = state()
    bs.set_status(s, "S01", "blocked", note="三轮未过")
    assert bs.next_story(s)["story"] == "S03"
    bs.set_status(s, "S03", "done")
    result = bs.next_story(s)
    assert result["story"] is None and result["blocked"] == ["S01"]
    assert sorted(result["waiting_on_blocked"]) == ["S02", "S04"]
    assert s["stories"]["S01"]["notes"][0]["text"] == "三轮未过"


def test_set_records_base_and_reviewed_commits():
    s = state()
    bs.set_status(s, "S01", "implementing", 1, base="b1")
    bs.set_status(s, "S01", "reviewing", reviewed="r1")
    assert (s["stories"]["S01"]["base"], s["stories"]["S01"]["reviewed"]) == ("b1", "r1")


def test_set_rejects_bad_values():
    s = state()
    with pytest.raises(ValueError):
        bs.set_status(s, "S01", "flying")
    with pytest.raises(KeyError):
        bs.set_status(s, "S99", "done")


def test_merge_reviews(tmp_path):
    def write(name, verdict, findings, lens=None):
        data = {"verdict": verdict, "findings": findings}
        if lens:
            data["lens"] = lens
        p = tmp_path / name
        p.write_text(json.dumps(data), encoding="utf-8")
        return str(p)

    paths = [
        write("review-general-r1.json", "approved", [{"id": "F1", "severity": "low"}]),
        write("review-adversarial-r1.json", "changes_requested", [{"id": "F1", "severity": "high"}]),
        write("x.json", "approved", [{"id": "F1", "severity": "medium"}], lens="edge"),
    ]
    merged = bs.merge_reviews(paths)
    assert merged["lenses"] == ["general", "adversarial", "edge"]
    assert merged["verdict"] == "changes_requested"
    assert [f["id"] for f in merged["findings"]] == ["adversarial-F1", "edge-F1", "general-F1"]
    assert merged["counts"] == {"critical": 0, "high": 1, "medium": 1, "low": 1}
    ok = bs.merge_reviews([paths[0], paths[2]])
    assert ok["verdict"] == "approved"


def test_cli_roundtrip(tmp_path, capsys):
    stories = tmp_path / "stories.json"
    stories.write_text(json.dumps(STORIES), encoding="utf-8")
    st_path = str(tmp_path / "build" / "state.json")
    assert bs.main(["init", "--stories", str(stories), "--state", st_path, "--feature-branch", "nova/f",
                    "--base", "main", "--test-cmd", "pytest"]) == 0
    assert bs.main(["init", "--stories", str(stories), "--state", st_path, "--feature-branch", "x",
                    "--base", "main", "--test-cmd", "pytest"]) == 1
    assert bs.main(["set", "--state", st_path, "S01", "--status", "implementing", "--round", "1"]) == 0
    assert bs.main(["next", "--state", st_path]) == 0
    assert '"resume": true' in capsys.readouterr().out
    assert bs.main(["show", "--state", st_path]) == 0
    assert "| S01 | a | implementing | 1 |" in capsys.readouterr().out
