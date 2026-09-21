"""La entrada nueva de F3 no se puede comer una entrada real.

EL BUG, reproducido: _book_materialize_pending usaba book_ring.index EN EL
MOMENTO EN QUE CORRE, no el índice donde está el fantasma. Si algo movía el
índice mientras había una entrada nueva sin nombrar, materializar actuaba sobre
la entrada equivocada: la sacaba de la biblioteca — pero NO borraba el archivo.
Eso explica el síntoma que describió Federico, textual: "creo que solo
desaparece de la lista".

Los caminos que movían el índice sin asentar el fantasma: _book_rebase (Ctrl+0),
la búsqueda (Ctrl+F: _open_f3_search / _close_f3_search / _f3_search_confirm) y
los movimientos de bloque (Alt+↑/↓).

Dos arreglos, porque son dos problemas:
  * asentar el fantasma ANTES de mover el índice, en esos caminos. Ahí el texto
    del renglón todavía es el del fantasma, que es lo único que lo puede nombrar.
  * y una red: si igual llega a materializarse con el índice en otro lado, el
    fantasma se DESCARTA en vez de pisar lo que haya ahí. Con el índice movido,
    el texto del renglón ya es el de otra entrada — nombrarlo con eso sería
    inventar. Perder una entrada sin nombre es recuperable; perder una con
    nombre, no.
"""
import os
import types
import pytest
from unittest.mock import MagicMock

pytest.importorskip("PyQt6")
from PyQt6.QtWidgets import QApplication

import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_f3_undo import _f3_app, _read
from new_interface import FullscreenCircleApp as App


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


def _app(tmp_path):
    a = _f3_app(tmp_path, ['.', 'Uno.txt', 'Dos.txt', 'Tres.txt'])
    for n in ('_book_new_entry', '_book_settle_pending', '_book_materialize_pending',
              '_book_spawn_new_below', '_book_remove_entry', '_book_navigate',
              '_book_pending_index', '_book_rebase', '_open_f3_search',
              '_book_swap_up', '_book_swap_down'):
        if hasattr(App, n):
            setattr(a, n, types.MethodType(getattr(App, n), a))
    a._book_show_editor = MagicMock()
    a._book_refresh_editor = MagicMock()
    a._tts_cut = MagicMock()
    a._book_is_portal = lambda: False
    a.book_ring.index = 1
    return a


def _files(tmp_path):
    return sorted(p.name for p in (tmp_path / 'I').glob('*.txt'))


# ── la red: nunca comerse una entrada real ───────────────────────────────────

def test_a_moved_index_never_eats_a_real_entry(qapp, tmp_path):
    """El bug exacto: fantasma creado, índice movido, settle → se comía Dos.txt."""
    a = _app(tmp_path)
    a._book_new_entry()                       # fantasma en 2
    a.book_ring.index = 3                     # algo movió el índice
    a.book_view.editor.text.return_value = ''
    a._book_settle_pending()
    assert 'Dos.txt' in a._library_lines, 'se comió una entrada real'
    assert 'Tres.txt' in a._library_lines


def test_the_phantom_itself_is_discarded(qapp, tmp_path):
    """Y el fantasma no queda colgado en la lista."""
    a = _app(tmp_path)
    a._book_new_entry()
    a.book_ring.index = 3
    a.book_view.editor.text.return_value = ''
    a._book_settle_pending()
    assert '' not in a._library_lines


def test_no_file_is_ever_deleted_by_this(qapp, tmp_path):
    a = _app(tmp_path)
    antes = _files(tmp_path)
    a._book_new_entry()
    a.book_ring.index = 3
    a.book_view.editor.text.return_value = ''
    a._book_settle_pending()
    assert _files(tmp_path) == antes


def test_the_pending_flag_is_cleared(qapp, tmp_path):
    a = _app(tmp_path)
    a._book_new_entry()
    a.book_ring.index = 3
    a._book_settle_pending()
    assert not a._book_pending_new


# ── el caso normal sigue andando ─────────────────────────────────────────────

def test_naming_in_place_still_creates_the_file(qapp, tmp_path):
    a = _app(tmp_path)
    a._book_new_entry()
    a.book_view.editor.text.return_value = 'Nuevo'
    a._book_settle_pending()
    assert 'Nuevo.txt' in a._library_lines
    assert 'Nuevo.txt' in _files(tmp_path)


def test_an_unnamed_phantom_in_place_is_still_dropped(qapp, tmp_path):
    a = _app(tmp_path)
    a._book_new_entry()
    a.book_view.editor.text.return_value = ''
    a._book_settle_pending()
    assert a._library_lines == ['.', 'Uno.txt', 'Dos.txt', 'Tres.txt']


# ── los caminos que movían el índice ahora asientan primero ──────────────────

def test_the_search_settles_the_phantom_first(qapp, tmp_path):
    a = _app(tmp_path)
    a._f3_search_bar = MagicMock()
    a._f3_search_show_center = MagicMock()
    a._f3_display_ring = None
    a._book_new_entry()
    a.book_view.editor.text.return_value = 'DesdeLaBusqueda'
    a._open_f3_search()
    assert 'DesdeLaBusqueda.txt' in a._library_lines, \
        'la búsqueda se llevó puesto el fantasma sin guardarlo'
    assert not a._book_pending_new


