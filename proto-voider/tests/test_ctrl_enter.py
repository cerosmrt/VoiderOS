"""Ctrl+Enter no es Enter.

La rama que maneja Return en circular_view.CustomLineEdit no miraba el Ctrl en
absoluto: sólo distinguía Shift y la posición del caret. O sea que Ctrl+Enter
hacía exactamente lo mismo que Enter pelado — en F3, con el caret en 0 (que es
donde queda siempre), te abría el capítulo sin que lo hubieras pedido. Ése era
el "algo raro que sucede cuando apreto ctrl enter".

Decisión suya: que no haga nada. Se implementa con event.ignore(), que es la
forma honesta de "nada acá" — deja que el evento siga hasta el router de la
ventana, igual que ya hace el entry de F1 con los combos de Ctrl. Hoy nadie lo
maneja en F2/F3/F6, así que no pasa nada; y si algún día se le quiere dar un
significado global, el camino ya está abierto.

El editor lo comparten F2, F3, F6 y la vista concatenada: el arreglo vale para
los cuatro, que es lo correcto porque el aliasing era el mismo en todos.
"""
import pytest

pytest.importorskip("PyQt6")
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtCore import Qt, QEvent

from circular_view import CustomLineEdit


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


def _edit(qapp, text='Capitulo', pos=0):
    le = CustomLineEdit()
    le.setText(text)
    le.setCursorPosition(pos)
    fired = []
    le.returnPressed.connect(lambda: fired.append('abrir'))
    le.splitAtCursor.connect(lambda p: fired.append(f'partir@{p}'))
    le.shiftReturnPressed.connect(lambda: fired.append('nuevo'))
    return le, fired


def _press(le, key=Qt.Key.Key_Return, mods=Qt.KeyboardModifier.NoModifier):
    ev = QKeyEvent(QEvent.Type.KeyPress, key, mods, '\r')
    le.keyPressEvent(ev)
    return ev


# ── lo que Ctrl+Enter NO debe hacer ──────────────────────────────────────────

@pytest.mark.parametrize("key", [Qt.Key.Key_Return, Qt.Key.Key_Enter])
def test_ctrl_enter_does_not_open(qapp, key):
    le, fired = _edit(qapp, pos=0)
    _press(le, key, Qt.KeyboardModifier.ControlModifier)
    assert fired == [], 'Ctrl+Enter se está comportando como Enter'


def test_ctrl_enter_mid_name_does_not_split(qapp):
    le, fired = _edit(qapp, pos=4)
    _press(le, mods=Qt.KeyboardModifier.ControlModifier)
    assert fired == []


def test_ctrl_shift_enter_does_not_create_either(qapp):
    le, fired = _edit(qapp, pos=0)
    _press(le, mods=(Qt.KeyboardModifier.ControlModifier
                     | Qt.KeyboardModifier.ShiftModifier))
    assert fired == []


def test_it_is_ignored_not_swallowed(qapp):
    """ignore() y no accept(): el evento sigue hasta el router de la ventana, por
    si algún día se le quiere dar un significado global."""
    le, fired = _edit(qapp, pos=0)
    ev = _press(le, mods=Qt.KeyboardModifier.ControlModifier)
    assert not ev.isAccepted()


# ── lo que Enter SÍ tiene que seguir haciendo ────────────────────────────────

def test_plain_enter_at_the_start_still_opens(qapp):
    le, fired = _edit(qapp, pos=0)
    _press(le)
    assert fired == ['abrir']


def test_plain_enter_mid_text_still_splits(qapp):
    le, fired = _edit(qapp, pos=4)
    _press(le)
    assert fired == ['partir@4']


def test_shift_enter_still_creates(qapp):
    le, fired = _edit(qapp, pos=0)
    _press(le, mods=Qt.KeyboardModifier.ShiftModifier)
    assert fired == ['nuevo']
