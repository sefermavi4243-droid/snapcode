"""Lightshot-style region selector: frozen screen, frame, handles, small toolbar."""

from __future__ import annotations

from PySide6.QtCore import QObject, QPoint, QRect, QRectF, QRunnable, QSize, Qt, QThreadPool, QTimer, Signal
from PySide6.QtGui import QColor, QCursor, QFont, QGuiApplication, QImage, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QHBoxLayout, QLabel, QToolButton, QWidget

from .. import blocks
from .theme import ACCENT, icon

HANDLE = 6
MIN_SIZE = 6
_SHADE = QColor(0, 0, 0, 110)

TOOLBAR_STYLE = """
QWidget#toolbar { background: #ffffff; border: 1px solid #c4c7c5; border-radius: 3px; }
QToolButton { border: none; border-radius: 2px; padding: 4px; background: transparent; }
QToolButton:hover { background: #e8eaed; }
QLabel { color: #5f6368; font-family: 'Segoe UI'; font-size: 8pt; padding: 0 6px; }
"""


def qimage_to_pil(image: QImage):
    from PIL import Image

    image = image.convertToFormat(QImage.Format_RGBA8888)
    return Image.frombuffer(
        "RGBA", (image.width(), image.height()), bytes(image.constBits()), "raw", "RGBA",
        image.bytesPerLine(), 1,
    )


_RUNNING: set = set()  # keeps scan tasks alive if their overlay closes first


class _ScanSignals(QObject):
    done = Signal(list)


class _ScanTask(QRunnable):
    """OCRs the whole frozen screen once so hovering can outline text blocks."""

    def __init__(self, image: QImage, language: str) -> None:
        super().__init__()
        self.image, self.language = image, language
        self.signals = _ScanSignals()

    def run(self) -> None:
        try:
            from ..engines import windows_ocr

            lines = windows_ocr.scan(qimage_to_pil(self.image), self.language)
            found = blocks.find_blocks(lines)
        except Exception:
            found = []
        self.signals.done.emit(found)
        _RUNNING.discard(self)


