"""F10 keys panel widget: navigation, capture, signals, and it paints."""
import pytest
from PyQt6.QtCore import Qt, QEvent
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import QApplication

from keys_panel import KeysPanel

K, M = Qt.Key, Qt.KeyboardModifier
DEFAULTS = {'help': 'F11', 'view_f1': 'F1', 'rebase': 'Ctrl+0'}


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


def _press(panel, key, mods=M.NoModifier):
    ev = QKeyEvent(QEvent.Type.KeyPress, key, mods)
    panel.keyPressEvent(ev)
    return ev


def _panel(qapp, overrides=None):
    p = KeysPanel()
    p.resize(800, 600)
    p.load(DEFAULTS, overrides or {})
    return p


def test_arrows_and_pages_move_the_selection(qapp):
    p = _panel(qapp)
    _press(p, K.Key_Down)
    assert p.model.index == 1
    _press(p, K.Key_Up)
    _press(p, K.Key_Up)
    assert p.model.index == len(p.model.rows) - 1       # wrapped
    _press(p, K.Key_PageUp)
    assert p.model.index == 0


def test_enter_then_a_key_remaps_and_emits(qapp):
    p = _panel(qapp)
    got = []
    p.remapped.connect(got.append)
    _press(p, K.Key_Down)                  # help
    _press(p, K.Key_Return)                # start capture
    assert p.model.capturing
    _press(p, K.Key_F6)
    assert got == [{'help': 'F6'}]
    assert not p.model.capturing


def test_capture_swallows_keys_that_would_navigate(qapp):
    p = _panel(qapp)
    _press(p, K.Key_Down)
    _press(p, K.Key_Return)
    ev = _press(p, K.Key_Down)             # in capture: a candidate key, not movement
    assert ev.isAccepted()
    assert p.model.index == 1


def test_escape_in_capture_cancels_and_is_consumed(qapp):
    p = _panel(qapp)
    got = []
    p.remapped.connect(got.append)
    _press(p, K.Key_Down)
    _press(p, K.Key_Return)
    ev = _press(p, K.Key_Escape)
    assert ev.isAccepted() and not p.model.capturing and got == []


def test_escape_outside_capture_is_left_for_the_app(qapp):
    p = _panel(qapp)
    ev = _press(p, K.Key_Escape)
    ev2 = QKeyEvent(QEvent.Type.KeyPress, K.Key_Escape, M.NoModifier)
    ev2.ignore()
    p.keyPressEvent(ev2)
    assert not ev2.isAccepted()


def test_delete_resets_the_row(qapp):
    p = _panel(qapp, {'help': 'F5'})
    got = []
    p.remapped.connect(got.append)
    _press(p, K.Key_Down)
    _press(p, K.Key_Delete)
    assert got == [{}]


def test_enter_on_settings_row_opens_the_form(qapp):
    p = _panel(qapp)
    opened = []
    p.open_settings.connect(lambda: opened.append(1))
    _press(p, K.Key_Up)                    # wraps to the settings row
    _press(p, K.Key_Return)
    assert opened == [1]


def test_it_paints_without_error(qapp):
    p = _panel(qapp, {'help': 'F5'})
    _press(p, K.Key_Down)
    _press(p, K.Key_Return)                # capture prompt visible
    pix = p.grab()
    assert not pix.isNull()
