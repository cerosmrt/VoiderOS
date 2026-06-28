"""F4 paginated reading view — a true book page, on screen and in print.

Builds a QTextDocument laid out to a real text block and renders it ONE PAGE AT
A TIME on a black background (no scrollbar). The same QTextDocument is what gets
printed, so what you read is what binds (WYSIWYG).

Margins are handled with a "text-block" model: the document's page size is the
TEXT BLOCK (page minus margins), so pagination is driven by the block height,
and the renderer positions that block on the full page with asymmetric book
margins (smaller top, larger bottom, inner gutter) — which QTextDocument's own
uniform documentMargin can't express.

Content is the dot-model: consecutive non-'.' lines join into a paragraph; a '.'
line ends the paragraph. A "section" is (title, lines) — one chapter; multiple
sections page-break between chapters.
"""
from PyQt6.QtWidgets import QWidget
from PyQt6.QtGui import (
    QTextDocument, QTextCursor, QTextBlockFormat, QTextCharFormat, QTextFormat,
    QFont, QColor, QPainter, QPalette, QAbstractTextDocumentLayout,
)
from PyQt6.QtCore import Qt, QSizeF, QRectF


def mm_to_pt(mm):
    """Millimetres → PostScript points (1 pt = 1/72 inch)."""
    return mm * 72.0 / 25.4


# Common trim sizes, in points.
A5_PT = (mm_to_pt(148), mm_to_pt(210))

# Book margins in mm: (top, bottom, inner, outer). Equal top/bottom.
BOOK_MARGINS_MM = (21.0, 21.0, 20.0, 20.0)


class PageLayout:
    """Page + margin geometry, all in points. block_* is the live text area."""

    def __init__(self, page_pt=A5_PT, margins_mm=BOOK_MARGINS_MM):
        self.page_w, self.page_h = page_pt
        self.m_top, self.m_bottom, self.m_inner, self.m_outer = (
            mm_to_pt(m) for m in margins_mm)
        self.block_w = self.page_w - self.m_inner - self.m_outer
        self.block_h = self.page_h - self.m_top - self.m_bottom


_HYPHEN_DICTS = {}
_SOFT_HYPHEN = '­'

# Cheap per-paragraph language guess for the bilingual book — no single default.
_ES_HINTS = set("el la de que y en los las un una por con no se su lo le del al "
                "es son como para más pero sus me mi te lo ya muy".split())
_EN_HINTS = set("the of and to in is that it for you with on as are be this his "
                "was from they not but have had your".split())


def guess_lang(text):
    """Best-effort 'es_ES' / 'en_US' / None for a paragraph, by function words and
    Spanish diacritics. None when there's no signal (then we don't hyphenate)."""
    words = [w.strip(".,;:!?¿¡\"'()[]—–-").lower() for w in text.split()]
    es = sum(1 for w in words if w in _ES_HINTS)
    en = sum(1 for w in words if w in _EN_HINTS)
    if any(c in text for c in 'áéíóúñü¿¡'):
        es += 2
    if es == 0 and en == 0:
        return None
    return 'es_ES' if es >= en else 'en_US'


def hyphenate_text(text, lang):
    """Insert invisible soft-hyphens so justified lines can break words and keep
    tight spacing. Needs Pyphen; missing Pyphen or a falsy lang returns text
    unchanged. lang='auto' detects the paragraph's language (bilingual-safe)."""
    if not lang or not text:
        return text
    if lang == 'auto':
        lang = guess_lang(text)
        if not lang:
            return text
    try:
        import pyphen
    except ImportError:
        return text
    dic = _HYPHEN_DICTS.get(lang)
    if dic is None:
        try:
            dic = pyphen.Pyphen(lang=lang)
        except Exception:
            return text
        _HYPHEN_DICTS[lang] = dic
    out = []
    for tok in text.split(' '):
        out.append(dic.inserted(tok, hyphen=_SOFT_HYPHEN) if len(tok) > 4 else tok)
    return ' '.join(out)


def lines_to_paragraphs(lines):
    """Dot-model → list of paragraph strings (consecutive lines joined, '.' breaks)."""
    paras, cur = [], []
    for raw in lines:
        s = raw.strip()
        if s == '.':
            if cur:
                paras.append(' '.join(cur)); cur = []
        elif s and s != 'ø':
            cur.append(s)
    if cur:
        paras.append(' '.join(cur))
    return paras


