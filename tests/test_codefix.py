from snapcode.codefix import balance_brackets, fix_tokens, unify_identifiers


def test_lone_closing_line_follows_its_block():
    text = "if (x) {\n  y = 1;\n]"
    assert balance_brackets(text) == ("if (x) {\n  y = 1;\n}", 1)


def test_same_line_opener_follows_its_closer():
    assert balance_brackets("items = {1, 2]") == ("items = [1, 2]", 1)
    assert balance_brackets("list.reduce({a, b) => a + b)")[0] == "list.reduce((a, b) => a + b)"


def test_c_read_for_paren():
    text = "int mainCint argc) {\n    for Cint i = 0; i < n; i++) {\n    v = Vec::newC);\n    }\n}"
    fixed, changes = balance_brackets(text)
    assert fixed == "int main(int argc) {\n    for (int i = 0; i < n; i++) {\n    v = Vec::new();\n    }\n}"
    assert changes == 3


def test_correct_code_is_untouched():
    code = (
        "def f(a, b=[1, 2]):\n    return {k: v for k, v in g(a)}\n"
        "const s = `total: ${total}`;\nprint(\"(\")  # )\nclass Config:\n    pass\n}"
    )
    assert balance_brackets(code) == (code, 0)


def test_never_rewrites_a_lone_closing_brace():
    # The stray "]" was misread somewhere above; the "}" lines are right.
    text = "fn main() {\n    let v = vec![1, 2;\n}"
    assert balance_brackets(text)[0].endswith("\n}")


def test_unifies_one_off_misspelling():
    text = "self.value = value\nreturn va1ue + self.vaIue"
    assert unify_identifiers(text) == ("self.value = value\nreturn value + self.value", 2)


def test_keywords_anchor_corrections():
    assert unify_identifiers("SELECT id FR0M users")[0] == "SELECT id FROM users"
    assert unify_identifiers("for item in items:\n    retum 1")[0] == "for item in items:\n    retum 1"


def test_leaves_distinct_names_alone():
    text = "int l1 = 0, I1 = 1;\nreturn l1 + I1 + l + i;"
    assert unify_identifiers(text) == (text, 0)


def test_fixes_tokens_code_cannot_contain():
    text = "def f() -Y bool:\n    return metrics.1ineSpacing(1ine) + 1en(x)"
    assert fix_tokens(text) == ("def f() -> bool:\n    return metrics.lineSpacing(line) + len(x)", 4)


def test_keeps_numbers_with_units():
    text = "margin: 1px 1rem; x = 1e5 + 1.1 + v1abc  # 1st"
    assert fix_tokens(text) == (text, 0)
