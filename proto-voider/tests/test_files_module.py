"""
Tests for files.py functions:
  - setup_file_handling
  - void_line (normal text, empty, dot, //, /move, block move)
Edge cases: empty files, missing files, consecutive dots, unicode, etc.
"""
import os
import tempfile
import pytest
from unittest.mock import MagicMock, patch


def _make_files_app(tmp_path, active_fname='0.txt', content=''):
    """Build a minimal mock app for files.py functions."""
    active_path = os.path.join(str(tmp_path), active_fname)
    void_file = os.path.join(str(tmp_path), '0.txt')
    with open(active_path, 'w', encoding='utf-8') as f:
        f.write(content)
    if active_path != void_file:
        with open(void_file, 'w', encoding='utf-8') as f:
            f.write('')

    app = MagicMock()
    app.void_dir = str(tmp_path)
    app.current_file_path = active_path
    app.void_file_path = void_file
    app.entry = MagicMock()
    app.entry.text.return_value = ''
    app.entry.clear = MagicMock()
    app.entry.setFocus = MagicMock()
    app.current_active_line = None
    app.current_active_line_index = None
    app.last_inserted_index = None
    app.first_up_after_submission = False
    app.txt_files = [active_path] if active_path not in [void_file] else [void_file]
    if void_file not in app.txt_files:
        app.txt_files.append(void_file)
    app.txt_files.sort()
    app.current_file_index = app.txt_files.index(active_path)
    return app


class TestSetupFileHandling:
    def test_creates_void_dir_if_missing(self, tmp_path):
        from files import setup_file_handling
        new_dir = str(tmp_path / 'newdir')
        active = os.path.join(new_dir, 'active.txt')
        void_f = os.path.join(new_dir, '0.txt')
        app = MagicMock()
        app.void_dir = new_dir
        app.current_file_path = active
        app.void_file_path = void_f
        setup_file_handling(app)
        assert os.path.isdir(new_dir)

    def test_creates_active_file_if_missing(self, tmp_path):
        from files import setup_file_handling
        active = str(tmp_path / 'missing_active.txt')
        void_f = str(tmp_path / '0.txt')
        app = MagicMock()
        app.void_dir = str(tmp_path)
        app.current_file_path = active
        app.void_file_path = void_f
        setup_file_handling(app)
        assert os.path.exists(active)

    def test_creates_void_file_if_missing(self, tmp_path):
        from files import setup_file_handling
        active = str(tmp_path / 'active.txt')
        void_f = str(tmp_path / '0.txt')
        open(active, 'w').close()
        app = MagicMock()
        app.void_dir = str(tmp_path)
        app.current_file_path = active
        app.void_file_path = void_f
        setup_file_handling(app)
        assert os.path.exists(void_f)

    def test_sets_navigation_state_to_none(self, tmp_path):
        from files import setup_file_handling
        active = str(tmp_path / 'active.txt')
        void_f = str(tmp_path / '0.txt')
        open(active, 'w').close()
        open(void_f, 'w').close()
        app = MagicMock()
        app.void_dir = str(tmp_path)
        app.current_file_path = active
        app.void_file_path = void_f
        setup_file_handling(app)
        assert app.current_active_line is None
        assert app.current_active_line_index is None
        assert app.last_inserted_index is None


class TestVoidLineNormalText:
    def test_appends_line_to_file(self, tmp_path):
        from files import void_line
        app = _make_files_app(tmp_path, content='.\n')
        app.entry.text.return_value = 'new line'
        void_line(app)
        content = open(app.current_file_path, encoding='utf-8').read()
        assert 'new line' in content

    def test_empty_input_no_write(self, tmp_path):
        from files import void_line
        app = _make_files_app(tmp_path, content='.\nexisting\n')
        app.entry.text.return_value = ''
        void_line(app)
        content = open(app.current_file_path, encoding='utf-8').read()
        # File should not change
        assert content == '.\nexisting\n'

    def test_empty_input_sets_last_inserted_index(self, tmp_path):
        from files import void_line
        app = _make_files_app(tmp_path, content='.\nline1\nline2\n')
        app.entry.text.return_value = ''
        void_line(app)
        # last_inserted_index should be set to end of file
        assert app.last_inserted_index is not None

    def test_writes_unicode_line(self, tmp_path):
        from files import void_line
        app = _make_files_app(tmp_path)
        app.entry.text.return_value = '日本語テスト'
        void_line(app)
        content = open(app.current_file_path, encoding='utf-8').read()
        assert '日本語テスト' in content

    def test_entry_cleared_after_void(self, tmp_path):
        from files import void_line
        app = _make_files_app(tmp_path)
        app.entry.text.return_value = 'hello'
        void_line(app)
        app.entry.clear.assert_called()

    def test_first_up_flag_set_after_void(self, tmp_path):
        from files import void_line
        app = _make_files_app(tmp_path)
        app.entry.text.return_value = 'hello'
        void_line(app)
        assert app.first_up_after_submission is True


