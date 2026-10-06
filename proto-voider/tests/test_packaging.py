"""The recipe for the Windows .exe — what the first build got wrong.

The first PyInstaller spec (kept next to the Windows sources) was minimal:
`upx=True`, `datas=[]`. UPX is a well-known source of exes that start oddly, and
with no data files the build silently lost what the app reads at runtime: the
bundled fonts, pyphen's hyphenation dictionaries and langdetect's language
profiles. The last two fail QUIETLY (the code catches the error and returns the
text unhyphenated), so the exe "worked" and just looked different.

These tests read the recipe, since a build cannot run here (it needs Windows).
"""
import os

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(name):
    with open(os.path.join(HERE, name), encoding='utf-8') as f:
        return f.read()


def test_the_pyinstaller_spec_does_not_use_upx():
    spec = _read('voider.spec')
    assert 'upx=False' in spec and 'upx=True' not in spec


def test_the_spec_ships_the_fonts():
    spec = _read('voider.spec')
    assert "('fonts', 'fonts')" in spec


def test_the_spec_ships_the_data_files_that_fail_silently_when_missing():
    spec = _read('voider.spec')
    for pkg in ('pyphen', 'langdetect'):
        assert f"collect_data_files('{pkg}')" in spec, f'{pkg} data is not collected'


def test_the_spec_is_a_windowed_single_exe_with_the_icon():
    spec = _read('voider.spec')
    assert 'console=False' in spec
    assert "icon='voider.ico'" in spec
    assert "['voider.py']" in spec


def test_the_spec_is_valid_python():
    compile(_read('voider.spec'), 'voider.spec', 'exec')


def test_the_nuitka_script_ships_the_same_data():
    bat = _read('build_windows_nuitka.bat')
    assert '--onefile' in bat
    assert '--enable-plugin=pyqt6' in bat
    assert '--include-data-dir=fonts=fonts' in bat
    assert '--include-package-data=pyphen' in bat
    assert '--include-package-data=langdetect' in bat
    assert 'voider.ico' in bat
    assert 'console-mode=disable' in bat or 'disable-console' in bat


def test_the_instructions_say_what_was_not_verified():
    doc = _read('BUILD-WINDOWS.md')
    assert 'Nuitka' in doc and 'PyInstaller' in doc
    # honesty: nothing here could be built from NixOS
    assert 'no se pudo probar' in doc.lower() or 'sin probar' in doc.lower()


def test_every_bundled_resource_the_recipes_name_exists():
    for rel in ('fonts/EBGaramond12-Regular.ttf', 'fonts/EBGaramond12-Italic.ttf',
                'fonts/EB-Garamond-LICENSE.txt', 'voider.ico'):
        assert os.path.exists(os.path.join(HERE, rel)), rel
