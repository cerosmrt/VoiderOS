"""El plan de páginas de un libro: qué va en cada página, en orden.

  1: página de título (a la derecha)      2: en blanco (atrás del título)
  3: índice (una o varias páginas)        y cada capítulo EMPIEZA A LA DERECHA
  (página impar), con una página en blanco antes si hace falta.
  Al final, lo que falta para completar el último cuadernillo: el colofón en la
  primera página sobrante y las demás para notas. Si no sobra ninguna, no hay colofón.

Es lógica pura: recibe cuántas páginas de texto tiene cada capítulo y devuelve
la secuencia. El dibujo viene aparte.
"""
import pytest

import book_plan as bp


CHAPS = [('Uno', 3), ('Dos', 2), ('Tres', 4)]


def _kinds(plan):
    return [p.kind for p in plan.pages]


def test_the_title_is_page_one_and_its_back_is_blank():
    plan = bp.plan_book('Mitad Humana', CHAPS, sheets=4)
    assert plan.pages[0].kind == 'title' and plan.pages[0].number == 1
    assert plan.pages[1].kind == 'blank' and plan.pages[1].number == 2


def test_a_worked_example_counted_by_hand():
    plan = bp.plan_book('M', CHAPS, sheets=4)
    assert _kinds(plan)[:14] == [
        'title', 'blank',                  # 1, 2
        'toc',                             # 3
        'blank',                           # 4  (para que el cap. 1 caiga a la derecha)
        'chapter', 'chapter', 'chapter',   # 5-7   Uno
        'blank',                           # 8
        'chapter', 'chapter',              # 9-10  Dos
        'chapter', 'chapter', 'chapter', 'chapter',   # 11-14 Tres
    ]


def test_the_index_lists_each_chapter_with_its_first_page():
    plan = bp.plan_book('M', CHAPS, sheets=4)
    assert plan.toc == [('Uno', 5), ('Dos', 9), ('Tres', 11)]


def test_every_chapter_starts_on_a_right_hand_page():
    plan = bp.plan_book('M', [('a', 1), ('b', 2), ('c', 5), ('d', 1), ('e', 4)], sheets=4)
    assert all(page % 2 == 1 for _, page in plan.toc)


def test_chapter_pages_know_which_chapter_and_which_part():
    plan = bp.plan_book('M', CHAPS, sheets=4)
    uno = [p for p in plan.pages if p.kind == 'chapter' and p.chapter == 0]
    assert [p.part for p in uno] == [0, 1, 2]
    assert [p.number for p in uno] == [5, 6, 7]


def test_pages_are_numbered_from_the_title_page():
    plan = bp.plan_book('M', CHAPS, sheets=4)
    assert [p.number for p in plan.pages] == list(range(1, len(plan.pages) + 1))


def test_the_book_is_padded_to_whole_signatures():
    plan = bp.plan_book('M', CHAPS, sheets=4)
    assert plan.content_pages == 14
    assert len(plan.pages) == 16 and plan.blank == 2


def test_the_first_spare_page_is_the_colophon_and_the_rest_are_notes():
    plan = bp.plan_book('M', CHAPS, sheets=2)       # 8 por cuadernillo: 14 → 16
    assert _kinds(plan)[14:] == ['colophon', 'notes']
    plan3 = bp.plan_book('M', CHAPS, sheets=1)      # 4 por cuadernillo: 14 → 16
    assert plan3.blank == 2


def test_with_no_spare_pages_there_is_no_colophon():
    # 14 páginas y 14 + 2 = 16... buscamos un libro que cierre justo
    plan = bp.plan_book('M', [('Uno', 3), ('Dos', 2), ('Tres', 6)], sheets=4)
    assert plan.content_pages == 16 and plan.blank == 0
    assert 'colophon' not in _kinds(plan) and 'notes' not in _kinds(plan)


def test_without_a_colophon_the_spare_pages_are_just_blank():
    plan = bp.plan_book('M', CHAPS, sheets=4, colophon=False)
    assert _kinds(plan)[14:] == ['blank', 'blank']


def test_notes_fill_every_spare_page_after_the_colophon():
    plan = bp.plan_book('M', [('Uno', 1)], sheets=4)
    kinds = _kinds(plan)
    assert kinds.count('colophon') == 1
    assert kinds.index('colophon') == plan.content_pages
    assert all(k == 'notes' for k in kinds[plan.content_pages + 1:])


def test_without_an_index_the_first_chapter_follows_the_blank_back_of_the_title():
    plan = bp.plan_book('M', CHAPS, sheets=4, toc=False)
    assert _kinds(plan)[:4] == ['title', 'blank', 'chapter', 'chapter']
    assert plan.toc == [('Uno', 3), ('Dos', 7), ('Tres', 9)]


def test_a_long_index_takes_several_pages():
    chaps = [(f'C{i}', 1) for i in range(50)]
    plan = bp.plan_book('M', chaps, sheets=4, toc_lines=22)
    kinds = _kinds(plan)
    assert kinds[2:5] == ['toc', 'toc', 'toc']          # 22 + 22 + 6
    assert kinds[5] == 'blank'                           # el 1 cae en la 7
    assert plan.toc[0] == ('C0', 7)


def test_toc_pages_know_which_entries_they_hold():
    chaps = [(f'C{i}', 1) for i in range(30)]
    plan = bp.plan_book('M', chaps, sheets=4, toc_lines=22)
    tocs = [p for p in plan.pages if p.kind == 'toc']
    assert [(p.part, len(p.entries)) for p in tocs] == [(0, 22), (1, 8)]


