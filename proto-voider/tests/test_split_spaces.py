"""Ctrl+Shift+E en F2 — devolverle los saltos de línea a un texto de scriptio
continua que quedó fundido en una sola línea.

La regla es de Federico, textual: «convierte los espacios en puntos y los puntos
en linebreaks». El punto QUEDA — no es un paso intermedio hacia el corte. Esa es
la parte que importa: sin puntuación, el próximo viaje a F9 vuelve a fundir todo,
porque F9 corta por oraciones y no hay oraciones que cortar. Con el punto al
final de cada línea, el texto sobrevive al viaje.

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

    def test_each_space_becomes_a_period_and_a_line(self):
        assert self._f()('itisagreatmovie agretaactress agreatactor') == [
            'itisagreatmovie.', 'agretaactress.', 'agreatactor.']

    def test_an_existing_period_also_breaks(self):
        """«los puntos en linebreaks» — la segunda mitad de la regla."""
        assert self._f()('uno.dos tres') == ['uno.', 'dos.', 'tres.']

    def test_runs_of_whitespace_collapse(self):
        assert self._f()('a   b\tc') == ['a.', 'b.', 'c.']

    def test_a_closer_that_already_ends_the_sentence_is_left_alone(self):
        assert self._f()('isthatit? yesitis! esto… fin') == [
            'isthatit?', 'yesitis!', 'esto…', 'fin.']

    def test_a_trailing_comma_keeps_its_comma(self):
        """No le como un carácter al texto: la coma queda y el punto cierra."""
        assert self._f()('snapback, counterjab') == ['snapback,.', 'counterjab.']

    def test_a_line_with_no_space_still_gets_its_period(self):
        """Clave: así se puede correr sobre líneas YA separadas, para puntuarlas."""
        assert self._f()('unasolapalabra') == ['unasolapalabra.']

    def test_an_empty_line_yields_nothing(self):
        assert self._f()('   ') == []

    def test_edges_are_trimmed(self):
        assert self._f()('  a b  ') == ['a.', 'b.']


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
    app, f = _app(['.', 'uno dos tres', 'otra.'], 1, tmp_path)
    app._split_line_on_spaces()
    assert app.line_ring.lines == ['.', 'uno.', 'dos.', 'tres.', 'otra.']


def test_the_caret_stays_on_the_first_piece(tmp_path):
    app, f = _app(['.', 'uno dos tres'], 1, tmp_path)
    app._split_line_on_spaces()
    assert app.line_ring.index == 1
    assert app.line_ring.current() == 'uno.'


def test_on_a_dot_it_splits_the_whole_paragraph(tmp_path):
    app, f = _app(['.', 'a b', 'c d', '.', 'no me toques.'], 0, tmp_path)
    app._split_line_on_spaces()
    assert app.line_ring.lines == [
        '.', 'a.', 'b.', 'c.', 'd.', '.', 'no me toques.']


def test_the_dots_are_never_exploded(tmp_path):
    app, f = _app(['.', 'a b', '.', 'c d'], 0, tmp_path)
    app._split_line_on_spaces()
    assert app.line_ring.lines.count('.') == 2


def test_it_reaches_disk(tmp_path):
    app, f = _app(['.', 'uno dos'], 1, tmp_path)
    app._split_line_on_spaces()
    assert f.read_text(encoding='utf-8').splitlines() == ['.', 'uno.', 'dos.']


def test_it_is_one_undo_step(tmp_path):
    app, f = _app(['.', 'uno dos'], 1, tmp_path)
    app._split_line_on_spaces()
    assert app._undo_begin.called and app._undo_commit.called


def test_it_punctuates_lines_that_are_already_split(tmp_path):
    """El caso de Federico: ya corrió el comando y quedaron líneas sin punto.
    Correrlo de nuevo sobre el párrafo tiene que ponerles el punto."""
    app, f = _app(['.', 'itisagreatmovie', 'agretaactress'], 0, tmp_path)
    app._split_line_on_spaces()
    assert app.line_ring.lines == ['.', 'itisagreatmovie.', 'agretaactress.']


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
    assert app.line_ring.lines == ['.', 'sin.', 'is.', 'not.', 'arbitrary.']


def test_it_survives_the_real_thing(tmp_path):
    """Una línea de scriptio continua de verdad, del 0.txt de Federico."""
    real = ('itisagreatmovie agretaactress agreatactor '
            'isthatthethingshewaswritingabout? bearruinedsomanylives')
    app, f = _app(['.', real], 1, tmp_path)
    app._split_line_on_spaces()
    assert app.line_ring.lines == [
        '.', 'itisagreatmovie.', 'agretaactress.', 'agreatactor.',
        'isthatthethingshewaswritingabout?', 'bearruinedsomanylives.']


def test_the_result_survives_a_round_trip_through_f9(tmp_path):
    """La prueba que importa: puntuado, ir a F9 y volver ya no funde nada."""
    from reading_page import lines_to_paragraphs
    app, f = _app(['.', 'unofrag dosfrag tresfrag'], 1, tmp_path)
    app._split_line_on_spaces()
    fixed = list(app.line_ring.lines)

    # F9 al abrir: pega el párrafo con espacios.
    prose = '\n\n'.join(lines_to_paragraphs(fixed))
    # F9 al salir: reformat reparte por oraciones. Ahora SÍ hay oraciones.
    import re
    back = [s.strip() for s in re.split(r'(?<=[.?!])\s+', prose) if s.strip()]
    assert back == ['unofrag.', 'dosfrag.', 'tresfrag.']


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
