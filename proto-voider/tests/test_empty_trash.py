"""Vaciar la basura: Ctrl+Delete sobre trash.txt en F3.

Es el último paso del tacho. Se podía tirar (Ctrl+Delete en F2) y recuperar
(Ctrl+Delete adentro de trash.txt), pero no vaciar.

Sobre cualquier otro capítulo, Ctrl+Delete manda las líneas a 0.txt y borra el
archivo. Sobre la basura eso sería justo lo contrario de vaciar: las líneas
volverían. Así que va sin escala — se borra y listo.

Sin diálogo de confirmación, decisión suya: la basura se abre y se lee antes,
así que la revisión ya es la confirmación, y esas líneas ya fueron descartadas
a propósito una vez. Igual no es irreversible: el undo de F3 guarda el archivo
antes de borrarlo, así que Ctrl+Z lo devuelve.
"""
import os
import sys
import types
import pytest
from unittest.mock import MagicMock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_f3_undo import _f3_app, _read


def _trash_app(tmp_path, trash_lines=('descartada uno.', 'descartada dos.')):
    app = _f3_app(tmp_path, ['.', 'Cap.txt', 'trash.txt'],
                  contents={'trash.txt': list(trash_lines),
                            'Cap.txt': ['algo.']})
    app._trash_file = app._library_path_cache['trash.txt']
    app.book_ring.index = 2                      # parado en la basura
    app.book_view.editor.text.return_value = 'trash'
    return app, app._trash_file


def test_emptying_deletes_the_file(tmp_path):
    app, trash = _trash_app(tmp_path)
    app._book_send_to_zero()
    assert not os.path.exists(trash)


def test_the_lines_do_not_come_back_to_zero(tmp_path):
    """El punto entero: vaciar es vaciar, no devolver."""
    app, trash = _trash_app(tmp_path)
    app._book_send_to_zero()
    zero = '\n'.join(_read(app.f1_file))
    assert 'descartada uno.' not in zero
    assert 'descartada dos.' not in zero


def test_it_leaves_the_library(tmp_path):
    app, trash = _trash_app(tmp_path)
    app._book_send_to_zero()
    assert 'trash.txt' not in app._library_lines


def test_another_chapter_still_goes_to_zero(tmp_path):
    """No romper el comportamiento normal: sólo la basura es especial."""
    app, trash = _trash_app(tmp_path)
    app.book_ring.index = 1                      # Cap.txt
    app.book_view.editor.text.return_value = 'Cap'
    app._book_send_to_zero()
    assert 'algo.' in '\n'.join(_read(app.f1_file))


def test_ctrl_z_brings_the_trash_back(tmp_path):
    """No pide confirmación, pero tampoco es irreversible."""
    app, trash = _trash_app(tmp_path)
    app._book_send_to_zero()
    assert not os.path.exists(trash)
    app._undo_apply()
    assert os.path.exists(trash)
    assert 'descartada uno.' in '\n'.join(_read(trash))


def test_an_already_empty_trash_still_gets_deleted(tmp_path):
    """Vaciar algo vacío no puede fallar ni dejar el archivo colgado."""
    app, trash = _trash_app(tmp_path, trash_lines=())
    open(trash, 'w').close()
    app._book_send_to_zero()
    assert not os.path.exists(trash)


def test_the_trash_comes_back_on_its_own(tmp_path):
    """Se regenera sola la próxima vez que se tire algo: _delete_line_to_trash
    hace makedirs + append, así que no hace falta recrearla al vaciar."""
    import inspect
    from new_interface import FullscreenCircleApp as App
    src = inspect.getsource(App._delete_line_to_trash)
    assert 'makedirs' in src and "'a'" in src
