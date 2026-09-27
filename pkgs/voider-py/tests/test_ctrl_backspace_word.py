"""Ctrl+Backspace at the end of a line used to delete the WHOLE line
(deleteLine), unlike everywhere else in the line, where it already fell
through to Qt's native delete-word-backward (no branch ever intercepted it
there). Federico: "quiero que ctrl backspace ya no borre la linea enterea
when at the end of a line, just last word (one word backwards no exception)"
— no position-based special case at all, unlike Ctrl+Delete (which keeps
its line-level meaning at position 0). Ctrl+Delete-at-start already covers
"send this line to trash", so nothing is lost by dropping the redundant
end-of-line path here.
"""
import pytest

pytest.importorskip("PyQt6")
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtCore import Qt, QEvent

from circular_view import CustomLineEdit


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


def _edit(text, pos):
    le = CustomLineEdit()
    le.setText(text)
    le.setCursorPosition(pos)
    fired = []
    le.deleteLine.connect(lambda: fired.append('deleteLine'))
    le.backspaceAtStart.connect(lambda: fired.append('backspaceAtStart'))
    return le, fired


def _ctrl_backspace(le):
    ev = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Backspace,
                   Qt.KeyboardModifier.ControlModifier)
    le.keyPressEvent(ev)
    return ev


def test_at_end_of_line_deletes_the_last_word_not_the_whole_line(qapp):
    le, fired = _edit('hola mundo bonito', pos=len('hola mundo bonito'))
    _ctrl_backspace(le)
    assert fired == []                        # no deleteLine fired
    assert le.text() == 'hola mundo '          # 'bonito' is gone, line survives


def test_mid_line_still_deletes_the_word_behind_the_caret(qapp):
    le, fired = _edit('hola mundo bonito', pos=len('hola mundo'))
    _ctrl_backspace(le)
    assert fired == []
    assert le.text() == 'hola  bonito'          # 'mundo' is gone


def test_at_start_of_line_is_unaffected(qapp):
    """Position 0 still means 'join with the previous line' (backspaceAtStart) —
    that path isn't the one Federico asked to change."""
    le, fired = _edit('hola', pos=0)
    _ctrl_backspace(le)
    assert fired == ['backspaceAtStart']
    assert le.text() == 'hola'
