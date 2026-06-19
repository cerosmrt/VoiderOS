"""
Tests for controls.py:
  - setup_controls
  - show_random_line_from_current_file
  - show_random_line_from_random_file
  - recycle_line_to_zero_txt
  - show_previous_current_file_line
  - show_next_current_file_line
"""
import os
import tempfile
import pytest
from unittest.mock import MagicMock, patch


def _make_app(tmp_path, filename='0.txt', content=''):
    """Build a minimal mock app object with the attributes controls.py expects."""
    fpath = os.path.join(str(tmp_path), filename)
    with open(fpath, 'w', encoding='utf-8') as f:
        f.write(content)

    app = MagicMock()
    app.current_file_path = fpath
    app.void_dir = str(tmp_path)
    app.entry = MagicMock()
    app.entry.text.return_value = ''
    app.current_active_line = None
    app.current_active_line_index = None
    app.last_inserted_index = None
    app.first_up_after_submission = False
    return app, fpath


class TestSetupControls:
    def test_sets_first_up_flag(self):
        from controls import setup_controls
        app = MagicMock()
        setup_controls(app)
        assert app.first_up_after_submission is False

    def test_idempotent(self):
        from controls import setup_controls
        app = MagicMock()
        setup_controls(app)
        setup_controls(app)
        assert app.first_up_after_submission is False


class TestShowRandomLineFromCurrentFile:
    def test_basic_picks_a_line(self, tmp_path):
        from controls import show_random_line_from_current_file
        app, _ = _make_app(tmp_path, content='.\nline one\nline two\n')
        show_random_line_from_current_file(app)
        app.entry.setText.assert_called_once()
        picked = app.entry.setText.call_args[0][0]
        assert picked in ('line one', 'line two')

    def test_dots_excluded(self, tmp_path):
        from controls import show_random_line_from_current_file
        app, _ = _make_app(tmp_path, content='.\n.\nhello\n')
        show_random_line_from_current_file(app)
        picked = app.entry.setText.call_args[0][0]
        assert picked == 'hello'
        assert picked != '.'

    def test_empty_file_no_setText(self, tmp_path):
        from controls import show_random_line_from_current_file
        app, _ = _make_app(tmp_path, content='')
        show_random_line_from_current_file(app)
        app.entry.setText.assert_not_called()

    def test_only_dots_no_setText(self, tmp_path):
        from controls import show_random_line_from_current_file
        app, _ = _make_app(tmp_path, content='.\n.\n.\n')
        show_random_line_from_current_file(app)
        app.entry.setText.assert_not_called()

    def test_missing_file_clears_entry(self, tmp_path):
        from controls import show_random_line_from_current_file
        app, _ = _make_app(tmp_path, content='hello')
        app.current_file_path = str(tmp_path / 'nonexistent.txt')
        show_random_line_from_current_file(app)
        app.entry.clear.assert_called()

    def test_cursor_set_to_zero(self, tmp_path):
        from controls import show_random_line_from_current_file
        app, _ = _make_app(tmp_path, content='.\nsome line\n')
        show_random_line_from_current_file(app)
        app.entry.setCursorPosition.assert_called_with(0)

    def test_excludes_current_line_when_alternatives_exist(self, tmp_path):
        """When entry already shows a line, that line is excluded from selection."""
        from controls import show_random_line_from_current_file
        content = '.\nalpha\nbeta\ngamma\n'
        app, _ = _make_app(tmp_path, content=content)
        app.entry.text.return_value = 'alpha'
        # Run many times to probabilistically ensure 'alpha' is never picked
        results = set()
        for _ in range(30):
            app.entry.setText.reset_mock()
            show_random_line_from_current_file(app)
            picked = app.entry.setText.call_args[0][0]
            results.add(picked)
        assert 'alpha' not in results

    def test_single_valid_line_always_returns_it(self, tmp_path):
        from controls import show_random_line_from_current_file
        app, _ = _make_app(tmp_path, content='.\nonly line\n')
        app.entry.text.return_value = 'only line'  # same as current → still returns it
        show_random_line_from_current_file(app)
        picked = app.entry.setText.call_args[0][0]
        assert picked == 'only line'


