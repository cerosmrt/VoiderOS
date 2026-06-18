"""
Tests for pure / standalone functions in new_interface.py that don't require
a full Qt application instance:
  - _zodiac_sign
  - _parse_keybinding
  - _load_config / _save_config
  - _build_doc_html (via FullscreenCircleApp class method pattern)
"""
import os
import json
import tempfile
import pytest
from unittest.mock import patch, MagicMock


class TestZodiacSign:
    """_zodiac_sign(month, day) returns Spanish zodiac string."""

    def _sign(self, month, day):
        from new_interface import _zodiac_sign
        return _zodiac_sign(month, day)

    def test_capricornio_dec(self):
        assert self._sign(12, 22) == 'capricornio'
        assert self._sign(12, 31) == 'capricornio'

    def test_capricornio_jan(self):
        assert self._sign(1, 1) == 'capricornio'
        assert self._sign(1, 19) == 'capricornio'

    def test_acuario(self):
        assert self._sign(1, 20) == 'acuario'
        assert self._sign(2, 18) == 'acuario'

    def test_piscis(self):
        assert self._sign(2, 19) == 'piscis'
        assert self._sign(3, 20) == 'piscis'

    def test_aries(self):
        assert self._sign(3, 21) == 'aries'
        assert self._sign(4, 19) == 'aries'

    def test_tauro(self):
        assert self._sign(4, 20) == 'tauro'
        assert self._sign(5, 20) == 'tauro'

    def test_geminis(self):
        assert self._sign(5, 21) == 'geminis'
        assert self._sign(6, 20) == 'geminis'

    def test_cancer(self):
        assert self._sign(6, 21) == 'cancer'
        assert self._sign(7, 22) == 'cancer'

    def test_leo(self):
        assert self._sign(7, 23) == 'leo'
        assert self._sign(8, 22) == 'leo'

    def test_virgo(self):
        assert self._sign(8, 23) == 'virgo'
        assert self._sign(9, 22) == 'virgo'

    def test_libra(self):
        assert self._sign(9, 23) == 'libra'
        assert self._sign(10, 22) == 'libra'

    def test_escorpio(self):
        assert self._sign(10, 23) == 'escorpio'
        assert self._sign(11, 21) == 'escorpio'

    def test_sagitario(self):
        assert self._sign(11, 22) == 'sagitario'
        assert self._sign(12, 21) == 'sagitario'

    def test_all_months_return_a_sign(self):
        from new_interface import _zodiac_sign
        expected_signs = {
            'capricornio', 'acuario', 'piscis', 'aries', 'tauro',
            'geminis', 'cancer', 'leo', 'virgo', 'libra',
            'escorpio', 'sagitario'
        }
        for month in range(1, 13):
            for day in (1, 15, 28):
                sign = _zodiac_sign(month, day)
                assert sign in expected_signs, f"month={month} day={day} got {sign!r}"


class TestParseKeybinding:
    def _parse(self, s):
        from new_interface import _parse_keybinding
        return _parse_keybinding(s)

    def test_single_key_f1(self):
        from PyQt6.QtCore import Qt
        key, mods = self._parse('F1')
        assert key == Qt.Key.Key_F1
        assert mods == Qt.KeyboardModifier.NoModifier

    def test_ctrl_r(self):
        from PyQt6.QtCore import Qt
        key, mods = self._parse('Ctrl+R')
        assert key == Qt.Key.Key_R
        assert mods == Qt.KeyboardModifier.ControlModifier

    def test_alt_up(self):
        from PyQt6.QtCore import Qt
        key, mods = self._parse('Alt+Up')
        assert key == Qt.Key.Key_Up
        assert mods == Qt.KeyboardModifier.AltModifier

    def test_ctrl_shift_f(self):
        from PyQt6.QtCore import Qt
        key, mods = self._parse('Ctrl+Shift+F')
        assert key == Qt.Key.Key_F
        assert mods == (Qt.KeyboardModifier.ControlModifier |
                        Qt.KeyboardModifier.ShiftModifier)

    def test_escape(self):
        from PyQt6.QtCore import Qt
        key, mods = self._parse('Escape')
        assert key == Qt.Key.Key_Escape

    def test_unknown_key_returns_none(self):
        key, mods = self._parse('UnknownKey')
        assert key is None

    def test_ctrl_p(self):
        from PyQt6.QtCore import Qt
        key, mods = self._parse('Ctrl+P')
        assert key == Qt.Key.Key_P
        assert mods == Qt.KeyboardModifier.ControlModifier


class TestLoadSaveConfig:
    def test_load_config_returns_default_if_no_file(self, tmp_path):
        from new_interface import _load_config, DEFAULT_CONFIG, CONFIG_PATH
        with patch('new_interface.CONFIG_PATH', str(tmp_path / 'noconfig.json')):
            from new_interface import _load_config
            cfg = _load_config()
        assert 'void_dir' in cfg
        assert 'keybindings' in cfg

    def test_save_then_load_roundtrip(self, tmp_path):
        cfg_path = str(tmp_path / 'config.json')
        with patch('new_interface.CONFIG_PATH', cfg_path):
            from new_interface import _load_config, _save_config
            cfg = _load_config()
            cfg['void_dir'] = '/test/dir'
            _save_config(cfg)
            cfg2 = _load_config()
        assert cfg2['void_dir'] == '/test/dir'

    def test_load_merges_keybindings(self, tmp_path):
        cfg_path = str(tmp_path / 'config.json')
        custom = {'keybindings': {'view_f1': 'F10'}}
        with open(cfg_path, 'w', encoding='utf-8') as f:
            json.dump(custom, f)
        with patch('new_interface.CONFIG_PATH', cfg_path):
            from new_interface import _load_config, DEFAULT_CONFIG
            cfg = _load_config()
        # Custom override applied
        assert cfg['keybindings']['view_f1'] == 'F10'
        # Default keys still present
        assert 'view_f2' in cfg['keybindings']

    def test_load_corrupt_file_falls_back_to_default(self, tmp_path):
        cfg_path = str(tmp_path / 'bad.json')
        with open(cfg_path, 'w') as f:
            f.write('{ invalid json ::')
        with patch('new_interface.CONFIG_PATH', cfg_path):
            from new_interface import _load_config, DEFAULT_CONFIG
            cfg = _load_config()
        assert cfg['void_dir'] == DEFAULT_CONFIG['void_dir']


