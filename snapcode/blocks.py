"""Group OCR words on a screen into rectangular text blocks.

Used for one-click selection: hovering over a code block outlines it, a click
selects it. Words are linked when they are close enough to belong to the same
paragraph of code (a blank line between functions still links, a sidebar a
few columns away does not).
"""

from __future__ import annotations

import statistics

from .postprocess import OcrLine

Rect = tuple[float, float, float, float]  # x0, y0, x1, y1


def find_blocks(lines: list[OcrLine]) -> list[Rect]:
    words = [w for line in lines for w in line.words if w.text.strip()]
    if not words:
        return []
    h = statistics.median(w.height for w in words)
    cw = statistics.median(w.width / max(len(w.text), 1) for w in words)
    max_dy, max_dx = 2.2 * h, 3.0 * cw

    parent = list(range(len(words)))

    def root(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    boxes = [(w.x, w.y, w.x + w.width, w.y + w.height) for w in words]
    order = sorted(range(len(words)), key=lambda i: boxes[i][1])
    for a_pos, a in enumerate(order):
        ax0, ay0, ax1, ay1 = boxes[a]
        for b in order[a_pos + 1:]:
            bx0, by0, bx1, by1 = boxes[b]
            if by0 - ay1 > max_dy:
                break  # sorted by top edge: nothing further down can link
            if bx0 - ax1 <= max_dx and ax0 - bx1 <= max_dx:
                parent[root(a)] = root(b)

    groups: dict[int, list[int]] = {}
    for i in range(len(words)):
        groups.setdefault(root(i), []).append(i)

    pad = 0.6 * h
    rects = []
    for members in groups.values():
        if len(members) < 2:
            continue
        rects.append((
            min(boxes[i][0] for i in members) - pad,
            min(boxes[i][1] for i in members) - pad,
            max(boxes[i][2] for i in members) + pad,
            max(boxes[i][3] for i in members) + pad,
        ))
    return _merge_overlapping(rects)


def _merge_overlapping(rects: list[Rect]) -> list[Rect]:
    rects = list(rects)
    merged = True
    while merged:
        merged = False
        for i in range(len(rects)):
            for j in range(i + 1, len(rects)):
                a, b = rects[i], rects[j]
                if a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]:
                    rects[i] = (min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3]))
                    del rects[j]
                    merged = True
                    break
            if merged:
                break
    return rects


def block_at(blocks: list[Rect], x: float, y: float) -> Rect | None:
    """Smallest block containing the point."""
    hits = [b for b in blocks if b[0] <= x <= b[2] and b[1] <= y <= b[3]]
    return min(hits, key=lambda b: (b[2] - b[0]) * (b[3] - b[1]), default=None)
