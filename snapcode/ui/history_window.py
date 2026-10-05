"""Searchable list of past captures."""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QGuiApplication, QImage, QPixmap
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QMessageBox,
    QPlainTextEdit, QPushButton, QSplitter, QVBoxLayout, QWidget,
)

from .. import languages
from ..config import APP_NAME
from ..i18n import t
from ..history import History
from .theme import CodeHighlighter, app_icon


class HistoryWindow(QMainWindow):
    def __init__(self, history: History) -> None:
        super().__init__()
        self._history = history
        self.setWindowTitle(t("{app} — Geçmiş", app=APP_NAME))
        self.setWindowIcon(app_icon())
        self.resize(1100, 640)

        root = QWidget(objectName="root")
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(14, 14, 14, 14)

        self.search = QLineEdit(placeholderText=t("Kodda ara…  (ör. useEffect, SELECT, python)"))
        self._debounce = QTimer(singleShot=True, interval=200, timeout=self.refresh)
        self.search.textChanged.connect(self._debounce.start)
        layout.addWidget(self.search)

        split = QSplitter(Qt.Horizontal)
        self.list = QListWidget()
        self.list.currentItemChanged.connect(self._show)
        split.addWidget(self.list)

        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        self.editor = QPlainTextEdit(readOnly=True)
        self.editor.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.highlighter = CodeHighlighter(self.editor.document())
        self.thumb = QLabel(objectName="preview", alignment=Qt.AlignCenter)
        self.thumb.setFixedHeight(160)
        rl.addWidget(self.thumb)
        rl.addWidget(self.editor, 1)
        buttons = QHBoxLayout()
        delete = QPushButton(t("Sil"))
        delete.clicked.connect(self._delete)
        clear = QPushButton(t("Tümünü temizle"))
        clear.clicked.connect(self._clear)
        copy = QPushButton(t("Kopyala"), objectName="primary")
        copy.clicked.connect(self._copy)
        buttons.addWidget(delete)
        buttons.addWidget(clear)
        buttons.addStretch()
        buttons.addWidget(copy)
        rl.addLayout(buttons)
        split.addWidget(right)
        split.setSizes([380, 720])
        layout.addWidget(split, 1)
        self.refresh()

    def refresh(self) -> None:
        self.list.clear()
        for snip in self._history.search(self.search.text().strip()):
            lang = languages.by_key(snip.language)
            item = QListWidgetItem(f"{snip.title}\n{t(lang.name)} · {snip.created_at:%d.%m.%Y %H:%M}")
            item.setData(Qt.UserRole, snip)
            self.list.addItem(item)
        if self.list.count():
            self.list.setCurrentRow(0)
        else:
            self.editor.clear()
            self.thumb.clear()

    def _current(self):
        item = self.list.currentItem()
        return item.data(Qt.UserRole) if item else None

    def _show(self) -> None:
        snip = self._current()
        if not snip:
            return
        self.editor.setPlainText(snip.code)
        self.highlighter.set_language(languages.by_key(snip.language).lexer)
        png = self._history.image(snip.id)
        if png:
            pix = QPixmap.fromImage(QImage.fromData(png))
            self.thumb.setPixmap(pix.scaled(self.thumb.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            self.thumb.clear()

    def _copy(self) -> None:
        if self._current():
            QGuiApplication.clipboard().setText(self.editor.toPlainText())

    def _delete(self) -> None:
        snip = self._current()
        if snip:
            self._history.delete(snip.id)
            self.refresh()

    def _clear(self) -> None:
        if QMessageBox.question(self, t("Geçmişi temizle"), t("Tüm geçmiş silinsin mi?")) == QMessageBox.Yes:
            self._history.clear()
            self.refresh()
