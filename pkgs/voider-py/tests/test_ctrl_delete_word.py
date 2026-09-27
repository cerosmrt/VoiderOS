"""Ctrl+Delete: two different jobs sharing one key, split by cursor position.

At the START of the line (cursor position 0), Ctrl+Delete is the line-level
command it always was — send the line to trash / harvest / empty trash /
remove a working-set slot, depending on which view's editor fired it
(deleteLine + ctrlDeletePressed).

Federico: "ctrl delete should delete one word forward" — then, before I could
even ask about the conflict — "(except when at beginning of line)". Anywhere
else in the line it's ordinary text editing: delete the next word forward,
like any editor. Before this, ctrlDeletePressed fired unconditionally
regardless of cursor position, so mid-line Ctrl+Delete silently ate the
keystroke instead of deleting a word — Qt's native word-delete never got a
chance to run because the branch always called event.accept() itself.
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
    le.ctrlDeletePressed.connect(lambda: fired.append('ctrlDeletePressed'))
    return le, fired


def _ctrl_delete(le):
    ev = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Delete,
                   Qt.KeyboardModifier.ControlModifier)
    le.keyPressEvent(ev)
    return ev


def test_at_start_still_fires_the_line_level_signals(qapp):
    le, fired = _edit('hola mundo', pos=0)
    _ctrl_delete(le)
    assert fired == ['deleteLine', 'ctrlDeletePressed']
    assert le.text() == 'hola mundo'          # the line-level command owns it, not text editing


def test_mid_line_deletes_the_next_word_instead(qapp):
    le, fired = _edit('hola mundo bonito', pos=5)   # caret right after 'hola '
    _ctrl_delete(le)
    assert fired == []                         # no line-level command fired
    assert le.text() == 'hola bonito'           # 'mundo' (+ its trailing space) is gone


def test_at_end_of_line_does_nothing_odd(qapp):
    le, fired = _edit('hola', pos=4)            # caret at the very end, no word ahead
    _ctrl_delete(le)
    assert fired == []
    assert le.text() == 'hola'
