"""F6 edita como F2: partir, unir, mover la línea, mover la palabra, copiar.

Decidido con Federico: copias propias para el lector, sin tocar los manejadores
de F2 — ahí viven sus capítulos y no vale arriesgarlos por esto. La única
excepción es _swap_words, que son 80 líneas de lógica delicada: en vez de
copiarlas se le agregaron parámetros OPCIONALES con los valores de hoy por
defecto, así F2 se comporta exactamente igual y no queda un duplicado que se
arregle en un lado y no en el otro.

Y Enter en F6 ahora parte la línea siempre; para salir del lector está F1.
"""
import os
import types
import pytest
from unittest.mock import MagicMock

pytest.importorskip("PyQt6")
from PyQt6.QtWidgets import QApplication, QLineEdit
from line_ring import LineRing


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


def _app(tmp_path, lines=('.', 'primera linea.', 'segunda linea.',
                          '.', 'otro parrafo.'), idx=1):
    from new_interface import FullscreenCircleApp as App

    class _App:
        pass
    a = _App()
    o = tmp_path / 'O'; o.mkdir(); (tmp_path / 'I').mkdir()
    book = o / 'Libro.txt'
    book.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    a.void_dir = str(tmp_path); a.o_dir = str(o)
    a.f1_file = str(tmp_path / 'I' / '0.txt'); open(a.f1_file, 'w').close()
    a.current_file_path = a.f1_file
    a.o_reader_file = str(book)
    a.o_reader_ring = LineRing(list(lines))
    a.o_reader_ring.index = idx
    a.o_reader_view = MagicMock()
    a.o_reader_view.editor = QLineEdit()
    a.o_reader_view.editor.setText(lines[idx])
    a._undo = None
    a._ws_books = []
    a._ws_save_position = MagicMock()
    a._tts_cut = MagicMock()
    a.load_doc_lines = MagicMock()
    for n in ('_reader_save', '_reader_split_line', '_reader_join_prev',
              '_reader_join_next', '_reader_move_line', '_reader_smart_copy',
              '_reader_para_nav', '_swap_words', '_reader_refresh_editor',
              '_atomic_write_lines', '_undo_capture'):
        if hasattr(App, n):
            setattr(a, n, types.MethodType(getattr(App, n), a))
    return a, str(book)


def _read(p):
    with open(p, encoding='utf-8') as f:
        return [l.rstrip('\n') for l in f]


# ── partir y unir ────────────────────────────────────────────────────────────

def test_enter_splits_the_line(qapp, tmp_path):
    a, book = _app(tmp_path)
    a._reader_split_line(len('primera'))
    assert a.o_reader_ring.lines[1:3] == ['primera', ' linea.']


def test_the_split_reaches_the_book(qapp, tmp_path):
    a, book = _app(tmp_path)
    a._reader_split_line(len('primera'))
    assert 'primera' in _read(book)


def test_backspace_at_start_joins_with_the_previous(qapp, tmp_path):
    a, book = _app(tmp_path, idx=2)
    a._reader_join_prev()
    assert 'primera linea.segunda linea.' in a.o_reader_ring.lines


def test_it_never_joins_across_a_dot(qapp, tmp_path):
    """Un punto es un límite de párrafo: unir a través de él lo borraría."""
    a, book = _app(tmp_path, idx=4)      # primera línea del segundo párrafo
    antes = list(a.o_reader_ring.lines)
    a._reader_join_prev()
    assert a.o_reader_ring.lines == antes


def test_delete_at_end_joins_with_the_next(qapp, tmp_path):
    a, book = _app(tmp_path, idx=1)
    a._reader_join_next()
    assert 'primera linea.segunda linea.' in a.o_reader_ring.lines


def test_it_never_joins_forward_across_a_dot(qapp, tmp_path):
    a, book = _app(tmp_path, idx=2)      # última del primer párrafo
    antes = list(a.o_reader_ring.lines)
    a._reader_join_next()
    assert a.o_reader_ring.lines == antes


# ── mover la línea ───────────────────────────────────────────────────────────

def test_alt_down_moves_the_line(qapp, tmp_path):
    a, book = _app(tmp_path, idx=1)
    a._reader_move_line(1)
    assert a.o_reader_ring.lines[1:3] == ['segunda linea.', 'primera linea.']


def test_alt_up_moves_it_back(qapp, tmp_path):
    a, book = _app(tmp_path, idx=2)
    a._reader_move_line(-1)
    assert a.o_reader_ring.lines[1:3] == ['segunda linea.', 'primera linea.']


def test_the_move_follows_the_line(qapp, tmp_path):
    a, book = _app(tmp_path, idx=1)
    a._reader_move_line(1)
    assert a.o_reader_ring.current() == 'primera linea.'