class Overlay(QWidget):
    """One per screen. Emits physical-pixel crops; never does OCR itself."""

    settled = Signal(QImage, QRect)  # selection stopped changing: start OCR early
    action = Signal(str, QImage, QRect)  # copy | edit | save | image
    cancelled = Signal()

    def __init__(self, screen, last_rect: QRect | None, language: str) -> None:
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setMouseTracking(True)
        self.setCursor(Qt.CrossCursor)
        self._image = screen.grabWindow(0).toImage()
        self._ratio = self._image.width() / max(1, screen.geometry().width())
        self._sel = QRect()
        self._hover = QRect()
        self._blocks: list[QRect] = []
        self._last = last_rect
        self._drag_mode: str | None = None  # draw | move | handle name
        self._press = QPoint()
        self._press_sel = QRect()

        self.create()
        self.windowHandle().setScreen(screen)
        self.setGeometry(screen.geometry())
        self._build_toolbar()

        self._scan = _ScanTask(self._image, language)
        self._scan.setAutoDelete(False)
        self._scan.signals.done.connect(self._blocks_ready)
        _RUNNING.add(self._scan)
        QThreadPool.globalInstance().start(self._scan)

    # -- coordinates -------------------------------------------------------
    def _physical(self, rect: QRect) -> QRect:
        r = self._ratio
        return QRect(round(rect.x() * r), round(rect.y() * r), round(rect.width() * r), round(rect.height() * r))

    def _logical(self, x0: float, y0: float, x1: float, y1: float) -> QRect:
        r = self._ratio
        return QRect(QPoint(round(x0 / r), round(y0 / r)), QPoint(round(x1 / r), round(y1 / r))).intersected(self.rect())

    def _blocks_ready(self, rects: list) -> None:
        self._blocks = [self._logical(*r) for r in rects]
        self._update_hover(self.mapFromGlobal(QCursor.pos()))

    # -- toolbar -----------------------------------------------------------
    def _build_toolbar(self) -> None:
        bar = QWidget(self, objectName="toolbar")
        bar.setStyleSheet(TOOLBAR_STYLE)
        bar.setAttribute(Qt.WA_StyledBackground)
        bar.setCursor(Qt.ArrowCursor)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(3, 3, 3, 3)
        layout.setSpacing(1)
        self.info = QLabel("")
        layout.addWidget(self.info)
        for name, glyph, tip in [
            ("copy", "code", "Kodu kopyala (Ctrl+C, Enter, çift tık)"),
            ("ide", "ide", "IDE'de aç (Ctrl+O)"),
            ("edit", "edit", "Düzenle (Ctrl+E)"),
            ("save", "save", "Kodu dosyaya kaydet (Ctrl+S)"),
            ("image", "image", "Görüntüyü kopyala (Ctrl+Shift+C)"),
            ("close", "close", "Kapat (Esc)"),
        ]:
            button = QToolButton()
            button.setIcon(icon(glyph))
            button.setIconSize(QSize(18, 18))
            button.setToolTip(tip)
            button.clicked.connect(lambda _=False, n=name: self._trigger(n))
            if name == "ide":
                self.ide_button = button
            layout.addWidget(button)
        bar.hide()
        self.toolbar = bar

    def _place_toolbar(self) -> None:
        if self._sel.isNull() or self._drag_mode:
            self.toolbar.hide()
            return
        self.toolbar.adjustSize()
        w, h = self.toolbar.width(), self.toolbar.height()
        x = min(max(0, self._sel.right() - w + 1), self.width() - w)
        y = self._sel.bottom() + 6
        if y + h > self.height():
            y = self._sel.top() - h - 6
        if y < 0:
            y = self._sel.bottom() - h - 6
        self.toolbar.move(x, y)
        self.toolbar.show()
        self.toolbar.raise_()

    def set_info(self, text: str) -> None:
        self.info.setText(text)
        self.info.setVisible(bool(text))
        self._place_toolbar()

    # -- selection ---------------------------------------------------------
    def _crop(self) -> tuple[QImage, QRect]:
        phys = self._physical(self._sel)
        return self._image.copy(phys), phys

    def _set_selection(self, rect: QRect) -> None:
        self._sel = rect.normalized().intersected(self.rect())
        self._hover = QRect()
        self.set_info("")
        self._place_toolbar()
        self.update()
        if self._sel.width() >= MIN_SIZE and self._sel.height() >= MIN_SIZE:
            self.settled.emit(*self._crop())

    def _trigger(self, name: str) -> None:
        if name == "close":
            self.cancelled.emit()
        elif not self._sel.isNull():
            self.action.emit(name, *self._crop())

    def _handles(self) -> dict[str, QRect]:
        r, s = self._sel, HANDLE
        xs = {"l": r.left(), "c": r.center().x(), "r": r.right()}
        ys = {"t": r.top(), "m": r.center().y(), "b": r.bottom()}
        out = {}
        for yk, y in ys.items():
            for xk, x in xs.items():
                if xk + yk != "cm":
                    out[yk + xk] = QRect(x - s // 2, y - s // 2, s, s)
        return out

    def _hit(self, pos: QPoint) -> str | None:
        if self._sel.isNull():
            return None
        for name, rect in self._handles().items():
            if rect.adjusted(-4, -4, 4, 4).contains(pos):
                return name
        return "move" if self._sel.contains(pos) else None

    def _update_hover(self, pos: QPoint) -> None:
        if not self._sel.isNull() or self._drag_mode:
            return
        hits = [b for b in self._blocks if b.contains(pos)]
        hover = min(hits, key=lambda b: b.width() * b.height(), default=QRect())
        if hover != self._hover:
            self._hover = hover
            self.update()

    # -- mouse -------------------------------------------------------------
    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.RightButton:
            self.cancelled.emit()
            return
        if event.button() != Qt.LeftButton:
            return
        pos = event.position().toPoint()
        self._press, self._press_sel = pos, QRect(self._sel)
        self._drag_mode = self._hit(pos) or "draw"
        if self._drag_mode == "draw":
            self._sel = QRect()
        self._place_toolbar()

    def mouseMoveEvent(self, event) -> None:
        pos = event.position().toPoint()
        mode = self._drag_mode
        if mode is None:
            hit = self._hit(pos)
            cursors = {"tl": Qt.SizeFDiagCursor, "br": Qt.SizeFDiagCursor, "tr": Qt.SizeBDiagCursor,
                       "bl": Qt.SizeBDiagCursor, "tc": Qt.SizeVerCursor, "bc": Qt.SizeVerCursor,
                       "ml": Qt.SizeHorCursor, "mr": Qt.SizeHorCursor, "move": Qt.SizeAllCursor}
            self.setCursor(cursors.get(hit, Qt.CrossCursor))
            self._update_hover(pos)
            return
        if mode == "draw":
            self._sel = QRect(self._press, pos).normalized()
        elif mode == "move":
            moved = self._press_sel.translated(pos - self._press)
            moved.moveLeft(min(max(0, moved.left()), self.width() - moved.width()))
            moved.moveTop(min(max(0, moved.top()), self.height() - moved.height()))
            self._sel = moved
        else:
            r = QRect(self._press_sel)
            d = pos - self._press
            if "l" in mode[1]:
                r.setLeft(r.left() + d.x())
            if "r" in mode[1]:
                r.setRight(r.right() + d.x())
            if mode[0] == "t":
                r.setTop(r.top() + d.y())
            if mode[0] == "b":
                r.setBottom(r.bottom() + d.y())
            self._sel = r.normalized()
        self.update()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() != Qt.LeftButton or self._drag_mode is None:
            return
        mode, self._drag_mode = self._drag_mode, None
        pos = event.position().toPoint()
        tiny = (pos - self._press).manhattanLength() < 4
        if mode == "draw" and tiny:
            # A click selects the outlined block under the cursor.
            if not self._hover.isNull():
                self._set_selection(self._hover)
            else:
                self._sel = QRect()
                self.update()
            return
        if mode == "move" and tiny:
            self._place_toolbar()
            return
        if self._sel.width() < MIN_SIZE or self._sel.height() < MIN_SIZE:
            self._sel = QRect()
            self.update()
            return
        self._set_selection(self._sel)

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.LeftButton and self._sel.contains(event.position().toPoint()):
            self._trigger("copy")

    # -- keyboard ----------------------------------------------------------
    def keyPressEvent(self, event) -> None:
        key, mods = event.key(), event.modifiers()
        ctrl = bool(mods & Qt.ControlModifier)
        if key == Qt.Key_Escape:
            self.cancelled.emit()
        elif key in (Qt.Key_Return, Qt.Key_Enter) or (ctrl and key == Qt.Key_C and not mods & Qt.ShiftModifier):
            self._trigger("copy")
        elif ctrl and key == Qt.Key_C:
            self._trigger("image")
        elif ctrl and key == Qt.Key_O:
            self._trigger("ide")
        elif ctrl and key == Qt.Key_E:
            self._trigger("edit")
        elif ctrl and key == Qt.Key_S:
            self._trigger("save")
        elif ctrl and key == Qt.Key_A:
            self._set_selection(self.rect())
        elif key == Qt.Key_Space and self._last is not None:
            self._set_selection(self._last)
        elif key in (Qt.Key_Left, Qt.Key_Right, Qt.Key_Up, Qt.Key_Down) and not self._sel.isNull():
            dx = {Qt.Key_Left: -1, Qt.Key_Right: 1}.get(key, 0)
            dy = {Qt.Key_Up: -1, Qt.Key_Down: 1}.get(key, 0)
            r = QRect(self._sel)
            if mods & Qt.ShiftModifier:  # resize
                r.setRight(r.right() + dx)
                r.setBottom(r.bottom() + dy)
            else:
                r.translate(dx, dy)
            self._sel = r
            self._place_toolbar()
            self.update()
            self._nudge_timer().start()

    def _nudge_timer(self) -> QTimer:
        # Re-run OCR once the arrow keys stop, not on every press.
        if not hasattr(self, "_nudge"):
            self._nudge = QTimer(self, singleShot=True, interval=300)
            self._nudge.timeout.connect(lambda: self._set_selection(self._sel))
        return self._nudge

    @property
    def selection(self) -> QRect:
        return QRect(self._sel)

    # -- painting ----------------------------------------------------------
    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.drawImage(self.rect(), self._image)

        shade = QPainterPath()
        shade.addRect(QRectF(self.rect()))
        if not self._sel.isNull():
            hole = QPainterPath()
            hole.addRect(QRectF(self._sel))
            shade = shade.subtracted(hole)
        p.fillPath(shade, _SHADE)

        if not self._hover.isNull():
            pen = QPen(ACCENT, 1, Qt.DashLine)
            p.setPen(pen)
            p.drawRect(self._hover.adjusted(0, 0, -1, -1))

        if not self._sel.isNull():
            p.setPen(QPen(ACCENT, 1))
            p.setBrush(Qt.NoBrush)
            p.drawRect(self._sel.adjusted(0, 0, -1, -1))
            p.setBrush(ACCENT)
            p.setPen(QPen(Qt.white, 1))
            for rect in self._handles().values():
                p.drawRect(rect)
            phys = self._physical(self._sel)
            self._size_label(p, f"{phys.width()} × {phys.height()}")
        p.end()

    def _size_label(self, p: QPainter, text: str) -> None:
        p.setFont(QFont("Segoe UI", 8))
        w = p.fontMetrics().horizontalAdvance(text) + 10
        y = self._sel.top() - 20 if self._sel.top() >= 20 else self._sel.top() + 2
        box = QRect(self._sel.left(), y, w, 18)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0, 170))
        p.drawRect(box)
        p.setPen(Qt.white)
        p.drawText(box, Qt.AlignCenter, text)


