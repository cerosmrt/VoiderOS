"""Alt+Left/Right with a selection: moving a selected phrase left a word that
ends right before punctuation glued to it (no space, like "realidad,") used
to get left behind — Federico: "la palabra realidad se queda porque esta
pegada a la coma, deberia moverse tambien, es un bug", caught moving a
selected phrase in the actual app.

Root cause: block_indices required a token's span to be FULLY contained in
the selection (s >= sel_start and e <= sel_end). A selection made by
shift-arrowing or double-click-dragging over a phrase stops right after the
last letter of the last word — it doesn't reach past the comma glued to it.
That word's token, though, is "realidad," (comma included, since core.split()
only splits on whitespace) — its span END is one character past the
selection's end, so the strict-containment check silently drops the token.
The block only picks up 'aplica a la' and swaps THAT, leaving 'realidad,'
behind. Fixed by switching to an overlap check (matching the old fallback
that was written for a different case and never reached this one).
"""
import pytest

pytest.importorskip("PyQt6")
from PyQt6.QtWidgets import QApplication

from circular_view import CustomLineEdit
from line_ring import LineRing
from f2_mixin import F2Mixin


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


def _app():
    class A(F2Mixin):
        pass
    return A()


def test_selection_stopping_before_glued_punctuation_still_moves_the_whole_word(qapp):
    ed = CustomLineEdit()
    ed.setText('eje aplica a la realidad, funciona bien')
    # Select "aplica a la realidad" — NOT the comma right after it, same as a
    # real shift-arrow or double-click-drag selection would stop.
    phrase = 'aplica a la realidad'
    start = ed.text().index(phrase)
    ed.setSelection(start, len(phrase))
    a = _app()
    saved = []
    a._swap_words(-1, editor=ed, ring=LineRing(['.']),
                  save=lambda undo_key=None: saved.append(1))
    assert ed.text() == 'aplica a la realidad, eje funciona bien'


def test_selection_reaching_the_comma_also_works(qapp):
    """Sanity check: if the selection DOES include the comma, it always worked."""
    ed = CustomLineEdit()
    ed.setText('eje aplica a la realidad, funciona bien')
    phrase = 'aplica a la realidad,'
    start = ed.text().index(phrase)
    ed.setSelection(start, len(phrase))
    a = _app()
    a._swap_words(-1, editor=ed, ring=LineRing(['.']),
                  save=lambda undo_key=None: None)
    assert ed.text() == 'aplica a la realidad, eje funciona bien'
