"""Tests for F5 paragraph triage view."""
import os
import types
import pytest
from unittest.mock import MagicMock

from line_ring import LineRing
from helpers import make_ring_app, _mock_circular_view


TRIAGE_METHODS = (
    '_paragraphs_from_ring', '_rebuild_ring_from_paragraphs', '_dot_line_index',
    '_triage_enter', '_triage_refresh',
    '_triage_next_para', '_triage_prev_para',
    '_triage_next_book', '_triage_prev_book',
    '_triage_dispatch', '_triage_swap_up', '_triage_swap_down',
    '_library_current_fname', '_save_library',
)


def _triage_app(lines, book_ring_lines=None, tmp_path=None):
    from new_interface import FullscreenCircleApp
    import tempfile

    app = make_ring_app(list(lines))
    app.line_ring = LineRing(list(lines))

    # Triage state
    app._triage_paragraphs = []
    app._triage_para_idx = 0
    app.triage_view = MagicMock()

    # Book ring (right panel)
    app.book_ring = LineRing(book_ring_lines or ['.', 'chapter-a', '.', 'chapter-b'])
    app.book_ring.index = 1  # on 'chapter-a'
    # _library_lines stores filenames (with .txt); book_ring stores display names
    app._library_lines = ['.', 'chapter-a.txt', '.', 'chapter-b.txt']
    app._book_pending_new = False

    if tmp_path:
        app.void_dir = str(tmp_path)
        app.f1_file = str(tmp_path / 'I' / '0.txt')
        (tmp_path / 'I').mkdir(exist_ok=True)
        open(app.f1_file, 'w').close()

    app._library_path_cache = {}

    for name in TRIAGE_METHODS:
        if hasattr(FullscreenCircleApp, name):
            setattr(app, name, types.MethodType(getattr(FullscreenCircleApp, name), app))

    app.auto_save_circular = MagicMock()
    app._save_library = MagicMock()

    return app


class TestTriageLoad:

    def test_load_extracts_paragraphs(self):
        app = _triage_app(['.', 'line1', 'line2', '.', 'line3'])
        app._triage_enter()
        assert len(app._triage_paragraphs) == 2
        assert app._triage_paragraphs[0] == ['line1', 'line2']
        assert app._triage_paragraphs[1] == ['line3']

    def test_load_sets_index_zero(self):
        app = _triage_app(['.', 'a', '.', 'b'])
        app._triage_enter()
        assert app._triage_para_idx == 0

    def test_load_single_paragraph(self):
        app = _triage_app(['.', 'only line'])
        app._triage_enter()
        assert app._triage_paragraphs == [['only line']]

    def test_load_skips_empty_paragraphs(self):
        """Paragraphs with no lines (consecutive dots) are ignored."""
        app = _triage_app(['.', '.', 'real line'])
        app._triage_enter()
        assert app._triage_paragraphs == [['real line']]


class TestTriageNavigation:

    def test_next_para_advances_index(self):
        app = _triage_app(['.', 'a', '.', 'b', '.', 'c'])
        app._triage_enter()
        app._triage_next_para()
        assert app._triage_para_idx == 1

    def test_prev_para_at_first_goes_to_zo(self):
        app = _triage_app(['.', 'a', '.', 'b'])
        app._triage_enter()
        app._triage_para_idx = 0
        app._triage_prev_para()
        assert app._triage_para_idx == -1  # lands on ø

    def test_zo_prev_goes_to_last(self):
        app = _triage_app(['.', 'a', '.', 'b'])
        app._triage_enter()
        app._triage_para_idx = -1
        app._triage_prev_para()
        assert app._triage_para_idx == 1  # last paragraph

    def test_next_para_at_last_goes_to_zo(self):
        app = _triage_app(['.', 'a', '.', 'b'])
        app._triage_enter()
        app._triage_para_idx = 1
        app._triage_next_para()
        assert app._triage_para_idx == -1  # lands on ø

    def test_zo_next_goes_to_first(self):
        app = _triage_app(['.', 'a', '.', 'b'])
        app._triage_enter()
        app._triage_para_idx = -1
        app._triage_next_para()
        assert app._triage_para_idx == 0  # first paragraph

    def test_next_book_advances_ring(self):
        app = _triage_app(['.', 'x'])
        app._triage_enter()
        before = app.book_ring.index
        app._triage_next_book()
        assert app.book_ring.index != before or len(app.book_ring.lines) == 1

    def test_prev_book_retreats_ring(self):
        app = _triage_app(['.', 'x'])
        app._triage_enter()
        app.book_ring.index = 1  # on chapter-a
        app._triage_prev_book()
        # Should have moved backwards (wrapping)
        assert app.book_ring.index != 1 or len(app.book_ring.lines) == 1


