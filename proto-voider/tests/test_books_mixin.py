"""F8, el empaquetador de libros: lo que no es interfaz.

Cargar y guardar el catálogo (<void>/books.json), armar un libro a partir de sus
capítulos, exportar los PDF para imprimir, y seguir lo que pasa en F3: si un
capítulo se renombra o se borra, los libros que lo tienen se enteran.
"""
import json
import os
import re
import types

import pytest

pytest.importorskip("PyQt6")
from PyQt6.QtWidgets import QApplication

import books as b
from test_f3_undo import _f3_app, _read

METHODS = ('_books_path', '_books_load', '_books_save', '_books_chapters_available',
           '_books_renderer', '_books_export', '_books_out_dir',
           '_books_on_chapter_renamed', '_books_on_chapter_deleted',
           '_books_notify', '_books_update_file', '_reading_file_lines',
           '_books_reference_text')


@pytest.fixture(scope='module')
def qapp():
    yield QApplication.instance() or QApplication([])


def _lines(n, tag):
    out = []
    for i in range(n):
        out += [f'{tag}: una oración numero {i} con texto suficiente para llenar una línea.', '.']
    return out


def _app(tmp_path, library=('.', 'A.txt', 'B.txt', '.', 'C.txt')):
    from new_interface import FullscreenCircleApp
    contents = {fn: _lines(30, fn[:-4]) for fn in library if fn != '.'}
    app = _f3_app(tmp_path, list(library), contents)
    app.config = {'reading_font': 'Sans Serif', 'reading_size': 11,
                  'reading_hyphen_lang': None}
    app.books = b.empty()
    for nm in METHODS:
        setattr(app, nm, types.MethodType(getattr(FullscreenCircleApp, nm), app))
    return app


def _pages_in(path):
    with open(path, 'rb') as f:
        return len(re.findall(rb'/Type\s*/Page(?!s)', f.read()))


# ── el catálogo ──────────────────────────────────────────────────────────────

def test_the_catalog_lives_in_books_json_at_the_void_root(tmp_path):
    app = _app(tmp_path)
    assert app._books_path() == str(tmp_path / 'books.json')


def test_loading_without_a_file_gives_an_empty_catalog(tmp_path):
    app = _app(tmp_path)
    assert app._books_load() == b.empty()
    assert app.books == b.empty()


def test_save_then_load_roundtrips(tmp_path):
    app = _app(tmp_path)
    app._books_load()
    b.new_book(app.books, 'Mitad Humana', ['A.txt', 'B.txt'])
    app._books_save()
    app.books = None
    app._books_load()
    assert app.books['libros'][0]['capitulos'] == ['A.txt', 'B.txt']


def test_available_chapters_skip_dots_and_the_portal(tmp_path):
    app = _app(tmp_path, ('.', 'A.txt', '0.txt', 'B.txt', '.', 'C.txt'))
    assert app._books_chapters_available() == ['A.txt', 'B.txt', 'C.txt']


# ── armar el libro desde los capítulos ───────────────────────────────────────

def test_the_renderer_follows_the_books_chapter_order(qapp, tmp_path):
    app = _app(tmp_path)
    bk = b.new_book(app.books, 'Mitad Humana', ['C.txt', 'A.txt'])
    r, missing = app._books_renderer(bk)
    assert r.titles == ['C', 'A'] and missing == []


def test_a_missing_chapter_is_skipped_and_reported(qapp, tmp_path):
    app = _app(tmp_path)
    bk = b.new_book(app.books, 'Mitad Humana', ['A.txt', 'Fantasma.txt', 'B.txt'])
    r, missing = app._books_renderer(bk)
    assert r.titles == ['A', 'B'] and missing == ['Fantasma.txt']


def test_the_book_uses_its_own_sheets_title_and_author(qapp, tmp_path):
    app = _app(tmp_path)
    bk = b.new_book(app.books, 'Mitad Humana', ['A.txt'])
    bk['hojas'], bk['autor'] = 3, 'Federico'
    r, _ = app._books_renderer(bk)
    assert r.plan.sheets == 3 and r.titulo == 'Mitad Humana' and r.autor == 'Federico'