def test_an_empty_chapter_still_takes_a_page_for_its_title():
    plan = bp.plan_book('M', [('Vacío', 0)], sheets=4)
    assert plan.toc == [('Vacío', 5)] or plan.toc[0][1] % 2 == 1
    assert sum(1 for p in plan.pages if p.kind == 'chapter') == 1


def test_a_book_without_chapters_is_only_a_title_and_padding():
    plan = bp.plan_book('M', [], sheets=4)
    assert plan.pages[0].kind == 'title'
    assert len(plan.pages) % 16 == 0 and plan.toc == []


def test_the_content_length_does_not_depend_on_the_signature_size():
    """Por eso la tabla de páginas en blanco se puede calcular antes de elegir."""
    counts = {bp.plan_book('M', CHAPS, sheets=s).content_pages for s in (1, 2, 3, 4, 5, 6)}
    assert counts == {14}


def test_content_page_count_matches_the_plan():
    assert bp.content_page_count(CHAPS) == bp.plan_book('M', CHAPS, sheets=4).content_pages
    assert bp.content_page_count(CHAPS, toc=False) == bp.plan_book(
        'M', CHAPS, sheets=4, toc=False).content_pages


def test_a_chapter_ending_on_a_left_page_leaves_a_blank_before_the_next():
    plan = bp.plan_book('M', [('a', 2), ('b', 1)], sheets=4)
    # a: 5-6, página 7 en blanco... no: b arranca en la 7 (impar)
    assert plan.toc == [('a', 5), ('b', 7)]
    plan2 = bp.plan_book('M', [('a', 3), ('b', 1)], sheets=4)
    assert plan2.toc == [('a', 5), ('b', 9)]       # a: 5-7, blanco 8, b en 9


# ── portada y referencia al software ─────────────────────────────────────────

def test_with_a_cover_the_book_opens_cover_blank_title_blank():
    plan = bp.plan_book('M', CHAPS, sheets=4, cover=True)
    assert _kinds(plan)[:5] == ['cover', 'blank', 'title', 'blank', 'toc']
    assert [p.number for p in plan.pages[:3]] == [1, 2, 3]


def test_the_cover_shifts_every_chapter_two_pages_and_they_still_start_on_the_right():
    sin = bp.plan_book('M', CHAPS, sheets=4)
    con = bp.plan_book('M', CHAPS, sheets=4, cover=True)
    assert [p for _, p in con.toc] == [p + 2 for _, p in sin.toc]
    assert all(p % 2 == 1 for _, p in con.toc)


def test_without_a_cover_nothing_changes():
    assert _kinds(bp.plan_book('M', CHAPS, sheets=4)) == _kinds(
        bp.plan_book('M', CHAPS, sheets=4, cover=False))


def test_the_reference_page_follows_the_last_chapter():
    plan = bp.plan_book('M', CHAPS, sheets=4, reference=True)
    kinds = _kinds(plan)
    assert kinds[plan.content_pages - 1] == 'reference'
    assert kinds[plan.content_pages - 2] == 'chapter'


def test_the_reference_page_counts_as_content_not_as_padding():
    sin = bp.plan_book('M', CHAPS, sheets=4)
    con = bp.plan_book('M', CHAPS, sheets=4, reference=True)
    assert con.content_pages == sin.content_pages + 1


def test_the_colophon_goes_after_the_reference():
    plan = bp.plan_book('M', CHAPS, sheets=4, reference=True)
    kinds = _kinds(plan)
    assert plan.blank >= 1
    assert kinds[plan.content_pages] == 'colophon'


def test_content_page_count_knows_about_cover_and_reference():
    for cover in (False, True):
        for ref in (False, True):
            assert bp.content_page_count(CHAPS, cover=cover, reference=ref) == bp.plan_book(
                'M', CHAPS, sheets=4, cover=cover, reference=ref).content_pages


def test_a_book_without_chapters_with_cover_and_reference_still_works():
    plan = bp.plan_book('M', [], sheets=4, cover=True, reference=True)
    assert _kinds(plan)[:4] == ['cover', 'blank', 'title', 'blank']
    assert 'reference' in _kinds(plan) and len(plan.pages) % 16 == 0


# ── la dedicatoria: una página sola, a la derecha, después de la portada ─────

def test_a_dedication_comes_after_the_title_page_on_its_own_right_hand_page():
    plan = bp.plan_book('M', CHAPS, sheets=4, dedication=True)
    assert _kinds(plan)[:5] == ['title', 'blank', 'dedication', 'blank', 'toc']
    assert plan.pages[2].number == 3                       # impar: a la derecha


def test_with_a_cover_the_dedication_is_still_on_a_right_hand_page():
    plan = bp.plan_book('M', CHAPS, sheets=4, cover=True, dedication=True)
    assert _kinds(plan)[:7] == ['cover', 'blank', 'title', 'blank', 'dedication', 'blank', 'toc']
    assert plan.pages[4].number % 2 == 1


def test_a_dedication_pushes_the_chapters_two_pages_and_they_still_start_on_the_right():
    sin = bp.plan_book('M', CHAPS, sheets=4)
    con = bp.plan_book('M', CHAPS, sheets=4, dedication=True)
    assert [p for _, p in con.toc] == [p + 2 for _, p in sin.toc]
    assert all(p % 2 == 1 for _, p in con.toc)


def test_without_a_dedication_nothing_changes():
    assert _kinds(bp.plan_book('M', CHAPS, sheets=4)) == _kinds(
        bp.plan_book('M', CHAPS, sheets=4, dedication=False))


def test_content_page_count_knows_about_the_dedication():
    for d in (False, True):
        assert bp.content_page_count(CHAPS, dedication=d) == bp.plan_book(
            'M', CHAPS, sheets=4, dedication=d).content_pages
