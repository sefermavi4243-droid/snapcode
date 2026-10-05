import ast
from pathlib import Path

from snapcode import i18n

SOURCE = Path(__file__).resolve().parents[1] / "snapcode"


def _translated_literals():
    for path in SOURCE.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if (isinstance(node, ast.Call) and getattr(node.func, "id", None) == "t" and node.args
                    and isinstance(node.args[0], ast.Constant)):
                yield path.name, node.args[0].value


def test_every_string_has_an_english_version():
    missing = [(name, text) for name, text in _translated_literals() if text not in i18n.EN]
    assert missing == []


def test_dynamic_strings_have_english_versions():
    from snapcode import languages, pipeline

    for text in [*pipeline.ENGINES.values(), *i18n.LANGUAGES.values(), languages.by_key("text").name]:
        assert text in i18n.EN or text in ("Türkçe", "English"), text


def test_switching_language():
    try:
        i18n.set_language("en")
        assert i18n.t("{n} satır", n=3) == "3 lines"
        i18n.set_language("tr")
        assert i18n.t("{n} satır", n=3) == "3 satır"
    finally:
        i18n.set_language("tr")
