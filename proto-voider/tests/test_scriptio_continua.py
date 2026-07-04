"""F1 scriptio-continua: while Caps Lock is ON (read from the kernel LED), the
spacebar releases the line to the void instead of typing a space. Caps OFF = space
types normally. The Caps Lock light IS the mode indicator."""
import types

import pytest

pytest.importorskip("PyQt6")
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtCore import Qt, QEvent

from helpers import make_ring_app
from widgets import CustomLineEdit


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


# ── _capslock_on reads the LED ────────────────────────────────────────────────

def test_capslock_on_reads_led(tmp_path):
    from new_interface import FullscreenCircleApp
    app = make_ring_app(['.'])
    app._capslock_on = types.MethodType(FullscreenCircleApp._capslock_on, app)
    led = tmp_path / 'input0::capslock'
    led.mkdir()
    app._CAPSLOCK_LED_GLOB = str(tmp_path / '*capslock*' / 'brightness')

    (led / 'brightness').write_text('0\n')
    assert app._capslock_on() is False
    (led / 'brightness').write_text('1\n')
    assert app._capslock_on() is True


def test_capslock_on_false_when_led_missing(tmp_path):
    from new_interface import FullscreenCircleApp
    app = make_ring_app(['.'])
    app._capslock_on = types.MethodType(FullscreenCircleApp._capslock_on, app)
    app._CAPSLOCK_LED_GLOB = str(tmp_path / 'nope' / 'brightness')
    assert app._capslock_on() is False


# ── spacebar behaviour in F1's entry widget ───────────────────────────────────

class _Parent:
    def __init__(self, caps):
        self.use_spacebar_for_void = False   # NOT the global spacebar mode
        self._caps = caps
    def _capslock_on(self):
        return self._caps


def _press_space(w):
    ev = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Space,
                   Qt.KeyboardModifier.NoModifier, ' ')
    w.keyPressEvent(ev)


def _entry(caps):
    w = CustomLineEdit(None)     # QLineEdit needs a real/absent QWidget parent
    w.parent = _Parent(caps)     # the app-like object the widget reads flags from
    return w


def test_space_voids_when_capslock_on(qapp):
    w = _entry(caps=True)
    fired = []
    w.spacePressed.connect(lambda: fired.append(1))
    _press_space(w)
    assert fired == [1]        # released the line
    assert w.text() == ''      # space was NOT typed


def test_space_types_when_capslock_off(qapp):
    w = _entry(caps=False)
    fired = []
    w.spacePressed.connect(lambda: fired.append(1))
    _press_space(w)
    assert fired == []         # did not void
    assert w.text() == ' '     # normal space typed
