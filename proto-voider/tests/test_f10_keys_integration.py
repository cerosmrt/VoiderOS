"""F10 wiring: remaps are saved to keybindings.json and take effect right away;
capturing a key is never stolen by the app's global handlers."""
import json
import types
from unittest.mock import MagicMock

from PyQt6.QtCore import Qt

from helpers import make_ring_app


def _app(tmp_path, monkeypatch):
    import new_interface
    from new_interface import FullscreenCircleApp
    monkeypatch.setattr(new_interface, 'CONFIG_PATH', str(tmp_path / 'config.json'))
    app = make_ring_app(['.', 'a'])
    app.config = {'keybindings': dict(new_interface.DEFAULT_CONFIG['keybindings'])}
    app._kb = {}
    app.keys_view = None
    for nm in ('_on_keys_remapped', '_keys_capturing', '_rebuild_kb'):
        setattr(app, nm, types.MethodType(getattr(FullscreenCircleApp, nm), app))
    return app


def test_remap_is_saved_and_applied_live(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch)
    app._on_keys_remapped({'help': 'F5'})
    assert json.loads((tmp_path / 'keybindings.json').read_text()) == {'help': 'F5'}
    assert app.config['keybindings']['help'] == 'F5'
    assert app._kb['help'] == (Qt.Key.Key_F5, Qt.KeyboardModifier.NoModifier)


def test_reset_goes_back_to_the_default_live(tmp_path, monkeypatch):
    import new_interface
    app = _app(tmp_path, monkeypatch)
    app._on_keys_remapped({'help': 'F5'})
    app._on_keys_remapped({})
    default = new_interface.DEFAULT_CONFIG['keybindings']['help']
    assert app.config['keybindings']['help'] == default
    assert json.loads((tmp_path / 'keybindings.json').read_text()) == {}


def test_capturing_flag_follows_the_panel(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch)
    assert not app._keys_capturing()
    app.keys_view = MagicMock(capturing=True)
    app.current_view = 10
    assert app._keys_capturing()
    app.current_view = 1
    assert not app._keys_capturing()
