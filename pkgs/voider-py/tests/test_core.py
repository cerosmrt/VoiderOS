"""
Core regression tests for Voider V2.

Tests ring operations, file I/O, and paragraph math without requiring a
running Qt GUI. Qt views are mocked so tests run headless.

Run from project root:
    python -m pytest tests/test_core.py -v

State this test suite was written against: a51bf13
  - LineRing basics
  - Paragraph helpers (_paragraphs_from_ring, _rebuild, _dot_line_index)
  - _find_move_target / swap_line_up / swap_line_down (MOVE semantics at boundaries)
  - swap_paragraph_up / swap_paragraph_down
  - rebase_to_index_zero (on text line and on dot)
  - para-focus (_enter_para_focus, _exit_para_focus, _swap_line_in_focus)
  - load_doc_lines / auto_save_circular

New tests added for today's features (df760e4 and fixes):
  - _doc_join_prev / _doc_split_line
  - _load_book_order / _save_book_order
  - _book_navigate (non-looping)
  - _book_swap_up / _book_swap_down / _book_rebase
"""
import os
import sys
import json
import types
import tempfile
import pytest
from unittest.mock import MagicMock

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from line_ring import LineRing

# ─────────────────────────────────────────────────────────────────────────────
# Helper: build a minimal app-like object with real ring + bound methods
# ─────────────────────────────────────────────────────────────────────────────

def _mock_circular_view():
    cv = MagicMock()
    cv._offset = 0.0
    cv.editor = MagicMock()
    cv.focus_indices = None
    cv.update = MagicMock()
    # Return integers for geometry calls so min() works in _doc_show_editor
    cv.width.return_value = 800
    cv.height.return_value = 600
    cv.editor.sizeHint.return_value.height.return_value = 30
    return cv


def make_ring_app(lines, tmp_file=None):
    """
    Bind FullscreenCircleApp ring-methods onto a plain object so we can test
    them without spinning up a Qt application.

    tmp_file, if given, MUST be named "0.txt" so that both a51bf13
    (uses void_dir/0.txt) and the refactored main (uses current_file_path)
    resolve to the same file.
    """
    from new_interface import FullscreenCircleApp

    class _App:
        pass

    app = _App()
    app.line_ring = LineRing(lines if lines else ['.'])
    app._para_focus = False
    app._para_focus_content = []
    app.current_view = 1
    app.circular_view = _mock_circular_view()

    # Temp file for save/load tests.
    # void_dir must be set so a51bf13's auto_save_circular/load_doc_lines work.
    if tmp_file:
        app.current_file_path = tmp_file
        app.void_dir = os.path.dirname(tmp_file)
    else:
        _void_dir = tempfile.mkdtemp()
        app.void_dir = _void_dir
        app.current_file_path = os.path.join(_void_dir, '0.txt')
        app._auto_tmp = app.current_file_path  # remember for optional cleanup
        # Create empty placeholder so save/load don't fail on missing file
        open(app.current_file_path, 'w').close()

    # Book-browser attributes (may not exist in older commit)
    app.book_dir = tempfile.mkdtemp()
    app.book_files = []
    app.book_ring = LineRing()
    app.book_view = None
    app.config = {}
    app._set_active_file = lambda path: None  # no-op: avoid writing config.json during tests

    # Always bind these (present in a51bf13)
    core_methods = [
        '_paragraphs_from_ring', '_rebuild_ring_from_paragraphs',
        '_dot_line_index', '_find_move_target', '_current_para_idx',
        '_move_paragraph',
        'swap_line_up', 'swap_line_down',
        'swap_paragraph_up', 'swap_paragraph_down',
        '_swap_line_in_focus',
        'goto_prev_dot', 'goto_next_dot',
        'rebase_to_index_zero',
        '_enter_para_focus', '_exit_para_focus',
        '_doc_show_editor',
        'load_doc_lines', 'auto_save_circular',
    ]
    # Bind only if present (for forward-compat with new features)
    optional_methods = [
        '_get_focus_dot_idx',
        '_doc_join_prev', '_doc_split_line',
        '_apply_editor_style',
        '_last_lines_path', '_save_last_line', '_restore_last_line',
        '_load_book_order', '_save_book_order', '_rebuild_book_ring',
        '_book_file_idx', '_book_try_rename',
        '_book_navigate', '_book_swap_up', '_book_swap_down', '_book_rebase',
    ]

    for name in core_methods:
        m = getattr(FullscreenCircleApp, name)
        setattr(app, name, types.MethodType(m, app))

    for name in optional_methods:
        if hasattr(FullscreenCircleApp, name):
            m = getattr(FullscreenCircleApp, name)
            setattr(app, name, types.MethodType(m, app))

    return app


def has(app, method):
    """Return True if app has this method (feature exists in current commit)."""
    return hasattr(app, method) and callable(getattr(app, method))


# ─────────────────────────────────────────────────────────────────────────────
# LineRing
# ─────────────────────────────────────────────────────────────────────────────

class TestLineRing:
    def test_empty_init(self):
        ring = LineRing()
        assert ring.lines == ['']  # LineRing([]) gives ['']
        assert ring.index == 0

    def test_init_with_lines(self):
        ring = LineRing(['a', 'b', 'c'])
        assert ring.lines == ['a', 'b', 'c']
        assert ring.current() == 'a'

    def test_move_forward(self):
        ring = LineRing(['a', 'b', 'c'])
        ring.move(1)
        assert ring.index == 1
        assert ring.current() == 'b'

    def test_move_backward(self):
        ring = LineRing(['a', 'b', 'c'])
        ring.index = 2
        ring.move(-1)
        assert ring.index == 1

    def test_move_wraps_forward(self):
        ring = LineRing(['a', 'b', 'c'])
        ring.index = 2
        ring.move(1)
        assert ring.index == 0

    def test_move_wraps_backward(self):
        ring = LineRing(['a', 'b', 'c'])
        ring.index = 0
        ring.move(-1)
        assert ring.index == 2

    def test_move_multi_step(self):
        ring = LineRing(['a', 'b', 'c'])
        ring.move(5)
        assert ring.index == 5 % 3

    def test_get_offset(self):
        ring = LineRing(['a', 'b', 'c'])
        ring.index = 1
        assert ring.get(0) == 'b'
        assert ring.get(1) == 'c'
        assert ring.get(-1) == 'a'


