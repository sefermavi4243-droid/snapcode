"""Measure Windows OCR accuracy on rendered code screenshots.

Renders a set of code snippets in several monospace fonts, sizes and themes,
runs them through the real recognition pipeline and reports the character
error rate (CER), exact-line accuracy and the most common mistakes.

    python tools/ocr_bench.py                 # PIL and Qt renderings
    python tools/ocr_bench.py --renderer qt -v
    python tools/ocr_bench.py --no-repair     # baseline without snapcode.glyphs

PIL renders like the glyph templates do, so it flatters the repair pass; the
Qt renderings (DirectWrite, scaling, JPEG) are the more honest number.
"""

from __future__ import annotations

import argparse
import collections
import difflib
import io
import sys
import time
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from snapcode import glyphs, pipeline  # noqa: E402
from snapcode.config import Settings  # noqa: E402

SNIPPETS = {
    "python": '''class Node:
    def __init__(self, value, left=None, right=None):
        self.value = value
        self.left = left
        self.right = right

    def __repr__(self):
        return f"Node({self.value!r})"


def insert(root, value):
    if root is None:
        return Node(value)
    if value < root.value:
        root.left = insert(root.left, value)
    else:
        root.right = insert(root.right, value)
    return root''',
    "javascript": '''const items = [1, 2, 3, 10, 101];
let total = 0;
for (let i = 0; i < items.length; i++) {
  if (items[i] % 2 === 0) {
    total += items[i];
  }
}
console.log(`total: ${total}`);
export default function sum(list) {
  return list.reduce((a, b) => a + b, 0);
}''',
    "c": '''#include <stdio.h>

int main(int argc, char **argv) {
    int l1 = 0, I1 = 1;
    for (int i = 0; i < 10; i++) {
        printf("%d\\n", i * l1 + I1);
    }
    return 0;
}''',
    "rust": '''fn main() {
    let mut v: Vec<i32> = Vec::new();
    v.push(1);
    match v.get(0) {
        Some(x) => println!("{}", x),
        None => {}
    }
}''',
    "sql": '''SELECT id, name, COUNT(*) AS n
FROM users u
JOIN orders o ON o.user_id = u.id
WHERE o.total >= 100 AND u.active = 1
GROUP BY id, name
ORDER BY n DESC;''',
}

LIGHT, DARK = ((255, 255, 255), (20, 20, 20)), ((30, 30, 30), (212, 212, 212))


def _png(image: Image.Image) -> bytes:
    out = io.BytesIO()
    image.save(out, "PNG")
    return out.getvalue()


def render_pil(code: str, font_file: str, size: int, dark: bool) -> bytes:
    font = ImageFont.truetype(str(glyphs.FONT_DIR / font_file), size)
    lines = code.split("\n")
    pitch = round(size * 1.45)
    bg, fg = DARK if dark else LIGHT
    image = Image.new("RGB", (int(max(font.getlength(l) for l in lines)) + 40, pitch * len(lines) + 30), bg)
    draw = ImageDraw.Draw(image)
    for i, line in enumerate(lines):
        draw.text((15, 15 + pitch * i), line, font=font, fill=fg)
    return _png(image)


def render_qt(code: str, family: str, px: int, dark: bool, scale: float, jpeg: bool) -> bytes:
    from PySide6.QtCore import QBuffer, QByteArray, QIODevice
    from PySide6.QtGui import QColor, QFont, QFontMetricsF, QImage, QPainter

    font = QFont(family)
    font.setPixelSize(round(px * scale))
    metrics = QFontMetricsF(font)
    lines = code.split("\n")
    pitch = round(metrics.height() * 1.35)
    bg, fg = DARK if dark else LIGHT
    image = QImage(int(max(metrics.horizontalAdvance(l) for l in lines)) + 40,
                   pitch * len(lines) + 30, QImage.Format_RGB32)
    image.fill(QColor(*bg))
    painter = QPainter(image)
    painter.setFont(font)
    painter.setPen(QColor(*fg))
    for i, line in enumerate(lines):
        painter.drawText(15, 15 + pitch * i + round(metrics.ascent()), line)
    painter.end()
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.WriteOnly)
    image.save(buffer, "PNG")
    png = bytes(data)
    if jpeg:  # video frames and screen shares are lossy
        out = io.BytesIO()
        Image.open(io.BytesIO(png)).convert("RGB").save(out, "JPEG", quality=70)
        png = _png(Image.open(io.BytesIO(out.getvalue())))
    return png


def cases(renderer: str):
    if renderer in ("pil", "both"):
        for name, code in SNIPPETS.items():
            for font in ("consola.ttf", "CascadiaMono.ttf", "lucon.ttf"):
                for size in (13, 16):
                    for dark in (False, True):
                        label = f"pil {name:10} {font:17} {size}px {'dark' if dark else 'light'}"
                        yield label, code, lambda c=code, f=font, s=size, d=dark: render_pil(c, f, s, d)
    if renderer in ("qt", "both"):
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance() or QApplication([])  # noqa: F841 - fonts need an app
        variants = ((13, 1.0, False, False), (14, 1.25, True, False), (15, 1.0, True, True), (12, 1.5, False, True))
        for name, code in SNIPPETS.items():
            for family in ("Consolas", "Cascadia Mono", "Courier New"):
                for px, scale, dark, jpeg in variants:
                    label = (f"qt  {name:10} {family:17} {px}px x{scale} {'dark' if dark else 'light'}"
                             f"{' jpeg' if jpeg else ''}")
                    yield label, code, lambda c=code, f=family, p=px, d=dark, s=scale, j=jpeg: render_qt(c, f, p, d, s, j)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--renderer", choices=("pil", "qt", "both"), default="both")
    parser.add_argument("--no-repair", action="store_true", help="skip the glyph repair pass")
    parser.add_argument("-v", "--verbose", action="store_true", help="print every case")
    parser.add_argument("--top", type=int, default=20, help="most common mistakes to list")
    args = parser.parse_args()

    if args.no_repair:
        glyphs.repair = lambda lines, gray, report=None: lines

    settings = Settings(engine="windows")
    mistakes: collections.Counter = collections.Counter()
    chars = errors = lines_total = lines_ok = 0
    elapsed = []
    for label, code, render in cases(args.renderer):
        start = time.perf_counter()
        got = pipeline.recognize(render(), settings).code.rstrip("\n")
        elapsed.append(time.perf_counter() - start)

        matcher = difflib.SequenceMatcher(None, code, got, autojunk=False)
        err = 0
        for op, a0, a1, b0, b1 in matcher.get_opcodes():
            if op != "equal":
                err += max(a1 - a0, b1 - b0)
                mistakes[(code[a0:a1], got[b0:b1])] += 1
        expected = code.split("\n")
        ok = sum(a == b for a, b in zip(expected, got.split("\n")))
        chars += len(code)
        errors += err
        lines_total += len(expected)
        lines_ok += ok
        if args.verbose:
            print(f"{label:58} CER={err / len(code):.3f}  lines={ok}/{len(expected)}")

    print(f"\n{len(elapsed)} images  CER={errors / chars:.4f}  line accuracy={lines_ok / lines_total:.3f}  "
          f"avg={sum(elapsed) / len(elapsed):.2f}s")
    for (want, got), n in mistakes.most_common(args.top):
        print(f"{n:4}  {want!r} -> {got!r}")


if __name__ == "__main__":
    main()