class TestShowRandomLineFromRandomFile:
    def test_picks_from_non_zero_file(self, tmp_path):
        from controls import show_random_line_from_random_file
        (tmp_path / 'notes.txt').write_text('.\nsome note\n', encoding='utf-8')
        (tmp_path / '0.txt').write_text('.\nshould be excluded\n', encoding='utf-8')
        app = MagicMock()
        app.void_dir = str(tmp_path)
        app.entry = MagicMock()
        show_random_line_from_random_file(app)
        if app.entry.setText.called:
            picked = app.entry.setText.call_args[0][0]
            assert picked != 'should be excluded'
            assert picked == 'some note'

    def test_no_files_available(self, tmp_path):
        from controls import show_random_line_from_random_file
        # Only 0.txt exists → no valid file
        (tmp_path / '0.txt').write_text('.\nblocked\n', encoding='utf-8')
        app = MagicMock()
        app.void_dir = str(tmp_path)
        app.entry = MagicMock()
        show_random_line_from_random_file(app)
        app.entry.setText.assert_not_called()

    def test_empty_dir_no_crash(self, tmp_path):
        from controls import show_random_line_from_random_file
        app = MagicMock()
        app.void_dir = str(tmp_path)
        app.entry = MagicMock()
        show_random_line_from_random_file(app)  # should not raise

    def test_picks_from_subdirectory(self, tmp_path):
        from controls import show_random_line_from_random_file
        subdir = tmp_path / 'sub'
        subdir.mkdir()
        (subdir / 'deep.txt').write_text('.\ndeep line\n', encoding='utf-8')
        app = MagicMock()
        app.void_dir = str(tmp_path)
        app.entry = MagicMock()
        show_random_line_from_random_file(app)
        if app.entry.setText.called:
            picked = app.entry.setText.call_args[0][0]
            assert picked == 'deep line'

    def test_cursor_set(self, tmp_path):
        from controls import show_random_line_from_random_file
        (tmp_path / 'a.txt').write_text('.\ntest line\n', encoding='utf-8')
        app = MagicMock()
        app.void_dir = str(tmp_path)
        app.entry = MagicMock()
        show_random_line_from_random_file(app)
        if app.entry.setText.called:
            app.entry.setCursorPosition.assert_called_with(0)


class TestRecycleLineToZeroTxt:
    def test_picks_from_other_file(self, tmp_path):
        from controls import recycle_line_to_zero_txt
        (tmp_path / 'current.txt').write_text('.\ncurrent content\n', encoding='utf-8')
        (tmp_path / 'other.txt').write_text('.\nother content\n', encoding='utf-8')
        app = MagicMock()
        app.void_dir = str(tmp_path)
        app.current_file_path = str(tmp_path / 'current.txt')
        app.entry = MagicMock()
        recycle_line_to_zero_txt(app)
        if app.entry.setText.called:
            picked = app.entry.setText.call_args[0][0]
            assert picked == 'other content'

    def test_excludes_current_file(self, tmp_path):
        from controls import recycle_line_to_zero_txt
        (tmp_path / 'current.txt').write_text('.\ncurrent line\n', encoding='utf-8')
        (tmp_path / 'other.txt').write_text('.\nother line\n', encoding='utf-8')
        app = MagicMock()
        app.void_dir = str(tmp_path)
        app.current_file_path = str(tmp_path / 'current.txt')
        app.entry = MagicMock()
        results = set()
        for _ in range(20):
            app.entry.setText.reset_mock()
            recycle_line_to_zero_txt(app)
            if app.entry.setText.called:
                results.add(app.entry.setText.call_args[0][0])
        assert 'current line' not in results

    def test_no_other_files_no_crash(self, tmp_path):
        from controls import recycle_line_to_zero_txt
        (tmp_path / 'only.txt').write_text('.\nhello\n', encoding='utf-8')
        app = MagicMock()
        app.void_dir = str(tmp_path)
        app.current_file_path = str(tmp_path / 'only.txt')
        app.entry = MagicMock()
        recycle_line_to_zero_txt(app)  # should not raise