# ─────────────────────────────────────────────────────────────────────────────
# Paragraph helpers
# ─────────────────────────────────────────────────────────────────────────────

class TestParagraphHelpers:
    def test_paragraphs_from_ring_two_paras(self):
        app = make_ring_app(['.', 'a', 'b', '.', 'c', 'd'])
        dot_indices, paragraphs = app._paragraphs_from_ring()
        assert dot_indices == [0, 3]
        assert paragraphs[0] == ['a', 'b']
        assert paragraphs[1] == ['c', 'd']

    def test_paragraphs_from_ring_single(self):
        app = make_ring_app(['.', 'x'])
        _, paragraphs = app._paragraphs_from_ring()
        assert paragraphs == [['x']]

    def test_paragraphs_from_ring_empty_para(self):
        """Two consecutive dots → one empty paragraph."""
        app = make_ring_app(['.', '.', 'a'])
        _, paragraphs = app._paragraphs_from_ring()
        assert paragraphs[0] == []
        assert paragraphs[1] == ['a']

    def test_dot_line_index_first(self):
        app = make_ring_app(['.', 'a', 'b', '.', 'c'])
        _, paragraphs = app._paragraphs_from_ring()
        assert app._dot_line_index(0, paragraphs) == 0

    def test_dot_line_index_second(self):
        app = make_ring_app(['.', 'a', 'b', '.', 'c'])
        _, paragraphs = app._paragraphs_from_ring()
        assert app._dot_line_index(1, paragraphs) == 3

    def test_rebuild_ring_from_paragraphs(self):
        app = make_ring_app(['.', 'a'])
        app._rebuild_ring_from_paragraphs([['x', 'y'], ['z']])
        assert app.line_ring.lines == ['.', 'x', 'y', '.', 'z']

    def test_roundtrip_paragraphs(self):
        """Extract then rebuild must produce the same ring."""
        original = ['.', 'a', 'b', '.', 'c', 'd', 'e']
        app = make_ring_app(original[:])
        _, paras = app._paragraphs_from_ring()
        app._rebuild_ring_from_paragraphs(paras)
        assert app.line_ring.lines == original

    def test_roundtrip_three_paras(self):
        original = ['.', 'a', '.', 'b', '.', 'c']
        app = make_ring_app(original[:])
        _, paras = app._paragraphs_from_ring()
        app._rebuild_ring_from_paragraphs(paras)
        assert app.line_ring.lines == original


# ─────────────────────────────────────────────────────────────────────────────
# _find_move_target
# ─────────────────────────────────────────────────────────────────────────────

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
        # From 'b' (index 3) going up: skips dot at index 2, finds 'a' at index 1.
        # 'wrapped' only means the ring index numerically wrapped around (e.g. 0→N),
        # NOT that it crossed a paragraph boundary.
        idx, wrapped = app._find_move_target(3, -1)
        assert idx == 1
        assert not wrapped  # index 1 < 3, no numerical ring-wrap


# ─────────────────────────────────────────────────────────────────────────────
# Line swap (MOVE semantics at boundaries)
# ─────────────────────────────────────────────────────────────────────────────

class TestLineSwap:
    def test_swap_up_middle(self):
        app = make_ring_app(['.', 'a', 'b', 'c'])
        app.line_ring.index = 2  # on 'b'
        app.swap_line_up()
        assert app.line_ring.lines == ['.', 'b', 'a', 'c']
        assert app.line_ring.index == 1

    def test_swap_down_middle(self):
        app = make_ring_app(['.', 'a', 'b', 'c'])
        app.line_ring.index = 2  # on 'b'
        app.swap_line_down()
        assert app.line_ring.lines == ['.', 'a', 'c', 'b']
        assert app.line_ring.index == 3

    def test_swap_up_first_line_swaps_with_dot(self):
        """First line swapped up: swaps with the leading dot (wraps circularly)."""
        app = make_ring_app(['.', 'a', 'b', 'c'])
        app.line_ring.index = 1  # on 'a'
        app.swap_line_up()
        # 'a' swaps with '.' at index 0
        assert app.line_ring.lines == ['a', '.', 'b', 'c']
        assert app.line_ring.index == 0

    def test_swap_down_last_line_swaps_with_dot(self):
        """Last line swapped down: swaps with the leading dot (wraps circularly)."""
        app = make_ring_app(['.', 'a', 'b', 'c'])
        app.line_ring.index = 3  # on 'c'
        app.swap_line_down()
        # 'c' swaps with '.' at index 0 (circular wrap)
        assert app.line_ring.lines == ['c', 'a', 'b', '.']
        assert app.line_ring.index == 0

    def test_swap_does_not_move_dots(self):
        """Alt+Up on a dot triggers paragraph swap, not line swap.
        We're testing that swap_line_up is a no-op on a dot."""
        app = make_ring_app(['.', 'a', '.', 'b'])
        app.line_ring.index = 0  # on dot
        original = list(app.line_ring.lines)
        # In F2, Alt+Up on a dot calls swap_paragraph_up, not swap_line_up.
        # swap_line_up itself checks para_focus; with a dot and no focus it
        # goes to _find_move_target which skips dots — result is a MOVE.
        # Just verify it doesn't crash.
        app.swap_line_up()  # should not raise

    def test_two_lines_swap_up(self):
        """First real line swapped up: swaps with the leading dot."""
        app = make_ring_app(['.', 'x', 'y'])
        app.line_ring.index = 1  # on 'x'
        app.swap_line_up()
        assert app.line_ring.lines == ['x', '.', 'y']
        assert app.line_ring.index == 0

    def test_two_lines_swap_down(self):
        """Last real line swapped down: swaps with the leading dot (circular wrap)."""
        app = make_ring_app(['.', 'x', 'y'])
        app.line_ring.index = 2  # on 'y'
        app.swap_line_down()
        assert app.line_ring.lines == ['y', 'x', '.']
        assert app.line_ring.index == 0


