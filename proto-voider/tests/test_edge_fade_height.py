"""El degradado de F1 cubre todo el alto del círculo, no el del renglón.

Federico: "input degrade too short for font. look how long letters dont get
covered by the degareding black... it should draw in the entire circle since if
i change the font size what would happen?".

El degradado se pintaba sobre el RECTÁNGULO DEL ENTRY, que mide lo que mide el
QLineEdit. Los glifos altos —las colas de las j, las q, las mayúsculas grandes—
se salen de esa caja y quedaban sin apagar. Y el problema de fondo es el que él
marcó: la altura dependía del tamaño de fuente, así que con otro tamaño se
rompía de otra forma.

Ahora el degradado va de arriba a abajo de la vista. Es horizontal —negro contra
el borde, transparente hacia el centro— así que estirarlo en vertical no cambia
el efecto: sólo deja de tener una altura que adivinar. El tamaño de fuente deja
de importar, que era el punto.
"""
import pytest

pytest.importorskip("PyQt6")
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QPixmap, QColor

from views import EdgeFade


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


_vivos = []
LADO = 800
R = LADO // 2 - EdgeFade.CIRCLE_INSET          # 365
CX = CY = LADO // 2


def _pintar(qapp, span=(100, 600)):
    """Pinta la capa sobre blanco y devuelve la imagen."""
    f = EdgeFade()
    f.resize(LADO, LADO)
    x, w = span
    if w > 0:
        f.set_fade_span(x, w)
    else:
        f.clear_fade()
    _vivos.append(f)
    pm = QPixmap(LADO, LADO)
    pm.fill(QColor(255, 255, 255))
    f.render(pm)
    return pm.toImage()


def _gris(img, x, y):
    return QColor(img.pixel(x, y)).red()


def _dentro_del_circulo(x, y):
    return (x - CX) ** 2 + (y - CY) ** 2 < (R - 10) ** 2


# ── el degradado llega arriba y abajo ────────────────────────────────────────

def test_it_covers_above_the_line(qapp):
    """El punto (300, 250) está DENTRO del círculo pero muy por encima del
    renglón. Antes quedaba sin pintar: ahí asomaban las letras."""
    assert _dentro_del_circulo(150, 250)
    img = _pintar(qapp)
    assert _gris(img, 150, 250) < 90, 'arriba del renglón no se apaga'


def test_it_covers_below_the_line(qapp):
    assert _dentro_del_circulo(150, 550)
    img = _pintar(qapp)
    assert _gris(img, 150, 550) < 90, 'abajo del renglón no se apaga'


def test_the_centre_stays_clear(qapp):
    """La gracia del degradado: en el centro se lee limpio."""
    img = _pintar(qapp)
    assert _gris(img, CX + 150, CY) > 200


def test_the_left_edge_is_the_darkest(qapp):
    img = _pintar(qapp)
    assert _gris(img, 110, CY) < _gris(img, 300, CY) < _gris(img, CX + 150, CY)


# ── y sigue sin depender del tamaño de fuente ────────────────────────────────

def test_the_api_has_no_height_at_all():
    """Era el reclamo de fondo: "si cambio el tamaño de fuente, qué pasaría".
    La respuesta es nada, y se garantiza en la firma: no hay dónde pasar un
    alto. Un test que le pasara uno y comprobara que no cambia nada sería
    trivialmente cierto — esto fija la razón por la que lo es."""
    import inspect
    params = list(inspect.signature(EdgeFade.set_fade_span).parameters)
    assert params == ['self', 'x', 'w'], params


def test_the_gradient_spans_the_whole_view():
    """Y el rectángulo que se pinta va de 0 al alto de la vista."""
    import inspect
    src = inspect.getsource(EdgeFade.paintEvent)
    assert 'QRect(x, 0, w, self.height())' in src


# ── apagarlo sigue siendo posible ────────────────────────────────────────────

def test_no_span_means_no_gradient(qapp):
    """Fuera de typewriter no hay degradado: el texto va centrado y no corre
    hacia el borde, así que no hay nada que apagar."""
    img = _pintar(qapp, span=(0, 0))
    assert _gris(img, 110, CY) > 200, 'se está pintando sin que nadie lo pida'


def test_the_circle_is_still_drawn_with_no_gradient(qapp):
    """Apagar el degradado no puede apagar el círculo ni el recorte."""
    img = _pintar(qapp, span=(0, 0))
    assert _gris(img, 5, 5) < 120, 'el afuera del círculo dejó de pintarse'
