"""Los libros de O/ se pueden editar, y sacarles una línea la cosecha a 0.txt.

La idea es leer un libro desmontándolo: lo que te sirve se lo sacás y queda en
el scratch; el libro se gasta a medida que lo usás.

Dos cosas decididas con Federico:
  * es DESTRUCTIVO. La línea se va del libro. O/ está en .gitignore y es un
    symlink a /mnt/data — no hay git, no hay snapshot, no hay vuelta.
  * editar un libro lo REESCRIBE en formato Voider. Lo que ves en F6 ya venía
    transformado (strip de Gutenberg + reformat a una oración por línea), así
    que el primer guardado convierte el archivo. Verificado sobre tres libros
    suyos que la secuencia de palabras es idéntica: reacomoda, no pierde.
"""
import os
import types
import pytest
from unittest.mock import MagicMock

pytest.importorskip("PyQt6")
from line_ring import LineRing


def _read(p):
    with open(p, encoding='utf-8') as f:
        return [l.rstrip('\n') for l in f]


def _app(tmp_path, book_lines=('.', 'primera del libro.', 'segunda del libro.',
                               '.', 'tercera.')):
    from new_interface import FullscreenCircleApp as App

    class _App:
        pass
    a = _App()
    o = tmp_path / 'O'
    o.mkdir()
    book = o / 'Libro.txt'
    book.write_text('\n'.join(book_lines) + '\n', encoding='utf-8')
    (tmp_path / 'I').mkdir()
    a.f1_file = str(tmp_path / 'I' / '0.txt')
    open(a.f1_file, 'w').close()

    a.void_dir = str(tmp_path)
    a.o_dir = str(o)
    a.o_reader_file = str(book)
    a.o_reader_ring = LineRing(list(book_lines))
    a.o_reader_view = MagicMock()
    a.o_reader_ring.index = 1
    a._ws_books = [{'path': 'Libro.txt', 'position': 1}]
    a._ws_save_position = MagicMock()
    a._tts_cut = MagicMock()
    a._undo = None                       # sin undo en el mock: _undo_capture no-opea
    a.load_doc_lines = MagicMock()
    a.current_file_path = a.f1_file

    for n in ('_reader_save', '_reader_live_save', '_reader_harvest_line',
              '_atomic_write_lines', '_undo_capture', '_rescue_on_large_shrink'):
        if hasattr(App, n):
            setattr(a, n, types.MethodType(getattr(App, n), a))
    return a, str(book)


# ── escribir en el libro ─────────────────────────────────────────────────────

def test_typing_reaches_the_book_on_disk(tmp_path):
    a, book = _app(tmp_path)
    a._reader_live_save('primera CAMBIADA.')
    assert 'primera CAMBIADA.' in _read(book)


def test_typing_does_not_touch_zero(tmp_path):
    """Editar no es cosechar: 0.txt sólo recibe lo que sacás a propósito."""
    a, book = _app(tmp_path)
    a._reader_live_save('otra cosa.')
    assert _read(a.f1_file) == []


def test_an_empty_edit_is_ignored(tmp_path):
    """Igual que en F2: borrar todo el renglón no vacía la línea del libro."""
    a, book = _app(tmp_path)
    a._reader_live_save('   ')
    assert 'primera del libro.' in _read(book)


def test_nothing_happens_with_no_book_open(tmp_path):
    a, book = _app(tmp_path)
    a.o_reader_file = None
    a._reader_live_save('algo.')       # no tiene que explotar
    assert _read(book)[1] == 'primera del libro.'


# ── cosechar una línea ───────────────────────────────────────────────────────

def test_harvest_appends_the_line_to_zero(tmp_path):
    a, book = _app(tmp_path)
    a._reader_harvest_line()
    assert 'primera del libro.' in _read(a.f1_file)


def test_harvest_removes_the_line_from_the_book(tmp_path):
    """Destructivo, como lo pidió: el libro se gasta."""
    a, book = _app(tmp_path)
    a._reader_harvest_line()
    assert 'primera del libro.' not in _read(book)
    assert 'segunda del libro.' in _read(book)


def test_harvest_leaves_the_caret_on_a_real_line(tmp_path):
    a, book = _app(tmp_path)
    a._reader_harvest_line()
    assert a.o_reader_ring.current() != '.'


def test_a_dot_is_never_harvested(tmp_path):
    """Los puntos son estructura del libro, no texto que quieras."""
    a, book = _app(tmp_path)
    a.o_reader_ring.index = 0
    a._reader_harvest_line()
    assert _read(a.f1_file) == []


def test_harvesting_the_last_line_does_not_empty_the_book(tmp_path):
    a, book = _app(tmp_path, book_lines=('.', 'la unica.'))
    a.o_reader_ring.index = 1
    a._reader_harvest_line()
    assert _read(book) != []


def test_harvest_with_no_book_open_is_a_noop(tmp_path):
    a, book = _app(tmp_path)
    a.o_reader_file = None
    a._reader_harvest_line()
    assert _read(a.f1_file) == []


# ── la vista deja editar ─────────────────────────────────────────────────────

def test_the_reader_editor_is_no_longer_read_only():
    import inspect
    from new_interface import FullscreenCircleApp as App
    src = inspect.getsource(App._reader_show_editor)
    assert 'setReadOnly(True)' not in src, 'F6 sigue siendo de sólo lectura'
    assert 'setReadOnly' in src, 'los puntos sí tienen que quedar bloqueados'


def test_the_editor_is_wired_for_typing_and_harvest():
    import inspect
    from new_interface import FullscreenCircleApp as App
    src = inspect.getsource(App.switch_to_view)
    assert '_reader_live_save' in src
    assert '_reader_harvest_line' in src
