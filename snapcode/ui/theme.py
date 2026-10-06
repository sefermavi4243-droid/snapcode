"""Styling, syntax highlighting, icons and the toast notification."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRect, QRectF, Qt, QTimer
from PySide6.QtGui import (
    QColor, QFontDatabase, QGuiApplication, QIcon, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap,
    QSyntaxHighlighter, QTextCharFormat,
)
from PySide6.QtWidgets import QLabel
from pygments.lexers import get_lexer_by_name
from pygments.token import Comment, Keyword, Name, Number, String, Token
from pygments.util import ClassNotFound

# Brand palette (Pluck, "Ink & Tangerine"): a ripe tangerine accent on warm
# paper, ink for text, mint for success.
INK = QColor("#1E2230")
TANGERINE = QColor("#FF6B35")
APRICOT = QColor("#FFB38A")
PAPER = QColor("#FFF8F3")
MINT = QColor("#5BB89A")
SLATE = QColor("#A9AEBB")
CORAL = QColor("#E5534B")
ACCENT = TANGERINE

STYLESHEET = """
QWidget { font-family: 'Segoe UI'; font-size: 9pt; color: #1E2230; }
QDialog, QMainWindow, QWidget#root { background: #F8F6F3; }
QPlainTextEdit {
    background: #FFFDFB; border: none; padding: 12px;
    font-family: 'Cascadia Mono', 'Consolas'; font-size: 10.5pt;
    selection-background-color: #FFD9C7; selection-color: #1E2230;
}
QListWidget { border: none; border-right: 1px solid #E6E1DA; background: #F2EFEB; outline: none; }
QListWidget::item { padding: 8px 10px; border-radius: 6px; margin: 2px 6px; }
QListWidget::item:hover { background: #EEEAE4; }
QListWidget::item:selected { background: #FFE6DA; color: #1E2230; }
QLineEdit, QComboBox {
    border: 1px solid #DED8CF; border-radius: 6px; padding: 4px 8px; background: #FFFDFB;
}
QLineEdit:focus, QComboBox:focus { border-color: #FF6B35; }
QComboBox::drop-down { border: none; width: 22px; }
QComboBox::down-arrow { image: url(@CHEVRON@); width: 10px; height: 10px; }
QComboBox QAbstractItemView {
    background: #FFFDFB; border: 1px solid #DED8CF; selection-background-color: #FFEDE4;
    selection-color: #1E2230; outline: none;
}
QPushButton {
    background: #FFFDFB; border: 1px solid #DED8CF; border-radius: 6px; padding: 5px 14px;
}
QPushButton:hover { background: #EFEBE6; }
QPushButton:pressed { background: #E6E1DA; }
QToolButton {
    background: #FFFDFB; border: 1px solid #DED8CF; border-radius: 6px; padding: 5px 12px;
}
QToolButton:hover { background: #EFEBE6; }
QToolButton[popupMode="1"] { padding-right: 26px; }
QToolButton::menu-button { border: none; border-left: 1px solid #DED8CF; width: 22px; }
QToolButton::menu-arrow { image: url(@CHEVRON@); width: 10px; height: 10px; }
QPushButton#primary { background: #FF6B35; border-color: #FF6B35; color: #FFFFFF; font-weight: 600; }
QPushButton#primary:hover { background: #EE5A24; border-color: #EE5A24; }
QPushButton#primary:pressed { background: #D94E1C; }
QWidget#bar { background: #F2EFEB; border-top: 1px solid #E6E1DA; }
QLabel#muted { color: #7C8294; }
QMenu { background: #FFFDFB; border: 1px solid #DED8CF; border-radius: 8px; padding: 6px; }
QMenu::item { padding: 6px 24px 6px 16px; border-radius: 5px; }
QMenu::item:selected { background: #FFEDE4; color: #1E2230; }
QMenu::separator { height: 1px; background: #E6E1DA; margin: 5px 8px; }
QToolTip { background: #1E2230; color: #FFF8F3; border: none; padding: 5px 8px; }
"""

# Light palette: berry keywords, tangerine functions, green strings, plum
# numbers and slate comments, all readable on paper.
_PALETTE = {
    Keyword: ("#B23A6E", False),
    Name.Function: ("#C2531E", False),
    Name.Class: ("#8A5A16", False),
    Name.Builtin: ("#3F7FA8", False),
    Name.Decorator: ("#C2531E", False),
    Name.Tag: ("#4E8A6F", False),
    Name.Attribute: ("#3F7FA8", False),
    Name.Exception: ("#8A5A16", False),
    String: ("#4E8A6F", False),
    Number: ("#8E5CB8", False),
    Comment: ("#9AA0AE", True),
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


def stylesheet() -> str:
    """The app stylesheet, with its drop-down chevron rendered to a file.

    Qt style sheets can only take images from files, so the chevron is drawn
    once into the data folder and referenced from there.
    """
    from ..config import data_dir

    path = data_dir() / "chevron.png"
    pix = QPixmap(40, 40)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    pen = QPen(INK, 4.5)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    p.setPen(pen)
    p.drawPolyline([QPointF(10, 15), QPointF(20, 25), QPointF(30, 15)])
    p.end()
    pix.save(str(path))
    return STYLESHEET.replace("@CHEVRON@", path.as_posix())


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
        # An editor window with a title bar and code inside.
        rect(2.5, 3.5, 15, 13, 2.5)
        p.drawLine(pt(2.5, 7), pt(17.5, 7))
        p.drawPolyline([pt(7.5, 9.5), pt(5.5, 11.75), pt(7.5, 14)])
        p.drawPolyline([pt(12.5, 9.5), pt(14.5, 11.75), pt(12.5, 14)])
        p.drawLine(pt(10.8, 9.5), pt(9.2, 14))
    elif name == "edit":
        # A pencil writing on a line.
        path = QPainterPath(pt(3.5, 14.5))
        for x, y in [(4.2, 11.6), (11.8, 4), (14.6, 6.8), (7, 14.4), (3.5, 14.5)]:
            path.lineTo(pt(x, y))
        p.drawPath(path)
        p.drawLine(pt(10.3, 5.5), pt(13.1, 8.3))
        p.drawLine(pt(10.5, 16.5), pt(16.5, 16.5))
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
    """The fruit: code brackets on a tangerine tile, a leaf where it was plucked."""
    result = QIcon()
    for size in (16, 24, 32, 48, 64, 256):
        pix = QPixmap(size, size)
        pix.fill(Qt.transparent)
        p = QPainter(pix)
        p.setRenderHint(QPainter.Antialiasing)
        f = size / 256

        def pt(x, y):
            return QPointF(x * f, y * f)

        skin = QLinearGradient(0, 0, 0, size)
        skin.setColorAt(0, APRICOT)
        skin.setColorAt(1, TANGERINE)
        p.setPen(Qt.NoPen)
        p.setBrush(skin)
        p.drawRoundedRect(QRectF(0, 0, size, size), 60 * f, 60 * f)
        # Small sizes drop the leaf and thicken the brackets so they stay legible.
        small = size <= 24
        pen = QPen(PAPER, (32 if small else 26 if size < 64 else 22) * f)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        p.setPen(pen)
        top, mid, bottom = (60, 128, 196) if small else (104, 150, 196)
        inner, outer = (100, 44) if small else (108, 52)
        p.drawPolyline([pt(inner, top), pt(outer, mid), pt(inner, bottom)])
        p.drawPolyline([pt(256 - inner, top), pt(256 - outer, mid), pt(256 - inner, bottom)])
        if not small:
            stem = QPen(INK, 12 * f)
            stem.setCapStyle(Qt.RoundCap)
            p.setPen(stem)
            p.drawLine(pt(128, 92), pt(128, 54))
            leaf = QPainterPath(pt(128, 62))
            leaf.cubicTo(pt(142, 30), pt(178, 26), pt(196, 40))
            leaf.cubicTo(pt(178, 68), pt(146, 74), pt(128, 62))
            p.setPen(Qt.NoPen)
            p.setBrush(MINT)
            p.drawPath(leaf)
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
            "background: #1E2230; color: #FFF8F3; border-radius: 8px; padding: 10px 16px;"
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

