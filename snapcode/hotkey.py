"""System-wide hotkeys through the Win32 RegisterHotKey API (no extra deps)."""

from __future__ import annotations

import ctypes
from ctypes import wintypes

from PySide6.QtCore import QThread, Signal

MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN, MOD_NOREPEAT = 0x1, 0x2, 0x4, 0x8, 0x4000
WM_HOTKEY, WM_QUIT = 0x0312, 0x0012

_MODIFIERS = {"ctrl": MOD_CONTROL, "control": MOD_CONTROL, "alt": MOD_ALT, "shift": MOD_SHIFT, "win": MOD_WIN}
_KEYS = {
    "printscreen": 0x2C, "print": 0x2C, "space": 0x20, "insert": 0x2D, "home": 0x24,
    "end": 0x23, "pageup": 0x21, "pagedown": 0x22, "pause": 0x13, "scrolllock": 0x91,
    **{f"f{i}": 0x6F + i for i in range(1, 25)},
}


def parse(combo: str) -> tuple[int, int]:
    """'ctrl+shift+x' -> (modifiers, virtual key code)."""
    mods, vk = 0, None
    for part in combo.lower().replace(" ", "").split("+"):
        if part in _MODIFIERS:
            mods |= _MODIFIERS[part]
        elif part in _KEYS:
            vk = _KEYS[part]
        elif len(part) == 1 and part.isalnum():
            vk = ord(part.upper())
        else:
            raise ValueError(f"Bilinmeyen tuş: {part!r}")
    if vk is None:
        raise ValueError("Kısayolda bir ana tuş olmalı (örn. ctrl+shift+x).")
    return mods, vk


class HotkeyListener(QThread):
    """Owns a Win32 message loop; emits ``triggered(name)`` when a hotkey fires."""

    triggered = Signal(str)
    failed = Signal(str)

    def __init__(self, bindings: dict[str, str]) -> None:
        super().__init__()
        self._bindings = bindings  # name -> combo
        self._thread_id = 0

    def run(self) -> None:
        user32 = ctypes.windll.user32
        self._thread_id = ctypes.windll.kernel32.GetCurrentThreadId()
        ids = {}
        for index, (name, combo) in enumerate(self._bindings.items(), start=1):
            try:
                mods, vk = parse(combo)
            except ValueError as exc:
                self.failed.emit(str(exc))
                continue
            if user32.RegisterHotKey(None, index, mods | MOD_NOREPEAT, vk):
                ids[index] = name
            else:
                self.failed.emit(f"{combo} kısayolu başka bir uygulama tarafından kullanılıyor.")

        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            if msg.message == WM_HOTKEY and msg.wParam in ids:
                self.triggered.emit(ids[msg.wParam])

        for index in ids:
            user32.UnregisterHotKey(None, index)

    def stop(self) -> None:
        if self._thread_id:
            ctypes.windll.user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
        self.wait(2000)
