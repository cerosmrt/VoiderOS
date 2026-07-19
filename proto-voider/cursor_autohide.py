from PyQt6.QtCore import Qt, QEvent
from PyQt6.QtGui import QCursor

# Mouse activity that brings the pointer back.
_MOUSE_EVENTS = (
    QEvent.Type.MouseMove,
    QEvent.Type.MouseButtonPress,
    QEvent.Type.MouseButtonRelease,
    QEvent.Type.MouseButtonDblClick,
    QEvent.Type.Wheel,
)


class CursorAutohide:
    """Hide the mouse pointer while typing; show it on any mouse activity.

    App-wide via QApplication's override-cursor stack. A single `_hidden` flag
    keeps the stack balanced (exactly one push while hidden, popped on show), so
    repeated keypresses or mouse moves never unbalance it.
    """

    def __init__(self, app, hidden=True):
        self._app = app
        self._hidden = False
        if hidden:
            self.hide()

    @property
    def hidden(self):
        return self._hidden

    def hide(self):
        if not self._hidden:
            self._app.setOverrideCursor(QCursor(Qt.CursorShape.BlankCursor))
            self._hidden = True

    def show(self):
        if self._hidden:
            self._app.restoreOverrideCursor()
            self._hidden = False

    def handle_event_type(self, etype):
        """Route a QEvent type: a key press hides the pointer, any mouse activity
        shows it. Never consumes the event; returns the new hidden state."""
        if etype == QEvent.Type.KeyPress:
            self.hide()
        elif etype in _MOUSE_EVENTS:
            self.show()
        return self._hidden
