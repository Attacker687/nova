import importlib.util
import sys
from pathlib import Path

SKILLS = Path(__file__).resolve().parents[1] / "plugins" / "nova" / "skills"
sys.path.insert(0, str(Path(__file__).resolve().parent))


def load_script(skill: str, name: str):
    """按文件路径加载 skills/【skill】/scripts/【name】.py（脚本目录不是包）。"""
    path = SKILLS / skill / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"nova_{skill.replace('-', '_')}_{name}", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module
