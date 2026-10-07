"""Glyph-template repair on rendered images with simulated OCR mistakes."""

import pytest
from PIL import Image, ImageDraw, ImageFont

from pluck import glyphs
from pluck.postprocess import OcrLine, OcrWord, build_code

pytestmark = pytest.mark.skipif(
    not (glyphs.FONT_DIR / "consola.ttf").exists(), reason="needs the Windows Consolas font"
)

CODE = """const items = [1, 2, 3];
let total = 0;
for (let i = 0; i < items.length; i++) {
  if (items[i] % 2 === 0) {
    total += items[i];
  }
}
export const sum = (list) => list.length;"""


def render(code: str, font_file: str = "consola.ttf", size: int = 15):
    """Image plus perfect OCR: one box per space-separated token."""
    font = ImageFont.truetype(str(glyphs.FONT_DIR / font_file), size)
    pitch = round(size * 1.45)
    rows = code.split("\n")
    image = Image.new("L", (int(max(font.getlength(r) for r in rows)) + 40, pitch * len(rows) + 30), 255)
    draw = ImageDraw.Draw(image)
    lines = []
    for i, row in enumerate(rows):
        y = 15 + pitch * i
        draw.text((15, y), row, font=font, fill=20)
        words, col = [], 0
        for token in row.split(" "):
            if token:
                x = 15 + font.getlength(row[:col])
                # OCR boxes hug the ink, about 0.3 of a cell narrower.
                _, top, _, bottom = font.getbbox(token)
                width = font.getlength(token) * (len(token) - 0.3) / len(token)
                words.append(OcrWord(token, x + 1, y + top, width, bottom - top))
            col += len(token) + 1
        if words:
            lines.append(OcrLine(words))
    return image, lines


def ocr_like(lines, drop=(), swap=None):
    """Simulate Windows OCR: lose some tokens, misread others."""
    swap = swap or {}
    out = []
    for line in lines:
        words = [
            OcrWord(swap.get(w.text, w.text), w.x, w.y, w.width, w.height)
            for w in line.words
            if w.text not in drop
        ]
        if words:
            out.append(OcrLine(words))
    return out


def test_recovers_symbols_ocr_dropped():
    image, lines = render(CODE)
    damaged = ocr_like(lines, drop={"}", "===", "=>", "%"})
    assert build_code(damaged) != CODE + "\n"
    report = []
    repaired = glyphs.repair(damaged, image, report)
    assert build_code(repaired) == CODE + "\n"
    assert any("recovered" in note for note in report)


def test_fixes_lookalike_characters():
    image, lines = render(CODE)
    damaged = ocr_like(lines, swap={"0;": "O;", "(list)": "Clist)"})
    report = []
    repaired = glyphs.repair(damaged, image, report)
    assert build_code(repaired) == CODE + "\n"
    assert any("look-alike" in note for note in report)


def test_keeps_correct_letters_inside_words():
    code = "def walk(root, level=1):\n    return all([level, root])"
    image, lines = render(code)
    assert build_code(glyphs.repair(lines, image)) == code + "\n"


def test_leaves_proportional_text_alone():
    if not (glyphs.FONT_DIR / "arial.ttf").exists():
        pytest.skip("needs Arial")
    image, lines = render("Settings were saved.\nClose this window to continue", "arial.ttf")
    report = []
    assert glyphs.repair(lines, image, report) is lines
    assert report == []
