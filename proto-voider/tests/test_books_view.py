"""F8, la vista: el anillo de libros y lo que se hace con él (crear, borrar, abrir el
cuadro). Los diálogos de Qt se reemplazan; el anillo y el catálogo son de verdad.
"""
import copy
import json
import types
from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("PyQt6")
from PyQt6.QtWidgets import QApplication, QMessageBox

import books as b
from line_ring import LineRing
from test_books_mixin import _app as _base_app

VIEW_METHODS = ('_books_rebuild_ring', '_books_current', '_books_navigate',
                '_books_new', '_books_delete', '_books_open_packer',
                '_books_f3_group', '_books_refresh_editor')


@pytest.fixture(scope='module')
def qapp():
    yield QApplication.instance() or QApplication([])


def _app(tmp_path, with_books=True):
    from new_interface import FullscreenCircleApp
    app = _base_app(tmp_path)
    app.books_view = MagicMock()
    app.books_ring = LineRing(['.'])
    app._books_ids = []
    if with_books:
        b.new_book(app.books, 'Uno', ['A.txt'])
        b.new_book(app.books, 'Dos', ['B.txt', 'C.txt'])
        b.new_book(app.books, 'Tres', [])
        app._books_save()
    for nm in VIEW_METHODS:
        setattr(app, nm, types.MethodType(getattr(FullscreenCircleApp, nm), app))
    app._books_rebuild_ring()
    return app


# ── el anillo ────────────────────────────────────────────────────────────────

def test_the_ring_lists_the_book_titles_in_order(tmp_path):
    app = _app(tmp_path)
    assert app.books_ring.lines == ['Uno', 'Dos', 'Tres']


def test_an_empty_catalog_shows_a_hint_instead_of_an_empty_ring(tmp_path):
    app = _app(tmp_path, with_books=False)
    assert len(app.books_ring.lines) == 1 and 'Shift+Enter' in app.books_ring.lines[0]
    assert app._books_current() is None


def test_current_is_the_book_under_the_cursor(tmp_path):
    app = _app(tmp_path)
    app.books_ring.index = 1
    assert app._books_current()['titulo'] == 'Dos'


def test_rebuilding_keeps_the_selected_book_by_id(tmp_path):
    app = _app(tmp_path)
    dos = app.books['libros'][1]['id']
    app.books['libros'].insert(0, b._normalize({'id': 'l9', 'titulo': 'Primero'}))
    app._books_rebuild_ring(select_id=dos)
    assert app._books_current()['id'] == dos


def test_navigating_wraps_around_the_ring(tmp_path):
    app = _app(tmp_path)
    app._books_navigate(-1)
    assert app._books_current()['titulo'] == 'Tres'
    app._books_navigate(+1)
    assert app._books_current()['titulo'] == 'Uno'


# ── crear y borrar ───────────────────────────────────────────────────────────

def test_a_new_book_is_created_saved_and_selected(tmp_path):
    app = _app(tmp_path)
    with patch('PyQt6.QtWidgets.QInputDialog.getText', return_value=('Nuevo libro', True)):
        app._books_new()
    assert app._books_current()['titulo'] == 'Nuevo libro'
    saved = json.loads((tmp_path / 'books.json').read_text(encoding='utf-8'))['libros']
    assert [x['titulo'] for x in saved] == ['Uno', 'Dos', 'Tres', 'Nuevo libro']


def test_a_cancelled_or_empty_name_creates_nothing(tmp_path):
    app = _app(tmp_path)
    for answer in (('', True), ('   ', True), ('x', False)):
        with patch('PyQt6.QtWidgets.QInputDialog.getText', return_value=answer):
            app._books_new()
    assert len(app.books['libros']) == 3


def test_deleting_asks_first_and_only_removes_that_book(tmp_path):
    app = _app(tmp_path)
    app.books_ring.index = 1
    with patch('PyQt6.QtWidgets.QMessageBox.question',
               return_value=QMessageBox.StandardButton.Yes):
        app._books_delete()
    assert [x['titulo'] for x in app.books['libros']] == ['Uno', 'Tres']
    saved = json.loads((tmp_path / 'books.json').read_text(encoding='utf-8'))['libros']
    assert [x['titulo'] for x in saved] == ['Uno', 'Tres']


def test_saying_no_keeps_the_book(tmp_path):
    app = _app(tmp_path)
    with patch('PyQt6.QtWidgets.QMessageBox.question',
               return_value=QMessageBox.StandardButton.No):
        app._books_delete()
    assert len(app.books['libros']) == 3


