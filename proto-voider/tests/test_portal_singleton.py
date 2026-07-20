"""The '0' scratch portal is a singleton in the F3 library: _dedupe_portals()
keeps at most one, so the marker never piles up (the 0.txt file was always
single; only the F3 marker could duplicate)."""
import os
import pytest

pytest.importorskip("PyQt6")

from line_ring import LineRing
from io_mixin import IoMixin


def _ring_label(fn):
    if fn == '.':
        return '.'
    if fn.lower() == '0.txt':
        return '0'
    return os.path.splitext(fn)[0]


def _app(libs, idx=0):
    class A(IoMixin):
        pass
    a = A()
    a._library_lines = list(libs)
    a.book_ring = LineRing([_ring_label(l) for l in libs])
    a.book_ring.index = idx
    return a


def test_no_portal_returns_none():
    a = _app(['.', 'A.txt', 'B.txt'])
    assert a._dedupe_portals() is None
    assert a._library_lines == ['.', 'A.txt', 'B.txt']


def test_single_portal_unchanged():
    a = _app(['0.txt', 'A.txt'])
    assert a._dedupe_portals() == 0
    assert a._library_lines == ['0.txt', 'A.txt']


def test_two_portals_keep_first_by_default():
    a = _app(['0.txt', 'A.txt', '0.txt', 'B.txt'])
    surv = a._dedupe_portals()
    assert surv == 0
    assert a._library_lines == ['0.txt', 'A.txt', 'B.txt']
    assert a.book_ring.lines == ['0', 'A', 'B']       # arrays stay aligned


def test_keep_named_portal():
    a = _app(['0.txt', 'A.txt', '0.txt', 'B.txt'])
    surv = a._dedupe_portals(keep=2)                  # keep the second portal
    assert surv == 1                                  # its index after removal
    assert a._library_lines == ['A.txt', '0.txt', 'B.txt']


def test_index_clamped_after_removal():
    a = _app(['A.txt', '0.txt', '0.txt'], idx=2)
    a._dedupe_portals(keep=1)
    assert a.book_ring.index < len(a.book_ring.lines)
    assert a._library_lines == ['A.txt', '0.txt']


def test_three_portals_collapse_to_one():
    a = _app(['0.txt', '0.txt', '0.txt'])
    a._dedupe_portals()
    assert a._library_lines.count('0.txt') == 1
    assert a.book_ring.lines.count('0') == 1
