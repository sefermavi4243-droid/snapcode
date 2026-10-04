from pathlib import Path

from snapcode import ide, languages

FAKE = (
    ide.Ide("vscode", "VS Code", "code.exe"),
    ide.Ide("pycharm", "PyCharm", "pycharm64.exe", (), frozenset({"python"})),
    ide.Ide("notepad", "Not Defteri", "notepad.exe"),
)


def test_choose_prefers_specialist_then_first(monkeypatch):
    monkeypatch.setattr(ide, "detect", lambda: FAKE)
    assert ide.choose("python").key == "pycharm"
    assert ide.choose("go").key == "vscode"


def test_choose_respects_user_pick(monkeypatch):
    monkeypatch.setattr(ide, "detect", lambda: FAKE)
    assert ide.choose("python", "notepad").key == "notepad"
    assert ide.choose("python", "missing").key == "pycharm"


def test_write_snippet_uses_extension_and_never_overwrites(tmp_path: Path):
    lang = languages.by_key("python")
    a = ide.write_snippet("print(1)\n", lang, tmp_path)
    b = ide.write_snippet("print(2)\n", lang, tmp_path)
    assert a.suffix == ".py" and a != b
    assert a.read_text(encoding="utf-8") == "print(1)\n"


def test_command_passes_path_as_separate_argument():
    target = ide.Ide("x", "X", r"C:\a b\x.exe", ("--reuse",))
    assert target.command(Path(r"C:\d e\f.py")) == [r"C:\a b\x.exe", "--reuse", r"C:\d e\f.py"]
