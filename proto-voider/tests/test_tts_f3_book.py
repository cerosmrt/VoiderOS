"""Ctrl+T en el libro entero (Enter sobre un punto en F3 → vista 9).

Ctrl+T prendía la voz pero _tts_on_view no conocía la vista 9: quedaba
activa y muda. Ahora lee como F2 — renglón por renglón, saltando los puntos
y los títulos de capítulo (que la navegación también saltea) — y se detiene
al final del libro en vez de volver a empezar.
"""
import types
from unittest.mock import MagicMock

import pytest

pytest.importorskip("PyQt6")
from line_ring import LineRing


def _app(lines, index, headers):
    from new_interface import FullscreenCircleApp as App

    class _A:
        pass
    a = _A()
    a.tts_active = True
    a.current_view = 9
    a.book_concat_ring = LineRing(lines)
    a.book_concat_ring.index = index
    a._book_concat_header_indices = set(headers)
    a.book_concat_view = MagicMock()
    a._tts_process = None
    a._tts_timer = MagicMock()
    a._tts_stop = MagicMock()
    a._tts_speak = MagicMock()
    a._tts_prefetch = MagicMock()
    for n in ('_tts_on_view', '_tts_poll', '_book_concat_next_index'):
        setattr(a, n, types.MethodType(getattr(App, n), a))
    return a


LIBRO = ['.', 'CAP UNO', 'uno a.', 'uno b.', '.', 'CAP DOS', 'dos a.', '.']
TITULOS = [1, 5]


def test_ctrl_t_en_el_libro_lee_el_renglon_actual_y_arranca_el_avance():
    a = _app(LIBRO, 2, TITULOS)
    a._tts_on_view(9)
    a._tts_speak.assert_called_once_with('uno a.')
    a._tts_timer.start.assert_called_once()


def test_al_terminar_un_renglon_pasa_al_siguiente_y_lo_muestra():
    a = _app(LIBRO, 2, TITULOS)
    a._tts_poll()
    assert a.book_concat_ring.index == 3
    a._tts_speak.assert_called_once_with('uno b.')
    a.book_concat_view.editor.setText.assert_called_with('uno b.')


def test_salta_puntos_y_titulos_de_capitulo():
    a = _app(LIBRO, 3, TITULOS)
    a._tts_poll()
    assert a.book_concat_ring.index == 6
    a._tts_speak.assert_called_once_with('dos a.')


def test_al_final_del_libro_se_calla_y_no_vuelve_a_empezar():
    a = _app(LIBRO, 6, TITULOS)
    a._tts_poll()
    a._tts_speak.assert_not_called()
    assert a.tts_active is False
    assert a.book_concat_ring.index == 6
