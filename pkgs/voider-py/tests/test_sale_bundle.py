"""F4 -> Ctrl+Shift+A: exportar PDF + EPUB + TXT juntos -- todo lo que hace
falta para subir un libro a la venta en un solo lugar. Mismo alcance que el
PDF/carrusel (_reading_sections): el capitulo resaltado, o el libro entero
si F3 esta resaltado sobre un '.'. Mismo prompt de nombre que el carrusel
(_carousel_out_name) cuando es libro entero.

El .txt de un solo capitulo es el archivo tal cual. El .txt de un libro
entero junta los capitulos con separadores /nombre-de-capitulo, el mismo
marcador que Voider ya usa para fences/dispatch -- no un formato nuevo.

Destino: Federico pidio que, configurado, vaya derecho a la carpeta del
sitio (books/ o libros/ segun idioma) en vez de una carpeta local -- pero
esas son rutas absolutas de SU maquina, sin sentido para cualquier otra
instalacion de Voider (el .exe que compilo para que otros descarguen).
sale_bundle_dir_es/en en config.json, vacios por defecto: sin configurar,
cae a void_dir/gPTA_books/<nombre>/ de siempre.
"""
import os
import types
import pytest
from contextlib import ExitStack
from unittest.mock import patch

pytest.importorskip("PyQt6")
from PyQt6.QtWidgets import QApplication

from line_ring import LineRing
from helpers import make_ring_app


@pytest.fixture(scope='module')
def qapp():
    yield QApplication.instance() or QApplication([])


def _app(tmp_path, library, book_index):
    """Mirrors test_carousel_export.py's harness so export_sale_bundle
    exercises the real _reading_sections()."""
    from new_interface import FullscreenCircleApp
    app = make_ring_app(['.'])
    void = tmp_path
    (void / 'I').mkdir(exist_ok=True)
    app.void_dir = str(void)
    app._library_lines = []
    app._library_path_cache = {}
    ring_names = []
    for name in library:
        if name == '.':
            app._library_lines.append('.')
            ring_names.append('.')
            continue
        fn = name + '.txt'
        app._library_lines.append(fn)
        ring_names.append(name)
        p = str(void / 'I' / fn)
        with open(p, 'w', encoding='utf-8') as f:
            f.write(f'Contenido real de {name}, con texto de sobra.\n.\n')
        app._library_path_cache[fn] = p
    app.book_ring = LineRing(ring_names or ['.'])
    app.book_ring.index = book_index
    app.current_file_path = str(void / 'I' / '0.txt')
    open(app.current_file_path, 'w').close()
    app.config = {'sale_bundle_dir_es': '', 'sale_bundle_dir_en': ''}
    for nm in ('_reading_sections', '_reading_file_lines', '_carousel_out_name',
               '_sections_as_txt', '_sale_bundle_dir', 'export_sale_bundle'):
        setattr(app, nm, types.MethodType(getattr(FullscreenCircleApp, nm), app))
    return app


def _dialogs(name_result=('A', True), lang_result=('Español', True)):
    """Patches both prompts export_sale_bundle can show: the folder-name
    dialog (only for a whole-book export) and the language dropdown
    (always). Returns a stack a test can `with`."""
    stack = ExitStack()
    stack.enter_context(patch('PyQt6.QtWidgets.QInputDialog.getText',
                              return_value=name_result))
    stack.enter_context(patch('PyQt6.QtWidgets.QInputDialog.getItem',
                              return_value=lang_result))
    return stack


def _bundle_dir(tmp_path, name):
    return tmp_path / 'gPTA_books' / name


class TestSectionsAsTxt:

    def test_single_section_is_the_raw_lines_unchanged(self, tmp_path):
        app = _app(tmp_path, ['.', 'A'], book_index=1)
        sections = [('A', ['Primera linea.', '.', 'Segunda linea.'])]
        txt = app._sections_as_txt(sections)
        assert txt == 'Primera linea.\n.\nSegunda linea.\n'

    def test_multiple_sections_get_name_fences_between_them(self, tmp_path):
        app = _app(tmp_path, ['.', 'A', 'B'], book_index=0)
        sections = [('Uno', ['linea uno.']), ('Dos', ['linea dos.'])]
        txt = app._sections_as_txt(sections)
        lines = txt.splitlines()
        assert lines[0] == '/Uno'
        assert 'linea uno.' in lines
        assert '/Dos' in lines
        assert lines.index('/Dos') > lines.index('linea uno.')
        assert 'linea dos.' in lines


