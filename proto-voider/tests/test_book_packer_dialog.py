"""El cuadro del empaquetador (F8): armar un libro, ver cuántas páginas en blanco
sobran según las hojas por cuadernillo, y exportar los PDF. Los tests le pasan un
renderizador de mentira: lo que se prueba es el cuadro, no el dibujo.
"""
import pytest

pytest.importorskip("PyQt6")
from PyQt6.QtWidgets import QApplication

import imposition
from book_packer_dialog import BookPackerDialog


@pytest.fixture(scope='module')
def qapp():
    yield QApplication.instance() or QApplication([])


class FakeRenderer:
    def __init__(self, content_pages=50):
        self.content_pages = content_pages
        self.sheets = 4

    def set_sheets(self, n):
        self.sheets = n

    def signature_table(self):
        return imposition.signature_table(self.content_pages)

    @property
    def blank(self):
        return imposition.pad_to_signatures(self.content_pages, self.sheets)[2]


def _book(caps=('A.txt', 'B.txt', 'C.txt')):
    return {'id': 'l1', 'titulo': 'Mitad Humana', 'capitulos': list(caps),
            'hojas': 4, 'autor': 'Federico', 'colofon': ''}


def _dlg(qapp, book=None, available=('A.txt', 'B.txt', 'C.txt', 'D.txt', 'E.txt'),
         missing=(), f3=None):
    llamadas = {'export': [], 'factory': 0}

    def factory(b):
        llamadas['factory'] += 1
        return FakeRenderer(), list(missing)

    def exporter(b, kind):
        llamadas['export'].append((kind, list(b['capitulos'])))
        return [f'/tmp/{b["titulo"]} - {kind}.pdf']
    d = BookPackerDialog(None, book or _book(), list(available), factory, exporter,
                         f3_group=f3)
    d.llamadas = llamadas
    return d


def _names(d):
    return [d.chapters.item(i).data(0x0100) for i in range(d.chapters.count())]


# ── lo que muestra ───────────────────────────────────────────────────────────

def test_it_shows_the_book_chapters_in_order(qapp):
    d = _dlg(qapp)
    assert _names(d) == ['A.txt', 'B.txt', 'C.txt']
    assert [d.chapters.item(i).text() for i in range(3)] == ['A', 'B', 'C']


def test_it_shows_title_author_and_sheets(qapp):
    d = _dlg(qapp)
    assert d.title_edit.text() == 'Mitad Humana'
    assert d.author_edit.text() == 'Federico'
    assert d.sheets_spin.value() == 4


def test_a_missing_chapter_is_marked(qapp):
    d = _dlg(qapp, missing=['B.txt'])
    assert d.chapters.item(1).text().startswith('⚠')
    assert not d.chapters.item(0).text().startswith('⚠')


# ── la tabla de páginas en blanco ────────────────────────────────────────────

def test_the_table_has_one_row_per_option_from_two_to_eight_sheets(qapp):
    d = _dlg(qapp)
    assert d.table.rowCount() == 7
    assert [d.table.item(r, 0).text().strip('★ ') for r in range(7)] == [
        '2', '3', '4', '5', '6', '7', '8']


def test_the_table_numbers_come_from_the_real_page_count(qapp):
    d = _dlg(qapp)                                   # 50 páginas de contenido
    fila4 = [r for r in range(7) if d.table.item(r, 0).text().strip('★ ') == '4'][0]
    pad, n, blank = imposition.pad_to_signatures(50, 4)
    assert d.table.item(fila4, 1).text() == '16'
    assert d.table.item(fila4, 2).text() == str(n)
    assert d.table.item(fila4, 3).text() == str(blank)


def test_the_best_row_is_starred(qapp):
    d = _dlg(qapp)
    estrellas = [r for r in range(7) if '★' in d.table.item(r, 0).text()]
    assert len(estrellas) == 1
    best = imposition.best_sheets(50)
    assert d.table.item(estrellas[0], 0).text().strip('★ ') == str(best)


def test_changing_the_sheets_tells_the_renderer_and_shows_the_blanks(qapp):
    d = _dlg(qapp)
    d.sheets_spin.setValue(6)
    assert d.renderer.sheets == 6
    assert str(imposition.pad_to_signatures(50, 6)[2]) in d.summary.text()


def test_changing_the_sheets_does_not_rebuild_the_book(qapp):
    d = _dlg(qapp)
    antes = d.llamadas['factory']
    d.sheets_spin.setValue(5)
    d.sheets_spin.setValue(3)
    assert d.llamadas['factory'] == antes