def test_deleting_a_book_never_touches_the_chapter_files(tmp_path):
    app = _app(tmp_path)
    antes = sorted(p.name for p in (tmp_path / 'I').iterdir())
    with patch('PyQt6.QtWidgets.QMessageBox.question',
               return_value=QMessageBox.StandardButton.Yes):
        app._books_delete()
    assert sorted(p.name for p in (tmp_path / 'I').iterdir()) == antes


def test_delete_and_open_with_no_books_do_nothing(tmp_path):
    app = _app(tmp_path, with_books=False)
    app._books_delete()
    app._books_open_packer()          # no revienta


# ── el cuadro ────────────────────────────────────────────────────────────────

class FakeDialog:
    """Un cuadro que 'acepta' con los cambios que se le indiquen."""
    last = None
    accept = True
    edit = None
    duplicate = False

    def __init__(self, parent, book, available, factory, exporter, f3_group=None):
        FakeDialog.last = self
        self.book = copy.deepcopy(book)                # el real también edita una copia
        self.available, self.f3_group = available, f3_group
        self.duplicate_requested = FakeDialog.duplicate

    def exec(self):
        return 1 if FakeDialog.accept else 0

    def result_book(self):
        out = dict(self.book)
        out.update(FakeDialog.edit or {})
        return out


def _reset():
    FakeDialog.last, FakeDialog.accept, FakeDialog.edit, FakeDialog.duplicate = None, True, None, False


def test_enter_opens_the_packer_with_the_book_and_the_library_chapters(tmp_path):
    _reset()
    app = _app(tmp_path)
    app.books_ring.index = 1
    with patch('book_packer_dialog.BookPackerDialog', FakeDialog):
        app._books_open_packer()
    assert FakeDialog.last.book['titulo'] == 'Dos'
    assert FakeDialog.last.available == ['A.txt', 'B.txt', 'C.txt']


def test_accepting_saves_every_change_to_the_catalog(tmp_path):
    _reset()
    app = _app(tmp_path)
    FakeDialog.edit = {'titulo': 'Dos y medio', 'capitulos': ['C.txt', 'B.txt'], 'hojas': 6}
    app.books_ring.index = 1
    with patch('book_packer_dialog.BookPackerDialog', FakeDialog):
        app._books_open_packer()
    saved = json.loads((tmp_path / 'books.json').read_text(encoding='utf-8'))['libros']
    assert saved[1]['titulo'] == 'Dos y medio'
    assert saved[1]['capitulos'] == ['C.txt', 'B.txt'] and saved[1]['hojas'] == 6
    assert app._books_current()['titulo'] == 'Dos y medio'


def test_cancelling_changes_nothing(tmp_path):
    _reset()
    app = _app(tmp_path)
    FakeDialog.accept = False
    FakeDialog.edit = {'titulo': 'No debería guardarse'}
    with patch('book_packer_dialog.BookPackerDialog', FakeDialog):
        app._books_open_packer()
    assert app.books['libros'][0]['titulo'] == 'Uno'


def test_a_duplicate_request_makes_an_edition_below(tmp_path):
    _reset()
    app = _app(tmp_path)
    FakeDialog.duplicate = True
    app.books_ring.index = 1
    with patch('book_packer_dialog.BookPackerDialog', FakeDialog):
        app._books_open_packer()
    assert [x['titulo'] for x in app.books['libros']] == [
        'Uno', 'Dos', 'Dos (copia)', 'Tres']
    assert app._books_current()['titulo'] == 'Dos (copia)'


def test_the_f3_group_comes_from_the_library_cursor(tmp_path):
    app = _app(tmp_path)                               # ('.','A','B','.','C')
    app.book_ring.index = 2
    assert app._books_f3_group() == ['A.txt', 'B.txt']
    app.book_ring.index = 4
    assert app._books_f3_group() == ['C.txt']


def test_the_view_methods_only_call_things_that_exist():
    """Los diálogos de Qt no se corren en un test: un nombre mal escrito explotaría
    recién al usarlos."""
    import inspect
    import re
    from new_interface import FullscreenCircleApp
    for nombre in ('_books_show', '_books_new', '_books_delete', '_books_open_packer',
                   '_books_navigate', '_books_show_editor'):
        fuente = inspect.getsource(getattr(FullscreenCircleApp, nombre))
        llamados = set(re.findall(r'self\.(_?[a-zA-Z_][a-zA-Z0-9_]*)\(', fuente))
        faltan = [n for n in sorted(llamados) if not hasattr(FullscreenCircleApp, n)]
        assert not faltan, f'{nombre} llama a métodos inexistentes: {faltan}'
