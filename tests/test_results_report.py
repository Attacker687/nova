import json

import pytest

from conftest import load_script

rs = load_script("test-run", "results")
rp = load_script("test-report", "report")

PLAN = {
    "feature": "coupon",
    "strategy": {"scope": "下单用券", "out_of_scope": "发券", "environment": "测试库"},
    "requirements": [{"id": "REQ-01", "text": "过期券不可用"}, {"id": "REQ-02", "text": "金额上限"}],
    "points": [{"id": "TP-001", "type": "api", "covers": ["REQ-01"]},
               {"id": "TP-002", "type": "unit", "covers": ["REQ-02"]}],
    "cases": [{"id": f"TC-00{i}", "point": "TP-001" if i <= 2 else "TP-002", "title": f"用例{i}"}
              for i in range(1, 5)],
}

JUNIT = """<?xml version="1.0" encoding="utf-8"?>
<testsuites><testsuite name="s">
  <testcase classname="tests.test_coupon" name="test_TC_001_expired" time="0.1"/>
  <testcase classname="tests.test_coupon" name="test_tc002_other" time="0.2">
    <failure message="assert 200 == 400">trace</failure>
  </testcase>
  <testcase classname="CouponTest" name="TC-003 limit ok" time="0.1"/>
  <testcase classname="CouponTest" name="TC-003 limit edge" time="0.1"><skipped message="flaky"/></testcase>
  <testcase classname="x" name="test_helper" time="0.0"/>
  <testcase classname="x" name="test_TC_099_extra" time="0.0"><error message="boom"/></testcase>
</testsuite></testsuites>
"""


@pytest.fixture
def junit(tmp_path):
    p = tmp_path / "junit.xml"
    p.write_text(JUNIT, encoding="utf-8")
    return str(p)


def test_parse_junit_maps_case_ids(junit):
    found, unmapped = rs.parse_junit(junit)
    assert found["TC-001"]["result"] == "pass"
    assert found["TC-002"]["result"] == "fail" and found["TC-002"]["message"] == "assert 200 == 400"
    assert found["TC-003"]["result"] == "pass" and len(found["TC-003"]["tests"]) == 2
    assert found["TC-099"]["result"] == "fail"
    assert unmapped == ["x.test_helper"]


def test_failure_with_blank_message(tmp_path):
    p = tmp_path / "j.xml"
    p.write_text('<testsuite><testcase name="test_TC_001"><failure>\n   </failure></testcase></testsuite>',
                 encoding="utf-8")
    found, _ = rs.parse_junit(str(p))
    assert found["TC-001"] == {**found["TC-001"], "result": "fail", "message": ""}


def test_import_set_and_summary(junit):
    results = {"cases": {}, "runs": []}
    report = rs.import_junit([junit], results, PLAN)
    assert report["unknown_cases"] == ["TC-099"] and report["imported"] == 4
    rs.set_result(results, "TC-002", "fail", kind="product", defect="BUG-001")
    rs.set_result(results, "TC-004", "blocked", "缺支付沙箱", kind="env")
    s = rs.summarize(results, PLAN)
    assert (s["planned"], s["pass"], s["fail"], s["blocked"]) == (4, 2, 1, 1)
    assert s["not_run"] == [] and s["fail_without_kind"] == ["TC-099"]
    rs.import_junit([junit], results, PLAN)
    assert results["cases"]["TC-002"]["defect"] == "BUG-001", "重新导入仍失败时保留缺陷关联"
    with pytest.raises(ValueError):
        rs.set_result(results, "TC-001", "maybe")


def results_with(**by_case):
    return {"cases": {cid: {"result": r} for cid, r in by_case.items()}, "runs": []}


def test_verdict_pass():
    stats = rp.compute(PLAN, results_with(**{f"TC-00{i}": "pass" for i in range(1, 5)}), {"defects": []})
    assert stats["verdict"] == "通过"
    assert all(r["status"] == "已验证" for r in stats["requirements"])


def test_verdict_conditional_needs_low_defects_linked_and_under_ten_percent():
    plan = dict(PLAN, cases=[{"id": f"TC-{i:03d}", "point": "TP-001", "title": ""} for i in range(1, 21)])
    res = results_with(**{f"TC-{i:03d}": "pass" for i in range(1, 21)})
    res["cases"]["TC-020"]["result"] = "fail"
    low = {"defects": [{"id": "BUG-1", "severity": "low", "status": "open", "cases": ["TC-020"]}]}
    assert rp.compute(plan, res, low)["verdict"] == "有条件通过"
    medium = {"defects": [{"id": "BUG-1", "severity": "medium", "status": "open", "cases": ["TC-020"]}]}
    assert rp.compute(plan, res, medium)["verdict"] == "不通过"
    unlinked = {"defects": [{"id": "BUG-1", "severity": "low", "status": "open", "cases": []}]}
    stats = rp.compute(plan, res, unlinked)
    assert stats["verdict"] == "不通过" and any("没有关联缺陷" in r for r in stats["reasons"])


def test_verdict_fails_when_not_all_executed_or_too_many_low():
    stats = rp.compute(PLAN, results_with(**{"TC-001": "pass", "TC-002": "pass", "TC-003": "pass",
                                              "TC-004": "blocked"}), {"defects": []})
    assert stats["verdict"] == "不通过" and stats["exec_rate"] == 0.75
    res = results_with(**{f"TC-00{i}": "pass" for i in range(1, 5)})
    res["cases"]["TC-004"]["result"] = "fail"
    low = {"defects": [{"id": "BUG-1", "severity": "low", "status": "fixed", "cases": ["TC-004"]}]}
    assert rp.compute(PLAN, res, low)["verdict"] == "不通过", "1/4 = 25% 超过 10%"
    closed = {"defects": [{"id": "BUG-1", "severity": "high", "status": "closed", "cases": []}]}
    assert rp.compute(PLAN, results_with(**{f"TC-00{i}": "pass" for i in range(1, 5)}), closed)["verdict"] == "通过"


def test_report_cli(tmp_path, junit, capsys):
    plan_path = tmp_path / "testplan.json"
    plan_path.write_text(json.dumps(PLAN, ensure_ascii=False), encoding="utf-8")
    res_path = tmp_path / "results.json"
    assert rs.main(["import", junit, "--plan", str(plan_path), "--out", str(res_path)]) == 0
    assert rs.main(["set", str(res_path), "TC-002", "--result", "fail", "--kind", "product",
                    "--defect", "BUG-001"]) == 0
    defects = tmp_path / "defects.json"
    defects.write_text(json.dumps({"defects": [{"id": "BUG-001", "title": "过期券仍可用", "severity": "high",
                                                "status": "open", "cases": ["TC-002"]}]}, ensure_ascii=False),
                       encoding="utf-8")
    out = tmp_path / "report.md"
    assert rp.main([str(plan_path), "--results", str(res_path), "--defects", str(defects), "--out", str(out)]) == 0
    md = out.read_text(encoding="utf-8")
    assert md.startswith("# 测试报告：coupon（结论：不通过）")
    assert "BUG-001（high，open）过期券仍可用" in md
    assert "| REQ-01 | 过期券不可用 | TC-001、TC-002 | 有问题 |" in md
    assert "| TC-004 | 用例4 | 未执行 |" in md
