"""Tray application: hotkey -> capture -> recognize -> clipboard."""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

from PySide6.QtCore import QBuffer, QLockFile, QObject, QRunnable, Qt, QThreadPool, QTimer, Signal
from PySide6.QtGui import QAction, QActionGroup, QGuiApplication, QImage
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon

from . import __version__, pipeline
from .config import Settings, data_dir
from .history import History
from .hotkey import HotkeyListener
from .ui.capture import CaptureSession
from .ui.history_window import HistoryWindow
from .ui.result_window import ResultWindow
from .ui.settings_dialog import SettingsDialog
from .ui.theme import STYLESHEET, app_icon


def image_to_png(image: QImage) -> bytes:
    buffer = QBuffer()
    buffer.open(QBuffer.WriteOnly)
    image.save(buffer, "PNG")
    return bytes(buffer.data())


class _TaskSignals(QObject):
    done = Signal(object)
    failed = Signal(str)


class RecognizeTask(QRunnable):
    def __init__(self, png: bytes, settings: Settings, engine: str | None) -> None:
        super().__init__()
        self.png, self.settings, self.engine = png, settings, engine
        self.signals = _TaskSignals()

    def run(self) -> None:
        try:
            self.signals.done.emit(pipeline.recognize(self.png, self.settings, self.engine))
        except Exception as exc:  # surfaced to the user, never crash the tray
            self.signals.failed.emit(str(exc) or exc.__class__.__name__)


