"""Window that shows the screenshot next to the recognized, editable code."""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication, QImage, QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QComboBox, QFileDialog, QHBoxLayout, QLabel, QMainWindow, QPlainTextEdit, QPushButton,
    QSplitter, QVBoxLayout, QWidget,
)

from .. import languages
from ..pipeline import Recognition
from .theme import CodeHighlighter, app_icon


class ResultWindow(QMainWindow):
    """``rerun(engine)`` asks the app to process the same image again."""

    def __init__(self, png: bytes, rerun: Callable[["ResultWindow", str], None], on_edit=None) -> None:
        super().__init__()
        self.png = png
        self.snippet_id: int | None = None
        self._rerun = rerun
        self._on_edit = on_edit
        self._loading = False
        self.setWindowTitle("SnapCode")
        self.setWindowIcon(app_icon())
        self.resize(1180, 660)
        self.setWindowFlag(Qt.WindowStaysOnTopHint, True)

        root = QWidget(objectName="root")
        layout = QVBoxLayout(root)
        layout.setContentsMargins(14, 14, 14, 10)
        self.setCentralWidget(root)

        # Toolbar
        bar = QHBoxLayout()
        self.lang_box = QComboBox()
        for lang in languages.LANGUAGES.values():
            self.lang_box.addItem(lang.name, lang.key)
        self.lang_box.currentIndexChanged.connect(self._language_changed)
        bar.addWidget(QLabel("Dil:"))
        bar.addWidget(self.lang_box)
        bar.addSpacing(12)
        self.btn_windows = QPushButton("↻ Windows OCR")
        self.btn_windows.setToolTip("Çevrimdışı motorla yeniden tanı")
        self.btn_windows.clicked.connect(lambda: self._request("windows"))
        self.btn_claude = QPushButton("✦ Claude ile mükemmelleştir")
        self.btn_claude.setToolTip("Claude Vision ile birebir girinti ve karakter doğruluğu")
        self.btn_claude.clicked.connect(lambda: self._request("claude"))
        bar.addWidget(self.btn_windows)
        bar.addWidget(self.btn_claude)
        bar.addStretch()
        save = QPushButton("Kaydet…")
        save.clicked.connect(self.save_as)
        markdown = QPushButton("Markdown")
        markdown.setToolTip("```dil … ``` bloğu olarak kopyala")
        markdown.clicked.connect(self.copy_markdown)
        self.copy_btn = QPushButton("Kopyala  Ctrl+Enter", objectName="primary")
        self.copy_btn.clicked.connect(self.copy_and_close)
        for b in (save, markdown, self.copy_btn):
            bar.addWidget(b)
        layout.addLayout(bar)

        # Body
        split = QSplitter(Qt.Horizontal)
        self.preview = QLabel(objectName="preview")
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setMinimumWidth(260)
        self._pixmap = QPixmap.fromImage(QImage.fromData(png))
        self.editor = QPlainTextEdit()
        self.editor.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.editor.setTabStopDistance(self.editor.fontMetrics().horizontalAdvance(" ") * 4)
        self.editor.textChanged.connect(self._text_changed)
        self.highlighter = CodeHighlighter(self.editor.document())
        split.addWidget(self.preview)
        split.addWidget(self.editor)
        split.setSizes([440, 740])
        layout.addWidget(split, 1)

        self.status = QLabel(objectName="muted")
        layout.addWidget(self.status)

        QShortcut(QKeySequence("Ctrl+Return"), self, activated=self.copy_and_close)
        QShortcut(QKeySequence("Ctrl+S"), self, activated=self.save_as)
        QShortcut(QKeySequence("Escape"), self, activated=self.close)
        self.set_busy("Tanınıyor…")

    # -- state -------------------------------------------------------------
    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._scale_preview()

    def _scale_preview(self) -> None:
        if not self._pixmap.isNull():
            self.preview.setPixmap(
                self._pixmap.scaled(self.preview.size() * 0.96, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            )

    def set_busy(self, message: str) -> None:
        self.status.setText(f"⏳ {message}")
        for b in (self.btn_windows, self.btn_claude, self.copy_btn):
            b.setEnabled(False)

    def set_error(self, message: str) -> None:
        self.status.setText(f"⚠ {message}")
        for b in (self.btn_windows, self.btn_claude, self.copy_btn):
            b.setEnabled(True)

    def set_result(self, result: Recognition) -> None:
        self._loading = True
        self.editor.setPlainText(result.code)
        index = self.lang_box.findData(result.language.key)
        self.lang_box.setCurrentIndex(max(0, index))
        self.highlighter.set_language(result.language.lexer)
        self._loading = False
        for b in (self.btn_windows, self.btn_claude, self.copy_btn):
            b.setEnabled(True)
        engine = {"windows": "Windows OCR", "claude": "Claude Vision"}.get(result.engine, result.engine)
        parts = [f"{engine} · {result.elapsed_ms} ms · {result.line_count} satır"]
        parts += result.notes
        self.status.setText("✓ " + " · ".join(parts))
        self._scale_preview()

    @property
    def language(self) -> languages.Language:
        return languages.by_key(self.lang_box.currentData())

    def _language_changed(self) -> None:
        self.highlighter.set_language(self.language.lexer)
        self._text_changed()

    def _text_changed(self) -> None:
        if not self._loading and self._on_edit and self.snippet_id is not None:
            self._on_edit(self.snippet_id, self.editor.toPlainText(), self.language.key)

    def _request(self, engine: str) -> None:
        self.set_busy("Claude Vision okuyor…" if engine == "claude" else "Windows OCR çalışıyor…")
        self._rerun(self, engine)

    # -- actions -----------------------------------------------------------
    def copy_and_close(self) -> None:
        QGuiApplication.clipboard().setText(self.editor.toPlainText())
        self.close()

    def copy_markdown(self) -> None:
        code = self.editor.toPlainText().rstrip("\n")
        QGuiApplication.clipboard().setText(f"```{self.language.markdown}\n{code}\n```\n")
        self.status.setText("✓ Markdown bloğu olarak kopyalandı")

    def save_as(self) -> None:
        lang = self.language
        path, _ = QFileDialog.getSaveFileName(
            self, "Kodu kaydet", f"snippet{lang.extension}", f"{lang.name} (*{lang.extension});;Tüm dosyalar (*)"
        )
        if path:
            with open(path, "w", encoding="utf-8", newline="\n") as f:
                f.write(self.editor.toPlainText())
            self.status.setText(f"✓ Kaydedildi: {path}")
