"""Ctrl+Shift+E en F2 — devolverle los saltos de línea a un texto de scriptio
continua que quedó fundido en una sola línea.

Ya NO le agrega puntuación. Federico: "remove dot adder in f2 when i press
ctrl+shift+E. If i fix the line cojoiner of f9, there is no need of adding
dots, just traducing spaces as linebreaks". El punto que este comando le
agregaba a cada fragmento era un parche: existía sólo para que F9 (que unía
TODO lo que hubiera entre dos puntos, sin mirar qué tenía cada línea) no
volviera a fundir el texto. Con el arreglo del "cojoiner" de F9
(reading_page.lines_to_paragraphs, ver test_lines_to_paragraphs_join.py —
ahora sólo une una línea con la siguiente si la primera ya termina en algo que
cierra), ese parche ya no hace falta: una línea sin puntuación sobrevive el
viaje a F9 sola, sin que nadie le agregue nada.

Este comando vuelve a ser lo que era antes del parche: partir por espacios (y
por un punto existente dentro del texto, que sigue actuando como separador),
sin tocar ni agregar ningún carácter.

Parado en una línea actúa sobre esa línea; parado en un punto, sobre todo el
párrafo — igual que Ctrl+C, Alt+↑ y Alt+Shift+→.
"""
import types
import pytest
from unittest.mock import MagicMock

from line_ring import LineRing
from helpers import make_ring_app


# ── la función pura ──────────────────────────────────────────────────────────

class TestSplitOnSpaces:
    def _f(self):
        from f2_mixin import split_on_spaces
        return split_on_spaces

    def test_each_space_becomes_a_line(self):
        assert self._f()('itisagreatmovie agretaactress agreatactor') == [
            'itisagreatmovie', 'agretaactress', 'agreatactor']

    def test_an_existing_period_also_breaks(self):
        """Un punto dentro del texto sigue actuando como separador — eso no
        cambió. Lo que se sacó es agregar uno donde no había."""
        assert self._f()('uno.dos tres') == ['uno', 'dos', 'tres']

    def test_runs_of_whitespace_collapse(self):
        assert self._f()('a   b\tc') == ['a', 'b', 'c']

    def test_nothing_gets_added_to_a_fragment(self):
        """El cambio en sí: sin punto agregado, ni a los que ya cierran ('?')
        ni a los que no ('unasolapalabra')."""
        assert self._f()('isthatit? unasolapalabra') == ['isthatit?', 'unasolapalabra']

    def test_a_trailing_comma_is_left_exactly_as_is(self):
        assert self._f()('snapback, counterjab') == ['snapback,', 'counterjab']

    def test_a_line_with_no_space_is_left_alone(self):
        assert self._f()('unasolapalabra') == ['unasolapalabra']

    def test_an_empty_line_yields_nothing(self):
        assert self._f()('   ') == []

    def test_edges_are_trimmed(self):
        assert self._f()('  a b  ') == ['a', 'b']


# ── el comando en F2 ─────────────────────────────────────────────────────────

def _app(lines, index, tmp_path):
    from new_interface import FullscreenCircleApp
    f = tmp_path / '0.txt'
    f.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    app = make_ring_app(list(lines), tmp_file=str(f))
    app.line_ring = LineRing(list(lines))
    app.line_ring.index = index
    for name in ('_split_line_on_spaces', '_atomic_write_lines'):
        setattr(app, name, types.MethodType(getattr(FullscreenCircleApp, name), app))
    app.load_doc_lines = MagicMock()
    app._doc_show_editor = MagicMock()
    app._undo_begin = MagicMock()
    app._undo_commit = MagicMock()
    app.auto_save_circular = MagicMock()
    return app, f


def test_on_a_line_it_splits_that_line_only(tmp_path):
    app, f = _app(['.', 'uno dos tres', 'otra linea'], 1, tmp_path)
    app._split_line_on_spaces()
    assert app.line_ring.lines == ['.', 'uno', 'dos', 'tres', 'otra linea']


def test_the_caret_stays_on_the_first_piece(tmp_path):
    app, f = _app(['.', 'uno dos tres'], 1, tmp_path)
    app._split_line_on_spaces()
    assert app.line_ring.index == 1
    assert app.line_ring.current() == 'uno'


def test_on_a_dot_it_splits_the_whole_paragraph(tmp_path):
    app, f = _app(['.', 'a b', 'c d', '.', 'no me toques'], 0, tmp_path)
    app._split_line_on_spaces()
    assert app.line_ring.lines == ['.', 'a', 'b', 'c', 'd', '.', 'no me toques']


