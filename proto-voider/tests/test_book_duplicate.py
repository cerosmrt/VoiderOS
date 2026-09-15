"""Alt+Shift+↑/↓ en F3: duplicar el capítulo resaltado, colocando la copia en
la dirección de la flecha.

Un archivo nuevo en disco con el mismo contenido, uniquificado con el mismo
patrón que ya usa la fusión de capítulos (_book_do_merge: "<name>-2.txt",
incrementando si hace falta) — y una entrada nueva en la biblioteca, al lado
de la original. El cursor sigue a la copia.

No hace nada sobre un punto (no es un capítulo) ni sobre el portal '0' (no es
un archivo).
"""
import os
import types
from unittest.mock import MagicMock

import pytest

from line_ring import LineRing


def _app(tmp_path, library, contents=None):
    from new_interface import FullscreenCircleApp

    class _App:
        pass

    app = _App()
    contents = contents or {}
    (tmp_path / 'I').mkdir(exist_ok=True)
    app.void_dir = str(tmp_path)
    app._library_lines = list(library)
    ring = ['.' if x == '.' else ('0' if x == '0.txt' else os.path.splitext(x)[0])
           for x in library]
    app.book_ring = LineRing(ring)
    app._library_path_cache = {}
    for fn in library:
        if fn in ('.', '0.txt'):
            continue
        p = str(tmp_path / 'I' / fn)
        with open(p, 'w', encoding='utf-8') as f:
            f.write('\n'.join(contents.get(fn, [os.path.splitext(fn)[0]])) + '\n')
        app._library_path_cache[fn] = p
    app.current_file_path = str(tmp_path / 'I' / '0.txt')
    app._book_pending_new = False
    app._save_library = lambda: None
    app._undo = None
    app._undo_applying = False
    app.book_view = MagicMock()
    app.book_view._offset = 0.0
    app.book_view.width.return_value = 800
    app.book_view.height.return_value = 600
    app.book_view.editor.sizeHint.return_value.height.return_value = 30
    for name in ('_book_duplicate', '_book_is_portal', '_f3_undo_begin',
                 '_f3_undo_file', '_f3_undo_commit', '_f3_state',
                 '_read_lines_or_none', '_book_show_editor'):
        if hasattr(FullscreenCircleApp, name):
            setattr(app, name, types.MethodType(getattr(FullscreenCircleApp, name), app))
    return app


def _read(p):
    with open(p, encoding='utf-8') as f:
        return [l.rstrip('\n') for l in f]


def _files(tmp_path):
    return sorted(p.name for p in (tmp_path / 'I').glob('*.txt'))


# ── el archivo ───────────────────────────────────────────────────────────────

def test_it_creates_a_new_file_with_the_same_content(tmp_path):
    app = _app(tmp_path, ['.', 'Uno.txt', 'Dos.txt'],
              contents={'Uno.txt': ['a.', 'b.']})
    app.book_ring.index = 1
    app._book_duplicate(1)
    assert 'Uno-2.txt' in _files(tmp_path)
    assert _read(str(tmp_path / 'I' / 'Uno-2.txt')) == ['a.', 'b.']


def test_the_original_is_untouched(tmp_path):
    app = _app(tmp_path, ['.', 'Uno.txt', 'Dos.txt'],
              contents={'Uno.txt': ['a.', 'b.']})
    app.book_ring.index = 1
    app._book_duplicate(1)
    assert _read(str(tmp_path / 'I' / 'Uno.txt')) == ['a.', 'b.']


def test_the_name_uniquifies_on_collision(tmp_path):
    app = _app(tmp_path, ['.', 'Uno.txt', 'Uno-2.txt'])
    app.book_ring.index = 1
    app._book_duplicate(1)
    assert 'Uno-3.txt' in _files(tmp_path)


# ── la posición ──────────────────────────────────────────────────────────────

def test_down_places_the_copy_right_after(tmp_path):
    app = _app(tmp_path, ['.', 'Uno.txt', 'Dos.txt'])
    app.book_ring.index = 1
    app._book_duplicate(1)
    assert app._library_lines == ['.', 'Uno.txt', 'Uno-2.txt', 'Dos.txt']


def test_up_places_the_copy_right_before(tmp_path):
    app = _app(tmp_path, ['.', 'Uno.txt', 'Dos.txt'])
    app.book_ring.index = 1
    app._book_duplicate(-1)
    assert app._library_lines == ['.', 'Uno-2.txt', 'Uno.txt', 'Dos.txt']


def test_the_cursor_follows_the_copy_down(tmp_path):
    app = _app(tmp_path, ['.', 'Uno.txt', 'Dos.txt'])
    app.book_ring.index = 1
    app._book_duplicate(1)
    assert app.book_ring.index == 2
    assert app.book_ring.current() == 'Uno-2'


def test_the_cursor_follows_the_copy_up(tmp_path):
    app = _app(tmp_path, ['.', 'Uno.txt', 'Dos.txt'])
    app.book_ring.index = 1
    app._book_duplicate(-1)
    assert app.book_ring.index == 1
    assert app.book_ring.current() == 'Uno-2'


# ── lo que no es un capítulo ─────────────────────────────────────────────────

def test_on_a_dot_it_does_nothing(tmp_path):
    app = _app(tmp_path, ['.', 'Uno.txt'])
    app.book_ring.index = 0
    app._book_duplicate(1)
    assert app._library_lines == ['.', 'Uno.txt']
    assert _files(tmp_path) == ['Uno.txt']


def test_on_the_scratch_portal_it_does_nothing(tmp_path):
    app = _app(tmp_path, ['.', '0.txt', 'Uno.txt'])
    app.book_ring.index = 1
    app._book_duplicate(1)
    assert app._library_lines == ['.', '0.txt', 'Uno.txt']
    assert _files(tmp_path) == ['Uno.txt']


def test_while_naming_a_pending_entry_it_does_nothing(tmp_path):
    """No duplicar a mitad de crear una entrada nueva sin nombrar."""
    app = _app(tmp_path, ['.', 'Uno.txt'])
    app.book_ring.index = 1
    app._book_pending_new = True
    app._book_duplicate(1)
    assert app._library_lines == ['.', 'Uno.txt']


# ── el cableado ──────────────────────────────────────────────────────────────

def test_the_keys_are_wired_in_f3():
    import inspect
    from key_router_mixin import KeyRouterMixin
    src = inspect.getsource(KeyRouterMixin._handle_f3_keys)
    assert '_book_duplicate' in src
