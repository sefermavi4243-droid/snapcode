"""Start with Windows via the per-user Run registry key."""

from __future__ import annotations

import sys
from pathlib import Path

_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_NAME = "Pluck"
_LEGACY_NAMES = ("CodeLift", "SnapCode")


def command() -> str:
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    return f'"{pythonw if pythonw.exists() else sys.executable}" -m snapcode'


def is_enabled() -> bool:
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _KEY) as key:
            winreg.QueryValueEx(key, _NAME)
        return True
    except OSError:
        return False


def set_enabled(enabled: bool) -> None:
    import winreg

    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _KEY, 0, winreg.KEY_SET_VALUE) as key:
        if enabled:
            winreg.SetValueEx(key, _NAME, 0, winreg.REG_SZ, command())
        else:
            try:
                winreg.DeleteValue(key, _NAME)
            except FileNotFoundError:
                pass


def migrate() -> None:
    """Carry an autostart entry from an earlier app name over to the new name and path."""
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _KEY, 0, winreg.KEY_ALL_ACCESS) as key:
            found = False
            for name in _LEGACY_NAMES:
                try:
                    winreg.QueryValueEx(key, name)
                except FileNotFoundError:
                    continue
                winreg.DeleteValue(key, name)
                found = True
            if found:
                winreg.SetValueEx(key, _NAME, 0, winreg.REG_SZ, command())
    except OSError:
        pass