def test_rebase_settles_the_phantom_first(qapp, tmp_path):
    a = _app(tmp_path)
    a._book_new_entry()
    a.book_view.editor.text.return_value = 'DesdeRebase'
    a._book_rebase()
    assert 'DesdeRebase.txt' in a._library_lines


def test_moving_a_block_settles_first(qapp, tmp_path):
    a = _app(tmp_path)
    a._book_new_entry()
    a.book_view.editor.text.return_value = 'DesdeAlt'
    a._book_swap_up()
    assert 'DesdeAlt.txt' in a._library_lines


# ── el localizador del fantasma ──────────────────────────────────────────────

def test_the_phantom_is_found_by_its_empty_name(qapp, tmp_path):
    a = _app(tmp_path)
    a._book_new_entry()
    assert a._book_pending_index() == 2


def test_with_no_phantom_there_is_no_index(qapp, tmp_path):
    a = _app(tmp_path)
    assert a._book_pending_index() is None


# ── nombre que ya existe: archivos separados, no el mismo archivo ───────────
# Federico nombró una entrada nueva "The Book of I", esperando que quedara
# vacía. Ya existía un capítulo con ese nombre — y lo que hacía
# _book_materialize_pending era registrar una SEGUNDA fila apuntando al MISMO
# archivo de siempre, sin avisar. Lo que vio al abrirla no era una entrada
# vacía: era el capítulo viejo, con todo lo que ya tenía escrito.
#
# Le pregunté si prefería que las dos filas compartieran el archivo (como el
# portal '0', que HOY es singleton — no existe ese mecanismo todavía) o que
# fueran dos archivos de verdad. Eligió dos archivos: "when i renamed the
# file, deleting the lines in one, would still delete on the other" — lo vivió
# él mismo, porque es el mismo archivo detrás de las dos filas.
#
# El arreglo: si el nombre tipeado ya existe como archivo, NO se reusa —
# se uniquifica igual que ya hace _book_do_merge / _book_duplicate
# ("<name>-2.txt", incrementando) y se crea un archivo nuevo, genuinamente
# vacío y separado. El título que se ve en F3 sale del archivo real, así que
# lleva el "-2" — eso es lo que le costó, y lo aceptó a cambio de que nunca
# más se comparta contenido sin querer.

def test_a_colliding_name_gets_its_own_separate_file(qapp, tmp_path):
    a = _app(tmp_path)
    a._book_new_entry()                          # fantasma en 2
    a.book_view.editor.text.return_value = 'Uno'  # choca con el Uno.txt real
    a._book_materialize_pending()
    assert 'Uno-2.txt' in a._library_lines


def test_the_existing_chapter_is_never_touched(qapp, tmp_path):
    a = _app(tmp_path)
    a._book_new_entry()
    a.book_view.editor.text.return_value = 'Uno'
    a._book_materialize_pending()
    assert _read(a._library_path_cache['Uno.txt']) == ['Uno']


def test_the_new_file_is_genuinely_empty(qapp, tmp_path):
    a = _app(tmp_path)
    a._book_new_entry()
    a.book_view.editor.text.return_value = 'Uno'
    a._book_materialize_pending()
    nuevo = a._library_path_cache['Uno-2.txt']
    assert os.path.exists(nuevo)
    assert _read(nuevo) == []


def test_the_two_are_never_the_same_file_on_disk(qapp, tmp_path):
    """El bug exacto que vivió: las dos filas apuntando al mismo path, así que
    borrar en una borraba en la otra. Acá tienen que ser paths distintos."""
    a = _app(tmp_path)
    a._book_new_entry()
    a.book_view.editor.text.return_value = 'Uno'
    a._book_materialize_pending()
    original = os.path.abspath(a._library_path_cache['Uno.txt'])
    nuevo = os.path.abspath(a._library_path_cache['Uno-2.txt'])
    assert original != nuevo


def test_a_second_collision_keeps_incrementing(qapp, tmp_path):
    a = _app(tmp_path)
    with open(os.path.join(str(tmp_path), 'I', 'Uno-2.txt'), 'w', encoding='utf-8') as f:
        f.write('ya usado\n')
    a._library_lines.append('Uno-2.txt')
    a.book_ring.lines.append('Uno-2')
    a._library_path_cache['Uno-2.txt'] = os.path.join(str(tmp_path), 'I', 'Uno-2.txt')
    a._book_new_entry()
    a.book_view.editor.text.return_value = 'Uno'
    a._book_materialize_pending()
    assert 'Uno-3.txt' in a._library_lines


def test_a_non_colliding_name_is_unaffected(qapp, tmp_path):
    """El caso normal — nombre que no existe todavía — sigue igual: se crea
    tal cual se tipeó, sin sufijo."""
    a = _app(tmp_path)
    a._book_new_entry()
    a.book_view.editor.text.return_value = 'Nombre Nuevo'
    a._book_materialize_pending()
    assert 'Nombre Nuevo.txt' in a._library_lines
    assert 'Nombre Nuevo-2.txt' not in a._library_lines
