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


# Scriptio continua es escribir sin volver atrás: con Caps prendido la línea de
# F1 sólo se escribe hacia adelante o se suelta al void. Backspace no borra.
# Sólo el input de F1 — F2/F3 es donde se edita, y ahí se borra siempre.
class TestCapsBlocksBackspaceInF1:
    def _edit(self, qapp, caps, text='hola'):
        app = FakeApp(caps)
        le = F1Edit(app)
        le._keep_app = app
        le.setText(text)
        le.setCursorPosition(len(text))
        return le

    def test_caps_on_backspace_erases_nothing(self, qapp):
        le = self._edit(qapp, caps=True)
        _type(le, Qt.Key.Key_Backspace, '\b')
        assert le.text() == 'hola'

    def test_caps_off_backspace_erases(self, qapp):
        le = self._edit(qapp, caps=False)
        _type(le, Qt.Key.Key_Backspace, '\b')
        assert le.text() == 'hol'

    def test_caps_on_blocks_ctrl_backspace_too(self, qapp):
        """En F1 Ctrl+⌫ sólo borraría una palabra — también es editar."""
        le = self._edit(qapp, caps=True)
        ev = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Backspace,
                       Qt.KeyboardModifier.ControlModifier, '\b')
        le.keyPressEvent(ev)
        assert le.text() == 'hola'


def test_caps_on_still_erases_in_the_doc_editor(qapp):
    """F2/F3 es el lugar donde se edita: Caps no lo toca."""
    app = FakeApp(True)
    le = DocEdit(app)
    le._keep_app = app
    le.setText('hola')
    le.setCursorPosition(4)
    _type(le, Qt.Key.Key_Backspace, '\b')
    assert le.text() == 'hol'