def test_the_dots_are_never_exploded(tmp_path):
    app, f = _app(['.', 'a b', '.', 'c d'], 0, tmp_path)
    app._split_line_on_spaces()
    assert app.line_ring.lines.count('.') == 2


def test_it_reaches_disk(tmp_path):
    app, f = _app(['.', 'uno dos'], 1, tmp_path)
    app._split_line_on_spaces()
    assert f.read_text(encoding='utf-8').splitlines() == ['.', 'uno', 'dos']


def test_it_is_one_undo_step(tmp_path):
    app, f = _app(['.', 'uno dos'], 1, tmp_path)
    app._split_line_on_spaces()
    assert app._undo_begin.called and app._undo_commit.called


def test_a_line_with_nothing_to_split_is_a_no_op(tmp_path):
    """Ya no hay puntuación que agregar, así que una línea de una sola palabra
    — con o sin puntuación al final — nunca cambia nada."""
    app, f = _app(['.', 'unasola'], 1, tmp_path)
    app._split_line_on_spaces()
    assert app.line_ring.lines == ['.', 'unasola']
    assert not app._undo_begin.called


def test_running_it_twice_does_nothing_the_second_time(tmp_path):
    """Idempotente: la salida de una corrida es punto fijo de la siguiente."""
    app, f = _app(['.', 'unofrag dosfrag tresfrag'], 0, tmp_path)
    app._split_line_on_spaces()
    once = list(app.line_ring.lines)
    app._undo_begin.reset_mock()
    app._split_line_on_spaces()
    assert app.line_ring.lines == once
    assert not app._undo_begin.called   # no se escribe un paso de undo vacío


def test_on_normal_prose_it_explodes_every_word(tmp_path):
    """No es un bug, es el precio: el comando no distingue prosa de scriptio
    continua. En prosa normal el espacio separa PALABRAS y las parte todas.
    Está documentado para que nadie lo descubra sobre su propio texto."""
    app, f = _app(['.', 'sin is not arbitrary'], 1, tmp_path)
    app._split_line_on_spaces()
    assert app.line_ring.lines == ['.', 'sin', 'is', 'not', 'arbitrary']


def test_it_survives_the_real_thing(tmp_path):
    """Una línea de scriptio continua de verdad, del 0.txt de Federico."""
    real = ('itisagreatmovie agretaactress agreatactor '
            'isthatthethingshewaswritingabout? bearruinedsomanylives')
    app, f = _app(['.', real], 1, tmp_path)
    app._split_line_on_spaces()
    assert app.line_ring.lines == [
        '.', 'itisagreatmovie', 'agretaactress', 'agreatactor',
        'isthatthethingshewaswritingabout?', 'bearruinedsomanylives']


def test_the_result_survives_a_round_trip_through_f9(tmp_path):
    """La prueba que importa, con el mecanismo nuevo: lo que arregla el viaje a
    F9 ya no es la puntuación que agrega este comando — es que F9 dejó de unir
    líneas que no cierran una oración. Partido acá, sin puntuación, sobrevive
    igual."""
    from reading_page import lines_to_paragraphs
    app, f = _app(['.', 'unofrag dosfrag tresfrag'], 1, tmp_path)
    app._split_line_on_spaces()
    sin_punto = [l for l in app.line_ring.lines if l != '.']
    assert lines_to_paragraphs(app.line_ring.lines) == sin_punto


# ── la tecla ─────────────────────────────────────────────────────────────────

def test_ctrl_shift_e_is_bound_and_free_of_collisions():
    from app_config import DEFAULT_CONFIG, _parse_keybinding
    kb = DEFAULT_CONFIG['keybindings']
    assert kb['split_spaces'] == 'Ctrl+Shift+E'
    parsed = [_parse_keybinding(v) for v in kb.values()]
    mine = _parse_keybinding(kb['split_spaces'])
    assert parsed.count(mine) == 1, 'Ctrl+Shift+E ya está tomada por otra acción'


def test_f2_routes_ctrl_shift_e_to_the_split(monkeypatch):
    from PyQt6.QtCore import Qt
    from app_config import _parse_keybinding
    from key_router_mixin import KeyRouterMixin

    called = []

    class App(KeyRouterMixin):
        current_file_path = '/tmp/x.txt'
        f1_file = '/tmp/other.txt'
        _f2_search_active = False
        _kb = {'split_spaces': _parse_keybinding('Ctrl+Shift+E')}
        def _split_line_on_spaces(self):
            called.append(True)

    class Ev:
        def accept(self): pass
        def ignore(self): pass

    key, mods = _parse_keybinding('Ctrl+Shift+E')
    App()._handle_f2_keys(key, mods, Ev())
    assert called
