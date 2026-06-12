import pytest
from helpers import make_ring_app, has


class TestFileIO:
    def test_load_doc_lines_basic(self, tmp_path):
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


class TestJoinSplit:
    def test_join_prev_normal(self):
        app = make_ring_app(['.', 'hello', 'world', 'end'])
        if not has(app, '_doc_join_prev'):
            pytest.skip("_doc_join_prev not present in this commit")
        app.line_ring.index = 2
        app._doc_join_prev()
        assert app.line_ring.lines == ['.', 'helloworld', 'end']
        assert app.line_ring.index == 1

    def test_join_prev_cursor_at_join_point(self):
        """Cursor position after join should be at the boundary."""
        app = make_ring_app(['.', 'abc', 'def'])
        if not has(app, '_doc_join_prev'):
            pytest.skip("_doc_join_prev not present in this commit")
        app.line_ring.index = 2
        app._doc_join_prev()
        app.circular_view.editor.setCursorPosition.assert_called_with(3)

    def test_join_prev_blocked_by_dot(self):
        """First line after a dot: join is a no-op."""
        app = make_ring_app(['.', 'a', 'b'])
        if not has(app, '_doc_join_prev'):
            pytest.skip("_doc_join_prev not present in this commit")
        app.line_ring.index = 1
        original = list(app.line_ring.lines)
        app._doc_join_prev()
        assert app.line_ring.lines == original

    def test_join_prev_blocked_by_dot_second_para(self):
        """First line of second paragraph: blocked by dot between paragraphs."""
        app = make_ring_app(['.', 'a', '.', 'b', 'c'])
        if not has(app, '_doc_join_prev'):
            pytest.skip("_doc_join_prev not present in this commit")
        app.line_ring.index = 3
        original = list(app.line_ring.lines)
        app._doc_join_prev()
        assert app.line_ring.lines == original

    def test_split_line_middle(self):
        app = make_ring_app(['.', 'abcde'])
        if not has(app, '_doc_split_line'):
            pytest.skip("_doc_split_line not present in this commit")
        app.line_ring.index = 1
        app._doc_split_line(2)
        assert app.line_ring.lines == ['.', 'ab', 'cde']
        assert app.line_ring.index == 2

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
