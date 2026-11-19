"""Gravitor — buscar todas las oraciones que tienen tal o tales palabras y juntarlas.

El motor es puro (sin Qt): parsea lo que se escribe, decide qué oraciones
coinciden y recorre las fuentes (tus textos en I/, o una muestra al azar de
los libros de O/).

Reglas de lo que se escribe:
  luz sombra    → las dos palabras en la misma oración (el espacio es "y")
  luz, sombra   → cualquiera de las dos (la coma es "o")
  grav          → sólo la palabra "grav"
  grav*         → las que EMPIEZAN con grav      *grav → las que TERMINAN
  *grav*        → las que la CONTIENEN
  sin distinguir mayúsculas ni acentos.
"""
import os
import random

import pytest

import gravitor as g


# ── parse_query ──────────────────────────────────────────────────────────────

def test_a_blank_query_is_nothing():
    assert g.parse_query('') is None
    assert g.parse_query('   ') is None
    assert g.parse_query(',,, ') is None
    assert g.parse_query('*') is None


def test_spaces_mean_all_words():
    q = g.parse_query('luz sombra')
    assert q.mode == 'all' and len(q.terms) == 2


def test_a_comma_means_any_word():
    q = g.parse_query('luz, sombra')
    assert q.mode == 'any' and len(q.terms) == 2


def test_a_single_word_is_one_term():
    q = g.parse_query('luz')
    assert len(q.terms) == 1


# ── matches: la palabra entera, y los comodines ──────────────────────────────

def test_a_bare_word_only_matches_the_whole_word():
    q = g.parse_query('grav')
    assert q.matches('Esto es grav y nada más.')
    assert not q.matches('La gravedad nos une.')
    assert not q.matches('Un cuerpo gravita.')


def test_a_trailing_star_matches_words_that_start_with_it():
    q = g.parse_query('grav*')
    assert q.matches('La gravedad nos une.')
    assert q.matches('Un cuerpo gravita.')
    assert q.matches('grav')
    assert not q.matches('Es una aggravation.')


def test_a_leading_star_matches_words_that_end_with_it():
    q = g.parse_query('*grav')
    assert q.matches('Es un subgrav.')
    assert q.matches('grav')
    assert not q.matches('La gravedad nos une.')


def test_stars_on_both_sides_match_anywhere_inside_a_word():
    q = g.parse_query('*grav*')
    assert q.matches('Es una aggravation.')
    assert q.matches('La gravedad nos une.')
    assert not q.matches('Nada de eso aquí.')


def test_case_and_accents_are_ignored():
    q = g.parse_query('accion')
    assert q.matches('La ACCIÓN decide.')
    assert q.matches('la acción')
    q2 = g.parse_query('ÁRBOL')
    assert q2.matches('un arbol, dos')


def test_punctuation_does_not_hide_a_word():
    q = g.parse_query('luz')
    assert q.matches('Dijo: «luz», y hubo luz.')
    assert q.matches('luz.')
    assert q.matches('(luz)')


def test_all_mode_needs_every_word_in_the_same_sentence():
    q = g.parse_query('luz sombra')
    assert q.matches('La luz y la sombra.')
    assert not q.matches('Sólo la luz.')
    assert not q.matches('Sólo la sombra.')


def test_any_mode_needs_just_one():
    q = g.parse_query('luz, sombra')
    assert q.matches('Sólo la luz.')
    assert q.matches('Sólo la sombra.')
    assert q.matches('La luz y la sombra.')
    assert not q.matches('Ni una ni otra cosa.')


def test_wildcards_work_inside_a_multi_word_query():
    q = g.parse_query('grav* luz')
    assert q.matches('La gravedad y la luz.')
    assert not q.matches('La gravedad sola.')


def test_empty_sentences_never_match():
    assert not g.parse_query('luz').matches('')
    assert not g.parse_query('luz').matches('.')


# ── might_match: la prueba barata sobre un párrafo entero ────────────────────

def test_might_match_never_rejects_a_paragraph_that_could_match():
    q = g.parse_query('luz sombra')
    assert q.might_match(g.fold('hay luz y también sombra aquí'))
    assert not q.might_match(g.fold('sólo hay luz aquí'))


def test_might_match_in_any_mode_needs_one_core():
    q = g.parse_query('luz, sombra')
    assert q.might_match(g.fold('sólo hay luz aquí'))
    assert not q.might_match(g.fold('nada'))


