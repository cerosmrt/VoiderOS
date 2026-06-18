"""
Extended tests for line_ring.py covering methods not tested in test_line_ring.py:
  - insert (before and after current)
  - remove_current
  - to_list_from_current
  - rebase_to_current
  - edge cases: single element, empty-ish
"""
import pytest
from line_ring import LineRing


class TestLineRingInsert:
    def test_insert_before_current_default(self):
        ring = LineRing(['a', 'b', 'c'])
        ring.index = 1
        ring.insert('X')
        # insert at current index (before_current) shifts right
        assert ring.lines[1] == 'X'
        assert ring.lines[2] == 'b'

    def test_insert_after_current(self):
        ring = LineRing(['a', 'b', 'c'])
        ring.index = 0
        ring.insert('X', after_current=True)
        assert ring.lines[1] == 'X'
        assert ring.index == 1  # move(1) called

    def test_insert_after_current_moves_index(self):
        ring = LineRing(['a', 'b', 'c'])
        ring.index = 0
        ring.insert('Z', after_current=True)
        assert ring.current() == 'Z'

    def test_insert_at_end_before_current(self):
        ring = LineRing(['a', 'b', 'c'])
        ring.index = 2
        ring.insert('D')
        assert ring.lines[2] == 'D'
        assert ring.lines[3] == 'c'

    def test_insert_after_last(self):
        ring = LineRing(['a', 'b'])
        ring.index = 1
        ring.insert('c', after_current=True)
        assert 'c' in ring.lines
        assert ring.current() == 'c'

    def test_insert_empty_string(self):
        ring = LineRing(['a', 'b'])
        ring.insert('')
        assert '' in ring.lines

    def test_insert_unicode(self):
        ring = LineRing(['hello'])
        ring.insert('héllo wörld', after_current=True)
        assert ring.current() == 'héllo wörld'


class TestLineRingRemoveCurrent:
    def test_remove_middle(self):
        ring = LineRing(['a', 'b', 'c'])
        ring.index = 1
        ring.remove_current()
        assert 'b' not in ring.lines
        assert ring.lines == ['a', 'c']

    def test_remove_adjusts_index_when_at_end(self):
        ring = LineRing(['a', 'b', 'c'])
        ring.index = 2
        ring.remove_current()
        assert ring.index == 1  # clamped to last

    def test_remove_first(self):
        ring = LineRing(['a', 'b', 'c'])
        ring.index = 0
        ring.remove_current()
        assert ring.lines == ['b', 'c']
        assert ring.index == 0

    def test_remove_single_element(self):
        ring = LineRing(['only'])
        ring.remove_current()
        assert ring.lines == ['']
        assert ring.index == 0

    def test_remove_from_two_element_ring(self):
        ring = LineRing(['a', 'b'])
        ring.index = 1
        ring.remove_current()
        assert ring.lines == ['a']
        assert ring.index == 0


class TestLineRingToListFromCurrent:
    def test_from_start(self):
        ring = LineRing(['a', 'b', 'c'])
        ring.index = 0
        result = ring.to_list_from_current()
        assert result == ['a', 'b', 'c']

    def test_from_middle(self):
        ring = LineRing(['a', 'b', 'c'])
        ring.index = 1
        result = ring.to_list_from_current()
        assert result == ['b', 'c', 'a']

    def test_from_last(self):
        ring = LineRing(['a', 'b', 'c'])
        ring.index = 2
        result = ring.to_list_from_current()
        assert result == ['c', 'a', 'b']

    def test_length_preserved(self):
        ring = LineRing(['x', 'y', 'z', 'w'])
        ring.index = 2
        result = ring.to_list_from_current()
        assert len(result) == 4

    def test_single_element(self):
        ring = LineRing(['solo'])
        assert ring.to_list_from_current() == ['solo']


class TestLineRingRebaseToCurrent:
    def test_rebase_from_middle(self):
        ring = LineRing(['a', 'b', 'c', 'd', 'e'])
        ring.index = 2
        ring.rebase_to_current()
        assert ring.lines[0] == 'c'
        assert ring.index == 0
        assert ring.lines == ['c', 'd', 'e', 'a', 'b']

    def test_rebase_from_zero_is_noop(self):
        ring = LineRing(['a', 'b', 'c'])
        ring.index = 0
        original = list(ring.lines)
        ring.rebase_to_current()
        assert ring.lines == original
        assert ring.index == 0

    def test_rebase_from_last(self):
        ring = LineRing(['a', 'b', 'c'])
        ring.index = 2
        ring.rebase_to_current()
        assert ring.lines[0] == 'c'
        assert ring.index == 0

    def test_rebase_preserves_all_elements(self):
        ring = LineRing(['a', 'b', 'c', 'd'])
        ring.index = 3
        ring.rebase_to_current()
        assert set(ring.lines) == {'a', 'b', 'c', 'd'}


class TestLineRingEdgeCases:
    def test_get_on_single_element(self):
        ring = LineRing(['x'])
        assert ring.get(0) == 'x'
        assert ring.get(1) == 'x'
        assert ring.get(-1) == 'x'

    def test_move_zero_delta(self):
        ring = LineRing(['a', 'b', 'c'])
        ring.index = 1
        ring.move(0)
        assert ring.index == 1

    def test_move_full_circle(self):
        ring = LineRing(['a', 'b', 'c'])
        ring.move(3)
        assert ring.index == 0

    def test_get_large_positive_offset(self):
        ring = LineRing(['a', 'b', 'c'])
        ring.index = 0
        assert ring.get(10) == ring.lines[10 % 3]

    def test_get_large_negative_offset(self):
        ring = LineRing(['a', 'b', 'c'])
        ring.index = 0
        assert ring.get(-10) == ring.lines[(-10) % 3]

    def test_current_after_init(self):
        ring = LineRing(['first', 'second'])
        assert ring.current() == 'first'

    def test_empty_lines_move_is_noop(self):
        ring = LineRing.__new__(LineRing)
        ring.lines = []
        ring.index = 0
        ring.move(1)  # should not crash
        assert ring.index == 0

    def test_get_on_empty_lines(self):
        ring = LineRing.__new__(LineRing)
        ring.lines = []
        ring.index = 0
        assert ring.get() == ''

    def test_very_long_line(self):
        long_line = 'x' * 10000
        ring = LineRing([long_line, '.'])
        assert ring.current() == long_line
        assert len(ring.current()) == 10000

    def test_unicode_lines(self):
        lines = ['Ñoño', '日本語', 'مرحبا', 'héllo']
        ring = LineRing(lines)
        for i, l in enumerate(lines):
            ring.index = i
            assert ring.current() == l

    def test_init_from_empty_list_creates_single_empty(self):
        ring = LineRing([])
        assert ring.lines == ['']
        assert ring.index == 0

    def test_init_preserves_whitespace_lines(self):
        ring = LineRing(['  hello  ', '\ttab'])
        assert ring.lines[0] == '  hello  '
        assert ring.lines[1] == '\ttab'
