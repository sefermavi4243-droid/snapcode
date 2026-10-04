"""Frozen-screen region selector with a pixel loupe, one overlay per monitor."""

from __future__ import annotations

from PySide6.QtCore import QObject, QPoint, QRect, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QCursor, QFont, QGuiApplication, QImage, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

ACCENT = QColor("#4f9dff")
LOUPE_SIZE = 132
LOUPE_PIXELS = 11


class ScreenOverlay(QWidget):
    selected = Signal(QImage)
    cancelled = Signal()

    def __init__(self, screen) -> None:
        super().__init__(
            None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
        )
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setCursor(Qt.CrossCursor)
        self.setMouseTracking(True)
        self._shot = screen.grabWindow(0)
        self._image = self._shot.toImage()
        self._ratio = self._shot.width() / max(1, screen.geometry().width())
        self._origin: QPoint | None = None
        self._current: QPoint | None = None
        self._mouse = QPoint(-1, -1)
        self.create()
        self.windowHandle().setScreen(screen)
        self.setGeometry(screen.geometry())

    # -- geometry ----------------------------------------------------------
    def _selection(self) -> QRect:
        if self._origin is None or self._current is None:
            return QRect()
        return QRect(self._origin, self._current).normalized()

    def _physical(self, rect: QRect) -> QRect:
        r = self._ratio
        return QRect(round(rect.x() * r), round(rect.y() * r), round(rect.width() * r), round(rect.height() * r))

    # -- events ------------------------------------------------------------
    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.RightButton:
            self.cancelled.emit()
            return
        self._origin = self._current = event.position().toPoint()
        self.update()

    def mouseMoveEvent(self, event) -> None:
        self._mouse = event.position().toPoint()
        if self._origin is not None:
            self._current = self._mouse
        self.update()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() != Qt.LeftButton or self._origin is None:
            return
        rect = self._selection()
        if rect.width() < 6 or rect.height() < 6:
            self._origin = self._current = None
            self.update()
            return
        self.selected.emit(self._image.copy(self._physical(rect)))

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key_Escape:
            self.cancelled.emit()
        elif event.key() in (Qt.Key_Return, Qt.Key_Enter):
            self.selected.emit(self._image)

    # -- painting ----------------------------------------------------------
    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.drawPixmap(self.rect(), self._shot)

        shade = QPainterPath()
        shade.addRect(QRectF(self.rect()))
        sel = self._selection()
        if not sel.isNull():
            hole = QPainterPath()
            hole.addRect(QRectF(sel))
            shade = shade.subtracted(hole)
        p.fillPath(shade, QColor(8, 12, 20, 150))

        if not sel.isNull():
            p.setPen(QPen(ACCENT, 2))
            p.drawRect(sel.adjusted(0, 0, -1, -1))
            phys = self._physical(sel)
            self._label(p, f"{phys.width()} × {phys.height()}", sel.topLeft() + QPoint(0, -30))
        else:
            self._hint(p)

        if self.rect().contains(self._mouse):
            self._loupe(p)
        p.end()

    def _label(self, p: QPainter, text: str, at: QPoint) -> None:
        p.setFont(QFont("Segoe UI", 9, QFont.DemiBold))
        width = p.fontMetrics().horizontalAdvance(text) + 16
        box = QRect(at.x(), max(4, at.y()), width, 24)
        p.setPen(Qt.NoPen)
        p.setBrush(ACCENT)
        p.drawRoundedRect(box, 6, 6)
        p.setPen(Qt.white)
        p.drawText(box, Qt.AlignCenter, text)

    def _hint(self, p: QPainter) -> None:
        text = "Kodu seçmek için sürükle   ·   Enter: tüm ekran   ·   Esc / sağ tık: iptal"
        p.setFont(QFont("Segoe UI", 11))
        width = p.fontMetrics().horizontalAdvance(text) + 40
        box = QRect((self.width() - width) // 2, 28, width, 40)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(15, 20, 30, 220))
        p.drawRoundedRect(box, 10, 10)
        p.setPen(QColor("#e6edf3"))
        p.drawText(box, Qt.AlignCenter, text)

    def _loupe(self, p: QPainter) -> None:
        center = self._physical(QRect(self._mouse, self._mouse)).topLeft()
        half = LOUPE_PIXELS // 2
        source = QRect(center.x() - half, center.y() - half, LOUPE_PIXELS, LOUPE_PIXELS)
        pos = self._mouse + QPoint(24, 24)
        if pos.x() + LOUPE_SIZE > self.width():
            pos.setX(self._mouse.x() - 24 - LOUPE_SIZE)
        if pos.y() + LOUPE_SIZE + 26 > self.height():
            pos.setY(self._mouse.y() - 24 - LOUPE_SIZE - 26)
        target = QRect(pos, pos + QPoint(LOUPE_SIZE, LOUPE_SIZE))

        p.save()
        clip = QPainterPath()
        clip.addRoundedRect(QRectF(target), 12, 12)
        p.setClipPath(clip)
        p.setRenderHint(QPainter.SmoothPixmapTransform, False)
        p.drawPixmap(target, self._shot, source)
        cell = LOUPE_SIZE / LOUPE_PIXELS
        p.setPen(QPen(QColor(79, 157, 255, 200), 1))
        p.drawRect(QRectF(target.x() + half * cell, target.y() + half * cell, cell, cell))
        p.restore()
        p.setPen(QPen(ACCENT, 2))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(target, 12, 12)

        color = self._image.pixelColor(center) if self._image.rect().contains(center) else QColor()
        self._label(p, f"{color.name().upper()}  {center.x()},{center.y()}", target.bottomLeft() + QPoint(0, 4))


class CaptureSession(QObject):
    """Shows an overlay on every screen; finishes with the selected image or None."""

    finished = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self._overlays: list[ScreenOverlay] = []
        self._done = False

    def start(self, delay_ms: int = 180) -> None:
        # Give menus and our own windows time to disappear before grabbing.
        QTimer.singleShot(delay_ms, self._open)

    def _open(self) -> None:
        for screen in QGuiApplication.screens():
            overlay = ScreenOverlay(screen)
            overlay.selected.connect(self._finish)
            overlay.cancelled.connect(lambda: self._finish(None))
            self._overlays.append(overlay)
            overlay.show()
        cursor_screen = QGuiApplication.screenAt(QCursor.pos())
        for overlay in self._overlays:
            if overlay.windowHandle().screen() is cursor_screen:
                overlay.activateWindow()
                overlay.raise_()

    def _finish(self, image: QImage | None) -> None:
        if self._done:
            return
        self._done = True
        for overlay in self._overlays:
            overlay.close()
        self._overlays.clear()
        self.finished.emit(image)
