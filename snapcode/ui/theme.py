"""Styling, syntax highlighting, icons and the toast notification."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRect, QRectF, Qt, QTimer
from PySide6.QtGui import (
    QColor, QFontDatabase, QGuiApplication, QIcon, QPainter, QPainterPath, QPen, QPixmap,
    QSyntaxHighlighter, QTextCharFormat,
)
from PySide6.QtWidgets import QLabel
from pygments.lexers import get_lexer_by_name
from pygments.token import Comment, Keyword, Name, Number, String, Token
from pygments.util import ClassNotFound

ACCENT = QColor("#1a73e8")

# Brand palette (CodeLift, "Ocean"): deep petrol ink, ice paper, turquoise
# highlight, amber for "nothing found".
INK = QColor("#0F1B24")
PAPER = QColor("#F2F7F7")
HIGHLIGHT = QColor("#2EC4B6")
GRAPHITE = QColor("#1C2B36")
LEAD = QColor("#8A9AA6")
EMBER = QColor("#FF9F1C")

STYLESHEET = """
QWidget { font-family: 'Segoe UI'; font-size: 9pt; color: #202124; }
QDialog, QMainWindow, QWidget#root { background: #ffffff; }
QPlainTextEdit {
    background: #ffffff; border: none; padding: 8px;
    font-family: 'Consolas'; font-size: 10.5pt; selection-background-color: #c6dafc;
}
QListWidget { border: none; border-right: 1px solid #e0e0e0; background: #fafafa; }
QListWidget::item { padding: 6px 8px; }
QListWidget::item:selected { background: #e8f0fe; color: #202124; }
QLineEdit, QComboBox {
    border: 1px solid #dadce0; border-radius: 3px; padding: 3px 6px; background: #ffffff;
}
QLineEdit:focus, QComboBox:focus { border-color: #1a73e8; }
QPushButton {
    background: #ffffff; border: 1px solid #dadce0; border-radius: 3px; padding: 4px 14px;
}
QPushButton:hover { background: #f1f3f4; }
QToolButton {
    background: #ffffff; border: 1px solid #dadce0; border-radius: 3px; padding: 4px 10px;
}
QToolButton:hover { background: #f1f3f4; }
QToolButton[popupMode="1"] { padding-right: 24px; }
QToolButton::menu-button { border-left: 1px solid #dadce0; width: 18px; }
QPushButton#primary { background: #1a73e8; border-color: #1a73e8; color: #ffffff; }
QPushButton#primary:hover { background: #1765cc; }
QWidget#bar { background: #f8f9fa; border-top: 1px solid #e0e0e0; }
QLabel#muted { color: #5f6368; }
QMenu { background: #ffffff; border: 1px solid #dadce0; padding: 4px 0; }
QMenu::item { padding: 5px 24px 5px 20px; }
QMenu::item:selected { background: #f1f3f4; }
QMenu::separator { height: 1px; background: #e0e0e0; margin: 4px 0; }
QToolTip { background: #3c4043; color: #ffffff; border: none; padding: 4px 6px; }
"""

# GitHub light palette.
_PALETTE = {
    Keyword: ("#cf222e", False),
    Name.Function: ("#8250df", False),
    Name.Class: ("#953800", False),
    Name.Builtin: ("#0550ae", False),
    Name.Decorator: ("#8250df", False),
    Name.Tag: ("#116329", False),
    Name.Attribute: ("#0550ae", False),
    Name.Exception: ("#953800", False),
    String: ("#0a3069", False),
    Number: ("#0550ae", False),
    Comment: ("#6e7781", True),
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


def load_brand_fonts() -> None:
    """Register the bundled JetBrains Mono, the brand's monospace face."""
    from ..glyphs import BUNDLED_DIR

    QFontDatabase.addApplicationFont(str(BUNDLED_DIR / "JetBrainsMono-Regular.ttf"))


# --------------------------------------------------------------------------
# Icons: simple 1.6px line drawings, crisp at 20px.
# --------------------------------------------------------------------------

def _draw_icon(name: str, p: QPainter, s: float) -> None:
    def pt(x, y):
        return QPointF(x * s / 20, y * s / 20)

    def rect(x, y, w, h, r=1.5):
        p.drawRoundedRect(QRectF(pt(x, y), pt(x + w, y + h)), r * s / 20, r * s / 20)

    if name == "code":
        p.drawPolyline([pt(7, 5), pt(2.5, 10), pt(7, 15)])
        p.drawPolyline([pt(13, 5), pt(17.5, 10), pt(13, 15)])
    elif name == "ide":
        p.drawPolyline([pt(9, 4), pt(4, 4), pt(4, 16), pt(16, 16), pt(16, 11)])
        p.drawLine(pt(9.5, 10.5), pt(16, 4))
        p.drawPolyline([pt(11.5, 4), pt(16, 4), pt(16, 8.5)])
    elif name == "edit":
        path = QPainterPath(pt(4, 16))
        for x, y in [(4.5, 12.5), (13, 4), (16, 7), (7.5, 15.5), (4, 16)]:
            path.lineTo(pt(x, y))
        p.drawPath(path)
        p.drawLine(pt(11.5, 5.5), pt(14.5, 8.5))
    elif name == "image":
        rect(3, 4, 14, 12)
        p.drawPolyline([pt(3.5, 14), pt(8, 9.5), pt(11, 12.5), pt(13, 10.5), pt(16.5, 14)])
        p.drawEllipse(QRectF(pt(12, 6), pt(14, 8)))
    elif name == "save":
        p.drawLine(pt(10, 3), pt(10, 12.5))
        p.drawPolyline([pt(6, 9), pt(10, 13), pt(14, 9)])
        p.drawPolyline([pt(3.5, 13), pt(3.5, 16.5), pt(16.5, 16.5), pt(16.5, 13)])
    elif name == "close":
        p.drawLine(pt(5, 5), pt(15, 15))
        p.drawLine(pt(15, 5), pt(5, 15))


def icon(name: str, color: str = "#3c4043") -> QIcon:
    result = QIcon()
    for size in (20, 40):
        pix = QPixmap(size, size)
        pix.fill(Qt.transparent)
        p = QPainter(pix)
        p.setRenderHint(QPainter.Antialiasing)
        pen = QPen(QColor(color), 1.6 * size / 20)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        p.setPen(pen)
        _draw_icon(name, p, size)
        p.end()
        pix.setDevicePixelRatio(size / 20)
        result.addPixmap(pix)
    return result


def app_icon() -> QIcon:
    """The cell: four selection corners around a highlighter cursor block."""
    result = QIcon()
    for size in (16, 24, 32, 48, 64, 256):
        pix = QPixmap(size, size)
        pix.fill(Qt.transparent)
        p = QPainter(pix)
        p.setRenderHint(QPainter.Antialiasing)
        f = size / 256
        p.setPen(Qt.NoPen)
        p.setBrush(INK)
        p.drawRoundedRect(QRectF(0, 0, size, size), 56 * f, 56 * f)
        if size <= 16:
            # Corners vanish at this size; the cell alone stays recognizable.
            p.setBrush(HIGHLIGHT)
            p.drawRect(QRectF(96 * f, 56 * f, 64 * f, 144 * f))
        else:
            pen = QPen(PAPER, (18 if size >= 128 else 22 if size >= 48 else 28) * f)
            pen.setCapStyle(Qt.SquareCap)
            pen.setJoinStyle(Qt.MiterJoin)
            p.setPen(pen)
            a, b, c, d = (52, 96, 160, 204) if size >= 48 else (52, 100, 156, 204)
            for pts in ([(a, b), (a, a), (b, a)], [(c, a), (d, a), (d, b)],
                        [(a, c), (a, d), (b, d)], [(c, d), (d, d), (d, c)]):
                p.drawPolyline([QPointF(x * f, y * f) for x, y in pts])
            p.setPen(Qt.NoPen)
            p.setBrush(HIGHLIGHT)
            w, h = (40, 88) if size >= 128 else (44, 96) if size >= 48 else (52, 104)
            p.drawRect(QRectF((128 - w / 2) * f, (128 - h / 2) * f, w * f, h * f))
        p.end()
        result.addPixmap(pix)
    return result


# --------------------------------------------------------------------------
# Toast
# --------------------------------------------------------------------------

class Toast(QLabel):
    """Small, click-through confirmation in the bottom-right corner."""

    _current: "Toast | None" = None

    def __init__(self, text: str) -> None:
        super().__init__(text)
        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool | Qt.WindowTransparentForInput
        )
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setStyleSheet(
            "background: #202124; color: #ffffff; border-radius: 4px; padding: 9px 14px;"
            "font-family: 'Segoe UI'; font-size: 9pt;"
        )

    @classmethod
    def show_text(cls, text: str, ms: int = 1800) -> None:
        if cls._current is not None:
            cls._current.close()
        toast = cls(text)
        toast.adjustSize()
        area: QRect = QGuiApplication.primaryScreen().availableGeometry()
        toast.move(area.right() - toast.width() - 16, area.bottom() - toast.height() - 16)
        toast.show()
        QTimer.singleShot(ms, toast.close)
        cls._current = toast
        toast.destroyed.connect(lambda: setattr(cls, "_current", None) if cls._current is toast else None)

