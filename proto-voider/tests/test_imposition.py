"""Imposición: acomodar las páginas de un libro en hojas para imprimir, doblar por
la mitad, apilar en cuadernillos y coser.

Hojas A4 apaisadas con 2 páginas A5 por cara. Un cuadernillo de N hojas dobladas
tiene 4N páginas. Las páginas se numeran desde 1; las que pasan del total del
libro son páginas en blanco (None) que completan el último cuadernillo.
"""
import itertools

import pytest

import imposition as imp


# ── el orden de páginas en un cuadernillo ────────────────────────────────────

def test_a_signature_of_two_sheets_is_the_classic_8_page_imposition():
    sheets = imp.impose(8, 2)
    assert [(s.front, s.back) for s in sheets] == [
        ((8, 1), (2, 7)),     # hoja de afuera
        ((6, 3), (4, 5)),     # hoja de adentro
    ]


def test_a_signature_of_four_sheets_is_the_16_page_imposition():
    sheets = imp.impose(16, 4)
    assert [(s.front, s.back) for s in sheets] == [
        ((16, 1), (2, 15)),
        ((14, 3), (4, 13)),
        ((12, 5), (6, 11)),
        ((10, 7), (8, 9)),
    ]


def test_one_sheet_is_a_4_page_booklet():
    s = imp.impose(4, 1)
    assert [(x.front, x.back) for x in s] == [((4, 1), (2, 3))]


def test_a_second_signature_continues_the_page_numbers():
    sheets = imp.impose(32, 4)
    assert len(sheets) == 8
    assert sheets[4].signature == 2 and sheets[4].sheet == 1
    assert (sheets[4].front, sheets[4].back) == ((32, 17), (18, 31))


@pytest.mark.parametrize('total,sheets', [(8, 2), (16, 4), (32, 4), (40, 5),
                                           (24, 3), (96, 6), (150, 3), (150, 4),
                                           (7, 2), (1, 4), (161, 4)])
def test_every_page_of_the_book_is_printed_exactly_once(total, sheets):
    seen = []
    for s in imp.impose(total, sheets):
        seen += [p for p in (*s.front, *s.back) if p is not None]
    assert sorted(seen) == list(range(1, total + 1))


@pytest.mark.parametrize('total,sheets', [(16, 4), (40, 5), (24, 3), (150, 3)])
def test_each_folded_leaf_has_consecutive_pages(total, sheets):
    """Una hoja doblada: la derecha del frente y la izquierda del dorso son las dos
    caras de la misma hoja, y tienen que ser páginas seguidas (impar, par)."""
    for s in imp.impose(total, sheets):
        right_front, left_back = s.front[1], s.back[0]
        assert right_front % 2 == 1 and left_back == right_front + 1


@pytest.mark.parametrize('sheets', [1, 2, 3, 4, 5, 6])
def test_the_outer_sheet_holds_the_first_and_last_page_of_its_signature(sheets):
    size = 4 * sheets
    first = imp.impose(size * 2, sheets)[0]
    assert first.front == (size, 1)


@pytest.mark.parametrize('sheets', [2, 3, 4, 5])
def test_sheets_nest_from_the_outside_in(sheets):
    """Cada hoja de más adentro tiene páginas más cerca del medio del cuadernillo."""
    size = 4 * sheets
    ss = imp.impose(size, sheets)
    lefts = [s.front[0] for s in ss]
    assert lefts == sorted(lefts, reverse=True)
    rights = [s.front[1] for s in ss]
    assert rights == sorted(rights)


def test_pages_past_the_end_of_the_book_are_blank():
    sheets = imp.impose(10, 4)               # se completa a 16
    seen = [p for s in sheets for p in (*s.front, *s.back)]
    assert len(seen) == 16
    assert sorted(p for p in seen if p is not None) == list(range(1, 11))
    assert seen.count(None) == 6


def test_a_book_with_no_pages_has_no_sheets():
    assert imp.impose(0, 4) == []


def test_zero_or_negative_sheets_per_signature_is_an_error():
    with pytest.raises(ValueError):
        imp.impose(10, 0)
    with pytest.raises(ValueError):
        imp.pad_to_signatures(10, -1)


# ── cuántas páginas en blanco sobran ─────────────────────────────────────────

@pytest.mark.parametrize('sheets,padded,signatures,blank', [
    (3, 156, 13, 6),
    (4, 160, 10, 10),
    (5, 160, 8, 10),
    (6, 168, 7, 18),
])
def test_the_blank_pages_for_a_150_page_book(sheets, padded, signatures, blank):
    assert imp.pad_to_signatures(150, sheets) == (padded, signatures, blank)


def test_a_book_that_fits_exactly_has_no_blank_pages():
    assert imp.pad_to_signatures(160, 4) == (160, 10, 0)


def test_the_table_has_one_row_per_option_with_the_four_numbers():
    rows = imp.signature_table(150, options=(3, 4, 5, 6))
    assert [(r.sheets, r.pages_per_signature, r.signatures, r.blank) for r in rows] == [
        (3, 12, 13, 6), (4, 16, 10, 10), (5, 20, 8, 10), (6, 24, 7, 18)]


def test_the_table_marks_the_option_with_fewest_blank_pages():
    rows = imp.signature_table(150, options=(3, 4, 5, 6))
    assert [r.sheets for r in rows if r.best] == [3]


def test_a_tie_prefers_the_size_closest_to_four_sheets():
    rows = imp.signature_table(160, options=(3, 4, 5, 6))
    assert imp.best_sheets(160, options=(3, 4, 5, 6)) == 4
    assert [r.sheets for r in rows if r.best] == [4]
    # 4 y 5 dan cero en blanco: se queda el más cerca de 4


def test_the_default_table_covers_two_to_eight_sheets():
    assert [r.sheets for r in imp.signature_table(100)] == [2, 3, 4, 5, 6, 7, 8]


# ── páginas físicas del PDF ──────────────────────────────────────────────────

def test_duplex_alternates_front_and_back_of_each_sheet():
    sheets = imp.impose(16, 4)
    pages = imp.duplex_pages(sheets)
    assert len(pages) == 8
    assert pages[0].pages == (16, 1) and pages[1].pages == (2, 15)
    assert pages[2].pages == (14, 3) and pages[3].pages == (4, 13)


def test_manual_prints_all_fronts_then_all_backs_in_reverse():
    sheets = imp.impose(16, 4)
    fronts, backs = imp.manual_passes(sheets)
    assert [p.pages for p in fronts] == [(16, 1), (14, 3), (12, 5), (10, 7)]
    assert [p.pages for p in backs] == [(8, 9), (6, 11), (4, 13), (2, 15)]


def test_every_physical_page_carries_a_collation_label():
    sheets = imp.impose(32, 4)
    pages = imp.duplex_pages(sheets)
    assert pages[0].label == 'C1/2 · H1/4'
    assert pages[-1].label == 'C2/2 · H4/4'
    assert pages[0].label == pages[1].label           # frente y dorso, la misma hoja


def test_the_test_sheet_is_one_labelled_sheet_to_check_the_flip():
    t = imp.test_sheet()
    assert len(t) == 2
    assert t[0].texts == ('1 · frente · izquierda', '2 · frente · derecha')
    assert t[1].texts == ('3 · dorso · izquierda', '4 · dorso · derecha')
