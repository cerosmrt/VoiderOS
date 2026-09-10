"""Shift+Tab en F1 recicla una línea de los libros del working set (F7).

En F1, Tab ya trae una línea al azar de I/ al renglón (cut-up, sin tocar el
archivo de origen). Shift+Tab es su espejo: la trae de O/, de los libros que
elegiste a mano en F7 — igual que en F2.

Por qué no andaba: F1 (widgets.py) sólo miraba Key_Tab. Shift+Tab llega como
Key_Backtab, no matcheaba, y se iba a la traversal de foco de Qt. En F2
(circular_view.py) sí había un event() que agarraba las dos. Nunca estuvo
implementado en F1 — no era que se hubiera roto.
"""
import types
import pytest
from unittest.mock import MagicMock

pytest.importorskip("PyQt6")
from PyQt6.QtWidgets import QApplication, QWidget, QLineEdit
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtCore import Qt, QEvent

from widgets import CustomLineEdit as F1Edit
from circular_view import CustomLineEdit as DocEdit


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


def _fire(w, key, mods):
    return w.event(QKeyEvent(QEvent.Type.KeyPress, key, mods, '\t'))


# ── la tecla llega al entry de F1 ────────────────────────────────────────────

class _Parent(QWidget):
    use_spacebar_for_void = False


def _entry(qapp):
    p = _Parent()
    le = F1Edit(p)
    le.parent = p
    le._keep = p
    got = []
    le.shiftTabPressed.connect(lambda: got.append('ws'))
    return le, got


def test_backtab_reaches_f1(qapp):
    le, got = _entry(qapp)
    _fire(le, Qt.Key.Key_Backtab, Qt.KeyboardModifier.ShiftModifier)
    assert got == ['ws']


def test_tab_with_shift_also_reaches_f1(qapp):
    """La otra codificación, según el layout."""
    le, got = _entry(qapp)
    _fire(le, Qt.Key.Key_Tab, Qt.KeyboardModifier.ShiftModifier)
    assert got == ['ws']


def test_plain_tab_is_left_alone_in_f1(qapp):
    """Tab sigue siendo el reciclado de I/, y se maneja donde ya se manejaba."""
    le, got = _entry(qapp)
    _fire(le, Qt.Key.Key_Tab, Qt.KeyboardModifier.NoModifier)
    assert got == []


# ── el helper compartido ─────────────────────────────────────────────────────

class TestTabIntent:
    """Una sola fuente de verdad para las dos codificaciones de Shift+Tab,
    usada por F1 y por F2."""

    def _i(self, key, mods=Qt.KeyboardModifier.NoModifier,
           typ=QEvent.Type.KeyPress):
        from widgets import tab_intent
        return tab_intent(QKeyEvent(typ, key, mods, '\t'))

    def test_plain_tab(self):
        assert self._i(Qt.Key.Key_Tab) == 'tab'

    def test_backtab(self):
        assert self._i(Qt.Key.Key_Backtab, Qt.KeyboardModifier.ShiftModifier) == 'shift-tab'

    def test_backtab_without_the_shift_flag(self):
        assert self._i(Qt.Key.Key_Backtab) == 'shift-tab'

    def test_tab_with_shift(self):
        assert self._i(Qt.Key.Key_Tab, Qt.KeyboardModifier.ShiftModifier) == 'shift-tab'

    def test_anything_else_is_none(self):
        assert self._i(Qt.Key.Key_A) is None

    def test_a_key_release_is_none(self):
        assert self._i(Qt.Key.Key_Tab, typ=QEvent.Type.KeyRelease) is None


def test_f2_uses_the_same_helper(qapp):
    """Que no queden dos copias de la regla, que fue justo el bug original."""
    le = DocEdit()
    got = []
    le.altTabPressed.connect(lambda: got.append('ws'))
    _fire(le, Qt.Key.Key_Tab, Qt.KeyboardModifier.ShiftModifier)
    _fire(le, Qt.Key.Key_Backtab, Qt.KeyboardModifier.ShiftModifier)
    assert got == ['ws', 'ws']


# ── qué hace cuando llega ────────────────────────────────────────────────────

def _app(ws_line):
    from new_interface import FullscreenCircleApp

    class _App:
        pass
    a = _App()
    a.entry = QLineEdit()
    a._random_line_from_ws = lambda: ws_line
    a._f1_recycle_ws_line = types.MethodType(
        FullscreenCircleApp._f1_recycle_ws_line, a)
    return a


def test_it_puts_the_working_set_line_in_the_entry(qapp):
    a = _app('una linea de un libro.')
    a._f1_recycle_ws_line()
    assert a.entry.text() == 'una linea de un libro.'
    assert a.entry.cursorPosition() == 0


def test_an_empty_working_set_leaves_the_entry_alone(qapp):
    """Si no hay libros en F7 no se pisa lo que estabas escribiendo."""
    a = _app(None)
    a.entry.setText('lo que venia escribiendo')
    a._f1_recycle_ws_line()
    assert a.entry.text() == 'lo que venia escribiendo'


def test_it_is_wired_to_the_entry():
    import inspect
    from new_interface import FullscreenCircleApp as App
    src = inspect.getsource(App.__init__) + inspect.getsource(App.init_ui)
    assert 'shiftTabPressed' in src, 'la señal no está conectada'
