"""Ctrl+C en F3 copia el título junto con el cuerpo.

Federico: "when I copy a book or a chapter with ctrl + c in f3, it should copy
with the title as well... to distinguish it from the lines in f9, right now it
cojoins lines".

Antes _smart_copy en F3 copiaba el texto crudo del archivo, sin nada que dijera
de qué capítulo era. Pegado en cualquier lado —F9 incluido— era indistinguible
de cualquier otro bloque de texto.

El formato reusa el que YA existe en F3: la vista concatenada (Enter sobre un
punto) ya encabeza cada capítulo con `── STEM ──` en mayúsculas
(_book_open_concat). Uso el mismo, para no inventar un segundo formato — vive
ahora en widgets.chapter_title_header y lo usan los dos lugares.
"""
import os
import types

import pytest

from PyQt6.QtWidgets import QApplication

from line_ring import LineRing
from helpers import make_ring_app


@pytest.fixture(scope='module')
def qapp():
    yield QApplication.instance() or QApplication([])


def _app(lines, view=1):
    from new_interface import FullscreenCircleApp
    app = make_ring_app(lines)
    app.current_view = view
    app._smart_copy = types.MethodType(FullscreenCircleApp._smart_copy, app)
    app._library_current_fname = types.MethodType(
        FullscreenCircleApp._library_current_fname, app)
    return app


def test_the_header_is_the_uppercase_stem():
    from widgets import chapter_title_header
    assert chapter_title_header('Templo.txt') == '── TEMPLO ──'


def test_the_header_strips_the_extension():
    from widgets import chapter_title_header
    assert '.txt' not in chapter_title_header('algo.txt')
    assert '.TXT' not in chapter_title_header('algo.txt')


def test_copy_chapter_includes_the_title(tmp_path, qapp):
    app = _app(['.'], view=2)
    (tmp_path / 'I').mkdir(exist_ok=True)
    fpath = str(tmp_path / 'I' / 'chap.txt')
    with open(fpath, 'w', encoding='utf-8') as f:
        f.write('line one\n.\nline two\n')
    app._library_lines = ['chap.txt']
    app._library_path_cache = {'chap.txt': fpath}
    app.book_ring = LineRing(['chap'])
    app.book_ring.index = 0
    app._smart_copy()
    assert QApplication.clipboard().text() == '── CHAP ──\nline one\n.\nline two'


def test_copy_whole_book_titles_each_chapter(tmp_path, qapp):
    app = _app(['.'], view=2)
    (tmp_path / 'I').mkdir(exist_ok=True)
    a, b = str(tmp_path / 'I' / 'A.txt'), str(tmp_path / 'I' / 'B.txt')
    with open(a, 'w', encoding='utf-8') as f:
        f.write('a1\na2\n')
    with open(b, 'w', encoding='utf-8') as f:
        f.write('b1\n')
    app._library_lines = ['.', 'A.txt', 'B.txt']
    app._library_path_cache = {'A.txt': a, 'B.txt': b}
    app.book_ring = LineRing(['.', 'A', 'B'])
    app.book_ring.index = 0
    app._smart_copy()
    assert QApplication.clipboard().text() == (
        '── A ──\na1\na2\n.\n── B ──\nb1')


def test_an_empty_chapter_still_copies_its_title(tmp_path, qapp):
    """Antes un capítulo vacío no copiaba nada (texto vacío = falsy). Con el
    título, siempre hay algo que decir qué se copió."""
    app = _app(['.'], view=2)
    (tmp_path / 'I').mkdir(exist_ok=True)
    fpath = str(tmp_path / 'I' / 'Vacio.txt')
    open(fpath, 'w', encoding='utf-8').close()
    app._library_lines = ['Vacio.txt']
    app._library_path_cache = {'Vacio.txt': fpath}
    app.book_ring = LineRing(['Vacio'])
    app.book_ring.index = 0
    app._smart_copy()
    assert QApplication.clipboard().text() == '── VACIO ──'


def test_f2_copy_is_unaffected(qapp):
    """El título es cosa de F3. En F2 seguís copiando la línea/párrafo pelado."""
    app = _app(['.', 'hello', '.', 'world'], view=1)
    app.line_ring.index = 1
    app._smart_copy()
    assert QApplication.clipboard().text() == 'hello'


def test_book_open_concat_reuses_the_same_helper():
    """Que no queden dos formatos de encabezado en el código."""
    import inspect
    from new_interface import FullscreenCircleApp as App
    assert 'chapter_title_header' in inspect.getsource(App._book_open_concat)
