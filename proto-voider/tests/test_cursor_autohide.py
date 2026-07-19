"""CursorAutohide: hide the mouse pointer while typing, show it on mouse
activity, and keep QApplication's override-cursor stack balanced. Pure logic —
a FakeApp records push/pop so no real display is touched."""
import pytest

pytest.importorskip("PyQt6")
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QEvent

from cursor_autohide import CursorAutohide


@pytest.fixture(scope="module")
def qapp():
    # A QGuiApplication must exist to construct a QCursor.
    app = QApplication.instance() or QApplication([])
    yield app


class FakeApp:
    def __init__(self):
        self.depth = 0          # current override-cursor stack depth
        self.pushes = 0
        self.pops = 0

    def setOverrideCursor(self, cursor):
        self.depth += 1
        self.pushes += 1

    def restoreOverrideCursor(self):
        self.depth -= 1
        self.pops += 1


def test_starts_hidden(qapp):
    fa = FakeApp()
    c = CursorAutohide(fa)
    assert c.hidden is True
    assert fa.depth == 1 and fa.pushes == 1


def test_can_start_shown(qapp):
    fa = FakeApp()
    c = CursorAutohide(fa, hidden=False)
    assert c.hidden is False
    assert fa.depth == 0 and fa.pushes == 0


def test_mouse_move_shows_pointer(qapp):
    fa = FakeApp()
    c = CursorAutohide(fa)
    c.handle_event_type(QEvent.Type.MouseMove)
    assert c.hidden is False
    assert fa.depth == 0                      # stack popped back to baseline


def test_typing_hides_pointer(qapp):
    fa = FakeApp()
    c = CursorAutohide(fa, hidden=False)
    c.handle_event_type(QEvent.Type.KeyPress)
    assert c.hidden is True
    assert fa.depth == 1


@pytest.mark.parametrize("etype", [
    QEvent.Type.MouseMove,
    QEvent.Type.MouseButtonPress,
    QEvent.Type.MouseButtonRelease,
    QEvent.Type.MouseButtonDblClick,
    QEvent.Type.Wheel,
])
def test_any_mouse_activity_shows(qapp, etype):
    fa = FakeApp()
    c = CursorAutohide(fa)
    c.handle_event_type(etype)
    assert c.hidden is False


def test_repeated_typing_pushes_once(qapp):
    fa = FakeApp()
    c = CursorAutohide(fa, hidden=False)
    for _ in range(5):
        c.handle_event_type(QEvent.Type.KeyPress)
    assert fa.pushes == 1                      # idempotent while already hidden


def test_repeated_mouse_pops_once(qapp):
    fa = FakeApp()
    c = CursorAutohide(fa)                     # starts hidden (one push)
    for _ in range(5):
        c.handle_event_type(QEvent.Type.MouseMove)
    assert fa.pops == 1                        # idempotent while already shown


def test_stack_stays_balanced_over_a_mixed_sequence(qapp):
    fa = FakeApp()
    c = CursorAutohide(fa)
    seq = [QEvent.Type.KeyPress, QEvent.Type.KeyPress, QEvent.Type.MouseMove,
           QEvent.Type.Wheel, QEvent.Type.KeyPress, QEvent.Type.MouseButtonPress,
           QEvent.Type.KeyPress]
    for e in seq:
        c.handle_event_type(e)
    assert fa.depth in (0, 1)                  # never unbalanced
    assert fa.depth == (1 if c.hidden else 0)


def test_unrelated_event_is_ignored(qapp):
    fa = FakeApp()
    c = CursorAutohide(fa, hidden=False)
    c.handle_event_type(QEvent.Type.Paint)
    assert c.hidden is False and fa.pushes == 0
