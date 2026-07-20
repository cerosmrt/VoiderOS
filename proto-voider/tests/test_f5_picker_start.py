"""F5 send-catalogue opens positioned at the '0' portal.

The picker already lists all sendable chapters in library order (empty filter)
and filters as you type. The only new behaviour: it opens on the chapter nearest
the '0' portal in the library — your working cluster — instead of at index 0.
"""
import pytest

pytest.importorskip("PyQt6")

from f5_reorder_mixin import F5ReorderMixin


def _app(libs, src='0.txt'):
    class A(F5ReorderMixin):
        pass
    a = A()
    a._library_lines = list(libs)
    a.current_file_path = '/void/I/' + src
    a._f5_pick_filter = ''
    a._f5_picker_open = False
    a._f5_pick_match_idx = 0
    a._f5_para_count = lambda: 3
    a._f5_refresh = lambda: None
    return a


def test_start_idx_is_chapter_after_the_portal():
    # matches (library order, minus 0.txt): A, B, C, D at lib idx 0,1,3,4
    a = _app(['A.txt', 'B.txt', '0.txt', 'C.txt', 'D.txt'])
    # portal at lib idx 2 → nearest chapter, tie broken toward the one after → C
    assert a._f5_pick_start_idx() == 2      # index of C in the match list


def test_start_idx_anchors_on_active_chapter():
    # active file is a chapter (B), no portal involved: catalogue opens next to B
    a = _app(['A.txt', 'B.txt', 'C.txt', 'D.txt'], src='B.txt')
    # matches exclude B → A,C,D at lib idx 0,2,3; anchor=1; tie A/C → C (after)
    assert a._f5_pick_start_idx() == 1      # index of C in the match list


def test_start_idx_active_file_not_in_library_is_zero():
    a = _app(['A.txt', 'B.txt', 'C.txt'], src='Loose.txt')
    assert a._f5_pick_start_idx() == 0


def test_start_idx_portal_at_top():
    a = _app(['0.txt', 'A.txt', 'B.txt'])   # active is the 0 scratch
    assert a._f5_pick_start_idx() == 0      # A, right after the portal


def test_start_idx_no_portal_is_zero():
    a = _app(['A.txt', 'B.txt', 'C.txt'])
    assert a._f5_pick_start_idx() == 0


def test_start_idx_no_matches_is_zero():
    a = _app(['0.txt', '.'])
    assert a._f5_pick_start_idx() == 0


def test_open_picker_lands_on_the_portal_neighbour():
    a = _app(['A.txt', 'B.txt', '0.txt', 'C.txt', 'D.txt'])
    a._f5_open_picker()
    assert a._f5_picker_open is True
    assert a._f5_pick_filter == ''
    assert a._f5_pick_match_idx == 2        # opened on C, next to the portal
