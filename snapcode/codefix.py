"""Fix OCR look-alike mistakes using what code must look like.

Pixels alone cannot always tell ``}`` from ``]`` or ``l`` from ``1`` at small
sizes. Code has structure that can: brackets must pair up, and a name used
five times is not spelled differently a sixth time. These passes run on the
rebuilt text and only change characters OCR is known to confuse.
"""

from __future__ import annotations

import re
from collections import Counter

_PAIRS = {"(": ")", "[": "]", "{": "}"}
_OPENERS = {v: k for k, v in _PAIRS.items()}


# --------------------------------------------------------------------------
# Brackets
# --------------------------------------------------------------------------

def _code_positions(line: str) -> list[int]:
    """Indexes of characters outside string literals and line comments."""
    out = []
    quote = None
    i = 0
    while i < len(line):
        ch = line[i]
        if quote:
            if ch == "\\":
                i += 2
                continue
            if ch == quote:
                quote = None
        elif ch in "\"'`":
            # Only treat it as a string when the quote closes on this line;
            # OCR often loses one of a pair.
            if line.find(ch, i + 1) != -1:
                quote = ch
        elif line.startswith("//", i) or (ch == "#" and line[i + 1:i + 2] in (" ", "")):
            break
        else:
            out.append(i)
        i += 1
    return out


# "C" read for "(": glued to a lowercase name before it (``mainCint``,
# ``newC)``) or standing alone before a lowercase word (``for Cint i``).
_C_FOR_PAREN = re.compile(r"(?<=[a-z0-9_ ])C(?=[a-z_])|(?<=[a-z0-9_])C(?=\))")


def balance_brackets(text: str) -> tuple[str, int]:
    """Repair brackets that do not pair up. Returns (text, changes)."""
    lines = [list(line) for line in text.split("\n")]
    stack: list[tuple[int, int]] = []  # (row, col) of open brackets
    changes = 0

    for row, chars in enumerate(lines):
        for col in _code_positions("".join(chars)):
            ch = chars[col]
            if ch in _PAIRS:
                stack.append((row, col))
                continue
            if ch not in _OPENERS:
                continue
            if stack and _PAIRS[lines[stack[-1][0]][stack[-1][1]]] == ch:
                stack.pop()
                continue
            if stack and stack[-1][0] == row:
                # Opened on this line: the opener is the likelier misread
                # (``{1, 2]`` is a list, ``reduce({a, b)`` a call). A "${"
                # template placeholder is left alone.
                r, c = stack.pop()
                if not (lines[r][c] == "{" and lines[r][c - 1:c] == ["$"]):
                    lines[r][c] = _OPENERS[ch]
                    changes += 1
                continue
            if _OPENERS[ch] in (lines[r][c] for r, c in stack):
                # Matches a bracket opened further out: an inner closer went
                # missing rather than this one being misread.
                while _PAIRS[lines[stack[-1][0]][stack[-1][1]]] != ch:
                    stack.pop()
                stack.pop()
                continue
            if ch == ")":
                # Nothing open to close: look for a "(" misread as "C".
                found = list(_C_FOR_PAREN.finditer("".join(chars[:col + 1])))
                if found:
                    chars[found[-1].start()] = "("
                    changes += 1
                    continue
            if stack and ch != "}" and not "".join(chars[:col]).strip():
                # A block opened lines ago and a lone "]" or ")" arrives:
                # OCR mangled a "}". A "}" itself is never second-guessed;
                # it is by far the most common closer on its own line.
                r, c = stack.pop()
                chars[col] = _PAIRS[lines[r][c]]
                changes += 1
    return "\n".join("".join(chars) for chars in lines), changes


# --------------------------------------------------------------------------
# Identifiers
# --------------------------------------------------------------------------

# Characters OCR swaps inside words, by visual class.
_LOOKALIKE: dict[str, str] = {}
for _group in ("l1I|i", "lt", "0Oo", "ec", "5S", "8B", "2Z", "6b", "9g",
               # Letters whose capital is the same shape, only bigger.
               "cC", "sS", "uU", "vV", "wW", "xX", "zZ"):
    for _ch in _group:
        _LOOKALIKE[_ch] = _LOOKALIKE.get(_ch, "") + _group

# Words common enough across languages to anchor a correction even when the
# snippet uses them only once.
KEYWORDS = frozenset("""
and as assert async await break case catch char class const continue def default del delete do
double elif else enum except export extends false final finally float fn for from func function
go goto if impl import in include int interface is lambda let long loop match mod mut new nil
none not null or package pass print printf println private protected pub public raise return
self static string struct super switch this throw throws true try type typeof undefined unsigned
use using var void while with yield len range list dict str bool true false none console log
select from where join group order by insert update values into limit having inner left right
outer union all distinct count sum avg min max null like between exists table create alter drop
index primary key foreign references not and or
""".split())

_WORD = re.compile(r"[A-Za-z0-9_]*[A-Za-z][A-Za-z0-9_]*")
_KEYWORD_FORMS = KEYWORDS | {k.upper() for k in KEYWORDS}


def _lookalike(a: str, b: str) -> bool:
    """Same length and every difference is a look-alike swap."""
    if len(a) != len(b) or a == b:
        return False
    return all(x == y or y in _LOOKALIKE.get(x, "") for x, y in zip(a, b))


def unify_identifiers(text: str) -> tuple[str, int]:
    """Respell one-off names that are look-alike variants of common ones.

    ``value`` used five times and ``va1ue`` once is an OCR slip, and so is
    ``FR0M``. Names under three characters are left alone: ``l`` and ``i``
    are both fine loop variables.
    """
    counts = Counter(_WORD.findall(text))
    anchors = {w for w, n in counts.items() if n >= 2} | _KEYWORD_FORMS
    fixes = {}
    for word, n in counts.items():
        if n != 1 or len(word) < 3 or word in anchors:
            continue
        matches = [a for a in anchors if _lookalike(word, a)]
        if len(matches) == 1:
            fixes[word] = matches[0]
    if not fixes:
        return text, 0
    pattern = re.compile(r"(?<![A-Za-z0-9_])(" + "|".join(map(re.escape, fixes)) + r")(?![A-Za-z0-9_])")
    return pattern.sub(lambda m: fixes[m.group(1)], text), len(fixes)