class TestExportSaleBundle:

    def test_single_chapter_writes_all_three_formats(self, qapp, tmp_path):
        app = _app(tmp_path, ['.', 'A', 'B'], book_index=1)   # highlight A
        with _dialogs():
            app.export_sale_bundle()
        d = _bundle_dir(tmp_path, 'A')
        assert (d / 'A.pdf').is_file()
        assert (d / 'A.epub').is_file()
        assert (d / 'A.txt').is_file()

    def test_pdf_and_epub_are_not_empty_shells(self, qapp, tmp_path):
        app = _app(tmp_path, ['.', 'A'], book_index=1)
        with _dialogs():
            app.export_sale_bundle()
        d = _bundle_dir(tmp_path, 'A')
        assert (d / 'A.pdf').stat().st_size > 500
        assert (d / 'A.epub').stat().st_size > 500

    def test_txt_contains_the_actual_chapter_text(self, qapp, tmp_path):
        app = _app(tmp_path, ['.', 'A'], book_index=1)
        with _dialogs():
            app.export_sale_bundle()
        d = _bundle_dir(tmp_path, 'A')
        content = (d / 'A.txt').read_text(encoding='utf-8')
        assert 'Contenido real de A' in content

    def test_whole_book_prompts_for_a_name(self, qapp, tmp_path):
        app = _app(tmp_path, ['.', 'A', 'B'], book_index=0)   # highlight the '.'
        with _dialogs(name_result=('MiLibro', True)):
            app.export_sale_bundle()
        d = _bundle_dir(tmp_path, 'MiLibro')
        assert (d / 'MiLibro.pdf').is_file()
        assert (d / 'MiLibro.epub').is_file()
        assert (d / 'MiLibro.txt').is_file()

    def test_whole_book_txt_has_both_chapters(self, qapp, tmp_path):
        app = _app(tmp_path, ['.', 'A', 'B'], book_index=0)
        with _dialogs(name_result=('MiLibro', True)):
            app.export_sale_bundle()
        content = (_bundle_dir(tmp_path, 'MiLibro') / 'MiLibro.txt').read_text(
            encoding='utf-8')
        assert 'Contenido real de A' in content
        assert 'Contenido real de B' in content

    def test_cancelled_name_dialog_writes_nothing(self, qapp, tmp_path):
        app = _app(tmp_path, ['.', 'A', 'B'], book_index=0)
        with _dialogs(name_result=('', False)):
            app.export_sale_bundle()
        assert not (tmp_path / 'gPTA_books').exists()

    def test_empty_name_writes_nothing(self, qapp, tmp_path):
        app = _app(tmp_path, ['.', 'A', 'B'], book_index=0)
        with _dialogs(name_result=('   ', True)):
            app.export_sale_bundle()
        assert not (tmp_path / 'gPTA_books').exists()


class TestLanguageAndDestination:

    def test_cancelled_language_dialog_writes_nothing(self, qapp, tmp_path):
        app = _app(tmp_path, ['.', 'A'], book_index=1)
        with _dialogs(lang_result=('', False)):
            app.export_sale_bundle()
        assert not (tmp_path / 'gPTA_books').exists()

    def test_unconfigured_falls_back_to_local_gpta_books(self, qapp, tmp_path):
        app = _app(tmp_path, ['.', 'A'], book_index=1)
        with _dialogs(lang_result=('English', True)):
            app.export_sale_bundle()
        assert (_bundle_dir(tmp_path, 'A') / 'A.pdf').is_file()

    def test_spanish_uses_the_configured_es_dir(self, qapp, tmp_path):
        app = _app(tmp_path, ['.', 'A'], book_index=1)
        dest = tmp_path / 'libros'
        app.config['sale_bundle_dir_es'] = str(dest)
        with _dialogs(lang_result=('Español', True)):
            app.export_sale_bundle()
        assert (dest / 'A' / 'A.pdf').is_file()
        assert not (tmp_path / 'gPTA_books').exists()

    def test_english_uses_the_configured_en_dir(self, qapp, tmp_path):
        app = _app(tmp_path, ['.', 'A'], book_index=1)
        dest = tmp_path / 'books'
        app.config['sale_bundle_dir_en'] = str(dest)
        with _dialogs(lang_result=('English', True)):
            app.export_sale_bundle()
        assert (dest / 'A' / 'A.pdf').is_file()

    def test_configuring_only_english_still_falls_back_for_spanish(self, qapp, tmp_path):
        app = _app(tmp_path, ['.', 'A'], book_index=1)
        app.config['sale_bundle_dir_en'] = str(tmp_path / 'books')
        with _dialogs(lang_result=('Español', True)):
            app.export_sale_bundle()
        assert (_bundle_dir(tmp_path, 'A') / 'A.pdf').is_file()
