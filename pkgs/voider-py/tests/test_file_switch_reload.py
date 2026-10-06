"""F1 Alt+↑/↓ cambia de archivo: el anillo tiene que ser el del archivo NUEVO.

El bug: switch_to_file cambiaba current_file_path sin recargar line_ring, así
que el próximo Enter (o cualquier guardado) escribía el contenido del archivo
anterior encima del nuevo. Un capítulo entero pisado con una tecla.
"""
import types
from unittest.mock import MagicMock

import pytest

pytest.importorskip("PyQt6")


def _app(tmp_path):
    from new_interface import FullscreenCircleApp as App

    class _A:
        pass
    a = _A()
    i = tmp_path / 'I'
    i.mkdir()
    (i / 'a.txt').write_text('.\nlinea de A uno\nlinea de A dos\n', encoding='utf-8')
    (i / 'b.txt').write_text('.\nlinea de B\n', encoding='utf-8')
    a.book_dir = str(i)
    a.void_dir = str(tmp_path)
    a.current_file_path = str(i / 'a.txt')
    a.current_view = 0
    a.circular_view = None
    a._undo = None
    a._ipc = None
    a.entry = MagicMock()
    for n in ('scan_txt_files', 'show_next_file', 'show_previous_file',
              'switch_to_file', 'load_doc_lines', 'auto_save_circular',
              '_f1_commit_line', '_f1_show_current', '_undo_capture',
              '_rescue_on_large_shrink', '_read_lines_or_none',
              '_restore_last_line', '_save_last_line', '_last_lines_path'):
        setattr(a, n, types.MethodType(getattr(App, n), a))
    a.load_doc_lines()
    a.scan_txt_files()
    return a, i


def test_switching_file_loads_the_new_files_lines(tmp_path):
    a, _ = _app(tmp_path)
    a.show_next_file()
    assert a.current_file_path.endswith('b.txt')
    assert 'linea de B' in a.line_ring.lines
    assert 'linea de A uno' not in a.line_ring.lines


def test_enter_after_switching_never_overwrites_the_new_file(tmp_path):
    a, i = _app(tmp_path)
    a.show_next_file()
    a._f1_commit_line('nueva')
    b = (i / 'b.txt').read_text(encoding='utf-8')
    assert 'linea de B' in b
    assert 'nueva' in b
    assert 'linea de A uno' not in b
    a_txt = (i / 'a.txt').read_text(encoding='utf-8')
    assert 'linea de A uno' in a_txt and 'nueva' not in a_txt


def test_switching_back_finds_the_old_file_intact(tmp_path):
    a, i = _app(tmp_path)
    a.show_next_file()
    a.show_previous_file()
    assert a.current_file_path.endswith('a.txt')
    assert 'linea de A uno' in a.line_ring.lines


def test_f1_shows_the_new_files_current_line(tmp_path):
    a, _ = _app(tmp_path)
    a.show_next_file()
    shown = a.entry.setText.call_args[0][0]
    assert shown == a.line_ring.current() or (shown == '' and a.line_ring.current() == '.')
