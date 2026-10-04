"""SQLite-backed history of every snippet captured."""

from __future__ import annotations

import io
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from PIL import Image

from .config import data_dir

_SCHEMA = """
CREATE TABLE IF NOT EXISTS snippets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    language TEXT NOT NULL,
    engine TEXT NOT NULL,
    code TEXT NOT NULL,
    image BLOB
);
CREATE INDEX IF NOT EXISTS snippets_created ON snippets(created_at);
"""

_THUMB_EDGE = 1200


@dataclass
class Snippet:
    id: int
    created_at: datetime
    language: str
    engine: str
    code: str
    image: bytes | None = None

    @property
    def title(self) -> str:
        first = next((line.strip() for line in self.code.splitlines() if line.strip()), "(boş)")
        return first[:70]


class History:
    def __init__(self, path: Path | None = None) -> None:
        self._db = sqlite3.connect(path or data_dir() / "history.db", check_same_thread=False)
        self._db.executescript(_SCHEMA)

    def add(self, code: str, language: str, engine: str, png: bytes | None = None) -> int:
        cur = self._db.execute(
            "INSERT INTO snippets (created_at, language, engine, code, image) VALUES (?, ?, ?, ?, ?)",
            (datetime.now().isoformat(timespec="seconds"), language, engine, code, _shrink(png)),
        )
        self._db.commit()
        return cur.lastrowid

    def update_code(self, snippet_id: int, code: str, language: str) -> None:
        self._db.execute(
            "UPDATE snippets SET code = ?, language = ? WHERE id = ?", (code, language, snippet_id)
        )
        self._db.commit()

    def search(self, query: str = "", limit: int = 200) -> list[Snippet]:
        sql = "SELECT id, created_at, language, engine, code FROM snippets"
        args: tuple = ()
        if query:
            sql += " WHERE code LIKE ? OR language LIKE ?"
            args = (f"%{query}%", f"%{query}%")
        sql += " ORDER BY id DESC LIMIT ?"
        rows = self._db.execute(sql, (*args, limit)).fetchall()
        return [Snippet(r[0], datetime.fromisoformat(r[1]), r[2], r[3], r[4]) for r in rows]

    def image(self, snippet_id: int) -> bytes | None:
        row = self._db.execute("SELECT image FROM snippets WHERE id = ?", (snippet_id,)).fetchone()
        return row[0] if row else None

    def delete(self, snippet_id: int) -> None:
        self._db.execute("DELETE FROM snippets WHERE id = ?", (snippet_id,))
        self._db.commit()

    def clear(self) -> None:
        self._db.execute("DELETE FROM snippets")
        self._db.commit()


def _shrink(png: bytes | None) -> bytes | None:
    if not png:
        return None
    image = Image.open(io.BytesIO(png))
    if max(image.size) <= _THUMB_EDGE:
        return png
    image.thumbnail((_THUMB_EDGE, _THUMB_EDGE), Image.Resampling.LANCZOS)
    out = io.BytesIO()
    image.save(out, "PNG", optimize=True)
    return out.getvalue()
