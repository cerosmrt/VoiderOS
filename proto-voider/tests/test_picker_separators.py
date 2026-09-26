"""El panel de capítulos muestra los puntos separadores, como F3.

Federico: "me gustaria que la lista se vea como se ve en f3 para que sea menos
mareable (con los puntos separadores)". Con 838 títulos corridos no hay dónde
agarrarse; los puntos parten la biblioteca en libros y dan referencia.

La lista que se DIBUJA y la lista de DESTINOS son dos cosas distintas ahora: un
punto se ve pero no se puede elegir — no es un capítulo, no hay adónde mandar.
Por eso _f5_pick_matches (los destinos) queda igual y se agrega _pick_display,
que arma las filas a mostrar y traduce cuál está resaltada.

Con filtro los puntos no van: un separador entre nada no separa nada, y la lista
filtrada ya es corta.
"""
import types
import pytest
from unittest.mock import MagicMock

pytest.importorskip("PyQt6")
from line_ring import LineRing
from helpers import make_ring_app


SEP = '·'


def _app(tmp_path, biblioteca=None, activo='B.txt'):
    from new_interface import FullscreenCircleApp as App
    i = tmp_path / 'I'
    i.mkdir(exist_ok=True)
    biblioteca = biblioteca or ['.', 'A.txt', 'B.txt', '.', 'C.txt', 'D.txt']
    for n in biblioteca:
        if n != '.':
            (i / n).write_text('.\n', encoding='utf-8')
    (i / '0.txt').write_text('.\n', encoding='utf-8')
    a = make_ring_app(['.', 'uno.'], tmp_file=str(i / activo))
    a.void_dir = str(tmp_path)
    a.f1_file = str(i / '0.txt')
    a.current_file_path = str(i / activo)
    a.line_ring = LineRing(['.', 'uno.'])
    a._library_lines = list(biblioteca)
    a._library_path_cache = {n: str(i / n) for n in biblioteca if n != '.'}
    for n in ('_f5_pick_matches', '_pick_display', '_f5_pick_target',
              '_f5_pick_start_idx'):
        if hasattr(App, n):
            setattr(a, n, types.MethodType(getattr(App, n), a))
    a._f5_pick_filter = ''
    a._f5_pick_match_idx = 0
    a._pick_include_self = True
    return a


# ── los puntos se ven ────────────────────────────────────────────────────────

def test_the_separators_show_up(tmp_path):
    a = _app(tmp_path)
    filas, _ = a._pick_display()
    assert SEP in filas, f'sin separadores: {filas}'


def test_they_keep_the_library_order(tmp_path):
    """Separan ENTRE libros. El punto de arriba de todo no va: en F3 se muestra
    porque es navegable —Enter ahí abre el libro entero— pero acá no se puede
    elegir, así que arriba de todo no separa nada. Igual que el del final."""
    a = _app(tmp_path)
    filas, _ = a._pick_display()
    assert filas == ['A', 'B', SEP, 'C', 'D']


def test_the_highlight_follows_the_right_row(tmp_path):
    """El índice de destinos y el de filas dibujadas no son el mismo número."""
    a = _app(tmp_path)
    a._f5_pick_match_idx = 2            # el tercer DESTINO: 'C'
    filas, i = a._pick_display()
    assert filas[i] == 'C'


def test_the_first_destination_maps_to_its_row(tmp_path):
    a = _app(tmp_path)
    a._f5_pick_match_idx = 0
    filas, i = a._pick_display()
    assert filas[i] == 'A'


# ── pero no se pueden elegir ─────────────────────────────────────────────────

def test_a_separator_is_never_a_destination(tmp_path):
    a = _app(tmp_path)
    assert SEP not in [d for _, d in a._f5_pick_matches()]
    assert '.' not in [f for f, _ in a._f5_pick_matches()]


def test_cycling_never_lands_on_a_separator(tmp_path):
    a = _app(tmp_path)
    for k in range(len(a._f5_pick_matches()) * 2):
        a._f5_pick_match_idx = k
        filas, i = a._pick_display()
        assert filas[i] != SEP, f'quedó parado en un separador con idx {k}'


