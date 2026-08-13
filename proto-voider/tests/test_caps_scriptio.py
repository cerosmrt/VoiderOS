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
