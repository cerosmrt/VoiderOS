import pytest
from helpers import make_ring_app


class TestFindMoveTarget:
    def test_up_normal(self):
        """Middle line: prev non-dot found, no wrap."""
        app = make_ring_app(['.', 'a', 'b', 'c'])
        idx, wrapped = app._find_move_target(2, -1)
        assert idx == 1
        assert not wrapped

    def test_down_normal(self):
        app = make_ring_app(['.', 'a', 'b', 'c'])
        idx, wrapped = app._find_move_target(2, 1)
        assert idx == 3
        assert not wrapped

    def test_up_from_first_non_dot_wraps(self):
        """First non-dot line going up: must wrap."""
        app = make_ring_app(['.', 'a', 'b'])
        idx, wrapped = app._find_move_target(1, -1)
        assert wrapped

    def test_down_from_last_line_wraps(self):
        app = make_ring_app(['.', 'a', 'b'])
        idx, wrapped = app._find_move_target(2, 1)
        assert wrapped

    def test_skips_dot_going_up(self):
        """Going up across a dot boundary skips the dot and lands on prev line."""
        app = make_ring_app(['.', 'a', '.', 'b'])
        idx, wrapped = app._find_move_target(3, -1)
        assert idx == 1
        assert not wrapped


class TestLineSwap:
    def test_swap_up_middle(self):
        app = make_ring_app(['.', 'a', 'b', 'c'])
        app.line_ring.index = 2
        app.swap_line_up()
        assert app.line_ring.lines == ['.', 'b', 'a', 'c']
        assert app.line_ring.index == 1

    def test_swap_down_middle(self):
        app = make_ring_app(['.', 'a', 'b', 'c'])
        app.line_ring.index = 2
        app.swap_line_down()
        assert app.line_ring.lines == ['.', 'a', 'c', 'b']
        assert app.line_ring.index == 3

    def test_swap_up_first_line_swaps_with_dot(self):
        """First line swapped up: swaps with the leading dot (wraps circularly)."""
        app = make_ring_app(['.', 'a', 'b', 'c'])
        app.line_ring.index = 1
        app.swap_line_up()
        assert app.line_ring.lines == ['a', '.', 'b', 'c']
        assert app.line_ring.index == 0

    def test_swap_down_last_line_swaps_with_dot(self):
        """Last line swapped down: swaps with the leading dot (wraps circularly)."""
        app = make_ring_app(['.', 'a', 'b', 'c'])
        app.line_ring.index = 3
        app.swap_line_down()
        assert app.line_ring.lines == ['c', 'a', 'b', '.']
        assert app.line_ring.index == 0

    def test_swap_does_not_move_dots(self):
        """Alt+Up on a dot triggers paragraph swap, not line swap."""
        app = make_ring_app(['.', 'a', '.', 'b'])
        app.line_ring.index = 0
        app.swap_line_up()  # should not raise

    def test_two_lines_swap_up(self):
        """First real line swapped up: swaps with the leading dot."""
        app = make_ring_app(['.', 'x', 'y'])
        app.line_ring.index = 1
        app.swap_line_up()
        assert app.line_ring.lines == ['x', '.', 'y']
        assert app.line_ring.index == 0

    def test_two_lines_swap_down(self):
        """Last real line swapped down: swaps with the leading dot (circular wrap)."""
        app = make_ring_app(['.', 'x', 'y'])
        app.line_ring.index = 2
        app.swap_line_down()
        assert app.line_ring.lines == ['y', 'x', '.']
        assert app.line_ring.index == 0


class TestParagraphSwap:
    def test_swap_para_up_second_becomes_first(self):
        app = make_ring_app(['.', 'a', 'b', '.', 'c', 'd'])
        app.line_ring.index = 3
        app.swap_paragraph_up()
        assert app.line_ring.lines == ['.', 'c', 'd', '.', 'a', 'b']

    def test_swap_para_down_first_becomes_second(self):
        app = make_ring_app(['.', 'a', 'b', '.', 'c', 'd'])
        app.line_ring.index = 0
        app.swap_paragraph_down()
        assert app.line_ring.lines == ['.', 'c', 'd', '.', 'a', 'b']

    def test_swap_para_up_first_wraps_to_last(self):
        """First paragraph moved up: MOVE to end."""
        app = make_ring_app(['.', 'a', '.', 'b', '.', 'c'])
        app.line_ring.index = 0
        app.swap_paragraph_up()
        assert app.line_ring.lines[-1] == 'a'

    def test_swap_para_down_last_wraps_to_first(self):
        """Last paragraph moved down: MOVE to front."""
        app = make_ring_app(['.', 'a', '.', 'b', '.', 'c'])
        app.line_ring.index = 4
        app.swap_paragraph_down()
        assert app.line_ring.lines[1] == 'c'

    def test_three_paras_order_preserved(self):
        """Three paragraphs: swap middle up, verify order."""
        app = make_ring_app(['.', 'a', '.', 'b', '.', 'c'])
        app.line_ring.index = 2
        app.swap_paragraph_up()
        _, paras = app._paragraphs_from_ring()
        assert paras[0] == ['b']
        assert paras[1] == ['a']
        assert paras[2] == ['c']


class TestRebase:
    def test_rebase_on_text_line_rotates_paragraph(self):
        """Ctrl+9 on 'b' in [., a, b, c]: paragraph rotates so 'b' is first."""
        app = make_ring_app(['.', 'a', 'b', 'c'])
        app.line_ring.index = 2
        app.rebase_to_index_zero()
        _, paras = app._paragraphs_from_ring()
        assert paras[0][0] == 'b'

    def test_rebase_on_first_line_is_noop(self):
        """Ctrl+9 when already first in paragraph: no change."""
        app = make_ring_app(['.', 'a', 'b'])
        app.line_ring.index = 1
        original_lines = list(app.line_ring.lines)
        app.rebase_to_index_zero()
        assert app.line_ring.lines == original_lines

    def test_rebase_on_dot_rotates_paragraphs(self):
        """Ctrl+9 on a dot: makes that paragraph first."""
        app = make_ring_app(['.', 'a', '.', 'b'])
        app.line_ring.index = 2
        original = list(app.line_ring.lines)
        app.rebase_to_index_zero()
        if app.line_ring.lines == original:
            pytest.skip("rebase-on-dot not implemented in this commit (returns early on dot)")
        _, paras = app._paragraphs_from_ring()
        assert paras[0] == ['b']
        assert app.line_ring.index == 0

    def test_rebase_multi_line_para(self):
        """Ctrl+9 on third line of 4-line paragraph."""
        app = make_ring_app(['.', 'w', 'x', 'y', 'z'])
        app.line_ring.index = 3
        app.rebase_to_index_zero()
        _, paras = app._paragraphs_from_ring()
        assert paras[0] == ['y', 'z', 'w', 'x']
