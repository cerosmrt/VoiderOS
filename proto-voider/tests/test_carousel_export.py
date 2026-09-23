"""F4 → Ctrl+Shift+C: exportar el capitulo actual como carrusel de Instagram.

El titulo va en su propio slide (1_titulo.png), el cuerpo empieza recien en el
slide 2 — a diferencia de build_reading_document normal, donde el titulo
comparte pagina con el cuerpo.
"""
import os
import types
import pytest
from unittest.mock import MagicMock

pytest.importorskip("PyQt6")
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QFont

import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from line_ring import LineRing
from helpers import make_ring_app
from new_interface import FullscreenCircleApp


@pytest.fixture(scope='module')
def qapp():
    yield QApplication.instance() or QApplication([])


def _app(tmp_path, body_lines, title='Capitulo Uno'):
    app = make_ring_app(['.'])
    void = tmp_path
    (void / 'I').mkdir(exist_ok=True)
    app.void_dir = str(void)
    fn = title + '.txt'
    p = str(void / 'I' / fn)
    with open(p, 'w', encoding='utf-8') as f:
        f.write('\n'.join(body_lines) + '\n')
    app._library_lines = ['.', fn]
    app._library_path_cache = {fn: p}
    app.book_ring = LineRing(['.', title])
    app.book_ring.index = 1                      # highlighted on the chapter
    app.current_file_path = p
    app.config = {}
    for nm in ('_reading_file_lines', '_carousel_current_chapter', 'export_carousel'):
        if hasattr(FullscreenCircleApp, nm):
            setattr(app, nm, types.MethodType(getattr(FullscreenCircleApp, nm), app))
    return app


def _slides(tmp_path, title='Capitulo Uno'):
    d = tmp_path / 'carousel' / title
    return sorted(p.name for p in d.glob('*.png')) if d.exists() else []


def test_current_chapter_picks_up_the_highlighted_title(qapp, tmp_path):
    app = _app(tmp_path, ['Una linea.', '.'])
    title, lines = app._carousel_current_chapter()
    assert title == 'Capitulo Uno'
    assert lines == ['Una linea.', '.']


def test_export_writes_a_dedicated_title_slide(qapp, tmp_path):
    app = _app(tmp_path, ['Contenido de sobra para llenar una pagina.', '.'])
    app.export_carousel()
    slides = _slides(tmp_path)
    assert '1_titulo.png' in slides


def test_export_writes_at_least_one_body_slide(qapp, tmp_path):
    app = _app(tmp_path, ['Contenido de sobra para llenar una pagina.', '.'])
    app.export_carousel()
    slides = _slides(tmp_path)
    assert '2.png' in slides


def test_export_uses_the_configured_preset(qapp, tmp_path):
    app = _app(tmp_path, ['Texto.', '.'])
    app.config['carousel_preset'] = '1:1'
    app.export_carousel()
    from PyQt6.QtGui import QPixmap
    pm = QPixmap(str(tmp_path / 'carousel' / 'Capitulo Uno' / '1_titulo.png'))
    assert pm.width() == pm.height() == 1080


def test_export_uses_custom_dimensions(qapp, tmp_path):
    app = _app(tmp_path, ['Texto.', '.'])
    app.config['carousel_preset'] = 'custom'
    app.config['carousel_w'] = 800
    app.config['carousel_h'] = 600
    app.export_carousel()
    from PyQt6.QtGui import QPixmap
    pm = QPixmap(str(tmp_path / 'carousel' / 'Capitulo Uno' / '1_titulo.png'))
    assert (pm.width(), pm.height()) == (800, 600)


def test_a_long_chapter_produces_several_body_slides(qapp, tmp_path):
    lines = []
    for i in range(120):
        lines.append(f'Parrafo numero {i} con texto suficiente para ocupar espacio real en la pagina de verdad.')
        lines.append('.')
    app = _app(tmp_path, lines)
    app.export_carousel()
    slides = _slides(tmp_path)
    body = [s for s in slides if s != '1_titulo.png']
    assert len(body) > 1
