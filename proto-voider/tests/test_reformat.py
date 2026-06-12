import types
import pytest
from unittest.mock import MagicMock
from helpers import make_ring_app


def _make_reformat_app(tmp_path, content):
    from new_interface import FullscreenCircleApp

    p = tmp_path / "doc.txt"
    p.write_text(content, encoding='utf-8')

    app = make_ring_app(['.'], tmp_file=str(p))
    app.current_file_path = str(p)

    m = getattr(FullscreenCircleApp, 'reformat_active_file')
    app.reformat_active_file = types.MethodType(m, app)

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
        assert lines.count('.') == 2
        dot_positions = [i for i, l in enumerate(lines) if l == '.']
        assert dot_positions[0] == 0
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
        assert not any(l == 'Dr.' for l in lines)
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
