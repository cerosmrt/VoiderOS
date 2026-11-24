"""F3 sin cursor al navegar.

En F3 el cursor no debe verse al ir arriba o abajo: sólo al ir a los costados.
  ↑ / ↓        moverse entre filas, SIN cursor
  Enter        entrar al capítulo directo (ya no depende de dónde esté el cursor)
  ← / →        aparece el cursor y se edita el nombre del título
Es un modo opcional del editor (browse_mode): F2 y las demás vistas no cambian.
"""
import pytest

pytest.importorskip("PyQt6")
from PyQt6.QtCore import Qt, QEvent, QPointF
from PyQt6.QtGui import QKeyEvent, QMouseEvent
from PyQt6.QtWidgets import QApplication

from circular_view import CustomLineEdit

NO = Qt.KeyboardModifier.NoModifier


@pytest.fixture(scope='module')
def qapp():
    yield QApplication.instance() or QApplication([])


def _press(ed, key, mods=NO, text=''):
    ed.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, key, mods, text))


def _ed(qapp, text='Capítulo uno', browse=True):
    ed = CustomLineEdit()
    ed.setText(text)
    ed.setCursorPosition(0)
    if browse:
        ed.set_browse_mode(True)
    ed.sent = []
    for name in ('returnPressed', 'splitAtCursor', 'upPressed', 'downPressed',
                 'shiftReturnPressed', 'ctrlReturnPressed'):
        getattr(ed, name).connect(lambda *a, n=name: ed.sent.append(n))
    return ed


# ── navegando: sin cursor ────────────────────────────────────────────────────

def test_while_browsing_the_caret_is_hidden(qapp):
    ed = _ed(qapp)
    assert ed.isReadOnly() and ed.browsing


def test_enter_opens_the_chapter_wherever_the_caret_is(qapp):
    ed = _ed(qapp)
    ed.setCursorPosition(5)                  # antes esto era "partir la línea"
    _press(ed, Qt.Key.Key_Return)
    assert ed.sent == ['returnPressed']


def test_up_and_down_navigate_and_stay_in_browse_mode(qapp):
    ed = _ed(qapp)
    _press(ed, Qt.Key.Key_Down)
    _press(ed, Qt.Key.Key_Up)
    assert ed.sent == ['downPressed', 'upPressed']
    assert ed.browsing and ed.isReadOnly()


def test_shift_and_ctrl_enter_still_create(qapp):
    ed = _ed(qapp)
    _press(ed, Qt.Key.Key_Return, Qt.KeyboardModifier.ShiftModifier)
    _press(ed, Qt.Key.Key_Return, Qt.KeyboardModifier.ControlModifier)
    assert ed.sent == ['shiftReturnPressed', 'ctrlReturnPressed']


# ── los costados: se edita el título ─────────────────────────────────────────

def test_right_arrow_starts_editing_with_the_caret_at_the_end(qapp):
    ed = _ed(qapp)
    _press(ed, Qt.Key.Key_Right)
    assert not ed.browsing and not ed.isReadOnly()
    assert ed.cursorPosition() == len('Capítulo uno')


def test_left_arrow_starts_editing_with_the_caret_at_the_start(qapp):
    ed = _ed(qapp)
    ed.setCursorPosition(4)
    _press(ed, Qt.Key.Key_Left)
    assert not ed.browsing and not ed.isReadOnly()
    assert ed.cursorPosition() == 0


def test_the_first_side_arrow_only_enters_edit_mode_it_does_not_also_move(qapp):
    ed = _ed(qapp)
    _press(ed, Qt.Key.Key_Right)
    assert ed.cursorPosition() == len('Capítulo uno')
    _press(ed, Qt.Key.Key_Left)                         # ya editando: se mueve normal
    assert ed.cursorPosition() == len('Capítulo uno') - 1


def test_typing_a_letter_while_browsing_starts_editing_and_types_it(qapp):
    ed = _ed(qapp)
    _press(ed, Qt.Key.Key_X, NO, 'x')
    assert not ed.browsing and ed.text().endswith('x')


def test_clicking_the_title_starts_editing(qapp):
    ed = _ed(qapp)
    ev = QMouseEvent(QEvent.Type.MouseButtonPress, QPointF(5, 5), QPointF(5, 5),
                     Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, NO)
    ed.mousePressEvent(ev)
    assert not ed.browsing and not ed.isReadOnly()


