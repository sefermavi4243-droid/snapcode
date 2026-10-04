"""Plain code editor shown for the "edit" action."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QComboBox, QFileDialog, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget,
)

from .. import languages
from ..pipeline import Recognition
from .theme import CodeHighlighter, Toast, app_icon


def save_code(parent, code: str, language: languages.Language) -> bool:
    path, _ = QFileDialog.getSaveFileName(
        parent, "Kodu kaydet", f"snippet{language.extension}",
        f"{language.name} (*{language.extension});;Tüm dosyalar (*)",
    )
    if not path:
        return False
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(code)
    return True


class EditorWindow(QWidget):
    def __init__(self, result: Recognition, on_edit=None) -> None:
        super().__init__()
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setWindowTitle("SnapCode")
        self.setWindowIcon(app_icon())
        self.setObjectName("root")
        self.snippet_id: int | None = None
        self._on_edit = on_edit

        self.editor = QPlainTextEdit()
        self.editor.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.editor.setTabStopDistance(self.editor.fontMetrics().horizontalAdvance(" ") * 4)
        self.highlighter = CodeHighlighter(self.editor.document(), result.language.lexer)
        self.editor.setPlainText(result.code)
        self.editor.textChanged.connect(self._changed)

        bar = QWidget(objectName="bar")
        row = QHBoxLayout(bar)
        row.setContentsMargins(10, 6, 10, 6)
        self.lang = QComboBox()
        for lang in languages.LANGUAGES.values():
            self.lang.addItem(lang.name, lang.key)
        self.lang.setCurrentIndex(max(0, self.lang.findData(result.language.key)))
        self.lang.currentIndexChanged.connect(self._language_changed)
        row.addWidget(self.lang)
        row.addWidget(QLabel(f"{result.line_count} satır", objectName="muted"))
        row.addStretch()
        save = QPushButton("Kaydet")
        save.clicked.connect(self.save)
        copy = QPushButton("Kopyala", objectName="primary")
        copy.setDefault(True)
        copy.clicked.connect(self.copy_and_close)
        row.addWidget(save)
        row.addWidget(copy)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.editor, 1)
        layout.addWidget(bar)

        lines = result.code.splitlines() or [""]
        metrics = self.editor.fontMetrics()
        width = max(metrics.horizontalAdvance(line) for line in lines) + 60
        height = metrics.lineSpacing() * len(lines) + 90
        self.resize(min(max(width, 460), 1100), min(max(height, 220), 760))

        QShortcut(QKeySequence("Ctrl+Return"), self, activated=self.copy_and_close)
        QShortcut(QKeySequence("Ctrl+S"), self, activated=self.save)
        QShortcut(QKeySequence("Escape"), self, activated=self.close)

    @property
    def language(self) -> languages.Language:
        return languages.by_key(self.lang.currentData())

    def _language_changed(self) -> None:
        self.highlighter.set_language(self.language.lexer)
        self._changed()

    def _changed(self) -> None:
        if self._on_edit and self.snippet_id is not None:
            self._on_edit(self.snippet_id, self.editor.toPlainText(), self.language.key)

    def copy_and_close(self) -> None:
        QGuiApplication.clipboard().setText(self.editor.toPlainText())
        Toast.show_text("Kod kopyalandı")
        self.close()

    def save(self) -> None:
        if save_code(self, self.editor.toPlainText(), self.language):
            Toast.show_text("Kaydedildi")
