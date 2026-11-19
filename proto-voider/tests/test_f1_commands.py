"""Comandos de F1: un renglón que empieza con `!` no se suelta al archivo, es una
orden para el texto que tiene F2.

El primero: `!rem vision` borra del archivo de F2 todas las líneas que NO tienen
la palabra. Las palabras siguen las reglas de Gravitor (espacio = todas, coma =
cualquiera, grav* / *grav / *grav*, sin mayúsculas ni acentos).
"""
import os
import types
from unittest.mock import MagicMock

import pytest

import f1_commands as c
import gravitor as g
from helpers import make_ring_app


# ── parse_command ────────────────────────────────────────────────────────────

def test_a_line_starting_with_bang_and_a_letter_is_a_command():
    assert c.parse_command('!rem vision') == ('rem', 'vision')


def test_the_name_is_case_insensitive_and_the_args_are_trimmed():
    assert c.parse_command('  !REM   luz  sombra  ') == ('rem', 'luz  sombra')


def test_a_command_without_args_is_still_a_command():
    assert c.parse_command('!rem') == ('rem', '')


def test_ordinary_writing_is_never_a_command():
    for text in ('hola', '¡hola!', 'hola !rem', '! algo', '!', '!!', '!1', '', '   ',
                 'Qué bien!', '/0'):
        assert c.parse_command(text) is None, text


# ── remove_lines_without ─────────────────────────────────────────────────────

def _q(text):
    return g.parse_query(text)


def test_it_keeps_the_lines_with_the_word_and_drops_the_rest():
    out = c.remove_lines_without(['.', 'Una vision.', 'Nada.', 'Otra vision.', '.'], _q('vision'))
    assert out.lines == ['.', 'Una vision.', 'Otra vision.', '.']
    assert (out.kept, out.total) == (2, 3)


def test_whole_words_only_by_default():
    out = c.remove_lines_without(['.', 'La division.', 'Mi vision.', '.'], _q('vision'))
    assert out.lines == ['.', 'Mi vision.', '.']


def test_case_and_accents_are_ignored():
    out = c.remove_lines_without(['.', 'Una VISIÓN clara.', 'Nada.', '.'], _q('vision'))
    assert out.lines == ['.', 'Una VISIÓN clara.', '.']


def test_all_words_with_spaces():
    out = c.remove_lines_without(['.', 'Luz y sombra.', 'Sólo luz.', '.'], _q('luz sombra'))
    assert out.lines == ['.', 'Luz y sombra.', '.']


def test_any_word_with_a_comma():
    out = c.remove_lines_without(['.', 'Luz y sombra.', 'Sólo luz.', 'Nada.', '.'], _q('luz, sombra'))
    assert out.lines == ['.', 'Luz y sombra.', 'Sólo luz.', '.']


def test_wildcards_work():
    out = c.remove_lines_without(['.', 'La gravedad.', 'Un cuerpo.', '.'], _q('grav*'))
    assert out.lines == ['.', 'La gravedad.', '.']


def test_groups_that_end_up_empty_disappear_without_doubled_dots():
    lines = ['.', 'Nada uno.', 'Nada dos.', '.', 'Con vision.', '.', 'Nada tres.', '.']
    out = c.remove_lines_without(lines, _q('vision'))
    assert out.lines == ['.', 'Con vision.', '.']


def test_a_paragraph_that_loses_some_lines_stays_a_paragraph():
    lines = ['.', 'Con vision a.', 'Nada.', 'Con vision b.', '.']
    out = c.remove_lines_without(lines, _q('vision'))
    assert out.lines == ['.', 'Con vision a.', 'Con vision b.', '.']


def test_the_result_always_starts_and_ends_with_a_dot():
    out = c.remove_lines_without(['Una vision.', 'Nada.'], _q('vision'))
    assert out.lines == ['.', 'Una vision.', '.']


def test_blank_lines_and_carriage_returns_are_dropped():
    out = c.remove_lines_without(['', 'Una vision.\r', '', 'Nada.\r', ''], _q('vision'))
    assert out.lines == ['.', 'Una vision.', '.']


def test_if_no_line_has_the_word_there_is_nothing_to_write():
    """Para no vaciar el archivo por un error de tipeo."""
    assert c.remove_lines_without(['.', 'Nada.', 'Más nada.', '.'], _q('vision')) is None


def test_an_empty_file_has_nothing_to_write():
    assert c.remove_lines_without([], _q('vision')) is None
    assert c.remove_lines_without(['.'], _q('vision')) is None


def test_a_prose_line_stays_or_goes_whole():
    p = 'Si te invitan, primero miras. Ahi actuo a su vision del mundo. Todo lo demas.'
    out = c.remove_lines_without(['.', p, 'Otra cosa.', '.'], _q('vision'))
    assert out.lines == ['.', p, '.']


