"""El modelo de libros del empaquetador (F8): una lista guardada en un JSON.

Un capítulo es un single y un libro es un álbum: el libro REFERENCIA los
archivos de I/ por nombre, no los copia. El mismo capítulo puede estar en varios
libros, y editarlo una vez lo cambia en todos. Las variantes son otro capítulo
(F3 ya duplica con Alt+Shift+↑/↓).
"""
import json
import os

import pytest

import books as b


def _data():
    d = b.empty()
    b.new_book(d, 'Mitad Humana', ['Prologo.txt', 'Uno.txt', 'Dos.txt'])
    b.new_book(d, 'Mitad Humana (corto)', ['Prologo.txt', 'Dos.txt'])
    return d


# ── lo básico ────────────────────────────────────────────────────────────────

def test_an_empty_catalog_has_no_books():
    assert b.empty() == {'version': 1, 'libros': []}


def test_a_new_book_has_the_defaults():
    d = b.empty()
    bk = b.new_book(d, 'Mitad Humana')
    assert bk['titulo'] == 'Mitad Humana'
    assert bk['capitulos'] == []
    assert bk['hojas'] == 4               # hojas por cuadernillo
    assert bk['autor'] == '' and bk['colofon'] == ''
    assert d['libros'] == [bk]


def test_every_book_gets_its_own_id_that_survives_a_rename():
    d = _data()
    ids = [x['id'] for x in d['libros']]
    assert len(set(ids)) == 2
    b.rename_book(d['libros'][0], 'Otro titulo')
    assert [x['id'] for x in d['libros']] == ids


def test_ids_are_never_reused_after_a_delete():
    d = _data()
    primero = d['libros'][0]['id']
    b.delete_book(d, primero)
    nuevo = b.new_book(d, 'Tercero')
    assert nuevo['id'] != primero


def test_a_book_title_is_trimmed_and_never_empty():
    d = b.empty()
    assert b.new_book(d, '  Mitad  ')['titulo'] == 'Mitad'
    assert b.new_book(d, '   ')['titulo'] != ''


def test_find_returns_the_book_or_none():
    d = _data()
    bid = d['libros'][1]['id']
    assert b.find(d, bid)['titulo'] == 'Mitad Humana (corto)'
    assert b.find(d, 'no-existe') is None


# ── capítulos: el mismo en varios libros ─────────────────────────────────────

def test_the_same_chapter_can_be_in_several_books():
    d = _data()
    assert [x['titulo'] for x in b.books_containing(d, 'Prologo.txt')] == [
        'Mitad Humana', 'Mitad Humana (corto)']
    assert [x['titulo'] for x in b.books_containing(d, 'Uno.txt')] == ['Mitad Humana']
    assert b.books_containing(d, 'Nada.txt') == []


def test_a_chapter_is_added_at_the_end_or_at_a_position():
    d = _data()
    bk = d['libros'][1]
    assert b.add_chapter(bk, 'Tres.txt') is True
    assert bk['capitulos'] == ['Prologo.txt', 'Dos.txt', 'Tres.txt']
    assert b.add_chapter(bk, 'Cero.txt', at=0) is True
    assert bk['capitulos'][0] == 'Cero.txt'


def test_a_chapter_cannot_be_twice_in_the_same_book():
    d = _data()
    bk = d['libros'][0]
    assert b.add_chapter(bk, 'Uno.txt') is False
    assert bk['capitulos'].count('Uno.txt') == 1


def test_a_chapter_is_removed_from_one_book_only():
    d = _data()
    assert b.remove_chapter(d['libros'][0], 'Prologo.txt') is True
    assert 'Prologo.txt' not in d['libros'][0]['capitulos']
    assert 'Prologo.txt' in d['libros'][1]['capitulos']
    assert b.remove_chapter(d['libros'][0], 'Prologo.txt') is False


def test_chapters_move_up_and_down_without_wrapping():
    d = _data()
    bk = d['libros'][0]
    assert b.move_chapter(bk, 'Uno.txt', +1) is True
    assert bk['capitulos'] == ['Prologo.txt', 'Dos.txt', 'Uno.txt']
    assert b.move_chapter(bk, 'Uno.txt', +1) is False      # ya es el último
    assert b.move_chapter(bk, 'Prologo.txt', -1) is False  # ya es el primero
    assert bk['capitulos'] == ['Prologo.txt', 'Dos.txt', 'Uno.txt']


# ── renombrar o borrar un capítulo en F3 no puede romper los libros ──────────

def test_renaming_a_chapter_updates_every_book_that_has_it():
    d = _data()
    n = b.rename_chapter_everywhere(d, 'Prologo.txt', 'Intro.txt')
    assert n == 2
    assert d['libros'][0]['capitulos'][0] == 'Intro.txt'
    assert d['libros'][1]['capitulos'][0] == 'Intro.txt'


def test_renaming_keeps_the_position():
    d = _data()
    b.rename_chapter_everywhere(d, 'Uno.txt', 'Primero.txt')
    assert d['libros'][0]['capitulos'] == ['Prologo.txt', 'Primero.txt', 'Dos.txt']


