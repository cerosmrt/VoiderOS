"""Alt+Shift+↑/↓ en F2: duplicar y posicionar la copia en la dirección de la
flecha.

Federico: "alt + shift + arrow up and down, should duplicate and possition it
ni the direction of the arrow (in f2 a line, in f3 a chapter)".

El alcance es el de siempre — sobre una línea, esa línea; sobre un punto, el
párrafo entero que ese punto abre (misma regla que Ctrl+C, Ctrl+Shift+E, el
envío a otro capítulo). El cursor sigue a la copia, que es el bloque que
acaba de aparecer del lado al que apuntaste: Arriba la copia queda ANTES del
original; Abajo, DESPUÉS.

La combinación estaba libre: el editor sólo intercepta Up/Down sin modificador
o con Ctrl — Alt y Alt+Shift no los toca, así que llegan tal cual al router
(a diferencia de Left/Right, que el editor SÍ absorbe para mover la palabra /
abrir el panel de envío).
"""
import types
import pytest
from unittest.mock import MagicMock

from line_ring import LineRing
from helpers import make_ring_app


def _app(lines, index, tmp_path, para_focus=False, focus_content=None):
    from new_interface import FullscreenCircleApp
    f = tmp_path / '0.txt'
    f.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    app = make_ring_app(list(lines), tmp_file=str(f))
    app.line_ring = LineRing(list(lines))
    app.line_ring.index = index
    app._para_focus = para_focus
    app._para_focus_content = focus_content or []
    for name in ('_doc_duplicate', '_get_focus_dot_idx'):
        if hasattr(FullscreenCircleApp, name):
            setattr(app, name, types.MethodType(getattr(FullscreenCircleApp, name), app))
    app.load_doc_lines = MagicMock()
    app._doc_show_editor = MagicMock()
    app._apply_editor_style = MagicMock()
    return app, f


def _read(p):
    return p.read_text(encoding='utf-8').splitlines()


# ── sobre una línea ──────────────────────────────────────────────────────────

def test_down_inserts_the_copy_right_after(tmp_path):
    app, f = _app(['.', 'uno.', 'dos.'], 1, tmp_path)
    app._doc_duplicate(1)
    assert app.line_ring.lines == ['.', 'uno.', 'uno.', 'dos.']


def test_up_inserts_the_copy_right_before(tmp_path):
    app, f = _app(['.', 'uno.', 'dos.'], 1, tmp_path)
    app._doc_duplicate(-1)
    assert app.line_ring.lines == ['.', 'uno.', 'uno.', 'dos.']


def test_down_the_cursor_follows_the_copy_below(tmp_path):
    app, f = _app(['.', 'uno.', 'dos.'], 1, tmp_path)
    app._doc_duplicate(1)
    assert app.line_ring.index == 2
    assert app.line_ring.current() == 'uno.'


def test_up_the_cursor_follows_the_copy_above(tmp_path):
    """La copia queda ARRIBA — el cursor se queda en el mismo índice de antes,
    que ahora apunta a la copia (el original se corrió un lugar)."""
    app, f = _app(['.', 'uno.', 'dos.'], 1, tmp_path)
    app._doc_duplicate(-1)
    assert app.line_ring.index == 1
    assert app.line_ring.current() == 'uno.'
    assert app.line_ring.lines[2] == 'uno.'   # el original, corrido


def test_it_reaches_disk(tmp_path):
    app, f = _app(['.', 'uno.'], 1, tmp_path)
    app._doc_duplicate(1)
    assert _read(f) == ['.', 'uno.', 'uno.']


# ── sobre un punto: el párrafo entero ────────────────────────────────────────

def test_on_a_dot_the_whole_paragraph_duplicates(tmp_path):
    app, f = _app(['.', 'uno.', 'dos.', '.', 'otro.'], 0, tmp_path)
    app._doc_duplicate(1)
    assert app.line_ring.lines == [
        '.', 'uno.', 'dos.', '.', 'uno.', 'dos.', '.', 'otro.']


