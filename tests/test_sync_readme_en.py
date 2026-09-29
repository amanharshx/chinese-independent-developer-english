import importlib.util
from pathlib import Path

import pytest


MODULE_PATH = Path(__file__).parents[1] / "scripts" / "sync_readme_en.py"
SPEC = importlib.util.spec_from_file_location("sync_readme_en", MODULE_PATH)
sync_readme_en = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(sync_readme_en)

ZH = """## 中国独立开发者项目列表
## 3. 项目列表

### 2026 年 8 月 3 号添加
#### 小明(北京) - [Github](https://github.com/xiaoming)
* :white_check_mark: [新工具](https://new.example)：新工具

### 2026 年 8 月 2 号添加
* :white_check_mark: [旧工具](https://old.example)：旧工具

## 值得关注的 Twitter 账号
* 推特
"""

EN = """## Chinese Independent Developer Projects List
## 3. Project List

### Added on August 2, 2026
* :white_check_mark: [Old Tool](https://old.example): Old tool

### Added on August 1, 2026
* :white_check_mark: [Gone](https://gone.example): Moved to the upstream archive

## Twitter accounts worth following
* Twitter
"""

TRANSLATIONS = {
    "#### 小明(北京) - [Github](https://github.com/xiaoming)": "#### Xiaoming (Beijing) - [Github](https://github.com/xiaoming)",
    "* :white_check_mark: [新工具](https://new.example)：新工具": "* :white_check_mark: [New Tool](https://new.example): New tool",
    "* :white_check_mark: [旧工具](https://old.example)：旧工具": "* :white_check_mark: [Old Tool](https://old.example): Old tool",
}


class FakeTranslator:
    def __init__(self, results=None):
        self.results = results or {}
        self.calls = []

    def translate(self, text):
        self.calls.append(text)
        result = self.results.get(text, "Translated")
        if isinstance(result, Exception):
            raise result
        return result


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(sync_readme_en.time, "sleep", lambda seconds: None)


def test_rebuild_mirrors_upstream_and_reuses_valid_sections():
    translator = FakeTranslator(TRANSLATIONS)

    result = sync_readme_en.build_english_readme(ZH, ZH, EN, translator)

    assert "### Added on August 3, 2026\n#### Xiaoming (Beijing)" in result
    assert "[Old Tool](https://old.example): Old tool" in result
    assert "Gone" not in result
    assert translator.calls == [
        "#### 小明(北京) - [Github](https://github.com/xiaoming)",
        "* :white_check_mark: [新工具](https://new.example)：新工具",
    ]


@pytest.mark.parametrize("broken_line", [
    "* :white_check_mark: [旧工具](https://old.example)：旧工具",
    "Error 500 (Server Error)!!1500.That’s an error.",
    "* :white_check_mark: [Other](https://other.example): Swapped in from another line",
])
def test_broken_existing_sections_are_retranslated(broken_line):
    en = EN.replace("* :white_check_mark: [Old Tool](https://old.example): Old tool", broken_line)
    result = sync_readme_en.build_english_readme(ZH, ZH, en, FakeTranslator(TRANSLATIONS))

    assert "[Old Tool](https://old.example): Old tool" in result
    assert broken_line not in result


def test_translation_restores_urls_google_rewrote():
    translator = FakeTranslator({
        "* [眼型测试](https://eyeshapedetector.app/zh)：AI 眼型分析": "* [Eye shape test](https://eyeshapedector.app/zh): AI eye shape analysis",
    })

    line = sync_readme_en.translate_line(translator, "* [眼型测试](https://eyeshapedetector.app/zh)：AI 眼型分析\n")

    assert line == "* [Eye shape test](https://eyeshapedetector.app/zh): AI eye shape analysis\n"


def test_translation_retries_then_fails_instead_of_keeping_bad_output():
    translator = FakeTranslator({"旧工具": "Error 500 (Server Error)!!1500.That’s an error."})

    with pytest.raises(RuntimeError, match="旧工具"):
        sync_readme_en.translate_line(translator, "旧工具\n")

    assert len(translator.calls) == len(sync_readme_en.RETRY_DELAYS) + 1


def test_failed_translation_leaves_files_untouched(tmp_path, monkeypatch):
    (tmp_path / "README.md").write_text(EN, encoding="utf-8")
    (tmp_path / "README-zh.md").write_text("", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sync_readme_en, "fetch_upstream_chinese_readme", lambda: ZH)
    monkeypatch.setattr(sync_readme_en, "GoogleTranslator",
                        lambda **kwargs: FakeTranslator({"#### 小明(北京) - [Github](https://github.com/xiaoming)": ConnectionError()}))

    with pytest.raises(RuntimeError):
        sync_readme_en.sync()

    assert (tmp_path / "README.md").read_text(encoding="utf-8") == EN
    assert (tmp_path / "README-zh.md").read_text(encoding="utf-8") == ""
