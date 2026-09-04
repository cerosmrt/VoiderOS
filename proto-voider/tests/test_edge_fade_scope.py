"""La capa del círculo es de F1 y de nadie más.

La regresión: se mostraba al entrar a F1 pero nadie la escondía al salir, así
que quedaba encima de F2, F3 y F4 recortándolas a un círculo y comiéndose el
texto. Federico lo vio en las tres vistas.

Los tests de test_edge_fade.py no podían agarrarlo: prueban el widget solo,
nunca su ciclo de vida al cambiar de vista. Éste mira el código que decide.
"""
import inspect
import re

import pytest

pytest.importorskip("PyQt6")

from new_interface import FullscreenCircleApp as App


def test_al_cambiar_de_vista_la_capa_se_esconde():
    """switch_to_view tiene que esconderla para cualquier vista que no sea F1."""
    src = inspect.getsource(App.switch_to_view)
    assert "_edge_fade" in src, "switch_to_view ni se entera de la capa"
    assert "hide()" in src, "la muestra pero nunca la esconde"


def test_la_esconde_antes_de_dibujar_la_vista_nueva():
    """Si escondiera al final, alcanzaría a taparse un frame de la vista nueva."""
    src = inspect.getsource(App.switch_to_view)
    linea_fade = next(i for i, l in enumerate(src.splitlines()) if "_edge_fade" in l)
    # Antes de que empiece a armar las vistas concretas.
    linea_vistas = next(
        (i for i, l in enumerate(src.splitlines()) if "view_index == 0" in l),
        len(src.splitlines()),
    )
    assert linea_fade < linea_vistas, "la esconde demasiado tarde"


def test_solo_se_muestra_en_f1():
    """_reposition_entry es la única que la muestra, y sólo con current_view 0."""
    src = inspect.getsource(App._reposition_entry)
    assert "current_view == 0" in src, "se mostraría fuera de F1"
    mostrar = [l for l in src.splitlines() if "fade.show()" in l]
    assert len(mostrar) == 1, f"se muestra desde varios lados: {mostrar}"