def test_everything_kept_means_the_same_lines_back():
    lines = ['.', 'Una vision.', '.', 'Otra vision.', '.']
    out = c.remove_lines_without(lines, _q('vision'))
    assert out.lines == lines and out.kept == out.total == 2


# ── el comando sobre un archivo: _cmd_rem_apply ──────────────────────────────

METHODS = ('_f1_command', '_cmd_rem_apply', '_cmd_rem', '_cmd_unknown',
           '_atomic_write_lines', '_undo_begin', '_undo_commit')


def _w(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8', newline='') as f:
        f.write(text)


def _app(tmp_path, content):
    from new_interface import FullscreenCircleApp
    app = make_ring_app(['.'])
    app.void_dir = str(tmp_path)
    path = str(tmp_path / 'I' / 'doc.txt')
    _w(path, content)
    app.f2_file = path
    app.current_file_path = str(tmp_path / 'I' / 'otro.txt')
    app._undo_capture = lambda *a, **k: None
    app._undo = None
    app._ipc = None
    app.load_doc_lines = MagicMock()
    app._cmd_message = MagicMock()
    for nm in METHODS:
        setattr(app, nm, types.MethodType(getattr(FullscreenCircleApp, nm), app))
    return app, path


def _read(path):
    with open(path, encoding='utf-8') as f:
        return f.read().splitlines()


def test_rem_rewrites_the_file_f2_has_open(tmp_path):
    app, path = _app(tmp_path, '.\nUna vision.\nNada.\n.\nOtra vision.\n.\n')
    status = app._cmd_rem_apply('vision')
    assert status == ('ok', 2, 3)
    assert _read(path) == ['.', 'Una vision.', '.', 'Otra vision.', '.']


def test_rem_leaves_a_bak_with_the_previous_content(tmp_path):
    app, path = _app(tmp_path, '.\nUna vision.\nNada.\n.\n')
    app._cmd_rem_apply('vision')
    assert _read(path + '.bak') == ['.', 'Una vision.', 'Nada.', '.']


def test_rem_does_not_touch_the_file_when_no_line_has_the_word(tmp_path):
    original = '.\nNada.\nMás nada.\n.\n'
    app, path = _app(tmp_path, original)
    status = app._cmd_rem_apply('vision')
    assert status[0] == 'nomatch'
    with open(path, encoding='utf-8') as f:
        assert f.read() == original
    assert not os.path.exists(path + '.bak')


def test_rem_without_a_word_does_nothing(tmp_path):
    original = '.\nUna vision.\n.\n'
    app, path = _app(tmp_path, original)
    assert app._cmd_rem_apply('   ')[0] == 'noquery'
    assert app._cmd_rem_apply(',,')[0] == 'noquery'
    with open(path, encoding='utf-8') as f:
        assert f.read() == original


def test_rem_on_a_missing_file_does_not_crash_or_create_it(tmp_path):
    app, path = _app(tmp_path, '.\nUna vision.\n.\n')
    os.remove(path)
    assert app._cmd_rem_apply('vision')[0] == 'missing'
    assert not os.path.exists(path)


def test_rem_is_one_undo_step(tmp_path):
    """Se agrupa entre _undo_begin y _undo_commit: Ctrl+Z lo revierte de una vez."""
    app, path = _app(tmp_path, '.\nUna vision.\nNada.\n.\n')
    pasos = []
    app._undo = MagicMock()
    app._undo.record_transaction = lambda txn, key=None: pasos.append((list(txn), key))
    app._undo_capture = lambda p, lines: app._undo_txn.append((p, lines))
    app._cmd_rem_apply('vision')
    assert len(pasos) == 1 and pasos[0][1][0] == 'rem'


def test_rem_reloads_f2s_ring_only_when_that_file_is_the_active_one(tmp_path):
    app, path = _app(tmp_path, '.\nUna vision.\nNada.\n.\n')
    app._cmd_rem_apply('vision')
    app.load_doc_lines.assert_not_called()
    app.current_file_path = path
    app._cmd_rem_apply('vision')
    app.load_doc_lines.assert_called_once()


def test_rem_handles_crlf_files(tmp_path):
    app, path = _app(tmp_path, '\r\nUna vision.\r\nNada.\r\n')
    app._cmd_rem_apply('vision')
    assert _read(path) == ['.', 'Una vision.', '.']


# ── el despachador: _f1_command ──────────────────────────────────────────────

def test_the_dispatcher_runs_rem_with_the_words(tmp_path):
    app, _ = _app(tmp_path, '.\nUna vision.\n.\n')
    app._cmd_rem = MagicMock()
    app._f1_command('rem', 'vision')
    app._cmd_rem.assert_called_once_with('vision')


def test_an_unknown_command_says_so_and_writes_nothing(tmp_path):
    app, path = _app(tmp_path, '.\nUna vision.\n.\n')
    app._cmd_unknown = MagicMock()
    app._cmd_rem_apply = MagicMock()
    app._f1_command('xyz', 'algo')
    app._cmd_unknown.assert_called_once_with('xyz')
    app._cmd_rem_apply.assert_not_called()


# ── cómo se engancha en F1 ───────────────────────────────────────────────────

def _f1(text, view=0):
    from new_interface import FullscreenCircleApp
    app = MagicMock()
    app.current_view = view
    app.entry.text.return_value = text
    app._handle_void_line = types.MethodType(FullscreenCircleApp._handle_void_line, app)
    return app


def test_enter_on_a_command_runs_it_and_does_not_write_the_line():
    app = _f1('!rem vision')
    app._handle_void_line()
    app._f1_command.assert_called_once_with('rem', 'vision')
    app._f1_commit_line.assert_not_called()
    app.entry.clear.assert_called()


def test_enter_on_ordinary_text_still_writes_it():
    app = _f1('una linea cualquiera')
    app._handle_void_line()
    app._f1_command.assert_not_called()
    app._f1_commit_line.assert_called_once_with('una linea cualquiera')


def test_a_command_is_not_run_from_other_views():
    app = _f1('!rem vision', view=4)         # F5 usa Enter para otra cosa
    app._handle_void_line()
    app._f1_command.assert_not_called()


def test_the_slash_zero_command_keeps_working():
    app = _f1('/0')
    app._handle_void_line()
    app._f1_scratch_jump.assert_called_once()
    app._f1_command.assert_not_called()


def test_the_command_methods_only_call_things_that_exist():
    """Los avisos usan Qt y no se pueden correr acá: un nombre mal escrito
    explotaría recién al usar el comando."""
    import inspect
    import re
    from new_interface import FullscreenCircleApp
    for nombre in ('_cmd_rem', '_cmd_unknown', '_f1_command'):
        fuente = inspect.getsource(getattr(FullscreenCircleApp, nombre))
        llamados = set(re.findall(r'self\.(_?[a-zA-Z_][a-zA-Z0-9_]*)\(', fuente))
        faltan = [n for n in sorted(llamados) if not hasattr(FullscreenCircleApp, n)]
        assert not faltan, f'{nombre} llama a métodos inexistentes: {faltan}'


def test_the_help_screen_mentions_it():
    from help_overlay import HELP
    assert any(k.startswith('!rem') for k, d in HELP)


# ── !sinpuntos: quitar los puntos separadores de un archivo ──────────────────
#
# Lo que hacía Ctrl+Shift+Delete (que nunca anduvo bien por la tecla), ahora como
# comando: todos los separadores de adentro se van y queda UN solo párrafo, con un
# punto al principio y otro al final (como Voider espera un archivo). Con eso Tab
# mezcla las líneas de todo el archivo de una vez.

def test_every_inner_separator_goes_and_one_paragraph_remains():
    out = c.remove_separators(['.', 'Uno.', 'Dos.', '.', 'Tres.', '.', 'Cuatro.', '.'])
    assert out.lines == ['.', 'Uno.', 'Dos.', 'Tres.', 'Cuatro.', '.']


def test_it_reports_how_many_separators_it_took_out():
    out = c.remove_separators(['.', 'Uno.', '.', 'Dos.', '.', 'Tres.', '.'])
    assert out.removed == 2 and out.kept == 3        # 4 puntos → quedan 2


def test_no_line_is_lost_or_reordered():
    lines = ['.', 'a', 'b', '.', 'c', '.', '.', 'd', '.']
    out = c.remove_separators(lines)
    assert [l for l in out.lines if l != '.'] == ['a', 'b', 'c', 'd']


def test_a_file_without_dots_gets_the_two_framing_dots():
    out = c.remove_separators(['Uno.', 'Dos.'])
    assert out.lines == ['.', 'Uno.', 'Dos.', '.'] and out.removed == 0


def test_blank_lines_and_carriage_returns_are_dropped_here_too():
    out = c.remove_separators(['', 'Uno.\r', '', '.\r', 'Dos.\r'])
    assert out.lines == ['.', 'Uno.', 'Dos.', '.']


def test_a_file_with_only_dots_or_nothing_has_nothing_to_write():
    assert c.remove_separators([]) is None
    assert c.remove_separators(['.', '.', '']) is None


def test_a_file_that_is_already_one_paragraph_is_reported_as_unchanged():
    lines = ['.', 'Uno.', 'Dos.', '.']
    out = c.remove_separators(lines)
    assert out.lines == lines and out.removed == 0


def _app2(tmp_path, content):
    app, path = _app(tmp_path, content)
    from new_interface import FullscreenCircleApp
    for nm in ('_cmd_sinpuntos_apply', '_cmd_sinpuntos'):
        setattr(app, nm, types.MethodType(getattr(FullscreenCircleApp, nm), app))
    return app, path


def test_sinpuntos_rewrites_the_file_f2_has_open(tmp_path):
    app, path = _app2(tmp_path, '.\nUno.\n.\nDos.\n.\nTres.\n.\n')
    assert app._cmd_sinpuntos_apply() == ('ok', 2, 3)
    assert _read(path) == ['.', 'Uno.', 'Dos.', 'Tres.', '.']


def test_sinpuntos_leaves_a_bak(tmp_path):
    app, path = _app2(tmp_path, '.\nUno.\n.\nDos.\n.\n')
    app._cmd_sinpuntos_apply()
    assert _read(path + '.bak') == ['.', 'Uno.', '.', 'Dos.', '.']


def test_sinpuntos_does_not_write_when_nothing_changes(tmp_path):
    app, path = _app2(tmp_path, '.\nUno.\nDos.\n.\n')
    assert app._cmd_sinpuntos_apply()[0] == 'same'
    assert not os.path.exists(path + '.bak')


def test_sinpuntos_on_an_empty_or_missing_file_does_nothing(tmp_path):
    app, path = _app2(tmp_path, '.\n.\n')
    assert app._cmd_sinpuntos_apply()[0] == 'empty'
    os.remove(path)
    assert app._cmd_sinpuntos_apply()[0] == 'missing'
    assert not os.path.exists(path)


def test_sinpuntos_is_one_undo_step(tmp_path):
    app, path = _app2(tmp_path, '.\nUno.\n.\nDos.\n.\n')
    pasos = []
    app._undo = MagicMock()
    app._undo.record_transaction = lambda txn, key=None: pasos.append(key)
    app._undo_capture = lambda p, lines: app._undo_txn.append((p, lines))
    app._cmd_sinpuntos_apply()
    assert len(pasos) == 1 and pasos[0][0] == 'sinpuntos'


def test_sinpuntos_reloads_f2s_ring_only_for_the_active_file(tmp_path):
    app, path = _app2(tmp_path, '.\nUno.\n.\nDos.\n.\n')
    app._cmd_sinpuntos_apply()
    app.load_doc_lines.assert_not_called()
    app.current_file_path = path
    app._cmd_sinpuntos_apply()                    # ya está en un párrafo
    app.load_doc_lines.assert_not_called()


def test_the_dispatcher_runs_sinpuntos(tmp_path):
    app, _ = _app2(tmp_path, '.\nUno.\n.\n')
    app._cmd_sinpuntos = MagicMock()
    app._f1_command('sinpuntos', '')
    app._cmd_sinpuntos.assert_called_once()


def test_the_unknown_command_hint_lists_both(tmp_path):
    import inspect
    from new_interface import FullscreenCircleApp
    fuente = inspect.getsource(FullscreenCircleApp._cmd_unknown)
    assert '!rem' in fuente and '!sinpuntos' in fuente


def test_sinpuntos_methods_only_call_things_that_exist():
    import inspect
    import re
    from new_interface import FullscreenCircleApp
    for nombre in ('_cmd_sinpuntos', '_cmd_sinpuntos_apply'):
        fuente = inspect.getsource(getattr(FullscreenCircleApp, nombre))
        llamados = set(re.findall(r'self\.(_?[a-zA-Z_][a-zA-Z0-9_]*)\(', fuente))
        faltan = [n for n in sorted(llamados) if not hasattr(FullscreenCircleApp, n)]
        assert not faltan, f'{nombre} llama a métodos inexistentes: {faltan}'


def test_the_help_screen_mentions_sinpuntos():
    from help_overlay import HELP
    assert any(k.startswith('!sinpuntos') for k, d in HELP)


def test_the_periods_ending_sentences_are_never_touched():
    """Se quitan los SEPARADORES (una línea que es sólo un punto), no los puntos
    al final de cada oración."""
    lines = ['.', 'Una oración.', 'Otra más...', 'Y una con 3.5 y U.S.A.', '.',
             'Fin.', '.']
    out = c.remove_separators(lines)
    assert out.lines == ['.', 'Una oración.', 'Otra más...', 'Y una con 3.5 y U.S.A.',
                         'Fin.', '.']


def test_a_separator_with_spaces_around_it_still_counts_as_a_separator():
    out = c.remove_separators(['.', 'Uno.', ' . ', 'Dos.', '.'])
    assert out.lines == ['.', 'Uno.', 'Dos.', '.']


def test_two_dots_in_a_row_inside_a_line_are_text_not_a_separator():
    out = c.remove_separators(['.', 'Uno.', '..', 'Dos.', '.'])
    assert '..' in out.lines
