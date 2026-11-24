"""book_render.py — dibujar un libro: cada página según el plan, el PDF de lectura
y las hojas impuestas A4 (2 páginas A5 por cara) para imprimir, doblar y coser.

Usa lo mismo que F4: el mismo tamaño A5, la misma tipografía y la misma rutina
de página (reading_page.draw_reading_page), así lo que se lee es lo que se
encuaderna. Cada capítulo se maqueta por separado; el plan (book_plan) decide
dónde cae cada uno y la imposición (imposition) decide en qué hoja va cada página.
"""
import datetime

from PyQt6.QtCore import Qt, QRectF, QSizeF, QPointF
from PyQt6.QtGui import (QColor, QFont, QFontMetricsF, QImage, QPageLayout,
                         QPageSize, QPainter, QPen)
from PyQt6.QtPrintSupport import QPrinter

import book_plan
import imposition
from reading_page import (A5_PT, build_reading_document, compute_page_offsets,
                          draw_reading_page, mm_to_pt)

A4_LANDSCAPE_PT = (mm_to_pt(297), mm_to_pt(210))
_MONTHS = ('enero febrero marzo abril mayo junio julio agosto septiembre octubre '
           'noviembre diciembre').split()


class BookRenderer:

    def __init__(self, titulo, chapters, font, autor='', colofon='', sheets=4,
                 hyphenate_lang='auto', toc=True, colophon=True, cover=False,
                 reference='', dedication=''):
        """chapters: [(título, líneas)] o [(título, líneas, mostrar_título)] en el modelo
        de puntos (el título de un capítulo con mostrar_título=False no se imprime en su
        página, pero el índice lo nombra). cover: anteportada (sólo el título) antes de
        la portada. reference: el texto de la página final (la referencia al software).
        dedication: el texto de la dedicatoria, en una página sola. Vacío = sin esa página."""
        self.titulo, self.autor, self.colofon_text = titulo, autor, colofon
        self.cover, self.reference = bool(cover), (reference or '').strip()
        self.dedication = (dedication or '').strip()
        self.font = QFont(font)
        self.ink = QColor('#111111')
        self.toc, self.colophon = toc, colophon
        self.page_w, self.page_h = A5_PT
        self.titles = [c[0] for c in chapters]
        self.show_title = [c[2] if len(c) > 2 else True for c in chapters]
        self._docs = []
        for c, show in zip(chapters, self.show_title):
            title, lines = c[0], c[1]
            doc, _, layout = build_reading_document(
                [(title if show else '', lines)], self.font, page_pt=A5_PT,
                hyphenate_lang=hyphenate_lang, ink=self.ink)
            offsets = compute_page_offsets(doc, layout.block_h, layout.title_blocks)
            self._docs.append((doc, layout, offsets))
        self.layout = self._docs[0][1] if self._docs else None
        self.set_sheets(sheets)

    # ── el plan ──────────────────────────────────────────────────────────────

    def chapter_pages(self, i):
        return len(self._docs[i][2])

    def set_sheets(self, sheets):
        """Cambiar las hojas por cuadernillo: sólo se recalcula el relleno final."""
        self.plan = book_plan.plan_book(
            self.titulo, [(t, self.chapter_pages(i)) for i, t in enumerate(self.titles)],
            sheets=sheets, toc=self.toc, colophon=self.colophon,
            cover=self.cover, reference=bool(self.reference),
            dedication=bool(self.dedication))

    @property
    def content_pages(self):
        return self.plan.content_pages

    @property
    def blank(self):
        """Páginas en blanco que sobran con las hojas por cuadernillo actuales."""
        return self.plan.blank

    def signature_table(self, options=range(2, 9)):
        """La tabla de páginas en blanco, calculada con el largo REAL del libro."""
        return imposition.signature_table(self.plan.content_pages, options)

    # ── una página ───────────────────────────────────────────────────────────

    def _font_scaled(self, k, italic=False):
        f = QFont(self.font)
        f.setPointSizeF(max(self.font.pointSizeF(), 1.0) * k)
        f.setItalic(italic)
        return f

    @property
    def _margins(self):
        lay = self.layout
        if lay is not None:
            return lay.m_top, lay.m_bottom, lay.m_inner, lay.m_outer
        return tuple(mm_to_pt(m) for m in (21.0, 21.0, 20.0, 20.0))

    def draw_page(self, painter, spec):
        """Dibuja una página del plan en (0,0)-(page_w,page_h), en puntos."""
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        painter.setPen(self.ink)
        kind = spec.kind
        if kind == 'chapter':
            doc, layout, offsets = self._docs[spec.chapter]
            draw_reading_page(painter, doc, layout, offsets, spec.part, self.ink)
            self._draw_number(painter, spec.number)
        elif kind == 'cover':
            self._draw_cover(painter)
        elif kind == 'title':
            self._draw_title(painter)
        elif kind == 'dedication':
            self._draw_dedication(painter)
        elif kind == 'reference':
            self._draw_reference(painter)
        elif kind == 'toc':
            self._draw_toc(painter, spec)
        elif kind == 'colophon':
            self._draw_colophon(painter)
        elif kind == 'notes':
            self._draw_notes(painter)
        painter.restore()

    def _draw_number(self, painter, n):
        _, bottom, _, _ = self._margins
        painter.setFont(self._font_scaled(0.85))
        painter.drawText(QRectF(0, self.page_h - bottom * 0.75, self.page_w, bottom * 0.5),
                         Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter, str(n))

    def _draw_cover(self, painter):
        """La anteportada: sólo el título, chico y centrado. El autor va en la portada
        (la página siguiente), como en un libro de imprenta."""
        _, _, inner, outer = self._margins
        painter.setFont(self._font_scaled(1.7))
        painter.drawText(
            QRectF(inner, self.page_h * 0.36, self.page_w - inner - outer, self.page_h * 0.16),
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter
            | Qt.TextFlag.TextWordWrap, self.titulo)

    def _draw_dedication(self, painter):
        """La dedicatoria: una página sola, el texto centrado y en cursiva, sin título."""
        _, _, inner, outer = self._margins
        painter.setFont(self._font_scaled(1.05, italic=True))
        painter.drawText(
            QRectF(inner, self.page_h * 0.30, self.page_w - inner - outer, self.page_h * 0.34),
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter
            | Qt.TextFlag.TextWordWrap, self.dedication)

    def _draw_reference(self, painter):
        """Una página al final con la referencia al software, chica y centrada."""
        _, _, inner, outer = self._margins
        painter.setFont(self._font_scaled(0.9, italic=True))
        painter.drawText(
            QRectF(inner, self.page_h * 0.62, self.page_w - inner - outer, self.page_h * 0.16),
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop
            | Qt.TextFlag.TextWordWrap, self.reference)

    def _draw_title(self, painter):
        _, _, inner, outer = self._margins
        w = self.page_w - inner - outer
        painter.setFont(self._font_scaled(2.4))
        painter.drawText(
            QRectF(inner, self.page_h * 0.30, w, self.page_h * 0.25),
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter
            | Qt.TextFlag.TextWordWrap, self.titulo)
        if self.autor:
            painter.setFont(self._font_scaled(1.15))
            painter.drawText(
                QRectF(inner, self.page_h * 0.60, w, self.page_h * 0.08),
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter, self.autor)

    def _draw_toc(self, painter, spec):
        top, _, inner, outer = self._margins
        left, right = inner, self.page_w - outer
        head = self._font_scaled(1.3)
        painter.setFont(head)
        if spec.part == 0:
            painter.drawText(QRectF(0, top, self.page_w, QFontMetricsF(head).height() * 1.6),
                             Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
                             'Índice')
        body = self._font_scaled(0.95)
        painter.setFont(body)
        fm = QFontMetricsF(body)
        step = fm.height() * 1.45
        y = top + QFontMetricsF(head).height() * 3.2
        for name, page in spec.entries or []:
            num = str(page)
            num_w = fm.horizontalAdvance(num)
            room = right - left - num_w - fm.horizontalAdvance('  ')
            label = fm.elidedText(name, Qt.TextElideMode.ElideRight, room)
            painter.setPen(self.ink)
            painter.drawText(QPointF(left, y), label)
            painter.drawText(QPointF(right - num_w, y), num)
            lead = QPen(QColor('#888888'))
            lead.setStyle(Qt.PenStyle.DotLine)
            lead.setWidthF(0.6)
            painter.setPen(lead)
            x1 = left + fm.horizontalAdvance(label) + fm.horizontalAdvance(' ')
            x2 = right - num_w - fm.horizontalAdvance(' ')
            if x2 > x1:
                painter.drawLine(QPointF(x1, y - 1.5), QPointF(x2, y - 1.5))
            y += step

    def _colophon_text(self):
        if self.colofon_text.strip():
            return self.colofon_text.strip()
        hoy = datetime.date.today()
        lineas = [self.titulo]
        if self.autor:
            lineas.append(self.autor)
        lineas += ['', f'Compuesto en {self.font.family()}',
                   f'{_MONTHS[hoy.month - 1]} de {hoy.year}']
        return '\n'.join(lineas)

    def _draw_colophon(self, painter):
        _, _, inner, outer = self._margins
        painter.setFont(self._font_scaled(0.85, italic=True))
        painter.drawText(
            QRectF(inner, self.page_h * 0.58, self.page_w - inner - outer, self.page_h * 0.28),
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop
            | Qt.TextFlag.TextWordWrap, self._colophon_text())

    def _draw_notes(self, painter):
        top, _, _, _ = self._margins
        painter.setPen(QColor('#777777'))
        painter.setFont(self._font_scaled(0.9, italic=True))
        painter.drawText(QRectF(0, top, self.page_w, top * 0.8),
                         Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter, 'Notas')

    # ── una cara de una hoja A4 ──────────────────────────────────────────────

    def _draw_face(self, painter, face, sheet_w, sheet_h):
        x0 = (sheet_w - 2 * self.page_w) / 2
        y0 = (sheet_h - self.page_h) / 2
        for i, num in enumerate(face.pages):
            painter.save()
            painter.translate(x0 + i * self.page_w, y0)
            painter.setClipRect(QRectF(0, 0, self.page_w, self.page_h))
            if face.texts:
                self._draw_test_label(painter, face.texts[i])
            elif num is not None:
                self.draw_page(painter, self.plan.pages[num - 1])
            painter.restore()
        self._draw_fold(painter, face.label, sheet_w, sheet_h)

    def _draw_test_label(self, painter, text):
        painter.setPen(self.ink)
        painter.setFont(self._font_scaled(1.6))
        painter.drawText(QRectF(0, 0, self.page_w, self.page_h),
                         Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, text)
        painter.drawRect(QRectF(mm_to_pt(10), mm_to_pt(10),
                                self.page_w - mm_to_pt(20), self.page_h - mm_to_pt(20)))

    def _draw_fold(self, painter, label, sheet_w, sheet_h):
        """Marcas en el pliegue: dos rayitas arriba y abajo (por dónde doblar) y la
        marca de compaginación (cuadernillo y hoja) para armar sin equivocarte."""
        mid = sheet_w / 2
        painter.save()
        painter.setPen(QPen(QColor('#999999'), 0.5))
        painter.drawLine(QPointF(mid, 2), QPointF(mid, 8))
        painter.drawLine(QPointF(mid, sheet_h - 8), QPointF(mid, sheet_h - 2))
        if label:
            f = QFont(self.font)
            f.setPointSizeF(5.5)
            painter.setFont(f)
            painter.setPen(QColor('#888888'))
            painter.drawText(QRectF(mid - 45, sheet_h - 20, 90, 10),
                             Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter, label)
        painter.restore()

    def render_face_image(self, face, width_px=900):
        """Una cara de hoja como imagen (para mirarla en pantalla)."""
        sw, sh = A4_LANDSCAPE_PT
        height = int(width_px * sh / sw)
        img = QImage(width_px, height, QImage.Format.Format_RGB32)
        img.fill(QColor('white'))
        p = QPainter(img)
        p.scale(width_px / sw, width_px / sw)
        self._draw_face(p, face, sw, sh)
        p.end()
        return img

    # ── los PDF ──────────────────────────────────────────────────────────────

    @staticmethod
    def _printer(path, landscape):
        pr = QPrinter(QPrinter.PrinterMode.HighResolution)
        pr.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
        pr.setOutputFileName(path)
        if landscape:
            pr.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
            pr.setPageOrientation(QPageLayout.Orientation.Landscape)
        else:
            pr.setPageSize(QPageSize(QSizeF(*A5_PT), QPageSize.Unit.Point))
        pr.setFullPage(True)
        return pr

    def _write(self, path, items, draw, landscape):
        pr = self._printer(path, landscape)
        painter = QPainter(pr)
        if not painter.isActive():
            return 0
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        rect = pr.pageRect(QPrinter.Unit.DevicePixel)
        ref_w = A4_LANDSCAPE_PT[0] if landscape else self.page_w
        scale = rect.width() / ref_w
        n = 0
        for item in items:
            if n:
                pr.newPage()
            painter.save()
            painter.scale(scale, scale)
            draw(painter, item)
            painter.restore()
            n += 1
        painter.end()
        return n

    def write_reading_pdf(self, path):
        """Las páginas A5 en orden, para leer en pantalla. → cantidad de páginas."""
        return self._write(path, self.plan.pages, self.draw_page, landscape=False)

    def _faces(self, faces, path):
        sw, sh = A4_LANDSCAPE_PT
        return self._write(path, faces, lambda p, f: self._draw_face(p, f, sw, sh),
                           landscape=True)

    def sheets(self):
        return imposition.impose(len(self.plan.pages), self.plan.sheets)

    def write_duplex_pdf(self, path):
        """Para una impresora de doble cara automática (voltear por el borde corto).
        → cantidad de caras (2 por hoja)."""
        return self._faces(imposition.duplex_pages(self.sheets()), path)

    def write_manual_pdfs(self, front_path, back_path):
        """Para dar vuelta las hojas a mano: los frentes y, aparte, los dorsos."""
        fronts, backs = imposition.manual_passes(self.sheets())
        return self._faces(fronts, front_path), self._faces(backs, back_path)

    def write_test_pdf(self, path):
        """Una sola hoja con las cuatro posiciones marcadas, para comprobar cómo da
        vuelta la impresora antes de imprimir el libro entero."""
        return self._faces(imposition.test_sheet(), path)
