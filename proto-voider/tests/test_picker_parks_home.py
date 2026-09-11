"""El panel abre parado en el capítulo donde ya estás.

Federico: "i think actual chapter should be shown (so if i close back to f2
nothing happens), right now it gets selected and the paragraph sends to the next
chapter".

El panel excluía el archivo activo de la lista, así que abría parado en el
capítulo VECINO — y un Enter distraído te mandaba el párrafo ahí. Ahora el
activo aparece y el panel abre sobre él: confirmar sin moverse no hace nada,
porque mandar a uno mismo ya era un no-op. El resguardo sale gratis.

Sólo cambia para F2. En F5 el panel sigue como estaba: ahí se abre con Right
como un gesto deliberado de enviar, y no me lo pidió.
"""
import os
import types
import pytest
from unittest.mock import MagicMock

pytest.importorskip("PyQt6")
from line_ring import LineRing
from helpers import make_ring_app


def _app(tmp_path, activo='Medio.txt'):
    from new_interface import FullscreenCircleApp as App
    i_dir = tmp_path / 'I'
    i_dir.mkdir(exist_ok=True)
    for n in ('Antes.txt', 'Medio.txt', 'Despues.txt'):
        (i_dir / n).write_text('.\ncontenido.\n', encoding='utf-8')
    (i_dir / '0.txt').write_text('.\n', encoding='utf-8')

    a = make_ring_app(['.', 'uno.', 'dos.'], tmp_file=str(i_dir / activo))
    a.void_dir = str(tmp_path)
    a.f1_file = str(i_dir / '0.txt')
    a.current_file_path = str(i_dir / activo)
    a.line_ring = LineRing(['.', 'uno.', 'dos.'])
    a.line_ring.index = 0
    a._library_lines = ['.', '0.txt', 'Antes.txt', 'Medio.txt', 'Despues.txt']
    a._library_path_cache = {n: str(i_dir / n) for n in
                             ('0.txt', 'Antes.txt', 'Medio.txt', 'Despues.txt')}
    for n in ('_doc_open_picker', '_doc_close_picker', '_doc_send_scope',
              '_doc_send_to', '_f5_pick_matches', '_f5_pick_target',
              '_f5_pick_start_idx', '_atomic_write_lines', '_f5_collapse_dots',
              '_undo_capture', 'auto_save_circular', '_rescue_on_large_shrink'):
        if hasattr(App, n):
            setattr(a, n, types.MethodType(getattr(App, n), a))
    a._undo = None
    a._undo_begin = MagicMock(); a._undo_commit = MagicMock()
    a._git_snapshot_void = MagicMock()
    a._doc_refresh_picker = MagicMock(); a._doc_refresh_editor = MagicMock()
    a.load_doc_lines = MagicMock()
    a._doc_picker_open = False
    a._doc_picker_side = 'right'
    a._f5_pick_filter = ''
    a._f5_pick_match_idx = 0
    a._pick_include_self = False
    return a


def _elegido(a):
    m = a._f5_pick_matches()
    return m[a._f5_pick_match_idx % len(m)][0] if m else None


# ── el activo aparece y es donde abre ────────────────────────────────────────

def test_the_current_chapter_is_listed(tmp_path):
    a = _app(tmp_path)
    a._doc_open_picker('right')
    assert 'Medio.txt' in [f for f, _ in a._f5_pick_matches()]


def test_it_opens_parked_on_the_current_chapter(tmp_path):
    a = _app(tmp_path)
    a._doc_open_picker('right')
    assert _elegido(a) == 'Medio.txt'


def test_confirming_without_moving_does_nothing(tmp_path):
    """El punto entero: cerrar sin querer no te manda el párrafo a ningún lado."""
    a = _app(tmp_path)
    a._doc_open_picker('right')
    antes = list(a.line_ring.lines)
    assert a._doc_send_to(_elegido(a)) is False
    assert a.line_ring.lines == antes


def test_moving_one_down_still_sends(tmp_path):
    a = _app(tmp_path)
    a._doc_open_picker('right')
    a._f5_pick_match_idx += 1
    destino = _elegido(a)
    assert destino != 'Medio.txt'
    assert a._doc_send_to(destino) is True


def test_the_scratch_is_still_out(tmp_path):
    """El portal 0 nunca fue un destino y sigue sin serlo."""
    a = _app(tmp_path)
    a._doc_open_picker('right')
    assert '0.txt' not in [f for f, _ in a._f5_pick_matches()]


def test_it_works_from_the_first_chapter_too(tmp_path):
    a = _app(tmp_path, activo='Antes.txt')
    a._doc_open_picker('right')
    assert _elegido(a) == 'Antes.txt'


# ── F5 no cambia ─────────────────────────────────────────────────────────────

def test_f5_still_excludes_the_source(tmp_path):
    """Allá el panel se abre con Right como gesto deliberado de enviar. No me
    lo pidió y no lo toco."""
    a = _app(tmp_path)
    a._pick_include_self = False          # como lo deja F5
    assert 'Medio.txt' not in [f for f, _ in a._f5_pick_matches()]


def test_closing_the_picker_resets_the_flag(tmp_path):
    a = _app(tmp_path)
    a._doc_open_picker('right')
    a._doc_close_picker()
    assert not a._pick_include_self, 'el flag quedó prendido y F5 lo hereda'


# ── el caso que importa: escribiendo en el scratch ───────────────────────────
# Probando en la app real apareció el agujero: el archivo activo de Federico es
# 0.txt, y el scratch está excluido del panel por ser el portal. Así que no
# había "sí mismo" donde estacionar y el panel volvía a abrir en el vecino —
# justo el caso más común, porque en 0.txt es donde escribe.
# Mandar de 0.txt a 0.txt ya es un no-op, así que dejarlo aparecer cuando es el
# activo da el mismo resguardo sin convertirlo en destino.

def test_from_the_scratch_it_parks_on_the_scratch(tmp_path):
    a = _app(tmp_path, activo='0.txt')
    a._doc_open_picker('right')
    assert _elegido(a) == '0.txt'


def test_confirming_from_the_scratch_does_nothing(tmp_path):
    a = _app(tmp_path, activo='0.txt')
    a._doc_open_picker('right')
    antes = list(a.line_ring.lines)
    assert a._doc_send_to(_elegido(a)) is False
    assert a.line_ring.lines == antes


def test_the_scratch_is_still_not_a_destination_from_elsewhere(tmp_path):
    """Desde un capítulo, 0.txt sigue sin ser un destino ofrecido."""
    a = _app(tmp_path, activo='Medio.txt')
    a._doc_open_picker('right')
    assert '0.txt' not in [f for f, _ in a._f5_pick_matches()]
