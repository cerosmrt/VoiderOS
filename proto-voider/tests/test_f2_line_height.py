"""F2 line spacing must follow the font size.

Bug: CircularView.__init__ set `self.line_height = 38` once and nothing ever
updated it. The glyph height (fm.height()) grows with the font, but lines were
still placed every 38px, so at large sizes they overlapped and F2 became
unreadable. Spacing has to be derived from the font, not frozen at a number
that happened to suit the default size.
"""
import pytest

pytest.importorskip("PyQt6")
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QFont, QFontMetrics

from circular_view import CircularView
from line_ring import LineRing


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


def _view(size):
    v = CircularView(LineRing(['.', 'una linea', '.', 'otra']))
    v.setFont(QFont('EB Garamond', size))
    return v


def test_line_height_grows_with_the_font(qapp):
    assert _view(40).line_height > _view(12).line_height


def test_lines_never_overlap_at_any_size(qapp):
    # The whole bug in one assertion: spacing must leave room for the glyphs.
    for size in (10, 14, 22, 30, 38, 44, 52, 72):
        v = _view(size)
        glyph_h = QFontMetrics(v.font()).height()
        assert v.line_height >= glyph_h, (
            f"at {size}pt lines are {v.line_height}px apart "
            f"but the text is {glyph_h}px tall — they collide"
        )


def test_spacing_is_not_absurdly_loose(qapp):
    # Readable, not double-spaced: F2 shows a ring of lines, not a poster.
    for size in (14, 22, 38, 52):
        v = _view(size)
        glyph_h = QFontMetrics(v.font()).height()
        assert v.line_height <= glyph_h * 1.9


def test_default_size_keeps_the_look_it_always_had(qapp):
    # 38px was tuned by eye for the default size; stay near it so F2 doesn't
    # visibly change for someone who never touches the font size.
    v = _view(22)
    assert 32 <= v.line_height <= 46
