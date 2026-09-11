"""Mandar desde F2 a otro capítulo, sin salir de F2.

Esto no existía en el Python — sólo en el mirror de Rust. Lo más parecido vivía
en F5, que tiene el panel de capítulos (filtrado, orden de biblioteca, crear uno
nuevo si el nombre no existe). Acá se reusa ese panel desde F2.

EL ALCANCE lo decide dónde estás parado, la misma regla que Ctrl+C, Ctrl+Shift+E
y el Ctrl+Delete de F6: sobre una línea va esa línea; sobre un punto va el
párrafo entero que ese punto abre.

LAS TECLAS, reconciliando las dos respuestas de Federico (que se contradecían):
  * Alt+←/→ sobre un PUNTO abre el panel y manda el párrafo.
  * Alt+←/→ sobre una LÍNEA sigue moviendo la palabra, como siempre.
  * Alt+Shift+←/→ abre el panel desde donde sea, línea o párrafo.
La flecha decide de qué lado sale el panel.

Y es un MOVER, no un copiar: el texto se va del archivo de origen. Igual que en
F5. Con snapshot de git y un solo paso de undo.
"""
import os
import types
import pytest
from unittest.mock import MagicMock

pytest.importorskip("PyQt6")

from line_ring import LineRing
from helpers import make_ring_app


def _read(p):
    with open(p, encoding='utf-8') as f:
        return [l.rstrip('\n') for l in f]


def _app(tmp_path, lines=('.', 'uno.', 'dos.', '.', 'tres.'), idx=1):
    from new_interface import FullscreenCircleApp as App

    i_dir = tmp_path / 'I'
    i_dir.mkdir(exist_ok=True)
    src = i_dir / '0.txt'
    src.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    dst = i_dir / 'Destino.txt'
    dst.write_text('.\nya estaba.\n', encoding='utf-8')

    a = make_ring_app(list(lines), tmp_file=str(src))
    a.void_dir = str(tmp_path)
    a.f1_file = str(src)
    a.current_file_path = str(src)
    a.line_ring = LineRing(list(lines))
    a.line_ring.index = idx
    a._library_lines = ['.', '0.txt', 'Destino.txt', 'Otro.txt']
    a._library_path_cache = {'0.txt': str(src), 'Destino.txt': str(dst),
                             'Otro.txt': str(i_dir / 'Otro.txt')}
    (i_dir / 'Otro.txt').write_text('.\n', encoding='utf-8')

    for n in ('_doc_send_scope', '_doc_send_to', '_doc_open_picker',
              '_doc_close_picker', '_atomic_write_lines', '_f5_collapse_dots',
              '_f5_pick_matches', '_f5_pick_target', '_f5_pick_start_idx',
              '_undo_capture', '_rescue_on_large_shrink', 'auto_save_circular'):
        if hasattr(App, n):
            setattr(a, n, types.MethodType(getattr(App, n), a))
    a._undo = None
    a._undo_begin = MagicMock()
    a._undo_commit = MagicMock()
    a._git_snapshot_void = MagicMock()
    a._doc_refresh_editor = MagicMock()
    a._doc_refresh_picker = MagicMock()
    a._doc_picker_open = False
    a._doc_picker_side = 'right'
    a._doc_show_editor = MagicMock()
    a.load_doc_lines = MagicMock()
    a._f5_picker_open = False
    a._f5_pick_filter = ''
    a._f5_pick_match_idx = 0
    return a, str(src), str(dst)


# ── el alcance ───────────────────────────────────────────────────────────────

def test_on_a_line_the_scope_is_that_line(tmp_path):
    a, src, dst = _app(tmp_path, idx=1)
    assert a._doc_send_scope() == (['uno.'], [1])


def test_on_a_dot_the_scope_is_the_whole_paragraph(tmp_path):
    a, src, dst = _app(tmp_path, idx=0)
    lineas, idxs = a._doc_send_scope()
    assert lineas == ['uno.', 'dos.']
    assert idxs == [0, 1, 2]          # el punto se va con su párrafo


def test_a_dot_with_nothing_under_it_has_no_scope(tmp_path):
    a, src, dst = _app(tmp_path, lines=('.', '.', 'algo.'), idx=0)
    lineas, _ = a._doc_send_scope()
    assert lineas == []


def test_the_scope_stops_at_the_next_dot(tmp_path):
    a, src, dst = _app(tmp_path, idx=3)     # el segundo punto
    lineas, _ = a._doc_send_scope()
    assert lineas == ['tres.']


# ── el envío ─────────────────────────────────────────────────────────────────

def test_the_paragraph_lands_in_the_target(tmp_path):
    a, src, dst = _app(tmp_path, idx=0)
    a._doc_send_to('Destino.txt')
    texto = '\n'.join(_read(dst))
    assert 'uno.' in texto and 'dos.' in texto
    assert 'ya estaba.' in texto, 'no puede pisar lo que ya había'


