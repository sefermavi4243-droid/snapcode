"""Code editor shown for the "edit" action.

The captured screenshot sits right above the recognized code, so a character
OCR got wrong can be spotted and fixed by looking up instead of switching
windows.
"""

from __future__ import annotations

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import QColor, QGuiApplication, QKeySequence, QPainter, QPixmap, QShortcut, QTextFormat
from PySide6.QtWidgets import (
    QComboBox, QFileDialog, QHBoxLayout, QLabel, QMenu, QPlainTextEdit, QPushButton,
    QScrollArea, QSplitter, QTextEdit, QToolButton, QVBoxLayout, QWidget,
)

from .. import ide, languages
from ..config import APP_NAME
from ..i18n import t
from ..pipeline import Recognition
from .theme import PAPER, INK, CodeHighlighter, Toast, app_icon, icon

EDITOR_STYLE = """
QWidget#header { background: #F8F6F3; border-bottom: 1px solid #E6E1DA; }
QLabel#meta { color: #7C8294; font-size: 8.5pt; }
QComboBox#chip {
    background: #FFEDE4; border: 1px solid #FFD9C7; border-radius: 11px; padding: 2px 10px;
    font-family: 'Segoe UI'; font-weight: 600; font-size: 8.5pt; min-height: 18px;
}
QComboBox#chip:hover { background: #FFE2D4; }
QToolButton#toggle {
    background: transparent; border: 1px solid #DED8CF; border-radius: 11px; padding: 2px 10px 2px 7px;
    font-size: 8.5pt; color: #4A5063;
}
QToolButton#toggle:hover { background: #EFEBE6; }
QToolButton#toggle:checked { background: #FFEDE4; border-color: #FFC9AE; color: #1E2230; }
QScrollArea#shot { background: #1E2230; border: none; }
QScrollArea#shot > QWidget > QWidget { background: #1E2230; }
QSplitter::handle { background: #E6E1DA; }
QSplitter::handle:hover { background: #FF6B35; }
QLabel#hint { color: #9AA0AE; font-size: 8pt; }
"""


def save_code(parent, code: str, language: languages.Language) -> bool:
    path, _ = QFileDialog.getSaveFileName(
        parent, t("Kodu kaydet"), f"snippet{language.extension}",
        f"{t(language.name)} (*{language.extension});;" + t("Tüm dosyalar (*)"),
    )
    if not path:
        return False
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(code)
    return True


# --------------------------------------------------------------------------
# Code view with a line-number gutter and current-line highlight
# --------------------------------------------------------------------------

class _Gutter(QWidget):
    def __init__(self, editor: "CodeView") -> None:
        super().__init__(editor)
        self.editor = editor

    def sizeHint(self) -> QSize:
        return QSize(self.editor.gutter_width(), 0)

    def paintEvent(self, event) -> None:
        self.editor.paint_gutter(event)


class CodeView(QPlainTextEdit):
    def __init__(self) -> None:
        super().__init__()
        self.gutter = _Gutter(self)
        self.blockCountChanged.connect(self._update_margins)
        self.updateRequest.connect(self._scroll_gutter)
        self.cursorPositionChanged.connect(self._highlight_line)
        self._update_margins()
        self._highlight_line()

    def gutter_width(self) -> int:
        digits = max(2, len(str(self.blockCount())))
        return 26 + self.fontMetrics().horizontalAdvance("9") * digits

    def _update_margins(self) -> None:
        self.setViewportMargins(self.gutter_width(), 0, 0, 0)

    def _scroll_gutter(self, rect: QRect, dy: int) -> None:
        if dy:
            self.gutter.scroll(0, dy)
        else:
            self.gutter.update(0, rect.y(), self.gutter.width(), rect.height())

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        r = self.contentsRect()
        self.gutter.setGeometry(QRect(r.left(), r.top(), self.gutter_width(), r.height()))

    def paint_gutter(self, event) -> None:
        p = QPainter(self.gutter)
        p.fillRect(event.rect(), QColor("#F2EFEB"))
        p.setFont(self.font())
        current = self.textCursor().blockNumber()
        block = self.firstVisibleBlock()
        offset = self.contentOffset()
        while block.isValid():
            geometry = self.blockBoundingGeometry(block).translated(offset)
            if geometry.top() > event.rect().bottom():
                break
            if block.isVisible():
                n = block.blockNumber()
                p.setPen(QColor("#C2531E") if n == current else QColor("#B3B8C4"))
                p.drawText(QRect(0, round(geometry.top()), self.gutter.width() - 12, round(geometry.height())),
                           Qt.AlignRight | Qt.AlignVCenter, str(n + 1))
            block = block.next()
        p.end()

    def _highlight_line(self) -> None:
        line = QTextEdit.ExtraSelection()
        line.format.setBackground(QColor("#FFF3EC"))
        line.format.setProperty(QTextFormat.FullWidthSelection, True)
        line.cursor = self.textCursor()
        line.cursor.clearSelection()
        self.setExtraSelections([line])
        self.gutter.update()


# --------------------------------------------------------------------------
# Window
# --------------------------------------------------------------------------