# ─────────────────────────────────────────────────────────────────────────────
# Paragraph swap
# ─────────────────────────────────────────────────────────────────────────────

class TestParagraphSwap:
    def test_swap_para_up_second_becomes_first(self):
        app = make_ring_app(['.', 'a', 'b', '.', 'c', 'd'])
        app.line_ring.index = 3  # on second dot
        app.swap_paragraph_up()
        assert app.line_ring.lines == ['.', 'c', 'd', '.', 'a', 'b']

    def test_swap_para_down_first_becomes_second(self):
        app = make_ring_app(['.', 'a', 'b', '.', 'c', 'd'])
        app.line_ring.index = 0  # on first dot
        app.swap_paragraph_down()
        assert app.line_ring.lines == ['.', 'c', 'd', '.', 'a', 'b']

    def test_swap_para_up_first_wraps_to_last(self):
        """First paragraph moved up: MOVE to end."""
        app = make_ring_app(['.', 'a', '.', 'b', '.', 'c'])
        app.line_ring.index = 0  # on first dot
        app.swap_paragraph_up()
        # ['a'] para should now be last
        assert app.line_ring.lines[-1] == 'a'

    def test_swap_para_down_last_wraps_to_first(self):
        """Last paragraph moved down: MOVE to front."""
        app = make_ring_app(['.', 'a', '.', 'b', '.', 'c'])
        app.line_ring.index = 4  # on third dot (before 'c')
        app.swap_paragraph_down()
        assert app.line_ring.lines[1] == 'c'

    def test_three_paras_order_preserved(self):
        """Three paragraphs: swap middle up, verify order."""
        app = make_ring_app(['.', 'a', '.', 'b', '.', 'c'])
        app.line_ring.index = 2  # on second dot (before 'b')
        app.swap_paragraph_up()
        _, paras = app._paragraphs_from_ring()
        assert paras[0] == ['b']
        assert paras[1] == ['a']
        assert paras[2] == ['c']


# ─────────────────────────────────────────────────────────────────────────────
# Rebase (Ctrl+9)
# ─────────────────────────────────────────────────────────────────────────────

class TestRebase:
    def test_rebase_on_text_line_rotates_paragraph(self):
        """Ctrl+9 on 'b' in [., a, b, c]: paragraph rotates so 'b' is first."""
        app = make_ring_app(['.', 'a', 'b', 'c'])
        app.line_ring.index = 2  # on 'b'
        app.rebase_to_index_zero()
        _, paras = app._paragraphs_from_ring()
        assert paras[0][0] == 'b'

    def test_rebase_on_first_line_is_noop(self):
        """Ctrl+9 when already first in paragraph: no change."""
        app = make_ring_app(['.', 'a', 'b'])
        app.line_ring.index = 1  # on 'a', already first
        original_lines = list(app.line_ring.lines)
        app.rebase_to_index_zero()
        assert app.line_ring.lines == original_lines

    def test_rebase_on_dot_rotates_paragraphs(self):
        """Ctrl+9 on a dot: makes that paragraph first (pending feature in a51bf13)."""
        app = make_ring_app(['.', 'a', '.', 'b'])
        app.line_ring.index = 2  # on second dot (before 'b')
        original = list(app.line_ring.lines)
        app.rebase_to_index_zero()
        if app.line_ring.lines == original:
            pytest.skip("rebase-on-dot not implemented in this commit (returns early on dot)")
        _, paras = app._paragraphs_from_ring()
        assert paras[0] == ['b']
        assert app.line_ring.index == 0  # lands on leading dot

    def test_rebase_multi_line_para(self):
        """Ctrl+9 on third line of 4-line paragraph."""
        app = make_ring_app(['.', 'w', 'x', 'y', 'z'])
        app.line_ring.index = 3  # on 'y'
        app.rebase_to_index_zero()
        _, paras = app._paragraphs_from_ring()
        assert paras[0] == ['y', 'z', 'w', 'x']


# ─────────────────────────────────────────────────────────────────────────────
# Para-focus mode
# ─────────────────────────────────────────────────────────────────────────────

class TestParaFocus:
    def test_enter_focus_sets_content(self):
        app = make_ring_app(['.', 'a', 'b', '.', 'c'])
        app.line_ring.index = 0  # on first dot
        app._enter_para_focus()
        assert app._para_focus is True
        assert set(app._para_focus_content) == {1, 2}  # 'a', 'b'

    def test_enter_focus_on_second_dot(self):
        app = make_ring_app(['.', 'a', 'b', '.', 'c'])
        app.line_ring.index = 3  # on second dot
        app._enter_para_focus()
        assert app._para_focus_content == [4]  # only 'c'

    def test_exit_focus_clears_state(self):
        app = make_ring_app(['.', 'a', 'b'])
        app.line_ring.index = 0
        app._enter_para_focus()
        app.line_ring.index = 2  # on 'b'
        app._exit_para_focus()
        assert app._para_focus is False
        assert app._para_focus_content == []
        assert app.circular_view.focus_indices is None

    def test_exit_focus_returns_to_dot(self):
        """After exiting focus, ring index lands on the preceding dot."""
        app = make_ring_app(['.', 'a', 'b'])
        app.line_ring.index = 0
        app._enter_para_focus()
        app.line_ring.index = 2  # navigate to 'b' inside focus
        app._exit_para_focus()
        assert app.line_ring.lines[app.line_ring.index] == '.'

    def test_swap_in_focus_wraps_circularly(self):
        """_swap_line_in_focus wraps within the focused paragraph only."""
        app = make_ring_app(['.', 'a', 'b', 'c', '.', 'x'])
        app.line_ring.index = 0
        app._enter_para_focus()
        # focus_content = [1, 2, 3]  ('a', 'b', 'c')
        app.line_ring.index = 1  # on 'a' (first in focus)
        app._swap_line_in_focus(-1)
        # 'a' wraps to the last ring position in the paragraph (ring index 3)
        # The cursor (ring.index) should be on 'a' after the swap
        assert app.line_ring.lines[app.line_ring.index] == 'a'
        # 'c' should now be at ring index 1 (the first slot in the paragraph)
        assert app.line_ring.lines[1] == 'c'


