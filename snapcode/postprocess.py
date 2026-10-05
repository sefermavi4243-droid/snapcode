"""Turn raw OCR geometry into clean, correctly indented source code.

Generic OCR engines return words with bounding boxes but throw away
whitespace, which is fatal for code. Screenshots of code are almost always
rendered in a monospace font, so the horizontal position of each word maps
back to a character column. This module uses that to rebuild indentation,
inner alignment and blank lines, then strips editor noise such as gutter line
numbers and shell prompts.
"""

from __future__ import annotations

import re
import statistics
from dataclasses import dataclass, field
from typing import Protocol

from . import codefix


@dataclass
class OcrWord:
    text: str
    x: float
    y: float
    width: float
    height: float

    @property
    def right(self) -> float:
        return self.x + self.width


@dataclass
class OcrLine:
    words: list[OcrWord]
    y: float = 0.0
    height: float = 0.0

    def __post_init__(self) -> None:
        if self.words and not self.height:
            self.y = min(w.y for w in self.words)
            self.height = max(w.height for w in self.words)

    @property
    def x(self) -> float:
        return self.words[0].x

    @property
    def text(self) -> str:
        return " ".join(w.text for w in self.words)


@dataclass
class BuildOptions:
    strip_line_numbers: bool = True
    strip_prompts: bool = True
    rebuild_blank_lines: bool = True
    fix_artifacts: bool = True
    fix_structure: bool = True  # bracket pairing, consistent identifier spelling
    report: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------
# Geometry
# --------------------------------------------------------------------------

def regroup_rows(lines: list[OcrLine]) -> list[OcrLine]:
    """Merge words into visual rows by vertical position.

    OCR engines often split one row into several "lines" when it contains a
    wide gap (an aligned comment, a gutter number, a run of spaces inside a
    string). For code a row is the unit that matters, so rebuild rows from the
    word boxes themselves.
    """
    words = [w for line in lines for w in line.words]
    if not words:
        return []
    tolerance = statistics.median(w.height for w in words) * 0.6
    words.sort(key=lambda w: w.y + w.height / 2)

    rows: list[list[OcrWord]] = []
    centers: list[float] = []
    for word in words:
        center = word.y + word.height / 2
        if rows and abs(center - centers[-1]) <= tolerance:
            rows[-1].append(word)
            centers[-1] = statistics.mean(w.y + w.height / 2 for w in rows[-1])
        else:
            rows.append([word])
            centers.append(center)
    return [OcrLine(sorted(row, key=lambda w: w.x)) for row in rows]


def estimate_char_width(lines: list[OcrLine]) -> float:
    """Advance width of one character, assuming a monospace font.

    A word box spans the ink of its glyphs, which is roughly ``len - 0.3``
    advances wide (the first and last glyphs have side bearings).
    """
    for min_len in (4, 2, 1):
        samples = [
            w.width / max(len(w.text) - 0.3, 0.7)
            for line in lines
            for w in line.words
            if len(w.text) >= min_len
        ]
        if len(samples) >= 3 or (samples and min_len == 1):
            return statistics.median(samples)
    heights = [line.height for line in lines if line.height]
    return statistics.median(heights) * 0.55 if heights else 8.0


class InkProbe(Protocol):
    def has_underscore(self, x0: float, x1: float, y0: float, y1: float) -> bool: ...


