@echo off
rem build_windows_nuitka.bat — build voider.exe with Nuitka (run on Windows, from this folder).
rem
rem Nuitka compiles the Python to C and bundles it. Compared with PyInstaller it tends
rem to leave out fewer Qt plugins, and it has no UPX step. Same data as voider.spec:
rem the fonts, pyphen's hyphenation dictionaries and langdetect's language profiles.
rem
rem Once:   pip install nuitka PyQt6 numpy watchdog langdetect pyphen ebooklib pyaudio
rem         (Nuitka also needs a C compiler; it offers to download MinGW the first time.)
rem Result: voider.exe in this folder (a single file; first launch unpacks it, so it is
rem         slower to open than the folder build).

python -m nuitka ^
  --onefile ^
  --enable-plugin=pyqt6 ^
  --windows-console-mode=disable ^
  --windows-icon-from-ico=voider.ico ^
  --include-data-dir=fonts=fonts ^
  --include-package-data=pyphen ^
  --include-package-data=langdetect ^
  --output-filename=voider.exe ^
  voider.py
