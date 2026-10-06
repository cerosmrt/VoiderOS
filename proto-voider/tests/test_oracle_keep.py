"""F8 Enter: quedarse con la línea del oráculo.

El bug: Enter reemplazaba el anillo del lector de F6 por ['.', línea] SIN soltar
el libro abierto (o_reader_file seguía apuntando a él) y saltaba a F5. Si
después ibas a F6 y escribías, el guardado escribía esas dos líneas encima del
libro de O/ — que no tiene git.

Ahora hace lo que dice su nombre: la línea (como la hayas editado) entra en el
documento activo debajo de donde estabas, y sale otra tirada. El lector de F6
no se toca.
"""
import types
from unittest.mock import MagicMock

import pytest

pytest.importorskip("PyQt6")
from line_ring import LineRing


def _app(tmp_path, typed='una linea del oraculo'):
    from new_interface import FullscreenCircleApp as App

    class _A:
        pass
    a = _A()
    doc = tmp_path / 'doc.txt'
    doc.write_text('.\nprimera\nsegunda\n', encoding='utf-8')
    a.current_file_path = str(doc)
    a.line_ring = LineRing(['.', 'primera', 'segunda'])
    a.line_ring.index = 1
    a._undo = None
    a._ipc = None
    a.oracle_o_view = MagicMock()
    a.oracle_o_view.editor.text.return_value = typed
    a.o_reader_ring = LineRing(['.', 'l1', 'l2', 'l3'])
    a.o_reader_file = str(tmp_path / 'Libro.txt')
    a.transform_view = None
    a.switch_to_view = MagicMock()
    def _otra():
        # Igual que el real: ['.', línea] parado en la línea.
        a.oracle_o_ring = LineRing(['.', 'otra'])
        a.oracle_o_ring.index = 1
    a._refresh_oracle_o = MagicMock(side_effect=_otra)
    for n in ('_oracle_o_confirm', 'auto_save_circular', '_undo_capture',
              '_rescue_on_large_shrink', '_read_lines_or_none'):
        setattr(a, n, types.MethodType(getattr(App, n), a))
    return a, doc


def test_the_line_goes_into_the_document_below_the_cursor(tmp_path):
    a, doc = _app(tmp_path)
    a._oracle_o_confirm()
    assert a.line_ring.lines == ['.', 'primera', 'una linea del oraculo', 'segunda']
    assert a.line_ring.index == 2
    assert 'una linea del oraculo' in doc.read_text(encoding='utf-8')


def test_the_reader_and_its_book_are_left_alone(tmp_path):
    a, _ = _app(tmp_path)
    a._oracle_o_confirm()
    assert a.o_reader_ring.lines == ['.', 'l1', 'l2', 'l3']
    assert a.o_reader_file.endswith('Libro.txt')


def test_it_stays_in_f8_and_draws_another(tmp_path):
    a, _ = _app(tmp_path)
    a._oracle_o_confirm()
    a.switch_to_view.assert_not_called()
    a._refresh_oracle_o.assert_called_once()
    a.oracle_o_view.editor.setText.assert_called_with('otra')


def test_an_empty_line_does_nothing(tmp_path):
    a, doc = _app(tmp_path, typed='   ')
    a._oracle_o_confirm()
    assert a.line_ring.lines == ['.', 'primera', 'segunda']
    a._refresh_oracle_o.assert_not_called()
