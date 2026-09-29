"""检查两个宿主安装整包后仍能找到资源和跨 skill 的脚本。"""
import json
import shutil
import subprocess
import sys
from pathlib import Path


def test_plugin_package(tmp_path):
    repo = Path(__file__).resolve().parents[1]
    catalog = json.loads((repo / ".agents/plugins/marketplace.json").read_text(encoding="utf-8"))
    entry, = catalog["plugins"]
    source = repo / entry["source"]["path"]
    plugin = tmp_path / "安装缓存 with spaces" / entry["name"]
    shutil.copytree(source, plugin)
    codex = json.loads((plugin / ".codex-plugin/plugin.json").read_text(encoding="utf-8"))
    claude = json.loads((plugin / ".claude-plugin/plugin.json").read_text(encoding="utf-8"))
    assert codex["name"] == claude["name"] == entry["name"]
    assert codex["version"].split("+")[0] == claude["version"].split("+")[0]
    skills = plugin / codex["skills"]
    assert len(list(skills.glob("*/SKILL.md"))) == 12
    assert (plugin / "references/runtime.md").is_file()
    assert len(list((plugin / "agents").glob("*.md"))) == 7
    review = tmp_path / "review.json"
    review.write_text('{"verdict": "approved", "findings": []}', encoding="utf-8")
    for script in skills.glob("*/scripts/*.py"):
        argument = str(review) if script.name == "review_check.py" else "--help"
        result = subprocess.run(
            [sys.executable, "-X", "utf8", str(script), argument], cwd=tmp_path,
            capture_output=True, text=True, encoding="utf-8",
        )
        assert result.returncode == 0, f"{script}: {result.stdout}\n{result.stderr}"
