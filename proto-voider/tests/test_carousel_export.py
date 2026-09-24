"""F4 → Ctrl+Shift+C: exportar la seleccion actual de F3 como carrusel de
Instagram, con el mismo alcance que la exportacion a PDF (_reading_sections):
el capitulo resaltado, o el libro entero si F3 esta resaltado sobre un '.'.

El titulo va en su propio slide (N_titulo.png), el cuerpo empieza recien en
el siguiente slide — a diferencia de build_reading_document normal, donde el
titulo comparte pagina con el cuerpo. Un libro entero no tiene un titulo
unico para nombrar la carpeta, asi que se pregunta antes de escribir nada.
"""
import os
import types
import pytest
from unittest.mock import MagicMock, patch

pytest.importorskip("PyQt6")
from PyQt6.QtWidgets import QApplication

from line_ring import LineRing
from helpers import make_ring_app


@pytest.fixture(scope='module')
def qapp():
    yield QApplication.instance() or QApplication([])


def _app(tmp_path, library, book_index):
    """library: list of names ('.' for separators). Mirrors
    tests/test_reading_sections.py's harness so export_carousel exercises the
    real _reading_sections()."""
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
    app.config = {}
    for nm in ('_reading_sections', '_reading_file_lines', '_carousel_dimensions',
               '_carousel_out_name', '_write_carousel_chapters',
               'export_carousel'):
        setattr(app, nm, types.MethodType(getattr(FullscreenCircleApp, nm), app))
    return app


def _slides(tmp_path, folder):
    d = tmp_path / 'carousel' / folder
    return sorted(p.name for p in d.glob('*.png')) if d.exists() else []


def test_single_highlighted_chapter_writes_its_own_title_and_body(qapp, tmp_path):
    app = _app(tmp_path, ['.', 'A', 'B'], book_index=1)   # highlight A
    app.export_carousel()
    slides = _slides(tmp_path, 'A')
    assert '1_titulo.png' in slides
    assert '2.png' in slides
    assert not (tmp_path / 'carousel' / 'B').exists()


def test_whole_book_prompts_for_a_folder_name(qapp, tmp_path):
    app = _app(tmp_path, ['.', 'A', 'B'], book_index=0)   # highlight the '.'
    with patch('PyQt6.QtWidgets.QInputDialog.getText', return_value=('MiLibro', True)):
        app.export_carousel()
    slides = _slides(tmp_path, 'MiLibro')
    assert '1_titulo.png' in slides                        # A's title
    assert any(s.endswith('_titulo.png') for s in slides if s != '1_titulo.png')  # B's title


def test_whole_book_cancelled_dialog_writes_nothing(qapp, tmp_path):
    app = _app(tmp_path, ['.', 'A', 'B'], book_index=0)
    with patch('PyQt6.QtWidgets.QInputDialog.getText', return_value=('', False)):
        app.export_carousel()
    assert not (tmp_path / 'carousel').exists()


def test_whole_book_empty_name_writes_nothing(qapp, tmp_path):
    app = _app(tmp_path, ['.', 'A', 'B'], book_index=0)
    with patch('PyQt6.QtWidgets.QInputDialog.getText', return_value=('   ', True)):
        app.export_carousel()
    assert not (tmp_path / 'carousel').exists()


def test_whole_book_numbers_slides_continuously_across_chapters(qapp, tmp_path):
    app = _app(tmp_path, ['.', 'A', 'B'], book_index=0)
    with patch('PyQt6.QtWidgets.QInputDialog.getText', return_value=('MiLibro', True)):
        app.export_carousel()
    slides = _slides(tmp_path, 'MiLibro')
    # A's title (1), A's body (2), B's title (3), B's body (4) — no gaps, no reuse
    assert slides == ['1_titulo.png', '2.png', '3_titulo.png', '4.png']


def test_uses_the_configured_preset(qapp, tmp_path):
    app = _app(tmp_path, ['.', 'A'], book_index=1)
    app.config['carousel_preset'] = '1:1'
    app.export_carousel()
    from PyQt6.QtGui import QPixmap
    pm = QPixmap(str(tmp_path / 'carousel' / 'A' / '1_titulo.png'))
    assert pm.width() == pm.height() == 1080


def test_uses_custom_dimensions(qapp, tmp_path):
    app = _app(tmp_path, ['.', 'A'], book_index=1)
    app.config['carousel_preset'] = 'custom'
    app.config['carousel_w'] = 800
    app.config['carousel_h'] = 600
    app.export_carousel()
    from PyQt6.QtGui import QPixmap
    pm = QPixmap(str(tmp_path / 'carousel' / 'A' / '1_titulo.png'))
    assert (pm.width(), pm.height()) == (800, 600)


def test_a_long_chapter_produces_several_body_slides(qapp, tmp_path):
    from new_interface import FullscreenCircleApp
    app = make_ring_app(['.'])
    (tmp_path / 'I').mkdir(exist_ok=True)
    app.void_dir = str(tmp_path)
    fn = 'Largo.txt'
    p = str(tmp_path / 'I' / fn)
    lines = []
    for i in range(120):
        lines.append(f'Parrafo numero {i} con texto suficiente para ocupar espacio real en la pagina de verdad.')
        lines.append('.')
    with open(p, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')
    app._library_lines = ['.', fn]
    app._library_path_cache = {fn: p}
    app.book_ring = LineRing(['.', 'Largo'])
    app.book_ring.index = 1
    app.current_file_path = p
    app.config = {}
    for nm in ('_reading_sections', '_reading_file_lines', '_carousel_dimensions',
               '_carousel_out_name', '_write_carousel_chapters',
               'export_carousel'):
        setattr(app, nm, types.MethodType(getattr(FullscreenCircleApp, nm), app))
    app.export_carousel()
    slides = _slides(tmp_path, 'Largo')
    body = [s for s in slides if s != '1_titulo.png']
    assert len(body) > 1
