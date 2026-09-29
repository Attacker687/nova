import copy
import json

from conftest import load_script

tp = load_script("test-plan", "testplan")


def point(pid, covers, **over):
    base = {"id": pid, "title": "过期券不能下单", "type": "api", "condition": "rule", "technique": "decision-table",
            "covers": covers, "story": "S01", "priority": "P0", "quote": "过期的券不可使用",
            "expected": "返回错误码 COUPON_EXPIRED，订单未创建"}
    base.update(over)
    return base


DATA = {
    "feature": "coupon",
    "strategy": {"scope": "下单用券", "out_of_scope": "券发放", "environment": "测试库", "data": "三张券",
                 "risks": "时区"},
    "requirements": [{"id": "REQ-01", "text": "过期券不可用", "source": "design §4.1"},
                     {"id": "REQ-02", "text": "券金额上限 100", "source": "R-004"}],
    "gaps": [{"id": "GAP-01", "text": "没说时区", "affects": ["TP-002"]}],
    "points": [
        point("TP-001", ["REQ-01"]),
        point("TP-002", ["REQ-02"], condition="input", technique="ep-bva", quote="", inferred="R-004 边界值",
              expected="金额 101 时返回 AMOUNT_EXCEEDED"),
        point("TP-003", ["REQ-01"], condition="state", technique="state-transition", type="unit", priority="P1",
              expected="状态由 ACTIVE 变为 EXPIRED"),
    ],
}


def test_valid_plan_passes():
    problems, warnings = tp.check(DATA, {"S01"})
    assert problems == [] and warnings == []


def test_plan_problems():
    bad = copy.deepcopy(DATA)
    bad["requirements"].append({"id": "REQ-03", "text": "未覆盖", "source": "x"})
    bad["points"][0]["expected"] = "成功"
    bad["points"][1]["inferred"] = ""
    bad["points"][2]["covers"] = ["REQ-09"]
    bad["points"][2]["story"] = "S09"
    bad["points"].append(point("TP-3", [], type="ui", quote="x" * 121))
    text = "\n".join(tp.check(bad, {"S01"})[0])
    for expected in ["判据项 REQ-03 没有被任何测试点覆盖", "TP-001 的 expected 太笼统",
                     "TP-002 既没有需求原文 quote，也没有推断依据", "不存在的判据项 REQ-09",
                     "story 不在 stories.json 里：S09", "测试点编号不合规：'TP-3'", "type 取值不对：'ui'",
                     "quote 超过 120 字", "没有对应任何判据项"]:
        assert expected in text


def test_missing_condition_class_is_only_a_warning():
    data = copy.deepcopy(DATA)
    data["points"] = [p for p in data["points"] if p["condition"] != "state"]
    problems, warnings = tp.check(data)
    assert problems == [] and any("状态流程" in w for w in warnings)


def test_cases_checks():
    data = copy.deepcopy(DATA)
    data["cases"] = [
        {"id": "TC-001", "point": "TP-001", "title": "用过期券下单", "preconditions": ["券已过期"],
         "steps": ["调用下单接口"], "data": {"couponId": "C1"}, "expected": ["返回 COUPON_EXPIRED"]},
        {"id": "TC-002", "point": "TP-404", "title": "x", "steps": ["a"], "expected": ["正常"]},
    ]
    problems, _ = tp.check(data, need_cases=True)
    text = "\n".join(problems)
    assert "TC-002 对应的测试点不存在" in text and "预期「正常」太笼统" in text
    assert "测试点 TP-002 还没有用例" in text and "TP-001 还没有用例" not in text


def test_render(tmp_path):
    data = copy.deepcopy(DATA)
    data["requirements"].append({"id": "REQ-03", "text": "没人管", "source": "x"})
    data["cases"] = [{"id": "TC-001", "point": "TP-001", "title": "a|b", "steps": ["1", "2"],
                      "data": {"k": "v"}, "expected": ["返回 E1"], "automatable": False}]
    md = tp.render(data)
    assert "| REQ-01 | 过期券不可用 | design §4.1 | TP-001、TP-003 |" in md
    assert "| REQ-03 | 没人管 | x | **未覆盖** |" in md
    assert "推断：R-004 边界值" in md and "原文：过期的券不可使用" in md
    assert "a\\|b" in md and "1<br>2" in md and "k：v" in md and "| 否 |" in md
    assert "## 5. 风险与需求缺口" in md and "| GAP-01 | 没说时区 | TP-002 |" in md


def test_cli(tmp_path, capsys):
    path = tmp_path / "testplan.json"
    path.write_text(json.dumps(DATA, ensure_ascii=False), encoding="utf-8")
    assert tp.main(["check", str(path)]) == 0
    assert "判据项 2 条全部覆盖" in capsys.readouterr().out
    assert tp.main(["check", str(path), "--need-cases"]) == 1
    out = tmp_path / "plan.md"
    assert tp.main(["render", str(path), "--out", str(out)]) == 0