def test_might_match_is_a_superset_of_matches():
    """La prueba barata puede dejar pasar de más, nunca de menos."""
    for text in ('grav*', '*grav', '*grav*', 'luz sombra', 'luz, sombra'):
        q = g.parse_query(text)
        for s in ('La gravedad y la luz.', 'subgrav', 'Sombra y luz', 'nada',
                  'aggravation de la sombra'):
            if q.matches(s):
                assert q.might_match(g.fold(s)), (text, s)


# ── fold ─────────────────────────────────────────────────────────────────────

def test_fold_lowercases_and_strips_accents():
    assert g.fold('ÁRBOL Ñandú Acción') == 'arbol nandu accion'


# ── sanitize_name ────────────────────────────────────────────────────────────

def test_the_name_is_what_you_typed():
    assert g.sanitize_name('luz sombra') == 'luz sombra'
    assert g.sanitize_name('luz, sombra') == 'luz, sombra'
    assert g.sanitize_name('grav*') == 'grav_'        # '*' no vale en Windows


def test_characters_a_filename_cannot_have_are_replaced():
    n = g.sanitize_name('a/b\\c:d?e"f<g>h|i*j')
    for ch in '/\\:?"<>|*':
        assert ch not in n


def test_the_name_is_trimmed_and_never_empty_or_a_reserved_dot():
    assert g.sanitize_name('  luz  ') == 'luz'
    assert g.sanitize_name('...') != '...'
    assert g.sanitize_name('') != ''


def test_the_name_has_a_sane_length():
    assert len(g.sanitize_name('a' * 500)) <= 120


# ── sentences_from_lines: un archivo de I/ ya viene una oración por línea ────

def test_i_lines_skip_dots_and_blanks():
    assert g.sentences_from_lines(['.', 'Uno.', '', '.', ' Dos. ', '.']) == ['Uno.', 'Dos.']


# ── search_i ─────────────────────────────────────────────────────────────────