def test_the_move_reaches_the_book(qapp, tmp_path):
    a, book = _app(tmp_path, idx=1)
    a._reader_move_line(1)
    assert _read(book)[1:3] == ['segunda linea.', 'primera linea.']


# ── mover la palabra (Alt+←/→) ───────────────────────────────────────────────

def test_alt_right_moves_the_word(qapp, tmp_path):
    a, book = _app(tmp_path, idx=1)
    ed = a.o_reader_view.editor
    ed.setText('uno dos tres')
    ed.setCursorPosition(0)
    a._swap_words(1, editor=ed, ring=a.o_reader_ring, save=a._reader_save)
    assert ed.text() == 'dos uno tres'


def test_the_word_swap_reaches_the_book(qapp, tmp_path):
    a, book = _app(tmp_path, idx=1)
    ed = a.o_reader_view.editor
    ed.setText('uno dos tres')
    ed.setCursorPosition(0)
    a._swap_words(1, editor=ed, ring=a.o_reader_ring, save=a._reader_save)
    assert 'dos uno tres' in _read(book)


def test_swap_words_still_defaults_to_f2():
    """Los parámetros son opcionales: sin pasarlos, F2 se comporta igual."""
    import inspect
    from new_interface import FullscreenCircleApp as App
    sig = inspect.signature(App._swap_words)
    for p in ('editor', 'ring', 'save'):
        assert sig.parameters[p].default is None, f'{p} tiene que ser opcional'


# ── copiar ───────────────────────────────────────────────────────────────────

def test_ctrl_c_copies_the_line(qapp, tmp_path):
    from PyQt6.QtWidgets import QApplication as QA
    a, book = _app(tmp_path, idx=1)
    a._reader_smart_copy()
    assert QA.clipboard().text() == 'primera linea.'


def test_ctrl_c_on_a_dot_copies_the_paragraph(qapp, tmp_path):
    from PyQt6.QtWidgets import QApplication as QA
    a, book = _app(tmp_path, idx=0)
    a._reader_smart_copy()
    assert QA.clipboard().text() == 'primera linea.\nsegunda linea.'


# ── saltar de párrafo ────────────────────────────────────────────────────────

def test_pagedown_jumps_to_the_next_dot(qapp, tmp_path):
    a, book = _app(tmp_path, idx=1)
    a._reader_para_nav(1)
    assert a.o_reader_ring.index == 3


def test_pageup_jumps_back(qapp, tmp_path):
    a, book = _app(tmp_path, idx=4)
    a._reader_para_nav(-1)
    assert a.o_reader_ring.index == 3


# ── pararse en un punto ──────────────────────────────────────────────────────
# _reader_navigate salteaba los puntos: nunca podías pararte en uno, así que el
# cosechado y el copiado de párrafo enteros eran inalcanzables navegando. En F2
# el punto es una posición como cualquier otra — y estando ahí, el párrafo que
# abre queda resaltado y el resto atenuado.

def test_navigating_lands_on_the_dot(qapp, tmp_path):
    a, book = _app(tmp_path, idx=2)      # última línea del primer párrafo
    a._reader_navigate = types.MethodType(
        __import__('new_interface').FullscreenCircleApp._reader_navigate, a)
    a._reader_navigate(1)
    assert a.o_reader_ring.current() == '.'


def test_you_can_navigate_off_the_dot_again(qapp, tmp_path):
    a, book = _app(tmp_path, idx=3)      # parado en el punto
    a._reader_navigate = types.MethodType(
        __import__('new_interface').FullscreenCircleApp._reader_navigate, a)
    a._reader_navigate(1)
    assert a.o_reader_ring.current() == 'otro parrafo.'


def test_the_editor_locks_on_the_dot(qapp, tmp_path):
    """Como en F2: sobre un punto no se escribe, pero se está parado ahí."""
    a, book = _app(tmp_path, idx=3)
    a._reader_refresh_editor()
    assert a.o_reader_view.editor.isReadOnly()


def test_the_view_highlights_the_paragraph_under_the_dot():
    """El resaltado lo hace CircularView.edit_alpha, el mismo widget que F2:
    parado en un punto, el párrafo que abre va entero y el resto atenuado."""
    from circular_view import CircularView
    hl = {0, 1, 2}
    assert CircularView.edit_alpha(1, True, 1.0, hl) == 1.0     # dentro
    assert CircularView.edit_alpha(2, True, 1.0, hl) == 1.0
    assert CircularView.edit_alpha(5, True, 1.0, hl) == pytest.approx(0.3)  # fuera
