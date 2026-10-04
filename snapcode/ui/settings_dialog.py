"""Settings form."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QLabel, QLineEdit, QVBoxLayout,
)

from .. import hotkey
from ..config import Settings
from ..pipeline import ENGINES
from .theme import app_icon

MODELS = ["claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-4-5"]
EFFORTS = ["low", "medium", "high"]


class SettingsDialog(QDialog):
    def __init__(self, settings: Settings, ocr_languages: list[str], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("SnapCode — Ayarlar")
        self.setWindowIcon(app_icon())
        self.setMinimumWidth(520)
        self._settings = settings

        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setVerticalSpacing(10)

        self.hotkey = QLineEdit(settings.hotkey)
        self.hotkey.setPlaceholderText("ctrl+shift+x")
        form.addRow("Yakalama kısayolu", self.hotkey)

        self.engine = QComboBox()
        for key, label in ENGINES.items():
            self.engine.addItem(label, key)
        self.engine.setCurrentIndex(max(0, self.engine.findData(settings.engine)))
        form.addRow("Tanıma motoru", self.engine)

        self.ocr_lang = QComboBox()
        self.ocr_lang.addItems(ocr_languages or [settings.ocr_language])
        self.ocr_lang.setCurrentText(settings.ocr_language)
        form.addRow("Windows OCR dili", self.ocr_lang)

        self.model = QComboBox(editable=True)
        self.model.addItems(MODELS)
        self.model.setCurrentText(settings.claude_model)
        form.addRow("Claude modeli", self.model)

        self.effort = QComboBox()
        self.effort.addItems(EFFORTS)
        self.effort.setCurrentText(settings.claude_effort)
        form.addRow("Claude effort", self.effort)

        self.api_key = QLineEdit(settings.api_key)
        self.api_key.setEchoMode(QLineEdit.Password)
        self.api_key.setPlaceholderText("Boşsa ANTHROPIC_API_KEY ortam değişkeni kullanılır")
        form.addRow("Anthropic API anahtarı", self.api_key)
        note = QLabel("Anahtar ayar dosyasında düz metin saklanır; ortam değişkeni daha güvenlidir.",
                      objectName="muted")
        note.setWordWrap(True)
        form.addRow("", note)

        self.checks = {}
        for field, label in [
            ("auto_copy", "Tanınan kodu otomatik panoya kopyala"),
            ("show_result_window", "Sonuç penceresini göster"),
            ("watch_clipboard", "Panoyu izle (Win+Shift+S görüntülerini otomatik çöz)"),
            ("strip_line_numbers", "Satır numaralarını temizle"),
            ("strip_prompts", "Terminal istemlerini ($, >>>) temizle"),
            ("keep_history", "Geçmişi kaydet"),
        ]:
            box = QCheckBox(label)
            box.setChecked(getattr(settings, field))
            self.checks[field] = box
            form.addRow("", box)

        layout.addLayout(form)
        self.error = QLabel(objectName="muted")
        layout.addWidget(self.error)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _accept(self) -> None:
        combo = self.hotkey.text().strip().lower()
        try:
            hotkey.parse(combo)
        except ValueError as exc:
            self.error.setText(f"⚠ {exc}")
            return
        s = self._settings
        s.hotkey = combo
        s.engine = self.engine.currentData()
        s.ocr_language = self.ocr_lang.currentText()
        s.claude_model = self.model.currentText().strip()
        s.claude_effort = self.effort.currentText()
        s.api_key = self.api_key.text().strip()
        for field, box in self.checks.items():
            setattr(s, field, box.isChecked())
        self.accept()