def test_the_dot_travels_with_its_paragraph(tmp_path):
    """La copia lleva SU propio punto — no se duplica sólo el contenido."""
    app, f = _app(['.', 'uno.', '.', 'otro.'], 0, tmp_path)
    app._doc_duplicate(-1)
    assert app.line_ring.lines.count('.') == 3


def test_up_on_a_dot_the_copy_is_first(tmp_path):
    app, f = _app(['.', 'uno.', 'dos.', '.', 'otro.'], 0, tmp_path)
    app._doc_duplicate(-1)
    assert app.line_ring.lines == [
        '.', 'uno.', 'dos.', '.', 'uno.', 'dos.', '.', 'otro.']
    assert app.line_ring.index == 0    # parado en el punto de la copia


def test_the_paragraph_scope_never_crosses_into_the_next(tmp_path):
    app, f = _app(['.', 'uno.', '.', 'dos.', 'tres.'], 0, tmp_path)
    app._doc_duplicate(1)
    assert app.line_ring.lines == [
        '.', 'uno.', '.', 'uno.', '.', 'dos.', 'tres.']


def test_an_empty_paragraph_still_duplicates_its_dot(tmp_path):
    """Un párrafo vacío (el punto de arriba es seguido por otro punto) igual
    tiene algo que duplicar: el separador mismo. De dos puntos pasa a tres."""
    app, f = _app(['.', '.', 'algo.'], 0, tmp_path)
    app._doc_duplicate(1)
    assert app.line_ring.lines == ['.', '.', '.', 'algo.']


# ── conviviendo con el foco de párrafo (Enter sobre un punto) ───────────────

def test_inside_para_focus_the_line_stays_in_focus(tmp_path):
    """Duplicar una línea adentro de un párrafo enfocado: la copia también
    queda dentro del foco — no se cae afuera de lo resaltado/navegable."""
    app, f = _app(['.', 'uno.', 'dos.', 'tres.'], 1, tmp_path,
                  para_focus=True, focus_content=[1, 2, 3])
    app.circular_view.focus_indices = {0, 1, 2, 3}
    app._doc_duplicate(1)
    assert app.line_ring.lines == ['.', 'uno.', 'uno.', 'dos.', 'tres.']
    # El original ('uno.') estaba en 1, ahora esta en 2; la copia entra al foco.
    assert set(app._para_focus_content) == {1, 2, 3, 4}


def test_inside_para_focus_indices_after_the_insert_point_shift(tmp_path):
    app, f = _app(['.', 'uno.', 'dos.', 'tres.'], 1, tmp_path,
                  para_focus=True, focus_content=[1, 2, 3])
    app.circular_view.focus_indices = {0, 1, 2, 3}
    app._doc_duplicate(1)
    # 'dos.' estaba en indice 2, ahora en 3; 'tres.' de 3 a 4.
    assert 3 in app._para_focus_content and 4 in app._para_focus_content


# ── el cableado ──────────────────────────────────────────────────────────────

def test_the_keys_are_wired_in_f2():
    import inspect
    from key_router_mixin import KeyRouterMixin
    src = inspect.getsource(KeyRouterMixin._handle_f2_keys)
    assert '_doc_duplicate' in src


def test_alt_shift_up_down_reach_the_router_unclaimed_by_the_editor(qapp_ke):
    """A diferencia de Left/Right (que el editor absorbe para mover la palabra
    / abrir el panel de envío), Alt+Shift+Up/Down tienen que llegar sin que el
    editor los acepte primero — así burbujean hasta _handle_f2_keys."""
    from PyQt6.QtGui import QKeyEvent
    from PyQt6.QtCore import Qt, QEvent
    from circular_view import CustomLineEdit

    le = CustomLineEdit()
    mods = Qt.KeyboardModifier.AltModifier | Qt.KeyboardModifier.ShiftModifier
    for key in (Qt.Key.Key_Up, Qt.Key.Key_Down):
        ev = QKeyEvent(QEvent.Type.KeyPress, key, mods, '')
        le.keyPressEvent(ev)
        assert not ev.isAccepted(), f'{key} quedó atrapada en el editor'


@pytest.fixture(scope='module')
def qapp_ke():
    from PyQt6.QtWidgets import QApplication
    yield QApplication.instance() or QApplication([])
