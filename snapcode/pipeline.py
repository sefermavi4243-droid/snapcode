"""Screenshot in, code out. Qt-free so the CLI and tests can use it."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from . import languages
from .config import Settings
from .postprocess import BuildOptions, build_code, fix_artifacts

ENGINES = {
    "auto": "Otomatik",
    "windows": "Windows OCR (çevrimdışı)",
    "claude": "Claude Vision (en yüksek doğruluk)",
}


@dataclass
class Recognition:
    code: str
    language: languages.Language
    engine: str
    elapsed_ms: int
    notes: list[str] = field(default_factory=list)

    @property
    def line_count(self) -> int:
        return len(self.code.rstrip("\n").splitlines()) if self.code.strip() else 0


def _windows(png: bytes, settings: Settings) -> tuple[str, languages.Language, list[str]]:
    from .engines import windows_ocr

    lines, probe = windows_ocr.recognize(png, settings.ocr_language)
    options = BuildOptions(
        strip_line_numbers=settings.strip_line_numbers,
        strip_prompts=settings.strip_prompts,
    )
    code = build_code(lines, options, probe)
    return code, languages.detect(code), options.report


def _claude(png: bytes, settings: Settings) -> tuple[str, languages.Language, list[str]]:
    from .engines import claude_vision

    data = claude_vision.recognize(
        png, model=settings.claude_model, effort=settings.claude_effort, api_key=settings.api_key
    )
    code = fix_artifacts(data.get("code", "")).rstrip() + "\n"
    lang = languages.by_key(data.get("language"))
    if lang.key == "text":
        lang = languages.detect(code)
    notes = [data["notes"]] if data.get("notes") else []
    return code, lang, notes


def recognize(png: bytes, settings: Settings, engine: str | None = None) -> Recognition:
    engine = engine or settings.engine
    start = time.perf_counter()
    fallback_note = None

    if engine == "auto":
        engine = "windows"
        if settings.claude_configured():
            from .engines.claude_vision import ClaudeError

            try:
                result = _claude(png, settings)
                engine = "claude"
            except ClaudeError as exc:
                fallback_note = f"Claude başarısız ({exc}), Windows OCR kullanıldı"
    elif engine == "claude":
        result = _claude(png, settings)

    if engine == "windows":
        result = _windows(png, settings)
    code, lang, notes = result
    if fallback_note:
        notes.insert(0, fallback_note)

    elapsed = round((time.perf_counter() - start) * 1000)
    return Recognition(code=code, language=lang, engine=engine, elapsed_ms=elapsed, notes=notes)