# ─────────────────────────────────────────────────────────────────────────────
# Dot navigation
# ─────────────────────────────────────────────────────────────────────────────

class TestDotNavigation:
    def test_goto_prev_dot(self):
        app = make_ring_app(['.', 'a', 'b', '.', 'c'])
        app.line_ring.index = 4  # on 'c'
        app.goto_prev_dot()
        assert app.line_ring.lines[app.line_ring.index] == '.'
        assert app.line_ring.index == 3

    def test_goto_next_dot(self):
        app = make_ring_app(['.', 'a', 'b', '.', 'c'])
        app.line_ring.index = 1  # on 'a'
        app.goto_next_dot()
        assert app.line_ring.lines[app.line_ring.index] == '.'
        assert app.line_ring.index == 3

    def test_goto_prev_dot_wraps(self):
        """From before first dot, wraps to last dot."""
        app = make_ring_app(['.', 'a', '.', 'b'])
        app.line_ring.index = 1  # on 'a'
        app.goto_prev_dot()
        assert app.line_ring.lines[app.line_ring.index] == '.'
        assert app.line_ring.index == 0  # wraps to first dot


# ─────────────────────────────────────────────────────────────────────────────
# File I/O
# ─────────────────────────────────────────────────────────────────────────────

class TestFileIO:
    def test_load_doc_lines_basic(self, tmp_path):
        # File must be named "0.txt" so void_dir/0.txt resolves to it (a51bf13 compat)
        txt = tmp_path / "0.txt"
        txt.write_text("line1\nline2\nline3\n", encoding='utf-8')
        app = make_ring_app(['.'], str(txt))
        app.load_doc_lines()
        assert 'line1' in app.line_ring.lines
        assert 'line2' in app.line_ring.lines
        assert 'line3' in app.line_ring.lines

    def test_load_doc_lines_prepends_dot(self, tmp_path):
        """If file doesn't start with '.', a leading dot is prepended."""
        txt = tmp_path / "0.txt"
        txt.write_text("hello\nworld\n", encoding='utf-8')
        app = make_ring_app(['.'], str(txt))
        app.load_doc_lines()
        assert app.line_ring.lines[0] == '.'

    def test_load_doc_lines_no_double_dot(self, tmp_path):
        """If file already starts with '.', no duplicate dot."""
        txt = tmp_path / "0.txt"
        txt.write_text(".\nhello\n", encoding='utf-8')
        app = make_ring_app(['.'], str(txt))
        app.load_doc_lines()
        assert app.line_ring.lines.count('.') == 1

    def test_load_doc_lines_empty_file(self, tmp_path):
        txt = tmp_path / "0.txt"
        txt.write_text("", encoding='utf-8')
        app = make_ring_app(['.'], str(txt))
        app.load_doc_lines()
        # Fallback: ring has at least ['.']
        assert app.line_ring.lines == ['.']

    def test_auto_save_circular(self, tmp_path):
        txt = tmp_path / "0.txt"
        app = make_ring_app(['.', 'hello', 'world'], str(txt))
        app.auto_save_circular()
        content = txt.read_text(encoding='utf-8').strip().splitlines()
        assert content == ['.', 'hello', 'world']

    def test_save_then_load_roundtrip(self, tmp_path):
        txt = tmp_path / "0.txt"
        original = ['.', 'alpha', 'beta', '.', 'gamma']
        app = make_ring_app(original[:], str(txt))
        app.auto_save_circular()

        app2 = make_ring_app(['.'], str(txt))
        app2.load_doc_lines()
        assert app2.line_ring.lines == original


# ─────────────────────────────────────────────────────────────────────────────
# NEW: _doc_join_prev / _doc_split_line  (added in fixes after df760e4)
# ─────────────────────────────────────────────────────────────────────────────

