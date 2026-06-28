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
        assert doc.pageCount() >= 1

    def test_long_document_spans_multiple_pages(self, qapp):
        # Many paragraphs must overflow a single A5 page.
        lines = []
        for i in range(120):
            lines += [f'Paragraph number {i} with several words to take up space.', '.']
        doc, para_blocks, layout = rp.build_reading_document([('Long', lines)], QFont('Consolas', 11))
        assert doc.pageCount() > 1
        # the last paragraph must live on a later page than the first
        first_pg = rp.page_of_block(doc, para_blocks[0], layout.block_h)
        last_pg = rp.page_of_block(doc, para_blocks[-1], layout.block_h)
        assert last_pg > first_pg

    def test_chapters_page_break(self, qapp):
        # two chapters → second chapter starts on a new page
        secs = [('One', ['a']), ('Two', ['b'])]
        doc, para_blocks, layout = rp.build_reading_document(secs, QFont('Consolas', 11))
        assert doc.pageCount() >= 2
        assert rp.page_of_block(doc, para_blocks[1], layout.block_h) >= 1


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