class TestVoidLineDot:
    def test_single_dot_appended_to_empty_file(self, tmp_path):
        from files import void_line
        app = _make_files_app(tmp_path, content='')
        app.entry.text.return_value = '.'
        void_line(app)
        content = open(app.current_file_path, encoding='utf-8').read()
        assert '.' in content

    def test_consecutive_dots_blocked(self, tmp_path):
        from files import void_line
        app = _make_files_app(tmp_path, content='.\n')
        app.entry.text.return_value = '.'
        void_line(app)
        content = open(app.current_file_path, encoding='utf-8').read()
        # Should still have only one dot (no double dot added)
        assert content.count('.\n') == 1


class TestVoidLineFileSwitch:
    def test_double_slash_switches_to_0txt(self, tmp_path):
        from files import void_line
        app = _make_files_app(tmp_path, active_fname='notes.txt')
        app.entry.text.return_value = '//'
        original_path = app.current_file_path
        void_line(app)
        # Should have switched to 0.txt
        assert app.current_file_path == app.void_file_path

    def test_double_slash_with_name_switches_file(self, tmp_path):
        from files import void_line
        app = _make_files_app(tmp_path)
        app.entry.text.return_value = '//newfile'
        void_line(app)
        assert app.current_file_path.endswith('newfile.txt')

    def test_double_slash_creates_file_if_not_exists(self, tmp_path):
        from files import void_line
        app = _make_files_app(tmp_path)
        app.entry.text.return_value = '//brandnew'
        void_line(app)
        assert os.path.exists(app.current_file_path)

    def test_already_in_file_stays_same(self, tmp_path):
        from files import void_line
        app = _make_files_app(tmp_path, active_fname='0.txt')
        # Normalize so comparison works
        app.entry.text.return_value = '//0'
        original_path = app.current_file_path
        void_line(app)
        assert os.path.normpath(app.current_file_path) == os.path.normpath(original_path)

    def test_double_slash_adds_txt_extension(self, tmp_path):
        from files import void_line
        app = _make_files_app(tmp_path)
        app.entry.text.return_value = '//myfile'
        void_line(app)
        assert app.current_file_path.lower().endswith('.txt')


class TestVoidLineSingleLineMoveCommand:
    def test_move_line_to_target_file(self, tmp_path):
        from files import void_line
        target = str(tmp_path / 'target.txt')
        open(target, 'w').close()
        app = _make_files_app(tmp_path)
        app.entry.text.return_value = 'my content /target'
        void_line(app)
        target_content = open(target, encoding='utf-8').read()
        assert 'my content' in target_content

    def test_move_line_creates_target_if_missing(self, tmp_path):
        from files import void_line
        app = _make_files_app(tmp_path)
        app.entry.text.return_value = 'hello /newtarget'
        void_line(app)
        assert os.path.exists(str(tmp_path / 'newtarget.txt'))


class TestVoidLineEditExisting:
    def test_edit_existing_line(self, tmp_path):
        from files import void_line
        app = _make_files_app(tmp_path, content='.\nold text\n')
        app.current_active_line_index = 1  # edit 'old text'
        app.entry.text.return_value = 'new text'
        void_line(app)
        lines = open(app.current_file_path, encoding='utf-8').readlines()
        assert any('new text' in l for l in lines)

    def test_out_of_range_index_appends(self, tmp_path):
        from files import void_line
        app = _make_files_app(tmp_path, content='.\nhello\n')
        app.current_active_line_index = 999  # out of range
        app.entry.text.return_value = 'appended'
        void_line(app)
        content = open(app.current_file_path, encoding='utf-8').read()
        assert 'appended' in content


class TestVoidLineEdgeCases:
    def test_very_long_line(self, tmp_path):
        from files import void_line
        app = _make_files_app(tmp_path)
        long_line = 'x' * 5000
        app.entry.text.return_value = long_line
        void_line(app)
        content = open(app.current_file_path, encoding='utf-8').read()
        assert long_line in content

    def test_whitespace_only_treated_as_empty(self, tmp_path):
        from files import void_line
        app = _make_files_app(tmp_path, content='.\nexisting\n')
        app.entry.text.return_value = '   '  # strip() → ''
        void_line(app)
        # File should not have gained a whitespace-only line
        lines = [l.strip() for l in open(app.current_file_path, encoding='utf-8')]
        assert '   ' not in lines

    def test_line_with_spaces_preserved(self, tmp_path):
        from files import void_line
        app = _make_files_app(tmp_path)
        app.entry.text.return_value = 'hello world'
        void_line(app)
        content = open(app.current_file_path, encoding='utf-8').read()
        assert 'hello world' in content
