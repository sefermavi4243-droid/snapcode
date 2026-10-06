"""Entry point.

    snapcode                      start the tray app
    snapcode shot.png             print the code found in an image
    snapcode --clipboard --copy   read the clipboard image, put the code back
"""

from __future__ import annotations

import argparse
import io
import json
import sys

from . import __version__
from .config import Settings
from .i18n import set_language, t


def _read_clipboard_png() -> bytes:
    from PIL import ImageGrab

    image = ImageGrab.grabclipboard()
    if image is None or isinstance(image, list):
        raise SystemExit(t("Panoda görüntü yok."))
    out = io.BytesIO()
    image.save(out, "PNG")
    return out.getvalue()


def _copy(text: str) -> None:
    from PySide6.QtGui import QGuiApplication

    app = QGuiApplication.instance() or QGuiApplication([])
    QGuiApplication.clipboard().setText(text)
    app.processEvents()


def main(argv: list[str] | None = None) -> int:
    set_language(Settings.load().ui_language)
    parser = argparse.ArgumentParser(prog="pluck", description=t("Ekran görüntüsündeki kodu metne çevir."))
    parser.add_argument("image", nargs="?", help=t("görüntü dosyası (yoksa tepsi uygulaması başlar)"))
    parser.add_argument("--clipboard", action="store_true", help=t("panodaki görüntüyü kullan"))
    parser.add_argument("--engine", choices=["auto", "windows", "claude"], help=t("tanıma motoru"))
    parser.add_argument("--copy", action="store_true", help=t("sonucu panoya kopyala"))
    parser.add_argument("--ide", nargs="?", const="auto", metavar="IDE",
                        help=t("sonucu IDE'de aç (vscode, cursor, pycharm, …; boşsa otomatik)"))
    parser.add_argument("--json", action="store_true", help=t("JSON çıktı (dil, motor, süre)"))
    parser.add_argument("--version", action="version", version=f"pluck {__version__}")
    args = parser.parse_args(argv)

    if not args.image and not args.clipboard:
        from .app import run_gui

        return run_gui()

    from .pipeline import recognize

    if args.clipboard:
        png = _read_clipboard_png()
    else:
        with open(args.image, "rb") as f:
            png = f.read()

    try:
        result = recognize(png, Settings.load(), args.engine)
    except RuntimeError as exc:  # ClaudeError, WindowsOcrUnavailable
        print(f"pluck: {exc}", file=sys.stderr)
        return 1
    if args.copy:
        _copy(result.code)
    if args.ide:
        from . import ide

        target, path = ide.send(result.code, result.language, args.ide)
        print(f"# {target.name}: {path}", file=sys.stderr)

    sys.stdout.reconfigure(encoding="utf-8")
    if args.json:
        print(json.dumps({
            "code": result.code,
            "language": result.language.key,
            "engine": result.engine,
            "elapsed_ms": result.elapsed_ms,
            "notes": result.notes,
        }, ensure_ascii=False, indent=2))
    else:
        print(result.code, end="")
        for note in result.notes:
            print(f"# {note}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