def test_a_book_without_readable_chapters_has_no_renderer(qapp, tmp_path):
    app = _app(tmp_path)
    bk = b.new_book(app.books, 'Vacío', [])
    r, missing = app._books_renderer(bk)
    assert r is None
    bk2 = b.new_book(app.books, 'Roto', ['Fantasma.txt'])
    assert app._books_renderer(bk2) == (None, ['Fantasma.txt'])


# ── exportar ─────────────────────────────────────────────────────────────────

def test_exports_go_to_a_folder_named_after_the_book(qapp, tmp_path):
    app = _app(tmp_path)
    bk = b.new_book(app.books, 'Mitad Humana', ['A.txt', 'B.txt'])
    assert app._books_out_dir(bk) == str(tmp_path / 'book_packer' / 'Mitad Humana')


def test_a_title_with_forbidden_characters_makes_a_safe_folder(qapp, tmp_path):
    app = _app(tmp_path)
    bk = b.new_book(app.books, 'Uno/Dos: ¿qué?', ['A.txt'])
    carpeta = os.path.basename(app._books_out_dir(bk))
    assert not any(ch in carpeta for ch in '/\\:?*"<>|')


def test_duplex_export_writes_one_pdf(qapp, tmp_path):
    app = _app(tmp_path)
    bk = b.new_book(app.books, 'Mitad Humana', ['A.txt', 'B.txt'])
    paths = app._books_export(bk, 'duplex')
    assert [os.path.basename(p) for p in paths] == ['Mitad Humana - doble cara.pdf']
    assert os.path.getsize(paths[0]) > 1000 and _pages_in(paths[0]) % 2 == 0


def test_manual_export_writes_fronts_and_backs(qapp, tmp_path):
    app = _app(tmp_path)
    bk = b.new_book(app.books, 'Mitad Humana', ['A.txt', 'B.txt'])
    paths = app._books_export(bk, 'manual')
    assert [os.path.basename(p) for p in paths] == [
        'Mitad Humana - caras.pdf', 'Mitad Humana - dorsos.pdf']
    assert _pages_in(paths[0]) == _pages_in(paths[1])


def test_the_test_sheet_is_two_sides(qapp, tmp_path):
    app = _app(tmp_path)
    bk = b.new_book(app.books, 'Mitad Humana', ['A.txt'])
    paths = app._books_export(bk, 'test')
    assert os.path.basename(paths[0]) == 'Mitad Humana - hoja de prueba.pdf'
    assert _pages_in(paths[0]) == 2


def test_the_reading_pdf_has_a_page_per_plan_page(qapp, tmp_path):
    app = _app(tmp_path)
    bk = b.new_book(app.books, 'Mitad Humana', ['A.txt', 'B.txt'])
    r, _ = app._books_renderer(bk)
    paths = app._books_export(bk, 'read')
    assert os.path.basename(paths[0]) == 'Mitad Humana - lectura.pdf'
    assert _pages_in(paths[0]) == len(r.plan.pages)


def test_exporting_a_book_with_nothing_to_print_writes_nothing(qapp, tmp_path):
    app = _app(tmp_path)
    bk = b.new_book(app.books, 'Vacío', [])
    assert app._books_export(bk, 'duplex') == []
    assert not (tmp_path / 'book_packer').exists()


def test_an_unknown_export_kind_is_an_error(qapp, tmp_path):
    app = _app(tmp_path)
    bk = b.new_book(app.books, 'Mitad Humana', ['A.txt'])
    with pytest.raises(ValueError):
        app._books_export(bk, 'otra-cosa')


# ── seguir lo que pasa en F3 ─────────────────────────────────────────────────

def _with_books(app):
    b.new_book(app.books, 'Uno', ['A.txt', 'B.txt'])
    b.new_book(app.books, 'Dos', ['B.txt', 'C.txt'])
    app._books_save()


def _on_disk(tmp_path):
    return json.loads((tmp_path / 'books.json').read_text(encoding='utf-8'))['libros']


