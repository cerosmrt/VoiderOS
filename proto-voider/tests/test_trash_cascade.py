"""El tacho de dos vías.

Antes esto era una cascada de tres niveles: otro archivo → 0.txt → trash.txt →
borrado para siempre. Ahora es un tacho con vuelta:

    cualquier archivo (0.txt incluido)  → trash.txt
    trash.txt                           → 0.txt

Nada se pierde por apretar una tecla. Ctrl+Delete / Ctrl+Backspace en F2.
"""
import os
import types
import tempfile

import pytest
from line_ring import LineRing
from helpers import make_ring_app


def _trash_app(lines, is_zero=False, is_trash=False, tmp=None):
    """Mock app viendo 0.txt, trash.txt, u otro archivo."""
    from new_interface import FullscreenCircleApp

    tmp = tmp or tempfile.mkdtemp()
    f0 = os.path.join(tmp, '0.txt')
    trash = os.path.join(tmp, 'I', 'trash.txt')
    other = os.path.join(tmp, 'other.txt')
    os.makedirs(os.path.join(tmp, 'I'), exist_ok=True)

    with open(f0, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')

    app = make_ring_app(list(lines), tmp_file=f0)
    app.line_ring = LineRing(list(lines))
    app.f1_file = f0
    app._trash_file = trash

    if is_zero:
        app.current_file_path = f0
    elif is_trash:
        with open(trash, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines) + '\n')
        app.current_file_path = trash
    else:
        with open(other, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines) + '\n')
        app.current_file_path = other

    for name in ('_delete_line_to_trash',):
        setattr(app, name, types.MethodType(getattr(FullscreenCircleApp, name), app))

    app.auto_save_circular = lambda: None
    app.circular_view._offset = 0.0
    app.circular_view.editor.setCursorPosition = lambda _: None

    return app, f0, trash


class TestTrashBin:

    def test_delete_from_zero_goes_to_trash(self, tmp_path):
        lines = ['Hello world.', '.', 'Keep this.']
        app, f0, trash = _trash_app(lines, is_zero=True, tmp=str(tmp_path))
        app.line_ring.index = 0
        app._delete_line_to_trash()
        assert 'Hello world.' in open(trash, encoding='utf-8').read()

    def test_delete_from_zero_removes_from_ring(self, tmp_path):
        lines = ['Hello world.', '.', 'Keep this.']
        app, f0, trash = _trash_app(lines, is_zero=True, tmp=str(tmp_path))
        app.line_ring.index = 0
        app._delete_line_to_trash()
        assert 'Hello world.' not in app.line_ring.lines

    def test_delete_from_another_file_goes_straight_to_trash(self, tmp_path):
        """El cambio: ya no hace escala en 0.txt. Va directo al tacho."""
        lines = ['From book.', '.', 'Stay.']
        app, f0, trash = _trash_app(lines, is_zero=False, tmp=str(tmp_path))
        before = open(f0, encoding='utf-8').read()   # el fixture ya lo escribió
        app.line_ring.index = 0
        app._delete_line_to_trash()
        assert 'From book.' in open(trash, encoding='utf-8').read()
        assert open(f0, encoding='utf-8').read() == before, '0.txt no se toca'

    def test_delete_from_trash_restores_to_zero(self, tmp_path):
        """La vuelta: desde la basura la línea revive en 0.txt, no se borra."""
        lines = ['Trashed line.', '.', 'Another.']
        app, f0, trash = _trash_app(lines, is_trash=True, tmp=str(tmp_path))
        app.line_ring.index = 0
        app._delete_line_to_trash()
        assert 'Trashed line.' in open(f0, encoding='utf-8').read()
        assert 'Trashed line.' not in app.line_ring.lines

    def test_nothing_is_ever_deleted_forever(self, tmp_path):
        """Ni un solo camino termina en la nada: siempre queda escrito en algún lado."""
        for kw in ({'is_zero': True}, {'is_trash': True}, {'is_zero': False}):
            d = tmp_path / str(kw)
            d.mkdir()
            lines = ['unica.', '.', 'otra.']
            app, f0, trash = _trash_app(lines, tmp=str(d), **kw)
            app.line_ring.index = 0
            app._delete_line_to_trash()
            landed = ''
            for p in (f0, trash):
                if os.path.exists(p):
                    landed += open(p, encoding='utf-8').read()
            assert 'unica.' in landed, f"se perdió con {kw}"

    def test_delete_dot_line_from_zero_goes_to_trash(self, tmp_path):
        lines = ['.', 'Line.']
        app, f0, trash = _trash_app(lines, is_zero=True, tmp=str(tmp_path))
        app.line_ring.index = 0
        app._delete_line_to_trash()
        assert '.' in open(trash, encoding='utf-8').read()

    def test_the_last_line_is_never_removed(self, tmp_path):
        app, f0, trash = _trash_app(['sola.'], is_zero=True, tmp=str(tmp_path))
        app.line_ring.index = 0
        app._delete_line_to_trash()
        assert app.line_ring.lines == ['sola.']
