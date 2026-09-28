"""A PyInstaller --onefile .exe self-extracts to a temp folder on every launch
and deletes it on exit. CONFIG_PATH used to be computed from __file__, which
under PyInstaller points INTO that temp folder — so config.json/state.json
writes were silently lost every time the exe closed. Federico, compiling
proto-voider to voider.exe: "como hago para que persista?"

_config_dir() picks the folder next to the real .exe (sys.executable) when
frozen, and next to this source file otherwise — dev mode is unaffected.
"""
import os
import sys

import app_config


def test_dev_mode_uses_the_source_file_dir(monkeypatch):
    monkeypatch.delattr(sys, 'frozen', raising=False)
    assert app_config._config_dir() == os.path.dirname(
        os.path.abspath(app_config.__file__))


def test_frozen_mode_uses_the_exe_dir(monkeypatch, tmp_path):
    fake_exe = tmp_path / 'dist' / 'voider.exe'
    fake_exe.parent.mkdir(parents=True)
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    monkeypatch.setattr(sys, 'executable', str(fake_exe))
    assert app_config._config_dir() == str(fake_exe.parent)


def test_frozen_mode_ignores_this_source_files_own_location(monkeypatch, tmp_path):
    """The whole point: frozen must NOT fall back to __file__'s temp-extraction
    path, even though that's exactly what un-frozen mode uses."""
    fake_exe = tmp_path / 'voider.exe'
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    monkeypatch.setattr(sys, 'executable', str(fake_exe))
    source_dir = os.path.dirname(os.path.abspath(app_config.__file__))
    assert app_config._config_dir() != source_dir
