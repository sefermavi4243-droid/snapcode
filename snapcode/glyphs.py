"""Second opinion on Windows OCR, read straight from the pixels.

Windows OCR is tuned for prose. On code it silently drops what does not look
like a word: a lone ``}`` line, ``===``, ``=>``, ``COUNT(*)``, half of a
template string. It also mixes up look-alikes such as ``l``/``1``/``I``,
``0``/``O`` and ``(``/``C``.

Code is drawn in a monospace font, so every character sits in a cell of a
fixed grid. This module recovers that grid from the OCR word boxes, finds the
font and size that best match the characters OCR did read, and then:

* classifies every inked cell OCR skipped by matching it against glyph
  templates rendered in that font, and
* re-checks look-alike characters inside OCR words against the same templates
  and against how that character looks elsewhere in the same image.

Everything is plain Pillow plus integer bitmasks (popcount), so it needs no
extra dependencies and runs in a few hundred milliseconds.
"""

from __future__ import annotations

import cmath
import math
import os
import statistics
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .postprocess import OcrLine, OcrWord, estimate_char_width, line_pitch, regroup_rows

FONT_DIR = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
BUNDLED_DIR = Path(__file__).parent / "fonts"
# Monospace fonts that ship with Windows, plus open-source coding fonts
# bundled with SnapCode (OFL / Bitstream Vera licences, see fonts/) for
# screenshots from JetBrains IDEs, macOS (Menlo derives from DejaVu Sans
# Mono) and tutorials. When the screenshot uses yet another font the closest
# of these still works, only a little less accurately.
FONTS = (
    FONT_DIR / "consola.ttf", FONT_DIR / "CascadiaMono.ttf", FONT_DIR / "lucon.ttf", FONT_DIR / "cour.ttf",
    BUNDLED_DIR / "JetBrainsMono-Regular.ttf", BUNDLED_DIR / "FiraCode-Regular.ttf",
    BUNDLED_DIR / "SourceCodePro-Regular.ttf", BUNDLED_DIR / "DejaVuSansMono.ttf",
)
CHARS = tuple(chr(c) for c in range(33, 127))

# A cell is accepted when its distance to the best template is below this.
ACCEPT = 0.4
# A look-alike is swapped only when the other glyph fits at least this much
# better in absolute distance and by this factor.
MARGIN = 0.05
FACTOR = 2.0
# Above this mean template distance on the characters OCR did read, the text
# is not in a monospace font we can model (UI text, prose) and nothing is
# touched. Monospace code scores below 0.26, proportional fonts above 0.5.
MAX_FIT_COST = 0.38
# Distance under which a cell counts as the same glyph as an in-image exemplar.
EXEMPLAR_MATCH = 0.08
# Characters OCR confuses with each other.
LOOKALIKES = ("l1I|i!", "0OoeQD@", "(C[{t", ")]}J", ";:", "'`", "vV", "sS", "zZ", "xX", "cC", "wW", "-~")
# Glyphs that reach below the baseline, which makes their box a poor baseline.
_DESCENDERS = set("gjpqy()[]{}|$@,;_Q")


# --------------------------------------------------------------------------
# Bitmaps
# --------------------------------------------------------------------------

def _bits(image: Image.Image) -> int:
    """Pack a mode "1" image into an int, one bit per inked pixel."""
    return int.from_bytes(image.tobytes(), "big")


def _distance(a: int, b: int, stride: int) -> float:
    """0 for identical glyph bitmaps, 1 for unrelated ones.

    Averages the plain pixel mismatch with a chamfer-like term that forgives
    ink lying within one pixel of the other shape, so hinting and
    anti-aliasing differences between renderers cost little.
    """
    union = (a | b).bit_count()
    if not union:
        return 0.0
    exact = (a ^ b).bit_count() / union

    def grow(v: int) -> int:
        return v | (v << 1) | (v >> 1) | (v << stride) | (v >> stride)

    far = (a & ~grow(b)).bit_count() + (b & ~grow(a)).bit_count()
    return (exact + far / max(1, a.bit_count() + b.bit_count())) / 2


class _Font:
    """Glyph templates of one font at one size, rendered on demand."""

    def __init__(self, path: Path, size: float) -> None:
        self.font = ImageFont.truetype(str(path), size)
        ascent, descent = self.font.getmetrics()
        self.ascent = ascent
        self.width = max(1, round(self.font.getlength("M")))
        self.height = ascent + descent
        self.stride = (self.width + 7) // 8 * 8  # bits per row in mode "1"
        self._glyphs: dict[str, int] = {}

    def glyph(self, ch: str) -> int:
        bits = self._glyphs.get(ch)
        if bits is None:
            # Draw anti-aliased and threshold like the screenshot; FreeType's
            # monochrome mode hints glyphs into noticeably different shapes.
            image = Image.new("L", (self.width, self.height), 0)
            ImageDraw.Draw(image).text((0, 0), ch, font=self.font, fill=255)
            mask = image.point(lambda p: 255 if p > 127 else 0).convert("1", dither=Image.Dither.NONE)
            bits = self._glyphs[ch] = _bits(mask)
        return bits


