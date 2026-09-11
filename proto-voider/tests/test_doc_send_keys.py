"""Las teclas del envío desde F2 tienen que llegar a algún lado.

EL BUG: la rama estaba en el router de la ventana, y nunca corría. El editor
tiene el foco y se come Alt+←/→ para mover la palabra (event.accept()), así que
la tecla no sube nunca. Alt+Shift+←/→ sí burbujeaba —el editor no la reconocía—
y por eso ésa hacía algo y la otra no. Federico: "when i just pressed alt
flecha, nothing happened at all".

El arreglo: que la decisión viva donde SÍ se sabe qué hay debajo del cursor.
  * el editor emite sendLeft/sendRight para Alt+Shift+←/→ (señal propia, no
    depende de que la tecla burbujee hasta la ventana)
  * y para Alt+←/→ sigue emitiendo wordSwap*, pero F2 lo conecta a un handler
    que decide: sobre un punto abre el panel, sobre una línea mueve la palabra.
    El editor no conoce el anillo; la app sí.
"""
import types
import pytest
from unittest.mock import MagicMock

pytest.importorskip("PyQt6")
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtCore import Qt, QEvent

from circular_view import CustomLineEdit
from line_ring import LineRing


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


Alt = Qt.KeyboardModifier.AltModifier
Shift = Qt.KeyboardModifier.ShiftModifier


def _edit(qapp):
    le = CustomLineEdit()
    le.setText('una linea')
    got = []
    le.wordSwapLeft.connect(lambda: got.append('palabra-izq'))
    le.wordSwapRight.connect(lambda: got.append('palabra-der'))
    le.sendLeft.connect(lambda: got.append('panel-izq'))
    le.sendRight.connect(lambda: got.append('panel-der'))
    return le, got


def _press(le, key, mods):
    le.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, key, mods, ''))


# ── el editor emite lo que corresponde ───────────────────────────────────────

def test_alt_shift_right_asks_for_the_panel(qapp):
    le, got = _edit(qapp)
    _press(le, Qt.Key.Key_Right, Alt | Shift)
    assert got == ['panel-der']


def test_alt_shift_left_asks_for_the_panel(qapp):
    le, got = _edit(qapp)
    _press(le, Qt.Key.Key_Left, Alt | Shift)
    assert got == ['panel-izq']


def test_plain_alt_arrow_still_asks_for_the_word_swap(qapp):
    le, got = _edit(qapp)
    _press(le, Qt.Key.Key_Right, Alt)
    _press(le, Qt.Key.Key_Left, Alt)
    assert got == ['palabra-der', 'palabra-izq']


# ── y la app decide qué hacer con Alt+flecha según dónde estés ───────────────

def _app(lines, idx):
    from new_interface import FullscreenCircleApp as App

    class _A:
        pass
    a = _A()
    a.line_ring = LineRing(list(lines))
    a.line_ring.index = idx
    a._doc_open_picker = MagicMock()
    a._swap_words = MagicMock()
    a._doc_alt_arrow = types.MethodType(App._doc_alt_arrow, a)
    return a


def test_on_a_dot_alt_arrow_opens_the_panel():
    a = _app(['.', 'uno.', 'dos.'], 0)
    a._doc_alt_arrow(1)
    a._doc_open_picker.assert_called_once_with('right')
    assert not a._swap_words.called


def test_on_a_line_alt_arrow_moves_the_word():
    a = _app(['.', 'uno dos.', 'tres.'], 1)
    a._doc_alt_arrow(1)
    a._swap_words.assert_called_once_with(1)
    assert not a._doc_open_picker.called


def test_the_arrow_picks_the_side():
    a = _app(['.', 'uno.'], 0)
    a._doc_alt_arrow(-1)
    a._doc_open_picker.assert_called_once_with('left')


# ── el cableado ──────────────────────────────────────────────────────────────

def test_f2_routes_alt_arrow_through_the_decider():
    import inspect
    from new_interface import FullscreenCircleApp as App
    src = inspect.getsource(App.switch_to_view)
    assert '_doc_alt_arrow' in src, 'F2 sigue yendo derecho a _swap_words'
    assert 'sendLeft' in src and 'sendRight' in src


def test_f6_keeps_the_plain_word_swap():
    """El lector no manda párrafos a capítulos: ahí Alt+flecha es sólo la palabra."""
    import inspect
    from new_interface import FullscreenCircleApp as App
    src = inspect.getsource(App.switch_to_view)
    i = src.index('o_reader_view.editor.wordSwapLeft')
    assert '_doc_alt_arrow' not in src[i:i + 400]


# ── con el panel abierto, el editor deja pasar todo ──────────────────────────
# La misma causa raíz de nuevo: el editor tiene el foco y acepta casi todo, así
# que las teclas del panel (flechas, Escape, Enter, escribir para filtrar)
# tampoco llegaban al router. Con el panel abierto el editor se aparta.

_vivos = []      # el recolector se lleva la vista y con ella su editor


def _edit_in_picker(qapp, picker_open):
    from circular_view import CircularView
    v = CircularView(LineRing(['.', 'una linea.']))
    v._picker_open = picker_open
    _vivos.append(v)
    return v.editor


@pytest.mark.parametrize("key,mods", [
    (Qt.Key.Key_Left, Qt.KeyboardModifier.NoModifier),
    (Qt.Key.Key_Right, Qt.KeyboardModifier.NoModifier),
    (Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier),
    (Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier),
    (Qt.Key.Key_Up, Qt.KeyboardModifier.NoModifier),
    (Qt.Key.Key_Backspace, Qt.KeyboardModifier.NoModifier),
    (Qt.Key.Key_A, Qt.KeyboardModifier.NoModifier),
])
def test_with_the_picker_open_the_editor_steps_aside(qapp, key, mods):
    ed = _edit_in_picker(qapp, True)
    ev = QKeyEvent(QEvent.Type.KeyPress, key, mods, 'a')
    ed.keyPressEvent(ev)
    assert not ev.isAccepted(), 'el editor se comió una tecla del panel'


def test_typing_does_not_reach_the_line_while_picking(qapp):
    """Lo que escribís con el panel abierto filtra, no edita la línea."""
    ed = _edit_in_picker(qapp, True)
    ed.setText('original')
    ed.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_A,
                               Qt.KeyboardModifier.NoModifier, 'a'))
    assert ed.text() == 'original'


def test_with_the_picker_closed_nothing_changes(qapp):
    """Sin panel el editor sigue manejando lo suyo. Se prueba con Alt+→, que sí
    acepta — Escape no servía: el editor no lo maneja y nunca lo aceptó."""
    ed = _edit_in_picker(qapp, False)
    ev = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Right, Alt, '')
    ed.keyPressEvent(ev)
    assert ev.isAccepted()
