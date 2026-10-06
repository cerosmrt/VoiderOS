# voider.spec — build with:  pyinstaller voider.spec        (run from this folder)
#
# One windowed .exe with Voider's own icon. Compared with the first spec:
#
#   * upx=False. UPX-compressed exes are a classic source of "starts oddly".
#   * datas now ships what the app READS AT RUNTIME. Before it shipped nothing, so
#     the exe quietly lost:
#       - fonts/            EB Garamond (Windows has none; the interface fell back
#                           to another font and every layout moved)
#       - pyphen's dictionaries   hyphenation of the book (the code catches the
#                           missing-dictionary error and returns the text as is)
#       - langdetect's profiles   language guess for TTS and hyphenation
#     Those two fail SILENTLY, which is why the exe "worked" and just looked different.
#
# config.json / state.json / void/ are NOT bundled: they are read and written next to
# the exe at runtime (app_config._config_dir), so after building copy them from this
# folder into dist/ alongside voider.exe if you want a pre-filled setup.
from PyInstaller.utils.hooks import collect_data_files

datas = [('fonts', 'fonts')]
datas += collect_data_files('pyphen')
datas += collect_data_files('langdetect')

a = Analysis(
    ['voider.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=['pyphen', 'langdetect', 'ebooklib'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='voider',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='voider.ico',
)
