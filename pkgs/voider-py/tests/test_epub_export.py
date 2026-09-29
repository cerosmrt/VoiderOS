"""EPUB export for F4's Ctrl+Shift+A bundle (PDF + EPUB + TXT). Same content
model as reading_page.py's PDF pipeline — sections: [(title, lines), ...] —
built as valid EPUB XHTML via ebooklib instead of a QTextDocument, reusing
reading_page.lines_to_paragraphs so paragraph joining exactly matches PDF.

Verified by round-tripping the written file through ebooklib's own reader,
not just checking "a file exists" — the kind of check that would have missed
the PDF export's blank-page bug earlier this session.
"""
import pytest

ebooklib = pytest.importorskip("ebooklib")
from ebooklib import epub

import epub_export as ee


def _read_back(path):
    return epub.read_epub(path)


def _chapter_htmls(book):
    """All EpubHtml chapter items, excluding the nav document (EpubNav is
    itself an ITEM_DOCUMENT — get_items_of_type alone can't tell them apart)."""
    return [item for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT)
            if not isinstance(item, epub.EpubNav)]


class TestBuildEpub:

    def test_writes_a_valid_epub_file(self, tmp_path):
        out = tmp_path / 'book.epub'
        sections = [('Capitulo Uno', ['Una linea.', '.', 'Otra linea.'])]
        ee.build_epub(sections, 'Mi Libro', str(out))
        assert out.is_file()
        book = _read_back(str(out))          # raises if the file is invalid
        assert book.get_metadata('DC', 'title')[0][0] == 'Mi Libro'

    def test_one_chapter_per_section(self, tmp_path):
        out = tmp_path / 'book.epub'
        sections = [
            ('Uno', ['Primera.', '.']),
            ('Dos', ['Segunda.', '.']),
            ('Tres', ['Tercera.', '.']),
        ]
        ee.build_epub(sections, 'Libro', str(out))
        book = _read_back(str(out))
        htmls = _chapter_htmls(book)
        assert len(htmls) == 3

    def test_paragraph_text_is_actually_in_the_content(self, tmp_path):
        out = tmp_path / 'book.epub'
        sections = [('Cap', ['Una frase reconocible aqui.', '.'])]
        ee.build_epub(sections, 'Libro', str(out))
        book = _read_back(str(out))
        htmls = _chapter_htmls(book)
        combined = b''.join(h.get_content() for h in htmls)
        assert b'Una frase reconocible aqui.' in combined

    def test_chapter_title_is_in_the_content(self, tmp_path):
        out = tmp_path / 'book.epub'
        sections = [('El Titulo Del Capitulo', ['linea.', '.'])]
        ee.build_epub(sections, 'Libro', str(out))
        book = _read_back(str(out))
        htmls = _chapter_htmls(book)
        combined = b''.join(h.get_content() for h in htmls)
        assert b'El Titulo Del Capitulo' in combined

    def test_dots_are_not_rendered_as_literal_text(self, tmp_path):
        """The dot-model '.' separator must become a paragraph break, never
        show up as a literal '.' character on its own in the output."""
        out = tmp_path / 'book.epub'
        sections = [('Cap', ['Primera.', '.', 'Segunda.'])]
        ee.build_epub(sections, 'Libro', str(out))
        book = _read_back(str(out))
        htmls = _chapter_htmls(book)
        combined = b''.join(h.get_content() for h in htmls).decode('utf-8')
        # Two distinct paragraphs, not one blob with a stray dot between them.
        assert combined.count('<p>') >= 2

    def test_html_special_characters_are_escaped(self, tmp_path):
        out = tmp_path / 'book.epub'
        sections = [('Cap', ['Texto con <tag> y & ampersand.', '.'])]
        ee.build_epub(sections, 'Libro', str(out))
        book = _read_back(str(out))          # would raise on malformed XHTML
        htmls = _chapter_htmls(book)
        combined = b''.join(h.get_content() for h in htmls).decode('utf-8')
        assert '<tag>' not in combined
        assert '&lt;tag&gt;' in combined

    def test_empty_chapter_title_does_not_crash(self, tmp_path):
        out = tmp_path / 'book.epub'
        sections = [('', ['Solo texto, sin titulo de capitulo.', '.'])]
        ee.build_epub(sections, 'Libro', str(out))
        assert out.is_file()

    def test_sets_the_author_when_given(self, tmp_path):
        out = tmp_path / 'book.epub'
        sections = [('Cap', ['linea.', '.'])]
        ee.build_epub(sections, 'Libro', str(out), author='Federico Moret')
        book = _read_back(str(out))
        creators = book.get_metadata('DC', 'creator')
        assert creators and creators[0][0] == 'Federico Moret'