def test_renaming_to_a_name_the_book_already_has_does_not_duplicate_it():
    d = _data()
    b.rename_chapter_everywhere(d, 'Uno.txt', 'Dos.txt')
    assert d['libros'][0]['capitulos'].count('Dos.txt') == 1


def test_dropping_a_chapter_takes_it_out_of_every_book():
    d = _data()
    assert b.drop_chapter_everywhere(d, 'Prologo.txt') == 2
    assert all('Prologo.txt' not in x['capitulos'] for x in d['libros'])


def test_missing_chapters_are_the_ones_whose_file_is_gone():
    d = _data()
    assert b.missing_chapters(d['libros'][0], {'Prologo.txt', 'Dos.txt'}) == ['Uno.txt']
    assert b.missing_chapters(d['libros'][0], {'Prologo.txt', 'Uno.txt', 'Dos.txt'}) == []


# ── libros: reordenar, borrar, duplicar, traer de F3 ─────────────────────────

def test_books_move_in_the_list():
    d = _data()
    primero = d['libros'][0]['id']
    assert b.move_book(d, primero, +1) is True
    assert d['libros'][1]['id'] == primero
    assert b.move_book(d, primero, +1) is False


def test_deleting_a_book_does_not_touch_the_others_chapters():
    d = _data()
    b.delete_book(d, d['libros'][0]['id'])
    assert len(d['libros']) == 1
    assert d['libros'][0]['capitulos'] == ['Prologo.txt', 'Dos.txt']


def test_a_duplicate_is_an_edition_with_the_same_chapters_and_no_shared_list():
    d = _data()
    copia = b.duplicate_book(d, d['libros'][0]['id'])
    assert copia['titulo'] == 'Mitad Humana (copia)'
    assert copia['capitulos'] == d['libros'][0]['capitulos']
    copia['capitulos'].append('Extra.txt')
    assert 'Extra.txt' not in d['libros'][0]['capitulos']
    assert copia['id'] != d['libros'][0]['id']
    assert d['libros'][1] is copia                       # justo debajo del original


def test_a_book_from_an_f3_group_skips_portals_and_dots():
    d = b.empty()
    bk = b.from_f3_group(d, 'Mitad Humana',
                         ['.', 'Uno.txt', '0.txt', 'Dos.txt', '.', 'Tres.txt'])
    assert bk['capitulos'] == ['Uno.txt', 'Dos.txt']


# ── guardar y cargar ─────────────────────────────────────────────────────────

def test_the_catalog_roundtrips_through_disk(tmp_path):
    p = str(tmp_path / 'books.json')
    d = _data()
    b.save(p, d)
    assert b.load(p) == d


def test_a_missing_file_loads_as_an_empty_catalog(tmp_path):
    assert b.load(str(tmp_path / 'no.json')) == b.empty()


def test_a_broken_file_loads_as_empty_and_is_left_alone(tmp_path):
    p = tmp_path / 'books.json'
    p.write_text('{no es json', encoding='utf-8')
    assert b.load(str(p)) == b.empty()
    assert p.read_text(encoding='utf-8') == '{no es json'


def test_loading_fills_in_what_an_old_file_lacks(tmp_path):
    p = tmp_path / 'books.json'
    p.write_text(json.dumps({'libros': [{'id': 'l1', 'titulo': 'A'}]}), encoding='utf-8')
    d = b.load(str(p))
    assert d['libros'][0]['capitulos'] == [] and d['libros'][0]['hojas'] == 4
    assert d['version'] == 1


def test_loading_drops_garbage_entries_and_duplicate_chapters(tmp_path):
    p = tmp_path / 'books.json'
    p.write_text(json.dumps({'libros': [
        'basura', 42,
        {'id': 'l1', 'titulo': 'A', 'capitulos': ['X.txt', 'X.txt', 7, 'Y.txt']}]}),
        encoding='utf-8')
    d = b.load(str(p))
    assert len(d['libros']) == 1
    assert d['libros'][0]['capitulos'] == ['X.txt', 'Y.txt']


def test_save_is_atomic_and_leaves_no_tmp(tmp_path):
    p = str(tmp_path / 'books.json')
    b.save(p, _data())
    assert [n for n in os.listdir(tmp_path) if n.endswith('.tmp')] == []


def test_save_keeps_the_last_good_version_as_a_bak(tmp_path):
    p = str(tmp_path / 'books.json')
    d = _data()
    b.save(p, d)
    d['libros'].pop()
    b.save(p, d)
    assert len(json.loads((tmp_path / 'books.json.bak').read_text(encoding='utf-8'))['libros']) == 2


def test_an_empty_save_does_not_overwrite_the_bak_with_nothing(tmp_path):
    p = str(tmp_path / 'books.json')
    b.save(p, _data())
    b.save(p, b.empty())                  # se vació el catálogo
    b.save(p, b.empty())                  # y otra vez
    assert len(json.loads((tmp_path / 'books.json.bak').read_text(encoding='utf-8'))['libros']) == 2


def test_the_file_is_readable_utf8_with_accents(tmp_path):
    p = tmp_path / 'books.json'
    d = b.empty()
    b.new_book(d, 'La visión', ['Él.txt'])
    b.save(str(p), d)
    assert 'visión' in p.read_text(encoding='utf-8')     # sin \u escapes
