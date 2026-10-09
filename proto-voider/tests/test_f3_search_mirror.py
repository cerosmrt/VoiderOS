"""Ctrl+F in F3 must look like F3: same list (separators included) and the cursor
on the same row. Typing then narrows to the matching entries."""
import os
import sys
import types
from unittest.mock import MagicMock

import pytest

pytest.importorskip("PyQt6")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_f3_undo import _f3_app
from new_interface import FullscreenCircleApp as App
from PyQt6.QtWidgets import QApplication


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


def _app(tmp_path):
    a = _f3_app(tmp_path, ['.', 'Uno.txt', 'Dos.txt', '.', 'Tres.txt'])
    for n in ('_open_f3_search', '_f3_search_changed', '_book_settle_pending',
              '_book_pending_index', '_book_materialize_pending'):
        setattr(a, n, types.MethodType(getattr(App, n), a))
    a._f3_search_bar = MagicMock()
    a._f3_search_show_center = MagicMock()
    a._f3_display_ring = None
    a.book_ring.index = 2
    return a


def test_search_opens_showing_the_same_list_as_f3(qapp, tmp_path):
    a = _app(tmp_path)
    before = list(a.book_ring.lines)
    a._open_f3_search()
    assert a._f3_display_ring.lines == before        # separators included
    assert a._f3_display_ring.index == 2             # same row highlighted


def test_clearing_the_query_goes_back_to_the_full_list(qapp, tmp_path):
    a = _app(tmp_path)
    before = list(a.book_ring.lines)
    a._open_f3_search()
    a._f3_search_changed('tre')
    assert a._f3_display_ring.lines == ['Tres'] or \
        [l for l in a._f3_display_ring.lines if l != '.'] == ['Tres']
    a._f3_search_changed('')
    assert a._f3_display_ring.lines == before
