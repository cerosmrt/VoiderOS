"""Caps Lock never uppercases — it only toggles scriptio-continua. So in the F1
entry AND the F2/F3 editor, while Caps is on, letters type in the normal case
(their case is swapped back). Shift still uppercases; digits/symbols untouched."""
import pytest

pytest.importorskip("PyQt6")
from PyQt6.QtWidgets import QApplication, QWidget
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtCore import Qt, QEvent

from widgets import CustomLineEdit as F1Edit
from circular_view import CustomLineEdit as DocEdit


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


class FakeApp(QWidget):
    """Stands in for the window: editors reach it via editor.window()."""
    use_spacebar_for_void = False

    def __init__(self, caps):
        super().__init__()
        self._caps = caps

    def _capslock_on(self):
        return self._caps


def _type(le, key, text, shift=False):
    mods = Qt.KeyboardModifier.ShiftModifier if shift else Qt.KeyboardModifier.NoModifier
    le.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, key, mods, text))


# Both the F1 entry and the F2/F3 doc editor must behave the same for Caps.
@pytest.mark.parametrize("EditCls", [F1Edit, DocEdit])
class TestCapsNeutralised:
    def _edit(self, qapp, EditCls, caps):
        app = FakeApp(caps)
        le = EditCls(app)
        le._keep_app = app          # keep the parent window alive (GC guard)
        return le

    def test_caps_on_types_lowercase(self, qapp, EditCls):
        le = self._edit(qapp, EditCls, caps=True)
        _type(le, Qt.Key.Key_A, 'A')          # OS sends 'A' with Caps on
        assert le.text() == 'a'

    def test_caps_on_shift_still_uppercases(self, qapp, EditCls):
        le = self._edit(qapp, EditCls, caps=True)
        _type(le, Qt.Key.Key_A, 'a', shift=True)   # Caps+Shift sends 'a'
        assert le.text() == 'A'

    def test_caps_off_is_normal(self, qapp, EditCls):
        le = self._edit(qapp, EditCls, caps=False)
        _type(le, Qt.Key.Key_A, 'A')
        assert le.text() == 'A'

    def test_caps_on_leaves_digits(self, qapp, EditCls):
        le = self._edit(qapp, EditCls, caps=True)
        _type(le, Qt.Key.Key_5, '5')
        assert le.text() == '5'


# Scriptio continua is writing without going back: con Caps prendido la línea
# sólo se puede escribir hacia adelante o soltarla al void. Backspace no borra.
# (El mirror de Rust ya lo hace así — esto pone al Python a la par.)
@pytest.mark.parametrize("EditCls", [F1Edit, DocEdit])
class TestCapsBlocksBackspace:
    def _edit(self, qapp, EditCls, caps, text='hola'):
        app = FakeApp(caps)
        le = EditCls(app)
        le._keep_app = app
        le.setText(text)
        le.setCursorPosition(len(text))
        return le

    def test_caps_on_backspace_erases_nothing(self, qapp, EditCls):
        le = self._edit(qapp, EditCls, caps=True)
        _type(le, Qt.Key.Key_Backspace, '\b')
        assert le.text() == 'hola'

    def test_caps_off_backspace_erases(self, qapp, EditCls):
        le = self._edit(qapp, EditCls, caps=False)
        _type(le, Qt.Key.Key_Backspace, '\b')
        assert le.text() == 'hol'

    def test_caps_on_ctrl_backspace_still_reaches_the_app(self, qapp, EditCls):
        """Ctrl+⌫ manda la línea a la cascada de basura — no es edición, no se bloquea."""
        le = self._edit(qapp, EditCls, caps=True)
        fired = []
        if hasattr(le, 'deleteLineToZero'):
            le.deleteLineToZero.connect(lambda: fired.append(True))
        ev = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Backspace,
                       Qt.KeyboardModifier.ControlModifier, '\b')
        le.keyPressEvent(ev)
        assert le.text() == 'hola'          # nunca borra un carácter
        if hasattr(le, 'deleteLineToZero'):
            assert fired, 'Ctrl+⌫ quedó comido por el bloqueo de scriptio continua'


def test_caps_on_backspace_at_start_does_not_join_lines(qapp):
    """En F2, ⌫ en la columna 0 pega la línea con la anterior. Con Caps, tampoco."""
    app = FakeApp(True)
    le = DocEdit(app)
    le._keep_app = app
    le.setText('hola')
    le.setCursorPosition(0)
    joined = []
    le.backspaceAtStart.connect(lambda: joined.append(True))
    _type(le, Qt.Key.Key_Backspace, '\b')
    assert not joined
    assert le.text() == 'hola'
