"""menu_model.py — the clickable menu's content (accessibility).

Every entry is the NAME of a keybinding action: clicking it presses that key for
you, so the menu can never drift from what the keyboard does, and the hint it
shows is always the live (possibly remapped) key."""
from app_config import _parse_keybinding
from i18n import t

# Una entrada que sólo funciona en una vista lleva la vista entre paréntesis:
# el botón aprieta la tecla, y en otra vista esa tecla no hace nada.
#
# Las etiquetas salen del catálogo de idioma (i18n) CADA VEZ que se leen: cambiar el
# idioma en F10 se ve en la próxima vez que se pinta la barra, sin reconstruir nada.
_STRUCTURE = (
    ('menu.file', ('export_doc', 'print_doc', 'backup', 'commit_void', 'pick_active_file',
                   'pick_dir', 'pick_book_dir', 'open_trash', 'quit_app')),
    ('menu.views', ('view_f1', 'view_f2', 'view_f3', 'view_f4', 'view_f5', 'view_f6',
                    'view_f7', 'view_f8', 'view_f9')),
    ('menu.edit', ('scratch_toggle', 'title_toggle', 'rebase', 'reformat_file',
                   'split_spaces', 'shuffle_zero', 'collapse_paragraphs', 'dispatch',
                   'split_chapter', 'merge_book', 'gravitor')),
    ('menu.export', ('export_carousel', 'export_carousel_cover', 'carousel_view_toggle',
                     'export_sale_bundle', 'screenshot', 'circle_screenshot',
                     'open_screenshots')),
    ('menu.options', ('view_f10', 'help', 'quit', 'tts_toggle', 'typewriter_toggle',
                      'dictation_toggle')),
)


class _LiveMenus:
    """Se usa como la tupla de siempre —for, len, índices— pero se arma en el idioma
    activo cada vez que se lee."""

    @staticmethod
    def _build():
        return tuple((t(title), tuple((t('menu.item.' + action), action) for action in actions))
                     for title, actions in _STRUCTURE)

    def __iter__(self):
        return iter(self._build())

    def __len__(self):
        return len(_STRUCTURE)

    def __getitem__(self, i):
        return self._build()[i]


MENUS = _LiveMenus()

# Acciones de teclado que NO tienen botón a propósito: son movimiento fino
# (flechas, saltos de párrafo, intercambio de líneas), o no hacen nada todavía.
NOT_IN_MENU = frozenset({
    'file_prev', 'file_next', 'swap_up', 'swap_down', 'para_prev', 'para_next',
    'opacity_up', 'opacity_down', 'reshuffle',
})


def key_hint(action, keybindings):
    return keybindings.get(action, '')


def entry_key(action, keybindings):
    """(key, modifiers) to press for `action`, or None if it has no binding."""
    text = keybindings.get(action)
    if not text:
        return None
    key, mods = _parse_keybinding(text)
    return None if key is None else (key, mods)
