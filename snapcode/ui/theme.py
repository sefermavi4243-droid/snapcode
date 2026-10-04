"""Dark theme, syntax highlighting and the generated app icon."""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import (
    QColor, QFont, QIcon, QLinearGradient, QPainter, QPixmap, QSyntaxHighlighter, QTextCharFormat,
)
from pygments.lexers import get_lexer_by_name
from pygments.token import Comment, Keyword, Name, Number, Operator, String, Token
from pygments.util import ClassNotFound

STYLESHEET = """
* { font-family: 'Segoe UI'; font-size: 10pt; color: #e6edf3; }
QMainWindow, QDialog, QWidget#root { background: #0f141c; }
QPlainTextEdit, QListWidget, QLineEdit, QComboBox, QSpinBox {
    background: #161c26; border: 1px solid #263041; border-radius: 8px; padding: 6px;
    selection-background-color: #2b5a9e;
}
QPlainTextEdit { font-family: 'Cascadia Code', 'Consolas'; font-size: 11pt; }
QListWidget::item { padding: 8px; border-radius: 6px; }
QListWidget::item:selected { background: #1f3a5f; }
QPushButton {
    background: #1d2633; border: 1px solid #2b3647; border-radius: 8px; padding: 7px 14px;
}
QPushButton:hover { background: #253144; border-color: #4f9dff; }
QPushButton#primary { background: #2f6fd6; border-color: #2f6fd6; font-weight: 600; }
QPushButton#primary:hover { background: #3b7ff0; }
QPushButton:disabled { color: #5b6677; }
QLabel#muted, QStatusBar { color: #8b98a9; }
QLabel#preview { background: #0a0e14; border: 1px solid #263041; border-radius: 8px; }
QCheckBox::indicator { width: 16px; height: 16px; }
QMenu { background: #161c26; border: 1px solid #263041; padding: 4px; }
QMenu::item { padding: 6px 22px; border-radius: 4px; }
QMenu::item:selected { background: #1f3a5f; }
QSplitter::handle { background: #0f141c; width: 8px; }
QToolTip { background: #161c26; border: 1px solid #263041; color: #e6edf3; }
"""

_PALETTE = {
    Keyword: ("#c678dd", False),
    Name.Function: ("#61afef", False),
    Name.Class: ("#e5c07b", False),
    Name.Builtin: ("#56b6c2", False),
    Name.Decorator: ("#e5c07b", False),
    Name.Tag: ("#e06c75", False),
    Name.Attribute: ("#d19a66", False),
    Name.Exception: ("#e5c07b", False),
    String: ("#98c379", False),
    Number: ("#d19a66", False),
    Operator: ("#56b6c2", False),
    Comment: ("#7f848e", True),
}


class CodeHighlighter(QSyntaxHighlighter):
    def __init__(self, document, language: str = "text") -> None:
        super().__init__(document)
        self._formats: dict = {}
        self._lexer = None
        self.set_language(language)

    def set_language(self, lexer_name: str) -> None:
        try:
            self._lexer = get_lexer_by_name(lexer_name, stripnl=False, ensurenl=False)
        except ClassNotFound:
            self._lexer = None
        self.rehighlight()

    def _format(self, ttype):
        if ttype in self._formats:
            return self._formats[ttype]
        probe = ttype
        while probe is not Token and probe not in _PALETTE:
            probe = probe.parent
        fmt = None
        if probe in _PALETTE:
            color, italic = _PALETTE[probe]
            fmt = QTextCharFormat()
            fmt.setForeground(QColor(color))
            fmt.setFontItalic(italic)
        self._formats[ttype] = fmt
        return fmt

    def highlightBlock(self, text: str) -> None:
        if not self._lexer or not text:
            return
        pos = 0
        for ttype, value in self._lexer.get_tokens(text):
            fmt = self._format(ttype)
            if fmt is not None:
                self.setFormat(pos, len(value), fmt)
            pos += len(value)


def app_icon() -> QIcon:
    icon = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        pix = QPixmap(size, size)
        pix.fill(Qt.transparent)
        p = QPainter(pix)
        p.setRenderHint(QPainter.Antialiasing)
        grad = QLinearGradient(0, 0, size, size)
        grad.setColorAt(0, QColor("#4f9dff"))
        grad.setColorAt(1, QColor("#8a5cff"))
        p.setBrush(grad)
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(QRectF(0, 0, size, size), size * 0.22, size * 0.22)
        p.setPen(QColor("white"))
        font = QFont("Consolas", max(5, int(size * 0.36)), QFont.Bold)
        p.setFont(font)
        p.drawText(QRectF(0, 0, size, size * 0.96), Qt.AlignCenter, "</>")
        p.end()
        icon.addPixmap(pix)
    return icon