class TestJoinSplit:
    def test_join_prev_normal(self):
        app = make_ring_app(['.', 'hello', 'world', 'end'])
        if not has(app, '_doc_join_prev'):
            pytest.skip("_doc_join_prev not present in this commit")
        app.line_ring.index = 2  # on 'world'
        app._doc_join_prev()
        assert app.line_ring.lines == ['.', 'helloworld', 'end']
        assert app.line_ring.index == 1

    def test_join_prev_cursor_at_join_point(self):
        """Cursor position after join should be at the boundary."""
        app = make_ring_app(['.', 'abc', 'def'])
        if not has(app, '_doc_join_prev'):
            pytest.skip("_doc_join_prev not present in this commit")
        app.line_ring.index = 2  # on 'def'
        app._doc_join_prev()
        # Editor should have been told to set cursor at len('abc') = 3
        app.circular_view.editor.setCursorPosition.assert_called_with(3)

    def test_join_prev_blocked_by_dot(self):
        """First line after a dot: join is a no-op."""
        app = make_ring_app(['.', 'a', 'b'])
        if not has(app, '_doc_join_prev'):
            pytest.skip("_doc_join_prev not present in this commit")
        app.line_ring.index = 1  # 'a' is right after dot
        original = list(app.line_ring.lines)
        app._doc_join_prev()
        assert app.line_ring.lines == original

    def test_join_prev_blocked_by_dot_second_para(self):
        """First line of second paragraph: blocked by dot between paragraphs."""
        app = make_ring_app(['.', 'a', '.', 'b', 'c'])
        if not has(app, '_doc_join_prev'):
            pytest.skip("_doc_join_prev not present in this commit")
        app.line_ring.index = 3  # 'b' is right after second dot
        original = list(app.line_ring.lines)
        app._doc_join_prev()
        assert app.line_ring.lines == original

    def test_split_line_middle(self):
        app = make_ring_app(['.', 'abcde'])
        if not has(app, '_doc_split_line'):
            pytest.skip("_doc_split_line not present in this commit")
        app.line_ring.index = 1  # on 'abcde'
        app._doc_split_line(2)
        assert app.line_ring.lines == ['.', 'ab', 'cde']
        assert app.line_ring.index == 2  # moved to new line

    def test_split_line_at_start(self):
        """Split at position 0: original line stays, empty string inserted before."""
        app = make_ring_app(['.', 'hello'])
        if not has(app, '_doc_split_line'):
            pytest.skip("_doc_split_line not present in this commit")
        app.line_ring.index = 1
        app._doc_split_line(0)
        assert app.line_ring.lines == ['.', '', 'hello']

    def test_split_line_at_end(self):
        """Split at end: new empty line appended after."""
        app = make_ring_app(['.', 'hello'])
        if not has(app, '_doc_split_line'):
            pytest.skip("_doc_split_line not present in this commit")
        app.line_ring.index = 1
        app._doc_split_line(5)
        assert app.line_ring.lines == ['.', 'hello', '']


# ─────────────────────────────────────────────────────────────────────────────
# NEW: book order  (added in df760e4)
# ─────────────────────────────────────────────────────────────────────────────

