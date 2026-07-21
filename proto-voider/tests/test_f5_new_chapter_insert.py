"""A chapter created from the F5 catalogue lands right below the ACTIVE (origin)
file in the library, so it sits next to what you're working on."""
import pytest

pytest.importorskip("PyQt6")

from line_ring import LineRing
from f5_reorder_mixin import F5ReorderMixin


def _app(libs, active, cursor=0):
    class A(F5ReorderMixin):
        pass
    a = A()
    a._library_lines = list(libs)
    a.current_file_path = '/void/I/' + active
    a.book_ring = LineRing(list(libs))
    a.book_ring.index = cursor
    return a


def test_insert_just_below_active_file():
    a = _app(['A.txt', 'B.txt', 'C.txt'], 'B.txt')
    assert a._f5_new_chapter_insert_idx() == 2       # below B (idx 1)


def test_insert_below_active_at_top():
    a = _app(['A.txt', 'B.txt'], 'A.txt')
    assert a._f5_new_chapter_insert_idx() == 1


def test_fallback_to_cursor_when_active_absent():
    a = _app(['A.txt', 'B.txt'], 'Loose.txt', cursor=1)
    assert a._f5_new_chapter_insert_idx() == 1


def test_fallback_clamps_to_end():
    a = _app(['A.txt', 'B.txt'], 'Loose.txt', cursor=99)
    assert a._f5_new_chapter_insert_idx() == 2
