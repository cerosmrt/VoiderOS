"""F2 navigation caret rule: the caret defaults to the START of the destination
line, EXCEPT when it sat at the END — then it sticks to the end of the target
line (Up or Down)."""
import types

from line_ring import LineRing
from helpers import make_ring_app


class FakeEdit:
    """Minimal QLineEdit stand-in tracking text + cursor position."""
    def __init__(self):
        self._text = ''
        self._cur = 0
        self._ro = False

    def text(self):
        return self._text

    def setText(self, t):
        self._text = t
        self._cur = len(t)

    def cursorPosition(self):
        return self._cur

    def setCursorPosition(self, p):
        self._cur = p

    def setReadOnly(self, v):
        self._ro = v


def _nav_app(lines, index):
    from new_interface import FullscreenCircleApp

    app = make_ring_app(list(lines))
    app.line_ring = LineRing(list(lines))
    app.line_ring.index = index
    app.circular_view.editor = FakeEdit()
    app.circular_view.zero_marker = False
    app._para_focus = False
    app._para_focus_content = []
    app._save_last_line = lambda: None
    app._apply_editor_style = lambda *a, **k: None
    app._doc_navigate = types.MethodType(FullscreenCircleApp._doc_navigate, app)
    return app


def _prime(app, text, cursor):
    ed = app.circular_view.editor
    ed.setText(text)
    ed.setCursorPosition(cursor)
    return ed


def test_up_at_end_lands_at_end_of_prev_line():
    app = _nav_app(['.', 'short', 'a longer line'], index=2)
    ed = _prime(app, 'a longer line', len('a longer line'))
    app._doc_navigate(-1)
    assert app.line_ring.current() == 'short'
    assert ed.cursorPosition() == len('short')


def test_down_at_end_lands_at_end_of_next_line():
    app = _nav_app(['.', 'short', 'a longer line'], index=1)
    ed = _prime(app, 'short', len('short'))
    app._doc_navigate(1)
    assert app.line_ring.current() == 'a longer line'
    assert ed.cursorPosition() == len('a longer line')


def test_mid_line_goes_to_start():
    app = _nav_app(['.', 'short', 'a longer line'], index=2)
    ed = _prime(app, 'a longer line', 3)
    app._doc_navigate(-1)
    assert app.line_ring.current() == 'short'
    assert ed.cursorPosition() == 0


def test_up_sticks_to_end_across_multiple_lines():
    app = _nav_app(['.', 'aa', 'bbbb', 'cccccc'], index=3)
    ed = _prime(app, 'cccccc', len('cccccc'))
    app._doc_navigate(-1)
    assert app.line_ring.current() == 'bbbb'
    assert ed.cursorPosition() == len('bbbb')
    app._doc_navigate(-1)
    assert app.line_ring.current() == 'aa'
    assert ed.cursorPosition() == len('aa')
