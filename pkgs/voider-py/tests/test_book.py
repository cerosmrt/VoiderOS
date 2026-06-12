import json
import types
import pytest
from unittest.mock import MagicMock
from helpers import make_ring_app, has, _mock_circular_view
from line_ring import LineRing


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
        app.book_ring = LineRing(['.', 'a', '.', 'b'])
        app.book_view = _mock_circular_view()
        app.book_ring.index = 1
        app._book_navigate(-1)
        assert app.book_ring.index == 3

        app.book_ring.index = 3
        app._book_navigate(1)
        assert app.book_ring.index == 1

    def test_book_swap_up(self, tmp_path):
        app = self._book_app(tmp_path)
        if not has(app, '_book_swap_up'):
            pytest.skip("book browser not present in this commit")
        app.book_files = ['a.txt', 'b.txt', 'c.txt']
        app.book_ring = LineRing(['.', 'a', '.', 'b', '.', 'c'])
        app.book_view = _mock_circular_view()
        app.book_ring.index = 3
        app._book_swap_up()
        assert app.book_files == ['b.txt', 'a.txt', 'c.txt']
        assert app.book_ring.index == 1

    def test_book_swap_up_at_first_noop(self, tmp_path):
        app = self._book_app(tmp_path)
        if not has(app, '_book_swap_up'):
            pytest.skip("book browser not present in this commit")
        app.book_files = ['a.txt', 'b.txt']
        app.book_ring = LineRing(['.', 'a', '.', 'b'])
        app.book_view = _mock_circular_view()
        app.book_ring.index = 1
        app._book_swap_up()
        assert app.book_files == ['a.txt', 'b.txt']

    def test_book_swap_down(self, tmp_path):
        app = self._book_app(tmp_path)
        if not has(app, '_book_swap_down'):
            pytest.skip("book browser not present in this commit")
        app.book_files = ['a.txt', 'b.txt', 'c.txt']
        app.book_ring = LineRing(['.', 'a', '.', 'b', '.', 'c'])
        app.book_view = _mock_circular_view()
        app.book_ring.index = 3
        app._book_swap_down()
        assert app.book_files == ['a.txt', 'c.txt', 'b.txt']
        assert app.book_ring.index == 5

    def test_book_rebase(self, tmp_path):
        app = self._book_app(tmp_path)
        if not has(app, '_book_rebase'):
            pytest.skip("book browser not present in this commit")
        app.book_files = ['a.txt', 'b.txt', 'c.txt']
        app.book_ring = LineRing(['.', 'a', '.', 'b', '.', 'c'])
        app.book_view = _mock_circular_view()
        app.book_ring.index = 5
        app._book_rebase()
        assert app.book_files == ['c.txt', 'a.txt', 'b.txt']
        assert app.book_ring.index == 1

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
        app.book_ring.index = 1

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
        app.book_ring.index = 3
        app.book_view = _mock_circular_view()
        app.current_view = 2

        app.stack = MagicMock()
        app.entry = MagicMock()
        app._doc_show_editor = MagicMock()
        app._save_last_line = MagicMock()

        activate_calls = []
        app._set_active_file = lambda path: activate_calls.append(path)

        for name in ('switch_to_view', '_book_file_idx', '_book_try_rename',
                     '_rebuild_book_ring', '_load_book_order'):
            if hasattr(FullscreenCircleApp, name) and not hasattr(app, name):
                setattr(app, name, types.MethodType(
                    getattr(FullscreenCircleApp, name), app))
        for name in ('switch_to_view', '_book_file_idx', '_book_try_rename'):
            if hasattr(FullscreenCircleApp, name):
                setattr(app, name, types.MethodType(
                    getattr(FullscreenCircleApp, name), app))

        app.switch_to_view(1)

        assert len(activate_calls) == 1
        assert activate_calls[0].endswith('b.txt')
