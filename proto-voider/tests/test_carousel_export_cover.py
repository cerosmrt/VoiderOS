"""F4 -> Ctrl+Shift+B: export the current F3 selection as an Instagram
carousel wrapped with a cover and a countercover. Separate command from plain
export_carousel() (Ctrl+Shift+C) -- covers are opt-in, not part of every
export.

Cover: a chosen image (file picker, defaulting to void_dir/covers/) + the
'I' mark centered on top. Countercover: the chapter's title (or the typed
book name, for a whole-book export), same style as a chapter title slide.
"""
import os
import types
import pytest
from unittest.mock import patch

pytest.importorskip("PyQt6")
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QPixmap, QColor

from line_ring import LineRing
from helpers import make_ring_app


@pytest.fixture(scope='module')
def qapp():
    yield QApplication.instance() or QApplication([])


def _cover_image(tmp_path, name='cover.png'):
    p = tmp_path / name
    pm = QPixmap(400, 400)
    pm.fill(QColor('#000000'))
    pm.save(str(p))
    return str(p)


def _app(tmp_path, library, book_index):
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
               'export_carousel_with_cover'):
        setattr(app, nm, types.MethodType(getattr(FullscreenCircleApp, nm), app))
    return app


def _slides(tmp_path, folder):
    d = tmp_path / 'carousel' / folder
    return sorted(p.name for p in d.glob('*.png')) if d.exists() else []


def test_single_chapter_gets_cover_and_countercover(qapp, tmp_path):
    app = _app(tmp_path, ['.', 'A', 'B'], book_index=1)   # highlight A
    cover = _cover_image(tmp_path)
    with patch('PyQt6.QtWidgets.QFileDialog.getOpenFileName', return_value=(cover, '')):
        app.export_carousel_with_cover()
    slides = _slides(tmp_path, 'A')
    assert slides[0] == '1_portada.png'
    assert slides[-1].endswith('_contratapa.png')
    assert '2_titulo.png' in slides
    assert '3.png' in slides


def test_cancelling_the_cover_picker_writes_nothing(qapp, tmp_path):
    app = _app(tmp_path, ['.', 'A'], book_index=1)
    with patch('PyQt6.QtWidgets.QFileDialog.getOpenFileName', return_value=('', '')):
        app.export_carousel_with_cover()
    assert not (tmp_path / 'carousel').exists()


def test_whole_book_still_prompts_for_a_name_and_uses_it_as_countercover(qapp, tmp_path):
    app = _app(tmp_path, ['.', 'A', 'B'], book_index=0)   # highlight the '.'
    cover = _cover_image(tmp_path)
    with patch('PyQt6.QtWidgets.QFileDialog.getOpenFileName', return_value=(cover, '')), \
         patch('PyQt6.QtWidgets.QInputDialog.getText', return_value=('MiLibro', True)):
        app.export_carousel_with_cover()
    slides = _slides(tmp_path, 'MiLibro')
    assert slides[0] == '1_portada.png'
    assert slides[-1].endswith('_contratapa.png')


def test_countercover_size_matches_the_configured_ratio(qapp, tmp_path):
    app = _app(tmp_path, ['.', 'A'], book_index=1)
    app.config['carousel_preset'] = '1:1'
    cover = _cover_image(tmp_path)
    with patch('PyQt6.QtWidgets.QFileDialog.getOpenFileName', return_value=(cover, '')):
        app.export_carousel_with_cover()
    slides = _slides(tmp_path, 'A')
    pm = QPixmap(str(tmp_path / 'carousel' / 'A' / slides[-1]))
    assert pm.width() == pm.height() == 1080
