"""First run with no void_dir in config.json used to force a blocking
QFileDialog — Cancel it and the app called sys.exit(0). Federico: wants the
compiled .exe to be "double-click and go", no dialog on first use.

Now, with no valid void_dir configured, __init__ auto-creates <config's own
folder>/void (same _config_dir() app_config.py already uses for CONFIG_PATH
itself — dev mode and a frozen exe both resolve correctly, for free) and
keeps booting. The manual picker (_pick_void_directory / change_void_directory,
Ctrl+F4) is untouched — it's just no longer forced at startup.
"""
import json
import os
import uuid
from unittest.mock import MagicMock

import pytest

pytest.importorskip("PyQt6")
from PyQt6.QtWidgets import QApplication


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


def _write_config(cfg):
    import app_config
    with open(app_config.CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f)


def _unique_ipc(monkeypatch):
    import ipc
    monkeypatch.setattr(ipc, "_SERVER_NAME", f"voider_test_{uuid.uuid4().hex}")


def test_missing_void_dir_autocreates_without_a_dialog(qapp, monkeypatch):
    _unique_ipc(monkeypatch)
    _write_config({"font_family": "Consolas", "font_size": 11, "keybindings": {}})

    from new_interface import FullscreenCircleApp, CONFIG_PATH
    # If the old forced-dialog path ran, this would fail the test outright
    # instead of silently doing the real (offscreen, auto-cancelling) thing.
    monkeypatch.setattr(
        FullscreenCircleApp, '_pick_void_directory',
        MagicMock(side_effect=AssertionError(
            "dialog must not be forced on first run")))
    app = FullscreenCircleApp()

    try:
        expected = os.path.join(os.path.dirname(os.path.abspath(CONFIG_PATH)), 'void')
        assert app.void_dir == expected
        assert os.path.isdir(app.void_dir)
    finally:
        app.close()


def test_the_autocreated_dir_is_saved_back_to_config(qapp, monkeypatch):
    _unique_ipc(monkeypatch)
    _write_config({"font_family": "Consolas", "font_size": 11, "keybindings": {}})

    from new_interface import FullscreenCircleApp, CONFIG_PATH, _load_config
    app = FullscreenCircleApp()
    try:
        saved = _load_config()
        assert saved['void_dir'] == app.void_dir
    finally:
        app.close()


def test_an_existing_valid_void_dir_is_left_alone(qapp, monkeypatch, tmp_path):
    _unique_ipc(monkeypatch)
    real_void = tmp_path / "my-real-void"
    real_void.mkdir()
    _write_config({"void_dir": str(real_void), "font_family": "Consolas",
                   "font_size": 11, "keybindings": {}})

    from new_interface import FullscreenCircleApp
    app = FullscreenCircleApp()
    try:
        assert app.void_dir == str(real_void)
    finally:
        app.close()


def test_manual_picker_still_works_for_changing_it_later(qapp, monkeypatch, tmp_path):
    """Ctrl+F4 (change_void_directory) — untouched by this fix."""
    _unique_ipc(monkeypatch)
    _write_config({"font_family": "Consolas", "font_size": 11, "keybindings": {}})

    from new_interface import FullscreenCircleApp
    app = FullscreenCircleApp()
    try:
        chosen = str(tmp_path / "picked-by-hand")
        os.makedirs(chosen, exist_ok=True)
        app._pick_void_directory = MagicMock(return_value=chosen)
        app.change_void_directory()
        assert app.void_dir == chosen
    finally:
        app.close()
