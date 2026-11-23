"""Dibujar el libro: cada página según el plan, el PDF de lectura y las hojas
impuestas A4 (2 páginas A5 por cara) listas para imprimir y coser.
"""
import os
import re

import pytest

pytest.importorskip("PyQt6")
from PyQt6.QtGui import QFont, QImage, QPainter, QColor
from PyQt6.QtWidgets import QApplication

import book_plan as bp
import imposition as imp
import book_render as br


@pytest.fixture(scope='module')
def qapp():
    yield QApplication.instance() or QApplication([])


def _lines(n):
    out = []
    for i in range(n):
        out += [f'Una oración numero {i} con texto suficiente para llenar la línea de la página.', '.']
    return out


CHAPS = [('Uno', _lines(40)), ('Dos', _lines(3)), ('Tres', _lines(60))]


def _renderer(sheets=4, **kw):
    return br.BookRenderer('Mitad Humana', CHAPS, QFont('Sans Serif', 11),
                           autor='Federico', sheets=sheets, hyphenate_lang=None, **kw)


def _ink(img, x0=0, x1=None):
    """Cuántos píxeles no blancos hay entre las columnas x0 y x1."""
    x1 = img.width() if x1 is None else x1
    n = 0
    for x in range(x0, x1, 2):
        for y in range(0, img.height(), 2):
            if img.pixelColor(x, y).lightness() < 200:
                n += 1
    return n


def _page_image(r, spec, w=300):
    h = int(w * r.page_h / r.page_w)
    img = QImage(w, h, QImage.Format.Format_RGB32)
    img.fill(QColor('white'))
    p = QPainter(img)
    p.scale(w / r.page_w, w / r.page_w)
    r.draw_page(p, spec)
    p.end()
    return img


# ── el plan sale del texto real ──────────────────────────────────────────────

def test_the_plan_uses_the_real_page_count_of_each_chapter(qapp):
    r = _renderer()
    counts = [r.chapter_pages(i) for i in range(3)]
    assert all(c >= 1 for c in counts)
    assert counts[0] > counts[1] and counts[2] > counts[0]
    assert r.plan.toc[0][0] == 'Uno' and all(p % 2 == 1 for _, p in r.plan.toc)


def test_the_blank_page_table_comes_from_the_real_content_length(qapp):
    r = _renderer()
    rows = r.signature_table()
    assert [x.sheets for x in rows] == [2, 3, 4, 5, 6, 7, 8]
    assert all(x.blank >= 0 for x in rows)
    assert sum(1 for x in rows if x.best) == 1


def test_changing_the_sheets_changes_the_padding_but_not_the_content(qapp):
    a, b = _renderer(sheets=3), _renderer(sheets=6)
    assert a.plan.content_pages == b.plan.content_pages
    assert len(a.plan.pages) % 12 == 0 and len(b.plan.pages) % 24 == 0


# ── cada tipo de página ──────────────────────────────────────────────────────

def test_a_blank_page_is_white(qapp):
    r = _renderer()
    spec = next(p for p in r.plan.pages if p.kind == 'blank')
    assert _ink(_page_image(r, spec)) == 0


@pytest.mark.parametrize('kind', ['title', 'toc', 'chapter', 'colophon', 'notes'])
def test_every_other_page_kind_has_ink(qapp, kind):
    # Las hojas que más páginas dejan sobrando: así hay colofón Y notas que dibujar.
    sheets = max(_renderer().signature_table(), key=lambda row: row.blank).sheets
    r = _renderer(sheets=sheets)
    assert r.plan.blank >= 2
    specs = [p for p in r.plan.pages if p.kind == kind]
    assert specs, f'el plan no tiene páginas {kind}'
    assert _ink(_page_image(r, specs[0])) > 0


