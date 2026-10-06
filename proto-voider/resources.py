# resources.py — where the app's own files (the bundled fonts) are, and loading them.
#
# Why this exists: the Windows .exe built with PyInstaller looked different from the
# one on NixOS. The default font was "Consolas" (absent on NixOS, so Qt used another
# monospace there) and the reading font "EB Garamond" is not installed on Windows at
# all. The fonts now travel with the app and are registered with Qt at startup, so
# both platforms draw the same letters.
import os
import sys

_FONT_EXTENSIONS = ('.ttf', '.otf')


def resource_dir():
    """The folder the app's data files (fonts/) live in.

    PyInstaller --onefile unpacks everything into a temporary folder and points
    sys._MEIPASS at it: the data is THERE, not next to the .exe. In development, and
    in a Nuitka build (which keeps included data next to the modules), it is the
    folder of this file."""
    if getattr(sys, 'frozen', False) and getattr(sys, '_MEIPASS', None):
        return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))


def bundled_font_files(base=None):
    """The font files shipped in <base>/fonts, sorted. A missing folder is simply no
    fonts: the app then uses whatever the system has."""
    folder = os.path.join(base if base is not None else resource_dir(), 'fonts')
    try:
        names = sorted(os.listdir(folder), key=str.lower)
    except OSError:
        return []
    return [os.path.join(folder, n) for n in names
            if n.lower().endswith(_FONT_EXTENSIONS)]


def load_bundled_fonts(base=None):
    """Register every bundled font with Qt (needs a QApplication to exist). Returns the
    family names that are now available from them. A file Qt cannot read is skipped,
    and the rest still load — one bad font must not cost the app its look."""
    from PyQt6.QtGui import QFontDatabase
    families = []
    for path in bundled_font_files(base):
        font_id = QFontDatabase.addApplicationFont(path)
        if font_id < 0:
            print(f'⚠️ No se pudo cargar la fuente {os.path.basename(path)}')
            continue
        for fam in QFontDatabase.applicationFontFamilies(font_id):
            if fam not in families:
                families.append(fam)
    return families
