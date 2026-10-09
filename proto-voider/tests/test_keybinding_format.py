"""Turn a pressed key back into the text stored in keybindings.json, and save
only the user's remaps there."""
import json

from PyQt6.QtCore import Qt

from app_config import (DEFAULT_CONFIG, _parse_keybinding, _format_keybinding,
                        _save_key_overrides, _load_key_overrides)

K, M = Qt.Key, Qt.KeyboardModifier


def test_format_simple_and_modified_keys():
    assert _format_keybinding(K.Key_F3, M.NoModifier) == 'F3'
    assert _format_keybinding(K.Key_F, M.ControlModifier | M.ShiftModifier) == 'Ctrl+Shift+F'
    assert _format_keybinding(K.Key_Up, M.AltModifier) == 'Alt+Up'
    assert _format_keybinding(K.Key_QuoteLeft, M.NoModifier) == '`'


def test_every_default_binding_round_trips():
    for action, text in DEFAULT_CONFIG['keybindings'].items():
        key, mods = _parse_keybinding(text)
        assert key is not None, action
        assert _parse_keybinding(_format_keybinding(key, mods)) == (key, mods), action


def test_unparseable_key_is_refused():
    # Home isn't in the key map, so it could never be loaded back.
    assert _format_keybinding(K.Key_Home, M.NoModifier) is None


def test_bare_modifier_press_is_refused():
    assert _format_keybinding(K.Key_Control, M.ControlModifier) is None
    assert _format_keybinding(K.Key_Shift, M.ShiftModifier) is None


def test_save_overrides_round_trip_and_only_changes(tmp_path):
    path = str(tmp_path / 'config.json')
    _save_key_overrides(path, {'help': 'F1'})
    assert json.loads((tmp_path / 'keybindings.json').read_text()) == {'help': 'F1'}
    assert _load_key_overrides(path) == {'help': 'F1'}


def test_overrides_equal_to_default_are_not_written(tmp_path):
    path = str(tmp_path / 'config.json')
    default_help = DEFAULT_CONFIG['keybindings']['help']
    _save_key_overrides(path, {'help': default_help, 'view_f2': 'F6'})
    assert json.loads((tmp_path / 'keybindings.json').read_text()) == {'view_f2': 'F6'}
