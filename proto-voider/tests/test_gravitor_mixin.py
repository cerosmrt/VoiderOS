"""Gravitor en F3: Ctrl+G pide las palabras y la fuente, busca, y el resultado es
un archivo I/<lo-que-escribiste>.txt que F3 muestra como un capítulo más.

La interfaz (el cuadro) no se puede correr en un test; lo que sí se prueba es
todo lo que hace por debajo: buscar, crear la entrada en F3, no repetirse.
"""
import inspect
import json
import os
import random
import re
import types
from unittest.mock import MagicMock

import pytest

from line_ring import LineRing
from helpers import make_ring_app


METHODS = ('_gravitor_registry_path', '_gravitor_search', '_gravitor_add_entry',
           '_gravitor_make_entry', '_gravitor_remember_source',
           '_atomic_write_lines', '_save_library', '_library_path',
           '_gravitor_sentences', '_gravitor_finish')


def _w(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(text)


def _app(tmp_path, library=('A', 'B'), index=1, o_books=0):
    """Un F3 mínimo: library son los capítulos (nombres sin .txt), index la fila marcada."""
    from new_interface import FullscreenCircleApp
    app = make_ring_app(['.'])
    app.void_dir = str(tmp_path)
    app.o_dir = str(tmp_path / 'O')
    os.makedirs(app.o_dir, exist_ok=True)
    (tmp_path / 'I').mkdir(exist_ok=True)
    app._library_lines = ['.']
    ring = ['.']
    app._library_path_cache = {}
    for name in library:
        fn = name + '.txt'
        _w(str(tmp_path / 'I' / fn), f'.\nLa luz de {name}.\n.\nNada de eso en {name}.\n.\n')
        app._library_lines.append(fn)
        ring.append(name)
        app._library_path_cache[fn] = str(tmp_path / 'I' / fn)
    app.book_ring = LineRing(ring)
    app.book_ring.index = index
    app.config = {}
    app._undo_capture = lambda *a, **k: None
    app._ipc = None
    app.book_view = MagicMock()
    for i in range(o_books):
        _w(str(tmp_path / 'O' / f'libro{i}.txt'),
           'Primer parrafo.\n\nLa luz de la\nmañana entro. Otra frase.\n')
    app._reformat_raw_to_lines = lambda raw: [s for s in re.split(
        r'(?<=[.!?])\s+', ' '.join(raw.split())) if s]
    for nm in METHODS:
        setattr(app, nm, types.MethodType(getattr(FullscreenCircleApp, nm), app))
    return app


def _lib(app):
    return [l for l in app._library_lines]


# ── _gravitor_add_entry: el archivo y la fila en F3 ──────────────────────────

def test_the_entry_is_a_real_file_in_i_named_as_typed(tmp_path):
    app = _app(tmp_path)
    fname = app._gravitor_add_entry('luz sombra', ['.', 'Una.', '.'])
    assert fname == 'luz sombra.txt'
    with open(tmp_path / 'I' / fname, encoding='utf-8') as f:
        assert f.read().splitlines() == ['.', 'Una.', '.']


def test_the_entry_appears_in_f3_right_below_the_marked_row_and_is_selected(tmp_path):
    app = _app(tmp_path, library=('A', 'B', 'C'), index=2)      # marcada B
    app._gravitor_add_entry('luz', ['.', 'Una.', '.'])
    assert _lib(app) == ['.', 'A.txt', 'B.txt', 'luz.txt', 'C.txt']
    assert app.book_ring.lines == ['.', 'A', 'B', 'luz', 'C']
    assert app.book_ring.index == 3


def test_the_library_file_on_disk_lists_the_new_entry(tmp_path):
    app = _app(tmp_path)
    app._gravitor_add_entry('luz', ['.', 'Una.', '.'])
    with open(tmp_path / 'I.txt', encoding='utf-8') as f:
        assert 'luz.txt' in f.read().splitlines()


def test_the_path_cache_knows_the_new_file(tmp_path):
    app = _app(tmp_path)
    fname = app._gravitor_add_entry('luz', ['.', 'Una.', '.'])
    assert app._library_path_cache[fname] == str(tmp_path / 'I' / fname)


def test_a_name_already_taken_gets_a_suffix_and_nothing_is_overwritten(tmp_path):
    app = _app(tmp_path)
    first = app._gravitor_add_entry('luz', ['.', 'Primera.', '.'])
    second = app._gravitor_add_entry('luz', ['.', 'Segunda.', '.'])
    assert (first, second) == ('luz.txt', 'luz-2.txt')
    assert 'Primera.' in (tmp_path / 'I' / 'luz.txt').read_text(encoding='utf-8')
    assert 'Segunda.' in (tmp_path / 'I' / 'luz-2.txt').read_text(encoding='utf-8')


def test_it_never_overwrites_one_of_your_own_chapters(tmp_path):
    app = _app(tmp_path, library=('A', 'B'))
    original = (tmp_path / 'I' / 'A.txt').read_text(encoding='utf-8')
    fname = app._gravitor_add_entry('A', ['.', 'Otra cosa.', '.'])
    assert fname == 'A-2.txt'
    assert (tmp_path / 'I' / 'A.txt').read_text(encoding='utf-8') == original


def test_the_name_loses_the_characters_a_file_cannot_have(tmp_path):
    app = _app(tmp_path)
    fname = app._gravitor_add_entry('luz/sombra?', ['.', 'Una.', '.'])
    assert fname == 'luz_sombra_.txt'
    assert os.path.exists(tmp_path / 'I' / fname)


def test_the_file_is_registered_so_it_is_not_searched_later(tmp_path):
    app = _app(tmp_path)
    fname = app._gravitor_add_entry('luz', ['.', 'Una.', '.'])
    with open(tmp_path / '.gravitor.json', encoding='utf-8') as f:
        assert fname in json.load(f)


# ── _gravitor_make_entry: todo junto, sin el cuadro ──────────────────────────

def test_a_blank_query_does_nothing(tmp_path):
    app = _app(tmp_path)
    before = _lib(app)
    assert app._gravitor_make_entry('   ', 'i') == (None, None)
    assert _lib(app) == before


def test_searching_your_texts_creates_a_chapter_named_after_the_query(tmp_path):
    app = _app(tmp_path)
    res, fname = app._gravitor_make_entry('luz', 'i')
    assert fname == 'luz.txt'
    lines = (tmp_path / 'I' / fname).read_text(encoding='utf-8').splitlines()
    assert lines[0] == '.' and lines[-1] == '.'
    assert 'La luz de A.' in lines and 'La luz de B.' in lines
    assert 'Nada de eso en A.' not in lines
    assert res.files == 2


def test_the_query_name_keeps_its_commas_and_spaces(tmp_path):
    app = _app(tmp_path)
    _, fname = app._gravitor_make_entry('luz, nada', 'i')
    assert fname == 'luz, nada.txt'


def test_nothing_found_creates_nothing(tmp_path):
    app = _app(tmp_path)
    before = _lib(app)
    res, fname = app._gravitor_make_entry('inexistente', 'i')
    assert fname is None and res.sentences == []
    assert _lib(app) == before
    assert not (tmp_path / 'I' / 'inexistente.txt').exists()


def test_a_second_search_does_not_find_the_first_ones_results(tmp_path):
    app = _app(tmp_path)
    app._gravitor_make_entry('luz', 'i')
    res, fname = app._gravitor_make_entry('luz', 'i')
    assert fname == 'luz-2.txt'
    assert res.sentences.count('La luz de A.') == 1
    assert len(res.sentences) == 2            # A y B, no las copias de luz.txt


def test_the_corpus_search_uses_the_configured_number_of_books(tmp_path):
    app = _app(tmp_path, o_books=6)
    app.config['gravitor_books'] = 2
    res, _ = app._gravitor_make_entry('luz', 'o', rng=random.Random(1))
    assert res.books == 2


def test_the_default_number_of_books_is_three_hundred(tmp_path):
    app = _app(tmp_path, o_books=4)
    res, _ = app._gravitor_make_entry('luz', 'o', rng=random.Random(1))
    assert res.books == 4                     # hay 4; el tope por defecto no se nota
    from gravitor_mixin import DEFAULT_BOOKS
    assert DEFAULT_BOOKS == 300


def test_a_corpus_search_returns_whole_sentences(tmp_path):
    app = _app(tmp_path, o_books=1)
    res, fname = app._gravitor_make_entry('luz', 'o', rng=random.Random(1))
    assert res.sentences == ['La luz de la mañana entro.']
    assert fname == 'luz.txt'


def test_without_the_corpus_it_says_so_and_creates_nothing(tmp_path):
    app = _app(tmp_path, o_books=0)
    res, fname = app._gravitor_make_entry('luz', 'o')
    assert res.unavailable is True and fname is None


def test_both_sources_join_into_one_file(tmp_path):
    app = _app(tmp_path, o_books=1)
    res, fname = app._gravitor_make_entry('luz', 'both', rng=random.Random(1))
    lines = (tmp_path / 'I' / fname).read_text(encoding='utf-8').splitlines()
    assert 'La luz de A.' in lines and 'La luz de la mañana entro.' in lines


def test_wildcards_and_any_mode_reach_the_search(tmp_path):
    app = _app(tmp_path)
    _w(str(tmp_path / 'I' / 'C.txt'), '.\nLa gravedad.\n.\nUn cuerpo gravita.\n.\n')
    app._library_lines.append('C.txt')
    res, fname = app._gravitor_make_entry('grav*', 'i')
    assert sorted(res.sentences) == ['La gravedad.', 'Un cuerpo gravita.']


# ── recordar la última fuente ────────────────────────────────────────────────

def test_the_last_source_is_remembered_in_the_config(tmp_path, monkeypatch):
    import gravitor_mixin
    guardados = []
    monkeypatch.setattr(gravitor_mixin, '_save_config', lambda c: guardados.append(dict(c)))
    app = _app(tmp_path)
    app._gravitor_remember_source('o')
    assert app.config['gravitor_source'] == 'o'
    assert guardados and guardados[-1]['gravitor_source'] == 'o'


def test_defaults_exist_in_the_config():
    from app_config import DEFAULT_CONFIG
    assert DEFAULT_CONFIG['gravitor_source'] in ('i', 'o', 'both')
    assert DEFAULT_CONFIG['gravitor_books'] == 300


# ── la tecla, el menú, F10 y la ayuda ────────────────────────────────────────

def test_ctrl_g_is_the_default_key_and_nothing_else_uses_it():
    from app_config import DEFAULT_CONFIG
    kb = DEFAULT_CONFIG['keybindings']
    assert kb['gravitor'] == 'Ctrl+G'
    assert [a for a, k in kb.items() if k == 'Ctrl+G'] == ['gravitor']


def test_f3_routes_the_key_to_gravitor(tmp_path):
    from PyQt6.QtCore import Qt
    from new_interface import FullscreenCircleApp
    app = _app(tmp_path)
    app._kb = {'gravitor': (Qt.Key.Key_G, Qt.KeyboardModifier.ControlModifier)}
    app._matches = types.MethodType(FullscreenCircleApp._matches, app)
    app._gravitor_open = MagicMock()
    ev = MagicMock()
    FullscreenCircleApp._handle_f3_keys(app, Qt.Key.Key_G,
                                        Qt.KeyboardModifier.ControlModifier, ev)
    app._gravitor_open.assert_called_once()
    ev.accept.assert_called()


def test_the_menu_has_a_gravitor_button_that_says_it_is_for_f3():
    from menu_model import MENUS
    etiquetas = {a: l for _, es in MENUS for l, a in es}
    assert 'gravitor' in etiquetas and '(F3' in etiquetas['gravitor']


def test_f10_can_set_the_number_of_books():
    from keys_model import SETTING_DEFS
    d = {s.key: s for s in SETTING_DEFS}['gravitor_books']
    assert d.kind == 'int' and d.lo >= 1 and d.hi >= 300


def test_the_help_screen_mentions_it():
    from help_overlay import HELP
    assert any('Ctrl+G' in k and 'ravitor' in (d or '') for k, d in HELP)


def test_gravitor_open_only_calls_methods_that_exist():
    """El cuadro de Qt no se puede correr en un test: un nombre mal escrito adentro
    explotaría recién al apretar Ctrl+G (pasó con commit_void_repo en Ctrl+B)."""
    from new_interface import FullscreenCircleApp
    fuente = inspect.getsource(FullscreenCircleApp._gravitor_open)
    llamados = set(re.findall(r'self\.(_?[a-zA-Z_][a-zA-Z0-9_]*)\(', fuente))
    faltantes = [n for n in sorted(llamados) if not hasattr(FullscreenCircleApp, n)]
    assert not faltantes, f'_gravitor_open llama a métodos inexistentes: {faltantes}'


def test_gravitor_open_is_ignored_while_a_new_entry_is_being_typed(tmp_path):
    """Con una fila fantasma abierta, insertar otra fila movería los índices."""
    from new_interface import FullscreenCircleApp
    app = _app(tmp_path)
    app._book_pending_new = True
    app._book_pending_merge = False
    app._gravitor_dialog = MagicMock()
    FullscreenCircleApp._gravitor_open(app)
    app._gravitor_dialog.assert_not_called()


# ── el caso real: un archivo de I/ en prosa (una línea = un párrafo), con CRLF ─

def test_your_prose_files_give_sentences_not_whole_paragraphs(tmp_path):
    app = _app(tmp_path, library=('A',))
    _w(str(tmp_path / 'I' / 'Prosa.txt'),
       '\r\nSi te invitan a una casa, primero miras la casa. A las reglas me adapto. '
       'Ahi actuo a su vision del mundo. Todo a partir de lo que me dicen.\r\n')
    app._library_lines.append('Prosa.txt')
    res, fname = app._gravitor_make_entry('vision', 'i')
    assert res.sentences == ['Ahi actuo a su vision del mundo.']
    lines = (tmp_path / 'I' / fname).read_text(encoding='utf-8').splitlines()
    assert lines == ['.', 'Ahi actuo a su vision del mundo.', '.']


def test_every_line_of_the_file_has_the_word_with_the_real_splitter(tmp_path):
    """Con el separador de F6 de verdad (no el de los tests)."""
    from new_interface import FullscreenCircleApp
    app = _app(tmp_path, library=('A',))
    app._reformat_raw_to_lines = types.MethodType(
        FullscreenCircleApp._reformat_raw_to_lines, app)
    _w(str(tmp_path / 'I' / 'Prosa.txt'),
       'Aca esta lo que decia de la division que se produjo. Nada de eso aqui. '
       'Una vision clara de las cosas. Y nada mas que decir.\n')
    app._library_lines.append('Prosa.txt')
    res, fname = app._gravitor_make_entry('vision', 'i')
    assert res.sentences == ['Una vision clara de las cosas.']
    body = [l for l in (tmp_path / 'I' / fname).read_text(encoding='utf-8').splitlines()
            if l != '.']
    assert all('vision' in l.lower() for l in body)
