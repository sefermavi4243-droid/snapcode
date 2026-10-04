"""Guess the programming language of a code snippet.

Pygments' ``guess_lexer`` alone is unreliable on short, OCR-noisy snippets, so
weighted signature patterns run first and Pygments only breaks ties.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Language:
    key: str
    name: str
    extension: str
    lexer: str
    markdown: str


LANGUAGES: dict[str, Language] = {
    lang.key: lang
    for lang in [
        Language("python", "Python", ".py", "python", "python"),
        Language("javascript", "JavaScript", ".js", "javascript", "javascript"),
        Language("typescript", "TypeScript", ".ts", "typescript", "typescript"),
        Language("java", "Java", ".java", "java", "java"),
        Language("csharp", "C#", ".cs", "csharp", "csharp"),
        Language("cpp", "C++", ".cpp", "cpp", "cpp"),
        Language("c", "C", ".c", "c", "c"),
        Language("go", "Go", ".go", "go", "go"),
        Language("rust", "Rust", ".rs", "rust", "rust"),
        Language("php", "PHP", ".php", "php", "php"),
        Language("ruby", "Ruby", ".rb", "ruby", "ruby"),
        Language("kotlin", "Kotlin", ".kt", "kotlin", "kotlin"),
        Language("swift", "Swift", ".swift", "swift", "swift"),
        Language("html", "HTML", ".html", "html", "html"),
        Language("css", "CSS", ".css", "css", "css"),
        Language("sql", "SQL", ".sql", "sql", "sql"),
        Language("bash", "Bash", ".sh", "bash", "bash"),
        Language("powershell", "PowerShell", ".ps1", "powershell", "powershell"),
        Language("json", "JSON", ".json", "json", "json"),
        Language("yaml", "YAML", ".yaml", "yaml", "yaml"),
        Language("dockerfile", "Dockerfile", ".dockerfile", "docker", "dockerfile"),
        Language("text", "Düz metin", ".txt", "text", ""),
    ]
}

_SIGNATURES: dict[str, list[tuple[str, int]]] = {
    "python": [
        (r"^\s*def \w+\(.*\)\s*(->.*)?:\s*$", 5), (r"^\s*(from [\w.]+ )?import \w+", 3),
        (r"^\s*class \w+(\(.*\))?:\s*$", 5), (r"\bself\b", 3), (r"^\s*elif\b", 5),
        (r"\bprint\(", 2), (r"^\s*if __name__ == ", 8), (r"\bNone\b|\bTrue\b|\bFalse\b", 1),
        (r"^\s*@\w+", 1), (r":\s*$", 1), (r"\bf\"", 2),
    ],
    "javascript": [
        (r"\b(const|let|var) \w+ =", 3), (r"=>", 2), (r"\bfunction\b", 3),
        (r"console\.log\(", 5), (r"\brequire\(", 4), (r"\bdocument\.", 4),
        (r"^\s*export (default )?", 2), (r"===|!==", 3), (r";\s*$", 1),
    ],
    "typescript": [
        (r"\binterface \w+", 4), (r":\s*(string|number|boolean|any|void)\b", 5),
        (r"\btype \w+ =", 4), (r"<\w+>\(", 2), (r"\b(public|private|readonly) \w+:", 3),
        (r"\bas const\b", 4),
    ],
    "java": [
        (r"\bpublic (static )?(class|void|interface)\b", 5), (r"System\.out\.print", 8),
        (r"\bString\[\] args\b", 8), (r"^\s*import java\.", 8), (r"@Override", 5),
        (r"\bnew \w+\(", 1), (r"^\s*package [\w.]+;", 4),
    ],
    "csharp": [
        (r"^\s*using System", 8), (r"\bnamespace \w+", 4), (r"Console\.Write", 8),
        (r"\b(public|private) (async )?\w+ \w+\(", 2), (r"\bvar \w+ = new\b", 3),
        (r"\{ get; (set; )?\}", 8),
    ],
    "cpp": [
        (r"#include\s*<\w+(\.h)?>", 4), (r"\bstd::", 8), (r"\bcout\s*<<", 8),
        (r"\btemplate\s*<", 6), (r"\bnullptr\b", 6), (r"\busing namespace\b", 6),
    ],
    "c": [
        (r"#include\s*<(stdio|stdlib|string)\.h>", 8), (r"\bprintf\(", 4), (r"\bmalloc\(", 4),
        (r"\bint main\(", 3),
    ],
    "go": [
        (r"^\s*package \w+\s*$", 5), (r"\bfunc \(?\w+", 5), (r":=", 3), (r"\bfmt\.", 8),
        (r"\bgo func\b", 8), (r"\bchan\b", 3),
    ],
    "rust": [
        (r"\bfn \w+\(", 5), (r"\blet mut\b", 8), (r"\bimpl\b", 5), (r"println!\(", 8),
        (r"->\s*\w+\s*\{", 2), (r"\buse \w+::", 5), (r"&mut\b|&str\b", 5),
    ],
    "php": [(r"<\?php", 10), (r"\$\w+\s*=", 3), (r"->\w+\(", 1), (r"\becho\b", 2)],
    "ruby": [
        (r"^\s*def \w+[^:]*$", 3), (r"^\s*end\s*$", 4), (r"\bputs\b", 5),
        (r"\battr_(accessor|reader)\b", 8), (r"\bdo \|\w+\|", 8),
    ],
    "kotlin": [(r"\bfun \w+\(", 6), (r"\bval \w+", 3), (r"\bprintln\(", 2), (r"\bdata class\b", 8)],
    "swift": [(r"\bfunc \w+\(.*\)\s*(->\s*\w+\s*)?\{", 5), (r"\bguard let\b", 8), (r"\bimport (UIKit|SwiftUI|Foundation)\b", 10), (r"\bvar \w+:\s*\w+", 2)],
    "html": [(r"<!DOCTYPE html>", 10), (r"</?(div|span|html|body|head|p|a|ul|li)\b", 4), (r"\bclass=\"", 2)],
    "css": [(r"^\s*[.#]?[\w-]+\s*\{\s*$", 3), (r"^\s*[\w-]+:\s*[^;]+;\s*$", 3), (r"@media\b", 6), (r"\b\d+(px|rem|em|vh|vw)\b", 2)],
    "sql": [
        (r"(?i)^\s*select\b.+\bfrom\b", 8), (r"(?i)\b(insert into|create table|update \w+ set|delete from)\b", 8),
        (r"(?i)\b(where|join|group by|order by)\b", 2),
    ],
    "bash": [
        (r"^#!/bin/(ba)?sh", 10), (r"^\s*(sudo |apt |npm |pip |git |cd |ls |echo |export |curl )", 4),
        (r"\$\{?\w+\}?", 1), (r"^\s*fi\s*$|^\s*done\s*$", 6), (r"\|\s*grep\b", 4),
    ],
    "powershell": [(r"\b(Get|Set|New|Remove)-\w+", 8), (r"\$env:", 8), (r"\|\s*(Where|Select|ForEach)-Object", 8)],
    "yaml": [(r"^\s*[\w-]+:\s*$", 2), (r"^\s*- \w+", 2), (r"^\s*[\w-]+: [^{;]+$", 1), (r"^---\s*$", 4)],
    "dockerfile": [(r"^(FROM|RUN|COPY|WORKDIR|ENTRYPOINT|CMD|EXPOSE) ", 6)],
}

_COMPILED = {
    key: [(re.compile(pattern, re.MULTILINE), weight) for pattern, weight in patterns]
    for key, patterns in _SIGNATURES.items()
}

_PYGMENTS_TO_KEY = {
    "Python": "python", "JavaScript": "javascript", "TypeScript": "typescript", "Java": "java",
    "C#": "csharp", "C++": "cpp", "C": "c", "Go": "go", "Rust": "rust", "PHP": "php",
    "Ruby": "ruby", "Kotlin": "kotlin", "Swift": "swift", "HTML": "html", "CSS": "css",
    "SQL": "sql", "Bash": "bash", "PowerShell": "powershell", "JSON": "json", "YAML": "yaml",
    "Docker": "dockerfile",
}


def score(code: str) -> dict[str, int]:
    return {
        key: sum(weight * min(len(rx.findall(code)), 3) for rx, weight in patterns)
        for key, patterns in _COMPILED.items()
    }


def detect(code: str) -> Language:
    stripped = code.strip()
    if not stripped:
        return LANGUAGES["text"]
    if stripped[0] in "{[":
        try:
            json.loads(stripped)
            return LANGUAGES["json"]
        except ValueError:
            pass

    scores = score(code)
    # TypeScript is a superset of JavaScript; C++ of C.
    scores["typescript"] += scores["javascript"] if scores["typescript"] else 0
    scores["cpp"] += scores["c"] if scores["cpp"] else 0

    best, best_score = max(scores.items(), key=lambda kv: kv[1])
    if best_score >= 5:
        return LANGUAGES[best]

    try:
        from pygments.lexers import guess_lexer

        key = _PYGMENTS_TO_KEY.get(guess_lexer(code).name)
        if key:
            return LANGUAGES[key]
    except Exception:
        pass
    return LANGUAGES[best] if best_score > 0 else LANGUAGES["text"]


def by_key(key: str | None) -> Language:
    if not key:
        return LANGUAGES["text"]
    key = key.strip().lower()
    aliases = {"c#": "csharp", "cs": "csharp", "c++": "cpp", "js": "javascript", "ts": "typescript",
               "py": "python", "sh": "bash", "shell": "bash", "golang": "go", "docker": "dockerfile",
               "yml": "yaml", "plaintext": "text", "plain": "text"}
    key = aliases.get(key, key)
    for lang in LANGUAGES.values():
        if key in (lang.key, lang.name.lower()):
            return lang
    return LANGUAGES["text"]