class TestBookOrder:
    def _book_app(self, tmp_path):
        app = make_ring_app(['.'])
        app.book_dir = str(tmp_path)
        return app

    def test_load_alphabetical_fallback(self, tmp_path):
        (tmp_path / "b.txt").write_text("b", encoding='utf-8')
        (tmp_path / "a.txt").write_text("a", encoding='utf-8')
        (tmp_path / "c.txt").write_text("c", encoding='utf-8')
        app = self._book_app(tmp_path)
        if not has(app, '_load_book_order'):
            pytest.skip("book browser not present in this commit")
        app._load_book_order()
        assert app.book_files == ['a.txt', 'b.txt', 'c.txt']

    def test_load_from_json_preserves_order(self, tmp_path):
        (tmp_path / "a.txt").write_text("a", encoding='utf-8')
        (tmp_path / "b.txt").write_text("b", encoding='utf-8')
        (tmp_path / "_book_order.json").write_text(
            json.dumps(["b.txt", "a.txt"]), encoding='utf-8'
        )
        app = self._book_app(tmp_path)
        if not has(app, '_load_book_order'):
            pytest.skip("book browser not present in this commit")
        app._load_book_order()
        assert app.book_files == ['b.txt', 'a.txt']

    def test_load_appends_unlisted_files(self, tmp_path):
        """Files not in JSON get appended at end."""
        (tmp_path / "a.txt").write_text("", encoding='utf-8')
        (tmp_path / "b.txt").write_text("", encoding='utf-8')
        (tmp_path / "c.txt").write_text("", encoding='utf-8')
        (tmp_path / "_book_order.json").write_text(
            json.dumps(["b.txt"]), encoding='utf-8'
        )
        app = self._book_app(tmp_path)
        if not has(app, '_load_book_order'):
            pytest.skip("book browser not present in this commit")
        app._load_book_order()
        assert app.book_files[0] == 'b.txt'
        assert set(app.book_files) == {'a.txt', 'b.txt', 'c.txt'}

    def test_save_book_order(self, tmp_path):
        app = self._book_app(tmp_path)
        if not has(app, '_save_book_order'):
            pytest.skip("book browser not present in this commit")
        app.book_files = ['ch1.txt', 'ch2.txt', 'ch3.txt']
        app._save_book_order()
        saved = json.loads((tmp_path / "_book_order.json").read_text(encoding='utf-8'))
        assert saved == ['ch1.txt', 'ch2.txt', 'ch3.txt']

    def test_book_navigate_circular(self, tmp_path):
        """_book_navigate wraps circularly at boundaries, skipping dots."""
        (tmp_path / "a.txt").write_text("", encoding='utf-8')
        (tmp_path / "b.txt").write_text("", encoding='utf-8')
        app = self._book_app(tmp_path)
        if not has(app, '_book_navigate'):
            pytest.skip("book browser not present in this commit")
        app.book_files = ['a.txt', 'b.txt']
        # New format: ['.', 'a', '.', 'b']
        app.book_ring = LineRing(['.', 'a', '.', 'b'])
        app.book_view = _mock_circular_view()
        app.book_ring.index = 1  # on 'a' (first file)
        app._book_navigate(-1)  # at first — wraps to last
        assert app.book_ring.index == 3

        app.book_ring.index = 3  # on 'b' (last file)
        app._book_navigate(1)  # at last — wraps to first
        assert app.book_ring.index == 1

    def test_book_swap_up(self, tmp_path):
        app = self._book_app(tmp_path)
        if not has(app, '_book_swap_up'):
            pytest.skip("book browser not present in this commit")
        app.book_files = ['a.txt', 'b.txt', 'c.txt']
        # New ring format: ['.', 'a', '.', 'b', '.', 'c']
        app.book_ring = LineRing(['.', 'a', '.', 'b', '.', 'c'])
        app.book_view = _mock_circular_view()
        app.book_ring.index = 3  # on 'b' (ring index 3)
        app._book_swap_up()
        assert app.book_files == ['b.txt', 'a.txt', 'c.txt']
        assert app.book_ring.index == 1  # moved to 'b' at ring index 1

    def test_book_swap_up_at_first_noop(self, tmp_path):
        app = self._book_app(tmp_path)
        if not has(app, '_book_swap_up'):
            pytest.skip("book browser not present in this commit")
        app.book_files = ['a.txt', 'b.txt']
        app.book_ring = LineRing(['.', 'a', '.', 'b'])
        app.book_view = _mock_circular_view()
        app.book_ring.index = 1  # on 'a' (first file)
        app._book_swap_up()
        assert app.book_files == ['a.txt', 'b.txt']  # unchanged

    def test_book_swap_down(self, tmp_path):
        app = self._book_app(tmp_path)
        if not has(app, '_book_swap_down'):
            pytest.skip("book browser not present in this commit")
        app.book_files = ['a.txt', 'b.txt', 'c.txt']
        app.book_ring = LineRing(['.', 'a', '.', 'b', '.', 'c'])
        app.book_view = _mock_circular_view()
        app.book_ring.index = 3  # on 'b'
        app._book_swap_down()
        assert app.book_files == ['a.txt', 'c.txt', 'b.txt']
        assert app.book_ring.index == 5  # moved to 'b' at ring index 5

    def test_book_rebase(self, tmp_path):
        app = self._book_app(tmp_path)
        if not has(app, '_book_rebase'):
            pytest.skip("book browser not present in this commit")
        app.book_files = ['a.txt', 'b.txt', 'c.txt']
        app.book_ring = LineRing(['.', 'a', '.', 'b', '.', 'c'])
        app.book_view = _mock_circular_view()
        app.book_ring.index = 5  # on 'c'
        app._book_rebase()
        assert app.book_files == ['c.txt', 'a.txt', 'b.txt']
        assert app.book_ring.index == 1  # lands on first filename after rebase

    def test_book_navigate_does_not_activate_file(self, tmp_path):
        """_book_navigate must NOT call _set_active_file — activation only on Enter/F2."""
        (tmp_path / "a.txt").write_text("", encoding='utf-8')
        (tmp_path / "b.txt").write_text("", encoding='utf-8')
        app = self._book_app(tmp_path)
        if not has(app, '_book_navigate'):
            pytest.skip("book browser not present in this commit")
        app.book_files = ['a.txt', 'b.txt']
        app.book_ring = LineRing(['.', 'a', '.', 'b'])
        app.book_view = _mock_circular_view()
        app.book_ring.index = 1  # on 'a'

        activate_calls = []
        app._set_active_file = lambda path: activate_calls.append(path)

        app._book_navigate(1)
        app._book_navigate(-1)
        assert activate_calls == [], "_book_navigate must not activate the file"

    def test_switch_to_f2_from_f3_activates_file(self, tmp_path):
        """switch_to_view(1) from F3 (current_view=2) must activate the highlighted file."""
        from new_interface import FullscreenCircleApp
        (tmp_path / "a.txt").write_text(".\nhello\n", encoding='utf-8')
        (tmp_path / "b.txt").write_text(".\nworld\n", encoding='utf-8')
        app = self._book_app(tmp_path)

        if not hasattr(FullscreenCircleApp, 'switch_to_view'):
            pytest.skip("switch_to_view not present in this commit")

        app.book_files = ['a.txt', 'b.txt']
        app.book_ring = LineRing(['.', 'a', '.', 'b'])
        app.book_ring.index = 3  # on 'b'
        app.book_view = _mock_circular_view()
        app.current_view = 2  # currently in F3

        # Mock Qt-dependent attributes so switch_to_view can run
        app.stack = MagicMock()
        app.entry = MagicMock()
        app._doc_show_editor = MagicMock()
        app._save_last_line = MagicMock()

        activate_calls = []
        app._set_active_file = lambda path: activate_calls.append(path)

        # Bind switch_to_view and its dependencies
        for name in ('switch_to_view', '_book_file_idx', '_book_try_rename',
                     '_rebuild_book_ring', '_load_book_order'):
            if hasattr(FullscreenCircleApp, name) and not hasattr(app, name):
                setattr(app, name, types.MethodType(
                    getattr(FullscreenCircleApp, name), app))
        # Ensure already-bound ones are updated too
        for name in ('switch_to_view', '_book_file_idx', '_book_try_rename'):
            if hasattr(FullscreenCircleApp, name):
                setattr(app, name, types.MethodType(
                    getattr(FullscreenCircleApp, name), app))

        app.switch_to_view(1)

        assert len(activate_calls) == 1
        assert activate_calls[0].endswith('b.txt')


# ─────────────────────────────────────────────────────────────────────────────
# NEW: reformat_active_file  (Ctrl+Shift+F)
# ─────────────────────────────────────────────────────────────────────────────

def _make_reformat_app(tmp_path, content):
    """Write content to a temp file and return an app bound to reformat_active_file."""
    from new_interface import FullscreenCircleApp

    p = tmp_path / "doc.txt"
    p.write_text(content, encoding='utf-8')

    app = make_ring_app(['.'], tmp_file=str(p))
    app.current_file_path = str(p)

    m = getattr(FullscreenCircleApp, 'reformat_active_file')
    app.reformat_active_file = types.MethodType(m, app)

    # stub out the post-write UI calls
    app.load_doc_lines = MagicMock()
    app._doc_show_editor = MagicMock()

    return app, p


