"""menu_model.py — the clickable menu's content (accessibility).

Every entry is the NAME of a keybinding action: clicking it presses that key for
you, so the menu can never drift from what the keyboard does, and the hint it
shows is always the live (possibly remapped) key."""
from app_config import _parse_keybinding

# Una entrada que sólo funciona en una vista lleva la vista entre paréntesis:
# el botón aprieta la tecla, y en otra vista esa tecla no hace nada.
MENUS = (
    ('Archivo', (
        ('Exportar / guardar', 'export_doc'),
        ('Imprimir', 'print_doc'),
        ('Copia de seguridad', 'backup'),
        ('Guardar versión del void', 'commit_void'),
        ('Elegir archivo', 'pick_active_file'),
        ('Elegir carpeta del void', 'pick_dir'),
        ('Elegir carpeta de libros', 'pick_book_dir'),
        ('Tacho', 'open_trash'),
        ('Salir', 'quit_app'),
    )),
    ('Vistas', (
        ('F1  Escribir', 'view_f1'),
        ('F2  Documento', 'view_f2'),
        ('F3  Biblioteca', 'view_f3'),
        ('F4  Libro', 'view_f4'),
        ('F5  Párrafos', 'view_f5'),
        ('F6  Lector', 'view_f6'),
        ('F7  Corpus', 'view_f7'),
        ('F8  Libros', 'view_f8'),
        ('F9  Prosa', 'view_f9'),
    )),
    ('Edición', (
        ('Ir al cuaderno y volver', 'scratch_toggle'),
        ('Título fijo arriba', 'title_toggle'),
        ('Poner al inicio (F2)', 'rebase'),
        ('Reformatear archivo (F2)', 'reformat_file'),
        ('Separar por espacios (F2)', 'split_spaces'),
        ('Mezclar el cuaderno (F2)', 'shuffle_zero'),
        ('Juntar en un párrafo (F2)', 'collapse_paragraphs'),
        ('Repartir párrafos (F2)', 'dispatch'),
        ('Cortar capítulo (F2 / F3)', 'split_chapter'),
        ('Unir libro (F3)', 'merge_book'),
        ('Gravitor: oraciones con palabras (F3)', 'gravitor'),
    )),
    ('Exportar', (
        ('Carrusel', 'export_carousel'),
        ('Portada del carrusel', 'export_carousel_cover'),
        ('Vista previa del carrusel (F4)', 'carousel_view_toggle'),
        ('Paquete de venta', 'export_sale_bundle'),
        ('Captura de pantalla', 'screenshot'),
        ('Captura del círculo', 'circle_screenshot'),
        ('Carpeta de capturas', 'open_screenshots'),
    )),
    ('Opciones', (
        ('Configuración y teclas', 'view_f10'),
        ('Ayuda', 'help'),
        ('Bloquear', 'quit'),
        ('Leer en voz alta', 'tts_toggle'),
        ('Máquina de escribir', 'typewriter_toggle'),
        ('Dictado (hablar para escribir)', 'dictation_toggle'),
    )),
)

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
