import copy
import json

import pytest

from conftest import load_script

st = load_script("stories", "stories")


def ac(aid, entry="src/coupon/Service.java::expire"):
    return {"id": aid, "given": "券已过期", "when": "调用过期处理", "then": "状态变为 EXPIRED",
            "entry": entry, "verify": "CouponServiceTest.expiresCoupon"}


DATA = {
    "feature": "coupon-expiry",
    "design": "docs/nova/coupon-expiry/design.md",
    "stories": [
        {"id": "S02", "title": "定时任务", "goal": "每天自动处理过期券", "depends_on": ["S01"],
         "scope": ["新建 src/coupon/ExpiryJob.java"],
         "acceptance": [ac("S02-AC1", "src/coupon/ExpiryJob.java::run")]},
        {"id": "S01", "title": "过期逻辑", "goal": "单张券能被标记过期", "depends_on": [],
         "scope": ["src/coupon/Service.java"], "design_refs": ["§4.1"],
         "acceptance": [ac("S01-AC1"), ac("S01-AC2")], "notes": "沿用现有状态枚举"},
        {"id": "S03", "title": "通知", "goal": "过期后通知用户", "depends_on": ["S01"],
         "acceptance": [ac("S03-AC1", "src/coupon/Service.java::notifyExpired")]},
    ],
}


@pytest.fixture
def code(tmp_path):
    f = tmp_path / "src" / "coupon" / "Service.java"
    f.parent.mkdir(parents=True)
    f.write_text("class Service { void expire() {} void notifyExpired() {} }\n", encoding="utf-8")
    return tmp_path


def test_valid_stories_pass_and_order(code):
    assert st.check(DATA, code) == []
    assert st.topo_order(DATA["stories"]) == ["S01", "S02", "S03"]


def test_structural_problems():
    bad = copy.deepcopy(DATA)
    bad["stories"][0]["depends_on"] = ["S09"]
    bad["stories"][1]["acceptance"][1]["id"] = "S01-AC1"
    bad["stories"][2]["acceptance"] = []
    bad["stories"].append({"id": "X1", "title": "", "goal": "g", "acceptance": [
        {"id": "S01-AC9", "given": "a", "when": "b", "then": "c", "entry": "no-separator", "verify": ""}]})
    text = "\n".join(st.check(bad))
    for expected in ["S02 依赖了不存在的 S09", "验收编号重复：S01-AC1", "S03 没有验收标准", "编号不合规：'X1'",
                     "X1 缺少 title", "应以 X1-AC 开头", "S01-AC9 缺少 verify", "路径::符号"]:
        assert expected in text


def test_cycle_detected():
    cyc = copy.deepcopy(DATA)
    cyc["stories"][1]["depends_on"] = ["S03"]
    cyc["stories"][2]["depends_on"] = ["S01"]
    assert any("依赖有环" in p for p in st.check(cyc))


def test_entry_rules_against_code(code):
    bad = copy.deepcopy(DATA)
    bad["stories"][1]["acceptance"][0]["entry"] = "src/test/java/ServiceTest.java::x"
    bad["stories"][1]["acceptance"][1]["entry"] = "src/coupon/Service.java::missingMethod"
    bad["stories"][2]["acceptance"][0]["entry"] = "src/coupon/Nope.java::run"
    bad["stories"][2]["scope"] = ["src/coupon/Gone.java"]
    text = "\n".join(st.check(bad, code))
    assert "指向测试代码" in text
    assert "入口符号在文件里找不到：missingMethod" in text
    assert "入口文件不存在" in text and "Nope.java" in text
    assert "改动范围里有不存在的文件" in text and "Gone.java" in text


def test_render_orders_and_escapes():
    data = copy.deepcopy(DATA)
    data["stories"][1]["acceptance"][0]["then"] = "返回 a|b"
    md = st.render(data)
    assert md.index("## S01 过期逻辑") < md.index("## S02 定时任务") < md.index("## S03 通知")
    assert "  S01 --> S02" in md and "  S01 --> S03" in md
    assert "返回 a\\|b" in md
    assert "| 1 | S01 | 过期逻辑 | — | 2 |" in md
    assert "**实现提示**：沿用现有状态枚举" in md


def test_cli(tmp_path, code, capsys):
    path = tmp_path / "stories.json"
    path.write_text(json.dumps(DATA, ensure_ascii=False), encoding="utf-8")
    assert st.main(["check", str(path), "--root", str(code)]) == 0
    assert "3 个 Story，4 条验收标准，顺序：S01 → S02 → S03" in capsys.readouterr().out
    out = tmp_path / "stories.md"
    assert st.main(["render", str(path), "--out", str(out)]) == 0
    assert out.read_text(encoding="utf-8").startswith("---\nfeature: coupon-expiry")
    assert st.main(["order", str(path)]) == 0
    assert capsys.readouterr().out.strip().endswith("S01 S02 S03")
