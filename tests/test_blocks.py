from snapcode.blocks import block_at, find_blocks
from tests.test_postprocess import layout

CODE = "def a():\n    return 1\n\ndef b():\n    return 2"


def test_code_with_blank_line_is_one_block():
    blocks = find_blocks(layout(CODE))
    assert len(blocks) == 1


def test_distant_text_is_a_separate_block():
    lines = layout(CODE) + layout("README.md\nsetup.py", x0=900)
    blocks = find_blocks(lines)
    assert len(blocks) == 2
    code_block = block_at(blocks, 60, 10)
    assert code_block and code_block[2] < 900


def test_block_at_misses_empty_space():
    assert block_at(find_blocks(layout(CODE)), 5000, 5000) is None
