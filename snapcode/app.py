"""Tray application: hotkey -> select -> code on the clipboard."""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QBuffer, QLockFile, QObject, QRect, QRunnable, QThreadPool, QTimer, Signal
from PySide6.QtGui import QAction, QGuiApplication, QImage
from PySide6.QtWidgets import QApplication, QFileDialog, QMenu, QMessageBox, QSystemTrayIcon

from . import __version__, pipeline
from .config import Settings, data_dir
from .history import History
from .hotkey import HotkeyListener
from .ui.capture import CaptureSession
from .ui.editor import EditorWindow, save_code
from .ui.history_window import HistoryWindow
from .ui.settings_dialog import SettingsDialog
from .ui.theme import STYLESHEET, Toast, app_icon


def image_to_png(image: QImage) -> bytes:
    buffer = QBuffer()
    buffer.open(QBuffer.WriteOnly)
    image.save(buffer, "PNG")
    return bytes(buffer.data())


def image_key(image: QImage) -> str:
    return hashlib.blake2b(bytes(image.constBits()), digest_size=16).hexdigest()


class _TaskSignals(QObject):
    done = Signal(object)
    failed = Signal(str)


class RecognizeTask(QRunnable):
    def __init__(self, png: bytes, settings: Settings) -> None:
        super().__init__()
        self.png, self.settings = png, settings
        self.signals = _TaskSignals()

    def run(self) -> None:
        try:
            self.signals.done.emit(pipeline.recognize(self.png, self.settings))
        except Exception as exc:  # shown to the user, never crash the tray
            self.signals.failed.emit(str(exc) or exc.__class__.__name__)


class Job:
    """One OCR run. Callbacks wait for it; it may finish before anyone asks."""

    def __init__(self, png: bytes) -> None:
        self.png = png
        self.result: pipeline.Recognition | None = None
        self.error: str | None = None
        self.waiters: list[Callable[["Job"], None]] = []

    @property
    def finished(self) -> bool:
        return self.result is not None or self.error is not None

    def then(self, callback: Callable[["Job"], None]) -> None:
        if self.finished:
            callback(self)
        else:
            self.waiters.append(callback)


