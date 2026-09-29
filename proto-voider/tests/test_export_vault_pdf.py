"""F4's Ctrl+S/Ctrl+P (export_vault / print_vault) built a plain centered
monospace HTML dump (_build_doc_html) — not the justified/hyphenated serif
typesetting reading_page.build_reading_document already produces for F4's
own on-screen book view and for the carousel export. This file's own
docstring even says build_reading_document's document "is what gets
printed, so what you read is what binds (WYSIWYG)" — it was, for the
screen, never for the actual PDF/print output.

Federico is preparing books for sale (PDF + EPUB + TXT bundle) and wants the
PDF to actually be the nice one, matching what F4 shows on screen.

Two bugs chased in sequence, both confirmed with real renders (pdftotext /
pdftoppm on an actual exported PDF), not just mocks:
  1. doc.print(printer) directly — build_reading_document lays the whole
     book out as one continuous ~1,000,000pt "page" for manual pagination
     (compute_page_offsets); handed straight to Qt's own print pagination,
     that huge page gets scaled ~1000x to fit a real page and the text
     becomes sub-pixel. Fixed by print_reading_document, which replays the
     same per-page clip/scale render compute_page_offsets already drives
     for the carousel export, but onto the printer's own QPainter with
     printer.newPage() between pages.
  2. No ink colour — build_reading_document's char formats carry no colour
     unless told to (the on-screen view supplies it separately via a
     palette override that a direct print never goes through). Fixed by
     always passing an explicit ink here.
"""
import types
from unittest.mock import MagicMock, patch

from helpers import make_ring_app


def _app(tmp_path, sections):
    from new_interface import FullscreenCircleApp
    book_dir = tmp_path / 'I'
    book_dir.mkdir()
    active = book_dir / '0.txt'
    active.write_text('.\n', encoding='utf-8')
    app = make_ring_app(['.'], tmp_file=str(active))
    app.void_dir = str(tmp_path)
    app.current_file_path = str(active)
    app.config = {'reading_font': 'EB Garamond', 'reading_size': 13,
                  'reading_hyphen_lang': 'auto'}
    app._reading_sections = MagicMock(return_value=(sections, True))
    for name in ('print_vault', 'export_vault', '_print_reading_doc',
                 '_printer_from_dialog', '_printer_from_save_dialog'):
        if hasattr(FullscreenCircleApp, name):
            app.__dict__[name] = types.MethodType(
                getattr(FullscreenCircleApp, name), app)
    return app


def _sections():
    return [('Capitulo Uno', ['Linea de prueba.', '.', 'Otra linea mas.'])]


def _patched(app, printer_attr, printer, doc=None, offsets=None):
    """Context manager stack: fakes the printer dialog, build_reading_document,
    compute_page_offsets, and print_reading_document all at once, returning
    the three mocks so a test can assert on whichever it needs."""
    from contextlib import ExitStack
    stack = ExitStack()
    stack.enter_context(patch.object(app, printer_attr, return_value=printer))
    bd = stack.enter_context(patch(
        'reading_page.build_reading_document',
        return_value=(doc or MagicMock(), [], MagicMock())))
    cpo = stack.enter_context(patch(
        'reading_page.compute_page_offsets', return_value=offsets or [0.0]))
    prd = stack.enter_context(patch('reading_page.print_reading_document'))
    return stack, bd, cpo, prd


class TestExportVault:

    def test_uses_reading_pages_document_builder(self, tmp_path):
        app = _app(tmp_path, _sections())
        stack, bd, cpo, prd = _patched(app, '_printer_from_save_dialog', MagicMock())
        with stack:
            app.export_vault()
        bd.assert_called_once()
        args, _ = bd.call_args
        assert args[0] == _sections()

    def test_the_built_document_is_sent_to_print_reading_document(self, tmp_path):
        app = _app(tmp_path, _sections())
        fake_doc = MagicMock()
        fake_printer = MagicMock()
        stack, bd, cpo, prd = _patched(app, '_printer_from_save_dialog',
                                       fake_printer, doc=fake_doc)
        with stack:
            app.export_vault()
        prd.assert_called_once()
        args, kwargs = prd.call_args
        assert args[0] is fake_doc
        assert args[3] is fake_printer

    def test_does_not_call_docs_own_print_directly(self, tmp_path):
        """The bug: doc.print(printer) scales the ~1,000,000pt continuous
        layout page down ~1000x to fit a real page — sub-pixel, invisible
        text (confirmed with a real render)."""
        app = _app(tmp_path, _sections())
        fake_doc = MagicMock()
        stack, bd, cpo, prd = _patched(app, '_printer_from_save_dialog',
                                       MagicMock(), doc=fake_doc)
        with stack:
            app.export_vault()
        fake_doc.print.assert_not_called()

    def test_passes_an_explicit_ink_color_to_build_reading_document(self, tmp_path):
        app = _app(tmp_path, _sections())
        stack, bd, cpo, prd = _patched(app, '_printer_from_save_dialog', MagicMock())
        with stack:
            app.export_vault()
        _, kwargs = bd.call_args
        assert kwargs.get('ink') is not None

    def test_passes_an_explicit_ink_color_to_print_reading_document(self, tmp_path):
        app = _app(tmp_path, _sections())
        stack, bd, cpo, prd = _patched(app, '_printer_from_save_dialog', MagicMock())
        with stack:
            app.export_vault()
        _, kwargs = prd.call_args
        assert kwargs.get('ink') is not None

    def test_uses_the_configured_reading_font_and_size(self, tmp_path):
        app = _app(tmp_path, _sections())
        app.config['reading_font'] = 'Georgia'
        app.config['reading_size'] = 17
        stack, bd, cpo, prd = _patched(app, '_printer_from_save_dialog', MagicMock())
        with stack:
            app.export_vault()
        font = bd.call_args.args[1]
        assert font.family() == 'Georgia'
        assert font.pointSize() == 17

    def test_no_longer_builds_the_plain_centered_html(self, tmp_path):
        app = _app(tmp_path, _sections())
        app._build_doc_html = MagicMock(side_effect=AssertionError(
            'export_vault should not build the plain HTML any more'))
        stack, bd, cpo, prd = _patched(app, '_printer_from_save_dialog', MagicMock())
        with stack:
            app.export_vault()   # would raise via the mock above if it regressed


class TestPrintVault:

    def test_uses_reading_pages_document_builder_and_prints(self, tmp_path):
        app = _app(tmp_path, _sections())
        fake_doc = MagicMock()
        fake_printer = MagicMock()
        stack, bd, cpo, prd = _patched(app, '_printer_from_dialog',
                                       fake_printer, doc=fake_doc)
        with stack:
            app.print_vault()
        bd.assert_called_once()
        prd.assert_called_once()
        args, _ = prd.call_args
        assert args[0] is fake_doc
        assert args[3] is fake_printer