# ── armar el libro ───────────────────────────────────────────────────────────

def test_chapters_are_added_at_the_end_without_repeats(qapp):
    d = _dlg(qapp)
    d.add_chapters(['D.txt', 'A.txt', 'E.txt'])
    assert _names(d) == ['A.txt', 'B.txt', 'C.txt', 'D.txt', 'E.txt']


def test_adding_rebuilds_the_table(qapp):
    d = _dlg(qapp)
    antes = d.llamadas['factory']
    d.add_chapters(['D.txt'])
    assert d.llamadas['factory'] == antes + 1


def test_the_selected_chapter_is_removed(qapp):
    d = _dlg(qapp)
    d.chapters.setCurrentRow(1)
    d.remove_selected()
    assert _names(d) == ['A.txt', 'C.txt']


def test_chapters_move_up_and_down(qapp):
    d = _dlg(qapp)
    d.chapters.setCurrentRow(1)
    d.move_selected(+1)
    assert _names(d) == ['A.txt', 'C.txt', 'B.txt']
    assert d.chapters.currentRow() == 2
    d.move_selected(+1)                               # ya es el último
    assert _names(d) == ['A.txt', 'C.txt', 'B.txt']
    d.move_selected(-1)
    assert _names(d) == ['A.txt', 'B.txt', 'C.txt']


def test_the_chapters_of_the_f3_book_can_be_added(qapp):
    d = _dlg(qapp, f3=lambda: ['C.txt', 'D.txt', 'E.txt'])
    d.add_from_f3()
    assert _names(d) == ['A.txt', 'B.txt', 'C.txt', 'D.txt', 'E.txt']


def test_without_an_f3_book_the_button_is_off(qapp):
    d = _dlg(qapp, f3=None)
    assert not d.f3_btn.isEnabled()


# ── lo que se guarda ─────────────────────────────────────────────────────────

def test_the_result_reflects_every_edit(qapp):
    d = _dlg(qapp)
    d.title_edit.setText('Otro título')
    d.author_edit.setText('Otro autor')
    d.sheets_spin.setValue(5)
    d.colofon_edit.setPlainText('Hecho en Gualeguay')
    d.chapters.setCurrentRow(0)
    d.move_selected(+1)
    r = d.result_book()
    assert r['titulo'] == 'Otro título' and r['autor'] == 'Otro autor'
    assert r['hojas'] == 5 and r['colofon'] == 'Hecho en Gualeguay'
    assert r['capitulos'] == ['B.txt', 'A.txt', 'C.txt']
    assert r['id'] == 'l1'


def test_the_original_book_is_not_touched_until_you_accept(qapp):
    book = _book()
    d = _dlg(qapp, book=book)
    d.title_edit.setText('Cambiado')
    d.remove_selected()
    assert book['titulo'] == 'Mitad Humana' and len(book['capitulos']) == 3


def test_a_blank_title_keeps_the_old_one(qapp):
    d = _dlg(qapp)
    d.title_edit.setText('   ')
    assert d.result_book()['titulo'] == 'Mitad Humana'


# ── exportar ─────────────────────────────────────────────────────────────────

@pytest.mark.parametrize('button,kind', [('duplex_btn', 'duplex'), ('manual_btn', 'manual'),
                                          ('test_btn', 'test'), ('read_btn', 'read')])
def test_each_export_button_asks_for_its_kind(qapp, button, kind):
    d = _dlg(qapp)
    getattr(d, button).click()
    assert d.llamadas['export'] == [(kind, ['A.txt', 'B.txt', 'C.txt'])]


def test_an_export_uses_the_current_edits_not_the_saved_book(qapp):
    d = _dlg(qapp)
    d.chapters.setCurrentRow(2)
    d.remove_selected()
    d.duplex_btn.click()
    assert d.llamadas['export'][-1][1] == ['A.txt', 'B.txt']


def test_after_an_export_the_status_says_where_it_went(qapp):
    d = _dlg(qapp)
    d.duplex_btn.click()
    assert 'Mitad Humana - duplex.pdf' in d.status.text()


def test_an_export_with_nothing_to_print_says_so(qapp):
    d = _dlg(qapp)
    d.exporter = lambda b, kind: []
    d.duplex_btn.click()
    assert 'nada' in d.status.text().lower()


def test_duplicating_asks_the_caller_to_make_an_edition(qapp):
    d = _dlg(qapp)
    assert d.duplicate_requested is False
    d.duplicate_btn.click()
    assert d.duplicate_requested is True
    assert d.result() == 1 or d.isHidden()             # el cuadro se acepta