class CaptureSession(QObject):
    """Opens an overlay on every screen and routes their signals."""

    settled = Signal(QImage, QRect)
    action = Signal(str, QImage, QRect)
    finished = Signal()

    def __init__(self, last: tuple[str, QRect] | None, language: str) -> None:
        super().__init__()
        self._last = last
        self._language = language
        self.overlays: list[Overlay] = []
        self.last_selection: tuple[str, QRect] | None = None
        self._closed = False

    def start(self) -> None:
        for screen in QGuiApplication.screens():
            last = self._last[1] if self._last and self._last[0] == screen.name() else None
            overlay = Overlay(screen, last, self._language)
            overlay.settled.connect(lambda img, rect, o=overlay: self._settled(o, img, rect))
            overlay.action.connect(lambda name, img, rect, o=overlay: self._action(o, name, img, rect))
            overlay.cancelled.connect(self.close)
            self.overlays.append(overlay)
            overlay.show()
        current = QGuiApplication.screenAt(QCursor.pos())
        for overlay in self.overlays:
            if overlay.windowHandle().screen() is current:
                overlay.activateWindow()
                overlay.raise_()

    def _settled(self, overlay: Overlay, image: QImage, rect: QRect) -> None:
        # Only one screen holds a selection at a time.
        for other in self.overlays:
            if other is not overlay and not other.selection.isNull():
                other._sel = QRect()
                other._place_toolbar()
                other.update()
        self.settled.emit(image, rect)

    def _action(self, overlay: Overlay, name: str, image: QImage, rect: QRect) -> None:
        self.last_selection = (overlay.windowHandle().screen().name(), overlay.selection)
        self.close()
        self.action.emit(name, image, rect)

    def set_ide_name(self, name: str) -> None:
        for overlay in self.overlays:
            overlay.ide_button.setToolTip(f"{name} içinde aç (Ctrl+O)")

    def set_info(self, text: str) -> None:
        for overlay in self.overlays:
            if not overlay.selection.isNull():
                overlay.set_info(text)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        for overlay in self.overlays:
            overlay.close()
        self.overlays.clear()
        self.finished.emit()
