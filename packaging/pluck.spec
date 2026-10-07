# PyInstaller spec: one-folder build (starts much faster than one-file).
# Build with: python -m PyInstaller packaging/pluck.spec --noconfirm

import re
from pathlib import Path

ROOT = Path(SPECPATH).parent
VERSION = re.search(r'__version__ = "([^"]+)"', (ROOT / "pluck" / "__init__.py").read_text()).group(1)
NUMS = tuple(int(x) for x in VERSION.split(".")) + (0,)

version_file = Path(SPECPATH) / "version_info.txt"
version_file.write_text(f"""
VSVersionInfo(
  ffi=FixedFileInfo(filevers={NUMS}, prodvers={NUMS}),
  kids=[
    StringFileInfo([StringTable('041f04b0', [
      StringStruct('CompanyName', 'Sefer Mavi'),
      StringStruct('FileDescription', 'Pluck'),
      StringStruct('FileVersion', '{VERSION}'),
      StringStruct('InternalName', 'Pluck'),
      StringStruct('OriginalFilename', 'Pluck.exe'),
      StringStruct('ProductName', 'Pluck'),
      StringStruct('ProductVersion', '{VERSION}'),
      StringStruct('LegalCopyright', 'MIT License')])]),
    VarFileInfo([VarStruct('Translation', [1055, 1200])])
  ]
)
""", encoding="utf-8")

# Qt modules Pluck never touches; dropping them roughly halves the size.
EXCLUDES = [
    "tkinter", "unittest", "pydoc", "numpy", "PySide6.QtNetwork", "PySide6.QtQml", "PySide6.QtQuick",
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtMultimedia",
    "PySide6.Qt3DCore", "PySide6.QtCharts", "PySide6.QtDataVisualization", "PySide6.QtPdf",
    "PySide6.QtSql", "PySide6.QtTest", "PySide6.QtOpenGL", "PySide6.QtSvg", "PySide6.QtBluetooth",
]

a = Analysis(
    [str(Path(SPECPATH) / "launcher.py")],
    pathex=[str(ROOT)],
    # Glyph templates for the OCR repair pass (pluck.glyphs).
    datas=[(str(ROOT / "pluck" / "fonts"), "pluck/fonts")],
    hiddenimports=[
        "winrt.windows.media.ocr", "winrt.windows.graphics.imaging",
        "winrt.windows.storage.streams", "winrt.windows.globalization",
        "winrt.windows.foundation", "winrt.windows.foundation.collections",
    ],
    excludes=EXCLUDES,
    noarchive=False,
)
# Qt plugins drag in heavy DLLs we never load (QML, PDF, software OpenGL).
DROP = ("opengl32sw", "Qt6Quick", "Qt6Qml", "Qt6Pdf", "Qt6Network", "Qt6OpenGL", "Qt6VirtualKeyboard",
        "qpdf", "qtvirtualkeyboard", "Qt6Svg", "qsvg")
a.binaries = [b for b in a.binaries if not any(d.lower() in b[0].lower() for d in DROP)]
# Keep only Turkish and English Qt translations (file dialogs, standard buttons).
a.datas = [
    d for d in a.datas
    if "translations" not in d[0] or Path(d[0]).name.startswith(("qtbase_tr", "qtbase_en"))
]

pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Pluck",
    icon=str(Path(SPECPATH) / "pluck.ico"),
    version=str(version_file),
    console=False,
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="Pluck", upx=False)