class SnapCodeApp(QObject):
    def __init__(self, app: QApplication) -> None:
        super().__init__()
        self.app = app
        self.settings = Settings.load()
        self.history = History()
        self.pool = QThreadPool.globalInstance()
        self._windows: set[ResultWindow] = set()
        self._tasks: set[RecognizeTask] = set()
        self._capture: CaptureSession | None = None
        self._history_window: HistoryWindow | None = None
        self._last_clip_hash = None
        self._hotkeys: HotkeyListener | None = None

        self.tray = QSystemTrayIcon(app_icon(), self)
        self.tray.setToolTip(f"SnapCode — {self.settings.hotkey.upper()} ile kod yakala")
        self.tray.activated.connect(self._tray_activated)
        self._build_menu()
        self.tray.show()

        QGuiApplication.clipboard().dataChanged.connect(self._clipboard_changed)
        self._start_hotkeys()
        self.notify("SnapCode hazır", f"{self.settings.hotkey.upper()} ile ekrandaki kodu yakala.")

    # -- tray --------------------------------------------------------------
    def _build_menu(self) -> None:
        menu = QMenu()
        self.capture_action = menu.addAction(f"Kod yakala\t{self.settings.hotkey.upper()}", self.capture)
        menu.addAction("Panodaki görüntüyü çöz", self.recognize_clipboard)
        menu.addAction("Görüntü dosyası aç…", self.open_file)
        menu.addSeparator()

        engines = menu.addMenu("Motor")
        group = QActionGroup(engines)
        self.engine_actions: dict[str, QAction] = {}
        for key, label in pipeline.ENGINES.items():
            action = QAction(label, engines, checkable=True, checked=self.settings.engine == key)
            action.triggered.connect(lambda _=False, k=key: self._set_engine(k))
            group.addAction(action)
            engines.addAction(action)
            self.engine_actions[key] = action

        self.watch_action = QAction("Panoyu izle", menu, checkable=True, checked=self.settings.watch_clipboard)
        self.watch_action.toggled.connect(self._set_watch)
        menu.addAction(self.watch_action)
        menu.addSeparator()
        menu.addAction("Geçmiş…", self.show_history)
        menu.addAction("Ayarlar…", self.show_settings)
        menu.addSeparator()
        menu.addAction(f"Çıkış  (v{__version__})", self.quit)
        self.menu = menu
        self.tray.setContextMenu(menu)

    def _tray_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.Trigger:
            self.capture()

    def notify(self, title: str, message: str, icon=QSystemTrayIcon.Information) -> None:
        self.tray.showMessage(title, message, icon, 3500)

    def _set_engine(self, key: str) -> None:
        self.settings.engine = key
        self.settings.save()

    def _set_watch(self, on: bool) -> None:
        self.settings.watch_clipboard = on
        self.settings.save()
        self._last_clip_hash = self._clipboard_hash()

    # -- hotkeys -----------------------------------------------------------
    def _start_hotkeys(self) -> None:
        if self._hotkeys:
            self._hotkeys.stop()
        self._hotkeys = HotkeyListener({"capture": self.settings.hotkey})
        self._hotkeys.triggered.connect(lambda name: self.capture())
        self._hotkeys.failed.connect(lambda msg: self.notify("Kısayol kaydedilemedi", msg, QSystemTrayIcon.Warning))
        self._hotkeys.start()

    # -- input sources -----------------------------------------------------
    def capture(self) -> None:
        if self._capture:
            return
        self._capture = CaptureSession()
        self._capture.finished.connect(self._captured)
        self._capture.start()

    def _captured(self, image: QImage | None) -> None:
        self._capture = None
        if image is not None and not image.isNull():
            self.process(image_to_png(image))

    def recognize_clipboard(self) -> None:
        image = QGuiApplication.clipboard().image()
        if image.isNull():
            self.notify("Panoda görüntü yok", "Önce bir ekran görüntüsü kopyala (Win+Shift+S).")
            return
        self.process(image_to_png(image))

    def open_file(self) -> None:
        from PySide6.QtWidgets import QFileDialog

        path, _ = QFileDialog.getOpenFileName(None, "Görüntü aç", "", "Görüntüler (*.png *.jpg *.jpeg *.bmp *.webp)")
        if path:
            image = QImage(path)
            if image.isNull():
                self.notify("Açılamadı", path, QSystemTrayIcon.Warning)
            else:
                self.process(image_to_png(image))

    def _clipboard_hash(self) -> str | None:
        image = QGuiApplication.clipboard().image()
        if image.isNull():
            return None
        return hashlib.blake2b(image.constBits().tobytes(), digest_size=16).hexdigest()

    def _clipboard_changed(self) -> None:
        if not self.settings.watch_clipboard:
            return
        # Snipping Tool writes the clipboard several times; let it settle.
        QTimer.singleShot(250, self._check_clipboard)

    def _check_clipboard(self) -> None:
        digest = self._clipboard_hash()
        if digest and digest != self._last_clip_hash:
            self._last_clip_hash = digest
            self.recognize_clipboard()

    # -- processing --------------------------------------------------------
    def process(self, png: bytes) -> None:
        window = None
        if self.settings.show_result_window:
            window = ResultWindow(png, self._rerun, self._edited)
            window.setAttribute(Qt.WA_DeleteOnClose)
            window.destroyed.connect(lambda _=None, w=window: self._windows.discard(w))
            self._windows.add(window)
            window.show()
            window.activateWindow()
        self._run(png, None, window)

    def _rerun(self, window: ResultWindow, engine: str) -> None:
        self._run(window.png, engine, window)

    def _run(self, png: bytes, engine: str | None, window: ResultWindow | None) -> None:
        task = RecognizeTask(png, self.settings, engine)
        task.setAutoDelete(False)
        self._tasks.add(task)
        task.signals.done.connect(lambda result: self._done(task, png, result, window))
        task.signals.failed.connect(lambda msg: self._failed(task, msg, window))
        self.pool.start(task)

    def _done(self, task, png: bytes, result: pipeline.Recognition, window) -> None:
        self._tasks.discard(task)
        if not result.code.strip():
            self._failed(task, "Görüntüde kod bulunamadı.", window)
            return
        if self.settings.auto_copy:
            QGuiApplication.clipboard().setText(result.code)
        snippet_id = None
        if self.settings.keep_history:
            snippet_id = self.history.add(result.code, result.language.key, result.engine, png)
            if self._history_window and self._history_window.isVisible():
                self._history_window.refresh()
        if window is not None and window in self._windows:
            window.snippet_id = snippet_id
            window.set_result(result)
        else:
            copied = "panoya kopyalandı" if self.settings.auto_copy else "geçmişe kaydedildi"
            self.notify(f"{result.language.name} · {result.line_count} satır {copied}",
                        result.code.strip().splitlines()[0][:80])

    def _failed(self, task, message: str, window) -> None:
        self._tasks.discard(task)
        if window is not None and window in self._windows:
            window.set_error(message)
        else:
            self.notify("Tanıma başarısız", message, QSystemTrayIcon.Warning)

    def _edited(self, snippet_id: int, code: str, language: str) -> None:
        self.history.update_code(snippet_id, code, language)

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
        dialog = SettingsDialog(self.settings, langs)
        if dialog.exec():
            self.settings.save()
            self.watch_action.setChecked(self.settings.watch_clipboard)
            if self.settings.hotkey != old_hotkey:
                self._start_hotkeys()
                self.capture_action.setText(f"Kod yakala\t{self.settings.hotkey.upper()}")
                self.tray.setToolTip(f"SnapCode — {self.settings.hotkey.upper()} ile kod yakala")
            self.engine_actions[self.settings.engine].setChecked(True)

    def quit(self) -> None:
        if self._hotkeys:
            self._hotkeys.stop()
        self.tray.hide()
        self.app.quit()


def run_gui() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("SnapCode")
    app.setQuitOnLastWindowClosed(False)
    app.setStyleSheet(STYLESHEET)
    app.setWindowIcon(app_icon())

    lock = QLockFile(str(Path(data_dir()) / "snapcode.lock"))
    if not lock.tryLock(100):
        QMessageBox.information(None, "SnapCode", "SnapCode zaten çalışıyor (sistem tepsisine bak).")
        return 0

    if not QSystemTrayIcon.isSystemTrayAvailable():
        QMessageBox.critical(None, "SnapCode", "Sistem tepsisi bulunamadı.")
        return 1

    controller = SnapCodeApp(app)  # noqa: F841 - keeps the tray alive
    return app.exec()
