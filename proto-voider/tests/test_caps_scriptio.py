"""Caps Lock in F1 only toggles scriptio-continua (spacebar voids the line) — it
must NOT uppercase. So while Caps is on, the F1 entry types in the normal case
(its effect is neutralised by swapping the case of each letter)."""
import pytest

pytest.importorskip("PyQt6")
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtCore import Qt, QEvent

from widgets import CustomLineEdit


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


class FakeParent:
    use_spacebar_for_void = False

    def __init__(self, caps):
        self._caps = caps

    def _capslock_on(self):
        return self._caps


def _le(qapp, caps):
    le = CustomLineEdit(None)
    le.parent = FakeParent(caps)
    return le


def _type(le, key, text, shift=False):
    mods = Qt.KeyboardModifier.ShiftModifier if shift else Qt.KeyboardModifier.NoModifier
    le.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, key, mods, text))


def test_caps_on_types_lowercase(qapp):
    le = _le(qapp, caps=True)
    _type(le, Qt.Key.Key_A, 'A')          # what the OS sends with Caps on
    assert le.text() == 'a'               # neutralised → normal case


def test_caps_on_shift_still_uppercases(qapp):
    le = _le(qapp, caps=True)
    _type(le, Qt.Key.Key_A, 'a', shift=True)   # Caps+Shift sends lowercase 'a'
    assert le.text() == 'A'


def test_caps_off_is_normal(qapp):
    le = _le(qapp, caps=False)
    _type(le, Qt.Key.Key_A, 'A')
    assert le.text() == 'A'               # untouched


def test_caps_on_leaves_digits_and_symbols(qapp):
    le = _le(qapp, caps=True)
    _type(le, Qt.Key.Key_5, '5')
    _type(le, Qt.Key.Key_Minus, '-')
    assert le.text() == '5-'
