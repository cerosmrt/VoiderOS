"""The clickable menu (accessibility): which entries exist, and the key hint each
one shows (read from the live keybindings, so remaps show up)."""
from app_config import DEFAULT_CONFIG
from menu_model import MENUS, key_hint, entry_key


def test_menus_have_the_expected_titles():
    assert [title for title, _ in MENUS] == ['Archivo', 'Vistas', 'Exportar', 'Opciones']


def test_every_entry_points_at_a_real_keybinding_action():
    known = set(DEFAULT_CONFIG['keybindings'])
    for title, entries in MENUS:
        assert entries, title
        for label, action in entries:
            assert action in known, (title, label, action)


def test_save_export_and_quit_are_reachable():
    actions = {a for _, entries in MENUS for _, a in entries}
    assert {'export_doc', 'print_doc', 'quit_app', 'export_carousel',
            'export_sale_bundle', 'view_f10', 'help'} <= actions


def test_key_hint_reads_the_current_binding():
    kb = dict(DEFAULT_CONFIG['keybindings'], export_doc='Ctrl+K')
    assert key_hint('export_doc', kb) == 'Ctrl+K'
    assert key_hint('nope', kb) == ''


def test_entry_key_parses_the_binding_for_dispatch():
    from PyQt6.QtCore import Qt
    kb = dict(DEFAULT_CONFIG['keybindings'])
    key, mods = entry_key('export_doc', kb)
    assert key == Qt.Key.Key_S and mods == Qt.KeyboardModifier.ControlModifier
    assert entry_key('nope', kb) is None
