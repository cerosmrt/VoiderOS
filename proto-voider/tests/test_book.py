import json
import types
import pytest
from unittest.mock import MagicMock, patch
from helpers import make_ring_app, has, _mock_circular_view
from line_ring import LineRing


def _book_app_with_library(tmp_path, fnames=None):
    """Create a book app with _library_lines and book_ring both populated."""
    app = make_ring_app(['.'])
    app.book_dir = str(tmp_path)
    app.void_dir = str(tmp_path)
    if fnames is None:
        fnames = []
    # Build parallel ring and library lines: ['.', 'a', '.', 'b', ...]
    ring_lines = []
    lib_lines = []
    for fname in fnames:
        ring_lines.append('.')
        lib_lines.append('.')
        stem = fname.rsplit('.', 1)[0]
        ring_lines.append(stem)
        lib_lines.append(fname)
    if not ring_lines:
        ring_lines = ['.']
        lib_lines = ['.']
    app.book_ring = LineRing(ring_lines)
    app._library_lines = lib_lines
    app._library_path_cache = {
        fname: str(tmp_path / fname) for fname in fnames
    }
    app.book_view = _mock_circular_view()
    app._save_library = MagicMock()
    return app


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

    def test_book_swap_up(self, tmp_path):
        app = _book_app_with_library(tmp_path, ['a.txt', 'b.txt', 'c.txt'])
        if not has(app, '_book_swap_up'):
            pytest.skip("book browser not present in this commit")
        # ring = ['.', 'a', '.', 'b', '.', 'c'] — index 3 = 'b'.
        # New behaviour: a chapter swaps with its IMMEDIATE neighbour, so 'b'
        # crosses the separator into the book above (joins 'a'). No skip-the-dot
        # interchange with another chapter.
        app.book_ring.index = 3
        app._book_swap_up()
        assert app.book_ring.lines == ['.', 'a', 'b', '.', '.', 'c']
        assert app.book_ring.index == 2

    def test_book_swap_up_at_first_noop(self, tmp_path):
        app = _book_app_with_library(tmp_path, ['a.txt', 'b.txt'])
        if not has(app, '_book_swap_up'):
            pytest.skip("book browser not present in this commit")
        # ring = ['.', 'a', '.', 'b'] — 'a' is in the first book, nothing above
        app.book_ring.index = 1
        app._book_swap_up()
        assert app.book_ring.lines == ['.', 'a', '.', 'b']   # no-op

    def test_book_swap_down(self, tmp_path):
        app = _book_app_with_library(tmp_path, ['a.txt', 'b.txt', 'c.txt'])
        if not has(app, '_book_swap_down'):
            pytest.skip("book browser not present in this commit")
        # ring = ['.', 'a', '.', 'b', '.', 'c'] — index 3 = 'b' crosses down
        app.book_ring.index = 3
        app._book_swap_down()
        assert app.book_ring.lines == ['.', 'a', '.', '.', 'b', 'c']
        assert app.book_ring.index == 4

    def test_book_rebase(self, tmp_path):
        app = _book_app_with_library(tmp_path, ['a.txt', 'b.txt', 'c.txt'])
        if not has(app, '_book_rebase'):
            pytest.skip("book browser not present in this commit")
        # ring = ['.', 'a', '.', 'b', '.', 'c'] — index 5 = 'c'
        app.book_ring.index = 5
        app._book_rebase()
        # After rebase from index 5, ring rotates so 'c' is first non-dot
        assert app.book_ring.lines[0] in ('.', 'c')
        # The first non-dot element should be 'c'
        first_non_dot = next(l for l in app.book_ring.lines if l != '.')
        assert first_non_dot == 'c'

    def test_book_navigate_does_not_activate_file(self, tmp_path):
        """_book_navigate must NOT call _set_active_file — activation only on Enter/F2."""
        app = _book_app_with_library(tmp_path, ['a.txt', 'b.txt'])
        if not has(app, '_book_navigate'):
            pytest.skip("book browser not present in this commit")
        # ring = ['.', 'a', '.', 'b'] — index 1 = 'a'
        app.book_ring.index = 1

        activate_calls = []
        app._set_active_file = lambda path: activate_calls.append(path)

        app._book_navigate(1)
        app._book_navigate(-1)
        assert activate_calls == [], "_book_navigate must not activate the file"

    def test_book_navigate_moves_index(self, tmp_path):
        """_book_navigate moves the ring index by one step."""
        app = _book_app_with_library(tmp_path, ['a.txt', 'b.txt'])
        if not has(app, '_book_navigate'):
            pytest.skip("book browser not present in this commit")
        app.book_ring.index = 1  # on 'a'
        old_idx = app.book_ring.index
        app._book_navigate(1)
        # Index must change (moving forward at least one step)
        assert app.book_ring.index != old_idx

    def test_switch_to_f2_from_f3_activates_file(self, tmp_path):
        """switch_to_view(1) from F3 (current_view=2) must activate the highlighted file."""
        from new_interface import FullscreenCircleApp

        (tmp_path / "a.txt").write_text(".\nhello\n", encoding='utf-8')
        (tmp_path / "b.txt").write_text(".\nworld\n", encoding='utf-8')
        app = _book_app_with_library(tmp_path, ['a.txt', 'b.txt'])

        if not hasattr(FullscreenCircleApp, 'switch_to_view'):
            pytest.skip("switch_to_view not present in this commit")

        # index 3 = 'b'
        app.book_ring.index = 3
        app.current_view = 2
        app.f2_file = str(tmp_path / "a.txt")
        app.current_file_path = str(tmp_path / "a.txt")
        app.f1_file = str(tmp_path / "a.txt")

        app.stack = MagicMock()
        app.entry = MagicMock()
        app.circular_view = _mock_circular_view()
        app.line_ring = LineRing(['.'])
        app._doc_show_editor = MagicMock()
        app._save_last_line = MagicMock()
        app._restore_last_line = MagicMock()
        app._f2_search_active = False
        app._f3_search_active = False
        app._book_pending_new = False
        app._tts_on_view = MagicMock()
        app._f2_peek_0 = False

        activate_calls = []
        app._set_active_file = lambda path: activate_calls.append(path)

        set_f2_calls = []
        def _fake_set_f2(path):
            set_f2_calls.append(path)
            app.current_file_path = path
            app.f2_file = path
        app._set_f2_file = _fake_set_f2

        app.load_doc_lines = MagicMock()

        for name in ('switch_to_view',):
            if hasattr(FullscreenCircleApp, name):
                setattr(app, name, types.MethodType(
                    getattr(FullscreenCircleApp, name), app))

        app.switch_to_view(1)

        # Either _set_active_file or _set_f2_file was called with b.txt
        all_calls = activate_calls + set_f2_calls
        assert any('b.txt' in p for p in all_calls), \
            f"Expected b.txt activation, got: {all_calls}"
