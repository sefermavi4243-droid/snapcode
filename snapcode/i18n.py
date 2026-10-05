"""Interface language: Turkish (the source strings) or English.

Every user-facing string is written in Turkish and passed through ``t()``,
which returns the English version when English is active. Placeholders use
``str.format`` names: ``t("{n} satır", n=12)``.
"""

from __future__ import annotations

LANGUAGES = {"auto": "Otomatik", "tr": "Türkçe", "en": "English"}

_current = "tr"

EN = {
    # app / tray
    "{app} çalışıyor · {combo}": "{app} is running · {combo}",
    "Kod yakala\t{combo}": "Capture code\t{combo}",
    "Panodaki görüntüden kod al": "Read code from clipboard image",
    "Görüntü dosyasından…": "From image file…",
    "Panoyu izle": "Watch clipboard",
    "Geçmiş": "History",
    "Ayarlar": "Settings",
    "Çıkış": "Quit",
    "Kod bulunamadı": "No code found",
    "{language} · {n} satır": "{language} · {n} lines",
    "Görüntü kopyalandı": "Image copied",
    "Kod kopyalandı · {summary}": "Code copied · {summary}",
    "Kod kopyalandı": "Code copied",
    "Kaydedildi": "Saved",
    "IDE açılamadı: {error}": "Could not open IDE: {error}",
    "{ide} içinde açıldı · kod panoda da": "Opened in {ide} · code is on the clipboard too",
    "Okunuyor…": "Reading…",
    "Panoda görüntü yok": "No image on the clipboard",
    "Panoda görüntü yok.": "No image on the clipboard.",
    "Görüntü aç": "Open image",
    "Görüntüler (*.png *.jpg *.jpeg *.bmp *.webp)": "Images (*.png *.jpg *.jpeg *.bmp *.webp)",
    "Görüntü açılamadı": "Could not open image",
    "{app} zaten çalışıyor.": "{app} is already running.",
    "Sistem tepsisi bulunamadı.": "No system tray found.",
    # capture overlay
    "Kodu kopyala (Ctrl+C, Enter, çift tık)": "Copy code (Ctrl+C, Enter, double-click)",
    "IDE'de aç (Ctrl+O)": "Open in IDE (Ctrl+O)",
    "{ide} içinde aç (Ctrl+O)": "Open in {ide} (Ctrl+O)",
    "Düzenle (Ctrl+E)": "Edit (Ctrl+E)",
    "Kodu dosyaya kaydet (Ctrl+S)": "Save code to file (Ctrl+S)",
    "Görüntüyü kopyala (Ctrl+Shift+C)": "Copy image (Ctrl+Shift+C)",
    "Kapat (Esc)": "Close (Esc)",
    "IDE": "IDE",
    "Düzenle": "Edit",
    "okunuyor…": "reading…",
    # editor
    "Kodu kaydet": "Save code",
    "Tüm dosyalar (*)": "All files (*)",
    "{n} satır": "{n} lines",
    "Kaydet": "Save",
    "Kopyala": "Copy",
    "IDE'de aç": "Open in IDE",
    "Görüntü": "Image",
    "Yakalanan görüntüyü kodun üstünde göster (Ctrl+G)": "Show the captured image above the code (Ctrl+G)",
    "Ctrl+Enter kopyala · Ctrl+S kaydet · Esc kapat": "Ctrl+Enter copy · Ctrl+S save · Esc close",
    # history
    "Kodda ara…  (ör. useEffect, SELECT, python)": "Search code…  (e.g. useEffect, SELECT, python)",
    "Sil": "Delete",
    "Tümünü temizle": "Clear all",
    "Geçmişi temizle": "Clear history",
    "Tüm geçmiş silinsin mi?": "Delete the whole history?",
    "{app} — Geçmiş": "{app} — History",
    # settings
    "Kısayol": "Shortcut",
    "Tanıma": "Recognition",
    "OCR dili": "OCR language",
    "Otomatik (dile göre en uygun)": "Automatic (best for the language)",
    "İsteğe bağlı": "Optional",
    "Anthropic API anahtarı": "Anthropic API key",
    "Seçimi bırakınca hemen kopyala": "Copy as soon as the selection is released",
    "Panodaki ekran görüntülerini otomatik çöz": "Read screenshots on the clipboard automatically",
    "Geçmişi sakla": "Keep history",
    "Windows ile başlat": "Start with Windows",
    "İptal": "Cancel",
    "Arayüz dili": "Language",
    "Otomatik": "Automatic",
    # engines and languages
    "Windows OCR (çevrimdışı)": "Windows OCR (offline)",
    "Claude Vision (API anahtarı gerekir)": "Claude Vision (needs an API key)",
    "Claude başarısız ({error}), Windows OCR kullanıldı": "Claude failed ({error}), used Windows OCR",
    "Düz metin": "Plain text",
    "Not Defteri": "Notepad",
    "Bu sistemde Windows OCR dil paketi yüklü değil.": "No Windows OCR language pack is installed on this system.",
    "Claude motoru için: pip install anthropic": "For the Claude engine: pip install anthropic",
    "Anthropic API anahtarı geçersiz veya eksik.": "The Anthropic API key is invalid or missing.",
    "Bu anahtarın {model} modeline erişimi yok.": "This key has no access to {model}.",
    "Claude hız limitine takıldı, biraz sonra tekrar dene.": "Claude hit a rate limit, try again shortly.",
    "Claude API hatası {status}: {message}": "Claude API error {status}: {message}",
    "Claude API'ye bağlanılamadı (internet?).": "Could not reach the Claude API (internet?).",
    "Anthropic API anahtarı ayarlanmamış.": "No Anthropic API key is set.",
    "Claude bu görüntüyü işlemeyi reddetti.": "Claude declined to process this image.",
    "Kod çok uzun, yanıt yarıda kesildi.": "The code is too long, the answer was cut off.",
    "Claude boş yanıt döndü.": "Claude returned an empty answer.",
    "Claude yanıtı çözümlenemedi.": "Could not parse Claude's answer.",
    # hotkeys
    "Bilinmeyen tuş: {key}": "Unknown key: {key}",
    "Kısayolda bir ana tuş olmalı (örn. ctrl+shift+x).": "The shortcut needs a main key (e.g. ctrl+shift+x).",
    "{combo} kısayolu başka bir uygulama tarafından kullanılıyor.": "{combo} is already used by another application.",
    # command line
    "Ekran görüntüsündeki kodu metne çevir.": "Turn code in a screenshot into text.",
    "görüntü dosyası (yoksa tepsi uygulaması başlar)": "image file (without one the tray app starts)",
    "panodaki görüntüyü kullan": "use the image on the clipboard",
    "tanıma motoru": "recognition engine",
    "sonucu panoya kopyala": "copy the result to the clipboard",
    "sonucu IDE'de aç (vscode, cursor, pycharm, …; boşsa otomatik)":
        "open the result in an IDE (vscode, cursor, pycharm, …; empty: automatic)",
    "JSON çıktı (dil, motor, süre)": "JSON output (language, engine, time)",
}


def system_language() -> str:
    """'tr' when Windows' display language is Turkish, else 'en'."""
    try:
        import ctypes

        return "tr" if ctypes.windll.kernel32.GetUserDefaultUILanguage() & 0x3FF == 0x1F else "en"
    except (AttributeError, OSError):
        import locale

        return "tr" if (locale.getlocale()[0] or "").lower().startswith(("tr", "turkish")) else "en"


def set_language(choice: str) -> str:
    """Activate 'tr', 'en' or 'auto' (follow Windows). Returns the active code."""
    global _current
    _current = system_language() if choice == "auto" else choice if choice in ("tr", "en") else "tr"
    return _current


def current() -> str:
    return _current


def t(text: str, **values) -> str:
    if _current == "en":
        text = EN.get(text, text)
    return text.format(**values) if values else text