def test_renaming_a_chapter_in_f3_updates_every_book_and_the_file(tmp_path):
    app = _app(tmp_path)
    _with_books(app)
    app.book_ring.index = 2                           # fila B
    app.book_view.editor.text.return_value = 'Nuevo'
    app._book_try_rename()
    assert [x['capitulos'] for x in _on_disk(tmp_path)] == [
        ['A.txt', 'Nuevo.txt'], ['Nuevo.txt', 'C.txt']]


def test_deleting_a_chapter_in_f3_takes_it_out_of_the_books(tmp_path):
    app = _app(tmp_path)
    _with_books(app)
    app.book_ring.index = 2                           # fila B
    app._book_send_to_zero()
    assert [x['capitulos'] for x in _on_disk(tmp_path)] == [['A.txt'], ['C.txt']]


def test_merging_chapters_in_f3_takes_the_merged_ones_out_of_the_books(tmp_path):
    app = _app(tmp_path, ('.', 'A.txt', 'B.txt'))
    b.new_book(app.books, 'Uno', ['A.txt', 'B.txt'])
    app._books_save()
    app.book_ring.index = 0
    app._book_merge_prompt()
    app.book_view.editor.text.return_value = 'M'
    app._book_do_merge()
    assert _on_disk(tmp_path)[0]['capitulos'] == []


def test_a_rename_that_no_book_cares_about_does_not_touch_the_file(tmp_path):
    app = _app(tmp_path)
    _with_books(app)
    antes = (tmp_path / 'books.json').stat().st_mtime_ns
    app.book_ring.index = 2
    app._books_on_chapter_renamed('Nadie.txt', 'Otro.txt')
    assert (tmp_path / 'books.json').stat().st_mtime_ns == antes


def test_without_a_catalog_file_f3_does_not_create_one(tmp_path):
    app = _app(tmp_path)
    app.book_ring.index = 2
    app.book_view.editor.text.return_value = 'Nuevo'
    app._book_try_rename()
    assert not (tmp_path / 'books.json').exists()


# ── el esqueleto llega al libro impreso ──────────────────────────────────────

def test_the_printed_book_follows_prologue_chapters_epilogue(qapp, tmp_path):
    app = _app(tmp_path)
    bk = b.new_book(app.books, 'Mitad Humana', ['A.txt'])
    b.assign(bk, 'epilogo', 'C.txt')
    b.assign(bk, 'prologo', 'B.txt')
    r, missing = app._books_renderer(bk)
    assert r.titles == ['Prólogo', 'A', 'Epílogo'] and missing == []


def test_the_prologue_and_epilogue_print_without_their_file_title(qapp, tmp_path):
    """Federico: prólogo y epílogo sin título impreso. El índice sí los nombra."""
    app = _app(tmp_path)
    bk = b.new_book(app.books, 'Mitad Humana', ['A.txt'])
    b.assign(bk, 'prologo', 'B.txt')
    r, _ = app._books_renderer(bk)
    assert r.show_title == [False, True]


def test_the_dedication_is_its_own_page_not_a_chapter(qapp, tmp_path):
    app = _app(tmp_path)
    bk = b.new_book(app.books, 'Mitad Humana', ['A.txt'])
    b.assign(bk, 'dedicatoria', 'B.txt')
    r, _ = app._books_renderer(bk)
    assert r.titles == ['A']                                # no es un capítulo
    assert any(p.kind == 'dedication' for p in r.plan.pages)
    assert 'B' in r.dedication or 'B.txt' in r.dedication or r.dedication


def test_the_dedication_text_is_the_files_lines_without_separators(qapp, tmp_path):
    app = _app(tmp_path)
    (tmp_path / 'I' / 'Dedic.txt').write_text('.\nPara mi madre,\n.\nque me enseñó a leer.\n.\n',
                                              encoding='utf-8')
    app._library_path_cache['Dedic.txt'] = str(tmp_path / 'I' / 'Dedic.txt')
    bk = b.new_book(app.books, 'Mitad Humana', ['A.txt'])
    b.assign(bk, 'dedicatoria', 'Dedic.txt')
    r, _ = app._books_renderer(bk)
    assert r.dedication == 'Para mi madre,\nque me enseñó a leer.'