@lru_cache(maxsize=128)
def _font(path: Path, size: float) -> _Font:
    return _Font(path, size)


def _candidates(char_width: float) -> list[_Font]:
    """Every available font at the sizes whose advance matches the grid."""
    out = []
    for path in FONTS:
        if not path.exists():
            continue
        unit = _font(path, 100).font.getlength("M") / 100
        exact = char_width / unit
        sizes = {round(exact, 1)}
        # Hinted renderers snap advances to whole pixels, so neighbouring
        # integer sizes are plausible too.
        for size in range(max(6, int(exact * 0.85)), int(exact * 1.15) + 2):
            if abs(_font(path, size).font.getlength("M") - char_width) < 0.75:
                sizes.add(size)
        out += [_font(path, size) for size in sorted(sizes)]
    return out


# --------------------------------------------------------------------------
# Grid
# --------------------------------------------------------------------------

def _ink_mask(gray: Image.Image) -> Image.Image:
    """Binarize halfway between the background and the darkest ink."""
    sample = sorted(gray.tobytes()[:: max(1, gray.width * gray.height // 20000)])
    threshold = (sample[len(sample) // 2] + sample[len(sample) // 50]) / 2
    return gray.point(lambda p: 255 if p < threshold else 0).convert("1", dither=Image.Dither.NONE)


def _grid_period(words: list[OcrWord], estimate: float) -> tuple[float, float]:
    """Character advance and grid origin, from the phase of word starts.

    Word boxes start on the grid, so for the true advance their x positions
    agree modulo the advance. Scan a small range around the estimate for the
    period with the strongest phase coherence.
    """
    best = (-1.0, estimate, 0j)
    for step in range(-60, 61):
        period = estimate * (1 + step * 0.002)
        z = sum(cmath.exp(2j * math.pi * w.x / period) for w in words)
        if abs(z) > best[0]:
            best = (abs(z), period, z)
    _, period, z = best
    return period, cmath.phase(z) / (2 * math.pi) * period % period


def _baseline(line: OcrLine) -> float:
    clean = [w for w in line.words if not _DESCENDERS & set(w.text)]
    return statistics.median(w.y + w.height for w in clean or line.words)


def _fits_grid(word: OcrWord, char_width: float) -> bool:
    """True when the box is as wide as its text, so letters map to cells."""
    return abs(word.width / char_width - (len(word.text) - 0.3)) <= 0.8


class _Grid:
    def __init__(self, gray: Image.Image, rows: list[OcrLine]) -> None:
        self.ink = _ink_mask(gray)
        self.size = gray.size
        words = [w for row in rows for w in row.words]
        self.cw, self.origin = _grid_period(words, estimate_char_width(rows))
        self._cells: dict[tuple, int] = {}

        baselines = [_baseline(row) for row in rows]
        samples = [
            (col, base, ch)
            for row, base in zip(rows, baselines)
            for col, ch in self.known(row)
        ]
        samples = samples[:: max(1, len(samples) // 40)]
        if not samples:
            raise ValueError("nothing to calibrate on")

        # Font, size and sub-cell offset that best explain what OCR did read.
        best = None
        for font in _candidates(self.cw):
            for dx in (-2, -1, 0, 1):
                for dy in range(-3, 4):
                    cost = sum(
                        _distance(self.cell(c, b - font.ascent + dy, font, dx), font.glyph(ch), font.stride)
                        for c, b, ch in samples
                    ) / len(samples)
                    if best is None or cost < best[0]:
                        best = (cost, font, dx, dy)
        if best is None:
            raise ValueError("no monospace font installed")
        self.cost, self.font, self.dx, dy = best
        self.tops = [self._refine(row, b - self.font.ascent + dy) for row, b in zip(rows, baselines)]
        self.exemplars = self._exemplars(rows)

    def column(self, word: OcrWord) -> int:
        return round((word.x - self.origin) / self.cw)

    def known(self, row: OcrLine) -> list[tuple[int, str]]:
        """(column, char) of the ASCII letters and digits OCR read in a row."""
        out = []
        for w in row.words:
            if _fits_grid(w, self.cw):
                c0 = self.column(w)
                out += [(c0 + k, ch) for k, ch in enumerate(w.text) if ch.isascii() and ch.isalnum()]
        return out

    def cell(self, col: int, top: float, font: _Font | None = None, dx: int | None = None,
             nudge: tuple[int, int] = (0, 0)) -> int:
        font = font or self.font
        x = round(self.origin + col * self.cw) + (self.dx if dx is None else dx) + nudge[0]
        y = round(top) + nudge[1]
        key = (x, y, font.width, font.height)
        bits = self._cells.get(key)
        if bits is None:
            bits = self._cells[key] = _bits(self.ink.crop((x, y, x + font.width, y + font.height)))
        return bits

    def has_ink(self, col: int, top: float) -> bool:
        """Ink in the cell's core, ignoring strokes bleeding in from neighbours."""
        x = self.origin + col * self.cw + self.dx
        box = (round(x + 0.15 * self.cw), round(top) + 1,
               round(x + 0.85 * self.cw), round(top + self.font.height) - 1)
        if box[0] < 0 or box[1] < 0 or box[2] > self.size[0] or box[3] > self.size[1]:
            return False
        return _bits(self.ink.crop(box)).bit_count() >= 2

    def scores(self, col: int, top: float, chars) -> dict[str, float]:
        """Distance to each glyph, allowing the cell to shift by one pixel."""
        cells = [self.cell(col, top, nudge=(x, y)) for x in (-1, 0, 1) for y in (-1, 0, 1)]
        font = self.font
        return {ch: min(_distance(c, font.glyph(ch), font.stride) for c in cells) for ch in chars}

    def _refine(self, row: OcrLine, top: float) -> float:
        """Snap a row's top to the offset where its known letters match best."""
        known = self.known(row)
        if not known:
            return top
        font = self.font

        def cost(dy: int) -> tuple[float, int]:
            total = sum(_distance(self.cell(c, top + dy), font.glyph(ch), font.stride) for c, ch in known)
            return total, abs(dy)

        return top + min(range(-2, 3), key=cost)

    def _exemplars(self, rows: list[OcrLine]) -> dict[str, int]:
        """How each character OCR read 3+ times looks in this very image.

        OCR is right most of the time, so the medoid of all cells it labelled
        with a character is a faithful picture of that character.
        """
        cells: dict[str, list[int]] = {}
        for row, top in zip(rows, self.tops):
            for w in row.words:
                if _fits_grid(w, self.cw):
                    c0 = self.column(w)
                    for k, ch in enumerate(w.text):
                        if ch in CHARS:
                            cells.setdefault(ch, []).append(self.cell(c0 + k, top))
        font = self.font
        out = {}
        for ch, found in cells.items():
            if len(found) < 3:
                continue
            found = found[:15]
            medoid = min(found, key=lambda a: sum(_distance(a, b, font.stride) for b in found))
            # A consistent misreading (every 0 read as O) would make the
            # exemplar lie, so keep it only if the templates agree with it.
            group = next((g for g in LOOKALIKES if ch in g), ch)
            if min(group, key=lambda g: _distance(medoid, font.glyph(g), font.stride)) == ch:
                out[ch] = medoid
        return out


# --------------------------------------------------------------------------
# Repair
# --------------------------------------------------------------------------

def _kind(ch: str) -> str:
    if ch.isdigit():
        return "digit"
    if ch.isalpha():
        return "upper" if ch.isupper() else "lower"
    return "other"


def _decisive(mine: float, theirs: float, strict: int) -> bool:
    """True when ``theirs`` beats ``mine`` clearly enough to act on."""
    return mine - theirs >= strict * MARGIN and mine >= strict * FACTOR * theirs


def _check_lookalikes(grid: _Grid, word: OcrWord, top: float) -> int:
    """Swap look-alike characters the pixels clearly disagree with.

    Two judges: glyph templates, and exemplars (how each character looks
    elsewhere in this same image). Templates decide first; when they are not
    decisive the exemplars get a vote, since they share the screenshot's
    exact font, size and rendering.
    """
    if not _fits_grid(word, grid.cw):
        return 0
    c0 = grid.column(word)
    chars = list(word.text)
    stride = grid.font.stride
    fixed = 0
    for k, ch in enumerate(chars):
        group = next((g for g in LOOKALIKES if ch in g), None)
        if group is None:
            continue
        # Lowercase sits next to lowercase, digits next to digits; crossing
        # over (``value`` -> ``va1ue``, ``walk`` -> ``waIk``) needs much
        # stronger evidence.
        near = {_kind(n) for n in chars[max(0, k - 1):k] + chars[k + 1:k + 2]} - {"other"}

        def strictness(other: str) -> int:
            return 1 if not near or _kind(other) in near else 3

        scores = grid.scores(c0 + k, top, group)
        cell = grid.cell(c0 + k, top)
        seen = {g: _distance(cell, grid.exemplars[g], stride) for g in group if g in grid.exemplars}

        other = min(scores, key=scores.get)
        if other != ch and _decisive(scores[ch], scores[other], strictness(other)):
            # The exemplar of the OCR'd character can still overrule a
            # template rendered by a different rasterizer.
            if ch not in seen or seen[ch] > seen.get(other, scores[other]):
                chars[k] = other
                fixed += 1
            continue
        if ch in seen and len(seen) > 1:
            other = min(seen, key=seen.get)
            # A near-perfect match with a character seen elsewhere in the
            # image outweighs what the neighbours suggest (``l1`` is a name).
            strict = 1 if seen[other] <= EXEMPLAR_MATCH else strictness(other)
            if (other != ch and _decisive(seen[ch], seen[other], strict)
                    and scores[other] <= scores[ch] + MARGIN):
                chars[k] = other
                fixed += 1
    word.text = "".join(chars)
    return fixed


def _classify(grid: _Grid, col: int, top: float) -> str | None:
    # Rank all glyphs cheaply at the nominal position, then score the best
    # few properly with one-pixel shifts.
    cell = grid.cell(col, top)
    font = grid.font
    rough = sorted(CHARS, key=lambda ch: _distance(cell, font.glyph(ch), font.stride))[:12]
    scores = grid.scores(col, top, rough)
    best = min(scores, key=scores.get)
    return best if scores[best] <= ACCEPT else None


def _row_tops(grid: _Grid, rows: list[OcrLine], pitch: float) -> list[tuple[float, OcrLine | None]]:
    """Tops of the OCR rows plus the rows in between and around them that OCR
    returned nothing for (a lone ``}`` is the classic case)."""
    tops = grid.tops
    out: list[tuple[float, OcrLine | None]] = []
    for i, (row, top) in enumerate(zip(rows, tops)):
        out.append((top, row))
        if i + 1 < len(rows):
            n = round((tops[i + 1] - top) / pitch)
            step = (tops[i + 1] - top) / n if n else pitch
            out += [(top + k * step, None) for k in range(1, n)]
    out += [(tops[-1] + k * pitch, None) for k in (1, 2)]
    out += [(tops[0] - k * pitch, None) for k in (1, 2)]
    return out


def repair(lines: list[OcrLine], gray: Image.Image, report: list[str] | None = None) -> list[OcrLine]:
    """Return OCR rows with dropped characters restored and look-alikes fixed.

    ``gray`` is the screenshot in the same pixel coordinates as the word
    boxes, with dark text on a light background. On anything unexpected the
    input is returned unchanged: this pass may only ever add accuracy.
    """
    rows = regroup_rows(lines)
    if sum(len(row.words) for row in rows) < 3:
        return lines
    try:
        grid = _Grid(gray, rows)
    except ValueError:
        return lines
    if grid.cost > MAX_FIT_COST:
        return lines
    pitch = line_pitch(rows) or grid.font.height * 1.3
    height = statistics.median(w.height for row in rows for w in row.words)

    first = -int(grid.origin / grid.cw)
    last = int((gray.width - grid.origin) / grid.cw)
    fixed = recovered = 0
    out = list(rows)
    for top, row in _row_tops(grid, rows, pitch):
        covered: set[int] = set()
        for w in row.words if row else []:
            fixed += _check_lookalikes(grid, w, top)
            covered.update(range(grid.column(w), grid.column(w) + len(w.text)))

        runs: list[list] = []  # [text, first column]
        for col in range(first, last + 1):
            if col in covered or not grid.has_ink(col, top):
                continue
            ch = _classify(grid, col, top)
            if ch is None:
                continue
            if runs and runs[-1][1] + len(runs[-1][0]) == col:
                runs[-1][0] += ch
            else:
                runs.append([ch, col])
        if not runs:
            continue
        recovered += sum(len(text) for text, _ in runs)
        baseline = top + grid.font.ascent
        new = [
            OcrWord(text, grid.origin + col * grid.cw, baseline - height, (len(text) - 0.3) * grid.cw, height)
            for text, col in runs
        ]
        if row:
            row.words = sorted(row.words + new, key=lambda w: w.x)
        else:
            out.append(OcrLine(new))

    if report is not None:
        if recovered:
            report.append(f"{recovered} characters recovered from pixels")
        if fixed:
            report.append(f"{fixed} look-alike characters fixed")
    return out