def join_words(line: OcrLine, char_width: float, probe: InkProbe | None = None) -> str:
    """Join words, restoring the number of spaces between them from the gaps.

    Positions are measured on the monospace character grid relative to the
    previous word's start, so punctuation boxes with large side bearings
    (".", ",", ":") do not grow phantom spaces.

    OCR engines routinely drop underscores, leaving ``__name__`` as a gap
    before ``name``. With a ``probe`` into the original pixels, each gap
    column is checked for a horizontal stroke on the baseline and turned back
    into ``_`` when one is found.
    """
    if not line.words:
        return ""
    baseline = statistics.median(w.y + w.height for w in line.words)
    height = statistics.median(w.height for w in line.words)
    y0, y1 = baseline - 0.08 * height, baseline + 0.4 * height

    def gap(start: float, count: int) -> str:
        if probe is None:
            return " " * count
        chars = []
        for k in range(count):
            x0 = start + k * char_width
            hit = probe.has_underscore(x0 + 0.1 * char_width, x0 + 0.9 * char_width, y0, y1)
            chars.append("_" if hit else " ")
        return "".join(chars)

    first = line.words[0]
    lead = gap(first.x - 2 * char_width, 2)
    parts = [lead[len(lead.rstrip("_")):] + first.text]
    for prev, word in zip(line.words, line.words[1:]):
        columns = (word.x - prev.x) / char_width
        spaces = max(0, round(columns - len(prev.text)))
        parts.append(gap(prev.x + len(prev.text) * char_width, spaces) + word.text)
    last = line.words[-1]
    tail = gap(last.x + len(last.text) * char_width, 2)
    parts.append(tail[: len(tail) - len(tail.lstrip("_"))])
    return "".join(parts)


def detect_indent_unit(columns: list[float]) -> int:
    """Pick the indentation step (4, 2, 3 or 1) that best explains the columns."""
    nonzero = [c for c in columns if c >= 0.75]
    if not nonzero:
        return 4
    for unit in (4, 2, 3):
        errors = [abs(c / unit - round(c / unit)) * unit for c in nonzero]
        if statistics.mean(errors) < 0.45 and all(round(c / unit) >= 1 for c in nonzero):
            return unit
    return 1


def indent_columns(lines: list[OcrLine], char_width: float) -> list[int]:
    """Indentation (in spaces) of each non-empty line, snapped to the indent unit."""
    present = [line for line in lines if line.words]
    if not present:
        return [0] * len(lines)
    base = min(line.x for line in present)
    raw = [(line.x - base) / char_width if line.words else 0.0 for line in lines]
    unit = detect_indent_unit([c for c, line in zip(raw, lines) if line.words])
    return [round(c / unit) * unit for c in raw]


