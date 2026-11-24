"""F8: la vista, como F3. Un anillo de libros; Enter entra al esqueleto del libro
(Portada · Título · Autor · Prólogo · Dedicatoria · Cap 1…n · Epílogo · Referencia
· .) y ahí cada fila se llena o se vacía; Esc vuelve. Ctrl+P / Ctrl+S abren el
bookbinder (los ajustes de impresión). Los diálogos de Qt se reemplazan; el anillo
y el catálogo son de verdad.
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

VIEW_METHODS = (
    '_books_rebuild_ring', '_books_current', '_books_current_key', '_books_open_book',
    '_books_navigate', '_books_new', '_books_delete', '_books_open_skeleton',
    '_books_back', '_books_escape', '_books_enter', '_books_commit_edit',
    '_books_activate', '_books_pick_for', '_books_edit_meta', '_books_ctrl_delete',
    '_books_clear_slot', '_books_duplicate', '_books_open_bookbinder',
    '_books_refresh_editor', '_books_f3_group')


@pytest.fixture(scope='module')
def qapp():
    yield QApplication.instance() or QApplication([])


def _app(tmp_path, with_books=True):
    from new_interface import FullscreenCircleApp
    app = _base_app(tmp_path)
    app.books_view = MagicMock()
    app.books_view.editor.browsing = True
    app.books_ring = LineRing(['.'])
    app._books_ids = []
    app._books_level = 'books'
    app._books_open_id = None
    app._books_row_keys = []
    if with_books:
        b.new_book(app.books, 'Uno', ['A.txt'])
        b.new_book(app.books, 'Dos', ['B.txt', 'C.txt'])
        b.new_book(app.books, 'Tres', [])
        app._books_save()
    for nm in VIEW_METHODS:
        setattr(app, nm, types.MethodType(getattr(FullscreenCircleApp, nm), app))
    app._books_rebuild_ring()
    return app


def _on_disk(tmp_path):
    return json.loads((tmp_path / 'books.json').read_text(encoding='utf-8'))['libros']


def _enter_book(app, i=0):
    app.books_ring.index = i
    app._books_enter()


def _go_to(app, key):
    app.books_ring.index = app._books_row_keys.index(key)


# ── el anillo de libros (nivel 1) ────────────────────────────────────────────

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


def test_a_new_book_is_created_saved_and_selected(tmp_path):
    app = _app(tmp_path)
    with patch('PyQt6.QtWidgets.QInputDialog.getText', return_value=('Nuevo libro', True)):
        app._books_new()
    assert app._books_current()['titulo'] == 'Nuevo libro'
    assert [x['titulo'] for x in _on_disk(tmp_path)] == ['Uno', 'Dos', 'Tres', 'Nuevo libro']


def test_a_cancelled_or_empty_name_creates_nothing(tmp_path):
    app = _app(tmp_path)
    for answer in (('', True), ('   ', True), ('x', False)):
        with patch('PyQt6.QtWidgets.QInputDialog.getText', return_value=answer):
            app._books_new()
    assert len(app.books['libros']) == 3


def test_deleting_a_book_asks_first_and_never_touches_the_chapter_files(tmp_path):
    app = _app(tmp_path)
    antes = sorted(p.name for p in (tmp_path / 'I').iterdir())
    app.books_ring.index = 1
    with patch('PyQt6.QtWidgets.QMessageBox.question', return_value=QMessageBox.StandardButton.No):
        app._books_delete()
    assert len(app.books['libros']) == 3
    with patch('PyQt6.QtWidgets.QMessageBox.question', return_value=QMessageBox.StandardButton.Yes):
        app._books_delete()
    assert [x['titulo'] for x in app.books['libros']] == ['Uno', 'Tres']
    assert sorted(p.name for p in (tmp_path / 'I').iterdir()) == antes


def test_ctrl_delete_on_the_book_ring_asks_to_delete_the_book(tmp_path):
    app = _app(tmp_path)
    with patch('PyQt6.QtWidgets.QMessageBox.question', return_value=QMessageBox.StandardButton.Yes):
        app._books_ctrl_delete()
    assert [x['titulo'] for x in app.books['libros']] == ['Dos', 'Tres']


def test_a_duplicate_is_an_edition_right_below(tmp_path):
    app = _app(tmp_path)
    app.books_ring.index = 1
    app._books_duplicate()
    assert [x['titulo'] for x in app.books['libros']] == ['Uno', 'Dos', 'Dos (copia)', 'Tres']
    assert app._books_current()['titulo'] == 'Dos (copia)'
    assert len(_on_disk(tmp_path)) == 4


def test_with_no_books_delete_duplicate_and_enter_do_nothing(tmp_path):
    app = _app(tmp_path, with_books=False)
    app._books_delete()
    app._books_duplicate()
    app._books_enter()
    app._books_ctrl_delete()
    assert app._books_level == 'books'


# ── renombrar un libro: ←/→ y escribir, como un título de F3 ─────────────────

def test_editing_the_title_in_the_ring_renames_the_book(tmp_path):
    app = _app(tmp_path)
    app.books_view.editor.browsing = False            # se está editando
    app.books_view.editor.text.return_value = 'Uno, corregido'
    app._books_commit_edit()
    assert app._books_current()['titulo'] == 'Uno, corregido'
    assert _on_disk(tmp_path)[0]['titulo'] == 'Uno, corregido'
    app.books_view.editor.leave_edit.assert_called()


def test_an_unchanged_or_empty_title_does_not_save(tmp_path):
    app = _app(tmp_path)
    antes = (tmp_path / 'books.json').stat().st_mtime_ns
    app.books_view.editor.browsing = False
    for text in ('Uno', '   ', ''):
        app.books_view.editor.text.return_value = text
        app._books_commit_edit()
    assert (tmp_path / 'books.json').stat().st_mtime_ns == antes


def test_committing_while_just_browsing_does_nothing(tmp_path):
    app = _app(tmp_path)
    app.books_view.editor.text.return_value = 'Otro'
    app._books_commit_edit()                          # browsing = True
    assert app._books_current()['titulo'] == 'Uno'


def test_enter_while_editing_commits_instead_of_opening(tmp_path):
    app = _app(tmp_path)
    app.books_view.editor.browsing = False
    app.books_view.editor.text.return_value = 'Cambiado'
    app._books_enter()
    assert app._books_level == 'books' and app._books_current()['titulo'] == 'Cambiado'


def test_navigating_while_editing_saves_the_rename_first(tmp_path):
    app = _app(tmp_path)
    app.books_view.editor.browsing = False
    app.books_view.editor.text.return_value = 'Renombrado'
    app._books_navigate(+1)
    assert [x['titulo'] for x in app.books['libros']][0] == 'Renombrado'


# ── el esqueleto (nivel 2) ───────────────────────────────────────────────────

def test_enter_on_a_book_opens_its_skeleton(tmp_path):
    app = _app(tmp_path)
    _enter_book(app, 1)
    assert app._books_level == 'skeleton'
    assert app.books_ring.lines[:6] == ['Portada · sí', 'Título · Dos', 'Autor · —',
                                        'Prólogo · —', 'Dedicatoria · —', 'Cap 1 · B']
    assert app.books_ring.lines[-1] == '.'
    assert app._books_current_key() == 'portada'


def test_the_skeleton_always_has_six_chapter_slots(tmp_path):
    app = _app(tmp_path)
    _enter_book(app, 2)                               # 'Tres', sin capítulos
    caps = [k for k in app._books_row_keys if k.startswith('cap:')]
    assert caps == [f'cap:{i}' for i in range(1, 7)]


def test_escape_goes_back_one_level_and_keeps_the_book_selected(tmp_path):
    app = _app(tmp_path)
    _enter_book(app, 1)
    assert app._books_escape() is True
    assert app._books_level == 'books' and app._books_current()['titulo'] == 'Dos'


def test_escape_on_the_book_ring_is_left_to_the_router(tmp_path):
    app = _app(tmp_path)
    assert app._books_escape() is False               # el router lo manda a F1


def test_the_skeleton_ring_navigates_and_wraps(tmp_path):
    app = _app(tmp_path)
    _enter_book(app)
    app._books_navigate(-1)
    assert app._books_current_key() == '.'
    app._books_navigate(+1)
    assert app._books_current_key() == 'portada'


def test_in_the_skeleton_the_editor_is_never_editable(tmp_path):
    """Las filas son 'Etiqueta · valor': el valor se cambia con Enter, no tipeando."""
    app = _app(tmp_path)
    _enter_book(app)
    app.books_view.editor.setReadOnly.assert_called_with(True)


def test_the_dot_row_does_nothing(tmp_path):
    app = _app(tmp_path)
    _enter_book(app)
    _go_to(app, '.')
    app._books_enter()
    assert app._books_level == 'skeleton'


def test_enter_on_the_cover_switch_toggles_it_and_saves(tmp_path):
    app = _app(tmp_path)
    _enter_book(app)
    app._books_enter()                                # estamos en 'portada'
    assert app.books_ring.lines[0] == 'Portada · no'
    assert _on_disk(tmp_path)[0]['portada'] is False
    assert app._books_current_key() == 'portada'      # no se mueve el cursor
    app._books_enter()
    assert app.books_ring.lines[0] == 'Portada · sí'


def test_enter_on_the_reference_switch_toggles_it(tmp_path):
    app = _app(tmp_path)
    _enter_book(app)
    _go_to(app, 'referencia')
    app._books_enter()
    assert _on_disk(tmp_path)[0]['referencia'] is False


def test_enter_on_the_title_row_renames_the_book(tmp_path):
    app = _app(tmp_path)
    _enter_book(app)
    _go_to(app, 'titulo')
    with patch('PyQt6.QtWidgets.QInputDialog.getText', return_value=('Nuevo título', True)) as q:
        app._books_enter()
    assert q.call_args.kwargs.get('text') == 'Uno' or 'Uno' in q.call_args.args
    assert _on_disk(tmp_path)[0]['titulo'] == 'Nuevo título'
    assert app.books_ring.lines[1] == 'Título · Nuevo título'


def test_enter_on_the_author_row_sets_the_author(tmp_path):
    app = _app(tmp_path)
    _enter_book(app)
    _go_to(app, 'autor')
    with patch('PyQt6.QtWidgets.QInputDialog.getText', return_value=('Federico Moret', True)):
        app._books_enter()
    assert _on_disk(tmp_path)[0]['autor'] == 'Federico Moret'
    assert app.books_ring.lines[2] == 'Autor · Federico Moret'


def test_an_empty_author_is_allowed_and_an_empty_title_is_not(tmp_path):
    app = _app(tmp_path)
    _enter_book(app)
    _go_to(app, 'autor')
    with patch('PyQt6.QtWidgets.QInputDialog.getText', return_value=('', True)):
        app._books_enter()
    assert _on_disk(tmp_path)[0]['autor'] == ''
    _go_to(app, 'titulo')
    with patch('PyQt6.QtWidgets.QInputDialog.getText', return_value=('  ', True)):
        app._books_enter()
    assert _on_disk(tmp_path)[0]['titulo'] == 'Uno'


def test_cancelling_the_title_or_author_dialog_changes_nothing(tmp_path):
    app = _app(tmp_path)
    _enter_book(app)
    for key in ('titulo', 'autor'):
        _go_to(app, key)
        with patch('PyQt6.QtWidgets.QInputDialog.getText', return_value=('X', False)):
            app._books_enter()
    assert (_on_disk(tmp_path)[0]['titulo'], _on_disk(tmp_path)[0]['autor']) == ('Uno', '')


# ── llenar los lugares con capítulos ─────────────────────────────────────────

def test_enter_on_a_role_row_picks_a_chapter_for_it(tmp_path):
    app = _app(tmp_path)
    _enter_book(app)
    _go_to(app, 'prologo')
    with patch('chapter_picker.pick_chapter', return_value='B.txt') as pick:
        app._books_enter()
    assert _on_disk(tmp_path)[0]['prologo'] == 'B.txt'
    assert app.books_ring.lines[3] == 'Prólogo · B'
    assert app._books_current_key() == 'prologo'


def test_the_picker_offers_only_chapters_not_already_in_the_book(tmp_path):
    app = _app(tmp_path)
    _enter_book(app, 1)                               # 'Dos': tiene B y C
    _go_to(app, 'dedicatoria')
    with patch('chapter_picker.pick_chapter', return_value=None) as pick:
        app._books_enter()
    ofrecidos = pick.call_args.args[1]
    assert ofrecidos == ['A.txt']


def test_the_picker_for_a_filled_slot_also_offers_its_own_chapter(tmp_path):
    app = _app(tmp_path)
    _enter_book(app, 1)
    _go_to(app, 'cap:1')                              # tiene B
    with patch('chapter_picker.pick_chapter', return_value=None) as pick:
        app._books_enter()
    assert 'B.txt' in pick.call_args.args[1] and 'A.txt' in pick.call_args.args[1]


def test_enter_on_an_empty_chapter_slot_fills_it_in_order(tmp_path):
    app = _app(tmp_path)
    _enter_book(app, 0)                               # 'Uno': cap 1 = A
    _go_to(app, 'cap:2')
    with patch('chapter_picker.pick_chapter', return_value='C.txt'):
        app._books_enter()
    assert _on_disk(tmp_path)[0]['capitulos'] == ['A.txt', 'C.txt']
    assert app.books_ring.lines[app._books_row_keys.index('cap:2')] == 'Cap 2 · C'


def test_a_chapter_slot_past_the_last_gets_a_new_empty_slot_after_it(tmp_path):
    app = _app(tmp_path)
    _enter_book(app, 1)
    for n in (3, 4, 5, 6):
        _go_to(app, f'cap:{n}')
        with patch('chapter_picker.pick_chapter', return_value=f'X{n}.txt'):
            app._books_enter()
    caps = [k for k in app._books_row_keys if k.startswith('cap:')]
    assert len(caps) == 7                             # 6 llenos + 1 vacío para el próximo


def test_cancelling_the_picker_changes_nothing(tmp_path):
    app = _app(tmp_path)
    _enter_book(app)
    _go_to(app, 'prologo')
    with patch('chapter_picker.pick_chapter', return_value=None):
        app._books_enter()
    assert _on_disk(tmp_path)[0]['prologo'] == ''


def test_ctrl_delete_empties_a_role_or_a_chapter_slot(tmp_path):
    app = _app(tmp_path)
    _enter_book(app, 1)
    b.assign(app._books_open_book(), 'prologo', 'A.txt')
    app._books_rebuild_ring(select_key='prologo')
    app._books_ctrl_delete()
    assert _on_disk(tmp_path)[1]['prologo'] == ''
    _go_to(app, 'cap:1')
    app._books_ctrl_delete()
    assert _on_disk(tmp_path)[1]['capitulos'] == ['C.txt']      # B salió y C subió


def test_ctrl_delete_on_a_switch_or_the_dot_does_nothing(tmp_path):
    app = _app(tmp_path)
    _enter_book(app)
    antes = (tmp_path / 'books.json').stat().st_mtime_ns
    for key in ('portada', 'referencia', 'titulo', 'autor', '.'):
        _go_to(app, key)
        app._books_ctrl_delete()
    assert (tmp_path / 'books.json').stat().st_mtime_ns == antes


def test_deleting_a_slot_never_touches_the_chapter_file(tmp_path):
    app = _app(tmp_path)
    _enter_book(app, 1)
    _go_to(app, 'cap:1')
    app._books_ctrl_delete()
    assert (tmp_path / 'I' / 'B.txt').exists()


# ── el bookbinder: los ajustes de impresión, aparte ──────────────────────────

class FakeBinder:
    last = None
    accept = True
    edit = None

    def __init__(self, parent, book, renderer_factory, exporter):
        FakeBinder.last = self
        self.book = copy.deepcopy(book)

    def exec(self):
        return 1 if FakeBinder.accept else 0

    def result_book(self):
        out = dict(self.book)
        out.update(FakeBinder.edit or {})
        return out


def _reset():
    FakeBinder.last, FakeBinder.accept, FakeBinder.edit = None, True, None


def test_the_bookbinder_opens_for_the_book_under_the_cursor_on_the_ring(tmp_path):
    _reset()
    app = _app(tmp_path)
    app.books_ring.index = 1
    with patch('bookbinder_dialog.BookbinderDialog', FakeBinder):
        app._books_open_bookbinder()
    assert FakeBinder.last.book['titulo'] == 'Dos'


def test_the_bookbinder_opens_for_the_open_book_inside_the_skeleton(tmp_path):
    _reset()
    app = _app(tmp_path)
    _enter_book(app, 2)
    with patch('bookbinder_dialog.BookbinderDialog', FakeBinder):
        app._books_open_bookbinder()
    assert FakeBinder.last.book['titulo'] == 'Tres'


def test_accepting_the_bookbinder_saves_the_print_settings_only(tmp_path):
    _reset()
    app = _app(tmp_path)
    FakeBinder.edit = {'hojas': 6, 'colofon': 'Hecho en Gualeguay', 'titulo': 'NO DEBE CAMBIAR'}
    with patch('bookbinder_dialog.BookbinderDialog', FakeBinder):
        app._books_open_bookbinder()
    libro = _on_disk(tmp_path)[0]
    assert libro['hojas'] == 6 and libro['colofon'] == 'Hecho en Gualeguay'
    assert libro['titulo'] == 'Uno'                    # el bookbinder no toca el armado


def test_cancelling_the_bookbinder_changes_nothing(tmp_path):
    _reset()
    app = _app(tmp_path)
    FakeBinder.accept = False
    FakeBinder.edit = {'hojas': 9}
    with patch('bookbinder_dialog.BookbinderDialog', FakeBinder):
        app._books_open_bookbinder()
    assert app.books['libros'][0]['hojas'] == 4


def test_the_bookbinder_with_no_books_does_nothing(tmp_path):
    _reset()
    app = _app(tmp_path, with_books=False)
    with patch('bookbinder_dialog.BookbinderDialog', FakeBinder):
        app._books_open_bookbinder()
    assert FakeBinder.last is None


# ── desde F3 ─────────────────────────────────────────────────────────────────

def test_the_f3_group_comes_from_the_library_cursor(tmp_path):
    app = _app(tmp_path)                               # ('.','A','B','.','C')
    app.book_ring.index = 2
    assert app._books_f3_group() == ['A.txt', 'B.txt']


def test_the_view_methods_only_call_things_that_exist():
    """Los diálogos de Qt no se corren en un test: un nombre mal escrito explotaría
    recién al usarlos."""
    import inspect
    import re
    from new_interface import FullscreenCircleApp
    for nombre in ('_books_show', '_books_new', '_books_delete', '_books_enter',
                   '_books_activate', '_books_pick_for', '_books_edit_meta',
                   '_books_open_bookbinder', '_books_navigate', '_books_show_editor',
                   '_books_commit_edit', '_books_ctrl_delete', '_books_clear_slot',
                   '_books_duplicate', '_books_escape', '_books_back',
                   '_books_open_skeleton', '_books_rebuild_ring'):
        fuente = inspect.getsource(getattr(FullscreenCircleApp, nombre))
        llamados = set(re.findall(r'self\.(_?[a-zA-Z_][a-zA-Z0-9_]*)\(', fuente))
        faltan = [n for n in sorted(llamados) if not hasattr(FullscreenCircleApp, n)]
        assert not faltan, f'{nombre} llama a métodos inexistentes: {faltan}'


def test_with_no_chapters_to_offer_it_says_so_instead_of_doing_nothing(tmp_path):
    app = _app(tmp_path)
    _enter_book(app, 1)                               # 'Dos' ya usa A? no: usa B y C; A libre
    app._books_chapters_available = lambda: []
    _go_to(app, 'prologo')
    with patch('PyQt6.QtWidgets.QMessageBox.information') as aviso, \
         patch('chapter_picker.pick_chapter') as pick:
        app._books_enter()
    aviso.assert_called_once()
    pick.assert_not_called()
