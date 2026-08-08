import importlib.util
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "scripts" / "sync_readme_en.py"
SPEC = importlib.util.spec_from_file_location("sync_readme_en", MODULE_PATH)
sync_readme_en = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(sync_readme_en)


def test_changed_and_new_chinese_sections_need_translation():
    previous = """### 2026 年 8 月 2 号添加
* Old description
"""
    current = """### 2026 年 8 月 3 号添加
* New section
### 2026 年 8 月 2 号添加
* Updated description
"""

    assert sync_readme_en.sections_needing_translation(previous, current) == [
        (2026, 8, 3),
        (2026, 8, 2),
    ]
