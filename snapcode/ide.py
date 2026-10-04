"""Find installed editors and open a snippet in one of them.

The snippet is written to Documents\\SnapCode with the right extension, so the
editor highlights it, its language server picks it up, and the file outlives
the clipboard.
"""

from __future__ import annotations

import ctypes
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from functools import lru_cache
from pathlib import Path

from .languages import Language


@dataclass(frozen=True)
class Ide:
    key: str
    name: str
    exe: str
    args: tuple[str, ...] = ()
    languages: frozenset[str] = field(default_factory=frozenset)  # preferred for these

    def command(self, path: Path) -> list[str]:
        return [self.exe, *self.args, str(path)]


# Electron editors: running the exe with a file path opens it in the
# existing window instead of starting a second instance.
_VSCODE_FAMILY = [
    ("cursor", "Cursor", [r"{LOCAL}\Programs\cursor\Cursor.exe"]),
    ("windsurf", "Windsurf", [r"{LOCAL}\Programs\Windsurf\Windsurf.exe"]),
    ("vscode", "VS Code", [r"{LOCAL}\Programs\Microsoft VS Code\Code.exe",
                           r"{PF}\Microsoft VS Code\Code.exe"]),
    ("vscode-insiders", "VS Code Insiders", [r"{LOCAL}\Programs\Microsoft VS Code Insiders\Code - Insiders.exe",
                                             r"{PF}\Microsoft VS Code Insiders\Code - Insiders.exe"]),
]

# JetBrains launcher name -> (display name, languages it is the natural home for)
_JETBRAINS = {
    "pycharm64.exe": ("PyCharm", {"python"}),
    "idea64.exe": ("IntelliJ IDEA", {"java", "kotlin"}),
    "webstorm64.exe": ("WebStorm", {"javascript", "typescript", "html", "css"}),
    "rider64.exe": ("Rider", {"csharp"}),
    "goland64.exe": ("GoLand", {"go"}),
    "clion64.exe": ("CLion", {"c", "cpp"}),
    "rustrover64.exe": ("RustRover", {"rust"}),
    "phpstorm64.exe": ("PhpStorm", {"php"}),
    "rubymine64.exe": ("RubyMine", {"ruby"}),
    "datagrip64.exe": ("DataGrip", {"sql"}),
    "studio64.exe": ("Android Studio", {"kotlin", "java"}),
}

_EDITORS = [
    ("sublime", "Sublime Text", [r"{PF}\Sublime Text\sublime_text.exe", r"{PF}\Sublime Text 3\sublime_text.exe"]),
    ("notepadpp", "Notepad++", [r"{PF}\Notepad++\notepad++.exe", r"{PF86}\Notepad++\notepad++.exe"]),
]


def _expand(pattern: str) -> Path:
    return Path(pattern.format(
        LOCAL=os.environ.get("LOCALAPPDATA", ""),
        PF=os.environ.get("ProgramFiles", r"C:\Program Files"),
        PF86=os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
    ))


# Fixed-depth globs: a recursive search of Program Files takes seconds.
_JETBRAINS_GLOBS = [
    ("{PF}", "JetBrains/*/bin/*64.exe"),                        # standalone installers
    ("{PF}", "Android/*/bin/*64.exe"),
    ("{LOCAL}", "Programs/*/bin/*64.exe"),                      # Toolbox 2.x
    ("{LOCAL}", "JetBrains/Toolbox/apps/*/ch-*/*/bin/*64.exe"),  # Toolbox 1.x
]


def _find_jetbrains() -> list[Ide]:
    found: dict[str, Ide] = {}
    for base, pattern in _JETBRAINS_GLOBS:
        root = _expand(base)
        if not root.is_dir():
            continue
        for exe in root.glob(pattern):
            meta = _JETBRAINS.get(exe.name.lower())
            # Keep the newest install when several versions exist.
            if meta and (exe.name not in found or exe.stat().st_mtime > Path(found[exe.name].exe).stat().st_mtime):
                found[exe.name] = Ide(exe.stem.removesuffix("64"), meta[0], str(exe), (), frozenset(meta[1]))
    return list(found.values())


@lru_cache(maxsize=1)
def detect() -> tuple[Ide, ...]:
    ides: list[Ide] = []
    for key, name, candidates in _VSCODE_FAMILY:
        exe = next((p for p in map(_expand, candidates) if p.is_file()), None)
        if exe is None and key == "vscode":
            cli = shutil.which("code")  # bin\code.cmd -> ..\Code.exe
            if cli and (Path(cli).parent.parent / "Code.exe").is_file():
                exe = Path(cli).parent.parent / "Code.exe"
        if exe:
            ides.append(Ide(key, name, str(exe)))
    ides += _find_jetbrains()
    for key, name, candidates in _EDITORS:
        exe = next((p for p in map(_expand, candidates) if p.is_file()), None)
        if exe:
            ides.append(Ide(key, name, str(exe)))
    ides.append(Ide("notepad", "Not Defteri", "notepad.exe"))
    return tuple(ides)


def by_key(key: str) -> Ide | None:
    return next((ide for ide in detect() if ide.key == key), None)


def choose(language_key: str, preferred: str = "auto") -> Ide:
    """The user's pick, else the specialist IDE for the language, else the first editor."""
    ides = detect()
    if preferred != "auto" and (ide := by_key(preferred)):
        return ide
    specialist = next((ide for ide in ides if language_key in ide.languages), None)
    return specialist or ides[0]


def snippets_dir() -> Path:
    buf = ctypes.create_unicode_buffer(260)
    # CSIDL_PERSONAL follows a Documents folder redirected to OneDrive.
    if ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, buf) == 0:
        documents = Path(buf.value)
    else:
        documents = Path.home() / "Documents"
    path = documents / "SnapCode"
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_snippet(code: str, language: Language, directory: Path | None = None) -> Path:
    directory = directory or snippets_dir()
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = directory / f"snippet-{stamp}{language.extension}"
    counter = 2
    while path.exists():
        path = directory / f"snippet-{stamp}-{counter}{language.extension}"
        counter += 1
    path.write_text(code, encoding="utf-8", newline="\n")
    return path


def open_in(ide: Ide, path: Path) -> None:
    subprocess.Popen(
        ide.command(path),
        creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS,
        close_fds=True,
    )


def send(code: str, language: Language, preferred: str = "auto") -> tuple[Ide, Path]:
    ide = choose(language.key, preferred)
    path = write_snippet(code, language)
    open_in(ide, path)
    return ide, path
