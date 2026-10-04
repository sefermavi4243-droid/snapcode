"""Settings form."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QLabel, QLineEdit, QVBoxLayout,
)

from .. import autostart, hotkey
from ..config import Settings
from ..pipeline import ENGINES
from .theme import app_icon


class SettingsDialog(QDialog):
    def __init__(self, settings: Settings, ocr_languages: list[str], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Ayarlar")
        self.setWindowIcon(app_icon())
        self.setMinimumWidth(440)
        self._settings = settings

        form = QFormLayout()
        form.setContentsMargins(16, 16, 16, 8)
        form.setVerticalSpacing(8)

        self.hotkey = QLineEdit(settings.hotkey)
        form.addRow("Kısayol", self.hotkey)

        self.engine = QComboBox()
        for key, label in ENGINES.items():
            self.engine.addItem(label, key)
        self.engine.setCurrentIndex(max(0, self.engine.findData(settings.engine)))
        form.addRow("Tanıma", self.engine)

        self.ocr_lang = QComboBox()
        self.ocr_lang.addItems(ocr_languages or [settings.ocr_language])
        self.ocr_lang.setCurrentText(settings.ocr_language)
        form.addRow("OCR dili", self.ocr_lang)

        self.api_key = QLineEdit(settings.api_key)
        self.api_key.setEchoMode(QLineEdit.Password)
        self.api_key.setPlaceholderText("İsteğe bağlı")
        form.addRow("Anthropic API anahtarı", self.api_key)

        self.checks = {}
        for field, label in [
            ("instant_copy", "Seçimi bırakınca hemen kopyala"),
            ("watch_clipboard", "Panodaki ekran görüntülerini otomatik çöz"),
            ("keep_history", "Geçmişi sakla"),
        ]:
            box = QCheckBox(label)
            box.setChecked(getattr(settings, field))
            self.checks[field] = box
            form.addRow("", box)

        self.autostart = QCheckBox("Windows ile başlat")
        self.autostart.setChecked(autostart.is_enabled())
        form.addRow("", self.autostart)

        self.error = QLabel(objectName="muted")
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText("Kaydet")
        buttons.button(QDialogButtonBox.Save).setObjectName("primary")
        buttons.button(QDialogButtonBox.Cancel).setText("İptal")
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 16, 16)
        layout.addLayout(form)
        layout.addWidget(self.error)
        layout.addWidget(buttons)

    def _accept(self) -> None:
        combo = self.hotkey.text().strip().lower()
        try:
            hotkey.parse(combo)
        except ValueError as exc:
            self.error.setText(str(exc))
            return
        s = self._settings
        s.hotkey = combo
        s.engine = self.engine.currentData()
        s.ocr_language = self.ocr_lang.currentText()
        s.api_key = self.api_key.text().strip()
        for field, box in self.checks.items():
            setattr(s, field, box.isChecked())
        if self.autostart.isChecked() != autostart.is_enabled():
            autostart.set_enabled(self.autostart.isChecked())
        self.accept()
