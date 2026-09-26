"""Alt+F4: quit the app cleanly (via QWidget.close(), so closeEvent still
saves the working-set position) instead of relying on the window manager,
which a fullscreen key-capturing app like Voider may never hand the keypress
to."""
import pytest
from unittest.mock import MagicMock

pytest.importorskip("PyQt6")
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtCore import Qt, QEvent

from key_router_mixin import KeyRouterMixin
from app_config import DEFAULT_CONFIG, _parse_keybinding


@pytest.fixture(scope='module')
def qapp():
    yield QApplication.instance() or QApplication([])


def _app():
    class A(KeyRouterMixin):
        pass
    a = A()
    a._kb = {action: _parse_keybinding(ks)
             for action, ks in DEFAULT_CONFIG['keybindings'].items()}
    a._lock_screen = None
    a._f2_search_active = False
    a._f3_search_active = False
    a.current_view = 0
    a.close = MagicMock()
    return a


def _press(app, key, mods):
    ev = QKeyEvent(QEvent.Type.KeyPress, key, mods)
    app.keyPressEvent(ev)
    return ev


def test_alt_f4_is_bound_to_quit_app():
    key, mods = DEFAULT_CONFIG['keybindings']['quit_app'], None
    assert DEFAULT_CONFIG['keybindings']['quit_app'] == 'Alt+F4'


def test_alt_f4_calls_close(qapp):
    a = _app()
    key, mods = a._kb['quit_app']
    ev = _press(a, key, mods)
    a.close.assert_called_once()
    assert ev.isAccepted()


def test_plain_f4_does_not_close(qapp):
    """Plain F4 is view_f4 (switch to the reading view) — must not also quit."""
    a = _app()
    a.switch_to_view = MagicMock()
    key, _ = a._kb['quit_app']
    _press(a, key, Qt.KeyboardModifier.NoModifier)
    a.close.assert_not_called()