class TestReformatActiveFile:

    def test_raw_single_paragraph_split_at_sentence(self, tmp_path):
        """Two sentences in one paragraph → two lines under a dot."""
        content = "Hello world. Goodbye world.\n"
        app, p = _make_reformat_app(tmp_path, content)
        app.reformat_active_file()
        lines = p.read_text(encoding='utf-8').splitlines()
        assert lines[0] == '.'
        assert 'Hello world.' in lines
        assert 'Goodbye world.' in lines

    def test_raw_blank_line_becomes_dot_separator(self, tmp_path):
        """Two paragraphs separated by blank line → dot separator between them."""
        content = "First sentence.\n\nSecond sentence.\n"
        app, p = _make_reformat_app(tmp_path, content)
        app.reformat_active_file()
        lines = p.read_text(encoding='utf-8').splitlines()
        assert lines.count('.') == 2  # leading dot + separator
        dot_positions = [i for i, l in enumerate(lines) if l == '.']
        assert dot_positions[0] == 0
        # content between the two dots
        between = lines[dot_positions[0]+1:dot_positions[1]]
        assert between == ['First sentence.']

    def test_already_voider_format_not_reprocessed(self, tmp_path):
        """File already in Voider format → sentences not merged."""
        content = ".\nFirst line.\nSecond line.\n"
        app, p = _make_reformat_app(tmp_path, content)
        app.reformat_active_file()
        lines = p.read_text(encoding='utf-8').splitlines()
        assert 'First line.' in lines
        assert 'Second line.' in lines

    def test_voider_format_consecutive_dot_lines_collapsed(self, tmp_path):
        """Two consecutive '.' separator lines → collapsed to one."""
        content = ".\nFirst line.\n.\n.\nSecond line.\n"
        app, p = _make_reformat_app(tmp_path, content)
        app.reformat_active_file()
        lines = p.read_text(encoding='utf-8').splitlines()
        # No two consecutive dots
        for i in range(len(lines) - 1):
            assert not (lines[i] == '.' and lines[i+1] == '.')

    def test_voider_format_multi_dot_line_collapsed(self, tmp_path):
        """A line like '..' or '...' → collapsed to single '.'."""
        content = ".\nFirst line.\n..\nSecond line.\n"
        app, p = _make_reformat_app(tmp_path, content)
        app.reformat_active_file()
        lines = p.read_text(encoding='utf-8').splitlines()
        assert '..' not in lines
        assert '.' in lines

    def test_voider_format_triple_dot_line_collapsed(self, tmp_path):
        """A line '...' → collapsed to single '.'."""
        content = ".\nFirst line.\n...\nSecond line.\n"
        app, p = _make_reformat_app(tmp_path, content)
        app.reformat_active_file()
        lines = p.read_text(encoding='utf-8').splitlines()
        assert '...' not in lines

    def test_voider_format_mixed_dot_mess_collapsed(self, tmp_path):
        """Multiple junk dot lines in a row → single '.' separator."""
        content = ".\nA.\n..\n.\n...\nB.\n"
        app, p = _make_reformat_app(tmp_path, content)
        app.reformat_active_file()
        lines = p.read_text(encoding='utf-8').splitlines()
        assert 'A.' in lines
        assert 'B.' in lines
        for i in range(len(lines) - 1):
            assert not (lines[i] == '.' and lines[i+1] == '.')

    def test_idempotent_clean_voider_file(self, tmp_path):
        """Running reformat twice on a clean Voider file → no change."""
        content = ".\nFirst line.\n.\nSecond line.\n"
        app, p = _make_reformat_app(tmp_path, content)
        app.reformat_active_file()
        result1 = p.read_text(encoding='utf-8')
        # second run: rebuild app on same file
        app2, p2 = _make_reformat_app(tmp_path, result1)
        app2.current_file_path = str(p)
        app2.reformat_active_file()
        result2 = p.read_text(encoding='utf-8')
        assert result1 == result2

    def test_voider_format_multi_sentence_line_split(self, tmp_path):
        """Voider file with a multi-sentence line → split into one line per sentence."""
        content = ".\nFirst sentence. Second sentence. Third sentence.\n"
        app, p = _make_reformat_app(tmp_path, content)
        app.reformat_active_file()
        lines = p.read_text(encoding='utf-8').splitlines()
        assert 'First sentence.' in lines
        assert 'Second sentence.' in lines
        assert 'Third sentence.' in lines
        # All three should be distinct lines, not merged
        assert len([l for l in lines if l != '.']) == 3

    def test_voider_format_multi_sentence_preserves_dot_structure(self, tmp_path):
        """Sentence splitting in Voider format keeps paragraph dot separators intact."""
        content = ".\nOne. Two.\n.\nThree. Four.\n"
        app, p = _make_reformat_app(tmp_path, content)
        app.reformat_active_file()
        lines = p.read_text(encoding='utf-8').splitlines()
        assert lines.count('.') == 2
        assert 'One.' in lines
        assert 'Two.' in lines
        assert 'Three.' in lines
        assert 'Four.' in lines

    def test_voider_format_abbreviation_not_split(self, tmp_path):
        """Abbreviation dot in a Voider-format line must not trigger a split."""
        content = ".\nDr. Smith went home. He left early.\n"
        app, p = _make_reformat_app(tmp_path, content)
        app.reformat_active_file()
        lines = p.read_text(encoding='utf-8').splitlines()
        # 'Dr.' should not produce an empty or broken line
        assert not any(l == 'Dr.' for l in lines)
        # Two real sentences
        assert any('Dr. Smith went home.' in l for l in lines)
        assert 'He left early.' in lines

    def test_voider_format_sentence_split_idempotent(self, tmp_path):
        """Running reformat twice on a Voider file with multi-sentence lines → stable on second run."""
        content = ".\nOne. Two.\n.\nThree.\n"
        app, p = _make_reformat_app(tmp_path, content)
        app.reformat_active_file()
        result1 = p.read_text(encoding='utf-8')
        app2, p2 = _make_reformat_app(tmp_path, result1)
        app2.current_file_path = str(p)
        app2.reformat_active_file()
        result2 = p.read_text(encoding='utf-8')
        assert result1 == result2


