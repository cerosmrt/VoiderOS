"""El panel: el elegido en blanco, el resto en gris.

Primero los grises estaban hardcodeados y oscuros —el más tenue, 45 sobre 255—
y el panel no se leía. Lo pasé a atenuar por ALPHA, que es como se atenúa el
resto de la interfaz. Pero Federico lo miró y pidió otra cosa: "me gustaria que
se vea asi con highlighted in white and the rest in gray".

O sea DOS NIVELES, no un degradado: el elegido a tinta plena y todo lo demás en
un gris parejo. Y se hace bajando el COLOR y no el alpha — así el texto queda
opaco y nítido incluso sobre un fondo transparente, en vez de dejar pasar el
escritorio a través de las letras.

El alpha sigue siendo el del eje TINTA, para que Ctrl+Shift+± atenúe el panel
junto con el círculo y las letras en vez de dejarlo como una isla.
"""
import pytest

pytest.importorskip("PyQt6")
from PyQt6.QtGui import QColor

from widgets import picker_shade


BLANCO = QColor(255, 255, 255, 255)


def test_the_selected_one_is_full_ink():
    c = picker_shade(0, BLANCO)
    assert (c.red(), c.green(), c.blue()) == (255, 255, 255)
    assert c.alpha() == 255


def test_the_rest_is_grey():
    """Gris de verdad, no blanco translúcido."""
    for d in (1, 2, 3, 5, 20):
        c = picker_shade(d, BLANCO)
        assert c.red() < 200, f'a {d} sigue siendo casi blanco ({c.red()})'
        assert c.red() > 90, f'a {d} queda demasiado oscuro ({c.red()})'


def test_the_grey_is_uniform():
    """Dos niveles, no un degradado: todo lo que no es el elegido va igual."""
    valores = {picker_shade(d, BLANCO).red() for d in (1, 2, 3, 8, 30)}
    assert len(valores) == 1, f'hay más de un gris: {valores}'


def test_it_stays_opaque():
    """Se baja el color, no el alpha: sobre un fondo transparente el texto no
    tiene que dejar pasar el escritorio."""
    for d in (0, 1, 7):
        assert picker_shade(d, BLANCO).alpha() == 255


def test_it_follows_the_ink_axis():
    """Ctrl+Shift+± tiene que atenuar el panel como atenúa todo lo demás."""
    tenue = QColor(255, 255, 255, 100)
    assert picker_shade(0, tenue).alpha() == 100
    assert picker_shade(3, tenue).alpha() == 100


def test_the_ink_colour_is_respected():
    rojo = QColor(255, 40, 40, 255)
    assert picker_shade(0, rojo).getRgb()[:3] == (255, 40, 40)
    gris = picker_shade(2, rojo)
    assert gris.red() < 255 and gris.green() < 40 or gris.green() == 0


def test_distance_is_symmetric():
    assert picker_shade(3, BLANCO).red() == picker_shade(-3, BLANCO).red()