def _w(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(text)


def _i(tmp_path):
    d = tmp_path / 'I'
    _w(str(d / 'a.txt'), '.\nLa luz entra.\n.\nNada de eso.\n.\nLuz y sombra.\n.\n')
    _w(str(d / 'sub' / 'b.txt'), '.\nOtra luz más.\n.\n')
    return str(d)


def test_search_i_finds_matching_sentences_across_files_and_subfolders(tmp_path):
    r = g.search_i(_i(tmp_path), g.parse_query('luz'))
    assert sorted(r.sentences) == ['La luz entra.', 'Luz y sombra.', 'Otra luz más.']
    assert r.files == 2


def test_search_i_skips_the_scratch_file(tmp_path):
    d = _i(tmp_path)
    _w(os.path.join(d, '0.txt'), '.\nLuz del cuaderno.\n.\n')
    r = g.search_i(d, g.parse_query('luz'))
    assert 'Luz del cuaderno.' not in r.sentences


def test_search_i_skips_files_gravitor_made_before(tmp_path):
    """Sin esto, la segunda búsqueda encontraría los resultados de la primera."""
    d = _i(tmp_path)
    _w(os.path.join(d, 'luz.txt'), '.\nLa luz entra.\n.\n')
    r = g.search_i(d, g.parse_query('luz'), skip={'luz.txt'})
    assert r.sentences.count('La luz entra.') == 1


def test_search_i_ignores_non_txt_files(tmp_path):
    d = _i(tmp_path)
    _w(os.path.join(d, 'x.bak'), 'Luz del backup.\n')
    r = g.search_i(d, g.parse_query('luz'))
    assert 'Luz del backup.' not in r.sentences


def test_search_i_removes_repeated_sentences(tmp_path):
    d = str(tmp_path / 'I')
    _w(os.path.join(d, 'a.txt'), '.\nLa luz.\n.\nLa luz.\n.\n')
    _w(os.path.join(d, 'b.txt'), '.\nLa luz.\n.\n')
    r = g.search_i(d, g.parse_query('luz'))
    assert r.sentences == ['La luz.']


def test_search_i_with_nothing_found_is_an_empty_result(tmp_path):
    r = g.search_i(_i(tmp_path), g.parse_query('inexistente'))
    assert r.sentences == [] and r.files == 2


def test_search_i_on_a_missing_folder_is_not_a_crash(tmp_path):
    r = g.search_i(str(tmp_path / 'no'), g.parse_query('luz'))
    assert r.sentences == [] and r.files == 0


def test_search_i_stops_at_the_cap_and_says_so(tmp_path):
    d = str(tmp_path / 'I')
    _w(os.path.join(d, 'a.txt'), '.\n' + '\n.\n'.join(f'Luz {i}.' for i in range(50)) + '\n.\n')
    r = g.search_i(d, g.parse_query('luz'), cap=10)
    assert len(r.sentences) == 10 and r.capped is True


def test_search_i_can_be_cancelled_from_the_progress_callback(tmp_path):
    d = _i(tmp_path)
    r = g.search_i(d, g.parse_query('luz'), on_progress=lambda i, n, label: False)
    assert r.cancelled is True


def test_search_i_reports_progress(tmp_path):
    visto = []
    g.search_i(_i(tmp_path), g.parse_query('luz'),
               on_progress=lambda i, n, label: visto.append((i, n)) or True)
    assert visto and visto[-1][0] == visto[-1][1]


# ── search_o: una muestra al azar de libros ──────────────────────────────────

RAW_BOOK = ('*** START OF THE PROJECT GUTENBERG EBOOK X ***\n\n'
            'Primer parrafo sin nada\ninteresante aqui.\n\n'
            'La luz de la\nmañana entro por la ventana. Otra frase sin eso.\n\n'
            '*** END OF THE PROJECT GUTENBERG EBOOK X ***\n')


def _split(raw):
    """Un separador de oraciones simple para los tests."""
    import re
    flat = ' '.join(raw.split())
    return [s.strip() for s in re.split(r'(?<=[.!?])\s+', flat) if s.strip()]


def _o(tmp_path, n=5):
    d = tmp_path / 'O'
    for i in range(n):
        _w(str(d / f'libro{i}.txt'), RAW_BOOK)
    return str(d)


def test_search_o_only_looks_at_the_requested_number_of_books(tmp_path):
    d = _o(tmp_path, 10)
    r = g.search_o(d, g.parse_query('luz'), 3, _split, rng=random.Random(1))
    assert r.books == 3


def test_search_o_never_asks_for_more_books_than_there_are(tmp_path):
    d = _o(tmp_path, 4)
    r = g.search_o(d, g.parse_query('luz'), 300, _split, rng=random.Random(1))
    assert r.books == 4


def test_search_o_returns_whole_sentences_not_wrapped_fragments(tmp_path):
    d = _o(tmp_path, 1)
    r = g.search_o(d, g.parse_query('luz'), 5, _split, rng=random.Random(1))
    assert r.sentences == ['La luz de la mañana entro por la ventana.']


def test_search_o_strips_the_gutenberg_boilerplate(tmp_path):
    d = str(tmp_path / 'O')
    _w(os.path.join(d, 'x.txt'),
       'Produced by luz Team\n*** START OF THE PROJECT GUTENBERG EBOOK X ***\n\n'
       'Nada.\n\n*** END OF THE PROJECT GUTENBERG EBOOK X ***\nLicense: luz\n')
    r = g.search_o(d, g.parse_query('luz'), 5, _split, rng=random.Random(1))
    assert r.sentences == []


def test_search_o_only_splits_paragraphs_that_could_match(tmp_path):
    """El ahorro: el separador de oraciones es lo caro, y sólo corre donde hace falta."""
    d = _o(tmp_path, 1)
    vistos = []

    def espia(raw):
        vistos.append(raw)
        return _split(raw)
    g.search_o(d, g.parse_query('luz'), 5, espia, rng=random.Random(1))
    assert len(vistos) == 1 and 'luz' in vistos[0]


def test_search_o_is_random_but_repeatable_with_a_seed(tmp_path):
    d = str(tmp_path / 'O')
    for i in range(30):
        _w(os.path.join(d, f'l{i}.txt'), f'Frase numero {i} con luz.\n')
    a = g.search_o(d, g.parse_query('luz'), 5, _split, rng=random.Random(7))
    b = g.search_o(d, g.parse_query('luz'), 5, _split, rng=random.Random(7))
    c = g.search_o(d, g.parse_query('luz'), 5, _split, rng=random.Random(8))
    assert a.sentences == b.sentences
    assert a.sentences != c.sentences


def test_search_o_unavailable_when_the_corpus_is_empty_or_missing(tmp_path):
    vacio = tmp_path / 'O'
    vacio.mkdir()
    (vacio / '.working_set.json').write_text('{}')
    assert g.search_o(str(vacio), g.parse_query('luz'), 5, _split).unavailable is True
    assert g.search_o(str(tmp_path / 'no'), g.parse_query('luz'), 5, _split).unavailable is True


def test_search_o_can_be_cancelled(tmp_path):
    d = _o(tmp_path, 10)
    r = g.search_o(d, g.parse_query('luz'), 10, _split,
                   on_progress=lambda i, n, label: False)
    assert r.cancelled is True


def test_search_o_stops_at_the_cap(tmp_path):
    d = str(tmp_path / 'O')
    for i in range(20):
        _w(os.path.join(d, f'l{i}.txt'), f'Frase numero {i} con luz.\n')
    r = g.search_o(d, g.parse_query('luz'), 20, _split, cap=5, rng=random.Random(1))
    assert len(r.sentences) == 5 and r.capped is True


def test_search_o_skips_an_unreadable_book_and_goes_on(tmp_path):
    d = _o(tmp_path, 2)
    os.mkdir(os.path.join(d, 'carpeta.txt'))      # un directorio que se llama .txt
    r = g.search_o(d, g.parse_query('luz'), 10, _split, rng=random.Random(1))
    assert r.sentences


# ── search: las dos fuentes ──────────────────────────────────────────────────

def test_search_source_i_only_touches_i(tmp_path):
    r = g.search('i', g.parse_query('luz'), i_dir=_i(tmp_path), o_dir=_o(tmp_path),
                 n_books=3, to_sentences=_split, rng=random.Random(1))
    assert r.books == 0 and r.files == 2


def test_search_source_o_only_touches_o(tmp_path):
    r = g.search('o', g.parse_query('luz'), i_dir=_i(tmp_path), o_dir=_o(tmp_path),
                 n_books=3, to_sentences=_split, rng=random.Random(1))
    assert r.files == 0 and r.books == 3


def test_search_both_joins_the_two_with_i_first(tmp_path):
    r = g.search('both', g.parse_query('luz'), i_dir=_i(tmp_path), o_dir=_o(tmp_path),
                 n_books=2, to_sentences=_split, rng=random.Random(1))
    assert r.files == 2 and r.books == 2
    assert r.sentences[0] in ('La luz entra.', 'Luz y sombra.', 'Otra luz más.')
    assert 'La luz de la mañana entro por la ventana.' in r.sentences


def test_search_both_with_the_corpus_missing_still_returns_i(tmp_path):
    r = g.search('both', g.parse_query('luz'), i_dir=_i(tmp_path),
                 o_dir=str(tmp_path / 'no'), n_books=3, to_sentences=_split)
    assert r.unavailable is True
    assert 'La luz entra.' in r.sentences


def test_search_cap_applies_to_the_total(tmp_path):
    d = str(tmp_path / 'I')
    _w(os.path.join(d, 'a.txt'), '.\n' + '\n.\n'.join(f'Luz {i}.' for i in range(30)) + '\n.\n')
    r = g.search('both', g.parse_query('luz'), i_dir=d, o_dir=_o(tmp_path),
                 n_books=3, to_sentences=_split, cap=10, rng=random.Random(1))
    assert len(r.sentences) == 10 and r.capped is True


def test_search_summary_says_where_it_looked(tmp_path):
    r = g.search('both', g.parse_query('luz'), i_dir=_i(tmp_path), o_dir=_o(tmp_path),
                 n_books=3, to_sentences=_split, rng=random.Random(1))
    s = r.summary()
    assert '3 libros' in s and '2 archivos' in s and str(len(r.sentences)) in s


# ── result_lines: el archivo que se escribe ──────────────────────────────────

def test_result_lines_are_one_sentence_per_paragraph_in_the_dot_model():
    assert g.result_lines(['Uno.', 'Dos.']) == ['.', 'Uno.', '.', 'Dos.', '.']


def test_result_lines_of_nothing_is_empty():
    assert g.result_lines([]) == []


# ── el registro de archivos que Gravitor generó ──────────────────────────────

def test_the_registry_roundtrips(tmp_path):
    p = str(tmp_path / '.gravitor.json')
    assert g.load_registry(p) == set()
    g.add_to_registry(p, 'luz.txt')
    g.add_to_registry(p, 'sombra.txt')
    g.add_to_registry(p, 'luz.txt')
    assert g.load_registry(p) == {'luz.txt', 'sombra.txt'}


def test_a_broken_registry_is_an_empty_one(tmp_path):
    p = tmp_path / '.gravitor.json'
    p.write_text('{no es json')
    assert g.load_registry(str(p)) == set()


# ── velocidad: probada contra un texto grande, no a ojo ──────────────────────

def test_fold_is_fast_on_a_large_text():
    import time
    texto = ('Ésta es la acción del árbol, y también la gravedad. ' * 4000)   # ~200 KB
    t = time.perf_counter()
    for _ in range(20):
        g.fold(texto)
    assert time.perf_counter() - t < 0.25


def test_fold_keeps_plain_ascii_untouched_apart_from_case():
    assert g.fold('Hello World') == 'hello world'


def test_search_i_does_not_fold_sentence_by_sentence_in_files_that_cannot_match(tmp_path, monkeypatch):
    """Un archivo sin ninguna de las palabras se descarta de un vistazo."""
    d = str(tmp_path / 'I')
    _w(os.path.join(d, 'a.txt'), '.\n' + '\n.\n'.join(f'Nada de nada {i}.' for i in range(200)) + '\n.\n')
    q = g.parse_query('luz')
    llamadas = []
    original = q.matches
    monkeypatch.setattr(q, 'matches', lambda s: llamadas.append(s) or original(s), raising=False)
    r = g.search_i(d, q)
    assert r.sentences == [] and llamadas == []


# ── I/ también tiene párrafos de una sola línea (prosa, no el modelo de puntos) ─
#
# Un archivo como "Escrito experimento 2.txt" guarda cada párrafo en UNA línea
# con varias oraciones. Buscar "vision" devolvía el párrafo entero, y después
# aparecían oraciones sin la palabra. Una oración, no una línea.

PROSA = ('\r\n\r\nSi te invitan a una casa, primero miras la casa. A las reglas me adapto. '
         'Ahi actuo a su vision del mundo. Todo a partir de lo que me dicen.\r\n\r\n'
         'Otro parrafo sin nada.\r\n')


def _prosa(tmp_path):
    d = str(tmp_path / 'I')
    _w(os.path.join(d, 'prosa.txt'), PROSA)
    return d


def test_a_prose_paragraph_gives_only_the_sentence_with_the_word(tmp_path):
    r = g.search_i(_prosa(tmp_path), g.parse_query('vision'), to_sentences=_split)
    assert r.sentences == ['Ahi actuo a su vision del mundo.']


def test_no_result_has_a_sentence_without_the_word(tmp_path):
    q = g.parse_query('vision')
    r = g.search_i(_prosa(tmp_path), q, to_sentences=_split)
    assert r.sentences and all(q.matches(s) for s in r.sentences)


def test_crlf_and_blank_lines_are_not_a_problem(tmp_path):
    r = g.search_i(_prosa(tmp_path), g.parse_query('vision'), to_sentences=_split)
    assert all('\r' not in s and s for s in r.sentences)


def test_two_matching_sentences_in_one_line_come_out_separately(tmp_path):
    d = str(tmp_path / 'I')
    _w(os.path.join(d, 'a.txt'), 'Una vision. Nada. Otra vision mas.\n')
    r = g.search_i(d, g.parse_query('vision'), to_sentences=_split)
    assert r.sentences == ['Una vision.', 'Otra vision mas.']


def test_the_splitter_only_runs_on_lines_that_could_match(tmp_path):
    """El separador es lo caro: sólo corre donde la palabra puede estar."""
    d = _prosa(tmp_path)
    vistos = []

    def espia(raw):
        vistos.append(raw)
        return _split(raw)
    g.search_i(d, g.parse_query('vision'), to_sentences=espia)
    assert len(vistos) == 1 and 'vision' in vistos[0]


def test_a_dot_model_file_gives_the_same_result_with_or_without_the_splitter(tmp_path):
    d = _i(tmp_path)
    q = g.parse_query('luz')
    a = g.search_i(d, q)
    b = g.search_i(d, q, to_sentences=_split)
    assert sorted(a.sentences) == sorted(b.sentences)


def test_a_part_that_is_only_a_dot_is_never_a_result(tmp_path):
    d = _prosa(tmp_path)
    r = g.search_i(d, g.parse_query('vision'),
                   to_sentences=lambda raw: ['.'] + _split(raw))
    assert '.' not in r.sentences


def test_search_passes_the_splitter_to_the_i_source(tmp_path):
    d = _prosa(tmp_path)
    r = g.search('i', g.parse_query('vision'), i_dir=d, o_dir=str(tmp_path / 'no'),
                 n_books=1, to_sentences=_split)
    assert r.sentences == ['Ahi actuo a su vision del mundo.']


def test_a_word_that_is_only_part_of_another_does_not_pull_the_paragraph(tmp_path):
    """'division' contiene 'vision': pasa la prueba barata pero no coincide."""
    d = str(tmp_path / 'I')
    _w(os.path.join(d, 'a.txt'), 'La division de todo. Nada mas aqui.\n')
    r = g.search_i(d, g.parse_query('vision'), to_sentences=_split)
    assert r.sentences == []