class SnapCodeApp(QObject):
    def __init__(self, app: QApplication) -> None:
        super().__init__()
        self.app = app
        self.settings = Settings.load()
        self.history = History()
        self.pool = QThreadPool.globalInstance()
        self._tasks: set[RecognizeTask] = set()
        self._jobs: dict[str, Job] = {}
        self._session: CaptureSession | None = None
        self._last_region: tuple[str, QRect] | None = None
        self._editors: set[EditorWindow] = set()
        self._history_window: HistoryWindow | None = None
        self._last_clip = None
        self._hotkeys: HotkeyListener | None = None

        self.tray = QSystemTrayIcon(app_icon(), self)
        self.tray.activated.connect(self._tray_activated)
        self._build_menu()
        self.tray.show()

        QGuiApplication.clipboard().dataChanged.connect(self._clipboard_changed)
        self._start_hotkeys()
        Toast.show_text(f"SnapCode çalışıyor · {self.settings.hotkey.title()}")

    # -- tray --------------------------------------------------------------
    def _build_menu(self) -> None:
        menu = QMenu()
        self.capture_action = menu.addAction("", self.capture)
        menu.addAction("Panodaki görüntüden kod al", self.from_clipboard)
        menu.addAction("Görüntü dosyasından…", self.from_file)
        menu.addSeparator()
        self.watch_action = QAction("Panoyu izle", menu, checkable=True, checked=self.settings.watch_clipboard)
        self.watch_action.toggled.connect(self._set_watch)
        menu.addAction(self.watch_action)
        menu.addAction("Geçmiş", self.show_history)
        menu.addAction("Ayarlar", self.show_settings)
        menu.addSeparator()
        menu.addAction("Çıkış", self.quit)
        self.menu = menu
        self.tray.setContextMenu(menu)
        self._label_hotkey()

    def _label_hotkey(self) -> None:
        combo = self.settings.hotkey.title()
        self.capture_action.setText(f"Kod yakala\t{combo}")
        self.tray.setToolTip(f"SnapCode {__version__} · {combo}")

    def _tray_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.Trigger:
            self.capture()

    def _set_watch(self, on: bool) -> None:
        self.settings.watch_clipboard = on
        self.settings.save()
        self._last_clip = self._clipboard_key()

    def _start_hotkeys(self) -> None:
        if self._hotkeys:
            self._hotkeys.stop()
        self._hotkeys = HotkeyListener({"capture": self.settings.hotkey})
        self._hotkeys.triggered.connect(lambda _name: self.capture())
        self._hotkeys.failed.connect(lambda msg: Toast.show_text(msg, 4000))
        self._hotkeys.start()

    # -- capture -----------------------------------------------------------
    def capture(self) -> None:
        if self._session:
            return
        self._jobs.clear()
        session = CaptureSession(self._last_region, self.settings.ocr_language)
        session.settled.connect(self._settled)
        session.action.connect(self._action)
        session.finished.connect(self._session_closed)
        self._session = session
        session.start()

    def _session_closed(self) -> None:
        if self._session and self._session.last_selection:
            self._last_region = self._session.last_selection
        self._session = None

    def _settled(self, image: QImage, rect: QRect) -> None:
        """Start OCR as soon as a selection exists, so Ctrl+C is instant."""
        if self.settings.instant_copy:
            QTimer.singleShot(0, lambda s=self._session: self._trigger_copy(s))
            return
        job = self._job(image)
        session = self._session

        def show_info(j: Job) -> None:
            if session is not None and session is self._session:
                session.set_info(self._summary(j))

        job.then(show_info)

    def _trigger_copy(self, session: CaptureSession | None) -> None:
        if session is None:
            return
        for overlay in session.overlays:
            if not overlay.selection.isNull():
                overlay._trigger("copy")
                return

    def _job(self, image: QImage) -> Job:
        key = image_key(image)
        if key not in self._jobs:
            job = Job(image_to_png(image))
            self._jobs[key] = job
            self._run(job)
        return self._jobs[key]

    def _run(self, job: Job) -> None:
        task = RecognizeTask(job.png, self.settings)
        task.setAutoDelete(False)
        self._tasks.add(task)

        def finish(result=None, error=None):
            self._tasks.discard(task)
            job.result, job.error = result, error
            if result is not None and not result.code.strip():
                job.result, job.error = None, "Kod bulunamadı"
            for callback in job.waiters:
                callback(job)
            job.waiters.clear()

        task.signals.done.connect(lambda r: finish(result=r))
        task.signals.failed.connect(lambda e: finish(error=e))
        self.pool.start(task)

    @staticmethod
    def _summary(job: Job) -> str:
        if job.error:
            return job.error
        r = job.result
        return f"{r.language.name} · {r.line_count} satır"

    def _action(self, name: str, image: QImage, rect: QRect) -> None:
        if name == "image":
            QGuiApplication.clipboard().setImage(image)
            Toast.show_text("Görüntü kopyalandı")
            return
        job = self._job(image)
        job.then(lambda j: self._deliver(name, j))

    def _deliver(self, name: str, job: Job) -> None:
        if job.error:
            Toast.show_text(job.error, 3000)
            return
        result = job.result
        snippet_id = self._remember(job)
        if name == "copy":
            QGuiApplication.clipboard().setText(result.code)
            Toast.show_text(f"Kod kopyalandı · {self._summary(job)}")
        elif name == "edit":
            self.open_editor(result, snippet_id)
        elif name == "save":
            if save_code(None, result.code, result.language):
                Toast.show_text("Kaydedildi")

    def _remember(self, job: Job) -> int | None:
        if not self.settings.keep_history:
            return None
        if not hasattr(job, "snippet_id"):
            r = job.result
            job.snippet_id = self.history.add(r.code, r.language.key, r.engine, job.png)
            if self._history_window and self._history_window.isVisible():
                self._history_window.refresh()
        return job.snippet_id

    def open_editor(self, result: pipeline.Recognition, snippet_id: int | None) -> None:
        editor = EditorWindow(result, self.history.update_code if snippet_id else None)
        editor.snippet_id = snippet_id
        editor.destroyed.connect(lambda _=None, e=editor: self._editors.discard(e))
        self._editors.add(editor)
        editor.show()
        editor.raise_()
        editor.activateWindow()

    # -- other sources -----------------------------------------------------
    def _recognize_image(self, image: QImage) -> None:
        Toast.show_text("Okunuyor…", 10000)
        job = Job(image_to_png(image))
        self._run(job)
        job.then(lambda j: self._deliver("copy", j))

    def from_clipboard(self) -> None:
        image = QGuiApplication.clipboard().image()
        if image.isNull():
            Toast.show_text("Panoda görüntü yok")
        else:
            self._recognize_image(image)

    def from_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(None, "Görüntü aç", "", "Görüntüler (*.png *.jpg *.jpeg *.bmp *.webp)")
        if path:
            image = QImage(path)
            if image.isNull():
                Toast.show_text("Görüntü açılamadı")
            else:
                self._recognize_image(image)

    def _clipboard_key(self) -> str | None:
        image = QGuiApplication.clipboard().image()
        return None if image.isNull() else image_key(image)

    def _clipboard_changed(self) -> None:
        if self.settings.watch_clipboard:
            # Snipping Tool writes the clipboard several times; let it settle.
            QTimer.singleShot(250, self._check_clipboard)

    def _check_clipboard(self) -> None:
        key = self._clipboard_key()
        if key and key != self._last_clip:
            self._last_clip = key
            self.from_clipboard()

    # -- windows -----------------------------------------------------------
    def show_history(self) -> None:
        if not self._history_window:
            self._history_window = HistoryWindow(self.history)
        self._history_window.refresh()
        self._history_window.show()
        self._history_window.raise_()
        self._history_window.activateWindow()

    def show_settings(self) -> None:
        try:
            from .engines.windows_ocr import available_languages

            langs = available_languages()
        except Exception:
            langs = []
        old_hotkey = self.settings.hotkey
        if SettingsDialog(self.settings, langs).exec():
            self.settings.save()
            self.watch_action.setChecked(self.settings.watch_clipboard)
            if self.settings.hotkey != old_hotkey:
                self._start_hotkeys()
                self._label_hotkey()

    def quit(self) -> None:
        if self._hotkeys:
            self._hotkeys.stop()
        self.tray.hide()
        self.app.quit()


def run_gui() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("SnapCode")
    app.setQuitOnLastWindowClosed(False)
    app.setStyle("Fusion")
    app.setStyleSheet(STYLESHEET)
    app.setWindowIcon(app_icon())

    lock = QLockFile(str(Path(data_dir()) / "snapcode.lock"))
    if not lock.tryLock(100):
        QMessageBox.information(None, "SnapCode", "SnapCode zaten çalışıyor.")
        return 0
    if not QSystemTrayIcon.isSystemTrayAvailable():
        QMessageBox.critical(None, "SnapCode", "Sistem tepsisi bulunamadı.")
        return 1

    controller = SnapCodeApp(app)  # noqa: F841 - keeps the tray alive
    return app.exec()
