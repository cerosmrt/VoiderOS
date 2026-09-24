"""render_cover_slide: the book carousel's cover — a chosen circle screenshot
scaled to fill the carousel frame (center-cropped, no distortion), with the
'I' mark drawn centered on top, same routine as the chapter title slides.
"""
import pytest

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QFont, QColor, QPixmap

import reading_page as rp


@pytest.fixture(scope='module')
def qapp():
    yield QApplication.instance() or QApplication([])


def _make_source_image(path, w, h, color='#204060'):
    pm = QPixmap(w, h)
    pm.fill(QColor(color))
    pm.save(str(path))


def test_output_is_exactly_the_requested_size(qapp, tmp_path):
    src = tmp_path / 'src.png'
    _make_source_image(src, 400, 300)
    pm = rp.render_cover_slide(str(src), 1080, 1350, QFont('EB Garamond', 13))
    assert pm.width() == 1080
    assert pm.height() == 1350


def test_output_size_is_correct_even_for_a_taller_source(qapp, tmp_path):
    src = tmp_path / 'tall.png'
    _make_source_image(src, 200, 900)
    pm = rp.render_cover_slide(str(src), 1080, 1080, QFont('EB Garamond', 13))
    assert pm.width() == 1080
    assert pm.height() == 1080


def test_missing_image_falls_back_without_crashing(qapp, tmp_path):
    pm = rp.render_cover_slide(str(tmp_path / 'nope.png'), 1080, 1350,
                                QFont('EB Garamond', 13))
    assert pm.width() == 1080
    assert pm.height() == 1350


def test_the_mark_is_actually_drawn(qapp, tmp_path):
    src = tmp_path / 'src.png'
    _make_source_image(src, 1080, 1350, color='#000000')
    pm = rp.render_cover_slide(str(src), 1080, 1350, QFont('EB Garamond', 13),
                                mark='I', ink=QColor('#ffffff'))
    img = pm.toImage()
    center = img.pixel(img.width() // 2, img.height() // 2)
    assert center != QColor('#000000').rgb()   # the white 'I' overwrote the black fill
