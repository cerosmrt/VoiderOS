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
    for nm in ('_on_keys_remapped', '_keys_capturing', '_rebuild_kb',
               '_on_setting_changed', '_apply_font_settings'):
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
    app.keys_view = MagicMock(busy=True)
    app.current_view = 10
    assert app._keys_capturing()
    app.current_view = 1
    assert not app._keys_capturing()


def test_setting_change_is_saved_and_font_applied_without_leaving_f10(tmp_path, monkeypatch):
    import new_interface
    from PyQt6.QtGui import QFont
    app = _app(tmp_path, monkeypatch)
    saved = []
    monkeypatch.setattr(new_interface, '_save_config', lambda cfg: saved.append(dict(cfg)))
    editor_view = MagicMock()
    app.circular_view = editor_view
    app.book_view = app.o_reader_view = app.o_browser_view = None
    app.oracle_o_view = app.metronome_view = app.book_concat_view = app.scratch_view = None
    app.entry = MagicMock()
    app.switch_to_view = MagicMock()
    app.config.update({'font_family': 'Georgia', 'font_size': 12})
    app._on_setting_changed('font_size', 30)
    assert app.config['font_size'] == 30 and saved
    assert isinstance(editor_view.editor.setFont.call_args[0][0], QFont)
    assert editor_view.editor.setFont.call_args[0][0].pointSize() == 30
    app.switch_to_view.assert_not_called()               # stays on the list


def test_non_font_setting_only_saves(tmp_path, monkeypatch):
    import new_interface
    app = _app(tmp_path, monkeypatch)
    saved = []
    monkeypatch.setattr(new_interface, '_save_config', lambda cfg: saved.append(dict(cfg)))
    app.switch_to_view = MagicMock()
    app._on_setting_changed('carousel_preset', '1:1')
    assert app.config['carousel_preset'] == '1:1' and saved
    app.switch_to_view.assert_not_called()


# ── menú clicable ────────────────────────────────────────────────────────────

def test_menu_trigger_presses_the_actions_key(tmp_path, monkeypatch):
    import new_interface
    from new_interface import FullscreenCircleApp
    app = _app(tmp_path, monkeypatch)
    app._menu_trigger = types.MethodType(FullscreenCircleApp._menu_trigger, app)
    app._refocus_active_editor = MagicMock()
    pressed = []
    app.keyPressEvent = lambda ev: pressed.append((ev.key(), ev.modifiers()))
    app._menu_trigger('export_doc')                         # Ctrl+S
    assert pressed == [(Qt.Key.Key_S, Qt.KeyboardModifier.ControlModifier)]
    app._refocus_active_editor.assert_called()


def test_menu_trigger_ignores_unbound_actions(tmp_path, monkeypatch):
    from new_interface import FullscreenCircleApp
    app = _app(tmp_path, monkeypatch)
    app._menu_trigger = types.MethodType(FullscreenCircleApp._menu_trigger, app)
    app._refocus_active_editor = MagicMock()
    app.keyPressEvent = MagicMock()
    app._menu_trigger('does_not_exist')
    app.keyPressEvent.assert_not_called()


def test_remap_updates_the_menu_hints(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch)
    app._menu_bar = MagicMock()
    app._on_keys_remapped({'export_doc': 'Ctrl+K'})
    app._menu_bar.set_keybindings.assert_called()
    assert app._menu_bar.set_keybindings.call_args[0][0]['export_doc'] == 'Ctrl+K'
