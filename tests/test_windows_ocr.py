"""End-to-end check against the real Windows OCR engine (skipped elsewhere)."""

import io
import sys

import pytest
from PIL import Image, ImageDraw, ImageFont

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows OCR only")

CODE = """import os

def walk(root, depth=0):
    for name in sorted(os.listdir(root)):
        path = os.path.join(root, name)
        if os.path.isdir(path):
            walk(path, depth + 1)"""


def render(code: str, dark: bool, numbers: bool) -> bytes:
    font = ImageFont.truetype("consola.ttf", 15)
    lines = code.split("\n")
    img = Image.new("RGB", (640, 22 * len(lines) + 30), (30, 30, 30) if dark else (255, 255, 255))
    draw = ImageDraw.Draw(img)
    for i, line in enumerate(lines):
        x = 15
        if numbers:
            draw.text((15, 15 + 22 * i), f"{i + 1:>3}", font=font, fill=(110, 110, 110))
            x = 60
        draw.text((x, 15 + 22 * i), line, font=font, fill=(220, 220, 220) if dark else (20, 20, 20))
    out = io.BytesIO()
    img.save(out, "PNG")
    return out.getvalue()


@pytest.mark.parametrize("dark,numbers", [(False, False), (True, True)])
def test_round_trip(dark, numbers):
    pytest.importorskip("winrt.windows.media.ocr")
    from pluck.engines.windows_ocr import available_languages

    if not available_languages():
        pytest.skip("no Windows OCR language pack installed (e.g. Windows Server)")
    from pluck.config import Settings
    from pluck.pipeline import recognize

    result = recognize(render(CODE, dark, numbers), Settings(engine="windows"))
    assert result.engine == "windows"
    assert result.language.key == "python"
    assert result.code == CODE + "\n"


def test_normalize_keeps_coloured_and_dim_text():
    """Syntax colours, dim comments and diff line backgrounds all become dark ink on white."""
    from pluck.engines.windows_ocr import _normalize

    img = Image.new("RGB", (60, 30), (30, 30, 30))
    draw = ImageDraw.Draw(img)
    draw.rectangle((0, 15, 59, 29), fill=(70, 20, 20))  # red diff row
    draw.rectangle((5, 3, 10, 10), fill=(197, 134, 192))  # purple bracket
    draw.rectangle((20, 3, 25, 10), fill=(90, 110, 80))  # dim comment
    draw.rectangle((5, 18, 10, 25), fill=(212, 212, 212))  # text on the red row
    out = _normalize(img).convert("L")
    assert out.getpixel((40, 5)) == 255 and out.getpixel((40, 22)) == 255  # backgrounds
    assert out.getpixel((7, 6)) < 100 and out.getpixel((7, 21)) < 100
    assert out.getpixel((22, 6)) < 200