# ── con filtro no van ────────────────────────────────────────────────────────

def test_filtering_drops_the_separators(tmp_path):
    a = _app(tmp_path)
    a._f5_pick_filter = 'a'
    filas, _ = a._pick_display()
    assert SEP not in filas


# ── casos raros ──────────────────────────────────────────────────────────────

def test_two_dots_in_a_row_collapse(tmp_path):
    a = _app(tmp_path, biblioteca=['.', '.', 'A.txt', 'B.txt'])
    filas, _ = a._pick_display()
    for k in range(len(filas) - 1):
        assert not (filas[k] == SEP and filas[k + 1] == SEP), filas


def test_a_trailing_dot_is_dropped(tmp_path):
    a = _app(tmp_path, biblioteca=['.', 'A.txt', '.'], activo='A.txt')
    filas, _ = a._pick_display()
    assert filas[-1] != SEP


def test_a_library_with_no_dots_still_works(tmp_path):
    a = _app(tmp_path, biblioteca=['A.txt', 'B.txt'], activo='A.txt')
    filas, i = a._pick_display()
    assert filas == ['A', 'B']
    assert filas[i] == 'A'


def test_an_empty_library_does_not_crash(tmp_path):
    a = _app(tmp_path, biblioteca=['.'], activo='0.txt')
    filas, i = a._pick_display()
    assert filas == [] and i == 0


# ── llega a la vista de F5, no solo a _pick_display ─────────────────────────

def test_f5_refresh_sends_the_separators_to_the_view(tmp_path):
    """_doc_refresh_picker (F2) ya usa _pick_display. _f5_refresh todavia
    armaba las filas a mano desde _f5_pick_matches, que nunca incluye el '.'
    — por eso el panel de F5 se veia sin puntos aunque el de F2 si los tenia."""
    from f5_reorder_mixin import F5ReorderMixin
    a = _app(tmp_path)
    a._f5_units = types.MethodType(F5ReorderMixin._f5_units, a)
    a._f5_tokens_cached = types.MethodType(F5ReorderMixin._f5_tokens_cached, a)
    a._f5_tokens = types.MethodType(F5ReorderMixin._f5_tokens, a)
    a._f5_current_title = types.MethodType(F5ReorderMixin._f5_current_title, a)
    a._f5_para_idx = 0
    a._f5_picker_open = True
    a.reorder_view = MagicMock()
    F5ReorderMixin._f5_refresh(a)
    args, _ = a.reorder_view.set_picker_state.call_args
    matches = args[2]
    assert SEP in matches, f'sin separadores en la vista: {matches}'


def test_f5_opens_parked_near_current_not_on_it(tmp_path):
    """F5 deja _pick_include_self en False (a diferencia de F2): el capitulo
    activo nunca es un destino valido, asi que nunca aparece listado en el
    panel — ni resaltado ni atenuado. Lo que SI tiene que pasar es que abra
    parado en el vecino mas cercano en la biblioteca (A, justo antes de B),
    que es la 'referencia de donde estas' que da _f5_pick_start_idx."""
    from f5_reorder_mixin import F5ReorderMixin
    a = _app(tmp_path)               # biblioteca ['.','A','B','.','C','D'], activo B
    a._pick_include_self = False     # el default real de F5 (_f5_open_picker)
    a._f5_units = types.MethodType(F5ReorderMixin._f5_units, a)
    a._f5_tokens_cached = types.MethodType(F5ReorderMixin._f5_tokens_cached, a)
    a._f5_tokens = types.MethodType(F5ReorderMixin._f5_tokens, a)
    a._f5_current_title = types.MethodType(F5ReorderMixin._f5_current_title, a)
    a._f5_para_idx = 0
    a._f5_picker_open = True
    a._f5_pick_match_idx = a._f5_pick_start_idx()
    a.reorder_view = MagicMock()
    F5ReorderMixin._f5_refresh(a)
    args, _ = a.reorder_view.set_picker_state.call_args
    filas, idx = args[2], args[3]
    assert 'B' not in filas, f'el activo no deberia listarse nunca: {filas}'
    assert filas[idx] == 'A', f'deberia parar en el vecino mas cercano: {filas}'