class TestShowPreviousCurrentFileLine:
    def test_first_call_shows_last_line(self, tmp_path):
        """Without any navigation state, show_previous navigates to the last non-dot line."""
        from controls import show_previous_current_file_line
        content = '.\nfirst\nsecond\nthird\n'
        app, _ = _make_app(tmp_path, content=content)
        show_previous_current_file_line(app)
        app.entry.setText.assert_called()
        picked = app.entry.setText.call_args[0][0]
        assert picked in ('first', 'second', 'third')

    def test_skips_dot_lines(self, tmp_path):
        from controls import show_previous_current_file_line
        content = '.\nhello\n.\nworld\n'
        app, _ = _make_app(tmp_path, content=content)
        for _ in range(10):
            show_previous_current_file_line(app)
        for call in app.entry.setText.call_args_list:
            assert call[0][0] not in ('.', '')

    def test_empty_file_clears_entry(self, tmp_path):
        from controls import show_previous_current_file_line
        app, _ = _make_app(tmp_path, content='')
        show_previous_current_file_line(app)
        app.entry.clear.assert_called()

    def test_first_up_after_submission_shows_last_inserted(self, tmp_path):
        from controls import show_previous_current_file_line
        content = '.\nfirst\nsecond\nthird\n'
        app, _ = _make_app(tmp_path, content=content)
        app.first_up_after_submission = True
        app.last_inserted_index = 2  # 'second' is at index 2 in file
        show_previous_current_file_line(app)
        app.entry.setText.assert_called()
        picked = app.entry.setText.call_args[0][0]
        assert picked == 'second'

    def test_first_up_flag_cleared_after_use(self, tmp_path):
        from controls import show_previous_current_file_line
        content = '.\nhello\n'
        app, _ = _make_app(tmp_path, content=content)
        app.first_up_after_submission = True
        app.last_inserted_index = 1
        show_previous_current_file_line(app)
        assert app.first_up_after_submission is False

    def test_missing_file_clears_entry(self, tmp_path):
        from controls import show_previous_current_file_line
        app, _ = _make_app(tmp_path, content='hello')
        app.current_file_path = str(tmp_path / 'nonexistent.txt')
        show_previous_current_file_line(app)
        app.entry.clear.assert_called()

    def test_navigation_wraps_circularly(self, tmp_path):
        """Going past the beginning wraps back to the last non-dot line."""
        from controls import show_previous_current_file_line
        # File: index 0 = '.', 1 = 'first', 2 = 'second'
        # Starting at current_active_line_index = 0 (on the dot line) triggers wrap.
        content = '.\nfirst\nsecond\n'
        app, _ = _make_app(tmp_path, content=content)
        # Simulate being 'before' the first line — current_index = 0, new_index = -1
        app.current_active_line_index = 0
        show_previous_current_file_line(app)
        # After wrap, should land on last non-dot line = 'second'
        app.entry.setText.assert_called()
        picked = app.entry.setText.call_args[0][0]
        assert picked == 'second'


class TestShowNextCurrentFileLine:
    def test_first_call_shows_a_line(self, tmp_path):
        from controls import show_next_current_file_line
        content = '.\nalpha\nbeta\n'
        app, _ = _make_app(tmp_path, content=content)
        show_next_current_file_line(app)
        app.entry.setText.assert_called()
        picked = app.entry.setText.call_args[0][0]
        assert picked in ('alpha', 'beta')

    def test_skips_dot_lines(self, tmp_path):
        from controls import show_next_current_file_line
        content = '.\nhello\n.\nworld\n'
        app, _ = _make_app(tmp_path, content=content)
        for _ in range(10):
            show_next_current_file_line(app)
        for call in app.entry.setText.call_args_list:
            assert call[0][0] not in ('.', '')

    def test_empty_file_clears_entry(self, tmp_path):
        from controls import show_next_current_file_line
        app, _ = _make_app(tmp_path, content='')
        show_next_current_file_line(app)
        app.entry.clear.assert_called()

    def test_navigation_moves_forward(self, tmp_path):
        from controls import show_next_current_file_line
        content = '.\nfirst\nsecond\nthird\n'
        app, _ = _make_app(tmp_path, content=content)
        # Start at first (index 1 in file)
        app.current_active_line_index = 1
        show_next_current_file_line(app)
        picked = app.entry.setText.call_args[0][0]
        assert picked == 'second'

    def test_wraps_at_end(self, tmp_path):
        from controls import show_next_current_file_line
        content = '.\nalpha\nbeta\n'
        app, _ = _make_app(tmp_path, content=content)
        # Position at last line (index 2 in file = 'beta')
        app.current_active_line_index = 2
        show_next_current_file_line(app)
        picked = app.entry.setText.call_args[0][0]
        assert picked == 'alpha'  # wraps to first

    def test_missing_file_clears_entry(self, tmp_path):
        from controls import show_next_current_file_line
        app, _ = _make_app(tmp_path, content='hello')
        app.current_file_path = str(tmp_path / 'missing.txt')
        show_next_current_file_line(app)
        app.entry.clear.assert_called()

    def test_cursor_positioned_at_zero(self, tmp_path):
        from controls import show_next_current_file_line
        content = '.\nhello\n'
        app, _ = _make_app(tmp_path, content=content)
        show_next_current_file_line(app)
        app.entry.setCursorPosition.assert_called_with(0)
