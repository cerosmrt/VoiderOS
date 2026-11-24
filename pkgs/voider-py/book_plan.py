"""book_plan.py — qué va en cada página de un libro, en orden. Puro, sin Qt.

  1: página de título (a la derecha)      2: en blanco (atrás del título)
  3: índice (una o varias páginas)        y cada capítulo EMPIEZA A LA DERECHA
  (página impar), con una página en blanco antes si hace falta.
  Al final, lo que falta para completar el último cuadernillo: el colofón en la
  primera página sobrante y las demás para notas. Si no sobra ninguna, no hay colofón.

Recibe cuántas páginas de texto tiene cada capítulo y devuelve la secuencia. El
dibujo (book_render) viene aparte. Las páginas se numeran desde la de título.
"""
from dataclasses import dataclass, field

import imposition

TOC_LINES = 22      # entradas del índice por página


@dataclass
class PageSpec:
    kind: str                   # cover | title | dedication | blank | toc | chapter | reference | colophon | notes
    number: int = 0             # número de página, desde 1 (la de título)
    chapter: int = None         # índice del capítulo (kind == 'chapter')
    part: int = None            # página dentro del capítulo / del índice, desde 0
    entries: list = None        # entradas del índice que lleva esta página


@dataclass
class BookPlan:
    pages: list
    toc: list                   # [(título, página)]
    content_pages: int          # páginas antes de completar el último cuadernillo
    blank: int                  # páginas que sobran
    sheets: int = 4
    title: str = ''


def _toc_pages(n_chapters, toc, toc_lines):
    return -(-n_chapters // toc_lines) if (toc and n_chapters) else 0


def _content(chapters, toc, toc_lines, cover=False, reference=False, dedication=False):
    """Las páginas de contenido y dónde empieza cada capítulo. Lo comparten el plan
    y content_page_count, así no pueden discrepar."""
    pages = [PageSpec('cover'), PageSpec('blank')] if cover else []
    pages += [PageSpec('title'), PageSpec('blank')]
    if dedication:                               # una página sola, a la derecha
        pages += [PageSpec('dedication'), PageSpec('blank')]
    n_toc = _toc_pages(len(chapters), toc, toc_lines)
    for part in range(n_toc):
        pages.append(PageSpec('toc', part=part))
    starts = []
    for i, (_, n) in enumerate(chapters):
        if (len(pages) + 1) % 2 == 0:       # la próxima página sería par (izquierda)
            pages.append(PageSpec('blank'))
        starts.append(len(pages) + 1)
        for part in range(max(1, n)):
            pages.append(PageSpec('chapter', chapter=i, part=part))
    if reference:
        pages.append(PageSpec('reference'))      # una página al final: cuenta como contenido
    return pages, starts, n_toc


def content_page_count(chapters, toc=True, toc_lines=TOC_LINES, cover=False,
                       reference=False, dedication=False):
    return len(_content(chapters, toc, toc_lines, cover, reference, dedication)[0])


def plan_book(title, chapters, sheets=4, toc=True, colophon=True, toc_lines=TOC_LINES,
              cover=False, reference=False, dedication=False):
    """chapters: [(título, páginas de texto)]. cover: una portada antes del título.
    reference: una página al final con la referencia al software. → un BookPlan."""
    pages, starts, n_toc = _content(chapters, toc, toc_lines, cover, reference, dedication)
    entries = [(name, starts[i]) for i, (name, _) in enumerate(chapters)]
    if n_toc:
        for p in pages:
            if p.kind == 'toc':
                p.entries = entries[p.part * toc_lines:(p.part + 1) * toc_lines]
    content = len(pages)
    padded, _, blank = imposition.pad_to_signatures(content, sheets)
    for k in range(blank):
        if colophon:
            pages.append(PageSpec('colophon' if k == 0 else 'notes'))
        else:
            pages.append(PageSpec('blank'))
    for n, p in enumerate(pages, 1):
        p.number = n
    return BookPlan(pages, entries, content, blank, sheets, title)
