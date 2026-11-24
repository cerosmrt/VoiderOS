"""El bookbinder: los ajustes previos a imprimir, aparte del armado del libro. Hojas
por cuadernillo con la tabla de páginas en blanco, el colofón, y los PDF. Los tests le
pasan un renderizador de mentira: lo que se prueba es el cuadro, no el dibujo."""
import pytest

pytest.importorskip("PyQt6")
from PyQt6.QtWidgets import QApplication

import imposition
from bookbinder_dialog import BookbinderDialog


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


def _book():
    return {'id': 'l1', 'titulo': 'Mitad Humana', 'capitulos': ['A.txt'], 'hojas': 4,
            'autor': 'Federico', 'colofon': ''}


def _dlg(qapp, renderer='ok', missing=()):
    calls = {'export': [], 'factory': 0}

    def factory(b):
        calls['factory'] += 1
        return (FakeRenderer() if renderer == 'ok' else None), list(missing)

    def exporter(b, kind):
        calls['export'].append((kind, b['hojas']))
        return [f'/tmp/{b["titulo"]} - {kind}.pdf']
    d = BookbinderDialog(None, _book(), factory, exporter)
    d.calls = calls
    return d


def test_it_is_about_printing_not_about_building_the_book(qapp):
    d = _dlg(qapp)
    for absent in ('chapters', 'add_btn', 'remove_btn', 'title_edit', 'author_edit'):
        assert not hasattr(d, absent), absent


def test_it_names_the_book_and_shows_the_sheets(qapp):
    d = _dlg(qapp)
    assert 'Mitad Humana' in d.windowTitle() or 'Mitad Humana' in d.heading.text()
    assert d.sheets_spin.value() == 4


def test_the_table_has_one_row_per_option_with_the_best_starred(qapp):
    d = _dlg(qapp)
    assert d.table.rowCount() == 7
    estrellas = [r for r in range(7) if '★' in d.table.item(r, 0).text()]
    assert len(estrellas) == 1
    assert d.table.item(estrellas[0], 0).text().strip('★ ') == str(imposition.best_sheets(50))


def test_changing_the_sheets_updates_the_summary_without_rebuilding(qapp):
    d = _dlg(qapp)
    antes = d.calls['factory']
    d.sheets_spin.setValue(6)
    assert d.renderer.sheets == 6
    assert str(imposition.pad_to_signatures(50, 6)[2]) in d.summary.text()
    assert d.calls['factory'] == antes


def test_the_result_carries_the_sheets_and_the_colophon(qapp):
    d = _dlg(qapp)
    d.sheets_spin.setValue(5)
    d.colofon_edit.setPlainText('Hecho en Gualeguay')
    r = d.result_book()
    assert r['hojas'] == 5 and r['colofon'] == 'Hecho en Gualeguay'
    assert r['titulo'] == 'Mitad Humana' and r['capitulos'] == ['A.txt']


def test_the_original_book_is_not_touched(qapp):
    book = _book()
    d = BookbinderDialog(None, book, lambda b: (FakeRenderer(), []), lambda b, k: [])
    d.sheets_spin.setValue(8)
    assert book['hojas'] == 4


@pytest.mark.parametrize('button,kind', [('duplex_btn', 'duplex'), ('manual_btn', 'manual'),
                                          ('test_btn', 'test'), ('read_btn', 'read')])
def test_each_export_button_asks_for_its_kind_with_the_current_sheets(qapp, button, kind):
    d = _dlg(qapp)
    d.sheets_spin.setValue(3)
    getattr(d, button).click()
    assert d.calls['export'] == [(kind, 3)]


def test_after_an_export_the_status_says_where_it_went(qapp):
    d = _dlg(qapp)
    d.duplex_btn.click()
    assert 'Mitad Humana - duplex.pdf' in d.status.text()


def test_a_book_with_nothing_to_print_says_so_and_has_no_table(qapp):
    d = _dlg(qapp, renderer=None)
    assert d.table.rowCount() == 0
    assert 'imprimir' in d.summary.text().lower()


def test_missing_chapters_are_warned_about(qapp):
    d = _dlg(qapp, missing=['Fantasma.txt'])
    assert 'Fantasma' in d.status.text() and 'faltan' in d.status.text().lower()


def test_an_export_that_writes_nothing_says_so(qapp):
    d = _dlg(qapp)
    d.exporter = lambda b, kind: []
    d.duplex_btn.click()
    assert 'nada' in d.status.text().lower()


def test_the_buttons_explain_the_flip_setting(qapp):
    d = _dlg(qapp)
    assert 'borde corto' in d.hint.text().lower()
