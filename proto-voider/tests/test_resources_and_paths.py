"""What made the Windows .exe look different from the one on NixOS.

Federico built it with PyInstaller on Windows and "salio recontra bugeado" — mostly
the interface. Three causes, found by reading the spec and the code:

1. FONTS. The default was "Consolas" (not on NixOS, so Qt fell back to some other
   monospace there; present on Windows, with different metrics) and the reading font
   "EB Garamond" is not installed on Windows at all. The fonts now travel WITH the
   app (fonts/) and are registered at startup, so both platforms draw the same
   letters; the default is the book's own font.
2. PATHS. /tmp/voider-fx, /tmp/voider-fx-panel and ~/void/tts/*.onnx do not exist
   on Windows. Temp files go through tempfile.gettempdir(); the voice models live
   under the configured void, not under ~.
3. The spec itself (upx, no data files) — see packaging/.
"""
import os
import sys
import tempfile
import types

import pytest

pytest.importorskip("PyQt6")
from PyQt6.QtWidgets import QApplication

import resources
import platform_paths


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


# ── where the app's own files are ────────────────────────────────────────────

def test_in_development_resources_live_next_to_the_modules():
    assert resources.resource_dir() == os.path.dirname(os.path.abspath(resources.__file__))


def test_a_pyinstaller_build_reads_from_its_extraction_folder(monkeypatch):
    # --onefile unpacks to sys._MEIPASS; the data files are THERE, not next to the exe
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    monkeypatch.setattr(sys, '_MEIPASS', '/tmp/_MEI12345', raising=False)
    assert resources.resource_dir() == '/tmp/_MEI12345'


def test_a_frozen_build_without_meipass_falls_back_to_the_module_folder(monkeypatch):
    # Nuitka's standalone/onefile has no _MEIPASS but keeps data next to __file__
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    monkeypatch.delattr(sys, '_MEIPASS', raising=False)
    assert resources.resource_dir() == os.path.dirname(os.path.abspath(resources.__file__))


# ── the bundled fonts ────────────────────────────────────────────────────────

def test_the_app_ships_eb_garamond():
    files = [os.path.basename(p) for p in resources.bundled_font_files()]
    assert 'EBGaramond12-Regular.ttf' in files
    assert 'EBGaramond12-Italic.ttf' in files


def test_the_fonts_ship_with_their_licence():
    # the SIL Open Font License asks for it to travel with the font
    lic = os.path.join(resources.resource_dir(), 'fonts', 'EB-Garamond-LICENSE.txt')
    assert os.path.isfile(lic)
    text = open(lic, encoding='utf-8').read()
    assert 'SIL OPEN FONT LICENSE' in text and 'Duffner' in text


def test_only_font_files_are_picked_and_in_a_stable_order(tmp_path):
    d = tmp_path / 'fonts'
    d.mkdir()
    for n in ('b.otf', 'a.ttf', 'notes.txt', 'C.TTF', 'readme.md'):
        (d / n).write_bytes(b'x')
    got = [os.path.basename(p) for p in resources.bundled_font_files(str(tmp_path))]
    assert got == ['a.ttf', 'b.otf', 'C.TTF']


def test_a_missing_fonts_folder_is_no_fonts_not_an_error(tmp_path):
    assert resources.bundled_font_files(str(tmp_path)) == []


def test_loading_registers_the_book_font_with_qt(qapp):
    families = resources.load_bundled_fonts()
    assert 'EB Garamond' in families, families


def test_loading_twice_is_harmless(qapp):
    a = resources.load_bundled_fonts()
    b = resources.load_bundled_fonts()
    assert 'EB Garamond' in a and 'EB Garamond' in b


def test_a_broken_font_file_is_skipped_and_the_rest_still_load(qapp, tmp_path):
    d = tmp_path / 'fonts'
    d.mkdir()
    (d / 'broken.ttf').write_bytes(b'this is not a font')
    real = os.path.join(resources.resource_dir(), 'fonts', 'EBGaramond12-Regular.ttf')
    (d / 'good.ttf').write_bytes(open(real, 'rb').read())
    families = resources.load_bundled_fonts(str(tmp_path))
    assert 'EB Garamond' in families


def test_the_default_font_is_the_books_not_one_only_windows_has():
    from app_config import DEFAULT_CONFIG
    assert DEFAULT_CONFIG['font_family'] == 'EB Garamond'
    assert DEFAULT_CONFIG['reading_font'] == 'EB Garamond'


def test_the_app_registers_its_fonts_before_it_builds_the_window():
    import inspect
    import runpy
    src = open(os.path.join(os.path.dirname(resources.__file__), 'voider.py'), encoding='utf-8').read()
    assert 'load_bundled_fonts' in src
    assert src.index('load_bundled_fonts') < src.index('FullscreenCircleApp()'), \
        'the window picks its font at construction, so the fonts must already be registered'


# ── paths that exist only on Linux ───────────────────────────────────────────

def test_temp_files_go_through_the_systems_temp_folder():
    p = platform_paths.tmp_file('voider-fx')
    assert os.path.dirname(p) == tempfile.gettempdir()
    assert os.path.basename(p) == 'voider-fx'


def test_the_fx_state_file_is_not_a_hardcoded_tmp_path():
    import fx_panel
    assert fx_panel.STATE_FILE == platform_paths.tmp_file('voider-fx')
    assert os.path.dirname(fx_panel.STATE_FILE) == tempfile.gettempdir()


def test_the_fx_panel_request_file_is_not_a_hardcoded_tmp_path():
    import inspect
    from new_interface import FullscreenCircleApp
    src = inspect.getsource(FullscreenCircleApp._poll_fx_panel)
    assert "'/tmp/voider-fx-panel'" not in src
    assert "tmp_file('voider-fx-panel')" in src


def test_the_voice_models_live_under_the_configured_void(tmp_path):
    m = platform_paths.tts_models(str(tmp_path))
    assert m['es'] == os.path.join(str(tmp_path), 'tts', 'es_ES-sharvard-medium.onnx')
    assert set(m) == {'en', 'es', 'it'}


def test_with_no_void_the_models_fall_back_to_the_home_void():
    m = platform_paths.tts_models('')
    assert m['en'] == os.path.join(os.path.expanduser('~/void'), 'tts', 'en_GB-alan-medium.onnx')


def test_the_tts_mixin_follows_the_apps_void_dir(tmp_path):
    from tts_mixin import TtsMixin

    class A(TtsMixin):
        pass

    a = A()
    a.void_dir = str(tmp_path)
    assert a._TTS_MODELS['en'] == os.path.join(str(tmp_path), 'tts', 'en_GB-alan-medium.onnx')
    # and it is not frozen at import time: a different void gives different paths
    a.void_dir = str(tmp_path / 'otro')
    assert a._TTS_MODELS['en'].startswith(str(tmp_path / 'otro'))


def test_no_source_file_hardcodes_a_linux_temp_path():
    import glob
    here = os.path.dirname(resources.__file__)
    offenders = []
    for path in glob.glob(os.path.join(here, '*.py')):
        for n, line in enumerate(open(path, encoding='utf-8', errors='replace'), 1):
            stripped = line.strip()
            if stripped.startswith('#'):
                continue
            if "'/tmp/" in line or '"/tmp/' in line:
                offenders.append(f'{os.path.basename(path)}:{n}: {stripped[:80]}')
    assert not offenders, '\n'.join(offenders)