def test_an_empty_dedication_role_has_no_dedication_page(qapp, tmp_path):
    app = _app(tmp_path)
    bk = b.new_book(app.books, 'Mitad Humana', ['A.txt'])
    r, _ = app._books_renderer(bk)
    assert not any(p.kind == 'dedication' for p in r.plan.pages)


def test_a_missing_role_file_is_reported(qapp, tmp_path):
    app = _app(tmp_path)
    bk = b.new_book(app.books, 'Mitad Humana', ['A.txt'])
    b.assign(bk, 'prologo', 'Fantasma.txt')
    b.assign(bk, 'dedicatoria', 'OtroFantasma.txt')
    r, missing = app._books_renderer(bk)
    assert sorted(missing) == ['Fantasma.txt', 'OtroFantasma.txt'] and r.titles == ['A']


def test_the_cover_switch_reaches_the_renderer(qapp, tmp_path):
    app = _app(tmp_path)
    bk = b.new_book(app.books, 'Mitad Humana', ['A.txt'])
    r, _ = app._books_renderer(bk)
    assert r.plan.pages[0].kind == 'cover'
    bk['portada'] = False
    r, _ = app._books_renderer(bk)
    assert r.plan.pages[0].kind == 'title'


def test_the_reference_switch_reaches_the_renderer(qapp, tmp_path):
    app = _app(tmp_path)
    bk = b.new_book(app.books, 'Mitad Humana', ['A.txt'])
    r, _ = app._books_renderer(bk)
    assert any(p.kind == 'reference' for p in r.plan.pages)
    bk['referencia'] = False
    r, _ = app._books_renderer(bk)
    assert not any(p.kind == 'reference' for p in r.plan.pages)


def test_the_reference_sends_the_reader_to_download_voider(qapp, tmp_path):
    """Federico: debería enviar a descargar Voider en www.godplaystheartist.com."""
    app = _app(tmp_path)
    texto = app._books_reference_text()
    assert 'Voider' in texto and 'www.godplaystheartist.com' in texto
    assert 'escarg' in texto                              # "Descargalo en …"


def test_the_reference_page_carries_that_text(qapp, tmp_path):
    app = _app(tmp_path)
    bk = b.new_book(app.books, 'Mitad Humana', ['A.txt'])
    r, _ = app._books_renderer(bk)
    assert r.reference == app._books_reference_text()


def test_the_link_and_the_text_can_be_changed_in_the_config(qapp, tmp_path):
    app = _app(tmp_path)
    app.config['book_reference_url'] = 'https://otra.página'
    assert app._books_reference_text().endswith('https://otra.página')
    app.config['book_reference_text'] = 'Hecho con Voider'
    assert app._books_reference_text().startswith('Hecho con Voider')


def test_an_empty_link_means_no_link_not_the_default(qapp, tmp_path):
    app = _app(tmp_path)
    app.config['book_reference_url'] = ''
    texto = app._books_reference_text()
    assert 'godplaystheartist' not in texto and 'escarg' not in texto


def test_a_book_with_only_a_prologue_can_be_printed(qapp, tmp_path):
    app = _app(tmp_path)
    bk = b.new_book(app.books, 'Chico', [])
    b.assign(bk, 'prologo', 'A.txt')
    assert len(app._books_export(bk, 'duplex')) == 1


# ── F8 sin haber pasado por F3 ───────────────────────────────────────────────

def test_the_available_chapters_load_the_library_if_f3_was_never_opened(tmp_path):
    """La lista de capítulos sale de la biblioteca de F3; si en esta sesión no se entró a
    F3 está vacía, y el selector de F8 no tenía nada que ofrecer."""
    app = _app(tmp_path)
    app._library_lines = []
    llamadas = []

    def cargar():
        llamadas.append(1)
        app._library_lines = ['.', 'A.txt', 'B.txt']
    app._load_library = cargar
    assert app._books_chapters_available() == ['A.txt', 'B.txt']
    assert llamadas == [1]


def test_an_already_loaded_library_is_not_read_again(tmp_path):
    app = _app(tmp_path)
    app._load_library = lambda: pytest.fail('no debería releer la biblioteca')
    assert app._books_chapters_available() == ['A.txt', 'B.txt', 'C.txt']
