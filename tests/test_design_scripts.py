import json
from pathlib import Path

from conftest import SKILLS, load_script

rv = load_script("design", "review_check")
dc = load_script("design", "doc_check")

TEMPLATES = SKILLS / "design" / "templates"


def finding(**over):
    base = {"id": "F1", "severity": "medium", "axis": "complete", "kind": "fix", "where": "§4",
            "problem": "缺少回滚方案", "evidence": "§5 没提", "suggestion": "补一段", "verify": "看 §5"}
    base.update(over)
    return base


def test_valid_review_passes_and_summarizes():
    data = {"round": 1, "verdict": "changes_requested",
            "goal_check": [{"goal": "G1", "supported": False, "where": "", "note": "没写"}],
            "findings": [finding(id="F1", severity="high"), finding(id="F2", kind="decide")]}
    assert rv.validate(data) == []
    s = rv.summarize(data)
    assert s["blocking"] == 1 and s["decide"] == ["F2"] and s["unsupported_goals"] == ["G1"]


def test_review_rules_are_enforced():
    data = {"verdict": "approved", "findings": [
        finding(id="F1", severity="critical"),
        finding(id="F1", axis="vibes", kind="maybe", problem=""),
    ], "goal_check": [{"goal": "G1"}]}
    text = "\n".join(rv.validate(data))
    for expected in ["axis 取值不对", "kind 取值不对", "缺少字段：problem", "编号重复：F1",
                     "verdict 必须是 changes_requested", "goal_check 条目不完整"]:
        assert expected in text


def test_review_cli(tmp_path, capsys):
    good = tmp_path / "a.json"
    good.write_text(json.dumps({"verdict": "approved", "findings": [finding(severity="low")]}), encoding="utf-8")
    other = tmp_path / "b.json"
    other.write_text(json.dumps({"verdict": "approved", "findings": []}), encoding="utf-8")
    assert rv.main([str(good), str(other)]) == 0
    assert "合计：critical=0 high=0 medium=0 low=1" in capsys.readouterr().out
    bad = tmp_path / "c.json"
    bad.write_text("{not json", encoding="utf-8")
    assert rv.main([str(bad)]) == 1


DOC = """---
feature: coupon
type: tech
status: draft
---

# 优惠券方案

## 1. 背景与目标
支撑 G1。

## 2. 现状
见 `src/Coupon.java:10`。待确认：券码长度。

## 3. 方案概览
```mermaid
flowchart TD
  A --> B
```

## 4. 详细设计
接口【待补】。

```text
代码块里的【占位】不算
## 5. 这也不算标题
```

## 6. 验收与测试要点
略

## 7. 待决策

| 编号 | 要决定的事 | 选项 | 建议 | 状态 | 来源 |
|---|---|---|---|---|---|
| D-001 | 过期券怎么处理 | A / B | A | 待定 | 需求 |
| D-002 | 券码长度 | 8 / 12 | 12 | 默认：12 位 | 写方案时 |
| D-003 | 是否可叠加 | 是 / 否 | 否 | 已定：否 | 评审 |
"""


def test_doc_check_against_tech_template():
    result = dc.check(DOC, (TEMPLATES / "tech.md").read_text(encoding="utf-8"))
    assert result["missing_sections"] == ["影响面与风险"]
    assert not result["ok"]
    assert [p["text"] for p in result["placeholders"]] == ["【待补】"]
    assert len(result["pending_confirm_lines"]) == 1
    assert result["mermaid_blocks"] == 1
    assert result["undecided"] == ["D-001"] and result["defaults"] == ["D-002"]
    assert result["status"] == "draft"


def test_filled_template_headings_match_all_templates():
    for name in ("goal.md", "tech.md", "general.md"):
        tpl = (TEMPLATES / name).read_text(encoding="utf-8")
        assert dc.check(tpl, tpl)["missing_sections"] == []


def test_export_strips_frontmatter_and_title(tmp_path, capsys):
    src = tmp_path / "d.md"
    src.write_text(DOC, encoding="utf-8")
    out = tmp_path / "out.md"
    assert dc.main([str(src), "--export", str(out)]) == 0
    assert "标题：优惠券方案" in capsys.readouterr().out
    body = out.read_text(encoding="utf-8")
    assert body.startswith("## 1. 背景与目标") and "---" not in body.splitlines()[0]
