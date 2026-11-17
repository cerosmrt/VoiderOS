"""The clickable menu (accessibility): which entries exist, and the key hint each
one shows (read from the live keybindings, so remaps show up)."""
from app_config import DEFAULT_CONFIG
from menu_model import MENUS, NOT_IN_MENU, key_hint, entry_key


def test_menus_have_the_expected_titles():
    assert [title for title, _ in MENUS] == ['Archivo', 'Vistas', 'Edición', 'Exportar', 'Opciones']


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


def _menu_actions():
    return {a for _, entries in MENUS for _, a in entries}


def test_every_keybinding_action_has_a_button_or_is_explicitly_left_out():
    """Para que una acción nueva no se quede sin botón sin que nadie lo decida."""
    known = set(DEFAULT_CONFIG['keybindings'])
    sin_boton = known - _menu_actions() - NOT_IN_MENU
    assert not sin_boton, f'acciones sin botón ni excepción: {sorted(sin_boton)}'


def test_the_exclusions_are_real_actions_and_not_already_in_the_menu():
    known = set(DEFAULT_CONFIG['keybindings'])
    assert NOT_IN_MENU <= known
    assert not (NOT_IN_MENU & _menu_actions())


def test_the_buttons_that_were_missing_are_there():
    assert {'commit_void', 'pick_book_dir', 'open_trash', 'tts_toggle',
            'scratch_toggle', 'title_toggle', 'reformat_file', 'split_spaces',
            'shuffle_zero', 'collapse_paragraphs', 'dispatch', 'split_chapter',
            'merge_book', 'rebase', 'carousel_view_toggle', 'circle_screenshot',
            'open_screenshots'} <= _menu_actions()


def test_an_entry_that_only_works_in_one_view_says_which():
    en_vista = {'reformat_file': 'F2', 'split_spaces': 'F2', 'shuffle_zero': 'F2',
                'collapse_paragraphs': 'F2', 'dispatch': 'F2', 'rebase': 'F2',
                'merge_book': 'F3', 'carousel_view_toggle': 'F4'}
    etiquetas = {a: label for _, entries in MENUS for label, a in entries}
    for accion, vista in en_vista.items():
        assert f'({vista}' in etiquetas[accion], (accion, etiquetas[accion])


def test_no_action_appears_twice():
    todas = [a for _, entries in MENUS for _, a in entries]
    assert len(todas) == len(set(todas))
