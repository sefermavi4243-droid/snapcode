from pluck.postprocess import (
    BuildOptions, OcrLine, OcrWord, build_code, detect_indent_unit, fix_artifacts, strip_prompts,
)

CW = 10.0  # character advance in px
LH = 20.0  # line pitch in px


def layout(text: str, drop: str = "", gutter: bool = False, x0: float = 50.0) -> list[OcrLine]:
    """Fake OCR output: one box per space-separated token on a monospace grid.

    Characters in ``drop`` are removed from tokens, the way OCR loses them.
    """
    lines = []
    for row, line in enumerate(text.split("\n")):
        words = []
        if gutter:
            num = str(row + 1)
            words.append(OcrWord(num, 30 - len(num) * CW, row * LH, len(num) * CW - 3, 14))
        col = 0
        for token in line.split(" "):
            if token:
                kept = "".join(c for c in token if c not in drop)
                offset = len(token) - len(token.lstrip(drop)) if drop else 0
                if kept:
                    words.append(OcrWord(kept, x0 + (col + offset) * CW + 1, row * LH, len(kept) * CW - 3, 14))
            col += len(token) + 1
        if words:
            lines.append(OcrLine(words))
    return lines


SAMPLE = """def walk(root, depth=0):
    for name in os.listdir(root):
        if name.startswith("."):
            continue
        print("  " * depth + name)"""


def test_rebuilds_indentation_and_spacing():
    assert build_code(layout(SAMPLE)) == SAMPLE + "\n"


def test_two_space_indent():
    code = "if (x) {\n  y();\n  if (z) {\n    w();\n  }\n}"
    assert build_code(layout(code)) == code + "\n"


def test_blank_lines_restored():
    code = "import os\n\n\ndef main():\n    pass"
    assert build_code(layout(code)) == code + "\n"


def test_gutter_line_numbers_removed():
    options = BuildOptions()
    assert build_code(layout(SAMPLE, gutter=True), options) == SAMPLE + "\n"
    assert "line numbers removed" in options.report


def test_numbers_in_code_are_kept():
    code = "10 PRINT X\n20 GOTO 10\nX = 5"
    assert build_code(layout(code)).startswith("10 PRINT")


def test_split_ocr_lines_are_merged():
    lines = layout('x = "a     b"  # note')
    words = lines[0].words
    split = [OcrLine(words[:3]), OcrLine(words[3:])]
    assert build_code(split) == 'x = "a     b"  # note\n'


class GridProbe:
    """Pretends there is an underscore at the given character columns."""

    def __init__(self, columns, x0=50.0):
        self.columns, self.x0 = set(columns), x0

    def has_underscore(self, x0, x1, y0, y1):
        return round((x0 - self.x0) / CW - 0.1) in self.columns


def test_underscores_recovered_from_pixels():
    code = "if __name__ == x:"
    lines = layout(code, drop="_")
    underscores = [i for i, c in enumerate(code) if c == "_"]
    assert build_code(lines, probe=GridProbe(underscores)) == code + "\n"


def test_python_repl_prompts():
    lines, removed = strip_prompts([">>> for i in range(3):", "...     print(i)", "0", "1"])
    assert removed
    assert lines == ["for i in range(3):", "    print(i)", "0", "1"]


def test_shell_prompts():
    lines, removed = strip_prompts(["$ pip install pluck", "Successfully installed"])
    assert removed and lines[0] == "pip install pluck"


def test_comment_is_not_a_prompt():
    lines, removed = strip_prompts(["# setup", "x = 1"])
    assert not removed and lines[0] == "# setup"


def test_fix_artifacts():
    assert fix_artifacts("print(“hi”) — ﬁle ≤ Ø") == 'print("hi") -- file <= 0'


def test_indent_unit():
    assert detect_indent_unit([0, 4, 8, 4]) == 4
    assert detect_indent_unit([0, 2, 4, 6]) == 2
    assert detect_indent_unit([0, 3.1, 5.9]) == 3
