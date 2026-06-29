"""Paginated F4 reading engine: dot-model paragraphs, real page layout, paging."""
import pytest

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QFont

import reading_page as rp


@pytest.fixture(scope='module')
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_mm_to_pt():
    assert rp.mm_to_pt(25.4) == pytest.approx(72.0)
    # A5 height 210mm
    assert rp.A5_PT[1] == pytest.approx(rp.mm_to_pt(210))


class TestLinesToParagraphs:

    def test_consecutive_lines_join(self):
        assert rp.lines_to_paragraphs(['a', 'b', '.', 'c']) == ['a b', 'c']

    def test_leading_and_double_dots(self):
        assert rp.lines_to_paragraphs(['.', 'a', '.', '.', 'b']) == ['a', 'b']

    def test_o_marker_and_blanks_ignored(self):
        assert rp.lines_to_paragraphs(['ø', 'a', '', 'b']) == ['a b']

    def test_empty(self):
        assert rp.lines_to_paragraphs([]) == []
        assert rp.lines_to_paragraphs(['.', '.']) == []


class TestBuildDocument:

    def test_para_blocks_count_matches_paragraphs(self, qapp):
        sections = [('Chap', ['p1', '.', 'p2', '.', 'p3'])]
        doc, para_blocks, layout = rp.build_reading_document(sections, QFont('Consolas', 11))
        assert len(para_blocks) == 3

    def test_long_document_spans_multiple_pages(self, qapp):
        lines = []
        for i in range(120):
            lines += [f'Paragraph number {i} with several words to take up space.', '.']
        doc, para_blocks, layout = rp.build_reading_document([('Long', lines)], QFont('Consolas', 11))
        offsets = rp.compute_page_offsets(doc, layout.block_h, layout.title_blocks)
        assert len(offsets) > 1
        # last paragraph sits below the first page break → later page
        assert rp.block_top(doc, para_blocks[-1]) >= offsets[1]

    def test_chapters_page_break(self, qapp):
        secs = [('One', ['a']), ('Two', ['b'])]
        doc, para_blocks, layout = rp.build_reading_document(secs, QFont('Consolas', 11))
        assert len(layout.title_blocks) == 2
        offsets = rp.compute_page_offsets(doc, layout.block_h, layout.title_blocks)
        assert len(offsets) >= 2                       # 2nd chapter forces a page
        assert rp.block_top(doc, para_blocks[1]) >= offsets[1]

    def test_page_windows_tile_without_overlap(self, qapp):
        # the visible window of each page must meet the next page's top exactly,
        # so no line is shown on two pages (the duplication bug)
        lines = []
        for i in range(200):
            lines += [f'Paragraph {i} with several words to consume page space here.', '.']
        doc, para_blocks, layout = rp.build_reading_document([('Long', lines)], QFont('Consolas', 11))
        v = rp.ReadingPageView()
        v.resize(800, 600)
        v.set_document(doc, para_blocks, layout)
        offsets = v._offsets
        windows = [(offsets[p], offsets[p] + v.page_clip_height(p))
                   for p in range(len(offsets))]
        for p in range(len(offsets) - 1):
            assert abs(windows[p][1] - offsets[p + 1]) < 1.0      # tiles exactly
        block = doc.begin()
        while block.isValid():
            bl = block.layout()
            y0 = bl.position().y()
            for i in range(bl.lineCount()):
                ln = bl.lineAt(i)
                mid = y0 + ln.y() + ln.height() / 2
                hits = sum(1 for (a, b) in windows if a - 0.5 <= mid < b + 0.5)
                assert hits == 1            # each line on exactly one page
            block = block.next()

    def test_no_line_split_across_pages(self, qapp):
        lines = []
        for i in range(200):
            lines += [f'Paragraph {i} with several words to consume page space here.', '.']
        doc, para_blocks, layout = rp.build_reading_document([('Long', lines)], QFont('Consolas', 11))
        offsets = rp.compute_page_offsets(doc, layout.block_h, layout.title_blocks)
        # every line must fit entirely inside exactly one page window
        block = doc.begin()
        while block.isValid():
            bl = block.layout()
            y0 = bl.position().y()
            for i in range(bl.lineCount()):
                ln = bl.lineAt(i)
                top, bottom = y0 + ln.y(), y0 + ln.y() + ln.height()
                page_top = max(o for o in offsets if o <= top + 0.5)
                assert bottom - page_top <= layout.block_h + 1.0
            block = block.next()


class TestHyphenation:

    def test_guess_lang_spanish(self):
        assert rp.guess_lang('el sistema entero de la nada que es') == 'es_ES'

    def test_guess_lang_english(self):
        assert rp.guess_lang('the void and the boundaries of it for you') == 'en_US'

    def test_guess_lang_diacritics_force_spanish(self):
        assert rp.guess_lang('jamás será suficiente') == 'es_ES'

    def test_guess_lang_none_without_signal(self):
        assert rp.guess_lang('xyzzy qqqq zzzz') is None

    def test_disabled_returns_unchanged(self):
        assert rp.hyphenate_text('infinito embodyment', '') == 'infinito embodyment'

    def test_auto_inserts_soft_hyphens(self):
        pytest.importorskip('pyphen')
        out = rp.hyphenate_text('la sinceridad no se lee jamás', 'auto')
        assert '­' in out  # soft hyphen present → words can break

    def test_auto_no_signal_leaves_text(self):
        pytest.importorskip('pyphen')
        # no detectable language → no hyphenation, text intact
        assert rp.hyphenate_text('xyzzy qqqq', 'auto') == 'xyzzy qqqq'


class TestReadingPageViewNav:

    def _view(self, qapp, n_paras=120):
        lines = []
        for i in range(n_paras):
            lines += [f'Paragraph {i} with enough words here to fill space nicely.', '.']
        doc, para_blocks, layout = rp.build_reading_document([('T', lines)], QFont('Consolas', 11))
        v = rp.ReadingPageView()
        v.resize(800, 600)
        v.set_document(doc, para_blocks, layout)
        return v

    def test_next_prev_clamped(self, qapp):
        v = self._view(qapp)
        assert v.page == 0
        v.prev_page()
        assert v.page == 0  # clamped at start
        last = v.page_count - 1
        for _ in range(v.page_count + 5):
            v.next_page()
        assert v.page == last  # clamped at end

    def test_first_last(self, qapp):
        v = self._view(qapp)
        v.last_page()
        assert v.page == v.page_count - 1
        v.first_page()
        assert v.page == 0

    def test_goto_paragraph_lands_on_its_page(self, qapp):
        v = self._view(qapp)
        # jumping to the final paragraph should move off page 0
        v.goto_paragraph(10_000)  # clamps to last paragraph
        assert v.page > 0
        v.goto_paragraph(0)
        assert v.page == 0
