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

ACCENT = QColor("#1a73e8")

# Brand palette (CodeLift, "Lo-fi"): dusk purple, lavender, peach, cream
# and sage, the soft colours of a late-night study stream.
DUSK = QColor("#2E2A47")
LAVENDER = QColor("#9B8AD9")
PEACH = QColor("#F6B99A")
CREAM = QColor("#FBF3E8")
SAGE = QColor("#7FB5A6")
MIST = QColor("#B8B0C8")
CORAL = QColor("#F09A7E")

STYLESHEET = """
QWidget { font-family: 'Segoe UI'; font-size: 9pt; color: #2E2A47; }
QDialog, QMainWindow, QWidget#root { background: #FBF7F1; }
QPlainTextEdit {
    background: #FFFCF8; border: none; padding: 12px;
    font-family: 'Cascadia Mono', 'Consolas'; font-size: 10.5pt;
    selection-background-color: #E2D9F3; selection-color: #2E2A47;
}
QListWidget { border: none; border-right: 1px solid #EADFCF; background: #F6EFE4; outline: none; }
QListWidget::item { padding: 8px 10px; border-radius: 6px; margin: 2px 6px; }
QListWidget::item:hover { background: #F0E6D8; }
QListWidget::item:selected { background: #E9E1F7; color: #2E2A47; }
QLineEdit, QComboBox {
    border: 1px solid #E3D6C4; border-radius: 6px; padding: 4px 8px; background: #FFFCF8;
}
QLineEdit:focus, QComboBox:focus { border-color: #9B8AD9; }
QComboBox::drop-down { border: none; width: 22px; }
QComboBox::down-arrow { image: url(@CHEVRON@); width: 10px; height: 10px; }
QComboBox QAbstractItemView {
    background: #FFFCF8; border: 1px solid #E3D6C4; selection-background-color: #EFE9F8;
    selection-color: #2E2A47; outline: none;
}
QPushButton {
    background: #FFFCF8; border: 1px solid #E3D6C4; border-radius: 6px; padding: 5px 14px;
}
QPushButton:hover { background: #F3EADF; }
QPushButton:pressed { background: #EADFCF; }
QToolButton {
    background: #FFFCF8; border: 1px solid #E3D6C4; border-radius: 6px; padding: 5px 12px;
}
QToolButton:hover { background: #F3EADF; }
QToolButton[popupMode="1"] { padding-right: 26px; }
QToolButton::menu-button { border: none; border-left: 1px solid #E3D6C4; width: 22px; }
QToolButton::menu-arrow { image: url(@CHEVRON@); width: 10px; height: 10px; }
QPushButton#primary { background: #9B8AD9; border-color: #9B8AD9; color: #FFFFFF; font-weight: 600; }
QPushButton#primary:hover { background: #8C7BCB; border-color: #8C7BCB; }
QPushButton#primary:pressed { background: #7E6DBE; }
QWidget#bar { background: #F6EFE4; border-top: 1px solid #EADFCF; }
QLabel#muted { color: #8A829C; }
QMenu { background: #FFFCF8; border: 1px solid #E3D6C4; border-radius: 8px; padding: 6px; }
QMenu::item { padding: 6px 24px 6px 16px; border-radius: 5px; }
QMenu::item:selected { background: #EFE9F8; color: #2E2A47; }
QMenu::separator { height: 1px; background: #EADFCF; margin: 5px 8px; }
QToolTip { background: #2E2A47; color: #FBF3E8; border: none; padding: 5px 8px; }
"""

# Lo-fi light palette: berry keywords, lavender functions, sage strings,
# peach numbers and dusty comments, all readable on cream.
_PALETTE = {
    Keyword: ("#B5507E", False),
    Name.Function: ("#6E5BC4", False),
    Name.Class: ("#A0603A", False),
    Name.Builtin: ("#3F7FA8", False),
    Name.Decorator: ("#6E5BC4", False),
    Name.Tag: ("#4E8A6F", False),
    Name.Attribute: ("#3F7FA8", False),
    Name.Exception: ("#A0603A", False),
    String: ("#4E8A6F", False),
    Number: ("#C2703D", False),
    Comment: ("#A79FB8", True),
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
    pen = QPen(DUSK, 4.5)
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
    """The cell: four selection corners around a highlighter cursor block."""
    result = QIcon()
    for size in (16, 24, 32, 48, 64, 256):
        pix = QPixmap(size, size)
        pix.fill(Qt.transparent)
        p = QPainter(pix)
        p.setRenderHint(QPainter.Antialiasing)
        f = size / 256
        # A sunset tile: peach fading into lavender.
        sky = QLinearGradient(0, 0, 0, size)
        sky.setColorAt(0, PEACH)
        sky.setColorAt(1, LAVENDER)
        p.setPen(Qt.NoPen)
        p.setBrush(sky)
        p.drawRoundedRect(QRectF(0, 0, size, size), 56 * f, 56 * f)
        if size <= 16:
            # Corners vanish at this size; the cell alone stays recognizable.
            p.setBrush(DUSK)
            p.drawRect(QRectF(96 * f, 56 * f, 64 * f, 144 * f))
        else:
            pen = QPen(CREAM, (18 if size >= 128 else 22 if size >= 48 else 28) * f)
            pen.setCapStyle(Qt.SquareCap)
            pen.setJoinStyle(Qt.MiterJoin)
            p.setPen(pen)
            a, b, c, d = (52, 96, 160, 204) if size >= 48 else (52, 100, 156, 204)
            for pts in ([(a, b), (a, a), (b, a)], [(c, a), (d, a), (d, b)],
                        [(a, c), (a, d), (b, d)], [(c, d), (d, d), (d, c)]):
                p.drawPolyline([QPointF(x * f, y * f) for x, y in pts])
            p.setPen(Qt.NoPen)
            p.setBrush(DUSK)
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
            "background: #2E2A47; color: #FBF3E8; border-radius: 8px; padding: 10px 16px;"
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