def test_it_leaves_the_source(tmp_path):
    """Es un MOVER, no un copiar. Igual que en F5."""
    a, src, dst = _app(tmp_path, idx=0)
    a._doc_send_to('Destino.txt')
    texto = '\n'.join(_read(src))
    assert 'uno.' not in texto and 'dos.' not in texto
    assert 'tres.' in texto, 'el resto del archivo queda'


def test_a_single_line_goes_alone(tmp_path):
    a, src, dst = _app(tmp_path, idx=1)
    a._doc_send_to('Destino.txt')
    assert 'uno.' in '\n'.join(_read(dst))
    assert 'dos.' not in '\n'.join(_read(dst))
    assert 'dos.' in '\n'.join(_read(src))


def test_a_dot_separates_it_from_what_was_there(tmp_path):
    a, src, dst = _app(tmp_path, idx=1)
    a._doc_send_to('Destino.txt')
    lineas = _read(dst)
    assert lineas.index('.') < lineas.index('uno.')


def test_sending_to_itself_does_nothing(tmp_path):
    a, src, dst = _app(tmp_path, idx=1)
    antes = _read(src)
    assert a._doc_send_to('0.txt') is False
    assert _read(src) == antes


def test_the_source_never_ends_up_empty(tmp_path):
    a, src, dst = _app(tmp_path, lines=('.', 'la unica.'), idx=1)
    a._doc_send_to('Destino.txt')
    assert _read(src) != []


def test_no_double_dots_are_left_in_the_source(tmp_path):
    a, src, dst = _app(tmp_path, idx=0)
    a._doc_send_to('Destino.txt')
    lineas = _read(src)
    for i in range(len(lineas) - 1):
        assert not (lineas[i] == '.' and lineas[i + 1] == '.'), lineas


def test_it_is_one_undo_step_with_a_snapshot(tmp_path):
    a, src, dst = _app(tmp_path, idx=1)
    a._doc_send_to('Destino.txt')
    assert a._undo_begin.called and a._undo_commit.called
    assert a._git_snapshot_void.called, '/void se toca: va con snapshot'


def test_an_unknown_target_does_nothing(tmp_path):
    a, src, dst = _app(tmp_path, idx=1)
    antes = _read(src)
    assert a._doc_send_to('NoExiste.txt') is False
    assert _read(src) == antes


# ── el panel ─────────────────────────────────────────────────────────────────

def test_the_picker_opens_on_the_side_you_point(tmp_path):
    a, src, dst = _app(tmp_path, idx=0)
    a._doc_open_picker('left')
    assert a._doc_picker_side == 'left'
    a._doc_close_picker()
    a._doc_open_picker('right')
    assert a._doc_picker_side == 'right'


def test_the_picker_does_not_open_with_nothing_to_send(tmp_path):
    a, src, dst = _app(tmp_path, lines=('.', '.', 'x.'), idx=0)
    a._doc_open_picker('right')
    assert not a._doc_picker_open


def test_the_picker_lists_the_file_you_are_in(tmp_path):
    """Cambió a propósito: el activo aparece para que el panel pueda abrir
    parado ahí, y confirmar sin moverse no mande nada. Ver
    test_picker_parks_home.py. Acá el activo es 0.txt."""
    a, src, dst = _app(tmp_path, idx=1)
    a._doc_open_picker('right')
    nombres = [f for f, _ in a._f5_pick_matches()]
    assert '0.txt' in nombres
    assert 'Destino.txt' in nombres


# ── que el panel se dibuje sin explotar ──────────────────────────────────────
# Los tests de arriba prueban la lógica; ninguno pinta. Un paintEvent que tira
# una excepción no rompe los tests pero sí la vista.

@pytest.mark.parametrize("side", ['left', 'right'])
@pytest.mark.parametrize("matches,filtro,is_new", [
    (['Capitulo uno', 'Capitulo dos'], '', False),
    ([], 'NombreNuevo', True),
    ([], '', False),                       # sin candidatos: el 'ø'
    ([f'Cap {i}' for i in range(200)], 'cap', False),
])
def test_the_picker_paints(qapp_for_paint, side, matches, filtro, is_new):
    from PyQt6.QtGui import QPixmap, QPainter
    from circular_view import CircularView
    from line_ring import LineRing

    v = CircularView(LineRing(['.', 'una linea.', 'otra.']))
    v.resize(1200, 800)
    v.set_picker_state(True, filtro, matches, 0, is_new, 'NombreNuevo', side)
    pm = QPixmap(1200, 800)
    pm.fill()
    p = QPainter(pm)
    try:
        v.render(pm)          # dispara paintEvent de verdad
    finally:
        p.end()


def test_a_tiny_window_does_not_crash_the_picker(qapp_for_paint):
    from PyQt6.QtGui import QPixmap
    from circular_view import CircularView
    from line_ring import LineRing
    v = CircularView(LineRing(['.', 'x.']))
    v.resize(40, 30)
    v.set_picker_state(True, '', ['uno'], 0, False, '', 'right')
    v.render(QPixmap(40, 30))


@pytest.fixture(scope="module")
def qapp_for_paint():
    from PyQt6.QtWidgets import QApplication
    yield QApplication.instance() or QApplication([])
