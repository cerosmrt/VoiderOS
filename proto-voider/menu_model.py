"""menu_model.py — the clickable menu's content (accessibility).

Every entry is the NAME of a keybinding action: clicking it presses that key for
you, so the menu can never drift from what the keyboard does, and the hint it
shows is always the live (possibly remapped) key."""
from app_config import _parse_keybinding

MENUS = (
    ('Archivo', (
        ('Exportar / guardar', 'export_doc'),
        ('Imprimir', 'print_doc'),
        ('Copia de seguridad', 'backup'),
        ('Elegir archivo', 'pick_active_file'),
        ('Elegir carpeta del void', 'pick_dir'),
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
        ('F8  Oráculo', 'view_f8'),
        ('F9  Prosa', 'view_f9'),
    )),
    ('Exportar', (
        ('Carrusel', 'export_carousel'),
        ('Portada del carrusel', 'export_carousel_cover'),
        ('Paquete de venta', 'export_sale_bundle'),
        ('Captura de pantalla', 'screenshot'),
    )),
    ('Opciones', (
        ('Configuración y teclas', 'view_f10'),
        ('Ayuda', 'help'),
        ('Bloquear', 'quit'),
        ('Máquina de escribir', 'typewriter_toggle'),
    )),
)


def key_hint(action, keybindings):
    return keybindings.get(action, '')


def entry_key(action, keybindings):
    """(key, modifiers) to press for `action`, or None if it has no binding."""
    text = keybindings.get(action)
    if not text:
        return None
    key, mods = _parse_keybinding(text)
    return None if key is None else (key, mods)
