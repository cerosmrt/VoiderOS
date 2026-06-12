import types
from unittest.mock import MagicMock, patch
from contextlib import ExitStack
from helpers import make_ring_app


def _make_print_app(tmp_path, book_files_content=None, active_content=None):
    from new_interface import FullscreenCircleApp

    book_dir = tmp_path / "book"
    book_dir.mkdir()
    fnames = []
    if book_files_content:
        for fname, text in book_files_content.items():
            (book_dir / fname).write_text(text, encoding='utf-8')
            fnames.append(fname)

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


class TestPrint:

    def _fake_printer(self, app):
        mock = MagicMock()
        stack = ExitStack()
        stack.enter_context(patch.object(app, '_printer_from_dialog', return_value=mock))
        stack.enter_context(patch.object(app, '_printer_from_save_dialog', return_value=mock))
        return stack

    def test_print_book_excludes_0txt(self, tmp_path):
        """print_book must not include 0.txt in the HTML output."""
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

        with self._fake_printer(app), patch('PyQt6.QtGui.QTextDocument', FakeDoc):
            app.print_book()

        assert captured_html, "print_book did not build any HTML"
        html = captured_html[0]
        assert 'Should be excluded' not in html
        assert 'Chapter one line' in html
        assert 'Chapter two line' in html

    def test_print_book_respects_book_files_order(self, tmp_path):
        """print_book renders chapters in book_files order."""
        files = {'b.txt': '.\nBeta.\n', 'a.txt': '.\nAlpha.\n'}
        app = _make_print_app(tmp_path, book_files_content=files)
        app.book_files = ['b.txt', 'a.txt']
        captured_html = []

        class FakeDoc:
            def setHtml(self_, html): captured_html.append(html)
            def print(self_, printer): pass

        with self._fake_printer(app), patch('PyQt6.QtGui.QTextDocument', FakeDoc):
            app.print_book()

        assert captured_html, "print_book did not build any HTML"
        html = captured_html[0]
        assert html.index('Beta') < html.index('Alpha')

    def _run_print_doc(self, app):
        captured_html = []

        class FakeDoc:
            def setHtml(self_, html): captured_html.append(html)
            def print(self_, printer): pass

        with self._fake_printer(app), patch('PyQt6.QtGui.QTextDocument', FakeDoc):
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
        assert '>.<' not in html
        assert '&nbsp;' in html
        assert 'Real line.' in html
        assert 'Another line.' in html
