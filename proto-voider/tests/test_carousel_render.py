"""F4 → carrusel: rasterizado de una página / del slide de título a QPixmap.

No se puede afirmar "se ve bien" en un test unitario, pero sí: el tamaño en
píxeles es EXACTO al pedido, y el resultado no queda en blanco cuando hay
contenido (evita el tipo de bug de esta sesión: código que "pasa" pero no
dibuja nada).
"""
import pytest

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QFont, QColor, QImage

import reading_page as rp


@pytest.fixture(scope='module')
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _font():
    return QFont('EB Garamond', 13)


def _not_blank(pixmap, paper=QColor('#000000')):
    img = pixmap.toImage().convertToFormat(QImage.Format.Format_RGB32)
    paper_rgb = paper.rgb()
    for y in range(0, img.height(), 7):
        for x in range(0, img.width(), 7):
            if img.pixel(x, y) != paper_rgb:
                return True
    return False


class TestRenderCarouselPage:

    def _doc(self, lines):
        page_pt = rp.carousel_page_pt(1080, 1350)
        return rp.build_reading_document([('', lines)], _font(), page_pt=page_pt)

    def test_pixmap_is_exactly_the_requested_size(self, qapp):
        doc, para_blocks, layout = self._doc(['Una linea.', '.'])
        offsets = rp.compute_page_offsets(doc, layout.block_h, layout.title_blocks)
        pm = rp.render_carousel_page(doc, layout, offsets, 0, 1080, 1350)
        assert pm.width() == 1080
        assert pm.height() == 1350

    def test_a_page_with_text_is_not_left_blank(self, qapp):
        doc, para_blocks, layout = self._doc(['Contenido real del capitulo.', '.'])
        offsets = rp.compute_page_offsets(doc, layout.block_h, layout.title_blocks)
        pm = rp.render_carousel_page(doc, layout, offsets, 0, 1080, 1350)
        assert _not_blank(pm)

    def test_a_long_chapter_paginates_into_multiple_slides(self, qapp):
        lines = []
        for i in range(120):
            lines.append(f'Parrafo numero {i} con texto suficiente para ocupar espacio real en la pagina.')
            lines.append('.')
        doc, para_blocks, layout = self._doc(lines)
        offsets = rp.compute_page_offsets(doc, layout.block_h, layout.title_blocks)
        assert len(offsets) > 1

    def test_default_background_is_black_matching_voiders_own_look(self, qapp):
        """Was white/near-black (the printed-book look, shared with the PDF
        path) — Federico: carousel slides should match Voider's own black
        background / white text, not look like a book page. render_cover_slide
        already defaulted to black/white; title and body slides didn't, so the
        cover flashed to a different background than the rest of the carousel."""
        doc, para_blocks, layout = self._doc(['Una linea.', '.'])
        offsets = rp.compute_page_offsets(doc, layout.block_h, layout.title_blocks)
        pm = rp.render_carousel_page(doc, layout, offsets, 0, 1080, 1350)
        img = pm.toImage().convertToFormat(QImage.Format.Format_RGB32)
        assert img.pixel(5, 5) == QColor('#000000').rgb()


class TestRenderTitleSlide:

    def test_pixmap_is_exactly_the_requested_size(self, qapp):
        pm = rp.render_title_slide('El Titulo', _font(), 1080, 1350)
        assert pm.width() == 1080
        assert pm.height() == 1350

    def test_a_real_title_is_not_left_blank(self, qapp):
        pm = rp.render_title_slide('El Libro de I', _font(), 1080, 1350)
        assert _not_blank(pm)

    def test_an_empty_title_is_left_blank(self, qapp):
        pm = rp.render_title_slide('', _font(), 1080, 1350)
        assert not _not_blank(pm)

    def test_default_background_is_black_matching_voiders_own_look(self, qapp):
        pm = rp.render_title_slide('El Titulo', _font(), 1080, 1350)
        img = pm.toImage().convertToFormat(QImage.Format.Format_RGB32)
        assert img.pixel(5, 5) == QColor('#000000').rgb()
