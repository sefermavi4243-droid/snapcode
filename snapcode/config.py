"""Persistent user settings stored as JSON under %APPDATA%\\SnapCode."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, fields
from pathlib import Path

APP_NAME = "SnapCode"


def data_dir() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home() / ".config")
    path = Path(base) / APP_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


@dataclass
class Settings:
    hotkey: str = "ctrl+shift+x"
    engine: str = "auto"  # auto | windows | claude
    ocr_language: str = "en-US"
    claude_model: str = "claude-opus-5-5"
    claude_effort: str = "low"
    api_key: str = ""
    instant_copy: bool = False  # copy as soon as the mouse is released
    watch_clipboard: bool = False
    strip_line_numbers: bool = True
    strip_prompts: bool = True
    keep_history: bool = True

    @classmethod
    def load(cls, path: Path | None = None) -> "Settings":
        path = path or data_dir() / "settings.json"
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return cls()
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in raw.items() if k in known})

    def save(self, path: Path | None = None) -> None:
        path = path or data_dir() / "settings.json"
        path.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")

    def claude_configured(self) -> bool:
        return bool(
            self.api_key
            or os.environ.get("ANTHROPIC_API_KEY")
            or os.environ.get("ANTHROPIC_AUTH_TOKEN")
        )