class EditorWindow(QWidget):
    def __init__(self, result: Recognition, on_edit=None, on_send=None, image: bytes | None = None) -> None:
        super().__init__()
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(app_icon())
        self.setObjectName("root")
        self.setStyleSheet(EDITOR_STYLE)
        self.snippet_id: int | None = None
        self._on_edit = on_edit
        self._on_send = on_send

        self.editor = CodeView()
        self.editor.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.editor.setTabStopDistance(self.editor.fontMetrics().horizontalAdvance(" ") * 4)
        self.highlighter = CodeHighlighter(self.editor.document(), result.language.lexer)
        # No phantom empty last line in the gutter; copying adds the newline back.
        self.editor.setPlainText(result.code.rstrip("\n"))
        self.editor.textChanged.connect(self._changed)

        # -- header: language chip, size, how it was read, screenshot toggle
        header = QWidget(objectName="header")
        top = QHBoxLayout(header)
        top.setContentsMargins(14, 9, 12, 9)
        top.setSpacing(10)
        self.lang = QComboBox(objectName="chip")
        for lang in languages.LANGUAGES.values():
            self.lang.addItem(t(lang.name), lang.key)
        self.lang.setCurrentIndex(max(0, self.lang.findData(result.language.key)))
        self.lang.currentIndexChanged.connect(self._language_changed)
        top.addWidget(self.lang)
        self.lines = QLabel(objectName="meta")
        top.addWidget(self.lines)
        engine = {"windows": "Windows OCR", "claude": "Claude"}.get(result.engine, result.engine)
        top.addWidget(QLabel(f"·   {engine} · {result.elapsed_ms} ms", objectName="meta"))
        top.addStretch()

        # -- the screenshot above the code
        self.shot = None
        pix = QPixmap()
        if image and pix.loadFromData(image):
            label = QLabel()
            label.setPixmap(pix)
            label.setAlignment(Qt.AlignCenter)
            self.shot = QScrollArea(objectName="shot")
            self.shot.setWidget(label)
            self.shot.setWidgetResizable(True)
            self.shot.setAlignment(Qt.AlignCenter)
            toggle = QToolButton(objectName="toggle", checkable=True, checked=True)
            toggle.setText(t("Görüntü"))
            toggle.setIcon(icon("image", INK.name()))
            toggle.setIconSize(QSize(14, 14))
            toggle.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
            toggle.setCursor(Qt.PointingHandCursor)
            toggle.setToolTip(t("Yakalanan görüntüyü kodun üstünde göster (Ctrl+G)"))
            toggle.toggled.connect(self.shot.setVisible)
            top.addWidget(toggle)
            QShortcut(QKeySequence("Ctrl+G"), self, activated=toggle.toggle)

        body = QSplitter(Qt.Vertical)
        body.setHandleWidth(3)
        body.setChildrenCollapsible(False)
        if self.shot is not None:
            body.addWidget(self.shot)
        body.addWidget(self.editor)

        # -- footer: keyboard hint and actions
        bar = QWidget(objectName="bar")
        row = QHBoxLayout(bar)
        row.setContentsMargins(14, 9, 12, 9)
        row.setSpacing(8)
        row.addWidget(QLabel(t("Ctrl+Enter kopyala · Ctrl+S kaydet · Esc kapat"), objectName="hint"))
        row.addStretch()
        save = QPushButton(icon("save", INK.name()), t("Kaydet"))
        save.clicked.connect(self.save)
        copy = QPushButton(icon("code", PAPER.name()), t("Kopyala"), objectName="primary")
        copy.setDefault(True)
        copy.clicked.connect(self.copy_and_close)
        row.addWidget(save)
        if on_send:
            row.addWidget(self._ide_button())
        row.addWidget(copy)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(header)
        layout.addWidget(body, 1)
        layout.addWidget(bar)

        code_lines = result.code.splitlines() or [""]
        metrics = self.editor.fontMetrics()
        code_w = max(metrics.horizontalAdvance(line) for line in code_lines) + self.editor.gutter_width() + 60
        code_h = metrics.lineSpacing() * len(code_lines) + 40
        shot_w = pix.width() + 24 if self.shot is not None else 0
        shot_h = min(pix.height() + 16, 320) if self.shot is not None else 0
        self.resize(min(max(code_w, shot_w, 640), 1200), min(max(code_h + shot_h + 110, 320), 860))
        if self.shot is not None:
            body.setSizes([shot_h, max(code_h, 160)])
        self._update_lines()

        QShortcut(QKeySequence("Ctrl+Return"), self, activated=self.copy_and_close)
        QShortcut(QKeySequence("Ctrl+S"), self, activated=self.save)
        QShortcut(QKeySequence("Escape"), self, activated=self.close)

    def _ide_button(self) -> QToolButton:
        """Click: default IDE. Arrow: pick any detected editor."""
        button = QToolButton()
        button.setText(t("IDE'de aç"))
        button.setIcon(icon("ide", INK.name()))
        button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        button.setPopupMode(QToolButton.MenuButtonPopup)
        button.clicked.connect(lambda: self.send(None))
        menu = QMenu(button)
        for target in ide.detect():
            menu.addAction(target.name, lambda key=target.key: self.send(key))
        button.setMenu(menu)
        return button

    def _update_lines(self) -> None:
        self.lines.setText(t("{n} satır", n=self.editor.blockCount()))

    def send(self, ide_key: str | None) -> None:
        self._on_send(self.code, self.language, ide_key)
        self.close()

    @property
    def code(self) -> str:
        return self.editor.toPlainText().rstrip("\n") + "\n"

    @property
    def language(self) -> languages.Language:
        return languages.by_key(self.lang.currentData())

    def _language_changed(self) -> None:
        self.highlighter.set_language(self.language.lexer)
        self._changed()

    def _changed(self) -> None:
        self._update_lines()
        if self._on_edit and self.snippet_id is not None:
            self._on_edit(self.snippet_id, self.code, self.language.key)

    def copy_and_close(self) -> None:
        QGuiApplication.clipboard().setText(self.code)
        Toast.show_text(t("Kod kopyalandı"))
        self.close()

    def save(self) -> None:
        if save_code(self, self.code, self.language):
            Toast.show_text(t("Kaydedildi"))