def test_the_title_page_is_mostly_empty_with_the_title_in_the_middle(qapp):
    r = _renderer()
    img = _page_image(r, r.plan.pages[0])
    h = img.height()
    top = sum(1 for y in range(0, h // 5) for x in range(0, img.width(), 2)
              if img.pixelColor(x, y).lightness() < 200)
    assert top == 0                          # arriba no hay nada
    assert _ink(img) > 0


def test_a_chapter_page_shows_the_page_number_at_the_bottom(qapp):
    r = _renderer()
    spec = next(p for p in r.plan.pages if p.kind == 'chapter' and p.part == 1)
    img = _page_image(r, spec)
    h = img.height()
    bottom = sum(1 for y in range(int(h * 0.93), h) for x in range(0, img.width(), 1)
                 if img.pixelColor(x, y).lightness() < 200)
    assert bottom > 0


def test_a_chapter_pages_text_changes_from_page_to_page(qapp):
    r = _renderer()
    ps = [p for p in r.plan.pages if p.kind == 'chapter' and p.chapter == 0][:2]
    assert _page_image(r, ps[0]) != _page_image(r, ps[1])


# ── el PDF de lectura ────────────────────────────────────────────────────────

def _pages_in(pdf_path):
    with open(pdf_path, 'rb') as f:
        return len(re.findall(rb'/Type\s*/Page(?!s)', f.read()))


def test_the_reading_pdf_has_one_page_per_plan_page(qapp, tmp_path):
    r = _renderer()
    out = str(tmp_path / 'lectura.pdf')
    r.write_reading_pdf(out)
    assert _pages_in(out) == len(r.plan.pages)


# ── las hojas impuestas ──────────────────────────────────────────────────────

def _sheet_image(r, face, w=800):
    return r.render_face_image(face, w)


def test_a_sheet_puts_each_page_in_its_place(qapp):
    r = _renderer()
    half = None
    for left, right, want_left, want_right in [(1, 2, True, False), (2, 1, False, True)]:
        img = _sheet_image(r, imp.Face((left, right)))
        half = img.width() // 2
        assert (_ink(img, 0, half) > 0) == want_left
        assert (_ink(img, half) > 0) == want_right


def test_a_blank_position_stays_white(qapp):
    r = _renderer()
    img = _sheet_image(r, imp.Face((None, None)))
    assert _ink(img) == 0


def test_the_collation_mark_sits_on_the_fold(qapp):
    r = _renderer()
    img = _sheet_image(r, imp.Face((None, None), 'C3/10 · H2/4'))
    w = img.width()
    assert _ink(img, w // 2 - 40, w // 2 + 40) > 0
    assert _ink(img, 0, w // 4) == 0


def test_the_duplex_pdf_has_a_physical_page_per_sheet_side(qapp, tmp_path):
    r = _renderer()
    out = str(tmp_path / 'doble-cara.pdf')
    n = r.write_duplex_pdf(out)
    sheets = imp.impose(len(r.plan.pages), r.plan.sheets)
    assert n == 2 * len(sheets) and _pages_in(out) == n


def test_the_duplex_pdf_is_a4_landscape(qapp, tmp_path):
    r = _renderer()
    out = str(tmp_path / 'doble-cara.pdf')
    r.write_duplex_pdf(out)
    with open(out, 'rb') as f:
        m = re.search(rb'/MediaBox\s*\[\s*0\s+0\s+([\d.]+)\s+([\d.]+)\s*\]', f.read())
    w, h = float(m.group(1)), float(m.group(2))
    assert w > h and abs(w - 842) < 3 and abs(h - 595) < 3


def test_the_manual_mode_writes_two_pdfs_fronts_then_backs(qapp, tmp_path):
    r = _renderer()
    a, b = str(tmp_path / 'caras.pdf'), str(tmp_path / 'dorsos.pdf')
    nf, nb = r.write_manual_pdfs(a, b)
    sheets = imp.impose(len(r.plan.pages), r.plan.sheets)
    assert nf == nb == len(sheets)
    assert _pages_in(a) == nf and _pages_in(b) == nb


def test_the_test_sheet_is_one_sheet_two_sides(qapp, tmp_path):
    r = _renderer()
    out = str(tmp_path / 'prueba.pdf')
    assert r.write_test_pdf(out) == 2 and _pages_in(out) == 2


def test_the_test_sheet_labels_are_drawn(qapp):
    r = _renderer()
    face = imp.test_sheet()[0]
    img = _sheet_image(r, face)
    assert _ink(img, 0, img.width() // 2) > 0 and _ink(img, img.width() // 2) > 0


def test_every_page_of_the_book_is_drawn_exactly_once_across_the_sheets(qapp):
    """La imposición (ya probada) y el dibujo tienen que coincidir: cada número de
    página del plan aparece en una sola posición de una sola hoja."""
    r = _renderer()
    seen = []
    for s in imp.impose(len(r.plan.pages), r.plan.sheets):
        seen += [p for p in (*s.front, *s.back) if p is not None]
    assert sorted(seen) == list(range(1, len(r.plan.pages) + 1))


# ── la rendija: las puntas de la línea siguiente no pueden asomar ────────────
#
# La página corta justo en el borde de la próxima línea. Las puntas de sus letras
# rozaban esa fila (se midió: tinta a 0,4 pt del corte, con EB Garamond y 132% de
# interlineado). En un libro impreso a 600 ppp asoma. El corte deja un margen.

def _clip_heights(offsets_len=4):
    from reading_page import (A5_PT, build_reading_document, compute_page_offsets,
                              draw_reading_page)
    doc, _, layout = build_reading_document([('T', _lines(80))], QFont('Sans Serif', 11),
                                            page_pt=A5_PT, hyphenate_lang=None)
    offsets = compute_page_offsets(doc, layout.block_h, layout.title_blocks)
    class Espia(QPainter):                 # anota el recorte y deja dibujar de verdad
        rects = []

        def setClipRect(self, rect, *a):
            self.rects.append(rect)
            return super().setClipRect(rect, *a)

    img = QImage(10, 10, QImage.Format.Format_RGB32)
    out = []
    for page in range(len(offsets)):
        painter = Espia(img)
        painter.rects = []
        draw_reading_page(painter, doc, layout, offsets, page, QColor('black'))
        painter.end()
        out.append(painter.rects[0].height())
    return offsets, layout, out


def test_a_page_stops_short_of_the_next_line(qapp):
    offsets, layout, clips = _clip_heights()
    assert len(offsets) >= 3
    for page in range(len(offsets) - 1):
        hasta_la_proxima = min(offsets[page + 1] - offsets[page], layout.block_h)
        assert clips[page] <= hasta_la_proxima - 1.0, page


def test_the_clip_still_covers_the_whole_last_line_of_a_page(qapp):
    """El margen no puede comerse la línea de abajo: sólo la rendija."""
    offsets, layout, clips = _clip_heights()
    for page in range(len(offsets) - 1):
        hasta_la_proxima = min(offsets[page + 1] - offsets[page], layout.block_h)
        assert clips[page] >= hasta_la_proxima - 3.0, page


def test_the_last_page_of_a_chapter_keeps_the_whole_block(qapp):
    offsets, layout, clips = _clip_heights()
    assert clips[-1] == pytest.approx(layout.block_h)