def build_reading_document(sections, font, page_pt=A5_PT,
                           margins_mm=BOOK_MARGINS_MM, line_height_pct=132,
                           justify=True, indent=True, hyphenate_lang=None):
    """Build the book QTextDocument.

    sections: list of (title, lines). Returns (doc, para_blocks, layout) where
    para_blocks[i] is the block number of the i-th body paragraph across all
    sections (used to jump to the page you're currently reading).
    """
    layout = PageLayout(page_pt, margins_mm)
    doc = QTextDocument()
    doc.setDefaultFont(font)
    doc.setDocumentMargin(0.0)
    doc.setPageSize(QSizeF(layout.block_w, layout.block_h))
    doc.setUndoRedoEnabled(False)

    cursor = QTextCursor(doc)
    para_blocks = []

    indent_pt = mm_to_pt(5.0) if indent else 0.0
    align = Qt.AlignmentFlag.AlignJustify if justify else Qt.AlignmentFlag.AlignLeft
    prop = QTextBlockFormat.LineHeightTypes.ProportionalHeight.value

    body_char = QTextCharFormat()
    body_char.setFont(font)

    title_font = QFont(font)
    title_font.setPointSizeF(max(font.pointSizeF(), 1.0) * 1.5)
    title_char = QTextCharFormat()
    title_char.setFont(title_font)

    first_block = True

    def open_block(fmt):
        nonlocal first_block
        # Reuse the document's initial empty block for the very first insertion.
        if first_block:
            cursor.setBlockFormat(fmt)
            first_block = False
        else:
            cursor.insertBlock(fmt)

    for si, (title, lines) in enumerate(sections):
        tf = QTextBlockFormat()
        tf.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        tf.setTopMargin(mm_to_pt(24.0))   # chapter-opening sink
        tf.setBottomMargin(mm_to_pt(12.0))
        if si > 0:
            tf.setPageBreakPolicy(QTextFormat.PageBreakFlag.PageBreak_AlwaysBefore)
        open_block(tf)
        cursor.setCharFormat(title_char)
        cursor.insertText(title or '')

        for pi, para in enumerate(lines_to_paragraphs(lines)):
            pf = QTextBlockFormat()
            pf.setAlignment(align)
            # First paragraph after a heading is flush-left (book convention).
            pf.setTextIndent(0.0 if pi == 0 else indent_pt)
            pf.setLineHeight(line_height_pct, prop)
            open_block(pf)
            cursor.setCharFormat(body_char)
            cursor.insertText(hyphenate_text(para, hyphenate_lang))
            para_blocks.append(cursor.block().blockNumber())

    return doc, para_blocks, layout


def page_of_block(doc, block_number, block_h):
    """Which 0-based page a given block falls on (block_h = text-block height)."""
    block = doc.findBlockByNumber(block_number)
    if not block.isValid() or block_h <= 0:
        return 0
    rect = doc.documentLayout().blockBoundingRect(block)
    return max(0, int(rect.top() // block_h))


class ReadingPageView(QWidget):
    """Renders one page of a reading QTextDocument, centered on black."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._doc = None
        self._para_blocks = []
        self._layout = None
        self._page = 0
        self._page_count = 1
        self._paper = QColor('#ffffff')
        self._ink = QColor('#111111')
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    # ── content ───────────────────────────────────────────────────────────────

    def set_document(self, doc, para_blocks, layout):
        self._doc = doc
        self._para_blocks = list(para_blocks)
        self._layout = layout
        self._page_count = max(1, doc.pageCount())
        self._page = 0
        self.update()

    def goto_paragraph(self, para_ordinal):
        """Jump to the page holding the given body paragraph (by ordinal)."""
        if not self._doc or not self._para_blocks or self._layout is None:
            return
        k = max(0, min(para_ordinal, len(self._para_blocks) - 1))
        p = page_of_block(self._doc, self._para_blocks[k], self._layout.block_h)
        self._page = max(0, min(p, self._page_count - 1))
        self.update()

    # ── navigation ──────────────────────────────────────────────────────────--

    @property
    def page(self):
        return self._page

    @property
    def page_count(self):
        return self._page_count

    def next_page(self):
        self._page = min(self._page + 1, self._page_count - 1)
        self.update()

    def prev_page(self):
        self._page = max(self._page - 1, 0)
        self.update()

    def first_page(self):
        self._page = 0
        self.update()

    def last_page(self):
        self._page = self._page_count - 1
        self.update()

    # ── paint ───────────────────────────────────────────────────────────────--

    def paintEvent(self, event):
        painter = QPainter(self)
        if not painter.isActive():
            return
        painter.fillRect(self.rect(), QColor('black'))
        L = self._layout
        if self._doc is None or L is None:
            painter.end()
            return
        W, H = self.width(), self.height()
        if W <= 0 or H <= 0 or L.page_w <= 0 or L.page_h <= 0:
            painter.end()
            return
        scale = min(W / L.page_w, H / L.page_h) * 0.94
        draw_w, draw_h = L.page_w * scale, L.page_h * scale
        ox = (W - draw_w) / 2.0
        oy = (H - draw_h) / 2.0

        # The paper is the full page; the text block sits inset by the margins.
        painter.fillRect(QRectF(ox, oy, draw_w, draw_h), self._paper)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        painter.save()
        painter.translate(ox, oy)
        painter.scale(scale, scale)
        painter.translate(L.m_inner, L.m_top)
        painter.translate(0, -self._page * L.block_h)
        ctx = QAbstractTextDocumentLayout.PaintContext()
        ctx.palette.setColor(QPalette.ColorRole.Text, self._ink)
        ctx.clip = QRectF(0, self._page * L.block_h, L.block_w, L.block_h)
        self._doc.documentLayout().draw(painter, ctx)
        painter.restore()
        painter.end()
