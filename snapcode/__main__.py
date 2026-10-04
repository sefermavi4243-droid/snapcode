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


def _read_clipboard_png() -> bytes:
    from PIL import ImageGrab

    image = ImageGrab.grabclipboard()
    if image is None or isinstance(image, list):
        raise SystemExit("Panoda görüntü yok.")
    out = io.BytesIO()
    image.save(out, "PNG")
    return out.getvalue()


def _copy(text: str) -> None:
    from PySide6.QtGui import QGuiApplication

    app = QGuiApplication.instance() or QGuiApplication([])
    QGuiApplication.clipboard().setText(text)
    app.processEvents()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="snapcode", description="Ekran görüntüsündeki kodu metne çevir.")
    parser.add_argument("image", nargs="?", help="görüntü dosyası (yoksa tepsi uygulaması başlar)")
    parser.add_argument("--clipboard", action="store_true", help="panodaki görüntüyü kullan")
    parser.add_argument("--engine", choices=["auto", "windows", "claude"], help="tanıma motoru")
    parser.add_argument("--copy", action="store_true", help="sonucu panoya kopyala")
    parser.add_argument("--json", action="store_true", help="JSON çıktı (dil, motor, süre)")
    parser.add_argument("--version", action="version", version=f"snapcode {__version__}")
    args = parser.parse_args(argv)

    if not args.image and not args.clipboard:
        from .app import run_gui

        return run_gui()

    from .config import Settings
    from .pipeline import recognize

    if args.clipboard:
        png = _read_clipboard_png()
    else:
        with open(args.image, "rb") as f:
            png = f.read()

    try:
        result = recognize(png, Settings.load(), args.engine)
    except RuntimeError as exc:  # ClaudeError, WindowsOcrUnavailable
        print(f"snapcode: {exc}", file=sys.stderr)
        return 1
    if args.copy:
        _copy(result.code)

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