class TestTriageDispatch:

    def test_dispatch_appends_to_book_file(self, tmp_path):
        book_file = tmp_path / 'chapter-a.txt'
        book_file.write_text('existing line\n', encoding='utf-8')

        app = _triage_app(['.', 'para line 1', 'para line 2', '.', 'other'],
                          tmp_path=tmp_path)
        app._library_path_cache = {'chapter-a.txt': str(book_file)}
        app.book_ring.index = 1  # on 'chapter-a'
        app._triage_enter()
        app._triage_para_idx = 0
        app._triage_dispatch()

        content = book_file.read_text(encoding='utf-8')
        assert 'para line 1' in content
        assert 'para line 2' in content

    def test_dispatch_removes_para_from_triage(self, tmp_path):
        book_file = tmp_path / 'chapter-a.txt'
        book_file.write_text('', encoding='utf-8')

        app = _triage_app(['.', 'gone', '.', 'stays'],
                          tmp_path=tmp_path)
        app._library_path_cache = {'chapter-a.txt': str(book_file)}
        app.book_ring.index = 1
        app._triage_enter()
        app._triage_para_idx = 0
        app._triage_dispatch()

        assert ['gone'] not in app._triage_paragraphs
        assert ['stays'] in app._triage_paragraphs

    def test_dispatch_saves_source_file(self, tmp_path):
        book_file = tmp_path / 'chapter-a.txt'
        book_file.write_text('', encoding='utf-8')

        app = _triage_app(['.', 'gone', '.', 'stays'],
                          tmp_path=tmp_path)
        app._library_path_cache = {'chapter-a.txt': str(book_file)}
        app.book_ring.index = 1
        app._triage_enter()
        app._triage_dispatch()

        app.auto_save_circular.assert_called()

    def test_dispatch_skips_dot_entries(self, tmp_path):
        """Dispatching when book ring is on a '.' separator does nothing."""
        app = _triage_app(['.', 'para'],
                          book_ring_lines=['.', 'chapter-a'],
                          tmp_path=tmp_path)
        app.book_ring.index = 0  # on the dot separator
        app._triage_enter()
        before = list(app._triage_paragraphs)
        app._triage_dispatch()
        assert app._triage_paragraphs == before


class TestTriageReorder:

    def test_swap_up_exchanges_paragraphs(self):
        app = _triage_app(['.', 'first', '.', 'second', '.', 'third'])
        app._triage_enter()
        app._triage_para_idx = 1  # on 'second'
        app._triage_swap_up()
        assert app._triage_paragraphs[0] == ['second']
        assert app._triage_paragraphs[1] == ['first']
        assert app._triage_para_idx == 0

    def test_swap_down_exchanges_paragraphs(self):
        app = _triage_app(['.', 'first', '.', 'second', '.', 'third'])
        app._triage_enter()
        app._triage_para_idx = 0  # on 'first'
        app._triage_swap_down()
        assert app._triage_paragraphs[0] == ['second']
        assert app._triage_paragraphs[1] == ['first']
        assert app._triage_para_idx == 1

    def test_swap_up_noop_at_first(self):
        app = _triage_app(['.', 'only', '.', 'two'])
        app._triage_enter()
        app._triage_para_idx = 0
        before = list(app._triage_paragraphs)
        app._triage_swap_up()
        assert app._triage_paragraphs == before

    def test_swap_down_noop_at_last(self):
        app = _triage_app(['.', 'only', '.', 'two'])
        app._triage_enter()
        app._triage_para_idx = 1
        before = list(app._triage_paragraphs)
        app._triage_swap_down()
        assert app._triage_paragraphs == before
