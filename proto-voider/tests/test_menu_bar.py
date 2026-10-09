"""Clickable menu bar: appears when the mouse moves, vanishes when keys are used,
and clicking an entry reports its action."""
import pytest
from PyQt6.QtCore import Qt, QEvent, QPoint, QPointF
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import QApplication

from app_config import DEFAULT_CONFIG
from menu_model import MENUS
from menu_bar import MenuBar


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


def _bar(qapp):
    b = MenuBar()
    b.set_keybindings(DEFAULT_CONFIG['keybindings'])
    b.resize(900, 600)
    return b


def _click(bar, x, y):
    pos = QPointF(x, y)
    ev = QMouseEvent(QEvent.Type.MouseButtonPress, pos, bar.mapToGlobal(pos),
                     Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
                     Qt.KeyboardModifier.NoModifier)
    bar.mousePressEvent(ev)


def test_hidden_until_the_mouse_moves(qapp):
    b = _bar(qapp)
    assert not b.shown
    b.handle_event_type(QEvent.Type.MouseMove)
    assert b.shown


def test_key_press_hides_it_and_closes_any_dropdown(qapp):
    b = _bar(qapp)
    b.handle_event_type(QEvent.Type.MouseMove)
    b.open_menu(0)
    b.handle_event_type(QEvent.Type.KeyPress)
    assert not b.shown and b.open_index is None


def test_other_events_do_not_show_it(qapp):
    b = _bar(qapp)
    b.handle_event_type(QEvent.Type.Paint)
    b.handle_event_type(QEvent.Type.KeyRelease)
    assert not b.shown


def test_clicking_a_title_opens_its_dropdown(qapp):
    b = _bar(qapp)
    b.handle_event_type(QEvent.Type.MouseMove)
    x, y = b.title_center(1)
    _click(b, x, y)
    assert b.open_index == 1


def test_clicking_an_entry_emits_its_action_and_closes(qapp):
    b = _bar(qapp)
    got = []
    b.triggered.connect(got.append)
    b.handle_event_type(QEvent.Type.MouseMove)
    b.open_menu(0)
    x, y = b.entry_center(0, 0)
    _click(b, x, y)
    assert got == [MENUS[0][1][0][1]]
    assert b.open_index is None


def test_clicking_the_bar_title_again_closes_the_dropdown(qapp):
    b = _bar(qapp)
    b.handle_event_type(QEvent.Type.MouseMove)
    x, y = b.title_center(0)
    _click(b, x, y)
    _click(b, x, y)
    assert b.open_index is None


def test_hidden_bar_lets_mouse_through(qapp):
    b = _bar(qapp)
    assert b.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
    b.handle_event_type(QEvent.Type.MouseMove)
    assert not b.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)


def test_it_paints(qapp):
    b = _bar(qapp)
    b.handle_event_type(QEvent.Type.MouseMove)
    b.open_menu(2)
    assert not b.grab().isNull()
