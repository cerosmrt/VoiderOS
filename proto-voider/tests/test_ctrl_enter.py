"""Ctrl+Enter no es Enter.

La rama que maneja Return en circular_view.CustomLineEdit no miraba el Ctrl en
absoluto: sólo distinguía Shift y la posición del caret. O sea que Ctrl+Enter
hacía exactamente lo mismo que Enter pelado — en F3, con el caret en 0 (que es
donde queda siempre), te abría el capítulo sin que lo hubieras pedido. Ése era
el "algo raro que sucede cuando apreto ctrl enter".

Decisión suya, en dos pasos: primero "que no haga nada", y después "que cree un
capitulo siempre sin importar donde este el cursor". El segundo gana, y resuelve
además un caso que la lógica del caret no cubre: parado en el portal 0 el
renglón es de sólo lectura, así que no hay posición de cursor que interpretar.
Ctrl+Enter crea, y listo.

Se emite una señal propia (ctrlReturnPressed) en vez de reusar las otras. Sólo
F3 la conecta: en F2 y F6 "crear un capítulo" no significa nada, así que ahí no
pasa nada — y eso queda como una decisión de cableado, no como una rama
escondida adentro del widget.

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
    le.ctrlReturnPressed.connect(lambda: fired.append('crear'))
    return le, fired


def _press(le, key=Qt.Key.Key_Return, mods=Qt.KeyboardModifier.NoModifier):
    ev = QKeyEvent(QEvent.Type.KeyPress, key, mods, '\r')
    le.keyPressEvent(ev)
    return ev


# ââ Ctrl+Enter crea, y ninguna otra cosa ââââââââââââââââââââââââââââââ

@pytest.mark.parametrize("key", [Qt.Key.Key_Return, Qt.Key.Key_Enter])
def test_ctrl_enter_creates(qapp, key):
    le, fired = _edit(qapp, pos=0)
    _press(le, key, Qt.KeyboardModifier.ControlModifier)
    assert fired == ['crear']


def test_ctrl_enter_does_not_open(qapp):
    le, fired = _edit(qapp, pos=0)
    _press(le, mods=Qt.KeyboardModifier.ControlModifier)
    assert 'abrir' not in fired, 'Ctrl+Enter se está comportando como Enter'


def test_ctrl_enter_mid_name_does_not_split(qapp):
    """Crea igual: la posición del cursor no entra en la decisión. Ésa es la
    gracia — en el portal 0 el renglón es de sólo lectura y no hay posición."""
    le, fired = _edit(qapp, pos=4)
    _press(le, mods=Qt.KeyboardModifier.ControlModifier)
    assert fired == ['crear']


def test_ctrl_shift_enter_also_creates(qapp):
    le, fired = _edit(qapp, pos=0)
    _press(le, mods=(Qt.KeyboardModifier.ControlModifier
                     | Qt.KeyboardModifier.ShiftModifier))
    assert fired == ['crear']


def test_only_f3_wires_it():
    """En F2 y F6 crear un capítulo no significa nada, así que no se conecta."""
    import inspect
    from new_interface import FullscreenCircleApp as App
    src = inspect.getsource(App.switch_to_view)
    assert src.count('ctrlReturnPressed') == 1, 'debería conectarse sólo en F3'


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
