"""El panel de capítulos tiene que leerse.

Federico: "look its there the nav but it looks so gray you can barely see it".
Los grises estaban hardcodeados y eran oscuros — el más tenue, 45 sobre 255 —
y además no seguían el eje de la TINTA, así que Ctrl+Shift+± no los tocaba
mientras el resto de la interfaz sí.

Ahora la escala sale de picker_shade(). Se atenúa por ALPHA y no bajando el
gris, que es como se atenúa todo el resto de la interfaz (el anillo de F2 hace
lo mismo con la distancia al centro). El color se mantiene: lo que baja es
cuánto tapa. Y el elegido va a tinta plena, con piso legible para los vecinos.
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


def test_the_neighbours_fade_but_stay_legible():
    """El problema era justamente éste: se iban a casi invisibles."""
    for d in (1, 2, 3, 5, 20):
        a = picker_shade(d, BLANCO).alpha()
        assert a >= 140, f'a {d} de distancia queda en alpha {a}, ilegible'


def test_they_fade_at_all():
    """Legibles, pero el elegido tiene que destacarse igual."""
    assert picker_shade(1, BLANCO).alpha() < picker_shade(0, BLANCO).alpha()
    assert picker_shade(3, BLANCO).alpha() <= picker_shade(1, BLANCO).alpha()


def test_the_colour_never_changes_only_how_much_it_covers():
    for d in (0, 1, 5):
        c = picker_shade(d, BLANCO)
        assert (c.red(), c.green(), c.blue()) == (255, 255, 255)


def test_it_follows_the_ink_axis():
    """Ctrl+Shift+± tiene que atenuar el panel como atenúa todo lo demás."""
    tenue = QColor(255, 255, 255, 100)
    assert picker_shade(0, tenue).alpha() == 100
    assert picker_shade(3, tenue).alpha() < 100


def test_the_ink_colour_is_respected():
    rojo = QColor(255, 40, 40, 255)
    c = picker_shade(0, rojo)
    assert (c.red(), c.green(), c.blue()) == (255, 40, 40)


def test_distance_is_symmetric():
    assert picker_shade(3, BLANCO).alpha() == picker_shade(-3, BLANCO).alpha()