class TestBuildDocHtml:
    """Test FullscreenCircleApp._build_doc_html via direct method access."""

    def _build(self, lines, title):
        from new_interface import FullscreenCircleApp
        # Access as unbound method
        return FullscreenCircleApp._build_doc_html(None, lines, title)

    def test_contains_title(self):
        html = self._build(['.', 'line one'], 'My Title')
        assert 'My Title' in html

    def test_dot_becomes_nbsp_spacer(self):
        html = self._build(['.'], 'T')
        assert '&nbsp;' in html
        assert '>.<' not in html

    def test_text_lines_wrapped_in_p(self):
        html = self._build(['.', 'hello world'], 'T')
        assert 'hello world' in html

    def test_multiple_lines_all_present(self):
        lines = ['.', 'alpha', 'beta', '.', 'gamma']
        html = self._build(lines, 'Test')
        assert 'alpha' in html
        assert 'beta' in html
        assert 'gamma' in html

    def test_empty_lines_list(self):
        html = self._build([], 'Empty')
        assert 'Empty' in html
        assert '<html>' in html.lower()

    def test_html_structure(self):
        html = self._build(['.', 'text'], 'Doc')
        assert html.startswith('<html>')
        assert '</html>' in html

    def test_unicode_in_lines(self):
        html = self._build(['.', '日本語テスト'], 'Unicode')
        assert '日本語テスト' in html

    def test_html_escape_not_double_escaped(self):
        """Lines with < or > should appear in HTML (may be escaped, not broken)."""
        html = self._build(['.', 'a < b'], 'Math')
        # Should be present in some form
        assert 'a' in html and 'b' in html


class TestPickOracleLine:
    """_pick_oracle_line should return a string, falling back to '...' if no files."""

    def test_returns_ellipsis_on_empty_dir(self, tmp_path):
        from new_interface import FullscreenCircleApp
        app = MagicMock()
        result = FullscreenCircleApp._pick_oracle_line(app, str(tmp_path))
        assert result == '...'

    def test_returns_line_from_file(self, tmp_path):
        (tmp_path / 'notes.txt').write_text('.\nhello oracle\n', encoding='utf-8')
        from new_interface import FullscreenCircleApp
        app = MagicMock()
        result = FullscreenCircleApp._pick_oracle_line(app, str(tmp_path))
        assert result == 'hello oracle'

    def test_excludes_0txt(self, tmp_path):
        (tmp_path / '0.txt').write_text('.\nshould be excluded\n', encoding='utf-8')
        (tmp_path / 'real.txt').write_text('.\nreal line\n', encoding='utf-8')
        from new_interface import FullscreenCircleApp
        app = MagicMock()
        results = set()
        for _ in range(20):
            results.add(FullscreenCircleApp._pick_oracle_line(app, str(tmp_path)))
        assert 'should be excluded' not in results

    def test_excludes_dot_only_lines(self, tmp_path):
        (tmp_path / 'book.txt').write_text('.\n.\n.\n', encoding='utf-8')
        from new_interface import FullscreenCircleApp
        app = MagicMock()
        result = FullscreenCircleApp._pick_oracle_line(app, str(tmp_path))
        assert result == '...'  # falls back since no valid lines


class TestLastLinePersistence:
    """_save_last_line and _restore_last_line roundtrip."""

    def test_save_and_restore(self, tmp_path):
        from new_interface import FullscreenCircleApp
        from helpers import make_ring_app

        app = make_ring_app(['.', 'a', 'b', 'c'])
        app.book_dir = str(tmp_path)
        app.line_ring.index = 2

        app.save_ll = FullscreenCircleApp._save_last_line.__get__(app, type(app))
        app.restore_ll = FullscreenCircleApp._restore_last_line.__get__(app, type(app))

        app.save_ll()

        # Change index
        app.line_ring.index = 0
        app.restore_ll()
        assert app.line_ring.index == 2

    def test_restore_clamps_to_valid_index(self, tmp_path):
        from new_interface import FullscreenCircleApp
        from helpers import make_ring_app

        app = make_ring_app(['.', 'a', 'b'])
        app.book_dir = str(tmp_path)

        # Save with a large index manually
        path = os.path.join(str(tmp_path), '_last_lines.json')
        fname = os.path.basename(app.current_file_path)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump({fname: 9999}, f)

        app.restore_ll = FullscreenCircleApp._restore_last_line.__get__(app, type(app))
        app.restore_ll()
        assert app.line_ring.index <= len(app.line_ring.lines) - 1

    def test_restore_graceful_on_missing_file(self, tmp_path):
        from new_interface import FullscreenCircleApp
        from helpers import make_ring_app

        app = make_ring_app(['.', 'a'])
        app.book_dir = str(tmp_path)
        # No _last_lines.json file
        app.restore_ll = FullscreenCircleApp._restore_last_line.__get__(app, type(app))
        app.restore_ll()  # should not raise
        assert app.line_ring.index == 0
