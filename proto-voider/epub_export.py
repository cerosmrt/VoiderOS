# epub_export.py — EPUB export for F4's Ctrl+Shift+A bundle (PDF + EPUB +
# TXT), so a book Federico is selling reads properly on a Kindle or any
# other e-reader — Amazon accepts EPUB directly now, no MOBI conversion
# needed.
#
# Same content model as reading_page.py's PDF pipeline: sections is a list
# of (chapter_title, lines) — one section per chapter, lines in the raw
# dot-model. Reuses reading_page.lines_to_paragraphs so a paragraph in the
# EPUB is exactly the same paragraph the PDF/carousel exporters see — one
# source of truth for "where does this sentence break", not two drifting
# implementations of the same dot-model rule.
import uuid
from html import escape

from ebooklib import epub

from reading_page import lines_to_paragraphs


def build_epub(sections, title, out_path, author='', lang='es'):
    """Write an EPUB to out_path. sections: [(chapter_title, lines), ...] —
    chapter_title may be '' (no heading rendered, matching how
    build_reading_document treats a falsy title). One EpubHtml chapter per
    section, in order, with a working nav/TOC."""
    book = epub.EpubBook()
    book.set_identifier(str(uuid.uuid4()))
    book.set_title(title)
    book.set_language(lang)
    if author:
        book.add_author(author)

    chapters = []
    for i, (chapter_title, lines) in enumerate(sections):
        heading = f'<h1>{escape(chapter_title)}</h1>' if chapter_title else ''
        body = ''.join(f'<p>{escape(p)}</p>'
                       for p in lines_to_paragraphs(lines))
        html_title = chapter_title or f'Capitulo {i + 1}'
        item = epub.EpubHtml(title=html_title, file_name=f'chap_{i + 1}.xhtml',
                             lang=lang)
        # ebooklib wraps this in its own <html><head>...<body> template at
        # write time — .content is just what goes INSIDE <body>, not a full
        # document. Setting a complete <html> here (the first thing tried)
        # made get_body_content()'s own re-parse choke with "Document is
        # empty", failing every write.
        item.content = f'{heading}{body}'
        book.add_item(item)
        chapters.append(item)

    book.toc = tuple(chapters)
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = ['nav'] + chapters
    epub.write_epub(out_path, book)
