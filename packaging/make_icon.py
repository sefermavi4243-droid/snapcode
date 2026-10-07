"""Render the app icon to packaging/pluck.ico (multi-size)."""

import io
import sys
from pathlib import Path

from PIL import Image
from PySide6.QtCore import QBuffer, QSize
from PySide6.QtGui import QGuiApplication

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pluck.ui.theme import app_icon  # noqa: E402

app = QGuiApplication([])
pixmap = app_icon().pixmap(QSize(256, 256))
buffer = QBuffer()
buffer.open(QBuffer.WriteOnly)
pixmap.save(buffer, "PNG")
image = Image.open(io.BytesIO(bytes(buffer.data())))
out = Path(__file__).with_name("pluck.ico")
image.save(out, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print(out)