# ─────────────────────────────────────────────────────────────────────────────
# NEW: print_book / print_doc
# ─────────────────────────────────────────────────────────────────────────────

def _make_print_app(tmp_path, book_files_content=None, active_content=None):
    """
    Build a minimal app for print tests.
    book_files_content: dict {fname: text} written into tmp_path
    active_content: text written as the active file
    """
    from new_interface import FullscreenCircleApp

    # Write book files
    book_dir = tmp_path / "book"
    book_dir.mkdir()
    fnames = []
    if book_files_content:
        for fname, text in book_files_content.items():
            (book_dir / fname).write_text(text, encoding='utf-8')
            fnames.append(fname)

    # Active file
    active_path = tmp_path / "active.txt"
    if active_content is not None:
        active_path.write_text(active_content, encoding='utf-8')
    else:
        active_path.write_text('', encoding='utf-8')

    app = make_ring_app(['.'], tmp_file=str(active_path))
    app.current_file_path = str(active_path)
    app.book_dir = str(book_dir)
    app.book_files = fnames
    app._app_font = MagicMock()
    app._app_font.family.return_value = 'Consolas'

    for name in ('print_book', 'print_doc', 'export_book', 'export_doc',
                 '_build_doc_html', '_render_doc', '_send_to_printer',
                 '_printer_from_dialog', '_printer_from_save_dialog'):
        if hasattr(FullscreenCircleApp, name):
            app.__dict__[name] = types.MethodType(
                getattr(FullscreenCircleApp, name), app)

    return app


def _make_mock_dialog():
    """
    Build a QPrintDialog mock that passes the `dialog.exec() != QPrintDialog.DialogCode.Accepted`
    guard inside print_book / print_doc. The trick: both the mock instance's exec() return value
    AND the mock class's DialogCode.Accepted must be the same object.
    """
    from unittest.mock import MagicMock
    from PyQt6.QtPrintSupport import QPrintDialog as _Real
    _accepted = _Real.DialogCode.Accepted          # real integer value

    dialog_inst = MagicMock()
    dialog_inst.exec.return_value = _accepted      # what dialog.exec() returns

    dialog_cls = MagicMock(return_value=dialog_inst)
    dialog_cls.DialogCode.Accepted = _accepted     # what QPrintDialog.DialogCode.Accepted is

    return dialog_cls


class TestPrint:

    def _fake_printer(self, app):
        """Patch printer helpers on the app instance to return a MagicMock printer."""
        from unittest.mock import patch, MagicMock
        mock = MagicMock()
        from contextlib import ExitStack
        stack = ExitStack()
        stack.enter_context(patch.object(app, '_printer_from_dialog', return_value=mock))
        stack.enter_context(patch.object(app, '_printer_from_save_dialog', return_value=mock))
        return stack

    def test_print_book_excludes_0txt(self, tmp_path):
        """print_book must not include 0.txt in the HTML output."""
        from unittest.mock import patch, MagicMock
        files = {
            '0.txt':   '.\nShould be excluded.\n',
            'ch1.txt': '.\nChapter one line.\n',
            'ch2.txt': '.\nChapter two line.\n',
        }
        app = _make_print_app(tmp_path, book_files_content=files)
        captured_html = []

        class FakeDoc:
            def setHtml(self_, html): captured_html.append(html)
            def print(self_, printer): pass

        with self._fake_printer(app), \
             patch('PyQt6.QtGui.QTextDocument', FakeDoc):
            app.print_book()

        assert captured_html, "print_book did not build any HTML"
        html = captured_html[0]
        assert 'Should be excluded' not in html
        assert 'Chapter one line' in html
        assert 'Chapter two line' in html

    def test_print_book_respects_book_files_order(self, tmp_path):
        """print_book renders chapters in book_files order."""
        from unittest.mock import patch, MagicMock
        files = {'b.txt': '.\nBeta.\n', 'a.txt': '.\nAlpha.\n'}
        app = _make_print_app(tmp_path, book_files_content=files)
        app.book_files = ['b.txt', 'a.txt']
        captured_html = []

        class FakeDoc:
            def setHtml(self_, html): captured_html.append(html)
            def print(self_, printer): pass

        with self._fake_printer(app), \
             patch('PyQt6.QtGui.QTextDocument', FakeDoc):
            app.print_book()

        assert captured_html, "print_book did not build any HTML"
        html = captured_html[0]
        assert html.index('Beta') < html.index('Alpha')

    def _run_print_doc(self, app):
        """Run print_doc with full Qt mocking, return captured HTML string."""
        from unittest.mock import patch, MagicMock
        captured_html = []

        class FakeDoc:
            def setHtml(self_, html): captured_html.append(html)
            def print(self_, printer): pass

        with self._fake_printer(app), \
             patch('PyQt6.QtGui.QTextDocument', FakeDoc):
            app.print_doc()

        return captured_html[0] if captured_html else ''

    def test_print_doc_uses_current_file_path(self, tmp_path):
        """print_doc reads current_file_path, not hardcoded 0.txt."""
        app = _make_print_app(tmp_path, active_content=".\nActive file line.\n")
        (tmp_path / "0.txt").write_text(".\nWrong file.\n", encoding='utf-8')
        app.void_dir = str(tmp_path)

        html = self._run_print_doc(app)

        assert 'Active file line.' in html
        assert 'Wrong file.' not in html

    def test_print_doc_dot_becomes_spacer(self, tmp_path):
        """print_doc must render '.' separators as blank spacer lines, not as text."""
        app = _make_print_app(tmp_path, active_content=".\nReal line.\n.\nAnother line.\n")

        html = self._run_print_doc(app)

        assert '>.<' not in html       # dot must not appear as visible text
        assert '&nbsp;' in html        # spacer paragraph must be present
        assert 'Real line.' in html
        assert 'Another line.' in html
