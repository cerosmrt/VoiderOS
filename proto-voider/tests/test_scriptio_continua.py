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


# ── Windows: el LED de Linux no existe, se le pregunta al sistema ─────────────
#
# En la versión compilada de Windows scriptio continua no andaba: _capslock_on lee
# /sys/class/leds/*capslock*/brightness, que sólo existe en Linux, así que Caps nunca
# se detectaba. Windows lo dice con GetKeyState(VK_CAPITAL): el bit de abajo es el
# estado "prendido".

class _FakeUser32:
    def __init__(self, value):
        self.value = value
        self.asked = []

    def GetKeyState(self, vk):
        self.asked.append(vk)
        return self.value


def _windows_app(monkeypatch, value, tmp_path):
    import ctypes
    import f1_mixin
    from new_interface import FullscreenCircleApp
    fake = types.SimpleNamespace(user32=_FakeUser32(value))
    monkeypatch.setattr(ctypes, 'windll', fake, raising=False)
    monkeypatch.setattr(f1_mixin.sys, 'platform', 'win32')
    app = make_ring_app(['.'])
    app._CAPSLOCK_LED_GLOB = str(tmp_path / 'nope' / 'brightness')   # no hay LED en Windows
    for nm in ('_capslock_on', '_caps_state_windows'):
        setattr(app, nm, types.MethodType(getattr(FullscreenCircleApp, nm), app))
    return app, fake.user32


def test_on_windows_caps_lock_comes_from_get_key_state(monkeypatch, tmp_path):
    app, user32 = _windows_app(monkeypatch, 1, tmp_path)
    assert app._capslock_on() is True
    assert user32.asked == [0x14]                 # VK_CAPITAL


def test_on_windows_caps_lock_off_is_off(monkeypatch, tmp_path):
    app, _ = _windows_app(monkeypatch, 0, tmp_path)
    assert app._capslock_on() is False


def test_on_windows_only_the_toggle_bit_counts_not_the_pressed_bit(monkeypatch, tmp_path):
    """El bit de arriba (0x8000) es "la tecla está apretada ahora"; el de abajo, "prendido"."""
    app, _ = _windows_app(monkeypatch, 0x8000, tmp_path)
    assert app._capslock_on() is False
    app, _ = _windows_app(monkeypatch, 0x8001, tmp_path)
    assert app._capslock_on() is True


def test_on_windows_a_failure_asking_the_system_means_off(monkeypatch, tmp_path):
    import ctypes
    app, _ = _windows_app(monkeypatch, 1, tmp_path)
    monkeypatch.setattr(ctypes, 'windll', None, raising=False)
    assert app._capslock_on() is False


def test_on_linux_it_still_reads_the_led_and_never_asks_windows(monkeypatch, tmp_path):
    import ctypes
    from new_interface import FullscreenCircleApp
    boom = types.SimpleNamespace(user32=types.SimpleNamespace(
        GetKeyState=lambda vk: pytest.fail('en Linux no se le pregunta a Windows')))
    monkeypatch.setattr(ctypes, 'windll', boom, raising=False)
    app = make_ring_app(['.'])
    for nm in ('_capslock_on', '_caps_state_windows'):
        setattr(app, nm, types.MethodType(getattr(FullscreenCircleApp, nm), app))
    led = tmp_path / 'input0::capslock'
    led.mkdir()
    (led / 'brightness').write_text('1\n')
    app._CAPSLOCK_LED_GLOB = str(tmp_path / '*capslock*' / 'brightness')
    assert app._capslock_on() is True