def line_pitch(lines: list[OcrLine]) -> float | None:
    ys = sorted(line.y for line in lines)
    diffs = [b - a for a, b in zip(ys, ys[1:]) if b - a > 0]
    if not diffs:
        return None
    # The smallest common spacing is the true line height; gaps above it are
    # blank lines. The lower quartile is robust against those gaps.
    diffs.sort()
    return diffs[len(diffs) // 4]


# --------------------------------------------------------------------------
# Noise removal
# --------------------------------------------------------------------------

_NUMBER = re.compile(r"^\d{1,5}$")


def strip_line_numbers(lines: list[OcrLine], char_width: float) -> bool:
    """Remove an editor gutter of line numbers in place. Returns True if removed."""
    candidates = [line for line in lines if line.words and _NUMBER.match(line.words[0].text)]
    nonempty = [line for line in lines if line.words]
    if len(candidates) < 2 or len(candidates) < 0.6 * len(nonempty):
        return False

    numbers = [int(line.words[0].text) for line in candidates]
    steps = [b - a for a, b in zip(numbers, numbers[1:])]
    # Consecutive rows; a step of 2-3 means OCR missed a number on a blank row.
    if sum(1 for s in steps if 1 <= s <= 3) < 0.7 * len(steps):
        return False

    # A gutter is right-aligned: the numbers end at the same x.
    rights = [line.words[0].right for line in candidates]
    if statistics.pstdev(rights) > char_width * 1.5:
        return False

    for line in candidates:
        line.words.pop(0)
    return True


_REPL = re.compile(r"^(>>>|\.\.\.)( |$)")
_SHELL = re.compile(r"^(\$|PS [^>]*>|[A-Za-z]:\\[^>]*>|\w+@[\w.-]+:[^$#]*[$#]) ")


def strip_prompts(text_lines: list[str]) -> tuple[list[str], bool]:
    """Remove Python REPL and shell prompts, keeping output lines intact."""
    stripped_lines = [line.lstrip() for line in text_lines]

    if any(s.startswith(">>>") for s in stripped_lines):
        out = []
        for line, s in zip(text_lines, stripped_lines):
            match = _REPL.match(s)
            out.append(s[match.end():] if match else line)
        return _dedent(out), True

    prompted = [s for s in stripped_lines if _SHELL.match(s)]
    first = next((s for s in stripped_lines if s), "")
    if prompted and _SHELL.match(first):
        out = [_SHELL.sub("", s, count=1) if _SHELL.match(s) else line
               for line, s in zip(text_lines, stripped_lines)]
        return out, True
    return text_lines, False


def _dedent(lines: list[str]) -> list[str]:
    indents = [len(line) - len(line.lstrip()) for line in lines if line.strip()]
    cut = min(indents, default=0)
    return [line[cut:] for line in lines]


# --------------------------------------------------------------------------
# Character fixes
# --------------------------------------------------------------------------

ARTIFACTS = {
    "“": '"', "”": '"', "„": '"', "«": '"', "»": '"',
    "‘": "'", "’": "'", "‚": "'", "´": "'",
    "—": "--", "–": "-", "−": "-", "…": "...",
    "ﬁ": "fi", "ﬂ": "fl", "ﬀ": "ff", "ﬃ": "ffi", "ﬄ": "ffl",
    "\u00a0": " ", "\u2009": " ", "\u200b": "",
    "，": ",", "；": ";", "：": ":", "（": "(", "）": ")",
    "＝": "=", "×": "*", "≤": "<=", "≥": ">=", "≠": "!=",
    "→": "->", "⇒": "=>",
    # Slashed zeros in fonts such as Consolas.
    "Ø": "0", "ø": "0", "∅": "0",
}
_ARTIFACT_RE = re.compile("|".join(re.escape(k) for k in sorted(ARTIFACTS, key=len, reverse=True)))


def fix_artifacts(text: str) -> str:
    """Replace typographic characters OCR likes to invent with their ASCII form."""
    return _ARTIFACT_RE.sub(lambda m: ARTIFACTS[m.group(0)], text)


# --------------------------------------------------------------------------
# Pipeline
# --------------------------------------------------------------------------

def build_code(
    lines: list[OcrLine], options: BuildOptions | None = None, probe: InkProbe | None = None
) -> str:
    """Convert OCR lines (any order) into source text."""
    options = options or BuildOptions()
    lines = regroup_rows(lines)
    if not lines:
        return ""

    char_width = estimate_char_width(lines)

    if options.strip_line_numbers and strip_line_numbers(lines, char_width):
        options.report.append("line numbers removed")

    indents = indent_columns(lines, char_width)
    pitch = line_pitch(lines) if options.rebuild_blank_lines else None

    out: list[str] = []
    prev_y = None
    for line, indent in zip(lines, indents):
        if pitch and prev_y is not None:
            blanks = round((line.y - prev_y) / pitch) - 1
            out.extend([""] * max(0, min(blanks, 3)))
        prev_y = line.y
        if not line.words:  # a gutter number on an otherwise blank line
            out.append("")
            continue
        text = join_words(line, char_width, probe)
        # Recovered leading underscores sit left of the first OCR'd word.
        recovered = len(text) - len(text.lstrip("_")) - (
            len(line.words[0].text) - len(line.words[0].text.lstrip("_"))
        )
        out.append(" " * max(0, indent - recovered) + text)

    if options.strip_prompts:
        out, removed = strip_prompts(out)
        if removed:
            options.report.append("prompts removed")

    text = "\n".join(line.rstrip() for line in out).strip("\n")
    if options.fix_artifacts:
        fixed = fix_artifacts(text)
        if fixed != text:
            options.report.append("typographic characters fixed")
        text = fixed
    if options.fix_structure:
        text, n = codefix.balance_brackets(text)
        if n:
            options.report.append(f"{n} brackets paired up")
        text, n = codefix.fix_tokens(text)
        if n:
            options.report.append(f"{n} impossible tokens fixed")
        text, n = codefix.unify_identifiers(text)
        if n:
            options.report.append(f"{n} misspelled names unified")
    return text + "\n"