def test_the_caret_is_hidden_because_a_read_only_line_edit_does_not_draw_one(qapp):
    """Lo que se midió: sólo lectura = sin cursor. Es lo que usa el modo navegar."""
    from PyQt6.QtWidgets import QLineEdit
    ed = _ed(qapp)
    assert QLineEdit.isReadOnly(ed) is True
    ed.enter_edit()
    assert QLineEdit.isReadOnly(ed) is False


def test_f3s_own_read_only_requests_survive_browsing_and_editing(qapp):
    ed = _ed(qapp, text='.')
    ed.setReadOnly(True)                       # F3: un punto
    ed.enter_edit()
    assert ed.isReadOnly()                     # no se edita
    ed.setReadOnly(False)                      # F3: ahora un capítulo
    assert ed.isReadOnly() and ed.browsing     # sigue navegando
    ed.enter_edit()
    assert not ed.isReadOnly()


def test_a_read_only_row_never_shows_a_caret(qapp):
    """Los puntos y el portal '0' no se renombran."""
    ed = _ed(qapp, text='.')
    ed.setReadOnly(True)
    _press(ed, Qt.Key.Key_Right)
    assert ed.browsing and ed.isReadOnly()


# ── editando: Enter funciona como siempre ────────────────────────────────────

def test_while_editing_enter_at_the_start_still_opens_the_chapter(qapp):
    ed = _ed(qapp)
    _press(ed, Qt.Key.Key_Left)                          # editando, caret en 0
    _press(ed, Qt.Key.Key_Return)
    assert ed.sent == ['returnPressed']


def test_while_editing_enter_after_the_text_still_splits_or_adds_below(qapp):
    ed = _ed(qapp)
    _press(ed, Qt.Key.Key_Right)                         # editando, caret al final
    _press(ed, Qt.Key.Key_Return)
    assert ed.sent == ['splitAtCursor']


def test_navigating_while_editing_leaves_edit_mode(qapp):
    ed = _ed(qapp)
    _press(ed, Qt.Key.Key_Right)
    assert not ed.browsing
    _press(ed, Qt.Key.Key_Down)
    assert ed.browsing and ed.isReadOnly() and ed.cursorPosition() == 0


def test_leave_edit_can_be_called_by_the_view(qapp):
    ed = _ed(qapp)
    ed.enter_edit(at_end=True)
    ed.leave_edit()
    assert ed.browsing and ed.isReadOnly()


def test_a_new_entry_being_named_can_start_in_edit_mode(qapp):
    ed = _ed(qapp, text='')
    ed.enter_edit(at_end=True)
    assert not ed.browsing and not ed.isReadOnly()
    _press(ed, Qt.Key.Key_A, NO, 'a')
    assert ed.text() == 'a'


# ── el resto de las vistas no cambia ─────────────────────────────────────────

def test_without_browse_mode_nothing_changes(qapp):
    ed = _ed(qapp, browse=False)
    assert not ed.isReadOnly() and not ed.browsing
    ed.setCursorPosition(5)
    _press(ed, Qt.Key.Key_Return)                        # F2: parte la línea
    assert ed.sent == ['splitAtCursor']


def test_without_browse_mode_left_at_the_start_still_wraps_to_the_end(qapp):
    ed = _ed(qapp, browse=False)
    _press(ed, Qt.Key.Key_Left)
    assert ed.cursorPosition() == len('Capítulo uno')


def test_turning_browse_mode_off_brings_the_caret_back(qapp):
    ed = _ed(qapp)
    ed.set_browse_mode(False)
    assert not ed.isReadOnly() and not ed.browsing


# ── cómo lo usa F3 ───────────────────────────────────────────────────────────

def test_f3_turns_on_browse_mode_for_its_editor():
    import inspect
    from new_interface import FullscreenCircleApp
    fuente = inspect.getsource(FullscreenCircleApp.switch_to_view)
    assert 'book_view.editor.set_browse_mode(True)' in fuente


def test_showing_the_f3_editor_leaves_edit_mode():
    import inspect
    from new_interface import FullscreenCircleApp
    for nombre in ('_book_show_editor', '_book_refresh_editor'):
        assert 'leave_edit' in inspect.getsource(getattr(FullscreenCircleApp, nombre)), nombre


def test_a_new_f3_entry_starts_in_edit_mode():
    import inspect
    from new_interface import FullscreenCircleApp
    assert 'enter_edit' in inspect.getsource(FullscreenCircleApp._book_spawn_new_below)
